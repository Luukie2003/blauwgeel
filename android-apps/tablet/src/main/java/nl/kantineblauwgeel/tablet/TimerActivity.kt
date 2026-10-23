package nl.kantineblauwgeel.tablet

import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import androidx.appcompat.app.AlertDialog
import org.json.JSONObject

/** De timer op de tv's (2.0): bijvoorbeeld "Patat" over 8 minuten. Starten, er 5 minuten bij doen of weghalen. Zelfde
 * als in de handterminal-app (/api/app/timers). */
class TimerActivity : LijstActivity() {

    override val pad = "/api/app/timers"
    override val titel = R.string.titel_timer

    override fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        val start = Ui.kaart(inhoud)
        Ui.regel(start, getString(R.string.timer_nieuw), getString(R.string.timer_uitleg), Ui.knop(this, getString(R.string.timer_starten)) { nieuw() })
        val timers = data.optJSONArray("timers")
        Ui.kop(inhoud, getString(R.string.timers_op_tv))
        val kaart = Ui.kaart(inhoud)
        if (timers == null || timers.length() == 0) Ui.tekst(kaart, getString(R.string.geen_timers))
        for (i in 0 until (timers?.length() ?: 0)) {
            val t = timers!!.getJSONObject(i)
            val rest = t.optInt("resterend")
            val detail = if (rest > 0) getString(R.string.timer_nog, rest / 60, rest % 60) else getString(R.string.timer_klaar)
            val regel = Ui.regel(kaart, t.optString("naam"), detail, Ui.knop(this, getString(R.string.plus_5)) {
                stuur("/api/app/timers/${t.getInt("id")}/verlengen", JSONObject().put("minuten", 5))
            })
            regel.addView(Ui.knop(this, getString(R.string.weghalen)) { stuur("/api/app/timers/${t.getInt("id")}/stoppen") })
        }
    }

    private fun nieuw() {
        val dp = resources.displayMetrics.density
        val vak = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((24 * dp).toInt(), (8 * dp).toInt(), (24 * dp).toInt(), 0)
        }
        val naam = EditText(this).apply { hint = getString(R.string.timer_naam_hint); inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES }
        val minuten = EditText(this).apply { hint = getString(R.string.timer_minuten_hint); inputType = InputType.TYPE_CLASS_NUMBER }
        vak.addView(naam)
        vak.addView(minuten)
        AlertDialog.Builder(this)
            .setTitle(R.string.timer_nieuw)
            .setView(vak)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.timer_starten) { _, _ ->
                stuur("/api/app/timers", JSONObject().put("naam", naam.text.toString().trim()).put("minuten", minuten.text.toString().toIntOrNull() ?: 0))
            }
            .show()
    }
}
