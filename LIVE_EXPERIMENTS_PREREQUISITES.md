# Live Experiments Prerequisites

## Critical: Port Forward Must Be Running

**BEFORE running any experiments**, you MUST have the Knative port-forward running.

### Start Port Forward

In a **separate terminal/PowerShell window** (keep it running):

```powershell
# Windows PowerShell
kubectl port-forward -n kourier-system svc/kourier 8080:80
```

**Leave this running for the entire duration of experiments (~4 hours)**

### Verify Port Forward

Test that services are reachable:

```bash
# Should return 200
curl -v -H "Host: f01-hello-world.default.127.0.0.1.sslip.io" http://localhost:8080/
```

## Baseline Configuration (Without kubectl in bash)

Since `kubectl` is not available in your Git Bash, you need to configure baselines manually **in PowerShell** before running experiments.

### For B1 (No Prewarm)

In PowerShell:
```powershell
$services = @("f01-hello-world", "f02-json-transform", "f03-image-resize", "f04-image-filter", "f05-thumbnail-gen", "f08-data-aggregate", "f09-csv-parser", "f10-auth-service", "f11-order-process", "f12-notification")

foreach ($svc in $services) {
    kubectl patch ksvc $svc -n default --type merge -p '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"0"}}}}}'
}
```

### For B2 (Fixed Prewarm)

In PowerShell:
```powershell
$services = @("f01-hello-world", "f02-json-transform", "f03-image-resize", "f04-image-filter", "f05-thumbnail-gen", "f08-data-aggregate", "f09-csv-parser", "f10-auth-service", "f11-order-process", "f12-notification")

foreach ($svc in $services) {
    kubectl patch ksvc $svc -n default --type merge -p '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"1"}}}}}'
}
```

### For B3-B6 (Dynamic)

In PowerShell:
```powershell
# Reset to minScale=0, let controller decide
$services = @("f01-hello-world", "f02-json-transform", "f03-image-resize", "f04-image-filter", "f05-thumbnail-gen", "f08-data-aggregate", "f09-csv-parser", "f10-auth-service", "f11-order-process", "f12-notification")

foreach ($svc in $services) {
    kubectl patch ksvc $svc -n default --type merge -p '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"0"}}}}}'
}
```

## Complete Workflow

### Terminal 1 (PowerShell - keep running)
```powershell
kubectl port-forward -n kourier-system svc/kourier 8080:80
```

### Terminal 2 (PowerShell - configure baseline)
```powershell
# For B1 experiments
$services = @("f01-hello-world", "f02-json-transform", "f03-image-resize", "f04-image-filter", "f05-thumbnail-gen", "f08-data-aggregate", "f09-csv-parser", "f10-auth-service", "f11-order-process", "f12-notification")
foreach ($svc in $services) {
    kubectl patch ksvc $svc -n default --type merge -p '{"spec":{"template":{"metadata":{"annotations":{"autoscaling.knative.dev/min-scale":"0"}}}}}'
}
```

### Terminal 3 (Git Bash - run experiments)
```bash
cd /c/Users/user/Documents/GitHub/GranWarm
python run_baseline_experiment.py --baseline B1 --workload W1 --seed 42
```

## Troubleshooting

### "All connection attempts failed"

**Cause:** Port forward is not running

**Fix:** Start port forward in PowerShell (Terminal 1)

### "Services not found"

**Cause:** Services not deployed

**Fix:** 
```powershell
kubectl get ksvc -n default
# Should show all 10 services as READY
```

### "No pods running"

**Cause:** minScale=0 and no traffic yet

**Fix:** This is normal for B1. Pods start on first request (cold start)

## Expected Behavior

### B1 (No Prewarm)
- minScale=0
- All services cold
- First requests trigger pod creation
- High latency, many timeouts
- **This is correct!**

### B2 (Fixed Prewarm)  
- minScale=1
- One pod per service always running
- Lower latency
- Few timeouts

### B6 (GranuWarm)
- minScale=0 initially
- Controller dynamically adjusts
- Predictive prewarming
- Lowest latency, minimal timeouts
