package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.view.HapticFeedbackConstants
import android.view.ViewGroup
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.RekenmachineBinding
import kotlin.math.roundToLong

/** Een ingebouwde rekenmachine voor het tellen: bijvoorbeeld 3 kratten van 24 en nog 7 losse, "3×24+7" = 79, en dan
 * "Gebruiken". Alleen + − × ÷ (keer en delen eerst), net als de rekenmachine op de looplijst van de site. */
object Rekenmachine {

    private val operatoren = setOf('+', '−', '×', '÷')

    fun open(activity: Activity, begin: String, bijGebruiken: (Int) -> Unit) {
        val r = RekenmachineBinding.inflate(activity.layoutInflater)
        var som = begin
        fun toon() {
            r.rekenSom.text = som
            r.rekenUitkomst.text = uitrekenen(som)?.let(::tekst) ?: "0"
        }
        for (i in 0 until r.rekenToetsen.childCount) {
            val rij = r.rekenToetsen.getChildAt(i) as ViewGroup
            for (k in 0 until rij.childCount) {
                val toets = rij.getChildAt(k)
                val teken = toets.tag as String
                toets.setOnClickListener {
                    it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                    som = when {
                        teken == "C" -> ""
                        teken == "⌫" -> som.dropLast(1)
                        teken[0] in operatoren -> when {
                            som.isEmpty() -> som
                            som.last() in operatoren -> som.dropLast(1) + teken
                            else -> som + teken
                        }
                        som.length >= 30 -> som
                        else -> som + teken
                    }
                    toon()
                }
            }
        }
        toon()
        AlertDialog.Builder(activity)
            .setView(r.root)
            .setNegativeButton(R.string.sluiten, null)
            .setPositiveButton(R.string.gebruiken) { _, _ ->
                uitrekenen(som)?.let { bijGebruiken(maxOf(0L, it.roundToLong()).toInt()) }
            }
            .show()
    }

    /** "3×24+7" → 79.0; null als er niets (zinnigs) staat. Een operator aan het eind telt niet mee. */
    fun uitrekenen(som: String): Double? {
        val delen = Regex("\\d+(?:,\\d+)?|[+−×÷]").findAll(som).map { it.value }.toMutableList()
        while (delen.isNotEmpty() && delen.last()[0] in operatoren) delen.removeAt(delen.lastIndex)
        if (delen.isEmpty()) return null
        var totaal = 0.0
        var teken = 1.0
        var term: Double? = null
        var op: String? = null
        for (d in delen) {
            when (d) {
                "+", "−" -> {
                    totaal += teken * (term ?: 0.0)
                    teken = if (d == "+") 1.0 else -1.0
                    term = null
                    op = null
                }
                "×", "÷" -> op = d
                else -> {
                    val getal = d.replace(',', '.').toDouble()
                    term = when {
                        term == null -> getal
                        op == "÷" -> term / getal
                        else -> term * getal
                    }
                }
            }
        }
        totaal += teken * (term ?: 0.0)
        return if (totaal.isFinite()) Math.round(totaal * 100) / 100.0 else null
    }

    private fun tekst(waarde: Double) =
        if (waarde == Math.floor(waarde)) waarde.toLong().toString() else waarde.toString().replace('.', ',')
}
