# Helio Strap → PWA · FC Bluetooth live

**Stato:** primo flusso con conferma sul telefono del servizio SIG 180D (FC
69/72/73 bpm confrontata con Zepp), ma **non ancora verificato end-to-end** verso
la VPS. Nessun comando proprietario Zepp richiesto per la FC osservata.

## Architettura

1. Nell'app Android `Benessere TEST`, la pressione di **FC standard** instaura
   una connessione GATT BLE 180D e riceve notifiche della caratteristica 2A37.
2. La casella **Invia FC Bluetooth live alla dashboard** è disattivata per
   impostazione predefinita. Va abilitata esplicitamente: non modifica la sync
   automatica di Health Connect.
3. Solo mentre l'app è in primo piano, invia al massimo un dato ogni 3 s via
   HTTPS e Bearer token già previsto dall'API Android. Niente MAC, chiave BLE
   o identificativo del wearable viene inviato; `device_id` è il UUID casuale
   del telefono.
4. `POST /api/v1/live-heart-rate` sul backend `sync_server.py` convalida
   bpm, data, provenienza `ble_180d` e token.
5. I campioni vengono salvati in `live_heart_samples`, **separati** da
   `hr_samples` di Health Connect. Conservazione limitata a 30 minuti.
6. FastAPI espone `GET /v1/live-heart-rate` solo con token web interno.
   Next.js inoltra la richiesta via route handler autenticato lato server.
7. La PWA interroga ogni 3 s nelle sezioni Oggi e Salute; mostra una misura
   come `live` soltanto se il backend l'ha ricevuta entro 15 secondi.
   Altrimenti visualizza **Non connesso**, non un battito vecchio.

## Precauzioni

- L'app TEST è separata dall'app originale, non eredita URL/token.
- Non impostare mai token in `NEXT_PUBLIC_*` o nel repository.
- Non trasmettere campioni di prova al DB di produzione.
- Non è una misura medica e non supporta ancora una sessione BLE in background:
  chiudere l'app o disconnettersi interrompe l'invio.
- L'indirizzo BLE può essere casualizzato: rilevare la stessa FC in Zepp è
  un buon indizio d'identità, non una autenticazione crittografica del dispositivo.
- HRV e SpO₂ derivano da Health Connect/Zepp se disponibili; il flusso
  `ble_180d` fornisce **soltanto FC**, non sonno o HRV.
- Vibrazione/sveglia Strap ancora gestite da Zepp. La sveglia telefonica
  Benessere non va usata come unico allarme finché non collaudata.

## Verifiche automatiche

`python -m pytest tests/test_live_heart.py -q`:
- Autenticazione e lettura FastAPI attraverso SQLite di test.
- Rejection di bpm, sorgente o timestamp non validi.
- Duplicati idempotenti, TTL, stato stale, pulizia dopo 30 minuti.
- Verifica assenza di inserimenti nella tabella Health Connect `hr_samples`.

## Distribuzione

- Richiede **nuova APK Android**, nuovo sorgente `sync_server.py`,
  modulo `benessere/live_heart.py`, nuove immagini `benessere-api-v2` e
  `benessere-pwa-preview` corrispondenti al medesimo commit.
- Non basta caricare l'APK: il vecchio backend Android risponderebbe 404
  su `/api/v1/live-heart-rate`.
- Prima di aggiornare, eseguire backup del database e annotare lo stato
  dei servizi in produzione. Non riavviare MCP, Sheets Bridge o YouTubeCreatorOS.
- L'app originale può continuare a sincronizzare via Health Connect; non attivare
  due sincronizzazioni automatiche identiche su APK normale e TEST.
