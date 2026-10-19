package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De laatste boekingen van alle producten: wie boekte wat erin of eruit, en waarom. */
class GeschiedenisActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.geschiedenis))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/geschiedenis"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        b.inhoud.removeAllViews()
        val mutaties = data.getJSONArray("mutaties").objecten()
        Lijst.kop(b.inhoud, getString(R.string.laatste_boekingen))
        if (mutaties.isEmpty()) return Lijst.leeg(b.inhoud, getString(R.string.nog_geen_boekingen))
        val kaart = Lijst.kaart(b.inhoud)
        for (m in mutaties) {
            val erin = m.optString("type") == "in"
            Lijst.regel(
                kaart,
                m.optString("product"),
                listOfNotNull(Lijst.datum(m.tekstOfNull("datum")), m.tekstOfNull("naam"), m.tekstOfNull("reden") ?: m.tekstOfNull("opmerking")).joinToString(" · "),
                (if (erin) "+" else "−") + m.optInt("aantal") + " " + m.optString("eenheid"),
                if (erin) R.color.groen_tekst else R.color.tekst,
            ) { ProductActivity.open(this, m.getInt("product_id")) }
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, GeschiedenisActivity::class.java))
    }
}
