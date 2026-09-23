package nl.kantineblauwgeel.tablet

import android.app.AlertDialog
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import nl.kantineblauwgeel.tablet.databinding.ActivityBardienstenBinding
import java.util.Calendar

private data class Bardienst(
    val id: Int,
    var datum: String,
    var startTijd: String,
    var eindTijd: String,
    var namen: String,
)

private fun isoNaarWeergave(iso: String): String {
    val delen = iso.split("-")
    return if (delen.size == 3) "${delen[2]}-${delen[1]}-${delen[0]}" else iso
}

/** Native lijst van bardiensten (zie kiosk_bardiensten in routes/kiosk.py)
 * -- aanmaken/bewerken kiest datum en tijden via de systeem-eigen date-/
 * time-pickers, geen los formulierscherm nodig. Tikken op een rij opent de
 * bewerk-dialoog, ✕ verwijdert direct na bevestiging. */
class BardienstenActivity : AppCompatActivity() {

    private lateinit var binding: ActivityBardienstenBinding
    private val bardiensten = mutableListOf<Bardienst>()
    private lateinit var adapter: BardienstenAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityBardienstenBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.terugKnop.setOnClickListener { finish() }
        adapter = BardienstenAdapter(bardiensten, ::toonDialoog, ::vraagVerwijderenBevestiging)
        binding.lijst.layoutManager = LinearLayoutManager(this)
        binding.lijst.adapter = adapter

        binding.knopNieuw.setOnClickListener { toonDialoog(null) }
        binding.foutmelding.setOnClickListener { laadBardiensten() }
        laadBardiensten()
    }

    private fun laadBardiensten() {
        binding.laadindicator.visibility = View.VISIBLE
        binding.foutmelding.visibility = View.GONE
        binding.lijst.visibility = View.GONE

        Thread {
            try {
                val antwoord = Api.get(this, "/api/tablet/bardiensten")
                val lijst = antwoord.getJSONArray("bardiensten")
                val nieuw = mutableListOf<Bardienst>()
                for (i in 0 until lijst.length()) {
                    val b = lijst.getJSONObject(i)
                    nieuw.add(
                        Bardienst(
                            b.getInt("id"), b.getString("datum"),
                            b.getString("start_tijd"), b.getString("eind_tijd"), b.getString("namen"),
                        )
                    )
                }
                runOnUiThread {
                    bardiensten.clear()
                    bardiensten.addAll(nieuw)
                    adapter.notifyDataSetChanged()
                    binding.laadindicator.visibility = View.GONE
                    binding.lijst.visibility = View.VISIBLE
                }
            } catch (e: Exception) {
                runOnUiThread {
                    binding.laadindicator.visibility = View.GONE
                    binding.foutmelding.visibility = View.VISIBLE
                }
            }
        }.start()
    }

    private fun vraagVerwijderenBevestiging(bardienst: Bardienst) {
        AlertDialog.Builder(this)
            .setMessage(R.string.bevestig_verwijderen_bardienst)
            .setPositiveButton(R.string.verwijderen) { _, _ -> verwijderBardienst(bardienst) }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun verwijderBardienst(bardienst: Bardienst) {
        Thread {
            try {
                Api.postForm(this, "/kiosk/prijzen/bardienst/${bardienst.id}/verwijderen", emptyMap())
                runOnUiThread { laadBardiensten() }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, R.string.fout_opslaan, Toast.LENGTH_SHORT).show() }
            }
        }.start()
    }

    private fun toonDialoog(bardienst: Bardienst?) {
        val vandaag = Calendar.getInstance()
        val view = LayoutInflater.from(this).inflate(R.layout.dialog_bardienst, null)
        val datumKnop = view.findViewById<Button>(R.id.datumKnop)
        val startKnop = view.findViewById<Button>(R.id.startKnop)
        val eindKnop = view.findViewById<Button>(R.id.eindKnop)
        val namenVeld = view.findViewById<EditText>(R.id.namenVeld)

        var datum = bardienst?.datum ?: "%04d-%02d-%02d".format(
            vandaag.get(Calendar.YEAR), vandaag.get(Calendar.MONTH) + 1, vandaag.get(Calendar.DAY_OF_MONTH)
        )
        var start = bardienst?.startTijd ?: "00:00"
        var eind = bardienst?.eindTijd ?: "23:59"
        namenVeld.setText(bardienst?.namen ?: "")

        fun werkKnoppenBij() {
            datumKnop.text = isoNaarWeergave(datum)
            startKnop.text = start
            eindKnop.text = eind
        }
        werkKnoppenBij()

        datumKnop.setOnClickListener {
            val delen = datum.split("-").map { it.toInt() }
            DatePickerDialog(this, { _, jaar, maand, dag ->
                datum = "%04d-%02d-%02d".format(jaar, maand + 1, dag)
                werkKnoppenBij()
            }, delen[0], delen[1] - 1, delen[2]).show()
        }
        startKnop.setOnClickListener {
            val delen = start.split(":").map { it.toInt() }
            TimePickerDialog(this, { _, uur, minuut ->
                start = "%02d:%02d".format(uur, minuut)
                werkKnoppenBij()
            }, delen[0], delen[1], true).show()
        }
        eindKnop.setOnClickListener {
            val delen = eind.split(":").map { it.toInt() }
            TimePickerDialog(this, { _, uur, minuut ->
                eind = "%02d:%02d".format(uur, minuut)
                werkKnoppenBij()
            }, delen[0], delen[1], true).show()
        }

        AlertDialog.Builder(this)
            .setTitle(if (bardienst == null) R.string.nieuwe_bardienst_titel else R.string.bardienst_bewerken_titel)
            .setView(view)
            .setPositiveButton(R.string.opslaan) { _, _ ->
                slaBardienstOp(bardienst, datum, start, eind, namenVeld.text.toString().trim())
            }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun slaBardienstOp(bardienst: Bardienst?, datum: String, start: String, eind: String, namen: String) {
        val pad = if (bardienst == null) "/kiosk/prijzen/bardienst/nieuw"
        else "/kiosk/prijzen/bardienst/${bardienst.id}/bewerken"
        val velden = mapOf("datum" to datum, "start_tijd" to start, "eind_tijd" to eind, "namen" to namen)

        Thread {
            try {
                val antwoord = Api.postForm(this, pad, velden)
                if (antwoord.optBoolean("ok", false)) {
                    runOnUiThread { laadBardiensten() }
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

private class BardienstenAdapter(
    private val items: List<Bardienst>,
    private val onBewerken: (Bardienst) -> Unit,
    private val onVerwijderen: (Bardienst) -> Unit,
) : RecyclerView.Adapter<BardienstenAdapter.Houder>() {

    class Houder(view: View) : RecyclerView.ViewHolder(view) {
        val inhoud: View = view.findViewById(R.id.inhoud)
        val datumTijd: TextView = view.findViewById(R.id.datumTijd)
        val namen: TextView = view.findViewById(R.id.namen)
        val verwijderKnop: View = view.findViewById(R.id.verwijderKnop)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): Houder =
        Houder(LayoutInflater.from(parent.context).inflate(R.layout.item_bardienst, parent, false))

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(houder: Houder, positie: Int) {
        val bardienst = items[positie]
        houder.datumTijd.text = "${isoNaarWeergave(bardienst.datum)}  ${bardienst.startTijd}–${bardienst.eindTijd}"
        houder.namen.text = bardienst.namen
        houder.inhoud.setOnClickListener { onBewerken(bardienst) }
        houder.verwijderKnop.setOnClickListener { onVerwijderen(bardienst) }
    }
}
