#!/usr/bin/env bash
# Restore Streamlit UI without restoring SQLite: avoids losing any new records
# created since switching to the PWA. All other Benessere services are untouched.
set -Eeuo pipefail
[ "$(id -u)" = 0 ] || { echo "Devi essere root" >&2; exit 1; }
ROOT=/opt/benessere
KEY="$ROOT/private/legacy-dashboard-name.txt"
[ -s "$KEY" ] || { echo "Nessuna dashboard legacy registrata" >&2; exit 1; }
NAME=$(cat "$KEY")
case "$NAME" in benessere-dashboard-legacy-*) ;; *) echo "Nome legacy inatteso";exit 1;; esac
docker inspect "$NAME" >/dev/null || { echo "Vecchio container non disponibile";exit 1; }
COMPOSE="$ROOT/preview-source/webapp/compose.production.yml"
docker compose -p benessere-v2 -f "$COMPOSE" down
if docker inspect benessere-dashboard >/dev/null 2>&1; then
  echo "Conflitto: benessere-dashboard esiste ancora" >&2
  exit 1
fi
docker rename "$NAME" benessere-dashboard
docker update --restart=unless-stopped benessere-dashboard >/dev/null
docker start benessere-dashboard >/dev/null
echo "Streamlit ripristinato sull'URL precedente."
echo "Il database NON è stato ripristinato a una copia vecchia: le registrazioni recenti sono preservate."
echo "Il backup precedente allo switch rimane nel percorso indicato da $ROOT/private/last-pwa-backup.txt"
