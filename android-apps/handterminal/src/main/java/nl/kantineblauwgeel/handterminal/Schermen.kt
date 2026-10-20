package nl.kantineblauwgeel.handterminal

import android.content.Intent

/** Welk scherm van de app hoort bij een pagina van de site (het endpoint)? Voor de taken die een beheerder klaarzet:
 * die verwijzen naar een pagina. Heeft de app er geen scherm voor, dan kan het niet in de app (zie nietInApp). */
object Schermen {

    private val schermen: Map<String, (BasisActivity) -> Unit> = buildMap {
        for (e in listOf("tellen", "tellen_lopen", "tellen_lopen_starten", "tellen_lopen_hervatten", "tellen_lopen_controleren")) {
            put(e) { it.startActivity(Intent(it, TellenActivity::class.java)) }
        }
        for (e in listOf("kassa_tellen", "kassa_geschiedenis")) put(e) { GeldActivity.open(it, GeldActivity.KASSA) }
        for (e in listOf("kluis_tellen", "kluis_geschiedenis")) put(e) { GeldActivity.open(it, GeldActivity.KLUIS) }
        for (e in listOf("keuken_voorraad", "keuken_tellen", "keuken_inboeken", "keuken_tellingen_overzicht", "frituurvet_vervangen")) {
            put(e) { KeukenActivity.open(it) }
        }
        for (e in listOf("facturen_overzicht", "factuur_start", "levering_inboeken")) {
            put(e) { it.startActivity(Intent(it, FacturenActivity::class.java)) }
        }
        for (e in listOf("producten_lijst", "voorraadoverzicht")) put(e) { ProductenActivity.open(it, ProductenActivity.Modus.VOORRAAD) }
        put("boeken") { ProductenActivity.open(it, ProductenActivity.Modus.BOEKEN) }
        put("bestellijst") { BestellijstActivity.open(it) }
        put("boodschappenlijst") { BoodschappenActivity.open(it) }
        put("prognose_pagina") { PrognoseActivity.open(it) }
        put("agenda") { AgendaActivity.open(it) }
        put("barcodes_overzicht") { BarcodesActivity.open(it) }
        put("tellingen_overzicht") { TellingenActivity.open(it) }
        put("geschiedenis") { GeschiedenisActivity.open(it) }
        put("bijzonderheden") { PrikbordActivity.open(it) }
        put("club_van_20_aanmeldingen") { AanmeldingenActivity.open(it) }
        put("timer_pagina") { TimerActivity.open(it) }
    }

    fun heeft(endpoint: String?) = endpoint != null && endpoint in schermen

    /** Het scherm openen; false als de app er geen heeft. */
    fun open(activity: BasisActivity, endpoint: String?): Boolean {
        val scherm = endpoint?.let { schermen[it] } ?: return false
        scherm(activity)
        return true
    }
}
