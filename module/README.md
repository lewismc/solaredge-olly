# SolarEdge module

Scrapes SolarEdge inverter and meter metrics exposed by a local Prometheus exporter that polls the inverter over Modbus TCP using the SunSpec protocol ([dave92082/SolarEdge-Exporter](https://github.com/dave92082/SolarEdge-Exporter) `1.2.1`).

This module does not speak Modbus. The Compose stack in the repository root runs the exporter, then Alloy loads this file with `import.file` and scrapes `/metrics` (default port `2112`). This module is the scrape. Exporter log shipping lives in `alloy/config.alloy`.

## Applicable Alloy versions

[Grafana Alloy](https://github.com/grafana/alloy) v1.0 and later. This repository pins `grafana/alloy:v1.21.2`. The module uses `import.file`, `discovery.relabel`, `prometheus.scrape`, and `prometheus.relabel`.

## Prerequisites

See the exporter's upstream [Requirements](https://github.com/dave92082/SolarEdge-Exporter/#requirements). In short:

- SolarEdge inverter with SunSpec support (SetApp models, or LCD firmware CPU `3.xxxx`+)
- Modbus TCP enabled on the inverter
- Ethernet / LAN path from the Docker host to the inverter (not ZigBee or GSM)
- Only one Modbus TCP client may connect to an inverter at a time
- Cloud SolarEdge monitoring and local Modbus TCP can run in parallel

## Components

- [`local`](#local)
- [`scrape`](#scrape)

### `local`

Builds a static scrape target for a SolarEdge Prometheus exporter.

#### Arguments

| Name | Optional | Default | Description |
| :--- | :--- | :--- | :--- |
| `exporter_address` | `true` | `127.0.0.1:2112` | Host:port of the SolarEdge Prometheus exporter |

#### Exports

| Name | Type | Description |
| :--- | :--- | :--- |
| `output` | `list(map(string))` | List of discovered targets |

#### Labels

| Label | Description |
| :--- | :--- |
| `source` | Constant value of `local`, denoting where the results came from |

### `scrape`

Scrapes SolarEdge exporter targets and keep-lists inverter and meter SunSpec metrics.

#### Arguments

| Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `targets` | yes | | List of targets to scrape |
| `forward_to` | yes | | List of `MetricsReceiver` where scraped samples are forwarded |
| `job_label` | no | `integrations/solaredge` | Job label for scraped metrics |
| `keep_metrics` | no | inverter series, `Inverter_Info`, `Modbus_Read_OK`, `M_*` / `M2_*` / `M3_*`, and `up` | Regex of metrics to keep |
| `drop_metrics` | no | `go_*` | Regex of metrics to drop |
| `scheme` | no | `http` | Scrape scheme |
| `bearer_token_file` | no | none | Optional bearer token file |
| `scrape_interval` | no | `15s` | How often to scrape |
| `scrape_timeout` | no | `10s` | Scrape timeout |
| `max_cache_size` | no | `100000` | Relabel cache size |
| `clustering` | no | `false` | Enable Alloy clustering for this scrape |

#### Labels

| Label | Description |
| :--- | :--- |
| `job` | Set to the value of `argument.job_label.value` |

The exporter adds an `inverter` label of `host:port` on every sample. Register values are unscaled. Multiply by ten to the power of the matching `*_SF` series to get engineering units. Example: `AC_Power * 10 ^ AC_Power_SF`.

`Inverter_Info` is 1 for each inverter whose SunSpec common block was read at startup. Manufacturer, model, serial, and version are labels on that one series. Join them onto a register series at query time:

```promql
AC_Power * on(inverter) group_left(manufacturer, model, serial, version) Inverter_Info
```

`Modbus_Read_OK` is a gauge with only the `inverter` label. It is 0 at the start of each poll and when the first Modbus connection fails, and 1 only after that poll's inverter model block is published. A meter error later in the same poll does not clear it.

## Usage

From this repository, with the module mounted at `/etc/alloy/module/metrics.alloy`:

```alloy
import.file "solaredge" {
  filename = "/etc/alloy/module/metrics.alloy"
}

solaredge.local "home" {
  exporter_address = "solaredge-exporter:2112"
}

solaredge.scrape "inverter" {
  targets    = solaredge.local.home.output
  forward_to = [prometheus.remote_write.metrics.receiver]
}

prometheus.remote_write "metrics" {
  endpoint {
    url = sys.env("GRAFANA_CLOUD_PROM_URL")

    basic_auth {
      username = sys.env("GRAFANA_CLOUD_PROM_USERNAME")
      password = sys.env("GRAFANA_CLOUD_PROM_PASSWORD")
    }
  }
}
```

`alloy/config.alloy` in the repository is that wiring for the Compose stack.

## Sample PromQL

```promql
up{job="integrations/solaredge"}
AC_Power
DC_Power
Status
SunSpec_DID
Inverter_Info
Modbus_Read_OK
M_AC_Power
```

`AC_Power{inverter="192.0.2.10:502"}` selects one inverter when `INVERTER_ADDRESS` lists more than one.

## Follow-up

Batteries (StorEdge / BYD registers) stay out of the keep-list until an exporter release exposes them.

## Notes

- One exporter process polls every address in the comma-separated `INVERTER_ADDRESS` list. Each inverter still accepts only one Modbus TCP client.
- Upstream exporter: [dave92082/SolarEdge-Exporter](https://github.com/dave92082/SolarEdge-Exporter) tag `1.2.1`, commit `42d4790b78f76a5fae9e931cf78a76dbda0ccb53` (MIT).
