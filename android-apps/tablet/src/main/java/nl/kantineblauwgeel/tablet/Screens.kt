package nl.kantineblauwgeel.tablet

import android.content.Context

data class Scherm(val titel: String, val pad: String)

object Screens {
    val PRIJZEN = Scherm("Prijzenscherm", "/kiosk/prijzen")
    val DIAS = Scherm("Dia's & sponsoren", "/kiosk/scherm")
    val GEDEELD = Scherm("Kantine-tv (gedeeld)", "/kiosk/tv")

    fun url(context: Context, scherm: Scherm): String = Prefs.getBaseUrl(context) + scherm.pad
}
