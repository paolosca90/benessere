#!/usr/bin/env bash
# Installazione conservativa: Benessere Google Sheets bridge su VPS esistente.
# Eseguire sulla VPS come root. Nessun token stampato a video.
set -Eeuo pipefail
SOURCE=/opt/benessere/source
PRIVATE=/opt/benessere/private
CADDYFILE=/opt/youtubecreatoros/app/Caddyfile
CADDY=youtube-creator-os-caddy
DOMAIN=bridge-benessere.45-77-66-215.nip.io
TOKENFILE="$PRIVATE/sheets_bridge_token.txt"
NOW="$(date -u +%Y%m%dT%H%M%SZ)"

die() { echo "[ERRORE] $*" >&2; exit 1; }
test "$(id -u)" = 0 || die "Esegui con sudo o come root sulla VPS."
command -v docker >/dev/null || die "Docker mancante"
command -v git >/dev/null || die "git mancante"
command -v openssl >/dev/null || die "openssl mancante"
command -v python3 >/dev/null || die "python3 mancante (backup SQLite necessario)"
command -v curl >/dev/null || die "curl mancante"
test -d "$SOURCE/.git" || die "Repository non trovato: $SOURCE"
test -f "$CADDYFILE" || die "Caddyfile non trovato: $CADDYFILE"
docker info >/dev/null || die "Docker non attivo"
docker compose version >/dev/null || die "Docker Compose mancante"
docker inspect "$CADDY" >/dev/null || die "Proxy Caddy non trovato: $CADDY"
test -d /opt/benessere/data || die "Directory dati Benessere assente"
test -f /opt/benessere/data/benessere.db || die "Database non trovato; non inizializzo una base vuota"

PROJECT_DIR="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$CADDY")"
COMPOSE_FILES="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$CADDY")"
SERVICE="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$CADDY")"
test -n "$PROJECT_DIR" && test "$PROJECT_DIR" != "<no value>" || die "Composizione Caddy non identificata"
test -n "$COMPOSE_FILES" && test "$COMPOSE_FILES" != "<no value>" || die "Compose files Caddy non identificati"
test -n "$SERVICE" && test "$SERVICE" != "<no value>" || die "Servizio Caddy non identificato"
test -d "$PROJECT_DIR" || die "Cartella compose Caddy non trovata"

# Non sovrascrivere modifiche in corso al repository in produzione.
test -z "$(git -C "$SOURCE" status --porcelain --untracked-files=no)" || die "Modifiche locali tracciate sulla VPS: niente pull automatico."
git -C "$SOURCE" fetch --quiet origin main
git -C "$SOURCE" merge --ff-only FETCH_HEAD || die "Git non fast-forward; non forzato."
test -f "$SOURCE/sheets_bridge.py" || die "Bridge non presente nel repository aggiornato"

# Backup consistente SQLite, senza fermare API/dashboard.
DB=/opt/benessere/data/benessere.db
BACKUP="/opt/benessere/data/benessere.before-sheets-$NOW.sqlite3"
python3 -c 'import sqlite3,sys; s=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); t=sqlite3.connect(sys.argv[2]); s.backup(t); t.close(); s.close()' "$DB" "$BACKUP"
chmod 600 "$BACKUP"
echo "[OK] Backup SQLite locale creato."

install -d -m 0700 "$PRIVATE"
if test ! -f "$TOKENFILE"; then
  umask 077
  openssl rand -hex 32 > "$TOKENFILE"
fi
test "$(wc -c < "$TOKENFILE")" -ge 33 || die "Token esistente troppo breve"
chown 10001:10001 "$TOKENFILE"
chmod 0600 "$TOKENFILE"

echo "[1/3] Verifico immagine Benessere esistente."
if ! docker image inspect benessere-web:20261021 >/dev/null 2>&1; then
  echo "[INFO] Immagine non presente; ricostruisco la base Benessere."
  docker build -q -t benessere-web:20261021 -f "$SOURCE/deploy/vultr/Dockerfile.web" "$SOURCE"
fi
echo "[2/3] Avvio solo il bridge (senza riavviare backend e dashboard)."
docker compose -f "$SOURCE/deploy/vultr/compose.web.yml" up -d --no-deps benessere-sheets-bridge
sleep 2
test "$(docker inspect -f '{{.State.Running}}' benessere-sheets-bridge)" = true || die "Il container bridge non è avviato."

echo "[3/3] Aggiorno il proxy senza toccare i servizi applicativi."
if grep -Fq "$DOMAIN {" "$CADDYFILE"; then
  echo "[OK] Vhost gia presente; salto modifica."
else
  CADDY_BACKUP="$CADDYFILE.before-sheets-$NOW"
  cp -p "$CADDYFILE" "$CADDY_BACKUP"
  printf '\n' >> "$CADDYFILE"
  cat "$SOURCE/deploy/vultr/sheets_bridge.Caddyfile" >> "$CADDYFILE"

  CADDY_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$CADDY")"
  if ! docker run --rm --network app_default -v "$CADDYFILE:/etc/caddy/Caddyfile:ro" --entrypoint caddy "$CADDY_IMAGE" validate --config /etc/caddy/Caddyfile; then
    cp -p "$CADDY_BACKUP" "$CADDYFILE"
    die "Caddy non valida il nuovo file: ripristinato backup, proxy NON riavviato."
  fi
  echo "[INFO] Ricreo SOLO il reverse proxy per aggiornare il bind mount del Caddyfile."
  oldifs="$IFS"
  IFS=,
  set --
  for f in $COMPOSE_FILES; do set -- "$@" -f "$f"; done
  IFS="$oldifs"
  (cd "$PROJECT_DIR" && docker compose "$@" up -d --no-deps --force-recreate "$SERVICE")
fi

# Check pubblico: non inviare mai token o dati sanitari.
status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 -X POST "https://$DOMAIN/bridge/v1/import" || true)"
if test "$status" != 401; then
  echo "[ATTENZIONE] POST anonimo su bridge restituisce HTTP $status (atteso 401). Controllare TLS/DNS e proxy."
else
  echo "[OK] HTTPS e protezione Bearer attivi: richiesta non autorizzata bloccata (401)."
fi

echo ""
echo "Installazione infrastruttura terminata. Non copiare token nella chat."
echo "1. Apri nel tuo browser Google Sheets > Estensioni > Apps Script."
echo "2. Codice da: https://github.com/paolosca90/benessere/blob/main/deploy/vultr/BenessereSheets.gs"
echo "3. Script Properties: BENESSERE_BRIDGE_URL=https://$DOMAIN/bridge/v1/import"
echo "4. Script Properties: BENESSERE_BRIDGE_TOKEN=contenuto di $TOKENFILE"
echo "   Leggilo SOLO nella tua sessione SSH, e incollalo direttamente in Google."
echo "5. Salva, avvia installaTrigger una volta, autorizza e verifica Coda!G2=SAVED."
