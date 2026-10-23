package nl.kantineblauwgeel.tablet

import android.os.Bundle
import android.view.View
import androidx.annotation.StringRes
import nl.kantineblauwgeel.tablet.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Een scherm van 2.0 (activity_lijst.xml): haalt [pad] op en laat [toon] de kaarten bouwen. [stuur] doet een
 * JSON-POST (Api.postJson) en toont daarna het antwoord, dat bij deze adressen steeds de nieuwe stand is. */
abstract class LijstActivity : BasisActivity() {

    protected lateinit var b: ActivityLijstBinding
    abstract val pad: String
    @get:StringRes abstract val titel: Int

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        b.titel.setText(titel)
        b.terugKnop.setOnClickListener { finish() }
        b.foutmelding.setOnClickListener { laad() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.ingelogd()) laad()
    }

    fun laad() {
        b.laadindicator.visibility = View.VISIBLE
        b.foutmelding.visibility = View.GONE
        opAchtergrond({ Api.get(this, pad) }, fout = {
            b.laadindicator.visibility = View.GONE
            b.foutmelding.visibility = View.VISIBLE
        }) { data ->
            b.laadindicator.visibility = View.GONE
            b.inhoud.removeAllViews()
            toon(data)
        }
    }

    fun stuur(adres: String, body: JSONObject = JSONObject()) {
        opAchtergrond({ Api.postJson(this, adres, body) }) { data ->
            data.optString("melding").takeIf { it.isNotEmpty() }?.let { melding(it) }
            b.inhoud.removeAllViews()
            toon(data)
        }
    }

    abstract fun toon(data: JSONObject)
}
