package nl.kantineblauwgeel.tablet

import org.json.JSONObject

/** De diashow (2.0): hele onderdelen (dia's en mededelingen, Club van 20, wedstrijden, standen, Man of the Match) en
 * losse dia's aan of uit. Dia's maken en bewerken gaat op de site. Zelfde als in de handterminal-app. */
class DiasActivity : LijstActivity() {

    override val pad = "/api/app/kantine-tv/dias"
    override val titel = R.string.titel_dias

    override fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        Ui.kop(inhoud, getString(R.string.onderdelen))
        val blokken = Ui.kaart(inhoud)
        data.optJSONArray("blokken")?.let { a ->
            for (i in 0 until a.length()) {
                val blok = a.getJSONObject(i)
                Ui.regel(blokken, blok.optString("naam"), null, Ui.schakelaar(this, blok.optBoolean("aan")) { aan ->
                    stuur("/api/app/kantine-tv/dia-blokken/${blok.optString("sleutel")}", JSONObject().put("aan", aan))
                })
            }
        }
        Ui.kop(inhoud, getString(R.string.losse_dias))
        val kaart = Ui.kaart(inhoud)
        val dias = data.optJSONArray("dias")
        if (dias == null || dias.length() == 0) Ui.tekst(kaart, getString(R.string.geen_dias))
        for (i in 0 until (dias?.length() ?: 0)) {
            val dia = dias!!.getJSONObject(i)
            val periode = when (dia.optString("periode")) {
                "voorbij" -> getString(R.string.dia_voorbij)
                "later" -> getString(R.string.dia_later, dia.optString("vanaf"))
                else -> null
            }
            Ui.regel(kaart, dia.optString("titel").ifEmpty { getString(R.string.dia_zonder_titel) },
                listOfNotNull(dia.optString("soort"), periode).joinToString(" · "),
                Ui.schakelaar(this, dia.optBoolean("actief")) { aan ->
                    stuur("/api/app/kantine-tv/dias/${dia.getInt("id")}", JSONObject().put("actief", aan))
                })
        }
    }
}
