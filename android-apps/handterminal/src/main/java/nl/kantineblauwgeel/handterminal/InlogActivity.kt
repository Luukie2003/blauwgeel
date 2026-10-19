package nl.kantineblauwgeel.handterminal

import android.animation.ObjectAnimator
import android.content.Intent
import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import nl.kantineblauwgeel.handterminal.databinding.InlogLaagBinding

/** Het startpunt van de app: inloggen met de persoonlijke 6-cijferige code (dezelfde als de tablet-code). Is er nog
 * een geldige sessie, dan meteen door naar het startscherm. Onderaan staat of er wifi is en of de website bereikbaar
 * is, nog voordat je je code intikt. Lang drukken op het clublogo opent de instellingen. */
class InlogActivity : BasisActivity() {

    override val vereistInlog = false

    private lateinit var b: InlogLaagBinding
    private val code = StringBuilder()
    private var bezigMetInloggen = false
    private var toestand: Verbinding.Toestand? = null
    private var websiteBereikbaar: Boolean? = null
    private var websiteCheckLoopt = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Sessie.isIngelogd(this)) {
            naarStart()
            return
        }
        b = InlogLaagBinding.inflate(layoutInflater)
        setContentView(b.root)
        Scanner.stelIn(this)

        listOf(
            b.toets0 to '0', b.toets1 to '1', b.toets2 to '2', b.toets3 to '3', b.toets4 to '4',
            b.toets5 to '5', b.toets6 to '6', b.toets7 to '7', b.toets8 to '8', b.toets9 to '9',
        ).forEach { (toets, c) ->
            toets.setOnClickListener {
                it.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY)
                cijfer(c)
            }
        }
        b.toetsWis.setOnClickListener { wisCode(); verbergMelding() }
        b.toetsTerug.setOnClickListener { haalCijferWeg() }
        b.toetsTerug.setOnLongClickListener { wisCode(); true }
        b.inlogLogo.setOnLongClickListener {
            startActivity(Intent(this, InstellingenActivity::class.java))
            true
        }
        b.inlogVersie.text = "v" + BuildConfig.VERSION_NAME
        werkStippenBij()
        intent.getStringExtra(EXTRA_MELDING)?.let { toonMelding(it, fout = false) }
        controleerWebsite()
    }

    private fun naarStart() {
        startActivity(Intent(this, StartActivity::class.java))
        finish()
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        // Een toestel met echte cijfertoetsen kan ook zo de code intikken.
        if (::b.isInitialized && event.action == KeyEvent.ACTION_DOWN) {
            when (event.keyCode) {
                in KeyEvent.KEYCODE_0..KeyEvent.KEYCODE_9 -> {
                    cijfer('0' + (event.keyCode - KeyEvent.KEYCODE_0)); return true
                }
                KeyEvent.KEYCODE_DEL -> {
                    haalCijferWeg(); return true
                }
            }
        }
        return super.dispatchKeyEvent(event)
    }

    override fun bijScan(code: String) = toonMelding(getString(R.string.scan_eerst_inloggen), fout = false)

    override fun verbindingGewijzigd(toestand: Verbinding.Toestand) {
        val was = this.toestand?.verbonden
        this.toestand = toestand
        if (!::b.isInitialized) return
        if (toestand.verbonden && was == false) controleerWebsite()
        werkVerbindingBij()
    }

    // ---------------------------------------------------------------- de code

    private fun cijfer(c: Char) {
        if (bezigMetInloggen || code.length >= 6) return
        code.append(c)
        verbergMelding()
        werkStippenBij()
        if (code.length == 6) controleerCode()
    }

    private fun haalCijferWeg() {
        if (bezigMetInloggen || code.isEmpty()) return
        code.deleteCharAt(code.length - 1)
        werkStippenBij()
    }

    private fun wisCode() {
        code.clear()
        werkStippenBij()
    }

    private fun werkStippenBij(fout: Boolean = false) {
        for (i in 0 until b.stippen.childCount) {
            b.stippen.getChildAt(i).setBackgroundResource(
                when {
                    fout -> R.drawable.stip_fout
                    i < code.length -> R.drawable.stip_vol
                    else -> R.drawable.stip_leeg
                },
            )
        }
    }

    private fun zetToetsen(aan: Boolean) {
        for (r in 0 until b.toetsen.childCount) {
            val rij = b.toetsen.getChildAt(r) as ViewGroup
            for (k in 0 until rij.childCount) rij.getChildAt(k).isEnabled = aan
        }
        b.toetsen.alpha = if (aan) 1f else 0.55f
    }

    private fun controleerCode() {
        val ingevoerd = code.toString()
        bezigMetInloggen = true
        zetToetsen(false)
        verbergMelding()
        b.inlogBezig.isVisible = true
        lifecycleScope.launch {
            val uitkomst = Api.inloggen(applicationContext, ingevoerd)
            bezigMetInloggen = false
            zetToetsen(true)
            b.inlogBezig.isVisible = false
            when (uitkomst) {
                is Api.Inlog.Gelukt -> {
                    Sessie.zet(this@InlogActivity, uitkomst.naam, uitkomst.csrfToken, uitkomst.cookies)
                    activiteit(direct = true)
                    naarStart()
                }
                is Api.Inlog.FouteCode -> codeFout(
                    uitkomst.pogingenOver?.takeIf { it in 1..2 }?.let { getString(R.string.code_fout_pogingen, it) }
                        ?: getString(R.string.code_fout),
                )
                is Api.Inlog.TeVeelPogingen -> codeFout(
                    uitkomst.minuten?.let { getString(R.string.code_te_veel_minuten, it) } ?: getString(R.string.code_te_veel),
                )
                Api.Inlog.Noodstop -> vergrendel()
                is Api.Inlog.Mislukt -> {
                    controleerWebsite()
                    codeFout(uitkomst.fout.message ?: getString(R.string.code_server), schudden = false)
                }
            }
        }
    }

    private fun codeFout(melding: String, schudden: Boolean = true) {
        toonMelding(melding, fout = true)
        if (schudden) {
            werkStippenBij(fout = true)
            ObjectAnimator.ofFloat(b.stippen, "translationX", 0f, 22f, -22f, 16f, -16f, 8f, -8f, 0f).setDuration(450).start()
            tril(120)
            lifecycleScope.launch {
                delay(500)
                wisCode()
            }
        } else {
            wisCode()
        }
    }

    private fun toonMelding(tekst: String, fout: Boolean) {
        b.inlogMelding.text = tekst
        b.inlogMelding.setBackgroundResource(if (fout) R.drawable.melding_fout else R.drawable.melding_info)
        b.inlogMelding.visibility = View.VISIBLE
    }

    private fun verbergMelding() {
        b.inlogMelding.visibility = View.INVISIBLE
    }

    // ---------------------------------------------------------------- verbinding onderaan

    private fun controleerWebsite() {
        if (websiteCheckLoopt) return
        websiteCheckLoopt = true
        lifecycleScope.launch {
            websiteBereikbaar = try {
                Api.meet(applicationContext)
                true
            } catch (e: Exception) {
                false
            }
            websiteCheckLoopt = false
            werkVerbindingBij()
        }
    }

    private fun werkVerbindingBij() {
        val t = toestand ?: return
        val netwerk = when (t.soort) {
            Verbinding.Soort.WIFI -> t.signaal?.let { getString(R.string.verbonden_wifi_signaal, signaalWoord(it)) }
                ?: getString(R.string.verbonden_wifi)
            Verbinding.Soort.MOBIEL -> getString(R.string.verbonden_mobiel)
            Verbinding.Soort.GEEN -> getString(R.string.geen_netwerk)
        }
        val site = websiteBereikbaar
        b.inlogVerbinding.text = when {
            !t.verbonden || site == null -> netwerk
            site -> getString(R.string.inlog_site_ok, netwerk)
            else -> getString(R.string.inlog_site_fout, netwerk)
        }
        kleurStip(
            b.inlogVerbindingStip,
            when {
                !t.verbonden -> R.color.rood
                site == false || (t.signaal ?: 3) <= 0 -> R.color.oranje
                else -> R.color.groen
            },
        )
    }

    companion object {
        const val EXTRA_MELDING = "melding"
    }
}
