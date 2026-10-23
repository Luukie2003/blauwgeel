package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Keuken inboeken. Scan wat er binnenkomt: elke scan is een doos of zak met het aantal dat erin zit (uit het artikel,
 * dus per supermarkt anders), en staat bovenaan in de lijst "Gescand", met een kruisje om hem weg te halen. Een
 * onbekende barcode koppel je meteen (KoppelenActivity) en die scan telt dan alsnog mee. Wat geen barcode heeft: tik
 * op het product en vul in hoeveel verpakkingen er binnenkwamen (bijvoorbeeld 2 dozen). Inboeken doet hetzelfde als
 * Keuken > Inboeken op de site. De keukentelling zelf is de looplijst in [KeukenTellenActivity]. */
class KeukenInvoerActivity : BasisActivity() {

    private class Scan(val productId: Int, val aantal: Int, val omschrijving: String)

    private lateinit var b: ActivityLijstBinding
    private var producten: List<JSONObject> = emptyList()
    private val opCode = HashMap<String, JSONObject>()
    /** Zonder barcode: aantal verpakkingen per product. */
    private val verpakkingen = mutableMapOf<Int, Int>()
    private val scans = mutableListOf<Scan>()
    private var verzoekId: String? = null
    private var teKoppelen: String? = null

    private val koppelen = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val code = r.data?.getStringExtra(KoppelenActivity.EXTRA_CODE)?.takeIf { r.resultCode == RESULT_OK } ?: teKoppelen
        teKoppelen = null
        if (code != null) bezig {
            laad(Api.getJson(this, "/api/app/keuken"))
            try {
                Catalogus.ververs(this)
            } catch (f: Api.Fout) {
            }
            scan(code, naKoppelen = true)
        }
    }

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
                    .setMessage(R.string.invoer_weggooien_vraag)
                    .setPositiveButton(R.string.weggooien) { _, _ -> finish() }
                    .setNegativeButton(R.string.annuleren, null)
                    .show()
            }
        })
        werkKnopBij()
        bezig {
            laad(Api.getJson(this, "/api/app/keuken"))
            bouw()
        }
    }

    private fun laad(keuken: JSONObject) {
        producten = keuken.getJSONArray("producten").objecten()
        opCode.clear()
        for (p in producten) for (d in p.optJSONArray("dozen")?.objecten().orEmpty()) {
            opCode[d.optString("code")] = JSONObject().put("product_id", p.getInt("id")).put("aantal", d.optInt("aantal"))
                .put("omschrijving", d.optString("omschrijving"))
        }
    }

    private fun product(id: Int) = producten.firstOrNull { it.getInt("id") == id }

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
                    verzoekId = null
                    bouw()
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
            val id = p.getInt("id")
            val n = verpakkingen[id]
            Lijst.regel(kaart, p.optString("naam"),
                getString(R.string.per_verpakking, p.optString("verpakking"), p.optInt("per_verpakking")) + " " + p.optString("eenheid"),
                n?.let { "$it ${p.optString("verpakking")}" } ?: "–", R.color.navy) { vraag(p) }
        }
        werkKnopBij()
    }

    private fun vraag(p: JSONObject) {
        val id = p.getInt("id")
        Cijferpad.vraag(this, getString(R.string.hoeveel_binnen, p.optString("naam")), verpakkingen[id]?.toString() ?: "",
            eenheid = p.optString("verpakking"), max = 4) { tekst ->
            val n = tekst.toIntOrNull()
            if (n == null || n == 0) verpakkingen.remove(id) else verpakkingen[id] = n
            verzoekId = null
            bouw()
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

    private fun scan(code: String, naKoppelen: Boolean = false) {
        val norm = Catalogus.normaliseerCode(code) ?: return melding(getString(R.string.scan_geen_barcode, code))
        val doos = opCode[norm]
        val treffer = Catalogus.opBarcode(norm)
        val productId = doos?.optInt("product_id") ?: treffer?.product?.id
        val p = productId?.let { product(it) }
        if (p == null) {
            if (productId != null) return melding(getString(R.string.geen_keukenproduct))
            if (naKoppelen) return melding(getString(R.string.keuken_nog_onbekend), lang = true)
            tril(150)
            teKoppelen = norm
            koppelen.launch(KoppelenActivity.intent(this, norm))
            return
        }
        val aantal = doos?.optInt("aantal") ?: treffer?.barcode?.aantal ?: 1
        val omschrijving = doos?.optString("omschrijving") ?: treffer?.barcode?.artikel ?: norm
        scans += Scan(p.getInt("id"), aantal, omschrijving)
        verzoekId = null
        tril()
        melding(getString(R.string.keuken_scan_erbij, aantal, p.optString("eenheid"), p.optString("naam"), omschrijving))
        bouw()
    }

    private fun opslaan() {
        if (aantalProducten == 0) return
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        val lijst = JSONObject()
        verpakkingen.forEach { (pid, n) -> lijst.put(pid.toString(), n) }
        val gescand = JSONObject()
        scans.groupBy { it.productId }.forEach { (pid, s) -> gescand.put(pid.toString(), s.sumOf { it.aantal }) }
        b.onderKnop.isEnabled = false
        bezig {
            try {
                val antwoord = Api.post(this, "/api/app/keuken/inboeken",
                    JSONObject().put("verpakkingen", lijst).put("gescand", gescand), verzoekId = id)
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
