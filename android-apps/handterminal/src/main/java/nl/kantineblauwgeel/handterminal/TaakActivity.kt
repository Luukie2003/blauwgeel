package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.CheckBox
import android.widget.LinearLayout
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Een taak die een beheerder voor je klaarzette: wat er moet gebeuren, de stappen om af te vinken, waar je het doet
 * (het scherm in de app, of "niet mogelijk in de app" als het alleen op de website kan) en afronden. Zelfde taken als
 * in "Wat moet er nu?" op de site. */
class TaakActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var taakId = 0
    private var taak: JSONObject? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        taakId = intent.getIntExtra(EXTRA_ID, 0)
        richtBalkIn(b.balk, getString(R.string.taak))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = true
        b.onderKnop.setText(R.string.taak_afronden)
        b.onderKnop.setOnClickListener { afronden() }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/taken/$taakId"))
            } catch (f: Api.Fout) {
                if (f.soort == Api.Soort.NIET_GEVONDEN) {
                    melding(f.message ?: "", lang = true)
                    finish()
                } else throw f
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(t: JSONObject) {
        taak = t
        zetBalkTitel(t.optString("titel"))
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)

        val kaart = Lijst.kaart(inhoud, if (t.optBoolean("te_laat")) R.drawable.rand_links_rood else R.drawable.kaart)
        Lijst.tekst(kaart, t.optString("titel"), grootte = 17f, kleur = R.color.tekst, vet = true)
        t.tekstOfNull("omschrijving")?.let { Lijst.tekst(kaart, it, grootte = 14f, kleur = R.color.tekst) }
        t.tekstOfNull("deadline")?.let {
            Lijst.info(kaart, getString(R.string.uiterlijk), Lijst.datum("$it 00:00", metTijd = false),
                if (t.optBoolean("te_laat")) getString(R.string.te_laat) else null, if (t.optBoolean("te_laat")) R.color.rood_balk else R.color.tekst)
        }
        t.tekstOfNull("door")?.let { Lijst.info(kaart, getString(R.string.klaargezet_door), it) }
        val anderen = t.optJSONArray("anderen")?.objecten().orEmpty()
        if (anderen.isNotEmpty()) {
            Lijst.info(kaart, getString(R.string.samen_met), anderen.joinToString(", ") { a ->
                a.optString("naam") + if (a.optBoolean("klaar")) " ✓" else ""
            })
        }

        val stappen = t.optJSONArray("stappen")?.objecten().orEmpty()
        if (stappen.isNotEmpty()) {
            Lijst.kop(inhoud, getString(R.string.stappen_n, stappen.count { it.optBoolean("af") }, stappen.size))
            val lijst = Lijst.kaart(inhoud).apply { setPadding(dp(this@TaakActivity, 8), dp(this@TaakActivity, 4), dp(this@TaakActivity, 8), dp(this@TaakActivity, 4)) }
            stappen.forEachIndexed { i, s ->
                lijst.addView(CheckBox(this).apply {
                    text = s.optString("tekst")
                    textSize = 15f
                    isChecked = s.optBoolean("af")
                    minHeight = dp(context, 44)
                    setOnCheckedChangeListener { _, aan -> vink(i, aan) }
                })
            }
        }

        val doel = t.optJSONObject("doel")
        if (doel != null) {
            Lijst.kop(inhoud, getString(R.string.waar_doe_je_het))
            val waar = Lijst.kaart(inhoud)
            val endpoint = doel.optString("endpoint")
            if (Schermen.heeft(endpoint)) {
                Lijst.knop(waar, getString(R.string.naar_scherm, doel.optString("label"))) { Schermen.open(this, endpoint) }
            } else {
                Lijst.tekst(waar, getString(R.string.taak_alleen_website, doel.optString("label")), kleur = R.color.tekst)
                Lijst.knop(waar, doel.optString("label")) { nietInApp(doel.optString("label")) }
            }
        }
        b.onderKnop.isEnabled = stappen.all { it.optBoolean("af") }
        b.onderKnop.alpha = if (b.onderKnop.isEnabled) 1f else 0.5f
    }

    private fun vink(index: Int, aan: Boolean) {
        bezig {
            Api.post(this, "/api/app/taken/$taakId/stap", JSONObject().put("stap", index).put("af", aan), herhaalbaar = true)
            laad()
        }
    }

    private fun afronden() {
        val id = Api.nieuwVerzoekId()
        bezig {
            val antwoord = Api.post(this, "/api/app/taken/$taakId/afronden", verzoekId = id)
            tril(60)
            melding(antwoord.optString("melding"), lang = true)
            finish()
        }
    }

    companion object {
        private const val EXTRA_ID = "taak_id"

        fun open(context: Context, taakId: Int) =
            context.startActivity(Intent(context, TaakActivity::class.java).putExtra(EXTRA_ID, taakId))
    }
}
