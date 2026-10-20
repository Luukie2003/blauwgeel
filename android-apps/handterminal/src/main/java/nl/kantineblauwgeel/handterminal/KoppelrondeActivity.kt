package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De koppelronde: alle producten die nog geen barcode van een losse verpakking hebben, één voor één. Scan één los
 * exemplaar (een flesje, een blikje, een zakje) en het volgende product staat klaar. Overslaan kan, en wat geen barcode
 * heeft (tapbier, een portie uit de keuken) zet je op "heeft geen barcode", zodat de lijst echt leeg kan. Dozen en
 * kratten horen er niet bij: die komen bij het inboeken van facturen. Zie routes/app_api_barcodes.py. */
class KoppelrondeActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var teDoen = mutableListOf<JSONObject>()
    private var geenBarcode = listOf<JSONObject>()
    private var gekoppeld = 0
    private var totaal = 0
    private var plek = 0

    /** Hoeveel er in één gescande verpakking zit (meestal 1), voor het huidige product. */
    private var perScan = 1

    /** De laatste koppeling, om ongedaan te kunnen maken: (barcode, productnaam). */
    private var laatste: Pair<String, String>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.koppelronde))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                neem(Api.getJson(this, "/api/app/koppelronde"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    /** Het antwoord van de site overnemen; het product dat nu in beeld is, blijft in beeld als het er nog is. */
    private fun neem(data: JSONObject) {
        val huidig = teDoen.getOrNull(plek)?.optInt("id")
        teDoen = data.optJSONArray("te_doen")?.objecten().orEmpty().toMutableList()
        geenBarcode = data.optJSONArray("geen_barcode")?.objecten().orEmpty()
        gekoppeld = data.optInt("gekoppeld")
        totaal = data.optInt("totaal")
        teDoen.indexOfFirst { it.optInt("id") == huidig }.takeIf { it >= 0 }?.let { plek = it }
        toon()
    }

    private fun toon() {
        if (plek >= teDoen.size) plek = 0
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        zetBalkSub(getString(R.string.n_van_m_gekoppeld, gekoppeld, totaal))

        // Voortgang
        Lijst.ruimte(inhoud, 8)
        inhoud.addView(ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = maxOf(1, totaal)
            progress = gekoppeld + geenBarcode.size
            progressTintList = android.content.res.ColorStateList.valueOf(getColor(R.color.groen))
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(this, 10)))

        laatste?.let { (code, naam) ->
            val kaart = Lijst.kaart(inhoud, R.drawable.rand_links_navy)
            Lijst.regel(kaart, getString(R.string.gekoppeld_aan, naam), code, getString(R.string.ongedaan), R.color.navy) { ongedaan(code) }
        }

        val p = teDoen.getOrNull(plek)
        if (p == null) {
            Lijst.kop(inhoud, getString(R.string.koppelronde))
            Lijst.leeg(inhoud, getString(R.string.koppelronde_klaar))
        } else {
            Lijst.kop(inhoud, getString(R.string.nu_scannen, plek + 1, teDoen.size))
            val kaart = Lijst.kaart(inhoud)
            val foto = ImageView(this).apply {
                scaleType = ImageView.ScaleType.FIT_CENTER
                setPadding(0, dp(context, 10), 0, 0)
            }
            kaart.addView(foto, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(this, 150)))
            Fotos.toon(foto, p.tekstOfNull("foto_groot"))
            kaart.addView(TextView(this).apply {
                text = p.optString("naam")
                textSize = 24f
                gravity = Gravity.CENTER
                setTextColor(getColor(R.color.tekst))
                typeface = Typeface.DEFAULT_BOLD
                setPadding(dp(context, 12), dp(context, 8), dp(context, 12), 0)
            })
            kaart.addView(TextView(this).apply {
                text = p.optString("categorie")
                textSize = 13f
                gravity = Gravity.CENTER
                setTextColor(getColor(R.color.tekst_zacht))
            })
            kaart.addView(TextView(this).apply {
                text = getString(R.string.scan_een_los, p.optString("eenheid"))
                textSize = 15f
                gravity = Gravity.CENTER
                setTextColor(getColor(R.color.navy))
                typeface = Typeface.DEFAULT_BOLD
                setPadding(dp(context, 12), dp(context, 10), dp(context, 12), dp(context, 10))
            })
            Lijst.regel(kaart, getString(R.string.per_scan), getString(R.string.per_scan_uitleg),
                "$perScan ${p.optString("eenheid")}", R.color.navy) { vraagPerScan(p) }
            Lijst.knop(kaart, getString(R.string.barcode_intikken)) {
                Cijferpad.vraag(this, getString(R.string.barcode_intikken), max = 14) { code -> if (code.isNotEmpty()) bijScan(code) }
            }
            Lijst.knop(kaart, getString(R.string.overslaan)) { volgende() }
            Lijst.knop(kaart, getString(R.string.heeft_geen_barcode)) { zetGeenBarcode(p, true) }

            // Wat er daarna komt: tik om meteen dat product te doen.
            val daarna = (1..minOf(5, teDoen.size - 1)).map { teDoen[(plek + it) % teDoen.size] }
            if (daarna.isNotEmpty()) {
                Lijst.kop(inhoud, getString(R.string.daarna))
                val lijst = Lijst.kaart(inhoud)
                for (d in daarna) Lijst.regel(lijst, d.optString("naam"), d.optString("categorie")) { springNaar(d) }
            }
        }

        if (geenBarcode.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.zonder_barcode_n, geenBarcode.size))
            val lijst = Lijst.kaart(inhoud)
            for (g in geenBarcode) {
                Lijst.regel(lijst, g.optString("naam"), g.optString("categorie"), getString(R.string.terugzetten), R.color.navy) {
                    zetGeenBarcode(g, false)
                }
            }
        }
        Lijst.tekst(inhoud, getString(R.string.koppelronde_uitleg), grootte = 11.5f)
    }

    private fun volgende() {
        if (teDoen.isEmpty()) return
        plek = (plek + 1) % teDoen.size
        perScan = 1
        toon()
    }

    private fun springNaar(p: JSONObject) {
        plek = teDoen.indexOf(p).coerceAtLeast(0)
        perScan = 1
        toon()
    }

    private fun vraagPerScan(p: JSONObject) {
        Cijferpad.vraag(this, getString(R.string.hoeveel_in_verpakking, p.optString("eenheid")), begin = perScan.toString()) { tekst ->
            tekst.toIntOrNull()?.takeIf { it in 1..1000 }?.let {
                perScan = it
                toon()
            }
        }
    }

    // ---------------------------------------------------------------- scannen

    override fun bijScan(code: String) {
        val p = teDoen.getOrNull(plek) ?: return melding(getString(R.string.koppelronde_klaar))
        val schoon = Catalogus.normaliseerCode(code)
        if (schoon == null || schoon.length !in setOf(8, 12, 13, 14)) {
            tril(150)
            return melding(getString(R.string.geen_geldige_barcode, code), lang = true)
        }
        Catalogus.opBarcode(schoon)?.let { treffer ->
            tril(150)
            return melding(getString(R.string.barcode_al_van, treffer.product.naam), lang = true)
        }
        if (schoon.length == 14) {
            // Een code van 14 cijfers zit meestal op een doos of krat; die komen bij het inboeken van facturen.
            AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.doos_gescand_titel)))
                .setMessage(getString(R.string.doos_gescand_vraag, p.optString("naam")))
                .setNegativeButton(R.string.nee, null)
                .setPositiveButton(R.string.toch_koppelen) { _, _ -> koppel(p, schoon) }
                .show()
            return
        }
        koppel(p, schoon)
    }

    private fun koppel(p: JSONObject, code: String) {
        val body = JSONObject().put("code", code).put("product_id", p.getInt("id"))
        if (perScan > 1) body.put("per_verpakking", perScan)
        bezig {
            val antwoord = Api.post(this, "/api/app/barcodes/koppelen", body, verzoekId = Api.nieuwVerzoekId())
            antwoord.optJSONObject("product")?.let { Catalogus.werkBij(this, Catalogus.product(it)) }
            tril(60)
            laatste = code to p.optString("naam")
            teDoen.remove(p)
            gekoppeld++
            perScan = 1
            if (plek >= teDoen.size) plek = 0
            toon()
        }
    }

    private fun ongedaan(code: String) {
        bezig {
            val antwoord = Api.post(this, "/api/app/koppelronde/ongedaan", JSONObject().put("code", code), verzoekId = Api.nieuwVerzoekId())
            antwoord.optJSONObject("product")?.let { Catalogus.werkBij(this, Catalogus.product(it)) }
            melding(antwoord.optString("melding"))
            laatste = null
            val naam = antwoord.optJSONObject("product")?.optInt("id")
            neem(antwoord)
            // Het product dat weer los is, meteen in beeld.
            teDoen.indexOfFirst { it.optInt("id") == naam }.takeIf { it >= 0 }?.let { plek = it; toon() }
        }
    }

    private fun zetGeenBarcode(p: JSONObject, geen: Boolean) {
        bezig {
            val antwoord = Api.post(this, "/api/app/koppelronde/geen-barcode",
                JSONObject().put("product_id", p.getInt("id")).put("geen", geen), herhaalbaar = true)
            tril()
            melding(antwoord.optString("melding"))
            perScan = 1
            neem(antwoord)
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, KoppelrondeActivity::class.java))
    }
}
