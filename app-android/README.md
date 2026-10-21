# Benessere — app Android

La "nostra app": coach personale CrossFit-first basato sui dati dell'Helio Strap.
Progetto Kotlin + Jetpack Compose (Material 3, dark-first), apribile in Android Studio.

## Requisiti

- **Android Studio** Koala/Ladybug o successivo (porta JDK 17 e SDK 34 incorporati)
- Telefono Android 9+ (min SDK 28) con:
  - app **Zepp** installata e sincronizzata con lo strap
  - **Health Connect** attivo (integrato su Android 14+; app separata su 9–13)
  - sincronizzazione Zepp → Health Connect abilitata nelle impostazioni dell'app Zepp

## Cosa contiene la 0.1.0

| Modulo | Stato | Note |
|---|---|---|
| `health/HealthConnectReader` | ✅ funzionale | legge FC, sonno, sessioni, passi, calorie, SpO2, peso di oggi dal canale near real-time |
| `alarm/SmartAlarmScheduler` | ✅ funzionale | sveglia intelligente **L1**: sveglie multiple nella finestra di risveglio via `AlarmManager.setAlarmClock` |
| `ble/HuamiProtocol` | ✅ costanti reali | porting da Gadgetbridge (AGPL): servizi FEE0/FEE1/180D, auth 3-step, comandi FC legacy |
| `ble/HuamiBleClient` | 🟡 skeleton | scan, connessione GATT, handshake auth con chiave di pairing (AES/ECB), sottoscrizione FC standard. **Il percorso comandi Zepp OS (chunked-transfer 0x0016/0x0017) è da validare** con l'analisi REA (docs/06) |
| UI (`MainActivity`) | ✅ base | tre schede: dati di oggi, strap Bluetooth (log + FC live), sveglia |

## Come si costruisce

1. Apri Android Studio → *Open* → seleziona la cartella `app-android`
2. Attendi la sincronizzazione Gradle (genera anche il wrapper al primo build)
3. *Run* ▶ sul telefono collegato con debug USB attivo

## Cose note

- Il client BLE richiede la **chiave di pairing** generata dall'app Zepp (32 cifre hex): vedi `docs/06-rea-analisi.md` per come estrarla.
- Le API BLE deprecate (`characteristic.value`) sono usate di proposito: funzionano su tutte le versioni target.
- La fascia pettorale BLE standard (es. Polar H10, CooSpo) è già visibile in scansione e la FC arriva via 180D/2A37 senza autenticazione: è il percorso live garantito durante i WOD.

## Prossimi passi

- [ ] Prima esecuzione sul telefono: verificare permessi + lettura Health Connect coi dati reali
- [ ] Sessione REA sull'APK Zepp → confermare frame chunked-transfer per FC live e sveglie sullo strap
- [ ] Modulo "tag allenamento" (notifica post-sessione: forza/metcon/gymnastics/tennis + RPE)
- [ ] Colloquio col backend PC (invio dati in LAN)
