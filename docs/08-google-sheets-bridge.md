# Ponte Google Sheets -> Benessere: allenamenti e pasti

Stato: codice locale preparato e test unitari iniziali OK. La sincronizzazione NON è attiva finché non sono completati deployment VPS, trigger Apps Script e verifica end-to-end.

## Flusso
ChatGPT scrive una riga nel Google Sheet privato tramite Google Drive. Uno script Google Apps Script ogni 5 minuti invia le righe PENDING via HTTPS autenticato al bridge VPS. Il bridge scrive in SQLite l'allenamento e l'eventuale risultato WOD, oppure il pasto. La chiave evento protegge dai duplicati. Il foglio passa a SAVED dopo risposta positiva; gli errori di validazione diventano ERROR.

## Installazione assistita (un solo comando SSH)
Dopo che lo script e stato pubblicato nel repository, sulla VPS come root eseguire:

    cd /opt/benessere/source && git fetch origin main && git merge --ff-only origin/main && bash deploy/vultr/install_sheets_bridge.sh

Prima di eseguire: questo comando aggiorna il repository locale e lo script crea un backup consistente di SQLite, riutilizza l'immagine Benessere esistente e avvia solo il bridge e aggiunge un virtual host Caddy. Se serve attivare il nuovo host, ricrea il SOLO container reverse proxy (breve interruzione delle connessioni web preesistenti); non modifica i container applicativi CreatorOS. Se Git ha modifiche locali, il preflight si interrompe senza forzare. Non inoltrare mai il token letto sulla VPS in questa chat.

## Installazione manuale / riferimento
1. Eseguire backup di DB e Caddyfile esistenti sulla VPS. Non modificare gli altri container.
2. Se non esiste l'immagine Docker benessere-web:20261021, ricostruirla in /opt/benessere/source: docker build -t benessere-web:20261021 -f deploy/vultr/Dockerfile.web .
3. Creare un token casuale di almeno 32 caratteri in /opt/benessere/private/sheets_bridge_token.txt; non inserirlo mai nel codice, in celle del foglio, in chat o nel repo pubblico. Assicurarsi che UID 10001 nel container possa leggerlo, con permessi restrittivi.
4. Avviare soltanto il servizio: docker compose -f deploy/vultr/compose.web.yml up -d --no-deps benessere-sheets-bridge
5. Aggiungere il contenuto di deploy/vultr/sheets_bridge.Caddyfile al Caddyfile già in uso (/opt/youtubecreatoros/app/Caddyfile) SENZA sovrascrivere gli host esistenti. Validare e applicare il file effettivamente montato dal container Caddy.
6. Aprire il Google Sheet privato, Estensioni > Apps Script e incollare deploy/vultr/BenessereSheets.gs. In Impostazioni progetto > Proprietà script impostare BENESSERE_BRIDGE_URL a https://bridge-benessere.45-77-66-215.nip.io/bridge/v1/import e BENESSERE_BRIDGE_TOKEN al token privato. Non pubblicare come Web App.
7. Eseguire manualmente installaTrigger() una volta nell'editor, autorizzare Apps Script, poi eseguire syncBenessere() per verificare la riga di prova.
8. Solo se stato della riga diventa SAVED e app mostra i dati considerare attiva l'integrazione.

## Struttura del foglio Coda
ID | TIPO | DATA | ORA | DESCRIZIONE | JSON | STATO | AGGIORNATO | ESITO | ORIGINE.
TIPO: workout oppure meal. STATO: PENDING, SAVED, ERROR. Ogni ID deve essere stabile e univoco per evento.

Allenamento (esempio sintetico):
{"date":"2026-10-21","type":"other","duration_min":60,"notes":"Sessione mista","wod":{"name":"WOD personalizzato","score_type":"time","description":"Movimenti e ripetizioni","score":"17:00","scaling":"unspecified","notes":"Carichi effettivi"}}

Pasto (esempio fittizio, non registrare finché non dichiarato mangiato):
{"date":"2026-10-21","time":"13:15","meal":"lunch","description":"Porzioni stimate","kcal":510,"protein_g":32,"carbs_g":48,"fat_g":18}

Per pasti da foto i macronutrienti sono stime, chiedere i pesi se poco chiari. Non inventare valori. Un pasto già presente allo stesso minuto non viene sovrascritto.

## Test
python -m unittest discover -s tests -p test_sheets_bridge.py -v

## Sicurezza e vincoli
Google Sheet privato, Script Properties private, Bearer separato per bridge, HTTPS obbligatorio. Mai condividere il foglio tramite link pubblico. Il deployment deve preservare gli altri servizi e richiede autorizzazione dell'account Google per trigger Apps Script.