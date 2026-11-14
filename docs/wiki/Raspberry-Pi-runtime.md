# Raspberry Pi runtime

## The product

The collector has to run somewhere. Grafana Cloud does not care whether that host is a container or a systemd unit. The host's limits do. A small machine decides the shape of the collector: which components fit, where the binary is built, and how an upgrade rolls back. [Fleet Management](https://grafana.com/docs/grafana-cloud/send-data/fleet-management/), [metrics](https://grafana.com/docs/grafana-cloud/send-data/metrics/), and [logs](https://grafana.com/docs/grafana-cloud/send-data/logs/) are the same products either way. The runtime is the constraint you design for.

## This stack

The live collector is a Raspberry Pi Model B+ Rev 1.2, armv6, 427 MB of RAM, Raspberry Pi OS Legacy 32-bit Lite. No Docker. [deploy/pi/](https://github.com/lewismc/solaredge-olly/tree/main/deploy/pi) holds the units, a non-secret env example, and the layout. `solaredge-exporter`, `solaredge-geolocate`, and `alloy` are enabled for `multi-user.target` and start at every boot. The simulator unit is enabled only while proving the path, then disabled, so a later boot does not open a second Modbus listener. Everything listens on localhost.

| Unit | Listens | MemoryMax |
| :--- | :--- | :--- |
| `solaredge-exporter.service` | `127.0.0.1:2112` | 64M |
| `solaredge-geolocate.service` | `127.0.0.1:9110` | 64M |
| `alloy.service` | `127.0.0.1:12345` | 220M |
| `synthetic-monitoring-agent.service` | `127.0.0.1:4050` | 96M |
| `node-exporter.service` | `127.0.0.1:9100` | 32M |

`solaredge-unit-memory.timer` writes each unit's cgroup memory for node_exporter every 30 seconds. See [Host metrics](https://github.com/lewismc/solaredge-olly/wiki/Host-metrics).

Alloy sits near 201 to 207 MB RSS against that 220 MB cap. Only about 40 MB of that is anonymous memory. The rest is file-backed pages of the 363 MB binary, which the kernel reclaims at the cap. The memory controller has to be on the kernel command line (`cgroup_enable=memory cgroup_memory=1`) before `MemoryMax` applies. Confirm `memory` is listed in `/sys/fs/cgroup/cgroup.controllers`.

No binary is built on the Pi. [`.github/workflows/alloy-armv6-build.yml`](https://github.com/lewismc/solaredge-olly/blob/main/.github/workflows/alloy-armv6-build.yml) cross-compiles Alloy and the exporter for `GOARCH=arm GOARM=6`, fetches the pinned upstream node_exporter `linux-armv6` build and checks its sha256, smoke-tests the binaries under qemu, and publishes a GitHub Release. [`.github/workflows/alloy-version-watch.yml`](https://github.com/lewismc/solaredge-olly/blob/main/.github/workflows/alloy-version-watch.yml) opens a pull request when a newer stable Alloy tag exists. The build has to pass before that pin is merged. Alloy carries one patch, [alloy/patches/](https://github.com/lewismc/solaredge-olly/tree/main/alloy/patches), for an armv6 alignment fault.

`solaredge-update.timer` runs [deploy/pi/update.sh](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/update.sh) once a day. It downloads the latest release, checks `SHA256SUMS`, points the symlinks at `releases/<tag>/`, and restarts Alloy. The exporter and node_exporter restart only when their binary changed. For five minutes Alloy must stay active, stay ready on `127.0.0.1:12345`, stay under 220 MB RSS, and log no panic, and node_exporter must stay active. A failure puts the previous release back. The env file is not part of a release. The older units are not copied over the live units, so a release does not switch Alloy off its config. `node-exporter.service` and the unit-memory timer are the exception: `update.sh` installs them from the release bundle and keeps them current. The script does not update itself. After a change to `update.sh`, install it once by hand (`sudo install -m 0755 deploy/pi/update.sh /opt/solaredge/bin/solaredge-update`).

`SHA256SUMS` comes from the same release, so it catches a corrupt download and not a forged one. Each release built on `main` also has a GitHub build-provenance attestation. The Pi does not check it. `gh` and cosign are too large for this host. Check a release from another machine:

```bash
gh release download <tag> -R lewismc/solaredge-olly -D /tmp/rel
gh attestation verify /tmp/rel/alloy-linux-armv6 -R lewismc/solaredge-olly
gh attestation verify /tmp/rel/solaredge-exporter-linux-armv6 -R lewismc/solaredge-olly
gh attestation verify /tmp/rel/node_exporter-linux-armv6 -R lewismc/solaredge-olly
gh attestation verify /tmp/rel/solaredge-bundle.tar.gz -R lewismc/solaredge-olly
```

The probe binary and k6 are installed by hand. A release does not ship them.

Compose remains the simulator and development path, on a Mac or a Linux host. It is not the live runtime.

## Reuse on a customer system

Measure the host before you add a component. A collector at 90% of its memory cap cannot grow an OpenTelemetry receiver later. Build where the CPU is, and ship a verified artifact. A health window plus an automatic rollback is the upgrade process. A checksum from the same release is not a signature. Put the signature check on a machine that can run it. Cap each unit, and keep the second copy of a singleton (a device session, a collector id) from starting on boot.
