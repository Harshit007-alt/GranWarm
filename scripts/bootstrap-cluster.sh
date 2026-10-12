#!/bin/bash
set -euo pipefail

CLUSTER_NAME="granuwarm-local"

echo "=== [1/8] Deleting any stale cluster ==="
kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true

echo "=== [2/8] Creating cluster ==="
kind create cluster --config configs/cluster_config.yaml

echo "=== [3/8] Installing Knative CRDs ==="
kubectl apply -f "https://github.com/knative/serving/releases/download/knative-v1.13.0/serving-crds.yaml"
kubectl wait --for=condition=Established --all crd --timeout=120s

echo "=== [4/8] Installing Knative Serving + Kourier ==="
kubectl apply -f "https://github.com/knative/serving/releases/download/knative-v1.13.0/serving-core.yaml"
kubectl apply -f "https://github.com/knative/net-kourier/releases/download/knative-v1.13.0/kourier.yaml"

kubectl patch configmap/config-network -n knative-serving --type merge \
  --patch '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'
kubectl patch configmap/config-domain -n knative-serving --type merge \
  --patch '{"data":{"127.0.0.1.sslip.io":""}}'
kubectl patch configmap/config-deployment -n knative-serving --type merge \
  --patch '{"data":{"registries-skipping-tag-resolving":"index.docker.io,docker.io"}}'

echo "=== [5/8] Installing Prometheus (Helm) ==="
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set prometheus.prometheusSpec.scrapeInterval="2s" \
  --set prometheus.prometheusSpec.evaluationInterval="2s" \
  --set grafana.enabled=false

echo "=== [6/8] Applying ServiceMonitor for autoscaler ==="
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: knative-serving-metrics
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames: [knative-serving]
  selector:
    matchLabels: {app: autoscaler}
  endpoints:
    - port: http-metrics
      interval: 10s
      path: /metrics
EOF

echo "=== [7/8] Applying PodMonitor for user pods ==="
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: knative-user-pods
  namespace: monitoring
  labels:
    release: prometheus
spec:
  namespaceSelector:
    matchNames: [default]
  selector:
    matchExpressions:
      - key: serving.knative.dev/revision
        operator: Exists
  podMetricsEndpoints:
    - port: http-usermetric
      path: /metrics
      interval: 10s
EOF

echo "=== [8/8] Waiting for pods ==="
kubectl wait -n knative-serving --for=condition=Ready pods --all --timeout=300s || true
kubectl wait -n monitoring --for=condition=Ready pods --all --timeout=300s || true

echo ""
echo "=== Cluster ready ==="
kubectl get nodes
kubectl get pods -n knative-serving
kubectl get pods -n monitoring