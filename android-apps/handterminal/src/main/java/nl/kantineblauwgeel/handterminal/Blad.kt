package nl.kantineblauwgeel.handterminal

import android.annotation.SuppressLint
import android.view.Gravity
import android.view.MotionEvent
import android.view.WindowManager
import android.widget.LinearLayout
import androidx.annotation.DrawableRes
import androidx.appcompat.app.AppCompatDialog
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import nl.kantineblauwgeel.handterminal.databinding.DialogOnderwerpBinding

/** Een blad dat van onderen omhoog schuift, met bovenin een navy kop (icoon, titel, regel eronder) en daaronder wat
 * [vul] erin zet. Dicht met terug, door ernaast te tikken of door de kop omlaag te vegen (dan [bijDicht]); gaat het
 * scherm zelf dicht, bijvoorbeeld bij automatisch uitloggen, dan het blad ook. Zo opent een onderwerp op het
 * startscherm, en een product op de bestellijst. */
object Blad {

    class Open(val dialoog: AppCompatDialog, val binding: DialogOnderwerpBinding) {
        fun sluit() {
            if (dialoog.isShowing) dialoog.dismiss()
        }
    }

    @SuppressLint("ClickableViewAccessibility")  // vegen is een extra; terug en ernaast tikken werken ook
    fun toon(
        activity: BasisActivity,
        titel: String,
        sub: String,
        @DrawableRes icoon: Int,
        bijDicht: (() -> Unit)? = null,
        vul: (inhoud: LinearLayout, blad: Open) -> Unit,
    ): Open {
        val binding = DialogOnderwerpBinding.inflate(activity.layoutInflater)
        val dialoog = AppCompatDialog(activity, R.style.Blad)
        val open = Open(dialoog, binding)
        binding.bladIcoon.setImageResource(icoon)
        binding.bladTitel.text = titel
        binding.bladSub.text = sub
        vul(binding.bladLijst, open)
        // De kop omlaag vegen: het blad gaat mee, en verder dan een kwart is dicht.
        var beginY = 0f
        // Eén keer sluiten: tijdens dismiss() krijgt de kop zelf nog een ACTION_CANCEL (het venster gaat weg), nog voordat
        // isShowing false is. Twee keer dismiss() laat de app vastlopen.
        var gesloten = false
        binding.bladKop.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> beginY = e.rawY
                MotionEvent.ACTION_MOVE -> if (!gesloten) binding.root.translationY = maxOf(0f, e.rawY - beginY)
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> when {
                    gesloten -> Unit
                    binding.root.translationY > binding.root.height / 4f -> {
                        gesloten = true
                        dialoog.dismiss()
                    }
                    else -> binding.root.animate().translationY(0f).setDuration(150).start()
                }
            }
            true
        }
        dialoog.setContentView(binding.root)
        dialoog.setCanceledOnTouchOutside(true)
        dialoog.window?.apply {
            setLayout(WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT)
            setGravity(Gravity.BOTTOM)
        }
        // Sluit het scherm (bijvoorbeeld automatisch uitloggen), dan het blad ook.
        val bijSluiten = LifecycleEventObserver { _, gebeurtenis -> if (gebeurtenis == Lifecycle.Event.ON_DESTROY) open.sluit() }
        activity.lifecycle.addObserver(bijSluiten)
        dialoog.setOnDismissListener {
            activity.lifecycle.removeObserver(bijSluiten)
            bijDicht?.invoke()
        }
        activity.tril(15)
        dialoog.show()
        return open
    }
}
