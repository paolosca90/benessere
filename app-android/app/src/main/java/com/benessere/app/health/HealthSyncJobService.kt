package com.benessere.app.health

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.util.concurrent.TimeUnit

/** JobScheduler: intervallo minimo di un'ora, esecuzione best effort (Doze/rete). */
object HealthSyncScheduler {
    private const val JOB_ID = 167810

    fun configure(context: Context, enabled: Boolean) {
        val manager = context.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
        if (!enabled) {
            manager.cancel(JOB_ID)
            return
        }
        val info = JobInfo.Builder(JOB_ID, ComponentName(context, HealthSyncJobService::class.java))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPeriodic(TimeUnit.HOURS.toMillis(1))
            .setPersisted(true)
            .build()
        if (manager.schedule(info) == JobScheduler.RESULT_FAILURE) {
            throw IllegalStateException("Android non ha accettato la sincronizzazione periodica")
        }
    }
}

class HealthSyncJobService : JobService() {
    private var task: Job? = null

    override fun onStartJob(params: JobParameters): Boolean {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
        task = scope.launch {
            try {
                if (HealthSyncClient.autoEnabled(applicationContext)) {
                    val reader = HealthConnectReader(applicationContext)
                    if (!reader.backgroundGranted()) {
                        HealthSyncClient.recordError(
                            applicationContext,
                            "Lettura Health Connect in background non autorizzata o non supportata. Apri Benessere."
                        )
                    } else {
                        HealthSyncClient.sync(applicationContext)
                    }
                }
            } catch (e: Exception) {
                HealthSyncClient.recordError(applicationContext, e.message ?: e.javaClass.simpleName)
            } finally {
                jobFinished(params, false)
                scope.cancel()
            }
        }
        return true
    }

    override fun onStopJob(params: JobParameters): Boolean {
        task?.cancel()
        return true
    }
}
