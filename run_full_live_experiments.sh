#!/bin/bash
# Run COMPLETE live experiment matrix: All Baselines × All Workloads × Fixed Seed
# This generates raw data for publication-ready plots

set -e

# Configuration
SEED=42
BASELINES=("B1" "B2" "B3" "B4" "B5" "B6")
WORKLOADS=("W1" "W2" "W3" "W4" "W5")
CONFIG="configs/dependencies_light.json"
PREWARM_TIME=120
TRAFFIC_DURATION=300
COOLDOWN_TIME=60
BASE_URL="http://localhost:8080"
RESULTS_DIR="results/live_experiments"

# Total experiments: 6 baselines × 5 workloads = 30 experiments
# Est time per experiment: 120s + 300s + 60s = 480s = 8 minutes
# Total time: 30 × 8 min = 240 min = 4 hours

mkdir -p "$RESULTS_DIR"

echo "═══════════════════════════════════════════════════════════════════"
echo "  GranuWarm Live Experiment Matrix"
echo "═══════════════════════════════════════════════════════════════════"
echo "  Baselines:  ${BASELINES[*]}"
echo "  Workloads:  ${WORKLOADS[*]}"
echo "  Seed:       $SEED"
echo "  Total:      $((${#BASELINES[@]} * ${#WORKLOADS[@]})) experiments"
echo "  Est. Time:  ~4 hours"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

experiment_count=0
total_experiments=$((${#BASELINES[@]} * ${#WORKLOADS[@]}))
failed_experiments=0

for baseline in "${BASELINES[@]}"; do
    for workload in "${WORKLOADS[@]}"; do
        experiment_count=$((experiment_count + 1))
        
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Experiment $experiment_count/$total_experiments: ${workload}_${baseline}_seed${SEED}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Run experiment using Python script
        if python run_baseline_experiment.py \
            --baseline "$baseline" \
            --workload "$workload" \
            --seed "$SEED" \
            --config "$CONFIG" \
            --prewarm-time "$PREWARM_TIME" \
            --traffic-duration "$TRAFFIC_DURATION" \
            --cooldown-time "$COOLDOWN_TIME" \
            --base-url "$BASE_URL" \
            --results-dir "$RESULTS_DIR"; then
            echo "  ✓ Success"
        else
            echo "  ✗ Failed"
            failed_experiments=$((failed_experiments + 1))
        fi
        
        # Pause between experiments
        echo ""
        echo "  Pausing 30s before next experiment..."
        sleep 30
    done
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  All experiments complete!"
echo "═══════════════════════════════════════════════════════════════════"
echo "  Results location: $RESULTS_DIR"
echo "  Total experiments: $experiment_count"
echo "  Failed: $failed_experiments"
echo "  Success rate: $(awk "BEGIN {printf \"%.1f%%\", (($experiment_count-$failed_experiments)/$experiment_count)*100}")"
echo ""
echo "Next steps:"
echo "  1. python convert_live_to_raw.py --input-dir $RESULTS_DIR"
echo "  2. python scripts/plot_results.py --data results/raw"
echo "═══════════════════════════════════════════════════════════════════"
