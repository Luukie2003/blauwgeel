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
import org.json.JSONObject

/** De keukentelling (hoeveel er nu is; wat minder is dan de voorraad is verkocht) of keuken inboeken (hoeveel
 * verpakkingen er binnenkwamen, bijvoorbeeld 2 dozen frikandellen van 40). Tik op een product voor het cijferpad, of
 * scan een volle doos of zak: dan telt wat erin zit er meteen bij (uit het artikel, dus per supermarkt anders).
 * Opslaan doet hetzelfde als Keuken > Tellen en Keuken > Inboeken op de site; bij tellen kies je dan of het een
 * begintelling is (dan is het verschil geen verkoop). */
class KeukenInvoerActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var modus = TELLEN
    private val isTellen get() = modus == TELLEN
    private var producten: List<JSONObject> = emptyList()
    private val waarden = mutableMapOf<Int, Int>()
    /** Inboeken: wat er per product gescand is, in de eenheid van het product (los van [waarden] in verpakkingen). */
    private val gescand = mutableMapOf<Int, Int>()
    private var eersteTelling = false
    private val waardeViews = mutableMapOf<Int, TextView>()
    private var verzoekId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        modus = intent.getStringExtra(EXTRA_MODUS) ?: TELLEN
        richtBalkIn(b.balk, getString(if (isTellen) R.string.keukentelling else R.string.keuken_inboeken))
        b.verversen.isEnabled = false
        b.onderKnop.isVisible = true
        b.onderKnop.setOnClickListener { opslaan() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (waarden.isEmpty() && gescand.isEmpty()) return finish()
                AlertDialog.Builder(this@KeukenInvoerActivity)
                    .setMessage(R.string.invoer_weggooien_vraag)
                    .setPositiveButton(R.string.weggooien) { _, _ -> finish() }
                    .setNegativeButton(R.string.annuleren, null)
                    .show()
            }
        })
        werkKnopBij()
        bezig {
            val keuken = Api.getJson(this, "/api/app/keuken")
            producten = keuken.getJSONArray("producten").objecten()
            eersteTelling = keuken.optBoolean("eerste_telling")
            bouw()
        }
    }

    private fun bouw() {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        Lijst.kaart(inhoud, R.drawable.melding_info).let {
            Lijst.tekst(it, getString(if (isTellen) R.string.keukentelling_uitleg else R.string.keuken_inboeken_uitleg), kleur = R.color.tekst)
        }
        if (producten.isEmpty()) return Lijst.leeg(inhoud, getString(R.string.geen_keukenproducten))
        // Per subcategorie (snacks, sauzen, ...) een kaart, zoals op de site.
        val meerdereGroepen = producten.map { it.optString("subcategorie") }.distinct().size > 1
        var groep: String? = null
        var kaart: LinearLayout? = null
        for (p in producten) {
            val sub = p.optString("subcategorie")
            if (kaart == null || sub != groep) {
                if (meerdereGroepen) Lijst.kop(inhoud, sub.ifEmpty { getString(R.string.overig) })
                kaart = Lijst.kaart(inhoud)
                groep = sub
            }
            val id = p.getInt("id")
            val detail = if (isTellen) getString(R.string.voorraad_nu, p.optInt("voorraad"), p.optString("eenheid"))
            else getString(R.string.per_verpakking, p.optString("verpakking"), p.optInt("per_verpakking")) + " " + p.optString("eenheid")
            val regel = Lijst.regel(kaart, p.optString("naam"), detail, "–", R.color.navy) { vraag(p) }
            waardeViews[id] = regel.getChildAt(regel.childCount - 1) as TextView
        }
        werkBij()
    }

    private fun vraag(p: JSONObject) {
        val id = p.getInt("id")
        val titel = if (isTellen) getString(R.string.hoeveel_nu, p.optString("naam")) else getString(R.string.hoeveel_binnen, p.optString("naam"))
        val eenheid = if (isTellen) p.optString("eenheid") else p.optString("verpakking")
        Cijferpad.vraag(this, titel, waarden[id]?.toString() ?: "", eenheid = eenheid, max = 5) { tekst ->
            val n = tekst.toIntOrNull()
            if (n == null || (!isTellen && n == 0)) waarden.remove(id) else waarden[id] = n
            verzoekId = null
            werkBij()
        }
    }

    private fun werkBij() {
        for (p in producten) {
            val id = p.getInt("id")
            val n = waarden[id]
            val stuks = gescand[id]
            waardeViews[id]?.text = when {
                isTellen -> if (n == null) "–" else "$n ${p.optString("eenheid")}"
                n == null && stuks == null -> "–"
                else -> listOfNotNull(n?.let { "$it ${p.optString("verpakking")}" }, stuks?.let { "+$it ${p.optString("eenheid")}" })
                    .joinToString(" ")
            }
        }
        werkKnopBij()
    }

    private val aantalProducten get() = (waarden.keys + gescand.keys).size

    private fun werkKnopBij() {
        val iets = aantalProducten > 0
        b.onderKnop.isEnabled = iets
        b.onderKnop.alpha = if (iets) 1f else 0.5f
        b.onderKnop.text = if (isTellen) getString(R.string.telling_opslaan_n, aantalProducten) else getString(R.string.inboeken_n, aantalProducten)
    }

    /** Een gescande doos of zak: wat erin zit telt er meteen bij (tellen: bij het getelde aantal, inboeken: bij wat er
     * binnenkwam). Een onbekende barcode koppel je eerst (KoppelenActivity) en scan je daarna nog een keer. */
    override fun bijScan(code: String) {
        val treffer = Catalogus.opBarcode(code)
        if (treffer == null) {
            if (Catalogus.normaliseerCode(code) == null) return melding(getString(R.string.scan_geen_barcode, code))
            melding(getString(R.string.keuken_eerst_koppelen), lang = true)
            KoppelenActivity.open(this, code)
            return
        }
        val p = producten.firstOrNull { it.getInt("id") == treffer.product.id }
            ?: return melding(getString(R.string.geen_keukenproduct))
        val id = p.getInt("id")
        val erbij = treffer.barcode.aantal
        if (isTellen) waarden[id] = (waarden[id] ?: 0) + erbij else gescand[id] = (gescand[id] ?: 0) + erbij
        verzoekId = null
        tril()
        melding(getString(R.string.keuken_scan_erbij, erbij, p.optString("eenheid"), p.optString("naam"), treffer.barcode.artikel))
        werkBij()
    }

    private fun opslaan() {
        if (aantalProducten == 0) return
        if (!isTellen) return verstuur(begintelling = false)
        // Tellen: een gewone telling of een begintelling (de eerste keer staat begintelling al aan).
        var keuze = if (eersteTelling) 1 else 0
        AlertDialog.Builder(this)
            .setTitle(R.string.keuken_soort_telling)
            .setSingleChoiceItems(arrayOf(getString(R.string.keuken_gewone_telling), getString(R.string.keuken_begintelling)), keuze) { _, i -> keuze = i }
            .setPositiveButton(R.string.opslaan) { _, _ -> verstuur(begintelling = keuze == 1) }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun verstuur(begintelling: Boolean) {
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        val lijst = JSONObject()
        waarden.forEach { (pid, n) -> lijst.put(pid.toString(), n) }
        val body = JSONObject().put(if (isTellen) "waarden" else "verpakkingen", lijst)
        if (isTellen) body.put("begintelling", begintelling)
        else body.put("gescand", JSONObject().also { g -> gescand.forEach { (pid, n) -> g.put(pid.toString(), n) } })
        b.onderKnop.isEnabled = false
        bezig {
            try {
                val antwoord = Api.post(this, if (isTellen) "/api/app/keuken/tellen" else "/api/app/keuken/inboeken", body, verzoekId = id)
                tril(60)
                melding(antwoord.optString("melding"), lang = true)
                finish()
            } finally {
                werkKnopBij()
            }
        }
    }

    companion object {
        const val TELLEN = "tellen"
        const val INBOEKEN = "inboeken"
        private const val EXTRA_MODUS = "modus"

        fun open(context: Context, modus: String) =
            context.startActivity(Intent(context, KeukenInvoerActivity::class.java).putExtra(EXTRA_MODUS, modus))
    }
}
