#!/usr/bin/env python3
"""Offline all-340-mode, power, and directional-gate analysis for Task40 Review V4."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from benchmarks.postprocess_task40_review_v4_directional_cross import (
    ROOT,
    RUNS,
    _canonical_json,
    _json_default,
)

VOLUME_RESULT = (
    ROOT
    / "benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/"
    "four_corner_volume_v1.json"
)
FROZEN_CHANNELS = (
    ROOT / "docs/task40extra_0p7nm_engineering/outcomes/records/channel_study_v2.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/"
    "four_corner_modes_v1.json"
)
INCIDENT_AMPLITUDE = 1.0
SIGNIFICANT_MODE_LIMIT = 0.01
POWER_LIMIT = 1.0e-3
ENERGY_CLOSURE_LIMIT = 1.0e-5
LEGACY_FAILED_KEYS = (
    ("top", 0, 0, "s"),
    ("bottom", -1, 0, "s"),
)
PAIRS = {
    "G00_to_G11": ("G00", "G11"),
    "x_increment_G10_minus_G00": ("G00", "G10"),
    "z_increment_G01_minus_G00": ("G00", "G01"),
    "x_to_G1_G10_minus_G11": ("G10", "G11"),
    "z_to_G1_G01_minus_G11": ("G01", "G11"),
}


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                indent=2,
                sort_keys=True,
                allow_nan=False,
                default=_json_default,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _complex(value: Any) -> complex:
    if isinstance(value, complex):
        return value
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _add_g1_normalization(
    comparison: dict[str, Any],
    g1: dict[tuple[str, int, int, str], dict[str, Any]],
) -> None:
    for row in comparison["all_ordered_mode_comparisons"]:
        key = tuple(row["key"])
        g1_amplitude = _complex(g1[key]["outgoing_amplitude_at_boundary"])
        denominator = max(abs(g1_amplitude), sys.float_info.min)
        row["g1_normalized_denominator"] = float(abs(g1_amplitude))
        row["g1_normalized_amplitude_difference"] = float(
            row["absolute_amplitude_difference"] / denominator
        )


def _interaction_rows(
    inventories: dict[str, dict[tuple[str, int, int, str], dict[str, Any]]],
) -> list[dict[str, Any]]:
    output = []
    for key in inventories["G00"]:
        amplitudes = {
            label: _complex(inventories[label][key]["outgoing_amplitude_at_boundary"])
            for label in ("G00", "G10", "G01", "G11")
        }
        mixed = amplitudes["G11"] - amplitudes["G10"] - amplitudes["G01"] + amplitudes["G00"]
        magnitude = abs(mixed)
        output.append(
            {
                "key": list(key),
                "corner_amplitudes_at_boundary": {
                    label: [value.real, value.imag]
                    for label, value in amplitudes.items()
                },
                "mixed_complex": [mixed.real, mixed.imag],
                "absolute_mixed_difference": float(magnitude),
                "relative_to_G00_amplitude": float(
                    magnitude / max(abs(amplitudes["G00"]), sys.float_info.min)
                ),
                "incident_normalized_mixed_difference": float(
                    magnitude / INCIDENT_AMPLITUDE
                ),
                "g1_normalized_mixed_difference": float(
                    magnitude / max(abs(amplitudes["G11"]), sys.float_info.min)
                ),
            }
        )
    return output


def _power_values(run: Any) -> dict[str, Any]:
    power = run.official_power
    volume = run.official_volume
    r_total = float(power["R_total"])
    t_total = float(power["T_total"])
    a_balance = float(power["A_balance"])
    a_volume = float(volume["A_volume_total"])
    return {
        "R_total": r_total,
        "T_total": t_total,
        "A_balance": a_balance,
        "A_volume_total": a_volume,
        "R00_s": power.get("R00_s"),
        "R00_p": power.get("R00_p"),
        "R00_total": power.get("R00_total"),
        "A_balance_minus_A_volume_absolute": abs(a_balance - a_volume),
        "port_volume_energy_closure_absolute": abs(r_total + t_total + a_volume - 1.0),
    }


def _run_analysis(
    volume_path: Path,
    frozen_path: Path,
    output: Path,
) -> None:
    started_utc = datetime.now(timezone.utc).isoformat()
    from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
        _load_run,
        _qualified_environment,
        _sha256,
    )
    from benchmarks.postprocess_task40_p3_mode_staircase import (
        _expected_manual_keys,
        _mode_inventory,
        _same_discretization_mode_comparison,
    )

    volume_bytes = volume_path.read_bytes()
    volume_result = json.loads(volume_bytes)
    if volume_result.get("status") != "completed":
        raise ValueError("the saved four-corner volume comparison is not complete")
    expected_identity = volume_result["run_identities"]
    signature_hashes = {
        value["input_signature_sha256"] for value in expected_identity.values()
    }
    if len(signature_hashes) != 1:
        raise ValueError("saved four-corner physical input signatures differ")

    environment = _qualified_environment()
    environment["thread_environment"] = {
        key: os.environ.get(key)
        for key in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        )
    }
    runs = {label: _load_run(label, root) for label, root in RUNS.items()}
    signatures = {
        label: _canonical_json(run.input_signature) for label, run in runs.items()
    }
    if len(set(signatures.values())) != 1:
        raise ValueError("four saved runs have different physical input signatures")
    if _sha256_bytes(next(iter(signatures.values())).encode()) != next(iter(signature_hashes)):
        raise ValueError("loaded run physical signature differs from completed volume analysis")

    for label, run in runs.items():
        recorded = expected_identity[label]
        if str(run.root) != recorded["run_root"]:
            raise ValueError(f"{label}: run root differs from the volume artifact")
        if _sha256(run.root / "run_manifest.json") != recorded["run_manifest_sha256"]:
            raise ValueError(f"{label}: run manifest changed after volume integration")
        for field in ("source_sha", "input_sha256", "physical_model_sha256"):
            if run.manifest[field] != recorded[
                "solver_source_sha" if field == "source_sha" else field
            ]:
                raise ValueError(f"{label}: {field} differs from the volume artifact")

    inventories = {}
    inventory_facts = {}
    for label, run in runs.items():
        inventories[label], inventory_facts[label] = _mode_inventory(run, 340)
    ordered_keys = list(inventories["G00"])
    if any(list(inventories[label]) != ordered_keys for label in RUNS if label != "G00"):
        raise ValueError("the four ordered 340-mode inventories differ")
    if set(ordered_keys) != _expected_manual_keys(8, 2):
        raise ValueError("the ordered modes do not match the frozen M=8, N=2 inventory")

    frozen_bytes = frozen_path.read_bytes()
    frozen = json.loads(frozen_bytes)["frozen_baseline"]
    frozen_order = [tuple(item) for item in frozen["selected_keys"]]
    frozen_keys = set(frozen_order)
    if len(frozen_keys) != 11 or not frozen_keys.issubset(set(ordered_keys)):
        raise ValueError("the frozen significant 11-key set is invalid")

    comparisons = {}
    for name, (first_label, second_label) in PAIRS.items():
        comparison = _same_discretization_mode_comparison(
            inventories[first_label],
            inventories[second_label],
            significant_keys=frozen_keys,
            incident_amplitude=INCIDENT_AMPLITUDE,
            relative_limit=SIGNIFICANT_MODE_LIMIT,
        )
        _add_g1_normalization(comparison, inventories["G11"])
        comparisons[name] = comparison
    mixed_modes = _interaction_rows(inventories)

    def pair_row(pair_name: str, key: tuple[str, int, int, str]) -> dict[str, Any]:
        return next(
            row
            for row in comparisons[pair_name]["all_ordered_mode_comparisons"]
            if tuple(row["key"]) == key
        )

    selected_details = []
    for key in frozen_order:
        selected_details.append(
            {
                "key": list(key),
                "per_run": {
                    label: {
                        "outgoing_amplitude_at_boundary": [
                            _complex(row["outgoing_amplitude_at_boundary"]).real,
                            _complex(row["outgoing_amplitude_at_boundary"]).imag,
                        ],
                        "propagating": bool(row["propagating"]),
                        "power_ratio": float(row["power_ratio"]),
                    }
                    for label, inventory in inventories.items()
                    for row in (inventory[key],)
                },
                "pairwise": {
                    pair_name: pair_row(pair_name, key)
                    for pair_name in comparisons
                },
                "mixed_interaction": mixed_modes[ordered_keys.index(key)],
            }
        )

    volume_comparison = volume_result["comparison"]
    field_metrics = {}
    physical_quantities = volume_comparison["regions"]["physical_domain"]["quantities"]
    for quantity in ("E_scattered", "scaled_curl_E_scattered"):
        metric = physical_quantities[quantity]
        field_metrics[quantity] = {
            "x_error_relative_to_G1": metric["Gx_relative_to_G1"],
            "z_error_relative_to_G1": metric["Gz_relative_to_G1"],
            "x_error_absolute_l2": metric["Gx_to_G1_difference_l2_norm"],
            "z_error_absolute_l2": metric["Gz_to_G1_difference_l2_norm"],
            "x_closer_to_G1": metric["Gx_relative_to_G1"] < metric["Gz_relative_to_G1"],
            "relative_error_limit": 0.01,
        }

    top_key = ("top", 0, 0, "s")
    top_gx = pair_row("x_to_G1_G10_minus_G11", top_key)
    top_gz = pair_row("z_to_G1_G01_minus_G11", top_key)
    modal_ranking = {
        "key": list(top_key),
        "x_error_g1_normalized": top_gx["g1_normalized_amplitude_difference"],
        "z_error_g1_normalized": top_gz["g1_normalized_amplitude_difference"],
        "x_closer_to_G1": (
            top_gx["g1_normalized_amplitude_difference"]
            < top_gz["g1_normalized_amplitude_difference"]
        ),
        "relative_error_limit": 0.01,
        "x_to_G1": top_gx,
        "z_to_G1": top_gz,
    }
    directional_metrics = {
        **field_metrics,
        "top_0_0_s_boundary_amplitude": modal_ranking,
    }
    x_dominance_supported = all(
        metric["x_closer_to_G1"] for metric in directional_metrics.values()
    )

    power_values = {label: _power_values(run) for label, run in runs.items()}
    power_comparisons = {}
    for name, first_label in (
        ("G00_to_G11", "G00"),
        ("G10_to_G11", "G10"),
        ("G01_to_G11", "G01"),
    ):
        values = {}
        for field in ("R_total", "T_total", "A_balance", "A_volume_total"):
            difference = abs(
                power_values["G11"][field] - power_values[first_label][field]
            )
            values[field] = {
                "first": power_values[first_label][field],
                "second": power_values["G11"][field],
                "absolute_difference": difference,
                "limit_absolute": POWER_LIMIT,
                "pass": difference <= POWER_LIMIT,
            }
        power_comparisons[name] = values

    gates = {
        "frozen_significant_modes_within_1_percent": all(
            value["significant_gate"]["pass"] for value in comparisons.values()
        ),
        "powers_within_1e-3": all(
            value["pass"]
            for pair in power_comparisons.values()
            for value in pair.values()
        ),
        "per_run_energy_closure_within_1e-5": all(
            values["A_balance_minus_A_volume_absolute"] <= ENERGY_CLOSURE_LIMIT
            and values["port_volume_energy_closure_absolute"] <= ENERGY_CLOSURE_LIMIT
            for values in power_values.values()
        ),
    }
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = {
        "schema": "task40.review-v4.directional-cross-modes.v1",
        "status": "completed",
        "analysis_source_sha": head,
        "started_utc": started_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "qualified_environment": environment,
        "volume_result": {
            "path": str(volume_path),
            "sha256": _sha256_bytes(volume_bytes),
            "analysis_source_sha": volume_result["analysis_source_sha"],
            "common_subcell_count": volume_comparison["common_subcell_count"],
            "material_tag_mismatch_count": volume_comparison[
                "material_tag_mismatch_count"
            ],
        },
        "frozen_significance": {
            "source": str(frozen_path),
            "sha256": _sha256_bytes(frozen_bytes),
            "rule": "use the preselected M0 frozen_baseline.selected_keys; do not reselect",
            "power_ratio_threshold": 1.0e-8,
            "incident_amplitude_reference": ["top", 0, 0, "s"],
            "incident_amplitude": INCIDENT_AMPLITUDE,
            "selected_keys": [list(key) for key in frozen_order],
        },
        "mode_inventory": {
            "ordered_mode_count": len(ordered_keys),
            "manual_M": 8,
            "manual_N": 2,
            "ordered_keys_identical_across_corners": True,
            "mode_output_sha256": {
                label: facts["mode_output_sha256"]
                for label, facts in inventory_facts.items()
            },
            "ordered_mode_manifest_sha256": {
                label: facts["ordered_mode_manifest_sha256"]
                for label, facts in inventory_facts.items()
            },
            "counts": {
                label: {
                    key: value
                    for key, value in facts.items()
                    if key in ("mode_count", "propagating_count", "power_carrying_count")
                }
                for label, facts in inventory_facts.items()
            },
        },
        "comparisons": comparisons,
        "mixed_interaction_all_340_modes": {
            "formula": "G11-G10-G01+G00",
            "mode_count": len(mixed_modes),
            "rows": mixed_modes,
        },
        "selected_mode_details": selected_details,
        "legacy_failed_channels": {
            str(key): next(item for item in selected_details if tuple(item["key"]) == key)
            for key in LEGACY_FAILED_KEYS
        },
        "field_directional_metrics": field_metrics,
        "top_0_0_s_directional_metric": modal_ranking,
        "x_direction_closer_for_all_three_preregistered_metrics": x_dominance_supported,
        "power_values_by_corner": power_values,
        "power_comparisons_to_G11": power_comparisons,
        "gates": gates,
        "limits": {
            "significant_mode_relative_to_first_amplitude": SIGNIFICANT_MODE_LIMIT,
            "power_absolute_difference": POWER_LIMIT,
            "energy_closure_absolute": ENERGY_CLOSURE_LIMIT,
        },
    }
    _atomic_json(output, result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--volume-result", type=Path, default=VOLUME_RESULT)
    parser.add_argument("--frozen-keys", type=Path, default=FROZEN_CHANNELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing mode result: {output}")
    _run_analysis(args.volume_result.resolve(), args.frozen_keys.resolve(), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
