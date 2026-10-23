package com.benessere.app.alarm

/**
 * Zepp OS alarm endpoint (0x000f): payload encoding only.
 * This is NOT a Bluetooth transport, pairing implementation or working Helio driver.
 * Do not transmit without device capability/slot ownership checks and read-back ACK.
 * Protocol reference: Gadgetbridge ZeppOsAlarmsService (AGPL-3.0).
 */
object ZeppOsAlarmCodec {
    const val ENDPOINT: Short = 0x000f
    private const val CREATE = 0x03
    private const val DELETE = 0x05
    private const val REQUEST = 0x09
    private const val FLAG_ENABLED = 0x04

    /** Leave the native 'smart' flag OFF; capability not verified for Helio Strap. */
    fun createEnabled(slot: Int, hour: Int, minute: Int, repeatDaysMask: Int = 0): ByteArray {
        require(slot in 0..9) { "Alarm slot must be 0..9" }
        require(hour in 0..23 && minute in 0..59) { "Invalid alarm time" }
        require(repeatDaysMask in 0..127) { "Invalid repeat mask" }
        return byteArrayOf(CREATE.toByte(), 0x01, FLAG_ENABLED.toByte(), slot.toByte(),
            hour.toByte(), minute.toByte(), repeatDaysMask.toByte(),
            0x00, 0x00, 0x00, 0x00, 0x00)
    }

    fun requestAlarms(): ByteArray = byteArrayOf(REQUEST.toByte())

    /** Never delete a slot that has not first been read and confirmed as ours. */
    fun deleteOwnedSlot(slot: Int): ByteArray {
        require(slot in 0..9)
        return byteArrayOf(DELETE.toByte(), 0x01, slot.toByte())
    }
}
