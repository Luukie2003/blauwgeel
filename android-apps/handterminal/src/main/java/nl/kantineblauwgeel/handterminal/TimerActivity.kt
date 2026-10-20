package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.InputType
import android.view.Gravity
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Timer op de tv's, bijvoorbeeld voor de gehaktballen: hij staat linksonder op alle tv's en telt af; daarna staat er
 * "Klaar!" tot je hem weghaalt (of tot een kwartier later). De snelknoppen onthouden de tijd van de vorige keer. Zelfde
 * timers als op de site (Timer op de tv), zie kiosk_timers.py. */
class TimerActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private val klok = Handler(Looper.getMainLooper())
    private var maxMinuten = 240

    /** Per lopende timer: wanneer hij klaar is (op de klok van het toestel) en het veld met de tijd. */
    private class Lopend(val klaarOp: Long, val tijd: TextView, val kaart: LinearLayout)
    private val lopend = mutableListOf<Lopend>()

    private val tik = object : Runnable {
        override fun run() {
            werkTijdenBij()
            klok.postDelayed(this, 1000)
        }
    }
    private val ververs = object : Runnable {
        override fun run() {
            laad(stil = true)
            klok.postDelayed(this, 15_000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.timer_titel))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = true
        b.onderKnop.setText(R.string.andere_timer)
        b.onderKnop.setOnClickListener { andereTimer(null, null) }
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
        klok.post(tik)
        klok.postDelayed(ververs, 15_000)
    }

    override fun onPause() {
        super.onPause()
        klok.removeCallbacks(tik)
        klok.removeCallbacks(ververs)
    }

    override fun weerVerbonden() = laad()

    private fun laad(stil: Boolean = false) {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/timers"))
            } finally {
                if (!stil) b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon(data: JSONObject) {
        maxMinuten = data.optInt("max_minuten", maxMinuten)
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        lopend.clear()

        Lijst.kop(inhoud, getString(R.string.op_de_tvs))
        val timers = data.optJSONArray("timers")?.objecten().orEmpty()
        if (timers.isEmpty()) Lijst.leeg(inhoud, getString(R.string.geen_timer))
        val nu = SystemClock.elapsedRealtime()
        for (t in timers) {
            val kaart = Lijst.kaart(inhoud, R.drawable.rand_links_navy)
            val boven = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(context, 12), dp(context, 8), dp(context, 12), 0)
            }
            val tekst = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            tekst.addView(TextView(this).apply {
                text = t.optString("naam")
                textSize = 16f
                setTextColor(getColor(R.color.tekst))
                setTypeface(typeface, Typeface.BOLD)
            })
            tekst.addView(TextView(this).apply {
                text = getString(R.string.klaar_om, t.optString("klaar_om")) + (t.tekstOfNull("gestart_door")?.let { " · $it" } ?: "")
                textSize = 12f
                setTextColor(getColor(R.color.tekst_zacht))
            })
            boven.addView(tekst, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            val tijd = TextView(this).apply {
                textSize = 30f
                setTextColor(getColor(R.color.navy))
                typeface = Typeface.DEFAULT_BOLD
                fontFeatureSettings = "tnum"  // cijfers even breed: de tijd springt niet heen en weer
            }
            boven.addView(tijd)
            kaart.addView(boven)
            val id = t.getInt("id")
            val knoppen = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            knoppen.addView(knop(getString(R.string.vijf_minuten_erbij)) { verleng(id) }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            knoppen.addView(knop(getString(R.string.weghalen)) { stop(id, t.optString("naam")) }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            kaart.addView(knoppen)
            lopend += Lopend(nu + t.optLong("resterend") * 1000, tijd, kaart)
        }
        werkTijdenBij()

        Lijst.kop(inhoud, getString(R.string.timer_starten))
        val voorstellen = data.optJSONArray("voorstellen")?.objecten().orEmpty()
        val kaart = Lijst.kaart(inhoud)
        for (v in voorstellen) {
            val naam = v.optString("naam")
            val minuten = v.optInt("minuten")
            val regel = Lijst.regel(kaart, naam, getString(R.string.lang_indrukken_andere_tijd), getString(R.string.n_min, minuten), R.color.navy) {
                start(naam, minuten)
            }
            regel.setOnLongClickListener {
                andereTimer(naam, minuten)
                true
            }
        }
        Lijst.tekst(inhoud, getString(R.string.timer_uitleg), grootte = 11.5f)
    }

    private fun knop(tekst: String, actie: () -> Unit) = TextView(this).apply {
        text = tekst
        textSize = 15f
        gravity = Gravity.CENTER
        setTextColor(getColor(R.color.navy))
        setTypeface(typeface, Typeface.BOLD)
        minHeight = dp(context, 46)
        setBackgroundResource(R.drawable.regel_klik_kaart)
        setOnClickListener { actie() }
    }

    private fun werkTijdenBij() {
        val nu = SystemClock.elapsedRealtime()
        for (l in lopend) {
            val rest = maxOf(0L, (l.klaarOp - nu + 999) / 1000)
            l.tijd.text = if (rest == 0L) getString(R.string.klaar) else tijdTekst(rest)
            l.kaart.setBackgroundResource(if (rest == 0L) R.drawable.rand_links_oranje else R.drawable.rand_links_navy)
        }
    }

    private fun tijdTekst(seconden: Long): String {
        val u = seconden / 3600
        val m = seconden % 3600 / 60
        val s = seconden % 60
        return if (u > 0) "%d:%02d:%02d".format(u, m, s) else "%d:%02d".format(m, s)
    }

    private fun start(naam: String, minuten: Int) {
        val id = Api.nieuwVerzoekId()
        bezig {
            val antwoord = Api.post(this, "/api/app/timers", JSONObject().put("naam", naam).put("minuten", minuten), verzoekId = id)
            tril(60)
            melding(antwoord.optString("melding"))
            toon(antwoord)
        }
    }

    private fun verleng(timerId: Int) {
        val id = Api.nieuwVerzoekId()
        bezig {
            val antwoord = Api.post(this, "/api/app/timers/$timerId/verlengen", JSONObject().put("minuten", 5), verzoekId = id)
            tril()
            melding(antwoord.optString("melding"))
            toon(antwoord)
        }
    }

    private fun stop(timerId: Int, naam: String) {
        AlertDialog.Builder(this)
            .setMessage(getString(R.string.timer_weghalen_vraag, naam))
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.weghalen) { _, _ ->
                bezig {
                    val antwoord = Api.post(this, "/api/app/timers/$timerId/stoppen", herhaalbaar = true)
                    tril()
                    melding(antwoord.optString("melding"))
                    toon(antwoord)
                }
            }
            .show()
    }

    /** Een timer met een eigen naam of een andere tijd. */
    private fun andereTimer(naam: String?, minuten: Int?) {
        val naamVeld = EditText(this).apply {
            hint = getString(R.string.timer_naam_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            setText(naam ?: "")
        }
        val minutenVeld = EditText(this).apply {
            hint = getString(R.string.minuten_hint)
            inputType = InputType.TYPE_CLASS_NUMBER
            setText((minuten ?: 15).toString())
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(TextView(context).apply { setText(R.string.waarvoor); textSize = 12f; setTextColor(getColor(R.color.tekst_zacht)) })
            addView(naamVeld)
            addView(TextView(context).apply {
                setText(R.string.hoeveel_minuten); textSize = 12f; setTextColor(getColor(R.color.tekst_zacht)); setPadding(0, dp(context, 8), 0, 0)
            })
            addView(minutenVeld)
        }
        val dialoog = AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.timer_starten)))
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.starten, null)
            .show()
        dialoog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val n = naamVeld.text.toString().trim()
            val m = minutenVeld.text.toString().trim().toIntOrNull()
            when {
                n.isEmpty() -> naamVeld.error = getString(R.string.timer_naam_nodig)
                m == null || m !in 1..maxMinuten -> minutenVeld.error = getString(R.string.timer_minuten_fout, maxMinuten)
                else -> {
                    dialoog.dismiss()
                    start(n, m)
                }
            }
        }
        (if (naam == null) naamVeld else minutenVeld).requestFocus()
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, TimerActivity::class.java))
    }
}
