# Benessere — VPS Vultr (installazione 21/10/2026)

Questo documento registra il deployment del **solo backend Android** sulla VPS esistente. La dashboard Streamlit **non** è stata pubblicata: prima servono autenticazione dedicata, dimensionamento della RAM e migrazione controllata dei dati Mac.

## Stato operativo

- VPS Ubuntu 24.04, IP pubblico `45.77.66.215`.
- Endpoint Android HTTPS: `https://benessere.45-77-66-215.nip.io` (senza percorso o porta nell'app).
- API backend Docker: container `benessere-api`, immagine `python:3.12-slim`, rete `app_default`; nessuna porta pubblicata sull'host.
- Repository sulla VPS: `/opt/benessere/source`, dati persistenti **privati** in `/opt/benessere/data`.
- Reverse proxy TLS: container preesistente `youtube-creator-os-caddy`, file host `/opt/youtubecreatoros/app/Caddyfile`; un sito Benessere aggiunto in coda al file; snippet di riferimento in `deploy/vultr/benessere.Caddyfile`.
- Backup del Caddyfile precedente: `/opt/youtubecreatoros/app/Caddyfile.backup-before-benessere`.
- YouTubeCreatorOS continua a usare la propria configurazione e i propri container. Non cancellare i suoi dati.

## Telefono Android

1. Imposta URL `https://benessere.45-77-66-215.nip.io`.
2. Recupera il token **senza incollarlo in chat** sul tuo PC autorizzato: `ssh root@45.77.66.215 'cat /opt/benessere/data/android_sync_token.txt'`.
3. Inserisci il token nell'app Benessere; deseleziona «Consento HTTP non cifrato» (si usa HTTPS).
4. Premi **Salva → Sincronizza ora** e, se desiderato, abilita la sincronizzazione automatica. La periodicità dipende dai permessi Android/Health Connect.

La VPS inizia con un database vuoto. I dati già sincronizzati nel database del Mac non sono stati trasferiti automaticamente.

## Verifiche e manutenzione

```bash
# Stato API e reverse proxy
docker ps --filter name=benessere-api
docker ps --filter name=youtube-creator-os-caddy
docker stats --no-stream benessere-api

# Salute HTTPS (da un altro computer)
curl --fail https://benessere.45-77-66-215.nip.io/health

# Verifica integrità configurazione del reverse proxy
docker exec youtube-creator-os-caddy caddy validate --config /etc/caddy/Caddyfile

# Token root-only, MAI includerlo nel repo o nei log di supporto
ls -l /opt/benessere/data/android_sync_token.txt
```

La chiave Bearer risiede esclusivamente in `/opt/benessere/data/android_sync_token.txt` (permessi `0600`); il database sanitario e i file journal SQLite nello stesso percorso non sono versionati. Il backend parte automaticamente al riavvio grazie a `--restart unless-stopped`.

Il container è limitato a `128 MB RAM`, `0,5 CPU`, UID non privilegiato `10001`, root filesystem read-only, nessuna capability, `no-new-privileges`; persiste soltanto `/app/data`. La porta 8766 è raggiungibile **solo** dalla rete Docker condivisa con Caddy, non dall'esterno.

Attenzione: la configurazione del Caddyfile preesistente era montata su un vecchio inode. Dopo aver aggiornato il file host è stata effettuata una ricreazione **del solo container Caddy** tramite Compose, per rendere persistente il nuovo host virtuale; tutti gli altri container YouTubeCreatorOS sono rimasti attivi. Quando aggiorni ancora quel Caddyfile, valida la copia che il container legge veramente prima del reload.

## Da completare

- Verificare il primo invio reale da Android a questa VPS.
- Organizzare backup SQLite cifrati e ripristino verificato; non effettuare backup su repository pubblico.
- Migrare, se richiesto, lo storico Mac usando copia consistente SQLite (backup API), TLS/SSH e senza sovrascrivere nuove sincronizzazioni.
- Pubblicare eventualmente la dashboard dietro autenticazione dedicata; la VPS dispone di ~1 GB RAM e dovrebbe essere dimensionata prima di aggiungere Streamlit.
- Sostituire il sottodominio `nip.io` con un dominio proprio quando disponibile.
