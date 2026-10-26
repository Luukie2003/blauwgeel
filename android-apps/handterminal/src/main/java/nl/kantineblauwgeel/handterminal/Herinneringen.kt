package nl.kantineblauwgeel.handterminal

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.AlarmManagerCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

/** De herinnering om te bestellen: een notificatie op het toestel, ook als de app dicht is, een paar uur voor het
 * uiterste bestelmoment van een leverancier ("Vandaag bestellen bij Sligro, vóór 16:00").
 *
 * De site geeft bij elk startscherm de bestelmomenten van de komende dagen mee (bestelvoorstel.bestelmomenten op de
 * site): wanneer, hoeveel producten er klaarstaan en of er al besteld is. De app bewaart die en zet voor elk moment een
 * wekker (AlarmManager); die gaat af in [HerinneringOntvanger], ook na een herstart van het toestel. Op de achtergrond
 * vraagt de app niets aan de site: wie uitgelogd is, heeft geen sessie. Het aantal is dus dat van de laatste keer dat
 * de app open was. Uit te zetten in Instellingen. */
object Herinneringen {

    const val ACTIE = "nl.kantineblauwgeel.handterminal.HERINNERING"
    private const val KANAAL = "bestellen"
    private const val PREFS = "herinneringen"
    private val formaat get() = SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US)

    fun tijd(tekst: String?): Long? = try {
        tekst?.let { formaat.parse(it)?.time }
    } catch (e: Exception) {
        null
    }

    /** De bestelmomenten van het startscherm bewaren en de wekkers opnieuw zetten. */
    fun plan(context: Context, momenten: JSONArray?) {
        if (momenten == null) return
        prefs(context).edit().putString("momenten", momenten.toString()).apply()
        planOpnieuw(context)
    }

    /** De wekkers zetten voor de bewaarde momenten (na een herstart, of als de herinnering weer aan gaat). */
    fun planOpnieuw(context: Context) {
        wis(context)
        if (!Instellingen(context).bestelHerinnering) return
        val momenten = try {
            JSONArray(prefs(context).getString("momenten", "[]"))
        } catch (e: Exception) {
            JSONArray()
        }
        val wekker = context.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
        val nu = System.currentTimeMillis()
        var aantal = 0
        momenten.objecten().forEach { m ->
            val wanneer = tijd(m.tekstOfNull("herinnering")) ?: return@forEach
            val uiterst = tijd(m.tekstOfNull("uiterst")) ?: return@forEach
            if (m.optBoolean("al_besteld") || uiterst <= nu || wanneer <= nu - 60_000) return@forEach
            AlarmManagerCompat.setAndAllowWhileIdle(wekker, AlarmManager.RTC_WAKEUP, maxOf(wanneer, nu + 5_000),
                wekkerIntent(context, aantal, m))
            aantal++
        }
        prefs(context).edit().putInt("gezet", aantal).apply()
    }

    /** Alle gezette wekkers weghalen. */
    fun wis(context: Context) {
        val wekker = context.getSystemService(Context.ALARM_SERVICE) as? AlarmManager ?: return
        repeat(prefs(context).getInt("gezet", 0)) { wekker.cancel(wekkerIntent(context, it, null)) }
        prefs(context).edit().putInt("gezet", 0).apply()
    }

    private fun wekkerIntent(context: Context, nummer: Int, moment: JSONObject?): PendingIntent {
        val intent = Intent(context, HerinneringOntvanger::class.java).setAction(ACTIE)
        moment?.let { intent.putExtra("moment", it.toString()) }
        return PendingIntent.getBroadcast(context, nummer, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    /** "Vandaag", "Morgen" of de dag, voor het uiterste moment. */
    fun wanneerTekst(context: Context, uiterst: Long, uiterstTekst: String): String {
        val dag = Calendar.getInstance().apply { timeInMillis = uiterst }
        val vandaag = Calendar.getInstance()
        val morgen = Calendar.getInstance().apply { add(Calendar.DAY_OF_YEAR, 1) }
        fun zelfde(a: Calendar, b: Calendar) = a.get(Calendar.YEAR) == b.get(Calendar.YEAR) && a.get(Calendar.DAY_OF_YEAR) == b.get(Calendar.DAY_OF_YEAR)
        return when {
            zelfde(dag, vandaag) -> context.getString(R.string.vandaag)
            zelfde(dag, morgen) -> context.getString(R.string.morgen)
            else -> uiterstTekst.substringBeforeLast(' ')
        }
    }

    /** De notificatie zelf (vanuit [HerinneringOntvanger]). */
    fun toon(context: Context, moment: JSONObject) {
        if (!Instellingen(context).bestelHerinnering) return
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        if (Build.VERSION.SDK_INT >= 26) {
            val beheer = context.getSystemService(NotificationManager::class.java)
            beheer.createNotificationChannel(NotificationChannel(KANAAL, context.getString(R.string.kanaal_bestellen), NotificationManager.IMPORTANCE_DEFAULT))
        }
        val uiterst = tijd(moment.tekstOfNull("uiterst")) ?: return
        val leverancier = moment.optString("leverancier")
        val wanneer = wanneerTekst(context, uiterst, moment.optString("uiterst_tekst"))
        val aantal = moment.optInt("aantal")
        val titel = context.getString(R.string.herinnering_titel, wanneer, leverancier).replaceFirstChar { it.uppercase() }
        val tekst = context.getString(R.string.herinnering_voor, moment.optString("tijd"), moment.optString("levering_tekst")) + " " +
            (if (aantal > 0) context.resources.getQuantityString(R.plurals.herinnering_aantal, aantal, aantal)
            else context.getString(R.string.herinnering_niets))
        // Tik: de app openen (inloggen als dat nodig is) en dan de bestellijst.
        val openen = PendingIntent.getActivity(
            context, moment.optInt("leverancier_id"),
            Intent(context, InlogActivity::class.java).putExtra(InlogActivity.EXTRA_OPEN, InlogActivity.OPEN_BESTELLIJST)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val melding = NotificationCompat.Builder(context, KANAAL)
            .setSmallIcon(R.drawable.ic_bestellijst)
            .setColor(ContextCompat.getColor(context, R.color.navy))
            .setContentTitle(titel)
            .setContentText(tekst)
            .setStyle(NotificationCompat.BigTextStyle().bigText(tekst))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentIntent(openen)
            .setAutoCancel(true)
            .setWhen(Date().time)
            .build()
        try {
            NotificationManagerCompat.from(context).notify(1000 + moment.optInt("leverancier_id"), melding)
        } catch (e: SecurityException) {
            // Geen toestemming voor meldingen: dan staat hij alleen op het startscherm.
        }
    }

    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}

/** De wekker van een herinnering gaat af (zie [Herinneringen]); na een herstart van het toestel: alles opnieuw zetten. */
class HerinneringOntvanger : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Herinneringen.ACTIE -> intent.getStringExtra("moment")?.let {
                try {
                    Herinneringen.toon(context, JSONObject(it))
                } catch (e: Exception) {
                    // Een kapotte herinnering: overslaan.
                }
            }
            Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED -> Herinneringen.planOpnieuw(context)
        }
    }
}
