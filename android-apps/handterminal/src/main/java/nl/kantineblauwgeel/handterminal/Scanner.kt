package nl.kantineblauwgeel.handterminal

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.core.content.ContextCompat

/** De ingebouwde barcodescanner van de Zebra, via DataWedge.
 *
 * Standaard "typt" DataWedge een scan in het veld dat de focus heeft. Staat er geen veld open, dan raakt de scan
 * kwijt. Daarom maakt de app een eigen DataWedge-profiel: zolang de app voorin staat, komen scans als bericht
 * binnen (en niet als toetsaanslagen), en beslist de app zelf waar de scan heen gaat (zie assets/scan.js).
 * In andere apps, zoals Chrome, blijft de scanner gewoon typen.
 *
 * Werkt met DataWedge 6.4 en nieuwer: één plugin per SET_CONFIG, zodat ook oudere versies het snappen. Op een
 * toestel zonder DataWedge gebeurt er niets en werkt de app gewoon met het toetsenbord. */
object Scanner {

    const val SCAN_ACTIE = "nl.kantineblauwgeel.handterminal.SCAN"
    private const val PROFIEL = "Kantine Handterminal"
    private const val DATAWEDGE = "com.symbol.datawedge"
    private const val API_ACTIE = "com.symbol.datawedge.api.ACTION"
    private const val EXTRA_GEGEVENS = "com.symbol.datawedge.data_string"
    private const val EXTRA_SOORT = "com.symbol.datawedge.label_type"

    fun isAanwezig(context: Context): Boolean = try {
        context.packageManager.getPackageInfo(DATAWEDGE, 0)
        true
    } catch (e: PackageManager.NameNotFoundException) {
        false
    }

    /** Maakt het profiel aan of zet het goed. Kan veilig bij elke start: dezelfde instellingen opnieuw. */
    fun stelIn(context: Context) {
        if (!isAanwezig(context)) return
        val app = Bundle().apply {
            putString("PACKAGE_NAME", context.packageName)
            putStringArray("ACTIVITY_LIST", arrayOf("*"))
        }
        stuurConfig(context, "CREATE_IF_NOT_EXIST", null) { putParcelableArray("APP_LIST", arrayOf(app)) }
        stuurConfig(context, "UPDATE", plugin("BARCODE", "scanner_selection" to "auto", "scanner_input_enabled" to "true",
            // QR-codes: het schaplabel en de koppelcode op een nieuwe tv.
            "decoder_qrcode" to "true"))
        stuurConfig(
            context, "UPDATE",
            plugin(
                "INTENT",
                "intent_output_enabled" to "true",
                "intent_action" to SCAN_ACTIE,
                "intent_category" to Intent.CATEGORY_DEFAULT,
                "intent_delivery" to "2", // 2 = als broadcast
            ),
        )
        stuurConfig(context, "UPDATE", plugin("KEYSTROKE", "keystroke_output_enabled" to "false"))
    }

    private fun plugin(naam: String, vararg parameters: Pair<String, String>) = Bundle().apply {
        putString("PLUGIN_NAME", naam)
        putString("RESET_CONFIG", "true")
        putBundle("PARAM_LIST", Bundle().apply { parameters.forEach { (k, v) -> putString(k, v) } })
    }

    private fun stuurConfig(context: Context, modus: String, plugin: Bundle?, extra: Bundle.() -> Unit = {}) {
        val profiel = Bundle().apply {
            putString("PROFILE_NAME", PROFIEL)
            putString("PROFILE_ENABLED", "true")
            putString("CONFIG_MODE", modus)
            if (plugin != null) putBundle("PLUGIN_CONFIG", plugin)
            extra()
        }
        context.sendBroadcast(
            Intent(API_ACTIE).setPackage(DATAWEDGE).putExtra("com.symbol.datawedge.api.SET_CONFIG", profiel),
        )
    }

    /** Zet de scanner aan alsof de scanknop wordt ingedrukt (voor de scanknop op de site). */
    fun startScan(context: Context) {
        context.sendBroadcast(
            Intent(API_ACTIE).setPackage(DATAWEDGE)
                .putExtra("com.symbol.datawedge.api.SOFT_SCAN_TRIGGER", "START_SCANNING"),
        )
    }

    /** Luistert naar scans zolang de activity voorin staat; geeft de code en het soort barcode door. */
    fun luister(context: Context, bijScan: (code: String, soort: String?) -> Unit): BroadcastReceiver {
        val ontvanger = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                val code = intent.getStringExtra(EXTRA_GEGEVENS)?.trim()?.trimEnd('\r', '\n') ?: return
                if (code.isNotEmpty()) bijScan(code, intent.getStringExtra(EXTRA_SOORT))
            }
        }
        val filter = IntentFilter(SCAN_ACTIE).apply { addCategory(Intent.CATEGORY_DEFAULT) }
        // EXPORTED: de scans komen van een andere app (DataWedge).
        ContextCompat.registerReceiver(context, ontvanger, filter, ContextCompat.RECEIVER_EXPORTED)
        return ontvanger
    }
}
