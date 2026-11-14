# Collection

## The product

[Grafana Alloy](https://grafana.com/docs/alloy/latest/) is the collector. It scrapes a Prometheus exporter and remote-writes the samples. The exporter is ordinary software that speaks the device's protocol and exposes `/metrics`. Alloy does not know Modbus. The split is the one to keep: a small exporter per protocol, one collector for delivery.

## This stack

A SolarEdge inverter speaks Modbus TCP / SunSpec. [dave92082/SolarEdge-Exporter](https://github.com/dave92082/SolarEdge-Exporter) `1.2.1`, commit `42d4790b78f76a5fae9e931cf78a76dbda0ccb53`, polls it and serves `:2112`. Three patches in [exporter/](https://github.com/lewismc/solaredge-olly/tree/main/exporter) add inverter identity, a poll-success gauge, and structured error fields. Upstream ships binaries, not an image, so the Compose file builds it.

```text
inverter --Modbus TCP--> solaredge-exporter --scrape :2112--> Alloy --remote_write--> Grafana Cloud Metrics
```

One Modbus TCP client can hold the inverter. Stop any other logger before this exporter connects. Cloud SolarEdge monitoring uses a different path and can stay on. `INVERTER_ADDRESS` is a comma-separated list, and an entry may carry its own port (`192.0.2.10:1502`). LCD units default to port 502, SetApp units to 1502. `NUMBER_METERS` defaults to `0`: this inverter has no meter, and the exporter otherwise probes meter 1 and logs an illegal-data-address skip. `INVERTER_CLIENT_ID` defaults to `1`.

The simulator is one fake inverter, SunSpec model 101, no meters. `INVERTER_ADDRESS=sunspec-sim NUMBER_METERS=0 docker compose --profile sim up -d --build` starts it. A plain `docker compose up` does not. Do not point Compose at the live inverter while the Pi is running: two clients, and two collectors with `collector_id=solaredge` would fight over the Fleet Management pipeline.

The LAN notes for the inverter this stack was checked against are in [docs/lan-inverter.md](https://github.com/lewismc/solaredge-olly/blob/main/docs/lan-inverter.md). Its address is a DHCP lease and moves.

**When the exporter cannot reach the inverter.** From the host, `nc -vz <inverter-ip> 502` (or `1502`) should succeed. **When another client is connected.** Disconnect it and restart `solaredge-exporter`. **When the simulator is not read.** The exporter environment for that run must be `INVERTER_ADDRESS=sunspec-sim` and `NUMBER_METERS=0`.

## Reuse on a customer system

Put the protocol adapter in its own process with a boring `/metrics` port. Keep the collector replaceable. Before the first scrape, find out how many sessions the device allows. A "down" that is really a second logger is the usual first incident. Record the device address as configuration, not as a label you cannot change, when DHCP can move it.
