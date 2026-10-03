"""Restore the saved Task40 fields and perform the two preregistered V5 comparisons."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GX = ROOT / (
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_gx560_manual_m2_v3_v1__full3d_iterative__mpi1__Mna/"
    "20261003T002312.848713Z"
)
DEFAULT_F5 = ROOT / (
    "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1__full3d_iterative__mpi1__Mna/"
    "20261002T000242.608221Z"
)
FROZEN_V4_VOLUME = ROOT / (
    "benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/"
    "four_corner_volume_v1.json"
)
FROZEN_V4_VOLUME_SHA256 = "5f8004f51cb7d9543730281ace16f296cdc47b0358c66038302bf4f39ac40c17"
FROZEN_KEYS = ROOT / "docs/task40extra_0p7nm_engineering/outcomes/records/channel_study_v2.json"
RUN_SUMMARY_NAME = "task40extra_nonseparable_0p7nm_p6q4_summary.json"
FIELD_NAMES = (
    "E_total",
    "E_scattered",
    "H_total",
    "H_scattered",
    "curl_E_total",
    "curl_E_scattered",
    "scaled_curl_E_total",
    "scaled_curl_E_scattered",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _fixed_f5_norms(gx: Any, f5: Any, archive_path: Path) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    data = _read_json(archive_path)
    digest = _sha256(archive_path)
    if digest != FROZEN_V4_VOLUME_SHA256:
        raise ValueError("the V4 denominator archive SHA differs from the frozen review artifact")
    if (
        data.get("schema") != "task40.review-v4.directional-cross-volume.v1"
        or data.get("status") != "completed"
    ):
        raise ValueError("the frozen V4 comparison archive is unavailable or changed")
    identities = data["run_identities"]
    for key, run, expected in (
        ("G10", gx, "task40extra_0p7nm_nonseparable_gx560_manual_m2_v3_v1"),
        ("G11", f5, "task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1"),
    ):
        row = identities[key]
        if (
            row["run_id"] != expected
            or row["run_root"] != str(run.root)
            or row["run_manifest_sha256"] != _sha256(run.root / "run_manifest.json")
        ):
            raise ValueError(f"frozen V4 {key} identity differs from the current saved run")
    norms: dict[str, dict[str, float]] = {}
    for region, row in data["comparison"]["regions"].items():
        norms[region] = {
            name: float(quantity["corner_l2_norms"]["G11"])
            for name, quantity in row["quantities"].items()
        }
    frozen_checks = {
        ("physical_domain", "E_scattered"): 0.8964588762723267,
        ("physical_domain", "scaled_curl_E_scattered"): 0.8963653695824167,
    }
    for (region, name), expected in frozen_checks.items():
        if not math.isclose(norms[region][name], expected, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError(f"frozen F5 norm changed for {region}/{name}")
    return norms, {
        "path": str(archive_path.resolve()),
        "sha256": digest,
        "archive_sha256": digest,
        "schema": data["schema"],
        "Gx_run_root": str(gx.root),
        "F5_run_root": str(f5.root),
        "normalization_rule": "V4 archived G11/F5 same-quantity same-region L2 norms; never recomputed on the V5 union",
        "norms": norms,
    }


def _residual_evidence(run_root: Path) -> dict[str, Any]:
    path = run_root / RUN_SUMMARY_NAME
    summary = _read_json(path)
    final = summary.get("final_residual", {})
    post_release = summary.get("post_release_final_residual", {})
    value = final.get("explicit_relative_residual")
    tail = post_release.get("explicit_relative_residual")
    if value is None or tail is None:
        raise ValueError("Gx784 full A6 independently computed residual is missing")
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "schema": summary.get("schema"),
        "status": summary.get("status"),
        "result_classification": summary.get("result_classification"),
        "explicit_relative_A6_true_residual": float(value),
        "post_release_explicit_relative_A6_true_residual": float(tail),
        "post_release_residual_gate": summary.get("gates", {}).get(
            "post_release_residual_gate"
        ),
        "limit": 1.0e-6,
    }


def _power_summary(run: Any) -> dict[str, Any]:
    power = run.official_power
    volume = run.official_volume
    names = ("R_total", "T_total", "A_balance", "R00_s", "R00_p", "R00_total")
    output = {name: float(power[name]) for name in names}
    output["A_volume_total"] = float(volume["A_volume_total"])
    output["A_balance_minus_A_volume_absolute"] = abs(
        output["A_balance"] - output["A_volume_total"]
    )
    output["port_volume_energy_closure_absolute"] = abs(
        output["R_total"] + output["T_total"] + output["A_volume_total"] - 1.0
    )
    return output


def _mode_inventory(run: Any, expected_count: int) -> dict[str, Any]:
    from benchmarks.postprocess_task40_p3_mode_staircase import _mode_inventory as load_modes

    _by_key, facts = load_modes(run, expected_count)
    records = facts["records"]
    near_zero_count = sum(
        math.isfinite(float(row["power_ratio"]))
        and abs(float(row["power_ratio"])) <= 1.0e-8
        for row in records
    )
    return {
        **facts,
        "records": records,
        "near_zero_power_ratio_count_threshold_1e-8": int(near_zero_count),
        "nonfinite_complex_or_power_fields": 0,
    }


def _mode_comparison(
    first: dict[tuple[str, int, int, str], dict[str, Any]],
    second: dict[tuple[str, int, int, str], dict[str, Any]],
    f5: dict[tuple[str, int, int, str], dict[str, Any]],
    significant_keys: set[tuple[str, int, int, str]],
) -> dict[str, Any]:
    from benchmarks.postprocess_task40_p3_mode_staircase import (
        _same_discretization_mode_comparison,
    )

    result = _same_discretization_mode_comparison(
        first,
        second,
        significant_keys=significant_keys,
        incident_amplitude=1.0,
        relative_limit=1.0e-2,
    )
    rows = result["all_ordered_mode_comparisons"]
    for row in rows:
        key = tuple(row["key"])
        delta = float(row["absolute_amplitude_difference"])
        f5_amplitude = complex(
            float(f5[key]["outgoing_amplitude_at_boundary"][0]),
            float(f5[key]["outgoing_amplitude_at_boundary"][1]),
        )
        row["fixed_F5_amplitude_denominator"] = float(abs(f5_amplitude))
        row["fixed_F5_normalized_amplitude_difference"] = float(
            delta / max(abs(f5_amplitude), sys.float_info.min)
        )
    return result


def _run_independent_checker(output: Path) -> dict[str, Any]:
    checker_output = output.with_name("gx784_independent_check.json")
    completed = subprocess.run(
        [
            sys.executable,
            "-u",
            "-m",
            "benchmarks.check_task40_review_v5_gx784",
            str(output),
            "--output",
            str(checker_output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "independent V5 checker could not complete: "
            + completed.stdout[-4000:]
            + completed.stderr[-4000:]
        )
    return {
        "comparison_path": str(output),
        "comparison_sha256": _sha256(output),
        "checker_path": str(checker_output),
        "checker_sha256": _sha256(checker_output),
        "checker_record": _read_json(checker_output),
    }


def _analysis(
    gx_root: Path,
    f5_root: Path,
    gx784_root: Path,
    output: Path,
    *,
    frozen_volume_path: Path = FROZEN_V4_VOLUME,
    frozen_keys_path: Path = FROZEN_KEYS,
) -> dict[str, Any]:
    started = time.monotonic()
    started_utc = datetime.now(timezone.utc).isoformat()
    gx784_root = gx784_root.resolve()
    from benchmarks.run_task40_v5_postprocess_service import _preflight_case

    preflight = _preflight_case(gx784_root)
    run_manifest = _read_json(gx784_root / "run_manifest.json")
    raw_summary_path = gx784_root / RUN_SUMMARY_NAME
    raw_solver_summary = _read_json(raw_summary_path)
    solver_preflight = preflight["solver_gate"]
    if not preflight["ready_for_supervised_field_work"]:
        output = output.resolve()
        if output.exists():
            raise FileExistsError(f"refusing to overwrite V5 held comparison output: {output}")
        held_payload = {
            "schema": "task40extra.review-v5.gx784-paired-comparison.v1",
            "status": "completed",
            "classification": (
                "solver_or_recovery_gate_not_passed_comparison_held"
                if not solver_preflight["pass"]
                else "saved_field_archive_missing_or_hash_mismatch_comparison_held"
            ),
            "started_utc": started_utc,
            "completed_utc": datetime.now(timezone.utc).isoformat(),
            "runs": {
                "Gx784": {
                    "run_root": str(gx784_root),
                    "run_id": raw_solver_summary.get("run_id"),
                    "field_restoration_sample_witness": {"pass": False},
                }
            },
            "solver_evidence": {
                "path": str(raw_summary_path.resolve()),
                "sha256": preflight["worker_summary_sha256"],
                "run_manifest_path": preflight["run_manifest_path"],
                "run_manifest_sha256": preflight["run_manifest_sha256"],
                "source_sha": preflight["source_sha"],
            },
            "solver_preflight_diagnostics": solver_preflight,
            "field_artifact_preflight": preflight["field_artifact_preflight"],
            "comparison_status": "held_before_FE_import_field_restoration_and_power_comparison",
            "postprocess_elapsed_monotonic_seconds": time.monotonic() - started,
            "analysis_source": {
                "source_sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "working_tree_status": subprocess.check_output(
                    ["git", "status", "--porcelain"], cwd=ROOT, text=True
                ).splitlines(),
                "script_sha256": _sha256(Path(__file__).resolve()),
                "qualified_environment_imported": False,
            },
        }
        _write_json(output, held_payload)
        return _run_independent_checker(output)

    from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
        _load_run,
        _qualified_environment,
    )
    from src.postprocessing.task40_saved_field_h_comparison import (
        _exact_axis_union_many,
        compare_common_subcell_volume,
        restore_p6_total_field,
        total_field_sample_witness,
    )

    environment = _qualified_environment()

    runs = {
        "Gx": _load_run("Gx", gx_root),
        "F5": _load_run("F5", f5_root),
        "Gx784": _load_run("Gx784", gx784_root),
    }
    expected_run_ids = {
        "Gx": "task40extra_0p7nm_nonseparable_gx560_manual_m2_v3_v1",
        "F5": "task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1",
        "Gx784": "task40extra_0p7nm_nonseparable_gx784_review_v5_v1",
    }
    for label, run in runs.items():
        if run.manifest.get("run_id") != expected_run_ids[label]:
            raise ValueError(f"{label}: saved run_id differs from the V5 pairing contract")
    signatures = [run.input_signature for run in runs.values()]
    if not (signatures[0] == signatures[1] == signatures[2]):
        raise ValueError("Gx, F5 and Gx784 physical model signatures differ")

    f5_norms, f5_binding = _fixed_f5_norms(
        runs["Gx"], runs["F5"], frozen_volume_path.resolve()
    )
    fields = {}
    sample_witnesses = {}
    for label, run in runs.items():
        fields[label] = restore_p6_total_field(label, run.cfg, run.vector)
        sample_witnesses[label] = total_field_sample_witness(
            fields[label], run.samples, run.sample_metadata
        )

    shared_axes, shared_axis_facts = _exact_axis_union_many(
        (fields["Gx"], fields["F5"], fields["Gx784"])
    )
    axis_identity = {
        "source_fields_order": ["Gx", "F5", "Gx784"],
        "axis_facts": shared_axis_facts,
        "union_coordinate_sha256": {
            axis: hashlib.sha256(shared_axes[index].tobytes()).hexdigest()
            for index, axis in enumerate(("x", "y", "z"))
        },
        "exact_float_union_no_tolerance_merge": True,
    }
    pair_specs = {
        "Gx_to_Gx784": ("Gx", "Gx784"),
        "F5_to_Gx784": ("F5", "Gx784"),
    }
    field_comparisons = {}
    for name, (first_label, second_label) in pair_specs.items():
        comparison = compare_common_subcell_volume(
            fields[first_label],
            fields[second_label],
            axis_reference_fields=(fields["Gx"], fields["F5"], fields["Gx784"]),
            denominator_field=fields["F5"],
            fixed_denominator_norms=f5_norms,
            progress=True,
        )
        for axis_index, axis_name in enumerate(("x", "y", "z")):
            if not (comparison["axis_union"][axis_index]["union_point_count"] == len(shared_axes[axis_index])):
                raise ValueError(f"{name}: common {axis_name} axis union differs")
        field_comparisons[name] = {
            "first": first_label,
            "second": second_label,
            "denominator": "F5 archived same-quantity norm",
            "comparison": comparison,
        }

    from benchmarks.postprocess_task40_p3_mode_staircase import (
        _expected_manual_keys,
        _mode_inventory as load_mode_inventory,
    )

    loaded_mode_maps = {}
    mode_facts = {}
    for label, run in runs.items():
        loaded_mode_maps[label], mode_facts[label] = load_mode_inventory(run, 340)
    ordered = list(loaded_mode_maps["Gx"])
    if any(list(loaded_mode_maps[label]) != ordered for label in ("F5", "Gx784")):
        raise ValueError("the Gx, F5 and Gx784 ordered M=8,N=2 mode keys differ")
    if set(ordered) != _expected_manual_keys(8, 2):
        raise ValueError("the mode inventory differs from the frozen full 340-key set")
    frozen_data = _read_json(frozen_keys_path)
    frozen_order = [tuple(row) for row in frozen_data["frozen_baseline"]["selected_keys"]]
    significant_keys = set(frozen_order)
    if len(frozen_order) != 11 or len(significant_keys) != 11:
        raise ValueError("frozen V4 significant keys are not the original 11 unique keys")
    mode_comparisons = {
        "Gx_to_Gx784": _mode_comparison(
            loaded_mode_maps["Gx"], loaded_mode_maps["Gx784"],
            loaded_mode_maps["F5"], significant_keys,
        ),
        "F5_to_Gx784": _mode_comparison(
            loaded_mode_maps["F5"], loaded_mode_maps["Gx784"],
            loaded_mode_maps["F5"], significant_keys,
        ),
    }
    mode_payloads = {
        label: {
            **mode_facts[label],
            "records": mode_facts[label]["records"],
        }
        for label in runs
    }
    for label, run in runs.items():
        mode_payloads[label]["near_zero_power_ratio_count_threshold_1e-8"] = sum(
            abs(float(row["power_ratio"])) <= 1.0e-8
            for row in mode_payloads[label]["records"]
            if math.isfinite(float(row["power_ratio"]))
        )
        mode_payloads[label]["nonfinite_complex_or_power_fields"] = 0

    official_power = {label: _power_summary(run) for label, run in runs.items()}
    solver_evidence = _residual_evidence(runs["Gx784"].root)
    payload = {
        "schema": "task40extra.review-v5.gx784-paired-comparison.v1",
        "status": "completed",
        "classification": "measured_diagnostics_gate_pending_independent_checker",
        "started_utc": started_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_source": {
            "source_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "working_tree_status": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).splitlines(),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "core_comparator_sha256": _sha256(
                ROOT / "src/postprocessing/task40_saved_field_h_comparison.py"
            ),
            "qualified_environment": environment,
        },
        "runs": {
            label: {
                "run_id": run.manifest["run_id"],
                "run_root": str(run.root),
                "source_sha": run.manifest["source_sha"],
                "input_sha256": run.manifest["input_sha256"],
                "physical_model_sha256": run.manifest["physical_model_sha256"],
                "run_manifest_sha256": _sha256(run.root / "run_manifest.json"),
                "run_summary_sha256": _sha256(run.root / "run_summary.json"),
                "retained_packet_sha256": run.packet_sha256,
                "retained_vector_archive_sha256": run.vector_archive_sha256,
                "retained_vector_sha256": run.vector_sha256,
                "field_restoration_sample_witness": sample_witnesses[label],
                "official_power": official_power[label],
                "run_summary_gate": {
                    "status": run.run_summary.get("status"),
                    "result_classification": run.run_summary.get("result_classification"),
                    "exit_status": run.run_summary.get("exit_status"),
                    "task40_swap_qualification": run.run_summary.get(
                        "task40_swap_qualification"
                    ),
                },
            }
            for label, run in runs.items()
        },
        "fixed_F5_denominator": f5_binding,
        "shared_three_grid_axis_union": axis_identity,
        "field_comparisons": field_comparisons,
        "mode_inventories": mode_payloads,
        "frozen_significant_keys": [list(key) for key in frozen_order],
        "mode_comparisons": mode_comparisons,
        "official_power_by_run": official_power,
        "solver_evidence": solver_evidence,
        "limits": {
            "field_quantity_relative_to_archived_F5_norm": 1.0e-2,
            "significant_mode_relative_to_first_run_amplitude": 1.0e-2,
            "power_absolute_difference": 1.0e-3,
            "energy_closure_and_absorption_difference": 1.0e-5,
            "full_A6_true_residual": 1.0e-6,
        },
        "postprocess_elapsed_monotonic_seconds": time.monotonic() - started,
    }
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite V5 comparison output: {output}")
    _write_json(output, payload)
    return _run_independent_checker(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gx-root", type=Path, default=DEFAULT_GX)
    parser.add_argument("--f5-root", type=Path, default=DEFAULT_F5)
    parser.add_argument("--gx784-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = _analysis(
        args.gx_root,
        args.f5_root,
        args.gx784_root,
        args.output,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
