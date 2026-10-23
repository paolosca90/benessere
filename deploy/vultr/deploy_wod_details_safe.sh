#!/usr/bin/env bash
# Benessere: targeted WOD UI/API + Sheets bridge upgrade, with rollback.
# Must be executed as root on the VPS after copying the CI artifact ZIP's tar.gz.
# No modifications to Helio/Android receiver, MCP, existing sync server or other stacks.
set -Eeuo pipefail
umask 077

ROOT=/opt/benessere
SRC="$ROOT/source"
COMPOSE="$ROOT/preview-source/webapp/compose.production.yml"
BRANCH="fix/pwa-wod-full-details-rpe4"
ARCHIVE="${1:-/tmp/benessere-wod-images.tar.gz}"
REV="${2:-}"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo "Expected full 40-char CI commit SHA" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || { echo "Root required" >&2; exit 1; }
for cmd in docker git python3 gzip; do command -v "$cmd" >/dev/null || { echo "Missing: $cmd" >&2; exit 1; }; done
[[ -s "$ARCHIVE" && -f "$COMPOSE" && -s "$SRC/sheets_bridge.py" ]] || { echo "Missing CI archive, compose, or bridge" >&2; exit 1; }
gzip -t "$ARCHIVE"
docker compose -p benessere-v2 -f "$COMPOSE" config --quiet
docker inspect benessere-dashboard benessere-api-v2 benessere-sheets-bridge >/dev/null
for i in benessere-pwa-preview:preview benessere-api-v2:preview; do
  docker image inspect "$i" >/dev/null
done
[[ "$(df -Pk / | awk 'NR==2{print $4}')" -gt 700000 ]] || { echo "Insufficient disk" >&2; exit 1; }
[[ -z "$(git -C "$SRC" status --porcelain -- sheets_bridge.py)" ]] || { echo "Source bridge has local edits; refusing overwrite" >&2; exit 1; }

# Fetch without touching the dirty live source worktree or current branch.
git -C "$SRC" fetch --no-tags origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
ACTUAL="$(git -C "$SRC" rev-parse "refs/remotes/origin/$BRANCH")"
[[ "$ACTUAL" = "$REV" ]] || { echo "CI revision and branch SHA differ: $ACTUAL != $REV" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$ROOT/backups/wod-update-$STAMP"
install -d -m 700 "$BACKUP"
cp -a "$SRC/sheets_bridge.py" "$BACKUP/sheets_bridge.py"
git -C "$SRC" show "$REV:sheets_bridge.py" > "$BACKUP/sheets_bridge.new.py"
python3 - "$BACKUP/sheets_bridge.new.py" <<'PY'
import ast, pathlib, sys
ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
PY

# Consistent, private backup of live SQLite; NEVER restore automatically over new writes.
python3 - "$ROOT/data/benessere.db" "$BACKUP/benessere.db" <<'PY'
import sqlite3,sys
src=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True,timeout=30)
dst=sqlite3.connect(sys.argv[2])
try: src.backup(dst)
finally: src.close(); dst.close()
check=sqlite3.connect("file:"+sys.argv[2]+"?mode=ro",uri=True)
try:
    assert check.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
finally: check.close()
print("SQLite backup integrity: OK")
PY
chmod 600 "$BACKUP/sheets_bridge.py" "$BACKUP/sheets_bridge.new.py" "$BACKUP/benessere.db"

OLD_UI="benessere-pwa-preview:rollback-wod-$STAMP"
OLD_API="benessere-api-v2:rollback-wod-$STAMP"
docker tag benessere-pwa-preview:preview "$OLD_UI"
docker tag benessere-api-v2:preview "$OLD_API"
STARTED=0
BRIDGE_CHANGED=0
rollback() {
  local rc=$?
  trap - ERR
  if [[ "$rc" -ne 0 ]]; then
    echo "ERROR: restoring old PWA/API images and previous bridge file" >&2
    if [[ "$BRIDGE_CHANGED" = 1 ]]; then
      cp "$BACKUP/sheets_bridge.py" "$SRC/sheets_bridge.py" || true
      chmod 644 "$SRC/sheets_bridge.py" || true
      docker restart benessere-sheets-bridge >/dev/null || true
    fi
    docker tag "$OLD_UI" benessere-pwa-preview:preview || true
    docker tag "$OLD_API" benessere-api-v2:preview || true
    if [[ "$STARTED" = 1 ]]; then
      docker compose -p benessere-v2 -f "$COMPOSE" up -d \
        --no-deps --no-build --pull never --force-recreate \
        benessere-api-v2 benessere-dashboard || true
    fi
    echo "Backup remains at $BACKUP. No database was restored." >&2
  fi
  exit "$rc"
}
trap rollback ERR

echo "[1/4] Import CI Docker images, verify exact source revision"
docker load -i "$ARCHIVE" >/dev/null
for image in benessere-pwa-preview:preview benessere-api-v2:preview; do
  label="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")"
  [[ "$label" = "$REV" ]] || { echo "$image: wrong image revision '$label' (expected '$REV')" >&2; false; }
done

echo "[2/4] Recreate ONLY web FastAPI and Next.js; leave MCP/Helio/bridge running"
STARTED=1
docker compose -p benessere-v2 -f "$COMPOSE" up -d \
  --no-deps --no-build --pull never --force-recreate \
  benessere-api-v2 benessere-dashboard
ready=0
for i in $(seq 1 30); do
  if docker exec benessere-dashboard node -e '
    Promise.all(["/api/summary","/api/wod-library"].map(async p=>{
      const r=await fetch("http://127.0.0.1:8501"+p,{signal:AbortSignal.timeout(4000)});
      if(!r.ok)throw Error(p+" HTTP "+r.status);
      const d=await r.json();
      if(p==="/api/wod-library"&&!Array.isArray(d.items))throw Error("No WOD items");
    })).catch(e=>{console.error(e.message);process.exitCode=1});
  ' >/dev/null 2>&1; then ready=1;break;fi
  sleep 2
done
[[ "$ready" = 1 ]] || { echo "New PWA/API health check failed" >&2; false; }

echo "[3/4] Swap ONLY bridge file (bind-mounted), restart only Sheets bridge"
install -m 644 "$BACKUP/sheets_bridge.new.py" "$SRC/sheets_bridge.py"
BRIDGE_CHANGED=1
docker exec benessere-sheets-bridge python -c 'from sheets_bridge import apply_workout_revision; print("bridge module OK")' >/dev/null
docker restart benessere-sheets-bridge >/dev/null
[[ "$(docker inspect --format '{{.State.Running}}' benessere-sheets-bridge)" = true ]] || { echo "Bridge is down" >&2; false; }

echo "[4/4] Final smoke without writing any diary data"
docker exec benessere-dashboard node -e '
  Promise.all(["/api/summary","/api/journal?kind=workouts&day=2026-10-23","/api/wod-library"].map(async p=>{
    const r=await fetch("http://127.0.0.1:8501"+p,{signal:AbortSignal.timeout(5000)});
    if(!r.ok)throw Error(p+" HTTP "+r.status);
    return r.json();
  })).then(([summary,journal,library])=>{
    if(!Array.isArray(journal.items)||!Array.isArray(library.items))throw Error("Missing lists");
    console.log("OK: summary + linked workouts + WOD library reachable");
  }).catch(e=>{console.error(e.message);process.exitCode=1});
'
trap - ERR
printf '%s\n' "$REV" > "$ROOT/private/wod-release-revision.txt"
chmod 600 "$ROOT/private/wod-release-revision.txt"
echo "UPDATE SUCCESS. Revision: $REV"
echo "Previous Docker images retained as $OLD_UI and $OLD_API"
echo "Backup: $BACKUP"
echo "Google Sheets correction row in HOLD: set to PENDING only AFTER checking this output."
