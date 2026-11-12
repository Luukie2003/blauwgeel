package nl.kantineblauwgeel.handterminal

import android.app.Activity
import android.content.Intent
import android.view.ViewGroup
import androidx.annotation.DrawableRes

/** Welke app dit is. Deze code is van de handterminal-app (de Zebra), maar de tablet-app ("Kantine Beheer",
 * android-apps/tablet) bouwt sinds 3.0 op dezelfde schermen. Op de tablet is er geen scanner en geen looplijst: tellen
 * (ook in de keuken) en de koppelronde doe je met de handterminal; Tellingen bekijken kan wel. De tablet heeft er een paar
 * eigen schermen voor de kantine-tv bij (acties, bardiensten, uitgelicht, wedstrijddag, het prijzenscherm), die hier op
 * naam worden geopend, zodat de handterminal-app ze niet hoeft te kennen. */
object App {

    val isTablet: Boolean = BuildConfig.APPLICATION_ID == "nl.kantineblauwgeel.tablet"

    /** Tellen met de looplijst (en in de keuken), en de koppelronde: alleen op de handterminal. */
    val metLooplijst: Boolean = !isTablet

    /** Hoe de app zich bij de site meldt (de User-Agent). */
    val userAgentNaam: String = if (isTablet) "KantineTablet" else "KantineHandterminal"

    /** Onder welke naam de site de nieuwste versie van deze app noemt (api_app_start). */
    val versieSleutel: String = if (isTablet) "tablet_versie" else "app_versie"

    /** Een eigen scherm van de tablet-app, op het startscherm bij Kantine en keuken. [sectie]: de rechten die nodig zijn. */
    class Extra(val naam: String, val uitleg: String, @DrawableRes val icoon: Int, val sectie: String, private val klasse: String) {
        fun open(activity: Activity) = activity.startActivity(Intent().setClassName(activity, "nl.kantineblauwgeel.tablet.$klasse"))
    }

    /** Zo breed staat de inhoud hooguit op de tablet (in dp); op een breder scherm in het midden. */
    private const val MAX_BREEDTE_DP = 920

    /** De inhoud van een scherm in het midden van een breed scherm: alles onder de kopbalk krijgt aan beide kanten
     * evenveel ruimte; de kopbalk zelf blijft over de hele breedte. Een lijst of scrollvak blijft over de hele breedte te
     * scrollen (clipToPadding uit). */
    fun centreer(activity: Activity) {
        val breedte = activity.resources.configuration.screenWidthDp
        if (breedte <= MAX_BREEDTE_DP + 48) return
        val root = activity.findViewById<ViewGroup>(android.R.id.content)?.getChildAt(0) as? ViewGroup ?: return
        val rand = ((breedte - MAX_BREEDTE_DP) / 2 * activity.resources.displayMetrics.density).toInt()
        for (i in 0 until root.childCount) {
            val kind = root.getChildAt(i)
            if (kind.id == R.id.balk) continue
            kind.setPaddingRelative(kind.paddingStart + rand, kind.paddingTop, kind.paddingEnd + rand, kind.paddingBottom)
            (kind as? ViewGroup)?.clipToPadding = false
        }
    }

    val tabletSchermen: List<Extra> = if (!isTablet) emptyList() else listOf(
        Extra("Prijzenscherm", "Welke producten er op de prijzen-tv staan, en hun prijs", R.drawable.ic_kiosk, "kantine_tv", "ProductenActivity"),
        Extra("Acties", "De acties op de tv: aanmaken, aanpassen en wanneer ze er staan", R.drawable.ic_kiosk, "kantine_tv", "ActiesActivity"),
        Extra("Bardiensten", "Wie er achter de bar staat, op de tv", R.drawable.ic_agenda, "kantine_tv", "BardienstenActivity"),
        Extra("Uitgelicht", "Het product dat de tv extra laat zien", R.drawable.ic_kiosk, "kantine_tv", "UitgelichtActivity"),
        Extra("Wedstrijddag", "De welkomst op de tv bij een thuiswedstrijd", R.drawable.ic_agenda, "kantine_tv", "WedstrijddagActivity"),
    )
}
