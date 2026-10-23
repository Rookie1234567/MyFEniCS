import bisect
import hashlib
import html
import json
import math
from itertools import pairwise
from pathlib import Path

r = Path(__file__).resolve().parents[3]
o = r / "docs/task43_hp_adaptivity/outcomes/figures"
o.mkdir(parents=True, exist_ok=True)
records = r / "docs/task43_hp_adaptivity/outcomes/records"
inputs = {}


def load(p):
    p = Path(p)
    p = p if p.is_absolute() else r / p
    inputs[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return json.loads(p.read_text())


def text(x, y, value, size=12, anchor="start", color="#222"):
    return f'<text x="{x:.3f}" y="{y:.3f}" font-size="{size}" text-anchor="{anchor}" fill="{color}">{html.escape(str(value))}</text>'


def start(w, h):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="Arial, sans-serif"><rect width="100%" height="100%" fill="white"/>'
    ]


def mesh(path, name, pdegree):
    plan = load(path)
    leaves = plan["cell_interior_degrees"]
    base = plan["base_config"]["axis_values"]
    xs = sorted({v for c in leaves for v in (c["lower"][0], c["upper"][0])})
    scale = 3.0
    pw = 150
    ph = 420
    rows = 1 if pdegree else 2
    width = 850
    height = 165 + rows * 495
    svg = start(width, height)
    categories = []
    colors = {5: "#4c78a8", 6: "#f2a541"} if pdegree else {0: "#c8d9ea", 1: "#d77545"}
    for c in leaves:
        center = (c["lower"][0] + c["upper"][0]) / 2
        i = bisect.bisect_right(base["x"], center) - 1
        level = round(
            math.log2(
                (base["x"][i + 1] - base["x"][i]) / (c["upper"][0] - c["lower"][0])
            )
        )
        categories.append(c["degree"] if pdegree else level)
    title = (
        "R9: last accepted state, 110,472 independent FE unknowns"
        if pdegree
        else "h1: actual local refinement, 600 leaves, 47,235 independent FE unknowns"
    )
    svg += [
        text(35, 30, title, 19),
        text(
            35,
            55,
            "28 p5 cells + 152 p6 cells; R10 all-p6 diagnostic was not accepted."
            if pdegree
            else "180 roots: 46 requested + 14 closure splits; 120 level-0 + 480 level-1 leaves.",
            13,
        ),
    ]
    for j, (a, b) in enumerate(pairwise(xs)):
        col = j % 3
        row = j // 3
        left = 85 + col * 260
        top = 105 + row * 495
        mid = (a + b) / 2
        svg.append(
            text(
                left + pw / 2,
                top - 17,
                f"x slice = {mid:g} nm; slab [{a:g}, {b:g}]",
                12,
                "middle",
            )
        )
        for cell, category in zip(leaves, categories, strict=True):
            lo = cell["lower"]
            hi = cell["upper"]
            if lo[0] < mid < hi[0]:
                svg.append(
                    f'<rect x="{left + lo[1] * scale:.3f}" y="{top + (130 - hi[2]) * scale:.3f}" width="{(hi[1] - lo[1]) * scale:.3f}" height="{(hi[2] - lo[2]) * scale:.3f}" fill="{colors[category]}" stroke="white" stroke-width=".65"/>'
                )
        if 16.5 < mid < 33.5:
            svg.append(
                f'<rect x="{left + 45}" y="{top + 30}" width="60" height="360" fill="none" stroke="#111" stroke-dasharray="5 3"/>'
            )
        svg.append(
            f'<rect x="{left}" y="{top}" width="{pw}" height="{ph}" fill="none" stroke="#333"/>'
        )
        for z in [-10, 0, 30, 60, 90, 120, 130]:
            svg.append(text(left - 8, top + (130 - z) * scale + 4, z, 10, "end"))
        for y in [0, 15, 35, 50]:
            svg.append(text(left + y * scale, top + ph + 18, y, 10, "middle"))
        svg += [
            text(left + pw / 2, top + ph + 38, "y (nm)", 12, "middle"),
            f'<text transform="translate({left - 45},{top + ph / 2}) rotate(-90)" text-anchor="middle" font-size="12">z (nm)</text>',
        ]
    legend_y = height - 45
    for j, (category, color) in enumerate(colors.items()):
        svg += [
            f'<rect x="{85 + j * 260}" y="{legend_y - 12}" width="16" height="16" fill="{color}"/>',
            text(
                110 + j * 260,
                legend_y + 1,
                f"p={category}" if pdegree else f"h refinement level {category}",
                13,
            ),
        ]
    svg.append(
        text(
            35,
            height - 15,
            "Equal nm scale. yz sections, not 3D perspective. Dashed: material block; coarse h cells may span two slices.",
            11,
        )
    )
    svg.append("</svg>")
    (o / (name + ".svg")).write_text("\n".join(svg) + "\n")
    return {
        "plan": str(path),
        "leaves": len(leaves),
        "categories": {str(k): categories.count(k) for k in colors},
        "nm_scale_pixels": scale,
        "scope": "Actual leaf boxes. Slices do not display all 3D trace entity degrees.",
    }


selection = load(records / "round9_selection_transition9_v1.json")
run = Path(selection["selected_candidate"]["run_root"])
p9 = run / "candidate_plan.json"
h = load(records / "h1_real_action_qualification_v1.json")
hp = Path(h["evidence"]["PDE_record"]["path"])
hp = hp if hp.is_absolute() else r / hp
metadata = {
    "accepted9": mesh(p9, "accepted9_mesh_degree", True),
    "h1": mesh(hp.parent / "candidate_plan.json", "h1_mesh_levels", False),
}
trajectory = []
for i in range(1, 10):
    s = load(records / f"round{i}_selection_transition{i}_v1.json")
    c = load(s["selected_candidate"]["comparison_record_path"])
    if i == 1:
        trajectory.append(
            {
                "cycle": 0,
                "eta": c["selection"]["eta_parent"],
                "J": c["J_infinity"]["parent"]["value"],
                "accepted": False,
                "role": "initial",
            }
        )
    trajectory.append(
        {
            "cycle": i,
            "eta": c["selection"]["eta_candidate"],
            "J": c["J_infinity"]["candidate"]["value"],
            "accepted": True,
        }
    )
c = load(
    r
    / "benchmarks/artifacts/task43/round1_candidates/comparisons/round10_p_up_attempt1/candidate_comparison_v2.json"
)
trajectory.append(
    {
        "cycle": 10,
        "eta": c["selection"]["eta_candidate"],
        "J": c["J_infinity"]["candidate"]["value"],
        "accepted": False,
        "role": "rejected_diagnostic",
    }
)
svg = start(940, 430)
svg += [
    text(35, 28, "Frozen selection history: 9 accepted updates; R10 rejected", 19),
    text(
        35,
        50,
        "R10: G reduction below frozen noise. Precision failure of R00_s is a separate judgment.",
        12,
    ),
]
for column, (key, label, minimum, maximum, threshold, ticks) in enumerate(
    [
        (
            "eta",
            "G field difference (fixed incident floor)",
            1e-5,
            1.0,
            1e-4,
            [1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1],
        ),
        (
            "J",
            "Largest normalized observable error J",
            0.5,
            1e6,
            1,
            [1, 10, 100, 1000, 10000, 100000, 1000000],
        ),
    ]
):
    left = 80 + column * 450
    top = 90
    w = 330
    hgt = 245

    def x(v, left=left, w=w):
        return left + v / 10 * w

    def y(v, top=top, maximum=maximum, minimum=minimum, hgt=hgt):
        return (
            top
            + (math.log10(maximum) - math.log10(v))
            / (math.log10(maximum) - math.log10(minimum))
            * hgt
        )

    for tick in ticks:
        yy = y(tick)
        svg.append(f'<path d="M{left},{yy:.3f}h{w}" fill="none" stroke="#e0e0e0"/>')
        svg.append(text(left - 8, yy + 4, f"{tick:g}", 10, "end"))
    for tick in range(11):
        svg.append(text(x(tick), top + hgt + 19, tick, 10, "middle"))
    svg.append(f'<path d="M{left},{top}v{hgt}h{w}" fill="none" stroke="#444"/>')
    svg.append(text(left + w / 2, top - 13, label, 13, "middle"))
    svg.append(
        text(
            left + w / 2,
            top + hgt + 41,
            "candidate cycle (R10 is diagnostic only)",
            11,
            "middle",
        )
    )
    svg.append(
        f'<path d="M{left},{y(threshold):.3f}h{w}" fill="none" stroke="#4f7d3a" stroke-width="1.5" stroke-dasharray="5 3"/>'
    )
    svg.append(text(left + w + 5, y(threshold) + 4, "limit", 10, color="#4f7d3a"))
    pts = " ".join(f"{x(a['cycle']):.3f},{y(a[key]):.3f}" for a in trajectory[:-1])
    svg.append(
        f'<polyline points="{pts}" fill="none" stroke="#4c78a8" stroke-width="2"/>'
    )
    for a in trajectory[:-1]:
        svg.append(
            f'<circle cx="{x(a["cycle"]):.3f}" cy="{y(a[key]):.3f}" r="3.5" fill="#4c78a8"/>'
        )
    a = trajectory[-1]
    svg.append(
        f'<circle cx="{x(10):.3f}" cy="{y(a[key]):.3f}" r="6" fill="white" stroke="#b04444" stroke-width="2"/>'
    )
svg.append(
    text(
        35,
        410,
        "Blue: initial state and accepted R1-R9. Hollow red: unaccepted R10. Vertical axes are logarithmic; all data vs Y6_1.",
        12,
    )
)
svg.append("</svg>")
(o / "selection_trajectory.svg").write_text("\n".join(svg) + "\n")
metadata["trajectory"] = trajectory
metadata["input_sha256"] = inputs
metadata["generator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
metadata["output_sha256"] = {
    name: hashlib.sha256((o / name).read_bytes()).hexdigest()
    for name in (
        "accepted9_mesh_degree.svg",
        "h1_mesh_levels.svg",
        "selection_trajectory.svg",
    )
}
(o / "figure_provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
print(
    {
        "figures": list(metadata)[:2],
        "trajectory_entries": len(trajectory),
        "hash_bound_inputs": len(inputs),
    }
)
