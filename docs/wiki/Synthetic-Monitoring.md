# Synthetic Monitoring

## The product

[Synthetic Monitoring](https://grafana.com/docs/grafana-cloud/testing/synthetic-monitoring/) runs a check from a probe on a schedule and records whether the check passed. A private probe is an agent you run, pointed at a target the public probes cannot reach. The check result is a metric (`probe_success`) and a log. It answers "could the probe fetch this URL". It does not answer "did the device produce a new sample". Those are different questions, and a check that only fetches `/metrics` will stay green while the device is stuck, as long as the last scrape is still being served.

## This stack

[synthetic/exporter-http.yaml](https://github.com/lewismc/solaredge-olly/blob/main/synthetic/exporter-http.yaml) is a MultiHTTP check, job `solaredge-exporter-metrics`, every 60 seconds, timeout 15 seconds, probe `solaredge`. The assertions require HTTP 200 and a body that contains `SunSpec_DID{`, `Status{`, `AC_Power{`, and `AC_Power_SF{`. `AC_Power{` does not match `AC_Power_SF`. The check does not read phase B, phase C, a meter, `/health`, or `Modbus_Read_OK`. A dead Modbus session after the first good poll still passes, because those series stay on the exporter until the process restarts.

The request URL is `http://127.0.0.1:2112/metrics`. The API rejects the single-label hostname on a MultiHTTP request. The check target stays `http://solaredge-exporter:2112/metrics`. The check label `service_name=solaredge-exporter` matches the exporter log stream, so the check does not become a second service.

The probe runs on the Pi. The published agent image has no armv6 build, so the binary is cross-compiled and run by hand. A release does not ship it. `alertSensitivity` is `none`, so the check raises no alerts of its own. The pass and the fail are visible as `probe_success`.

```bash
gcx synthetic-monitoring checks create -f synthetic/exporter-http.yaml
```

On Compose, the agent image is `grafana/synthetic-monitoring-agent:v0.68.0`. Its command includes `--blocked-nets=0.0.0.0/32`, which turns off the agent's default `10.0.0.0/8` denylist so the probe can open the Compose address. `SM_API_SERVER` is the gRPC host only, with no scheme and no port. `SM_API_TOKEN` is the one-time probe token, not a Grafana access-policy token.

## Reuse on a customer system

Point a private probe at the thing the public probes cannot see, and label the check with the same `service_name` as the service. Decide what the check is allowed to miss, and write that down: a body assertion on a cached series does not prove the last poll. A forced failure (stop the process, watch `probe_success` drop, start it, watch it recover) is the test that the probe is reaching the target. `alertSensitivity: none` is right when the SLO and the alert rules already page. Two pagers on one outage is how people mute both.
