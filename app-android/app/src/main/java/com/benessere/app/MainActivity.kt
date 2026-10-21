package com.benessere.app

import android.Manifest
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
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.benessere.app.alarm.SmartAlarmScheduler
import com.benessere.app.ble.HuamiBleClient
import com.benessere.app.health.HealthConnectReader
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
    val hcContract = remember(reader) { reader?.permissionContract }
    val hcLauncher: androidx.activity.compose.ManagedActivityResultLauncher<Set<String>, Set<String>>? =
        if (hcContract != null) {
            rememberLauncherForActivityResult(hcContract) { granted: Set<String> ->
                hcGranted = granted.isNotEmpty()
                if (hcGranted) {
                    scope.launch {
                        val r = reader ?: return@launch
                        hcSnapshot = runCatching { r.snapshot() }.getOrNull()
                    }
                }
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
                    Button(onClick = { hcLauncher?.launch(reader.permissions) }) { Text("Permessi") }
                    Button(
                        onClick = {
                            scope.launch {
                                hcGranted = reader.hasAllPermissions()
                                if (hcGranted) {
                                    hcSnapshot = runCatching { reader.snapshot() }.getOrNull()
                                }
                            }
                        },
                        enabled = hcGranted
                    ) { Text("Aggiorna") }
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
