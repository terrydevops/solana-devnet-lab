#!/usr/bin/env bash
# Build the community solana-exporter and put the binary where the Ansible role expects it.
# The project publishes no release binaries, so it is built from the tag in the Dockerfile.
set -euo pipefail
cd "$(dirname "$0")"
docker build -t solana-exporter:v3.1.0 .
cid=$(docker create solana-exporter:v3.1.0)
docker cp "$cid:/usr/local/bin/solana-exporter" ../../ansible/files/bin/solana-exporter
docker rm "$cid" >/dev/null
echo "wrote ansible/files/bin/solana-exporter"
