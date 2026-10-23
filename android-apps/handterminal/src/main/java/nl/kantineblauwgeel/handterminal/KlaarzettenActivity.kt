package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Een bestelling klaarzetten, zoals "Voorgesteld om te bestellen" op de bestellijst van de site. Staan klaar (met het
 * voorgestelde aantal): wat onder het minimum zit (met het advies van de prognose als die meer vraagt), en wat bij een
 * vorige bestelling niet geleverd is. Wat waarschijnlijk opraakt staat eronder, nog op 0. Tik op een product om het
 * aantal te veranderen (0 = niet bestellen). "Klaarzetten" maakt de bestelling; hij staat dan bij Factuur inboeken. */
class KlaarzettenActivity : BasisActivity() {

    private class Regel(val p: JSONObject, val soort: String, var aantal: Int)

    private lateinit var b: ActivityLijstBinding
    private val regels = mutableListOf<Regel>()
    private var verzoekId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.bestelling_klaarzetten))
        b.verversen.isEnabled = false
        b.onderKnop.isVisible = true
        b.onderKnop.setOnClickListener { klaarzetten() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (regels.none { it.aantal > 0 }) return finish()
                AlertDialog.Builder(this@KlaarzettenActivity)
                    .setMessage(R.string.klaarzetten_weggooien_vraag)
                    .setPositiveButton(R.string.weggooien) { _, _ -> finish() }
                    .setNegativeButton(R.string.annuleren, null)
                    .show()
            }
        })
        werkKnopBij()
        bezig {
            val lijst = Api.getJson(this, "/api/app/bestellijst")
            lijst.getJSONArray("bestellen").objecten().forEach { regels += Regel(it, "laag", basis(it)) }
            lijst.optJSONArray("manco")?.objecten()?.forEach { regels += Regel(it, "manco", it.optInt("tekort_besteleenheden")) }
            toon()
            // De prognose rekent soms even: daarna het advies erbij, en wat waarschijnlijk opraakt.
            val prognose = Api.getJson(this, "/api/app/bestellijst/prognose")
            val advies = prognose.optJSONObject("producten")
            for (r in regels) {
                val x = advies?.optJSONObject(r.p.getInt("id").toString()) ?: continue
                r.p.put("advies", x.optInt("advies_eenheden"))
                if (r.soort == "laag" && x.optInt("advies_eenheden") > r.aantal) r.aantal = x.optInt("advies_eenheden")
            }
            val al = regels.map { it.p.getInt("id") }.toSet()
            prognose.optJSONArray("extra")?.objecten()?.filter { it.getInt("id") !in al }?.forEach {
                it.put("advies", it.optInt("advies_eenheden"))
                regels += Regel(it, "opraken", 0)
            }
            toon()
        }
    }

    /** Het gewone voorstel: de vaste bestelhoeveelheid, of tot het minimum, in hele besteleenheden. */
    private fun basis(p: JSONObject): Int {
        val per = maxOf(1, p.optInt("per_besteleenheid", 1))
        val tekort = if (p.optInt("bestel_hoeveelheid") > 0) p.optInt("bestel_hoeveelheid") else p.optInt("min_voorraad") - p.optInt("voorraad")
        return maxOf(1, (tekort + per - 1) / per)
    }

    private fun eenheid(p: JSONObject) = p.tekstOfNull("besteleenheid") ?: p.optString("eenheid")

    private fun toon() {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        Lijst.kaart(inhoud, R.drawable.melding_info).let { Lijst.tekst(it, getString(R.string.klaarzetten_uitleg), kleur = R.color.tekst) }
        for ((soort, kop) in listOf("laag" to R.string.klaarzetten_laag, "manco" to R.string.klaarzetten_manco, "opraken" to R.string.raakt_waarschijnlijk_op)) {
            val groep = regels.filter { it.soort == soort }
            if (groep.isEmpty()) continue
            Lijst.kop(inhoud, getString(kop))
            val kaart: LinearLayout = Lijst.kaart(inhoud, if (soort == "manco") R.drawable.rand_links_oranje else R.drawable.kaart)
            for (r in groep) {
                val p = r.p
                val detail = listOfNotNull(
                    getString(R.string.voorraad_min, p.optInt("voorraad"), p.optInt("min_voorraad"), p.optString("eenheid")),
                    if (soort == "manco") getString(R.string.niet_geleverd_bij, p.optJSONArray("bestellingen")?.let { a -> (0 until a.length()).joinToString(", #") { a.optInt(it).toString() } } ?: "")
                    else null,
                    if (p.has("advies")) getString(R.string.advies_kort_eenheden, p.optInt("advies"), eenheid(p)) else null,
                ).joinToString(" · ")
                Lijst.regel(kaart, p.optString("naam"), detail, if (r.aantal > 0) "${r.aantal} ${eenheid(p)}" else "–",
                    if (r.aantal > 0) R.color.navy else R.color.tekst_zacht) { vraag(r) }
            }
        }
        if (regels.isEmpty()) Lijst.leeg(inhoud, getString(R.string.niets_bestellen))
        werkKnopBij()
    }

    private fun vraag(r: Regel) {
        val p = r.p
        Cijferpad.vraag(this, getString(R.string.hoeveel_bestellen, p.optString("naam")), if (r.aantal > 0) r.aantal.toString() else "",
            eenheid = eenheid(p), max = 4) { tekst ->
            r.aantal = tekst.toIntOrNull() ?: 0
            verzoekId = null
            toon()
        }
    }

    private fun werkKnopBij() {
        val n = regels.count { it.aantal > 0 }
        b.onderKnop.isEnabled = n > 0
        b.onderKnop.alpha = if (n > 0) 1f else 0.5f
        b.onderKnop.text = getString(R.string.klaarzetten_n, n)
    }

    private fun klaarzetten() {
        val gekozen = regels.filter { it.aantal > 0 }
        if (gekozen.isEmpty()) return
        AlertDialog.Builder(this)
            .setTitle(R.string.bestelling_klaarzetten)
            .setMessage(gekozen.joinToString("\n") { "${it.aantal} ${eenheid(it.p)} ${it.p.optString("naam")}" })
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.klaarzetten) { _, _ ->
                val id = verzoekId ?: Api.nieuwVerzoekId().also { verzoekId = it }
                val aantallen = JSONObject()
                gekozen.forEach { aantallen.put(it.p.getInt("id").toString(), it.aantal) }
                b.onderKnop.isEnabled = false
                bezig {
                    try {
                        val antwoord = Api.post(this, "/api/app/bestellijst/bestellen", JSONObject().put("aantallen", aantallen), verzoekId = id)
                        tril(60)
                        melding(antwoord.optString("melding"), lang = true)
                        finish()
                    } finally {
                        werkKnopBij()
                    }
                }
            }
            .show()
    }

    companion object {
        fun open(context: Context) = context.startActivity(Intent(context, KlaarzettenActivity::class.java))
    }
}
