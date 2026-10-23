package com.benessere.app.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
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
        val exercisesToday: Int?,
        val stepsToday: Long?,
        val totalCaloriesToday: Double?,
        val spo2Last: Double?,
        val weightLastKg: Double?
    )

    private val client = HealthConnectClient.getOrCreate(context)

    val permissions = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(HeartRateVariabilityRmssdRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(OxygenSaturationRecord::class),
        HealthPermission.getReadPermission(WeightRecord::class)
    )

    val permissionContract = PermissionController.createRequestPermissionResultContract()

    suspend fun grantedPermissions(): Set<String> =
        client.permissionController.getGrantedPermissions().intersect(permissions)

    suspend fun hasAnyPermissions(): Boolean = grantedPermissions().isNotEmpty()

    suspend fun hasAllPermissions(): Boolean =
        client.permissionController.getGrantedPermissions().containsAll(permissions)

    suspend fun permissionSummary(): String {
        val granted = grantedPermissions()
        val missing = permissions.size - granted.size
        return "${granted.size}/${permissions.size} categorie autorizzate" +
            if (missing > 0) " · $missing mancanti (le altre vengono comunque sincronizzate)" else ""
    }

    // Feature detection ufficiale: Android API level da solo non basta.
    val backgroundAvailable: Boolean
        get() = client.features.getFeatureStatus(
            HealthConnectFeatures.FEATURE_READ_HEALTH_DATA_IN_BACKGROUND
        ) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE

    suspend fun backgroundGranted(): Boolean = backgroundAvailable &&
        client.permissionController.getGrantedPermissions().contains(
            HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
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
        val granted = grantedPermissions()
        if (granted.isEmpty()) throw SecurityException("Nessuna lettura Health Connect autorizzata")
        fun allowed(record: kotlin.reflect.KClass<out Record>): Boolean =
            HealthPermission.getReadPermission(record) in granted
        val now = Instant.now()
        val zone = ZoneId.systemDefault()
        val today = LocalDate.now(zone)
        val start = today.minusDays((days - 1).toLong()).atStartOfDay(zone).toInstant()
        val range = TimeRangeFilter.between(start, now)
        val result = JSONObject().put("schema", 1)
        val daily = JSONArray()
        val stepsGranted = allowed(StepsRecord::class)
        val activeGranted = allowed(ActiveCaloriesBurnedRecord::class)
        val totalGranted = allowed(TotalCaloriesBurnedRecord::class)
        if (stepsGranted || activeGranted || totalGranted) {
            for (offset in days - 1 downTo 0) {
                val day = today.minusDays(offset.toLong())
                val from = day.atStartOfDay(zone).toInstant()
                val end = minOf(day.plusDays(1).atStartOfDay(zone).toInstant(), now)
                val metrics = setOfNotNull(
                    StepsRecord.COUNT_TOTAL.takeIf { stepsGranted },
                    ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL.takeIf { activeGranted },
                    TotalCaloriesBurnedRecord.ENERGY_TOTAL.takeIf { totalGranted }
                )
                val agg = client.aggregate(AggregateRequest(
                    metrics = metrics,
                    timeRangeFilter = TimeRangeFilter.between(from, end)
                ))
                daily.put(JSONObject().put("date", day.toString())
                    .put("steps", if (stepsGranted) agg[StepsRecord.COUNT_TOTAL] ?: JSONObject.NULL else JSONObject.NULL)
                    .put("active_kcal", if (activeGranted) agg[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]
                        ?.inKilocalories ?: JSONObject.NULL else JSONObject.NULL)
                    .put("total_kcal", if (totalGranted) agg[TotalCaloriesBurnedRecord.ENERGY_TOTAL]
                        ?.inKilocalories ?: JSONObject.NULL else JSONObject.NULL))
            }
        }
        val heart = JSONArray()
        (if (allowed(HeartRateRecord::class)) allRecords<HeartRateRecord>(range) else emptyList()).forEach { record ->
            record.samples.forEach { sample ->
                heart.put(JSONObject().put("ts", sample.time.toString())
                    .put("bpm", sample.beatsPerMinute))
            }
        }
        val sessions = JSONArray()
        (if (allowed(SleepSessionRecord::class)) allRecords<SleepSessionRecord>(range, 2000) else emptyList()).forEach { s ->
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
            // Completed-session history ONLY: never use these stages as a live
            // sleep-stage stream or as authorization to vibrate Helio Strap.
            if (s.stages.isNotEmpty()) {
                val timeline = JSONArray()
                s.stages.sortedBy { it.startTime }.forEach { stage ->
                    val name = when (stage.stage) {
                        SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
                        SleepSessionRecord.STAGE_TYPE_LIGHT -> "light"
                        SleepSessionRecord.STAGE_TYPE_REM -> "rem"
                        SleepSessionRecord.STAGE_TYPE_AWAKE,
                        SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED -> "awake"
                        SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> "out_of_bed"
                        SleepSessionRecord.STAGE_TYPE_SLEEPING -> "sleeping"
                        else -> "unknown"
                    }
                    timeline.put(JSONObject().put("start", stage.startTime.toString())
                        .put("end", stage.endTime.toString()).put("stage", name))
                }
                data.put("stages", timeline)
            }
            sessions.put(data)
        }
        (if (allowed(ExerciseSessionRecord::class)) allRecords<ExerciseSessionRecord>(range, 2000) else emptyList()).forEach { s ->
            sessions.put(JSONObject().put("kind", "exercise")
                .put("id", s.metadata.id.ifBlank { "${s.startTime}-${s.endTime}" })
                .put("origin", s.metadata.dataOrigin.packageName)
                .put("start", s.startTime.toString()).put("end", s.endTime.toString())
                .put("title", s.title ?: "Attività ${s.exerciseType}"))
        }
        // I dati biometrici già accessibili sul telefono devono arrivare anche sul server.
        val oxygen = JSONArray()
        (if (allowed(OxygenSaturationRecord::class)) allRecords<OxygenSaturationRecord>(range, 2000) else emptyList()).forEach { s ->
            oxygen.put(JSONObject().put("ts", s.time.toString())
                .put("pct", s.percentage.value))
        }
        val weights = JSONArray()
        (if (allowed(WeightRecord::class)) allRecords<WeightRecord>(range, 2000) else emptyList()).forEach { w ->
            weights.put(JSONObject().put("date", w.time.atZone(zone).toLocalDate().toString())
                .put("weight_kg", w.weight.inKilograms))
        }
        // HRV RMSSD: incluso SOLO se Health Connect espone misure autorizzate.
        val hrv = JSONArray()
        (if (allowed(HeartRateVariabilityRmssdRecord::class))
            allRecords<HeartRateVariabilityRmssdRecord>(range, 2000) else emptyList()).forEach { h ->
            hrv.put(JSONObject().put("night_date", h.time.atZone(zone).toLocalDate().toString())
                .put("ts", h.time.toString()).put("rmssd_ms", h.heartRateVariabilityMillis))
        }
        return result.put("days", daily).put("heart_rates", heart).put("sessions", sessions)
            .put("oxygen_saturation", oxygen).put("weights", weights).put("hrv_rmssd", hrv)
    }

    suspend fun snapshot(): Snapshot {
        val now = Instant.now()
        val zone = ZoneId.systemDefault()
        val startOfDay = LocalDate.now(zone).atStartOfDay(zone).toInstant()
        val today = TimeRangeFilter.between(startOfDay, now)
        val granted = grantedPermissions()
        if (granted.isEmpty()) throw SecurityException("Permessi Health Connect assenti")
        fun allowed(record: kotlin.reflect.KClass<out Record>): Boolean =
            HealthPermission.getReadPermission(record) in granted
        val hr = if (allowed(HeartRateRecord::class)) allRecords<HeartRateRecord>(today) else emptyList()
        val lastBpm = hr.flatMap { it.samples }.maxByOrNull { it.time }?.beatsPerMinute
        val sleep = if (allowed(SleepSessionRecord::class)) allRecords<SleepSessionRecord>(
            TimeRangeFilter.between(now.minus(Duration.ofDays(2)), now), 2000
        ) else emptyList()
        val lastSleep = sleep.maxByOrNull { it.endTime }
        val exercises = if (allowed(ExerciseSessionRecord::class)) allRecords<ExerciseSessionRecord>(today, 2000) else emptyList()
        val stepsAllowed = allowed(StepsRecord::class)
        val totalAllowed = allowed(TotalCaloriesBurnedRecord::class)
        val metricSet = setOfNotNull(
            StepsRecord.COUNT_TOTAL.takeIf { stepsAllowed },
            TotalCaloriesBurnedRecord.ENERGY_TOTAL.takeIf { totalAllowed }
        )
        val aggregates = if (metricSet.isNotEmpty()) client.aggregate(AggregateRequest(
            metrics = metricSet,
            timeRangeFilter = today
        )) else null
        val spo2 = if (allowed(OxygenSaturationRecord::class)) allRecords<OxygenSaturationRecord>(today, 2000) else emptyList()
        val weight = if (allowed(WeightRecord::class)) allRecords<WeightRecord>(
            TimeRangeFilter.between(now.minus(Duration.ofDays(30)), now), 2000
        ) else emptyList()
        return Snapshot(
            heartRateSamples = hr.sumOf { it.samples.size },
            lastHeartRate = lastBpm?.toInt(),
            lastNightSleepMinutes = lastSleep?.let { Duration.between(it.startTime, it.endTime).toMinutes() },
            exercisesToday = if (allowed(ExerciseSessionRecord::class)) exercises.size else null,
            stepsToday = if (stepsAllowed) aggregates?.get(StepsRecord.COUNT_TOTAL) else null,
            totalCaloriesToday = if (totalAllowed) aggregates?.get(TotalCaloriesBurnedRecord.ENERGY_TOTAL)?.inKilocalories else null,
            spo2Last = spo2.maxByOrNull { it.time }?.percentage?.value,
            weightLastKg = weight.maxByOrNull { it.time }?.weight?.inKilograms
        )
    }
}
