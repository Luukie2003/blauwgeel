package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Paint
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Uitverkocht op de tv: de producten op het prijzenscherm, per groep zoals op de tv. Tik een product aan en het staat
 * op de tv als uitverkocht (doorgestreept, met de melding "Uitverkocht" over het scherm); nog een keer tikken en het is
 * weer te koop. Raakt de voorraad niet, net als de knop op de site (routes/app_api_meer.py). */
class UitverkochtActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.uitverkocht_titel))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/prijzenscherm"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val uitverkocht = data.optInt("uitverkocht")
        zetBalkSub(if (uitverkocht > 0) resources.getQuantityString(R.plurals.n_uitverkocht, uitverkocht, uitverkocht) else null)
        Lijst.tekst(inhoud, getString(R.string.uitverkocht_uitleg), grootte = 12f).setPadding(dp(this, 4), dp(this, 10), dp(this, 4), 0)
        val groepen = data.optJSONArray("groepen")?.objecten().orEmpty()
        if (groepen.isEmpty()) return Lijst.leeg(inhoud, getString(R.string.uitverkocht_leeg))
        for (groep in groepen) {
            Lijst.kop(inhoud, groep.optString("naam"))
            val kaart = Lijst.kaart(inhoud)
            groep.optJSONArray("producten")?.objecten()?.forEach { p -> regel(kaart, p) }
        }
    }

    private fun regel(kaart: LinearLayout, p: JSONObject) {
        val uit = p.optBoolean("uitverkocht")
        val regel = Lijst.regel(
            kaart, p.optString("naam"),
            if (uit) getString(R.string.tik_weer_te_koop) else null,
            getString(if (uit) R.string.uitverkocht_kort else R.string.te_koop),
            if (uit) R.color.rood_balk else R.color.groen_tekst,
        ) { zet(p.getInt("id"), !uit) }
        if (uit) ((regel.getChildAt(0) as LinearLayout).getChildAt(0) as TextView).paintFlags = Paint.STRIKE_THRU_TEXT_FLAG
    }

    private fun zet(productId: Int, uitverkocht: Boolean) {
        bezig {
            val antwoord = Api.post(this, "/api/app/producten/$productId/uitverkocht", JSONObject().put("uitverkocht", uitverkocht), herhaalbaar = true)
            tril(60)
            melding(antwoord.optString("melding"))
            toon(antwoord)
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, UitverkochtActivity::class.java))
    }
}
