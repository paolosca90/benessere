package com.benessere.app.health

import android.content.Context
import com.benessere.app.alarm.SmartAlarmScheduler
import android.content.SharedPreferences
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.UUID

/** Trasferimento opzionale; il token e' privato all'app (backup Android disabilitato). */
object HealthSyncClient {
    private const val STORE = "benessere_sync"
    const val BACKGROUND_PERMISSION = "android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND"

    fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(STORE, Context.MODE_PRIVATE)

    fun server(context: Context) = prefs(context).getString("url", "") ?: ""
    fun token(context: Context) = prefs(context).getString("token", "") ?: ""
    fun allowLocalHttp(context: Context) = prefs(context).getBoolean("allow_lan_http", false)
    fun autoEnabled(context: Context) = prefs(context).getBoolean("auto", false)
    fun lastStatus(context: Context) = prefs(context).getString("last_status", "Mai sincronizzato") ?: ""

    fun save(context: Context, url: String, secret: String, allowHttp: Boolean, auto: Boolean) {
        validateUrl(url.trim(), allowHttp)
        require(secret.trim().length >= 24) { "Token del server non valido (minimo 24 caratteri)" }
        prefs(context).edit().putString("url", url.trim().trimEnd('/'))
            .putString("token", secret.trim())
            .putBoolean("allow_lan_http", allowHttp)
            .putBoolean("auto", auto).apply()
    }

    /** HTTP e' consentito solo dopo consenso esplicito e solo su IPv4 privato. */
    fun validateUrl(raw: String, allowHttp: Boolean) {
        val uri = URI(raw)
        val url = uri.toURL()
        require(uri.userInfo == null && uri.query == null && uri.fragment == null && uri.path.orEmpty().trimEnd('/').isEmpty()) {
            "Inserisci solo protocollo, IP/host e porta, senza percorso"
        }
        val secure = url.protocol.equals("https", ignoreCase = true)
        if (!secure) {
            val ip = url.host
            val local = ip.matches(Regex("""192\.168\.\d{1,3}\.\d{1,3}""")) ||
                ip.matches(Regex("""10\.\d{1,3}\.\d{1,3}\.\d{1,3}""")) ||
                ip.matches(Regex("""172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"""))
            require(url.protocol == "http" && local && allowHttp) {
                "Per HTTP serve IPv4 privato e consenso esplicito. Su Internet usa HTTPS."
            }
        }
    }

    private fun deviceId(context: Context): String {
        val p = prefs(context)
        val existing = p.getString("device_id", null)
        if (!existing.isNullOrBlank()) return existing
        return UUID.randomUUID().toString().also { p.edit().putString("device_id", it).apply() }
    }

    suspend fun sync(context: Context, days: Int = 3): String = withContext(Dispatchers.IO) {
        val url = server(context)
        val secret = token(context)
        validateUrl(url, allowLocalHttp(context))
        require(secret.length >= 24) { "Token non configurato" }

        val payload = HealthConnectReader(context).exportPayload(days)
            .put("device_id", deviceId(context))
        val data = payload.toString().toByteArray(Charsets.UTF_8)
        require(data.size <= 8 * 1024 * 1024) { "Troppi dati per un invio: riduci l'intervallo" }
        val conn = URL(url + "/api/v1/health-sync").openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 10000
            conn.readTimeout = 30000
            conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer $secret")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "application/json")
            conn.outputStream.use { it.write(data) }
            val code = conn.responseCode
            val response = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader()?.use { it.readText().take(5000) }.orEmpty()
            if (code !in 200..299) throw IllegalStateException("Server HTTP $code: $response")
            val answer = JSONObject(response)
            if (answer.optString("status") != "ok") throw IllegalStateException("Risposta server non valida")
            val status = "OK: ${answer.optInt("new_hr_samples")} nuove FC, " +
                "${answer.optInt("received_sessions")} sessioni, " +
                "${answer.optInt("received_days")} giorni, " +
                "${answer.optInt("received_hrv")} HRV, " +
                "${answer.optInt("received_spo2")} SpO2 • ${answer.optString("synced_at")}"
            prefs(context).edit().putString("last_status", status).apply()
            status
        } finally {
            conn.disconnect()
        }
    }

    /** Applica sul telefono la configurazione salvata via web.
     * Questo avviene esplicitamente alla pressione del pulsante.
     */
    suspend fun syncAlarm(context: Context): String = withContext(Dispatchers.IO) {
        val base=server(context)
        val secret=token(context)
        validateUrl(base,allowLocalHttp(context))
        require(secret.length>=24) { "Token server non configurato" }
        val connection=URL(base+"/api/v1/alarm-config").openConnection() as HttpURLConnection
        val cfg=try {
            connection.connectTimeout=10000
            connection.readTimeout=10000
            connection.setRequestProperty("Authorization","Bearer "+secret)
            val code=connection.responseCode
            if(code!=200) error("Lettura sveglia: HTTP "+code)
            JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        } finally { connection.disconnect() }

        // Si conferma solo una programmazione locale effettivamente accettata.
        val outcome=try {
            SmartAlarmScheduler.applyRemote(context,cfg)
        } catch(e:Exception) {
            sendAlarmAck(base,secret,deviceId(context),cfg.getInt("revision"),false,
                (e.message ?: "errore programmazione").take(180))
            throw e
        }
        sendAlarmAck(base,secret,deviceId(context),cfg.getInt("revision"),true,"")
        outcome
    }

    private fun sendAlarmAck(base:String,secret:String,device:String,
                            revision:Int,installed:Boolean,errorMessage:String) {
        val conn=URL(base+"/api/v1/alarm-ack").openConnection() as HttpURLConnection
        try {
            conn.requestMethod="POST"
            conn.connectTimeout=10000
            conn.readTimeout=10000
            conn.doOutput=true
            conn.setRequestProperty("Authorization","Bearer "+secret)
            conn.setRequestProperty("Content-Type","application/json")
            val payload=JSONObject().put("device_id",device)
                .put("revision",revision).put("installed",installed)
                .put("error",errorMessage).toString()
            conn.outputStream.use { it.write(payload.toByteArray(Charsets.UTF_8)) }
            check(conn.responseCode==200) { "Conferma server rifiutata (HTTP "+conn.responseCode+")" }
        } finally { conn.disconnect() }
    }

    fun recordError(context: Context, error: String) {
        prefs(context).edit().putString("last_status", "Errore: ${error.take(220)}").apply()
    }
}
