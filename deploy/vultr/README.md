# Benessere — VPS Vultr (installazione 21/10/2026)

Questo documento registra il deployment sulla VPS esistente. Il backend Android e, dopo l'installazione dello stack web, la dashboard Streamlit e il server MCP condividono lo stesso database persistente. La dashboard usa HTTP Basic Auth su HTTPS; MCP usa un Bearer separato. La connessione nativa da ChatGPT è subordinata ai permessi del prodotto e al metodo di autenticazione supportato.

## Stato operativo

- VPS Ubuntu 24.04, IP pubblico `45.77.66.215`.
- Endpoint Android HTTPS: `https://benessere.45-77-66-215.nip.io` (senza percorso o porta nell'app).
- API backend Docker: container `benessere-api`, immagine `python:3.12-slim`, rete `app_default`; nessuna porta pubblicata sull'host.
- Repository sulla VPS: `/opt/benessere/source`, dati persistenti **privati** in `/opt/benessere/data`.
- Reverse proxy TLS: container preesistente `youtube-creator-os-caddy`, file host `/opt/youtubecreatoros/app/Caddyfile`; un sito Benessere aggiunto in coda al file; snippet di riferimento in `deploy/vultr/benessere.Caddyfile`.
- Backup del Caddyfile precedente: `/opt/youtubecreatoros/app/Caddyfile.backup-before-benessere`.
- YouTubeCreatorOS continua a usare la propria configurazione e i propri container. Non cancellare i suoi dati.

## Dashboard e MCP

- Dashboard su `https://dashboard-benessere.45-77-66-215.nip.io`, utente `benessere`.
- Password dashboard salvata **solo sulla VPS**, recuperabile con:
  `ssh root@45.77.66.215 'cat /opt/benessere/private/dashboard_password.txt'`.
- MCP remoto su `https://mcp-benessere.45-77-66-215.nip.io/mcp`.
- Token MCP separato, recuperabile solo sulla VPS:
  `ssh root@45.77.66.215 'cat /opt/benessere/private/mcp_token.txt'`.
- **Non** incollare credenziali o foto sanitarie nella configurazione pubblica del sito o nel repo. Il server MCP richiede `Authorization: Bearer <token>` su ogni richiesta.
- Dockerfile e Compose dello stack web sono in questa cartella. Lo stack è separato da CreatorOS e non espone porte host.
- Lo stream HTTP MCP è disponibile per client compatibili. L'integrazione in ChatGPT richiede un'app/plugin autorizzato e autenticazione supportata; **non** è automaticamente collegata dall'esistenza dell'URL.

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
- Monitorare l'impatto di Streamlit sulla VPS (~1 GB RAM): valutare upgrade a 2 GB se compaiono OOM/restart o rallentamenti.
- Sostituire il sottodominio `nip.io` con un dominio proprio quando disponibile.
