#!/usr/bin/env bash
# Benessere: switch controllato dalla dashboard Streamlit alla PWA Next.js.
# Da lanciare come root via SSH; nessun dato di produzione viene sovrascritto.
set -Eeuo pipefail
umask 077

ROOT=/opt/benessere
SOURCE="$ROOT/source"
STAGING="$ROOT/preview-source"
DATA="$ROOT/data"
PRIVATE="$ROOT/private"
ARCHIVE=/tmp/benessere-preview-images.tar.gz
BRANCH=feature/benessere-v2-pwa-sveglia
COMPOSE="$STAGING/webapp/compose.production.yml"
PROJECT=benessere-v2
LEGACY="benessere-dashboard-legacy-$(date -u +%Y%m%dT%H%M%SZ)"

die() { echo "ERRORE: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "Esegui come root."
command -v docker >/dev/null || die "Docker non disponibile."
command -v python3 >/dev/null || die "Python3 non disponibile."
test -f "$SOURCE/.git/HEAD" || test -f "$SOURCE/.git" || die "Repository originale assente."
test -s "$DATA/benessere.db" || die "Database originale assente."
test -s "$ARCHIVE" || die "Archivio delle immagini Docker assente: scarica quello dell'ULTIMO run CI."
test -d "$PRIVATE" || die "Directory segreti assente."
docker network inspect app_default >/dev/null || die "Rete originale di Caddy assente."

disk_kb=$(df -Pk / | awk 'NR==2{print $4}')
[ "$disk_kb" -gt 900000 ] || die "Spazio insufficiente prima del deploy."
avail_mb=$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)
[ "$avail_mb" -ge 150 ] || die "RAM disponibile inferiore a 150 MB: aggiorna la VPS prima del deploy."

docker inspect benessere-dashboard >/dev/null 2>&1 || die "Dashboard originale non trovata."
original_image=$(docker inspect --format '{{.Config.Image}}' benessere-dashboard)
case "$original_image" in
  benessere-web:*) ;;
  *) die "La dashboard non usa l'immagine Streamlit prevista ($original_image). Arresto per evitare modifiche errate." ;;
esac
if docker inspect benessere-api-v2 >/dev/null 2>&1; then
  die "Il nuovo servizio API esiste già: non sovrascrivere una migrazione precedente."
fi

echo "[1/7] Allineamento git del worktree di staging"
git -C "$SOURCE" fetch --no-tags origin \
  "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
expected=$(git -C "$SOURCE" rev-parse "refs/remotes/origin/$BRANCH")
if [ -e "$STAGING/.git" ]; then
  [ -z "$(git -C "$STAGING" status --porcelain)" ] ||
    die "Il worktree staging ha modifiche locali: non sovrascriverle."
  git -C "$STAGING" checkout --detach "$expected"
else
  git -C "$SOURCE" worktree add --detach "$STAGING" "$expected"
fi
test -s "$COMPOSE" || die "Compose di produzione assente nel worktree."

echo "[2/7] Caricamento e verifica della versione delle immagini"
gzip -t "$ARCHIVE" || die "Archivio corrotto."
docker load -i "$ARCHIVE" >/dev/null
for image in benessere-api-v2:preview benessere-pwa-preview:preview; do
  docker image inspect "$image" >/dev/null || die "Immagine mancante: $image"
  revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
  [ "$revision" = "$expected" ] ||
    die "Immagine $image non aggiornata: revision=$revision, attesa=$expected. Scarica l'artifact dell'ultimo run."
done

echo "[3/7] Token server-to-server e configurazione"
ENV_FILE="$PRIVATE/webapp.preview.env"
if [ ! -s "$ENV_FILE" ]; then
  printf 'BENESSERE_WEB_API_TOKEN=%s\n' "$(openssl rand -hex 32)" > "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"
docker compose -p "$PROJECT" -f "$COMPOSE" config --quiet

echo "[4/7] Backup completo e controllato"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="$ROOT/backups/pre-pwa-$STAMP"
install -d -m 700 "$BACKUP"
export BENESSERE_SOURCE_DB="$DATA/benessere.db"
export BENESSERE_BACKUP_DB="$BACKUP/benessere.db"
python3 - <<'PY'
import os, sqlite3
src=sqlite3.connect('file:'+os.environ['BENESSERE_SOURCE_DB']+'?mode=ro',uri=True,timeout=30)
dst=sqlite3.connect(os.environ['BENESSERE_BACKUP_DB'])
try: src.backup(dst)
finally: src.close();dst.close()
verify=sqlite3.connect('file:'+os.environ['BENESSERE_BACKUP_DB']+'?mode=ro',uri=True)
try:
    ok=verify.execute('PRAGMA integrity_check').fetchone()[0]
    if ok!='ok': raise RuntimeError('Backup SQLite non integro: '+ok)
    for name in ('meals','workouts','workout_blocks','wod_results',
                 'strength_maxes','progress_photos','hr_samples','sleeps'):
        found=verify.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
        if found:
            total=verify.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]
            print(name, 'record:', total)
finally: verify.close()
print('Backup SQLite integro.')
PY
tar -C "$DATA" --exclude='./benessere.db' \
  --exclude='./benessere.db-wal' --exclude='./benessere.db-shm' \
  -czf "$BACKUP/data-files.tar.gz" .
chmod 600 "$BACKUP/benessere.db" "$BACKUP/data-files.tar.gz"
echo "$BACKUP" > "$PRIVATE/last-pwa-backup.txt"
echo "Backup protetto: $BACKUP"

echo "[5/7] Cambio dashboard (Streamlit arrestato, NON eliminato)"
rollback_on_error() {
  set +e
  echo "ATTENZIONE: avvio non riuscito, ripristino la dashboard precedente." >&2
  docker compose -p "$PROJECT" -f "$COMPOSE" down >/dev/null 2>&1
  if docker inspect "$LEGACY" >/dev/null 2>&1; then
    if ! docker inspect benessere-dashboard >/dev/null 2>&1; then
      docker rename "$LEGACY" benessere-dashboard
    fi
  fi
  if docker inspect benessere-dashboard >/dev/null 2>&1; then
    docker update --restart=unless-stopped benessere-dashboard >/dev/null
    docker start benessere-dashboard >/dev/null
  fi
}
trap rollback_on_error ERR
docker update --restart=no benessere-dashboard >/dev/null
docker stop -t 20 benessere-dashboard >/dev/null
docker rename benessere-dashboard "$LEGACY"
docker compose -p "$PROJECT" -f "$COMPOSE" up -d --no-build --pull never

echo "[6/7] Test API / Next.js con autenticazione interna"
for attempt in $(seq 1 20); do
  if docker exec benessere-dashboard node -e \
  'fetch("http://127.0.0.1:8501/api/summary",{cache:"no-store"}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))' \
  >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
docker exec benessere-dashboard node -e \
  'Promise.all(["/api/summary","/api/journal?kind=meals","/api/journal?kind=workouts","/api/alarm"].map(
   path=>fetch("http://127.0.0.1:8501"+path,{cache:"no-store"}).then(r=>{
    if(!r.ok)throw Error(path+": HTTP "+r.status);
    return r.json()
   }))).then(()=>{console.log("Smoke Next + FastAPI: OK")}).catch(e=>{console.error(e.message);process.exit(1)})'
docker inspect --format '{{.Name}} {{.State.Status}} {{.State.OOMKilled}}' \
  benessere-dashboard benessere-api-v2

echo "[7/7] Conferma switch e salvataggio percorso rollback"
echo "$LEGACY" > "$PRIVATE/legacy-dashboard-name.txt"
chmod 600 "$PRIVATE/legacy-dashboard-name.txt"
trap - ERR
echo "SWITCH RIUSCITO."
echo "Caddy mantiene l'indirizzo https://dashboard-benessere.45-77-66-215.nip.io"
echo "Vecchia Streamlit conservata spenta come: $LEGACY"
echo "Backup: $BACKUP"
echo "Android, MCP e Google Sheets rimangono collegati al DB originale."
