#!/usr/bin/env python3
"""Check Prometheus readiness and GranuWarm's configured Knative metrics."""

import argparse
import json
import math
from pathlib import Path
import sys

import requests

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

from controller.monitor.prometheus_client import PrometheusMonitor  # noqa: E402


def _get(session, url, *, params=None):
    try:
        return session.get(url, params=params, timeout=(0.5, 2.0))
    except requests.RequestException as error:
        print(f"ERROR GET {url}: {error}")
        return None


def check_prometheus(url: str, service: str, namespace: str) -> int:
    if not PrometheusMonitor.DNS_LABEL_PATTERN.fullmatch(service):
        print(f"ERROR invalid Kubernetes service DNS label: {service!r}")
        return 1
    if not PrometheusMonitor.DNS_LABEL_PATTERN.fullmatch(namespace):
        print(f"ERROR invalid Kubernetes namespace DNS label: {namespace!r}")
        return 1

    url = url.rstrip("/")
    session = requests.Session()
    failed = False

    ready = _get(session, f"{url}/-/ready")
    if ready is None:
        print("/-/ready: unavailable")
        failed = True
    else:
        is_ready = ready.status_code == 200
        print(f"/-/ready: HTTP {ready.status_code} ({'ready' if is_ready else 'not ready'})")
        failed = failed or not is_ready

    metrics_response = _get(
        session, f"{url}/api/v1/label/__name__/values",
    )
    metric_names = set()
    if metrics_response is None or metrics_response.status_code != 200:
        status = (
            "unavailable" if metrics_response is None
            else f"HTTP {metrics_response.status_code}"
        )
        print(f"base metrics: unavailable ({status})")
        failed = True
    else:
        try:
            payload = metrics_response.json()
        except ValueError:
            payload = {}
        if (
            isinstance(payload, dict)
            and payload.get("status") == "success"
            and isinstance(payload.get("data"), list)
            and all(isinstance(name, str) for name in payload["data"])
        ):
            metric_names = set(payload["data"])
        else:
            print("base metrics: invalid Prometheus response")
            failed = True

    for metric in PrometheusMonitor.REQUIRED_BASE_METRICS:
        present = metric in metric_names
        print(f"base metric {metric}: {'present' if present else 'MISSING'}")
        failed = failed or not present

    for signal, template in PrometheusMonitor.QUERY_SCHEMA.items():
        query = (
            template.replace("{svc}", service)
            .replace("{namespace}", namespace)
        )
        response = _get(
            session, f"{url}/api/v1/query", params={"query": query},
        )
        required = signal in ("R_i", "M")
        if response is None or response.status_code != 200:
            status = (
                "unavailable" if response is None
                else f"HTTP {response.status_code}"
            )
            print(f"query {signal}: ERROR ({status}) query={query}")
            failed = failed or required
            continue

        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict) or payload.get("status") != "success":
            print(
                f"query {signal}: ERROR "
                f"(status={payload.get('status') if isinstance(payload, dict) else None!r}) "
                f"query={query}"
            )
            failed = failed or required
            continue

        data = payload.get("data")
        results = data.get("result") if isinstance(data, dict) else None
        if isinstance(results, list) and results:
            sample = results[0]
            value = sample.get("value") if isinstance(sample, dict) else None
            if required and isinstance(value, list) and len(value) > 1:
                try:
                    finite = math.isfinite(float(value[1]))
                except (TypeError, ValueError):
                    finite = False
                if not finite:
                    print(
                        f"query {signal}: ERROR (non-finite value) "
                        f"query={query}"
                    )
                    failed = True
                    continue
            print(f"query {signal}: {results[0]!r}")
        else:
            print(f"query {signal}: EMPTY query={query}")
            failed = failed or required

    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Prometheus base URL")
    parser.add_argument("--service", required=True, help="Knative service name")
    parser.add_argument(
        "--namespace",
        help="Kubernetes namespace (defaults to configs/prometheus.json)",
    )
    args = parser.parse_args(argv)

    config_path = REPOSITORY_ROOT / "configs" / "prometheus.json"
    with config_path.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    namespace = args.namespace or config["namespace"]
    return check_prometheus(args.url, args.service, namespace)


if __name__ == "__main__":
    raise SystemExit(main())
