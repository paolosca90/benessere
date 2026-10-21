package com.benessere.app.health

import android.content.Context
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.health.connect.client.permission.HealthPermission
import java.time.Duration
import java.time.ZonedDateTime

/**
 * Lettura dei dati che l'app Zepp scrive su Health Connect (canale near real-time).
 */
class HealthConnectReader(context: Context) {

    data class Snapshot(
        val heartRateSamples: Int,
        val lastHeartRate: Int?,
        val lastNightSleepMinutes: Long?,
        val exercisesToday: Int,
        val stepsToday: Long,
        val totalCaloriesToday: Double?,
        val spo2Last: Double?,
        val weightLastKg: Double?
    )

    private val client: HealthConnectClient = HealthConnectClient.getOrCreate(context)

    val permissions = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(OxygenSaturationRecord::class),
        HealthPermission.getReadPermission(WeightRecord::class)
    )

    val permissionContract = PermissionController.createRequestPermissionResultContract()

    suspend fun hasAllPermissions(): Boolean =
        client.permissionController.getGrantedPermissions().containsAll(permissions)

    suspend fun snapshot(): Snapshot {
        val now = ZonedDateTime.now()
        val startOfDay = now.toLocalDate().atStartOfDay(now.zone)
        val today = TimeRangeFilter.between(startOfDay.toInstant(), now.toInstant())

        val hr = client.readRecords(ReadRecordsRequest(HeartRateRecord::class, today))
        val lastBpm = hr.records.lastOrNull()
            ?.samples?.lastOrNull()?.beatsPerMinute

        val sleep = client.readRecords(
            ReadRecordsRequest(
                SleepSessionRecord::class,
                TimeRangeFilter.between(
                    now.minusDays(2).toLocalDate().atStartOfDay(now.zone).toInstant(),
                    now.toInstant()
                )
            )
        )
        val lastSleep = sleep.records.maxByOrNull { it.startTime }
        val sleepMinutes = lastSleep?.let { Duration.between(it.startTime, it.endTime).toMinutes() }

        val exercises = client.readRecords(ReadRecordsRequest(ExerciseSessionRecord::class, today))
        val steps = client.readRecords(ReadRecordsRequest(StepsRecord::class, today))
        val calories = client.readRecords(ReadRecordsRequest(TotalCaloriesBurnedRecord::class, today))
        val spo2 = client.readRecords(ReadRecordsRequest(OxygenSaturationRecord::class, today))
        val weight = client.readRecords(ReadRecordsRequest(WeightRecord::class, today))

        return Snapshot(
            heartRateSamples = hr.records.sumOf { r -> r.samples.size },
            lastHeartRate = lastBpm?.toInt(),
            lastNightSleepMinutes = sleepMinutes,
            exercisesToday = exercises.records.size,
            stepsToday = steps.records.sumOf { it.count },
            totalCaloriesToday = calories.records.sumOf { it.energy.inKilocalories },
            spo2Last = spo2.records.lastOrNull()?.percentage?.value,
            weightLastKg = weight.records.lastOrNull()?.weight?.inKilograms
        )
    }
}
