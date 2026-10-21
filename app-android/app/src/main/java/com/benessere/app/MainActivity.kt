package com.benessere.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.core.content.ContextCompat
import androidx.health.connect.client.HealthConnectClient
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.benessere.app.alarm.SmartAlarmScheduler
import com.benessere.app.ble.HuamiBleClient
import com.benessere.app.health.HealthConnectReader
import com.benessere.app.health.HealthSyncClient
import com.benessere.app.health.HealthSyncScheduler
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.format.DateTimeFormatter

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkScheme()) {
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    BenessereApp()
                }
            }
        }
    }

    private fun darkScheme() = androidx.compose.material3.darkColorScheme(
        primary = Color(0xFF4ADE80),
        secondary = Color(0xFF38BDF8),
        background = Color(0xFF0B1220),
        surface = Color(0xFF111A2C),
        onPrimary = Color(0xFF06130B),
        onBackground = Color(0xFFE2E8F0),
        onSurface = Color(0xFFE2E8F0)
    )
}

@Composable
fun BenessereApp() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val scroll = rememberScrollState()

    // ---- permessi runtime ----
    val btPermissions = mutableListOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    if (Build.VERSION.SDK_INT >= 33) btPermissions.add(Manifest.permission.POST_NOTIFICATIONS)
    var permissionsGranted by remember {
        mutableStateOf(btPermissions.all {
            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
        })
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissionsGranted = it.values.all { granted -> granted } }

    // ---- Health Connect ----
    val reader = remember {
        runCatching { HealthConnectReader(context) }.getOrNull()
    }
    var hcGranted by remember { mutableStateOf(false) }
    var hcSnapshot by remember { mutableStateOf<HealthConnectReader.Snapshot?>(null) }
    var hcMessage by remember { mutableStateOf("") }

    suspend fun refreshHealthConnect() {
        val r = reader ?: return
        try {
            hcGranted = r.hasAllPermissions()
            if (hcGranted) {
                hcSnapshot = r.snapshot()
                hcMessage = ""
            } else {
                hcSnapshot = null
                hcMessage = "Permessi Health Connect mancanti o incompleti: premi Permessi e consenti tutte le letture richieste."
            }
        } catch (e: Exception) {
            hcSnapshot = null
            hcMessage = "Errore Health Connect: ${e.message ?: e.javaClass.simpleName}"
        }
    }

    // Rileggi i permessi già concessi anche se l'app viene riaperta.
    LaunchedEffect(reader) { refreshHealthConnect() }
    // Torna qui anche quando i permessi vengono modificati dalle Impostazioni Android.
    DisposableEffect(context, reader) {
        val lifecycle = (context as? ComponentActivity)?.lifecycle
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) scope.launch { refreshHealthConnect() }
        }
        lifecycle?.addObserver(observer)
        onDispose { lifecycle?.removeObserver(observer) }
    }

    val hcContract = remember(reader) { reader?.permissionContract }
    val bgLauncher = if (hcContract != null) {
        rememberLauncherForActivityResult(hcContract) { _ ->
            scope.launch { refreshHealthConnect() }
        }
    } else null
    val hcLauncher: androidx.activity.compose.ManagedActivityResultLauncher<Set<String>, Set<String>>? =
        if (hcContract != null) {
            rememberLauncherForActivityResult(hcContract) { _ ->
                scope.launch { refreshHealthConnect() }
            }
        } else {
            null
        }

    // ---- BLE ----
    val bleClient = remember { HuamiBleClient(context) }
    val bleLog = remember { androidx.compose.runtime.mutableStateListOf<String>() }
    var liveHr by remember { mutableStateOf<Int?>(null) }
    DisposableEffect(Unit) {
        onDispose { runCatching { bleClient.disconnect() } }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(scroll)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Benessere", style = MaterialTheme.typography.headlineLarge)
        Text("Coach personale — Helio Strap, CrossFit-first", style = MaterialTheme.typography.bodySmall)

        if (!permissionsGranted) {
            Button(onClick = { permissionLauncher.launch(btPermissions.toTypedArray()) }) {
                Text("Concedi permessi (Bluetooth + notifiche)")
            }
        }

        // ---- Scheda dati di oggi (Health Connect) ----
        SectionCard("Dati di oggi — Health Connect") {
            if (reader == null) {
                Text("Health Connect non disponibile su questo telefono (serve Android 8+ con l'app Health Connect o Android 14+).")
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = {
                        scope.launch {
                            try {
                                if (reader.hasAllPermissions()) {
                                    hcMessage = "Permessi già concessi. Usa Aggiorna per leggere i dati oppure Gestisci Health Connect per modificarli."
                                } else {
                                    hcMessage = "Richiesta autorizzazioni Health Connect in corso…"
                                    if (hcLauncher == null) {
                                        hcMessage = "Impossibile aprire la richiesta. Usa Gestisci Health Connect."
                                    } else {
                                        hcLauncher.launch(reader.permissions)
                                    }
                                }
                            } catch (e: Exception) {
                                hcMessage = "Apertura permessi non riuscita: ${e.message ?: e.javaClass.simpleName}. Usa Gestisci Health Connect."
                            }
                        }
                    }) { Text("Permessi") }
                    Button(onClick = { scope.launch { refreshHealthConnect() } }) { Text("Aggiorna") }
                }
                Button(onClick = {
                    try {
                        context.startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS))
                    } catch (e: Exception) {
                        hcMessage = "Impossibile aprire Health Connect: ${e.message ?: e.javaClass.simpleName}. Cercalo dalle Impostazioni Android."
                    }
                }) { Text("Gestisci Health Connect") }
                if (hcMessage.isNotEmpty()) {
                    Text(hcMessage, color = MaterialTheme.colorScheme.secondary)
                }
                val s = hcSnapshot
                if (s == null) {
                    Text("Nessun dato letto: concedi i permessi e assicurati che l'app Zepp sincronizzi su Health Connect.")
                } else {
                    StatLine("Campioni FC oggi", s.heartRateSamples.toString())
                    StatLine("Ultima FC", s.lastHeartRate?.let { "$it bpm" } ?: "—")
                    StatLine("Sonno ultima notte", s.lastNightSleepMinutes?.let { "${it / 60}h ${it % 60}m" } ?: "—")
                    StatLine("Allenamenti oggi", s.exercisesToday.toString())
                    StatLine("Passi oggi", s.stepsToday.toString())
                    StatLine("Calorie totali oggi", s.totalCaloriesToday?.let { "%.0f kcal".format(it) } ?: "—")
                    StatLine("SpO2 ultimo", s.spo2Last?.let { "%.0f%%".format(it) } ?: "—")
                    StatLine("Peso ultimo", s.weightLastKg?.let { "%.1f kg".format(it) } ?: "—")
                }
            }
        }

        // ---- Sincronizzazione Android -> backend (nessun dato spedito senza configurazione) ----
        SectionCard("Sincronizzazione dati — PC / VPS") {
            var backendUrl by remember { mutableStateOf(HealthSyncClient.server(context)) }
            var backendToken by remember { mutableStateOf(HealthSyncClient.token(context)) }
            var allowLan by remember { mutableStateOf(HealthSyncClient.allowLocalHttp(context)) }
            var autoSync by remember { mutableStateOf(HealthSyncClient.autoEnabled(context)) }
            var syncStatus by remember { mutableStateOf(HealthSyncClient.lastStatus(context)) }
            var syncing by remember { mutableStateOf(false) }
            var lastForegroundAttempt by remember { mutableStateOf(0L) }

            // ON_RESUME intercetta sia l'avvio che il rientro da Zepp/Health Connect.
            // Limite: non fare piu' di un tentativo automatico ogni 15 minuti.
            DisposableEffect(context, autoSync) {
                val lifecycle = (context as? ComponentActivity)?.lifecycle
                val observer = LifecycleEventObserver { _, event ->
                    if (event == Lifecycle.Event.ON_RESUME && autoSync &&
                        HealthSyncClient.autoEnabled(context) && !syncing &&
                        HealthSyncClient.server(context).isNotBlank()
                    ) {
                        val now = System.currentTimeMillis()
                        if (now - lastForegroundAttempt >= 15 * 60 * 1000L) {
                            lastForegroundAttempt = now
                            scope.launch {
                                syncing = true
                                try { syncStatus = HealthSyncClient.sync(context) }
                                catch (e: Exception) {
                                    HealthSyncClient.recordError(context, e.message ?: "Errore di sync")
                                    syncStatus = HealthSyncClient.lastStatus(context)
                                } finally { syncing = false }
                            }
                        }
                    }
                }
                lifecycle?.addObserver(observer)
                onDispose { lifecycle?.removeObserver(observer) }
            }
            Text("Server sul PC o VPS. Nessuna trasmissione finché non configuri indirizzo e token.")
            OutlinedTextField(
                value = backendUrl, onValueChange = { backendUrl = it },
                label = { Text("URL backend (es. http://192.168.1.100:8766)") },
                modifier = Modifier.fillMaxWidth(), singleLine = true
            )
            OutlinedTextField(
                value = backendToken, onValueChange = { backendToken = it },
                label = { Text("Token di accesso del server") },
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth(), singleLine = true
            )
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(checked = allowLan, onCheckedChange = { allowLan = it })
                Text("Consento HTTP non cifrato solo sulla mia Wi-Fi privata")
            }
            Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Checkbox(checked = autoSync, onCheckedChange = { autoSync = it })
                Text("Sincronizza all'apertura + ogni ora dove Android lo consente")
            }
            if (reader != null && reader.backgroundAvailable) {
                Button(onClick = {
                    bgLauncher?.launch(setOf(HealthSyncClient.BACKGROUND_PERMISSION))
                }) { Text("Autorizza lettura in background") }
            } else {
                Text("Background Health Connect non disponibile: funziona l'invio manuale e all'apertura.")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    scope.launch {
                        try {
                            HealthSyncClient.save(context, backendUrl, backendToken, allowLan, autoSync)
                            val backgroundOk = reader?.backgroundGranted() == true
                            HealthSyncScheduler.configure(context, autoSync && backgroundOk)
                            syncStatus = if (autoSync && !backgroundOk) {
                                "Configurazione salvata. Sync automatica all'apertura; per quella oraria autorizza il background."
                            } else "Configurazione salvata."
                        } catch (e: Exception) {
                            syncStatus = "Errore: ${e.message ?: e.javaClass.simpleName}"
                        }
                    }
                }) { Text("Salva") }
                Button(enabled = !syncing, onClick = {
                    scope.launch {
                        syncing = true
                        try {
                            HealthSyncClient.save(context, backendUrl, backendToken, allowLan, autoSync)
                            HealthSyncScheduler.configure(context, autoSync && (reader?.backgroundGranted() == true))
                            syncStatus = HealthSyncClient.sync(context)
                        } catch (e: Exception) {
                            HealthSyncClient.recordError(context, e.message ?: e.javaClass.simpleName)
                            syncStatus = HealthSyncClient.lastStatus(context)
                        } finally { syncing = false }
                    }
                }) { Text(if (syncing) "Invio…" else "Sincronizza ora") }
            }
            if (syncStatus.isNotEmpty()) Text(syncStatus)
            Text("Consigliato HTTPS per VPS. Su LAN HTTP il token e i dati transitano senza cifratura; usa solo una rete privata fidata.")
        }

        // ---- Scheda BLE ----
        SectionCard("Helio Strap — Bluetooth") {
            var mac by remember { mutableStateOf("") }
            var key by remember { mutableStateOf("") }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    bleClient.listener = object : HuamiBleClient.Listener {
                        override fun onLog(line: String) { bleLog.add(0, line); if (bleLog.size > 50) bleLog.removeAt(bleLog.size - 1) }
                        override fun onHeartRate(bpm: Int) { liveHr = bpm }
                        override fun onAuthResult(success: Boolean) {}
                    }
                    if (permissionsGranted) bleClient.startScan() else permissionLauncher.launch(btPermissions.toTypedArray())
                }) { Text("Scansiona") }
                Button(onClick = { bleClient.disconnect() }) { Text("Disconnetti") }
            }
            liveHr?.let { Text("FC live: $it bpm", style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary) }
            OutlinedTextField(
                value = mac, onValueChange = { mac = it },
                label = { Text("MAC dello strap (es. C8:00:00:00:00:00)") },
                modifier = Modifier.fillMaxWidth(), singleLine = true
            )
            OutlinedTextField(
                value = key, onValueChange = { key = it },
                label = { Text("Chiave di pairing (32 cifre hex — docs/06)") },
                modifier = Modifier.fillMaxWidth(), singleLine = true
            )
            Button(
                onClick = { bleClient.connect(mac.trim(), key.trim()) },
                enabled = permissionsGranted && mac.isNotBlank() && key.isNotBlank()
            ) { Text("Connetti e autentica") }
            Column {
                bleLog.take(12).forEach { line ->
                    Text("• $line", style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        // ---- Scheda sveglia ----
        SectionCard("Sveglia intelligente (L1)") {
            var startField by remember { mutableStateOf("06:30") }
            var endField by remember { mutableStateOf("07:00") }
            var stepField by remember { mutableStateOf("10") }
            OutlinedTextField(value = startField, onValueChange = { startField = it }, label = { Text("Inizio finestra (HH:mm)") }, singleLine = true)
            OutlinedTextField(value = endField, onValueChange = { endField = it }, label = { Text("Fine finestra (HH:mm)") }, singleLine = true)
            OutlinedTextField(value = stepField, onValueChange = { stepField = it }, label = { Text("Passo minuti") }, singleLine = true)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = {
                    val fmt = DateTimeFormatter.ofPattern("HH:mm")
                    val today = LocalDateTime.now()
                    scheduleAlarms(
                        context,
                        today.with(LocalTime.parse(startField, fmt)),
                        today.with(LocalTime.parse(endField, fmt)),
                        stepField.toLongOrNull() ?: 10
                    )
                }) { Text("Programma per domattina") }
                Button(onClick = { SmartAlarmScheduler.cancelAll(context) }) { Text("Annulla") }
            }
            Text(
                "L1 = sveglie multiple nella finestra prevista. L2 (FC live nella finestra) arriva col modulo BLE.",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

private fun scheduleAlarms(context: android.content.Context, start: LocalDateTime, end: LocalDateTime, step: Long) {
    val tomorrowStart = start.plusDays(1)
    val tomorrowEnd = end.plusDays(1)
    SmartAlarmScheduler.schedule(context, tomorrowStart, tomorrowEnd, step)
}

@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            content()
        }
    }
}

@Composable
private fun StatLine(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.secondary)
    }
}
