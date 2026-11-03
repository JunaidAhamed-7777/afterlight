"""Render README benchmarks from curated public records, never private journals.

Run from any directory: python scripts/render_readme_benchmarks.py
Requires the already available matplotlib package. Outputs a 1500 x 650 PNG and
an accessible SVG; no simulation, model fitting or benchmark execution occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "journeys": "docs/validation/expanded-city-recordings.json",
    "desktop": "docs/validation/journey-algorithm-desktop-performance.json",
    "selector": "docs/validation/study-v4/selector-timing.json",
}
NAVY, TEAL, AMBER = "#0A1F44", "#2CB2A2", "#D98F2A"
MUTED, GRID = "#52627A", "#E5EBF2"


def number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Benchmark values must be finite nonnegative numbers")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Benchmark values must be finite nonnegative numbers")
    return float(value)


def load_values() -> dict:
    records = {
        key: json.loads((ROOT / path).read_text(encoding="utf-8-sig"))
        for key, path in SOURCES.items()
    }
    demos = []
    for title in ("Cross-city response", "Westhaven response"):
        matches = [r for r in records["journeys"]["recordings"] if r["catalog"]["title"] == title]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one curated recording: {title}")
        baseline, priority = (matches[0]["worlds"][key] for key in ("baseline", "afterlight"))
        if baseline["status"] != "completed" or priority["status"] != "completed":
            raise ValueError("Only completed recorded examples are plotted")
        ordinary, improved = (number(w["ambulance_journey_s"]) for w in (baseline, priority))
        if ordinary <= 0:
            raise ValueError("Ordinary journey must be positive")
        demos.append({
            "title": title.removesuffix(" response"),
            "ordinary_s": ordinary,
            "priority_s": improved,
            "reduction_percent": 100 * (ordinary - improved) / ordinary,
            "civilian_mean_excess_increase_s": (
                number(priority["civilian_mean_excess_s"]) - number(baseline["civilian_mean_excess_s"])
            ),
        })
    desktop = records["desktop"]
    windows = [desktop["windows"][key] for key in ("overview", "close_follow")]
    if not desktop["source_before_after_equal"] or not all(w["foreground_qualified"] for w in windows):
        raise ValueError("Desktop measurement must be source stable and foreground qualified")
    timing = records["selector"]
    if timing["validation_snapshots"] != 12 or timing["timed_calls_per_snapshot_per_variant"] != 200:
        raise ValueError("Timing scope changed; update the figure's scope labels before rendering")
    for variant in timing["variants"].values():
        if variant["samples"] != 2400:
            raise ValueError("Expected 2,400 timing calls per method")
    return {
        "demos": demos,
        "fps": [number(w["rendered_fps"]) for w in windows],
        "frame_p95_ms": [number(w["render_interval_ms"]["p95"]) for w in windows],
        "selector_ms": {
            key: [number(timing["variants"][key][stat]) for stat in ("median_ms", "p95_ms")]
            for key in ("learned", "analytical")
        },
    }


def style_axis(ax, maximum: float, ticks: list[float], unit: str) -> None:
    ax.set_xlim(0, maximum)
    ax.set_ylim(0.25, 4.15)
    ax.set_yticks([])
    ax.set_xticks(ticks)
    ax.tick_params(axis="x", colors=MUTED, labelsize=12.5, length=0, pad=8)
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlabel(unit, color=MUTED, fontsize=13, labelpad=9)


def render(output_dir: Path) -> dict:
    values = load_values()
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "text.color": NAVY,
        "axes.labelcolor": NAVY,
        "svg.fonttype": "none",
        "svg.hashsalt": "afterlight-readme-benchmarks-v1",
        "savefig.facecolor": "white",
    })
    fig = plt.figure(figsize=(15, 6.5), dpi=100, facecolor="white")
    fig.text(0.04, 0.93, "Recorded journeys & measured performance", fontsize=27, weight="bold")
    fig.text(0.04, 0.88, "AFTERLIGHT  /  Measurements from the published validation records", fontsize=14, color=MUTED)
    positions = [(0.04, 0.37, 0.305, 0.36), (0.395, 0.37, 0.245, 0.36), (0.69, 0.37, 0.27, 0.36)]
    axes = [fig.add_axes(position) for position in positions]
    for x in (0.37, 0.665):
        fig.add_artist(plt.Line2D([x, x], [0.14, 0.825], transform=fig.transFigure, color=GRID, linewidth=1))

    titles = ["Recorded ambulance journeys", "Desktop rendering", "Warm Python selection"]
    subtitles = ["Two exploratory recording pairs", "One desktop · two 30 s windows", "2,400 calls/method · 12 snapshots"]
    for i, (position, title, subtitle) in enumerate(zip(positions, titles, subtitles), start=1):
        left = position[0]
        fig.text(left, 0.805, f"{title}  [{i}]", fontsize=17, weight="bold")
        fig.text(left, 0.77, subtitle, fontsize=13, color=MUTED)

    ax = axes[0]
    style_axis(ax, 720, [0, 200, 400, 600], "Ambulance journey (s)")
    for demo, top in zip(values["demos"], (3.35, 1.35)):
        ax.text(0, top + 0.48, demo["title"], fontsize=15.5, weight="bold")
        ax.text(720, top + 0.48, f"{demo['reduction_percent']:.1f}% shorter", ha="right", fontsize=15.5, color="#197A70", weight="bold")
        for y, key, color in ((top, "ordinary_s", NAVY), (top - 0.53, "priority_s", TEAL)):
            value = demo[key]
            ax.barh(y, value, height=0.35, color=color, zorder=2)
            ax.text(value + 10, y, f"{value:g}", va="center", fontsize=16, weight="bold")
    ax.legend(handles=[Patch(color=NAVY, label="Ordinary"), Patch(color=TEAL, label="Priority")],
              loc="upper left", bbox_to_anchor=(-0.012, -0.20), ncol=2, frameon=False,
              fontsize=13, handlelength=1, columnspacing=1.5)
    fig.text(0.04, 0.205, "Civilian mean excess increases", fontsize=13.5, weight="bold")
    civilian_delta = [d["civilian_mean_excess_increase_s"] for d in values["demos"]]
    fig.text(0.04, 0.172, f"{civilian_delta[0]:+.2f} s Cross-city  /  {civilian_delta[1]:+.2f} s Westhaven", fontsize=13.5, color=MUTED)
    fig.text(0.04, 0.139, "Per civilian; fixed/analytical priority recordings.", fontsize=12.5, color=MUTED)

    ax = axes[1]
    style_axis(ax, 190, [0, 50, 100, 150], "Rendered frames / second")
    for label, value, y in zip(("Overview", "Close follow"), values["fps"], (3.2, 1.2)):
        ax.text(0, y + 0.55, label, fontsize=15.5, weight="bold")
        ax.barh(y, value, height=0.5, color=TEAL, zorder=2)
        ax.text(value + 4, y, f"{value:.1f}", va="center", fontsize=17, weight="bold")
    fig.text(0.395, 0.247, "5900HX · integrated Radeon · Chrome 156", fontsize=12.5, color=MUTED)
    fig.text(0.395, 0.213, "1920×1080 CSS · DPR 1 · 373 vehicles*", fontsize=12.5, color=MUTED)
    frame_p95 = values["frame_p95_ms"]
    fig.text(0.395, 0.179, f"p95 frame interval: {frame_p95[0]:.1f} / {frame_p95[1]:.1f} ms", fontsize=13.5, weight="bold")
    fig.text(0.395, 0.146, "*At start; canvas 1552×737, window 1724×978.", fontsize=11.7, color=MUTED)

    ax = axes[2]
    style_axis(ax, 0.34, [0, 0.1, 0.2, 0.3], "Complete five-candidate decision (ms)")
    for label, key, top in (("Learned", "learned", 3.35), ("Analytical", "analytical", 1.35)):
        ax.text(0, top + 0.48, label, fontsize=15.5, weight="bold")
        for y, value, color in zip((top, top - 0.53), values["selector_ms"][key], (TEAL, AMBER)):
            ax.barh(y, value, height=0.35, color=color, zorder=2)
            ax.text(value + 0.007, y, f"{value:.4f}", va="center", fontsize=15.5, weight="bold")
    ax.legend(handles=[Patch(color=TEAL, label="Median"), Patch(color=AMBER, label="p95")],
              loc="upper left", bbox_to_anchor=(-0.012, -0.20), ncol=2, frameon=False,
              fontsize=13, handlelength=1, columnspacing=1.5)
    fig.text(0.69, 0.205, "Warm, offline, in-process Python", fontsize=13.5, weight="bold")
    fig.text(0.69, 0.172, "Excludes loading, fitting, simulator, UI, network.", fontsize=12.5, color=MUTED)
    fig.text(0.69, 0.139, "Repeated calls across frozen validation snapshots.", fontsize=12.5, color=MUTED)

    fig.text(0.04, 0.055, "Sources", fontsize=11.5, color=MUTED, weight="bold")
    for x, key, label in ((0.1, "journeys", "[1] Recorded pairs"), (0.29, "desktop", "[2] Foreground desktop run"), (0.56, "selector", "[3] Frozen validation timing")):
        text = fig.text(x, 0.055, label, fontsize=11.5, color=MUTED)
        text.set_url("../validation/" + SOURCES[key].split("/validation/", 1)[1])

    output_dir.mkdir(parents=True, exist_ok=True)
    png, svg = (output_dir / f"readme-benchmarks.{suffix}" for suffix in ("png", "svg"))
    description = (
        "Two exploratory recording pairs: Cross-city ordinary 601 seconds versus priority 473 seconds, "
        "21.3 percent shorter with civilian mean excess increasing 2.19 seconds; Westhaven 426.5 versus "
        "322.5 seconds, 24.4 percent shorter with civilian mean excess increasing 1.14 seconds. "
        "One desktop, two foreground 30-second windows: overview 152.5 FPS, close follow 129.7 FPS; "
        "p95 frame intervals 12.1 and 12.2 milliseconds. Warm offline Python five-candidate selection, "
        "2400 calls per method across 12 validation snapshots: learned median 0.2241 ms and p95 0.2512 ms; "
        "analytical median 0.0429 ms and p95 0.0549 ms. Recorded fixed/analytical priority examples and the offline AI study are separate."
    )
    metadata = {"Title": "AFTERLIGHT recorded journeys and measured performance", "Description": description}
    fig.savefig(png, dpi=100, metadata=metadata)
    fig.savefig(svg, metadata={**metadata, "Date": None})
    plt.close(fig)
    raw = svg.read_text(encoding="utf-8")
    raw = re.sub(r"<svg\b", '<svg role="img" aria-labelledby="benchmark-title benchmark-description"', raw, count=1)
    root_end = raw.index(">", raw.index("<svg")) + 1
    raw = raw[:root_end] + '\n <title id="benchmark-title">AFTERLIGHT benchmarks</title>\n <desc id="benchmark-description">' + escape(description) + "</desc>" + raw[root_end:]
    raw = "\n".join(line.rstrip() for line in raw.splitlines()) + "\n"
    svg.write_text(raw, encoding="utf-8", newline="\n")
    return {
        "values": values,
        "sources": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES.values()},
        "outputs": {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in (png, svg)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/images")
    print(json.dumps(render(parser.parse_args().output_dir), indent=2))
