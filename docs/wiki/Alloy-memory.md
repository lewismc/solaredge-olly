# Alloy memory

## The product

[Grafana Alloy](https://grafana.com/docs/alloy/latest/) is one binary that links every component it was compiled with. On a small host the binary's pages show up in RSS. Those pages are file-backed: the kernel drops them and reads them back. Anonymous memory is the Go heap and stacks. `MemoryMax=` caps that anonymous memory. [`GOMEMLIMIT`](https://pkg.go.dev/runtime) is a soft cap on the Go heap. It does not shrink the file-backed pages.

Grafana documents a [custom OpenTelemetry Collector build](https://grafana.com/docs/alloy/latest/set-up/otel_engine/custom-builds/) that adds or removes OTel components. That build still links every native Alloy component. There is no supported allowlist for the native components in `v1.21.2`.

## This stack

Alloy runs as `alloy.service` with `MemoryMax=220M` on the Pi. A 24-hour read of `solaredge_unit_memory_bytes{unit="alloy.service"}` peaked at 46 MB anonymous, 177 MB file-backed, and 212 MB current. The live binary, release `v1.21.2-b592b56`, is 346 MB. The Go heap in use on `instance="solaredge"` peaked at 49 MB, and `go_memstats_sys_bytes` was about 60 MB. An RSS alert at 90% of the cap would fire for most of the day, because the file-backed pages cross that line whenever the binary is faulted in. The existing rule stays at 80% of anonymous memory over `MemoryMax`.

The self-scrape stays. `prometheus.exporter.self` in [fleet/solaredge.alloy](https://github.com/lewismc/solaredge-olly/blob/main/fleet/solaredge.alloy), plus Fleet Management's generated `self_monitoring_metrics` pipeline, is how you check that an Alloy upgrade landed: `alloy_build_info`, `up`, and the process and Go series under `job="integrations/alloy"`. The Knowledge Graph Collector entity and `CollectorScrapeDown` read those series too.

`GOMEMLIMIT=80MiB` is set on the live process through `/etc/solaredge/solaredge.env`, which the unit loads with `EnvironmentFile=`. [deploy/pi/alloy.service](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/alloy.service) and [deploy/pi/solaredge.env.example](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/solaredge.env.example) carry the same variable. `update.sh` does not replace `alloy.service`, so a release does not put the variable on the Pi by itself. After the restart the unit stayed ready, with no panic. Anonymous memory was 40 MB. RSS climbed back toward the previous range as the binary's pages were read in. That is the expected shape, so the limit stayed.

The armv6 workflow applies [alloy/patches/component-allowlist.patch](https://github.com/lewismc/solaredge-olly/blob/main/alloy/patches/component-allowlist.patch) on top of the fanout alignment patch. The patch does two things. It replaces `internal/component/all` with the components the collector actually loads, taken from the bootstrap, the Fleet Management cache, and the generated pipelines:

- `discovery.relabel`
- `local.file_match`
- `loki.process`, `loki.source.file`, `loki.source.journal`, `loki.write`
- `prometheus.exporter.self`, `prometheus.relabel`, `prometheus.remote_write`, `prometheus.scrape`

`remotecfg` and `import.file` are part of the Alloy runtime, not rows in that file. It also replaces the generated OTel factory list with an empty one. The Pi runs `alloy run`. Phase 2 sends traces from geolocate straight to the OTLP gateway, so this binary does not need `alloy otel`. The OpAMP supervisor command is still linked.

A local `linux/arm/v6` build of that patch is 302 MB. The live binary is 346 MB. Dropping the unused OpAMP supervisor command as well saved under 1 MB, so the patch leaves it. The new binary is not on the Pi. It ships when the armv6 workflow publishes a release and `solaredge-update.timer` installs it. The health check in [update.sh](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/update.sh) rolls back if RSS, including file-backed pages, stays above 220 MB during the five-minute window.

## Reuse on a customer system

Split anonymous memory from file-backed RSS before you alert on a collector. Alerting on RSS of a large binary pages the file cache, not a leak. Set `GOMEMLIMIT` above the measured heap and below the cgroup cap, and keep the self-metrics you use to prove an upgrade. A component allowlist on Alloy `v1.21.2` is a local patch. Inventory every block the remote config loads, including generated pipelines, or the collector rejects the config. Ship the binary through the same checksummed release path as the full build. Do not copy it onto the host by hand.
