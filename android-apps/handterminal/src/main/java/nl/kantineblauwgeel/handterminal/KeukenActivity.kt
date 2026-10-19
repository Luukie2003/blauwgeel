package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De keuken: het frituurvet (wanneer het voor het laatst is vervangen, en vervangen registreren), de keukentelling en
 * inboeken (in [KeukenInvoerActivity]), de voorraad van de keukenproducten en de laatste keukentellingen. Zelfde als
 * Keuken op de site; de keukenprijzen en de instellingen kunnen alleen op de website. */
class KeukenActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.keuken))
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
                toon(Api.getJson(this, "/api/app/keuken"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()

        val vet = data.getJSONObject("frituurvet")
        Lijst.kop(inhoud, getString(R.string.frituurvet))
        val vetKaart = Lijst.kaart(inhoud, if (vet.optBoolean("ok")) R.drawable.kaart else R.drawable.rand_links_rood)
        val dagen = vet.takeIf { !it.isNull("dagen_geleden") }?.optInt("dagen_geleden")
        Lijst.regel(
            vetKaart,
            if (dagen == null) getString(R.string.frituurvet_nooit) else getString(R.string.frituurvet_laatst, Lijst.datum(vet.tekstOfNull("datum"), metTijd = false)) +
                (vet.tekstOfNull("naam")?.let { " · $it" } ?: ""),
            getString(R.string.frituurvet_interval, vet.optInt("interval")),
            when (dagen) {
                null -> getString(R.string.vervangen_uitroep)
                0 -> getString(R.string.vandaag)
                else -> resources.getQuantityString(R.plurals.n_dagen, dagen, dagen)
            },
            if (vet.optBoolean("ok")) R.color.groen_tekst else R.color.rood_balk,
        )
        Lijst.knop(vetKaart, getString(R.string.frituurvet_vervangen)) { vetVervangen() }

        Lijst.kop(inhoud, getString(R.string.tellen_en_inboeken))
        val acties = Lijst.kaart(inhoud)
        Lijst.knop(acties, getString(R.string.keukentelling)) { KeukenInvoerActivity.open(this, KeukenInvoerActivity.TELLEN) }
        Lijst.knop(acties, getString(R.string.keuken_inboeken)) { KeukenInvoerActivity.open(this, KeukenInvoerActivity.INBOEKEN) }

        val producten = data.getJSONArray("producten").objecten()
        Lijst.kop(inhoud, getString(R.string.keuken_voorraad))
        if (producten.isEmpty()) Lijst.leeg(inhoud, getString(R.string.geen_keukenproducten))
        else {
            val kaart = Lijst.kaart(inhoud)
            val voorraadRechten = inst.toegang("voorraad")
            for (p in producten) {
                val laag = p.optInt("voorraad") < p.optInt("min_voorraad")
                Lijst.regel(
                    kaart, p.optString("naam"),
                    listOfNotNull(p.tekstOfNull("subcategorie"), getString(R.string.minimum, p.optInt("min_voorraad")),
                        if (p.optInt("per_verpakking") > 1) getString(R.string.per_verpakking, p.optString("verpakking"), p.optInt("per_verpakking")) else null,
                    ).joinToString(" · "),
                    "${p.optInt("voorraad")} ${p.optString("eenheid")}",
                    if (laag) R.color.rood_balk else R.color.tekst,
                    if (voorraadRechten) ({ ProductActivity.open(this, p.getInt("id")) }) else null,
                )
            }
        }

        val tellingen = data.getJSONArray("tellingen").objecten()
        if (tellingen.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.laatste_keukentellingen))
            val kaart = Lijst.kaart(inhoud)
            for (t in tellingen) {
                Lijst.regel(kaart, Lijst.datum(t.tekstOfNull("datum")) + (t.tekstOfNull("naam")?.let { " · $it" } ?: ""),
                    resources.getQuantityString(R.plurals.n_producten, t.optInt("producten"), t.optInt("producten")),
                    Lijst.euro(t.optDouble("omzet")), R.color.tekst_zacht)
            }
        }

        Lijst.kop(inhoud, getString(R.string.op_de_computer))
        val computer = Lijst.kaart(inhoud)
        if (inst.beheerder) Lijst.knop(computer, getString(R.string.keukenprijzen)) { nietInApp(getString(R.string.wat_keukenprijzen)) }
        Lijst.knop(computer, getString(R.string.keuken_instellingen)) { nietInApp(getString(R.string.wat_keuken_instellingen)) }
    }

    private fun vetVervangen() {
        AlertDialog.Builder(this)
            .setMessage(R.string.frituurvet_vraag)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.vervangen) { _, _ ->
                val id = Api.nieuwVerzoekId()
                bezig {
                    val antwoord = Api.post(this, "/api/app/frituurvet", verzoekId = id)
                    tril(60)
                    melding(antwoord.optString("melding"))
                    vraagTaken(antwoord) { laad() }
                }
            }
            .show()
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, KeukenActivity::class.java))
    }
}
