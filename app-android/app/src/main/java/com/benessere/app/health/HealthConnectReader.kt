package com.benessere.app.health

import android.content.Context
import android.os.Build
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONArray
import org.json.JSONObject
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/** Lettura locale (niente Zepp token) di Health Connect; un unico export con aggregati deduplicati. */
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

    private val client = HealthConnectClient.getOrCreate(context)

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

    // La lettura in background non e' disponibile su ogni combinazione OS/provider.
    // Compatibilità con la versione 1.1.0 del client SDK attualmente installata.
    // La disponibilità effettiva viene verificata dal permesso concesso: se manca,
    // niente JobScheduler e resta la sincronizzazione all'apertura.
    val backgroundAvailable: Boolean
        get() = Build.VERSION.SDK_INT >= 35

    suspend fun backgroundGranted(): Boolean = backgroundAvailable &&
        client.permissionController.getGrantedPermissions().contains(
            "android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND"
        )

    private suspend inline fun <reified T : Record> allRecords(
        range: TimeRangeFilter, maxRecords: Int = 30000
    ): List<T> {
        val out = mutableListOf<T>()
        var token: String? = null
        var pages = 0
        do {
            val response = client.readRecords(
                ReadRecordsRequest(T::class, range, pageSize = 1000, pageToken = token)
            )
            out.addAll(response.records)
            if (out.size > maxRecords || ++pages > 50) {
                throw IllegalStateException("Troppi dati Health Connect: riduci i giorni di sync")
            }
            token = response.pageToken
        } while (!token.isNullOrEmpty())
        return out
    }

    suspend fun exportPayload(days: Int = 3): JSONObject {
        require(days in 1..7)
        if (!hasAllPermissions()) throw SecurityException("Autorizza prima tutte le letture Health Connect")
        val now = Instant.now()
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val start = today.minusDays((days - 1).toLong()).atStartOfDay(zone).toInstant()
        val range = TimeRangeFilter.between(start, now)
        val result = JSONObject().put("schema", 1)
        val daily = JSONArray()
        for (offset in days - 1 downTo 0) {
            val day = today.minusDays(offset.toLong())
            val from = day.atStartOfDay(zone).toInstant()
            val end = minOf(day.plusDays(1).atStartOfDay(zone).toInstant(), now)
            val agg = client.aggregate(
                AggregateRequest(
                    metrics = setOf(
                        StepsRecord.COUNT_TOTAL,
                        ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                        TotalCaloriesBurnedRecord.ENERGY_TOTAL
                    ),
                    timeRangeFilter = TimeRangeFilter.between(from, end)
                )
            )
            daily.put(JSONObject().put("date", day.toString())
                .put("steps", agg[StepsRecord.COUNT_TOTAL] ?: JSONObject.NULL)
                .put("active_kcal", agg[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]
                    ?.inKilocalories ?: JSONObject.NULL)
                .put("total_kcal", agg[TotalCaloriesBurnedRecord.ENERGY_TOTAL]
                    ?.inKilocalories ?: JSONObject.NULL))
        }
        val heart = JSONArray()
        allRecords<HeartRateRecord>(range).forEach { record ->
            record.samples.forEach { sample ->
                heart.put(JSONObject().put("ts", sample.time.toString())
                    .put("bpm", sample.beatsPerMinute))
            }
        }
        val sessions = JSONArray()
        allRecords<SleepSessionRecord>(range, 2000).forEach { s ->
            val nightDate = s.endTime.atZone(zone).toLocalDate().toString()
            var deep = 0L
            var light = 0L
            var rem = 0L
            var awake = 0L
            s.stages.forEach { stage ->
                val minutes = Duration.between(stage.startTime, stage.endTime).toMinutes().coerceAtLeast(0L)
                when (stage.stage) {
                    SleepSessionRecord.STAGE_TYPE_DEEP -> deep += minutes
                    SleepSessionRecord.STAGE_TYPE_LIGHT -> light += minutes
                    SleepSessionRecord.STAGE_TYPE_REM -> rem += minutes
                    SleepSessionRecord.STAGE_TYPE_AWAKE,
                    SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED -> awake += minutes
                }
            }
            val data = JSONObject().put("kind", "sleep")
                .put("id", s.metadata.id.ifBlank { "${s.startTime}-${s.endTime}" })
                .put("origin", s.metadata.dataOrigin.packageName)
                .put("start", s.startTime.toString()).put("end", s.endTime.toString())
                .put("night_date", nightDate)
                .put("deep_min", if (s.stages.isEmpty()) JSONObject.NULL else deep)
                .put("light_min", if (s.stages.isEmpty()) JSONObject.NULL else light)
                .put("rem_min", if (s.stages.isEmpty()) JSONObject.NULL else rem)
                .put("awake_min", if (s.stages.isEmpty()) JSONObject.NULL else awake)
            sessions.put(data)
        }
        allRecords<ExerciseSessionRecord>(range, 2000).forEach { s ->
            sessions.put(JSONObject().put("kind", "exercise")
                .put("id", s.metadata.id.ifBlank { "${s.startTime}-${s.endTime}" })
                .put("origin", s.metadata.dataOrigin.packageName)
                .put("start", s.startTime.toString()).put("end", s.endTime.toString())
                .put("title", s.title ?: "Attività ${s.exerciseType}"))
        }
        // I dati biometrici già accessibili sul telefono devono arrivare anche sul server.
        val oxygen = JSONArray()
        allRecords<OxygenSaturationRecord>(range, 2000).forEach { s ->
            oxygen.put(JSONObject().put("ts", s.time.toString())
                .put("pct", s.percentage.value))
        }
        val weights = JSONArray()
        allRecords<WeightRecord>(range, 2000).forEach { w ->
            weights.put(JSONObject().put("date", w.time.atZone(zone).toLocalDate().toString())
                .put("weight_kg", w.weight.inKilograms))
        }
        return result.put("days", daily).put("heart_rates", heart).put("sessions", sessions)
            .put("oxygen_saturation", oxygen).put("weights", weights)
    }

    suspend fun snapshot(): Snapshot {
        val now = Instant.now()
        val zone = ZoneId.systemDefault()
        val startOfDay = LocalDate.now(zone).atStartOfDay(zone).toInstant()
        val today = TimeRangeFilter.between(startOfDay, now)
        val hr = allRecords<HeartRateRecord>(today)
        val lastBpm = hr.flatMap { it.samples }.maxByOrNull { it.time }?.beatsPerMinute
        val sleep = allRecords<SleepSessionRecord>(
            TimeRangeFilter.between(now.minus(Duration.ofDays(2)), now), 2000
        )
        val lastSleep = sleep.maxByOrNull { it.endTime }
        val exercises = allRecords<ExerciseSessionRecord>(today, 2000)
        val aggregates = client.aggregate(AggregateRequest(
            metrics = setOf(StepsRecord.COUNT_TOTAL, TotalCaloriesBurnedRecord.ENERGY_TOTAL),
            timeRangeFilter = today
        ))
        val spo2 = allRecords<OxygenSaturationRecord>(today, 2000)
        val weight = allRecords<WeightRecord>(
            TimeRangeFilter.between(now.minus(Duration.ofDays(30)), now), 2000
        )
        return Snapshot(
            heartRateSamples = hr.sumOf { it.samples.size },
            lastHeartRate = lastBpm?.toInt(),
            lastNightSleepMinutes = lastSleep?.let { Duration.between(it.startTime, it.endTime).toMinutes() },
            exercisesToday = exercises.size,
            stepsToday = aggregates[StepsRecord.COUNT_TOTAL] ?: 0L,
            totalCaloriesToday = aggregates[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories,
            spo2Last = spo2.maxByOrNull { it.time }?.percentage?.value,
            weightLastKg = weight.maxByOrNull { it.time }?.weight?.inKilograms
        )
    }
}
