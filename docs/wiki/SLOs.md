# SLOs

## The product

A [Grafana Cloud SLO](https://grafana.com/docs/grafana-cloud/alerting-and-irm/slo/) is an objective (for example 99% of good events over 28 days) plus a definition of a good event. The app burns an error budget and alerts on a fast burn and a slow burn. The label `service_name` is what the SLO app reads for the service column. A label named `service` does not count. A burn alert can carry an enrichment. `assistantInvestigation` starts a [Grafana Assistant](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/) investigation when the burn fires.

The event has to be something a ratio or a threshold can see. A gauge that sits at 1 between polls is not a rate. Wrapping it in `rate()` produces a number near 0 and an SLO that is always failing.

## This stack

[slo/](https://github.com/lewismc/solaredge-olly/tree/main/slo) holds two SLOs, objective 0.99 over 28 days. `metadata.name` is empty so the file does not pin one stack's UUID. Both set `spec.labels` to `service_name=solaredge-exporter`. Fast-burn and slow-burn alerts each carry an `assistantInvestigation` enrichment. `gcx resources push` treats that empty name as a single object, so push one file at a time. The burn alerts inherit `service_name=solaredge-exporter` and route to Slack. There is no energy SLO.

`Modbus_Read_OK` is the poll gauge from [exporter/modbus-read-ok.patch](https://github.com/lewismc/solaredge-olly/blob/main/exporter/modbus-read-ok.patch). It is 1 after a poll publishes the inverter model, and it stays 1 between polls. It goes to 0 only when a connect, a read, or a parse fails, and the next successful poll sets it back to 1. A meter error later in the poll does not clear it. An earlier revision reset the gauge to 0 at the start of every poll, so a scrape that landed during a good read recorded a failure. The poll-success SLO history starts over at that change. Earlier values are not comparable.

Poll success is a threshold query: `Modbus_Read_OK{job="integrations/solaredge"}` at or above 1, grouped by `inverter`.

Fault-free polls are freeform. The numerator is samples where the poll succeeded and `Status` is not 7. The denominator is samples where the poll succeeded. Sleeping (`Status == 2`) counts as good. A stale `Status` while `Modbus_Read_OK` is 0 is in neither side. Both sides use `$__rate_interval`.

```bash
for f in slo/*.yaml; do
  d=$(mktemp -d)
  cp "$f" "$d/"
  gcx resources push slo -p "$d"
  rm -rf "$d"
done
```

## Reuse on a customer system

Define the good event before the objective. A gauge of "last poll worked" is a threshold SLO, not a ratio of rates. Group by the label you already alert on (`inverter`), and use `service_name` exactly, because the app looks for that key. Start the error-budget history over when you change the indicator, and say so. Attach an investigation enrichment to the burn alert so the page comes with a first look, and let the burn alert use the same notification route as the symptom alerts.
