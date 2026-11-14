# Host metrics

## The product

A Grafana Cloud [integration](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/) is a bundle: an Alloy snippet that sets the job label, plus dashboards, alert rules, and recording rules that select on that label. The [Raspberry Pi integration](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/integration-reference/integration-raspberry-pi-node/) is built on [node-observ-lib](https://github.com/grafana/node_exporter/tree/master/docs/node-mixin/lib/linux), the same library as the Linux node integration. It expects node_exporter metrics under `job="integrations/raspberrypi-node"`, with `instance` set to the host. Whoever produces those series, the integration's content works. Installing it is a click under **Connections**. There is no API for that step.

## This stack

**node_exporter is its own unit, not an Alloy component.** The integration's snippet uses `prometheus.exporter.unix`, which would run node_exporter inside Alloy. Alloy already sits near its 220 MB cap, so node_exporter runs as `node-exporter.service` with `MemoryMax=32M`, and Alloy only scrapes it. Measured on the Pi: 18 MB RSS (4 MB anonymous), 235 series before the keep-list, and a scrape of about 0.55 s.

The binary is the upstream `linux-armv6` release, pinned in [node_exporter/VERSION](https://github.com/lewismc/solaredge-olly/blob/main/node_exporter/VERSION). The [armv6 release workflow](https://github.com/lewismc/solaredge-olly/blob/main/.github/workflows/alloy-armv6-build.yml) checks it against upstream's `sha256sums.txt`, runs it under qemu, and ships it as `node_exporter-linux-armv6` next to Alloy, covered by `SHA256SUMS` and the build attestation. [update.sh](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/update.sh) installs it like the other binaries, and creates the `node-exporter` user and unit the first time.

**Collectors are the ones the integration reads.** [node-exporter.service](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/node-exporter.service) disables the defaults and enables `cpu`, `diskstats`, `filesystem`, `hwmon`, `loadavg`, `meminfo`, `netdev`, `os`, `stat`, `systemd`, `textfile`, `thermal_zone`, `uname`, and `vmstat`. The systemd collector is limited to this stack's units plus `ssh`. Disk stats are limited to the SD card (`mmcblk0`). The SoC temperature arrives twice: `node_hwmon_temp_celsius{chip="thermal_thermal_zone0"}`, which the integration uses, and `node_thermal_zone_temp{type="cpu-thermal"}`.

The scrape is in [fleet/solaredge.alloy](https://github.com/lewismc/solaredge-olly/blob/main/fleet/solaredge.alloy), every 60 seconds:

```alloy
prometheus.scrape "node" {
	targets = [{
		__address__ = "127.0.0.1:9100",
		instance    = constants.hostname,
	}]
	forward_to      = [prometheus.relabel.node.receiver]
	job_name        = "integrations/raspberrypi-node"
	scrape_interval = "60s"
}
```

The keep-list is `up`, `node_*`, and `solaredge_unit_*`. Collector timings and three filesystem families nobody reads are dropped. The integration's journal and syslog snippets are not used. A `loki.source.journal` would add memory to Alloy for logs that the exporter's own stream already covers.

**Memory against each unit's cap.** node_exporter does not read systemd cgroups. [unit-memory.sh](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/unit-memory.sh) runs every 30 seconds from `solaredge-unit-memory.timer` and writes `/var/lib/node_exporter/textfile/unit-memory.prom`:

| Series | From |
| :--- | :--- |
| `solaredge_unit_memory_bytes{unit, kind="current"}` | `memory.current` |
| `solaredge_unit_memory_bytes{unit, kind="anon"}` / `{kind="file"}` | `memory.stat` |
| `solaredge_unit_memory_bytes{unit, kind="swap"}` | `memory.swap.current` |
| `solaredge_unit_memory_max_bytes{unit}` | `memory.max` (`MemoryMax=`) |
| `solaredge_unit_memory_events_total{unit, event="max"\|"oom_kill"}` | `memory.events` |

This split changed how Alloy's number reads. Alloy's 201 MB RSS was 40 MB anonymous and 173 MB file-backed. Most of it is pages of the 363 MB Alloy binary, which the kernel drops and reloads at `memory.max`. `event="max"` had counted 13 reclaims at the cap and no OOM kill. So the alerts read `anon`, not RSS. This kernel has no PSI (`memory.pressure`), so there is no stall metric.

Two rules in [alerting/](https://github.com/lewismc/solaredge-olly/tree/main/alerting) use these series and route to Slack like the others: [unit memory near MemoryMax](https://github.com/lewismc/solaredge-olly/blob/main/alerting/solaredge-unit-memory.yaml) (anon above 80% of the cap for 15 minutes) and [unit OOM kill](https://github.com/lewismc/solaredge-olly/blob/main/alerting/solaredge-unit-oom.yaml) (any `oom_kill` increase in 15 minutes). The integration's own alerts cover SoC temperature (`NodeHardwareTemperatureHigh`), the SD-card filesystem (`NodeFilesystemAlmostOutOfSpace`), host memory, and failed systemd units.

## Reuse on a customer system

Match the integration's job label, and its content works no matter what runs the exporter. On a small or shared host, run the exporter as its own capped process instead of inside the collector, so a host-metrics problem cannot take down the pipeline. Enable only the collectors the dashboards read, and cut the systemd and disk collectors to the units and devices you own. When a process sits near its memory cap, split anonymous from file-backed memory before calling it a leak. A large binary's pages count as RSS and are reclaimable.
