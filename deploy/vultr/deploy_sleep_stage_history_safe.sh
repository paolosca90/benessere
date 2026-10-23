#!/usr/bin/env bash
# Benessere / phase 2: install real historical stage intervals, NOT a smart alarm.
# Run on Vultr after transferring official CI Docker archive for pinned revision.
# No git checkout, reset, merge or blanket compose restarts.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == "0" ]] || { echo "Root required" >&2; exit 1; }
ROOT=/opt/benessere
SRC="$ROOT/source"
COMPOSE="$ROOT/preview-source/webapp/compose.production.yml"
ARCHIVE="${1:-/tmp/benessere-sleepstage-images.tar.gz}"
REV="${2:-}"
BASE=8e3f5748f3e86cad72c6f3283c6382f2ae464a90
BRANCH=feature/helio-smart-wake-phase2-stage-audit
[[ "$REV" =~ ^[a-f0-9]{40}$ ]] || { echo "Full revision SHA required" >&2; exit 1; }
[[ -s "$ARCHIVE" && -f "$COMPOSE" && -f "$SRC/benessere/health_sync.py" ]] || {
  echo "Required archive, compose or receiver file missing" >&2; exit 1;
}
for bin in git docker python3 gzip; do command -v "$bin" >/dev/null; done
gzip -t "$ARCHIVE"
docker inspect benessere-dashboard benessere-api-v2 benessere-api >/dev/null
docker compose -p benessere-v2 -f "$COMPOSE" config --quiet

echo "[0/5] Inspecting receiver mount and original local changes"
# The receiver must actually use the host source. Do not claim success if it
# has baked-in code or bind mounts only one file without the new module.
python3 - "$SRC" "$(docker inspect --format '{{json .Mounts}}' benessere-api)" <<'PY'
import json, pathlib, sys
source = pathlib.Path(sys.argv[1]).resolve()
mounts = json.loads(sys.argv[2])
ok = any(x.get("Type") == "bind" and (
    source == pathlib.Path(x.get("Source", "/invalid")).resolve() or
    pathlib.Path(x.get("Source", "/invalid")).resolve() in source.parents
) for x in mounts)
assert ok, "Android sync receiver is not mounted from source. No deployment."
print("Receiver source bind: OK")
PY

git -C "$SRC" fetch --no-tags origin \
  "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH" \
  "refs/heads/feature/wod-day-physiological-load:refs/remotes/origin/feature/wod-day-physiological-load"
ACTUAL="$(git -C "$SRC" rev-parse "refs/remotes/origin/$BRANCH")"
[[ "$ACTUAL" == "$REV" ]] || { echo "Git/CI revision mismatch" >&2; exit 1; }
git -C "$SRC" cat-file -e "$BASE^{commit}"

# Only overwrite files known identical (ignoring CRLF differences) to the
# already-installed, separately verified Health Connect / BLE / HRV source.
python3 - "$SRC" "$BASE" <<'PY'
import pathlib, subprocess, sys
root, base = pathlib.Path(sys.argv[1]), sys.argv[2]
for path in ("benessere/health_sync.py", "sync_server.py"):
    old = subprocess.check_output(
        ["git","-C",str(root),"show",f"{base}:{path}"]
    ).decode("utf-8").replace("\r\n","\n")
    live = (root/path).read_text(encoding="utf-8").replace("\r\n","\n")
    assert live == old, f"{path} has additional VPS changes; refusing to overwrite"
assert not (root/"benessere/sleep_stage_history.py").exists(), (
    "Stage-history module already exists; inspect before proceeding")
print("Local HRV + alarm + BLE changes match audited GitHub base: OK")
PY

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$ROOT/backups/sleep-stage-$STAMP"
install -d -m 700 "$BACKUP"
cp -a "$SRC/benessere/health_sync.py" "$BACKUP/health_sync.original.py"
cp -a "$SRC/sync_server.py" "$BACKUP/sync_server.untouched.py"
git -C "$SRC" show "$REV:benessere/health_sync.py" > "$BACKUP/health_sync.new.py"
git -C "$SRC" show "$REV:benessere/sleep_stage_history.py" > "$BACKUP/sleep_stage_history.new.py"
python3 - "$BACKUP" <<'PY'
import ast, pathlib, sys
for name in ("health_sync.new.py","sleep_stage_history.new.py"):
    ast.parse((pathlib.Path(sys.argv[1])/name).read_text(encoding="utf-8"))
print("Receiver Python files: syntax OK")
PY

# Private hot SQLite backup. No restore over live new writes.
python3 - "$ROOT/data/benessere.db" "$BACKUP/benessere.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True,timeout=30)
dst = sqlite3.connect(sys.argv[2])
try: src.backup(dst)
finally: src.close(); dst.close()
try:
    check = sqlite3.connect("file:"+sys.argv[2]+"?mode=ro",uri=True)
    assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
finally: check.close()
print("SQLite backup integrity: OK")
PY
chmod 600 "$BACKUP"/*.py "$BACKUP/benessere.db"

API_OLD="benessere-api-v2:rollback-stages-$STAMP"
UI_OLD="benessere-pwa-preview:rollback-stages-$STAMP"
docker tag benessere-api-v2:preview "$API_OLD"
docker tag benessere-pwa-preview:preview "$UI_OLD"
UPDATED_RECEIVER=0
UPDATED_WEB=0
rollback() {
  rc=$?
  trap - ERR
  if [[ "$rc" != "0" ]]; then
    echo "FAIL: restoring receiver source and old web images" >&2
    if [[ "$UPDATED_RECEIVER" == "1" ]]; then
      cp -a "$BACKUP/health_sync.original.py" "$SRC/benessere/health_sync.py" || true
      rm -f "$SRC/benessere/sleep_stage_history.py" || true
      docker restart benessere-api >/dev/null || true
    fi
    docker tag "$API_OLD" benessere-api-v2:preview || true
    docker tag "$UI_OLD" benessere-pwa-preview:preview || true
    if [[ "$UPDATED_WEB" == "1" ]]; then
      docker compose -p benessere-v2 -f "$COMPOSE" up -d \
        --no-deps --no-build --pull never --force-recreate \
        benessere-api-v2 benessere-dashboard || true
    fi
    echo "Protected backup: $BACKUP. SQLite not restored." >&2
  fi
  exit "$rc"
}
trap rollback ERR

echo "[1/5] Loading signed-off GitHub CI images"
docker load -i "$ARCHIVE" >/dev/null
for image in benessere-api-v2:preview benessere-pwa-preview:preview; do
  label="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")"
  [[ "$label" == "$REV" ]] || { echo "Wrong image version for $image" >&2; false; }
done

echo "[2/5] Installing ONLY two receiver files; leaving sync_server.py untouched"
UPDATED_RECEIVER=1
install -m 644 "$BACKUP/sleep_stage_history.new.py" "$SRC/benessere/sleep_stage_history.py"
install -m 644 "$BACKUP/health_sync.new.py" "$SRC/benessere/health_sync.py"
docker restart benessere-api >/dev/null
docker exec benessere-api python3 -c \
  'from benessere import health_sync, sleep_stage_history; print("New stage-history importer available")'
[[ "$(docker inspect --format '{{.State.Running}}' benessere-api)" == "true" ]]

echo "[3/5] Updating ONLY PWA and internal FastAPI"
UPDATED_WEB=1
docker compose -p benessere-v2 -f "$COMPOSE" up -d \
  --no-deps --no-build --pull never --force-recreate \
  benessere-api-v2 benessere-dashboard

echo "[4/5] Checking new authenticated read-only endpoint"
READY=0
for attempt in $(seq 1 30); do
  if docker exec benessere-dashboard node -e '
    Promise.all([
      "/api/summary",
      "/api/sleep-stage-history?day=2026-10-23",
      "/api/wod-library",
      "/api/physiological-load?day=2026-10-23",
      "/api/alarm"
    ].map(async path=>{
      const response=await fetch("http://127.0.0.1:8501"+path,{
        cache:"no-store",signal:AbortSignal.timeout(5000)});
      if(!response.ok)throw Error(path+" HTTP "+response.status);
      const j=await response.json();
      if(path.includes("sleep-stage-history") &&
         (j.history_only!==true || j.live_stage_available!==false))
         throw Error("Unsafe sleep stage status");
    })).catch(error=>{console.error(error.message);process.exitCode=1});
  ' >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
[[ "$READY" == "1" ]] || { echo "API/PWA smoke failed" >&2; false; }

echo "[5/5] Check that Helio and Zepp alarm remain UNCHANGED"
docker inspect benessere-mcp benessere-sheets-bridge >/dev/null
trap - ERR
echo "SLEEP_STAGE_SERVER_SUCCESS: $REV"
echo "Backup: $BACKUP"
echo "No Android APK installed. No Zepp alarm commands sent."
echo "Existing past nights may have only summary minutes until phone resync."
