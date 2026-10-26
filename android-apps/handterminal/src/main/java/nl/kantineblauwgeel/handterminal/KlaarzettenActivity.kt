package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Een bestelling klaarzetten, zoals "Voorgesteld om te bestellen" op de bestellijst van de site. Staan klaar (met het
 * voorgestelde aantal): wat onder het minimum zit (met het advies van de prognose als die meer vraagt), wat bij een
 * vorige bestelling niet geleverd is, en wat iemand bij het product zelf koos (een aantal colli, ook boven het minimum).
 * Wat waarschijnlijk opraakt staat eronder, nog op 0. Tik op een product om het aantal te veranderen (0 = niet
 * bestellen). Scan een product om het toe te voegen; nog een keer scannen is één colli meer. "Klaarzetten" maakt de
 * bestelling; hij staat dan bij Factuur inboeken. */
class KlaarzettenActivity : BasisActivity() {

    /** [vast]: zelf gekozen (bij het product, hier getikt of gescand): dan verandert de prognose het aantal niet. */
    private class Regel(val p: JSONObject, val soort: String, var aantal: Int, var vast: Boolean = false)

    private lateinit var b: ActivityLijstBinding
    private val regels = mutableListOf<Regel>()
    private var verzoekId: String? = null
    private var geladen = false
    /** Een scan van voordat de lijst er was (of waarmee de bestellijst dit scherm opende). */
    private var wachtendeScan: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.bestelling_klaarzetten))
        b.verversen.isEnabled = false
        b.onderKnop.isVisible = true
        b.onderKnop.setOnClickListener { klaarzetten() }
        wachtendeScan = intent.getStringExtra(EXTRA_SCAN)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (regels.none { it.aantal > 0 }) return finish()
                AlertDialog.Builder(this@KlaarzettenActivity)
                    .setMessage(R.string.klaarzetten_weggooien_vraag)
                    .setPositiveButton(R.string.weggooien) { _, _ -> finish() }
                    .setNegativeButton(R.string.annuleren, null)
                    .show()
            }
        })
        werkKnopBij()
        bezig {
            val lijst = Api.getJson(this, "/api/app/bestellijst")
            lijst.getJSONArray("bestellen").objecten().forEach { regels += Regel(it, "laag", gekozenOf(it, basis(it)), vast = it.heeftGekozen()) }
            lijst.optJSONArray("manco")?.objecten()?.forEach {
                regels += Regel(it, "manco", gekozenOf(it, it.optInt("tekort_besteleenheden")), vast = it.heeftGekozen())
            }
            lijst.optJSONArray("gekozen")?.objecten()?.forEach { regels += Regel(it, "gekozen", it.optInt("gekozen"), vast = true) }
            geladen = true
            toon()
            wachtendeScan?.let {
                wachtendeScan = null
                scan(it)
            }
            // De prognose rekent soms even: daarna het advies erbij, en wat waarschijnlijk opraakt.
            val prognose = Api.getJson(this, "/api/app/bestellijst/prognose")
            val advies = prognose.optJSONObject("producten")
            for (r in regels) {
                val x = advies?.optJSONObject(r.p.getInt("id").toString()) ?: continue
                r.p.put("advies", x.optInt("advies_eenheden"))
                r.p.put("bijstelling", x.optInt("bijstelling"))
                // Hoger als de prognose meer vraagt; lager alleen als iemand de prognose omlaag bijstelde.
                if (r.soort == "laag" && !r.vast && (x.optInt("advies_eenheden") > r.aantal || x.optInt("bijstelling") < 0)) {
                    r.aantal = x.optInt("advies_eenheden")
                }
            }
            val al = regels.map { it.p.getInt("id") }.toSet()
            prognose.optJSONArray("extra")?.objecten()?.filter { it.getInt("id") !in al }?.forEach {
                it.put("advies", it.optInt("advies_eenheden"))
                // Zelf de prognose omhoog bijgesteld (bij het product, app 2.13.0): dan staat hij al klaar.
                regels += Regel(it, "opraken", if (it.optInt("bijstelling") > 0) it.optInt("advies_eenheden") else 0)
            }
            toon()
        }
    }

    private fun JSONObject.heeftGekozen() = has("gekozen") && !isNull("gekozen")

    private fun gekozenOf(p: JSONObject, anders: Int) = if (p.heeftGekozen()) p.optInt("gekozen") else anders

    /** Het gewone voorstel: de vaste bestelhoeveelheid, of tot het minimum, in hele besteleenheden. */
    private fun basis(p: JSONObject): Int {
        val per = maxOf(1, p.optInt("per_besteleenheid", 1))
        val tekort = if (p.optInt("bestel_hoeveelheid") > 0) p.optInt("bestel_hoeveelheid") else p.optInt("min_voorraad") - p.optInt("voorraad")
        return maxOf(1, (tekort + per - 1) / per)
    }

    private fun eenheid(p: JSONObject) = p.tekstOfNull("besteleenheid") ?: p.optString("eenheid")

    private fun toon() {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        Lijst.kaart(inhoud, R.drawable.melding_info).let { Lijst.tekst(it, getString(R.string.klaarzetten_uitleg), kleur = R.color.tekst) }
        val groepen = listOf(
            "gescand" to R.string.klaarzetten_gescand,
            "gekozen" to R.string.klaarzetten_gekozen,
            "laag" to R.string.klaarzetten_laag,
            "manco" to R.string.klaarzetten_manco,
            "opraken" to R.string.raakt_waarschijnlijk_op,
        )
        for ((soort, kop) in groepen) {
            val groep = regels.filter { it.soort == soort }
            if (groep.isEmpty()) continue
            Lijst.kop(inhoud, getString(kop))
            val kaart: LinearLayout = Lijst.kaart(inhoud, if (soort == "manco") R.drawable.rand_links_oranje else R.drawable.kaart)
            for (r in groep) {
                val p = r.p
                val detail = listOfNotNull(
                    getString(R.string.voorraad_min, p.optInt("voorraad"), p.optInt("min_voorraad"), p.optString("eenheid")),
                    if (soort == "manco") getString(R.string.niet_geleverd_bij, p.optJSONArray("bestellingen")?.let { a -> (0 until a.length()).joinToString(", #") { a.optInt(it).toString() } } ?: "")
                    else null,
                    if (p.has("advies")) getString(R.string.advies_n, p.optInt("advies"), eenheid(p)) else null,
                    if (p.heeftGekozen() && soort != "gekozen") getString(R.string.zelf_gekozen) else null,
                    p.optInt("bijstelling").takeIf { it != 0 }?.let { getString(R.string.bijgesteld_n, (if (it > 0) "+" else "") + it) },
                ).joinToString(" · ")
                Lijst.regel(kaart, p.optString("naam"), detail, if (r.aantal > 0) "${r.aantal} ${eenheid(p)}" else "–",
                    if (r.aantal > 0) R.color.navy else R.color.tekst_zacht) { vraag(r) }
            }
        }
        if (regels.isEmpty()) Lijst.leeg(inhoud, getString(R.string.niets_bestellen))
        werkKnopBij()
    }

    private fun vraag(r: Regel) {
        val p = r.p
        Cijferpad.vraag(this, getString(R.string.hoeveel_bestellen, p.optString("naam")), if (r.aantal > 0) r.aantal.toString() else "",
            eenheid = eenheid(p), max = 4) { tekst ->
            r.aantal = tekst.toIntOrNull() ?: 0
            r.vast = true
            verzoekId = null
            toon()
        }
    }

    // ---------------------------------------------------------------- scannen

    override fun bijScan(code: String) = scan(code)

    /** Een product scannen (barcode, ook van de doos, of de QR-code van een schaplabel): het komt erbij met 1 colli,
     * of één colli meer als het er al op staat (en aan staat). */
    private fun scan(code: String) {
        tril()
        if (!geladen) {
            wachtendeScan = code
            return
        }
        val id = Regex("/(?:scan|producten)/(\\d+)").find(code)?.groupValues?.get(1)?.toIntOrNull()
            ?: Catalogus.opBarcode(code)?.product?.id
        if (id != null) return voegToe(id)
        if (Catalogus.normaliseerCode(code) == null) return melding(getString(R.string.scan_geen_barcode, code))
        // Onbekend op het toestel: misschien net op een ander toestel gekoppeld. Eerst de lijst verversen.
        bezig {
            try {
                Catalogus.ververs(this)
            } catch (e: Api.Fout) {
                // Geen verbinding: dan met wat we hebben.
            }
            val treffer = Catalogus.opBarcode(code)
            if (treffer != null) voegToe(treffer.product.id) else melding(getString(R.string.barcode_onbekend_bestellen, code), lang = true)
        }
    }

    private fun voegToe(id: Int) {
        val bestaand = regels.firstOrNull { it.p.optInt("id") == id }
        val regel = if (bestaand != null) {
            bestaand.aantal = if (bestaand.aantal > 0) bestaand.aantal + 1 else maxOf(1, bestaand.p.optInt("advies"))
            bestaand.vast = true
            bestaand
        } else {
            val c = Catalogus.opId(id) ?: return melding(getString(R.string.product_niet_gevonden))
            val p = JSONObject()
                .put("id", c.id).put("naam", c.naam).put("eenheid", c.eenheid)
                .put("voorraad", c.voorraad).put("min_voorraad", c.minVoorraad)
                .put("besteleenheid", if (c.perBesteleenheid > 1) c.besteleenheid else JSONObject.NULL)
                .put("per_besteleenheid", c.perBesteleenheid)
                .put("leverancier", c.leverancier ?: JSONObject.NULL)
            Regel(p, "gescand", 1, vast = true).also { regels.add(0, it) }
        }
        verzoekId = null
        tril(60)
        toon()
        melding("${regel.p.optString("naam")}: ${regel.aantal} ${eenheid(regel.p)}")
    }

    // ---------------------------------------------------------------- klaarzetten

    private fun werkKnopBij() {
        val n = regels.count { it.aantal > 0 }
        b.onderKnop.isEnabled = n > 0
        b.onderKnop.alpha = if (n > 0) 1f else 0.5f
        b.onderKnop.text = getString(R.string.klaarzetten_n, n)
    }

    private fun klaarzetten() {
        val gekozen = regels.filter { it.aantal > 0 }
        if (gekozen.isEmpty()) return
        // Per leverancier een eigen bestelling (zie bestellen.maak_bestellingen op de site): zo staat het ook hier.
        val perLeverancier = gekozen.groupBy { it.p.tekstOfNull("leverancier") }.entries
            .sortedWith(compareBy({ it.key == null }, { it.key?.lowercase() }))
        val tekst = perLeverancier.joinToString("\n\n") { (lev, groep) ->
            (lev ?: getString(R.string.zonder_leverancier)) + ":\n" +
                groep.joinToString("\n") { "${it.aantal} ${eenheid(it.p)} ${it.p.optString("naam")}" }
        }
        AlertDialog.Builder(this)
            .setTitle(if (perLeverancier.size > 1) getString(R.string.n_bestellingen_klaarzetten, perLeverancier.size) else getString(R.string.bestelling_klaarzetten))
            .setMessage(tekst)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.klaarzetten) { _, _ ->
                val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
                val aantallen = JSONObject()
                gekozen.forEach { aantallen.put(it.p.getInt("id").toString(), it.aantal) }
                b.onderKnop.isEnabled = false
                bezig {
                    try {
                        val antwoord = Api.post(this, "/api/app/bestellijst/bestellen", JSONObject().put("aantallen", aantallen), verzoekId = id)
                        tril(60)
                        melding(antwoord.optString("melding"), lang = true)
                        finish()
                    } finally {
                        werkKnopBij()
                    }
                }
            }
            .show()
    }

    companion object {
        private const val EXTRA_SCAN = "scan"

        /** [scan]: een product dat net op de bestellijst gescand is; dat komt er meteen bij. */
        fun open(context: Context, scan: String? = null) =
            context.startActivity(Intent(context, KlaarzettenActivity::class.java).putExtra(EXTRA_SCAN, scan))
    }
}
