# Knative + Kind Local Image Registry Setup

## Context

I'm working on a GranuWarm research project that evaluates serverless prewarming strategies. I need to run live experiments on a Kubernetes cluster where:
- A traffic generator sends HTTP requests to Knative services
- Controller reads real Prometheus metrics (no mocks)
- Controller actuates Knative services based on metrics
- I measure actual latency, cold starts, and memory usage

## Current Setup

**What's working:**
- ✅ 2-node Kind cluster running (granuwarm-local-control-plane, granuwarm-local-worker)
- ✅ Knative Serving v1.11 installed
- ✅ Prometheus v2.45 running in monitoring namespace
- ✅ 10 Docker images built locally (granuwarm/f01_hello_world:v1, etc.)
- ✅ Images loaded into Kind nodes using `kind load docker-image`
- ✅ Traffic generator implemented (workload/generator.py)
- ✅ Controller works (tested in live mode, successfully scaled services)

**What's NOT working:**
- ❌ Knative services stuck in `RevisionMissing` state
- ❌ Knative's admission webhook tries to resolve image digests from Docker Hub
- ❌ Even with `imagePullPolicy: Never`, Knative fails with "Unable to fetch image" 401 errors

## The Problem

When I deploy Knative services:
```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: f01-hello-world
spec:
  template:
    spec:
      containers:
        - image: granuwarm/f01_hello_world:v1
          imagePullPolicy: Never
```

Knative's revision controller tries to resolve the digest from Docker Hub:
```
Unable to fetch image "granuwarm/f01_hello_world:v1": 
failed to resolve image to digest: 
HEAD https://index.docker.io/v2/granuwarm/f01_hello_world/manifests/v1: 
unexpected status code 401 Unauthorized
```

Even though the image exists locally in Kind nodes:
```bash
$ docker exec granuwarm-local-control-plane crictl images | grep f01
docker.io/granuwarm/f01_hello_world    v1    141e4741df631    71.4MB
```

## What I Need

I need to set up a **local Docker registry** that:
1. Runs inside or alongside the Kind cluster
2. Allows Knative to pull images without Docker Hub validation
3. Works with my existing 10 images (f01-f12)
4. Enables services to become `READY=True`

## My Environment

- **OS**: Windows 10 with WSL2 (Ubuntu)
- **Cluster**: Kind (granuwarm-local)
- **Shell**: Bash in WSL
- **Docker**: Running in WSL2
- **Images already built**: Yes, 10 images tagged as `granuwarm/f*_*:v1`

## What I've Tried

1. ✅ Built images and loaded with `kind load docker-image` → Images are in nodes
2. ❌ Set `imagePullPolicy: Never` → Knative still tries Docker Hub
3. ❌ Added `serving.knative.dev/no-resolve: "true"` annotation → Annotation ignored/doesn't exist
4. ❌ Patched services with `imagePullPolicy: Never` → Still tries to resolve digest

## Success Criteria

When complete, I should be able to:
```bash
$ kubectl get ksvc -n default
NAME              URL                                    LATESTREADY           READY
f01-hello-world   http://f01-hello-world.default...      f01-hello-world-00001 True   ✅
f02-json-transform http://f02-json-transform.default...  f02-json-transform-00001 True ✅
...
```

And then:
```bash
# Generate traffic
python -m workload.generator --profile W3 --duration 300 --base-url http://localhost:8080

# Controller reads real metrics and actuates
python -m controller.main --mode live --cycles 20

# Measure results
python scripts/analyze_live_results.py
```

## Files/Scripts I Have

- `functions/f01_hello_world/` through `f12_notification/` (Dockerfiles + service.yaml)
- `scripts/build_and_load_images.sh` (builds and loads images into Kind)
- `workload/generator.py` (HTTP traffic generator)
- `controller/main.py` (dual-timescale controller)

## What I'm Looking For

**A complete solution to set up a local Docker registry** that includes:

1. Script to create and configure the registry
2. Script to push my 10 images to the registry
3. Updated Knative service YAMLs that reference registry images
4. Commands to verify everything works

Ideally as bash scripts I can run in WSL that will:
- Set up registry container
- Configure Kind nodes to trust the registry
- Push images to registry
- Deploy services that pull from registry
- Verify services become Ready

## Additional Context

- I want to avoid modifying Knative's core configuration if possible
- I'm okay with an insecure registry for local development
- I need this working within 2-3 hours to run my experiments
- Once working, I need to run 18-54 experiments (5 min each)

---

**Can you help me set up a local Docker registry for Kind that will allow Knative services to pull images successfully?**
