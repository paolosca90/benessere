package com.benessere.app.alarm

import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * Sveglia locale di sicurezza. Non deduce le fasi del sonno e non controlla
 * la vibrazione Helio Strap (protocollo BLE ancora non confermato).
 */
object SmartAlarmScheduler {
    private const val PREFS = "benessere_alarm"
    private const val CHANNEL = "benessere_sveglie"
    private const val REQUEST = 18080
    private fun prefs(c: Context) = c.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun applyRemote(context: Context, cfg: JSONObject): String {
        require(cfg.optString("mode")=="fixed") { "Risveglio adattivo non ancora validato" }
        val enabled=cfg.getBoolean("enabled")
        val deadline=LocalTime.parse(cfg.getString("deadline"))
        val arr=cfg.getJSONArray("weekdays")
        val days=(0 until arr.length()).map { arr.getInt(it) }.toSet()
        require(days.isNotEmpty() && days.all { it in 1..7 })
        val revision=cfg.getInt("revision")
        require(revision>=0)
        if(enabled) ensurePermission(context)
        val committed=prefs(context).edit().putBoolean("enabled",enabled)
            .putString("deadline",deadline.toString())
            .putString("weekdays",days.sorted().joinToString(","))
            .putInt("revision",revision).commit()
        check(committed) { "Impossibile salvare la sveglia sul telefono" }
        if(enabled) scheduleNext(context) else cancelAll(context)
        return (if(enabled) "Sveglia telefonica programmata" else "Sveglia disattivata")+
            " · revisione "+revision
    }

    // Retrocompatibilità con L1: viene usato solo l'orario finale della finestra.
    fun schedule(context: Context,start: LocalDateTime,end: LocalDateTime,step: Long) {
        require(step>0 && !end.isBefore(start))
        ensurePermission(context)
        scheduleAt(context,end)
    }

    fun scheduleNext(context: Context) {
        val p=prefs(context)
        if(!p.getBoolean("enabled",false)) return
        ensurePermission(context)
        val deadline=LocalTime.parse(p.getString("deadline","07:00"))
        val weekdays=p.getString("weekdays","1,2,3,4,5,6,7")!!
            .split(",").mapNotNull { it.toIntOrNull() }.toSet()
        val now=LocalDateTime.now()
        val next=(0L..8L).map { now.toLocalDate().plusDays(it).atTime(deadline) }
            .firstOrNull { it.isAfter(now.plusSeconds(15)) && it.dayOfWeek.value in weekdays }
            ?: error("Nessun giorno disponibile")
        scheduleAt(context,next)
    }

    private fun ensurePermission(context: Context) {
        check(NotificationManagerCompat.from(context).areNotificationsEnabled()) {
            "Notifiche della sveglia disabilitate: autorizzale nelle impostazioni Android"
        }
        if(Build.VERSION.SDK_INT>=Build.VERSION_CODES.S) {
            val manager=context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            check(manager.canScheduleExactAlarms()) {
                "Autorizza 'Sveglie e promemoria' nelle impostazioni Android"
            }
        }
    }

    private fun pending(context: Context, code:Int=REQUEST): PendingIntent =
        PendingIntent.getBroadcast(context,code,
            Intent(context,AlarmReceiver::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

    private fun scheduleAt(context: Context,time:LocalDateTime) {
        val manager=context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        createChannel(context)
        val trigger=time.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
        manager.cancel(pending(context))
        manager.setAlarmClock(AlarmManager.AlarmClockInfo(trigger,pending(context)),pending(context))
    }

    fun cancelAll(context: Context,slots:Int=10) {
        val manager=context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        manager.cancel(pending(context))
        // Rimuovi anche le sveglie multiple create dalle versioni L1 precedenti.
        for(i in 0 until slots) {
            val old=PendingIntent.getBroadcast(context,1000+i,
                Intent(context,AlarmReceiver::class.java).putExtra("slot",i),
                PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE)
            if(old!=null) { manager.cancel(old); old.cancel() }
        }
    }

    fun rearmAfterBoot(context: Context) {
        if(prefs(context).getBoolean("enabled",false)) scheduleNext(context)
    }
    fun configuredStatus(context:Context):String {
        val p=prefs(context)
        return if(!p.getBoolean("enabled",false)) "Disattivata" else
            "Attiva sul telefono: "+p.getString("deadline","?")+
            " (rev "+p.getInt("revision",0)+")"
    }

    private fun createChannel(context: Context) {
        val nm=context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if(Build.VERSION.SDK_INT>=26) {
            val channel=NotificationChannel(CHANNEL,"Benessere — sveglie",
                NotificationManager.IMPORTANCE_HIGH).apply {
                setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM),
                    AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build())
                enableVibration(true)
            }
            nm.createNotificationChannel(channel)
        }
    }
}

class AlarmReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent) {
        val nm=context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(2000,NotificationCompat.Builder(context,"benessere_sveglie")
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("Benessere — sveglia")
            .setContentText("Allarme del telefono. Helio Strap non è controllato da Benessere.")
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_MAX).setAutoCancel(true).build())
        runCatching { SmartAlarmScheduler.scheduleNext(context) }
    }
}
class AlarmBootReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent) {
        if(intent.action==Intent.ACTION_BOOT_COMPLETED)
            runCatching { SmartAlarmScheduler.rearmAfterBoot(context) }
    }
}
