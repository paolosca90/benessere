package com.benessere.app.health

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/**
 * Invio FC Bluetooth standard solo su esplicito consenso, solo mentre la
 * schermata Android è in primo piano e la connessione GATT è attiva.
 *
 * Non copia i campioni in Health Connect e non invia MAC/pairing key.
 * Campioni reali, con timestamp di ricezione BLE e cadenza max 1/3s.
 */
class LiveHeartUploader(private val context: Context) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val main = Handler(Looper.getMainLooper())
    private val busy = AtomicBoolean(false)
    private val earliestNextMs = AtomicLong(0L)
    private val store = context.getSharedPreferences("benessere_live_hr", Context.MODE_PRIVATE)

    fun enabled(): Boolean = store.getBoolean("enabled", false)

    fun setEnabled(value: Boolean) {
        store.edit().putBoolean("enabled", value).apply()
    }

    fun offer(bpm: Int, update: (String) -> Unit) {
        if (!enabled() || bpm !in 25..240) return
        val now = SystemClock.elapsedRealtime()
        if (now < earliestNextMs.get() || !busy.compareAndSet(false, true)) return
        earliestNextMs.set(now + 3000L)
        val sampledAt = Instant.now().toString()
        scope.launch {
            try {
                val base = HealthSyncClient.server(context)
                val token = HealthSyncClient.token(context)
                if (base.isBlank() || token.length < 24) {
                    earliestNextMs.set(SystemClock.elapsedRealtime() + 30_000L)
                    main.post { update("FC live non inviata: configura HTTPS e token in «Sincronizzazione dati»") }
                    return@launch
                }
                HealthSyncClient.validateUrl(base, HealthSyncClient.allowLocalHttp(context))
                val body = JSONObject()
                    .put("device_id", HealthSyncClient.deviceId(context))
                    .put("bpm", bpm)
                    .put("sampled_at", sampledAt)
                    .put("source", "ble_180d")
                    .toString().toByteArray(Charsets.UTF_8)
                val conn = URL(base + "/api/v1/live-heart-rate").openConnection() as HttpURLConnection
                try {
                    conn.requestMethod = "POST"
                    conn.connectTimeout = 5000
                    conn.readTimeout = 6000
                    conn.doOutput = true
                    conn.setRequestProperty("Authorization", "Bearer $token")
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.outputStream.use { it.write(body) }
                    val code = conn.responseCode
                    if (code != 200) error("Server HTTP $code")
                    main.post { update("FC live inviata alla dashboard · $bpm bpm") }
                } finally {
                    conn.disconnect()
                }
            } catch (e: Exception) {
                earliestNextMs.set(SystemClock.elapsedRealtime() + 30_000L)
                main.post { update("Invio FC live non riuscito: ${e.message ?: "errore di rete"}") }
            } finally {
                busy.set(false)
            }
        }
    }

    fun close() {
        scope.cancel()
    }
}
