package com.benessere.app.alarm

/**
 * Decision logic only: it NEVER claims to vibrate the band.
 * Sources must supply live, timestamped measurements. Health Connect sleep
 * sessions written after waking must not be treated as live sleep stages.
 */
object SmartWakeEngine {
    enum class Stage { LIGHT, AWAKE, DEEP, REM, UNKNOWN }
    enum class Action { WAIT, EARLY_WAKE_CANDIDATE, DEADLINE_REACHED }
    enum class Evidence { BEFORE_WINDOW, NO_FRESH_DATA, DEEP_OR_REM, INSUFFICIENT_EVIDENCE,
        LIVE_LIGHT_OR_AWAKE, HEART_RATE_AND_MOVEMENT_PROXY, DEADLINE }

    data class Observation(
        val timeMs: Long,
        val bpm: Int? = null,
        /** Normalized 0..1 *calibrated* movement indicator, not raw accelerometer. */
        val movement: Double? = null,
        /** Only if a provider really supplies a CURRENT sleep stage. */
        val stage: Stage = Stage.UNKNOWN
    )

    data class Decision(val action: Action, val evidence: Evidence)

    fun evaluate(
        nowMs: Long,
        windowStartMs: Long,
        deadlineMs: Long,
        observations: List<Observation>,
        baselineBpm: Int? = null
    ): Decision {
        require(deadlineMs > windowStartMs) { "Invalid wake window" }
        require(deadlineMs - windowStartMs <= 90L * 60_000) { "Wake window too long" }
        if (nowMs < windowStartMs) return Decision(Action.WAIT, Evidence.BEFORE_WINDOW)
        // A device-side backup alarm MUST have been independently confirmed.
        if (nowMs >= deadlineMs) return Decision(Action.DEADLINE_REACHED, Evidence.DEADLINE)

        val fresh = observations
            .asSequence()
            .filter { it.timeMs in windowStartMs..nowMs && nowMs - it.timeMs <= 120_000L }
            .filter { it.bpm == null || it.bpm in 30..220 }
            .filter { it.movement == null || (it.movement in 0.0..1.0 && it.movement.isFinite()) }
            .distinctBy { it.timeMs }
            .sortedBy { it.timeMs }
            .toList()
            .takeLast(4)
        if (fresh.size < 2) return Decision(Action.WAIT, Evidence.NO_FRESH_DATA)
        val latest = fresh.last()
        if (latest.stage == Stage.DEEP || latest.stage == Stage.REM) {
            return Decision(Action.WAIT, Evidence.DEEP_OR_REM)
        }
        val recent = fresh.takeLast(3)
        val spaced = recent.zipWithNext().all { (a, b) ->
            b.timeMs - a.timeMs in 20_000L..90_000L
        }
        if (!spaced) return Decision(Action.WAIT, Evidence.INSUFFICIENT_EVIDENCE)

        // Require sustained *verified live* stage indications, never a single sample.
        if (recent.size >= 2 && recent.takeLast(2).all {
            it.stage == Stage.LIGHT || it.stage == Stage.AWAKE
        }) {
            return Decision(Action.EARLY_WAKE_CANDIDATE, Evidence.LIVE_LIGHT_OR_AWAKE)
        }

        // No live stage? Only a conservative waking-proxy, NOT a sleep-stage diagnosis.
        // The movement signal and baseline must be calibrated for this device/user.
        if (recent.size == 3 && baselineBpm in 35..100 &&
            recent.takeLast(2).all { sample ->
                sample.bpm != null && sample.bpm >= baselineBpm!! + 8 &&
                    sample.movement != null && sample.movement >= 0.65
            }) {
            return Decision(Action.EARLY_WAKE_CANDIDATE, Evidence.HEART_RATE_AND_MOVEMENT_PROXY)
        }
        return Decision(Action.WAIT, Evidence.INSUFFICIENT_EVIDENCE)
    }
}
