package nl.kantineblauwgeel.tablet

import android.content.Context
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.widget.SwitchCompat

/** Bouwstenen voor de lijstschermen van 2.0 (activity_lijst.xml): witte kaarten met regels, knoppen en schakelaars,
 * in de stijl van de bestaande schermen. */
object Ui {

    private fun dp(context: Context, n: Int) = (n * context.resources.displayMetrics.density).toInt()

    /** Een kopje op de blauwe achtergrond. */
    fun kop(ouder: LinearLayout, tekst: String) {
        ouder.addView(TextView(ouder.context).apply {
            text = tekst
            textSize = 15f
            setTextColor(context.getColor(R.color.tekst_zacht_licht))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 4), dp(context, 18), 0, dp(context, 8))
        })
    }

    fun kaart(ouder: LinearLayout): LinearLayout {
        val kaart = LinearLayout(ouder.context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.kaart_achtergrond)
            elevation = dp(context, 4).toFloat()
            setPadding(dp(context, 20), dp(context, 8), dp(context, 20), dp(context, 8))
        }
        ouder.addView(kaart, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { bottomMargin = dp(ouder.context, 12) })
        return kaart
    }

    /** Een regel: titel en detail links, rechts wat je meegeeft (een knop, schakelaar of tekst). */
    fun regel(kaart: LinearLayout, titel: String, detail: String? = null, rechts: View? = null): LinearLayout {
        val context = kaart.context
        if (kaart.childCount > 0) kaart.addView(View(context).apply { setBackgroundColor(context.getColor(R.color.rand_licht)) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1))
        val regel = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(context, 64)
            setPadding(0, dp(context, 8), 0, dp(context, 8))
        }
        val links = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        links.addView(TextView(context).apply {
            text = titel
            textSize = 18f
            setTextColor(context.getColor(R.color.tekst_donker))
            setTypeface(typeface, Typeface.BOLD)
        })
        if (!detail.isNullOrEmpty()) links.addView(TextView(context).apply {
            text = detail
            textSize = 14f
            setTextColor(context.getColor(R.color.tekst_zacht))
        })
        regel.addView(links, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        if (rechts != null) regel.addView(rechts)
        kaart.addView(regel)
        return regel
    }

    fun knop(context: Context, tekst: String, actie: () -> Unit) = Button(context).apply {
        text = tekst
        isAllCaps = false
        textSize = 15f
        setOnClickListener { actie() }
    }

    /** Een rij knoppen naast elkaar, de gekozen in het geel. */
    fun keuze(context: Context, opties: List<Pair<String, String>>, gekozen: String?, kies: (String) -> Unit) =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            for ((sleutel, naam) in opties) addView(Button(context).apply {
                text = naam
                isAllCaps = false
                textSize = 14f
                if (sleutel == gekozen) {
                    setBackgroundColor(context.getColor(R.color.geel))
                    setTextColor(context.getColor(R.color.tekst_donker))
                }
                setOnClickListener { if (sleutel != gekozen) kies(sleutel) }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
                .apply { marginStart = dp(context, 6) })
        }

    fun schakelaar(context: Context, aan: Boolean, wissel: (Boolean) -> Unit) = SwitchCompat(context).apply {
        isChecked = aan
        setOnCheckedChangeListener { _, nieuw -> wissel(nieuw) }
    }

    fun tekst(kaart: LinearLayout, tekst: String) {
        kaart.addView(TextView(kaart.context).apply {
            text = tekst
            textSize = 14f
            setTextColor(context.getColor(R.color.tekst_zacht))
            setPadding(0, dp(context, 8), 0, dp(context, 8))
        })
    }
}
