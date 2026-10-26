package nl.kantineblauwgeel.handterminal

import android.os.Build
import android.os.Bundle
import android.view.MenuItem
import android.view.View
import android.webkit.WebSettings
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Spinner
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityInstellingenBinding

/** Instellingen van de app op dit toestel. Te openen via het menu, of op het inlogscherm door lang op het
 * clublogo te drukken. Het website-adres is alleen in een testversie aan te passen. */
class InstellingenActivity : AppCompatActivity() {

    private lateinit var b: ActivityInstellingenBinding
    private lateinit var inst: Instellingen

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityInstellingenBinding.inflate(layoutInflater)
        setContentView(b.root)
        inst = Instellingen(this)
        title = getString(R.string.instellingen)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        val uitlogLabels = Instellingen.UITLOG_KEUZES.map {
            when (it) {
                0 -> getString(R.string.nooit)
                60 -> getString(R.string.een_uur)
                else -> getString(R.string.minuten, it)
            }
        }
        keuzelijst(b.uitloggenKeuze, uitlogLabels, Instellingen.UITLOG_KEUZES.indexOf(inst.uitlogMinuten)) {
            inst.uitlogMinuten = Instellingen.UITLOG_KEUZES[it]
        }

        val zebra = Scanner.isAanwezig(this)
        b.scannerStatus.setText(if (zebra) R.string.inst_scanner_zebra else R.string.inst_scanner_geen)
        b.scannerOpnieuw.isVisible = zebra
        b.scannerOpnieuw.setOnClickListener {
            Scanner.stelIn(this)
            Toast.makeText(this, R.string.inst_scanner_klaar, Toast.LENGTH_SHORT).show()
        }
        b.trillenSchakelaar.isChecked = inst.trillen
        b.trillenSchakelaar.setOnCheckedChangeListener { _, aan -> inst.trillen = aan }
        b.herinneringSchakelaar.isChecked = inst.bestelHerinnering
        b.herinneringSchakelaar.setOnCheckedChangeListener { _, aan ->
            inst.bestelHerinnering = aan
            Herinneringen.planOpnieuw(this) // uit: de wekkers weg; aan: weer zetten
        }

        b.websiteAdres.setText(inst.basisUrl)
        b.websiteAdres.isEnabled = BuildConfig.DEBUG
        b.websiteStandaard.isVisible = BuildConfig.DEBUG
        b.websiteStandaard.setOnClickListener { b.websiteAdres.setText(Instellingen.STANDAARD_URL) }

        val webview = try {
            Regex("Chrome/([\\d.]+)").find(WebSettings.getDefaultUserAgent(this))?.groupValues?.get(1) ?: "?"
        } catch (e: Exception) {
            "?"
        }
        b.overTekst.text = getString(R.string.inst_over_tekst, BuildConfig.VERSION_NAME, Build.VERSION.RELEASE, webview)
    }

    override fun onPause() {
        super.onPause()
        if (!BuildConfig.DEBUG) return
        val adres = b.websiteAdres.text.toString().trim().trimEnd('/')
        if (adres == inst.basisUrl) return
        if (adres.startsWith("https://") || adres.startsWith("http://10.0.2.2")) {
            inst.basisUrl = adres // de sessie hoort bij het oude adres: Sessie.isIngelogd is dan false, dus opnieuw inloggen
        } else {
            Toast.makeText(this, R.string.inst_website_ongeldig, Toast.LENGTH_LONG).show()
        }
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) {
            finish()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    private fun keuzelijst(lijst: Spinner, labels: List<String>, gekozen: Int, bijKeuze: (Int) -> Unit) {
        lijst.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, labels).apply {
            setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        if (gekozen >= 0) lijst.setSelection(gekozen, false)
        lijst.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, positie: Int, id: Long) = bijKeuze(positie)
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
    }
}
