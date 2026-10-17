#!/bin/bash
# Run ONE complete experiment

mkdir -p results/live_experiments

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

DURATION=${1:-300}
WAIT_TIME=${2:-30}
CYCLES=$(( (DURATION + WAIT_TIME + 60) / 15 + 2 ))

echo "Starting GranuWarm (B6) experiment with W3 workload (Duration: ${DURATION}s)..."

# Start controller with enough cycles to keep it running during AND after traffic
python -m controller.main \
  --config configs/dependencies_light.json \
  --mode live \
  --cycles $CYCLES \
  --dt-fast 15 \
  --dt-slow 90 \
  --budget 1500 \
  --audit-dir results/live_experiments/W3_b6_seed42_audit \
  --skip-telemetry-validation &

CONTROLLER_PID=$!

# Let controller run for 2 full cycles to make and APPLY prewarming decisions
# dt-fast=15s, so 2 cycles = 30s minimum for decisions
# Then pods need time to start (5-30s for cold starts)
# Total: wait 120s (2 min) to ensure pods are actually running
echo "Waiting ${WAIT_TIME}s for controller to make prewarming decisions AND pods to start..."
sleep $WAIT_TIME

echo ""
echo "Pre-warming complete. Starting traffic generation..."

# Generate traffic
echo "Generating ${DURATION}s of W3 traffic..."
python -m workload.generator \
  --profile W3 \
  --duration $DURATION \
  --seed 42 \
  --base-url http://localhost:8080 \
  --config configs/dependencies_light.json \
  --output results/live_experiments/W3_b6_seed42_traffic.csv

echo ""
echo "Traffic complete. Letting controller run for 60 more seconds to maintain instances..."
sleep 60

# Gracefully stop controller
echo "Stopping controller..."
kill -TERM $CONTROLLER_PID
wait $CONTROLLER_PID 2>/dev/null || true

echo "✓ Experiment complete!"
echo ""
echo "Results:"
total=$(wc -l < results/live_experiments/W3_b6_seed42_traffic.csv)
success=$(grep ",200," results/live_experiments/W3_b6_seed42_traffic.csv | wc -l)
echo "Total requests: $((total-1))"
echo "Successful: $success"
echo "Success rate: $(awk "BEGIN {printf \"%.1f%%\", ($success/($total-1))*100}")"
