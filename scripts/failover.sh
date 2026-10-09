#!/usr/bin/env bash
# Move the staked identity to the other host of the failover pair, showing each step.
#
#   scripts/failover.sh              # find out which host is active, switch to the other one
#   scripts/failover.sh --check      # only show where the pair stands; change nothing
#   scripts/failover.sh validator2 spare        # name both hosts yourself
#   scripts/failover.sh -e min_idle_slots=40    # anything else goes to ansible-playbook
#
# Without host names the script asks both hosts which identity they run. It switches only when
# exactly one of them holds the staked identity and the other is running and caught up; in every
# other case it says what it found and stops. Starting it is the decision; it does not decide.
#
# The full Ansible output goes to run/failover-<time>.log; the terminal gets the step log.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
max_behind=20
check=0
hosts=()
opts=()
while [ $# -gt 0 ]; do
  case "$1" in
    --check) check=1 ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) opts+=("$1"); [ $# -gt 1 ] && { opts+=("$2"); shift; } ;;
    *) hosts+=("$1") ;;
  esac
  shift
done

cd "$root/ansible"
if [ ${#hosts[@]} -eq 2 ]; then
  from=${hosts[0]}; to=${hosts[1]}
elif [ ${#hosts[@]} -eq 0 ]; then
  status=$(ANSIBLE_FORCE_COLOR=0 ANSIBLE_NOCOLOR=1 ansible-playbook pair-status.yml </dev/null 2>&1 | grep -o 'PAIR host=[^"]*' || true)
  [ -n "$status" ] || { echo "could not read the state of the pair (are the hosts up?)"; exit 1; }
  active=(); standby=(); notes=()
  while read -r _ h s r b v; do
    host=${h#host=}; staked=${s#staked=}; runs=${r#runs=}; behind=${b#behind=}; service=${v#service=}
    if [ "$runs" = "$staked" ] && [ "$staked" != none ]; then
      active+=("$host"); role="ACTIVE   runs the staked identity"
    else
      standby+=("$host"); role="standby  runs ${runs:0:8}..."
      if [ "$service" != active ]; then notes+=("$host: validator service is $service")
      elif [ "$behind" = unknown ]; then notes+=("$host: cannot tell how far behind it is")
      elif [ "$behind" -gt "$max_behind" ]; then notes+=("$host: $behind slots behind (limit $max_behind)")
      fi
    fi
    printf '  %-12s %s, %s slots behind, service %s\n' "$host" "$role" "$behind" "$service"
  done <<< "$status"
  if [ ${#active[@]} -eq 2 ]; then echo "STOP: both hosts run the staked identity. That is double voting: fix it by hand, now."; exit 1; fi
  if [ ${#active[@]} -eq 0 ]; then echo "STOP: neither host runs the staked identity. Nobody is voting for it; decide by hand which host takes it."; exit 1; fi
  [ ${#standby[@]} -eq 1 ] || { echo "STOP: expected one standby host, found ${#standby[@]}."; exit 1; }
  from=${active[0]}; to=${standby[0]}
  if [ ${#notes[@]} -gt 0 ]; then printf 'NOT READY: %s\n' "${notes[@]}"; [ "$check" -eq 1 ] && exit 1; echo "not switching."; exit 1; fi
  echo "  the standby is ready: a switch would go $from -> $to"
  [ "$check" -eq 1 ] && exit 0
else
  echo "give both hosts or none: $0 [--check] [<from> <to>] [ansible-playbook options]"; exit 2
fi
[ "$check" -eq 1 ] && { echo "--check works without host names"; exit 2; }

mkdir -p "$root/run"
log="$root/run/failover-$(date +%Y%m%d-%H%M%S).log"
echo "$(date +%H:%M:%S)  identity switch: $from -> $to   (full output: ${log#"$root"/})"
set +e
ANSIBLE_FORCE_COLOR=0 ANSIBLE_NOCOLOR=1 PYTHONUNBUFFERED=1 \
  ansible-playbook failover.yml -e "from=$from" -e "to=$to" ${opts[@]+"${opts[@]}"} </dev/null 2>&1 \
  | tee "$log" | python3 -u "$root/scripts/failover-log.py"
rc=${PIPESTATUS[0]}
set -e
echo
if [ "$rc" -eq 0 ]; then echo "$(date +%H:%M:%S)  done"; else echo "$(date +%H:%M:%S)  FAILED (exit $rc), see ${log#"$root"/}"; fi
exit "$rc"
