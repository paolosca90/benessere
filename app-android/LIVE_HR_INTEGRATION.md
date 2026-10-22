# FC Bluetooth live: Benessere Android → VPS → web

## Funzionamento verificato vs previsto
- L'utente ha osservato in Benessere TEST FC diretta di 69, 72, 73 bpm, confrontabile con Zepp.
- L'aggiornamento v0.2.5 aggiunge una funzione **opt-in** per inviare campioni via HTTPS.
- Al massimo un campione ogni 3 s mentre l'attività Android è visibile e l'FC BLE arriva davvero.
- `POST /api/v1/live-heart-rate` usa il token Android esistente; non invia MAC, chiave Zepp o altre informazioni BLE sensibili.
- La nuova tabella `live_heart_samples` è separata da `hr_samples` (Health Connect), con retention massima di 30 min per le righe ripulite durante l'ingest.
- `GET /v1/live-heart-rate`, autenticato in FastAPI, mostra un valore live soltanto se ricevuto negli ultimi 15 s.
- La dashboard effettua polling ogni 3 s solo quando è visibile; offline / errore sono espliciti.
- Non avviare due app Android che trasmettono FC live contemporaneamente; l'MVP presuppone un solo utente/dispositivo.

## Installazione Android test
Gli APK GitHub Actions debug cambiano firma da un run all'altro.
Se `benessere-v0.2.5-TEST-installabile` rifiuta l'aggiornamento
della TEST 0.2.4, **disinstalla soltanto Benessere TEST**, non Benessere
originale. La TEST non condivide né impostazioni né token con l'originale.

1. Installa la nuova TEST 0.2.5.
2. Apri Zepp e assicurati che l'Helio Strap trasmetta FC standard.
3. Da Benessere TEST: imposta l'URL HTTPS del server e il token Android già in uso (non condividerlo in chat), poi premi Salva.
4. Lascia disattivata la sincronizzazione periodica Health Connect della TEST se l'app originale la gestisce già.
5. Scansiona BLE, scegli il dispositivo vicino, premi FC standard e verifica che arrivi FC live.
6. Abilita «Invia FC Bluetooth live alla dashboard»: consenso inizialmente disattivato.
7. Lascia la TEST aperta per il test e verifica il pannello «Frequenza cardiaca in tempo reale» sul sito (richiede anche aggiornamento server).
8. Spegni il consenso / chiudi la connessione per confermare che la dashboard non mostri più un dato come live dopo 15 s.

## Server e produzione
Android da solo non basta: il server Android deve utilizzare il
nuovo `sync_server.py` e `benessere/live_heart.py`, mentre la webapp
richiede la nuova immagine Next.js/FastAPI. Non pubblicare `/v1/*`
senza autenticazione, non disabilitare Caddy e non sovrascrivere
`/opt/benessere/data/benessere.db`.

Non è un dispositivo medico né un sistema di allarme cardiaco;
non invia notifiche cliniche.
