#!/usr/bin/env bash
# Read-only inventory: no prune, no database cleanup, no deletion.
set -euo pipefail
echo '== disk =='; df -h /
echo '== docker =='; docker system df
echo '== assets =='
for p in /srv/octv-assets/demo/videos /srv/octv-assets/models /srv/octv-backups; do
  if [ -e "$p" ]; then du -sh "$p"; else echo "MISSING $p"; fi
done
