package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import nl.kantineblauwgeel.handterminal.databinding.ActivityKoppelenBinding

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
        Koppelvraag.vraag(this, code, p, getString(R.string.wat_heb_je_gescand, p.naam)) {
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
