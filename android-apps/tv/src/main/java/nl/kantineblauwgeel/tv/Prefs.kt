package nl.kantineblauwgeel.tv

import android.content.Context

object Prefs {
    private const val NAAM = "kantine_tv_prefs"
    private const val KEY_ZOOM = "zoom_percent"
    private const val KEY_LAST_URL = "last_url"
    private const val KEY_AUTO_START = "auto_start_last"

    const val DEFAULT_ZOOM = 100

    private fun prefs(context: Context) =
        context.getSharedPreferences(NAAM, Context.MODE_PRIVATE)

    fun getZoom(context: Context): Int =
        prefs(context).getInt(KEY_ZOOM, DEFAULT_ZOOM)

    fun setZoom(context: Context, waarde: Int) {
        prefs(context).edit().putInt(KEY_ZOOM, waarde).apply()
    }

    fun getLastUrl(context: Context): String? =
        prefs(context).getString(KEY_LAST_URL, null)

    fun setLastUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_LAST_URL, url).apply()
    }

    fun isAutoStartEnabled(context: Context): Boolean =
        prefs(context).getBoolean(KEY_AUTO_START, true)

    fun setAutoStartEnabled(context: Context, waarde: Boolean) {
        prefs(context).edit().putBoolean(KEY_AUTO_START, waarde).apply()
    }
}
