package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De diashow aan of uit: hele onderdelen (de standen, Man of the Match, ...) en losse dia's, bijvoorbeeld een
 * mededeling die niet meer klopt. Tik en hij draait wel of niet mee; maken en bewerken doe je op de site. Zie
 * routes/app_api_tv.py. */
class DiasActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.diashow))
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
                toon(Api.getJson(this, "/api/app/kantine-tv/dias"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun zet(pad: String, body: JSONObject) {
        bezig {
            val antwoord = Api.post(this, pad, body, herhaalbaar = true)
            tril(60)
            antwoord.tekstOfNull("melding")?.let { melding(it) }
            toon(antwoord)
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()

        Lijst.kop(inhoud, getString(R.string.onderdelen))
        val blokken = Lijst.kaart(inhoud)
        val sponsorenAan = data.optJSONArray("blokken")?.objecten().orEmpty().firstOrNull { it.optString("sleutel") == "toon_sponsoren" }
            ?.optBoolean("aan") ?: true
        for (blok in data.optJSONArray("blokken")?.objecten().orEmpty()) {
            val aan = blok.optBoolean("aan")
            Lijst.regel(blokken, blok.optString("naam"), null, getString(if (aan) R.string.aan else R.string.uit),
                if (aan) R.color.groen_tekst else R.color.tekst_zacht) {
                zet("/api/app/kantine-tv/dia-blokken/${blok.optString("sleutel")}", JSONObject().put("aan", !aan))
            }
        }

        Lijst.kop(inhoud, getString(R.string.dias))
        if (!sponsorenAan) Lijst.tekst(inhoud, getString(R.string.dias_blok_uit), grootte = 12f, kleur = R.color.oranje_balk)
        val dias = data.optJSONArray("dias")?.objecten().orEmpty()
        if (dias.isEmpty()) return Lijst.leeg(inhoud, getString(R.string.geen_dias))
        val kaart = Lijst.kaart(inhoud)
        for (dia in dias) {
            val actief = dia.optBoolean("actief")
            val periode = when (dia.tekstOfNull("periode")) {
                "voorbij" -> getString(R.string.dia_voorbij, Lijst.datum(dia.tekstOfNull("tot"), metTijd = false))
                "later" -> getString(R.string.dia_later, Lijst.datum(dia.tekstOfNull("vanaf"), metTijd = false))
                else -> dia.tekstOfNull("tot")?.let { getString(R.string.dia_tot, Lijst.datum(it, metTijd = false)) }
            }
            Lijst.regel(kaart, dia.tekstOfNull("titel") ?: dia.optString("soort"),
                listOfNotNull(dia.optString("soort").substringBefore(" ("), periode).joinToString(" · "),
                getString(if (actief) R.string.aan else R.string.uit), if (actief) R.color.groen_tekst else R.color.tekst_zacht) {
                zet("/api/app/kantine-tv/dias/${dia.getInt("id")}", JSONObject().put("actief", !actief))
            }
        }
        Lijst.tekst(inhoud, getString(R.string.dias_op_site), grootte = 11.5f)
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, DiasActivity::class.java))
    }
}
