package com.benessere.app.alarm

import org.junit.Assert.assertEquals
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class SmartWakeEngineTest {
    private val deadline = 10_000_000L
    private val start = deadline - 30 * 60_000L
    private val now = deadline - 10 * 60_000L

    @Test fun neverWakesOutsideWindow() {
        val d = SmartWakeEngine.evaluate(start - 1, start, deadline, emptyList())
        assertEquals(SmartWakeEngine.Action.WAIT, d.action)
    }

    @Test fun deadlineAlwaysHasPriorityButIsNotAnAck() {
        val d = SmartWakeEngine.evaluate(deadline, start, deadline, emptyList())
        assertEquals(SmartWakeEngine.Action.DEADLINE_REACHED, d.action)
    }

    @Test fun rejectsStaleData() {
        val samples = listOf(
            SmartWakeEngine.Observation(now - 190_000L, stage = SmartWakeEngine.Stage.LIGHT),
            SmartWakeEngine.Observation(now - 140_000L, stage = SmartWakeEngine.Stage.LIGHT)
        )
        assertEquals(SmartWakeEngine.Evidence.NO_FRESH_DATA,
            SmartWakeEngine.evaluate(now, start, deadline, samples).evidence)
    }

    @Test fun twoRecentLiveLightSamplesAreCandidate() {
        val samples = listOf(
            SmartWakeEngine.Observation(now - 65_000L, stage = SmartWakeEngine.Stage.LIGHT),
            SmartWakeEngine.Observation(now - 25_000L, stage = SmartWakeEngine.Stage.LIGHT)
        )
        val d = SmartWakeEngine.evaluate(now, start, deadline, samples)
        assertEquals(SmartWakeEngine.Action.EARLY_WAKE_CANDIDATE, d.action)
        assertEquals(SmartWakeEngine.Evidence.LIVE_LIGHT_OR_AWAKE, d.evidence)
    }

    @Test fun latestDeepStageVetoesWake() {
        val samples = listOf(
            SmartWakeEngine.Observation(now - 65_000L, stage = SmartWakeEngine.Stage.LIGHT),
            SmartWakeEngine.Observation(now - 25_000L, stage = SmartWakeEngine.Stage.DEEP)
        )
        assertEquals(SmartWakeEngine.Evidence.DEEP_OR_REM,
            SmartWakeEngine.evaluate(now, start, deadline, samples).evidence)
    }

    @Test fun movementAndPulseRiseAreOnlyProxyNotStage() {
        val samples = listOf(
            SmartWakeEngine.Observation(now - 110_000L, bpm = 51, movement = 0.1),
            SmartWakeEngine.Observation(now - 70_000L, bpm = 62, movement = 0.71),
            SmartWakeEngine.Observation(now - 30_000L, bpm = 61, movement = 0.8)
        )
        val d = SmartWakeEngine.evaluate(now, start, deadline, samples, baselineBpm = 52)
        assertEquals(SmartWakeEngine.Evidence.HEART_RATE_AND_MOVEMENT_PROXY, d.evidence)
        assertEquals(SmartWakeEngine.Action.EARLY_WAKE_CANDIDATE, d.action)
        assertEquals(SmartWakeEngine.Action.WAIT,
            SmartWakeEngine.evaluate(now, start, deadline, samples, baselineBpm = null).action)
    }

    @Test fun invalidOrBurstySamplesCannotTrigger() {
        val samples = listOf(
            SmartWakeEngine.Observation(now - 2000L, stage = SmartWakeEngine.Stage.LIGHT),
            SmartWakeEngine.Observation(now - 1000L, stage = SmartWakeEngine.Stage.LIGHT)
        )
        assertEquals(SmartWakeEngine.Action.WAIT,
            SmartWakeEngine.evaluate(now, start, deadline, samples).action)
    }

    @Test fun commandPayloadIsBoundedAndNeverUsesUnverifiedSmartFlag() {
        val payload = ZeppOsAlarmCodec.createEnabled(0, 7, 30)
        assertArrayEquals(byteArrayOf(3, 1, 4, 0, 7, 30, 0, 0, 0, 0, 0, 0), payload)
        assertArrayEquals(byteArrayOf(9), ZeppOsAlarmCodec.requestAlarms())
        assertThrows(IllegalArgumentException::class.java) { ZeppOsAlarmCodec.createEnabled(10, 7, 30) }
    }
}
