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
 * scan het. Opslaan doet hetzelfde als Keuken > Tellen en Keuken > Inboeken op de site. */
class KeukenInvoerActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var modus = TELLEN
    private val isTellen get() = modus == TELLEN
    private var producten: List<JSONObject> = emptyList()
    private val waarden = mutableMapOf<Int, Int>()
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
                if (waarden.isEmpty()) return finish()
                AlertDialog.Builder(this@KeukenInvoerActivity)
                    .setMessage(R.string.invoer_weggooien_vraag)
                    .setPositiveButton(R.string.weggooien) { _, _ -> finish() }
                    .setNegativeButton(R.string.annuleren, null)
                    .show()
            }
        })
        werkKnopBij()
        bezig {
            producten = Api.getJson(this, "/api/app/keuken").getJSONArray("producten").objecten()
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
            waardeViews[id]?.text = when {
                n == null -> "–"
                isTellen -> "$n ${p.optString("eenheid")}"
                else -> "$n ${p.optString("verpakking")}"
            }
        }
        werkKnopBij()
    }

    private fun werkKnopBij() {
        b.onderKnop.isEnabled = waarden.isNotEmpty()
        b.onderKnop.alpha = if (waarden.isNotEmpty()) 1f else 0.5f
        b.onderKnop.text = if (isTellen) getString(R.string.telling_opslaan_n, waarden.size) else getString(R.string.inboeken_n, waarden.size)
    }

    /** Een gescand keukenproduct: meteen het cijferpad voor dat product. */
    override fun bijScan(code: String) {
        val treffer = Catalogus.opBarcode(code)
        val p = treffer?.let { t -> producten.firstOrNull { it.getInt("id") == t.product.id } }
        if (p == null) {
            melding(getString(R.string.geen_keukenproduct))
            return
        }
        tril()
        vraag(p)
    }

    private fun opslaan() {
        if (waarden.isEmpty()) return
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        val lijst = JSONObject()
        waarden.forEach { (pid, n) -> lijst.put(pid.toString(), n) }
        val body = JSONObject().put(if (isTellen) "waarden" else "verpakkingen", lijst)
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
