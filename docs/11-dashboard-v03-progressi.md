# Benessere v0.3 — installazione e utilizzo

Questa versione aggiunge UI responsive, sezioni separare **Benchmark** e **Massimali/Complex**, profilo senza valori inventati e archivio privato **Foto progressi**.

## Pubblicazione VPS (una volta, SSH root)

Eseguire sulla VPS in una sessione SSH autorizzata:

```bash
cd /opt/benessere/source && git fetch origin main && git merge --ff-only origin/main && bash deploy/vultr/upgrade_dashboard_v03.sh
```

Lo script verifica Docker, token esistenti e configurazione Compose. Prima di modificare il database crea un backup SQLite coerente. Ricrea solo i container Benessere (dashboard, MCP e bridge); non modifica Caddy o altri progetti. Non visualizzare o copiare token in chat. Se appare un errore, fermarsi e fornire soltanto le righe senza segreti.

Dashboard protetta: https://dashboard-benessere.45-77-66-215.nip.io

## Sincronizzazione ChatGPT

La coda Google Sheets privata è il canale di inserimento. Nuovi tipi:
- `max`: `{"date":"2026-08","lift":"Power Clean","weight_kg":100,"reps":1,"category":"lift"}`. Date `YYYY-MM` senza un giorno inventato, oppure `YYYY-MM-DD`. `category="complex"` per sequenze, non contate come 1RM.
- `profile`: `{"height_cm":180,"weight_kg":81,"body_fat_pct_estimate":6}`. Percentuale dichiarata/stimata, non misurazione.
- `meal` e `workout` continuano come prima.

**Aggiornare Apps Script** in Google Sheets, editor `Codice.gs`: nella riga di validazione cambiare soltanto il controllo dei tipi da `['meal','workout'].includes(kind)` a `['meal','workout','max','profile'].includes(kind)` (se la versione attuale accetta già max, aggiungere soltanto profile). Alternativa: sostituire tutto con `deploy/vultr/BenessereSheets.gs` dopo avere salvato una copia. Le Script Properties `BENESSERE_BRIDGE_URL` e `BENESSERE_BRIDGE_TOKEN` non si modificano. `installaTrigger()` conserva la frequenza a cinque minuti.

Le righe di massimali/profilo preesistenti su Sheets restano `HOLD` finché non è confermato il deployment. **Non impostare PENDING prima di avere aggiornato la VPS e Apps Script.** Quando le condizioni sono rispettate si impostano su `PENDING` una sola volta; il bridge usa ID idempotenti.

## Foto progressi

Aprire la sezione `Foto progressi` da smartphone o PC:
1. Data della foto (giorno effettivo), inquadratura frontale, laterale o posteriore; upload JPG/PNG/WebP massimo 10 MB.
2. Confermare il salvataggio; il server converte in JPEG, rimuove EXIF e GPS e ridimensiona il lato maggiore a 2048px.
3. Caricare almeno due foto con la stessa inquadratura e selezionarle nella sezione confronto affiancato.
4. Usare il tasto di eliminazione (con doppia conferma) se si vuole rimuovere una foto.

Le foto sono **private** e salvate fisicamente in `/opt/benessere/data/photos`, non nella repository pubblica. Il database conserva soltanto percorso relativo, data, inquadratura e note; niente link fotografici pubblici. Backup di SQLite da solo **non** include i file JPG: fare un backup cifrato anche della cartella `photos`. La dashboard è protetta da HTTP Basic Auth via HTTPS.

Le foto archiviate sulla VPS **non sono automaticamente leggibili da ChatGPT** tramite Google Sheets: per chiedere analisi comparativa in chat bisogna caricare le due immagini nella conversazione oppure aggiungere in futuro un canale foto con autenticazione dedicata, mai un link pubblico.

## Integrità dati

I benchmark sono un catalogo statico con descrizioni, non risultati utente. La migrazione pulisce esclusivamente definizioni seed non accompagnate da risultati e alcuni carichi sintetici riconoscibili, dopo aver creato backup SQLite. Non elimina pasti o allenamenti reali. Nessun massimale predefinito, nessun valore anagrafico fittizio, nessuna data giornaliera inventata.

## Test

`python -m pytest tests -q`. Tutti i test usano database temporanei.
