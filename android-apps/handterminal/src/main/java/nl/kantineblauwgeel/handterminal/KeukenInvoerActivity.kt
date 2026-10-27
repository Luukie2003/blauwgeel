package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONArray
import org.json.JSONObject

/** Keuken inboeken, altijd per verpakking. Scan wat er binnenkomt: elke scan is een zak of doos met wat erin zit (van de
 * barcode, dus per merk anders), en staat bovenaan bij "Gescand", met een kruisje om hem weg te halen. Een onbekende
 * barcode koppel je meteen ([KeukenKoppelen]: alleen keukenproducten, en hoeveel zit erin); staat bij een barcode nog niet
 * hoeveel erin zit, dan vraagt de app dat één keer. Zonder barcode: tik op het product en kies de verpakking (de zak van
 * 20 van AH, de zak van 15 van Plus), of stel er een in. Wat je invult, blijft op het toestel bewaard (ook als de app
 * uitlogt) tot je inboekt. Inboeken doet hetzelfde als Keuken > Inboeken op de site. De keukentelling zelf is de
 * looplijst in [KeukenTellenActivity]. */
class KeukenInvoerActivity : BasisActivity() {

    private class Scan(val code: String, val productId: Int, val aantal: Int, val omschrijving: String)

    private lateinit var b: ActivityLijstBinding
    private var producten: List<JSONObject> = emptyList()
    /** Barcode -> {product_id, aantal (null: nog niet bekend), omschrijving}. */
    private val opCode = HashMap<String, JSONObject>()
    /** Zonder barcode: per product per verpakking (de sleutel uit "verpakkingen") hoeveel er binnen zijn. */
    private val verpakkingen = mutableMapOf<Int, MutableMap<String, Int>>()
    private val scans = mutableListOf<Scan>()
    private var verzoekId: String? = null

    private val lokaal by lazy { getSharedPreferences("keuken_inboeken", MODE_PRIVATE) }
    /** Per persoon: wie na het uitloggen inlogt, ziet niet wat een ander aan het inboeken was. */
    private val sleutel get() = "stand_" + (Sessie.naam ?: "")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.keuken_inboeken))
        b.verversen.isEnabled = false
        b.onderKnop.isVisible = true
        b.onderKnop.setOnClickListener { opslaan() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (verpakkingen.isEmpty() && scans.isEmpty()) return finish()
                AlertDialog.Builder(this@KeukenInvoerActivity)
                    .setMessage(R.string.keuken_inboeken_bewaard_vraag)
                    .setPositiveButton(R.string.later_verder) { _, _ -> finish() }
                    .setNeutralButton(R.string.wissen) { _, _ ->
                        lokaal.edit().remove(sleutel).apply()
                        finish()
                    }
                    .setNegativeButton(R.string.annuleren, null)
                    .show()
            }
        })
        werkKnopBij()
        bezig {
            laad(Api.getJson(this, "/api/app/keuken"))
            herstel()
            bouw()
        }
    }

    private fun laad(keuken: JSONObject) {
        producten = keuken.getJSONArray("producten").objecten()
        opCode.clear()
        for (p in producten) for (d in p.optJSONArray("dozen")?.objecten().orEmpty()) {
            zetCode(d.put("product_id", p.getInt("id")))
        }
    }

    private fun zetCode(d: JSONObject) {
        opCode[d.optString("code")] = JSONObject().put("product_id", d.getInt("product_id"))
            .put("aantal", if (d.isNull("aantal")) JSONObject.NULL else d.getInt("aantal"))
            .put("omschrijving", d.optString("omschrijving"))
    }

    private fun product(id: Int) = producten.firstOrNull { it.getInt("id") == id }

    private fun pakketten(p: JSONObject) = p.optJSONArray("verpakkingen")?.objecten().orEmpty()

    /** Wat er de vorige keer is ingevuld en nog niet ingeboekt (bijvoorbeeld voordat de app uitlogde). */
    private fun herstel() {
        val stand = lokaal.getString(sleutel, null)?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return
        for (s in stand.optJSONArray("scans")?.objecten().orEmpty()) {
            val code = s.optString("code")
            val d = opCode[code] ?: continue
            if (d.isNull("aantal") || product(d.getInt("product_id")) == null) continue
            scans += Scan(code, d.getInt("product_id"), d.getInt("aantal"), d.optString("omschrijving"))
        }
        stand.optJSONObject("verpakkingen")?.let { alle ->
            for (pid in alle.keys()) {
                val p = pid.toIntOrNull()?.let { product(it) } ?: continue
                val bekend = pakketten(p).map { it.optString("sleutel") }.toSet()
                val keuzes = alle.optJSONObject(pid) ?: continue
                for (s in keuzes.keys()) {
                    val n = keuzes.optInt(s)
                    if (n > 0 && s in bekend) verpakkingen.getOrPut(p.getInt("id")) { mutableMapOf() }[s] = n
                }
            }
        }
        verzoekId = stand.tekstOfNull("verzoek_id")
        if (scans.isNotEmpty() || verpakkingen.isNotEmpty()) melding(getString(R.string.keuken_inboeken_verder))
    }

    /** Op het toestel bewaren, tot er is ingeboekt. */
    private fun bewaar() {
        if (scans.isEmpty() && verpakkingen.isEmpty()) return lokaal.edit().remove(sleutel).apply()
        val v = JSONObject()
        verpakkingen.forEach { (pid, keuzes) -> v.put(pid.toString(), JSONObject(keuzes.toMap())) }
        lokaal.edit().putString(sleutel, JSONObject()
            .put("scans", JSONArray(scans.map { JSONObject().put("code", it.code) }))
            .put("verpakkingen", v)
            .put("verzoek_id", verzoekId ?: JSONObject.NULL)
            .toString()).apply()
    }

    private fun veranderd() {
        verzoekId = null
        bewaar()
        bouw()
    }

    private fun bouw() {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        Lijst.kaart(inhoud, R.drawable.melding_info).let {
            Lijst.tekst(it, getString(R.string.keuken_inboeken_uitleg), kleur = R.color.tekst)
        }
        if (producten.isEmpty()) return Lijst.leeg(inhoud, getString(R.string.geen_keukenproducten))

        // Wat er gescand is, nieuwste bovenaan, met een kruisje om een verkeerde scan weg te halen.
        Lijst.kop(inhoud, getString(R.string.keuken_gescand_kop, scans.sumOf { it.aantal }))
        val gescand = Lijst.kaart(inhoud)
        if (scans.isEmpty()) Lijst.tekst(gescand, getString(R.string.keuken_nog_niets_gescand))
        scans.withIndex().reversed().forEach { (i, s) ->
            val p = product(s.productId)
            val regel = Lijst.regel(gescand, p?.optString("naam") ?: "?", s.omschrijving,
                "+${s.aantal} ${p?.optString("eenheid") ?: ""}", R.color.groen_tekst)
            regel.addView(TextView(this).apply {
                text = "✕"
                textSize = 18f
                setTextColor(getColor(R.color.tekst_zacht))
                setPadding(dp(context, 14), dp(context, 4), dp(context, 2), dp(context, 4))
                contentDescription = getString(R.string.scan_weghalen)
                setOnClickListener {
                    scans.removeAt(i)
                    veranderd()
                }
            })
        }

        Lijst.kop(inhoud, getString(R.string.keuken_zonder_barcode))
        val meerdereGroepen = producten.map { it.optString("subcategorie") }.distinct().size > 1
        var groep: String? = null
        var kaart: LinearLayout? = null
        for (p in producten) {
            val sub = p.optString("subcategorie")
            if (kaart == null || sub != groep) {
                if (meerdereGroepen && sub.isNotEmpty()) Lijst.subkop(inhoud, sub)
                kaart = Lijst.kaart(inhoud)
                groep = sub
            }
            val lijst = pakketten(p)
            val gekozen = verpakkingen[p.getInt("id")].orEmpty()
            val stuks = lijst.sumOf { (gekozen[it.optString("sleutel")] ?: 0) * it.optInt("aantal") }
            Lijst.regel(kaart, p.optString("naam"),
                if (lijst.isEmpty()) getString(R.string.keuken_geen_verpakking)
                else lijst.joinToString(" · ") { v ->
                    (gekozen[v.optString("sleutel")]?.let { "$it× " } ?: "") + getString(R.string.verpakking_van, v.optString("naam"), v.optInt("aantal"))
                },
                if (stuks > 0) "+$stuks ${p.optString("eenheid")}" else "–", if (stuks > 0) R.color.groen_tekst else R.color.navy) { kies(p) }
        }
        werkKnopBij()
    }

    /** Zonder barcode: welke verpakking (bij meer dan één), en hoeveel zijn er binnen? Zonder verpakking: eerst instellen. */
    private fun kies(p: JSONObject) {
        val lijst = pakketten(p)
        val gekozen = verpakkingen[p.getInt("id")].orEmpty()
        when (lijst.size) {
            0 -> KeukenKoppelen.vraagProductVerpakking(this, p.getInt("id") to p.optString("naam")) { nieuw ->
                p.put("verpakkingen", JSONArray(nieuw))
                bouw()
                kies(p)
            }
            1 -> vraagAantal(p, lijst[0])
            else -> AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.keuken_welke_verpakking, p.optString("naam"))))
                .setItems(lijst.map { v ->
                    getString(R.string.verpakking_van, v.optString("naam"), v.optInt("aantal")) +
                        (gekozen[v.optString("sleutel")]?.let { "   · " + getString(R.string.n_binnen, it) } ?: "")
                }.toTypedArray()) { _, i -> vraagAantal(p, lijst[i]) }
                .setNegativeButton(R.string.annuleren, null)
                .show()
        }
    }

    private fun vraagAantal(p: JSONObject, v: JSONObject) {
        val id = p.getInt("id")
        val s = v.optString("sleutel")
        // Een merk zegt zelf wat het is ("AH frikandellen"); de verpakking van het product ("doos") niet.
        val wat = if (s == "product") "${p.optString("naam")}, ${v.optString("naam")}" else v.optString("naam")
        Cijferpad.vraag(this, getString(R.string.keuken_hoeveel_binnen, wat, v.optInt("aantal")),
            verpakkingen[id]?.get(s)?.toString() ?: "", eenheid = "×", max = 3) { tekst ->
            val n = tekst.toIntOrNull()
            if (n == null || n == 0) {
                verpakkingen[id]?.remove(s)
                if (verpakkingen[id].isNullOrEmpty()) verpakkingen.remove(id)
            } else {
                verpakkingen.getOrPut(id) { mutableMapOf() }[s] = n
            }
            veranderd()
        }
    }

    private val aantalProducten get() = (verpakkingen.keys + scans.map { it.productId }).size

    private fun werkKnopBij() {
        val iets = aantalProducten > 0
        b.onderKnop.isEnabled = iets
        b.onderKnop.alpha = if (iets) 1f else 0.5f
        b.onderKnop.text = getString(R.string.inboeken_n, aantalProducten)
    }

    override fun bijScan(code: String) = scan(code)

    /** Een zak of doos: wat erin zit erbij. Onbekend: eerst koppelen; nog niet bekend hoeveel erin zit: eerst vragen. */
    private fun scan(code: String) {
        val norm = Catalogus.normaliseerCode(code) ?: return melding(getString(R.string.scan_geen_barcode, code))
        val doos = opCode[norm]
        if (doos == null) {
            // De barcode van een gewoon product (als de app de productlijst kent): dat is geen keukenproduct.
            if (Catalogus.opBarcode(norm) != null) return melding(getString(R.string.geen_keukenproduct))
            return KeukenKoppelen.koppel(this, norm, producten.map { it.getInt("id") to it.optString("naam") }) { nieuw ->
                zetCode(nieuw)
                scan(norm)
            }
        }
        val p = product(doos.getInt("product_id")) ?: return melding(getString(R.string.geen_keukenproduct))
        if (doos.isNull("aantal")) {
            return KeukenKoppelen.vraagAantal(this, norm, doos.optString("omschrijving"), p.optString("eenheid")) { nieuw ->
                zetCode(nieuw)
                scan(norm)
            }
        }
        val aantal = doos.getInt("aantal")
        val omschrijving = doos.optString("omschrijving")
        scans += Scan(norm, p.getInt("id"), aantal, omschrijving)
        tril()
        melding(getString(R.string.keuken_scan_erbij, aantal, p.optString("eenheid"), p.optString("naam"), omschrijving))
        veranderd()
    }

    private fun opslaan() {
        if (aantalProducten == 0) return
        val id = verzoekId ?: Api.nieuwVerzoekId().also {
            verzoekId = it
            bewaar()  // gaat het mis na het versturen, dan herkent de site een tweede poging
        }
        val lijst = JSONObject()
        verpakkingen.forEach { (pid, keuzes) -> lijst.put(pid.toString(), JSONObject(keuzes.toMap())) }
        val body = JSONObject().put("scans", JSONArray(scans.map { it.code })).put("verpakkingen", lijst)
        b.onderKnop.isEnabled = false
        bezig {
            try {
                val antwoord = Api.post(this, "/api/app/keuken/inboeken", body, verzoekId = id)
                lokaal.edit().remove(sleutel).apply()
                scans.clear()
                verpakkingen.clear()
                tril(60)
                melding(antwoord.optString("melding"), lang = true)
                finish()
            } finally {
                werkKnopBij()
            }
        }
    }

    companion object {
        const val INBOEKEN = "inboeken"
        private const val EXTRA_MODUS = "modus"

        fun open(context: Context, modus: String = INBOEKEN) =
            context.startActivity(Intent(context, KeukenInvoerActivity::class.java).putExtra(EXTRA_MODUS, modus))
    }
}
