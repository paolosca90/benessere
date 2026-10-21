# 06 — Analisi REA dell'app Zepp (reverse engineering)

[REA](https://github.com/morluto/rea) ("Reverse Engineer Anything", MIT) è il toolkit che usiamo per analizzare **l'APK dell'app Zepp** e confermare dal codice reale i dettagli che il nostro client BLE e l'ingest cloud assumono.

Stato: CLI REA installata e verificata (v6.7.0, funziona con Node 22.14 — l'engine richiede ≥22.19, warning non bloccante). Mancano: **APK di Zepp** (dal telefono) e **JDK 17+** (per apktool/JADX usati da REA).

## Perché serve

| Domanda aperta | Dove la risposta |
|---|---|
| Come vengono incapsulati i comandi Zepp OS (FC live, sveglie) nel chunked-transfer 0x0016/0x0017? | codice BLE dell'APK |
| La FC live dell'Helio Strap arriva su 180D/2A37 o solo via chunked? | codice BLE dell'APK |
| Come si scaricano gli zip di FC al secondo (`second_heart_rate`)? | codice cloud dell'APK |
| Esiste l'endpoint cibo/nutrizione e che forma ha? | codice cloud dell'APK (vedi anche `lcanis/zepp-food-extractor`) |
| Come si scrive una sveglia sullo strap via protocollo? | codice BLE dell'APK |

Le costanti base del protocollo sono già in `app-android/.../ble/HuamiProtocol.kt` (porting da Gadgetbridge, `vendor/gadgetbridge-protocol/HuamiService.java`); REA serve per il **livello Zepp OS sopra** quelle basi.

## Esito della sessione (2026-10-20)

Setup riuscito: APK estratto dal Pixel 9 Pro XL via adb (Mac) e trasferito via LAN
(`base.apk`, 184.321.007 byte, sha256 `1c5271ea…`). Toolchain portabile in `vendor/`:
JDK Temurin 21, apktool 3.0.3 (+ launcher `apktool.bat`), jadx 1.5.6.

- REA installato e funzionante, ma `decode-android-resources` fallisce con
  `unreadable_output` attraverso il launcher .bat (probabile incompatibilità del
  wrapper, non dell'APK). Sostituito con **apktool diretto** (stesso motore che REA
  invoca) + **jadx** per il codice: risultati equivalenti.
- Decodifica risorse completata in `vendor/zepp-apk/decoded/`, codice in `vendor/zepp-apk/jadx-out/`.

### Scoperte (risorse)

| Fatto | Evidenza |
|---|---|
| Package: `com.huami.watch.hmwatchmanager`, stack interno `com.xiaomi.hm.health.*` (classico Huami → la mappatura Gadgetbridge vale) | `AndroidManifest.xml` |
| **Nome in codice Helio Strap = `stuttgart`** (Pro = `stuttgartw`) | `res/values/strings.xml`: `<string name="stuttgart">Amazfit Helio Strap</string>` |
| Sveglia sul device: vibra all'orario impostato, si annulla picchiettando la parte frontale del device | stringa `alarm_stuttgart_close_tips` |
| Bind del device richiede il caricatore (pin a contatto) | `bind_stuttgart_*` |
| CDN upload: `upload-cdn.zepp.com` | strings/assets |
| Endpoint OAuth: auth.amazon.com / api.amazon.com/auth/o2/token (per login social) | `assets/api_key.txt` (JWE) |

## Procedura (per riferimento)

### 1. Preparazione PC (una volta)

```bash
# adb (zip ufficiale, ~5 MB): https://developer.android.com/tools/releases/platform-tools
# JDK: Android Studio porta già il suo JBR (…/Android Studio/jbr) oppure https://adoptium.net (Temurin 21)
java -version   # deve funzionare
adb version     # deve funzionare
```

**Se usi il Mac per collegare il telefono** (setup REA/project su Windows):

```bash
brew install --cask android-platform-tools   # installa adb
adb version
```

Poi estrai l'APK sul Mac e trasferisci `base.apk` nel progetto Windows
(`vendor/zepp-apk/base.apk`) con il metodo che preferisci (chiavetta, cloud, NAS).

### 2. Estrazione dell'APK

```bash
adb shell pm path com.huami.watch.hmwatchmanager   # elenca gli split
adb pull /data/app/…/base.apk vendor/zepp-apk/base.apk
```

### 3. Comandi REA

```bash
cd vendor/rea && npm install   # se si vuole usare da sorgente
# oppure via npx (già verificato):
npx -y rea-agents@latest capabilities                    # provider disponibili (JADX/apktool)
npx -y rea-agents@latest analyze ../zepp-apk/base.apk --json
npx -y rea-agents@latest decode-android-resources ../zepp-apk/base.apk
```

Stringhe/obiettivi da cercare nell'analisi:
- `00000016-0000-3512-2118-0009af100700` e `00000017-…` (chunked transfer 2021)
- `FEE1`, `00000009-…` (auth), `2A37` (FC standard)
- `second_heart_rate`, `fileInfo`, zip/COS (FC 1 s)
- `api-mifit`, `api-user`, `/v2/users/me/events` (cloud)
- `food`, `diet`, `nutrition` (endpoint nutrizione)
- `alarm` write (sveglie via protocollo)

Nota: `npx rea-agents setup` registra REA come MCP negli agent supportati (Claude Code, Codex, Cursor…); ZCode non compare nell'elenco ufficiale — usiamo la CLI, o la registrazione manuale del server MCP se il client la consente.

### 4. Chiave di pairing dello strap

Il nostro `HuamiBleClient` autentica con la chiave 16 byte generata dall'app Zepp al momento del pairing. Due modi per ottenerla:

1. **Logcat durante un re-pairing** (metodo classico documentato da Gadgetbridge): avviare `adb logcat`, filtrare per chiavi tipo `pair`/`key`/`mac`, quindi **riassociare** lo strap nell'app Zepp (rimuovi dispositivo → riaggiungi). La chiave appare nei log.
2. **Telefono rooted**: lettura del database dell'app Zepp.

Dopo l'estrazione, salvare la chiave solo nell'app (mai nel repo).

## Output atteso di questa sessione

| Domanda | Risposta trovata | Evidenza (file/classe/offset REA) |
|---|---|---|
| Frame FC live su chunked-transfer | **NO chunked 0x0016/17.** Trasporto reale = `HMSmartWatchTransportProfile`: servizio **FED0**, **write 0x0010 / notify 0x0011**, frame 20 byte con header 3 | `jadx-out/…/defpackage/oxk.java` (tag "HMSmartWatchTransportProfile") |
| File transfer | caratteristiche **0x0023 (send) / 0x0024 (receive)**, classe "FileReceiver" | `defpackage/zdh.java` |
| Altri canali | 0x0022 usato come socket **RFCOMM/SPP** (fallback seriale); FED1/FED2 definiti in `dcs.java` | `defpackage/n16.java`, `dcs.java` |
| Servizi assenti (bene saperlo) | **Nessun uso di FEE0/FEE1, auth classico 0x0009, servizio HR standard 180D/2A37** → FC live e comandi viaggiano nel protocollo app-layer (protobuf) sopra FED0/0010/11 | grep esaustivo UUID su tutto l'albero |
| Formato pacchetto FC live | Da ricostruire: protobuf app-layer sopra il trasporto. Riferimento pratico: codice Zepp OS di Gadgetbridge | — |
| Scrittura sveglie via BLE | Non ancora isolata (messaggi di config app-layer). Confermato dalle risorse: sveglia vibra sul device e si annulla picchiettando la parte frontale | stringa `alarm_stuttgart_close_tips` |
| Endpoint zip FC 1 s | `SecondHeartRateRemotePlugin`, fileType **`second_heart_rate`** (coerente con `/users/me/fileInfo/events` già esposto da zepp-health-cli) | `defpackage/jq30.java`, `kq30.java`, `com/huami/health/matrix/record/heartrate/SecondHeartRateRecord.java` |
| Endpoint food | Nessun path `/food` letterale nel Java (URL costruiti dinamicamente) — riferimento: repo `lcanis/zepp-food-extractor` | grep su `com/` |

### Impatto sul progetto

1. `HuamiBleClient`: il percorso legacy (auth 0x0009 + 180D/2A37) **non si applica all'Helio Strap** — resta per device Huami vecchi e come riferimento. Il percorso giusto da costruire in F3: FED0/0x0010/11 → framing 20/3 → protocollo protobuf Zepp OS (studio da `zdh.java` + Gadgetbridge ZeppOS).
2. La fascia pettorale BLE standard (180D/2A37) resta il canale live **garantito** per i WOD — nessun dipendente dal reverse engineering.
3. Il canale cloud (F0, zepp-health-cli) copre comunque tutta la storia: FC 1 s comprese (file `second_heart_rate`), HRV, sonno, temperature.
