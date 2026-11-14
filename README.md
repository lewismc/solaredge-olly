# solaredge-olly

A Grafana Cloud learning project, and a monitor for a home SolarEdge inverter. One pipeline does both. A Prometheus exporter polls the inverter over Modbus TCP / SunSpec. Grafana Alloy remote-writes the samples and pushes the exporter's logs. The live collector runs on a Raspberry Pi under systemd. Docker Compose runs the same services on a Mac or a Linux host for simulator and development runs.

```text
inverter --Modbus TCP--> solaredge-exporter --scrape :2112--> Alloy --remote_write--> Grafana Cloud Metrics
                         solaredge-exporter --log file-----> Alloy --loki push--> Grafana Cloud Logs
solaredge-geolocate --scrape :9110--> Alloy --remote_write--> Grafana Cloud Metrics
```

The long-form notes live in the [wiki](https://github.com/lewismc/solaredge-olly/wiki). Each page says what the Grafana Cloud product is, how this stack uses it, and what to reuse on a customer system. The pages are written in [docs/wiki/](docs/wiki/) and published from there. Edit the copy in the repo.

| Order | Module | Product |
| :--- | :--- | :--- |
| 1 | [Collection](https://github.com/lewismc/solaredge-olly/wiki/Collection) | Alloy, a Prometheus exporter |
| 2 | [Metrics](https://github.com/lewismc/solaredge-olly/wiki/Metrics) | Grafana Cloud Metrics |
| 3 | [Fleet Management](https://github.com/lewismc/solaredge-olly/wiki/Fleet-Management) | Fleet Management |
| 4 | [Logs](https://github.com/lewismc/solaredge-olly/wiki/Logs) | Grafana Cloud Logs |
| 5 | [Dashboard](https://github.com/lewismc/solaredge-olly/wiki/Dashboard) | Dashboards |
| 6 | [Alerts](https://github.com/lewismc/solaredge-olly/wiki/Alerts) | Grafana Alerting |
| 7 | [Notifications](https://github.com/lewismc/solaredge-olly/wiki/Notifications) | Contact points and notification policies |
| 8 | [Geolocation and expected yield](https://github.com/lewismc/solaredge-olly/wiki/Geolocation-and-expected-yield) | Metrics, Geomap |
| 9 | [Synthetic Monitoring](https://github.com/lewismc/solaredge-olly/wiki/Synthetic-Monitoring) | Synthetic Monitoring |
| 10 | [SLOs](https://github.com/lewismc/solaredge-olly/wiki/SLOs) | SLOs, Grafana Assistant |
| 11 | [Raspberry Pi runtime](https://github.com/lewismc/solaredge-olly/wiki/Raspberry-Pi-runtime) | The collector host |

## Run

The Pi is the live runtime. Its units, layout, and the daily updater are in [deploy/pi/](deploy/pi/).

For a simulator or development run, `docker compose up -d --build` starts the exporter, Alloy, the private probe, and geolocate. Do not point Compose at the live inverter while the Pi is running. The inverter accepts one Modbus client, and two collectors with `collector_id=solaredge` would fight over the Fleet Management pipeline.

```bash
cp .env.example .env
docker compose up -d --build
```

`.env` holds the inverter address and the Grafana Cloud tokens. The names are in [.env.example](.env.example). The simulator is one fake inverter and no meters:

```bash
INVERTER_ADDRESS=sunspec-sim NUMBER_METERS=0 docker compose --profile sim up -d --build
```

Alloy's UI is on http://127.0.0.1:12345. In Grafana Cloud, `up{job="integrations/solaredge"}` and `AC_Power` are the first queries.

## Attribution

- Exporter: [dave92082/SolarEdge-Exporter](https://github.com/dave92082/SolarEdge-Exporter) (MIT), tag [`1.2.1`](https://github.com/dave92082/SolarEdge-Exporter/releases/tag/1.2.1), commit [`42d4790b78f76a5fae9e931cf78a76dbda0ccb53`](https://github.com/dave92082/SolarEdge-Exporter/commit/42d4790b78f76a5fae9e931cf78a76dbda0ccb53)
- Collector: [grafana/alloy](https://github.com/grafana/alloy) `v1.21.2`
- Irradiance: [Open-Meteo](https://open-meteo.com/) forecast API (CC BY 4.0 data, no key)
- Location: [ipinfo.io](https://ipinfo.io/) IP lookup, used only when `SITE_LAT` and `SITE_LON` are unset
