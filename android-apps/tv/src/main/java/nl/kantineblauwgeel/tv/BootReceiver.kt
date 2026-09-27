package nl.kantineblauwgeel.tv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Zorgt dat de tv na een stroomstoring of herstart vanzelf weer het laatst
 * gekozen kioskscherm toont, zonder dat iemand de afstandsbediening pakt.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        if (!Prefs.isAutoStartEnabled(context)) return

        val scherm = Screens.opSleutel(Prefs.getLastSchermSleutel(context))
        val playerIntent = PlayerActivity.intentVoor(context, scherm).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(playerIntent)
    }
}
