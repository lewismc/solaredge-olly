# Logs

## The product

[Grafana Cloud Logs](https://grafana.com/docs/grafana-cloud/send-data/logs/) is a [Loki](https://grafana.com/docs/loki/latest/) store. Alloy pushes log streams. A stream is defined by its labels. Labels are indexed. Everything else is in the line body and is filtered after the stream is selected. High-cardinality labels (an IP that DHCP can change, a user id, a trace id) multiply streams and cost. Put those in the line and parse them with `| json`.

Redact a sensitive value in the collector, before the push. [`loki.process`](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.process/) `stage.replace` rewrites the line Alloy sends. A `line_format` in a query changes that one result, and the stored line stays as it was written. A label is indexed for the life of the stream, so an address or a serial belongs in the line, which is where you mask it. The Grafana Labs Professional Services guide [Masking/Redacting PII Logs in Loki with Alloy](https://storage.googleapis.com/ps-best-practice-guides/loki/loki-pii-redaction.pdf) (updated 2026-07-15) is the pattern catalog: email, phone, SSN, card numbers with `stage.luhn`, and IP addresses. Grafana Cloud documents the same `stage.replace` approach on the [send logs](https://grafana.com/docs/grafana-cloud/send-data/logs/) page.

## This stack

The exporter writes JSON lines to a file. Alloy tails that file. A healthy process logs startup once, then only Modbus errors and reconnects. Debug stays off: it writes a line every 5 seconds. Alloy remembers the byte offset, so a restart does not send the same lines again.

The exporter stream carries `service_name="solaredge-exporter"`, `job="integrations/solaredge"`, `service_namespace="solaredge"`, `deployment_environment="home"`, and `service_instance_id` set to the host name. Those four resource labels are the same ones on the metrics, with the OpenTelemetry dots replaced by underscores. `job` stays the integration name, so a metrics alert and a log query name the same thing. `deployment_environment` stays that key because the Knowledge Graph maps it.

```logql
{service_name="solaredge-exporter", job="integrations/solaredge"}
```

The exporter writes the inverter address into the local JSON file. That file is the on-host record. `loki.process "exporter"` in [fleet/solaredge.alloy](https://github.com/lewismc/solaredge-olly/blob/main/fleet/solaredge.alloy) masks the line on the way to Loki, after the label stages. `stage.regex` extracts the first IPv4 address into `ipv4`. `stage.metrics` increments `alloy_pii_ipv4_redacted_total` when that key is present. The series stays on Alloy's `/metrics` for 24 hours after the last match, and a config reload resets it. `stage.replace` then substitutes every IPv4 address with `*IPv4*`. The expression is the guide's IPv4 pattern wrapped in a capture group, which `stage.replace` requires. A second `stage.replace` substitutes the token after `Serial: ` with `*SERIAL*`. The port stays, so a masked target still reads `*IPv4*:502`. The listen address `127.0.0.1` matches the same IPv4 expression, so the startup line that records it is masked too. Alloy's own log pipeline is separate and has no replace stage.

The replacement stays inside the JSON string, so `| json` and the Modbus-error alert still parse the line.

```logql
{service_name="solaredge-exporter", job="integrations/solaredge"} |= `*IPv4*`
```

```logql
{service_name="solaredge-exporter", job="integrations/solaredge"} |~ `\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b`
```

Lines pushed after the pipeline is live match the first query. A dotted IPv4 in a line means that line was stored before the change. It stays until retention. Removing a stored line is a [log deletion request](https://grafana.com/docs/grafana-cloud/send-data/logs/delete-log-lines/). This work leaves stored lines in place.

The Alloy self-scrape drop list does not name `alloy_pii_ipv4_redacted_total`, so the counter is remote-written with the other Alloy metrics. There is no alert on it. On this host a match means the stage saw an address. The counter also moves for the listen address, because that is an IPv4 address too.

A failed Modbus read keeps the old message text and adds body fields. Read failures are at error level, except meter detection, which stays at warn. `phase` is `connect`, `common_block`, `poll`, or `meter_read`. `error_class` is `modbus_exception`, `timeout`, `connection_reset`, `connection_closed`, `connection_refused`, or `other`. A `modbus_exception` line also carries `modbus_function_code` and `modbus_exception_code`. Query them with `| json`.

```logql
{service_name="solaredge-exporter", job="integrations/solaredge"} | json | error_class=~".+"
```

`modbus_exception_code` `2` is an illegal data address, `4` a device failure, `6` a busy device. `timeout` and `connection_reset` point at the network or a busy inverter. `connection_refused` means nothing is listening.

A read failure after the redaction pipeline is live looks like this. The address is masked in `target` and in both places it appears in `message`. The fields a query filters on are unchanged.

```json
{"level":"error","target":"*IPv4*:502","phase":"poll","error_class":"connection_refused","time":"2026-11-15T04:47:05-08:00","message":"[*IPv4*:502] Error reading holding registers: dial tcp *IPv4*:502: connect: connection refused"}
```

A line stored before the pipeline went live still shows the raw address. Those lines are kept until retention, as described above.

Logs credentials are a different URL and instance id from metrics. `GRAFANA_CLOUD_LOKI_URL` ends in `/loki/api/v1/push`. `GRAFANA_CLOUD_LOKI_USERNAME` is the Loki instance id. The token needs `logs:write` and can be the same token as metrics when the policy has both scopes.

Alloy's own logs are a different stream. They keep `job="integrations/alloy"` and `collector_id="solaredge"`, and they carry the same four resource labels, with `service_name="alloy"`. They are described on [Fleet Management](https://github.com/lewismc/solaredge-olly/wiki/Fleet-Management).

**When exporter logs do not arrive.** Confirm the file tail and the Loki writer are healthy in the Alloy UI. Then check `logs:write`, the Loki instance id, and that the URL ends in `/loki/api/v1/push`.

## Reuse on a customer system

Pick two or three stream labels and stop. `service_name` plus `job` was enough to join logs to metrics, alerts, and SLOs. Parse structured fields from the body. A label that moves (a DHCP address, a container id) splits one service into many streams and then ages out of every query. Keep the line format stable when you add fields, so old queries still match.

Use one `stage.replace` expression per sensitive type, and run it before `loki.write`. A constant replacement is enough when a metric label or the stream already names the thing. This pipeline writes `*IPv4*` because the `inverter` series label is already `primary`. Reach for `Hash` in `stage.template` when a later query still groups by the hidden value, and keep the salt out of the repository. A salt in a public file, with a small input set such as a private IPv4 range, can be guessed by trying that set.

On a high-volume pipeline, `stage.match` runs the replace only for lines the selector matches. This exporter logs at startup and on errors, so the stages run on each line. The selector reads labels. `stage.labels` copies an extracted field onto the label set before a selector can match it.

A Kubernetes collector can import a mask module at a pinned revision and enable patterns with pod annotations. Pin the revision. Tracking `main` will change the patterns under you. This Pi runs the two replace stages in the fleet file. `stage.luhn` is the card-number stage, for a pipeline that can log a card number. Email, phone, and SSN stages belong on a pipeline that can log those values. The `serial` label on `Inverter_Info` is a metric label, so changing it is a relabel in the metrics pipeline. Geolocate lines carry city, region, and country. The public IP stays in the local cache.
