package nl.kantineblauwgeel.tablet

import org.json.JSONObject

/** Uitverkocht op het prijzenscherm (2.0): per groep zoals op de tv, tik de schakelaar om een product doorgestreept
 * (met "Uitverkocht") te tonen. Raakt de voorraad niet. Zelfde als in de handterminal-app (/api/app/prijzenscherm). */
class UitverkochtActivity : LijstActivity() {

    override val pad = "/api/app/prijzenscherm"
    override val titel = R.string.titel_uitverkocht

    override fun toon(data: JSONObject) {
        val inhoud = b.inhoud
        val groepen = data.optJSONArray("groepen")
        if (groepen == null || groepen.length() == 0) Ui.tekst(Ui.kaart(inhoud), getString(R.string.geen_producten_op_scherm))
        for (i in 0 until (groepen?.length() ?: 0)) {
            val groep = groepen!!.getJSONObject(i)
            Ui.kop(inhoud, groep.optString("naam"))
            val kaart = Ui.kaart(inhoud)
            val producten = groep.getJSONArray("producten")
            for (j in 0 until producten.length()) {
                val p = producten.getJSONObject(j)
                Ui.regel(kaart, p.optString("naam"), if (p.optBoolean("uitverkocht")) getString(R.string.label_uitverkocht) else null,
                    Ui.schakelaar(this, p.optBoolean("uitverkocht")) { uit ->
                        stuur("/api/app/producten/${p.getInt("id")}/uitverkocht", JSONObject().put("uitverkocht", uit))
                    })
            }
        }
    }
}
