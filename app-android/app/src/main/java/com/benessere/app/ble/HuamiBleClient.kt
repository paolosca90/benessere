package com.benessere.app.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.content.Context
import android.os.Handler
import android.os.Looper
import javax.crypto.Cipher
import javax.crypto.spec.SecretKeySpec

/**
 * Client BLE per dispositivi Huami/Amazfit (Helio Strap incluso).
 *
 * Stato attuale (0.1.0): scansione, connessione GATT, discovery servizi,
 * handshake di autenticazione classico a 3 step (chiave di pairing 16 byte,
 * AES/ECB), sottoscrizione heart rate standard (180D/2A37) e abilitazione
 * misurazione continua legacy.
 *
 * DA VALIDARE sul device reale (docs/06): l'Helio Strap è un device
 * Zepp OS, quindi buona parte dei comandi viaggia probabilmente nel
 * chunked-transfer 2021 (0x0016/0x0017) con frame protobuf-like —
 * la sessione REA sull'APK Zepp servirà a confermare i frame esatti
 * per FC live e scrittura sveglie.
 */
class HuamiBleClient(private val context: Context) {

    interface Listener {
        fun onLog(line: String)
        fun onHeartRate(bpm: Int)
        fun onAuthResult(success: Boolean)
    }

    var listener: Listener? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var adapter: BluetoothAdapter? = null
    private var gatt: BluetoothGatt? = null
    private var authKey: ByteArray = ByteArray(16)
    private var scanCallback: ScanCallback? = null

    private fun log(line: String) {
        mainHandler.post { listener?.onLog(line) }
    }

    @SuppressLint("MissingPermission")
    fun startScan() {
        val btManager = context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        adapter = btManager?.adapter
        val scanner = adapter?.bluetoothLeScanner ?: run {
            log("BLE non disponibile su questo dispositivo")
            return
        }
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val name = result.device.name ?: return
                if (name.contains("Helio", ignoreCase = true) ||
                    name.contains("Amazfit", ignoreCase = true) ||
                    name.contains("Mi Band", ignoreCase = true) ||
                    name.contains("CooSpo", ignoreCase = true) ||
                    name.contains("Polar", ignoreCase = true)
                ) {
                    log("Trovato: $name [${result.device.address}]")
                }
            }

            override fun onScanFailed(errorCode: Int) {
                log("Scansione fallita (errore $errorCode)")
            }
        }
        scanCallback = callback
        log("Scansione BLE avviata…")
        scanner.startScan(callback)
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        val callback = scanCallback ?: return
        adapter?.bluetoothLeScanner?.stopScan(callback)
        scanCallback = null
        log("Scansione fermata")
    }

    /**
     * Connette al dispositivo per MAC address.
     * @param keyHex chiave di pairing in esadecimale (32 caratteri); quella
     *   generata dall'app Zepp al pairing, estraibile una volta (docs/06).
     */
    @SuppressLint("MissingPermission")
    fun connect(macAddress: String, keyHex: String) {
        val key = runCatching { hexToBytes(keyHex) }.getOrNull()
        if (key == null || key.size != 16) {
            log("Chiave di pairing non valida: servono 32 cifre esadecimali (docs/06 per estrarla)")
            return
        }
        authKey = key
        val device: BluetoothDevice? = adapter?.getRemoteDevice(macAddress)
        if (device == null) {
            log("MAC non raggiungibile: $macAddress (prima scansiona)")
            return
        }
        stopScan()
        log("Connessione a ${device.name ?: macAddress} …")
        gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
    }

    @SuppressLint("MissingPermission")
    fun disconnect() {
        gatt?.disconnect()
        gatt?.close()
        gatt = null
        log("Disconnesso")
    }

    private val gattCallback = object : BluetoothGattCallback() {

        @SuppressLint("MissingPermission")
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    log("Connesso, discovery servizi…")
                    g.discoverServices()
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    log("Disconnesso (status=$status)")
                    listener?.onAuthResult(false)
                }
            }
        }

        @SuppressLint("MissingPermission")
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                log("Discovery servizi fallita (status=$status)")
                return
            }
            val fee1 = g.getService(HuamiProtocol.SERVICE_MIBAND2)
            val authChar = fee1?.getCharacteristic(HuamiProtocol.CHARACTERISTIC_AUTH)
            if (authChar == null) {
                log("Servizio Huami FEE1 non trovato: dispositivo non Huami o protocollo diverso")
                return
            }
            log("Servizi trovati. Abilito notifiche su AUTH…")
            enableNotifications(g, authChar)

            // Step 1: invio della chiave
            val step1 = byteArrayOf(
                HuamiProtocol.AUTH_SEND_KEY, HuamiProtocol.AUTH_BYTE
            ) + authKey
            write(g, authChar, step1)
        }

        @SuppressLint("MissingPermission")
        override fun onCharacteristicWrite(
            g: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            status: Int
        ) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                log("Scrittura fallita su ${characteristic.uuid} (status=$status)")
            }
        }

        @Deprecated("Delegato alla variante con byte[] (API < 33)")
        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic
        ) {
            @Suppress("DEPRECATION")
            characteristic.value?.let { handleCharacteristicChanged(g, characteristic.uuid, it) }
        }

        override fun onCharacteristicChanged(
            g: BluetoothGatt,
            characteristic: BluetoothGattCharacteristic,
            value: ByteArray
        ) {
            handleCharacteristicChanged(g, characteristic.uuid, value)
        }
    }

    private fun handleCharacteristicChanged(g: BluetoothGatt, uuid: java.util.UUID, value: ByteArray) {
        when (uuid) {
            HuamiProtocol.CHARACTERISTIC_AUTH -> handleAuthResponse(g, value)
            HuamiProtocol.CHARACTERISTIC_HEART_RATE_MEASUREMENT ->
                HuamiProtocol.parseHeartRate(value)?.let { bpm ->
                    mainHandler.post { listener?.onHeartRate(bpm) }
                }
        }
    }

    @SuppressLint("MissingPermission")
    private fun handleAuthResponse(g: BluetoothGatt, value: ByteArray) {
        val authChar = g.getService(HuamiProtocol.SERVICE_MIBAND2)
            ?.getCharacteristic(HuamiProtocol.CHARACTERISTIC_AUTH) ?: return
        if (value.isEmpty() || value[0] != HuamiProtocol.AUTH_RESPONSE) return

        val step = value.getOrNull(1)
        val ok = value.getOrNull(2) == HuamiProtocol.AUTH_SUCCESS
        when {
            step == AUTH_RESULT_SEND_KEY && ok -> {
                log("Auth step 1 OK — richiedo numero random…")
                write(g, authChar, byteArrayOf(
                    HuamiProtocol.AUTH_REQUEST_RANDOM_AUTH_NUMBER, HuamiProtocol.AUTH_BYTE
                ))
            }
            step == AUTH_RESULT_RANDOM && ok && value.size >= 19 -> {
                val random = value.copyOfRange(3, 19)
                log("Auth step 2 OK — invio random cifrato…")
                val cipher = Cipher.getInstance("AES/ECB/NoPadding")
                cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(authKey, "AES"))
                val encrypted = cipher.doFinal(random)
                write(g, authChar, byteArrayOf(
                    HuamiProtocol.AUTH_SEND_ENCRYPTED_AUTH_NUMBER, HuamiProtocol.AUTH_BYTE
                ) + encrypted)
            }
            step == AUTH_RESULT_ENCRYPTED && ok -> {
                log("AUTENTICATO ✔")
                listener?.onAuthResult(true)
                onAuthenticated(g)
            }
            else -> {
                log("Auth FALLITA (step=$step code=${value.getOrNull(2)}) — chiave errata?")
                listener?.onAuthResult(false)
            }
        }
    }

    /** Dopo l'autenticazione: sottoscrive la FC standard e attiva la misura continua (legacy). */
    @SuppressLint("MissingPermission")
    private fun onAuthenticated(g: BluetoothGatt) {
        val hrChar = g.getService(HuamiProtocol.SERVICE_HEART_RATE)
            ?.getCharacteristic(HuamiProtocol.CHARACTERISTIC_HEART_RATE_MEASUREMENT)
        if (hrChar == null) {
            log("Caratteristica FC standard non presente (device Zepp OS: attendere supporto chunked-transfer)")
        } else {
            enableNotifications(g, hrChar)
            log("Sottoscritto alla FC (180D/2A37)")
        }
        val config = g.getService(HuamiProtocol.SERVICE_MIBAND)
            ?.getCharacteristic(HuamiProtocol.CHARACTERISTIC_CONFIGURATION)
        if (config != null) {
            write(g, config, HuamiProtocol.enableHrConnection(true))
            write(g, config, HuamiProtocol.periodicHrInterval(0))
            log("Misurazione FC continua richiesta (legacy)")
        }
    }

    @SuppressLint("MissingPermission")
    private fun enableNotifications(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        g.setCharacteristicNotification(characteristic, true)
        val ccc = characteristic.getDescriptor(HuamiProtocol.CCC_DESCRIPTOR) ?: return
        ccc.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
        g.writeDescriptor(ccc)
    }

    @SuppressLint("MissingPermission")
    private fun write(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic, payload: ByteArray) {
        characteristic.value = payload
        characteristic.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        g.writeCharacteristic(characteristic)
    }

    private fun hexToBytes(hex: String): ByteArray {
        val clean = hex.replace(" ", "").replace(":", "")
        require(clean.length == 32) { "Lunghezza chiave errata: ${clean.length}/32" }
        return ByteArray(16) { i ->
            ((Character.digit(clean[i * 2], 16) shl 4) + Character.digit(clean[i * 2 + 1], 16)).toByte()
        }
    }

    companion object {
        // Codici in byte[1] della risposta auth (0x10)
        private const val AUTH_RESULT_SEND_KEY: Byte = 0x01
        private const val AUTH_RESULT_RANDOM: Byte = 0x02
        private const val AUTH_RESULT_ENCRYPTED: Byte = 0x03
    }
}
