package com.benessere.app.ble

import java.util.UUID

/**
 * Costanti del protocollo BLE Huami/Amazfit.
 *
 * Fonti: Gadgetbridge (AGPLv3, `vendor/gadgetbridge-protocol/HuamiService.java`)
 * e analisi del APK Zepp del 2026-10-20 (`vendor/zepp-apk/jadx-out`, docs/06).
 *
 * conferme APK: l'app Zepp parla con lo strap tramite
 * HMSmartWatchTransportProfile — servizio FED0, write 0x0010, notify 0x0011,
 * frame 20 byte con header 3 — più il file transfer v3 (0x0023/24, classe
 * "FileReceiver"). NON usa FEE0/FEE1, né l'auth classico su 0x0009, né il
 * servizio HR standard 180D: FC live e comandi viaggiano nel protocollo
 * app-layer (protobuf) sopra questo trasporto. Riferimento per quel layer:
 * codice Zepp OS di Gadgetbridge.
 */
object HuamiProtocol {

    private const val SIG_BASE = "0000%s-0000-1000-8000-00805f9b34fb"
    private const val HUAMI_BASE = "0000%s-0000-3512-2118-0009af100700"

    private fun sig(id: String): UUID = UUID.fromString(String.format(SIG_BASE, id.uppercase()))
    private fun huami(id: String): UUID = UUID.fromString(String.format(HUAMI_BASE, id))

    // ---- Servizi ----
    val SERVICE_MIBAND: UUID = sig("FEE0")        // config, batteria, passi realtime (legacy Gadgetbridge)
    val SERVICE_MIBAND2: UUID = sig("FEE1")       // auth, device event, chunked transfer (legacy Gadgetbridge)
    val SERVICE_HEART_RATE: UUID = sig("180D")    // heart rate standard Bluetooth SIG (NON usato da Zepp su Helio Strap)
    val CCC_DESCRIPTOR: UUID = sig("2902")

    // ---- Trasporto confermato dall'APK Zepp (HMSmartWatchTransportProfile, classe oxk) ----
    val SERVICE_HM_TRANSPORT: UUID = huami("FED0")
    val CHARACTERISTIC_TRANSPORT_SEND: UUID = huami("0010")     // write, frame 20 byte con header 3
    val CHARACTERISTIC_TRANSPORT_RECEIVE: UUID = huami("0011")  // notify

    // ---- Caratteristiche sotto FEE0 ----
    val CHARACTERISTIC_CONFIGURATION: UUID = huami("0003")
    val CHARACTERISTIC_BATTERY: UUID = huami("0006")
    val CHARACTERISTIC_REALTIME_STEPS: UUID = huami("0007")

    // ---- Caratteristiche sotto FEE1 ----
    val CHARACTERISTIC_AUTH: UUID = huami("0009")
    val CHARACTERISTIC_DEVICE_EVENT: UUID = huami("0010")
    val CHUNKED_TRANSFER_2021_WRITE: UUID = huami("0016")
    val CHUNKED_TRANSFER_2021_READ: UUID = huami("0017")
    val ZEPP_OS_FILE_TRANSFER_SEND: UUID = huami("0023")
    val ZEPP_OS_FILE_TRANSFER_RECEIVE: UUID = huami("0024")

    // ---- Heart rate standard (180D), valido anche per fasce pettorali ----
    val CHARACTERISTIC_HEART_RATE_MEASUREMENT: UUID = sig("2A37")

    // ---- Handshake di autenticazione (3 step, chiave a 16 byte) ----
    const val AUTH_SEND_KEY: Byte = 0x01
    const val AUTH_REQUEST_RANDOM_AUTH_NUMBER: Byte = 0x02
    const val AUTH_SEND_ENCRYPTED_AUTH_NUMBER: Byte = 0x03
    const val AUTH_RESPONSE: Byte = 0x10
    const val AUTH_SUCCESS: Byte = 0x01
    const val AUTH_FAIL: Byte = 0x04
    const val AUTH_BYTE: Byte = 0x08

    /** Abilita la misurazione FC continua durante la connessione (legacy). */
    fun enableHrConnection(enable: Boolean): ByteArray =
        byteArrayOf(0x06, 0x1f, 0x00, if (enable) 0x01 else 0x00)

    /** Intervallo misurazione FC periodica in minuti (0 = continua). Legacy. */
    fun periodicHrInterval(minutes: Int): ByteArray =
        byteArrayOf(0x14, minutes.toByte())

    /**
     * Parsing della Heart Rate Measurement standard (0x2A37).
     * Ritorna la FC in bpm oppure null se il pacchetto non è valido.
     */
    fun parseHeartRate(bytes: ByteArray): Int? {
        if (bytes.isEmpty()) return null
        val flags = bytes[0].toInt()
        return if (flags and 0x01 == 0) {
            if (bytes.size > 1) bytes[1].toInt() and 0xFF else null
        } else {
            if (bytes.size > 2) (bytes[1].toInt() and 0xFF) or ((bytes[2].toInt() and 0xFF) shl 8) else null
        }
    }
}
