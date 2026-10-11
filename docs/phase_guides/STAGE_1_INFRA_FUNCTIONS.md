# 🏗️ STAGE 1: Infrastructure & Function Deployment

> **Assigned to:** Tijil Gupta — Cloud Native Infrastructure & Knative/Docker Lead
>
> **Phases:** 0 → 1 → 2 → 3 → 4
>
> **Estimated Duration:** 2–3 weeks

---

## Overview

This stage builds the entire cloud-native foundation that GranuWarm runs on. By the end, all 12 heterogeneous benchmark functions (F1–F12) will be deployed as Knative Services on a local KinD Kubernetes cluster, automatically scaling to zero when idle and scaling up on HTTP invocations.

---

## Phase 0 — Prerequisites

### 0.1 Learning Objectives

- Linux CLI proficiency (Bash navigation, process management, `$PATH`, environment variables)
- Python 3.11 core (asyncio, type hints, venv, pip)
- Git fundamentals (init, commit, branch, .gitignore)

### 0.2 Practical Steps

```bash
# 1. Ensure Ubuntu 22.04 LTS with ≥8 CPU cores, ≥16 GB RAM

# 2. Install system utilities
sudo apt update && sudo apt install -y \
    curl git htop jq build-essential \
    python3-pip python3-venv python3.11

# 3. Initialize repository
mkdir granuwarm && cd granuwarm
git init
echo "venv/\n__pycache__/\n*.pyc\nresults/raw/\n.env" > .gitignore

# 4. Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### 0.3 Verification Checklist

- [ ] `python3 --version` → ≥ 3.11
- [ ] `git --version` → git version 2.x
- [ ] `jq --version` → jq-1.x
- [ ] Virtual environment active (prompt shows `(venv)`)

### 0.4 Common Pitfalls

| Issue | Solution |
|:---|:---|
| Python < 3.11 | `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.11` |
| `pip install` permission error | Never use `sudo` inside venv |

---

## Phase 1 — Docker

### 1.1 Learning Objectives

- Container isolation (namespaces, cgroups, OverlayFS)
- Dockerfile syntax (`FROM`, `WORKDIR`, `COPY`, `RUN`, `CMD`)
- Multi-stage builds and slim images

### 1.2 Practical Steps

```bash
# Install Docker Engine v26+
sudo apt install -y docker.io
sudo usermod -aG docker $USER
newgrp docker
docker --version  # Verify ≥ 26.0
```

### 1.3 Create Base Dockerfiles

**`docker/base_python/Dockerfile`:**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
ENV PORT=8080
EXPOSE 8080
```

**`docker/base_node/Dockerfile`:**

```dockerfile
FROM node:20-slim
WORKDIR /app
RUN npm init -y
ENV PORT=8080
EXPOSE 8080
```

### 1.4 Build F1 (Hello World) and F3 (Image Resize)

```bash
# F1: Lightweight Node.js function
mkdir -p functions/f01_hello_world
cat > functions/f01_hello_world/Dockerfile << 'EOF'
FROM node:20-slim
WORKDIR /app
COPY package.json server.js ./
RUN npm install --production
ENV PORT=8080
EXPOSE 8080
CMD ["node", "server.js"]
EOF

# Build and test
docker build -t granuwarm/f01_hello_world:v1 functions/f01_hello_world/
docker run -d --name test_f1 -p 8081:8080 granuwarm/f01_hello_world:v1
curl http://localhost:8081
# Expected: {"message": "Hello from F1!", "timestamp": "..."}
docker stop test_f1 && docker rm test_f1
```

### 1.5 All 12 Function Images

| ID | Function | Runtime | Base Image | Key Dependencies | Target Size |
|:---:|:---|:---:|:---|:---|:---:|
| F1 | helloWorld | Node.js 20 | `node:20-slim` | minimal | < 200 MB |
| F2 | jsonTransform | Node.js 20 | `node:20-slim` | lodash | < 200 MB |
| F3 | imageResize | Python 3.11 | `python:3.11-slim` | Pillow, numpy | < 500 MB |
| F4 | imageFilter | Python 3.11 | `python:3.11-slim` | Pillow, numpy, scipy | < 600 MB |
| F5 | thumbnailGen | Python 3.11 | `python:3.11-slim` | Pillow | < 400 MB |
| F6 | mlInference | Python 3.11 | `python:3.11-slim` | scikit-learn, numpy, pandas | < 800 MB |
| F7 | sentimentAnalysis | Python 3.11 | `python:3.11-slim` | transformers, torch | < 2 GB |
| F8 | dataAggregate | Python 3.11 | `python:3.11-slim` | pandas, numpy | < 500 MB |
| F9 | csvParser | Python 3.11 | `python:3.11-slim` | pandas | < 400 MB |
| F10 | authService | Node.js 20 | `node:20-slim` | jsonwebtoken, bcrypt | < 250 MB |
| F11 | orderProcess | Python 3.11 | `python:3.11-slim` | requests, sqlalchemy | < 400 MB |
| F12 | notification | Node.js 20 | `node:20-slim` | firebase-admin | < 300 MB |

### 1.6 Verification

- [ ] `docker images | grep granuwarm` shows all 12 images
- [ ] Each image runs, responds on port 8080, and returns valid JSON
- [ ] All Python images use `python:3.11-slim` (< 150 MB base)
- [ ] All Node.js images use `node:20-slim` (< 200 MB base)

---

## Phase 2 — Kubernetes Concepts

### 2.1 Learning Objectives

- Core K8s abstractions: Pod, Deployment, Service, Namespace, ConfigMap
- `kubectl` CLI: `get`, `describe`, `apply`, `logs`, `delete`
- YAML manifest structure

### 2.2 Practical Steps

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
```

### 2.3 Key Concepts

```
┌─────────────────────────────────────┐
│         Kubernetes Cluster          │
│                                     │
│  ┌──────────┐    ┌──────────┐      │
│  │  Node 1  │    │  Node 2  │      │
│  │ ┌──────┐ │    │ ┌──────┐ │      │
│  │ │ Pod  │ │    │ │ Pod  │ │      │
│  │ │┌────┐│ │    │ │┌────┐│ │      │
│  │ ││ Ctr││ │    │ ││ Ctr││ │      │
│  │ │└────┘│ │    │ │└────┘│ │      │
│  │ └──────┘ │    │ └──────┘ │      │
│  └──────────┘    └──────────┘      │
│                                     │
│     Service (Load Balancer)         │
│     routes traffic → Pods           │
└─────────────────────────────────────┘
```

### 2.4 Verification

- [ ] `kubectl version --client` → client version v1.28+
- [ ] Can explain difference between Deployment (desired state) and Service (network endpoint)
- [ ] Understand label selectors for routing

---

## Phase 3 — KinD (Kubernetes-in-Docker)

### 3.1 Learning Objectives

- KinD local cluster provisioning
- Port mapping (host 80/443 → KinD node)
- Loading local Docker images into KinD nodes

### 3.2 Practical Steps

```bash
# Install KinD v0.22+
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64
chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind
```

#### Create `configs/cluster_config.yaml`

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: granuwarm-local
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
  - role: worker
```

```bash
# Create cluster
kind create cluster --config configs/cluster_config.yaml --name granuwarm-local

# Load all images
for img in $(docker images --format '{{.Repository}}:{{.Tag}}' | grep granuwarm); do
    kind load docker-image "$img" --name granuwarm-local
done
```

### 3.3 Verification

- [ ] `kubectl cluster-info --context kind-granuwarm-local` → cluster running
- [ ] `kubectl get nodes` → 1 control-plane + 3 workers, all `Ready`
- [ ] `kind get clusters` → lists `granuwarm-local`

---

## Phase 4 — Knative Serving

### 4.1 Learning Objectives

- Knative Service CRDs (Service → Configuration → Revision → Route)
- Knative Pod Autoscaler (KPA) and scale-to-zero
- Controlling `autoscaling.knative.dev/min-scale` annotation
- Kourier ingress + sslip.io DNS

### 4.2 Install Knative Serving v1.13 + Kourier

Create `scripts/setup_env.sh`:

```bash
#!/bin/bash
set -euo pipefail

echo "=== Installing Knative Serving v1.13 ==="
KNATIVE_VERSION="v1.13.0"

# Install Knative Serving CRDs
kubectl apply -f "https://github.com/knative/serving/releases/download/knative-${KNATIVE_VERSION}/serving-crds.yaml"
kubectl wait --for=condition=Established --all crd --timeout=120s

# Install Knative Serving core
kubectl apply -f "https://github.com/knative/serving/releases/download/knative-${KNATIVE_VERSION}/serving-core.yaml"

# Install Kourier networking layer
kubectl apply -f "https://github.com/knative/net-kourier/releases/download/knative-${KNATIVE_VERSION}/kourier.yaml"

# Configure Knative to use Kourier
kubectl patch configmap/config-network \
    --namespace knative-serving \
    --type merge \
    --patch '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'

# Configure default domain (sslip.io for local)
kubectl patch configmap/config-domain \
    --namespace knative-serving \
    --type merge \
    --patch '{"data":{"127.0.0.1.sslip.io":""}}'

# Wait for Knative components to be ready
kubectl wait -n knative-serving --for=condition=Ready pods --all --timeout=300s

echo "=== Installing Prometheus ==="
# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install Prometheus via Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring --create-namespace \
    --set prometheus.prometheusSpec.scrapeInterval="2s" \
    --set prometheus.prometheusSpec.evaluationInterval="2s" \
    --set grafana.enabled=false

echo "=== Setup complete ==="
kubectl get pods -n knative-serving
kubectl get pods -n monitoring
```

### 4.3 Create Knative Service YAMLs

Example for F1 — `functions/f01_hello_world/service.yaml`:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: f01-hello-world
  namespace: default
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/min-scale: "0"
        autoscaling.knative.dev/max-scale: "10"
        autoscaling.knative.dev/target: "10"
    spec:
      containers:
        - image: granuwarm/f01_hello_world:v1
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "128Mi"
              cpu: "500m"
```

> Repeat for all 12 functions with appropriate memory limits from Table 4.

### 4.4 Deploy & Test

```bash
# Deploy all functions
kubectl apply -f functions/

# Check all Knative services
kubectl get ksvc

# Test cold start
curl -H "Host: f01-hello-world.default.127.0.0.1.sslip.io" http://localhost:80
# First call: ~150ms (cold start)
# Second call: ~5ms (warm)

# Wait 60s, verify scale-to-zero
sleep 65
kubectl get pods  # Should show 0 pods for idle functions
```

### 4.5 Verification Checklist

- [ ] All 12 Knative services show `READY=True` in `kubectl get ksvc`
- [ ] First invocation of each function incurs cold-start delay matching Table 4 estimates
- [ ] Subsequent invocations return in < 10ms (warm)
- [ ] After 60s idle, pods scale to zero (`kubectl get pods` shows no function pods)
- [ ] `autoscaling.knative.dev/min-scale` annotation is patchable via `kubectl annotate`

### 4.6 Function Characteristics Reference (Table 4)

| ID | Function | Runtime | Memory | Cold-Start | Category |
|:---:|:---|:---:|:---:|:---:|:---:|
| F1 | helloWorld | Node.js 20 | 128 MB | ~150 ms | Lightweight |
| F2 | jsonTransform | Node.js 20 | 128 MB | ~200 ms | Lightweight |
| F3 | imageResize | Python 3.11 | 512 MB | ~1.2 s | Image |
| F4 | imageFilter | Python 3.11 | 512 MB | ~1.4 s | Image |
| F5 | thumbnailGen | Python 3.11 | 256 MB | ~0.9 s | Image |
| F6 | mlInference | Python 3.11 | 1024 MB | ~3.5 s | ML |
| F7 | sentimentAnalysis | Python 3.11 | 2048 MB | ~8.0 s | ML |
| F8 | dataAggregate | Python 3.11 | 512 MB | ~1.5 s | Data |
| F9 | csvParser | Python 3.11 | 256 MB | ~1.0 s | Data |
| F10 | authService | Node.js 20 | 256 MB | ~300 ms | API |
| F11 | orderProcess | Python 3.11 | 256 MB | ~0.8 s | API |
| F12 | notification | Node.js 20 | 256 MB | ~350 ms | API |

---

## ➡️ Handoff to Stage 2

Once all 12 functions deploy, respond to HTTP, and auto-scale to zero, notify **Ayush Rawat** to begin Phase 5 (Prometheus monitoring setup). The KinD cluster and Knative installation must be stable and reproducible via `scripts/setup_env.sh`.
