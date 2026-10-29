package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import nl.kantineblauwgeel.handterminal.databinding.ActivityLijstBinding
import org.json.JSONObject

/** De kantine-tv vanaf de bar: hoe de tv's erbij staan (aan of uit, wat ze tonen, opnieuw laden, de wisselknop),
 * het programma met momenten (de schijnwerper: nu tonen, stoppen, een kwartier later), uitverkocht en de timer, de
 * specials (het uitgelichte product en de prijs-acties), de bardienst van vandaag en morgen, en de diashow
 * (DiasActivity, ook de mappen). Dia's maken, de indeling en een nieuwe tv koppelen doe je op de site. Zie
 * routes/app_api_tv.py. */
class KantineTvActivity : BasisActivity() {

    private lateinit var b: ActivityLijstBinding
    private var data: JSONObject? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityLijstBinding.inflate(layoutInflater)
        setContentView(b.root)
        richtBalkIn(b.balk, getString(R.string.kantine_tv))
        b.verversen.setColorSchemeResources(R.color.navy)
        b.verversen.setOnRefreshListener { laad() }
        teKoppelen = intent.getStringExtra(EXTRA_KOPPELCODE)
    }

    override fun onResume() {
        super.onResume()
        if (Sessie.isIngelogd(this)) laad()
    }

    override fun weerVerbonden() = laad()

    /** Geopend door de QR-code op een nieuwe tv: meteen het koppelvenster (zie onCreate). */
    private var teKoppelen: String? = null

    /** Een scan hier: de QR-code van een nieuwe tv koppelt die tv; de rest zoals overal. */
    override fun bijScan(code: String) {
        val koppel = KOPPEL_LINK.find(code)?.groupValues?.get(1)
        if (koppel != null) {
            tril()
            koppelVenster(koppel)
        } else super.bijScan(code)
    }

    private fun laad() {
        bezig {
            try {
                toon(Api.getJson(this, "/api/app/kantine-tv"))
                teKoppelen?.let { teKoppelen = null; koppelVenster(it) }
            } finally {
                b.verversen.isRefreshing = false
            }
        }
    }

    /** Een schrijfactie; het antwoord is het hele overzicht opnieuw, met een melding. */
    private fun stuur(pad: String, body: JSONObject = JSONObject(), verzoekId: String? = null) {
        bezig {
            val antwoord = Api.post(this, pad, body, verzoekId = verzoekId, herhaalbaar = verzoekId == null)
            tril(60)
            antwoord.tekstOfNull("melding")?.let { melding(it, lang = true) }
            toon(antwoord)
        }
    }

    private fun toon(d: JSONObject) {
        data = d
        val inhoud = b.inhoud
        inhoud.removeAllViews()

        // Tv's
        Lijst.kop(inhoud, getString(R.string.tvs))
        val tvs = d.optJSONArray("tvs")?.objecten().orEmpty()
        val schermen = d.optJSONArray("schermen")?.objecten().orEmpty().associate { it.optString("sleutel") to it.optString("naam") }
        if (tvs.isEmpty()) Lijst.leeg(inhoud, getString(R.string.geen_tvs))
        else {
            val kaart = Lijst.kaart(inhoud)
            for (tv in tvs) {
                val status = tv.optJSONObject("status") ?: JSONObject()
                val aan = status.optBoolean("aan")
                // Wat hij moet tonen, en (als hij aan staat en nog iets anders toont) wat hij nu toont.
                val ingesteld = (schermen[tv.optString("scherm")] ?: "").substringBefore(" (").lowercase()
                val toont = status.tekstOfNull("toont")
                val detail = listOfNotNull(
                    when {
                        !aan -> getString(R.string.tv_ingesteld, ingesteld)
                        toont == null || toont.endsWith(ingesteld) || tv.optString("scherm") == "wissel" ->
                            getString(R.string.tv_toont, toont ?: ingesteld) + if (tv.optString("scherm") == "wissel") " " + getString(R.string.tv_via_wissel) else ""
                        else -> getString(R.string.tv_ingesteld_toont_nog, ingesteld, toont)
                    },
                    if (aan) null else status.tekstOfNull("tekst"),
                    status.tekstOfNull("app"),
                ).joinToString(" · ")
                Lijst.regel(kaart, tv.optString("naam"), detail, getString(if (aan) R.string.aan else R.string.uit),
                    if (aan) R.color.groen_tekst else R.color.rood_balk) { tvMenu(tv, schermen) }
            }
        }
        Lijst.regel(Lijst.kaart(inhoud), getString(R.string.tv_koppelen), getString(R.string.tv_koppelen_uitleg), "+", R.color.navy) {
            koppelVenster(null)
        }
        val wisselDias = d.optString("wissel") == "dias"
        Lijst.regel(Lijst.kaart(inhoud), getString(R.string.wisselscherm),
            getString(if (wisselDias) R.string.wissel_toont_dias else R.string.wissel_toont_prijzen),
            getString(R.string.wisselen), R.color.navy) {
            stuur("/api/app/kantine-tv/wissel", JSONObject().put("toont", if (wisselDias) "prijzen" else "dias"))
        }

        // Het thema op alle schermen (zoals Halloween): met één tik aan of uit.
        val halloween = d.tekstOfNull("thema") == "halloween"
        Lijst.regel(Lijst.kaart(inhoud), getString(R.string.halloween_thema),
            getString(if (halloween) R.string.halloween_aan_uitleg else R.string.halloween_uit_uitleg),
            getString(if (halloween) R.string.aan else R.string.uit),
            if (halloween) R.color.oranje_balk else R.color.tekst_zacht) {
            stuur("/api/app/kantine-tv/thema", JSONObject().put("thema", if (halloween) JSONObject.NULL else "halloween"))
        }

        // Het programma (zie kiosk_momenten.py): een dia met een moment staat de eerste minuten groot op alle tv's.
        val momenten = d.optJSONArray("momenten")?.objecten().orEmpty()
        if (momenten.isNotEmpty() || d.optBoolean("schijnwerper")) {
            Lijst.kop(inhoud, getString(R.string.momenten))
            val kaart = Lijst.kaart(inhoud)
            for (m in momenten) {
                val status = m.optString("status")
                val (wat, kleur) = when (status) {
                    "schijnwerper" -> getString(R.string.moment_schijnwerper) to R.color.oranje_balk
                    "bezig" -> getString(R.string.moment_bezig) to R.color.groen_tekst
                    "klaar" -> getString(R.string.moment_klaar) to R.color.tekst_zacht
                    "map_uit" -> getString(R.string.moment_map_uit) to R.color.rood_balk
                    "dia_uit" -> getString(R.string.moment_dia_uit) to R.color.rood_balk
                    else -> getString(R.string.moment_straks) to R.color.navy
                }
                Lijst.regel(kaart, m.optString("tijd") + "  " + (m.tekstOfNull("titel") ?: ""),
                    listOfNotNull(m.tekstOfNull("map"), m.tekstOfNull("balk")).joinToString(" · ").ifEmpty { null }, wat, kleur) {
                    momentMenu(m)
                }
            }
            if (d.optBoolean("schijnwerper")) {
                Lijst.knop(kaart, getString(R.string.schijnwerper_stop)) { stuur("/api/app/kantine-tv/schijnwerper/stop") }
            }
        }

        // Op het prijzenscherm: uitverkocht en de timer
        Lijst.kop(inhoud, getString(R.string.op_het_prijzenscherm))
        val prijzen = Lijst.kaart(inhoud)
        if (inst.toegang("voorraad")) {  // uitverkocht zetten mag met voorraadrechten (zie rechten.py)
            val uitverkocht = d.optInt("uitverkocht")
            Lijst.regel(prijzen, getString(R.string.uitverkocht_titel), getString(R.string.uitverkocht_kort_uitleg),
                if (uitverkocht > 0) uitverkocht.toString() else null, R.color.rood_balk) { UitverkochtActivity.open(this) }
        }
        val timers = d.optInt("timers")
        Lijst.regel(prijzen, getString(R.string.timer_titel), getString(R.string.timer_kort_uitleg),
            if (timers > 0) timers.toString() else null, R.color.navy) { TimerActivity.open(this) }

        // Specials
        Lijst.kop(inhoud, getString(R.string.specials))
        val specials = Lijst.kaart(inhoud)
        val uitgelicht = d.optJSONObject("uitgelicht")
        Lijst.regel(specials, uitgelicht?.optString("titel") ?: d.optString("uitgelicht_titel"),
            uitgelicht?.optString("naam") ?: getString(R.string.niets_uitgelicht),
            getString(R.string.wijzigen), R.color.navy) { uitgelichtMenu(uitgelicht, d.optString("uitgelicht_titel")) }
        val acties = d.optJSONArray("acties")?.objecten().orEmpty()
        if (acties.isEmpty()) Lijst.tekst(specials, getString(R.string.geen_acties), grootte = 12f)
        for (a in acties) {
            val actief = a.optBoolean("actief")
            Lijst.regel(specials, getString(R.string.actie_naam, a.optString("product")), a.tekstOfNull("tekst"),
                getString(if (actief) R.string.aan else R.string.uit), if (actief) R.color.groen_tekst else R.color.tekst_zacht) {
                stuur("/api/app/kantine-tv/acties/${a.getInt("id")}", JSONObject().put("actief", !actief))
            }
        }

        // Bardienst
        Lijst.kop(inhoud, getString(R.string.bardienst))
        val bardienst = Lijst.kaart(inhoud)
        val diensten = d.optJSONArray("bardiensten")?.objecten().orEmpty()
        val vandaag = d.optString("vandaag")
        for ((datum, label) in listOf(vandaag to getString(R.string.dag_vandaag), d.optString("morgen") to getString(R.string.dag_morgen))) {
            val opDag = diensten.filter { it.optString("datum") == datum }
            if (opDag.isEmpty()) continue
            Lijst.subkop(bardienst, label)
            for (bd in opDag) {
                val tijd = "${bd.optString("start_tijd")} – ${bd.optString("eind_tijd")}"
                Lijst.regel(bardienst, bd.optString("namen"),
                    if (bd.optBoolean("bezig")) getString(R.string.nu_bezig, tijd) else tijd,
                    if (bd.optBoolean("bezig")) getString(R.string.nu) else null, R.color.groen_tekst) { bardienstVenster(bd, vandaag) }
            }
        }
        if (diensten.isEmpty()) Lijst.tekst(bardienst, getString(R.string.geen_bardienst), grootte = 12f)
        Lijst.knop(bardienst, getString(R.string.bardienst_toevoegen)) { bardienstVenster(null, vandaag) }

        // Diashow
        Lijst.kop(inhoud, getString(R.string.diashow))
        Lijst.regel(Lijst.kaart(inhoud), getString(R.string.dias_aan_uit), getString(R.string.dias_aan_uit_uitleg)) { DiasActivity.open(this) }
        Lijst.tekst(inhoud, getString(R.string.kantine_tv_op_site), grootte = 11.5f)
    }

    // ---------------------------------------------------------------- momenten

    /** Een moment aangetikt: nu groot op alle tv's, of het moment een kwartier later of eerder (het programma loopt uit). */
    private fun momentMenu(m: JSONObject) {
        val id = m.getInt("id")
        val keuzes = listOf(
            getString(R.string.moment_nu_tonen) to { stuur("/api/app/kantine-tv/momenten/$id/nu", verzoekId = Api.nieuwVerzoekId()) },
            getString(R.string.moment_later) to { stuur("/api/app/kantine-tv/momenten/$id/later", JSONObject().put("minuten", 15), Api.nieuwVerzoekId()) },
            getString(R.string.moment_eerder) to { stuur("/api/app/kantine-tv/momenten/$id/later", JSONObject().put("minuten", -15), Api.nieuwVerzoekId()) },
        )
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(m.optString("tijd") + "  " + (m.tekstOfNull("titel") ?: "")))
            .setItems(keuzes.map { it.first }.toTypedArray()) { _, i -> keuzes[i].second() }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    // ---------------------------------------------------------------- tv's

    private fun tvMenu(tv: JSONObject, schermen: Map<String, String>) {
        val huidig = tv.optString("scherm")
        val sleutels = schermen.keys.toList()
        val opties = sleutels.map { (if (it == huidig) "✓  " else "     ") + schermen[it] } + getString(R.string.opnieuw_laden)
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.wat_toont, tv.optString("naam"))))
            .setItems(opties.toTypedArray()) { _, i ->
                val id = tv.getInt("id")
                if (i == sleutels.size) stuur("/api/app/kantine-tv/tvs/$id/herladen")
                else if (sleutels[i] != huidig) stuur("/api/app/kantine-tv/tvs/$id/scherm", JSONObject().put("scherm", sleutels[i]))
            }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    /** Een nieuwe tv koppelen: de code (uit de QR-code, of zelf intikken), een naam en wat hij toont. */
    private fun koppelVenster(code: String?) {
        val codeVeld = EditText(this).apply {
            hint = getString(R.string.koppelcode_hint)
            inputType = InputType.TYPE_CLASS_NUMBER
            setText(code ?: "")
        }
        val naam = EditText(this).apply {
            hint = getString(R.string.tv_naam_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        val schermen = data?.optJSONArray("schermen")?.objecten().orEmpty()
        val keuze = RadioGroup(this).apply {
            schermen.forEachIndexed { i, s -> addView(RadioButton(context).apply { id = i + 1; text = s.optString("naam") }) }
            // Standaard de dia's: met de afstandsbediening wissel je op de tv zelf naar de prijzenlijst.
            check((schermen.indexOfFirst { it.optString("sleutel") == "dias" }.takeIf { it >= 0 } ?: 0) + 1)
        }
        fun label(tekst: Int) = TextView(this).apply {
            setText(tekst)
            textSize = 12f
            setTextColor(getColor(R.color.tekst_zacht))
            setPadding(0, dp(context, 8), 0, 0)
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(label(R.string.code_op_de_tv))
            addView(codeVeld)
            addView(label(R.string.naam_van_de_tv))
            addView(naam)
            addView(label(R.string.wat_toont_hij))
            addView(keuze)
        }
        val dialoog = AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.tv_koppelen)))
            .setView(android.widget.ScrollView(this).apply { addView(vorm) })
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.koppelen, null)
            .show()
        dialoog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val c = codeVeld.text.toString().filter { it.isDigit() }
            val n = naam.text.toString().trim()
            when {
                c.length != 6 -> codeVeld.error = getString(R.string.koppelcode_fout)
                n.isEmpty() -> naam.error = getString(R.string.tv_naam_nodig)
                else -> {
                    val scherm = schermen.getOrNull(keuze.checkedRadioButtonId - 1)?.optString("sleutel") ?: "prijzen"
                    dialoog.dismiss()
                    stuur("/api/app/kantine-tv/tvs/koppelen", JSONObject().put("code", c).put("naam", n).put("scherm", scherm),
                        verzoekId = Api.nieuwVerzoekId())
                }
            }
        }
        (if (code == null) codeVeld else naam).requestFocus()
    }

    // ---------------------------------------------------------------- specials

    private fun uitgelichtMenu(uitgelicht: JSONObject?, titel: String) {
        val opties = mutableListOf(getString(R.string.kies_ander_product), getString(R.string.titel_aanpassen))
        if (uitgelicht != null) opties += getString(R.string.uitgelicht_uitzetten)
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(titel))
            .setItems(opties.toTypedArray()) { _, i ->
                when (i) {
                    0 -> kiesProduct(titel)
                    1 -> titelVenster(titel, uitgelicht)
                    else -> stuur("/api/app/kantine-tv/uitgelicht", JSONObject().put("product_id", JSONObject.NULL))
                }
            }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun titelVenster(titel: String, uitgelicht: JSONObject?) {
        val veld = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            setText(titel)
            setSelection(text.length)
        }
        val vorm = LinearLayout(this).apply {
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(veld, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }
        AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(R.string.titel_aanpassen)))
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.opslaan) { _, _ ->
                val nieuw = veld.text.toString().trim()
                if (nieuw.isEmpty()) return@setPositiveButton
                if (uitgelicht == null) kiesProduct(nieuw)  // zonder product staat er niets op de tv: eerst een product kiezen
                else stuur("/api/app/kantine-tv/uitgelicht", JSONObject().put("product_id", uitgelicht.getInt("product_id")).put("titel", nieuw))
            }
            .show()
        veld.requestFocus()
    }

    /** Een product kiezen, met een zoekveld; de producten op het prijzenscherm staan bovenaan. */
    private fun kiesProduct(titel: String) {
        bezig {
            val producten = Api.getJson(this, "/api/app/kantine-tv/producten").optJSONArray("producten")?.objecten().orEmpty()
                .sortedByDescending { it.optBoolean("op_prijzenscherm") }
            val zoek = EditText(this).apply {
                hint = getString(R.string.zoek_product)
                inputType = InputType.TYPE_CLASS_TEXT
            }
            var zichtbaar = producten
            val adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, zichtbaar.map { it.optString("naam") }.toMutableList())
            val lijst = ListView(this).apply { this.adapter = adapter }
            val vorm = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(context, 16), 0, dp(context, 16), 0)
                addView(zoek)
                addView(lijst, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(context, 300)))
            }
            val dialoog = AlertDialog.Builder(this)
                .setCustomTitle(dialoogTitel(getString(R.string.kies_product_voor, titel)))
                .setView(vorm)
                .setNegativeButton(R.string.annuleren, null)
                .show()
            zoek.addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    val term = s.toString().trim().lowercase()
                    zichtbaar = producten.filter { term.isEmpty() || it.optString("naam").lowercase().contains(term) }
                    adapter.clear()
                    adapter.addAll(zichtbaar.map { it.optString("naam") })
                }
            })
            lijst.setOnItemClickListener { _, _, i, _ ->
                dialoog.dismiss()
                stuur("/api/app/kantine-tv/uitgelicht", JSONObject().put("product_id", zichtbaar[i].getInt("id")).put("titel", titel))
            }
        }
    }

    // ---------------------------------------------------------------- bardienst

    /** Een bardienst toevoegen ([bd] null) of aanpassen, bijvoorbeeld een wissel ter plekke. */
    private fun bardienstVenster(bd: JSONObject?, vandaag: String) {
        fun veld(hint: Int, waarde: String?, soort: Int) = EditText(this).apply {
            this.hint = getString(hint)
            inputType = soort
            setText(waarde ?: "")
        }
        val tijdSoort = InputType.TYPE_CLASS_DATETIME or InputType.TYPE_DATETIME_VARIATION_TIME
        val namen = veld(R.string.wie_bardienst, bd?.optString("namen"), InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS)
        val start = veld(R.string.van_tijd, bd?.optString("start_tijd"), tijdSoort)
        val eind = veld(R.string.tot_tijd, bd?.optString("eind_tijd"), tijdSoort)
        val dag = RadioGroup(this).apply {
            orientation = RadioGroup.HORIZONTAL
            addView(RadioButton(context).apply { id = 1; setText(R.string.dag_vandaag) })
            addView(RadioButton(context).apply { id = 2; setText(R.string.dag_morgen) })
            check(1)
        }
        fun label(tekst: Int) = TextView(this).apply {
            setText(tekst)
            textSize = 12f
            setTextColor(getColor(R.color.tekst_zacht))
            setPadding(0, dp(context, 8), 0, 0)
        }
        val tijden = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(start, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(TextView(context).apply { text = " – " })
            addView(eind, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        }
        val vorm = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(context, 20), dp(context, 6), dp(context, 20), 0)
            addView(label(R.string.wie))
            addView(namen)
            addView(label(R.string.hoe_laat))
            addView(tijden)
            if (bd == null) {
                addView(label(R.string.wanneer))
                addView(dag)
            }
        }
        val bouwer = AlertDialog.Builder(this)
            .setCustomTitle(dialoogTitel(getString(if (bd == null) R.string.bardienst_toevoegen else R.string.bardienst_aanpassen)))
            .setView(vorm)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.opslaan, null)
        if (bd != null) bouwer.setNeutralButton(R.string.verwijderen) { _, _ ->
            AlertDialog.Builder(this)
                .setMessage(getString(R.string.bardienst_verwijderen_vraag, bd.optString("namen")))
                .setNegativeButton(R.string.annuleren, null)
                .setPositiveButton(R.string.verwijderen) { _, _ -> stuur("/api/app/kantine-tv/bardiensten/${bd.getInt("id")}/verwijderen") }
                .show()
        }
        val dialoog = bouwer.show()
        dialoog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val n = namen.text.toString().trim()
            val s = tijd(start.text.toString(), "00:00")  // leeg: de hele dag, net als op de site
            val e = tijd(eind.text.toString(), "23:59")
            when {
                n.isEmpty() -> namen.error = getString(R.string.vul_namen_in)
                s == null -> start.error = getString(R.string.tijd_fout)
                e == null -> eind.error = getString(R.string.tijd_fout)
                else -> {
                    dialoog.dismiss()
                    val body = JSONObject().put("namen", n).put("start_tijd", s).put("eind_tijd", e)
                    if (bd != null) stuur("/api/app/kantine-tv/bardiensten/${bd.getInt("id")}", body)
                    else {
                        val datum = if (dag.checkedRadioButtonId == 2) data?.optString("morgen") else vandaag
                        stuur("/api/app/kantine-tv/bardiensten", body.put("datum", datum), verzoekId = Api.nieuwVerzoekId())
                    }
                }
            }
        }
        namen.requestFocus()
    }

    /** "14:00", "1400", "14.00" of "9" → "14:00"/"09:00"; leeg → [leeg]; anders null (fout). */
    private fun tijd(invoer: String, leeg: String?): String? {
        val t = invoer.trim().replace('.', ':')
        if (t.isEmpty()) return leeg
        val (u, m) = when {
            ':' in t -> t.substringBefore(':') to t.substringAfter(':')
            t.length <= 2 -> t to "0"
            else -> t.dropLast(2) to t.takeLast(2)
        }
        val uur = u.toIntOrNull() ?: return null
        val minuut = m.toIntOrNull() ?: return null
        if (uur !in 0..23 || minuut !in 0..59) return null
        return "%02d:%02d".format(uur, minuut)
    }

    companion object {
        private const val EXTRA_KOPPELCODE = "koppelcode"

        /** De QR-code op een nieuwe tv wijst naar /kiosk/koppel/<code> op de site. */
        val KOPPEL_LINK = Regex("/kiosk/koppel/(\\d{6})")

        fun open(context: Context, koppelcode: String? = null) =
            context.startActivity(Intent(context, KantineTvActivity::class.java).putExtra(EXTRA_KOPPELCODE, koppelcode))
    }
}
