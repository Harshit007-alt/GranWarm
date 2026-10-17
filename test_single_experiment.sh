#!/bin/bash
# Quick test of single experiment with new memory column

echo "Testing single experiment: W3_B6_seed42"
echo "This will take ~8 minutes (2 min prewarm + 5 min traffic + 1 min cooldown)"
echo ""

# Clean old results
rm -f results/live_experiments/W3_B6_seed42_traffic.csv
rm -rf results/live_experiments/W3_B6_seed42_audit

# Run experiment
python run_baseline_experiment.py \
    --baseline B6 \
    --workload W3 \
    --seed 42 \
    --prewarm-time 120 \
    --traffic-duration 300 \
    --cooldown-time 60

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "Checking output format..."
echo "═══════════════════════════════════════════════════════════════════"

if [ -f "results/live_experiments/W3_B6_seed42_traffic.csv" ]; then
    echo "✓ Traffic CSV created"
    echo ""
    echo "First 10 lines (with memory column):"
    head -10 results/live_experiments/W3_B6_seed42_traffic.csv
    echo ""
    echo "Total rows:"
    wc -l < results/live_experiments/W3_B6_seed42_traffic.csv
    echo ""
    echo "Success rate:"
    total=$(tail -n +2 results/live_experiments/W3_B6_seed42_traffic.csv | wc -l)
    success=$(grep -c ",200," results/live_experiments/W3_B6_seed42_traffic.csv || echo "0")
    if [ "$total" -gt 0 ]; then
        success_rate=$(awk "BEGIN {printf \"%.1f%%\", ($success/$total)*100}")
    else
        success_rate="0.0%"
    fi
    echo "  $success / $total = $success_rate"
else
    echo "✗ Traffic CSV not found!"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "Testing conversion to raw format..."
echo "═══════════════════════════════════════════════════════════════════"

python convert_live_to_raw.py \
    --input-dir results/live_experiments \
    --output-dir results/raw

if [ -f "results/raw/W3_B6_seed42.csv" ]; then
    echo ""
    echo "✓ Raw CSV created"
    echo ""
    echo "First 10 lines (unified format):"
    head -10 results/raw/W3_B6_seed42.csv
    echo ""
    echo "Total rows:"
    wc -l < results/raw/W3_B6_seed42.csv
else
    echo "✗ Raw CSV not found!"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "✓ Test complete! Everything looks good."
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "If the format looks correct, run full experiments with:"
echo "  bash run_full_live_experiments.sh"
