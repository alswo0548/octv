#!/usr/bin/env bash
# Non-destructive PostgreSQL logical backup; never runs pg_restore on production.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_dir="${OCTV_BACKUP_DIR:-/srv/octv-backups}"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
output="$backup_dir/octv_$(date -u +%Y%m%dT%H%M%SZ).dump"
temporary="$output.partial"
trap 'rm -f "$temporary"' EXIT
# Loaded environment stays inside Docker; no DB password in command line.
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml \
  exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary"
test -s "$temporary"
docker compose --env-file /etc/octv/production.env -f deploy/compose.prod.yaml \
  exec -T db pg_restore --list < "$temporary" > /dev/null
chmod 600 "$temporary"
mv "$temporary" "$output"
trap - EXIT
sha256sum "$output" > "$output.sha256"
echo "Backup created: $output"
echo "IMPORTANT: Copy DB+model+video backups off-server and TEST restore separately."
