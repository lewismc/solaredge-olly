# Build https://github.com/dave92082/SolarEdge-Exporter from a pinned commit (MIT).
# Tag 1.2.1: https://github.com/dave92082/SolarEdge-Exporter/releases/tag/1.2.1
# Pin: https://github.com/dave92082/SolarEdge-Exporter/commit/42d4790b78f76a5fae9e931cf78a76dbda0ccb53
# Upstream publishes release binaries, not a container image. This image builds that commit.
# Do not use unofficial Docker Hub images.
ARG EXPORTER_GIT_SHA=42d4790b78f76a5fae9e931cf78a76dbda0ccb53

FROM golang:1.26-alpine AS build
ARG EXPORTER_GIT_SHA
RUN apk add --no-cache git
WORKDIR /src
COPY inverter-info.patch /tmp/inverter-info.patch
COPY modbus-read-ok.patch /tmp/modbus-read-ok.patch
COPY modbus-read-errors.patch /tmp/modbus-read-errors.patch
RUN git clone https://github.com/dave92082/SolarEdge-Exporter.git . \
    && git checkout "${EXPORTER_GIT_SHA}" \
    && git apply /tmp/inverter-info.patch \
    && git apply /tmp/modbus-read-ok.patch \
    && git apply /tmp/modbus-read-errors.patch
RUN CGO_ENABLED=0 go build -o solaredge-exporter .

FROM alpine:3.22
RUN apk add --no-cache bash su-exec && adduser -D solaredge
WORKDIR /home/solaredge
COPY --from=build /src/solaredge-exporter .
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
USER root
ENTRYPOINT ["/entrypoint.sh"]
EXPOSE 2112
CMD ["./solaredge-exporter"]
