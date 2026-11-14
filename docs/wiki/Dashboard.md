# Dashboard

## The product

A Grafana dashboard is a saved layout of queries. A variable filters every panel from one control. A v2 dashboard (`dashboard.grafana.app/v2`) is a resource you can push, the same way as an alert rule. The dashboard is not the source of truth for the data. The queries are. If a panel is empty, the query or the label match is wrong before the panel is.

## This stack

[dashboards/solaredge.json](https://github.com/lewismc/solaredge-olly/blob/main/dashboards/solaredge.json) is a v2 dashboard named `solaredge`. Import it and pick the Prometheus and Loki data sources when asked. The `inverter` variable lists `host:port` values and defaults to all of them. Panels scope series with `job="integrations/solaredge"` and that variable, and they apply the scale factor:

```promql
AC_Power * 10 ^ AC_Power_SF
```

The Status tab holds inverter status. Status keeps its value map: `2` is Sleeping, `7` is Fault. The SunSpec model stat is labeled Grid configuration. Phase B and phase C panels stay empty on a single-phase inverter and on the simulator.

The Site tab compares actual AC power with expected AC power. The performance ratio is a gauge of the latest value, shown only while the sun is up and plane-of-array irradiance is above 50 W/m². The tab also has irradiance, a Geomap of the site, and stats for location source, data age, and the PV assumptions. That model is described on [Geolocation and expected yield](https://github.com/lewismc/solaredge-olly/wiki/Geolocation-and-expected-yield).

The logs panel queries `{service_name="solaredge-exporter"}`. Those lines also carry `job="integrations/solaredge"`.

## Reuse on a customer system

One variable that matches the label you alert on. The same `job` and `service_name` in the dashboard, the alert, and the log query, so a panel and an alert cannot silently diverge. Put unit conversion in the query and label the panel with the unit. Leave a panel empty on purpose when the hardware does not have that phase, and say so, instead of hiding a broken query. Import the dashboard as a resource so the next environment gets the same file.
