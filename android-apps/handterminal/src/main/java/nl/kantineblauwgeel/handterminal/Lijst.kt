package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.view.LayoutInflater
import android.view.View
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.annotation.ColorRes
import androidx.annotation.DrawableRes
import java.util.Locale

/** Bouwstenen voor de lijstschermen (prikbord, bestellijst, tellingen, kassa, keuken, agenda, ...) en de
 * productinformatie: een kop, een witte kaart met regels, inforegels en knoppen, en kerncijfers. Compact voor het
 * kleine scherm van de handterminal, in de stijl van de handterminal-weergave van de site. */
object Lijst {

    private fun dp(context: Context, waarde: Int) = (waarde * context.resources.displayMetrics.density).toInt()

    fun kop(ouder: LinearLayout, tekst: String) {
        val context = ouder.context
        ouder.addView(TextView(context).apply {
            text = tekst
            textSize = 12f
            isAllCaps = true
            letterSpacing = 0.06f
            setTextColor(context.getColor(R.color.tekst_zacht))
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setPadding(dp(context, 4), dp(context, 14), 0, dp(context, 6))
        })
    }

    fun kaart(ouder: LinearLayout, @DrawableRes achtergrond: Int = R.drawable.kaart): LinearLayout {
        val kaart = LinearLayout(ouder.context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(achtergrond)
            clipToOutline = true  // een ingedrukte regel blijft binnen de ronde hoeken
        }
        ouder.addView(kaart, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = dp(ouder.context, 6)
        })
        return kaart
    }

    /** Een regel: titel, daaronder een (grijze) uitleg, rechts eventueel een getal of woord, links eventueel een
     * [icoon] (zoals het vinkje op de bestellijst). Aantikbaar met [klik]. Met [pil] staat het woord rechts in een
     * gekleurd labeltje (zoals "Aan" of "straks" bij de kantine-tv, 2.21.0). */
    fun regel(
        kaart: LinearLayout,
        titel: String,
        detail: String? = null,
        rechts: String? = null,
        @ColorRes rechtsKleur: Int = R.color.tekst,
        @DrawableRes icoon: Int? = null,
        @ColorRes icoonKleur: Int? = null,
        pil: Boolean = false,
        klik: (() -> Unit)? = null,
    ): LinearLayout {
        val context = kaart.context
        if (kaart.childCount > 0) {
            kaart.addView(View(context).apply { setBackgroundResource(R.drawable.scheiding) },
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1))
        }
        val regel = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            minimumHeight = dp(context, 48)
            setPadding(dp(context, 12), dp(context, 7), dp(context, 12), dp(context, 7))
            if (klik != null) {
                setBackgroundResource(R.drawable.regel_klik_kaart)
                setOnClickListener { klik() }
            }
        }
        if (icoon != null) regel.addView(ImageView(context).apply {
            setImageResource(icoon)
            icoonKleur?.let { setColorFilter(context.getColor(it)) }
            contentDescription = null
        }, LinearLayout.LayoutParams(dp(context, 24), dp(context, 24)).apply { marginEnd = dp(context, 12) })
        val links = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        links.addView(TextView(context).apply {
            text = titel
            textSize = 15f
            setTextColor(context.getColor(R.color.tekst))
            setTypeface(typeface, Typeface.BOLD)
        })
        if (!detail.isNullOrEmpty()) links.addView(TextView(context).apply {
            text = detail
            textSize = 12f
            setTextColor(context.getColor(R.color.tekst_zacht))
        })
        regel.addView(links, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        if (rechts != null && pil) {
            regel.addView(pil(context, rechts, context.getColor(rechtsKleur)),
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                    marginStart = dp(context, 8)
                })
        } else if (rechts != null) regel.addView(TextView(context).apply {
            text = rechts
            textSize = 15f
            setTextColor(context.getColor(rechtsKleur))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 8), 0, 0, 0)
        })
        kaart.addView(regel)
        return regel
    }

    /** Een rond labeltje: de tekst in [kleur] op een lichte tint van die kleur (of, met [vol], wit op de kleur). */
    fun pil(context: Context, tekst: String, kleur: Int, vol: Boolean = false): TextView = TextView(context).apply {
        text = tekst
        textSize = 12.5f
        setTypeface(typeface, Typeface.BOLD)
        setTextColor(if (vol) context.getColor(R.color.tekst) else kleur)
        setPadding(dp(context, 10), dp(context, 3), dp(context, 10), dp(context, 3))
        background = GradientDrawable().apply {
            cornerRadius = dp(context, 99).toFloat()
            setColor(if (vol) kleur else (kleur and 0x00FFFFFF) or (0x24 shl 24))
        }
    }

    /** Een gele balk bovenaan een scherm (zoals "Nu groot op de tv's: Heksenbrouwsel"), met rechts een knop. */
    fun balk(ouder: LinearLayout, tekst: String, knop: String, actie: () -> Unit) {
        val context = ouder.context
        val rij = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(dp(context, 14), dp(context, 10), dp(context, 8), dp(context, 10))
            background = GradientDrawable().apply {
                cornerRadius = dp(context, 14).toFloat()
                setColor(context.getColor(R.color.geel))
            }
        }
        rij.addView(TextView(context).apply {
            text = tekst
            textSize = 14.5f
            setTextColor(context.getColor(R.color.navy_donker))
            setTypeface(typeface, Typeface.BOLD)
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        rij.addView(TextView(context).apply {
            text = knop
            textSize = 14f
            setTextColor(context.getColor(R.color.wit))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 14), dp(context, 7), dp(context, 14), dp(context, 7))
            background = GradientDrawable().apply {
                cornerRadius = dp(context, 99).toFloat()
                setColor(context.getColor(R.color.rood_balk))
            }
            setOnClickListener { actie() }
        })
        ouder.addView(rij, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(context, 10)
            bottomMargin = dp(context, 4)
        })
    }

    /** Een rij snelknoppen (icoon en tekst in een rond vlak) die opzij scrolt als ze niet op het scherm passen. */
    fun snelknoppen(ouder: LinearLayout, knoppen: List<Triple<String, Int, () -> Unit>>) {
        val context = ouder.context
        val rij = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
        for ((tekst, icoon, actie) in knoppen) {
            rij.addView(TextView(context).apply {
                text = tekst
                textSize = 13.5f
                setTextColor(context.getColor(R.color.navy))
                setTypeface(typeface, Typeface.BOLD)
                gravity = android.view.Gravity.CENTER_VERTICAL
                compoundDrawablePadding = dp(context, 6)
                setCompoundDrawablesRelative(context.getDrawable(icoon)?.mutate()?.apply {
                    setTint(context.getColor(R.color.navy))
                    setBounds(0, 0, dp(context, 18), dp(context, 18))
                }, null, null, null)
                setPadding(dp(context, 12), dp(context, 8), dp(context, 14), dp(context, 8))
                background = GradientDrawable().apply {
                    cornerRadius = dp(context, 99).toFloat()
                    setColor(context.getColor(R.color.kaart))
                    setStroke(dp(context, 1), context.getColor(R.color.rand_licht))
                }
                setOnClickListener { actie() }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                marginEnd = dp(context, 8)
            })
        }
        ouder.addView(HorizontalScrollView(context).apply {
            isHorizontalScrollBarEnabled = false
            setPadding(0, dp(context, 10), 0, dp(context, 2))
            clipToPadding = false
            addView(rij)
        })
    }

    /** Een tegel voor [tegels]: een vlak met de titel in [kleur] (zoals bij de dia's op de site), een geel [label]
     * linksboven (bijvoorbeeld 17:00), daaronder de titel, een regel uitleg en of hij aan of uit staat. */
    class Tegel(val titel: String, val sub: String?, val kleur: Int, val label: String?, val aan: Boolean, val klik: () -> Unit)

    /** Tegels, twee naast elkaar. */
    fun tegels(ouder: LinearLayout, tegels: List<Tegel>) {
        val context = ouder.context
        tegels.chunked(2).forEach { paar ->
            val rij = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
            paar.forEachIndexed { i, t ->
                rij.addView(tegel(context, t), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                    if (i == 0) marginEnd = dp(context, 4) else marginStart = dp(context, 4)
                })
            }
            if (paar.size == 1) {
                rij.addView(View(context), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply { marginStart = dp(context, 4) })
            }
            ouder.addView(rij, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(context, 8)
            })
        }
    }

    private fun tegel(context: Context, t: Tegel): View {
        val tegel = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.kaart)
            clipToOutline = true
            isClickable = true
            foreground = context.getDrawable(R.drawable.regel_klik_kaart)
            setOnClickListener { t.klik() }
            contentDescription = t.titel
        }
        val vlak = FrameLayout(context).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(0xFF3A1352.toInt(), 0xFF0B0412.toInt()))
            alpha = if (t.aan) 1f else 0.45f
        }
        vlak.addView(TextView(context).apply {
            text = t.titel
            textSize = 15f
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
            gravity = android.view.Gravity.CENTER
            setTextColor(t.kleur)
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 8), dp(context, 14), dp(context, 8), dp(context, 8))
        }, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        if (t.label != null) vlak.addView(pil(context, t.label, context.getColor(R.color.geel), vol = true),
            FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT).apply {
                leftMargin = dp(context, 6)
                topMargin = dp(context, 6)
            })
        tegel.addView(vlak, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(context, 78)))
        tegel.addView(TextView(context).apply {
            text = t.titel
            textSize = 13.5f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setTextColor(context.getColor(R.color.tekst))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 10), dp(context, 8), dp(context, 10), 0)
        })
        val onder = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setPadding(dp(context, 10), dp(context, 2), dp(context, 8), dp(context, 9))
        }
        onder.addView(TextView(context).apply {
            text = t.sub ?: ""
            textSize = 11.5f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setTextColor(context.getColor(R.color.tekst_zacht))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        onder.addView(pil(context, context.getString(if (t.aan) R.string.aan else R.string.uit),
            context.getColor(if (t.aan) R.color.groen_tekst else R.color.tekst_zacht)))
        tegel.addView(onder)
        return tegel
    }

    /** Witruimte bovenaan een scherm dat niet met een kop begint. */
    fun ruimte(ouder: LinearLayout, hoogte: Int = 10) {
        ouder.addView(View(ouder.context), LinearLayout.LayoutParams(1, dp(ouder.context, hoogte)))
    }

    /** Een lege kaart met uitleg, als er niets te tonen is. */
    fun leeg(ouder: LinearLayout, tekst: String) {
        val context = ouder.context
        kaart(ouder).addView(TextView(context).apply {
            text = tekst
            textSize = 14f
            setTextColor(context.getColor(R.color.tekst_zacht))
            setPadding(dp(context, 12), dp(context, 12), dp(context, 12), dp(context, 12))
        })
    }

    /** Een regel "label  waarde" in een infokaart, zoals de lijstjes Prijzen en Inkoop op de productpagina van de
     * site. [zacht] komt er kleiner en grijs achter. */
    fun info(kaart: LinearLayout, label: String, waarde: String, zacht: String? = null, @ColorRes kleur: Int = R.color.tekst) {
        val context = kaart.context
        val regel = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(context, 12), dp(context, 5), dp(context, 12), dp(context, 5))
        }
        regel.addView(TextView(context).apply {
            text = label
            textSize = 13f
            setTextColor(context.getColor(R.color.tekst_zacht))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.38f))
        val tekst = SpannableStringBuilder(waarde)
        if (!zacht.isNullOrEmpty()) {
            val begin = tekst.length
            tekst.append("  ").append(zacht)
            tekst.setSpan(ForegroundColorSpan(context.getColor(R.color.tekst_zacht)), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            tekst.setSpan(RelativeSizeSpan(0.86f), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        regel.addView(TextView(context).apply {
            text = tekst
            textSize = 14f
            setTextColor(context.getColor(kleur))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.62f))
        kaart.addView(regel)
    }

    /** Losse tekst in een kaart (uitleg, een opmerking). */
    fun tekst(
        kaart: LinearLayout,
        tekst: CharSequence,
        grootte: Float = 13f,
        @ColorRes kleur: Int = R.color.tekst_zacht,
        vet: Boolean = false,
    ): TextView {
        val context = kaart.context
        val view = TextView(context).apply {
            text = tekst
            textSize = grootte
            setTextColor(context.getColor(kleur))
            if (vet) setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 12), dp(context, 6), dp(context, 12), dp(context, 6))
        }
        kaart.addView(view)
        return view
    }

    /** Een kopje binnen een kaart (zoals "Gepland" onder Prijzen). */
    fun subkop(kaart: LinearLayout, tekst: String) {
        val context = kaart.context
        kaart.addView(TextView(context).apply {
            text = tekst
            textSize = 12f
            setTextColor(context.getColor(R.color.tekst))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 2))
        })
    }

    /** Een knop als regel onderaan een kaart (navy, vet), bijvoorbeeld "Op de bestellijst". */
    fun knop(kaart: LinearLayout, tekst: String, actie: () -> Unit): TextView {
        val context = kaart.context
        if (kaart.childCount > 0) {
            kaart.addView(View(context).apply { setBackgroundResource(R.drawable.scheiding) },
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1))
        }
        val knop = TextView(context).apply {
            text = tekst
            textSize = 15f
            setTextColor(context.getColor(R.color.navy))
            setTypeface(typeface, Typeface.BOLD)
            gravity = android.view.Gravity.CENTER_VERTICAL
            minHeight = dp(context, 46)
            setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
            setBackgroundResource(R.drawable.regel_klik_kaart)
            setOnClickListener { actie() }
        }
        kaart.addView(knop)
        return knop
    }

    /** Een kerncijfer: een groot getal met eronder wat het is (zoals de blokjes bovenaan de productpagina). */
    class Cijfer(val getal: String, val label: String, val eenheid: String? = null, val waarschuwing: Boolean = false)

    /** Kerncijfers, twee naast elkaar. */
    fun cijfers(ouder: LinearLayout, cijfers: List<Cijfer>) {
        val context = ouder.context
        cijfers.chunked(2).forEach { paar ->
            val rij = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
            paar.forEachIndexed { i, c ->
                val blok = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    setBackgroundResource(if (c.waarschuwing) R.drawable.rand_links_rood else R.drawable.kaart)
                    setPadding(dp(context, 12), dp(context, 8), dp(context, 10), dp(context, 8))
                }
                val getal = SpannableStringBuilder(c.getal)
                if (!c.eenheid.isNullOrEmpty()) {
                    val begin = getal.length
                    getal.append(" ").append(c.eenheid)
                    getal.setSpan(RelativeSizeSpan(0.6f), begin, getal.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                }
                blok.addView(TextView(context).apply {
                    text = getal
                    textSize = 19f
                    setTextColor(context.getColor(if (c.waarschuwing) R.color.rood_balk else R.color.tekst))
                    setTypeface(typeface, Typeface.BOLD)
                })
                blok.addView(TextView(context).apply {
                    text = c.label
                    textSize = 11.5f
                    setTextColor(context.getColor(R.color.tekst_zacht))
                })
                rij.addView(blok, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply {
                    if (i == 0) marginEnd = dp(context, 3) else marginStart = dp(context, 3)
                })
            }
            // De lege plek ook MATCH_PARENT: anders telt een LinearLayout de hoogte van het blok niet mee en klapt het in.
            if (paar.size == 1) {
                rij.addView(View(context), LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f).apply { marginStart = dp(context, 3) })
            }
            ouder.addView(rij, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                bottomMargin = dp(context, 6)
            })
        }
    }

    /** Een rij keuzechips (bijvoorbeeld 7 of 14 dagen); [gekozen] is aangetikt. */
    fun keuzes(ouder: LinearLayout, opties: List<Pair<String, () -> Unit>>, gekozen: Int) {
        val context = ouder.context
        val rij = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(context, 10), 0, 0)
        }
        opties.forEachIndexed { i, (tekst, actie) ->
            val chip = LayoutInflater.from(context).inflate(R.layout.keuze, rij, false) as TextView
            chip.text = tekst
            chip.isSelected = i == gekozen
            chip.setOnClickListener { actie() }
            rij.addView(chip)
        }
        ouder.addView(rij)
    }

    /** Het verschil van een kassa- of kluistelling: "klopt", "+ € 2,50" (te veel) of "− € 2,50" (te weinig). */
    fun verschil(context: Context, bedrag: Double): Pair<String, Int> = when {
        kotlin.math.abs(bedrag) < 0.005 -> context.getString(R.string.klopt) to R.color.groen_tekst
        bedrag > 0 -> "+ ${euro(bedrag)}" to R.color.oranje_balk
        else -> "− ${euro(-bedrag)}" to R.color.rood_balk
    }

    private val nl = Locale("nl", "NL")

    /** € 1.234,50 */
    fun euro(bedrag: Double): String = "€ " + String.format(nl, "%,.2f", bedrag)

    /** 2,5 of 3 (geen ",0"). */
    fun getal(waarde: Double, decimalen: Int = 1): String {
        val tekst = String.format(nl, "%.${decimalen}f", waarde)
        return if (decimalen > 0) tekst.trimEnd('0').trimEnd(',') else tekst
    }

    /** "2026-10-18 14:02" → "18-10 14:02" (of alleen de dag). */
    fun datum(tekst: String?, metTijd: Boolean = true): String {
        if (tekst == null || tekst.length < 10) return tekst ?: ""
        val dag = "${tekst.substring(8, 10)}-${tekst.substring(5, 7)}"
        return if (metTijd && tekst.length >= 16) "$dag ${tekst.substring(11, 16)}" else dag
    }
}
