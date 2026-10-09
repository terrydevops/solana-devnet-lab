#!/usr/bin/env bash
# List every container image the compose files use.
#   --json    matrix for the image scan
#   --check   fail on an unpinned or floating tag
set -euo pipefail
cd "$(dirname "$0")/../.."

images() {
  find . -path ./.git -prune -o \( -name 'docker-compose*.yml' -o -name 'compose*.yml' \) -print0 \
    | xargs -0 grep -hE '^[[:space:]]*image:' \
    | sed -E 's/^[[:space:]]*image:[[:space:]]*//; s/^"//; s/"[[:space:]]*$//; s/[[:space:]]*#.*$//' \
    | sed -E 's/\$\{[A-Z_]+:-([^}]*)\}/\1/g' \
    | grep -v '^$' | sort -u
}

check() {
  local bad=0 img tag
  while read -r img; do
    [[ "$img" == *'${'* ]] && { echo "UNRESOLVED variable: $img"; bad=1; continue; }
    [[ "$img" =~ @sha256:[0-9a-f]{64}$ ]] && continue
    tag=${img##*:}
    if [[ "$img" != *:* || "$tag" == */* ]]; then echo "UNPINNED (no tag): $img"; bad=1; continue; fi
    case "$tag" in
      latest|stable|main|master|edge|nightly|dev) echo "FLOATING tag: $img"; bad=1 ;;
    esac
    [[ "$tag" =~ ^v?[0-9]+$ ]] && { echo "FLOATING (major-only tag): $img"; bad=1; }
  done
  return "$bad"
}

case "${1:-}" in
  --json)  images | python3 -c 'import sys,json; print(json.dumps([l for l in sys.stdin.read().split("\n") if l]))' ;;
  --check) images | check && echo "all $(images | wc -l | tr -d ' ') image references pinned" ;;
  *)       images ;;
esac
