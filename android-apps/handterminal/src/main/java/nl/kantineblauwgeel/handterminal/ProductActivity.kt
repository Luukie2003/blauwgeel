package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityProductBinding
import org.json.JSONObject

/** Eén product: de voorraad, boeken (erin of eruit), de laatste boekingen en de barcodes.
 *
 * Geopend door een scan staat het aantal al goed (een krat van 24: 24) en bij een doos of krat staat "Erin" al aan.
 * Nog een keer scannen van hetzelfde product telt erbij op: drie kratten scannen is 72. Een onbekende barcode scannen
 * op dit scherm vraagt of hij bij dit product hoort; dan is hij in één tik gekoppeld.
 *
 * Boeken gaat met een verzoek_id: valt de verbinding weg, dan probeert de app het vanzelf opnieuw, en de site boekt het
 * toch maar één keer (zie routes/app_api.py). */
class ProductActivity : BasisActivity() {

    private lateinit var b: ActivityProductBinding
    private var productId = 0
    private var product: Catalogus.Product? = null
    private var richting: String? = null
    private var aantal = 1
    private var aantalAangepast = false
    private var reden: String? = null
    private var verzoekId: String? = null
    private var boekt = false
    private var scans = 0
    private var pad: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityProductBinding.inflate(layoutInflater)
        setContentView(b.root)
        productId = intent.getIntExtra(EXTRA_ID, 0)
        product = Catalogus.opId(productId)
        richtBalkIn(b.balk, product?.naam ?: getString(R.string.product), sub = product?.let(::balkSub))

        b.erinKnop.setOnClickListener { kiesRichting("in") }
        b.eruitKnop.setOnClickListener { kiesRichting("uit") }
        b.minKnop.setOnClickListener { zetAantal(maxOf(1, aantal - 1)) }
        b.plusKnop.setOnClickListener { zetAantal(aantal + 1) }
        b.aantal.setOnClickListener {
            Cijferpad.vraag(this, getString(R.string.aantal), aantal.toString(), eenheid = product?.eenheid ?: "") {
                it.toIntOrNull()?.takeIf { n -> n > 0 }?.let(::zetAantal)
            }
        }
        b.boekKnop.setOnClickListener { boek() }
        b.koppelKnop.setOnClickListener { koppelKnop() }
        b.siteKnop.setOnClickListener { WebActivity.open(this, pad ?: "/producten/$productId", product?.naam) }

        bouwRedenen()
        toonProduct()
        intent.getStringExtra(EXTRA_SCAN)?.let { gescand(it, eerste = true) }
        werkBoekKnopBij()
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laadDetail()
    }

    override fun weerVerbonden() = laadDetail()

    private fun balkSub(p: Catalogus.Product) = listOf(p.categorie, p.eenheid).filter { it.isNotEmpty() }.joinToString(" · ")

    // ---------------------------------------------------------------- tonen

    private fun toonProduct() {
        val p = product ?: return
        zetBalkTitel(p.naam)
        zetBalkSub(balkSub(p))
        b.voorraad.text = p.voorraadTekst()
        b.voorraad.setTextColor(getColor(if (p.laag || p.voorraad < 0) R.color.rood_balk else R.color.tekst))
        b.laagLabel.isVisible = p.laag || !p.actief
        b.laagLabel.text = getString(if (!p.actief) R.string.inactief else R.string.laag)
        b.laagLabel.setBackgroundResource(if (!p.actief) R.drawable.badge_grijs else R.drawable.badge_rood)
        if (b.voorraadSub.text.isNullOrEmpty()) b.voorraadSub.text = getString(R.string.minimum, p.minVoorraad)
        bouwSnelKnoppen(p)
        toonBarcodes(p)
        b.aantal.text = getString(R.string.aantal_eenheid, aantal, p.eenheid)
    }

    private fun bouwSnelKnoppen(p: Catalogus.Product) {
        b.snelKnoppen.removeAllViews()
        val stappen = mutableListOf<Pair<String, () -> Unit>>()
        if (p.besteleenheid != null && p.perBesteleenheid > 1) {
            stappen += getString(R.string.een_besteleenheid, p.besteleenheid, p.perBesteleenheid) to {
                zetAantal(if (aantalAangepast) aantal + p.perBesteleenheid else p.perBesteleenheid)
            }
        }
        for (n in listOf(5, 10)) stappen += "+$n" to { zetAantal(if (aantalAangepast) aantal + n else n) }
        for ((tekst, actie) in stappen) {
            val chip = LayoutInflater.from(this).inflate(R.layout.keuze, b.snelKnoppen, false) as TextView
            chip.text = tekst
            chip.setOnClickListener { actie() }
            b.snelKnoppen.addView(chip)
        }
    }

    private fun bouwRedenen() {
        b.redenen.removeAllViews()
        val keuzes = listOf<Pair<String?, String>>(null to getString(R.string.verkocht_of_verbruikt)) +
            Catalogus.dervingRedenen.map { (sleutel, tekst) -> sleutel to tekst.substringBefore(" (") }
        for ((sleutel, tekst) in keuzes) {
            val chip = LayoutInflater.from(this).inflate(R.layout.keuze, b.redenen, false) as TextView
            chip.text = tekst
            chip.isSelected = sleutel == reden
            chip.setOnClickListener {
                reden = sleutel
                for (i in 0 until b.redenen.childCount) b.redenen.getChildAt(i).isSelected = false
                chip.isSelected = true
                verzoekId = null
            }
            b.redenen.addView(chip)
        }
    }

    private fun toonBarcodes(p: Catalogus.Product) {
        b.barcodeLijst.removeAllViews()
        if (p.barcodes.isEmpty()) {
            b.barcodeLijst.addView(regel(getString(R.string.nog_geen_barcode), zacht = true))
        }
        for (code in p.barcodes) {
            val wat = if (code.isDoos) getString(R.string.doos_van, code.aantal, p.eenheid) else getString(R.string.los_aantal, code.aantal, p.eenheid)
            b.barcodeLijst.addView(regel("${code.code}  ·  $wat"))
        }
    }

    private fun regel(tekst: String, zacht: Boolean = false) = TextView(this).apply {
        text = tekst
        textSize = 13f
        setTextColor(getColor(if (zacht) R.color.tekst_zacht else R.color.tekst))
        setPadding(0, dp(this@ProductActivity, 5), 0, dp(this@ProductActivity, 5))
    }

    private fun laadDetail() {
        bezig {
            val detail = Api.getJson(this, "/api/app/producten/$productId")
            pad = detail.tekstOfNull("pad")
            val nieuw = Catalogus.product(detail.getJSONObject("product"))
            Catalogus.werkBij(this, nieuw)
            product = nieuw
            val telling = detail.optJSONObject("laatste_telling")
            b.voorraadSub.text = listOfNotNull(
                getString(R.string.minimum, nieuw.minVoorraad),
                telling?.let { getString(R.string.geteld_op, datum(it.optString("datum")), it.optInt("geteld_aantal")) },
            ).joinToString(" · ")
            toonProduct()
            toonMutaties(detail.optJSONArray("mutaties")?.objecten() ?: emptyList())
        }
    }

    private fun toonMutaties(mutaties: List<JSONObject>) {
        b.mutaties.removeAllViews()
        if (mutaties.isEmpty()) b.mutaties.addView(regel(getString(R.string.nog_geen_boekingen), zacht = true))
        val eenheid = product?.eenheid ?: ""
        for (m in mutaties.take(6)) {
            val teken = if (m.optString("type") == "in") "+" else "−"
            val wat = m.tekstOfNull("reden") ?: m.tekstOfNull("opmerking")
            val tekst = "$teken${m.optInt("aantal")} $eenheid  ·  ${datum(m.optString("datum"), metTijd = true)}" +
                (m.tekstOfNull("naam")?.let { "  ·  $it" } ?: "") + (wat?.let { "\n$it" } ?: "")
            b.mutaties.addView(regel(tekst))
        }
    }

    /** "2026-10-18 14:02" → "18-10 14:02" (of alleen "18-10"). */
    private fun datum(tekst: String, metTijd: Boolean = false): String {
        if (tekst.length < 10) return tekst
        val dag = "${tekst.substring(8, 10)}-${tekst.substring(5, 7)}"
        return if (metTijd && tekst.length >= 16) "$dag ${tekst.substring(11, 16)}" else dag
    }

    // ---------------------------------------------------------------- boeken

    private fun kiesRichting(nieuw: String) {
        richting = nieuw
        b.erinKnop.isSelected = nieuw == "in"
        b.eruitKnop.isSelected = nieuw == "uit"
        b.redenenScroll.isVisible = nieuw == "uit"
        verzoekId = null
        werkBoekKnopBij()
    }

    private fun zetAantal(nieuw: Int) {
        aantal = nieuw.coerceIn(1, 99_999)
        aantalAangepast = true
        verzoekId = null
        b.aantal.text = getString(R.string.aantal_eenheid, aantal, product?.eenheid ?: "")
        werkBoekKnopBij()
    }

    private fun werkBoekKnopBij() {
        val eenheid = product?.eenheid ?: ""
        b.boekKnop.isEnabled = richting != null && !boekt
        b.boekKnop.alpha = if (b.boekKnop.isEnabled) 1f else 0.5f
        b.boekKnop.text = when {
            boekt -> getString(R.string.bezig_met_boeken)
            richting == "in" -> getString(R.string.boek_erin, aantal, eenheid)
            richting == "uit" -> getString(R.string.boek_eruit, aantal, eenheid)
            else -> getString(R.string.kies_erin_of_eruit)
        }
    }

    private fun boek() {
        val r = richting ?: return
        if (boekt) return
        // Hetzelfde verzoek_id bij nog een keer proberen na een fout: dan boekt de site het nooit dubbel.
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        boekt = true
        werkBoekKnopBij()
        bezig {
            try {
                val body = JSONObject().put("type", r).put("aantal", aantal)
                if (r == "uit" && reden != null) body.put("reden", reden)
                val antwoord = Api.post(this, "/api/app/producten/$productId/boeken", body, verzoekId = id)
                val nieuw = Catalogus.product(antwoord.getJSONObject("product"))
                Catalogus.werkBij(this, nieuw)
                product = nieuw
                tril(60)
                melding(antwoord.optString("melding"))
                antwoord.tekstOfNull("waarschuwing")?.let {
                    AlertDialog.Builder(this).setMessage(it).setPositiveButton(R.string.ok, null).show()
                }
                // Klaar voor de volgende boeking.
                verzoekId = null
                richting = null
                reden = null
                aantal = 1
                aantalAangepast = false
                scans = 0
                b.erinKnop.isSelected = false
                b.eruitKnop.isSelected = false
                b.redenenScroll.isVisible = false
                b.scanMelding.isVisible = false
                bouwRedenen()
                toonProduct()
                laadDetail()
            } finally {
                boekt = false
                werkBoekKnopBij()
            }
        }
    }

    // ---------------------------------------------------------------- scannen en koppelen

    override fun bijScan(code: String) {
        val treffer = Catalogus.opBarcode(code)
        when {
            treffer != null && treffer.product.id == productId -> gescand(treffer.barcode.code, eerste = false)
            treffer != null -> {
                ProductActivity.open(this, treffer.product.id, scan = treffer.barcode.code)
                finish()
            }
            Catalogus.normaliseerCode(code)?.length in setOf(8, 13, 14) -> vraagKoppelen(code)
            else -> openScan(code)
        }
    }

    /** Een barcode van dit product is gescand: het aantal erbij (de eerste keer: precies dat aantal). */
    private fun gescand(code: String, eerste: Boolean) {
        val p = product ?: return
        val barcode = p.barcodes.firstOrNull { it.code == Catalogus.normaliseerCode(code) } ?: return
        tril()
        scans = if (eerste) 1 else scans + 1
        zetAantal(if (eerste || !aantalAangepast) barcode.aantal else aantal + barcode.aantal)
        if (barcode.isDoos && richting == null) kiesRichting("in")
        val wat = if (barcode.isDoos) getString(R.string.doos_van, barcode.aantal, p.eenheid) else getString(R.string.los_aantal, barcode.aantal, p.eenheid)
        b.scanMelding.text = if (scans > 1) getString(R.string.n_keer_gescand, scans, wat, barcode.artikel)
        else getString(R.string.gescand, wat, barcode.artikel)
        b.scanMelding.isVisible = true
    }

    private fun koppelKnop() {
        if (Scanner.isAanwezig(this)) {
            Scanner.startScan(this)
            melding(getString(R.string.scan_de_barcode))
        } else {
            Cijferpad.vraag(this, getString(R.string.barcode_intikken), max = 14) { code ->
                if (code.isNotEmpty()) bijScan(code)
            }
        }
    }

    /** Onbekende barcode op dit scherm: hoort hij bij dit product? Eén tik en hij is gekoppeld. */
    private fun vraagKoppelen(code: String) {
        val p = product ?: return
        tril()
        val keuzes = mutableListOf(getString(R.string.koppel_los, p.eenheid))
        val doosAantallen = mutableListOf<Int?>(null)
        if (p.besteleenheid != null && p.perBesteleenheid > 1) {
            keuzes += getString(R.string.koppel_doos, p.besteleenheid, p.perBesteleenheid, p.eenheid)
            doosAantallen += p.perBesteleenheid
        }
        keuzes += getString(R.string.koppel_doos_anders)
        keuzes += getString(R.string.ander_product)
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.onbekende_barcode_bij, Catalogus.normaliseerCode(code), p.naam)))
            .setItems(keuzes.toTypedArray()) { _, i ->
                when {
                    i < doosAantallen.size -> koppel(code, doosAantallen[i])
                    i == keuzes.size - 2 -> Cijferpad.vraag(this, getString(R.string.hoeveel_in_doos), eenheid = p.eenheid) { n ->
                        n.toIntOrNull()?.takeIf { it > 0 }?.let { koppel(code, it) }
                    }
                    else -> KoppelenActivity.open(this, code)
                }
            }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun koppel(code: String, perDoos: Int?) {
        val id = Api.nieuwVerzoekId()
        bezig {
            val body = JSONObject().put("code", code).put("product_id", productId)
            if (perDoos != null) body.put("per_doos", perDoos)
            val antwoord = Api.post(this, "/api/app/barcodes/koppelen", body, verzoekId = id)
            val nieuw = Catalogus.product(antwoord.getJSONObject("product"))
            Catalogus.werkBij(this, nieuw)
            product = nieuw
            toonProduct()
            melding(getString(R.string.gekoppeld))
            gescand(code, eerste = !aantalAangepast)
        }
    }

    companion object {
        private const val EXTRA_ID = "product_id"
        private const val EXTRA_SCAN = "scan"

        fun open(activity: Activity, productId: Int, scan: String? = null) {
            activity.startActivity(Intent(activity, ProductActivity::class.java).putExtra(EXTRA_ID, productId).putExtra(EXTRA_SCAN, scan))
        }
    }
}
