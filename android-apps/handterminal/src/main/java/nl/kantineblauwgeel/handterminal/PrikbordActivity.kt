package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Het prikbord (Bijzonderheden op de site): wat er openstaat (urgent bovenaan), een nieuwe mededeling plaatsen,
 * reageren en afhandelen. Hetzelfde prikbord als op de site. */
class PrikbordActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.prikbord))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = true
        b.onderKnop.setText(R.string.nieuwe_mededeling)
        b.onderKnop.setOnClickListener { schrijf(getString(R.string.nieuwe_mededeling), metUrgent = true) { tekst, urgent ->
            post("/api/app/prikbord", JSONObject().put("tekst", tekst).put("urgent", urgent))
        } }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/prikbord"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun post(pad: String, body: JSONObject) {
        val verzoekId = Api.nieuwVerzoekId()
        bezig { toon(Api.post(this, pad, body, verzoekId = verzoekId)) }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val alle = data.getJSONArray("mededelingen").objecten()
        val open = alle.filter { !it.optBoolean("afgehandeld") }
        val klaar = alle.filter { it.optBoolean("afgehandeld") }
        Lijst.kop(inhoud, getString(R.string.n_open_kop, open.size))
        if (open.isEmpty()) Lijst.leeg(inhoud, getString(R.string.prikbord_leeg))
        open.forEach { mededeling(inhoud, it) }
        if (klaar.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.afgehandeld))
            klaar.forEach { mededeling(inhoud, it) }
        }
    }

    private fun mededeling(inhoud: LinearLayout, m: JSONObject) {
        val afgehandeld = m.optBoolean("afgehandeld")
        val kaart = Lijst.kaart(inhoud, if (m.optBoolean("urgent") && !afgehandeld) R.drawable.rand_links_rood else R.drawable.kaart)
        kaart.setPadding(dp(this, 14), dp(this, 10), dp(this, 12), dp(this, 6))
        kaart.alpha = if (afgehandeld) 0.6f else 1f
        if (m.optBoolean("urgent") && !afgehandeld) kaart.addView(tekst(getString(R.string.urgent), 11f, R.color.rood_balk, vet = true))
        kaart.addView(tekst(m.optString("tekst"), 15f, R.color.tekst))
        val wie = listOfNotNull(m.tekstOfNull("naam"), Lijst.datum(m.tekstOfNull("datum"))).joinToString(" · ")
        kaart.addView(tekst(if (afgehandeld) "$wie · " + getString(R.string.afgehandeld_door, m.tekstOfNull("afgehandeld_door") ?: "?") else wie, 12f, R.color.tekst_zacht))
        m.optJSONArray("reacties")?.objecten()?.forEach { r ->
            kaart.addView(tekst("↳ ${r.optString("tekst")}  (${r.optString("naam")}, ${Lijst.datum(r.tekstOfNull("datum"))})", 13f, R.color.tekst).apply {
                setPadding(dp(context, 10), dp(context, 4), 0, 0)
            })
        }
        if (afgehandeld) return
        val knoppen = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        knoppen.addView(knop(getString(R.string.reageren)) {
            schrijf(getString(R.string.reageren)) { tekst, _ ->
                post("/api/app/prikbord/${m.getInt("id")}/reactie", JSONObject().put("tekst", tekst))
            }
        })
        knoppen.addView(knop(getString(R.string.afhandelen)) {
            AlertDialog.Builder(this)
                .setMessage(R.string.afhandelen_vraag)
                .setPositiveButton(R.string.afhandelen) { _, _ ->
                    bezig { toon(Api.post(this, "/api/app/prikbord/${m.getInt("id")}/afhandelen", herhaalbaar = true)) }
                }
                .setNegativeButton(R.string.annuleren, null)
                .show()
        })
        kaart.addView(knoppen)
    }

    private fun tekst(waarde: String, grootte: Float, kleur: Int, vet: Boolean = false) = TextView(this).apply {
        text = waarde
        textSize = grootte
        setTextColor(getColor(kleur))
        if (vet) setTypeface(typeface, android.graphics.Typeface.BOLD)
        setPadding(0, dp(context, 2), 0, dp(context, 2))
    }

    private fun knop(tekst: String, actie: () -> Unit) = TextView(this).apply {
        text = tekst
        textSize = 14f
        setTextColor(getColor(R.color.navy))
        setTypeface(typeface, android.graphics.Typeface.BOLD)
        setBackgroundResource(R.drawable.regel_klik_kaart)
        setPadding(dp(context, 4), dp(context, 10), dp(context, 18), dp(context, 8))
        setOnClickListener { actie() }
    }

    /** Een tekst schrijven (nieuwe mededeling of reactie). Met @naam tag je iemand, net als op de site. */
    private fun schrijf(titel: String, metUrgent: Boolean = false, klaar: (String, Boolean) -> Unit) {
        val veld = EditText(this).apply {
            hint = getString(R.string.mededeling_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            minLines = 3
            maxLines = 6
        }
        val urgent = CheckBox(this).apply {
            text = getString(R.string.urgent_vraag)
            isVisible = metUrgent
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(veld)
            addView(urgent)
        }
        AlertDialog.Builder(this)
            .setTitle(titel)
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.plaatsen) { _, _ ->
                val tekst = veld.text.toString().trim()
                if (tekst.isNotEmpty()) klaar(tekst, urgent.isChecked)
            }
            .show()
        veld.requestFocus()
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, PrikbordActivity::class.java))
    }
}
