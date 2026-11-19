"""Render this retained dataset only; never run tools, fetch or reuse missing inputs."""
from collections import Counter
from pathlib import Path
import hashlib
import json


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    root = Path(__file__).resolve().parent
    raw = (root / "results.json").read_bytes()
    result = json.loads(raw)
    records = json.loads((root / "observations.json").read_bytes())["records"]
    files = json.loads((root / "source-metrics.json").read_bytes())["files"]
    assert result["historical"] is True
    assert dict(Counter(x["category"] for x in records)) == result["observed"]["by_category"]
    assert len(records) == result["observed"]["finding_records"]
    assert len(files) == result["observed"]["selected_translation_units"]
    assert sum(x["physical_loc"] for x in files) == result["observed"]["physical_loc"]
    for name, info in result["public_artifacts"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == info["sha256"]
    fig = plt.figure(figsize=(10.8, 5.6), facecolor="#0b1220")
    ax = fig.add_axes((0, 0, 1, 1)); ax.set_xlim(0, 1080); ax.set_ylim(0, 560); ax.axis("off")
    def text(x, y, value, size=13, color="#e5edf7", **kwargs):
        ax.text(x, y, value, fontsize=size, color=color, fontfamily="DejaVu Sans", **kwargs)
    text(44, 505, "LevelDB · retained native analysis", size=23, weight="bold")
    text(44, 471, "HISTORICAL · 16 NOV 2026 · selected C++11 compilation-database scope", size=11, color="#fbbf24")
    values = [(str(len(files)), "selected translation units"), (f"{result['observed']['physical_loc']:,}", "physical source lines"), (str(len(records)), "experimental rule observations")]
    for x, (value, label) in zip((44, 370, 696), values):
        ax.add_patch(FancyBboxPatch((x, 357), 298, 90, boxstyle="round,pad=0.02,rounding_size=10", facecolor="#152238", edgecolor="#263850"))
        text(x+17, 405, value, size=26, weight="bold");text(x+17, 377, label, size=10.5, color="#b7c6d9")
    rows = [("memory_safety", "Memory patterns", "#38bdf8"), ("misra", "MISRA-tagged patterns", "#a78bfa"), ("modernization", "Modernization", "#34d399"), ("complexity", "Complexity", "#fbbf24")]
    maximum = max(result["observed"]["by_category"].values())
    for y, (key, label, color) in zip((308, 254, 200, 146), rows):
        value = result["observed"]["by_category"][key];text(44, y, label, size=13)
        ax.barh(y+4, 590*value/maximum, left=280, height=22, color=color)
        text(892, y, str(value), size=14, weight="bold")
    text(44, 91, "486 observations are review prompts, not confirmed defects or a readiness score.", size=11, color="#b7c6d9")
    text(44, 63, "Linux x86_64 · GCC 14.2 · libclang 19.1.7 · upstream 99b3c03b3284…", size=10, color="#94a8c1")
    text(44, 35, "Git ownership / risk / policy gate: not collected in this native-only snapshot.", size=10, color="#94a8c1")
    fig.savefig(root / "results-card.png", dpi=140, facecolor=fig.get_facecolor(), metadata={"Description":"Data-derived documentation card; results.json SHA256 "+hashlib.sha256(raw).hexdigest()})
    plt.close(fig)


if __name__ == "__main__":
    main()
