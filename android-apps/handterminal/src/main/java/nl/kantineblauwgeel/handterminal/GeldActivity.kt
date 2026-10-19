package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De kassa (of de kluis, alleen voor beheerders): de stand, de tellingen die op goedkeuring wachten en de laatste
 * goedgekeurde. Tellen gaat in [GeldTellenActivity]. Goedkeuren kan hier; corrigeren, bewerken, heropenen en geld
 * afdragen of overboeken kan alleen op de website. Zelfde logica als Kassa en Kluis op de site. */
class GeldActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var soort = KASSA
    private val isKassa get() = soort == KASSA

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        soort = intent.getStringExtra(EXTRA_SOORT) ?: KASSA
        richtBalkIn(b.balk, getString(if (isKassa) R.string.kassa else R.string.kluis))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = true
        b.onderKnop.setText(if (isKassa) R.string.kassa_tellen else R.string.kluis_tellen)
        b.onderKnop.setOnClickListener { GeldTellenActivity.open(this, soort) }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/$soort"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val coupures = data.getJSONArray("coupures").objecten()

        Lijst.kop(inhoud, getString(R.string.stand))
        val stand = Lijst.kaart(inhoud).apply { setPadding(0, dp(this@GeldActivity, 4), 0, dp(this@GeldActivity, 4)) }
        Lijst.info(stand, getString(if (isKassa) R.string.in_de_kassalade else R.string.in_de_kluis),
            Lijst.euro(data.optDouble("stand")), getString(R.string.volgens_administratie))

        val concepten = data.getJSONArray("concepten").objecten()
        Lijst.kop(inhoud, getString(R.string.wacht_op_goedkeuring, concepten.size))
        if (concepten.isEmpty()) Lijst.leeg(inhoud, getString(R.string.geen_concepten))
        else {
            val kaart = Lijst.kaart(inhoud, R.drawable.rand_links_oranje)
            concepten.forEach { telling(kaart, it, coupures, concept = true) }
        }

        val recent = data.getJSONArray("recent").objecten()
        if (recent.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.laatst_goedgekeurd))
            val kaart = Lijst.kaart(inhoud)
            recent.forEach { telling(kaart, it, coupures, concept = false) }
        }

        Lijst.kop(inhoud, getString(R.string.op_de_computer))
        val computer = Lijst.kaart(inhoud)
        Lijst.knop(computer, getString(R.string.telling_corrigeren)) { nietInApp(getString(R.string.wat_geld_corrigeren)) }
        Lijst.knop(computer, getString(if (isKassa) R.string.geld_afdragen else R.string.geld_storten)) {
            nietInApp(getString(if (isKassa) R.string.wat_geld_afdragen else R.string.wat_geld_storten))
        }
    }

    private fun telling(kaart: LinearLayout, t: JSONObject, coupures: List<JSONObject>, concept: Boolean) {
        val (verschil, kleur) = Lijst.verschil(this, t.optDouble("verschil"))
        Lijst.regel(
            kaart,
            Lijst.euro(t.optDouble("geteld")),
            listOfNotNull(Lijst.datum(t.tekstOfNull("datum")), t.tekstOfNull("naam"),
                if (!concept) t.tekstOfNull("goedgekeurd_door")?.let { getString(R.string.goedgekeurd_door, it) } else null).joinToString(" · "),
            verschil, kleur,
        ) { details(t, coupures, concept) }
    }

    /** Een telling in detail: de aantallen per coupure en de bedragen. Een concept kun je hier goedkeuren. */
    private fun details(t: JSONObject, coupures: List<JSONObject>, concept: Boolean) {
        val aantallen = t.optJSONObject("aantallen") ?: JSONObject()
        val regels = mutableListOf<String>()
        for (c in coupures) {
            val n = aantallen.optInt(c.optString("veld"))
            if (n > 0) regels += "$n × ${c.optString("naam")} = ${Lijst.euro(n * c.optDouble("waarde"))}"
        }
        if (regels.isEmpty()) regels += getString(R.string.niets_geteld)
        regels += ""
        regels += getString(R.string.geteld_bedrag, Lijst.euro(t.optDouble("geteld")))
        regels += getString(R.string.verwacht_bedrag, Lijst.euro(t.optDouble("verwacht")))
        regels += getString(R.string.verschil_bedrag, Lijst.verschil(this, t.optDouble("verschil")).first)
        if (isKassa) {
            regels += getString(R.string.contante_omzet_bedrag, Lijst.euro(t.optDouble("contante_omzet")))
            if (t.optDouble("kaart_omzet") > 0) regels += getString(R.string.kaart_omzet_bedrag, Lijst.euro(t.optDouble("kaart_omzet")))
        }
        t.tekstOfNull("opmerking")?.let { regels += "\n" + getString(R.string.opmerking_tekst, it) }
        if (!concept) t.tekstOfNull("goedgekeurd_door")?.let {
            regels += getString(R.string.goedgekeurd_door_op, it, Lijst.datum(t.tekstOfNull("goedgekeurd_op")))
        }
        val dialoog = AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(listOfNotNull(
                getString(if (isKassa) R.string.kassatelling else R.string.kluistelling),
                Lijst.datum(t.tekstOfNull("datum")), t.tekstOfNull("naam"),
            ).joinToString(" · ")))
            .setMessage(regels.joinToString("\n"))
            .setNeutralButton(R.string.corrigeren) { _, _ -> nietInApp(getString(R.string.wat_geld_corrigeren)) }
        if (concept) {
            dialoog.setPositiveButton(R.string.goedkeuren) { _, _ -> goedkeuren(t) }
            dialoog.setNegativeButton(R.string.sluiten, null)
        } else {
            dialoog.setPositiveButton(R.string.sluiten, null)
        }
        dialoog.show()
    }

    private fun goedkeuren(t: JSONObject) {
        val veld = EditText(this).apply {
            hint = getString(R.string.opmerking_optioneel)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 4), dp(context, 20), 0)
            addView(veld)
        }
        val uitleg = getString(
            if (isKassa) R.string.goedkeuren_kassa_vraag else R.string.goedkeuren_kluis_vraag, Lijst.euro(t.optDouble("geteld")),
        ) + if (t.optBoolean("van_mij")) "\n\n" + getString(R.string.eigen_telling_goedkeuren) else ""
        val verzoekId = Api.nieuwVerzoekId()
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.goedkeuren)))
            .setMessage(uitleg)
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.goedkeuren) { _, _ ->
                bezig {
                    val antwoord = Api.post(
                        this, "/api/app/$soort/${t.getInt("id")}/goedkeuren",
                        JSONObject().put("opmerking", veld.text.toString().trim()), verzoekId = verzoekId,
                    )
                    tril(60)
                    melding(antwoord.optString("melding"))
                    laad()
                }
            }
            .show()
    }

    companion object {
        const val KASSA = "kassa"
        const val KLUIS = "kluis"
        private const val EXTRA_SOORT = "soort"

        fun open(context: Context, soort: String) =
            context.startActivity(Intent(context, GeldActivity::class.java).putExtra(EXTRA_SOORT, soort))
    }
}
