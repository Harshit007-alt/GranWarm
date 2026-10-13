# GranuWarm — Local Development Setup Guide

This guide walks you through setting up a complete local environment for
GranuWarm on **Windows + WSL2 + Ubuntu**. By the end, you'll have:

- A local Kubernetes cluster (via KinD)
- Knative Serving + Kourier for serverless functions
- Prometheus for telemetry
- The GranuWarm controller able to talk to the cluster

**Time to complete:** ~45–60 minutes first time.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Fix WSL2 Memory Allocation](#2-fix-wsl2-memory-allocation)
3. [Install Docker](#3-install-docker)
4. [Install kind](#4-install-kind)
5. [Install kubectl](#5-install-kubectl)
6. [Install Helm](#6-install-helm)
7. [Verify All Tools](#7-verify-all-tools)
8. [Create the KinD Cluster](#8-create-the-kind-cluster)
9. [Install Knative + Prometheus](#9-install-knative--prometheus)
10. [Connect the GranuWarm Controller](#10-connect-the-granuwarm-controller)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

Before starting, confirm you have:

| Requirement | Minimum | How to check |
|---|---|---|
| Windows 10/11 with WSL2 | WSL2 enabled | `wsl --status` in PowerShell |
| Ubuntu on WSL2 | 20.04+ | `lsb_release -a` in Ubuntu |
| Physical RAM | 8 GB+ | Task Manager → Performance → Memory |
| Free disk space | 20 GB+ | `df -h` in Ubuntu |
| Internet access | Required | `curl -I https://github.com` |

If you don't have WSL2 or Ubuntu installed, run this from **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu
```

Then reboot. After reboot, Ubuntu will launch and prompt you to create a Unix user.

---

## 2. Fix WSL2 Memory Allocation

**Why this matters:** WSL2 defaults to using only ~50% of your Windows RAM.
On an 8 GB machine, that means only ~3.5 GB inside Ubuntu — not enough to run
the full GranuWarm cluster (1 control-plane + 3 workers + Knative + Prometheus).

### Step 2.1 — Create `.wslconfig` on the Windows side

From your **Ubuntu terminal**, run:

```bash
# Find your Windows user folder
cmd.exe /c "echo %USERPROFILE%"
```

Note the output (e.g. `C:\Users\user`). Then create the config:

```bash
cat > /mnt/c/Users/<YOUR_WINDOWS_USER>/.wslconfig <<'EOF'
[wsl2]
memory=6GB
swap=2GB
processors=4
EOF
```

Replace `<YOUR_WINDOWS_USER>` with the actual username from the previous step.

**Adjust `processors`** to match your CPU core count:

```bash
nproc
```

If `nproc` returns 2, set `processors=2`. If 4 or more, `processors=4` is fine.

### Step 2.2 — Verify the file

```bash
cat -A /mnt/c/Users/<YOUR_WINDOWS_USER>/.wslconfig
```

Expected output (each line ends with `$`, no `^M`):

```
[wsl2]$
memory=6GB$
swap=2GB$
processors=4$
```

If you see `^M$` (Windows line endings) or a BOM at the start, recreate it with:

```bash
printf '[wsl2]\nmemory=6GB\nswap=2GB\nprocessors=4\n' > /mnt/c/Users/<YOUR_WINDOWS_USER>/.wslconfig
```

### Step 2.3 — Restart WSL2

This will close your Ubuntu terminal. Save any work first.

```bash
/mnt/c/Windows/System32/wsl.exe --shutdown
```

Wait 10 seconds. Reopen Ubuntu from the Windows Start menu.

### Step 2.4 — Verify

```bash
free -h
```

You should see `total` around **5.8–6.0 GiB** (not 3.5 GiB). If it still shows 3.5 GiB, see the [Troubleshooting](#11-troubleshooting) section.

---

## 3. Install Docker

Docker is the container runtime. KinD creates Kubernetes nodes as Docker containers, so Docker must be installed and running.

### Option A — Docker Desktop (recommended for Windows/WSL2)

1. Download Docker Desktop: https://www.docker.com/products/docker-desktop/
2. Run the installer, choose **"Use WSL 2 instead of Hyper-V"** when prompted.
3. Reboot if asked.
4. Open **Docker Desktop** from the Start menu and wait for the whale icon in the system tray to stop animating.
5. In Docker Desktop settings → **Resources** → **WSL Integration**, enable integration with your Ubuntu distro.
6. Verify from Ubuntu:

```bash
docker --version
docker ps
```

`docker ps` should show an empty table (headers only).

### Option B — Native Docker in Ubuntu (if you don't want Docker Desktop)

```bash
sudo apt update
sudo apt install docker.io -y
sudo systemctl start docker
sudo systemctl enable docker

# Add yourself to the docker group (avoids sudo on every command)
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker ps
```

### Permission error?

If `docker ps` says "permission denied":

```bash
sudo usermod -aG docker $USER
newgrp docker
docker ps
```

If it says "Cannot connect to the Docker daemon":

```bash
# For Docker Desktop: open it from the Start menu and wait
# For native Docker:
sudo systemctl start docker
```

---

## 4. Install kind

KinD (Kubernetes in Docker) runs a full Kubernetes cluster inside Docker containers.

```bash
# Download the latest binary
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64

# Make it executable and move to PATH
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Verify
kind --version
```

Expected: `kind v0.3x.x ... linux/amd64`

---

## 5. Install kubectl

`kubectl` is the CLI for talking to the cluster.

```bash
# Download the latest stable version
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"

# Make it executable and move to PATH
chmod +x kubectl
sudo mv ./kubectl /usr/local/bin/kubectl

# Verify
kubectl version --client
```

Expected: `Client Version: v1.3x.x ...`

> **Tip:** If you accidentally download `kubectl` into the repo folder and
> commit it, add `kubectl` to `.gitignore` and move the binary to
> `/usr/local/bin/`. Never commit tool binaries.

---

## 6. Install Helm

Helm is used by `scripts/setup_env.sh` to install Prometheus.

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify
helm version
```

Expected: `version.BuildInfo{Version:"v3.x.x", ...}`

---

## 7. Verify All Tools

Run this checklist before creating the cluster:

```bash
docker --version          # Docker 2x.x.x
docker ps                 # empty table, no errors
kind --version            # kind v0.3x.x
kubectl version --client  # Client Version: v1.3x.x
helm version              # v3.x.x
nproc                     # your CPU count
free -h                   # total ~5.8–6.0 GiB
```

Also confirm ports 80 and 443 are free (your cluster will bind them):

```bash
sudo lsof -i :80
sudo lsof -i :443
```

Both should return nothing. If something is using them (e.g. Apache, nginx), stop it first.

---

## 8. Create the KinD Cluster

From the repo root:

```bash
cd /mnt/c/Users/<YOUR_WINDOWS_USER>/Documents/GitHub/GranWarm

kind create cluster --config configs/cluster_config.yaml
```

Expected output ends with:

```
Set kubectl context to "kind-granuwarm-local"
```

Verify nodes:

```bash
kubectl get nodes
```

You should see **4 nodes** — 1 control-plane + 3 workers — all `Ready`:

```
NAME                          STATUS   ROLES           AGE   VERSION
granuwarm-local-control-plane Ready    control-plane   ...   v1.3x.x
granuwarm-local-worker        Ready    <none>          ...   v1.3x.x
granuwarm-local-worker2       Ready    <none>          ...   v1.3x.x
granuwarm-local-worker3       Ready    <none>          ...   v1.3x.x
```

Check memory headroom after cluster creation:

```bash
free -h
```

You should still have ~3 GB available.

---

## 9. Install Knative + Prometheus

The repo provides `scripts/setup_env.sh`, which installs:

- Knative Serving CRDs and core
- Kourier ingress
- kube-prometheus-stack (Prometheus + exporters)

Run it:

```bash
bash scripts/setup_env.sh
```

This takes **5–10 minutes**. In a second terminal, you can watch progress:

```bash
watch -n 2 kubectl get pods -A
```

When done, verify:

```bash
kubectl get pods -n knative-serving
kubectl get pods -n monitoring
```

All pods should be `Running` (or `Completed` for short-lived jobs).

> **If any pod is stuck in `Pending` or `CrashLoopBackOff`**, it's usually a
> memory issue. See [Troubleshooting](#11-troubleshooting).

---

## 10. Connect the GranuWarm Controller

### Step 10.1 — Point kubectl at the cluster

The cluster's kubeconfig is already merged into `~/.kube/config` by kind.
Verify:

```bash
kubectl config current-context
```

Expected: `kind-granuwarm-local`

### Step 10.2 — Create a `.env` file

In the repo root, create `.env`:

```bash
cat > .env <<EOF
K8S_SERVER=https://127.0.0.1:6443
K8S_TOKEN=$(kubectl get secret default-token -o jsonpath='{.data.token}' 2>/dev/null | base64 --decode)
K8S_CA_CERT_FILE=$HOME/.kube/ca.crt
EOF
```

> If `default-token` doesn't exist (newer Kubernetes versions use TokenRequest API),
> the simplest alternative is to let the Python Kubernetes client read
> `~/.kube/config` directly. Set `KUBECONFIG` instead:
>
> ```bash
> echo "KUBECONFIG=$HOME/.kube/config" >> .env
> ```

Add `.env` to `.gitignore`:

```bash
echo ".env" >> .gitignore
```

### Step 10.3 — Run the controller in dry-run mode

```bash
source .venv/Scripts/activate    # or .venv/bin/activate on native Linux
python -m controller.main --mode dry_run
```

This reads Prometheus and computes decisions without touching the cluster.

### Step 10.4 — Run in live mode (optional)

> **Caution:** The live actuator is a prototype (no retries, no reconciliation,
> no idempotency per the audit). Only run live if you know what you're doing.

```bash
python -m controller.main --mode live
```

### Step 10.5 — Send live workload through Knative ingress

Run these commands from **WSL**, where `kubectl` can access the KinD cluster.
Check that the services are ready:

```bash
kubectl config current-context
kubectl get ksvc
```

In a dedicated WSL terminal, forward Kourier's HTTP port to WSL localhost:

```bash
kubectl get svc -n kourier-system
kubectl port-forward -n kourier-system svc/kourier 8080:80
```

Keep that terminal open. In a second WSL terminal, verify one service through
the same forwarded port:

```bash
curl -i -H "Host: f01-hello-world.default.127.0.0.1.sslip.io" \
  http://127.0.0.1:8080/
```

Then run the workload generator against that exact URL:

```bash
python workload/generator.py \
  --profile W3 \
  --duration 120 \
  --base-url http://127.0.0.1:8080 \
  --output results/raw/live_W3.csv
```

The generator sets the Knative service `Host` header for each function and
records HTTP responses separately from connection errors. A blank
`status_code` with an `error` in the CSV means the request did not receive an
HTTP response; it is not a synthetic status. A successful `curl` from Git
Bash/Windows does not establish that `localhost` from WSL reaches the same
port, so run both the port-forward and test curl in WSL.

Press Ctrl+C to stop early; outstanding requests are cancelled and the CSV is
closed cleanly. Connection errors usually mean the port-forward stopped, the
generator is targeting a different port, or the request is being run from a
different environment than the port-forward.

---

## 11. Troubleshooting

### WSL2 memory still shows 3.5 GiB after restart

**Cause:** `.wslconfig` not read (wrong location, wrong encoding, or WSL not fully shut down).

**Fix:**
```bash
# Confirm location and content
ls -la /mnt/c/Users/<YOUR_WINDOWS_USER>/.wslconfig
cat -A /mnt/c/Users/<YOUR_WINDOWS_USER>/.wslconfig

# Look for ^M (CRLF) or BOM at the start
# If found, recreate with printf:
printf '[wsl2]\nmemory=6GB\nswap=2GB\nprocessors=4\n' > /mnt/c/Users/<YOUR_WINDOWS_USER>/.wslconfig

# Full shutdown (from PowerShell is more reliable)
# In PowerShell:
wsl --shutdown
```

Wait 15 seconds, reopen Ubuntu, check `free -h`.

### `kind: command not found`

Re-run the install step. Confirm `/usr/local/bin/kind` exists:

```bash
ls -la /usr/local/bin/kind
echo $PATH   # should include /usr/local/bin
```

### `docker: command not found`

Run the Docker commands from your **Ubuntu (WSL) terminal**, not from a shell
that is not configured for Docker. From PowerShell, open the Ubuntu terminal with:

```powershell
wsl -d Ubuntu
```

In Ubuntu, check whether the Docker CLI is available:

```bash
command -v docker
docker --version
```

If `command -v docker` prints nothing:

1. Open Docker Desktop from the Windows Start menu and wait for it to finish starting.
2. Go to **Settings → Resources → WSL Integration** and enable integration for
   the Ubuntu distro you use.
3. In PowerShell, restart WSL with `wsl --shutdown`, then reopen Ubuntu and retry
   the checks above.

Do not install a second Docker Engine with `apt` when using Docker Desktop; enable
WSL integration instead. If the CLI is found but Docker commands report that they
cannot connect to the daemon, see [Cannot connect to the Docker daemon](#cannot-connect-to-the-docker-daemon).

### `Cannot connect to the Docker daemon`

Docker Desktop isn't running. Open it from the Start menu and wait for the whale icon to stop animating.

### `kind create cluster` fails with port bind error

Ports 80 or 443 are in use. Check:

```bash
sudo lsof -i :80
sudo lsof -i :443
```

Stop whatever is using them, or edit `configs/cluster_config.yaml` to use different host ports (and update `config-domain` accordingly in `scripts/setup_env.sh`).

### Nodes stuck in `NotReady`

Usually CNI (networking) not yet initialized. Wait 60 seconds, then:

```bash
kubectl get pods -n kube-system
```

If `kindnet` or similar is `CrashLoopBackOff`, check `free -h` — you may be out of memory.

### Pods in `Pending` or `OOMKilled`

Memory pressure. Check:

```bash
free -h
kubectl describe pod <pod-name> -n <namespace> | grep -A5 Events
```

**Fixes:**
- Trim the cluster: edit `configs/cluster_config.yaml`, remove two worker nodes, and recreate.
- Reduce Prometheus memory in `scripts/setup_env.sh`:
  ```bash
  --set prometheus.prometheusSpec.resources.requests.memory="256Mi" \
  --set prometheus.prometheusSpec.resources.limits.memory="512Mi"
  ```

### Delete the cluster and start over

```bash
kind delete cluster --name granuwarm-local
kind create cluster --config configs/cluster_config.yaml
```

To delete all kind clusters:

```bash
kind delete clusters --all
```

### Reset everything

```bash
# Remove cluster
kind delete cluster --name granuwarm-local

# Stop Docker (optional)
# Open Docker Desktop → Troubleshoot → Restart

# Recreate
kind create cluster --config configs/cluster_config.yaml
bash scripts/setup_env.sh
```

---

## Appendix A — Quick Command Reference

```bash
# Cluster lifecycle
kind create cluster --config configs/cluster_config.yaml
kind delete cluster --name granuwarm-local
kind get clusters

# Inspect cluster
kubectl get nodes
kubectl get pods -A
kubectl cluster-info

# Knative
kubectl get ksvc -A
kubectl get pods -n knative-serving
kubectl get pods -n monitoring

# Controller
python -m controller.main --mode dry_run
python -m controller.main --mode live

# Simulator (no cluster needed)
python -m pytest tests -q
python simulator/run_sim.py --workload W3 --policy granuwarm --duration 300 --seed 42
```

---

## Appendix B — Architecture Recap

```
Windows host (8 GB RAM)
└── WSL2 (6 GB allocated via .wslconfig)
    └── Ubuntu
        └── Docker
            └── KinD cluster "granuwarm-local"
                ├── control-plane node (Docker container)
                ├── worker node 1 (Docker container)
                ├── worker node 2 (Docker container)
                └── worker node 3 (Docker container)
                    ├── Knative Serving (serverless layer)
                    ├── Kourier (ingress)
                    ├── Prometheus (telemetry)
                    └── Function pods (f01–f12)
```

The GranuWarm controller reads from Prometheus and patches Knative
`min-scale` annotations to control prewarming under a memory budget.

---

## Appendix C — Skip the Live Path (Fastest Option)

If you only want to understand GranuWarm's logic — not run it against a real
cluster — you can skip Docker, kind, Knative, and Prometheus entirely. The
simulator is pure Python:

```bash
cd /mnt/c/Users/<YOUR_WINDOWS_USER>/Documents/GitHub/GranWarm
source .venv/Scripts/activate

python -m pytest tests -q
python simulator/run_sim.py --workload W3 --policy granuwarm --duration 300 --seed 42
```

Given that the live actuator is a prototype, the simulator is where most of the
meaningful development happens today.

---

```
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
```

# 1. Build the image with the exact tag from service.yaml
docker build -t granuwarm/f01_hello_world:v1 functions/f01_hello_world/

# 2. Load it into the kind cluster
kind load docker-image granuwarm/f01_hello_world:v1 --name granuwarm-local

# 3. Apply the Knative Service
kubectl apply -f functions/f01_hello_world/service.yaml

# 4. Watch the pod come up
kubectl get pods -w

# 5. Check the Knative Service:
kubectl get ksvc