#!/usr/bin/env bash
# Install ONLY the historical physiological-load report API and PWA.
# No Android APK, no BLE changes, no MCP/Sheets/sync receiver restarts.
# Requires the GitHub Actions benessere-preview-images tar.gz for EXACT SHA.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "Root VPS required"; exit 1; }
ROOT=/opt/benessere
SOURCE="$ROOT/source"
COMPOSE="$ROOT/preview-source/webapp/compose.production.yml"
ARCHIVE="${1:-/tmp/benessere-physio-images.tar.gz}"
REV="${2:-}"
BRANCH=feature/wod-day-physiological-load
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || { echo "Full commit SHA required" >&2; exit 1; }
[[ -s "$ARCHIVE" && -s "$COMPOSE" && -s "$ROOT/data/benessere.db" ]] || { echo "Missing image archive, compose or database" >&2; exit 1; }
for cmd in docker git python3 gzip; do command -v "$cmd" >/dev/null || { echo "Missing $cmd" >&2; exit 1; }; done
gzip -t "$ARCHIVE"
docker inspect benessere-dashboard benessere-api-v2 >/dev/null
docker compose -p benessere-v2 -f "$COMPOSE" config --quiet
[[ "$(df -Pk / | awk 'NR==2{print $4}')" -gt 750000 ]] || { echo "Disk space insufficient" >&2; exit 1; }

git -C "$SOURCE" fetch --no-tags origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
ACTUAL="$(git -C "$SOURCE" rev-parse "refs/remotes/origin/$BRANCH")"
[[ "$ACTUAL" = "$REV" ]] || { echo "Wrong commit: branch $ACTUAL versus artifact $REV" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$ROOT/backups/physio-$STAMP"
install -d -m 700 "$BACKUP"
python3 - "$ROOT/data/benessere.db" "$BACKUP/benessere.db" <<'PY'
import sqlite3,sys
src=sqlite3.connect("file:"+sys.argv[1]+"?mode=ro",uri=True,timeout=30)
dest=sqlite3.connect(sys.argv[2])
try: src.backup(dest)
finally: src.close();dest.close()
verify=sqlite3.connect("file:"+sys.argv[2]+"?mode=ro",uri=True)
try: assert verify.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
finally: verify.close()
print("SQLite safety copy: OK")
PY
chmod 600 "$BACKUP/benessere.db"
OLD_API="benessere-api-v2:rollback-physio-$STAMP"
OLD_UI="benessere-pwa-preview:rollback-physio-$STAMP"
docker tag benessere-api-v2:preview "$OLD_API"
docker tag benessere-pwa-preview:preview "$OLD_UI"
STARTED=0

recover() {
  local rc=$?
  trap - ERR
  if [[ "$rc" -ne 0 ]]; then
    echo "FAIL: restoring previous PWA and API images. Database remains untouched." >&2
    docker tag "$OLD_API" benessere-api-v2:preview || true
    docker tag "$OLD_UI" benessere-pwa-preview:preview || true
    if [[ "$STARTED" = 1 ]]; then
      docker compose -p benessere-v2 -f "$COMPOSE" up -d \
        --no-deps --no-build --pull never --force-recreate \
        benessere-api-v2 benessere-dashboard || true
    fi
    echo "Backup at $BACKUP" >&2
  fi
  exit "$rc"
}
trap recover ERR

echo "[1/3] Importing and pinning exact CI image revisions"
docker load -i "$ARCHIVE" >/dev/null
for image in benessere-api-v2:preview benessere-pwa-preview:preview; do
  IMGREV="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")"
  [[ "$IMGREV" = "$REV" ]] || { echo "$image contains revision '$IMGREV' instead of $REV" >&2; false; }
done

echo "[2/3] Updating only FastAPI and Next.js"
STARTED=1
docker compose -p benessere-v2 -f "$COMPOSE" up -d \
  --no-deps --no-build --pull never --force-recreate \
  benessere-api-v2 benessere-dashboard

echo "[3/3] Checking authenticated PWA → API without inserting samples"
READY=0
for attempt in $(seq 1 30); do
  if docker exec benessere-dashboard node -e '
    Promise.all([
      "/api/summary",
      "/api/physiological-load?day=2026-10-23",
      "/api/wod-library"
    ].map(async path=>{
      const res=await fetch("http://127.0.0.1:8501"+path,{
        cache:"no-store",signal:AbortSignal.timeout(5000)
      });
      if(!res.ok)throw Error(path+" status "+res.status);
      const json=await res.json();
      if(path.includes("physiological-load") &&
         (!Array.isArray(json.workouts)||!json.training||!json.day))
         throw Error("Invalid load report schema");
    })).catch(err=>{console.error(err.message);process.exitCode=1});
  ' >/dev/null 2>&1; then READY=1; break; fi
  sleep 2
done
[[ "$READY" = 1 ]] || { echo "Smoke checks failed" >&2; false; }
trap - ERR
echo "PHYSIO SUCCESS: $REV"
echo "Backup: $BACKUP"
echo "Old API/UI images: $OLD_API $OLD_UI"
echo "No BLE/Android/MCP/Sheets receiver changed; no measurements inserted."
