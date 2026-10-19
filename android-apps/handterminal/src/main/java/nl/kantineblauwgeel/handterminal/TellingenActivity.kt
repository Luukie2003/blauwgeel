package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De laatste tellingen, en per telling wat er per product geteld en verkocht is. Corrigeren kan alleen op de
 * website. */
class TellingenActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var tellingId = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        tellingId = intent.getIntExtra(EXTRA_ID, 0)
        richtBalkIn(b.balk, if (tellingId > 0) getString(R.string.telling_nr, tellingId) else getString(R.string.tellingen))
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
                if (tellingId > 0) toonTelling(Api.getJson(this, "/api/app/tellingen/$tellingId"))
                else toonLijst(Api.getJson(this, "/api/app/tellingen"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toonLijst(data: JSONObject) {
        b.inhoud.removeAllViews()
        val tellingen = data.getJSONArray("tellingen").objecten()
        Lijst.kop(b.inhoud, getString(R.string.laatste_tellingen))
        if (tellingen.isEmpty()) return Lijst.leeg(b.inhoud, getString(R.string.nog_geen_tellingen))
        val kaart = Lijst.kaart(b.inhoud)
        for (t in tellingen) {
            Lijst.regel(
                kaart,
                getString(R.string.telling_nr, t.getInt("id")) + " · " + Lijst.datum(t.tekstOfNull("datum")),
                listOfNotNull(t.tekstOfNull("naam"), resources.getQuantityString(R.plurals.n_producten, t.optInt("aantal_producten"), t.optInt("aantal_producten"))).joinToString(" · "),
                FactuurActivity.euro(t.optDouble("omzet")),
                R.color.tekst_zacht,
            ) { open(this, t.getInt("id")) }
        }
    }

    private fun toonTelling(data: JSONObject) {
        b.inhoud.removeAllViews()
        val t = data.getJSONObject("telling")
        zetBalkSub(listOfNotNull(Lijst.datum(t.tekstOfNull("datum")), t.tekstOfNull("naam")).joinToString(" · "))
        Lijst.kop(b.inhoud, getString(R.string.telling_omzet, FactuurActivity.euro(data.optDouble("omzet"))))
        val kaart = Lijst.kaart(b.inhoud)
        for (r in data.getJSONArray("regels").objecten()) {
            val eenheid = r.optString("eenheid")
            val verkocht = r.optInt("verkocht")
            val correctie = r.optInt("correctie")
            Lijst.regel(
                kaart,
                r.optString("product"),
                getString(R.string.was_geteld, r.optInt("voorraad_voor"), r.optInt("geteld_aantal"), eenheid),
                when {
                    verkocht > 0 -> getString(R.string.verkocht_n, verkocht)
                    correctie > 0 -> "+$correctie"
                    else -> "0"
                },
                if (correctie > 0) R.color.oranje_balk else R.color.tekst,
            ) { ProductActivity.open(this, r.getInt("product_id")) }
        }
        Lijst.kop(b.inhoud, getString(R.string.op_de_computer))
        Lijst.knop(Lijst.kaart(b.inhoud), getString(R.string.telling_corrigeren)) { nietInApp(getString(R.string.wat_telling_corrigeren)) }
    }

    companion object {
        private const val EXTRA_ID = "telling_id"

        fun open(context: Context, tellingId: Int = 0) =
            context.startActivity(Intent(context, TellingenActivity::class.java).putExtra(EXTRA_ID, tellingId))
    }
}
