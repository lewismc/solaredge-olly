# solaredge-olly

Docker Compose collector for SolarEdge inverters. A Prometheus exporter polls each inverter over Modbus TCP / SunSpec. Grafana Alloy scrapes that exporter and remote-writes the samples to Grafana Cloud. The same Alloy process tails the exporter's JSON log file and pushes it to Grafana Cloud Logs.

```text
inverter --Modbus TCP--> solaredge-exporter --scrape :2112--> Alloy --remote_write--> Grafana Cloud Metrics
                         solaredge-exporter --log file-----> Alloy --loki push--> Grafana Cloud Logs
solaredge-geolocate --scrape :9110--> Alloy --remote_write--> Grafana Cloud Metrics
```

The dashboard is [`dashboards/solaredge.json`](dashboards/solaredge.json). Alerts, optional Fleet Management, a private Synthetic Monitoring probe, two SLOs, and site geolocation with expected yield are in this repo.

## What runs

`docker compose up` starts four services on a bridge network:

| Service | Role |
| :--- | :--- |
| `solaredge-exporter` | [dave92082/SolarEdge-Exporter](https://github.com/dave92082/SolarEdge-Exporter) `1.2.1`, built from commit `42d4790b78f76a5fae9e931cf78a76dbda0ccb53`. Upstream ships release binaries, not a container image. |
| `alloy` | `grafana/alloy:v1.21.2`. Loads [`module/metrics.alloy`](module/metrics.alloy) with `import.file`, remote-writes metrics, and tails the exporter's JSON log file to Grafana Cloud Logs. |
| `synthetic-monitoring-agent` | `grafana/synthetic-monitoring-agent:v0.68.0`. Private probe. Reads `http://solaredge-exporter:2112/metrics` on the Compose network. |
| `solaredge-geolocate` | Site location and expected yield. Built from [`geolocate/`](geolocate/). Serves `:9110` on the Compose network. Calls Open-Meteo over HTTPS, and ipinfo.io unless `SITE_LAT` and `SITE_LON` are set. |

Profile `sim` adds `sunspec-sim`, a single fake inverter (SunSpec model 101, no meters) for a run that does not hold a live Modbus session.

The Docker host must be able to open TCP to every address in `INVERTER_ADDRESS`. The same Compose file runs on a Mac or a Linux host. Port `2112`, the simulator's port `502`, and the probe's listen port stay on the Compose network. Alloy's UI is published on `127.0.0.1:12345`.

## Before you begin

- Docker with Compose v2.20 or newer (`depends_on.required`)
- A Grafana Cloud stack and an access-policy token that can write metrics (`metrics:write`) and logs (`logs:write`)
- For a live inverter: SunSpec support, Modbus TCP enabled, and a LAN path from this Docker host (LCD default port **502**, SetApp default **1502**). The inverter this stack was checked against is recorded in [`docs/lan-inverter.md`](docs/lan-inverter.md).

One Modbus TCP client can hold an inverter session at a time. Stop Home Assistant or any other logger before this exporter connects. Cloud SolarEdge monitoring can stay enabled. It uses a different path.

## Configure

```bash
cp .env.example .env
```

Set `INVERTER_ADDRESS` to the inverter's LAN address. Several inverters are a comma-separated list, and an entry may carry its own port:

```text
INVERTER_ADDRESS=192.0.2.10,192.0.2.10:1502
```

`NUMBER_METERS` defaults to `0`. This SE3800 has no meter, and exporter 1.2.1 otherwise probes meter 1 and logs an illegal-data-address skip. Set `NUMBER_METERS` to `1`, `2`, or `3` when a meter is installed. `INVERTER_CLIENT_ID` defaults to `1`.

Grafana Cloud metrics:

- `GRAFANA_CLOUD_PROM_URL` is the Prometheus remote_write URL, ending in `/api/prom/push`
- `GRAFANA_CLOUD_PROM_USERNAME` is the stack's Prometheus instance id
- `GRAFANA_CLOUD_PROM_PASSWORD` is an access-policy token with `metrics:write`

Grafana Cloud logs. This is a different URL and instance id from the Prometheus triple:

- `GRAFANA_CLOUD_LOKI_URL` is the Loki push URL, ending in `/loki/api/v1/push`
- `GRAFANA_CLOUD_LOKI_USERNAME` is the stack's Loki instance id
- `GRAFANA_CLOUD_LOKI_PASSWORD` is an access-policy token with `logs:write`. It can be the same token as `GRAFANA_CLOUD_PROM_PASSWORD` when that policy includes both scopes.

Those values are passed into Alloy as environment variables. They are not written into `alloy/config.alloy`.

Synthetic Monitoring. Both variables are required, and `docker compose` fails until they are set:

- `SM_API_SERVER` is the private-probe gRPC host only, with no scheme and no port. Compose appends `:443`. An example is `synthetic-monitoring-grpc-us-west-0.grafana.net`.
- `SM_API_TOKEN` is the one-time probe token. Compose maps it to the agent's `SM_AGENT_API_TOKEN`. It is not a Grafana access-policy token.

## Run against the inverter

```bash
docker compose up -d --build
```

The first build clones the exporter commit and compiles it. Later starts reuse the local image.

- Alloy UI: http://127.0.0.1:12345
- In Grafana Cloud Metrics, query `up{job="integrations/solaredge"}` and `AC_Power`
- In Grafana Cloud Logs, query `{service_name="solaredge-exporter", job="integrations/solaredge"}` for exporter logs. For the collector's own logs, query `{job="integrations/alloy", collector_id="solaredge"}`.

Exporter logs are JSON lines, at info level. A healthy process logs startup once, then only Modbus errors and reconnects. The stream labels are `service_name` and `job`. `job` is `integrations/solaredge`, the same value as the scrape. The inverter address is in the line body, not a label, because a DHCP lease can move it. Debug logging stays off: it writes a line every 5 seconds. Alloy remembers the byte offset in the file, so a restart does not send those lines again.

A failed Modbus read is logged with the same message text as before, plus body fields. Read failures are at error level, except meter detection, which stays at warn. `phase` is `connect`, `common_block`, `poll`, or `meter_read`. `error_class` is `modbus_exception`, `timeout`, `connection_reset`, `connection_closed`, `connection_refused`, or `other`. A `modbus_exception` line also carries `modbus_function_code` and `modbus_exception_code`, the code the inverter returned. These are body fields, not labels, so query them with `| json`.

Each series has an `inverter` label of `host:port`, for example `AC_Power{inverter="192.0.2.10:502"}`.

Register values are unscaled. The dashboard turns them into engineering units with the matching scale factor, and scopes each series with `job="integrations/solaredge"` and the `inverter` variable:

```promql
AC_Power * 10 ^ AC_Power_SF
DC_Power * 10 ^ DC_Power_SF
AC_Power * on(inverter) group_left(manufacturer, model, serial, version) Inverter_Info
```

Meter series use the prefixes `M_`, `M2_`, and `M3_`. Batteries are not collected.

## Run the simulator

The simulator is one fake inverter and no meters. Point the exporter at it and skip the meter probe:

```bash
INVERTER_ADDRESS=sunspec-sim NUMBER_METERS=0 docker compose --profile sim up -d --build
```

Shell values override `.env` for that command. `sunspec-sim` must be healthy before the exporter starts. A live `docker compose up` does not start the simulator and does not wait for it.

Stop the stack with `docker compose --profile sim down` when the simulator was started, so the profile container is removed too.

## Raspberry Pi

On the Pi the same processes run under systemd, with no Docker. [`deploy/pi/`](deploy/pi/) holds the units, a non-secret env example, and the layout. `solaredge-exporter`, `solaredge-geolocate`, and `alloy` are enabled for `multi-user.target`, so they start at every boot. The simulator unit is enabled only while proving the path, then disabled so a later boot does not open a second Modbus listener. Alloy's HTTP port, the exporter, geolocate, and the simulator all listen on localhost.

## Module

Scrape settings, the keep-list, and the `forward_to` receiver live in [`module/metrics.alloy`](module/metrics.alloy). The default keep-list is `up`, `SunSpec_*`, `AC_*`, `DC_*`, `Temp_*`, `Status*`, `Inverter_Info`, `M_*`, `M2_*`, and `M3_*`. Exporter `go_*` series are dropped. See [`module/README.md`](module/README.md). Exporter log shipping lives in [`fleet/solaredge.alloy`](fleet/solaredge.alloy), not in that module.

## Dashboard

[`dashboards/solaredge.json`](dashboards/solaredge.json) is a Grafana dashboard v2 resource (`dashboard.grafana.app/v2`, name `solaredge`). In Grafana, import that file. Pick your Prometheus data source and your Loki data source when asked. The `inverter` variable lists `host:port` values and defaults to all of them.

The logs panel queries `{service_name="solaredge-exporter"}`. Those lines also carry `job="integrations/solaredge"`. Phase B and phase C panels stay empty on a single-phase inverter and on the simulator. The SunSpec model stat is labeled Grid configuration. Status keeps its value map: `2` is Sleeping, `7` is Fault. The Status tab holds the inverter status panels. The Site tab is described in [Geolocation and expected yield](#geolocation-and-expected-yield).

## Geolocation and expected yield

[`geolocate/`](geolocate/) is a small Python exporter. It finds the site, asks Open-Meteo for the irradiance on the array's plane every 15 minutes, and exposes expected AC power on port `9110`. Alloy scrapes it as job `integrations/solaredge-geolocate`, so the inverter alerts and SLOs on `integrations/solaredge` do not change.

**Location.** Set `SITE_LAT` and `SITE_LON` in `.env` to use a fixed location. The exporter then makes no IP lookup. Leave both empty and it looks up the public IP at ipinfo.io once a day. The result is cached in the `geolocate-data` volume, so a restart within a day does not call ipinfo again. The `location_source` label on `Site_Location_Info` is `Public IP lookup` or `Set coordinates`. When a lookup fails, the exporter keeps the cached location and retries in an hour. With no location at all, it exports no irradiance or expected-power series.

The home's public IP is sent to ipinfo.io for that lookup, and the public IP is never a label or metric. Coordinates keep 4 decimal places (about 11 m), which is the precision ipinfo returns. Rounding to 2 decimals moves the point by up to about 700 m, so the map marker sits on a coarser grid than the lookup. City, region, and country from ipinfo are also stored as labels in Grafana Cloud. Set both `SITE_LAT` and `SITE_LON` to avoid the lookup and those labels. The lookup itself is only accurate to the neighbourhood the address appears to be in, so the marker can still be some distance from the inverter.

**Expected power.** Open-Meteo gives the plane-of-array irradiance (`GTI`) at `PV_TILT` degrees from horizontal and `PV_AZIMUTH` (0 is south, -90 east, 90 west). Expected AC power is `min(GTI × PV_KWP × PV_PR, PV_AC_LIMIT_W)` in watts. The defaults are 25 degrees, south, 4.56 kWp (3.8 kWp × 1.2), PR 0.8, and a 3800 W limit. Set them to match the array. The model ignores shading, soiling, temperature, and clipping above the AC limit, so the ratio shows direction and is not a measured efficiency. Expected is for the whole site, so read the ratio with all inverters selected.

**Dashboard.** The Site tab compares actual with expected AC power. The performance ratio is a gauge of the latest value, shown only while the sun is up and GTI is above 50 W/m², and it is empty outside that. The tab also has irradiance, a Geomap of the site, and stats for location source, data age, and PV assumptions. Inverter status stays on the Status tab.

The Docker host needs outbound HTTPS to `ipinfo.io` and `api.open-meteo.com`. Open-Meteo data is CC BY 4.0. Attribution is in the [Attribution](#attribution) section.

## Alerts

[`alerting/`](alerting/) holds four Grafana-managed rules, one resource per file (`gcx resources push` reads the first document in a file). A scrape with `up == 0` for `job="integrations/solaredge"`, Modbus errors at `level="error"` on `{service_name="solaredge-exporter", job="integrations/solaredge"}`, `Status == 7` (Fault), and `Modbus_Read_OK == 0` for five minutes. `Status == 2` (Sleeping) is healthy and is not a rule. `up == 0` is the scrape of port `2112`. The poll-failure rule is the gauge, and a missing gauge is NoData. No contact point is committed. Each rule evaluates every minute. The API rejects `grafana.com/group` on create, and a rule sequence has to contain a recording rule, so these rules are not placed in a shared evaluation group.

The queries use the Grafana Cloud datasource UIDs `grafanacloud-prom` and `grafanacloud-logs`. Set `grafana.app/folder` to your folder UID before pushing (`gcx resources get folders`).

```bash
gcx resources push alertrules -p alerting
```

## Fleet Management

[`alloy/config.alloy`](alloy/config.alloy) is the bootstrap. It registers the collector with Fleet Management and ships the collector's own logs to Grafana Cloud Logs. It is the only local Alloy config Compose loads. [`fleet/solaredge.alloy`](fleet/solaredge.alloy) is the pipeline, published to the `lewism` stack's Fleet Management by [`.github/workflows/fleet-management-sync.yml`](.github/workflows/fleet-management-sync.yml), using [`grafana/fleet-management-sync-action@v0.3.0`](https://github.com/grafana/fleet-management-sync-action). The pipeline is [`fleet/solaredge.yaml`](fleet/solaredge.yaml) with matcher `integration=solaredge`, in namespace `solaredge-olly`.

The workflow runs a format check and a validation against [`module/metrics.alloy`](module/metrics.alloy). Pull requests into `main` run the action as a dry run. Pushes to `main` and manual runs sync for real. It needs these repository secrets:

- `FM_URL` is the Fleet Management base URL from Connections, Fleet Management, API.
- `FM_USERNAME` is the numeric Fleet Management instance id from the same tab. The stack slug is rejected.
- `FM_TOKEN` is the access-policy token alone, with `fleet-management:write`. No `username:token` prefix and no trailing newline.

Compose passes `FLEET_MANAGEMENT_URL` and `FLEET_MANAGEMENT_USERNAME` from `.env`, and `GCLOUD_RW_API_KEY` from the metrics token. The collector id is the fixed string `solaredge`, so a container recreate does not register a new collector. Compose also sets `GCLOUD_FM_COLLECTOR_ID=solaredge`, which the generated Fleet Management pipelines read.

The collector's local config is only the bootstrap: the `remotecfg` block and a `logging` tee that sends Alloy's own logs to Loki with `job="integrations/alloy"` and `collector_id="solaredge"`. The generated `self_monitoring_logs_linux` pipeline reads the systemd journal, which this container does not have, so the tee is required for the Fleet Management Logs tab to show anything. The module stays mounted at `/etc/alloy/module/metrics.alloy`, which the remote pipeline imports. Secrets stay in the environment.

```alloy
remotecfg {
  url = sys.env("FLEET_MANAGEMENT_URL")

  basic_auth {
    username = sys.env("FLEET_MANAGEMENT_USERNAME")
    password = sys.env("GCLOUD_RW_API_KEY")
  }

  id             = "solaredge"
  poll_frequency = "1m"

  attributes = {
    integration = "solaredge",
  }
}
```

The remote pipeline is the contents of `fleet/solaredge.alloy`. Fleet Management loads it inside `declare "solaredge"`, so the module import is named `solaredge_module` and the file has no `livedebugging` block. A service block is not allowed inside a module. The pipeline matches this collector through the `integration=solaredge` attribute. A collector that does not run this bootstrap receives no scrape configuration.

Alloy's own metrics reach Grafana Cloud from two pipelines. The generated `self_monitoring_metrics` pipeline ships the Fleet Management health keep-list. `fleet/solaredge.alloy` scrapes `prometheus.exporter.self` every 60 seconds and ships every other family, with the same `job="integrations/alloy"`, `instance`, and `collector_id` labels. Together they send everything Alloy's `/metrics` exposes, about 1,000 series for this collector. The pipeline drops the generated keep-list by name so the two never write the same series. That regex is a copy, so update it if the generated pipelines are recreated with a different list. Metrics for components this collector does not run, such as `cluster_*` and `otelcol_*`, do not exist until those components run.

## Synthetic monitoring

[`synthetic/exporter-http.yaml`](synthetic/exporter-http.yaml) is a MultiHTTP check, job `solaredge-exporter-metrics`, every 60 seconds, timeout 15 seconds, probe `solaredge`. Its assertions require HTTP 200 and a body that contains `SunSpec_DID{`, `Status{`, `AC_Power{`, and `AC_Power_SF{`. `AC_Power{` does not match `AC_Power_SF`. It does not read phase B, phase C, a meter, `/health`, or `Modbus_Read_OK`. A dead Modbus session after the first good poll still passes, because those series stay on the exporter until the process restarts. The request URL is `http://127.0.0.1:2112/metrics` because the API rejects the single-label hostname on a MultiHTTP request; the check target stays `http://solaredge-exporter:2112/metrics`. The check label `service_name=solaredge-exporter` is the same value as the exporter log stream.

The agent image is pinned to `v0.68.0`. Its command includes `--blocked-nets=0.0.0.0/32`, which turns off the agent's default `10.0.0.0/8` denylist so the probe can open the Compose address. No ports are published. `alertSensitivity` is `none`. No contact point is committed.

```bash
gcx synthetic-monitoring checks create -f synthetic/exporter-http.yaml
```

## SLOs

[`slo/`](slo/) holds two Grafana Cloud SLOs, objective 0.99 over 28 days. `metadata.name` is empty so the file does not pin one stack's UUID. Both set `spec.labels` to `service_name=solaredge-exporter`. The SLO app reads that key for the service column and the insights "Missing service label" count. A label named `service` does not count. Fast-burn and slow-burn alerts each carry an `assistantInvestigation` enrichment, so a firing burn alert starts an Assistant investigation. `gcx resources push` treats that empty name as a single object, so push one file at a time. No contact point is committed. There is no energy SLO.

`Modbus_Read_OK` is the poll gauge from [`exporter/modbus-read-ok.patch`](exporter/modbus-read-ok.patch). It is 1 after a poll publishes the inverter model, and it stays 1 between polls. It goes to 0 only when a connect, a read, or a parse fails, and the next successful poll sets it back to 1. A meter error later in the poll does not clear it. An earlier revision reset the gauge to 0 at the start of every poll, so a scrape that landed during a good read recorded a failure. The poll-success SLO history therefore starts over at this change, and its earlier values are not comparable. `Inverter_Info` stays the once-at-startup series. The keep-list in [`module/metrics.alloy`](module/metrics.alloy) includes the gauge.

Poll success is a threshold query: `Modbus_Read_OK{job="integrations/solaredge"}` at or above 1, grouped by `inverter`. A ratio query would wrap the gauge in `rate()`, which stays near 0.

Fault-free polls are freeform. The numerator is samples where the poll succeeded and `Status` is not 7. The denominator is samples where the poll succeeded. Sleeping (`Status == 2`) counts as good. A stale `Status` while `Modbus_Read_OK` is 0 is in neither side. Both sides use `$__rate_interval`.

Each SLO enables the app's fast-burn and slow-burn annotations.

```bash
for f in slo/*.yaml; do
  d=$(mktemp -d)
  cp "$f" "$d/"
  gcx resources push slo -p "$d"
  rm -rf "$d"
done
```

## What comes next

Each chapter gets its own directory when it is implemented.

1. **Alerts** in [`alerting/`](alerting/). Implemented.
2. **Fleet Management** in [`fleet/solaredge.alloy`](fleet/solaredge.alloy). Implemented. [`alloy/config.alloy`](alloy/config.alloy) is the `remotecfg` bootstrap.
3. **Synthetic monitoring** in [`synthetic/`](synthetic/). Implemented. The private probe runs on the Pi. The MultiHTTP check does not prove the inverter answered the latest poll.
4. **SLOs** in [`slo/`](slo/). Implemented. Poll success, and fault-free among successful polls. No energy SLO.
5. **Geolocation and expected yield** in [`geolocate/`](geolocate/). Implemented. No alert or SLO on expected yield yet.

## Troubleshooting

**Exporter cannot reach the inverter.** From the Docker host, `nc -vz <inverter-ip> 502` (or `1502`) should succeed. The container uses the host's route to that address.

**Exporter cannot read the simulator.** `docker compose logs solaredge-exporter` and `docker compose logs sunspec-sim`. The exporter environment for that run must be `INVERTER_ADDRESS=sunspec-sim` and `NUMBER_METERS=0`.

**No samples in Grafana Cloud.** Open the Alloy UI and confirm `solaredge.scrape.inverter` is healthy. Then check the Cloud access policy includes `metrics:write`, and that the URL, instance id, and token match the stack.

**No exporter logs in Grafana Cloud.** Confirm `loki.source.file.exporter` is tailing `/var/log/solaredge/solaredge-exporter.log` and `loki.write.cloud` is healthy. The access policy needs `logs:write`. `GRAFANA_CLOUD_LOKI_USERNAME` is the Loki instance id, not the Prometheus one, and the URL must end in `/loki/api/v1/push`.

**No collector logs in Fleet Management.** Collector logs are Alloy's own logs, a different stream from exporter logs. The bootstrap `logging` block in [`alloy/config.alloy`](alloy/config.alloy) writes them to Loki. Query `{job="integrations/alloy", collector_id="solaredge"}` to confirm they arrive. In the Alloy UI, `self_monitoring_logs_linux` may show an unhealthy `loki.source.journal`. That is expected in this container, which has no systemd journal. Leave the generated pipeline enabled, because disabling it affects every Linux collector on the stack. The lines that matter come from the `logging` tee, not from the journal readers.

**Another Modbus client is already connected.** The inverter accepts one client. Disconnect the other client and restart `solaredge-exporter`.

**A Modbus read failed and you need the cause.** Filter the exporter logs by failure kind: `{service_name="solaredge-exporter", job="integrations/solaredge"} | json | error_class=~".+"`. A `modbus_exception` means the inverter answered, and `modbus_exception_code` gives the reason (for example `2` is an illegal data address, `4` a device failure, `6` a busy device). `timeout` and `connection_reset` point at the network path or a busy inverter. `connection_refused` means nothing listens on the port.

**The site location is wrong.** A VPN, a corporate proxy, or iCloud Private Relay makes ipinfo see another address. Set `SITE_LAT` and `SITE_LON` in `.env`, then run `docker compose up -d solaredge-geolocate`. `Site_Location_Info` should show `location_source="Set coordinates"`.

**No `Site_*` irradiance or expected-power series.** Run `docker compose logs solaredge-geolocate`. It logs each failed ipinfo or Open-Meteo request. `Site_PV_Config_Info` is always exported. The location and irradiance series wait for a location and a successful fetch.

## Attribution

- Exporter: [dave92082/SolarEdge-Exporter](https://github.com/dave92082/SolarEdge-Exporter) (MIT), tag [`1.2.1`](https://github.com/dave92082/SolarEdge-Exporter/releases/tag/1.2.1), commit [`42d4790b78f76a5fae9e931cf78a76dbda0ccb53`](https://github.com/dave92082/SolarEdge-Exporter/commit/42d4790b78f76a5fae9e931cf78a76dbda0ccb53)
- Collector: [grafana/alloy](https://github.com/grafana/alloy) `v1.21.2`
- Irradiance: [Open-Meteo](https://open-meteo.com/) forecast API (CC BY 4.0 data, no key)
- Location: [ipinfo.io](https://ipinfo.io/) IP lookup, used only when `SITE_LAT` and `SITE_LON` are unset
