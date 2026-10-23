package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Eén keukentelling bekijken: per product wat er was, wat er geteld is, wat er verkocht is en wat dat opbracht (of bij
 * een begintelling: wat er gecorrigeerd is). Zelfde als Keuken > Tellingen op de site. */
class KeukenTellingActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var tellingId = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        tellingId = intent.getIntExtra(EXTRA_ID, 0)
        richtBalkIn(b.balk, getString(R.string.keukentelling))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        laad()
    }

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/keuken/tellingen/$tellingId"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(t: JSONObject) {
        val begin = t.optBoolean("begintelling")
        zetBalkTitel(getString(if (begin) R.string.keuken_begintelling_kort else R.string.keukentelling))
        zetBalkSub(Lijst.datum(t.tekstOfNull("datum")) + (t.tekstOfNull("naam")?.let { " · $it" } ?: ""))
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val regels = t.getJSONArray("regels").objecten()

        Lijst.ruimte(inhoud)
        val samen = Lijst.kaart(inhoud)
        Lijst.regel(samen, resources.getQuantityString(R.plurals.n_producten, regels.size, regels.size),
            if (begin) getString(R.string.keuken_begintelling_uitleg) else getString(R.string.keuken_verkocht_totaal, regels.sumOf { it.optInt("verkocht") }),
            if (begin) null else Lijst.euro(t.optDouble("omzet")), R.color.groen_tekst)
        t.tekstOfNull("opmerking")?.let { Lijst.tekst(samen, it) }

        Lijst.kop(inhoud, getString(R.string.per_product))
        val kaart = Lijst.kaart(inhoud)
        for (r in regels) {
            val eenheid = r.optString("eenheid")
            val correctie = r.optInt("correctie")
            val wat = when {
                r.optInt("verkocht") > 0 -> getString(R.string.keuken_verkocht, r.optInt("verkocht"), Lijst.euro(r.optDouble("omzet")))
                correctie > 0 -> getString(R.string.keuken_meer, correctie)
                correctie < 0 -> getString(R.string.keuken_minder, -correctie)
                else -> getString(R.string.keuken_klopt)
            }
            Lijst.regel(kaart, r.optString("naam"), getString(R.string.was_voorraad, r.optInt("was")) + " · " + wat,
                getString(R.string.aantal_eenheid, r.optInt("geteld"), eenheid))
        }
    }

    companion object {
        private const val EXTRA_ID = "telling_id"

        fun open(context: Context, id: Int) =
            context.startActivity(Intent(context, KeukenTellingActivity::class.java).putExtra(EXTRA_ID, id))
    }
}
