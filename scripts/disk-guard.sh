#!/usr/bin/env bash
# Lab safety net: stop the validators before the shared Docker disk is full.
#
# The ledger of this cluster grows by several GB per hour and --limit-blockstore-size cannot go
# low enough to cap it (docs/lab-notes.md, incident 2026-10-08). Until the host disk alert exists, this loop
# does the one thing a person would do: stop the services while there is still room to work.
#
#   scripts/disk-guard.sh &          # stops the cluster when free space drops under 15 GB
#   MIN_FREE_GB=25 scripts/disk-guard.sh
set -euo pipefail

MIN_FREE_GB="${MIN_FREE_GB:-15}"
INTERVAL="${INTERVAL:-60}"
HOSTS=(sol-bootstrap sol-validator2 sol-rpc sol-spare)

while true; do
  free_gb=$(docker exec sol-rpc df -BG --output=avail /mnt/ledger | tail -1 | tr -dc '0-9')
  if [ "${free_gb}" -lt "${MIN_FREE_GB}" ]; then
    echo "$(date -u +%FT%TZ) free space ${free_gb} GB is under ${MIN_FREE_GB} GB: stopping the validators"
    for h in "${HOSTS[@]}"; do
      docker exec "$h" systemctl stop sol 2>/dev/null || true
    done
    exit 0
  fi
  sleep "${INTERVAL}"
done
