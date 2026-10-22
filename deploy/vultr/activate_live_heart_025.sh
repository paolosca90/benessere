#!/usr/bin/env bash
# Deploy verified Helio live HR backend and PWA on an already migrated VPS.
# Does not overwrite health records, unrelated containers, or user secrets.
set -Eeuo pipefail
umask 077

ROOT=/opt/benessere
SOURCE="$ROOT/source"
STAGE="$ROOT/preview-source"
DATA="$ROOT/data"
PRIVATE="$ROOT/private"
DB="$DATA/benessere.db"
ARCHIVE=/tmp/benessere-live-025.tar.gz
COMPOSE="$STAGE/webapp/compose.production.yml"
BRANCH=feature/benessere-v2-pwa-sveglia
REV=e4f252a6ae4845b3acea4c52e08ee17473080166
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="$ROOT/backups/live-025-$STAMP"
OLD_API="benessere-api-v2:rollback-$STAMP"
OLD_PWA="benessere-pwa-preview:rollback-$STAMP"
OLD_STAGE=
ARMED=0

fail() { printf 'ERRORE: %s\n' "$*" >&2; exit 1; }
report() { printf '==> %s\n' "$*"; }

restore() {
  local rc=$?
  [ "$rc" -eq 0 ] && return 0
  trap - EXIT
  [ "$ARMED" = 1 ] || exit "$rc"
  set +e
  echo "ATTENZIONE: ripristino dei soli servizi Benessere interessati." >&2

  if [ -f "$BACKUP/sync_server.py" ]; then
    cp -p "$BACKUP/sync_server.py" "$SOURCE/sync_server.py"
  fi
  # Restore exactly the previous Python dependency set.
  for module in live_heart alarm_settings health_sync; do
    if [ -f "$BACKUP/$module-absent" ]; then
      rm -f "$SOURCE/benessere/$module.py"
    elif [ -f "$BACKUP/$module.py" ]; then
      cp -p "$BACKUP/$module.py" "$SOURCE/benessere/$module.py"
    fi
  done

  docker tag "$OLD_API" benessere-api-v2:preview
  docker tag "$OLD_PWA" benessere-pwa-preview:preview
  if [ -n "$OLD_STAGE" ]; then
    git -C "$STAGE" checkout --detach "$OLD_STAGE"
  fi

  docker restart benessere-api
  docker compose -p benessere-v2 -f "$COMPOSE" up -d \
    --no-build --pull never --force-recreate benessere-api-v2 benessere-dashboard
  echo "Tentativo di rollback completato. Database originale non ripristinato né sovrascritto." >&2
  exit "$rc"
}

[ "$(id -u)" -eq 0 ] || fail "Richiesto accesso root sulla VPS."
for command in git docker python3 curl gzip; do
  command -v "$command" >/dev/null || fail "Comando mancante: $command"
done
[ -s "$ARCHIVE" ] || fail "Archivio assente: $ARCHIVE"
[ -s "$DB" ] || fail "Database Benessere assente."
[ -s "$SOURCE/sync_server.py" ] || fail "Backend Android assente."
[ -s "$COMPOSE" ] || fail "Compose della PWA assente."
[ -s "$PRIVATE/webapp.preview.env" ] || fail "Segreti PWA mancanti."
[ -z "$(git -C "$STAGE" status --porcelain)" ] || fail "Lo staging ha modifiche locali."
[ -z "$(git -C "$SOURCE" status --porcelain)" ] || fail "La sorgente attiva ha modifiche locali non protette."
gzip -t "$ARCHIVE" || fail "Archivio Docker non valido."
[ "$(df -Pk / | awk 'NR==2{print $4}')" -ge 900000 ] || fail "Spazio libero insufficiente."
docker inspect benessere-api benessere-api-v2 benessere-dashboard >/dev/null ||
  fail "Uno o più container Benessere attesi non esistono."

report "Verifica repository e commit delle immagini"
git -C "$SOURCE" fetch --no-tags origin \
  "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
git -C "$SOURCE" cat-file -e "$REV^{commit}" ||
  fail "Commit del codice non disponibile."
OLD_STAGE=$(git -C "$STAGE" rev-parse HEAD)
[ "$OLD_STAGE" != "$REV" ] ||
  fail "Staging già al commit live: controllare prima lo stato dei servizi."

report "Backup coerente del database e dei moduli Python interessati"
install -d -m 700 "$BACKUP"
cp -p "$SOURCE/sync_server.py" "$BACKUP/sync_server.py"
for module in live_heart alarm_settings health_sync; do
  if [ -f "$SOURCE/benessere/$module.py" ]; then
    cp -p "$SOURCE/benessere/$module.py" "$BACKUP/$module.py"
  else
    : > "$BACKUP/$module-absent"
  fi
done
python3 - "$DB" "$BACKUP/benessere.db" <<'PY'
import sqlite3, sys
source=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro", uri=True, timeout=30)
dest=sqlite3.connect(sys.argv[2])
try:
    source.backup(dest)
finally:
    dest.close()
    source.close()
check=sqlite3.connect("file:"+sys.argv[2]+"?mode=ro", uri=True)
try:
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
finally:
    check.close()
print("Backup SQLite completo e integro; nessuna misura di prova inserita.")
PY
chmod 600 "$BACKUP/benessere.db"

report "Salvataggio immagini Docker attuali per rollback"
docker tag benessere-api-v2:preview "$OLD_API"
docker tag benessere-pwa-preview:preview "$OLD_PWA"
ARMED=1
trap restore EXIT

report "Caricamento immagini e verifica revisione GitHub"
docker load -i "$ARCHIVE"
for image in benessere-api-v2:preview benessere-pwa-preview:preview; do
  actual=$(docker image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
  [ "$actual" = "$REV" ] ||
    fail "Immagine $image non corrispondente: $actual (atteso $REV)."
done

report "Allineamento worktree della sola dashboard"
git -C "$STAGE" checkout --detach "$REV"
docker compose -p benessere-v2 -f "$COMPOSE" config --quiet

report "Aggiornamento ricevitore e dipendenze con verifica preventiva"
python3 - "$STAGE/sync_server.py" \
  "$STAGE/benessere/alarm_settings.py" \
  "$STAGE/benessere/health_sync.py" \
  "$STAGE/benessere/live_heart.py" <<'PY'
import ast,sys
for item in sys.argv[1:]:
    ast.parse(open(item, encoding="utf-8").read(), filename=item)
print("Sintassi di tutte le dipendenze Python verificata.")
PY
cp "$STAGE/sync_server.py" "$SOURCE/sync_server.py"
for module in alarm_settings health_sync live_heart; do
  cp "$STAGE/benessere/$module.py" "$SOURCE/benessere/$module.py"
done
chmod 644 "$SOURCE/sync_server.py" "$SOURCE/benessere/alarm_settings.py" \
  "$SOURCE/benessere/health_sync.py" "$SOURCE/benessere/live_heart.py"
# Reproduce the container runtime's imports with no network, no production DB,
# and a read-only code mount. Fail before stopping any running service.
docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  -v "$SOURCE:/app:ro" -w /app --entrypoint python python:3.12-slim \
  -c 'import sync_server; from benessere import alarm_settings, health_sync, live_heart; print("All Android receiver imports OK")'

report "Riavvio del solo ricevitore Android"
docker restart benessere-api >/dev/null

report "Aggiornamento dei soli due container PWA/FastAPI"
docker compose -p benessere-v2 -f "$COMPOSE" up -d \
  --no-build --pull never --force-recreate benessere-api-v2 benessere-dashboard

report "Verifica HTTP e autenticazione: nessun dato sanitario di prova"
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl --max-time 8 -sS -o /dev/null -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' \
    https://benessere.45-77-66-215.nip.io/api/v1/live-heart-rate) || code=000
  [ "$code" = 401 ] && break
  sleep 2
done
[ "$code" = 401 ] || fail "Ricevitore live non disponibile: HTTP $code (previsto 401 senza token)."
curl --fail --silent --show-error --max-time 10 \
  https://benessere.45-77-66-215.nip.io/health >/dev/null
docker exec benessere-dashboard node -e \
  'fetch("http://127.0.0.1:8501/api/live-heart-rate",{cache:"no-store"}).then(async r=>{if(!r.ok)throw new Error("HTTP "+r.status);const v=await r.json();if(v.status!=="offline"&&v.status!=="live")throw Error("Invalid payload");console.log("PWA/live-heart-rate:",v.status)}).catch(e=>{console.error(e.message);process.exit(1)})'

ARMED=0
trap - EXIT
report "SUCCESSO: ricevitore live e webapp aggiornati"
report "Backup riservato: $BACKUP"
report "Per vedere i battiti, abilita l'invio FC live su Android e tieni l'app aperta."
