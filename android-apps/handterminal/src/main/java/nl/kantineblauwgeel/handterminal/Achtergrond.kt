package nl.kantineblauwgeel.handterminal

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** Werk dat door moet gaan als een scherm sluit, zoals de stand van een telling doorgeven bij pauzeren of afbreken.
 * Op het scherm zelf (lifecycleScope) zou het bij het sluiten worden afgebroken. */
object Achtergrond {
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
}
