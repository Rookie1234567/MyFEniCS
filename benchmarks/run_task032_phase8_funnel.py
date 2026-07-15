from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _complex(value: Any) -> complex:
    if isinstance(value, list) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _order_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        str(row["side"]),
        int(row["m"]),
        int(row["n"]),
        str(row["polarization"]),
    )


def _order_comparison(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    significant_power: float,
    relative_tolerance: float,
    weak_absolute_tolerance: float,
) -> dict[str, Any]:
    previous_rows = {
        _order_key(row): row
        for row in previous.get("validation", {}).get(
            "external_diffraction_orders", []
        )
    }
    current_rows = {
        _order_key(row): row
        for row in current.get("validation", {}).get(
            "external_diffraction_orders", []
        )
    }
    common = sorted(set(previous_rows) & set(current_rows))
    rows = []
    for key in common:
        first = previous_rows[key]
        second = current_rows[key]
        if not (bool(first["propagating"]) and bool(second["propagating"])):
            continue
        amplitude_first = _complex(first["outgoing_amplitude_at_boundary"])
        amplitude_second = _complex(second["outgoing_amplitude_at_boundary"])
        amplitude_delta = abs(amplitude_second - amplitude_first)
        amplitude_scale = max(abs(amplitude_first), abs(amplitude_second), 1.0e-30)
        power_first = float(first["power_ratio"])
        power_second = float(second["power_ratio"])
        power_delta = abs(power_second - power_first)
        power_scale = max(abs(power_first), abs(power_second), 1.0e-30)
        significant = power_scale >= significant_power
        row = {
            "side": key[0],
            "m": key[1],
            "n": key[2],
            "polarization": key[3],
            "significant": significant,
            "previous_power_ratio": power_first,
            "current_power_ratio": power_second,
            "power_absolute_delta": power_delta,
            "power_relative_delta": power_delta / power_scale,
            "complex_amplitude_absolute_delta": amplitude_delta,
            "complex_amplitude_relative_delta": amplitude_delta / amplitude_scale,
            "gate_pass": (
                max(power_delta / power_scale, amplitude_delta / amplitude_scale)
                <= relative_tolerance
                if significant
                else max(power_delta, amplitude_delta) <= weak_absolute_tolerance
            ),
        }
        rows.append(row)
    significant_rows = [row for row in rows if row["significant"]]
    weak_rows = [row for row in rows if not row["significant"]]
    return {
        "available": bool(previous_rows and current_rows),
        "matching_propagating_order_count": len(rows),
        "significant_order_count": len(significant_rows),
        "weak_order_count": len(weak_rows),
        "max_significant_power_relative_delta": max(
            (row["power_relative_delta"] for row in significant_rows), default=0.0
        ),
        "max_significant_complex_amplitude_relative_delta": max(
            (
                row["complex_amplitude_relative_delta"]
                for row in significant_rows
            ),
            default=0.0,
        ),
        "all_order_gates_pass": bool(rows) and all(row["gate_pass"] for row in rows),
        "orders": rows,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Task32 Phase8 mode truncation records")
    parser.add_argument("records", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mandatory-total-tolerance", type=float, default=1.0e-5)
    parser.add_argument("--strong-total-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--significant-order-relative-tolerance", type=float, default=1.0e-4)
    parser.add_argument("--significant-order-power", type=float, default=1.0e-8)
    parser.add_argument("--weak-order-absolute-tolerance", type=float, default=1.0e-8)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if len(args.records) < 2:
        raise SystemExit("Phase8 funnel requires at least two records.")
    records = []
    sources = []
    for requested_path in args.records:
        path = requested_path if requested_path.is_absolute() else ROOT / requested_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        mode_count = int(payload["case"]["requested_modes_per_direction"])
        records.append((mode_count, payload, path))
        sources.append(
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": _sha256(path),
                "mode_count_per_direction": mode_count,
                "commit_sha": payload["metadata"]["commit_sha"],
                "tracked_source_dirty": payload["metadata"]["tracked_source_dirty"],
            }
        )
    if [item[0] for item in records] != sorted({item[0] for item in records}):
        raise SystemExit("Phase8 records must be unique and strictly increasing in M.")
    identity = {
        (
            float(payload["case"]["h_nm"]),
            float(payload["case"]["wavelength_nm"]),
            float(payload["case"]["incident_grazing_deg"]),
            str(payload["case"]["polarization_kind"]),
        )
        for _count, payload, _path in records
    }
    if len(identity) != 1:
        raise SystemExit("Phase8 records do not describe one physical case.")

    comparisons = []
    for (previous_m, previous, _), (current_m, current, _) in zip(
        records[:-1], records[1:]
    ):
        previous_power = previous["validation"]["port_power"]
        current_power = current["validation"]["port_power"]
        deltas = {
            key: abs(float(current_power[key]) - float(previous_power[key]))
            for key in ("R_total", "T_total", "A_balance")
        }
        orders = _order_comparison(
            previous,
            current,
            significant_power=args.significant_order_power,
            relative_tolerance=args.significant_order_relative_tolerance,
            weak_absolute_tolerance=args.weak_order_absolute_tolerance,
        )
        comparisons.append(
            {
                "previous_mode_count": previous_m,
                "current_mode_count": current_m,
                "absolute_total_deltas": deltas,
                "max_absolute_total_delta": max(deltas.values()),
                "mandatory_total_gate_pass": max(deltas.values())
                <= args.mandatory_total_tolerance,
                "strong_total_gate_pass": max(deltas.values())
                <= args.strong_total_tolerance,
                "interface_projection_residual": float(
                    current["validation"]["interface_e_projection"][
                        "combined_relative_residual"
                    ]
                ),
                "interface_projection_gate_pass": float(
                    current["validation"]["interface_e_projection"][
                        "combined_relative_residual"
                    ]
                )
                <= 1.0e-8,
                "diffraction_orders": orders,
            }
        )
    final = comparisons[-1]
    qualifying_order_gate = (
        final["diffraction_orders"]["available"]
        and final["diffraction_orders"]["all_order_gates_pass"]
    )
    converged = bool(
        final["mandatory_total_gate_pass"]
        and final["interface_projection_gate_pass"]
        and qualifying_order_gate
    )
    output = {
        "schema_version": 1,
        "benchmark_id": "task032_phase8_mode_truncation_funnel",
        "status": "mode_truncation_converged" if converged else "mode_truncation_pending",
        "case": {
            "h_nm": next(iter(identity))[0],
            "wavelength_nm": next(iter(identity))[1],
            "incident_grazing_deg": next(iter(identity))[2],
            "polarization_kind": next(iter(identity))[3],
            "mode_counts": [item[0] for item in records],
        },
        "tolerances": {
            "mandatory_total": args.mandatory_total_tolerance,
            "strong_total": args.strong_total_tolerance,
            "significant_order_relative": args.significant_order_relative_tolerance,
            "significant_order_power": args.significant_order_power,
            "weak_order_absolute": args.weak_order_absolute_tolerance,
            "interface_projection": 1.0e-8,
        },
        "sources": sources,
        "comparisons": comparisons,
        "qualification": {
            "mode_count_converged": converged,
            "selected_mode_count_per_direction": records[-1][0] if converged else None,
            "latest_pair_mandatory_total_gate_pass": final["mandatory_total_gate_pass"],
            "latest_pair_strong_total_gate_pass": final["strong_total_gate_pass"],
            "latest_pair_order_gate_pass": qualifying_order_gate,
            "all_sources_clean": all(
                not source["tracked_source_dirty"] for source in sources
            ),
        },
    }
    path = args.output if args.output.is_absolute() else ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Task32 Phase8 funnel: {path}")
    print(f"Task32 Phase8 status: {output['status']}")
    if not converged:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
