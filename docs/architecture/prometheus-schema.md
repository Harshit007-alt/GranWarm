# Prometheus telemetry schema

The live controller expects the following metrics to be present in the
Prometheus metric-name index at startup:

- `revision_app_request_count` for invocation rate (`R_i`);
- `activator_request_count` for the cold-start-related proxy (`C_i`);
- `container_memory_working_set_bytes` and
  `kube_pod_container_resource_limits` for memory pressure (`M`).

Queries use Knative's `service_name` label for request metrics. The memory
query scopes both metrics to the configured Kubernetes namespace and pods
whose names begin with `<service_name>-`. This assumes the deployed Knative
revision pod names start with their service name and that kube-state-metrics
exports resource limits with `resource="memory"` and `unit="byte"`.

| Signal | Query | Meaning and normalization |
| --- | --- | --- |
| `R_i` | `sum(rate(revision_app_request_count{service_name="<service>"}[1m])) or vector(0)` | Requests/second, divided by the configured historical max rate and clamped to `[0,1]`. `or vector(0)` represents an idle or scaled-to-zero service as zero. |
| `C_i` | `sum(increase(activator_request_count{service_name="<service>"}[60s])) or vector(0)` | **Proxy, not a direct cold-start count:** requests sent through the Knative Activator in the last 60 seconds, clamped to `[0,1]`. Validate the metric and labels against the deployed Knative release. |
| `M` | `sum(container_memory_working_set_bytes{namespace="<namespace>",pod=~"<service>-.*",container!=""}) / sum(kube_pod_container_resource_limits{namespace="<namespace>",pod=~"<service>-.*",resource="memory",unit="byte"}) or vector(0)` | Working-set bytes divided by configured memory-limit bytes for matching pods, clamped to `[0,1]`. No matching pods yields zero. |

The `sum(up)` health query is checked separately on each non-mock fetch.
It detects a Prometheus instance with no successful scrape targets, so the
`or vector(0)` in `R_i` cannot by itself mask a completely broken scrape.
This is a general scrape-health guard; deployments with unrelated healthy
targets should additionally monitor the Knative scrape targets.

The service and namespace substitutions must each be a Kubernetes DNS label
(lowercase letters, digits, and internal hyphens; at most 63 characters).
The local controller defaults live in [configs/prometheus.json](../../configs/prometheus.json);
CLI flags `--prometheus-url` and `--prometheus-namespace` override those
values.

## Deployment assumptions to verify

- Knative exposes `activator_request_count` with a `service_name` label.
  Its rate indicates Activator-routed requests and can include cold paths
  other than scale-from-zero; treat `C_i` as a proxy.
- Prometheus scrapes revision request metrics and kube-state-metrics
  container limits. The supplied monitors currently select Knative
  autoscaler targets in `knative-serving` and function pods in `default`.
- If the Knative release does not attach `service_name` or pod naming/metric
  labels differ, update these selectors to that release's exported labels.
