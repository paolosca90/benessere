# Benessere 2.0 — anteprima Next.js + FastAPI

**Stato:** codice di sviluppo; non sostituisce Streamlit in produzione.
La PWA è mobile-first, mostra solo dati reali di SQLite e non conserva
dati di salute in cache offline. La modalità sveglia attualmente disponibile
è **allarme fisso sul telefono**, non smart wake-up basato sulle fasi di sonno.

## Backend FastAPI

```sh
pip install -r webapp/api/requirements.txt
# Generare token privato di almeno 32 caratteri, MAI includerlo nel repo
export BENESSERE_WEB_API_TOKEN=... 
uvicorn webapp.api.main:app --host 127.0.0.1 --port 8780
```

Ogni endpoint `/v1/*` rifiuta richieste senza Bearer. L'endpoint pubblico
`/health` segnala soltanto che il processo è raggiungibile.

## Frontend Next.js

```sh
cd webapp/frontend
npm ci
# Configura .env.local LOCALMENTE copiando i nomi da .env.example
npm run build
npm start
```

Impostare `BENESSERE_API_INTERNAL_URL=http://127.0.0.1:8780` e
`BENESSERE_WEB_API_TOKEN` soltanto **nel processo Next.js**. Non usare
variabili `NEXT_PUBLIC_` per token.

In un deployment web pubblico, la PWA deve essere ulteriormente protetta
da autenticazione a livello reverse proxy (Basic Auth già usata dal progetto
oppure una soluzione più robusta). I route handler sono un proxy server-to-server
autenticato; **non costituiscono di per sé un login utente**.

## Preview VPS — NON AVVIARE SENZA CHECKLIST

Il file `webapp/compose.preview.yml` propone una preview completamente
separata, raggiungibile solo da `127.0.0.1:3001` sulla VPS. Non crea
nuovi domini, non cambia Caddy e non sostituisce i container attuali.

Preparare `/opt/benessere/preview-data/benessere.db` come copia coerente, effettuata con la SQLite backup API. La preview usa ESCLUSIVAMENTE questo percorso separato e non deve accedere al database di produzione.\n\nPreparare su VPS `/opt/benessere/private/webapp.preview.env` contenente
`BENESSERE_WEB_API_TOKEN` generato in modo casuale e tenuto privato.
Usare un tunnel SSH per il browser: `ssh -L 3001:127.0.0.1:3001 <vps>`.
NON pubblicare la porta 3001 su Internet.

Prima di avviare la preview:
1. Confrontare HEAD locale e remoto senza sovrascrivere modifiche di ZCode.
2. Backup SQLite coerente e ripristino di prova.
3. Verificare spazio disco e risorse VPS.
4. Verificare che i servizi esistenti restino isolati.
5. Autorizzare la preview; nessun rollout autonomo in produzione.

## Sveglia: funzionamento effettivo

- La pagina `Sveglia` su Streamlit e nella PWA aggiorna `alarm_config`.
- La configurazione è disattivata inizialmente e ha revisioni idempotenti.
- Android usa `GET /api/v1/alarm-config` con il token Android esistente.
- Solo la pressione esplicita di `Applica sveglia dalla web app` applica
  la configurazione nel sistema Android e invia `POST /api/v1/alarm-ack`.
- La web app mostra `pending_phone`, `confirmed` o `failed`.
- Un allarme ricorrente locale è riprogrammato dopo lo scatto e dopo il riavvio.
- L'assenza di Internet non deve interrompere una programmazione già installata.
- L'allarme Android è implementato mediante `AlarmManager.setAlarmClock`
  e una notifica ad alta priorità; **non è equivalente a una sveglia di sistema
  completamente collaudata**. Testare permessi, suono, DND e riavvio sul telefono.
- Le fasi del sonno in Health Connect sono informazioni principalmente
  retrospettive; non garantiscono uno streaming notturno in tempo reale.
- Helio Strap vibra tramite sveglie impostate in Zepp; nessun comando BLE
  proprietario è ancora implementato o dichiarato funzionante in Benessere.
- Continuare a utilizzare Zepp o la sveglia di sistema come riserva affidabile.

## Acceptance prima di abilitare il risveglio notturno

- APK Android compilato, installato e testato su dispositivo reale.
- Conferma revisione Android `confirmed` e backend correttamente aggiornato.
- Allarme in background e a schermo spento.
- Reboot, Doze, notifiche negate, DST, cambio ora e offline.
- Controllo che la vibrazione sullo Strap sia effettivamente attivabile
  soltanto dopo ricerca e verifica dei comandi BLE su un dispositivo reale.

## API e privacy

Tutte le chiamate Next → FastAPI passano dal server e non espongono il token
al browser. Service worker salva esclusivamente una pagina statica di errore
offline, mai misure, pasti o record di salute.
