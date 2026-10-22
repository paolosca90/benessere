#!/usr/bin/env bash
# Aggiorna SOLO la dashboard Next.js, conservando API, database e altri servizi.
# Esegui sulla VPS passando archivio immagini CI e SHA del commit costruito.
set -Eeuo pipefail
umask 077
ARCHIVE="${1:-/tmp/benessere-ui-live.tar.gz}"
REV="${2:-}"
COMPOSE=/opt/benessere/preview-source/webapp/compose.production.yml
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OLD_PWA="benessere-pwa-preview:rollback-live-card-$STAMP"
OLD_API="benessere-api-v2:rollback-live-card-$STAMP"
ARMED=0

fail() { echo "ERRORE: $*" >&2; exit 1; }
rollback() {
  local rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ] && [ "$ARMED" -eq 1 ]; then
    echo "Ripristino dashboard precedente, senza toccare API o database..." >&2
    docker tag "$OLD_API" benessere-api-v2:preview || true
    docker tag "$OLD_PWA" benessere-pwa-preview:preview || true
    docker compose -p benessere-v2 -f "$COMPOSE" up -d \
      --no-deps --no-build --pull never --force-recreate benessere-dashboard || true
  fi
  exit "$rc"
}
[ "$(id -u)" -eq 0 ] || fail "Eseguire come root VPS"
[[ "$REV" =~ ^[0-9a-f]{40}$ ]] || fail "SHA GitHub completo richiesto"
[ -s "$ARCHIVE" ] || fail "Archivio immagini mancante: $ARCHIVE"
[ -f "$COMPOSE" ] || fail "Compose di produzione non trovato"
for cmd in docker gzip; do command -v "$cmd" >/dev/null || fail "$cmd non disponibile"; done
gzip -t "$ARCHIVE" || fail "Archivio CI non integro"
docker inspect benessere-dashboard benessere-api-v2 >/dev/null || fail "Servizi in produzione non trovati"
docker compose -p benessere-v2 -f "$COMPOSE" config --quiet
[ "$(df -Pk / | awk 'NR==2 {print $4}')" -gt 600000 ] || fail "Spazio VPS insufficiente"
docker tag benessere-pwa-preview:preview "$OLD_PWA"
docker tag benessere-api-v2:preview "$OLD_API"
ARMED=1
trap rollback EXIT

echo "Caricamento immagini CI..."
docker load -i "$ARCHIVE" >/dev/null
# L'archivio comprende anche FastAPI: ripristinare il vecchio tag, senza riavviarla.
docker tag "$OLD_API" benessere-api-v2:preview
ACTUAL="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' benessere-pwa-preview:preview)"
[ "$ACTUAL" = "$REV" ] || fail "Immagine PWA revisione $ACTUAL, attesa $REV"

echo "Sostituzione del solo container web..."
docker compose -p benessere-v2 -f "$COMPOSE" up -d \
  --no-deps --no-build --pull never --force-recreate benessere-dashboard

ready=0
for attempt in $(seq 1 45); do
  if docker exec benessere-dashboard node -e '
    Promise.all(["/api/summary","/api/live-heart-rate"].map(async path=>{
      const controller=new AbortController();
      const t=setTimeout(()=>controller.abort(),3000);
      try {
        const res=await fetch("http://127.0.0.1:8501"+path,{signal:controller.signal,cache:"no-store"});
        if(!res.ok)throw Error(path+" HTTP "+res.status);
        await res.json();
      } finally {clearTimeout(t)}
    })).catch(err=>{console.error(err.message);process.exitCode=1});
  ' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[ "$ready" -eq 1 ] || fail "La dashboard non risponde: rollback automatico"
ARMED=0
trap - EXIT
echo "OK: dashboard aggiornata a $REV. API, database, MCP e altri container invariati."
echo "Immagine web precedente conservata: $OLD_PWA"
