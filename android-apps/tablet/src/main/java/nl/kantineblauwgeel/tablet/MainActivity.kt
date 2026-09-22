package nl.kantineblauwgeel.tablet

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivityMainBinding
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Startscherm: vraagt de 6-cijferige tablet-code (zie tablet_code_instellen
 * op de website) en stuurt 'm ter controle naar /api/tablet-code/controleren.
 * Bij een geldige code ga je naar het schermkiezer (ScreenPickerActivity) --
 * verder is dit apparaat puur kiosk: geen gebruikersnaam, geen wachtwoord,
 * geen toegang tot de rest van de website. Lang indrukken op het logo opent
 * de (verborgen) instellingen, voor het wijzigen van het website-adres. */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val ingevoerdeCode = StringBuilder()
    private lateinit var stippen: List<TextView>
    private lateinit var cijferKnoppen: List<Pair<View, String>>

    private enum class ControleResultaat { GELDIG, ONGELDIG, TE_VEEL_POGINGEN, VERBINDINGSFOUT }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        stippen = listOf(
            binding.stip1, binding.stip2, binding.stip3,
            binding.stip4, binding.stip5, binding.stip6
        )
        cijferKnoppen = listOf(
            binding.cijfer0 to "0", binding.cijfer1 to "1", binding.cijfer2 to "2",
            binding.cijfer3 to "3", binding.cijfer4 to "4", binding.cijfer5 to "5",
            binding.cijfer6 to "6", binding.cijfer7 to "7", binding.cijfer8 to "8",
            binding.cijfer9 to "9"
        )
        cijferKnoppen.forEach { (knop, cijfer) -> knop.setOnClickListener { voegCijferToe(cijfer) } }
        binding.wisKnop.setOnClickListener { wisCode() }
        binding.backspaceKnop.setOnClickListener { verwijderLaatsteCijfer() }
        binding.logo.setOnLongClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
            true
        }

        werkStippenBij()
    }

    private fun voegCijferToe(cijfer: String) {
        if (ingevoerdeCode.length >= 6 || !binding.cijfer0.isEnabled) return
        ingevoerdeCode.append(cijfer)
        werkStippenBij()
        if (ingevoerdeCode.length == 6) controleerCode()
    }

    private fun verwijderLaatsteCijfer() {
        if (ingevoerdeCode.isNotEmpty()) {
            ingevoerdeCode.deleteCharAt(ingevoerdeCode.length - 1)
            werkStippenBij()
        }
        verbergFout()
    }

    private fun wisCode() {
        ingevoerdeCode.clear()
        werkStippenBij()
        verbergFout()
    }

    private fun werkStippenBij() {
        stippen.forEachIndexed { i, stip -> stip.text = if (i < ingevoerdeCode.length) "●" else "○" }
    }

    private fun verbergFout() {
        binding.foutmelding.visibility = View.GONE
    }

    private fun toonFout(bericht: String) {
        binding.foutmelding.text = bericht
        binding.foutmelding.visibility = View.VISIBLE
        wisCode()
    }

    private fun setInvoerIngeschakeld(ingeschakeld: Boolean) {
        cijferKnoppen.forEach { (knop, _) -> knop.isEnabled = ingeschakeld }
        binding.wisKnop.isEnabled = ingeschakeld
        binding.backspaceKnop.isEnabled = ingeschakeld
    }

    private fun controleerCode() {
        val code = ingevoerdeCode.toString()
        setInvoerIngeschakeld(false)
        binding.laadindicator.visibility = View.VISIBLE
        verbergFout()

        Thread {
            val resultaat = probeerControleren(code)
            runOnUiThread {
                binding.laadindicator.visibility = View.GONE
                setInvoerIngeschakeld(true)
                when (resultaat) {
                    ControleResultaat.GELDIG -> {
                        startActivity(Intent(this, ScreenPickerActivity::class.java))
                        wisCode()
                    }
                    ControleResultaat.ONGELDIG -> toonFout(getString(R.string.code_onjuist))
                    ControleResultaat.TE_VEEL_POGINGEN -> toonFout(getString(R.string.te_veel_pogingen))
                    ControleResultaat.VERBINDINGSFOUT -> toonFout(getString(R.string.geen_verbinding))
                }
            }
        }.start()
    }

    private fun probeerControleren(code: String): ControleResultaat {
        return try {
            val verbinding = URL(Prefs.getBaseUrl(this) + "/api/tablet-code/controleren")
                .openConnection() as HttpURLConnection
            verbinding.requestMethod = "POST"
            verbinding.doOutput = true
            verbinding.connectTimeout = 8000
            verbinding.readTimeout = 8000
            verbinding.setRequestProperty("Content-Type", "application/json")
            verbinding.outputStream.use {
                it.write(JSONObject().put("code", code).toString().toByteArray(Charsets.UTF_8))
            }
            val status = verbinding.responseCode
            val stream = if (status in 200..299) verbinding.inputStream else verbinding.errorStream
            val antwoord = JSONObject(stream.bufferedReader().use { it.readText() })
            when {
                status == 429 -> ControleResultaat.TE_VEEL_POGINGEN
                antwoord.optBoolean("geldig", false) -> ControleResultaat.GELDIG
                else -> ControleResultaat.ONGELDIG
            }
        } catch (e: IOException) {
            ControleResultaat.VERBINDINGSFOUT
        } catch (e: Exception) {
            ControleResultaat.VERBINDINGSFOUT
        }
    }
}
