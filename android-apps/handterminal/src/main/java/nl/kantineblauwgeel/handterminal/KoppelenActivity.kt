package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.widget.ArrayAdapter
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityKoppelenBinding
import nl.kantineblauwgeel.handterminal.databinding.DialogNieuwProductBinding
import org.json.JSONObject

/** Een onbekende barcode koppelen, in twee tikken: het product kiezen, en dan "één fles" of "een krat van 24". Verder
 * niets invullen (merk, leverancier, inkoopprijs kan later op de site). Daarna opent het product, met de scan al
 * meegeteld. Vanuit Factuur inboeken gaat het terug naar de factuur, die de scan dan alsnog meetelt.
 * Staat het product er nog niet bij (iets nieuws in de levering), dan maak je het hier aan: naam, categorie, eenheid en
 * eventueel de besteleenheid en verkoopprijs (zie maak_product in routes/app_api_meer.py op de site). */
class KoppelenActivity : BasisActivity() {

    private lateinit var b: ActivityKoppelenBinding
    private lateinit var code: String
    private val adapter by lazy { ProductAdapter(this) { kies(it) } }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityKoppelenBinding.inflate(layoutInflater)
        setContentView(b.root)
        code = Catalogus.normaliseerCode(intent.getStringExtra(EXTRA_CODE) ?: "") ?: ""
        richtBalkIn(b.balk, getString(R.string.barcode_koppelen_titel), sub = getString(R.string.onbekende_barcode))
        b.codeTekst.text = code
        adapter.koppel(b.lijst)
        b.nieuwKnop.setOnClickListener { nieuwProduct() }
        b.zoekVeld.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) = filter()
        })
        filter()
    }

    private fun filter() {
        adapter.zet(Catalogus.zoek(b.zoekVeld.text.toString(), ookInactief = true))
    }

    /** Nog een scan op dit scherm: een bekende opent dat product, een andere onbekende vervangt deze. */
    override fun bijScan(code: String) {
        if (Catalogus.opBarcode(code) != null) {
            openScan(code)
            finish()
            return
        }
        Catalogus.normaliseerCode(code)?.let {
            this.code = it
            b.codeTekst.text = it
            tril()
        }
    }

    /** Een nieuw product aanmaken, en er daarna de barcode aan koppelen (de gewone vraag: één losse, of een doos). */
    private fun nieuwProduct() {
        bezig {
            val keuzes = Api.getJson(this, "/api/app/producten/nieuw")
            val categorieen = keuzes.getJSONArray("categorieen").let { a -> (0 until a.length()).map { a.getString(it) } }
            val eenheden = keuzes.getJSONArray("eenheden").let { a -> (0 until a.length()).map { a.getString(it) } }
            val besteleenheden = keuzes.getJSONArray("besteleenheden").let { a -> (0 until a.length()).map { a.getString(it) } }
            val d = DialogNieuwProductBinding.inflate(layoutInflater)
            d.naam.setText(b.zoekVeld.text.toString().trim())
            d.categorie.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, categorieen)
            d.eenheid.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, eenheden)
            d.besteleenheid.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
                listOf(getString(R.string.geen_besteleenheid)) + besteleenheden)
            val verzoekId = Api.nieuwVerzoekId()
            val dialoog = AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.nieuw_product)))
                .setView(d.root)
                .setNegativeButton(R.string.annuleren, null)
                .setPositiveButton(R.string.aanmaken, null)
                .show()
            // Zelf afhandelen, zodat de dialoog blijft staan als er iets ontbreekt.
            dialoog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val naam = d.naam.text.toString().trim()
                if (naam.isEmpty()) return@setOnClickListener melding(getString(R.string.nieuw_naam_nodig))
                val body = JSONObject()
                    .put("naam", naam)
                    .put("categorie", categorieen.getOrNull(d.categorie.selectedItemPosition) ?: "")
                    .put("eenheid", eenheden.getOrNull(d.eenheid.selectedItemPosition) ?: "")
                    .put("verkoopprijs", d.verkoopprijs.text.toString().trim().replace(',', '.'))
                d.besteleenheid.selectedItemPosition.takeIf { it > 0 }?.let {
                    body.put("besteleenheid", besteleenheden[it - 1]).put("per_besteleenheid", d.perBesteleenheid.text.toString().trim())
                }
                bezig {
                    val antwoord = Api.post(this, "/api/app/producten/nieuw", body, verzoekId = verzoekId)
                    val nieuw = Catalogus.product(antwoord.getJSONObject("product"))
                    Catalogus.werkBij(this, nieuw)
                    dialoog.dismiss()
                    tril(60)
                    kies(nieuw, getString(R.string.wat_heb_je_gescand_nieuw, nieuw.naam))
                }
            }
        }
    }

    private fun kies(p: Catalogus.Product, titel: String = getString(R.string.wat_heb_je_gescand, p.naam)) {
        Koppelvraag.vraag(this, code, p, titel) {
            if (callingActivity != null) {
                setResult(RESULT_OK, Intent().putExtra(EXTRA_CODE, code))
            } else {
                ProductActivity.open(this, p.id, scan = code)
            }
            finish()
        }
    }

    companion object {
        const val EXTRA_CODE = "code"

        fun open(activity: Activity, code: String) {
            activity.startActivity(intent(activity, code))
        }

        fun intent(activity: Activity, code: String) = Intent(activity, KoppelenActivity::class.java).putExtra(EXTRA_CODE, code)
    }
}
