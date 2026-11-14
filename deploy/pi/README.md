# Raspberry Pi

The collector runs as ordinary processes under systemd. Docker is not required and is not installed for this stack.

| Unit | Listens | MemoryMax | Boot |
| :--- | :--- | :--- | :--- |
| `sunspec-sim.service` | `127.0.0.1:502` | 64M | Enabled only while proving the simulator path |
| `solaredge-exporter.service` | `127.0.0.1:2112` | 64M | Enabled |
| `solaredge-geolocate.service` | `127.0.0.1:9110` | 64M | Enabled |
| `alloy.service` | `127.0.0.1:12345` | 220M | Enabled |
| `synthetic-monitoring-agent.service` | `127.0.0.1:4050` | 96M | Enabled. Installed by hand; a release does not ship the probe or k6 |

`solaredge-exporter`, `solaredge-geolocate`, and `alloy` are installed into `multi-user.target`, so they start at every boot and wait for `network-online.target`. `sunspec-sim` is enabled during the simulator phase and disabled at cutover, so a later boot does not open a second Modbus listener.

## Layout

- Binaries: `/opt/solaredge/bin/solaredge-exporter`, `/opt/solaredge/bin/alloy`
- Python: `/opt/solaredge/sim/` and `/opt/solaredge/geolocate/`, each with its own venv
- Environment: `/etc/solaredge/solaredge.env` (root:root, mode 0600). Start from [`solaredge.env.example`](solaredge.env.example). Grafana tokens stay in this file. Do not commit it.
- Alloy config: `/etc/alloy/config.alloy`, `/etc/alloy/solaredge.alloy`, `/etc/alloy/module/metrics.alloy`
- State: `/var/log/solaredge`, `/var/lib/geolocate`, `/var/lib/alloy/data`
- `/etc/hosts` maps `solaredge-exporter` and `solaredge-geolocate` to `127.0.0.1`, so [`fleet/solaredge.alloy`](../../fleet/solaredge.alloy) resolves unchanged

The simulator phase runs `/etc/alloy/solaredge.alloy` directly. After the scrape works, `alloy.service` switches to `/etc/alloy/config.alloy` and Fleet Management delivers the pipeline. Credentials come from the environment, the same names Compose uses. `GCLOUD_RW_API_KEY` is the Prometheus token.

`SIM_LISTEN_ADDR` and `GEOLOCATE_LISTEN_ADDR` default to `0.0.0.0` when unset, so Compose is unchanged. The Pi env file sets both to `127.0.0.1`.

The exporter binary is the pinned commit `42d4790b78f76a5fae9e931cf78a76dbda0ccb53` with the three patches in [`exporter/`](../../exporter/), cross-compiled with `CGO_ENABLED=0 GOOS=linux GOARCH=arm GOARM=6`. The Alloy binary is the measured armv6 build. Neither is built on the Pi.

## Updates

`solaredge-update.timer` runs [`update.sh`](update.sh) once a day. The script downloads the latest public GitHub release, checks `SHA256SUMS`, points `/opt/solaredge/bin/alloy` and `/opt/solaredge/bin/solaredge-exporter` at `releases/<tag>/`, and restarts Alloy. The exporter restarts only when its binary changed. For five minutes the script requires Alloy to stay active, stay ready on `127.0.0.1:12345`, stay under 220 MB RSS, and log no panic. A failure puts the previous release back. `/etc/solaredge/solaredge.env` is not part of a release. The systemd units in this directory are not copied over the live units, so a release does not switch Alloy off `/etc/alloy/config.alloy`.

`SHA256SUMS` comes from the same release, so it catches a corrupt download and not a forged release. Each release built on `main` also has a GitHub build-provenance attestation for the three payloads. The Pi does not check it: `gh` and cosign are not installed, and either one is a large binary for a 427 MB host. Check a release from another machine before trusting it:

```bash
gh release download <tag> -R lewismc/solaredge-olly -D /tmp/rel
gh attestation verify /tmp/rel/alloy-linux-armv6 -R lewismc/solaredge-olly
gh attestation verify /tmp/rel/solaredge-exporter-linux-armv6 -R lewismc/solaredge-olly
gh attestation verify /tmp/rel/solaredge-bundle.tar.gz -R lewismc/solaredge-olly
```

The memory controller has to be on the kernel command line (`cgroup_enable=memory cgroup_memory=1` in `/boot/firmware/cmdline.txt`) before `MemoryMax` applies. Confirm `memory` is listed in `/sys/fs/cgroup/cgroup.controllers`.

One Modbus TCP client can hold the inverter. Stop and disable `sunspec-sim` before setting `INVERTER_ADDRESS` to the inverter, and do not point the exporter at the inverter while another logger is connected.
