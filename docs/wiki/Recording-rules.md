# Recording rules

## The product

A [recording rule](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/alerting/alerting-rules/create-recording-rules/) runs a query on an interval and writes the result back as a new series. It turns a formula that every panel repeats into one name. Grafana Cloud has two kinds. [Grafana-managed recording rules](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/alerting/alerting-rules/create-recording-rules/create-grafana-managed-recording-rules/) are evaluated by Grafana, can query any alerting datasource, and write to a Prometheus datasource you name. Data source-managed rules are evaluated by the Mimir ruler and read only that Mimir. Recorded series are ordinary series, so they count toward active series and DPM.

## This stack

[recording-rules/](https://github.com/lewismc/solaredge-olly/tree/main/recording-rules) holds three Grafana-managed rules, one resource per file, the same shape and the same folder as the alert rules. They write to `grafanacloud-prom` and carry `service_name=solaredge-exporter`.

| Series | Every | Query |
| :--- | :--- | :--- |
| `solaredge:ac_power:watts` | 1m | `AC_Power * 10 ^ AC_Power_SF`, summed by `job`, `inverter`, `service_namespace`, `deployment_environment`, `service_name`, `service_instance_id` |
| `solaredge:ac_energy:kwh_24h` | 5m | max minus min of `AC_Energy_WH * 10 ^ AC_Energy_WH_SF` over a `[24h:5m]` subquery, over 1000, grouped the same way as the watts rule |
| `solaredge:performance_ratio` | 1m | watts over `max(Site_Expected_AC_Power_W)`, only while `max(Site_Irradiance_GTI_Wm2) > 200` |

The scale factor is the reason for the first rule. SunSpec sends each value with a power-of-ten exponent, and forgetting it is off by a factor of 10 or 100. The name follows the Prometheus `level:metric:operations` convention.

`AC_Energy_WH` is the inverter's lifetime counter. Over the day these rules were written it had no resets and a constant scale factor of 0, and the last 24 hours came to 3.188 kWh. max minus min tolerates the gaps while the inverter sleeps. `increase()` would assume a counter with resets. The result is a rolling 24 hours. A calendar day is a dashboard query over `now/d`, because a recording rule has no time zone.

The performance ratio is recorded only above 200 W/m², the same gate as the [underperformance alert](https://github.com/lewismc/solaredge-olly/blob/main/alerting/solaredge-underperformance.yaml). Night and overcast samples would otherwise pull the average toward zero. Expect gaps after dark. The alert still runs its own query and does not depend on this rule.

```bash
mkdir -p /tmp/rr
for f in recording-rules/*.yaml; do sed "s/YOUR_FOLDER_UID/<folder uid>/g" "$f" > /tmp/rr/$(basename "$f"); done
gcx resources push recordingrules -p /tmp/rr
```

`gcx resources validate` checks recording rules client-side only. The API has no server-side dry run for this kind. Check the query in Explore first.

## Reuse on a customer system

Record a formula once three panels repeat it, or once it carries a unit conversion someone will get wrong. Keep the labels you filter and route by in the `by ()` clause, including the environment and namespace labels, or the recorded series falls outside every scope that uses them. Prefer Grafana-managed rules when the input spans datasources. Prefer data source-managed rules when the input lives in one Mimir and evaluation load matters. Gate ratios on the condition that makes them meaningful, and write down what an empty result means.
