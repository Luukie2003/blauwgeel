package nl.kantineblauwgeel.tv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Zorgt dat de tv na een stroomstoring of herstart vanzelf weer zijn gekoppelde scherm toont, zonder dat iemand de
 * afstandsbediening pakt.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        context.startActivity(PlayerActivity.intent(context).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}
