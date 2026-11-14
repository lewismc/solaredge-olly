# Notifications

## The product

A [contact point](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/) is where Grafana delivers an alert. A [notification policy](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/create-notification-policy/) is a tree of matchers that pick the contact point. The default route catches everything that no child matches. `set` replaces the whole tree, so a file that only contains your route will delete every other route on the stack. Secrets (a webhook URL, a token) belong in the contact point's secure fields, filled at apply time, not in the file you commit.

## This stack

[notifications/slack-contact-point.yaml](https://github.com/lewismc/solaredge-olly/blob/main/notifications/slack-contact-point.yaml) is the contact point `solaredge-slack`, type `slack`, an incoming webhook bound to the private channel `#alerts` in the SolarEdge Observability Slack workspace. The webhook URL, not the recipient field, chooses the channel. The URL is `${SLACK_WEBHOOK_URL}` and lives in `.env`. It is never committed.

[notifications/policy-tree.yaml](https://github.com/lewismc/solaredge-olly/blob/main/notifications/policy-tree.yaml) is the whole tree. The default receiver stays `grafana-default-email`. One child route matches `service_name=solaredge-exporter` and sends to `solaredge-slack`, grouping by `alertname` and `grafana_slo_uuid`, with a 30 second group wait, a 5 minute group interval, and a 12 hour repeat. The five rules and both SLOs' burn-rate alerts carry that label, so no rule names a contact point. Merge any other route on the stack into the file before setting it.

```bash
set -a; . ./.env; set +a
envsubst '$SLACK_WEBHOOK_URL' < notifications/slack-contact-point.yaml | gcx alert contact-points create -f -
gcx alert notification-policies set -f notifications/policy-tree.yaml
```

`envsubst` with no argument list replaces every `$name`, including the `$query` and `$value` inside the Go template. The quotes around `$SLACK_WEBHOOK_URL` limit it to that one variable.

Slack bolds with a single asterisk. The message template uses `*FIRING: name*` and then the summary. It then prints each entry of `.Values` as `query = value`. Grafana's default template uses `**Firing**`, which Slack shows with the asterisks, and it prints `Value: [no value]` when a notification has no samples. The title still uses Grafana's default title.

The webhook posts only to the channel it was created for. A workspace that requires admin approval for apps will not hand out a webhook URL. A private channel appears in the picker only when you are a member of it.

## Reuse on a customer system

One label, one route, many rules. Commit the policy tree, not the secret, and review the whole tree before every `set`. Render the message in the destination's markup, not Markdown. Put the query name in the ref id so the delivered value is readable. Test through Grafana's receiver test with the saved template included. A test that omits `text` and `title` renders the built-in message and tells you nothing about yours.
