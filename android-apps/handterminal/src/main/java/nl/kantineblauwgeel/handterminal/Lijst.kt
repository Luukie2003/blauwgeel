package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.AbsoluteSizeSpan
import android.text.style.ForegroundColorSpan
import android.text.style.RelativeSizeSpan
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.annotation.ColorInt
import androidx.annotation.ColorRes
import androidx.annotation.DrawableRes
import androidx.appcompat.content.res.AppCompatResources
import androidx.appcompat.widget.AppCompatTextView
import java.util.Locale

/** Bouwstenen voor de lijstschermen (prikbord, bestellijst, tellingen, kassa, keuken, agenda, ...) en de
 * productinformatie, in de clubstijl van de site: witte panelen met een kop in de sportletter, regels met een lichte
 * lijn ertussen, een stand als woord met een gekleurde stip, getallen in de smalle letter en kerncijfers als scorebord.
 * Compact voor het kleine scherm van de handterminal. */
object Lijst {

    private fun dp(context: Context, waarde: Int) = (waarde * context.resources.displayMetrics.density).toInt()

    /** Een kopje dat (nog) los staat; [kaart] haalt het het paneel in. */
    private const val LOSSE_KOP = "losse_kop"
    /** De kop binnen een paneel: daaronder geen extra lijn (die heeft de kop zelf al). */
    private const val PANEEL_KOP = "paneel_kop"

    /** Een kopje in de sportletter. Komt er meteen een paneel onder ([kaart], ook via [leeg] of [cijfers]), dan wordt
     * het de kop van dat paneel, zoals op de site; anders blijft het een kopje tussen de panelen in. */
    fun kop(ouder: LinearLayout, tekst: String) {
        val context = ouder.context
        ouder.addView(AppCompatTextView(context).apply {
            text = tekst
            textSize = 20f
            typeface = Letters.koppen(context)
            setTextColor(context.getColor(R.color.tekst))
            setPadding(dp(context, 2), dp(context, 14), 0, dp(context, 6))
            tag = LOSSE_KOP
        })
    }

    /** Een wit paneel. Staat er net een [kop] boven, dan gaat die erin. */
    fun kaart(ouder: LinearLayout, @DrawableRes achtergrond: Int = R.drawable.kaart): LinearLayout {
        val context = ouder.context
        val kaart = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(achtergrond)
            clipToOutline = true  // een ingedrukte regel blijft binnen de hoeken
        }
        val kop = (ouder.getChildAt(ouder.childCount - 1) as? TextView)?.takeIf { it.tag == LOSSE_KOP }
        if (kop != null) {
            ouder.removeView(kop)
            kaart.addView(paneelKop(context, kop.text, null))
        }
        ouder.addView(kaart, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = if (kop != null) kopRuimte(ouder) else 0
            bottomMargin = dp(context, 8)
        })
        return kaart
    }

    /** Boven een paneel met een kop: 12dp tot het paneel erboven (dat zelf 8dp onder zich heeft), of tot de bovenkant. */
    private fun kopRuimte(ouder: LinearLayout) = dp(ouder.context, if (ouder.childCount == 1) 12 else 4)

    /** Een paneel met een kop ("Onderdelen") en rechts daarvan eventueel iets kleins ("Tik om aan of uit te zetten"). */
    fun paneel(ouder: LinearLayout, titel: String, rechts: String? = null, @DrawableRes achtergrond: Int = R.drawable.kaart): LinearLayout {
        val kaart = kaart(ouder, achtergrond)
        kaart.addView(paneelKop(ouder.context, titel, rechts))
        (kaart.layoutParams as LinearLayout.LayoutParams).topMargin = kopRuimte(ouder)
        return kaart
    }

    /** De kop van een paneel: de titel in de sportletter, rechts iets kleins, een lichte lijn eronder. */
    fun paneelKop(context: Context, titel: CharSequence, rechts: String?): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setBackgroundResource(R.drawable.kop_lijn)
        setPadding(dp(context, 12), dp(context, 10), dp(context, 12), dp(context, 9))
        tag = PANEEL_KOP
        addView(AppCompatTextView(context).apply {
            text = titel
            textSize = 21f
            typeface = Letters.koppen(context)
            setTextColor(context.getColor(R.color.tekst))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        if (rechts != null) addView(AppCompatTextView(context).apply {
            text = rechts
            textSize = 13f
            typeface = Letters.medium(context)
            setTextColor(context.getColor(R.color.tekst_zacht))
            setPadding(dp(context, 8), 0, 0, 0)
        })
    }

    /** Een lichte lijn tussen twee regels, behalve direct onder de kop van het paneel. */
    private fun scheiding(kaart: LinearLayout) {
        if (kaart.childCount == 0 || kaart.getChildAt(kaart.childCount - 1).tag == PANEEL_KOP) return
        kaart.addView(View(kaart.context).apply { setBackgroundResource(R.drawable.scheiding) },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 1))
    }

    /** Een regel: titel, daaronder een (zachte) uitleg, rechts eventueel een getal of woord (in de smalle letter), links
     * eventueel een [icoon] (zoals het vinkje op de bestellijst). Aantikbaar met [klik]. Met [pil] is het woord rechts
     * een stand: een woord met een gekleurde stip ervoor (zoals "Aan" of "straks" bij de kantine-tv). */
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
        scheiding(kaart)
        val regel = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(context, 46)
            setPadding(dp(context, 12), dp(context, 9), dp(context, 12), dp(context, 9))
            if (klik != null) {
                setBackgroundResource(R.drawable.regel_klik_kaart)
                setOnClickListener { klik() }
            }
        }
        if (icoon != null) regel.addView(ImageView(context).apply {
            setImageResource(icoon)
            icoonKleur?.let { setColorFilter(context.getColor(it)) }
            contentDescription = null
        }, LinearLayout.LayoutParams(dp(context, 22), dp(context, 22)).apply { marginEnd = dp(context, 12) })
        val links = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        links.addView(AppCompatTextView(context).apply {
            text = titel
            textSize = 15f
            typeface = Letters.medium(context)
            setTextColor(context.getColor(R.color.tekst))
        })
        if (!detail.isNullOrEmpty()) links.addView(AppCompatTextView(context).apply {
            text = detail
            textSize = 13f
            setTextColor(context.getColor(R.color.tekst_zacht))
            setPadding(0, dp(context, 1), 0, 0)
        })
        regel.addView(links, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        if (rechts != null && pil) {
            regel.addView(stand(context, rechts, context.getColor(rechtsKleur)),
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                    marginStart = dp(context, 10)
                })
        } else if (rechts != null) regel.addView(AppCompatTextView(context).apply {
            text = rechts
            textSize = 18f
            setTypeface(Letters.koppen(context), Typeface.BOLD)
            setTextColor(context.getColor(rechtsKleur))
            setPadding(dp(context, 10), 0, 0, 0)
        })
        kaart.addView(regel)
        return regel
    }

    /** Een stand als woord met een gekleurde stip ervoor ("• Aan", "• 21 onder het minimum"), zoals .cs-punt op de site:
     * in plaats van een gekleurd labeltje. */
    fun stand(context: Context, tekst: CharSequence, @ColorInt kleur: Int): TextView = AppCompatTextView(context).apply {
        textSize = 14f
        setTypeface(Letters.tekst(context), Typeface.BOLD)
        isSingleLine = true
        zetStand(this, tekst, kleur)
    }

    /** Maak van [view] een stand: de tekst in [kleur] met een stip in dezelfde kleur ervoor (half-vet, of met [vet]
     * false medium, zoals onder het inlogscherm). */
    fun zetStand(view: TextView, tekst: CharSequence, @ColorInt kleur: Int, vet: Boolean = true) {
        view.text = tekst
        view.setTextColor(kleur)
        if (vet) view.setTypeface(Letters.tekst(view.context), Typeface.BOLD) else view.typeface = Letters.medium(view.context)
        val stip = AppCompatResources.getDrawable(view.context, R.drawable.stip)?.mutate()?.apply { setTint(kleur) }
        view.setCompoundDrawablesRelativeWithIntrinsicBounds(stip, null, null, null)
        view.compoundDrawablePadding = dp(view.context, 6)
    }

    /** Het omgekeerde van [zetStand]: gewone zachte tekst, zonder stip. */
    fun zetZacht(view: TextView, tekst: CharSequence) {
        view.text = tekst
        view.setTextColor(view.context.getColor(R.color.tekst_zacht))
        view.typeface = Letters.medium(view.context)
        view.setCompoundDrawablesRelative(null, null, null, null)
    }

    /** Een getal in de smalle letter met de eenheid erachter, kleiner en zacht ("46 blik"). [letter] null: de eenheid in
     * de letter van het getal; anders in die letter (zoals Barlow, half-vet). */
    fun getalMetEenheid(context: Context, getal: String, eenheid: String?, eenheidSp: Int, letter: Typeface? = null): CharSequence {
        val tekst = SpannableStringBuilder(getal)
        if (!eenheid.isNullOrEmpty()) {
            val begin = tekst.length
            tekst.append(" ").append(eenheid)
            tekst.setSpan(AbsoluteSizeSpan(eenheidSp, true), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            tekst.setSpan(ForegroundColorSpan(context.getColor(R.color.tekst_zacht)), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            if (letter != null) tekst.setSpan(Letters.Span(letter), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        return tekst
    }

    /** Een melding bovenaan een scherm, zoals "Nu groot op de tv's: Tussenstand Shout-out!": wit met een gele streep,
     * het [label] klein erboven, en rechts een knop (zoals Stop). */
    fun melding(ouder: LinearLayout, label: String?, tekst: String, knop: String, actie: () -> Unit) {
        val context = ouder.context
        val rij = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundResource(R.drawable.rand_links_oranje)
            setPadding(dp(context, 16), dp(context, 10), dp(context, 10), dp(context, 10))
        }
        val links = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        if (label != null) links.addView(AppCompatTextView(context).apply {
            text = label
            textSize = 13f
            typeface = Letters.medium(context)
            setTextColor(context.getColor(R.color.tekst_zacht))
        })
        links.addView(AppCompatTextView(context).apply {
            text = tekst
            textSize = 16f
            setTypeface(Letters.tekst(context), Typeface.BOLD)
            setTextColor(context.getColor(R.color.tekst))
        })
        rij.addView(links, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        rij.addView(AppCompatTextView(context).apply {
            text = knop
            textSize = 15f
            setTypeface(Letters.tekst(context), Typeface.BOLD)
            setTextColor(context.getColor(R.color.rood))
            gravity = Gravity.CENTER
            setPadding(dp(context, 16), 0, dp(context, 16), 0)
            setBackgroundResource(R.drawable.knop_stop)
            setOnClickListener { actie() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, dp(context, 38)).apply { marginStart = dp(context, 10) })
        ouder.addView(rij, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(context, 12)
            bottomMargin = dp(context, 4)
        })
    }

    /** Een rij snelknoppen (icoon en tekst) die opzij scrolt als ze niet op het scherm passen. */
    fun snelknoppen(ouder: LinearLayout, knoppen: List<Triple<String, Int, () -> Unit>>) {
        val context = ouder.context
        val rij = LinearLayout(context).apply { orientation = LinearLayout.HORIZONTAL }
        for ((tekst, icoon, actie) in knoppen) {
            rij.addView(AppCompatTextView(context).apply {
                text = tekst
                textSize = 14f
                setTextColor(context.getColor(R.color.blauw_donker))
                setTypeface(Letters.tekst(context), Typeface.BOLD)
                gravity = Gravity.CENTER_VERTICAL
                compoundDrawablePadding = dp(context, 7)
                setCompoundDrawablesRelative(AppCompatResources.getDrawable(context, icoon)?.mutate()?.apply {
                    setTint(context.getColor(R.color.blauw))
                    setBounds(0, 0, dp(context, 19), dp(context, 19))
                }, null, null, null)
                setPadding(dp(context, 11), dp(context, 9), dp(context, 13), dp(context, 9))
                setBackgroundResource(R.drawable.knop_rand)
                setOnClickListener { actie() }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                marginEnd = dp(context, 8)
            })
        }
        ouder.addView(HorizontalScrollView(context).apply {
            isHorizontalScrollBarEnabled = false
            setPadding(0, dp(context, 12), 0, dp(context, 2))
            clipToPadding = false
            addView(rij)
        })
    }

    /** Een tegel voor [tegels]: een vlak met de titel in [kleur] op de achtergrond van een dia op de tv, een geel [label]
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
        // Eén kleur, geen verloop: de achtergrond van een dia op de tv (kiosk_scherm_stijl.css).
        val vlak = FrameLayout(context).apply {
            setBackgroundColor(0xFF1D0B33.toInt())
            alpha = if (t.aan) 1f else 0.45f
        }
        vlak.addView(AppCompatTextView(context).apply {
            text = t.titel
            textSize = 17f
            maxLines = 2
            ellipsize = android.text.TextUtils.TruncateAt.END
            gravity = Gravity.CENTER
            setTextColor(t.kleur)
            setTypeface(Letters.koppen(context), Typeface.BOLD)
            setPadding(dp(context, 8), dp(context, 14), dp(context, 8), dp(context, 8))
        }, FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT))
        if (t.label != null) vlak.addView(AppCompatTextView(context).apply {
            text = t.label
            textSize = 13f
            setTypeface(Letters.koppen(context), Typeface.BOLD)
            setTextColor(context.getColor(R.color.blauw_donker))
            setPadding(dp(context, 6), dp(context, 1), dp(context, 6), dp(context, 1))
            background = GradientDrawable().apply {
                cornerRadius = dp(context, 3).toFloat()
                setColor(context.getColor(R.color.geel))
            }
        }, FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT).apply {
            leftMargin = dp(context, 6)
            topMargin = dp(context, 6)
        })
        tegel.addView(vlak, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(context, 78)))
        tegel.addView(AppCompatTextView(context).apply {
            text = t.titel
            textSize = 14f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            typeface = Letters.medium(context)
            setTextColor(context.getColor(R.color.tekst))
            setPadding(dp(context, 10), dp(context, 8), dp(context, 10), 0)
        })
        val onder = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(context, 10), dp(context, 2), dp(context, 10), dp(context, 9))
        }
        onder.addView(AppCompatTextView(context).apply {
            text = t.sub ?: ""
            textSize = 12f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setTextColor(context.getColor(R.color.tekst_zacht))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        onder.addView(stand(context, context.getString(if (t.aan) R.string.aan else R.string.uit),
            context.getColor(if (t.aan) R.color.groen else R.color.grijs)).apply { textSize = 13f })
        tegel.addView(onder)
        return tegel
    }

    /** Witruimte bovenaan een scherm dat niet met een kop begint. */
    fun ruimte(ouder: LinearLayout, hoogte: Int = 10) {
        ouder.addView(View(ouder.context), LinearLayout.LayoutParams(1, dp(ouder.context, hoogte)))
    }

    /** Een paneel met uitleg, als er niets te tonen is. */
    fun leeg(ouder: LinearLayout, tekst: String) {
        val context = ouder.context
        kaart(ouder).addView(AppCompatTextView(context).apply {
            text = tekst
            textSize = 14f
            setTextColor(context.getColor(R.color.tekst_zacht))
            setPadding(dp(context, 12), dp(context, 12), dp(context, 12), dp(context, 12))
        })
    }

    /** Een regel "label  waarde" in een paneel, zoals de lijstjes Prijzen en Inkoop op de productpagina van de site.
     * [zacht] komt er kleiner en zacht achter. */
    fun info(kaart: LinearLayout, label: String, waarde: String, zacht: String? = null, @ColorRes kleur: Int = R.color.tekst) {
        val context = kaart.context
        val regel = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(context, 12), dp(context, 6), dp(context, 12), dp(context, 6))
        }
        regel.addView(AppCompatTextView(context).apply {
            text = label
            textSize = 13f
            typeface = Letters.medium(context)
            setTextColor(context.getColor(R.color.tekst_zacht))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.38f))
        val tekst = SpannableStringBuilder(waarde)
        if (!zacht.isNullOrEmpty()) {
            val begin = tekst.length
            tekst.append("  ").append(zacht)
            tekst.setSpan(ForegroundColorSpan(context.getColor(R.color.tekst_zacht)), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            tekst.setSpan(RelativeSizeSpan(0.86f), begin, tekst.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        regel.addView(AppCompatTextView(context).apply {
            text = tekst
            textSize = 14f
            setTextColor(context.getColor(kleur))
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 0.62f))
        kaart.addView(regel)
    }

    /** Losse tekst in een paneel (uitleg, een opmerking). */
    fun tekst(
        kaart: LinearLayout,
        tekst: CharSequence,
        grootte: Float = 13f,
        @ColorRes kleur: Int = R.color.tekst_zacht,
        vet: Boolean = false,
    ): TextView {
        val context = kaart.context
        val view = AppCompatTextView(context).apply {
            text = tekst
            textSize = grootte
            setTextColor(context.getColor(kleur))
            if (vet) setTypeface(Letters.tekst(context), Typeface.BOLD)
            setPadding(dp(context, 12), dp(context, 7), dp(context, 12), dp(context, 7))
        }
        kaart.addView(view)
        return view
    }

    /** Een kopje binnen een paneel (zoals "Gepland" onder Prijzen). */
    fun subkop(kaart: LinearLayout, tekst: String) {
        val context = kaart.context
        kaart.addView(AppCompatTextView(context).apply {
            text = tekst
            textSize = 17f
            typeface = Letters.koppen(context)
            setTextColor(context.getColor(R.color.tekst))
            setPadding(dp(context, 12), dp(context, 10), dp(context, 12), dp(context, 2))
        })
    }

    /** Een knop als regel onderaan een paneel (blauw, als een link op de site), bijvoorbeeld "Op de bestellijst". */
    fun knop(kaart: LinearLayout, tekst: String, actie: () -> Unit): TextView {
        val context = kaart.context
        scheiding(kaart)
        val knop = AppCompatTextView(context).apply {
            text = tekst
            textSize = 15f
            setTextColor(context.getColor(R.color.blauw))
            setTypeface(Letters.tekst(context), Typeface.BOLD)
            gravity = Gravity.CENTER_VERTICAL
            minHeight = dp(context, 46)
            setPadding(dp(context, 12), dp(context, 8), dp(context, 12), dp(context, 8))
            setBackgroundResource(R.drawable.regel_klik_kaart)
            setOnClickListener { actie() }
        }
        kaart.addView(knop)
        return knop
    }

    /** Een kerncijfer: een groot getal met eronder wat het is (zoals het scorebord bovenaan de productpagina). */
    class Cijfer(val getal: String, val label: String, val eenheid: String? = null, val waarschuwing: Boolean = false)

    /** Kerncijfers als scorebord, zoals op de site: één paneel met vakken, twee naast elkaar (een oneven laatste over de
     * hele breedte), met lichte lijnen ertussen. Een getal met [Cijfer.waarschuwing] is rood. */
    fun cijfers(ouder: LinearLayout, cijfers: List<Cijfer>) {
        val context = ouder.context
        val bord = kaart(ouder)
        cijfers.chunked(2).forEach { paar ->
            scheiding(bord)
            val rij = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                dividerDrawable = context.getDrawable(R.drawable.scheiding_staand)
                showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
            }
            for (c in paar) {
                val vak = LinearLayout(context).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(context, 12), dp(context, 9), dp(context, 10), dp(context, 10))
                }
                vak.addView(AppCompatTextView(context).apply {
                    text = getalMetEenheid(context, c.getal, c.eenheid, 15)
                    textSize = 26f
                    setTypeface(Letters.koppen(context), Typeface.BOLD)
                    includeFontPadding = false
                    setTextColor(context.getColor(if (c.waarschuwing) R.color.rood else R.color.tekst))
                })
                vak.addView(AppCompatTextView(context).apply {
                    text = c.label
                    textSize = 12.5f
                    typeface = Letters.medium(context)
                    setTextColor(context.getColor(R.color.tekst_zacht))
                    setPadding(0, dp(context, 3), 0, 0)
                })
                rij.addView(vak, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            }
            bord.addView(rij)
        }
    }

    /** Een rij keuzeknoppen (bijvoorbeeld 7 of 14 dagen); [gekozen] is aangetikt. */
    fun keuzes(ouder: LinearLayout, opties: List<Pair<String, () -> Unit>>, gekozen: Int) {
        val context = ouder.context
        val rij = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(context, 12), 0, 0)
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
        kotlin.math.abs(bedrag) < 0.005 -> context.getString(R.string.klopt) to R.color.groen
        bedrag > 0 -> "+ ${euro(bedrag)}" to R.color.oranje
        else -> "− ${euro(-bedrag)}" to R.color.rood
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
