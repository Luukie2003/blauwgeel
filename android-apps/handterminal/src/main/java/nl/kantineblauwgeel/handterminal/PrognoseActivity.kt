package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject
import kotlin.math.roundToInt

/** De prognose: wat er de komende dagen verkocht wordt (de omzet, per dag), wat er dreigt op te raken en hoeveel je
 * dan het beste bestelt. Uit het voorspelmodel van de site; dat rekent soms enkele seconden. De verkoopdagen en
 * evenementen instellen kan alleen op de website. */
class PrognoseActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var dagen = 7

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.prognose))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        laad()
    }

    override fun weerVerbonden() = laad()

    private fun keuzes() {
        val opties = listOf(3, 7, 14)
        Lijst.keuzes(b.inhoud, opties.map { n -> getString(R.string.n_dagen_kort, n) to { dagen = n; laad() } }, opties.indexOf(dagen))
    }

    private fun laad() {
        b.inhoud.removeAllViews()
        keuzes()
        Lijst.leeg(b.inhoud, getString(R.string.even_rekenen))
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/prognose?dagen=$dagen"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        keuzes()
        if (!data.optBoolean("beschikbaar")) return Lijst.leeg(inhoud, data.tekstOfNull("reden") ?: getString(R.string.prognose_niet_beschikbaar))

        val totaal = data.getJSONObject("totaal")
        val samenvatting = data.getJSONObject("samenvatting")
        Lijst.kop(inhoud, getString(R.string.komende_n_dagen, dagen))
        Lijst.cijfers(inhoud, listOf(
            Lijst.Cijfer(Lijst.euro(totaal.optDouble("omzet")).substringBefore(','), getString(R.string.verwachte_omzet,
                Lijst.euro(totaal.optDouble("laag")).substringBefore(','), Lijst.euro(totaal.optDouble("hoog")).substringBefore(','))),
            Lijst.Cijfer((samenvatting.optInt("urgent") + samenvatting.optInt("let_op")).toString(),
                getString(R.string.producten_let_op, samenvatting.optInt("urgent"), samenvatting.optInt("let_op")),
                waarschuwing = samenvatting.optInt("urgent") > 0),
        ))

        val perDag = data.getJSONArray("per_dag").objecten()
        if (perDag.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.per_dag))
            val kaart = Lijst.kaart(inhoud)
            for (d in perDag) {
                val open = d.optBoolean("open")
                val wat = listOfNotNull(
                    d.optInt("wedstrijden").takeIf { it > 0 }?.let { resources.getQuantityString(R.plurals.n_thuiswedstrijden, it, it) },
                    d.optInt("evenementen").takeIf { it > 0 }?.let { getString(R.string.evenement) },
                    if (d.optBoolean("training")) getString(R.string.training) else null,
                ).joinToString(" · ")
                Lijst.regel(kaart, "${d.optString("weekdag")} ${Lijst.datum(d.optString("datum") + " 00:00", metTijd = false)}",
                    wat.ifEmpty { null },
                    if (open) Lijst.euro(d.optDouble("omzet")).substringBefore(',') else getString(R.string.dicht),
                    if (open) R.color.tekst else R.color.tekst_zacht)
            }
        }

        val producten = data.getJSONArray("producten").objecten()
        val urgent = producten.filter { it.optString("status") == "urgent" }
        val letOp = producten.filter { it.optString("status") == "let_op" }
        if (urgent.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.raakt_waarschijnlijk_op))
            productLijst(Lijst.kaart(inhoud, R.drawable.rand_links_rood), urgent)
        }
        if (letOp.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.let_op))
            productLijst(Lijst.kaart(inhoud, R.drawable.rand_links_oranje), letOp)
        }
        val ok = producten.size - urgent.size - letOp.size
        Lijst.tekst(inhoud, resources.getQuantityString(R.plurals.genoeg_voorraad, ok, ok), grootte = 12f)

        Lijst.kop(inhoud, getString(R.string.op_de_computer))
        Lijst.knop(Lijst.kaart(inhoud), getString(R.string.verkoopdagen_instellen)) { nietInApp(getString(R.string.wat_verkoopdagen)) }
    }

    private fun productLijst(kaart: LinearLayout, producten: List<JSONObject>) {
        for (p in producten) {
            val eenheid = p.optString("eenheid")
            val advies = when {
                p.optInt("advies_stuks") <= 0 -> null
                !p.isNull("advies_eenheden") -> getString(R.string.advies_kort_eenheden, p.optInt("advies_eenheden"), p.tekstOfNull("besteleenheid") ?: "")
                else -> getString(R.string.advies_kort_stuks, p.optInt("advies_stuks"), eenheid)
            }
            Lijst.regel(
                kaart, p.optString("naam"),
                listOfNotNull(
                    getString(R.string.voorraad_verwacht, p.optInt("voorraad"), p.optDouble("verwacht").roundToInt(), eenheid),
                    advies,
                    if (p.optInt("onderweg") > 0) getString(R.string.n_onderweg, p.optInt("onderweg")) else null,
                    if (p.optBoolean("al_op_bestellijst")) getString(R.string.op_bestellijst_kort) else null,
                ).joinToString(" · "),
                "${(p.optDouble("kans_tekort") * 100).roundToInt()}%",
                if (p.optString("status") == "urgent") R.color.rood_balk else R.color.oranje_balk,
            ) { ProductActivity.open(this, p.getInt("id")) }
        }
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, PrognoseActivity::class.java))
    }
}
