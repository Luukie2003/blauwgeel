package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Paint
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De boodschappenlijst: losse inkopen buiten de voorraad om (schoonmaakspullen, wc-papier). Tik om af te vinken (of
 * weer terug te zetten), lang indrukken om weg te halen. Dezelfde lijst als op de site. */
class BoodschappenActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.boodschappen))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = true
        b.onderKnop.setText(R.string.boodschap_toevoegen)
        b.onderKnop.setOnClickListener { toevoegen() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/boodschappen"))
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        val open = data.getJSONArray("open").objecten()
        Lijst.kop(inhoud, getString(R.string.nog_halen, open.size))
        if (open.isEmpty()) Lijst.leeg(inhoud, getString(R.string.boodschappen_leeg))
        else {
            val kaart = Lijst.kaart(inhoud)
            open.forEach { item(kaart, it, af = false) }
        }
        val af = data.getJSONArray("afgevinkt").objecten()
        if (af.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.afgevinkt))
            val kaart = Lijst.kaart(inhoud)
            af.forEach { item(kaart, it, af = true) }
        }
        Lijst.tekst(inhoud, getString(R.string.boodschappen_uitleg), grootte = 11.5f)
    }

    private fun item(kaart: LinearLayout, i: JSONObject, af: Boolean) {
        val detail = if (af) listOfNotNull(i.tekstOfNull("afgevinkt_door"), Lijst.datum(i.tekstOfNull("afgevinkt_op"))).joinToString(" · ")
        else listOfNotNull(i.tekstOfNull("door"), Lijst.datum(i.tekstOfNull("op"))).joinToString(" · ")
        val regel = Lijst.regel(kaart, i.optString("tekst"), detail, if (af) "✓" else "○", if (af) R.color.groen_tekst else R.color.tekst_zacht) {
            post("/api/app/boodschappen/${i.getInt("id")}/afvinken", JSONObject().put("af", !af))
        }
        if (af) {
            regel.alpha = 0.6f
            ((regel.getChildAt(0) as LinearLayout).getChildAt(0) as TextView).paintFlags = Paint.STRIKE_THRU_TEXT_FLAG
        }
        regel.setOnLongClickListener {
            AlertDialog.Builder(this)
                .setMessage(getString(R.string.boodschap_weghalen_vraag, i.optString("tekst")))
                .setNegativeButton(R.string.annuleren, null)
                .setPositiveButton(R.string.weghalen) { _, _ -> post("/api/app/boodschappen/${i.getInt("id")}/verwijderen", JSONObject()) }
                .show()
            true
        }
    }

    private fun post(pad: String, body: JSONObject) {
        bezig {
            tril()
            toon(Api.post(this, pad, body, herhaalbaar = true))
        }
    }

    private fun toevoegen() {
        val veld = EditText(this).apply {
            hint = getString(R.string.boodschap_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(veld)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.boodschap_toevoegen)
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.toevoegen) { _, _ ->
                val tekst = veld.text.toString().trim()
                if (tekst.isNotEmpty()) {
                    val id = Api.nieuwVerzoekId()
                    bezig {
                        val antwoord = Api.post(this, "/api/app/boodschappen", JSONObject().put("tekst", tekst), verzoekId = id)
                        melding(antwoord.optString("melding"))
                        toon(antwoord)
                    }
                }
            }
            .show()
        veld.requestFocus()
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, BoodschappenActivity::class.java))
    }
}
