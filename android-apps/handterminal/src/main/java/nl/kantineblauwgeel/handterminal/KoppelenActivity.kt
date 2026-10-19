package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityKoppelenBinding
import org.json.JSONObject

/** Een onbekende barcode koppelen, in twee tikken: het product kiezen, en dan "één fles" of "een krat van 24". Verder
 * niets invullen (merk, leverancier, inkoopprijs kan later op de site). Daarna opent het product, met de scan al
 * meegeteld. Vanuit Factuur inboeken gaat het terug naar de factuur, die de scan dan alsnog meetelt. */
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

    private fun kies(p: Catalogus.Product) {
        val keuzes = mutableListOf(getString(R.string.koppel_los, p.eenheid))
        val aantallen = mutableListOf<Int?>(null)
        if (p.besteleenheid != null && p.perBesteleenheid > 1) {
            keuzes += getString(R.string.koppel_doos, p.besteleenheid, p.perBesteleenheid, p.eenheid)
            aantallen += p.perBesteleenheid
        }
        keuzes += getString(R.string.koppel_doos_anders)
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.wat_heb_je_gescand, p.naam)))
            .setItems(keuzes.toTypedArray()) { _, i ->
                if (i < aantallen.size) koppel(p, aantallen[i])
                else Cijferpad.vraag(this, getString(R.string.hoeveel_in_doos), eenheid = p.eenheid) { n ->
                    n.toIntOrNull()?.takeIf { it > 0 }?.let { koppel(p, it) }
                }
            }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun koppel(p: Catalogus.Product, perDoos: Int?) {
        val id = Api.nieuwVerzoekId()
        bezig {
            val body = JSONObject().put("code", code).put("product_id", p.id)
            if (perDoos != null) body.put("per_doos", perDoos)
            val antwoord = Api.post(this, "/api/app/barcodes/koppelen", body, verzoekId = id)
            Catalogus.werkBij(this, Catalogus.product(antwoord.getJSONObject("product")))
            tril(60)
            melding(getString(R.string.gekoppeld_aan, p.naam))
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
