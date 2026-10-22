#!/usr/bin/env bash
# Deploy only Benessere PWA cards refresh, never restart receiver/API.
# Input: verified GitHub Actions benessere-preview-images.tar.gz archive.
set -Eeuo pipefail
umask 077
ROOT=/opt/benessere
SOURCE="$ROOT/source"
STAGE="$ROOT/preview-source"
COMPOSE="$STAGE/webapp/compose.production.yml"
ARCHIVE=/tmp/benessere-ui-refresh.tar.gz
REV=b7a24e0dd872fff647b62b3c6c46cb1da1c425b2
BRANCH=feature/benessere-v2-pwa-sveglia
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OLD_PWA="benessere-pwa-preview:rollback-ui-$STAMP"
OLD_API="benessere-api-v2:rollback-ui-$STAMP"
OLD_STAGE=
ARMED=0

fail() { echo "ERRORE: $*" >&2; exit 1; }
msg() { echo "==> $*"; }

rollback() {
  local result=$?
  [ "$result" -ne 0 ] || return 0
  trap - EXIT
  [ "$ARMED" -eq 1 ] || exit "$result"
  set +e
  echo "ATTENZIONE: ripristino della sola dashboard precedente." >&2
  docker tag "$OLD_API" benessere-api-v2:preview
  docker tag "$OLD_PWA" benessere-pwa-preview:preview
  if [ -n "$OLD_STAGE" ]; then
    git -C "$STAGE" checkout --detach "$OLD_STAGE"
  fi
  docker compose -p benessere-v2 -f "$COMPOSE" up -d \
    --no-deps --no-build --pull never --force-recreate benessere-dashboard
  echo "Rollback dashboard tentato. Nessuna operazione sul database sanitario." >&2
  exit "$result"
}

[ "$(id -u)" -eq 0 ] || fail "Richiesto utente root."
for command in docker git gzip curl; do
  command -v "$command" >/dev/null || fail "Comando mancante: $command"
done
[ -s "$ARCHIVE" ] || fail "Scarica il NUOVO archivio in $ARCHIVE"
gzip -t "$ARCHIVE" || fail "Archivio danneggiato."
[ -s "$COMPOSE" ] || fail "Compose PWA mancante."
[ -z "$(git -C "$STAGE" status --porcelain)" ] ||
  fail "Codice staging con modifiche non salvate."
[ "$(df -Pk / | awk 'NR==2{print $4}')" -ge 900000 ] ||
  fail "Spazio disco insufficiente."
docker inspect benessere-api benessere-api-v2 benessere-dashboard >/dev/null ||
  fail "Backend Android, API o dashboard non disponibili."
[ "$(docker inspect benessere-api --format '{{.State.Status}}')" = running ] ||
  fail "Ricevitore Android non operativo: non continuare."
[ "$(docker inspect benessere-api-v2 --format '{{.State.Status}}')" = running ] ||
  fail "API dati PWA non operativa: non continuare."

msg "Verifica revisione sorgenti"
git -C "$SOURCE" fetch --no-tags origin \
  "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
git -C "$SOURCE" cat-file -e "$REV^{commit}" ||
  fail "Commit PWA non disponibile."
OLD_STAGE=$(git -C "$STAGE" rev-parse HEAD)

msg "Salvataggio immagini precedenti per rollback"
docker tag benessere-pwa-preview:preview "$OLD_PWA"
docker tag benessere-api-v2:preview "$OLD_API"
ARMED=1
trap rollback EXIT

msg "Caricamento immagini GitHub verificate"
docker load -i "$ARCHIVE"
for image in benessere-api-v2:preview benessere-pwa-preview:preview; do
  image_rev=$(docker image inspect --format \
    '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")
  [ "$image_rev" = "$REV" ] ||
    fail "Immagine $image incompatibile: $image_rev (prevista $REV)."
done

# The archive also retags FastAPI. Restore its old tag, do NOT restart it.
docker tag "$OLD_API" benessere-api-v2:preview

msg "Aggiornamento sola webapp (backend e ricevitore invariati)"
git -C "$STAGE" checkout --detach "$REV"
docker compose -p benessere-v2 -f "$COMPOSE" config --quiet
docker compose -p benessere-v2 -f "$COMPOSE" up -d \
  --no-deps --no-build --pull never --force-recreate benessere-dashboard

msg "Controllo dashboard, dati storici e FC live senza campioni sintetici"
success=0
for n in $(seq 1 45); do
  if docker exec benessere-dashboard node -e '
    const guard=new AbortController();
    const timer=setTimeout(()=>guard.abort(),3500);
    Promise.all(["/api/summary","/api/live-heart-rate"].map(async path=>{
      const response=await fetch("http://127.0.0.1:8501"+path,{
        cache:"no-store",signal:guard.signal
      });
      if(!response.ok)throw Error(path+": HTTP "+response.status);
      const data=await response.json();
      if(path==="/api/live-heart-rate" &&
        data.status!=="live"&&data.status!=="offline"){
        throw Error("Risposta FC live non valida");
      }
    })).then(()=>console.log("PWA overview + FC live: OK"))
       .catch(e=>{console.error(e.message);process.exitCode=1;})
       .finally(()=>clearTimeout(timer));
  ' >/dev/null 2>&1; then
    success=1
    break
  fi
  sleep 2
done
[ "$success" -eq 1 ] || fail "Dashboard non pronta dopo 90 secondi."
backend_status=$(curl --max-time 7 -sS -o /dev/null -w '%{http_code}' \
  https://benessere.45-77-66-215.nip.io/health)
[ "$backend_status" = 200 ] || fail "Ricevitore Android non più raggiungibile."
api_status=$(curl --max-time 7 -sS -o /dev/null -w '%{http_code}' \
  -X POST -H 'Content-Type: application/json' \
  https://benessere.45-77-66-215.nip.io/api/v1/live-heart-rate)
[ "$api_status" = 401 ] ||
  fail "Ricevitore live non risponde più con 401 senza token."

ARMED=0
trap - EXIT
msg "SUCCESSO: riquadri web aggiornati ogni 30 secondi; Bluetooth invariato"
msg "Il riquadro FC mostra la lettura diretta soltanto quando arrivano nuovi campioni."
