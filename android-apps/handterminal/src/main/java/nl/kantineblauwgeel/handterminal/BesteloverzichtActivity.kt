package nl.kantineblauwgeel.handterminal

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.core.view.isVisible
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** Het overzicht van klaargezette bestellingen, een per leverancier: wat je bij de leverancier bestelt (op zijn site,
 * in zijn app of aan de telefoon), met per product het artikelnummer en het aantal colli, en je klantnummer. Opent na
 * het klaarzetten op de bestellijst, en als je daar onder Onderweg op een bestelling tikt. Kopiëren of delen geeft de
 * lijst als tekst (voor een mail of WhatsApp); "Levering inscannen" opent Factuur inboeken. Zie api_app_bestelling op
 * de site. */
class BesteloverzichtActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var bestellingen: List<JSONObject> = emptyList()
    private val nieuw get() = intent.getBooleanExtra(EXTRA_NIEUW, false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.besteloverzicht))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        b.onderKnop.isVisible = nieuw
        b.onderKnop.text = getString(R.string.besteloverzicht_klaar)
        b.onderKnop.setOnClickListener { finish() }
        laad()
    }

    override fun weerVerbonden() = laad()

    private fun laad() {
        val ids = intent.getIntArrayExtra(EXTRA_IDS) ?: intArrayOf()
        bezig {
            try {
                bestellingen = ids.map { Api.getJson(this, "/api/app/bestellingen/$it") }
                toon()
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    private fun toon() {
        val inhoud = b.inhoud
        inhoud.removeAllViews()
        Lijst.ruimte(inhoud)
        if (nieuw) Lijst.kaart(inhoud, R.drawable.melding_info).let { Lijst.tekst(it, getString(R.string.besteloverzicht_uitleg), kleur = R.color.tekst) }
        for (best in bestellingen) {
            val nr = best.tekstOfNull("referentie") ?: getString(R.string.bestelling_nr, best.getInt("id"))
            Lijst.kop(inhoud, (best.tekstOfNull("leverancier") ?: getString(R.string.zonder_leverancier)) + " · " + nr)
            val kaart = Lijst.kaart(inhoud)
            listOfNotNull(
                best.tekstOfNull("klantnummer")?.let { getString(R.string.klantnummer_n, it) },
                best.tekstOfNull("uiterst_tekst")?.let { getString(R.string.uiterlijk_n, it) },
            ).joinToString(" · ").takeIf { it.isNotEmpty() }?.let { Lijst.tekst(kaart, it, kleur = R.color.tekst) }
            for (r in best.getJSONArray("regels").objecten()) {
                Lijst.regel(
                    kaart,
                    r.optString("naam"),
                    listOfNotNull(
                        r.tekstOfNull("artikelcode")?.let { getString(R.string.art_nr, it) },
                        if (r.optInt("factor", 1) > 1) getString(R.string.n_eenheid, r.optInt("stuks"), r.optString("eenheid")) else null,
                    ).joinToString(" · "),
                    getString(R.string.n_eenheid, r.optInt("eenheden"), r.optString("besteleenheid")),
                    R.color.navy,
                )
            }
            val tekst = best.optString("tekst")
            Lijst.knop(kaart, getString(R.string.kopieren)) { kopieer(tekst) }
            Lijst.knop(kaart, getString(R.string.delen)) { deel(tekst) }
            if (best.optString("status") == "besteld") {
                Lijst.knop(kaart, getString(R.string.levering_inscannen)) { FacturenActivity.inboeken(this, best.getInt("id")) }
            }
        }
    }

    private fun kopieer(tekst: String) {
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(getString(R.string.besteloverzicht), tekst))
        tril(30)
        melding(getString(R.string.gekopieerd))
    }

    private fun deel(tekst: String) {
        val delen = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, tekst)
        startActivity(Intent.createChooser(delen, getString(R.string.delen)))
    }

    companion object {
        private const val EXTRA_IDS = "ids"
        private const val EXTRA_NIEUW = "nieuw"

        /** [nieuw]: net klaargezet (dan staat er uitleg boven en een knop Klaar onderaan). */
        fun open(context: Context, ids: IntArray, nieuw: Boolean = false) =
            context.startActivity(Intent(context, BesteloverzichtActivity::class.java).putExtra(EXTRA_IDS, ids).putExtra(EXTRA_NIEUW, nieuw))
    }
}
