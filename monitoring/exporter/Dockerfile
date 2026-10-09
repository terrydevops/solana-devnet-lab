# Community Solana exporter (asymmetric-research/solana-exporter), built from a release tag.
# The project publishes no binaries, so it is built here. Native build: works on arm64 and amd64.
FROM golang:1-alpine AS build
ARG EXPORTER_VERSION=v3.1.0
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${EXPORTER_VERSION}" \
      https://github.com/asymmetric-research/solana-exporter.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -o /solana-exporter ./cmd/solana-exporter

FROM alpine:3
COPY --from=build /solana-exporter /usr/local/bin/solana-exporter
USER nobody
EXPOSE 8080
ENTRYPOINT ["solana-exporter"]
