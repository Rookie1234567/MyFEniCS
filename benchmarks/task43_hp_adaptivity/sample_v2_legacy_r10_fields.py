"""Restore and resample the frozen R10 field for Task43 V2 comparisons.

This is post-solve work only. It reuses the round-one candidate restorer and
field sampler, validates the accepted-parent chain and recorded numerical
source hashes, and creates q8/q10 samples at the actual R10 mesh breakpoints.
It never assembles or solves a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity import compare_initial_to_references as base
from benchmarks.task43_hp_adaptivity import compare_round1_candidate as round1
from benchmarks.task43_hp_adaptivity.compare_v2_endpoints import (
    R13_MODE_KEYS,
    _validated_rows,
    task43_v2_physical_configuration_identity,
)
from src.common.analytic_fields_3d import (
    electric_field_code_values,
    magnetic_field_code_values,
)
from src.postprocessing.physical_field_comparison import (
    build_common_volume_quadrature,
    magnetic_field_from_electric_curl,
    scattered_field_samples,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "benchmarks/artifacts/task43/round10_p_up_attempt1/run"
DEFAULT_SELECTION = (
    ROOT
    / "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json"
)
ACCEPTANCE = (
    ROOT
    / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
)
R10_EXPECTED_ID = "round10_p_up"
R10_EXPECTED_STORAGE_SHA256 = (
    "e1296a9b55ff6d29fde55bf545e44be737c4f5d534b12b69f1ded5f05a0a7eaf"
)
R10_EXPECTED_PLAN_SHA256 = (
    "7e8305e0d6117ceeb37e88eb715d98ab5212505a2410161f0b38aff5c7ed1826"
)
R10_EXPECTED_RECORD_SHA256 = (
    "66d56c0644b5c8eb66d075a7898cdfa28024e3cc30834a08cd3d8b76e453968d"
)
SELECTION_SHA256 = "8307bbe843b0db0f95949f29de106e32ee6dff5f83bdd44bfd7a33c29c7404e9"
ACCEPTANCE_SHA256 = "e589d7c980b4467fc21e13445c4af19202ea662cae9f7277f61e98a3e7702647"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _source_snapshot() -> dict[str, Any]:
    extra = (
        "benchmarks/task43_hp_adaptivity/compare_round1_candidate.py",
        "benchmarks/task43_hp_adaptivity/compare_v2_endpoints.py",
        "benchmarks/task43_hp_adaptivity/sample_v2_legacy_r10_fields.py",
    )
    names = tuple(dict.fromkeys((*base.SOURCE_FILES, *extra)))
    return {
        "git_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "dirty_paths": subprocess.run(
            ["git", "status", "--short"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines(),
        "file_sha256": {name: _sha256_file(ROOT / name) for name in names},
    }


def _validate_accepted_parent_binding(
    candidate: dict[str, Any],
    parent: dict[str, Any],
    selection_path: Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    record = candidate["record"]
    identity = record["candidate_identity"]
    task = plan["task43_candidate"]
    provenance = task["provenance"]
    expected_provenance = {
        "accepted_parent_selection_sha256": parent["selection_sha256"],
        "parent_run_root": str(parent["run_root"]),
        "parent_candidate_id": parent["selected"]["candidate_id"],
        "parent_case_record_sha256": parent["hashes"]["record_sha256"],
        "parent_recovered_storage_sha256": parent["hashes"]["storage_sha256"],
        "parent_plan_sha256": parent["hashes"]["plan_sha256"],
        "parent_comparison_sha256": parent["hashes"]["comparison_record_sha256"],
        "acceptance_contract_sha256": ACCEPTANCE_SHA256,
    }
    if any(
        provenance.get(name) != value for name, value in expected_provenance.items()
    ):
        raise ValueError("R10 candidate plan is not bound to the selected R9 parent")
    if (
        Path(str(provenance.get("accepted_parent_selection_record_path"))).resolve()
        != selection_path.resolve()
    ):
        raise ValueError("R10 candidate plan names another parent-selection record")
    if (
        identity.get("candidate_id") != R10_EXPECTED_ID
        or identity.get("action") != "p_up"
        or identity.get("adaptive_round_id") != "round10"
        or identity.get("accepted_parent_selection_sha256")
        != parent["selection_sha256"]
        or identity.get("parent_candidate_id") != parent["selected"]["candidate_id"]
    ):
        raise ValueError(
            "R10 solve identity differs from its accepted-parent selection"
        )
    expected_identity = {
        "accepted_parent_selection_sha256": parent["selection_sha256"],
        "parent_candidate_id": parent["selected"]["candidate_id"],
        "parent_case_record_sha256": parent["hashes"]["record_sha256"],
        "parent_recovered_storage_sha256": parent["hashes"]["storage_sha256"],
        "parent_plan_sha256": parent["hashes"]["plan_sha256"],
        "parent_comparison_record_sha256": parent["hashes"]["comparison_record_sha256"],
    }
    if any(identity.get(name) != value for name, value in expected_identity.items()):
        raise ValueError("R10 solve record differs from its accepted-parent artifacts")
    if _sha256_file(ACCEPTANCE) != ACCEPTANCE_SHA256:
        raise ValueError("frozen V1 acceptance contract hash changed")
    return {
        "selection_record_sha256": parent["selection_sha256"],
        "selected_parent_candidate_id": parent["selected"]["candidate_id"],
        "parent_hashes": parent["hashes"],
        "provenance_matches": True,
    }


def _legacy_solver_source_compatibility(record: dict[str, Any]) -> dict[str, Any]:
    recorded = record.get("source_identity", {}).get("file_sha256")
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("R10 solve record is missing its numerical source hashes")
    current = {name: _sha256_file(ROOT / name) for name in sorted(recorded)}
    mismatches = [
        {"path": name, "recorded": recorded[name], "current": current[name]}
        for name in sorted(recorded)
        if current[name] != recorded[name]
    ]
    if mismatches:
        raise ValueError(
            f"R10 numerical source hashes differ from this checkout: {mismatches}"
        )
    return {
        "scope": "all 41 solve-recorded source files; Git HEAD may differ because later non-solver evidence code was added",
        "recorded_solve_git_head": record["source_identity"].get("git_head"),
        "matching_source_file_count": len(recorded),
        "mismatches": [],
        "file_sha256": current,
        "all_recorded_numerical_sources_match": True,
    }


def _sample_endpoint(
    candidate: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    cfg = candidate["cfg"]
    record = candidate["record"]
    degree_counts = record["numerical_controls"]["active_space"][
        "active_cell_degree_counts"
    ]
    if degree_counts != {"p4": 0, "p5": 0, "p6": 180}:
        raise ValueError("R10 baseline is not the frozen all-p6 180-cell space")
    if (
        record["numerical_controls"]["active_space"]["independent_active_fe_dofs"]
        != 118800
    ):
        raise ValueError(
            "R10 baseline FE identity differs from the frozen 118800-DoF space"
        )
    if (
        record["numerical_controls"]["volume_quadrature_degree"] != 15
        or record["numerical_controls"]["incident_and_port_quadrature_degree"] != 28
    ):
        raise ValueError("R10 baseline quadrature is not the recorded q15/q28 endpoint")
    if record["numerical_controls"]["ordered_mode_count"] != 612:
        raise ValueError("R10 baseline mode inventory is not R13")
    _validated_rows(
        candidate["mode_payload"], label="R10 baseline R13", expected=R13_MODE_KEYS
    )

    active_degree_sha = record["recovered_solution_storage"][
        "active_degree_plan_sha256"
    ]
    actual_axes = {
        name: candidate["axes"][index] for index, name in enumerate(("x", "y", "z"))
    }
    physical_identity = task43_v2_physical_configuration_identity(
        record["resolved_config"],
        axis_values_nm=actual_axes,
        candidate_plan_sha256=candidate["plan_sha256"],
        active_degree_plan_sha256=active_degree_sha,
    )
    reconstructed_identity = task43_v2_physical_configuration_identity(
        cfg.as_jsonable(),
        axis_values_nm=actual_axes,
        candidate_plan_sha256=candidate["plan_sha256"],
        active_degree_plan_sha256=active_degree_sha,
    )
    if reconstructed_identity["sha256"] != physical_identity["sha256"]:
        raise ValueError(
            "restored R10 physical configuration differs from its solve record"
        )
    arrays: dict[str, np.ndarray] = {}
    rules: dict[str, Any] = {}
    for order in (8, 10):
        rule = build_common_volume_quadrature([candidate["axes"]], gauss_order=order)
        sampled = round1._sample_field(candidate, rule.points_nm)
        background_e = electric_field_code_values(cfg, rule.points_nm)
        background_h = cfg.magnetic_field_scale_A_per_m * magnetic_field_code_values(
            cfg, rule.points_nm
        )
        total_e = np.asarray(sampled["E"], dtype=np.complex128)
        curl_e = np.asarray(sampled["curl_E"], dtype=np.complex128)
        total_h = magnetic_field_from_electric_curl(
            curl_e,
            magnetic_field_scale_A_per_m=cfg.magnetic_field_scale_A_per_m,
            k0_per_nm=cfg.k0,
            mu_r=cfg.mu_r,
        )
        values = {
            "points_nm": np.asarray(rule.points_nm, dtype=np.float64),
            "weights_nm3": np.asarray(rule.weights_nm3, dtype=np.float64),
            "E_total_code": total_e,
            "curl_E_total_code": curl_e,
            "H_total_A_per_m": total_h,
            "incident_background_E_code": np.asarray(background_e, dtype=np.complex128),
            "incident_background_H_A_per_m": np.asarray(
                background_h, dtype=np.complex128
            ),
            "E_scattered_code": scattered_field_samples(total_e, background_e),
            "H_scattered_A_per_m": scattered_field_samples(total_h, background_h),
        }
        prefix = f"q{order}_"
        arrays.update({prefix + name: value for name, value in values.items()})
        rules[f"q{order}"] = {
            "gauss_order_per_axis_per_interval": order,
            "point_count": int(rule.weights_nm3.size),
            "rule_sha256": rule.rule_sha256,
            "rule_volume_nm3": float(np.sum(rule.weights_nm3, dtype=np.float64)),
        }
    return arrays, {
        "physical_configuration_identity": physical_identity,
        "active_degree_plan_sha256": active_degree_sha,
        "candidate_plan_sha256": candidate["plan_sha256"],
        "actual_axes_nm": {
            name: values.tolist()
            for name, values in zip(("x", "y", "z"), candidate["axes"], strict=True)
        },
        "mesh_identity": candidate["mesh_identity"],
        "quadrature_rules": rules,
        "mode_key_sha256": _sha256_json(sorted(R13_MODE_KEYS)),
        "R13_mode_count": len(candidate["mode_payload"]["orders"]),
        "solver_power_record": candidate["power"],
    }


def sample_legacy_r10_fields(
    *, candidate_run_root: Path, selection_record: Path, output_root: Path
) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("legacy R10 restoration requires MPI1")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty output {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    source_start = _source_snapshot()
    if _sha256_file(selection_record) != SELECTION_SHA256:
        raise ValueError("R9 transition9 selection record hash changed")
    record_path = candidate_run_root / "task43_round1_candidate_record.json"
    plan_path = candidate_run_root / "candidate_plan.json"
    storage_path = candidate_run_root / "candidate_recovered_solution_storage.npz"
    mode_path = candidate_run_root / "solve/dtn_port_diffraction_orders_3d.json"
    observed_inputs = {
        "selection_record": {
            "path": str(selection_record.resolve()),
            "sha256": _sha256_file(selection_record),
        },
        "acceptance_contract": {
            "path": str(ACCEPTANCE.resolve()),
            "sha256": _sha256_file(ACCEPTANCE),
        },
        "candidate_record": {
            "path": str(record_path.resolve()),
            "sha256": _sha256_file(record_path),
        },
        "candidate_plan": {
            "path": str(plan_path.resolve()),
            "sha256": _sha256_file(plan_path),
        },
        "recovered_solution_storage": {
            "path": str(storage_path.resolve()),
            "sha256": _sha256_file(storage_path),
        },
        "R13_mode_rows": {
            "path": str(mode_path.resolve()),
            "sha256": _sha256_file(mode_path),
        },
    }
    expected_hashes = {
        "candidate_record": R10_EXPECTED_RECORD_SHA256,
        "candidate_plan": R10_EXPECTED_PLAN_SHA256,
        "recovered_solution_storage": R10_EXPECTED_STORAGE_SHA256,
    }
    for name, expected in expected_hashes.items():
        if observed_inputs[name]["sha256"] != expected:
            raise ValueError(
                f"frozen R10 {name} hash differs from the verified artifact"
            )

    accepted_parent = round1._load_accepted_parent(selection_record)
    candidate = round1._restore_candidate(
        candidate_run_root, output_root / "mesh_restore"
    )
    plan = round1._json(candidate_run_root / "candidate_plan.json")
    parent_binding = _validate_accepted_parent_binding(
        candidate, accepted_parent, selection_record, plan
    )
    source_compatibility = _legacy_solver_source_compatibility(candidate["record"])
    samples, sampling_identity = _sample_endpoint(candidate)
    samples_path = output_root / "r10_q8_q10_field_samples.npz"
    with samples_path.open("xb") as stream:
        np.savez_compressed(stream, **samples)
    sample_sha = _sha256_file(samples_path)
    source_end = _source_snapshot()
    if source_start != source_end:
        raise RuntimeError("source identity changed during legacy field restoration")
    record = {
        "schema": "task43.v2.legacy_r10_field_resampling.v1",
        "classification": "post_solve_restore_and_same_space_field_resampling_only",
        "model_attempts_used": 0,
        "PDE_solve_performed": False,
        "candidate_id": R10_EXPECTED_ID,
        "candidate_run_root": str(candidate_run_root.resolve()),
        "candidate_record_sha256": observed_inputs["candidate_record"]["sha256"],
        "plan_sha256": observed_inputs["candidate_plan"]["sha256"],
        "recovered_storage_sha256": observed_inputs["recovered_solution_storage"][
            "sha256"
        ],
        "mode_rows_sha256": observed_inputs["R13_mode_rows"]["sha256"],
        "input_artifacts": observed_inputs,
        "accepted_parent_binding": parent_binding,
        "solver_source_compatibility": source_compatibility,
        "restored_mesh_and_space_identity": sampling_identity["mesh_identity"],
        "sampling": {
            "artifact": {"path": str(samples_path.resolve()), "sha256": sample_sha},
            "physical_configuration_identity": sampling_identity[
                "physical_configuration_identity"
            ],
            "active_degree_plan_sha256": sampling_identity["active_degree_plan_sha256"],
            "candidate_plan_sha256": sampling_identity["candidate_plan_sha256"],
            "actual_axes_nm": sampling_identity["actual_axes_nm"],
            "quadrature_rules": sampling_identity["quadrature_rules"],
            "mode_key_sha256": sampling_identity["mode_key_sha256"],
            "R13_mode_count": sampling_identity["R13_mode_count"],
        },
        "source_identity": source_start,
        "elapsed_seconds_in_process": time.perf_counter() - started,
        "cost_scope": "postprocessing restore/sample only; no solver setup, assembly, factorization, or PDE solve",
    }
    output_record = output_root / "legacy_r10_field_resampling.json"
    output_record.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--selection-record", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    record = sample_legacy_r10_fields(
        candidate_run_root=args.candidate_run_root,
        selection_record=args.selection_record,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "classification": record["classification"],
                "model_attempts_used": record["model_attempts_used"],
                "output_root": str(args.output_root.resolve()),
                "sample_sha256": record["sampling"]["artifact"]["sha256"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
