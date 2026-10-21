#!/usr/bin/env bash
# Aggiornamento sicuro Benessere UI + MCP + Sheets Bridge.
# Eseguire da SSH come root. NON visualizza né modifica i token privati.
set -Eeuo pipefail
SOURCE=/opt/benessere/source
DB=/opt/benessere/data/benessere.db
COMPOSE="$SOURCE/deploy/vultr/compose.web.yml"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
die() { echo "[ERRORE] $*" >&2; exit 1; }
test "$(id -u)" -eq 0 || die "Eseguire come root sulla VPS"
command -v docker >/dev/null || die "Docker non installato"
command -v git >/dev/null || die "Git non installato"
command -v python3 >/dev/null || die "Python3 non installato"
test -d "$SOURCE/.git" || die "Repository non trovato in $SOURCE"
test -f "$DB" || die "Database assente: non avvio nuovi database vuoti"
test -f "$COMPOSE" || die "File compose mancante"
test -f /opt/benessere/private/mcp_token.txt || die "Token MCP mancante"
test -f /opt/benessere/private/sheets_bridge_token.txt || die "Token Sheets mancante"
docker image inspect benessere-web:20261021 >/dev/null || die "Immagine Benessere esistente non trovata"
test -z "$(git -C "$SOURCE" status --porcelain --untracked-files=no)" || die "Modifiche locali tracciate: fermo l'aggiornamento"
git -C "$SOURCE" fetch --quiet origin main
git -C "$SOURCE" merge --ff-only FETCH_HEAD || die "Git non fast-forward, nessuna modifica forzata"
test -f "$SOURCE/benessere/maxes.py" || die "Nuova versione non presente"
test -f "$SOURCE/benessere/housekeeping.py" || die "Pulizia sicura non presente"
docker compose -f "$COMPOSE" config --quiet || die "Compose non valida"

# Backup coerente del DB prima di avviare il nuovo codice.
BACKUP="/opt/benessere/data/benessere.pre-ui-v03-$STAMP.sqlite3"
python3 -c 'import sqlite3,sys; src=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()' "$DB" "$BACKUP"
chmod 0600 "$BACKUP"
echo "[OK] Backup consistente creato su VPS."

# Nuova UI come volumi read-only: niente build, niente modifica a CreatorOS.
docker compose -f "$COMPOSE" up -d --no-deps --force-recreate \
    benessere-dashboard benessere-mcp benessere-sheets-bridge
for name in benessere-dashboard benessere-mcp benessere-sheets-bridge; do
  test "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" = "true" || \
      die "Container non in esecuzione: $name. Controlla docker logs --tail 40 $name."
  echo "[OK] $name in esecuzione"
done

# Streamlit può impiegare decine di secondi a inizializzare SQLite e il primo avvio.
# Non dichiarare errore al primo ConnectionRefused: attendere fino a 90 secondi.
ready=0
for attempt in {1..45}; do
  if docker exec benessere-dashboard python -c 'import urllib.request; v=urllib.request.urlopen("http://127.0.0.1:8501/_stcore/health",timeout=3); assert v.status==200' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if test "$ready" -ne 1; then
  echo "[ERRORE] Dashboard non pronta dopo 90 secondi: diagnosi di avvio."
  docker inspect --format 'Status={{.State.Status}} OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}' benessere-dashboard || true
  docker logs --tail 35 benessere-dashboard || true
  die "Dashboard non sana. Non modificare il DB: backup pre-aggiornamento già presente."
fi
echo "[OK] Health endpoint dashboard HTTP 200"

# Endpoints pubblici protetti (non inviare token).
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 -X POST https://bridge-benessere.45-77-66-215.nip.io/bridge/v1/import || true)"
test "$code" = "401" || echo "[ATTENZIONE] HTTPS bridge ha restituito HTTP $code, atteso 401 a richiesta anonima."
echo ""
echo "[OK] Aggiornamento Benessere v0.3 completato."
echo "Dashboard: https://dashboard-benessere.45-77-66-215.nip.io"
echo "Backup privato: $BACKUP"
echo "Non è stato modificato il reverse proxy CreatorOS."
