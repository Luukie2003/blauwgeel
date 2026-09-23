package nl.kantineblauwgeel.tablet

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import nl.kantineblauwgeel.tablet.databinding.ActivityWedstrijddagBinding

/** Native scherm voor de wedstrijddag-welkomstmelding (zie
 * kiosk_wedstrijddag_welkom_instellingen in routes/kiosk.py) -- alleen aan/
 * uit + de tekst ({tegenstander} wordt op het prijzenscherm vervangen door
 * de naam van de tegenstander). Toont zelf geen balk meer op het
 * prijzenscherm (die is verwijderd) -- staat 'm aan, dan verschijnt de
 * melding daar af en toe schermvullend, alleen binnen het tijdvak van een
 * eigen thuiswedstrijd vandaag. */
class WedstrijddagActivity : AppCompatActivity() {

    private lateinit var binding: ActivityWedstrijddagBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityWedstrijddagBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.terugKnop.setOnClickListener { finish() }
        binding.foutmelding.setOnClickListener { laadGegevens() }
        binding.opslaanKnop.setOnClickListener { slaOp() }
        binding.testKnop.setOnClickListener { testen() }
        laadGegevens()
    }

    private fun laadGegevens() {
        binding.laadindicator.visibility = View.VISIBLE
        binding.foutmelding.visibility = View.GONE
        binding.inhoud.visibility = View.GONE

        Thread {
            try {
                val antwoord = Api.get(this, "/api/tablet/wedstrijddag-welkom")
                val actief = antwoord.getBoolean("actief")
                val tekst = antwoord.optString("tekst")
                runOnUiThread {
                    binding.actiefSchakelaar.isChecked = actief
                    binding.tekstVeld.setText(tekst)
                    binding.laadindicator.visibility = View.GONE
                    binding.inhoud.visibility = View.VISIBLE
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.laadindicator.visibility = View.GONE
                    binding.foutmelding.visibility = View.VISIBLE
                }
            }
        }.start()
    }

    private fun slaOp() {
        val actief = binding.actiefSchakelaar.isChecked
        val tekst = binding.tekstVeld.text.toString().trim()
        val velden = mutableMapOf("wedstrijddag_welkom_tekst" to tekst)
        if (actief) velden["wedstrijddag_welkom_actief"] = "on"

        Thread {
            try {
                val antwoord = Api.postForm(this, "/kiosk/prijzen/wedstrijddag-welkom", velden)
                if (antwoord.optBoolean("ok", false)) {
                    runOnUiThread { Toast.makeText(this, R.string.instellingen_opgeslagen, Toast.LENGTH_SHORT).show() }
                } else {
                    runOnUiThread {
                        Toast.makeText(this, antwoord.optString("fout", getString(R.string.fout_opslaan)), Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }

    /** Dwingt de melding 1x schermvullend af op het (al open staande)
     * prijzenscherm, los van of er nu echt een thuiswedstrijd is -- zie
     * kiosk_wedstrijddag_welkom_testen in routes/kiosk.py. */
    private fun testen() {
        Thread {
            try {
                val antwoord = Api.postForm(this, "/kiosk/prijzen/wedstrijddag-welkom/test", emptyMap())
                if (antwoord.optBoolean("ok", false)) {
                    runOnUiThread { Toast.makeText(this, R.string.wedstrijddag_test_verstuurd, Toast.LENGTH_SHORT).show() }
                } else {
                    runOnUiThread {
                        Toast.makeText(this, antwoord.optString("fout", getString(R.string.fout_opslaan)), Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }
}
