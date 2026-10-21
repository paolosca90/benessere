# Benessere — coach personale del crossfitter

Sistema **local-first** che trasforma i dati dell'Amazfit Helio Strap (e il tuo log manuale) in allenamento, nutrizione e recupero ottimizzati per il CrossFit (più tennis). Tre pezzi:

1. **Web app locale** (Streamlit) — le quattro aree: Oggi, Allenamenti, WOD, Alimentazione
2. **Server MCP** — collega i tuoi dati a **ChatGPT/Claude**, in lettura *e scrittura*
3. **App Android** (`app-android/`) — collegamento al device: Health Connect, BLE Huami, sveglia intelligente

## Avvio rapido

```bash
pip install -r requirements.txt

# 1. l'app
streamlit run app.py            # → http://localhost:8501

# 2. il collegamento a ChatGPT (in un altro terminale)
python mcp_server.py --http 8000
#    ChatGPT: Impostazioni → Connectors → Developer mode → Create → http://localhost:8000/mcp
#    Guida completa e prompt d'esempio: docs/07-mcp-chatgpt.md

# 3. i test
python -m pytest tests/ -q
```

## Le quattro aree

| Area | Cosa c'è |
|---|---|
| 🏠 **Oggi** | readiness (quando ci sono i dati Zepp), target kcal/macro del giorno con periodizzazione carboidrati, pasti registrati, **reminder pasti mancanti**, registrazione rapida |
| 🏋️ **Allenamenti** | log sessioni (forza/metcon/gymnastics/skill/tennis) con **carico ibrido** (TRIMP sulla FC per il cardio, durata×RPE per la forza), grafici **Fitness/Fatica/Forma** (CTL/ATL/TSB), volume per tipo |
| 🔥 **WOD** | catalogo con 18 benchmark (Girls, Hero, massimali, engine) + WOD custom; risultati con punteggi normalizzati (tempo, round+reps, kg, reps); **PR automatici per scaling** |
| 🍽️ **Alimentazione** | TDEE adattivo (BMR + attività reale), macro per obiettivo (cut/maintain/bulk), log pasti, **reminder se un pasto non è registrato entro la finestra** (10:00 / 14:00 / 21:30) |

## Collegamento al device (Helio Strap)

Tre canali, il sistema funziona fin da subito col log manuale e si arricchisce a ogni canale attivo:

1. **Cloud Zepp** (storico completo: FC 1 s, HRV, sonno, temperatura) — serve il token una tantum: `docs/04-report-dati.md`. Poi `sync` dall'app o dal tool MCP `sync_zepp`.
2. **Health Connect** (near real-time) — via app Android in `app-android/`.
3. **BLE diretto** (fase 3: sveglia intelligente) — protocollo confermato dall'analisi APK in `docs/06-rea-analisi.md`.

## Il codice

- [`app-android/`](app-android/README.md) — **la nostra app** (Kotlin + Compose): lettura Health Connect, client BLE Huami, sveglia intelligente L1 — APK precompilato in [`dist/`](dist/benessere-v0.1.0-debug.apk)
- [`app.py`](app.py) — la web app Streamlit (Oggi / Allenamenti / WOD / Alimentazione / Impostazioni)
- [`mcp_server.py`](mcp_server.py) — server MCP (15 tool) per ChatGPT/Claude, con flusso foto
- [`benessere/`](benessere/) — core Python: nutrizione, carico allenamento, WOD/PR, readiness, reminder, ingest Zepp
- [`tests/`](tests/) — pytest (14 test) + smoke test MCP

### Cartella `vendor/` (non nel repo)

La toolchain di reverse engineering (JDK, apktool, jadx, SDK Android, APK decompilato ~2 GB) non è versionata. Se serve:

```bash
git clone --depth 1 https://github.com/m4ary/zepp-health-cli vendor/zepp-health-cli   # canale cloud Zepp
git clone --depth 1 https://github.com/morluto/rea vendor/rea                          # toolkit reverse engineering
# JDK/apktool/jadx/SDK Android: comandi completi in docs/06-rea-analisi.md
```

## Documentazione

- [01 Dispositivo e dati](docs/01-dispositivo-dati.md) · [02 Architettura](docs/02-architettura.md) · [03 Roadmap](docs/03-roadmap.md)
- [04 Token Zepp](docs/04-report-dati.md) · [05 Tempo reale](docs/05-tempo-reale-app.md)
- [06 Reverse engineering APK](docs/06-rea-analisi.md) · [07 MCP/ChatGPT con flusso foto](docs/07-mcp-chatgpt.md)
- [08 Collegare l'app all'Amazfit](docs/08-collegare-amazfit.md)

## Principi

1. **Local-first**: SQLite in `data/benessere.db`, nessun cloud di terze parti.
2. **Calibrato su di me**: baseline personali (HRV, RHR, TDEE corretto sul peso reale), mai medie di popolazione.
3. **CrossFit-first**: carico e recupero pensati per forza + metcon + gymnastics, tennis come secondo sport.
4. **Onestà sui limiti**: i sensori stimano; i consigli sono informativi, non medici.
