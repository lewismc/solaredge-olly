# Fleet Management

## The product

Fleet Management stores Alloy configuration in Grafana Cloud and delivers it to collectors. A collector runs a small local bootstrap, a `remotecfg` block, and polls for the pipelines that match its attributes. One pipeline can target many collectors. The collector id is how you tell two installs apart. Secrets stay on the collector. The remote config should not contain them.

## This stack

[alloy/config.alloy](https://github.com/lewismc/solaredge-olly/blob/main/alloy/config.alloy) is only the bootstrap. It registers collector id `solaredge` with attribute `integration=solaredge`, and it ships Alloy's own logs. [fleet/solaredge.alloy](https://github.com/lewismc/solaredge-olly/blob/main/fleet/solaredge.alloy) is the pipeline. [`.github/workflows/fleet-management-sync.yml`](https://github.com/lewismc/solaredge-olly/blob/main/.github/workflows/fleet-management-sync.yml) publishes it with `grafana/fleet-management-sync-action` to namespace `solaredge-olly`, matcher `integration=solaredge`. Pull requests dry-run. Pushes to `main` sync. The repository secrets are `FM_URL` (the base URL from Connections, Fleet Management, API), `FM_USERNAME` (the numeric instance id; the stack slug is rejected), and `FM_TOKEN` (the token alone, with `fleet-management:write`, no `username:token` prefix and no trailing newline).

```alloy
remotecfg {
  url            = sys.env("FLEET_MANAGEMENT_URL")
  id             = "solaredge"
  poll_frequency = "1m"
  attributes     = { integration = "solaredge" }
}
```

Fleet Management loads the pipeline inside `declare "solaredge"`. The module import is named `solaredge_module`, the file has no `livedebugging` block, and a service block is not allowed inside a module. A collector that does not run this bootstrap gets no scrape.

Alloy's own metrics arrive from two pipelines. The generated `self_monitoring_metrics` pipeline ships a health keep-list. `fleet/solaredge.alloy` scrapes `prometheus.exporter.self` every 60 seconds and ships every other family, with the same `job="integrations/alloy"`, `instance`, and `collector_id` labels. The second pipeline drops the keep-list by name so the two never write the same series. That regex is a copy. Update it if the generated pipelines are recreated. Metrics for components this collector does not run, such as `cluster_*` and `otelcol_*`, do not exist until those components run.

The generated `self_monitoring_logs_linux` pipeline reads the systemd journal. The Compose container has no journal, so the bootstrap `logging` block tees Alloy's own logs to Loki with `job="integrations/alloy"` and `collector_id="solaredge"`. Leave the generated pipeline enabled: disabling it affects every Linux collector on the stack. Query `{job="integrations/alloy", collector_id="solaredge"}`. An unhealthy `loki.source.journal` in the Alloy UI is expected in that container.

## Reuse on a customer system

The bootstrap is the only file on the host. Everything else is a pull request. Pin the collector id so a recreate does not register a second collector. Match pipelines on an attribute you control, not on a hostname. Two collectors with the same id will fight over the assignment. Generated self-monitoring pipelines are shared, so do not disable one to fix a single host. When you add a second writer of the same series, drop the overlap by name and treat that list as a copy you have to maintain.
