package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.ActivityFactuurBinding
import org.json.JSONObject
import java.util.Locale

/** Eén factuur inboeken: dozen, kratten en losse verpakkingen scannen. De site weet per barcode wat het is en hoeveel
 * erin zit; hier zie je per product wat erbij komt en of het totaal klopt met het bedrag op de factuur. Een onbekende
 * barcode koppel je meteen (KoppelenActivity), en die scan telt dan alsnog mee. "Afronden en inboeken" zet alles in
 * één keer in de voorraad.
 *
 * Scans gaan op volgorde de wachtrij in: snel achter elkaar tien dozen scannen gaat goed. Elke scan heeft een eigen
 * verzoek_id, dus bij een haperende verbinding probeert de app het opnieuw zonder dat een doos dubbel telt. */
class FactuurActivity : BasisActivity() {

    private lateinit var b: ActivityFactuurBinding
    private var rondeId = 0
    private var ronde: JSONObject? = null
    private val wachtrij = ArrayDeque<Pair<String, String>>() // (code, verzoek_id)
    private var bezigMetScan = false
    private var afrondId: String? = null

    private val koppelen = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        r.data?.getStringExtra(KoppelenActivity.EXTRA_CODE)?.takeIf { r.resultCode == RESULT_OK }?.let { scan(it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityFactuurBinding.inflate(layoutInflater)
        setContentView(b.root)
        rondeId = intent.getIntExtra(EXTRA_ID, 0)
        richtBalkIn(b.balk, getString(R.string.factuur))
        b.bedragKnop.setOnClickListener { vraagBedrag() }
        b.intikKnop.setOnClickListener {
            Cijferpad.vraag(this, getString(R.string.barcode_intikken), max = 14) { code -> if (code.isNotEmpty()) scan(code) }
        }
        b.afrondenKnop.setOnClickListener { afronden() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            val r = Api.getJson(this, "/api/facturen/$rondeId")
            if (r.optString("status") != "open") {
                melding(getString(R.string.factuur_al_afgerond))
                finish()
                return@bezig
            }
            toon(r)
        }
    }

    // ---------------------------------------------------------------- tonen

    private fun toon(r: JSONObject) {
        ronde = r
        zetBalkTitel(naam(this, r))
        zetBalkSub(r.tekstOfNull("factuurnummer")?.let { getString(R.string.factuur_nr, it) } ?: Sessie.naam)
        b.totaal.text = euro(r.optDouble("totaal"))
        b.scans.text = resources.getQuantityString(R.plurals.n_scans, r.optInt("scans"), r.optInt("scans"))
        if (r.isNull("factuurbedrag")) {
            b.bedrag.text = getString(R.string.tik_om_in_te_vullen)
            b.bedrag.textSize = 15f
            b.verschil.text = ""
        } else {
            b.bedrag.text = euro(r.optDouble("factuurbedrag"))
            b.bedrag.textSize = 22f
            val verschil = r.optDouble("verschil")
            b.verschil.text = if (Math.abs(verschil) < 0.005) getString(R.string.klopt) else getString(R.string.verschil, euro(verschil))
            b.verschil.setTextColor(getColor(if (Math.abs(verschil) < 0.005) R.color.groen else R.color.oranje_balk))
        }

        b.perProduct.removeAllViews()
        val perProduct = r.optJSONArray("per_product")?.objecten() ?: emptyList()
        if (perProduct.isEmpty()) b.perProduct.addView(tekst(getString(R.string.nog_niets_gescand), zacht = true))
        for (p in perProduct) {
            b.perProduct.addView(tekst("${p.optString("naam")}   +${p.optInt("eenheden")} ${p.optString("eenheid")}   ${euro(p.optDouble("bedrag"))}"))
        }

        b.regels.removeAllViews()
        val regels = r.optJSONArray("regels")?.objecten() ?: emptyList()
        if (regels.isEmpty()) b.regels.addView(tekst(getString(R.string.nog_niets_gescand), zacht = true))
        for (g in regels) b.regels.addView(regelView(g))
        b.afrondenKnop.isEnabled = regels.isNotEmpty()
        b.afrondenKnop.alpha = if (regels.isNotEmpty()) 1f else 0.5f
    }

    private fun tekst(waarde: String, zacht: Boolean = false) = TextView(this).apply {
        text = waarde
        textSize = 13f
        setTextColor(getColor(if (zacht) R.color.tekst_zacht else R.color.tekst))
        setPadding(0, dp(context, 6), 0, dp(context, 6))
    }

    /** Eén scanregel: wat het is, hoe vaak gescand, met min en plus om een verkeerde scan te verbeteren. */
    private fun regelView(g: JSONObject): LinearLayout {
        val regel = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
        }
        val links = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        links.addView(TextView(this).apply {
            text = g.optString("omschrijving")
            textSize = 13f
            setTextColor(getColor(R.color.tekst))
        })
        links.addView(TextView(this).apply {
            text = "${g.optString("product")} · +${g.optInt("eenheden")} ${g.optString("eenheid")}"
            textSize = 12f
            setTextColor(getColor(R.color.tekst_zacht))
        })
        regel.addView(links, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val aantal = g.optInt("aantal")
        regel.addView(knop(R.drawable.ic_min) { zetAantal(g.getInt("id"), aantal - 1) })
        regel.addView(TextView(this).apply {
            text = "×$aantal"
            textSize = 16f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(getColor(R.color.tekst))
            gravity = android.view.Gravity.CENTER
            minWidth = dp(context, 40)
        })
        regel.addView(knop(R.drawable.ic_plus) { zetAantal(g.getInt("id"), aantal + 1) })
        return regel
    }

    private fun knop(icoon: Int, actie: () -> Unit) = ImageView(this).apply {
        setImageResource(icoon)
        setColorFilter(getColor(R.color.tekst))
        setBackgroundResource(R.drawable.toets_licht)
        scaleType = ImageView.ScaleType.CENTER
        setOnClickListener { actie() }
        layoutParams = LinearLayout.LayoutParams(dp(context, 40), dp(context, 40)).apply { setMargins(dp(context, 2), dp(context, 4), dp(context, 2), dp(context, 4)) }
    }

    // ---------------------------------------------------------------- scannen

    override fun bijScan(code: String) = scan(code)

    private fun scan(code: String) {
        wachtrij.addLast(code to Api.nieuwVerzoekId())
        volgendeScan()
    }

    private fun volgendeScan() {
        if (bezigMetScan) return
        val (code, verzoekId) = wachtrij.removeFirstOrNull() ?: return
        bezigMetScan = true
        lifecycleScope.launch {
            try {
                val antwoord = Api.post(this@FactuurActivity, "/api/facturen/$rondeId/scan", JSONObject().put("code", code), verzoekId = verzoekId)
                antwoord.optJSONObject("ronde")?.let(::toon)
                val barcode = antwoord.optJSONObject("barcode")
                when (antwoord.optString("status")) {
                    "toegevoegd" -> {
                        tril()
                        b.scanMelding.text = getString(R.string.factuur_gescand, barcode?.optString("omschrijving") ?: code,
                            barcode?.optJSONObject("product")?.optString("naam") ?: "")
                    }
                    "onbekend" -> {
                        tril(150)
                        wachtrij.clear() // eerst deze koppelen; de rest scan je daarna opnieuw
                        koppelen.launch(KoppelenActivity.intent(this@FactuurActivity, barcode?.optString("code") ?: code))
                    }
                    "gesloten" -> {
                        melding(antwoord.optString("melding"), lang = true)
                        finish()
                    }
                    else -> {
                        tril(150)
                        melding(antwoord.optString("melding"), lang = true)
                    }
                }
            } catch (f: Api.Fout) {
                // Niet gelukt, ook niet na opnieuw proberen: laat het weten en haal de stand op, dan zie je wat er staat.
                wachtrij.clear()
                toonFout(f)
                if (f.tijdelijk) b.scanMelding.text = getString(R.string.scan_niet_zeker, code)
            } finally {
                bezigMetScan = false
                volgendeScan()
            }
        }
    }

    private fun zetAantal(regelId: Int, aantal: Int) {
        bezig {
            toon(Api.post(this, "/api/facturen/$rondeId/regels/$regelId", JSONObject().put("aantal", maxOf(0, aantal)), herhaalbaar = true))
        }
    }

    // ---------------------------------------------------------------- bedrag en afronden

    private fun vraagBedrag() {
        val r = ronde ?: return
        val nu = if (r.isNull("factuurbedrag")) "" else String.format(Locale("nl", "NL"), "%.2f", r.optDouble("factuurbedrag"))
        Cijferpad.vraag(this, getString(R.string.bedrag_op_factuur), nu, decimaal = true, voor = "€") { tekst ->
            // werk_gegevens_bij zet alle gegevens tegelijk: de rest gaat ongewijzigd mee.
            val body = JSONObject()
                .put("factuurbedrag", tekst.replace(',', '.').ifEmpty { null } ?: JSONObject.NULL)
                .put("leverancier_id", r.opt("leverancier_id"))
                .put("factuurnummer", r.opt("factuurnummer"))
                .put("bestelling_id", r.opt("bestelling_id"))
                .put("opmerking", r.opt("opmerking"))
            bezig { toon(Api.post(this, "/api/facturen/$rondeId", body, herhaalbaar = true)) }
        }
    }

    private fun afronden() {
        val r = ronde ?: return
        val verschil = if (r.isNull("verschil")) 0.0 else r.optDouble("verschil")
        val tekst = buildString {
            append(getString(R.string.afronden_vraag, r.optInt("scans")))
            if (Math.abs(verschil) >= 0.005) append("\n\n").append(getString(R.string.afronden_verschil, euro(verschil)))
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.afronden_en_inboeken)
            .setMessage(tekst)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.inboeken) { _, _ ->
                b.afrondenKnop.isEnabled = false
                val verzoekId = afrondId ?: Api.nieuwVerzoekId().also { afrondId = it }
                bezig {
                    try {
                        val antwoord = Api.post(this, "/api/facturen/$rondeId/afronden", verzoekId = verzoekId)
                        val s = antwoord.getJSONObject("samenvatting")
                        tril(80)
                        AlertDialog.Builder(this)
                            .setTitle(R.string.ingeboekt)
                            .setMessage(getString(R.string.ingeboekt_tekst, s.optInt("eenheden"), s.optInt("producten")))
                            .setPositiveButton(R.string.ok) { _, _ -> finish() }
                            .setOnDismissListener { finish() }
                            .show()
                        try {
                            Catalogus.ververs(this)
                        } catch (f: Api.Fout) {
                        }
                    } finally {
                        b.afrondenKnop.isEnabled = true
                    }
                }
            }
            .show()
    }

    override fun vulMenu(menu: Menu) {
        menu.add(0, 100, 0, R.string.op_de_website)
    }

    override fun bijMenu(id: Int): Boolean {
        if (id != 100) return false
        WebActivity.open(this, "/facturen/$rondeId", getString(R.string.factuur))
        return true
    }

    companion object {
        private const val EXTRA_ID = "ronde_id"

        fun open(activity: Activity, rondeId: Int) {
            activity.startActivity(Intent(activity, FactuurActivity::class.java).putExtra(EXTRA_ID, rondeId))
        }

        fun naam(context: Context, r: JSONObject) =
            r.tekstOfNull("leverancier") ?: r.tekstOfNull("factuurnummer")?.let { context.getString(R.string.factuur_nr, it) }
            ?: context.getString(R.string.factuur_id, r.optInt("id"))

        fun euro(bedrag: Double): String = "€ " + String.format(Locale("nl", "NL"), "%.2f", bedrag)
    }
}
