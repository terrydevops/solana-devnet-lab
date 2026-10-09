#!/usr/bin/env bash
# Show alert notifications as they are delivered, and raise a desktop notification for each.
#
# The stack delivers alerts to a local sink that only logs them (monitoring/metrics/alertmanager/
# alert-sink.mjs); nothing reaches a person unless something reads that log. This does.
#
#   scripts/alerts-watch.sh            # from now on
#   scripts/alerts-watch.sh 30m        # replay the last 30 minutes first
#
# p1 notifications come with a sound. macOS only for the desktop part; the terminal output works
# anywhere.
set -euo pipefail
since=${1:-0s}

notify() { # priority, text
  command -v osascript >/dev/null || return 0
  local sound=""
  [ "$1" = "p1" ] && sound=' sound name "Sosumi"'
  osascript -e "display notification \"${2//\"/\'}\" with title \"Solana lab: $1\"$sound" >/dev/null 2>&1 || true
}

echo "watching alert deliveries (since $since); Ctrl-C to stop"
docker logs -f --since "$since" sol-alert-sink 2>&1 | while IFS= read -r line; do
  printf '%s  %s\n' "$(date +%H:%M:%S)" "$line"
  case "$line" in
    "[FIRING] p1 "*)   notify p1 "${line#"[FIRING] p1 "}" ;;
    "[FIRING] p2 "*)   notify p2 "${line#"[FIRING] p2 "}" ;;
    "[RESOLVED] p1 "*) notify p1 "resolved: ${line#"[RESOLVED] p1 "}" ;;
  esac
done
