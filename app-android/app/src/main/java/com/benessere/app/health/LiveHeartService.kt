package com.benessere.app.health

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.benessere.app.MainActivity
import com.benessere.app.ble.HuamiBleClient

/** In-process UI status only; no fabricated samples or persistent medical history. */
object LiveHeartRuntime {
    var running by mutableStateOf(false)
        internal set
    var bpm by mutableStateOf<Int?>(null)
        internal set
    var status by mutableStateOf("Ricevitore Bluetooth non avviato.")
        internal set
}

/**
 * Explicitly started, visible connected-device foreground service.
 * The BLE subscription and HTTPS uploader outlive the Compose screen.
 * No auto-start at boot, no pairing commands and no health sample replay.
 */
class LiveHeartService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var client: HuamiBleClient
    private lateinit var uploader: LiveHeartUploader
    private var address = ""
    private var active = false
    private var ready = false
    private var retryCount = 0
    private var lastAttempt = 0L
    private var lastHeart = 0L
    private var retryQueued = false

    private val retryTask = Runnable {
        retryQueued = false
        if (active) connect()
    }
    private val watchdog = object : Runnable {
        override fun run() {
            if (!active) return
            val now = SystemClock.elapsedRealtime()
            val timeout = if (ready) 45_000L else 20_000L
            val since = if (ready && lastHeart > 0L) lastHeart else lastAttempt
            if (since > 0L && now - since > timeout && !retryQueued) {
                updateStatus("Nessun dato FC recente: ripristino Bluetooth…")
                ready = false
                client.disconnect()
                scheduleRetry()
            }
            handler.postDelayed(this, 5_000L)
        }
    }

    override fun onCreate() {
        super.onCreate()
        client = HuamiBleClient(applicationContext)
        uploader = LiveHeartUploader(applicationContext)
        client.listener = object : HuamiBleClient.Listener {
            override fun onLog(line: String) {
                // Do not log BLE MACs, secrets or health readings into Logcat.
            }
            override fun onHeartRate(bpm: Int) {
                if (!active || !uploader.enabled()) return
                lastHeart = SystemClock.elapsedRealtime()
                ready = true
                retryCount = 0
                LiveHeartRuntime.bpm = bpm
                updateStatus("FC Bluetooth ricevuta; invio alla dashboard…")
                uploader.offer(bpm) { message ->
                    if (active) updateStatus(message)
                }
            }
            override fun onAuthResult(success: Boolean) { /* standard 180D has no Huami auth */ }
            override fun onLinkState(connected: Boolean, status: Int) {
                if (!active) return
                if (connected) {
                    updateStatus("Bluetooth connesso; attendo il sensore FC.")
                } else {
                    ready = false
                    LiveHeartRuntime.bpm = null
                    updateStatus("Bluetooth disconnesso (GATT $status); riconnessione…")
                    scheduleRetry()
                }
            }
            override fun onStreamReady() {
                if (!active) return
                ready = true
                updateStatus("Notifiche FC attivate; attendo dati reali.")
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action != ACTION_START || !uploader.enabled() || !hasBluetoothPermission()) {
            updateStatus("Avvio annullato: autorizzazione Bluetooth o consenso invio assente.")
            stopSelf()
            return START_NOT_STICKY
        }
        val target = intent.getStringExtra(EXTRA_ADDRESS).orEmpty()
        if (!android.bluetooth.BluetoothAdapter.checkBluetoothAddress(target)) {
            updateStatus("Indirizzo BLE non valido. Scansiona di nuovo.")
            stopSelf()
            return START_NOT_STICKY
        }
        createChannel()
        startForeground(NOTIFICATION_ID, notification("Monitoraggio Bluetooth attivo"))
        handler.removeCallbacks(retryTask)
        handler.removeCallbacks(watchdog)
        retryQueued = false
        active = true
        LiveHeartRuntime.running = true
        LiveHeartRuntime.bpm = null
        if (address != target) {
            client.disconnect()
            address = target
        }
        retryCount = 0
        ready = false
        lastHeart = 0L
        connect()
        handler.postDelayed(watchdog, 5_000L)
        return START_NOT_STICKY
    }

    private fun hasBluetoothPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) ==
            PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) ==
            PackageManager.PERMISSION_GRANTED

    private fun connect() {
        if (!active) return
        val bt = (getSystemService(BLUETOOTH_SERVICE) as BluetoothManager).adapter
        if (bt?.isEnabled != true || !hasBluetoothPermission()) {
            updateStatus("Bluetooth spento o permessi revocati; ritento la connessione.")
            scheduleRetry()
            return
        }
        lastAttempt = SystemClock.elapsedRealtime()
        ready = false
        updateStatus("Connessione Bluetooth in corso… (tentativo ${retryCount + 1})")
        client.connectStandardHeartRate(address)
    }

    private fun scheduleRetry() {
        if (!active || retryQueued) return
        retryQueued = true
        val delay = (2_000L shl retryCount.coerceAtMost(5)).coerceAtMost(60_000L)
        retryCount = (retryCount + 1).coerceAtMost(6)
        handler.postDelayed(retryTask, delay)
    }

    private fun updateStatus(message: String) {
        LiveHeartRuntime.status = message
    }

    private fun createChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID, "Benessere · FC Bluetooth live",
            NotificationManager.IMPORTANCE_LOW
        )
        (getSystemService(NOTIFICATION_SERVICE) as NotificationManager)
            .createNotificationChannel(channel)
    }

    private fun notification(message: String): Notification {
        val activity = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, LiveHeartService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentTitle("Benessere · monitoraggio FC")
            .setContentText(message)
            .setContentIntent(activity)
            .setOngoing(true)
            .setVisibility(Notification.VISIBILITY_SECRET)
            .addAction(android.R.drawable.ic_media_pause, "Interrompi", stop)
            .build()
    }

    override fun onDestroy() {
        active = false
        handler.removeCallbacks(watchdog)
        handler.removeCallbacks(retryTask)
        client.disconnect()
        uploader.close()
        LiveHeartRuntime.running = false
        LiveHeartRuntime.bpm = null
        LiveHeartRuntime.status = "Monitoraggio Bluetooth interrotto."
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        const val ACTION_START = "com.benessere.app.START_LIVE_HR"
        const val ACTION_STOP = "com.benessere.app.STOP_LIVE_HR"
        const val EXTRA_ADDRESS = "ble_address"
        private const val CHANNEL_ID = "live_heart_receiver"
        private const val NOTIFICATION_ID = 4126
    }
}
