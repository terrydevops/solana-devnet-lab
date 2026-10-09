#!/usr/bin/env bash
# Move the staked identity from one host to another and show each step as it happens.
#
#   scripts/failover.sh validator2 spare
#   scripts/failover.sh spare validator2 -e min_idle_slots=40
#
# The full Ansible output goes to run/failover-<time>.log; the terminal gets the step log.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: $0 <from-host> <to-host> [ansible-playbook options]"; exit 2; }
from=$1; to=$2; shift 2
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$root/run"
log="$root/run/failover-$(date +%Y%m%d-%H%M%S).log"

echo "$(date +%H:%M:%S)  identity switch: $from -> $to   (full output: ${log#"$root"/})"
cd "$root/ansible"
set +e
ANSIBLE_FORCE_COLOR=0 ANSIBLE_NOCOLOR=1 PYTHONUNBUFFERED=1 \
  ansible-playbook failover.yml -e "from=$from" -e "to=$to" "$@" </dev/null 2>&1 \
  | tee "$log" | python3 -u "$root/scripts/failover-log.py"
rc=${PIPESTATUS[0]}
set -e
echo
if [ "$rc" -eq 0 ]; then echo "$(date +%H:%M:%S)  done"; else echo "$(date +%H:%M:%S)  FAILED (exit $rc), see ${log#"$root"/}"; fi
exit "$rc"
