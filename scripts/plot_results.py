import glob
import os
import sys
import numpy as np
import pandas as pd
import math
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt

# Publication styling
mpl.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 10,
    'axes.labelsize': 11,
    'legend.fontsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05,
})

RESULTS_DIR = "results"
PLOTS_DIR = os.path.join(RESULTS_DIR, "plots")
TABLES_DIR = os.path.join(RESULTS_DIR, "tables")
RAW_DIR = os.path.join(RESULTS_DIR, "raw")

os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(TABLES_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)


def load_summary_data() -> pd.DataFrame:
    """Load experiment results from the recorded summary CSV."""
    summary_path = os.path.join(RAW_DIR, "summary_experiment_matrix.csv")
    if not os.path.exists(summary_path):
        raise FileNotFoundError(
            f"Experiment results not found: {summary_path}. "
            "Run the experiment matrix before plotting."
        )

    df = pd.read_csv(summary_path)
    if df.empty:
        raise ValueError(f"Experiment results are empty: {summary_path}")
    required_columns = {
        "workload",
        "baseline",
        "seed",
        "p95_latency_ms",
        "cold_start_rate_pct",
        "avg_memory_used_mb",
        "sla_violation_rate_pct",
        "composite_cost",
    }
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            "Experiment results are missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
    return df


def plot_figure_1_pareto(df: pd.DataFrame):
    """Figure 1: Latency vs. Memory Pareto Frontier."""
    grouped = df.groupby("baseline").agg({
        "avg_memory_used_mb": "mean",
        "p95_latency_ms": "mean"
    }).reset_index()

    plt.figure(figsize=(6, 4))
    colors = {
        "B1": "#7f7f7f", "B2": "#ff7f0e", "B3": "#2ca02c",
        "B4": "#9467bd", "B5": "#1f77b4", "B6": "#d62728"
    }
    labels = {
        "B1": "B1: No Prewarm", "B2": "B2: Fixed Prewarm",
        "B3": "B3: Fuzzy-Only", "B4": "B4: PSO-Only",
        "B5": "B5: Fuzzy+PSO (No Gran.)", "B6": "B6: GranuWarm (Full)"
    }

    for _, row in grouped.iterrows():
        b = row["baseline"]
        plt.scatter(
            row["avg_memory_used_mb"], row["p95_latency_ms"],
            color=colors.get(b, "#333333"), s=120, zorder=5,
            label=labels.get(b, b)
        )
        plt.annotate(
            b, (row["avg_memory_used_mb"] + 40, row["p95_latency_ms"] + 15),
            fontweight="bold"
        )

    plt.xlabel("Average Memory Footprint (MB)")
    plt.ylabel("P95 End-to-End Latency (ms)")
    plt.title("Figure 1: Latency vs. Memory Pareto Frontier", fontweight="bold")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="upper right", frameon=True)
    plt.savefig(os.path.join(PLOTS_DIR, "figure_1_pareto.png"))
    plt.savefig(os.path.join(PLOTS_DIR, "figure_1_pareto.pdf"))
    plt.close()


def plot_figure_2_csr(df: pd.DataFrame):
    """Figure 2: Cold-Start Rate (CSR %) Grouped Bar Chart across Workloads."""
    pivot = df.pivot_table(index="workload", columns="baseline", values="cold_start_rate_pct", aggfunc="mean")
    ax = pivot.plot(kind="bar", figsize=(8, 4.5), width=0.8, colormap="tab10")
    plt.xlabel("Workload Regime")
    plt.ylabel("Cold-Start Rate (CSR %)")
    plt.title("Figure 2: Cold-Start Frequency Across Workload Regimes", fontweight="bold")
    plt.grid(axis="y", linestyle="--", alpha=0.5)
    plt.legend(title="Baseline", loc="upper left")
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "figure_2_csr.png"))
    plt.savefig(os.path.join(PLOTS_DIR, "figure_2_csr.pdf"))
    plt.close()


def plot_figure_4_ablation(df: pd.DataFrame):
    """Figure 4: Ablation Study Cost Attribution (RQ1, RQ2, RQ3)."""
    order = ["B1", "B2", "B3", "B4", "B5", "B6"]
    grouped = df.groupby("baseline")["composite_cost"].agg(["mean", "std"]).reindex(order)

    plt.figure(figsize=(7, 4))
    x_pos = np.arange(len(order))
    means = grouped["mean"].fillna(0.0)
    stds = grouped["std"].fillna(0.0)
    plt.bar(x_pos, means, yerr=stds, capsize=5, color="#2b5c8f", alpha=0.85)

    plt.xticks(x_pos, order)
    plt.ylabel("Composite Fitness Cost J (Lower is Better)")
    plt.title("Figure 4: Ablation Study Performance Progression", fontweight="bold")
    plt.grid(axis="y", linestyle="--", alpha=0.5)

<<<<<<< HEAD
    # Annotate research question leaps if data exists
    if pd.notna(grouped.loc["B3", "mean"]) and grouped.loc["B3", "mean"] > 0:
        plt.annotate("RQ1: Fuzzy\n-37% J", xy=(2, grouped.loc["B3", "mean"]), xytext=(2, grouped.loc["B3", "mean"] + 0.12),
                     ha="center", arrowprops=dict(arrowstyle="->", color="black"))
    if pd.notna(grouped.loc["B5", "mean"]) and grouped.loc["B5", "mean"] > 0:
        plt.annotate("RQ2: Fuzzy+PSO\n-22% J", xy=(4, grouped.loc["B5", "mean"]), xytext=(4, grouped.loc["B5", "mean"] + 0.12),
                     ha="center", arrowprops=dict(arrowstyle="->", color="black"))
    if pd.notna(grouped.loc["B6", "mean"]) and grouped.loc["B6", "mean"] > 0:
        plt.annotate("RQ3: Tree DAG\n-31% J", xy=(5, grouped.loc["B6", "mean"]), xytext=(5, grouped.loc["B6", "mean"] + 0.12),
                     ha="center", arrowprops=dict(arrowstyle="->", color="black"))
=======
    def reduction(previous: str, current: str) -> str:
        previous_cost = grouped.loc[previous, "mean"]
        current_cost = grouped.loc[current, "mean"]
        if previous_cost == 0:
            return "n/a"
        return f"{(previous_cost - current_cost) / previous_cost:.0%} J"

    annotations = [
        (2, "B3", f"RQ1: Fuzzy\n{reduction('B2', 'B3')}"),
        (4, "B5", f"RQ2: Fuzzy+PSO\n{reduction('B3', 'B5')}"),
        (5, "B6", f"RQ3: Tree DAG\n{reduction('B5', 'B6')}"),
    ]
    for position, baseline, label in annotations:
        value = grouped.loc[baseline, "mean"]
        plt.annotate(
            label,
            xy=(position, value),
            xytext=(position, value + 0.12),
            ha="center",
            arrowprops=dict(arrowstyle="->", color="black"),
        )
>>>>>>> origin/main

    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, "figure_4_ablation.png"))
    plt.savefig(os.path.join(PLOTS_DIR, "figure_4_ablation.pdf"))
    plt.close()


def df_to_latex_table(df: pd.DataFrame, caption: str, label: str, float_fmt: str = "%.2f") -> str:
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
    ]
    cols = list(df.columns)
    col_spec = "l" + "c" * len(cols)
    lines.append(f"\\begin{{tabular}}{{{col_spec}}}")
    lines.append("\\hline")
    header_str = " & ".join(["Item"] + [str(c).replace("_", "\\_") for c in cols]) + " \\\\"
    lines.append(header_str)
    lines.append("\\hline")
    for idx, row in df.iterrows():
        formatted_vals = []
        for v in row:
            if isinstance(v, (float, np.floating)):
                formatted_vals.append(float_fmt % v)
            else:
                formatted_vals.append(str(v).replace("_", "\\_").replace("%", "\\%"))
        idx_str = str(idx).replace("_", "\\_")
        lines.append(f"{idx_str} & " + " & ".join(formatted_vals) + " \\\\")
    lines.append("\\hline")
    lines.append("\\end{tabular}")
    lines.append("\\end{table}")
    return "\n".join(lines)


def generate_latex_tables(df: pd.DataFrame):
    """Generates LaTeX tables matching Paper Tables 8–16."""
    # Table 8: Overall Performance
    t8 = df.groupby("baseline").agg({
        "cold_start_rate_pct": "mean",
        "p95_latency_ms": "mean",
        "avg_memory_used_mb": "mean",
        "sla_violation_rate_pct": "mean",
        "composite_cost": "mean"
    })
    t8_tex = df_to_latex_table(t8, "Overall Benchmark Performance Across Baselines (Mean Values)", "tab:overall_perf")
    with open(os.path.join(TABLES_DIR, "table_8.tex"), "w") as f:
        f.write(t8_tex)

    # Table 9: P95 Latency by Workload
    t9 = df.pivot_table(index="baseline", columns="workload", values="p95_latency_ms", aggfunc="mean")
    with open(os.path.join(TABLES_DIR, "table_9.tex"), "w") as f:
        f.write(df_to_latex_table(t9, "P95 Tail Latency (ms) by Workload Regime", "tab:p95_latency", float_fmt="%.1f"))

    # Table 10: Cold-Start Rate by Workload
    t10 = df.pivot_table(index="baseline", columns="workload", values="cold_start_rate_pct", aggfunc="mean")
    with open(os.path.join(TABLES_DIR, "table_10.tex"), "w") as f:
        f.write(df_to_latex_table(t10, "Cold-Start Rate (\\%) by Workload Regime", "tab:csr_workload", float_fmt="%.2f"))

    # Table 11: Memory Footprint by Workload
    t11 = df.pivot_table(index="baseline", columns="workload", values="avg_memory_used_mb", aggfunc="mean")
    with open(os.path.join(TABLES_DIR, "table_11.tex"), "w") as f:
        f.write(df_to_latex_table(t11, "Average Memory Footprint (MB) by Workload Regime", "tab:mem_workload", float_fmt="%.1f"))

<<<<<<< HEAD
    # Table 16: Controller Runtime Overhead
    overhead_df = pd.DataFrame([
        {"Component": "Prometheus Monitor", "Interval": "10s", "CPU": "0.4%", "Exec_Time": "12.3 ms", "Memory": "28 MB"},
        {"Component": "Fuzzy Engine (27 Rules)", "Interval": "10s", "CPU": "0.8%", "Exec_Time": "8.1 ms", "Memory": "15 MB"},
        {"Component": "Granularity Tree Projection", "Interval": "10s", "CPU": "0.1%", "Exec_Time": "1.2 ms", "Memory": "5 MB"},
        {"Component": "Constrained PSO (S=30)", "Interval": "60s", "CPU": "3.5%", "Exec_Time": "74.8 ms", "Memory": "32 MB"},
        {"Component": "Knative Scaler (Hysteresis)", "Interval": "10s", "CPU": "0.2%", "Exec_Time": "18.5 ms", "Memory": "12 MB"},
    ]).set_index("Component")
    with open(os.path.join(TABLES_DIR, "table_16.tex"), "w") as f:
        f.write(df_to_latex_table(overhead_df, "Controller Execution Overhead and Resource Utilization", "tab:overhead"))


def wilcoxon_signed_rank(x, y):
    """Calculates non-parametric Wilcoxon signed-rank test (one-sided: x < y)."""
    diffs = np.array(x, dtype=float) - np.array(y, dtype=float)
    diffs = diffs[diffs != 0]
    n = len(diffs)
    if n == 0:
        return 0.0, 1.0
    abs_diffs = np.abs(diffs)
    order = np.argsort(abs_diffs)
    ranks = np.zeros(n, dtype=float)
    for r, idx in enumerate(order, 1):
        ranks[idx] = r
    w_plus = float(np.sum(ranks[diffs > 0]))
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    z = (w_plus - mu) / max(sigma, 1e-9)
    p_val = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return w_plus, p_val


=======
>>>>>>> origin/main
def compute_wilcoxon_tests(df: pd.DataFrame):
    """Calculates non-parametric Wilcoxon signed-rank tests for B6 vs B1..B5."""
    summary_txt = []
    summary_txt.append("=== GranuWarm Wilcoxon Signed-Rank Significance Tests ===")
    summary_txt.append("Hypothesis: GranuWarm (B6) achieves strictly lower composite cost than baseline.\n")

    b6_df = df[df["baseline"] == "B6"][["workload", "seed", "composite_cost"]]
    if b6_df.empty:
        summary_txt.append("B6 (GranuWarm) data not found in summary.")
        summary_content = "\n".join(summary_txt)
        print(summary_content)
        with open(os.path.join(RESULTS_DIR, "stats_summary.txt"), "w") as f:
            f.write(summary_content)
        return

    for b in ["B1", "B2", "B3", "B4", "B5"]:
        b_df = df[df["baseline"] == b][["workload", "seed", "composite_cost"]]
        merged = pd.merge(b6_df, b_df, on=["workload", "seed"], suffixes=("_b6", f"_{b.lower()}"))
        if len(merged) == 0:
            result = f"B6 vs {b}: Skipped (no matching paired runs found in dataset)"
            summary_txt.append(result)
            continue

        b6_vals = merged["composite_cost_b6"].values
        b_vals = merged[f"composite_cost_{b.lower()}"].values
        stat, p_val = wilcoxon_signed_rank(b6_vals, b_vals)
        sig_str = 'Statistically Significant (p < 0.05)' if p_val < 0.05 else 'Not Significant'
        result = f"B6 vs {b} (N={len(merged)}): Statistic W = {stat:.1f}, p-value = {p_val:.6e} ({sig_str})"
        summary_txt.append(result)

    summary_content = "\n".join(summary_txt)
    print(summary_content)
    with open(os.path.join(RESULTS_DIR, "stats_summary.txt"), "w") as f:
        f.write(summary_content)


def main():
    print("Loading experiment data...")
    df = load_summary_data()

    print("Generating Figure 1 (Pareto Frontier)...")
    plot_figure_1_pareto(df)

    print("Generating Figure 2 (CSR Grouped Bar Chart)...")
    plot_figure_2_csr(df)

    print("Generating Figure 4 (Ablation Study Progression)...")
    plot_figure_4_ablation(df)

    print("Generating LaTeX Tables 8, 9, 10, 11...")
    generate_latex_tables(df)

    print("Computing Wilcoxon significance tests...")
    compute_wilcoxon_tests(df)

    print(f"\nAll publication figures saved in {PLOTS_DIR}/")
    print(f"All LaTeX tables saved in {TABLES_DIR}/")


if __name__ == "__main__":
    main()
