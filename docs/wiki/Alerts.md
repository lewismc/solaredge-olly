# Alerts

## The product

Grafana Alerting evaluates rules on an interval and moves an instance through pending and firing. A rule is a query plus a condition, held for a duration so one bad sample does not page. `NoData` and `Error` are states you choose: a missing series can be fine (night) or a failure (the scrape vanished). Rules do not name a contact point. A label does, and the notification policy matches it. That split is what lets one route cover rules you have not written yet.

## This stack

[alerting/](https://github.com/lewismc/solaredge-olly/tree/main/alerting) holds five Grafana-managed rules, one resource per file. `gcx resources push` reads the first document in a file. Each rule evaluates every minute and carries `service_name=solaredge-exporter`, which is what [Notifications](https://github.com/lewismc/solaredge-olly/wiki/Notifications) matches. The queries use the Grafana Cloud datasource UIDs `grafanacloud-prom` and `grafanacloud-logs`. Set `grafana.app/folder` to the folder UID before pushing (`gcx resources get folders`). The committed files keep the placeholder `YOUR_FOLDER_UID`.

The API rejects `grafana.com/group` on create, and a rule sequence has to contain a recording rule, so these rules are not placed in a shared evaluation group.

| Rule | Fires when | Held for | No data |
| :--- | :--- | :--- | :--- |
| Exporter down | `ScrapeUp` (`up{job="integrations/solaredge"}`) is below 1 | 5m | Alerting |
| Modbus errors | `ErrorLogs`, a count of `level="error"` lines, is above 0 | 5m | OK |
| Inverter fault | `InverterStatus` (`Status`) equals 7 | 5m | OK |
| Poll failure | `ModbusReadOK` is below 1 | 5m | NoData |
| Underperformance | `PowerRatio` is below 0.25 while irradiance is above 200 W/m² | 1h | OK |

`Status == 2` (Sleeping) is healthy and is not a rule. The exporter-down query keeps the `up` series and thresholds it. A query of `up == 0` is empty while the exporter is up, and `noDataState: Alerting` would fire on that empty result. The poll-failure rule is the same shape on the gauge. A missing gauge is NoData, which is a different failure from a gauge of 0.

The fault rule is three queries: `InverterStatus` reads `Status`, `IsFault` is `$InverterStatus == 7`, and `FaultFired` thresholds that above 0. The names are the ref ids. Slack prints them, so a ref id of `A` would show up as `A = 0`.

Underperformance is actual AC power over `Site_Expected_AC_Power_W`, and only while `Site_Irradiance_GTI_Wm2` is above 200. The query is empty at night, so NoData is OK. The expected-power model is optimistic: over the first week the ratio averaged about 0.58 under that irradiance, and its 10th percentile was about 0.27. A threshold of 0.5 would have fired on ordinary days. 0.25 for an hour sits below that.

```bash
gcx resources push alertrules -p alerting
```

## Reuse on a customer system

Name every query ref for the value a person will read in the notification. Route on one label (`service_name`), not on rule titles. Choose `NoData` per rule: missing data is a page only when the series should always exist. Hold a rule long enough to outlast one scrape. Set a threshold from recorded data, not from the number that feels right. A model that ignores shading will sit well below 1 on a normal day.
