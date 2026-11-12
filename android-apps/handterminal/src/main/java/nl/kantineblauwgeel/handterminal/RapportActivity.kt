package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Een rapport van de site (2.11.0, eerst voor de tablet): verkoop, het weekoverzicht, de omzet per seizoen, seizoen in
 * cijfers, en voor beheerders de marge, de derving, de niet-lopers en de omzet per bardienst. Elk rapport komt van de site
 * in dezelfde vorm (routes/app_api_rapporten.py): bovenaan eventueel de periode om te kiezen, dan kerncijfers, lijsten en
 * losse tekst. Dit ene scherm laat ze dus allemaal zien. Alleen bekijken; aanpassen gaat op de site. */
class RapportActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var sleutel = ""
    private var keuze: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        sleutel = intent.getStringExtra(EXTRA_SLEUTEL) ?: "verkoop"
        keuze = savedInstanceState?.getString(EXTRA_KEUZE)
        richtBalkIn(b.balk, intent.getStringExtra(EXTRA_TITEL) ?: getString(R.string.rapporten))
        b.verversen.setColorSchemeResources(R.color.blauw_donker)
        b.verversen.setOnRefreshListener { laad() }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString(EXTRA_KEUZE, keuze)
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        if (b.inhoud.childCount == 0) Lijst.leeg(b.inhoud, getString(R.string.even_rekenen))
        bezig {
            try {
                val pad = "/api/app/rapporten/$sleutel" + (keuze?.let { "?keuze=" + android.net.Uri.encode(it) } ?: "")
                toon(Api.getJson(this, pad))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(rapport: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        zetBalkSub(rapport.tekstOfNull("sub"))
        val keuzes = rapport.optJSONArray("keuzes")?.objecten().orEmpty()
        if (keuzes.isNotEmpty()) {
            Lijst.keuzes(inhoud, keuzes.map { k -> k.optString("label") to { keuze = k.optString("sleutel"); laad() } },
                keuzes.indexOfFirst { it.optBoolean("actief") })
        }
        for (deel in rapport.optJSONArray("delen")?.objecten().orEmpty()) {
            when (deel.optString("soort")) {
                "cijfers" -> {
                    deel.tekstOfNull("kop")?.let { Lijst.kop(inhoud, it) }
                    Lijst.cijfers(inhoud, deel.getJSONArray("cijfers").objecten().map { c ->
                        Lijst.Cijfer(c.optString("waarde"), listOfNotNull(c.tekstOfNull("label"), c.tekstOfNull("sub")).joinToString(" · "))
                    })
                }
                "lijst" -> {
                    deel.tekstOfNull("kop")?.let { Lijst.kop(inhoud, it) }
                    val regels = deel.getJSONArray("regels").objecten()
                    if (regels.isEmpty()) Lijst.leeg(inhoud, deel.optString("leeg"))
                    else {
                        val kaart = Lijst.kaart(inhoud)
                        for (r in regels) {
                            Lijst.regel(kaart, r.optString("titel"), r.tekstOfNull("detail"), r.tekstOfNull("rechts"),
                                when (r.tekstOfNull("kleur")) {
                                    "rood" -> R.color.rood
                                    "groen" -> R.color.groen
                                    else -> R.color.tekst
                                })
                        }
                    }
                }
                else -> deel.tekstOfNull("tekst")?.let { Lijst.tekst(inhoud, it) }
            }
        }
    }

    companion object {
        private const val EXTRA_SLEUTEL = "sleutel"
        private const val EXTRA_TITEL = "titel"
        private const val EXTRA_KEUZE = "keuze"

        /** [sleutel]: het rapport, zoals in het adres op de site (verkoop, week, seizoenen, seizoen-in-cijfers, marge,
         * derving, niet-lopers, bardiensten). */
        fun open(context: Context, sleutel: String, titel: String) = context.startActivity(
            Intent(context, RapportActivity::class.java).putExtra(EXTRA_SLEUTEL, sleutel).putExtra(EXTRA_TITEL, titel)
        )
    }
}
