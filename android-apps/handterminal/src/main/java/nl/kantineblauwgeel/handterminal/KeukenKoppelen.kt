package nl.kantineblauwgeel.handterminal

import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import org.json.JSONObject

/** De vragen van de keuken bij het scannen en inboeken (ook voor wie alleen keukenrechten heeft):
 * - [koppel]: een onbekende barcode aan een keukenproduct koppelen. Er staan alleen keukenproducten in de lijst, en er is
 *   één vraag: hoeveel zit erin (naam en inkoopprijs mogen leeg).
 * - [vraagAantal]: een gekoppelde zak of doos waar nog niet bij staat hoeveel erin zit.
 * - [vraagProductVerpakking]: een product zonder barcode (gehaktballen van de slager) één keer een verpakking geven.
 * De keuken boekt per verpakking in, nooit per stuk: er zit altijd minstens 2 in. Na [koppel] en [vraagAantal] krijgt
 * klaar de barcode zoals in "dozen" bij /api/app/keuken: {code, product_id, aantal, omschrijving}. */
object KeukenKoppelen {

    private const val MIN_PER_VERPAKKING = 2

    /** [producten]: (id, naam) van de keukenproducten; [voorkeur] (het product waar je bent) staat bovenaan. */
    fun koppel(activity: BasisActivity, code: String, producten: List<Pair<Int, String>>, voorkeur: Int? = null, klaar: (JSONObject) -> Unit) {
        if (producten.isEmpty()) return activity.melding(activity.getString(R.string.geen_keukenproducten))
        val lijst = producten.sortedWith(compareBy({ it.first != voorkeur }, { it.second.lowercase() }))
        activity.tril(150)
        AlertDialog.Builder(activity)
            .setCustomTitle(activity.dialoogTitel(activity.getString(R.string.keuken_koppel_welk, code)))
            .setItems(lijst.map { it.second }.toTypedArray()) { _, i -> vraagVerpakking(activity, code, lijst[i], klaar) }
            .setNegativeButton(R.string.annuleren, null)
            .show()
    }

    private fun vraagVerpakking(activity: BasisActivity, code: String, product: Pair<Int, String>, klaar: (JSONObject) -> Unit) {
        val aantal = veld(activity, activity.getString(R.string.koppel_aantal_hint), InputType.TYPE_CLASS_NUMBER)
        val naam = veld(activity, activity.getString(R.string.koppel_naam_hint, product.second),
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
        val prijs = veld(activity, activity.getString(R.string.mag_leeg), InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
        val inhoud = formulier(activity, listOf(
            activity.getString(R.string.keuken_hoeveel_erin_kort) to aantal,
            activity.getString(R.string.koppel_naam) to naam,
            activity.getString(R.string.koppel_prijs) to prijs,
        ))
        val verzoekId = Api.nieuwVerzoekId()
        val dialoog = AlertDialog.Builder(activity)
            .setCustomTitle(activity.dialoogTitel(product.second))
            .setView(inhoud)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.koppelen, null)
            .show()
        aantal.requestFocus()
        // Zelf afhandelen, zodat het venster blijft staan als het aantal ontbreekt.
        dialoog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val n = aantal.text.toString().toIntOrNull()
            if (n == null || n < MIN_PER_VERPAKKING) return@setOnClickListener activity.melding(activity.getString(R.string.keuken_minstens_twee), lang = true)
            val body = JSONObject().put("code", code).put("product_id", product.first).put("aantal", n)
            naam.text.toString().trim().takeIf { it.isNotEmpty() }?.let { body.put("naam", it) }
            prijs.text.toString().trim().takeIf { it.isNotEmpty() }?.let { body.put("inkoopprijs", it.replace(',', '.')) }
            activity.bezig {
                val antwoord = Api.post(activity, "/api/app/keuken/koppelen", body, verzoekId = verzoekId)
                dialoog.dismiss()
                activity.tril(60)
                klaar(antwoord)  // de scan meldt daarna zelf wat erbij komt
            }
        }
    }

    /** Er staat nog niet bij hoeveel er in deze zak of doos zit: één keer vragen (de site onthoudt het). */
    fun vraagAantal(activity: BasisActivity, code: String, omschrijving: String, eenheid: String, klaar: (JSONObject) -> Unit) {
        activity.tril(150)
        Cijferpad.vraag(activity, activity.getString(R.string.keuken_hoeveel_erin, omschrijving.substringBefore(',')),
            eenheid = eenheid, max = 4) { tekst ->
            val n = tekst.toIntOrNull()
            if (n == null || n < MIN_PER_VERPAKKING) return@vraag activity.melding(activity.getString(R.string.keuken_minstens_twee), lang = true)
            activity.bezig {
                val antwoord = Api.post(activity, "/api/app/keuken/verpakking", JSONObject().put("code", code).put("aantal", n),
                    herhaalbaar = true)
                activity.tril(60)
                klaar(antwoord)  // de scan meldt daarna zelf wat erbij komt
            }
        }
    }

    /** Een product zonder barcode: in welke verpakking komt het binnen, en hoeveel zit erin? klaar krijgt de
     * verpakkingen van het product (zoals "verpakkingen" bij /api/app/keuken). */
    fun vraagProductVerpakking(activity: BasisActivity, product: Pair<Int, String>, klaar: (List<JSONObject>) -> Unit) {
        val soort = veld(activity, activity.getString(R.string.keuken_verpakking_soort_hint),
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
        val aantal = veld(activity, activity.getString(R.string.koppel_aantal_hint), InputType.TYPE_CLASS_NUMBER)
        val inhoud = formulier(activity, listOf(
            activity.getString(R.string.keuken_verpakking_soort) to soort,
            activity.getString(R.string.keuken_hoeveel_erin_kort) to aantal,
        ))
        inhoud.addView(TextView(activity).apply {
            text = activity.getString(R.string.keuken_verpakking_uitleg, product.second)
            textSize = 12f
            setTextColor(activity.getColor(R.color.tekst_zacht))
            setPadding(0, BasisActivity.dp(activity, 10), 0, 0)
        }, 0)
        val dialoog = AlertDialog.Builder(activity)
            .setCustomTitle(activity.dialoogTitel(activity.getString(R.string.keuken_verpakking_instellen)))
            .setView(inhoud)
            .setNegativeButton(R.string.annuleren, null)
            .setPositiveButton(R.string.opslaan, null)
            .show()
        soort.requestFocus()
        dialoog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val n = aantal.text.toString().toIntOrNull()
            if (n == null || n < MIN_PER_VERPAKKING) return@setOnClickListener activity.melding(activity.getString(R.string.keuken_minstens_twee), lang = true)
            activity.bezig {
                val antwoord = Api.post(activity, "/api/app/keuken/product-verpakking",
                    JSONObject().put("product_id", product.first).put("naam", soort.text.toString().trim()).put("aantal", n),
                    herhaalbaar = true)
                dialoog.dismiss()
                activity.tril(60)
                activity.melding(antwoord.optString("melding"))
                klaar(antwoord.getJSONArray("verpakkingen").objecten())
            }
        }
    }

    private fun veld(activity: BasisActivity, hint: String, soort: Int) = EditText(activity).apply {
        this.hint = hint
        inputType = soort
        setSingleLine()
    }

    private fun formulier(activity: BasisActivity, velden: List<Pair<String, EditText>>): LinearLayout {
        val dp = activity.resources.displayMetrics.density
        return LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((22 * dp).toInt(), (4 * dp).toInt(), (22 * dp).toInt(), 0)
            for ((label, veld) in velden) {
                addView(TextView(activity).apply {
                    text = label
                    textSize = 12f
                    setTextColor(activity.getColor(R.color.tekst_zacht))
                    setPadding(0, (8 * dp).toInt(), 0, 0)
                })
                addView(veld)
            }
        }
    }
}
