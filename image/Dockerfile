# Agave built from source for linux/arm64.
#
# Why this exists: Anza publishes Linux binaries and images for x86_64 only. On an Apple Silicon
# machine the x86_64 image runs under emulation, and the emulation layer does not implement
# io_uring, which Agave requires on Linux ("assertion failed: io_uring_supported()"). A native
# arm64 build runs on the Docker VM's own kernel, which has io_uring.
#
# Build:  docker build -t agave-arm64:v4.3.0 --build-arg AGAVE_TAG=v4.3.0 image/
ARG AGAVE_TAG=v4.3.0

FROM rust:1-bookworm AS build
ARG AGAVE_TAG
RUN apt-get update && apt-get install -y --no-install-recommends \
      libssl-dev libudev-dev pkg-config zlib1g-dev llvm clang cmake make \
      libprotobuf-dev protobuf-compiler libclang-dev git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${AGAVE_TAG}" https://github.com/anza-xyz/agave.git /agave
WORKDIR /agave
# rust-toolchain.toml in the repository pins the compiler; rustup installs it on first use.
# The binary list is the operator set from scripts/agave-build-lists.sh (AGAVE_BINS_VAL_OP) plus the
# CLI and keygen. agave-ledger-tool is not in the main workspace at this tag (it lives in dev-bins).
RUN --mount=type=cache,target=/agave/target \
    --mount=type=cache,target=/usr/local/cargo/registry \
    cargo build --release --locked \
      --bin agave-validator --bin agave-watchtower --bin solana-gossip \
      --bin solana-genesis --bin solana-faucet --bin solana --bin solana-keygen \
    && mkdir -p /out \
    && for b in agave-validator agave-watchtower solana-gossip solana-genesis \
                solana-faucet solana solana-keygen; do \
         cp "target/release/$b" /out/; \
       done \
    && cp fetch-core-bpf.sh fetch-programs.sh fetch-spl.sh /out/

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates libssl3 libudev1 bzip2 curl jq procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/ /usr/local/bin/
ENTRYPOINT ["agave-validator"]
