# 02 — Architettura

## Principi

- **Local-first**: SQLite sul PC, nessun cloud di terze parti. I dati di salute non lasciano la macchina dell'utente.
- **Ingest-then-cache**: ogni importazione scrive nel DB locale; se un canale dati muore, lo storico resta nostro.
- **Una pipeline, molte viste**: i quattro pilastri sono viste/derivate sugli stessi dati grezzi, non moduli separati.

## Vista d'insieme

```
┌─────────────────────────────── TELEFONO ───────────────────────────────┐
│  Helio Strap ─BLE─> app Zepp ──> cloud Zepp                            │
│        (pairing esclusivo: una sola app host)                          │
└────────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼──────────────────────────┐
        │ canale C (primario)     │ canale A/B (fallback)    │ canale D (fase 3, opzionale)
        │ API non ufficiale       │ Health Connect /         │ protocollo live-HR
        │ cloud Zepp, da PC       │ HealthKit via bridge     │ Huami in app Android
        ▼                         ▼                          ▼
┌───────────────────────  BACKEND PYTHON (PC)  ─────────────────────────┐
│  ingest │ storage SQLite │ analytics │ scheduler (cron mattutino)     │
└───────────────────────────────┬───────────────────────────────────────┘
                                ▼
              Dashboard web locale + report giornaliero
              (readiness, target nutrizionali, carico, sonno)
```

## Stack

| Componente | Scelta | Perché |
|---|---|---|
| Backend / analisi | **Python 3.12+** | Ecosistema dati/scientifico, `zepp-health-cli` è già Python, integrabile con tutto |
| Storage | **SQLite** (WAL) | Zero setup, portabile, backup = un file |
| UI v1 | **Streamlit** | Dashboard analitica in ore, non settimane; sostituibile poi con FastAPI+web |
| Ingest cloud | script basato su `zepp-health-cli` (MIT) | Login con credenziali Zepp, pull giornaliero |
| Bridge Android (fase 2/3) | **Kotlin, minimo** | Solo per Health Connect e FC live; parla REST col backend |
| Scheduler | Task Scheduler Windows / cron | Sync ogni mattina + ricalcolo metriche |

## Modello dati (bozza SQLite)

```sql
-- GREZZI (una tabella per tipo di dato, append-only, dedup su chiave naturale)
CREATE TABLE hr_samples    (ts TEXT PRIMARY KEY, bpm INTEGER, source TEXT);      -- ts ISO8601
CREATE TABLE hrv_daily     (night_date TEXT PRIMARY KEY, rmssd_ms REAL, source TEXT);
CREATE TABLE temp_daily    (night_date TEXT PRIMARY KEY, skin_c REAL, deviation REAL, source TEXT);
CREATE TABLE spo2_samples  (ts TEXT PRIMARY KEY, pct REAL, source TEXT);

CREATE TABLE sleeps (
  id INTEGER PRIMARY KEY,
  night_date TEXT UNIQUE,          -- data del risveglio
  start TEXT, stop TEXT,
  deep_min INT, light_min INT, rem_min INT, awake_min INT,
  score REAL, source TEXT
);
CREATE TABLE sleep_stages (sleep_id INT, stage TEXT, start TEXT, end TEXT);

CREATE TABLE workouts (
  id INTEGER PRIMARY KEY,
  start TEXT, stop TEXT, sport TEXT,
  avg_hr INT, max_hr INT, calories INT, distance_m REAL,
  load REAL,                        -- carico calcolato da noi (vedi sotto)
  rpe REAL, notes TEXT,             -- input manuale opzionale
  source TEXT
);

CREATE TABLE days (
  date TEXT PRIMARY KEY,
  steps INT, distance_m REAL,
  active_kcal INT, total_kcal INT,
  resting_hr INT, resting_hrv REAL,
  weight_kg REAL                    -- da bilancia, manuale
);

-- INPUT UTENTE
CREATE TABLE nutrition_log (
  ts TEXT PRIMARY KEY, meal TEXT, description TEXT,
  kcal REAL, protein_g REAL, carbs_g REAL, fat_g REAL
);
CREATE TABLE profile (key TEXT PRIMARY KEY, value TEXT);  -- età, sesso, altezza, FCmax, obiettivo...

-- DERIVATE (ricalcolate dallo scheduler)
CREATE TABLE metrics_daily (
  date TEXT PRIMARY KEY,
  readiness REAL, readiness_flags TEXT,   -- JSON: quali componenti pesano
  ctl REAL, atl REAL, tsb REAL, monotony REAL, strain REAL,
  sleep_debt_7d REAL,
  tdee REAL, target_kcal REAL, target_protein_g REAL, target_carbs_g REAL, target_fat_g REAL
);
```

## Algoritmi per pilastro

### 1. Readiness quotidiano (0–100)

Ogni componente è valutata contro la **baseline personale** (media mobile 30 giorni, z-score), mai contro medie di popolazione:

```
readiness = 0.35·HRV  + 0.20·RHR  + 0.25·Sonno  + 0.10·Temp  + 0.10·Carico
  HRV    : z-score RMSSD notturno (negativo se molto sotto baseline)
  RHR    : deviazione RHR notturno dalla baseline
  Sonno  : durata vs bisogno personale + efficienza + debito 7 giorni
  Temp   : deviazione temperatura cutanea (febbre/incombenza → penalità netta)
  Carico : TSB clampato in finestra (ottimale 0…+10)
```

Pesi configurabili e ricalibrati dopo 60+ giorni di dati (regressione: quali componenti hanno predetto le giornate soggettive/buone performance).

### 2. Rilevazione e carico di allenamento (CrossFit-first)

- **Sessioni** arrivano già rilevate da Zepp → noi le arricchiamo con **tag manuale rapido post-allenamento**: tipo sessione CrossFit (forza pura / metcon / gymnastics / skill / mista) oppure tennis, durata effettiva e RPE (1–10). Il tag arriva via notifica pochi minuti dopo la fine rilevata: tre tocchi, fatto.
- **Modello di carico ibrido per tipo di lavoro** (la FC da polso è inaffidabile sotto sforzo isometrico/forza, affidabile nei metcon e nel tennis):
  - *Metcon / tennis* → TRIMP di Banister sulla curva FC della sessione.
  - *Forza / gymnastics* → durata × RPE × fattore volume muscolare (giornate "heavy" su squat/hinge/push/pull tracciate separatamente).
  - La sessione CrossFit mista viene scomposta se l'utente indica durata forza vs metcon (default 50/50).
- **Fitness-fatigue**: `CTL = EWMA(load, 42g)` (fitness) · `ATL = EWMA(load, 7g)` (fatica) · `TSB = CTL − ATL` (forma), confrontato anche con il training load nativo di Zepp (`SPORT_LOAD`, già esportato dall'API) come sanity check.
- **Fatica muscolare locale**: contatore per pattern motori (squat / hinge / push / pull / core) con decadimento ~72 h — per il CrossFit è il segnale che il solo carico cardio non vede (DOMS, volume totale settimanale, benchmark WOD).
- **Progressi misurabili**: log dei benchmark (girl WOD, 1RM stimati da AMRAP, tennis: durata/carico) correlato a HRV/RHR dei giorni successivi → "questa settimana hai assorbito X volume in più con HRV stabile".
- **Monotonia/strain** di Foster sulla settimana: allarme precoce sovrallenamento.
- **Zone**: FC max funzionale stimata dai dati (FC più alta osservata in metcon reali) o test sul campo; zone 1–5 con correzione per RHR; per la forza non si usano zone FC.

### 3. Miglioramenti (trend & coaching)

- Trend RHR a riposo (proxy adattamento aerobico), HRV baseline mobile, peso, FC media a parità di sforzo (sessions matching).
- Regole di coaching basate su readiness + TSB (es. readiness < 60 e TSB < −20 → sessione rigenerante; readiness > 75 e TSB ≥ 0 → OK lavoro intenso).
- Report settimanale: cosa ha funzionato (sonno lungo → HRV alta il giorno dopo?), correlazioni semplici e trasparenti, niente black-box.

### 4. Nutrizione

- **TDEE adattivo** = BMR (Mifflin-St Jeor da profilo) + calorie attive della giornata (serie Zepp). Media mobile 7 giorni per stabilità.
- **Auto-calibrazione sul peso reale**: se il peso non si muove come previsto dal target, il TDEE stimato viene corretto (aggiustamento statistico tipo "metabolismo adattivo nascosto") — il sistema impara il *tuo* dispendio, non quello delle formule.
- **Target** in funzione dell'obiettivo (cut / mantenimento / bulk: ±10–20%) e del carico reale.
- **Macro**: proteine 1.8–2.2 g/kg (upper in deficit), grassi 0.8–1.0 g/kg, resto carboidrati, con **periodizzazione dei carboidrati**: giorni di metcon/WOD intenso +100–150 g, giorni di forza pura +50 g, giorni off standard.
- **Timing**: finestre pre (carb 1–3 h prima) e post (proteine + carb entro 2 h) sincronizzate con le sessioni CrossFit/tennis rilevate.
- **Log pasti**: inserimento manuale rapido (pasti ricorrenti salvati); foto+AI come estensione fase successiva, non MVP.

### 5. Sonno e sveglia intelligente — i tre livelli

**L1 — Previsionale (MVP, solo telefono, zero integrazioni).**
Dallo storico dei cicli (orari tipici di inizio sonno leggero) + regola dei multipli di ~90 min dal bedtime target, il sistema propone la finestra ottimale per *domani* e imposta 2–3 sveglie telefoniche a 10 min di distanza dentro la finestra. Migliora subito l'esperienza senza alcun canale tempo reale.

**L2 — Live (fase 3, sperimentale).**
Durante la finestra di risveglio (es. 30 min prima dell'ora massima) una piccola app Android legge la FC in tempo reale dallo strap tramite il protocollo live-HR Huami (documentato nel codice open di Gadgetbridge, che supporta già l'Helio Strap) **senza** togliere il pairing a Zepp. Trigger: FC sopra soglia (baseline notturna +Δ) tenuta per N campioni → è sonno leggero/prossimità di risveglio → parte la sveglia sul telefono (volume crescente). Rischio tecnico medio-alto: da prototipare presto ma non blocca il resto.

**L3 — Vibrazione sullo strap (opzionale).**
Due strade: (a) pilare la vibrazione dello strap via notifica (facile se si ospita Gadgetbridge, ma pairing esclusivo → perdi Zepp); (b) scrivere negli slot svegliera del dispositivo via protocollo (le 10 sveglie sono impostabili da app host). Da valutare solo dopo L2.

## Privacy e sicurezza

- Nessun dato esce dal PC; il bridge Android invia solo in LAN al backend.
- Credenziali Zepp in variabili d'ambiente / credential store, mai nel repo.
- Backup cifrato del file DB.

## Non-obiettivi (dichiarati)

- Diagnosi mediche o terapia del sonno (apnee ecc.).
- Sostituire i coach per atleti elite: il taglio è "coach personale data-driven per un utente singolo".
- GPS/tracciamento percorso: il device non lo supporta e il progetto non ne dipende.
