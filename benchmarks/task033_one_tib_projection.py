from __future__ import annotations

import hashlib
import math
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
CASE_ROOT = ROOT / "benchmarks" / "cases" / "091_hybrid_hp_adaptivity_feasibility"
DEFAULT_BASELINE_RECORD = (
    ROOT
    / "docs"
    / "task032_hybrid_fem_modal_direct_baseline"
    / "outcomes"
    / "task032_0p7nm_projection.json"
)
EQUAL_ACCURACY_SCHEMA = CASE_ROOT / "equal_accuracy_schema.json"
ONE_TIB_SCHEMA = CASE_ROOT / "one_tib_projection_schema.json"

PREFERRED_MAX_ROWS = 200_000_000.0
CANDIDATE_MAX_ROWS = 350_000_000.0
HIGH_RISK_MAX_ROWS = 500_000_000.0
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
QUALIFIED_ACCURACY_STATUSES = {
    "same_accuracy_mandatory_gate_pass",
    "same_accuracy_strong_gate_pass",
}
ADAPTIVE_RECORD_TYPE = "p2_periodic_graded_mesh_plan"
EQUAL_ACCURACY_RECORD_TYPE = "task033_global_equal_accuracy_efficiency"
ADAPTIVE_ROUTE = "p2_adaptive_only"
EQUAL_ACCURACY_ROUTE = "equal_accuracy_best_candidate"
EQUAL_ACCURACY_GATE_KEYS = {
    "same_clean_source_sha",
    "same_physical_case",
    "rta_absolute_delta",
    "significant_diffraction_complex_amplitude",
    "interface_e_h",
    "selected_plane_fields",
    "qep_beta_when_available",
}


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    canonical = dict(payload)
    canonical.pop("payload_sha256", None)
    rendered = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _load_schema(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Schema {path} must contain one JSON object.")
    Draft202012Validator.check_schema(payload)
    return payload


def _schema_errors(payload: Mapping[str, Any], path: Path) -> list[str]:
    validator = Draft202012Validator(_load_schema(path))
    return [
        error.message
        for error in sorted(
            validator.iter_errors(payload), key=lambda error: list(error.absolute_path)
        )
    ]


def validate_one_tib_projection(payload: Mapping[str, Any]) -> None:
    """Validate one generated projection against the frozen Case091 schema."""

    problems = _schema_errors(payload, ONE_TIB_SCHEMA)
    if problems:
        raise ValueError(f"Invalid Task033 1 TiB projection: {problems[0]}")


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result > 0.0 else None


def _positive_int(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _selection_defaults(route_basis: str) -> dict[str, Any]:
    return {
        "route_basis": route_basis,
        "measured_compression": None,
        "measurement_identity": "measured",
        "source_sha": None,
        "same_accuracy_status": None,
        "compression_source_unit": None,
        "compression_baseline": None,
        "physical_equal_accuracy_qualified": False,
        "evidence_record_type": None,
        "evidence_schema_version": None,
        "evidence_payload_sha256": None,
        "best_candidate_id": None,
        "best_candidate_label": None,
        "reference_local_dofs": None,
        "candidate_local_dofs": None,
        "failures": [],
    }


def _adaptive_selection(evidence: Mapping[str, Any]) -> dict[str, Any]:
    result = _selection_defaults(ADAPTIVE_ROUTE)
    failures: list[str] = result["failures"]
    result["evidence_record_type"] = evidence.get("record_type")
    result["evidence_schema_version"] = evidence.get("schema_version")
    qualification = evidence.get("same_accuracy_qualification")
    qualification = qualification if isinstance(qualification, Mapping) else {}
    plan = evidence.get("plan")
    plan = plan if isinstance(plan, Mapping) else {}
    identity = evidence.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    source = evidence.get("formal_source")
    source = source if isinstance(source, Mapping) else {}

    if evidence.get("schema_version") != 1:
        failures.append("adaptive_evidence_schema_version_invalid")
    if evidence.get("status") != "measured_same_accuracy_qualification_attached":
        failures.append("adaptive_evidence_status_not_measured_qualified")
    if identity.get("is_adaptive_compression_measurement") is not True:
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

    reference_h = plan.get("reference_h_nm")
    expected_baseline = (
        f"uniform_p2_h{float(reference_h):g}"
        if isinstance(reference_h, (int, float))
        and not isinstance(reference_h, bool)
        else None
    )
    if expected_baseline is None or qualification.get("compression_baseline") != expected_baseline:
        failures.append("compression_baseline_mismatch")
    if qualification.get("compression_denominator") != "candidate_local_fe_rows":
        failures.append("compression_denominator_mismatch")
    if plan.get("degree") != 2 or reference_h not in (5.0, 3.0):
        failures.append("adaptive_plan_not_fixed_p2_h5_or_h3")

    compression = _positive_number(qualification.get("compression"))
    if compression is None:
        failures.append("measured_compression_invalid")
    evidence_sha = source.get("commit_sha")
    if not isinstance(evidence_sha, str) or FULL_SHA_RE.fullmatch(evidence_sha) is None:
        failures.append("adaptive_evidence_source_sha_invalid")
        evidence_sha = None
    if source.get("tracked_source_clean") is not True:
        failures.append("adaptive_evidence_source_not_clean")

    result.update(
        {
            "measured_compression": compression,
            "source_sha": evidence_sha,
            "same_accuracy_status": qualification.get("status"),
            "compression_source_unit": qualification.get("compression_unit"),
            "compression_baseline": qualification.get("compression_baseline"),
            "physical_equal_accuracy_qualified": (
                qualification.get("mandatory_gate_pass") is True
            ),
            "reference_local_dofs": _positive_int(
                qualification.get("reference_local_fe_rows")
            ),
            "candidate_local_dofs": _positive_int(
                qualification.get("candidate_local_fe_rows")
            ),
        }
    )
    return result


def _equal_accuracy_selection(evidence: Mapping[str, Any]) -> dict[str, Any]:
    result = _selection_defaults(EQUAL_ACCURACY_ROUTE)
    failures: list[str] = result["failures"]
    result["evidence_record_type"] = evidence.get("record_type")
    result["evidence_schema_version"] = evidence.get("schema_version")

    try:
        schema_problems = _schema_errors(evidence, EQUAL_ACCURACY_SCHEMA)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        schema_problems = [str(exc)]
    if schema_problems:
        failures.append("equal_accuracy_schema_invalid")

    declared_payload_sha = evidence.get("payload_sha256")
    if not isinstance(declared_payload_sha, str) or SHA256_RE.fullmatch(
        declared_payload_sha
    ) is None:
        failures.append("equal_accuracy_payload_sha256_invalid")
        declared_payload_sha = None
    else:
        try:
            observed_payload_sha = _payload_sha256(evidence)
        except (TypeError, ValueError):
            observed_payload_sha = None
        if observed_payload_sha != declared_payload_sha:
            failures.append("equal_accuracy_payload_sha256_mismatch")
    result["evidence_payload_sha256"] = declared_payload_sha

    identity = evidence.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    evidence_sha = identity.get("source_commit_full_sha")
    if not isinstance(evidence_sha, str) or FULL_SHA_RE.fullmatch(evidence_sha) is None:
        failures.append("equal_accuracy_evidence_source_sha_invalid")
        evidence_sha = None
    if identity.get("all_qualified_inputs_same_clean_sha") is not True:
        failures.append("equal_accuracy_inputs_not_same_clean_sha")
    if identity.get("consumes_measured_pde_records") is not True:
        failures.append("equal_accuracy_not_bound_to_measured_pde_records")
    if identity.get("proves_0p7nm_feasible") is not False:
        failures.append("equal_accuracy_exaggerates_0p7nm_claim")
    if evidence.get("status") != "qualified":
        failures.append("equal_accuracy_status_not_qualified")

    reference = evidence.get("reference")
    reference = reference if isinstance(reference, Mapping) else {}
    reference_costs = reference.get("costs")
    reference_costs = reference_costs if isinstance(reference_costs, Mapping) else {}
    reference_local_dofs = _positive_int(reference_costs.get("local_dofs"))
    if reference_local_dofs is None:
        failures.append("equal_accuracy_reference_local_dofs_invalid")
    if reference.get("source_commit_full_sha") != evidence_sha:
        failures.append("equal_accuracy_reference_source_sha_mismatch")

    inputs = evidence.get("inputs")
    inputs = inputs if isinstance(inputs, Mapping) else {}
    input_reference = inputs.get("reference")
    input_reference = input_reference if isinstance(input_reference, Mapping) else {}
    if input_reference.get("source_commit_full_sha") != evidence_sha:
        failures.append("equal_accuracy_reference_input_source_sha_mismatch")
    if reference.get("selected_mode_count_per_direction") != input_reference.get(
        "selected_mode_count_per_direction"
    ):
        failures.append("equal_accuracy_reference_selected_mode_count_mismatch")
    for key in ("funnel_sha256", "selected_watchdog_sha256"):
        value = input_reference.get(key)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            failures.append("equal_accuracy_reference_input_hash_invalid")
            break
    input_candidates = inputs.get("candidates")
    input_candidates = input_candidates if isinstance(input_candidates, list) else []

    candidate_descriptors: dict[str, Mapping[str, Any]] = {}
    for descriptor in input_candidates:
        if not isinstance(descriptor, Mapping):
            failures.append("equal_accuracy_candidate_input_descriptor_invalid")
            continue
        candidate_id = descriptor.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in candidate_descriptors:
            failures.append("equal_accuracy_candidate_input_descriptor_invalid")
            continue
        candidate_descriptors[candidate_id] = descriptor

    candidates = evidence.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    if len(candidate_descriptors) != len(candidates):
        failures.append("equal_accuracy_candidate_input_descriptor_count_mismatch")
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        row_input = row.get("input")
        row_input = row_input if isinstance(row_input, Mapping) else {}
        descriptor = candidate_descriptors.get(str(row.get("candidate_id")))
        if descriptor is None:
            failures.append("equal_accuracy_candidate_input_descriptor_missing")
            continue
        expected_input = dict(descriptor)
        expected_input.pop("candidate_id", None)
        if dict(row_input) != expected_input:
            failures.append("equal_accuracy_candidate_input_descriptor_mismatch")
        if row.get("selected_mode_count_per_direction") != row_input.get(
            "selected_mode_count_per_direction"
        ):
            failures.append("equal_accuracy_candidate_selected_mode_count_mismatch")

    qualified_rows = [
        row
        for row in candidates
        if isinstance(row, Mapping) and row.get("status") == "equal_accuracy_qualified"
    ]
    selection = evidence.get("selection")
    selection = selection if isinstance(selection, Mapping) else {}
    if selection.get("qualified_candidate_count") != len(qualified_rows):
        failures.append("equal_accuracy_qualified_candidate_count_mismatch")
    best_candidate_id = selection.get("best_candidate_id")
    matches = [row for row in qualified_rows if row.get("candidate_id") == best_candidate_id]
    if len(matches) != 1:
        failures.append("equal_accuracy_best_candidate_not_uniquely_qualified")
        best = {}
    else:
        best = matches[0]
    frontier = selection.get("pareto_frontier_candidate_ids")
    if not isinstance(frontier, list) or best_candidate_id not in frontier:
        failures.append("equal_accuracy_best_candidate_not_on_pareto_frontier")

    for row in qualified_rows:
        row_input = row.get("input")
        row_input = row_input if isinstance(row_input, Mapping) else {}
        if (
            row.get("source_commit_full_sha") != evidence_sha
            or row_input.get("source_commit_full_sha") != evidence_sha
        ):
            failures.append("equal_accuracy_qualified_candidate_source_sha_mismatch")
            break
        for key in ("funnel_sha256", "selected_watchdog_sha256"):
            value = row_input.get(key)
            if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                failures.append("equal_accuracy_qualified_candidate_input_hash_invalid")
                break
        matching_inputs = [
            descriptor
            for descriptor in input_candidates
            if isinstance(descriptor, Mapping)
            and descriptor.get("candidate_id") == row.get("candidate_id")
        ]
        if (
            len(matching_inputs) != 1
            or matching_inputs[0].get("source_commit_full_sha") != evidence_sha
        ):
            failures.append("equal_accuracy_qualified_input_binding_mismatch")
            break

    cost_keys = (
        "local_dofs",
        "total_rows",
        "assembled_nnz",
        "authoritative_rss_bytes",
        "total_time_seconds",
    )
    qualified_cost_rows: list[
        tuple[tuple[float | str, ...], Mapping[str, Any]]
    ] = []
    for row in qualified_rows:
        costs = row.get("costs")
        costs = costs if isinstance(costs, Mapping) else {}
        numeric_costs = tuple(_positive_number(costs.get(key)) for key in cost_keys)
        if any(value is None for value in numeric_costs):
            failures.append("equal_accuracy_qualified_candidate_costs_invalid")
            break
        qualified_cost_rows.append(
            (
                tuple(float(value) for value in numeric_costs if value is not None)
                + (str(row.get("candidate_id")),),
                row,
            )
        )
    if qualified_cost_rows:
        recomputed_best = min(qualified_cost_rows, key=lambda item: item[0])[1]
        if recomputed_best.get("candidate_id") != best_candidate_id:
            failures.append("equal_accuracy_best_candidate_selection_mismatch")

    best_gates = best.get("gates") if isinstance(best, Mapping) else None
    if (
        not isinstance(best_gates, Mapping)
        or set(best_gates) != EQUAL_ACCURACY_GATE_KEYS
        or any(value is not True for value in best_gates.values())
    ):
        failures.append("equal_accuracy_best_candidate_gates_not_all_true")
    if best.get("failures") != []:
        failures.append("equal_accuracy_best_candidate_contains_failures")
    if best.get("label") != selection.get("best_candidate_label"):
        failures.append("equal_accuracy_best_candidate_label_mismatch")

    best_costs = best.get("costs") if isinstance(best, Mapping) else None
    best_costs = best_costs if isinstance(best_costs, Mapping) else {}
    candidate_local_dofs = _positive_int(best_costs.get("local_dofs"))
    if candidate_local_dofs is None:
        failures.append("equal_accuracy_candidate_local_dofs_invalid")
    compression = (
        None
        if reference_local_dofs is None or candidate_local_dofs is None
        else float(reference_local_dofs) / float(candidate_local_dofs)
    )
    compression_ratios = best.get("compression_ratios") if isinstance(best, Mapping) else None
    compression_ratios = (
        compression_ratios if isinstance(compression_ratios, Mapping) else {}
    )
    reported_compression = _positive_number(compression_ratios.get("local_dofs"))
    if compression is None or reported_compression is None or not math.isclose(
        compression, reported_compression, rel_tol=1.0e-12, abs_tol=1.0e-15
    ):
        failures.append("equal_accuracy_local_dof_compression_mismatch")

    result.update(
        {
            "measured_compression": compression,
            "source_sha": evidence_sha,
            "same_accuracy_status": "equal_accuracy_qualified",
            "compression_source_unit": "dimensionless_local_fe_row_ratio",
            "compression_baseline": "measured_equal_accuracy_reference_local_dofs",
            "physical_equal_accuracy_qualified": len(matches) == 1,
            "best_candidate_id": best_candidate_id,
            "best_candidate_label": selection.get("best_candidate_label"),
            "reference_local_dofs": reference_local_dofs,
            "candidate_local_dofs": candidate_local_dofs,
        }
    )
    return result


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
    """Classify a 1 TiB row scenario from one strictly identified Task033 route.

    ``compression_evidence`` is auto-detected as either the existing fixed-p2
    adaptive formal record or the global equal-accuracy record.  The latter is
    accepted only after schema, self-payload hash, best-candidate, measured
    local-DoF ratio, and same-clean-SHA checks.  This remains a planning
    transfer, never a 0.7 nm PDE or feasibility proof.
    """

    baseline = _load_task032_baseline(baseline_record)
    baseline_rows = float(baseline["uniform_grid_estimates"]["local_fe_rows"])
    if measured_compression is not None:
        measured_compression = float(measured_compression)
        if not math.isfinite(measured_compression) or measured_compression <= 0.0:
            raise ValueError("measured_compression must be positive and finite.")

    if compression_evidence is None:
        selection = _selection_defaults(ADAPTIVE_ROUTE)
        selection["measurement_identity"] = measurement_identity
        selection["measured_compression"] = measured_compression
        selection["failures"].append("measured_same_accuracy_evidence_missing")
    else:
        evidence_type = compression_evidence.get("record_type")
        if evidence_type == ADAPTIVE_RECORD_TYPE:
            selection = _adaptive_selection(compression_evidence)
        elif evidence_type == EQUAL_ACCURACY_RECORD_TYPE:
            selection = _equal_accuracy_selection(compression_evidence)
        else:
            selection = _selection_defaults(ADAPTIVE_ROUTE)
            selection["evidence_record_type"] = evidence_type
            selection["evidence_schema_version"] = compression_evidence.get(
                "schema_version"
            )
            selection["failures"].append(
                "unsupported_compression_evidence_record_type"
            )

    failures: list[str] = selection["failures"]
    current_source = formal_source if isinstance(formal_source, Mapping) else {}
    current_sha = current_source.get("commit_sha")
    evidence_sha = selection["source_sha"]
    if formal_source is None:
        failures.append("formal_source_missing")
    if not isinstance(current_sha, str) or FULL_SHA_RE.fullmatch(current_sha) is None:
        failures.append("current_formal_source_sha_invalid")
    if current_source.get("tracked_source_clean") is not True:
        failures.append("current_formal_source_not_clean")
    for field in (
        "source_stable_during_run",
        "nonignored_untracked_clean",
        "complete_worktree_clean",
    ):
        if current_source.get(field) is not True:
            failures.append("current_formal_source_not_complete_clean_stable")
            break
    if isinstance(current_sha, str) and (
        current_source.get("head_before_sha") != current_sha
        or current_source.get("head_after_sha") != current_sha
    ):
        failures.append("current_formal_source_head_binding_invalid")
    if evidence_sha != current_sha:
        prefix = (
            "equal_accuracy"
            if selection["route_basis"] == EQUAL_ACCURACY_ROUTE
            else "adaptive"
        )
        failures.append(f"{prefix}_evidence_source_sha_mismatch")
    if selection["measured_compression"] is None:
        failures.append("measured_compression_missing")
    if not evidence_record or not evidence_record.strip():
        failures.append("measurement_evidence_record_missing")

    failures = list(dict.fromkeys(failures))
    measured_compression = selection["measured_compression"]
    measurement_identity = selection["measurement_identity"]

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
        "route_basis": selection["route_basis"],
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
            "evidence_record_type": selection["evidence_record_type"],
            "evidence_schema_version": selection["evidence_schema_version"],
            "evidence_payload_sha256": selection["evidence_payload_sha256"],
            "source_commit_sha": evidence_sha,
            "same_accuracy_status": selection["same_accuracy_status"],
            "compression_source_unit": selection["compression_source_unit"],
            "compression_baseline": selection["compression_baseline"],
            "physical_equal_accuracy_qualified": selection[
                "physical_equal_accuracy_qualified"
            ],
            "best_candidate_id": selection["best_candidate_id"],
            "best_candidate_label": selection["best_candidate_label"],
            "reference_local_dofs": selection["reference_local_dofs"],
            "candidate_local_dofs": selection["candidate_local_dofs"],
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
            "route_basis identifies either the reviewed equal-accuracy best "
            "candidate or the compatible fixed-p2 adaptive-only route; it does "
            "not promote either route to a 0.7 nm feasibility proof.",
        ],
    }
    if formal_source is not None:
        record["formal_source"] = dict(formal_source)
    return record
