package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De aanmeldingen voor de Club van 20 die via de website binnenkwamen: controleer de betaling (Mollie in de app,
 * contant bij de bardienst) en keur goed, of wijs af met een reden. Hetzelfde als Club van 20 > Aanmeldingen op de
 * handterminal-pagina van de site; ontbrekende gegevens (team, telefoon) vul je later op de computer aan. */
class AanmeldingenActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.aanmeldingen))
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
                toon(Api.getJson(this, "/api/app/aanmeldingen"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        val status = data.optJSONObject("status")
        when {
            status?.optBoolean("aan") == false ->
                Lijst.tekst(Lijst.kaart(inhoud, R.drawable.rand_links_rood), getString(R.string.aanmelden_uit), kleur = R.color.tekst)
            status?.optBoolean("open") == false ->
                Lijst.tekst(Lijst.kaart(inhoud, R.drawable.rand_links_oranje), getString(R.string.aanmelden_opent, status.optString("opent")), kleur = R.color.tekst)
        }
        Lijst.tekst(inhoud, getString(R.string.aanmeldingen_uitleg), grootte = 12f)

        val open = data.getJSONArray("openstaand").objecten()
        Lijst.kop(inhoud, getString(R.string.wacht_op_goedkeuring, open.size))
        if (open.isEmpty()) Lijst.leeg(inhoud, getString(R.string.geen_aanmeldingen))
        open.forEach { aanmelding(inhoud, it) }

        val behandeld = data.getJSONArray("behandeld").objecten()
        if (behandeld.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.eerder_behandeld))
            val kaart = Lijst.kaart(inhoud)
            behandeld.forEach { a ->
                val goed = a.optString("status") == "goedgekeurd"
                Lijst.regel(kaart, a.optString("bordje"),
                    listOfNotNull(a.tekstOfNull("naam"), Lijst.datum(a.tekstOfNull("op")), a.tekstOfNull("door")).joinToString(" · "),
                    a.optString("status"), if (goed) R.color.groen_tekst else R.color.tekst_zacht)
            }
        }
    }

    private fun aanmelding(inhoud: LinearLayout, a: JSONObject) {
        val kaart = Lijst.kaart(inhoud)
        val lid = a.optJSONObject("lid")
        val soort = when {
            a.optBoolean("verlenging") -> getString(R.string.verlenging) + (lid?.takeIf { a.optBoolean("bordje_anders") }?.let { " · " + getString(R.string.nu_bordje, it.optString("naam")) } ?: "")
            lid != null -> getString(R.string.bestaand_lid, lid.optString("naam"))
            else -> getString(R.string.nieuw_lid)
        }
        Lijst.regel(kaart, a.optString("bordje"), "${a.optString("naam")} · $soort", Lijst.datum(a.tekstOfNull("op")), R.color.tekst_zacht)
        val betaling = (if (a.optString("betaalwijze") == "mollie") "Mollie" else getString(R.string.contant)) + " · " + Lijst.euro(a.optDouble("bedrag"))
        Lijst.info(kaart, getString(R.string.betaling), betaling, a.tekstOfNull("bardienst")?.let { getString(R.string.bardienst_naam, it) })
        Lijst.knop(kaart, getString(R.string.goedkeuren)) { goedkeuren(a) }
        Lijst.knop(kaart, getString(R.string.afwijzen)) { afwijzen(a) }
    }

    private fun goedkeuren(a: JSONObject) {
        val gecontroleerd = CheckBox(this).apply { text = getString(R.string.betaling_gecontroleerd) }
        val bordje = CheckBox(this).apply {
            text = getString(R.string.bordje_aanpassen, a.optString("bordje"))
            isVisible = a.optBoolean("bordje_anders")
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(gecontroleerd)
            addView(bordje)
        }
        val id = Api.nieuwVerzoekId()
        val dialoog = AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.aanmelding_goedkeuren, a.optString("bordje"))))
            .setMessage(getString(R.string.goedkeuren_uitleg))
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.goedkeuren) { _, _ ->
                bezig {
                    val antwoord = Api.post(this, "/api/app/aanmeldingen/${a.getInt("id")}/goedkeuren",
                        JSONObject().put("betaling_gecontroleerd", true).put("bordje_aanpassen", bordje.isChecked), verzoekId = id)
                    tril(60)
                    melding(antwoord.optString("melding"), lang = true)
                    laad()
                }
            }
            .show()
        // Pas goedkeuren als de betaling is gecontroleerd, net als het vinkje op de site.
        val knop = dialoog.getButton(AlertDialog.BUTTON_POSITIVE)
        knop.isEnabled = false
        gecontroleerd.setOnCheckedChangeListener { _, aan -> knop.isEnabled = aan }
    }

    private fun afwijzen(a: JSONObject) {
        val veld = EditText(this).apply {
            hint = getString(R.string.afwijs_reden_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(veld)
        }
        val id = Api.nieuwVerzoekId()
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.aanmelding_afwijzen, a.optString("bordje"))))
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.afwijzen) { _, _ ->
                bezig {
                    val antwoord = Api.post(this, "/api/app/aanmeldingen/${a.getInt("id")}/afwijzen",
                        JSONObject().put("reden", veld.text.toString().trim()), verzoekId = id)
                    melding(antwoord.optString("melding"))
                    laad()
                }
            }
            .show()
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, AanmeldingenActivity::class.java))
    }
}
