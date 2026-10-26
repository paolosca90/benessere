# Passaggio da Streamlit a Benessere 2.0 — guida operativa

Questa operazione mantiene **lo stesso sito HTTPS** e **lo stesso database**.
Il container Streamlit viene solo rinominato e spento, non eliminato.
Restano attivi: API Android Health Connect, MCP ChatGPT, bridge Google Sheets e Caddy.

## Prima: cosa include la PWA

- Oggi, Salute e grafici interattivi, Progressi e Sveglia.
- Diario: pasti, allenamenti, blocchi, WOD, risultati, massimali, foto, profilo.
- I dati vengono letti da `/opt/benessere/data/benessere.db` e `/opt/benessere/data/photos`.
- Non è ancora implementata l'intera esperienza avanzata di Streamlit
  (ad esempio confronti fotografici automatici e tutti gli strumenti benchmark).
- La sveglia sul telefono necessita APK 0.2.2 e collaudo reale;
  Helio Strap continua ad essere configurabile tramite Zepp.

## Download delle immagini corrette

Nella [PR #1](https://github.com/paolosca90/benessere/pull/1),
aprire l'ultimo workflow GitHub Actions VERDE.
Scaricare l'artifact `benessere-preview-images` dal run più recente.
Estrarre lo ZIP e copiare il file `benessere-preview-images.tar.gz`.

**Non usare il vecchio archivio del 22 ottobre prima delle modifiche**:
lo script verifica la revisione Git delle immagini e lo rifiuta.

Da Mac:

```sh
cd ~/benessere-v2
git checkout feature/benessere-v2-pwa-sveglia
git pull --ff-only
FILE=$(find "$HOME/Downloads" "$HOME/Desktop" -type f -name benessere-preview-images.tar.gz -print -quit)
test -n "$FILE" || { echo "Artifact non trovato"; exit 1; }
scp "$FILE" root@45.77.66.215:/tmp/benessere-preview-images.tar.gz
```

## Esecuzione switch con backup automatico

**Comando sul Terminale del Mac**, non all'interno della sessione SSH.
Leggere il messaggio di backup e l'esito:

```sh
ssh root@45.77.66.215 'bash -se' < ~/benessere-v2/deploy/vultr/migrate_to_pwa_v2.sh
```

Lo script:
1. Verifica lo stato del container originale, le risorse, il branch e le immagini.
2. Carica immagini Docker prodotte da CI (non compila sulla VPS).
3. Esegue un backup SQLite consistente e un archivio dei file/foto con permessi 0600.
4. Ferma e rinomina solo il container `benessere-dashboard` di Streamlit.
5. Avvia `benessere-api-v2` e il nuovo `benessere-dashboard` nel network già usato da Caddy.
6. Testa API e Next.js. Su errore, ripristina automaticamente il vecchio container.
7. Conserva il nome del container legacy e il percorso di backup per il rollback.

Non usare `docker compose down` sui servizi Benessere originali o su CreatorOS:
non serve e potrebbe fermare Android/MCP/Sheets.

## Verifiche utente dopo lo switch

Aprire `https://dashboard-benessere.45-77-66-215.nip.io`.
Usare le credenziali **già esistenti** della dashboard (Caddy Basic Auth).
Confrontare record del Diario e tabelle con quanto mostrava Streamlit.
Controllare che la sincronizzazione Android e ChatGPT continui a funzionare.
Registrare **una sola operazione di prova reale** (oppure su copia test)
e verificare che app e plugin vedano la stessa modifica.

Lo switch web NON aggiorna automaticamente l'app Android installata.
Le impostazioni della sveglia sono funzioni sperimentali:
non usarle come sveglia unica.

## Rollback SENZA perdere i nuovi dati

Da Mac:

```sh
cd ~/benessere-v2
ssh root@45.77.66.215 'bash -se' < deploy/vultr/rollback_to_streamlit.sh
```

Il rollback ripristina l'interfaccia Streamlit, ma **non sostituisce il database**
con il vecchio backup. Questo evita di cancellare pasti, WOD, foto e misure
che sarebbero entrati nel database durante l'uso della nuova PWA.

La copia SQLite consistente e le foto pre-switch rimangono custodite
in `/opt/benessere/backups/pre-pwa-<timestamp>` per emergenze.
