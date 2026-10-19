package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.RectF
import android.view.View
import kotlin.math.roundToInt

/** "Verkocht per week" op de productpagina: een staaf per week met het aantal erboven en het weeknummer eronder,
 * zoals op de site. Een week die nog niet helemaal geteld is, is lichter met een stippelrand. */
class WeekGrafiek(context: Context) : View(context) {

    class Week(val nummer: Int, val aantal: Double, val nietAf: Boolean)

    var weken: List<Week> = emptyList()
        set(waarde) {
            field = waarde
            contentDescription = waarde.joinToString { "week ${it.nummer}: ${it.aantal.roundToInt()}" }
            invalidate()
        }

    private val dichtheid = resources.displayMetrics.density
    private val staaf = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = context.getColor(R.color.navy) }
    private val staafLicht = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = context.getColor(R.color.navy); alpha = 70 }
    private val stippel = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.getColor(R.color.navy)
        style = Paint.Style.STROKE
        strokeWidth = 1.2f * dichtheid
        pathEffect = DashPathEffect(floatArrayOf(3 * dichtheid, 2 * dichtheid), 0f)
    }
    private val waardeTekst = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.getColor(R.color.tekst)
        textSize = 10.5f * dichtheid
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
    }
    private val labelTekst = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = context.getColor(R.color.tekst_zacht)
        textSize = 10f * dichtheid
        textAlign = Paint.Align.CENTER
    }
    private val lijn = Paint().apply { color = context.getColor(R.color.rand_licht); strokeWidth = dichtheid }
    private val vak = RectF()

    override fun onMeasure(breedteSpec: Int, hoogteSpec: Int) {
        setMeasuredDimension(MeasureSpec.getSize(breedteSpec), (124 * dichtheid).roundToInt())
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (weken.isEmpty()) return
        val boven = 16 * dichtheid
        val onder = height - 16 * dichtheid
        val hoogste = weken.maxOf { it.aantal }.coerceAtLeast(1.0)
        val kolom = width.toFloat() / weken.size
        val breedte = (kolom * 0.62f).coerceAtMost(26 * dichtheid)
        canvas.drawLine(0f, onder, width.toFloat(), onder, lijn)
        weken.forEachIndexed { i, w ->
            val midden = kolom * i + kolom / 2
            val top = onder - ((onder - boven) * (w.aantal / hoogste)).toFloat()
            vak.set(midden - breedte / 2, top, midden + breedte / 2, onder)
            if (w.aantal > 0) {
                if (w.nietAf) {
                    canvas.drawRect(vak, staafLicht)
                    canvas.drawRect(vak, stippel)
                } else {
                    canvas.drawRect(vak, staaf)
                }
            }
            canvas.drawText(w.aantal.roundToInt().toString(), midden, top - 4 * dichtheid, waardeTekst)
            canvas.drawText(w.nummer.toString(), midden, height - 3 * dichtheid, labelTekst)
        }
    }
}
