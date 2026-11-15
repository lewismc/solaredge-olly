# Traces

## The product

[OpenTelemetry](https://opentelemetry.io/docs/languages/python/) is the vendor-neutral API and SDK an application uses to create spans. A span is one timed operation, such as an HTTP call, with attributes. OTLP is the protocol that carries spans to a collector or a backend. Grafana Cloud's OTLP gateway accepts them with a stack instance id and an access-policy token.

Tempo stores the traces. [Application Observability](https://grafana.com/docs/grafana-cloud/monitor-applications/application-observability/) reads the spans and builds the RED metrics (rate, errors, duration) from them with the Tempo metrics-generator, plus the service map and the operation list. Traces Drilldown explores the spans one at a time.

Alloy receives OTLP with [`otelcol.receiver.otlp`](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.receiver.otlp/), batches with `otelcol.processor.batch`, and forwards with [`otelcol.exporter.otlphttp`](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlphttp/). The credentials go through [`otelcol.auth.basic`](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.auth.basic/).

## This stack

[geolocate/server.py](https://github.com/lewismc/solaredge-olly/blob/main/geolocate/server.py) runs two outbound calls: the ipinfo lookup and the Open-Meteo forecast. Each runs inside a manual CLIENT span. The span carries the HTTP method, the host, the path, and the status code. It does not carry the query string, the response body, the public IP, or the coordinates.

The process sends OTLP/HTTP to `127.0.0.1:4318`, which is Alloy, with no credentials. Alloy adds the Grafana Cloud token on the way out. The pipeline is in [fleet/solaredge.alloy](https://github.com/lewismc/solaredge-olly/blob/main/fleet/solaredge.alloy), so Fleet Management delivers it with the rest of the collector config. The resource attributes are `service.name=solaredge-geolocate`, `service.namespace=solaredge`, and `deployment.environment.name=home`.

Tracing is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. The Pi sets it in `/etc/solaredge/solaredge.env`. With the variable unset, the API has no provider and the calls are unchanged. An export failure is logged by OpenTelemetry in the background and never fails the lookup. The Mac tests showed no added delay with an unreachable endpoint.

The dependencies are pinned in [geolocate/requirements.txt](https://github.com/lewismc/solaredge-olly/blob/main/geolocate/requirements.txt). [deploy/pi/update.sh](https://github.com/lewismc/solaredge-olly/blob/main/deploy/pi/update.sh) installs them into the geolocate venv with `--only-binary=:all:`, so no source build runs as root. It records the installed file in a stamp. If the install fails, the running `server.py` stays in place.

Alloy's allowlist links the four OTel components. Its OTel engine stays empty. The memory readings are on [Alloy memory](Alloy-memory).

Not yet live at the time of writing: the Grafana Cloud OTLP token on the Pi, the Fleet Management push of the traces pipeline, and the first span in Tempo.

## Reuse on a customer system

- Instrument the app with the OTel SDK and export OTLP to a local collector, not to the backend. The collector holds the token and the app holds none.
- Give the collector only the OTel components it needs. A slim build that omits the OTel engine still runs the native pipeline.
- Put only host, path, and status code on HTTP client spans. Query strings and response bodies often carry personal data or coordinates.
- Make tracing opt-in with an endpoint variable. An empty value turns it off, and a dead endpoint must never fail the request.
- Install dependencies from wheels only, and pin them. Keep the old code running when the install fails.
- Check the span names in Tempo with a TraceQL query on `resource.service.name` before you build dashboards on them.
