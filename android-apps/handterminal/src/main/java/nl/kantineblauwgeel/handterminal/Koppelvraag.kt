package nl.kantineblauwgeel.handterminal

import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import org.json.JSONObject

/** De vraag bij het koppelen van een onbekende barcode aan een product: wat heb je gescand?
 * - één losse (een flesje Hertog Jan): één tik, verder niets invullen;
 * - een krat of doos van de besteleenheid, of met een ander aantal;
 * - een verpakking met meer stuks, zoals een zak AH frikandellen van 20 voor € 20 (spullen uit de keuken): dan ook een
 *   naam en eventueel de inkoopprijs, zodat AH en Plus naast elkaar bij "Frikandel" kunnen staan.
 * Gebruikt door het productscherm en het koppelscherm. */
object Koppelvraag {

    fun vraag(
        activity: BasisActivity,
        code: String,
        p: Catalogus.Product,
        titel: String,
        anderProduct: (() -> Unit)? = null,
        klaar: (Catalogus.Product) -> Unit,
    ) {
        val keuzes = mutableListOf<Pair<String, () -> Unit>>()
        val los = activity.getString(R.string.koppel_los, p.eenheid) to { koppel(activity, code, p, JSONObject(), klaar) }
        val meerStuks = activity.getString(R.string.koppel_verpakking) to { vraagVerpakking(activity, code, p, klaar) }
        keuzes += los
        // Bij de keuken is een verpakking met meer stuks het gewoonst (een zak frikandellen); dan staat die bovenaan.
        if (p.categorie.equals("Keuken", ignoreCase = true)) keuzes.add(0, meerStuks)
        if (p.besteleenheid != null && p.perBesteleenheid > 1) {
            keuzes += activity.getString(R.string.koppel_doos, p.besteleenheid, p.perBesteleenheid, p.eenheid) to {
                koppel(activity, code, p, JSONObject().put("per_doos", p.perBesteleenheid), klaar)
            }
        }
        keuzes += activity.getString(R.string.koppel_doos_anders) to {
            Cijferpad.vraag(activity, activity.getString(R.string.hoeveel_in_doos), eenheid = p.eenheid) { n ->
                n.toIntOrNull()?.takeIf { it > 0 }?.let { koppel(activity, code, p, JSONObject().put("per_doos", it), klaar) }
            }
        }
        if (!p.categorie.equals("Keuken", ignoreCase = true)) keuzes += meerStuks
        if (anderProduct != null) keuzes += activity.getString(R.string.ander_product) to anderProduct
        activity.tril()
        AlertDialog.Builder(activity)
            .setCustomTitle(activity.dialoogTitel(titel))
            .setItems(keuzes.map { it.first }.toTypedArray()) { _, i -> keuzes[i].second() }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    /** Een verpakking met meer stuks: naam, hoeveel erin en (mag leeg) de inkoopprijs. */
    private fun vraagVerpakking(activity: BasisActivity, code: String, p: Catalogus.Product, klaar: (Catalogus.Product) -> Unit) {
        val dp = activity.resources.displayMetrics.density
        fun label(tekst: String) = TextView(activity).apply {
            text = tekst
            textSize = 12f
            setTextColor(activity.getColor(R.color.tekst_zacht))
            setPadding(0, (8 * dp).toInt(), 0, 0)
        }
        val naam = EditText(activity).apply {
            hint = activity.getString(R.string.koppel_naam_hint, p.naam)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            setSingleLine()
        }
        val aantal = EditText(activity).apply {
            hint = activity.getString(R.string.koppel_aantal_hint)
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine()
        }
        val prijs = EditText(activity).apply {
            hint = activity.getString(R.string.mag_leeg)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
            setSingleLine()
        }
        val inhoud = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((22 * dp).toInt(), (4 * dp).toInt(), (22 * dp).toInt(), 0)
            addView(label(activity.getString(R.string.koppel_naam)))
            addView(naam)
            addView(label(activity.getString(R.string.koppel_aantal, p.eenheid)))
            addView(aantal)
            addView(label(activity.getString(R.string.koppel_prijs)))
            addView(prijs)
        }
        AlertDialog.Builder(activity)
            .setTitle(p.naam)
            .setView(inhoud)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.koppelen) { _, _ ->
                val n = aantal.text.toString().toIntOrNull()
                if (n == null || n < 1) {
                    activity.melding(activity.getString(R.string.koppel_aantal_nodig), lang = true)
                    return@setPositiveButton
                }
                val body = JSONObject().put("per_verpakking", n)
                naam.text.toString().trim().takeIf { it.isNotEmpty() }?.let { body.put("naam", it) }
                prijs.text.toString().trim().takeIf { it.isNotEmpty() }?.let { body.put("inkoopprijs", it) }
                koppel(activity, code, p, body, klaar)
            }
            .show()
    }

    private fun koppel(activity: BasisActivity, code: String, p: Catalogus.Product, body: JSONObject, klaar: (Catalogus.Product) -> Unit) {
        val verzoekId = Api.nieuwVerzoekId()
        activity.bezig {
            body.put("code", code).put("product_id", p.id)
            val antwoord = Api.post(activity, "/api/app/barcodes/koppelen", body, verzoekId = verzoekId)
            val nieuw = Catalogus.product(antwoord.getJSONObject("product"))
            Catalogus.werkBij(activity, nieuw)
            activity.tril(60)
            activity.melding(activity.getString(R.string.gekoppeld_aan, p.naam))
            klaar(nieuw)
        }
    }
}
