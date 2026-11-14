# Alerts

## The product

[Grafana Alerting](https://grafana.com/docs/grafana/latest/alerting/) evaluates rules on an interval and moves an instance through pending and firing. A rule is a query plus a condition, held for a duration so one bad sample does not page. `NoData` and `Error` are states you choose: a missing series can be fine (night) or a failure (the scrape vanished). Rules do not name a contact point. A label does, and the notification policy matches it. That split is what lets one route cover rules you have not written yet.

## This stack

[alerting/](https://github.com/lewismc/solaredge-olly/tree/main/alerting) holds seven Grafana-managed rules, one resource per file. `gcx resources push` reads the first document in a file. Each rule evaluates every minute and carries `service_name=solaredge-exporter`, which is what [Notifications](https://github.com/lewismc/solaredge-olly/wiki/Notifications) matches. The queries use the Grafana Cloud datasource UIDs `grafanacloud-prom` and `grafanacloud-logs`. Set `grafana.app/folder` to the folder UID before pushing (`gcx resources get folders`). The committed files keep the placeholder `YOUR_FOLDER_UID`.

The API rejects `grafana.com/group` on create, and a rule sequence has to contain a recording rule, so these rules are not placed in a shared evaluation group.

| Rule | Fires when | Held for | No data |
| :--- | :--- | :--- | :--- |
| Exporter down | `ScrapeUp` (`up{job="integrations/solaredge"}`) is below 1 | 5m | Alerting |
| Modbus errors | `ErrorLogs`, a count of `level="error"` lines, is above 0 | 5m | OK |
| Inverter fault | `InverterStatus` (`Status`) equals 7 | 5m | OK |
| Poll failure | `ModbusReadOK` is below 1 | 5m | NoData |
| Underperformance | `PowerRatio` is below 0.25 while irradiance is above 200 W/m² | 1h | OK |
| Unit memory near MemoryMax | `AnonRatio`, a unit's anonymous memory over its `MemoryMax`, is above 0.8 | 15m | OK |
| Unit OOM kill | `OOMKills`, the 15-minute increase of a unit's `oom_kill` count, is above 0 | 0s | OK |

The two unit rules read the textfile series described on [Host metrics](https://github.com/lewismc/solaredge-olly/wiki/Host-metrics). The Raspberry Pi integration's own alerts (temperature, filesystem, host memory, failed units) are installed with the integration and are not in this directory.

Four more rules live in the `knowledge-graph` folder, group `solaredge-home-health`, and are not in [alerting/](https://github.com/lewismc/solaredge-olly/tree/main/alerting). They are the [Knowledge Graph](https://github.com/lewismc/solaredge-olly/wiki/Knowledge-Graph) health rules. Each one notifies `grafana-insight-processor`, so it colors an entity and does not post to Slack. The files are in [knowledge-graph/alertrules/](https://github.com/lewismc/solaredge-olly/tree/main/knowledge-graph/alertrules).

| Rule | Fires when | Entity | No data |
| :--- | :--- | :--- | :--- |
| ExporterScrapeDown | `up{job="integrations/solaredge"}` is 0 | Exporter | OK |
| InverterFault | `Status` is 7 | Inverter | OK |
| SiteFault | the same fault, labeled as the site | Site | OK |
| CollectorScrapeDown | `up{job="integrations/alloy"}` is 0 | Collector | OK |

`InverterFault` matches only 7, so `Status == 2` (Sleeping) leaves the Inverter healthy. These expressions use `== bool` and return 0 while healthy. The Slack inverter-fault rule is the same condition, held for 5 minutes, and it pages. The Knowledge Graph rule is not held, and it only colors the graph.

The seven Slack rules also carry `asserts_env`, `asserts_site`, `asserts_entity_type`, `asserts_alert_category`, and `asserts_severity`. `service_name=solaredge-exporter` is unchanged, so they still page Slack. The Knowledge Graph watcher copies a firing alert from this folder onto the matching entity. Exporter down and inverter fault therefore show twice when they fire: the health rule immediately, and the Slack rule after its hold. The inverter name stays the series label. The other rules name their one entity in the file, because the query drops labels or the alert fires on no data.

`Status == 2` (Sleeping) is healthy and is not a rule. The exporter-down query keeps the `up` series and thresholds it. A query of `up == 0` is empty while the exporter is up, and `noDataState: Alerting` would fire on that empty result. The poll-failure rule is the same shape on the gauge. A missing gauge is NoData, which is a different failure from a gauge of 0.

The fault rule is three queries: `InverterStatus` reads `Status`, `IsFault` is `$InverterStatus == 7`, and `FaultFired` thresholds that above 0. The names are the ref ids. Slack prints them, so a ref id of `A` would show up as `A = 0`.

Underperformance is actual AC power over `Site_Expected_AC_Power_W`, and only while `Site_Irradiance_GTI_Wm2` is above 200. The query is empty at night, so NoData is OK. The expected-power model is optimistic: over the first week the ratio averaged about 0.58 under that irradiance, and its 10th percentile was about 0.27. A threshold of 0.5 would have fired on ordinary days. 0.25 for an hour sits below that.

```bash
gcx resources push alertrules -p alerting
```

## Reuse on a customer system

Name every query ref for the value a person will read in the notification. Route on one label (`service_name`), not on rule titles. Choose `NoData` per rule: missing data is a page only when the series should always exist. Hold a rule long enough to outlast one scrape. Set a threshold from recorded data, not from the number that feels right. A model that ignores shading will sit well below 1 on a normal day.
