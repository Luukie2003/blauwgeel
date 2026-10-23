package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De keuken: het frituurvet (wanneer het voor het laatst is vervangen, en vervangen registreren), de keukentelling (de
 * looplijst in [KeukenTellenActivity], met "verder" als er een op het toestel klaarstaat) en inboeken
 * ([KeukenInvoerActivity]), de voorraad van de keukenproducten met hun gekoppelde dozen, en de laatste keukentellingen
 * (tik om te bekijken, [KeukenTellingActivity]). Tik op een product voor de productinformatie of om het op de
 * boodschappenlijst te zetten. Zelfde als Keuken op de site; de keukenprijzen en de instellingen kunnen alleen op de
 * website. */
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
        val bezig = getSharedPreferences("keuken_tellen", MODE_PRIVATE).getString("stand", null) != null
        Lijst.knop(acties, getString(if (bezig) R.string.keukentelling_verder else R.string.keukentelling)) { KeukenTellenActivity.open(this) }
        Lijst.knop(acties, getString(R.string.keuken_inboeken)) { KeukenInvoerActivity.open(this, KeukenInvoerActivity.INBOEKEN) }

        val producten = data.getJSONArray("producten").objecten()
        Lijst.kop(inhoud, getString(R.string.keuken_voorraad))
        if (producten.isEmpty()) Lijst.leeg(inhoud, getString(R.string.geen_keukenproducten))
        else {
            val kaart = Lijst.kaart(inhoud)
            for (p in producten) {
                val laag = p.optInt("voorraad") < p.optInt("min_voorraad")
                val dozen = p.optJSONArray("dozen")?.objecten().orEmpty()
                Lijst.regel(
                    kaart, p.optString("naam"),
                    listOfNotNull(p.tekstOfNull("subcategorie"), getString(R.string.minimum, p.optInt("min_voorraad")),
                        if (dozen.isNotEmpty()) getString(R.string.keuken_dozen, dozen.joinToString(" · ") { "${it.optInt("aantal")}" })
                        else if (p.optInt("per_verpakking") > 1) getString(R.string.per_verpakking, p.optString("verpakking"), p.optInt("per_verpakking")) else null,
                        if (p.optBoolean("op_boodschappenlijst")) getString(R.string.op_boodschappenlijst_kort) else null,
                    ).joinToString(" · "),
                    "${p.optInt("voorraad")} ${p.optString("eenheid")}",
                    if (laag) R.color.rood_balk else R.color.tekst,
                ) { productKeuze(p) }
            }
        }

        val tellingen = data.getJSONArray("tellingen").objecten()
        if (tellingen.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.laatste_keukentellingen))
            val kaart = Lijst.kaart(inhoud)
            for (t in tellingen) {
                val begin = t.optBoolean("begintelling")
                Lijst.regel(kaart, Lijst.datum(t.tekstOfNull("datum")) + (t.tekstOfNull("naam")?.let { " · $it" } ?: ""),
                    listOfNotNull(if (begin) getString(R.string.keuken_begintelling_kort) else null,
                        resources.getQuantityString(R.plurals.n_producten, t.optInt("producten"), t.optInt("producten"))).joinToString(" · "),
                    if (begin) "–" else Lijst.euro(t.optDouble("omzet")), R.color.tekst_zacht) { KeukenTellingActivity.open(this, t.getInt("id")) }
            }
        }

        Lijst.kop(inhoud, getString(R.string.instellingen))
        val beheer = Lijst.kaart(inhoud)
        if (inst.beheerder) Lijst.knop(beheer, getString(R.string.keukenprijzen)) { prijzen() }
        Lijst.knop(beheer, getString(R.string.frituurvet_interval_aanpassen, vet.optInt("interval"))) { interval(vet.optInt("interval")) }
    }

    /** Een keukenproduct aangetikt: de productinformatie (met voorraadrechten), en op de boodschappenlijst zetten. */
    private fun productKeuze(p: JSONObject) {
        val keuzes = mutableListOf<Pair<String, () -> Unit>>()
        if (!p.optBoolean("op_boodschappenlijst")) keuzes += getString(R.string.op_boodschappenlijst_zetten) to { opBoodschappenlijst(p) }
        if (inst.toegang("voorraad")) keuzes += getString(R.string.productinformatie) to { ProductActivity.open(this, p.getInt("id")) }
        val dozen = p.optJSONArray("dozen")?.objecten().orEmpty()
        val uitleg = if (dozen.isEmpty()) getString(R.string.keuken_geen_dozen_lang)
        else dozen.joinToString("\n") { "• " + it.optString("omschrijving") }
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(p.optString("naam")))
            .setMessage(getString(R.string.voorraad_nu, p.optInt("voorraad"), p.optString("eenheid")) + "\n\n" + uitleg)
            .apply { if (keuzes.isNotEmpty()) setPositiveButton(keuzes[0].first) { _, _ -> keuzes[0].second() } }
            .apply { if (keuzes.size > 1) setNeutralButton(keuzes[1].first) { _, _ -> keuzes[1].second() } }
            .setNegativeButton(R.string.sluiten, null)
            .show()
    }

    private fun opBoodschappenlijst(p: JSONObject) {
        val id = Api.nieuwVerzoekId()
        bezig {
            val antwoord = Api.post(this, "/api/app/keuken/boodschap", JSONObject().put("product_id", p.getInt("id")), verzoekId = id)
            tril(60)
            melding(antwoord.optString("melding"))
            laad()
        }
    }

    /** (Beheerders) De verkoopprijzen van de keuken: tik op een product en vul de nieuwe prijs in. */
    private fun prijzen() {
        bezig {
            val lijst = Api.getJson(this, "/api/app/keuken/prijzen").getJSONArray("producten").objecten()
            if (lijst.isEmpty()) return@bezig melding(getString(R.string.geen_keukenproducten))
            AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.keukenprijzen)))
                .setItems(lijst.map {
                    "${it.optString("naam")}   ${Lijst.euro(it.optDouble("verkoopprijs"))}" +
                        "\n" + getString(R.string.inkoop_per_stuk_kort, Lijst.euro(it.optDouble("inkoop_per_stuk")), it.optString("eenheid"))
                }.toTypedArray()) { _, i -> prijsVragen(lijst[i]) }
                .setNegativeButton(R.string.sluiten, null)
                .show()
        }
    }

    private fun prijsVragen(p: JSONObject) {
        val nu = String.format(java.util.Locale("nl", "NL"), "%.2f", p.optDouble("verkoopprijs"))
        Cijferpad.vraag(this, p.optString("naam"), nu, decimaal = true, voor = "€") { tekst ->
            if (tekst.isEmpty()) return@vraag
            val id = Api.nieuwVerzoekId()
            bezig {
                val antwoord = Api.post(this, "/api/app/keuken/prijzen",
                    JSONObject().put("prijzen", JSONObject().put(p.getInt("id").toString(), tekst.replace(',', '.'))), verzoekId = id)
                tril(40)
                melding(antwoord.optString("melding"))
                prijzen()
            }
        }
    }

    /** Om de hoeveel dagen het frituurvet vervangen moet. */
    private fun interval(nu: Int) {
        Cijferpad.vraag(this, getString(R.string.frituurvet_interval_vraag), nu.toString(), eenheid = getString(R.string.dagen), max = 3) { tekst ->
            val dagen = tekst.toIntOrNull() ?: return@vraag
            bezig {
                val antwoord = Api.post(this, "/api/app/keuken/instellingen", JSONObject().put("frituurvet_interval_dagen", dagen), herhaalbaar = true)
                melding(antwoord.optString("melding"))
                laad()
            }
        }
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
