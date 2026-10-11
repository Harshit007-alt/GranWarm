#!/bin/bash
set -euo pipefail

echo "=========================================================="
echo " GranuWarm: Knative Serving + Kourier + Prometheus Setup  "
echo "=========================================================="

KNATIVE_VERSION="v1.13.0"

echo "[1/5] Installing Knative Serving CRDs..."
kubectl apply -f "https://github.com/knative/serving/releases/download/knative-${KNATIVE_VERSION}/serving-crds.yaml"
kubectl wait --for=condition=Established --all crd --timeout=120s

echo "[2/5] Installing Knative Serving Core..."
kubectl apply -f "https://github.com/knative/serving/releases/download/knative-${KNATIVE_VERSION}/serving-core.yaml"

echo "[3/5] Installing Kourier Networking Layer..."
kubectl apply -f "https://github.com/knative/net-kourier/releases/download/knative-${KNATIVE_VERSION}/kourier.yaml"

echo "[4/5] Configuring Knative Network & Domain..."
kubectl patch configmap/config-network \
    --namespace knative-serving \
    --type merge \
    --patch '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'

kubectl patch configmap/config-domain \
    --namespace knative-serving \
    --type merge \
    --patch '{"data":{"127.0.0.1.sslip.io":""}}'

echo "Waiting for Knative components to be ready..."
kubectl wait -n knative-serving --for=condition=Ready pods --all --timeout=300s || true

echo "[5/5] Deploying Prometheus Monitoring Stack..."
if ! command -v helm &> /dev/null; then
    echo "Installing Helm 3..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
helm repo update
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring --create-namespace \
    --set prometheus.prometheusSpec.scrapeInterval="2s" \
    --set prometheus.prometheusSpec.evaluationInterval="2s" \
    --set grafana.enabled=false

echo "=========================================================="
echo " Setup Complete! Cluster Pod Status:                      "
echo "=========================================================="
kubectl get pods -n knative-serving
kubectl get pods -n monitoring
