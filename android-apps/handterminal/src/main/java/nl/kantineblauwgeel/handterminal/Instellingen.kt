package nl.kantineblauwgeel.handterminal

import android.content.Context
import android.net.Uri

/** Wat de app onthoudt op het toestel. De sessie zelf zit in de cookies van de WebView (CookieManager); hier
 * staat alleen wie er is ingelogd en wanneer die voor het laatst iets deed, voor het automatisch uitloggen. */
class Instellingen(context: Context) {

    private val prefs = context.applicationContext.getSharedPreferences("handterminal", Context.MODE_PRIVATE)

    var basisUrl: String
        get() = prefs.getString("basis_url", null) ?: STANDAARD_URL
        set(waarde) = prefs.edit().putString("basis_url", waarde.trimEnd('/')).apply()

    val siteHost: String
        get() = Uri.parse(basisUrl).host ?: ""

    /** Na hoeveel minuten zonder aanraken of scannen de app uitlogt; 0 = nooit. */
    var uitlogMinuten: Int
        get() = prefs.getInt("uitlog_minuten", 15)
        set(waarde) = prefs.edit().putInt("uitlog_minuten", waarde).apply()

    var tekstGrootte: Int
        get() = prefs.getInt("tekst_grootte", 100)
        set(waarde) = prefs.edit().putInt("tekst_grootte", waarde).apply()

    var trillen: Boolean
        get() = prefs.getBoolean("trillen", true)
        set(waarde) = prefs.edit().putBoolean("trillen", waarde).apply()

    /** Naam van wie er nu is ingelogd, of null. */
    var naam: String?
        get() = prefs.getString("naam", null)
        set(waarde) = prefs.edit().putString("naam", waarde).apply()

    /** Wie er het laatst was ingelogd en waar die was: na automatisch uitloggen gaat dezelfde persoon daar verder. */
    var vorigeNaam: String?
        get() = prefs.getString("vorige_naam", null)
        set(waarde) = prefs.edit().putString("vorige_naam", waarde).apply()

    var vorigePagina: String?
        get() = prefs.getString("vorige_pagina", null)
        set(waarde) = prefs.edit().putString("vorige_pagina", waarde).apply()

    var laatsteActiviteit: Long
        get() = prefs.getLong("laatste_activiteit", 0L)
        set(waarde) = prefs.edit().putLong("laatste_activiteit", waarde).apply()

    fun isVerlopen(nu: Long = System.currentTimeMillis()): Boolean {
        val minuten = uitlogMinuten
        return minuten > 0 && nu - laatsteActiviteit > minuten * 60_000L
    }

    companion object {
        const val STANDAARD_URL = "https://www.kantineblauwgeel.nl"
        val UITLOG_KEUZES = intArrayOf(5, 10, 15, 30, 60, 0)
        val TEKST_KEUZES = intArrayOf(90, 100, 115, 130)
    }
}
