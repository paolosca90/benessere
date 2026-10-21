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
import androidx.core.app.NotificationCompat
import java.time.LocalDateTime
import java.time.ZoneId

/**
 * Sveglia intelligente — livello 1 (previsionale).
 *
 * Nella finestra di risveglio (es. 06:30–07:00) programma N sveglie a distanza
 * di `stepMinutes`: la prima che incontra il momento buio giusto... per ora
 * suona e l'utente decide se rialzarsi o aspettare la successiva (che va
 * annullata alzandosi). Il livello 2 (FC live nella finestra) la sostituirà.
 */
object SmartAlarmScheduler {

    private const val CHANNEL_ID = "benessere_sveglie"
    private const val EXTRA_SLOT = "slot"

    fun schedule(context: Context, windowStart: LocalDateTime, windowEnd: LocalDateTime, stepMinutes: Long) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        createChannel(context)

        val slots = generateSequence(windowStart) { it.plusMinutes(stepMinutes) }
            .takeWhile { !it.isAfter(windowEnd) }
            .toList()

        slots.forEachIndexed { index, time ->
            val pi = pendingIntent(context, index, time)
            val triggerAtMillis = time.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli()
            // setAlarmClock: massima priorità di sveglia, compare nel pannello sistema
            am.setAlarmClock(
                AlarmManager.AlarmClockInfo(triggerAtMillis, nextAlarmPi(context)),
                pi
            )
        }
    }

    fun cancelAll(context: Context, slots: Int = 10) {
        val am = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        for (i in 0 until slots) {
            am.cancel(pendingIntent(context, i, null))
        }
    }

    private fun nextAlarmPi(context: Context): PendingIntent = pendingIntent(context, 0, null)

    private fun pendingIntent(context: Context, slot: Int, time: LocalDateTime?): PendingIntent {
        val intent = Intent(context, AlarmReceiver::class.java).putExtra(EXTRA_SLOT, slot)
        return PendingIntent.getBroadcast(
            context,
            1000 + slot,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    private fun createChannel(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val sound = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Sveglia intelligente",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            setSound(
                sound,
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
            enableVibration(true)
        }
        nm.createNotificationChannel(channel)
    }
}

class AlarmReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val slot = intent.getIntExtra("slot", 0)
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val notification = NotificationCompat.Builder(context, "benessere_sveglie")
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle("Benessere — sveglia")
            .setContentText("Finestra di risveglio: slot ${slot + 1}. Alzati e ignora le successive.")
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setAutoCancel(true)
            .build()

        nm.notify(2000 + slot, notification)
    }
}
