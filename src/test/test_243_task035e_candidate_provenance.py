from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from benchmarks.task035e_candidate_output import (
    CandidateOutputError,
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from src.test.test_232_task035e_candidate_output import (
    _sha,
    _write_candidate_run,
    _write_json,
)


FOREST_SHA = "1" * 64
CONNECTIVITY_SHA = "2" * 64
BOX_SHA = "3" * 64
DEGREE_SHA = "4" * 64
ENTITY_DEGREE_SHA = "5" * 64
CONFIG_IDENTITY_SHA = "6" * 64
RAW_ACTIVE_DOFS = 84_152
ACTIVE_DOFS = 78_384
MATRIX_ROWS = 23_018
MATRIX_NNZ = 15_291_778
FACTOR_NNZ = 94_398_336
SOLVER_PEAK_BYTES = 5 * 1024**3
RESOURCE_CAP_BYTES = 10 * 1024**3


def _passed_gate(schema_version: str) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "pass": True,
        "checks": {"fixture_authority": True},
        "failures": [],
    }


def _add_provenance(
    record_input: CandidateWatchdogInput,
) -> CandidateWatchdogInput:
    record_path = record_input.path
    run_dir = record_path.parent
    summary_path = run_dir / "run_summary.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    plan = {
        "expected_forest": {"leaf_catalog_sha256": FOREST_SHA},
        "cell_interior_degree_plan_sha256": DEGREE_SHA,
    }
    plan_path = run_dir / "blind-plan.json"
    _write_json(plan_path, plan)
    plan_sha = _sha(plan_path)
    matrix = {
        "matrix_rows": MATRIX_ROWS,
        "matrix_cols": MATRIX_ROWS,
        "matrix_nnz_used": float(MATRIX_NNZ),
    }
    summary.update(
        {
            "num_raw_broken_active_fe_dofs": RAW_ACTIVE_DOFS,
            "num_actual_conforming_active_fe_dofs": ACTIVE_DOFS,
            "matrix_stats": matrix,
            "stage4_dtn_factor_inventory": {
                "available": True,
                "factor_solver_type": "mumps",
                "matrix_stats": {
                    "matrix_rows": MATRIX_ROWS,
                    "matrix_nnz_used": float(FACTOR_NNZ),
                },
            },
            "stage4_local_h_constraint_audit": {
                "schema_version": (
                    "task035e.stage4-multilevel-local-hp-"
                    "reduction-authority.v1"
                ),
                "status": "stage4_local_h_reduction_authority_pass",
                "pass": True,
                "mesh": {
                    "schema_version": (
                        "task035e.stage4-multilevel-local-h-mesh.v1"
                    ),
                    "status": (
                        "stage4_balanced_multilevel_local_h_mesh_pass"
                    ),
                    "pass": True,
                    "plan_path": str(plan_path),
                    "plan_file_sha256": plan_sha,
                    "base_config_identity_sha256": CONFIG_IDENTITY_SHA,
                    "cell_interior_degree_plan_sha256": DEGREE_SHA,
                    "forest": {
                        "schema_version": (
                            "task035d.dyadic-hexa-forest.v1"
                        ),
                        "pass": True,
                        "leaf_catalog_sha256": FOREST_SHA,
                    },
                    "carrier": {
                        "schema_version": (
                            "task035d.broken-dyadic-hexa-carrier.v1"
                        ),
                        "pass": True,
                        "leaf_catalog_sha256": FOREST_SHA,
                        "canonical_connectivity_sha256": (
                            CONNECTIVITY_SHA
                        ),
                    },
                },
                "degree_plan": {
                    "schema_version": (
                        "task035e.local-h-variable-exact-sequence-plan.v1"
                    ),
                    "status": (
                        "local_h_variable_exact_sequence_plan_closed"
                    ),
                    "pass": True,
                    "mesh_cell_box_catalog_sha256": BOX_SHA,
                    "cell_degree_plan_sha256": DEGREE_SHA,
                    "geometry_canonical_entity_degree_sha256": (
                        ENTITY_DEGREE_SHA
                    ),
                    "active_rows": RAW_ACTIVE_DOFS,
                },
            },
        }
    )
    _write_json(summary_path, summary)

    resource_policy = {
        "schema_version": (
            "task035e.blind-candidate-resource-policy.v1"
        ),
        "pass": True,
        "effective_job_cap_bytes": RESOURCE_CAP_BYTES,
    }
    plan_gate = _passed_gate(
        "task035e.blind-multilevel-plan-authority-gate.v1"
    )
    plan_gate.update(
        {
            "path": str(plan_path),
            "expected_file_sha256": plan_sha,
            "observed_file_sha256": plan_sha,
            "base_config_identity_sha256": CONFIG_IDENTITY_SHA,
        }
    )
    live_resource = {
        "schema_version": (
            "task035e.blind-candidate-live-resource-gate.v1"
        ),
        "pass": True,
        "controlled_resource_stop": False,
        "stop_reason": None,
        "zero_swap_every_sample": True,
        "maximum_swap_authority_bytes": 0,
        "memory_cap_at_most_11_gib": True,
        "maximum_job_memory_authority_bytes": SOLVER_PEAK_BYTES,
        "effective_job_cap_respected": True,
        "minimum_headroom_20_percent_preserved": True,
        "policy": resource_policy,
    }
    record.update(
        {
            "task035e_blind_candidate_launch_gate": {
                "schema_version": (
                    "task035e.blind-candidate-launch-gate.v1"
                ),
                "selected": True,
                "plan": plan_gate,
                "solver": _passed_gate(
                    "task035e.blind-candidate-solver-gate.v1"
                ),
                "artifacts": _passed_gate(
                    "task035e.blind-candidate-artifact-gate.v1"
                ),
                "resource_policy": resource_policy,
                "live_resource_gate": live_resource,
            },
            "calibration": {
                "exact_rows": MATRIX_ROWS,
                "exact_assembled_nnz": float(MATRIX_NNZ),
                "factorization_or_solve_stage_seen": True,
            },
            "matrix_inventory": {"final": matrix},
            "solver_summary": summary,
            "solver_summary_sha256": _sha(summary_path),
        }
    )
    _write_json(record_path, record)
    return CandidateWatchdogInput(record_path, _sha(record_path))


def _rewrite_summary_and_record(
    record_input: CandidateWatchdogInput,
    mutator: Callable[[dict[str, Any], dict[str, Any]], None],
) -> CandidateWatchdogInput:
    record_path = record_input.path
    summary_path = record_path.parent / "run_summary.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    mutator(record, summary)
    _write_json(summary_path, summary)
    record["solver_summary"] = summary
    record["solver_summary_sha256"] = _sha(summary_path)
    _write_json(record_path, record)
    return CandidateWatchdogInput(record_path, _sha(record_path))


def test_candidate_exposes_only_bound_plan_geometry_and_resource_evidence(
    tmp_path: Path,
) -> None:
    record = _add_provenance(_write_candidate_run(tmp_path))
    adapted = adapt_candidate_output(record)

    assert adapted.plan_path == record.path.parent / "blind-plan.json"
    assert adapted.plan_file_sha256 == _sha(adapted.plan_path)
    assert adapted.artifact_sha256["blind_plan"] == adapted.plan_file_sha256
    assert adapted.forest_leaf_catalog_sha256 == FOREST_SHA
    assert adapted.carrier_connectivity_sha256 == CONNECTIVITY_SHA
    assert adapted.mesh_cell_box_catalog_sha256 == BOX_SHA
    assert adapted.cell_degree_plan_sha256 == DEGREE_SHA
    assert (
        adapted.geometry_canonical_entity_degree_sha256
        == ENTITY_DEGREE_SHA
    )
    assert adapted.structural_inventory == {
        "raw_active_fe_dofs": RAW_ACTIVE_DOFS,
        "active_fe_dofs": ACTIVE_DOFS,
        "matrix_rows": MATRIX_ROWS,
        "matrix_nnz": MATRIX_NNZ,
        "factor_nnz": FACTOR_NNZ,
        "solver_peak_bytes": SOLVER_PEAK_BYTES,
    }


def test_candidate_rejects_missing_launch_authority_and_plan_tamper(
    tmp_path: Path,
) -> None:
    missing = _add_provenance(
        _write_candidate_run(tmp_path / "missing")
    )
    record = json.loads(missing.path.read_text(encoding="utf-8"))
    record.pop("task035e_blind_candidate_launch_gate")
    _write_json(missing.path, record)
    with pytest.raises(CandidateOutputError, match="launch_gate"):
        adapt_candidate_output(
            CandidateWatchdogInput(missing.path, _sha(missing.path))
        )

    tampered = _add_provenance(
        _write_candidate_run(tmp_path / "tampered")
    )
    plan_path = tampered.path.parent / "blind-plan.json"
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(CandidateOutputError, match="SHA-256 mismatch"):
        adapt_candidate_output(tampered)


def test_candidate_rejects_identity_and_measured_inventory_substitution(
    tmp_path: Path,
) -> None:
    identity = _add_provenance(
        _write_candidate_run(tmp_path / "identity")
    )

    def drift_forest(
        _record: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        summary["stage4_local_h_constraint_audit"]["mesh"]["forest"][
            "leaf_catalog_sha256"
        ] = "7" * 64

    identity = _rewrite_summary_and_record(identity, drift_forest)
    with pytest.raises(CandidateOutputError, match="identities differ"):
        adapt_candidate_output(identity)

    structural = _add_provenance(
        _write_candidate_run(tmp_path / "structural")
    )
    record = json.loads(structural.path.read_text(encoding="utf-8"))
    record["calibration"]["exact_rows"] = MATRIX_ROWS + 1
    _write_json(structural.path, record)
    with pytest.raises(CandidateOutputError, match="inventories differ"):
        adapt_candidate_output(
            CandidateWatchdogInput(structural.path, _sha(structural.path))
        )

    resource = _add_provenance(
        _write_candidate_run(tmp_path / "resource")
    )
    record = json.loads(resource.path.read_text(encoding="utf-8"))
    record["task035e_blind_candidate_launch_gate"][
        "live_resource_gate"
    ]["maximum_job_memory_authority_bytes"] = RESOURCE_CAP_BYTES
    _write_json(resource.path, record)
    with pytest.raises(CandidateOutputError, match="resource envelope"):
        adapt_candidate_output(
            CandidateWatchdogInput(resource.path, _sha(resource.path))
        )
