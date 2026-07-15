from __future__ import annotations

import math
import json
from pathlib import Path
import re
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE_RECORD = (
    ROOT
    / "docs"
    / "task032_hybrid_fem_modal_direct_baseline"
    / "outcomes"
    / "task032_0p7nm_projection.json"
)

PREFERRED_MAX_ROWS = 200_000_000.0
CANDIDATE_MAX_ROWS = 350_000_000.0
HIGH_RISK_MAX_ROWS = 500_000_000.0
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
QUALIFIED_ACCURACY_STATUSES = {
    "same_accuracy_mandatory_gate_pass",
    "same_accuracy_strong_gate_pass",
}


def classify_local_fe_rows(projected_rows: float) -> str:
    """Classify disjoint Task033 1 TiB row zones at exact boundaries."""

    rows = float(projected_rows)
    if not math.isfinite(rows) or rows <= 0.0:
        raise ValueError("projected_rows must be positive and finite.")
    if rows <= PREFERRED_MAX_ROWS:
        return "preferred"
    if rows <= CANDIDATE_MAX_ROWS:
        return "candidate"
    if rows <= HIGH_RISK_MAX_ROWS:
        return "high-risk"
    return "infeasible"


def _stable_row_ratio(numerator: float, denominator: float) -> float:
    value = numerator / denominator
    nearest_integer = round(value)
    if math.isclose(value, nearest_integer, rel_tol=1.0e-12, abs_tol=1.0e-6):
        return float(nearest_integer)
    return value


def _load_task032_baseline(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "analytical_resource_projection":
        raise ValueError("Task032 baseline must be an analytical resource projection.")
    rows = payload.get("uniform_grid_estimates", {}).get("local_fe_rows")
    if rows != 923_346_000:
        raise ValueError("Unexpected Task032 0.7 nm local-FE-row baseline.")
    if payload.get("identity", {}).get("is_solver_pass") is not False:
        raise ValueError("Task032 projection identity must not be a solver pass.")
    return payload


def build_one_tib_projection(
    *,
    measured_compression: float | None = None,
    measurement_identity: str | None = None,
    evidence_record: str | None = None,
    compression_evidence: Mapping[str, Any] | None = None,
    formal_source: Mapping[str, Any] | None = None,
    baseline_record: Path = DEFAULT_BASELINE_RECORD,
) -> dict[str, Any]:
    """Update the Task032 row scenario only from a sourced measurement.

    The calculation transfers a same-error 13.5 nm compression ratio to the
    Task032 mechanical uniform-grid 0.7 nm row baseline. It is a planning
    scenario, not a PDE run, memory model, wavelength-transfer validation, or
    proof that a 0.7 nm solve fits in 1 TiB.
    """

    baseline = _load_task032_baseline(baseline_record)
    baseline_rows = float(baseline["uniform_grid_estimates"]["local_fe_rows"])

    failures: list[str] = []
    evidence = compression_evidence or {}
    qualification = evidence.get("same_accuracy_qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    plan = evidence.get("plan")
    plan = plan if isinstance(plan, Mapping) else {}
    evidence_identity = evidence.get("identity")
    evidence_identity = (
        evidence_identity if isinstance(evidence_identity, Mapping) else {}
    )
    evidence_source = evidence.get("formal_source")
    evidence_source = evidence_source if isinstance(evidence_source, Mapping) else {}
    current_source = formal_source if isinstance(formal_source, Mapping) else {}

    if compression_evidence is None:
        failures.append("measured_same_accuracy_evidence_missing")
    evidence_compression = qualification.get("compression")
    if compression_evidence is not None:
        try:
            measured_compression = float(evidence_compression)
        except (TypeError, ValueError):
            measured_compression = None
            failures.append("measured_compression_invalid")
        else:
            if not math.isfinite(measured_compression) or measured_compression <= 0.0:
                measured_compression = None
                failures.append("measured_compression_invalid")
        measurement_identity = "measured"
    elif measured_compression is not None:
        measured_compression = float(measured_compression)
        if not math.isfinite(measured_compression) or measured_compression <= 0.0:
            raise ValueError("measured_compression must be positive and finite.")

    reference_h = plan.get("reference_h_nm")
    expected_baseline = (
        f"uniform_p2_h{float(reference_h):g}"
        if isinstance(reference_h, (int, float)) and not isinstance(reference_h, bool)
        else None
    )
    if evidence.get("status") != "measured_same_accuracy_qualification_attached":
        failures.append("adaptive_evidence_status_not_measured_qualified")
    if evidence_identity.get("is_adaptive_compression_measurement") is not True:
        failures.append("adaptive_identity_not_compression_measurement")
    if qualification.get("status") not in QUALIFIED_ACCURACY_STATUSES:
        failures.append("same_accuracy_status_not_qualified")
    if qualification.get("mandatory_gate_pass") is not True:
        failures.append("physical_equal_accuracy_gate_not_passed")
    if (
        qualification.get("data_identity")
        != "derived_from_clean_measured_reference_and_candidate"
    ):
        failures.append("compression_not_derived_from_clean_measurements")
    if qualification.get("compression_unit") != "dimensionless_local_fe_row_ratio":
        failures.append("compression_unit_not_local_fe_row_ratio")
    if expected_baseline is None or qualification.get(
        "compression_baseline"
    ) != expected_baseline:
        failures.append("compression_baseline_mismatch")
    if qualification.get("compression_denominator") != "candidate_local_fe_rows":
        failures.append("compression_denominator_mismatch")
    if plan.get("degree") != 2 or reference_h not in (5.0, 3.0):
        failures.append("adaptive_plan_not_fixed_p2_h5_or_h3")

    evidence_sha = evidence_source.get("commit_sha")
    current_sha = current_source.get("commit_sha")
    if formal_source is None:
        failures.append("formal_source_missing")
    if not isinstance(evidence_sha, str) or FULL_SHA_RE.fullmatch(evidence_sha) is None:
        failures.append("adaptive_evidence_source_sha_invalid")
    if not isinstance(current_sha, str) or FULL_SHA_RE.fullmatch(current_sha) is None:
        failures.append("current_formal_source_sha_invalid")
    if evidence_source.get("tracked_source_clean") is not True:
        failures.append("adaptive_evidence_source_not_clean")
    if current_source.get("tracked_source_clean") is not True:
        failures.append("current_formal_source_not_clean")
    if evidence_sha != current_sha:
        failures.append("adaptive_evidence_source_sha_mismatch")
    if measured_compression is None:
        failures.append("measured_compression_missing")
    if not evidence_record or not evidence_record.strip():
        failures.append("measurement_evidence_record_missing")

    failures = list(dict.fromkeys(failures))

    qualified_input = not failures
    projected_rows = (
        _stable_row_ratio(baseline_rows, measured_compression)
        if qualified_input and measured_compression is not None
        else None
    )
    classification = (
        classify_local_fe_rows(projected_rows)
        if projected_rows is not None
        else None
    )

    thresholds = {
        "preferred": {"maximum_local_fe_rows": int(PREFERRED_MAX_ROWS)},
        "candidate": {
            "minimum_exclusive_local_fe_rows": int(PREFERRED_MAX_ROWS),
            "maximum_local_fe_rows": int(CANDIDATE_MAX_ROWS),
        },
        "high-risk": {
            "minimum_exclusive_local_fe_rows": int(CANDIDATE_MAX_ROWS),
            "maximum_local_fe_rows": int(HIGH_RISK_MAX_ROWS),
        },
        "infeasible": {
            "minimum_exclusive_local_fe_rows": int(HIGH_RISK_MAX_ROWS)
        },
    }

    record = {
        "schema_version": "task033.case091.one-tib-projection.v1",
        "record_type": "task033_one_tib_local_fe_row_projection",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "classified" if qualified_input else "not_qualified",
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_memory_measurement": False,
            "is_0p7nm_wavelength_transfer_validation": False,
            "is_0p7nm_feasibility_proof": False,
            "ordinary_default_changed": False,
            "is_formal_record": formal_source is not None,
        },
        "baseline": {
            "value": int(baseline_rows),
            "unit": "local_fe_rows",
            "data_identity": "predicted_mechanical_uniform_grid_scaling",
            "wavelength_nm": baseline["inputs"]["wavelength_nm"],
            "mesh_target_nm": baseline["inputs"]["mesh_target_nm"],
            "source_record": baseline_record.relative_to(ROOT).as_posix(),
            "source_record_type": baseline["record_type"],
            "source_is_pde_run": baseline["identity"]["is_pde_run"],
            "source_is_solver_pass": baseline["identity"]["is_solver_pass"],
        },
        "input": {
            "same_error_local_dof_compression": measured_compression,
            "unit": "dimensionless_ratio",
            "data_identity": measurement_identity,
            "evidence_record": evidence_record,
            "source_commit_sha": evidence_sha,
            "same_accuracy_status": qualification.get("status"),
            "compression_source_unit": qualification.get("compression_unit"),
            "compression_baseline": qualification.get("compression_baseline"),
            "physical_equal_accuracy_qualified": (
                qualification.get("mandatory_gate_pass") is True
            ),
            "qualified": qualified_input,
            "qualification_failures": failures,
        },
        "equation": {
            "text": (
                "projected_local_fe_rows = "
                "task032_uniform_0p7nm_local_fe_rows / "
                "measured_same_error_local_dof_compression"
            ),
            "numerator": "task032_uniform_0p7nm_local_fe_rows",
            "denominator": "measured_same_error_local_dof_compression",
            "output_unit": "local_fe_rows",
        },
        "one_tib_row_zones": thresholds,
        "result": {
            "projected_local_fe_rows": projected_rows,
            "unit": "local_fe_rows",
            "classification": classification,
            "data_identity": (
                "derived_scenario_from_prediction_and_measurement"
                if qualified_input
                else "not_qualified"
            ),
        },
        "compression_boundaries_for_task032_baseline": {
            "preferred_at_or_above": baseline_rows / PREFERRED_MAX_ROWS,
            "candidate_at_or_above": baseline_rows / CANDIDATE_MAX_ROWS,
            "high_risk_at_or_above": baseline_rows / HIGH_RISK_MAX_ROWS,
            "unit": "dimensionless_ratio",
        },
        "limitations": [
            "The numerator is a Task032 mechanical uniform-grid prediction, not "
            "a 0.7 nm PDE measurement.",
            "A 13.5 nm measured compression ratio is not proven to transfer to "
            "0.7 nm material, modal, accuracy, or mesh requirements.",
            "The row zone omits modal-core, matrix-free solver, mesh, vectors, "
            "runtime, and safety-margin memory qualification.",
            "Even a preferred row classification does not prove that 0.7 nm is "
            "solvable or that the whole solver fits in 1 TiB.",
        ],
    }
    if formal_source is not None:
        record["formal_source"] = dict(formal_source)
    return record
