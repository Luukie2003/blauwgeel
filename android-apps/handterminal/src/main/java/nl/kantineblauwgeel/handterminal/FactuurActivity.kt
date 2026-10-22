package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.ActivityFactuurBinding
import org.json.JSONObject
import java.util.Locale

/** Eén factuur inboeken: dozen, kratten en losse verpakkingen scannen. De site weet per barcode wat het is en hoeveel
 * erin zit; hier zie je per product wat erbij komt en of het totaal klopt met het bedrag op de factuur. Hoort de factuur
 * bij een klaargezette bestelling, dan staat bovenaan per besteld product wat er besteld is en wat er al gescand is; wat
 * zonder barcode binnenkomt, zet je er met één tik bij zoals besteld. Een onbekende
 * barcode koppel je meteen (KoppelenActivity), en die scan telt dan alsnog mee. "Afronden en inboeken" zet alles in
 * één keer in de voorraad.
 *
 * Scans gaan op volgorde de wachtrij in: snel achter elkaar tien dozen scannen gaat goed. Elke scan heeft een eigen
 * verzoek_id, dus bij een haperende verbinding probeert de app het opnieuw zonder dat een doos dubbel telt.
 *
 * Scan je een losse verpakking (één zakje chips, één flesje cola) terwijl er een doos of krat van bestaat, dan vraagt de
 * app of je de hele colli wilt inboeken. Het antwoord geldt voor de rest van deze factuur bij dat artikel.
 *
 * Wat geen barcode heeft (fusten, en producten op 'heeft geen barcode') kies je uit de PLU-lijst. "Factuur
 * gecontroleerd" laat eerst zien wat er van de bestelling nog mist (dat wordt manco) en boekt daarna alles in. */
class FactuurActivity : BasisActivity() {

    private lateinit var b: ActivityFactuurBinding
    private var rondeId = 0
    private var ronde: JSONObject? = null
    /** Een scan in de wachtrij; [extra]: hoeveel keer hij er daarna nog bij moet (een volle doos zonder eigen barcode). */
    private class Scan(val code: String, val verzoekId: String, val extra: Int = 0, val melding: String? = null)

    private val wachtrij = ArrayDeque<Scan>()
    private val volleEenheidPerCode = HashMap<String, Boolean>()
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
        b.pluKnop.setOnClickListener { pluKiezen() }
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

        toonBesteld(r.optJSONArray("besteld")?.objecten().orEmpty())

        b.perProduct.removeAllViews()
        val perProduct = r.optJSONArray("per_product")?.objecten() ?: emptyList()
        val metBestelling = !r.isNull("bestelling_id")
        if (perProduct.isEmpty()) b.perProduct.addView(tekst(getString(R.string.nog_niets_gescand), zacht = true))
        for (p in perProduct) {
            val extra = if (metBestelling && !p.optBoolean("besteld")) "   · " + getString(R.string.niet_besteld) else ""
            b.perProduct.addView(tekst("${p.optString("naam")}   +${p.optInt("eenheden")} ${p.optString("eenheid")}   ${euro(p.optDouble("bedrag"))}$extra"))
        }

        b.regels.removeAllViews()
        val regels = r.optJSONArray("regels")?.objecten() ?: emptyList()
        if (regels.isEmpty()) b.regels.addView(tekst(getString(R.string.nog_niets_gescand), zacht = true))
        for (g in regels) b.regels.addView(regelView(g))
        b.afrondenKnop.isEnabled = regels.isNotEmpty()
        b.afrondenKnop.alpha = if (regels.isNotEmpty()) 1f else 0.5f
    }

    /** Bij een klaargezette bestelling: per besteld product besteld en gescand, met een vinkje als alles binnen is.
     * Tik op een product dat nog mist om het erbij te zetten zoals besteld. */
    private fun toonBesteld(besteld: List<JSONObject>) {
        b.besteldKop.isVisible = besteld.isNotEmpty()
        b.besteld.isVisible = besteld.isNotEmpty()
        b.besteld.removeAllViews()
        if (besteld.isEmpty()) return
        b.besteldKop.text = getString(R.string.besteld_kop_n, besteld.count { it.optString("status") == "binnen" }, besteld.size)
        for (x in besteld) {
            val rest = x.optInt("rest")
            val hoeveel = "${x.optInt("besteld_eenheden")} ${x.optString("besteleenheid")}" +
                if (x.optInt("per_besteleenheid", 1) > 1) " (${x.optInt("besteld")} ${x.optString("eenheid")})" else ""
            val (rechts, kleur) = when (x.optString("status")) {
                "binnen" -> "✓" to R.color.groen_tekst
                "deels" -> "−$rest" to R.color.oranje_balk
                else -> getString(R.string.nog_niet_binnen) to R.color.tekst_zacht
            }
            Lijst.regel(b.besteld, x.optString("naam"), getString(R.string.besteld_detail, hoeveel, x.optInt("gescand"), x.optString("eenheid")),
                rechts, kleur, klik = if (rest > 0) ({ zoalsBesteld(x) }) else null)
        }
        if (besteld.count { it.optInt("rest") > 0 } > 1) Lijst.knop(b.besteld, getString(R.string.alles_zoals_besteld)) { zoalsBesteld(null) }
        Lijst.tekst(b.besteld, getString(R.string.besteld_uitleg), grootte = 11.5f)
    }

    /** Wat van de bestelling nog mist erbij zetten zoals besteld: één product ([x]), of alles (null). */
    private fun zoalsBesteld(x: JSONObject?) {
        val vraag = if (x == null) getString(R.string.zoals_besteld_alles_vraag)
        else getString(R.string.zoals_besteld_vraag, x.optString("naam"), x.optInt("rest"), x.optString("eenheid"))
        val verzoekId = Api.nieuwVerzoekId()
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(x?.optString("naam") ?: getString(R.string.zoals_besteld_titel)))
            .setMessage(vraag)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.zoals_besteld) { _, _ ->
                val body = JSONObject()
                x?.let { body.put("product_id", it.getInt("product_id")) }
                bezig {
                    toon(Api.post(this, "/api/facturen/$rondeId/zoals-besteld", body, verzoekId = verzoekId))
                    tril(60)
                }
            }
            .show()
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
        val treffer = Catalogus.opBarcode(code)
        val barcode = treffer?.barcode
        val volle = if (barcode != null && !barcode.isDoos) treffer.product.volleEenheid(barcode) else null
        if (barcode == null || volle == null) return zetInRij(code)
        volleEenheidPerCode[barcode.code]?.let { return zetInRij(barcode, volle, it) }
        val p = treffer.product
        val doos = p.besteleenheid ?: getString(R.string.doos)
        tril()
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.los_gescand_titel)))
            .setMessage(getString(R.string.los_gescand_vraag, getString(R.string.los_aantal, barcode.aantal, p.eenheid), barcode.artikel))
            .setPositiveButton(getString(R.string.los_gescand_vol, doos, volle, p.eenheid)) { _, _ ->
                volleEenheidPerCode[barcode.code] = true
                zetInRij(barcode, volle, true)
            }
            .setNegativeButton(getString(R.string.los_gescand_los, barcode.aantal, p.eenheid)) { _, _ ->
                volleEenheidPerCode[barcode.code] = false
                zetInRij(barcode, volle, false)
            }
            .show()
    }

    /** Een volle doos: de barcode van de doos als die bekend is, anders de losse zo vaak als er in de doos zitten. */
    private fun zetInRij(barcode: Catalogus.Barcode, volle: Int, vol: Boolean) = when {
        !vol -> zetInRij(barcode.code)
        barcode.doosCode != null -> zetInRij(barcode.doosCode)
        else -> {
            val p = Catalogus.opBarcode(barcode.code)?.product
            val melding = p?.let { "+1 ${it.besteleenheid ?: getString(R.string.doos)} ($volle ${it.eenheid}) · ${it.naam}" }
            zetInRij(barcode.code, extra = maxOf(0, volle / maxOf(1, barcode.aantal) - 1), melding = melding)
        }
    }

    private fun zetInRij(code: String, extra: Int = 0, melding: String? = null) {
        wachtrij.addLast(Scan(code, Api.nieuwVerzoekId(), extra, melding))
        volgendeScan()
    }

    private fun volgendeScan() {
        if (bezigMetScan) return
        val volgende = wachtrij.removeFirstOrNull() ?: return
        val code = volgende.code
        bezigMetScan = true
        lifecycleScope.launch {
            try {
                val antwoord = Api.post(this@FactuurActivity, "/api/facturen/$rondeId/scan", JSONObject().put("code", code), verzoekId = volgende.verzoekId)
                antwoord.optJSONObject("ronde")?.let(::toon)
                if (antwoord.optString("status") == "toegevoegd" && volgende.extra > 0) {
                    // Een volle doos zonder eigen barcode: de losse regel zoveel keer extra.
                    val regelId = antwoord.optInt("regel_id")
                    val regel = antwoord.optJSONObject("ronde")?.optJSONArray("regels")?.objecten()?.firstOrNull { it.optInt("id") == regelId }
                    if (regel != null) {
                        toon(Api.post(this@FactuurActivity, "/api/facturen/$rondeId/regels/$regelId",
                            JSONObject().put("aantal", regel.optInt("aantal") + volgende.extra), herhaalbaar = true))
                    }
                }
                val barcode = antwoord.optJSONObject("barcode")
                when (antwoord.optString("status")) {
                    "toegevoegd" -> {
                        tril()
                        b.scanMelding.text = volgende.melding ?: getString(R.string.factuur_gescand, barcode?.optString("omschrijving") ?: code,
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

    // ---------------------------------------------------------------- zonder barcode (PLU)

    /** De PLU-lijst: fusten en producten zonder barcode, met wat er besteld en al binnen is. Tik er een aan en vul in
     * hoeveel (in fusten, kratten). */
    private fun pluKiezen() {
        bezig {
            val lijst = Api.getJson(this, "/api/facturen/$rondeId/plu").getJSONArray("plu").objecten()
            if (lijst.isEmpty()) {
                AlertDialog.Builder(this).setTitle(R.string.plu_titel).setMessage(R.string.plu_leeg)
                    .setPositiveButton(R.string.ok, null).show()
                return@bezig
            }
            val namen = lijst.map { x ->
                val detail = if (x.optInt("besteld") > 0)
                    getString(R.string.plu_regel_besteld, x.optInt("besteld"), x.optInt("gescand"), x.optString("eenheid"))
                else getString(R.string.plu_regel_binnen, x.optInt("gescand"), x.optString("eenheid"))
                "${x.optString("naam")}\n$detail"
            }.toTypedArray()
            AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.plu_titel)))
                .setItems(namen) { _, i -> pluAantal(lijst[i]) }
                .setNegativeButton(R.string.annuleren, null)
                .show()
        }
    }

    private fun pluAantal(x: JSONObject) {
        val eenheid = x.optString("besteleenheid")
        val verzoekId = Api.nieuwVerzoekId()
        Cijferpad.vraag(this, getString(R.string.plu_hoeveel, eenheid, x.optString("naam")), eenheid = eenheid, max = 4) { tekst ->
            val n = tekst.toIntOrNull() ?: 0
            if (n <= 0) return@vraag
            bezig {
                toon(Api.post(this, "/api/facturen/$rondeId/plu",
                    JSONObject().put("product_id", x.getInt("product_id")).put("aantal", n), verzoekId = verzoekId))
                tril(60)
                b.scanMelding.text = "+$n $eenheid · ${x.optString("naam")}"
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
        val mist = r.optJSONArray("nog_niet_binnen")?.objecten().orEmpty()
        val tekst = buildString {
            // Bij een klaargezette bestelling eerst wat er nog mist: dat wordt manco.
            if (!r.isNull("bestelling_id")) {
                if (mist.isEmpty()) append(getString(R.string.gecontroleerd_compleet))
                else {
                    append(getString(R.string.gecontroleerd_mist))
                    for (m in mist) append("\n").append(getString(R.string.gecontroleerd_mist_regel, m.optString("naam"),
                        m.optInt("gescand"), m.optInt("besteld"), m.optString("eenheid")))
                    append("\n\n").append(getString(R.string.gecontroleerd_manco))
                }
                append("\n\n")
            }
            append(getString(R.string.afronden_vraag, r.optInt("scans")))
            if (Math.abs(verschil) >= 0.005) append("\n\n").append(getString(R.string.afronden_verschil, euro(verschil)))
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.afronden_en_inboeken)
            .setMessage(tekst)
            .setNegativeButton(R.string.terug_naar_factuur, null)
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

    companion object {
        private const val EXTRA_ID = "ronde_id"

        fun open(activity: Activity, rondeId: Int) {
            activity.startActivity(Intent(activity, FactuurActivity::class.java).putExtra(EXTRA_ID, rondeId))
        }

        fun naam(context: Context, r: JSONObject) =
            r.tekstOfNull("leverancier") ?: r.tekstOfNull("factuurnummer")?.let { context.getString(R.string.factuur_nr, it) }
            ?: r.takeIf { !it.isNull("bestelling_id") }?.let { context.getString(R.string.bestelling_nr, it.optInt("bestelling_id")) }
            ?: context.getString(R.string.factuur_id, r.optInt("id"))

        fun euro(bedrag: Double): String = "€ " + String.format(Locale("nl", "NL"), "%.2f", bedrag)
    }
}
