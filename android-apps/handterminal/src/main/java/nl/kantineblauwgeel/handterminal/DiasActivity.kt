package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De diashow aan of uit: hele onderdelen (de standen, Man of the Match, ...), mappen (zoals "Halloween feest") en
 * losse dia's, bijvoorbeeld een mededeling die niet meer klopt. Een dia kun je ook meteen groot op alle tv's zetten (de
 * schijnwerper, 2.20.0), ook een dia zonder moment zoals het programma. De dia's staan per map: de mappen die aan
 * staan bovenaan. Maken en bewerken doe je op de site. Zie routes/app_api_tv.py. */
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

    /** De schijnwerper aan of uit; het antwoord is de diashow opnieuw, met een melding. */
    private fun schijnwerper(pad: String, verzoekId: String? = null) {
        bezig {
            val antwoord = Api.post(this, pad, JSONObject().put("lijst", "dias"), verzoekId = verzoekId, herhaalbaar = verzoekId == null)
            tril(60)
            antwoord.tekstOfNull("melding")?.let { melding(it, lang = true) }
            toon(antwoord)
        }
    }

    /** Een dia aangetikt: nu groot op alle tv's, of aan of uit in de diashow. */
    private fun diaMenu(dia: JSONObject) {
        val id = dia.getInt("id")
        val actief = dia.optBoolean("actief")
        val keuzes = listOf(
            getString(R.string.dia_nu_groot) to { schijnwerper("/api/app/kantine-tv/momenten/$id/nu", Api.nieuwVerzoekId()) },
            getString(if (actief) R.string.dia_uitzetten else R.string.dia_aanzetten) to {
                zet("/api/app/kantine-tv/dias/$id", JSONObject().put("actief", !actief))
            },
        )
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(dia.tekstOfNull("titel") ?: dia.optString("soort")))
            .setItems(keuzes.map { it.first }.toTypedArray()) { _, i -> keuzes[i].second() }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()

        // Staat er nu iets groot op de tv's, dan bovenaan in het geel, met Stop (2.21.0).
        data.optJSONObject("schijnwerper")?.let { s ->
            Lijst.balk(inhoud, getString(R.string.schijnwerper_nu, s.tekstOfNull("titel") ?: getString(R.string.een_dia)),
                getString(R.string.stop_knop)) { schijnwerper("/api/app/kantine-tv/schijnwerper/stop") }
        }

        Lijst.kop(inhoud, getString(R.string.onderdelen))
        val blokken = Lijst.kaart(inhoud)
        val sponsorenAan = data.optJSONArray("blokken")?.objecten().orEmpty().firstOrNull { it.optString("sleutel") == "toon_sponsoren" }
            ?.optBoolean("aan") ?: true
        for (blok in data.optJSONArray("blokken")?.objecten().orEmpty()) {
            val aan = blok.optBoolean("aan")
            Lijst.regel(blokken, blok.optString("naam"), null, getString(if (aan) R.string.aan else R.string.uit),
                if (aan) R.color.groen_tekst else R.color.tekst_zacht, pil = true) {
                zet("/api/app/kantine-tv/dia-blokken/${blok.optString("sleutel")}", JSONObject().put("aan", !aan))
            }
        }

        // Mappen: een hele map dia's met één tik aan of uit; met een begin en einde gaat hij ook vanzelf.
        val mappen = data.optJSONArray("mappen")?.objecten().orEmpty()
        if (mappen.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.mappen))
            val kaart = Lijst.kaart(inhoud)
            for (m in mappen) {
                val aan = m.optBoolean("aan")
                val wanneer = when (m.optString("status")) {
                    "straks" -> getString(R.string.map_straks, Lijst.datum(m.tekstOfNull("vanaf")))
                    "voorbij" -> getString(R.string.map_voorbij)
                    else -> m.tekstOfNull("tot")?.let { getString(R.string.map_tot, Lijst.datum(it)) }
                }
                Lijst.regel(kaart, m.optString("naam"),
                    listOfNotNull(resources.getQuantityString(R.plurals.n_dias, m.optInt("dias"), m.optInt("dias")), wanneer).joinToString(" · "),
                    getString(if (aan) R.string.aan else R.string.uit), if (aan) R.color.groen_tekst else R.color.tekst_zacht, pil = true) {
                    zet("/api/app/kantine-tv/mappen/${m.getInt("id")}", JSONObject().put("aan", !aan))
                }
            }
        }

        val dias = data.optJSONArray("dias")?.objecten().orEmpty()
        if (dias.isEmpty()) {
            Lijst.kop(inhoud, getString(R.string.dias))
            return Lijst.leeg(inhoud, getString(R.string.geen_dias))
        }
        if (!sponsorenAan) Lijst.tekst(inhoud, getString(R.string.dias_blok_uit), grootte = 12f, kleur = R.color.oranje_balk)
        // Per map: de mappen die aan staan eerst (zoals het feest van vandaag), dan Algemeen, dan de mappen die uit staan.
        val mapPerId = mappen.associateBy { it.getInt("id") }
        val perMap: Map<Int?, List<JSONObject>> = dias.groupBy { if (it.isNull("map_id")) null else it.getInt("map_id") }
        val volgorde: List<Int?> = mappen.filter { it.optBoolean("aan") }.map { it.getInt("id") } + listOf(null) +
            mappen.filterNot { it.optBoolean("aan") }.map { it.getInt("id") }
        for (mapId in volgorde + perMap.keys.filter { it !in volgorde }) {
            val groep = perMap[mapId] ?: continue
            val m = mapId?.let { mapPerId[it] }
            val naam = when {
                m == null -> getString(R.string.algemeen)
                m.optBoolean("aan") -> m.optString("naam")
                else -> getString(R.string.map_staat_uit, m.optString("naam"))
            }
            Lijst.kop(inhoud, getString(R.string.dias_in, naam))
            // Elke dia als tegel (2.21.0): de titel in de kleur van zijn effect, het tijdstip in het geel.
            Lijst.tegels(inhoud, groep.map { dia ->
                val moment = dia.tekstOfNull("moment")
                val periode = when (dia.tekstOfNull("periode")) {
                    "voorbij" -> getString(R.string.dia_voorbij, Lijst.datum(dia.tekstOfNull("tot"), metTijd = false))
                    "later" -> getString(R.string.dia_later, Lijst.datum(dia.tekstOfNull("vanaf"), metTijd = false))
                    else -> dia.tekstOfNull("tot")?.let { getString(R.string.dia_tot, Lijst.datum(it, metTijd = false)) }
                }
                val kleur = try {
                    Color.parseColor(dia.tekstOfNull("kleur") ?: "#FCD42F")
                } catch (fout: IllegalArgumentException) {
                    getColor(R.color.geel)
                }
                Lijst.Tegel(
                    titel = dia.tekstOfNull("titel") ?: dia.optString("soort"),
                    sub = periode ?: moment?.let { Lijst.datum(it, metTijd = false) } ?: dia.optString("soort").substringBefore(" ("),
                    kleur = kleur,
                    label = moment?.takeIf { it.length >= 16 }?.substring(11, 16),
                    aan = dia.optBoolean("actief"),
                ) { diaMenu(dia) }
            })
        }
        Lijst.tekst(inhoud, getString(R.string.dias_op_site), grootte = 11.5f)
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, DiasActivity::class.java))
    }
}
