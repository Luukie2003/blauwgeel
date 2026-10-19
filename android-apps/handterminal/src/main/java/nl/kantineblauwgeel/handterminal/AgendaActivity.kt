package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De agenda: de komende weken in de kantine. Per dag of de kantine open is, de thuiswedstrijden, evenementen,
 * bardiensten, training en het weer. Zelfde als Start > Agenda op de site. */
class AgendaActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var dagen = 21

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.agenda))
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
                toon(Api.getJson(this, "/api/app/agenda?dagen=$dagen"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val keuzes = listOf(14, 21, 28)
        Lijst.keuzes(inhoud, keuzes.map { n -> getString(R.string.n_weken, n / 7) to { dagen = n; laad() } }, keuzes.indexOf(dagen))
        val weken = data.getJSONArray("weken").objecten()
        if (weken.isEmpty()) return Lijst.leeg(inhoud, getString(R.string.agenda_leeg))
        for (week in weken) {
            Lijst.kop(inhoud, getString(R.string.week_n, week.optInt("week")))
            week.getJSONArray("dagen").objecten().forEach { dag(inhoud, it) }
        }
    }

    private fun dag(inhoud: LinearLayout, d: JSONObject) {
        val open = d.optBoolean("open")
        val kaart = Lijst.kaart(inhoud, if (d.optBoolean("vandaag")) R.drawable.rand_links_oranje else R.drawable.kaart)
        val wanneer = when {
            d.optBoolean("vandaag") -> " · " + getString(R.string.vandaag)
            d.optBoolean("morgen") -> " · " + getString(R.string.morgen)
            else -> ""
        }
        Lijst.regel(
            kaart,
            d.optString("weekdag").replaceFirstChar { it.uppercase() } + " " + d.optString("datum_tekst") + wanneer,
            null,
            getString(if (open) R.string.open else R.string.dicht),
            if (open) R.color.groen_tekst else R.color.tekst_zacht,
        )
        val regels = mutableListOf<String>()
        d.optJSONObject("weer")?.let { w ->
            regels += listOfNotNull(
                "${w.optString("icoon")} ${w.optString("label")}",
                w.takeIf { !it.isNull("max_temp") }?.let { "${it.optDouble("max_temp").toInt()}°" },
                w.takeIf { !it.isNull("neerslag_kans") }?.let { getString(R.string.kans_regen, it.optInt("neerslag_kans")) },
            ).joinToString(" · ")
        }
        if (d.optBoolean("dicht_op_vaste_dag")) regels += getString(R.string.dicht_op_vaste_dag)
        d.tekstOfNull("uitzondering_tekst")?.let { regels += "📌 $it" }
        d.optJSONArray("wedstrijden")?.objecten()?.forEach { w ->
            regels += "⚽ " + listOfNotNull(w.tekstOfNull("tijd"), w.tekstOfNull("omschrijving") ?: w.tekstOfNull("team")).joinToString("  ") +
                if (w.optBoolean("afgelast")) " (" + getString(R.string.afgelast) + ")" else ""
        }
        d.optJSONArray("evenementen")?.objecten()?.forEach { e ->
            regels += "★ " + e.optString("naam") + (e.tekstOfNull("groep")?.let { " ($it)" } ?: "")
        }
        d.optJSONArray("bardiensten")?.objecten()?.forEach { bd ->
            regels += getString(R.string.bardienst_regel, bd.optString("van"), bd.optString("tot"), bd.optString("namen"))
        }
        if (d.optBoolean("training")) regels += getString(R.string.training)
        if (regels.isNotEmpty()) Lijst.tekst(kaart, regels.joinToString("\n"), kleur = R.color.tekst).setPadding(dp(this, 12), 0, dp(this, 12), dp(this, 8))
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, AgendaActivity::class.java))
    }
}
