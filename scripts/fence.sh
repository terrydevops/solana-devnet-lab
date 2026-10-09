#!/usr/bin/env bash
# Fence a host from outside: it keeps running but can no longer reach anybody.
#
#   scripts/fence.sh validator2          # cut it off
#   scripts/fence.sh --lift validator2   # reconnect it, only if it no longer holds the staked identity
#
# In this lab the "switch port" is the Docker network, and `docker exec` plays the part of the
# out-of-band console: it still works on a fenced host. On real hardware the equivalents are a
# port shut on the switch or a power-off through the BMC, and the console of the BMC.
#
# A fenced host that believed it was the primary still believes it. Lifting the fence while it
# holds the staked identity would put two machines on one identity, so --lift refuses until the
# host runs its unstaked key and its identity.json link says the same.
set -euo pipefail
net=solhosts_solnet
lift=0
[ "${1:-}" = "--lift" ] && { lift=1; shift; }
host=${1:?usage: fence.sh [--lift] <host>}
c="sol-$host"

if [ "$lift" -eq 0 ]; then
  docker network disconnect "$net" "$c"
  echo "$host is fenced: disconnected from $net, still running"
  exit 0
fi

staked=$(docker exec -u sol "$c" solana-keygen pubkey /home/sol/keys/staked-identity.json 2>/dev/null || echo none)
link=$(docker exec "$c" readlink /home/sol/keys/identity.json 2>/dev/null || echo unknown)
runs=$(docker exec -u sol "$c" agave-validator --ledger /mnt/ledger contact-info 2>/dev/null | awk '/^Identity:/ {print $2}')
if [ "$runs" = "$staked" ] || [[ "$link" != *unstaked-identity.json ]]; then
  echo "REFUSED: $host still holds the staked identity (runs ${runs:-nothing}, link -> $link)."
  echo "On its console: agave-validator --ledger /mnt/ledger set-identity /home/sol/keys/unstaked-identity.json"
  echo "                ln -sfn /home/sol/keys/unstaked-identity.json /home/sol/keys/identity.json"
  exit 1
fi
ip=$(cd "$(dirname "$0")/../ansible" && ansible-inventory --host "$host" 2>/dev/null </dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["node_ip"])')
docker network connect --ip "$ip" "$net" "$c"
echo "$host is back on $net at $ip, as a standby"
