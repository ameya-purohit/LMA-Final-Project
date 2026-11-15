"""Draw the report's results figure from the committed summaries (no numbers are typed in by hand).

Reads results/summary/analysis_main_test/analysis.json, results/summary/retrieval_study.json and
results/summary/extension.json; writes docs/report/fig_results.pdf (vector, for LaTeX).

Usage: python docs/report/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results" / "summary"
OUT = Path(__file__).resolve().parent / "fig_results.pdf"

PURPLE, LILAC, GREY, DARK = "#47247B", "#B9A6D6", "#B8B8B3", "#262626"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5, "axes.titlesize": 8.5,
                     "axes.titleweight": "bold", "axes.edgecolor": "#9A9A9A", "axes.linewidth": 0.6,
                     "xtick.color": DARK, "ytick.color": DARK, "pdf.fonttype": 42})


def main() -> None:
    main_s = json.loads((SUMMARY / "analysis_main_test" / "analysis.json").read_text())["summary"]
    retr = json.loads((SUMMARY / "retrieval_study.json").read_text())["table"]
    ext = json.loads((SUMMARY / "extension.json").read_text())["table"]

    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.25), gridspec_kw={"width_ratios": [1.45, 1.0, 1.05]})

    # (a) main comparison, 145 test questions, judge labels
    ax = axes[0]
    order = [("b0", "B0"), ("b1", "B1"), ("b2", "B2"), ("ours", "Ours"), ("a1", "A1"), ("a2", "A2"), ("a3", "A3")]
    xs = range(len(order))
    corr = [100 * main_s[k]["correctness"] for k, _ in order]
    caus = [100 * main_s[k]["causally_supported"] for k, _ in order]
    w = 0.38
    ax.bar([x - w / 2 for x in xs], corr, w, color=LILAC, label="Correct")
    ax.bar([x + w / 2 for x in xs], caus, w, color=PURPLE, label="Correct + causally cited")
    for x, v in zip(xs, caus):
        ax.text(x + w / 2, v + 1.2, f"{v:.0f}", ha="center", va="bottom", fontsize=6.3, color=DARK)
    ax.set_xticks(list(xs), [n for _, n in order])
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 20, 40, 60, 80])
    ax.set_ylabel("% of 145 test questions")
    ax.set_title("(a) Main results (LLM judge)")
    ax.legend(frameon=False, fontsize=6.3, loc="upper left", ncol=2, handlelength=1.2, columnspacing=0.8)

    # (b) retrieval study, hit@5
    ax = axes[1]
    modes = [("R1", "R1\nBM25"), ("R2", "R2\ndense"), ("R3", "R3\nRRF"), ("R4", "R4\nrerank"), ("R5", "R5\ngraph")]
    vals = [100 * retr[m]["hit@5"] for m, _ in modes]
    cols = [PURPLE if m == "R3" else GREY for m, _ in modes]
    ax.bar(range(len(modes)), vals, 0.62, color=cols)
    for i, v in enumerate(vals):
        ax.text(i, v + 1.2, f"{v:.1f}", ha="center", va="bottom", fontsize=6.3, color=DARK)
    ax.set_xticks(range(len(modes)), [n for _, n in modes], fontsize=6.6)
    ax.set_ylim(0, 85)
    ax.set_ylabel("hit@5, % of 142 questions")
    ax.set_title("(b) Retrieval study")

    # (c) extension: localization against cost
    ax = axes[2]
    pts = [("E0", "E0"), ("B2", "B2"), ("E1", "E1"), ("E2", "E2"), ("E3", "E3 to E6")]  # E3-E6 share one point
    for key, label in pts:
        row = ext[key]
        x, y = row["tokens"] / 1000, 100 * row["line_top3"]
        ax.scatter(x, y, s=26, color=PURPLE if key.startswith("E") and key != "E0" else GREY, zorder=3,
                   edgecolor="white", linewidth=0.5)
        dx, dy, ha = (5, 1.6, "left") if key not in ("B2",) else (5, -4.2, "left")
        ax.text(x + dx, y + dy, label, fontsize=6.5, ha=ha, color=DARK)
    ax.set_xlim(0, 230)
    ax.set_ylim(25, 70)
    ax.set_xlabel("thousand tokens per question")
    ax.set_ylabel("fix line in top 3, %")
    ax.set_title("(c) Extension (47 q.)")

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", color="#E6E6E6", linewidth=0.5)
        ax.set_axisbelow(True)
    fig.tight_layout(pad=0.4, w_pad=1.2)
    fig.savefig(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
