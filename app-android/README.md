# Benessere — app Android

La "nostra app": coach personale CrossFit-first basato sui dati dell'Helio Strap.
Progetto Kotlin + Jetpack Compose (Material 3, dark-first), apribile in Android Studio.

## Requisiti

- **Android Studio** Koala/Ladybug o successivo (porta JDK 17 e SDK 34 incorporati)
- Telefono Android 9+ (min SDK 28) con:
  - app **Zepp** installata e sincronizzata con lo strap
  - **Health Connect** attivo (integrato su Android 14+; app separata su 9–13)
  - sincronizzazione Zepp → Health Connect abilitata nelle impostazioni dell'app Zepp

## Cosa contiene la 0.2.0

| Modulo | Stato | Note |
|---|---|---|
| `health/HealthConnectReader` | ✅ funzionale | legge FC, sonno, sessioni, passi, calorie, SpO2, peso di oggi dal canale near real-time |
| `alarm/SmartAlarmScheduler` | ✅ funzionale | sveglia intelligente **L1**: sveglie multiple nella finestra di risveglio via `AlarmManager.setAlarmClock` |
| `ble/HuamiProtocol` | ✅ costanti reali | porting da Gadgetbridge (AGPL): servizi FEE0/FEE1/180D, auth 3-step, comandi FC legacy |
| `ble/HuamiBleClient` | 🟡 skeleton | scan, connessione GATT, handshake auth con chiave di pairing (AES/ECB), sottoscrizione FC standard. **Il percorso comandi Zepp OS (chunked-transfer 0x0016/0x0017) è da validare** con l'analisi REA (docs/06) |
| UI (`MainActivity`) | ✅ base | dati di oggi, sync backend, strap Bluetooth (log + FC live), sveglia |
| `health/HealthSyncClient` | ✅ compilato | invio al server con token, HTTPS o HTTP solo dopo consenso LAN |
| `health/HealthSyncJobService` | 🟡 da verificare sul telefono | job periodico ogni ora dove Android consente lettura Health Connect in background; fallback alla sincronizzazione all'apertura |

## Come si costruisce

1. Apri Android Studio → *Open* → seleziona la cartella `app-android`
2. Attendi la sincronizzazione Gradle (genera anche il wrapper al primo build)
3. *Run* ▶ sul telefono collegato con debug USB attivo

## Cose note

- Il client BLE richiede la **chiave di pairing** generata dall'app Zepp (32 cifre hex): vedi `docs/06-rea-analisi.md` per come estrarla.
- Le API BLE deprecate (`characteristic.value`) sono usate di proposito: funzionano su tutte le versioni target.
- La fascia pettorale BLE standard (es. Polar H10, CooSpo) è già visibile in scansione e la FC arriva via 180D/2A37 senza autenticazione: è il percorso live garantito durante i WOD.

## Health Connect: gestione permessi

Dalla versione 0.1.2 è disponibile una schermata informativa per la richiesta dati prevista da Android 14+, corregge i filtri di intent nel manifest e permette di aprire direttamente **Gestisci Health Connect**. Se **Permessi** non apre una finestra perché le autorizzazioni sono già concesse, compare un messaggio; dopo le modifiche in Impostazioni l'app ricontrolla gli accessi. Usa **Aggiorna** per leggere i dati.

## Trasferimento Android → PC

L'app 0.2.0 invia via HTTP autenticato (LAN privata e consenso esplicito) oppure HTTPS verso un server Benessere sulla porta 8765. Leggi [docs/10-sync-android.md](../docs/10-sync-android.md) per configurazione, limiti e sicurezza. Non trasmette nulla senza un server/token configurati.

## Prossimi passi

- [ ] Prima esecuzione sul telefono: verificare permessi + lettura Health Connect coi dati reali
- [ ] Sessione REA sull'APK Zepp → confermare frame chunked-transfer per FC live e sveglie sullo strap
- [ ] Modulo "tag allenamento" (notifica post-sessione: forza/metcon/gymnastics/tennis + RPE)
- [x] Backend PC + invio in LAN con token; da collaudare end-to-end sul telefono reale
