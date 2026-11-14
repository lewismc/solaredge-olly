# Logs

## The product

[Grafana Cloud Logs](https://grafana.com/docs/grafana-cloud/send-data/logs/) is a [Loki](https://grafana.com/docs/loki/latest/) store. Alloy pushes log streams. A stream is defined by its labels. Labels are indexed. Everything else is in the line body and is filtered after the stream is selected. High-cardinality labels (an IP that DHCP can change, a user id, a trace id) multiply streams and cost. Put those in the line and parse them with `| json`.

## This stack

The exporter writes JSON lines to a file. Alloy tails that file. A healthy process logs startup once, then only Modbus errors and reconnects. Debug stays off: it writes a line every 5 seconds. Alloy remembers the byte offset, so a restart does not send the same lines again.

The exporter stream carries `service_name="solaredge-exporter"`, `job="integrations/solaredge"`, `service_namespace="solaredge"`, `deployment_environment="home"`, and `service_instance_id` set to the host name. Those four resource labels are the same ones on the metrics, with the OpenTelemetry dots replaced by underscores. `job` stays the integration name, so a metrics alert and a log query name the same thing. `deployment_environment` stays that key because the Knowledge Graph maps it. The inverter address is in the line body, not a label.

```logql
{service_name="solaredge-exporter", job="integrations/solaredge"}
```

A failed Modbus read keeps the old message text and adds body fields. Read failures are at error level, except meter detection, which stays at warn. `phase` is `connect`, `common_block`, `poll`, or `meter_read`. `error_class` is `modbus_exception`, `timeout`, `connection_reset`, `connection_closed`, `connection_refused`, or `other`. A `modbus_exception` line also carries `modbus_function_code` and `modbus_exception_code`. Query them with `| json`.

```logql
{service_name="solaredge-exporter", job="integrations/solaredge"} | json | error_class=~".+"
```

`modbus_exception_code` `2` is an illegal data address, `4` a device failure, `6` a busy device. `timeout` and `connection_reset` point at the network or a busy inverter. `connection_refused` means nothing is listening.

Logs credentials are a different URL and instance id from metrics. `GRAFANA_CLOUD_LOKI_URL` ends in `/loki/api/v1/push`. `GRAFANA_CLOUD_LOKI_USERNAME` is the Loki instance id. The token needs `logs:write` and can be the same token as metrics when the policy has both scopes.

Alloy's own logs are a different stream. They keep `job="integrations/alloy"` and `collector_id="solaredge"`, and they carry the same four resource labels, with `service_name="alloy"`. They are described on [Fleet Management](https://github.com/lewismc/solaredge-olly/wiki/Fleet-Management).

**When exporter logs do not arrive.** Confirm the file tail and the Loki writer are healthy in the Alloy UI. Then check `logs:write`, the Loki instance id, and that the URL ends in `/loki/api/v1/push`.

## Reuse on a customer system

Pick two or three stream labels and stop. `service_name` plus `job` was enough to join logs to metrics, alerts, and SLOs. Parse structured fields from the body. A label that moves (a DHCP address, a container id) splits one service into many streams and then ages out of every query. Keep the line format stable when you add fields, so old queries still match.
