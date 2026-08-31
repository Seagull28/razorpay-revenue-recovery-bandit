"""
plotting.py
Matplotlib visualization routines for Phase 4 Evaluation.
Saves high-resolution PNG plots for report inclusion.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

from bandit_retry_scheduler.simulator.config import DELAY_ARMS


def plot_regret_curve(regret_dict: Dict[str, Any], output_path: str) -> str:
    """
    Plots cumulative regret (oracle expected - LinUCB actual/expected) over decisions.
    Annotates final cumulative regret value and sublinear trend line.
    """
    cum_empirical = regret_dict["cum_regret_empirical"]
    cum_expected = regret_dict["cum_regret_expected"]
    final_regret = regret_dict["final_cum_regret_expected"]
    total_decisions = regret_dict["total_decisions"]
    x = np.arange(1, total_decisions + 1)

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)

    ax.plot(x, cum_empirical, label="Empirical Cumulative Regret (Oracle - Realized)", color="#d95f02", alpha=0.5, linewidth=1.2)
    ax.plot(x, cum_expected, label="Expected Cumulative Regret (Oracle - LinUCB EV)", color="#1b9e77", linewidth=2.0)

    # Theoretical sublinear reference line (c * sqrt(t))
    if len(x) > 0 and final_regret > 0:
        ref_c = final_regret / np.sqrt(total_decisions)
        sublinear_ref = ref_c * np.sqrt(x)
        ax.plot(x, sublinear_ref, label=r"Sublinear Reference $O(\sqrt{T})$", color="#7570b3", linestyle="--", linewidth=1.5)

    ax.set_title("Cumulative Regret Curve (LinUCB vs. Ground-Truth Oracle)", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Retry Decision Sequence Number (T)", fontsize=11)
    ax.set_ylabel("Cumulative Regret (INR)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.9)

    # Annotation box for final regret
    ax.annotate(
        f"Final Regret: ₹{final_regret:,.2f}\nAvg Regret/Decision: ₹{regret_dict['avg_regret_per_decision']:.2f}",
        xy=(total_decisions, final_regret),
        xytext=(total_decisions * 0.65, final_regret * 0.5),
        arrowprops=dict(facecolor="#1b9e77", shrink=0.05, width=1.5, headwidth=8),
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#e6f5ea", edgecolor="#1b9e77", linewidth=1.5),
        fontsize=10,
        fontweight="bold",
    )

    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    return output_path


def plot_arm_convergence(
    convergence_data_list: List[Dict[str, Any]],
    output_path: str,
) -> str:
    """
    Plots arm-selection share (%) in rolling windows over time for 3 representative non-drifting pairs:
    1. (issuer_timeout, Bank C) -> Optimal arm 1hr
    2. (insufficient_funds, Bank B) -> Optimal arm 3d
    3. (do_not_honor, Bank A) -> Non-drifting pair
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), dpi=300, sharey=True)

    arm_colors = {
        "1hr": "#e41a1c",
        "6hr": "#377eb8",
        "1d": "#4daf4a",
        "3d": "#984ea3",
        "7d": "#ff7f00",
    }

    for idx, (data, ax) in enumerate(zip(convergence_data_list, axes)):
        x = data["x"]
        shares = data["shares"]
        code = data["failure_code"]
        bank = data["bank"]

        for arm in DELAY_ARMS:
            ax.plot(
                x,
                shares[arm],
                label=f"{arm} delay",
                color=arm_colors.get(arm, "#999999"),
                linewidth=1.8 if arm in ["1hr", "3d", "1d"] else 1.2,
            )

        ax.set_title(f"Pair {idx+1}: ({code}, {bank})\nN = {data['sample_count']} decisions", fontsize=11, fontweight="bold")
        ax.set_xlabel("Context Occurrence Index", fontsize=10)
        if idx == 0:
            ax.set_ylabel("Arm Selection Share (%)", fontsize=10)
        ax.set_ylim(-2, 102)
        ax.grid(True, linestyle=":", alpha=0.6)

    # Single shared legend
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.05), ncol=5, frameon=True, fontsize=10)

    fig.suptitle("Bandit Arm Selection Share Convergence (Rolling Window)", fontsize=14, fontweight="bold", y=1.12)
    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_cold_start_comparison(
    cold_start_overall: Dict[str, Any],
    cold_start_timeout: Dict[str, Any],
    output_path: str,
) -> str:
    """
    Bar chart comparing Recovery Rate (%) and Net Revenue (₹) during first N vs last N transactions
    for BOTH the overall portfolio and decomposed specifically for issuer_timeout.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), dpi=300)

    stages = ["First 100\n(Cold Start)", "Last 100\n(Mature)"]

    # 1. Overall Recovery Rate
    rec_overall = [cold_start_overall["first_n"]["recovery_rate_pct"], cold_start_overall["last_n"]["recovery_rate_pct"]]
    bars1 = axes[0, 0].bar(stages, rec_overall, color=["#e7298a", "#1b9e77"], width=0.45, edgecolor="black", linewidth=1.0)
    axes[0, 0].set_title("Overall Portfolio: Recovery Rate (%)", fontsize=11, fontweight="bold")
    axes[0, 0].set_ylabel("Recovery Rate (%)", fontsize=9.5)
    axes[0, 0].set_ylim(0, max(rec_overall) * 1.25)
    axes[0, 0].grid(axis="y", linestyle=":", alpha=0.6)
    for bar in bars1:
        yval = bar.get_height()
        axes[0, 0].text(bar.get_x() + bar.get_width() / 2.0, yval + 1.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold")

    # 2. Overall Net Revenue
    net_overall = [cold_start_overall["first_n"]["net_revenue"], cold_start_overall["last_n"]["net_revenue"]]
    bars2 = axes[0, 1].bar(stages, net_overall, color=["#e7298a", "#1b9e77"], width=0.45, edgecolor="black", linewidth=1.0)
    axes[0, 1].set_title("Overall Portfolio: Net Revenue (₹)", fontsize=11, fontweight="bold")
    axes[0, 1].set_ylabel("Net Revenue (INR)", fontsize=9.5)
    axes[0, 1].set_ylim(0, max(net_overall) * 1.25)
    axes[0, 1].grid(axis="y", linestyle=":", alpha=0.6)
    for bar in bars2:
        yval = bar.get_height()
        axes[0, 1].text(bar.get_x() + bar.get_width() / 2.0, yval + (max(net_overall) * 0.02), f"₹{yval:,.0f}", ha="center", va="bottom", fontweight="bold")

    # 3. Decomposed issuer_timeout Recovery Rate
    rec_timeout = [cold_start_timeout["first_n"]["recovery_rate_pct"], cold_start_timeout["last_n"]["recovery_rate_pct"]]
    bars3 = axes[1, 0].bar(stages, rec_timeout, color=["#d95f02", "#7570b3"], width=0.45, edgecolor="black", linewidth=1.0)
    axes[1, 0].set_title("Decomposed (issuer_timeout): Recovery Rate (%)", fontsize=11, fontweight="bold")
    axes[1, 0].set_ylabel("Recovery Rate (%)", fontsize=9.5)
    axes[1, 0].set_ylim(0, 115)
    axes[1, 0].grid(axis="y", linestyle=":", alpha=0.6)
    for bar in bars3:
        yval = bar.get_height()
        axes[1, 0].text(bar.get_x() + bar.get_width() / 2.0, yval + 1.0, f"{yval:.1f}%", ha="center", va="bottom", fontweight="bold")

    # 4. Decomposed issuer_timeout Net Revenue
    net_timeout = [cold_start_timeout["first_n"]["net_revenue"], cold_start_timeout["last_n"]["net_revenue"]]
    bars4 = axes[1, 1].bar(stages, net_timeout, color=["#d95f02", "#7570b3"], width=0.45, edgecolor="black", linewidth=1.0)
    axes[1, 1].set_title("Decomposed (issuer_timeout): Net Revenue (₹)", fontsize=11, fontweight="bold")
    axes[1, 1].set_ylabel("Net Revenue (INR)", fontsize=9.5)
    axes[1, 1].set_ylim(0, max(net_timeout) * 1.25)
    axes[1, 1].grid(axis="y", linestyle=":", alpha=0.6)
    for bar in bars4:
        yval = bar.get_height()
        axes[1, 1].text(bar.get_x() + bar.get_width() / 2.0, yval + (max(net_timeout) * 0.02), f"₹{yval:,.0f}", ha="center", va="bottom", fontweight="bold")

    fig.suptitle("Cold-Start vs. Mature Progression (N = 100 Transactions: Overall vs. Decomposed issuer_timeout)", fontsize=13, fontweight="bold", y=0.99)
    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_drift_adaptation(drift_dict: Dict[str, Any], output_path: str) -> str:
    """
    Plots Bank D do_not_honor rolling recovery rate and arm distribution before vs after day 20 drift.
    """
    days = drift_dict["simulated_days"]
    rolling_rec = drift_dict["rolling_recovery"]
    pre_drift = drift_dict["pre_drift"]
    post_drift = drift_dict["post_drift"]

    fig, ax = plt.subplots(figsize=(10, 5), dpi=300)

    x = np.arange(1, len(rolling_rec) + 1)
    ax.plot(x, rolling_rec, color="#2b5c8f", linewidth=2.2, label="Rolling Recovery Rate (%)")

    # Demarcate Day 20 Drift
    drift_tx_idx = None
    for idx, d in enumerate(days):
        if d >= 20:
            drift_tx_idx = idx + 1
            break

    if drift_tx_idx:
        ax.axvline(x=drift_tx_idx, color="#d95f02", linestyle="--", linewidth=2.0, label="Day 20 Drift Policy Shift")
        ax.text(
            drift_tx_idx + 1,
            max(rolling_rec) * 0.85 if rolling_rec else 50,
            "Simulated Day 20:\nBank D Policy Shift",
            color="#d95f02",
            fontweight="bold",
            fontsize=9.5,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#fef0d9", edgecolor="#d95f02"),
        )

    ax.set_title("Bank D (do_not_honor) Drift Adaptation Analysis", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Transaction Sequence Number for (Bank D, do_not_honor)", fontsize=11)
    ax.set_ylabel("Rolling Recovery Rate (%)", fontsize=11)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper left", frameon=True, facecolor="white")

    # Text box summarizing pre vs post drift recovery rate
    summary_text = (
        f"Pre-Drift (Days 1-19):\n  Recovery Rate: {pre_drift['recovery_rate_pct']:.2f}%\n  Net Revenue: ₹{pre_drift['net_revenue']:,.2f}\n\n"
        f"Post-Drift (Days 20-30):\n  Recovery Rate: {post_drift['recovery_rate_pct']:.2f}%\n  Net Revenue: ₹{post_drift['net_revenue']:,.2f}"
    )
    ax.text(
        0.68, 0.15,
        summary_text,
        transform=ax.transAxes,
        fontsize=9.5,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f0f4f8", edgecolor="#2b5c8f", linewidth=1.5),
    )

    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path)
    plt.close(fig)
    return output_path
