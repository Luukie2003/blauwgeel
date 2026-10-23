package nl.kantineblauwgeel.tablet

import org.json.JSONObject

/** De tv's in de kantine (2.0): per tv of hij aan staat en wat hij toont (prijzenlijst, dia's of het wisselscherm),
 * opnieuw laden, en de wisselknop: wat de wisselschermen nu tonen. Zelfde als Kantine-tv op de site en in de
 * handterminal-app (/api/app/kantine-tv). Een nieuwe tv koppelen gaat op de site of met de handterminal (QR-code). */
class TvsActivity : LijstActivity() {

    override val pad = "/api/app/kantine-tv"
    override val titel = R.string.titel_tvs

    override fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        Ui.kop(inhoud, getString(R.string.wisselknop))
        val wissel = Ui.kaart(inhoud)
        Ui.regel(wissel, getString(R.string.wisselschermen_tonen), getString(R.string.wissel_uitleg),
            Ui.keuze(this, listOf("prijzen" to getString(R.string.prijzenlijst), "dias" to getString(R.string.dias)), data.optString("wissel")) {
                stuur("/api/app/kantine-tv/wissel", JSONObject().put("toont", it))
            })

        val schermen = data.optJSONArray("schermen")?.let { a -> (0 until a.length()).map { a.getJSONObject(it) } }.orEmpty()
            .map { it.optString("sleutel") to it.optString("naam").substringBefore(" (") }
        val tvs = data.optJSONArray("tvs")?.let { a -> (0 until a.length()).map { a.getJSONObject(it) } }.orEmpty()
        Ui.kop(inhoud, getString(R.string.tvs_kop, tvs.size))
        val kaart = Ui.kaart(inhoud)
        if (tvs.isEmpty()) Ui.tekst(kaart, getString(R.string.geen_tvs))
        for (tv in tvs) {
            val id = tv.getInt("id")
            val status = tv.optJSONObject("status")
            Ui.regel(kaart, tv.optString("naam"), status?.optString("tekst"),
                Ui.keuze(this, schermen, tv.optString("scherm")) {
                    stuur("/api/app/kantine-tv/tvs/$id/scherm", JSONObject().put("scherm", it))
                }).addView(Ui.knop(this, getString(R.string.opnieuw_laden)) {
                stuur("/api/app/kantine-tv/tvs/$id/herladen")
            })
        }
        Ui.tekst(kaart, getString(R.string.tv_koppelen_uitleg))
    }
}
