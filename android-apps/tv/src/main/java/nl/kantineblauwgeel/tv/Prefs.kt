package nl.kantineblauwgeel.tv

import android.content.Context

object Prefs {
    private const val NAAM = "kantine_tv_prefs"
    // Dezelfde sleutels als de vaste schermen van de app tot 1.1 (zoom_percent_prijzen, zoom_percent_dias): een zoom die
    // daar al op de tv was ingesteld, blijft zo gewoon bewaard.
    private const val KEY_ZOOM_PREFIX = "zoom_percent_"
    private const val KEY_GEKOPPELD_URL = "gekoppeld_url"

    const val DEFAULT_ZOOM = 100
    const val PRIJZEN = "prijzen"
    const val DIAS = "dias"

    private fun prefs(context: Context) =
        context.getSharedPreferences(NAAM, Context.MODE_PRIVATE)

    /** De grootte die op de site voor deze tv is gekozen (zie PlayerActivity.Brug). */
    fun getSiteZoom(context: Context): Int = prefs(context).getInt(KEY_ZOOM_PREFIX + Screens.GEKOPPELD, DEFAULT_ZOOM)

    fun setSiteZoom(context: Context, waarde: Int) {
        prefs(context).edit().putInt(KEY_ZOOM_PREFIX + Screens.GEKOPPELD, waarde).apply()
    }

    /** De eigen zoom van deze tv voor de prijzenlijst of de dia's (Instellingen, de OK-knop), of null: dan de site. */
    fun getEigenZoom(context: Context, scherm: String): Int? {
        val instellingen = prefs(context)
        return if (instellingen.contains(KEY_ZOOM_PREFIX + scherm)) instellingen.getInt(KEY_ZOOM_PREFIX + scherm, DEFAULT_ZOOM) else null
    }

    fun setEigenZoom(context: Context, scherm: String, waarde: Int?) {
        val bewerk = prefs(context).edit()
        if (waarde == null) bewerk.remove(KEY_ZOOM_PREFIX + scherm) else bewerk.putInt(KEY_ZOOM_PREFIX + scherm, waarde)
        bewerk.apply()
    }

    /** De zoom die nu geldt voor dit scherm: de eigen zoom van de tv, anders die van de site. */
    fun zoomVoor(context: Context, scherm: String?): Int =
        scherm?.let { getEigenZoom(context, it) } ?: getSiteZoom(context)

    /** Het eigen adres van deze tv als gekoppeld scherm (/kiosk/t/<token>), zodra de site dat heeft gegeven. Zo blijft
     * de koppeling ook bewaard als de opslag van de webweergave ooit leeg raakt. */
    fun getGekoppeldUrl(context: Context): String? = prefs(context).getString(KEY_GEKOPPELD_URL, null)

    fun setGekoppeldUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_GEKOPPELD_URL, url).apply()
    }
}
