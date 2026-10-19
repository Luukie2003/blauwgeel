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

/** Tellen met de looplijst: eerst de bar, dan het voorraadhok, product voor product. Daarna een controlescherm met de
 * totalen (en wat opvallend afwijkt), en pas bij "Telling opslaan" verandert de voorraad.
 *
 * Het tellen zelf gebeurt helemaal op het toestel: het volgende product staat er meteen, ook bij een slechte
 * verbinding. De stand gaat elke paar producten (en bij pauzeren) naar de site, in dezelfde vorm als de looplijst van
 * de site: verder gaan kan dus ook op een ander toestel of op de site. Lukt dat even niet, dan blijft de stand op het
 * toestel bewaard en gaat hij later mee.
 *
 * Een product scannen tijdens het tellen springt naar dat product. */
class TellenActivity : BasisActivity() {

    private class TelProduct(val id: Int, val naam: String, val categorie: String, val eenheid: String, val verwacht: JSONObject?)

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
    private var tellingPad: String? = null

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
        b.terugNaarTellenKnop.setOnClickListener {
            fase = "hok"
            index = producten.lastIndex
            toonLaag(Laag.TELLEN)
            toonProduct()
        }
        b.opslaanKnop.setOnClickListener { bevestig() }
        b.klaarKnop.setOnClickListener { finish() }
        b.bekijkKnop.setOnClickListener { tellingPad?.let { WebActivity.open(this, it, getString(R.string.telling)) } }

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
                Api.getJson(this@TellenActivity, "/api/app/tellen")
            } catch (f: Api.Fout) {
                toonFout(f)
                finish()
                return@launch
            }
            producten = data.getJSONArray("producten").objecten().map {
                TelProduct(it.getInt("id"), it.getString("naam"), it.optString("categorie"), it.optString("eenheid"), it.optJSONObject("verwacht"))
            }
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
                    zetStand(stand)
                    controleer()
                }
                else -> vraagVerder(stand)
            }
        }
    }

    private fun vraagVerder(stand: JSONObject) {
        val faseNaam = getString(if (stand.optString("fase") == "hok") R.string.fase_hok else R.string.fase_bar)
        val nummer = stand.optInt("index") + 1
        AlertDialog.Builder(this)
            .setTitle(R.string.verder_tellen_titel)
            .setMessage(getString(R.string.verder_tellen_vraag, faseNaam, nummer, producten.size))
            .setCancelable(false)
            .setPositiveButton(R.string.verder) { _, _ ->
                zetStand(stand)
                toonLaag(Laag.TELLEN)
                toonProduct()
            }
            .setNegativeButton(R.string.opnieuw_beginnen) { _, _ -> begin() }
            .show()
    }

    private fun zetStand(stand: JSONObject) {
        fase = if (stand.optString("fase") == "hok") "hok" else "bar"
        index = stand.optInt("index").coerceIn(0, producten.lastIndex)
        bar.clear()
        hok.clear()
        stand.optJSONObject("bar")?.let { j -> j.keys().forEach { bar[it] = j.optString(it) } }
        stand.optJSONObject("hok")?.let { j -> j.keys().forEach { hok[it] = j.optString(it) } }
    }

    private fun begin() {
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
        zetBalkTitel(getString(if (fase == "bar") R.string.tellen_bar else R.string.tellen_hok))
        zetBalkSub(getString(R.string.n_van_m, index + 1, producten.size))
        val stap = (if (fase == "bar") 0 else producten.size) + index
        b.voortgang.progress = (stap * 1000) / (producten.size * 2)
        b.telCategorie.text = p.categorie
        b.telNaam.text = p.naam
        b.telEenheid.text = p.eenheid
        val hints = mutableListOf<String>()
        p.verwacht?.let { v ->
            hints += getString(R.string.verwacht_totaal, v.optInt("verwacht"), v.optInt("laag"), v.optInt("hoog"))
        }
        if (fase == "hok") hints += getString(R.string.in_de_bar, bar[p.id.toString()]?.ifEmpty { null } ?: "0")
        b.telHint.text = hints.joinToString(" · ")
        waarde = huidige[p.id.toString()] ?: ""
        toonWaarde()
        b.vorigeKnop.isEnabled = !(fase == "bar" && index == 0)
        b.vorigeKnop.alpha = if (b.vorigeKnop.isEnabled) 1f else 0.4f
    }

    private fun toonWaarde() {
        b.telWaarde.text = waarde.ifEmpty { "–" }
        b.telWaarde.setTextColor(getColor(if (waarde.isEmpty()) R.color.rand_licht else R.color.tekst))
        val laatste = fase == "hok" && index == producten.lastIndex
        b.volgendeKnop.text = getString(
            when {
                laatste -> R.string.naar_controle
                waarde.isEmpty() -> R.string.overslaan
                else -> R.string.volgende
            },
        )
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
        menu.add(0, 100, 0, R.string.pauzeren)
        menu.add(0, 101, 1, R.string.naar_product)
        menu.add(0, 102, 2, R.string.stoppen_zonder_opslaan)
    }

    override fun bijMenu(id: Int): Boolean {
        when (id) {
            100 -> pauzeer()
            101 -> kiesProduct()
            102 -> AlertDialog.Builder(this)
                .setMessage(R.string.stoppen_vraag)
                .setPositiveButton(R.string.stoppen) { _, _ -> stop() }
                .setNegativeButton(R.string.annuleren, null)
                .show()
            else -> return false
        }
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

    private fun stop() {
        lokaal.edit().remove("stand").apply()
        lifecycleScope.launch {
            try {
                Api.post(this@TellenActivity, "/api/app/tellen/stoppen", herhaalbaar = true)
            } catch (f: Api.Fout) {
            }
        }
        melding(getString(R.string.gestopt))
        finish()
    }

    // ---------------------------------------------------------------- de stand bewaren

    private fun standJson(onverzonden: Boolean) = JSONObject()
        .put("fase", fase).put("index", index).put("bar", JSONObject(bar as Map<*, *>)).put("hok", JSONObject(hok as Map<*, *>))
        .put("naam", Sessie.naam).put("onverzonden", onverzonden).put("tijd", System.currentTimeMillis())

    private fun bewaarLokaal(onverzonden: Boolean = true) {
        lokaal.edit().putString("stand", standJson(onverzonden).toString()).apply()
    }

    /** Altijd op het toestel; elke vijf wijzigingen ook naar de site. */
    private fun bewaar() {
        bewaarLokaal()
        if (wijzigingen >= 5) stuurStand()
    }

    private fun stuurStand() {
        wijzigingen = 0
        val stand = standJson(false)
        val app = applicationContext
        lifecycleScope.launch {
            try {
                Api.post(app, "/api/app/tellen/stand", stand, herhaalbaar = true)
                // Doorgegeven: bij de volgende start telt de stand van de site (die kan intussen verder zijn).
                lokaal.edit().putString("stand", stand.toString()).apply()
            } catch (f: Api.Fout) {
                if (f.soort == Api.Soort.NIET_INGELOGD) toonFout(f)
            }
        }
    }

    // ---------------------------------------------------------------- controleren en opslaan

    private fun controleer() {
        toonLaag(Laag.LADEN)
        bezig {
            try {
                val body = JSONObject().put("bar", JSONObject(bar as Map<*, *>)).put("hok", JSONObject(hok as Map<*, *>))
                val regels = Api.post(this, "/api/app/tellen/controleren", body, herhaalbaar = true).getJSONArray("regels").objecten()
                lokaal.edit().putString("stand", standJson(false).toString()).apply()
                toonControle(regels)
            } catch (f: Api.Fout) {
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
                val antwoord = Api.post(this, "/api/app/tellen/bevestigen", JSONObject().put("waarden", waarden), verzoekId = id)
                lokaal.edit().remove("stand").apply()
                tellingPad = antwoord.tekstOfNull("pad")
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
    }
}
