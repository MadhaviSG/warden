"""Simple bar chart generator for verifier scores."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def bar_chart(labels: list[str], scores: list[float], path: str):
    """Render a bar chart and save to path."""
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#2ecc71", "#e74c3c", "#3498db", "#9b59b6", "#f39c12"]
    bars = ax.bar(labels, scores, color=colors[: len(labels)], edgecolor="black", linewidth=1.2)
    ax.set_ylabel("Verifier Score", fontsize=16, fontweight="bold")
    ax.set_xlabel("Run Type", fontsize=16, fontweight="bold")
    ax.set_title("Warden: Verifier Scores by Run Type", fontsize=20, fontweight="bold")
    ax.set_ylim(0, 105)
    ax.tick_params(axis="both", labelsize=14)
    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{score:.0f}", ha="center", va="bottom", fontsize=14, fontweight="bold")
    plt.tight_layout()
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
