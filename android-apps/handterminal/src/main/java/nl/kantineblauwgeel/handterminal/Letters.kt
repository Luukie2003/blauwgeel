package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.graphics.Typeface
import android.text.TextPaint
import android.text.style.MetricAffectingSpan
import androidx.core.content.res.ResourcesCompat

/** De letters van de site (res/font): Barlow voor de tekst en de smalle Barlow Condensed (de sportletter) voor koppen
 * en getallen. Het thema zet Barlow al overal; dit is voor tekst die de app zelf opbouwt. */
object Letters {

    fun tekst(context: Context): Typeface = ResourcesCompat.getFont(context, R.font.barlow) ?: Typeface.DEFAULT

    fun medium(context: Context): Typeface = ResourcesCompat.getFont(context, R.font.barlow_medium) ?: Typeface.DEFAULT

    /** De sportletter: gewoon is half-vet, met [Typeface.BOLD] vet. */
    fun koppen(context: Context): Typeface = ResourcesCompat.getFont(context, R.font.barlow_condensed) ?: Typeface.DEFAULT_BOLD

    /** Een stuk tekst in een andere letter, zoals "blik" achter het getal 24 (een TypefaceSpan met een eigen letter kan
     * pas vanaf Android 9). */
    class Span(private val letter: Typeface) : MetricAffectingSpan() {
        override fun updateDrawState(tp: TextPaint) {
            tp.typeface = letter
        }

        override fun updateMeasureState(tp: TextPaint) {
            tp.typeface = letter
        }
    }
}
