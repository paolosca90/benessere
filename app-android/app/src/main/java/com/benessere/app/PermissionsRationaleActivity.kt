package com.benessere.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Informativa sui permessi Health Connect richiamabile dal pannello privacy Android. */
class PermissionsRationaleActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    Column(
                        modifier = Modifier
                            .verticalScroll(rememberScrollState())
                            .padding(24.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp)
                    ) {
                        Text("Benessere — uso dei dati salute", style = MaterialTheme.typography.headlineSmall)
                        Text("Benessere richiede accesso in sola lettura a frequenza cardiaca, sonno, allenamenti, passi, calorie, saturazione e peso per mostrare i dati della giornata e aiutarti a interpretare allenamento e recupero.")
                        Text("Questa versione legge Health Connect direttamente sul telefono. Non invia automaticamente questi dati al PC o a servizi online e non conserva le misurazioni Health Connect in un archivio remoto.")
                        Text("Puoi modificare o revocare i permessi in qualsiasi momento nelle impostazioni di Health Connect. Se li revochi, Benessere non potrà più leggere quei dati.")
                        Text("Le informazioni mostrate hanno finalità di benessere e non sostituiscono il parere medico.")
                        Button(onClick = { finish() }) { Text("Chiudi") }
                    }
                }
            }
        }
    }
}
