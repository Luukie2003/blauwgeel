package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.ActivityTellenBinding
import org.json.JSONObject
import java.util.UUID

/** Tellen met de looplijst: eerst de bar, dan het voorraadhok, product voor product. Daarna een controlescherm met de
 * totalen (en wat opvallend afwijkt), en pas bij "Telling opslaan" verandert de voorraad. Het scherm volgt de looplijst
 * van de site: foto, geregistreerde voorraad, wat er verwacht wordt, de snelknoppen (0, −1, +1, +2, +1 krat), plus een
 * rekenmachine (3 kratten van 24 en 7 losse).
 *
 * Het tellen zelf gebeurt helemaal op het toestel: het volgende product staat er meteen, ook bij een slechte
 * verbinding. De stand gaat elke paar producten (en bij pauzeren) naar de site, in dezelfde vorm als de looplijst van
 * de site: verder gaan kan dus ook op een ander toestel of op de site. Lukt dat even niet, dan blijft de stand op het
 * toestel bewaard en gaat hij later mee.
 *
 * Elke telling heeft een eigen loop_id. Wordt hij op de site of een ander toestel afgebroken, opgeslagen of opnieuw
 * begonnen, dan zegt de site dat bij de volgende keer doorgeven (409, "afgebroken") en stopt de telling hier ook, in
 * plaats van hem op de site weer terug te zetten. Afbreken gaat ook naar de site als het scherm meteen sluit
 * (Achtergrond); zonder verbinding gebeurt dat zodra het weer kan.
 *
 * Een product scannen tijdens het tellen springt naar dat product. */
class TellenActivity : BasisActivity() {

    private class TelProduct(
        val id: Int,
        val naam: String,
        val categorie: String,
        val eenheid: String,
        val voorraad: Int,
        var verwacht: JSONObject?,
        val foto: String?,
        val besteleenheid: String?,
        val perBesteleenheid: Int,
    )

    private enum class Laag { LADEN, TELLEN, CONTROLE, KLAAR }

    private lateinit var b: ActivityTellenBinding
    private var producten: List<TelProduct> = emptyList()
    private var fase = "bar"
    private var index = 0
    private val bar = LinkedHashMap<String, String>()
    private val hok = LinkedHashMap<String, String>()
    private var waarde = ""
    private var wijzigingen = 0
    private var laag = Laag.LADEN
    private var controleWaarden = LinkedHashMap<String, Int>()
    private var opslaanId: String? = null
    private var tellingId: Int? = null
    /** Welke telling dit is, en of de site hem al eens kreeg (dan herkent die hem; anders is hij nieuw). */
    private var loopId = UUID.randomUUID().toString()
    private var opSite = false

    private val lokaal by lazy { getSharedPreferences("tellen", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityTellenBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.titel_tellen))

        Cijferpad.koppel(b.pad, waarde = { waarde }) {
            waarde = it
            toonWaarde()
        }
        b.volgendeKnop.setOnClickListener { volgende() }
        b.vorigeKnop.setOnClickListener { vorige() }
        // De snelknoppen van de looplijst op de site: 0 (en meteen door), −1, +1, +2 en +1 krat.
        b.snelNul.setOnClickListener {
            waarde = "0"
            volgende()
        }
        b.snelMin1.setOnClickListener { pasAan(-1) }
        b.snelPlus1.setOnClickListener { pasAan(1) }
        b.snelPlus2.setOnClickListener { pasAan(2) }
        b.snelKrat.setOnClickListener { pasAan(producten[index].perBesteleenheid) }
        b.rekenKnop.setOnClickListener {
            Rekenmachine.open(this, waarde) {
                waarde = it.toString()
                toonWaarde()
            }
        }
        b.pauzeerKnop.setOnClickListener { pauzeer() }
        b.stopKnop.setOnClickListener { vraagStoppen() }
        b.terugNaarTellenKnop.setOnClickListener {
            fase = "hok"
            index = producten.lastIndex
            toonLaag(Laag.TELLEN)
            toonProduct()
        }
        b.opslaanKnop.setOnClickListener { bevestig() }
        b.klaarKnop.setOnClickListener { finish() }
        b.bekijkKnop.setOnClickListener { tellingId?.let { TellingenActivity.open(this, it) } }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                when (laag) {
                    Laag.TELLEN -> pauzeer()
                    Laag.CONTROLE -> b.terugNaarTellenKnop.performClick()
                    else -> finish()
                }
            }
        })
        toonLaag(Laag.LADEN)
        laad()
    }

    override fun onPause() {
        super.onPause()
        if (laag == Laag.TELLEN) {
            bewaarLokaal()
            stuurStand()
        }
    }

    private fun toonLaag(nieuw: Laag) {
        laag = nieuw
        b.laden.isVisible = nieuw == Laag.LADEN
        b.telLaag.isVisible = nieuw == Laag.TELLEN
        b.controleLaag.isVisible = nieuw == Laag.CONTROLE
        b.klaarLaag.isVisible = nieuw == Laag.KLAAR
        b.voortgang.isVisible = nieuw == Laag.TELLEN
        when (nieuw) {
            Laag.CONTROLE -> zetBalkTitel(getString(R.string.titel_controleren))
            Laag.KLAAR -> { zetBalkTitel(getString(R.string.titel_tellen)); zetBalkSub(Sessie.naam) }
            else -> {}
        }
    }

    // ---------------------------------------------------------------- laden en hervatten

    private fun laad() {
        lifecycleScope.launch {
            val data = try {
                b.ladenTekst.setText(R.string.laden_producten)
                stuurWachtendeStop(applicationContext)
                Api.getJson(this@TellenActivity, "/api/app/tellen")
            } catch (f: Api.Fout) {
                toonFout(f)
                finish()
                return@launch
            }
            producten = data.getJSONArray("producten").objecten().map {
                TelProduct(
                    it.getInt("id"), it.getString("naam"), it.optString("categorie"), it.optString("eenheid"),
                    it.optInt("voorraad"), it.optJSONObject("verwacht"), it.tekstOfNull("foto_groot"),
                    it.tekstOfNull("besteleenheid"), it.optInt("per_besteleenheid", 1),
                )
            }
            Fotos.haalAlvast(this@TellenActivity, producten.take(4).map { it.foto })
            haalVerwachting()
            zetFotosKlaar()
            if (producten.isEmpty()) {
                melding(getString(R.string.niets_te_tellen), lang = true)
                finish()
                return@launch
            }
            val opSite = data.optJSONObject("stand")
            // Een stand op het toestel die de site nog niet kreeg (geen verbinding bij het pauzeren) gaat voor, als hij
            // van dezelfde persoon is en niet ouder dan de drie dagen die de site een looplijst bewaart.
            val opToestel = lokaal.getString("stand", null)?.let { JSONObject(it) }?.takeIf {
                it.optString("naam") == Sessie.naam && it.optBoolean("onverzonden") &&
                    System.currentTimeMillis() - it.optLong("tijd") < 3 * 24 * 3_600_000L
            }
            val stand = opToestel ?: opSite
            when {
                stand == null -> begin()
                !stand.isNull("review") -> {
                    zetStand(stand, vanSite = opToestel == null)
                    controleer()
                }
                else -> vraagVerder(stand, vanSite = opToestel == null)
            }
        }
    }

    /** Wat er ongeveer hoort te staan (het voorspelmodel): apart, want dat rekent op de server soms even. Je kunt al
     * tellen; de regel "verwacht" verschijnt zodra het binnen is. Lukt het niet, dan zonder verwachting. */
    private fun haalVerwachting() {
        lifecycleScope.launch {
            val verwacht = try {
                Api.getJson(this@TellenActivity, "/api/app/tellen/verwachting").optJSONObject("verwacht") ?: return@launch
            } catch (f: Api.Fout) {
                return@launch
            }
            for (p in producten) p.verwacht = verwacht.optJSONObject(p.id.toString())
            if (laag == Laag.TELLEN) producten.getOrNull(index)?.let { toonVerwacht(it) }
        }
    }

    /** Alle foto's van de looplijst op het toestel zetten, met de voortgang in de kopbalk ("Foto's 23/44"): daarna staat
     * elk product er meteen, ook bij een slechte verbinding. */
    private fun zetFotosKlaar() {
        Fotos.zetOpToestel(this, producten.map { it.foto }) { klaar, totaal ->
            if (isFinishing || isDestroyed) return@zetOpToestel
            zetBalkSub(if (klaar < totaal) getString(R.string.fotos_klaarzetten, klaar, totaal) else Sessie.naam)
        }
    }

    private fun vraagVerder(stand: JSONObject, vanSite: Boolean) {
        val faseNaam = getString(if (stand.optString("fase") == "hok") R.string.fase_hok else R.string.fase_bar)
        val nummer = stand.optInt("index") + 1
        AlertDialog.Builder(this)
            .setTitle(R.string.verder_tellen_titel)
            .setMessage(getString(R.string.verder_tellen_vraag, faseNaam, nummer, producten.size))
            .setCancelable(false)
            .setPositiveButton(R.string.verder) { _, _ ->
                zetStand(stand, vanSite)
                toonLaag(Laag.TELLEN)
                toonProduct()
            }
            .setNegativeButton(R.string.opnieuw_beginnen) { _, _ -> begin() }
            .show()
    }

    private fun zetStand(stand: JSONObject, vanSite: Boolean) {
        loopId = stand.tekstOfNull("loop_id") ?: UUID.randomUUID().toString()
        opSite = vanSite || stand.optBoolean("op_site")
        fase = if (stand.optString("fase") == "hok") "hok" else "bar"
        index = stand.optInt("index").coerceIn(0, producten.lastIndex)
        bar.clear()
        hok.clear()
        stand.optJSONObject("bar")?.let { j -> j.keys().forEach { bar[it] = j.optString(it) } }
        stand.optJSONObject("hok")?.let { j -> j.keys().forEach { hok[it] = j.optString(it) } }
    }

    private fun begin() {
        loopId = UUID.randomUUID().toString()
        opSite = false
        fase = "bar"
        index = 0
        bar.clear()
        hok.clear()
        opslaanId = null
        toonLaag(Laag.TELLEN)
        toonProduct()
        wijzigingen = 5 // meteen doorgeven: er loopt een telling
        bewaar()
    }

    // ---------------------------------------------------------------- tellen

    private val huidige get() = if (fase == "bar") bar else hok

    private fun toonProduct() {
        val p = producten[index]
        val bar = fase == "bar"
        zetBalkTitel(getString(R.string.titel_looplijst))
        zetBalkSub(getString(R.string.product_n_van_m, index + 1, producten.size))
        val stap = (if (bar) 0 else producten.size) + index
        b.voortgang.progress = (stap * 1000) / (producten.size * 2)
        b.faseLabel.setText(if (bar) R.string.bar_tellen else R.string.hok_tellen)
        b.faseLabel.setBackgroundResource(if (bar) R.drawable.fase_bar else R.drawable.fase_hok)
        b.faseLabel.setTextColor(getColor(if (bar) R.color.groen_tekst else R.color.oranje_balk))
        b.telBarGeteld.text = if (bar) "" else getString(R.string.bar_geteld, this.bar[p.id.toString()]?.ifEmpty { null } ?: "—", p.eenheid)
        Fotos.toon(b.telFoto, p.foto)
        b.telCategorie.text = p.categorie
        b.telNaam.text = p.naam
        b.telEenheid.text = p.eenheid
        b.telVoorraad.text = getString(R.string.geregistreerde_voorraad, p.voorraad, p.eenheid)
        toonVerwacht(p)
        b.snelKrat.isVisible = p.besteleenheid != null && p.perBesteleenheid > 1
        b.snelKrat.text = getString(R.string.plus_een_besteleenheid, p.besteleenheid ?: "", p.perBesteleenheid)
        waarde = huidige[p.id.toString()] ?: ""
        toonWaarde()
        b.vorigeKnop.isEnabled = !(bar && index == 0)
        b.vorigeKnop.alpha = if (b.vorigeKnop.isEnabled) 1f else 0.4f
        b.volgendeKnop.setText(
            when {
                index < producten.lastIndex -> R.string.volgende_pijl
                bar -> R.string.door_naar_hok
                else -> R.string.bekijken_en_bevestigen
            },
        )
        // De foto's van de volgende producten alvast ophalen, dan staan ze er meteen.
        Fotos.haalAlvast(this, producten.drop(index + 1).take(3).map { it.foto })
    }

    private fun toonVerwacht(p: TelProduct) {
        b.telVerwacht.text = p.verwacht?.let { v ->
            val laag = v.optInt("laag")
            val hoog = v.optInt("hoog")
            if (hoog > laag) getString(R.string.verwacht_nu_marge, v.optInt("verwacht"), p.eenheid, laag, hoog)
            else getString(R.string.verwacht_nu, v.optInt("verwacht"), p.eenheid)
        } ?: ""
        b.telVerwacht.isVisible = p.verwacht != null
    }

    private fun toonWaarde() {
        b.telWaarde.text = waarde.ifEmpty { "–" }
        b.telWaarde.setTextColor(getColor(if (waarde.isEmpty()) R.color.rand_licht else R.color.tekst))
    }

    private fun pasAan(stap: Int) {
        val nu = waarde.toIntOrNull() ?: 0
        waarde = maxOf(0, nu + stap).toString()
        toonWaarde()
    }

    private fun vraagStoppen() {
        AlertDialog.Builder(this)
            .setMessage(R.string.stoppen_vraag)
            .setPositiveButton(R.string.ja_afbreken) { _, _ -> stop() }
            .setNegativeButton(R.string.nee_verder_tellen, null)
            .show()
    }

    private fun legVast() {
        val sleutel = producten[index].id.toString()
        if (waarde.isEmpty()) huidige.remove(sleutel) else huidige[sleutel] = waarde
        wijzigingen++
    }

    private fun volgende() {
        legVast()
        if (index < producten.lastIndex) {
            index++
        } else if (fase == "bar") {
            fase = "hok"
            index = 0
            AlertDialog.Builder(this)
                .setTitle(R.string.bar_klaar_titel)
                .setMessage(R.string.bar_klaar_tekst)
                .setPositiveButton(R.string.ok, null)
                .show()
        } else {
            bewaar()
            controleer()
            return
        }
        toonProduct()
        bewaar()
    }

    private fun vorige() {
        legVast()
        if (index > 0) {
            index--
        } else if (fase == "hok") {
            fase = "bar"
            index = producten.lastIndex
        }
        toonProduct()
        bewaar()
    }

    override fun bijScan(code: String) {
        if (laag != Laag.TELLEN) return super.bijScan(code)
        val treffer = Catalogus.opBarcode(code)
        val positie = treffer?.let { t -> producten.indexOfFirst { it.id == t.product.id } } ?: -1
        tril()
        if (positie < 0) {
            melding(getString(if (treffer == null) R.string.scan_onbekend_tellen else R.string.scan_telt_niet_mee))
            return
        }
        legVast()
        index = positie
        toonProduct()
        bewaar()
    }

    override fun vulMenu(menu: Menu) {
        if (laag != Laag.TELLEN) return
        menu.add(0, 101, 1, R.string.naar_product)
    }

    override fun bijMenu(id: Int): Boolean {
        if (id != 101) return false
        kiesProduct()
        return true
    }

    private fun kiesProduct() {
        val namen = producten.mapIndexed { i, p ->
            val ingevuld = huidige[p.id.toString()]
            (if (ingevuld != null) "✓ " else "") + p.naam + (ingevuld?.let { "  ($it)" } ?: "")
        }
        AlertDialog.Builder(this)
            .setTitle(getString(if (fase == "bar") R.string.fase_bar else R.string.fase_hok))
            .setItems(namen.toTypedArray()) { _, i ->
                legVast()
                index = i
                toonProduct()
                bewaar()
            }
            .show()
    }

    private fun pauzeer() {
        legVast()
        wijzigingen = 5
        bewaar()
        melding(getString(R.string.gepauzeerd))
        finish()
    }

    /** Afbreken: weg op het toestel en op de site. Het scherm sluit meteen; het bericht aan de site gaat op de
     * achtergrond, en zonder verbinding de volgende keer dat je gaat tellen (stuurWachtendeStop). */
    private fun stop() {
        laag = Laag.KLAAR // anders bewaart onPause de stand meteen weer
        lokaal.edit().remove("stand").putString("stoppen", loopId).apply()
        stopOpAchtergrond(applicationContext)
        melding(getString(R.string.gestopt))
        finish()
    }

    /** De telling is ergens anders afgebroken, opgeslagen of opnieuw begonnen: hier ook stoppen. */
    private fun afgebroken(melding: String?) {
        laag = Laag.KLAAR
        lokaal.edit().remove("stand").apply()
        if (isFinishing) return
        tril(150)
        AlertDialog.Builder(this)
            .setTitle(R.string.telling_afgebroken_titel)
            .setMessage(melding ?: getString(R.string.telling_afgebroken))
            .setCancelable(false)
            .setPositiveButton(R.string.ok) { _, _ -> finish() }
            .show()
    }

    // ---------------------------------------------------------------- de stand bewaren

    private fun standJson(onverzonden: Boolean) = JSONObject()
        .put("fase", fase).put("index", index).put("bar", JSONObject(bar as Map<*, *>)).put("hok", JSONObject(hok as Map<*, *>))
        .put("naam", Sessie.naam).put("onverzonden", onverzonden).put("tijd", System.currentTimeMillis())
        .put("loop_id", loopId).put("op_site", opSite)

    private fun bewaarLokaal(onverzonden: Boolean = true) {
        lokaal.edit().putString("stand", standJson(onverzonden).toString()).apply()
    }

    /** Altijd op het toestel; elke vijf wijzigingen ook naar de site. */
    private fun bewaar() {
        bewaarLokaal()
        if (wijzigingen >= 5) stuurStand()
    }

    /** De stand naar de site; ook als het scherm net sluit (pauzeren), dus op de achtergrond. */
    private fun stuurStand() {
        wijzigingen = 0
        val stand = standJson(false)
        val body = JSONObject(stand.toString()).put("nieuw", !opSite)
        val app = applicationContext
        val prefs = lokaal
        Achtergrond.scope.launch {
            try {
                Api.post(app, "/api/app/tellen/stand", body, herhaalbaar = true)
                // Doorgegeven: bij de volgende start telt de stand van de site (die kan intussen verder zijn).
                opSite = true
                prefs.edit().putString("stand", stand.put("op_site", true).toString()).apply()
            } catch (f: Api.Fout) {
                runOnUiThread {
                    when {
                        f.code == "afgebroken" -> afgebroken(f.message)
                        f.soort == Api.Soort.NIET_INGELOGD && !isFinishing -> toonFout(f)
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- controleren en opslaan

    private fun controleer() {
        toonLaag(Laag.LADEN)
        bezig {
            try {
                val body = JSONObject().put("bar", JSONObject(bar as Map<*, *>)).put("hok", JSONObject(hok as Map<*, *>))
                    .put("loop_id", loopId).put("nieuw", !opSite)
                val regels = Api.post(this, "/api/app/tellen/controleren", body, herhaalbaar = true).getJSONArray("regels").objecten()
                opSite = true
                lokaal.edit().putString("stand", standJson(false).toString()).apply()
                toonControle(regels)
            } catch (f: Api.Fout) {
                if (f.code == "afgebroken") return@bezig afgebroken(f.message)
                toonLaag(Laag.TELLEN)
                toonProduct()
                throw f
            }
        }
    }

    private fun toonControle(regels: List<JSONObject>) {
        controleWaarden.clear()
        b.controleLijst.removeAllViews()
        for (r in regels) {
            val id = r.getInt("product_id").toString()
            controleWaarden[id] = r.getInt("totaal")
            b.controleLijst.addView(controleRegel(r, id))
        }
        zetBalkSub(resources.getQuantityString(R.plurals.n_producten, regels.size, regels.size) + " · " + getString(R.string.nog_niet_opgeslagen))
        toonLaag(Laag.CONTROLE)
    }

    private fun controleRegel(r: JSONObject, id: String): View {
        val eenheid = r.optString("eenheid")
        val regel = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
            setBackgroundResource(R.drawable.regel_klik)
            isClickable = true
        }
        val links = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        links.addView(TextView(this).apply {
            text = r.optString("naam")
            textSize = 15f
            setTextColor(getColor(R.color.tekst))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        val details = mutableListOf(getString(R.string.bar_plus_hok, r.optString("bar"), r.optString("hok")))
        details += getString(R.string.was_voorraad, r.optInt("voorraad"))
        links.addView(TextView(this).apply {
            text = details.joinToString(" · ")
            textSize = 12f
            setTextColor(getColor(R.color.tekst_zacht))
        })
        val waarschuwing = when {
            !r.isNull("afwijking") -> getString(R.string.afwijking_tikfout)
            r.optString("model_afwijking") == "minder" -> getString(R.string.afwijking_minder)
            r.optString("model_afwijking") == "meer" -> getString(R.string.afwijking_meer)
            else -> null
        }
        if (waarschuwing != null) links.addView(TextView(this).apply {
            text = "⚠ $waarschuwing"
            textSize = 12f
            setTextColor(getColor(R.color.oranje_balk))
        })
        regel.addView(links, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val totaal = TextView(this).apply {
            text = getString(R.string.aantal_eenheid, controleWaarden[id] ?: 0, eenheid)
            textSize = 17f
            setTextColor(getColor(R.color.tekst))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        regel.addView(totaal)
        regel.setOnClickListener {
            Cijferpad.vraag(this, r.optString("naam"), (controleWaarden[id] ?: 0).toString(), eenheid = eenheid) { nieuw ->
                nieuw.toIntOrNull()?.let {
                    controleWaarden[id] = it
                    totaal.text = getString(R.string.aantal_eenheid, it, eenheid)
                    opslaanId = null
                }
            }
        }
        val scheiding = View(this).apply { setBackgroundResource(R.drawable.scheiding) }
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(regel)
            addView(scheiding, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1))
        }
    }

    private fun bevestig() {
        val id = opslaanId ?: Api.nieuwVerzoekId().also { opslaanId = it }
        b.opslaanKnop.isEnabled = false
        bezig {
            try {
                val waarden = JSONObject()
                controleWaarden.forEach { (k, v) -> waarden.put(k, v) }
                val antwoord = try {
                    Api.post(this, "/api/app/tellen/bevestigen", JSONObject().put("waarden", waarden).put("loop_id", loopId), verzoekId = id)
                } catch (f: Api.Fout) {
                    if (f.code == "afgebroken") return@bezig afgebroken(f.message)
                    throw f
                }
                lokaal.edit().remove("stand").apply()
                tellingId = antwoord.optInt("telling_id")
                b.klaarTitel.text = getString(R.string.telling_opgeslagen, antwoord.optInt("telling_id"))
                b.klaarTekst.text = resources.getQuantityString(R.plurals.n_producten_bijgewerkt, antwoord.optInt("aantal"), antwoord.optInt("aantal"))
                tril(80)
                toonLaag(Laag.KLAAR)
                // De voorraad is veranderd: de productlijst op het toestel bijwerken.
                try {
                    Catalogus.ververs(this)
                } catch (f: Api.Fout) {
                }
            } finally {
                b.opslaanKnop.isEnabled = true
            }
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, TellenActivity::class.java))

        /** Een afgebroken telling die de site nog niet weet (geen verbinding bij het afbreken): alsnog doorgeven. Alleen
         * die telling (loop_id): is er intussen een nieuwe begonnen, dan blijft die staan. */
        suspend fun stuurWachtendeStop(context: Context) {
            val prefs = context.getSharedPreferences("tellen", Context.MODE_PRIVATE)
            val id = prefs.getString("stoppen", null) ?: return
            try {
                Api.post(context, "/api/app/tellen/stoppen", JSONObject().put("loop_id", id), herhaalbaar = true)
                prefs.edit().remove("stoppen").apply()
            } catch (f: Api.Fout) {
            }
        }

        private fun stopOpAchtergrond(context: Context) {
            Achtergrond.scope.launch { stuurWachtendeStop(context) }
        }
    }
}
