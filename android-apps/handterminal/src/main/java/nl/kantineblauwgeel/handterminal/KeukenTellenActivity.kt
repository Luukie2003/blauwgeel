package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityTellenBinding
import org.json.JSONArray
import org.json.JSONObject

/** De keukentelling als looplijst, net als Tellen (en de keukenlooplijst op de site): product voor product, met foto,
 * voortgang, de snelknoppen en de rekenmachine. Losse stuks tik je in; een volle doos of zak scan je, en wat erin zit
 * (uit het artikel, dus per supermarkt anders) telt er meteen bij. Onder de naam staat wat er gescand is ("Gescand: +40
 * · +15"); tik erop om een verkeerde scan weg te halen. Scan je een ander keukenproduct, dan springt de lijst daarheen; een
 * onbekende barcode koppel je meteen (KoppelenActivity) en die scan telt dan alsnog mee.
 *
 * De stand staat op het toestel (SharedPreferences "keuken_tellen"): na Terug, de slaapstand of een herstart ga je
 * verder waar je was. Aan het eind een controlescherm met per product geteld, de voorraad, het verschil en wat er als
 * verkocht telt (met de omzet), waar je ook kiest of het een begintelling is. Pas bij "Telling opslaan" verandert de
 * voorraad (/api/app/keuken/tellen, zoals Keuken > Tellen op de site). */
class KeukenTellenActivity : BasisActivity() {

    private class KeukenProduct(
        val id: Int,
        val naam: String,
        val subcategorie: String,
        val eenheid: String,
        val voorraad: Int,
        val verkoopprijs: Double,
        val foto: String?,
        val verpakking: String,
        val perVerpakking: Int,
        val dozen: List<JSONObject>,
    )

    private class Scan(val aantal: Int, val omschrijving: String)

    private enum class Laag { LADEN, TELLEN, CONTROLE, KLAAR }

    private lateinit var b: ActivityTellenBinding
    private var producten: List<KeukenProduct> = emptyList()
    /** Barcode -> {product_id, aantal, omschrijving}, uit de gekoppelde dozen en zakken van de keukenproducten. */
    private val opCode = HashMap<String, JSONObject>()
    private var index = 0
    private val waarden = LinkedHashMap<Int, String>()
    private val scans = HashMap<Int, MutableList<Scan>>()
    private var waarde = ""
    private var begintelling = false
    private var laag = Laag.LADEN
    private var opslaanId: String? = null
    private var tellingId: Int? = null
    /** De scan die moest worden gekoppeld: na het koppelen telt hij alsnog mee. */
    private var teKoppelen: String? = null

    private val lokaal by lazy { getSharedPreferences("keuken_tellen", Context.MODE_PRIVATE) }

    private val koppelen = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val code = r.data?.getStringExtra(KoppelenActivity.EXTRA_CODE)?.takeIf { r.resultCode == RESULT_OK } ?: teKoppelen
        teKoppelen = null
        if (code != null) bezig {
            laadDozen(Api.getJson(this, "/api/app/keuken"))
            try {
                Catalogus.ververs(this)
            } catch (f: Api.Fout) {
            }
            telScan(code, naKoppelen = true)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityTellenBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.keukentelling))

        Cijferpad.koppel(b.pad, waarde = { waarde }) {
            waarde = it
            toonWaarde()
        }
        b.volgendeKnop.setOnClickListener { volgende() }
        b.vorigeKnop.setOnClickListener { vorige() }
        b.snelNul.setOnClickListener {
            waarde = "0"
            volgende()
        }
        b.snelMin1.setOnClickListener { pasAan(-1) }
        b.snelPlus1.setOnClickListener { pasAan(1) }
        b.snelPlus2.setOnClickListener { pasAan(2) }
        b.snelKrat.setOnClickListener { pasAan(producten[index].perVerpakking) }
        b.rekenKnop.setOnClickListener {
            Rekenmachine.open(this, waarde) {
                waarde = it.toString()
                toonWaarde()
            }
        }
        b.pauzeerKnop.setOnClickListener { pauzeer() }
        b.stopKnop.setOnClickListener { vraagStoppen() }
        b.terugNaarTellenKnop.setOnClickListener {
            index = producten.lastIndex
            toonLaag(Laag.TELLEN)
            toonProduct()
        }
        b.opslaanKnop.setOnClickListener { opslaan() }
        b.klaarKnop.setText(R.string.terug_naar_keuken)
        b.klaarKnop.setOnClickListener { finish() }
        b.bekijkKnop.setOnClickListener { tellingId?.let { KeukenTellingActivity.open(this, it) } }
        b.telBarGeteld.isVisible = false
        b.controleUitleg.setText(R.string.keuken_controle_uitleg)

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
        if (laag == Laag.TELLEN || laag == Laag.CONTROLE) {
            if (laag == Laag.TELLEN) legVast()
            bewaar()
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
            Laag.KLAAR -> { zetBalkTitel(getString(R.string.keukentelling)); zetBalkSub(Sessie.naam) }
            else -> {}
        }
    }

    // ---------------------------------------------------------------- laden en verder gaan

    private fun laad() {
        bezig {
            val keuken = Api.getJson(this, "/api/app/keuken")
            producten = keuken.getJSONArray("producten").objecten().map { p ->
                KeukenProduct(
                    p.getInt("id"), p.optString("naam"), p.optString("subcategorie"), p.optString("eenheid"),
                    p.optInt("voorraad"), p.optDouble("verkoopprijs", 0.0), p.tekstOfNull("foto_groot") ?: p.tekstOfNull("foto"),
                    p.optString("verpakking"), p.optInt("per_verpakking", 1), p.optJSONArray("dozen")?.objecten().orEmpty(),
                )
            }
            laadDozen(keuken)
            if (producten.isEmpty()) {
                melding(getString(R.string.geen_keukenproducten), lang = true)
                finish()
                return@bezig
            }
            begintelling = keuken.optBoolean("eerste_telling")
            val bewaard = lokaal.getString("stand", null)?.let { runCatching { JSONObject(it) }.getOrNull() }
            if (bewaard != null && bewaard.optJSONObject("waarden")?.length() ?: 0 > 0) vraagVerder(bewaard) else begin()
            Fotos.haalAlvast(this, producten.map { it.foto })
        }
    }

    private fun laadDozen(keuken: JSONObject) {
        opCode.clear()
        for (p in keuken.getJSONArray("producten").objecten()) {
            for (d in p.optJSONArray("dozen")?.objecten().orEmpty()) {
                opCode[d.optString("code")] = JSONObject().put("product_id", p.getInt("id")).put("aantal", d.optInt("aantal"))
                    .put("omschrijving", d.optString("omschrijving"))
            }
        }
    }

    private fun vraagVerder(stand: JSONObject) {
        val n = stand.optJSONObject("waarden")?.length() ?: 0
        AlertDialog.Builder(this)
            .setTitle(R.string.keuken_verder_titel)
            .setMessage(resources.getQuantityString(R.plurals.keuken_verder_tekst, n, n))
            .setCancelable(false)
            .setPositiveButton(R.string.verder_tellen) { _, _ -> zetStand(stand) }
            .setNegativeButton(R.string.opnieuw_beginnen) { _, _ -> begin() }
            .show()
    }

    private fun zetStand(stand: JSONObject) {
        waarden.clear()
        scans.clear()
        stand.optJSONObject("waarden")?.let { w -> w.keys().forEach { k -> k.toIntOrNull()?.let { waarden[it] = w.optString(k) } } }
        stand.optJSONObject("scans")?.let { s ->
            s.keys().forEach { k ->
                val id = k.toIntOrNull() ?: return@forEach
                scans[id] = s.optJSONArray(k)?.objecten()?.map { Scan(it.optInt("aantal"), it.optString("omschrijving")) }?.toMutableList()
                    ?: mutableListOf()
            }
        }
        if (stand.has("begintelling")) begintelling = stand.optBoolean("begintelling")
        index = stand.optInt("index").coerceIn(0, producten.lastIndex)
        if (stand.optBoolean("controle")) toonControle() else {
            toonLaag(Laag.TELLEN)
            toonProduct()
        }
    }

    private fun begin() {
        waarden.clear()
        scans.clear()
        index = 0
        opslaanId = null
        lokaal.edit().remove("stand").apply()
        toonLaag(Laag.TELLEN)
        toonProduct()
    }

    private fun bewaar() {
        val w = JSONObject()
        waarden.forEach { (id, v) -> w.put(id.toString(), v) }
        val s = JSONObject()
        scans.forEach { (id, lijst) ->
            if (lijst.isNotEmpty()) s.put(id.toString(), JSONArray(lijst.map { JSONObject().put("aantal", it.aantal).put("omschrijving", it.omschrijving) }))
        }
        val stand = JSONObject().put("waarden", w).put("scans", s).put("index", index).put("begintelling", begintelling)
            .put("controle", laag == Laag.CONTROLE)
        lokaal.edit().putString("stand", stand.toString()).apply()
    }

    // ---------------------------------------------------------------- tellen

    private fun toonProduct() {
        val p = producten[index]
        zetBalkTitel(getString(R.string.keukentelling))
        zetBalkSub(getString(R.string.keuken_product_n_van_m, index + 1, producten.size, waarden.size))
        b.voortgang.progress = (index * 1000) / producten.size
        b.faseLabel.setText(R.string.keuken)
        b.faseLabel.setBackgroundResource(R.drawable.fase_bar)
        b.faseLabel.setTextColor(getColor(R.color.groen_tekst))
        Fotos.toon(b.telFoto, p.foto)
        b.telCategorie.text = p.subcategorie
        b.telNaam.text = p.naam
        b.telEenheid.text = p.eenheid
        b.telVoorraad.text = getString(R.string.geregistreerde_voorraad, p.voorraad, p.eenheid)
        b.snelKrat.isVisible = p.perVerpakking > 1
        b.snelKrat.text = getString(R.string.plus_een_besteleenheid, p.verpakking, p.perVerpakking)
        waarde = waarden[p.id] ?: ""
        toonWaarde()
        toonScans()
        b.vorigeKnop.isEnabled = index > 0
        b.vorigeKnop.alpha = if (b.vorigeKnop.isEnabled) 1f else 0.4f
        b.volgendeKnop.setText(if (index < producten.lastIndex) R.string.volgende_pijl else R.string.bekijken_en_bevestigen)
        Fotos.haalAlvast(this, producten.drop(index + 1).take(3).map { it.foto })
    }

    /** Onder de naam: wat er van dit product gescand is (tik om een scan weg te halen), of anders welke dozen en zakken
     * er bekend zijn, als hulp bij het scannen. */
    private fun toonScans() {
        val p = producten[index]
        val lijst = scans[p.id].orEmpty()
        b.telVerwacht.isVisible = true
        if (lijst.isNotEmpty()) {
            b.telVerwacht.text = getString(R.string.keuken_gescand_regel, lijst.joinToString(" · ") { "+${it.aantal}" })
            b.telVerwacht.setTextColor(getColor(R.color.navy))
            b.telVerwacht.setOnClickListener { kiesScanWeg() }
        } else {
            b.telVerwacht.text = if (p.dozen.isEmpty()) getString(R.string.keuken_geen_dozen)
            else getString(R.string.keuken_dozen, p.dozen.joinToString(" · ") { "${it.optInt("aantal")}" })
            b.telVerwacht.setTextColor(getColor(R.color.tekst_zacht))
            b.telVerwacht.setOnClickListener(null)
            b.telVerwacht.isClickable = false
        }
    }

    private fun kiesScanWeg() {
        val p = producten[index]
        val lijst = scans[p.id].orEmpty()
        if (lijst.isEmpty()) return
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.keuken_scans_titel, p.naam)))
            .setItems(lijst.map { "✕  " + getString(R.string.keuken_scan_regel, it.aantal, p.eenheid, it.omschrijving) }.toTypedArray()) { _, i ->
                haalScanWeg(i)
            }
            .setNegativeButton(R.string.sluiten, null)
            .show()
    }

    private fun haalScanWeg(i: Int) {
        val p = producten[index]
        val scan = scans[p.id]?.removeAt(i) ?: return
        waarde = maxOf(0, (waarde.toIntOrNull() ?: 0) - scan.aantal).toString()
        legVast()
        toonWaarde()
        toonScans()
        bewaar()
    }

    private fun toonWaarde() {
        b.telWaarde.text = waarde.ifEmpty { "–" }
        b.telWaarde.setTextColor(getColor(if (waarde.isEmpty()) R.color.rand_licht else R.color.tekst))
    }

    private fun pasAan(stap: Int) {
        waarde = maxOf(0, (waarde.toIntOrNull() ?: 0) + stap).toString()
        toonWaarde()
    }

    private fun legVast() {
        val id = producten[index].id
        if (waarde.isEmpty()) waarden.remove(id) else waarden[id] = waarde
        opslaanId = null
    }

    private fun volgende() {
        legVast()
        if (index < producten.lastIndex) {
            index++
            toonProduct()
            bewaar()
        } else {
            toonControle()
            bewaar()
        }
    }

    private fun vorige() {
        legVast()
        if (index > 0) index--
        toonProduct()
        bewaar()
    }

    override fun bijScan(code: String) {
        if (laag != Laag.TELLEN) return super.bijScan(code)
        telScan(code)
    }

    /** Een doos of zak: naar dat product en wat erin zit erbij. Onbekend: eerst koppelen. */
    private fun telScan(code: String, naKoppelen: Boolean = false) {
        val norm = Catalogus.normaliseerCode(code) ?: return melding(getString(R.string.scan_geen_barcode, code))
        val doos = opCode[norm]
        val productId = doos?.optInt("product_id") ?: Catalogus.opBarcode(norm)?.product?.id
        val positie = productId?.let { id -> producten.indexOfFirst { it.id == id } } ?: -1
        if (positie < 0) {
            if (productId != null) return melding(getString(R.string.geen_keukenproduct))
            if (naKoppelen) return melding(getString(R.string.keuken_nog_onbekend), lang = true)
            tril(150)
            teKoppelen = norm
            legVast()
            koppelen.launch(KoppelenActivity.intent(this, norm))
            return
        }
        val aantal = doos?.optInt("aantal") ?: Catalogus.opBarcode(norm)?.barcode?.aantal ?: 1
        val omschrijving = doos?.optString("omschrijving") ?: Catalogus.opBarcode(norm)?.barcode?.artikel ?: norm
        if (laag == Laag.TELLEN) legVast()
        index = positie
        val p = producten[index]
        waarden[p.id] = ((waarden[p.id]?.toIntOrNull() ?: 0) + aantal).toString()
        scans.getOrPut(p.id) { mutableListOf() }.add(Scan(aantal, omschrijving))
        opslaanId = null
        tril()
        toonLaag(Laag.TELLEN)
        toonProduct()
        bewaar()
        melding(getString(R.string.keuken_scan_erbij, aantal, p.eenheid, p.naam, omschrijving))
    }

    private fun pauzeer() {
        legVast()
        bewaar()
        melding(getString(R.string.keuken_gepauzeerd))
        finish()
    }

    private fun vraagStoppen() {
        AlertDialog.Builder(this)
            .setMessage(R.string.keuken_stoppen_vraag)
            .setPositiveButton(R.string.ja_afbreken) { _, _ ->
                lokaal.edit().remove("stand").apply()
                finish()
            }
            .setNegativeButton(R.string.nee_verder_tellen, null)
            .show()
    }

    // ---------------------------------------------------------------- controleren en opslaan

    private fun toonControle() {
        toonLaag(Laag.CONTROLE)
        val lijst = b.controleLijst
        lijst.removeAllViews()
        // Bovenaan: gewone telling of begintelling (tik om te wisselen), en wat het oplevert.
        val geteld = producten.filter { waarden[it.id]?.toIntOrNull() != null }
        var verkochtTotaal = 0
        var omzet = 0.0
        for (p in geteld) {
            val verschil = waarden[p.id]!!.toInt() - p.voorraad
            if (!begintelling && verschil < 0) {
                verkochtTotaal += -verschil
                omzet += -verschil * p.verkoopprijs
            }
        }
        val soort = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        lijst.addView(soort)
        Lijst.regel(soort, getString(if (begintelling) R.string.keuken_begintelling else R.string.keuken_gewone_telling),
            getString(if (begintelling) R.string.keuken_begintelling_uitleg else R.string.keuken_gewone_uitleg),
            getString(R.string.wisselen), R.color.navy) {
            begintelling = !begintelling
            opslaanId = null
            bewaar()
            toonControle()
        }
        Lijst.regel(soort, getString(R.string.keuken_controle_totaal, geteld.size, producten.size),
            if (begintelling) getString(R.string.keuken_geen_verkoop) else getString(R.string.keuken_verkocht_totaal, verkochtTotaal),
            if (begintelling) null else Lijst.euro(omzet), R.color.groen_tekst)
        lijst.addView(View(this).apply { setBackgroundResource(R.drawable.scheiding) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(this, 6)))

        val regels = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        lijst.addView(regels)
        for (p in producten) {
            val n = waarden[p.id]?.toIntOrNull()
            val (detail, rechts, kleur) = if (n == null) {
                Triple(getString(R.string.keuken_niet_geteld, p.voorraad, p.eenheid), "–", R.color.tekst_zacht)
            } else {
                val verschil = n - p.voorraad
                val wat = when {
                    verschil == 0 -> getString(R.string.keuken_klopt)
                    verschil < 0 && !begintelling -> getString(R.string.keuken_verkocht, -verschil, Lijst.euro(-verschil * p.verkoopprijs))
                    verschil < 0 -> getString(R.string.keuken_minder, -verschil)
                    else -> getString(R.string.keuken_meer, verschil)
                }
                Triple(getString(R.string.was_voorraad, p.voorraad) + " · " + wat, getString(R.string.aantal_eenheid, n, p.eenheid),
                    if (verschil < 0 && !begintelling) R.color.oranje_balk else R.color.tekst)
            }
            Lijst.regel(regels, p.naam, detail, rechts, kleur) {
                Cijferpad.vraag(this, p.naam, waarden[p.id] ?: "", eenheid = p.eenheid) { nieuw ->
                    if (nieuw.isEmpty()) waarden.remove(p.id) else nieuw.toIntOrNull()?.let { waarden[p.id] = it.toString() }
                    opslaanId = null
                    bewaar()
                    toonControle()
                }
            }
        }
        zetBalkSub(resources.getQuantityString(R.plurals.n_producten, geteld.size, geteld.size) + " · " + getString(R.string.nog_niet_opgeslagen))
        b.opslaanKnop.isEnabled = geteld.isNotEmpty()
        b.opslaanKnop.alpha = if (geteld.isNotEmpty()) 1f else 0.5f
    }

    private fun opslaan() {
        val lijst = JSONObject()
        waarden.forEach { (id, v) -> v.toIntOrNull()?.let { lijst.put(id.toString(), it) } }
        if (lijst.length() == 0) return
        val id = opslaanId ?: Api.nieuwVerzoekId().also { opslaanId = it }
        b.opslaanKnop.isEnabled = false
        bezig {
            try {
                val antwoord = Api.post(this, "/api/app/keuken/tellen",
                    JSONObject().put("waarden", lijst).put("begintelling", begintelling), verzoekId = id)
                lokaal.edit().remove("stand").apply()
                tellingId = antwoord.optInt("telling_id")
                b.klaarTitel.text = antwoord.optString("melding")
                b.klaarTekst.text = getString(if (begintelling) R.string.keuken_klaar_begin else R.string.keuken_klaar_gewoon)
                b.bekijkKnop.setText(R.string.keuken_telling_bekijken)
                tril(80)
                toonLaag(Laag.KLAAR)
            } finally {
                b.opslaanKnop.isEnabled = true
            }
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, KeukenTellenActivity::class.java))
    }
}
