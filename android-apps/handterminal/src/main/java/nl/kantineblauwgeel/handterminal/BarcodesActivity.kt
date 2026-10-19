package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.LinearLayout
import kotlinx.coroutines.Job
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Alle artikelen met hun barcodes, per product (Voorraad > Barcodes op de site). Zoeken op naam, merk of barcode; een
 * scan zoekt meteen. Tik op een product om het te openen. Een artikel bewerken of weghalen kan alleen op de website;
 * een barcode koppelen kan op het productscherm. */
class BarcodesActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private lateinit var zoekveld: EditText
    private val wacht = Handler(Looper.getMainLooper())
    private var zoeken: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.barcodes))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        zoekveld = EditText(this).apply {
            hint = getString(R.string.zoek_barcode_hint)
            inputType = InputType.TYPE_CLASS_TEXT
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            setSingleLine()
            setBackgroundResource(R.drawable.zoekveld)
            setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
            textSize = 15f
        }
        b.root.addView(zoekveld, 1, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(this, 44)).apply {
            setMargins(dp(this@BarcodesActivity, 10), dp(this@BarcodesActivity, 8), dp(this@BarcodesActivity, 10), 0)
        })
        zoekveld.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                wacht.removeCallbacksAndMessages(null)
                wacht.postDelayed({ laad() }, 350)
            }
        })
        laad()
    }

    override fun onDestroy() {
        wacht.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    override fun weerVerbonden() = laad()

    /** Een scan zoekt die barcode op (in plaats van het product te openen). */
    override fun bijScan(code: String) {
        tril()
        zoekveld.setText(code)
        zoekveld.setSelection(code.length)
    }

    private fun laad() {
        val term = zoekveld.text.toString().trim()
        zoeken?.cancel()
        zoeken = bezig {
            try {
                toon(Api.getJson(this, "/api/app/barcodes?q=" + java.net.URLEncoder.encode(term, "UTF-8")), term)
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject, term: String) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val producten = data.getJSONArray("producten").objecten()
        Lijst.kop(inhoud, resources.getQuantityString(R.plurals.n_artikelen, data.optInt("aantal"), data.optInt("aantal")))
        if (producten.isEmpty()) {
            return Lijst.leeg(inhoud, if (term.isEmpty()) getString(R.string.nog_geen_barcodes) else getString(R.string.niets_gevonden_voor, term))
        }
        val kaart = Lijst.kaart(inhoud)
        for (p in producten) {
            val eenheid = p.optString("eenheid")
            val regels = p.getJSONArray("artikelen").objecten().map { a ->
                val codes = listOfNotNull(a.tekstOfNull("ean"), a.tekstOfNull("doos_ean")?.let { getString(R.string.doos_code, a.optInt("per_doos"), it) })
                    .joinToString(" · ").ifEmpty { getString(R.string.geen_barcode) }
                "${a.optString("naam")} (${a.optInt("aantal")} $eenheid" +
                    (a.takeIf { !it.isNull("inkoopprijs") }?.let { ", " + Lijst.euro(it.optDouble("inkoopprijs")) } ?: "") + ")\n$codes"
            }
            Lijst.regel(kaart, p.optString("naam"), regels.joinToString("\n")) { ProductActivity.open(this, p.getInt("product_id")) }
        }
        Lijst.tekst(inhoud, getString(R.string.barcodes_uitleg), grootte = 11.5f)
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, BarcodesActivity::class.java))
    }
}
