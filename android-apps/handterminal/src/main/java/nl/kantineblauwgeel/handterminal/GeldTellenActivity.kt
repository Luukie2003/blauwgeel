package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Kassa (of kluis) tellen: per coupure hoeveel er is (tik op het aantal voor het cijferpad, of − en +), bij de kassa
 * ook de contante omzet en de kaartbetalingen uit het PayPal-overzicht. Onderaan staat meteen het getelde bedrag, wat er
 * verwacht wordt en het verschil. Opslaan maakt een concept, net als op de site; goedkeuren gaat daarna in
 * [GeldActivity]. */
class GeldTellenActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var soort = GeldActivity.KASSA
    private val isKassa get() = soort == GeldActivity.KASSA

    private var coupures: List<JSONObject> = emptyList()
    private val aantallen = mutableMapOf<String, Int>()
    private val aantalViews = mutableMapOf<String, TextView>()
    private val bedragViews = mutableMapOf<String, TextView>()
    private var stand = 0.0
    private var contant = 0.0
    private var kaart = 0.0
    private var opmerking = ""
    private var verzoekId: String? = null

    private lateinit var contantView: TextView
    private lateinit var kaartView: TextView
    private lateinit var opmerkingView: TextView
    private lateinit var getelView: TextView
    private lateinit var verwachtView: TextView
    private lateinit var verschilView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        soort = intent.getStringExtra(EXTRA_SOORT) ?: GeldActivity.KASSA
        richtBalkIn(b.balk, getString(if (isKassa) R.string.kassa_tellen else R.string.kluis_tellen))
        b.verversen.isEnabled = false
        b.onderKnop.isVisible = true
        b.onderKnop.setText(R.string.opslaan_als_concept)
        b.onderKnop.setOnClickListener { opslaan() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (aantallen.values.none { it > 0 } && contant == 0.0 && kaart == 0.0) return finish()
                AlertDialog.Builder(this@GeldTellenActivity)
                    .setMessage(R.string.tellen_weggooien_vraag)
                    .setPositiveButton(R.string.weggooien) { _, _ -> finish() }
                    .setNegativeButton(R.string.verder_tellen, null)
                    .show()
            }
        })
        laad()
    }

    private fun laad() {
        bezig {
            val data = Api.getJson(this, "/api/app/$soort")
            stand = data.optDouble("stand")
            coupures = data.getJSONArray("coupures").objecten()
            bouw()
        }
    }

    private fun bouw() {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.kop(inhoud, getString(R.string.per_coupure))
        val lijst = Lijst.kaart(inhoud)
        coupures.forEachIndexed { i, c ->
            if (i > 0) lijst.addView(View(this).apply { setBackgroundResource(R.drawable.scheiding) },
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1))
            lijst.addView(coupureRegel(c))
        }

        if (isKassa) {
            Lijst.kop(inhoud, getString(R.string.omzet_uit_paypal))
            val omzet = Lijst.kaart(inhoud)
            contantView = invulRegel(omzet, getString(R.string.contante_omzet)) {
                Cijferpad.vraag(this, getString(R.string.contante_omzet), bedragTekst(contant), decimaal = true, voor = "€") {
                    contant = bedrag(it)
                    werkBij()
                }
            }
            kaartView = invulRegel(omzet, getString(R.string.kaartbetalingen)) {
                Cijferpad.vraag(this, getString(R.string.kaartbetalingen), bedragTekst(kaart), decimaal = true, voor = "€") {
                    kaart = bedrag(it)
                    werkBij()
                }
            }
            Lijst.tekst(omzet, getString(R.string.kaart_telt_niet_mee), grootte = 11.5f)
        }

        Lijst.kop(inhoud, getString(R.string.opmerking))
        val opm = Lijst.kaart(inhoud)
        opmerkingView = invulRegel(opm, getString(R.string.opmerking_optioneel)) { vraagOpmerking() }

        Lijst.kop(inhoud, getString(R.string.uitkomst))
        val uitkomst = Lijst.kaart(inhoud).apply { setPadding(0, dp(this@GeldTellenActivity, 4), 0, dp(this@GeldTellenActivity, 4)) }
        getelView = waardeRegel(uitkomst, getString(R.string.geteld))
        verwachtView = waardeRegel(uitkomst, getString(R.string.verwacht))
        verschilView = waardeRegel(uitkomst, getString(R.string.verschil_kort))
        Lijst.tekst(uitkomst, getString(if (isKassa) R.string.verwacht_kassa_uitleg else R.string.verwacht_kluis_uitleg, Lijst.euro(stand)), grootte = 11.5f)
        werkBij()
    }

    private fun coupureRegel(c: JSONObject): LinearLayout {
        val veld = c.optString("veld")
        val regel = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(context, 12), dp(context, 5), dp(context, 12), dp(context, 5))
        }
        regel.addView(TextView(this).apply {
            text = c.optString("naam")
            textSize = 16f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(getColor(R.color.tekst))
        }, LinearLayout.LayoutParams(dp(this, 70), LinearLayout.LayoutParams.WRAP_CONTENT))
        regel.addView(stapKnop(R.drawable.ic_min, R.string.minder) { zet(veld, (aantallen[veld] ?: 0) - 1) })
        val aantal = TextView(this).apply {
            textSize = 22f
            gravity = Gravity.CENTER
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(getColor(R.color.tekst))
            setBackgroundResource(R.drawable.regel_klik_kaart)
            setOnClickListener {
                Cijferpad.vraag(this@GeldTellenActivity, getString(R.string.hoeveel_van, c.optString("naam")),
                    (aantallen[veld] ?: 0).takeIf { it > 0 }?.toString() ?: "", max = 5) { zet(veld, it.toIntOrNull() ?: 0) }
            }
        }
        aantalViews[veld] = aantal
        regel.addView(aantal, LinearLayout.LayoutParams(0, dp(this, 44), 1f))
        regel.addView(stapKnop(R.drawable.ic_plus, R.string.meer_aantal) { zet(veld, (aantallen[veld] ?: 0) + 1) })
        val bedrag = TextView(this).apply {
            textSize = 13f
            gravity = Gravity.END
            setTextColor(getColor(R.color.tekst_zacht))
        }
        bedragViews[veld] = bedrag
        regel.addView(bedrag, LinearLayout.LayoutParams(dp(this, 82), LinearLayout.LayoutParams.WRAP_CONTENT))
        return regel
    }

    private fun stapKnop(icoon: Int, beschrijving: Int, actie: () -> Unit) = ImageView(this).apply {
        setImageResource(icoon)
        setColorFilter(getColor(R.color.tekst))
        contentDescription = getString(beschrijving)
        scaleType = ImageView.ScaleType.CENTER
        setBackgroundResource(R.drawable.toets_licht)
        layoutParams = LinearLayout.LayoutParams(dp(context, 44), dp(context, 44))
        setOnClickListener {
            actie()
            tril(15)
        }
    }

    private fun invulRegel(kaart: LinearLayout, label: String, actie: () -> Unit): TextView {
        val regel = Lijst.regel(kaart, label, null, "–", R.color.navy, klik = actie)
        return regel.getChildAt(regel.childCount - 1) as TextView
    }

    private fun waardeRegel(kaart: LinearLayout, label: String): TextView {
        val regel = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(context, 12), dp(context, 5), dp(context, 12), dp(context, 5))
        }
        regel.addView(TextView(this).apply {
            text = label
            textSize = 14f
            setTextColor(getColor(R.color.tekst_zacht))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val waarde = TextView(this).apply {
            textSize = 17f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(getColor(R.color.tekst))
        }
        regel.addView(waarde)
        kaart.addView(regel)
        return waarde
    }

    private fun zet(veld: String, aantal: Int) {
        aantallen[veld] = aantal.coerceIn(0, 99_999)
        verzoekId = null
        werkBij()
    }

    private fun geteld(): Double = coupures.sumOf { (aantallen[it.optString("veld")] ?: 0) * it.optDouble("waarde") }

    private fun verwacht(): Double = stand + if (isKassa) contant else 0.0

    private fun werkBij() {
        for (c in coupures) {
            val veld = c.optString("veld")
            val n = aantallen[veld] ?: 0
            aantalViews[veld]?.text = n.toString()
            aantalViews[veld]?.setTextColor(getColor(if (n > 0) R.color.tekst else R.color.rand_licht))
            bedragViews[veld]?.text = if (n > 0) Lijst.euro(n * c.optDouble("waarde")) else ""
        }
        if (isKassa) {
            contantView.text = Lijst.euro(contant)
            kaartView.text = Lijst.euro(kaart)
        }
        opmerkingView.text = if (opmerking.isEmpty()) "–" else "✓"
        val geteld = geteld()
        getelView.text = Lijst.euro(geteld)
        verwachtView.text = Lijst.euro(verwacht())
        val (tekst, kleur) = Lijst.verschil(this, geteld - verwacht())
        verschilView.text = tekst
        verschilView.setTextColor(getColor(kleur))
        b.onderKnop.text = getString(R.string.opslaan_als_concept_bedrag, Lijst.euro(geteld))
    }

    private fun bedragTekst(bedrag: Double) = if (bedrag == 0.0) "" else Lijst.getal(bedrag, 2)

    private fun bedrag(tekst: String) = (tekst.replace(',', '.').toDoubleOrNull() ?: 0.0).coerceIn(0.0, 99_999.0)

    private fun vraagOpmerking() {
        val veld = EditText(this).apply {
            setText(opmerking)
            hint = getString(R.string.opmerking_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES or InputType.TYPE_TEXT_FLAG_MULTI_LINE
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(veld)
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.opmerking)
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.ok) { _, _ ->
                opmerking = veld.text.toString().trim()
                verzoekId = null
                werkBij()
            }
            .show()
        veld.requestFocus()
    }

    private fun opslaan() {
        val geteld = geteld()
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.opslaan_als_concept)))
            .setMessage(getString(R.string.geld_opslaan_vraag, Lijst.euro(geteld), Lijst.verschil(this, geteld - verwacht()).first))
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.opslaan) { _, _ -> verstuur() }
            .show()
    }

    private fun verstuur() {
        // Hetzelfde verzoek_id bij nog een keer proberen na een fout: dan slaat de site hem nooit dubbel op.
        val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
        val body = JSONObject().put("opmerking", opmerking)
        val lijst = JSONObject()
        aantallen.forEach { (veld, n) -> lijst.put(veld, n) }
        body.put("aantallen", lijst)
        if (isKassa) body.put("contante_omzet", contant).put("kaart_omzet", kaart)
        b.onderKnop.isEnabled = false
        bezig {
            try {
                val antwoord = Api.post(this, "/api/app/$soort/tellen", body, verzoekId = id)
                tril(60)
                AlertDialog.Builder(this)
                    .setCustomTitle(dialoogTitel(getString(R.string.opgeslagen)))
                    .setMessage(antwoord.optString("melding") + "\n\n" + getString(R.string.concept_uitleg))
                    .setCancelable(false)
                    .setPositiveButton(R.string.ok) { _, _ -> vraagTaken(antwoord) { finish() } }
                    .show()
            } finally {
                b.onderKnop.isEnabled = true
            }
        }
    }

    companion object {
        private const val EXTRA_SOORT = "soort"

        fun open(context: Context, soort: String) =
            context.startActivity(Intent(context, GeldTellenActivity::class.java).putExtra(EXTRA_SOORT, soort))
    }
}
