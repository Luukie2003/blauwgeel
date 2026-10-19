package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.CijferpadBinding

/** Het cijferpad (layout/cijferpad.xml): een getal intikken zonder het toetsenbord van Android.
 * [koppel] maakt een vast pad (zoals in het telscherm) werkend; [vraag] toont het in een venster. */
object Cijferpad {

    /** [decimaal]: de linker onderste toets is een komma in plaats van C (wissen), voor bedragen. */
    fun koppel(pad: CijferpadBinding, decimaal: Boolean = false, max: Int = 6, waarde: () -> String, zet: (String) -> Unit) {
        val cijfers = listOf(pad.pad0, pad.pad1, pad.pad2, pad.pad3, pad.pad4, pad.pad5, pad.pad6, pad.pad7, pad.pad8, pad.pad9)
        cijfers.forEachIndexed { cijfer, toets ->
            toets.setOnClickListener {
                it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                val nu = waarde()
                val delen = nu.split(',')
                when {
                    nu.length >= max -> {}
                    delen.size == 2 && delen[1].length >= 2 -> {} // hooguit twee cijfers achter de komma
                    nu == "0" -> zet(cijfer.toString())
                    else -> zet(nu + cijfer)
                }
            }
        }
        pad.padLinks.text = if (decimaal) "," else "C"
        pad.padLinks.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            val nu = waarde()
            if (!decimaal) zet("") else if (!nu.contains(',')) zet(if (nu.isEmpty()) "0," else "$nu,")
        }
        pad.padTerug.setOnClickListener {
            it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
            zet(waarde().dropLast(1))
        }
        pad.padTerug.setOnLongClickListener {
            zet("")
            true
        }
    }

    fun vraag(
        activity: Activity,
        titel: String,
        begin: String = "",
        decimaal: Boolean = false,
        eenheid: String = "",
        voor: String = "",
        max: Int = if (decimaal) 9 else 6,
        bijOk: (String) -> Unit,
    ) {
        val inflater = LayoutInflater.from(activity)
        val pad = CijferpadBinding.inflate(inflater)
        val dp = activity.resources.displayMetrics.density
        val scherm = TextView(activity).apply {
            textSize = 34f
            gravity = Gravity.CENTER
            setTextColor(activity.getColor(R.color.tekst))
            setPadding(0, (4 * dp).toInt(), 0, (8 * dp).toInt())
        }
        var waarde = begin
        fun toon() {
            scherm.text = if (waarde.isEmpty()) "–" else listOf(voor, waarde, eenheid).filter { it.isNotEmpty() }.joinToString(" ")
        }
        toon()
        koppel(pad, decimaal, max = max, waarde = { waarde }) {
            waarde = it
            toon()
        }
        val inhoud = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((14 * dp).toInt(), (4 * dp).toInt(), (14 * dp).toInt(), 0)
            addView(scherm)
            addView(pad.root)
        }
        AlertDialog.Builder(activity)
            .setTitle(titel)
            .setView(inhoud)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.ok) { _, _ -> bijOk(waarde) }
            .show()
    }
}
