# Metrics

## The product

[Grafana Cloud Metrics](https://grafana.com/docs/grafana-cloud/send-data/metrics/) is a Prometheus store. Alloy remote-writes samples to it. A series is a name plus labels. Cardinality is the count of those combinations, and it is what the bill tracks. PromQL computes on the stored samples. Scale, units, and "is this the right series" are the sender's job. The store will not fix them.

## This stack

Credentials are environment variables, never written into [alloy/config.alloy](https://github.com/lewismc/solaredge-olly/blob/main/alloy/config.alloy):

- `GRAFANA_CLOUD_PROM_URL` ends in `/api/prom/push`
- `GRAFANA_CLOUD_PROM_USERNAME` is the stack's Prometheus instance id
- `GRAFANA_CLOUD_PROM_PASSWORD` is an access-policy token with `metrics:write`

The scrape, the keep-list, and the `forward_to` receiver live in [module/metrics.alloy](https://github.com/lewismc/solaredge-olly/blob/main/module/metrics.alloy). The keep-list is `up`, `SunSpec_*`, `AC_*`, `DC_*`, `Temp_*`, `Status*`, `Inverter_Info`, `M_*`, `M2_*`, and `M3_*`. Exporter `go_*` series are dropped. The job label is `integrations/solaredge`. A second scrape, job `integrations/solaredge-geolocate`, takes `up` and `Site_*` only, so the inverter alerts and SLOs do not see the site series.

Each series has an `inverter` label of `host:port`, for example `AC_Power{inverter="192.0.2.10:502"}`. Register values are unscaled. Engineering units need the matching scale factor:

```promql
AC_Power * 10 ^ AC_Power_SF
DC_Power * 10 ^ DC_Power_SF
AC_Power * on(inverter) group_left(manufacturer, model, serial, version) Inverter_Info
```

Meter series use the prefixes `M_`, `M2_`, and `M3_`. Batteries are not collected. A healthy check is `up{job="integrations/solaredge"}` and `AC_Power`.

Alloy's own `/metrics` is a second stream, about 1,000 series, under `job="integrations/alloy"`. That is described on [Fleet Management](https://github.com/lewismc/solaredge-olly/wiki/Fleet-Management).

**When no samples arrive.** In the Alloy UI, confirm the scrape is healthy. Then check the access policy includes `metrics:write`, and that the URL, the instance id, and the token belong to the same stack.

## Reuse on a customer system

Decide the label set before the first remote write. A label that can change (an IP, a pod name, a customer id with unbounded values) becomes a cardinality problem you cannot delete cheaply. Drop the process metrics you will never alert on. Store raw instrument values and convert units in the query or a recording rule, and write down the scale factor next to the dashboard. Two jobs are cheaper than one job with a label you then have to exclude from every alert.
