from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from benchmarks.task033_qep_qualification import (
    qep_full_aggregate_gate,
    qep_p3_only_partial_aggregate_gate,
    qep_source_record_file_gate,
)
from benchmarks.task033_hybrid_funnel import (
    _controlled_physical_truncation_negative,
    is_exact_p1_h5_modal_basis_capacity,
    is_exact_p1_terminal_reference_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "final_outcome_schema.json"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HP_CLASSIFICATIONS = {
    "weak": "hp_compression_weak",
    "positive": "hp_compression_positive",
    "clear": "hp_compression_clear",
    "engineering": "hp_compression_engineering",
    "strong": "hp_compression_strong",
}
INPUT_ROLES = (
    "case090_core",
    "qep_mpi1_aggregate",
    "qep_mpi2_timeout_negative",
    "qep_mpi4_timeout_negative",
    "augmented_vs_minimal_p1",
    "augmented_vs_minimal_p3",
    "uniform_p_h_matrix",
    "equal_accuracy",
    "adaptive_p2_h5",
    "adaptive_p2_h3",
    "interface_buffer_tradeoff",
    "variable_p_capability_audit",
    "one_tib_projection",
)


class FinalOutcomeError(ValueError):
    """Raised when final evidence is malformed, contradictory, or unbound."""


@dataclass(frozen=True)
class Evidence:
    role: str
    path: Path
    descriptor_path: str
    payload: Mapping[str, Any]
    sha256: str
    source_sha: str

    def descriptor(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.descriptor_path,
            "sha256": self.sha256,
            "schema_version": self.payload.get("schema_version"),
            "record_type": self.payload.get("record_type")
            or self.payload.get("benchmark_id"),
            "source_commit_sha": self.source_sha,
            "source_clean": True,
        }


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FinalOutcomeError(f"{label} must be one JSON object")
    return value


def _full_sha(value: Any, *, label: str) -> str:
    normalized = str(value).lower() if isinstance(value, str) else ""
    if FULL_SHA_RE.fullmatch(normalized) is None:
        raise FinalOutcomeError(f"{label} must be one lowercase full Git SHA")
    return normalized


def _sha256(value: Any, *, label: str) -> str:
    normalized = str(value).lower() if isinstance(value, str) else ""
    if SHA256_RE.fullmatch(normalized) is None:
        raise FinalOutcomeError(f"{label} must be one lowercase SHA-256")
    return normalized


def _finite_positive(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise FinalOutcomeError(f"{label} must be positive and finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FinalOutcomeError(f"{label} must be positive and finite") from exc
    if not math.isfinite(result) or result <= 0.0:
        raise FinalOutcomeError(f"{label} must be positive and finite")
    return result


def _finite_nonnegative(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise FinalOutcomeError(f"{label} must be nonnegative and finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise FinalOutcomeError(
            f"{label} must be nonnegative and finite"
        ) from exc
    if not math.isfinite(result) or result < 0.0:
        raise FinalOutcomeError(f"{label} must be nonnegative and finite")
    return result


def _canonical_payload_sha(payload: Mapping[str, Any], field: str) -> str:
    canonical = dict(payload)
    canonical.pop(field, None)
    rendered = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(rendered).hexdigest()


def _read_json(
    role: str, path: Path | str, *, repo_root: Path
) -> tuple[Path, str, Mapping[str, Any], str]:
    root = repo_root.resolve()
    requested = Path(path)
    resolved = (
        requested.resolve()
        if requested.is_absolute()
        else (root / requested).resolve()
    )
    try:
        descriptor_path = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise FinalOutcomeError(
            f"{role} evidence path escapes repository root: {path}"
        ) from exc
    try:
        raw = resolved.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalOutcomeError(f"cannot read {role} evidence {resolved}: {exc}") from exc
    return (
        resolved,
        descriptor_path,
        _mapping(payload, label=f"{role} evidence"),
        hashlib.sha256(raw).hexdigest(),
    )


def _formal_source(payload: Mapping[str, Any], *, role: str) -> str:
    source = _mapping(payload.get("formal_source"), label=f"{role}.formal_source")
    if source.get("tracked_source_clean") is not True:
        raise FinalOutcomeError(f"{role} is not tracked-source-clean")
    return _full_sha(source.get("commit_sha"), label=f"{role}.formal_source.commit_sha")


def _watchdog_source(payload: Mapping[str, Any], *, role: str) -> str:
    gate = _mapping(payload.get("source_gate"), label=f"{role}.source_gate")
    checks = _mapping(gate.get("checks"), label=f"{role}.source_gate.checks")
    if gate.get("pass") is not True or not checks or not all(value is True for value in checks.values()):
        raise FinalOutcomeError(f"{role} failed its complete clean-source gate")
    return _full_sha(gate.get("head_sha"), label=f"{role}.source_gate.head_sha")


def _validate_kind(role: str, payload: Mapping[str, Any]) -> None:
    expected: dict[str, tuple[Any, Any]] = {
        "case090_core": (
            "task033.case090.core-gates.v1",
            "high_order_floquet_core_gate_result",
        ),
        "qep_mpi1_aggregate": (
            "task033.qep-aggregate.v1",
            "task033_qep_aggregate",
        ),
        "uniform_p_h_matrix": (
            "task033.case091.uniform-p-h-matrix.v1",
            "task033_uniform_p_h_matrix",
        ),
        "equal_accuracy": (
            "task033.case091.equal-accuracy.v1",
            "task033_global_equal_accuracy_efficiency",
        ),
        "adaptive_p2_h5": (1, "p2_periodic_graded_mesh_plan"),
        "adaptive_p2_h3": (1, "p2_periodic_graded_mesh_plan"),
        "interface_buffer_tradeoff": (
            "task033.case091.interface-buffer-tradeoff.v1",
            "task033_interface_buffer_tradeoff",
        ),
        "variable_p_capability_audit": (
            "task033.case091.variable-p-audit.v1",
            "task033_variable_p_hcurl_capability_audit",
        ),
        "one_tib_projection": (
            "task033.case091.one-tib-projection.v1",
            "task033_one_tib_local_fe_row_projection",
        ),
    }
    if role in expected:
        schema_version, record_type = expected[role]
        if payload.get("schema_version") != schema_version or payload.get("record_type") != record_type:
            raise FinalOutcomeError(f"{role} has the wrong schema_version or record_type")
        return
    if role.startswith("qep_mpi") and role.endswith("timeout_negative"):
        if payload.get("schema_version") != "task033.memory-watchdog.v2" or payload.get("target") != "qep":
            raise FinalOutcomeError(f"{role} is not a Task033 QEP watchdog summary")
        return
    if role.startswith("augmented_vs_minimal_"):
        if payload.get("schema_version") != "task033.memory-watchdog.v2" or payload.get("target") != "hybrid":
            raise FinalOutcomeError(f"{role} is not a Task033 Hybrid watchdog summary")
        return
    raise FinalOutcomeError(f"unsupported final-outcome evidence role: {role}")


def _load(role: str, path: Path | str, *, repo_root: Path) -> Evidence:
    resolved, descriptor_path, payload, file_sha = _read_json(
        role, path, repo_root=repo_root
    )
    _validate_kind(role, payload)
    if role == "case090_core":
        identity = _mapping(payload.get("identity"), label="case090_core.identity")
        if identity.get("tracked_source_dirty") is not False:
            raise FinalOutcomeError("case090_core is not clean-source evidence")
        source_sha = _full_sha(
            identity.get("source_commit_full_sha"),
            label="case090_core.identity.source_commit_full_sha",
        )
        observed = _sha256(payload.get("evidence_sha256"), label="case090_core.evidence_sha256")
        if observed != _canonical_payload_sha(payload, "evidence_sha256"):
            raise FinalOutcomeError("case090_core payload SHA-256 is invalid")
    elif role == "equal_accuracy":
        identity = _mapping(payload.get("identity"), label="equal_accuracy.identity")
        source_sha = _full_sha(
            identity.get("source_commit_full_sha"),
            label="equal_accuracy.identity.source_commit_full_sha",
        )
        if identity.get("all_qualified_inputs_same_clean_sha") is not True:
            raise FinalOutcomeError("equal_accuracy lacks its same-clean-SHA attestation")
        observed = _sha256(payload.get("payload_sha256"), label="equal_accuracy.payload_sha256")
        if observed != _canonical_payload_sha(payload, "payload_sha256"):
            raise FinalOutcomeError("equal_accuracy payload SHA-256 is invalid")
    elif role.startswith("qep_mpi") and role.endswith("timeout_negative") or role.startswith(
        "augmented_vs_minimal_"
    ):
        source_sha = _watchdog_source(payload, role=role)
    else:
        source_sha = _formal_source(payload, role=role)
    if role == "qep_mpi1_aggregate":
        files = qep_source_record_file_gate(
            payload, root=repo_root
        )
        if files.get("pass") is not True:
            raise FinalOutcomeError(
                "qep_mpi1_aggregate source-record files failed hash/binding "
                f"checks: {files.get('failures')!r}"
            )
    return Evidence(
        role, resolved, descriptor_path, payload, file_sha, source_sha
    )


def _command_mpi_size(command: Any, *, label: str) -> int | None:
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        return None
    values = [str(item) for item in command]
    try:
        return int(values[values.index("-n") + 1])
    except (ValueError, IndexError):
        return None


def _all_true(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(item is True for item in value.values())


def _timeout_result(evidence: Evidence, expected_mpi: int) -> dict[str, Any]:
    payload = evidence.payload
    reasons: list[str] = []
    resource_authority = payload.get("resource_authority")
    resource_authority = (
        resource_authority
        if isinstance(resource_authority, Mapping)
        else {}
    )
    resource_gate = resource_authority.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    checks = {
        "formal_not_pass": payload.get("status") == "formal_not_pass" and payload.get("formal_pass") is False,
        "numeric_not_pass": payload.get("numeric_pass") is False,
        "nonzero_integer_return_code": (
            type(payload.get("return_code")) is int
            and payload.get("return_code") != 0
        ),
        "wall_timeout_only": (
            payload.get("terminated_for_timeout") is True
            and payload.get("terminated_for_memory") is False
            and payload.get("terminated_for_authority_unreadable") is False
        ),
        "memory_authority_pass": payload.get("memory_authority_pass") is True,
        "resource_authority_gate_pass": resource_gate.get("pass") is True,
        "no_swap": payload.get("no_swap") is True,
        "source_gate_pass": isinstance(payload.get("source_gate"), Mapping)
        and payload["source_gate"].get("pass") is True,
        "launch_gate_pass": isinstance(payload.get("launch_gate"), Mapping)
        and payload["launch_gate"].get("pass") is True,
        "expected_mpi_size": _command_mpi_size(payload.get("command"), label=evidence.role)
        == expected_mpi,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    return {
        "mpi_size": expected_mpi,
        "disposition": "legitimate_not_run" if not reasons else "failed",
        "classification": (
            "clean_wall_timeout_only" if not reasons else "invalid_timeout_negative"
        ),
        "positive_qep_qualification": False,
        "proves_watchdog_source_resource_timeout_contract_only": not reasons,
        "proves_pep_or_mumps_boundary": False,
        "checks": checks,
        "failures": reasons,
    }


def _anchor_result(evidence: Evidence, expected_degree: int) -> dict[str, Any]:
    payload = evidence.payload
    measurements = payload.get("measurements")
    measurements = measurements if isinstance(measurements, Mapping) else {}
    case = measurements.get("case")
    case = case if isinstance(case, Mapping) else {}
    hybrid = measurements.get("hybrid_system")
    hybrid = hybrid if isinstance(hybrid, Mapping) else {}
    comparison = measurements.get("modal_schur_comparison")
    comparison = comparison if isinstance(comparison, Mapping) else {}
    expected_modes = 120 if expected_degree == 1 else 160
    controlled_p1_negative = bool(
        expected_degree == 1
        and _controlled_physical_truncation_negative(payload)
    )
    checks = {
        "formal_watchdog_pass_or_controlled_p1_physical_negative": bool(
            controlled_p1_negative
            or (
                payload.get("status") == "measured_shard_pass"
                and payload.get("formal_pass") is True
            )
        ),
        "no_termination_or_swap": (
            payload.get("terminated_for_timeout") is False
            and payload.get("terminated_for_memory") is False
            and payload.get("terminated_for_authority_unreadable") is False
            and payload.get("no_swap") is True
        ),
        "launch_and_memory_authority_pass": payload.get("memory_authority_pass") is True
        and isinstance(payload.get("launch_gate"), Mapping)
        and payload["launch_gate"].get("pass") is True,
        "case_is_expected_p_h_mpi": case.get("degree") == expected_degree
        and float(case.get("h_nm", -1.0)) == 5.0
        and _command_mpi_size(payload.get("command"), label=evidence.role) == 4
        and payload.get("requested_modes") == expected_modes
        and payload.get("candidate_modes") == 2 * expected_modes,
        "augmented_primary": hybrid.get("primary_solver_path") == "augmented",
        "minimal_comparison_pass": comparison.get("status") == "pass"
        and comparison.get("comparison_solver_path") == "modal-schur-memory-minimal"
        and comparison.get("comparison_solver_path_argument") == "minimal",
        "sparse_comparison": comparison.get("dense_interface_square_formed") is False,
        "all_comparison_gates_pass": _all_true(comparison.get("gates")),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "degree": expected_degree,
        "disposition": "pass" if not failures else "failed",
        "classification": (
            (
                "augmented_vs_memory_minimal_algebraic_qualified_"
                "with_controlled_p1_physical_truncation_negative"
            )
            if not failures and controlled_p1_negative
            else "augmented_vs_memory_minimal_qualified"
            if not failures
            else "augmented_vs_memory_minimal_not_qualified"
        ),
        "checks": checks,
        "failures": failures,
    }


def _uniform_rows(evidence: Evidence) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    payload = evidence.payload
    raw = payload.get("entries")
    if not isinstance(raw, list) or len(raw) != 20 or not all(isinstance(row, Mapping) for row in raw):
        raise FinalOutcomeError("uniform_p_h_matrix must contain exactly 20 object rows")
    rows = list(raw)
    coordinates = {(row.get("degree"), float(row.get("h_nm", -1.0))) for row in rows}
    expected = {(degree, h) for degree in (1, 2, 3, 4) for h in (5.0, 3.0, 2.5, 2.0, 1.5)}
    if coordinates != expected:
        raise FinalOutcomeError("uniform_p_h_matrix does not cover the frozen 4x5 matrix")
    measured = 0
    not_run = 0
    capacity_negatives = 0
    terminal_physical_negatives = 0
    for row in rows:
        disposition = row.get("evidence_disposition")
        if disposition == "not_run_by_memory_gate":
            if (
                row.get("planning_decision") != "not_run_by_memory_gate"
                or row.get("launch_decision") != "not_run_by_memory_gate"
                or row.get("data_identity") != "not_run"
                or row.get("source_record_sha256") is not None
            ):
                raise FinalOutcomeError("uniform matrix contains an invalid memory-gated row")
            not_run += 1
        else:
            if disposition not in {
                "measured_qualified_funnel",
                "measured_not_qualified_by_modal_basis_capacity",
                "measured_not_qualified_by_physical_field_gates",
                "measured_external_watchdog_shard",
                "measured_task032_clean_anchor",
            }:
                raise FinalOutcomeError(
                    "uniform matrix contains an unknown measured disposition"
                )
            if disposition == "measured_not_qualified_by_modal_basis_capacity":
                exact_capacity_row = bool(
                    row.get("degree") == 1
                    and float(row.get("h_nm", -1.0)) == 5.0
                    and row.get("source_status") == "not_qualified"
                    and row.get("source_is_pde_run") is True
                    and row.get("source_is_solver_pass") is False
                    and row.get("selected_mode_count_per_direction") is None
                    and row.get("candidate_modes_per_target_branch") == 320
                    and row.get("attempted_mode_count_per_direction") == 160
                    and is_exact_p1_h5_modal_basis_capacity(
                        row.get("modal_basis_capacity")
                    )
                )
                if not exact_capacity_row:
                    raise FinalOutcomeError(
                        "uniform matrix contains a non-exact modal-basis capacity negative"
                    )
            if disposition == "measured_not_qualified_by_physical_field_gates":
                terminal = row.get("terminal_physical_gate_evidence")
                terminal = terminal if isinstance(terminal, Mapping) else {}
                exact_terminal_row = bool(
                    row.get("degree") == 1
                    and float(row.get("h_nm", -1.0)) in {3.0, 2.5, 2.0, 1.5}
                    and row.get("source_status") == "not_qualified"
                    and row.get("source_is_pde_run") is True
                    and row.get("source_is_solver_pass") is False
                    and row.get("selected_mode_count_per_direction") is None
                    and row.get("candidate_modes_per_target_branch") == 320
                    and row.get("attempted_mode_count_per_direction") == 160
                    and row.get("modal_basis_capacity") is None
                    and row.get("terminal_physical_gate_limited") is True
                    and is_exact_p1_terminal_reference_evidence(
                        row.get("terminal_physical_reference_evidence")
                    )
                    and terminal.get("integration_pass") is False
                    and terminal.get("algebraic_chain_pass") is True
                    and terminal.get("physical_field_gates_pass") is False
                    and terminal.get("task033_physical_truncation_allowed") is True
                    and terminal.get("candidate_pool_is_twice_requested_modes") is True
                    and terminal.get("true_relative_residual_le_1e-9") is True
                    and terminal.get("all_reported_gates_pass") is False
                    and _finite_nonnegative(
                        terminal.get("true_relative_residual"),
                        label="uniform terminal p1 true residual",
                    )
                    <= 1.0e-9
                )
                if not exact_terminal_row:
                    raise FinalOutcomeError(
                        "uniform matrix contains a non-exact p1 terminal physical negative"
                    )
            _sha256(row.get("source_record_sha256"), label=f"uniform.{row.get('matrix_key')}.source_record_sha256")
            if row.get("source_commit_sha") != evidence.source_sha or row.get("data_identity") != "measured":
                raise FinalOutcomeError("uniform measured row is not bound to the common clean SHA")
            measured += 1
            capacity_negatives += int(
                disposition
                == "measured_not_qualified_by_modal_basis_capacity"
            )
            terminal_physical_negatives += int(
                disposition
                == "measured_not_qualified_by_physical_field_gates"
            )
    passed = payload.get("status") == "formal_matrix_complete"
    return rows, {
        "disposition": "pass" if passed else "failed",
        "measured_entries": measured,
        "not_run_by_memory_gate_entries": not_run,
        "modal_basis_capacity_negative_entries": capacity_negatives,
        "p1_terminal_physical_gate_negative_entries": (
            terminal_physical_negatives
        ),
        "entry_count": len(rows),
    }


def classify_compression(ratio: float) -> str:
    value = _finite_positive(ratio, label="compression ratio")
    if value < 1.3:
        return HP_CLASSIFICATIONS["weak"]
    if value < 2.0:
        return HP_CLASSIFICATIONS["positive"]
    if value < 3.0:
        return HP_CLASSIFICATIONS["clear"]
    if value < 5.0:
        return HP_CLASSIFICATIONS["engineering"]
    return HP_CLASSIFICATIONS["strong"]


def _degree_equal_accuracy(
    evidence: Evidence,
    uniform_rows: Sequence[Mapping[str, Any]],
    *,
    degree: int,
) -> tuple[dict[str, Any], list[tuple[str, float]]]:
    payload = evidence.payload
    reference = _mapping(payload.get("reference"), label="equal_accuracy.reference")
    reference_case = _mapping(reference.get("case"), label="equal_accuracy.reference.case")
    if reference_case.get("degree") != 2 or float(reference_case.get("h_nm", -1.0)) != 3.0:
        raise FinalOutcomeError("equal_accuracy reference must be uniform p2/h3")
    if reference.get("source_commit_full_sha") != evidence.source_sha:
        raise FinalOutcomeError("equal_accuracy reference SHA differs from the final source SHA")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not all(isinstance(row, Mapping) for row in candidates):
        raise FinalOutcomeError("equal_accuracy.candidates must be an array of objects")
    inputs = _mapping(payload.get("inputs"), label="equal_accuracy.inputs")
    input_rows = inputs.get("candidates")
    if not isinstance(input_rows, list):
        raise FinalOutcomeError("equal_accuracy input descriptors are missing")
    descriptors = {
        row.get("candidate_id"): row
        for row in input_rows
        if isinstance(row, Mapping) and isinstance(row.get("candidate_id"), str)
    }
    degree_candidates: list[Mapping[str, Any]] = []
    by_coordinate: dict[tuple[int, float], Mapping[str, Any]] = {}
    for row in candidates:
        source_sha = _full_sha(
            row.get("source_commit_full_sha"),
            label=f"equal_accuracy.{row.get('candidate_id')}.source_commit_full_sha",
        )
        if source_sha != evidence.source_sha:
            raise FinalOutcomeError("equal_accuracy contains a mixed-SHA candidate")
        case = _mapping(row.get("case"), label=f"equal_accuracy.{row.get('candidate_id')}.case")
        coordinate = (int(case.get("degree", -1)), float(case.get("h_nm", -1.0)))
        descriptor = _mapping(descriptors.get(row.get("candidate_id")), label="equal_accuracy candidate descriptor")
        input_descriptor = _mapping(row.get("input"), label="equal_accuracy candidate input")
        digest = _sha256(input_descriptor.get("funnel_sha256"), label="equal_accuracy funnel SHA")
        if descriptor.get("funnel_sha256") != digest:
            raise FinalOutcomeError("equal_accuracy candidate descriptor SHA mismatch")
        is_target_uniform = bool(
            coordinate[0] == degree
            and case.get("graded_reference_h_nm") is None
        )
        if is_target_uniform:
            if coordinate in by_coordinate:
                raise FinalOutcomeError(
                    f"equal_accuracy contains duplicate uniform p{degree}/h candidates"
                )
            by_coordinate[coordinate] = row
            degree_candidates.append(row)

    matrix_degree_rows = [row for row in uniform_rows if row.get("degree") == degree]
    measured_rows = [row for row in matrix_degree_rows if row.get("evidence_disposition") != "not_run_by_memory_gate"]
    for row in measured_rows:
        coordinate = (degree, float(row["h_nm"]))
        candidate = by_coordinate.get(coordinate)
        if candidate is None:
            continue
        candidate_digest = candidate.get("input", {}).get("funnel_sha256")
        if candidate_digest != row.get("source_record_sha256"):
            raise FinalOutcomeError(f"equal_accuracy and uniform matrix disagree on {coordinate} file SHA")
    missing = [float(row["h_nm"]) for row in measured_rows if (degree, float(row["h_nm"])) not in by_coordinate]
    unexpected = [float(row.get("case", {}).get("h_nm")) for row in degree_candidates if not any(float(base["h_nm"]) == float(row.get("case", {}).get("h_nm")) for base in measured_rows)]
    if degree == 4 and not measured_rows:
        legitimate = all(row.get("evidence_disposition") == "not_run_by_memory_gate" for row in matrix_degree_rows)
        return {
            "degree": degree,
            "disposition": "legitimate_not_run" if legitimate else "failed",
            "classification": "not_run_by_memory_gate" if legitimate else "missing_required_result",
            "measured_candidate_count": 0,
            "qualified_candidate_count": 0,
            "best_candidate_id": None,
            "best_h_nm": None,
            "local_dof_compression": None,
            "compression_classification": None,
            "failures": [] if legitimate else ["p4_not_run_is_not_memory_gated"],
        }, []
    if missing or unexpected or not measured_rows:
        failures = [
            *(f"missing_equal_accuracy_h{h:g}" for h in missing),
            *(f"unexpected_equal_accuracy_h{h:g}" for h in unexpected),
        ]
        if not measured_rows:
            failures.append(f"p{degree}_has_no_measured_uniform_candidate")
        return {
            "degree": degree,
            "disposition": "failed",
            "classification": "incomplete_equal_accuracy_evidence",
            "measured_candidate_count": len(measured_rows),
            "qualified_candidate_count": 0,
            "best_candidate_id": None,
            "best_h_nm": None,
            "local_dof_compression": None,
            "compression_classification": None,
            "failures": failures,
        }, []
    qualified = [row for row in degree_candidates if row.get("status") == "equal_accuracy_qualified"]
    invalid_status = [row for row in degree_candidates if row.get("status") not in {"equal_accuracy_qualified", "not_qualified"}]
    if invalid_status:
        raise FinalOutcomeError(f"equal_accuracy p{degree} contains an invalid status")
    compressions: list[tuple[str, float]] = []
    for row in qualified:
        ratios = _mapping(row.get("compression_ratios"), label="equal_accuracy compression_ratios")
        compression = _finite_positive(ratios.get("local_dofs"), label="equal_accuracy local DoF compression")
        expected_class = classify_compression(compression).removeprefix("hp_compression_")
        if row.get("local_dof_compression_classification") != expected_class:
            raise FinalOutcomeError("equal_accuracy compression classification is inconsistent")
        compressions.append((str(row.get("candidate_id")), compression))
    if not qualified:
        return {
            "degree": degree,
            "disposition": "negative",
            "classification": "measured_no_equal_accuracy_candidate",
            "measured_candidate_count": len(measured_rows),
            "qualified_candidate_count": 0,
            "best_candidate_id": None,
            "best_h_nm": None,
            "local_dof_compression": None,
            "compression_classification": None,
            "failures": [],
        }, []
    best = min(
        qualified,
        key=lambda row: tuple(
            float(_mapping(row.get("costs"), label="equal_accuracy costs")[key])
            for key in ("local_dofs", "total_rows", "assembled_nnz", "authoritative_rss_bytes", "total_time_seconds")
        ),
    )
    compression = _finite_positive(best["compression_ratios"]["local_dofs"], label="best compression")
    return {
        "degree": degree,
        "disposition": "pass",
        "classification": "equal_accuracy_qualified",
        "measured_candidate_count": len(measured_rows),
        "qualified_candidate_count": len(qualified),
        "best_candidate_id": best.get("candidate_id"),
        "best_h_nm": float(best["case"]["h_nm"]),
        "local_dof_compression": compression,
        "compression_classification": classify_compression(compression),
        "failures": [],
    }, compressions


def _adaptive_result(evidence: Evidence, expected_h: float) -> dict[str, Any]:
    payload = evidence.payload
    plan = _mapping(payload.get("plan"), label=f"adaptive_h{expected_h:g}.plan")
    qualification = _mapping(
        payload.get("same_accuracy_qualification"),
        label=f"adaptive_h{expected_h:g}.same_accuracy_qualification",
    )
    compression = _finite_positive(qualification.get("compression"), label=f"adaptive h{expected_h:g} compression")
    passed = bool(
        payload.get("status") == "measured_same_accuracy_qualification_attached"
        and float(plan.get("reference_h_nm", -1.0)) == expected_h
        and qualification.get("mandatory_gate_pass") is True
        and qualification.get("status")
        in {"same_accuracy_mandatory_gate_pass", "same_accuracy_strong_gate_pass"}
        and qualification.get("compression_unit") == "dimensionless_local_fe_row_ratio"
        and qualification.get("compression_baseline") == f"uniform_p2_h{expected_h:g}"
        and qualification.get("compression_denominator") == "candidate_local_fe_rows"
    )
    measured = _mapping(payload.get("measured_evidence"), label=f"adaptive_h{expected_h:g}.measured_evidence")
    for key in ("reference", "candidate"):
        descriptor = _mapping(measured.get(key), label=f"adaptive_h{expected_h:g}.{key}")
        _sha256(descriptor.get("sha256"), label=f"adaptive_h{expected_h:g}.{key}.sha256")
        _sha256(
            descriptor.get("selected_watchdog_sha256"),
            label=f"adaptive_h{expected_h:g}.{key}.selected_watchdog_sha256",
        )
    return {
        "reference_h_nm": expected_h,
        "disposition": "pass" if passed else "failed",
        "qualification_status": qualification.get("status"),
        "compression": compression,
        "compression_classification": classify_compression(compression),
    }


def _buffer_result(evidence: Evidence) -> dict[str, Any]:
    payload = evidence.payload
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise FinalOutcomeError("buffer tradeoff candidates are missing")
    observed = {float(row.get("buffer_nm")) for row in candidates if isinstance(row, Mapping)}
    if observed != {10.0, 7.5, 5.0, 2.5}:
        raise FinalOutcomeError("buffer tradeoff does not contain the four frozen candidates")
    for row in candidates:
        _sha256(row.get("source_record_sha256"), label="buffer candidate source SHA")
    selected = float(payload.get("selected_buffer_nm", -1.0))
    passed = payload.get("status") == "qualified" and selected in observed
    return {
        "disposition": "pass" if passed else "failed",
        "selected_buffer_nm": selected if selected in observed else None,
        "candidate_count": len(candidates),
    }


def _variable_p_result(evidence: Evidence) -> dict[str, Any]:
    payload = evidence.payload
    decision = _mapping(payload.get("decision"), label="variable_p.decision")
    safe_negative = bool(
        payload.get("status") == "not_qualified_fail_closed"
        and decision.get("native_cellwise_variable_p_hcurl_qualified") is False
        and decision.get("implement_bespoke_arbitrary_variable_p_constraints") is False
        and decision.get("disposition") == "fail_closed_no_hp_zoning_prototype"
    )
    return {
        "capability_disposition": (
            "not_qualified_fail_closed" if safe_negative else "failed"
        ),
        "hp_zoning_prototype_disposition": (
            "legitimate_not_run" if safe_negative else "failed"
        ),
        "bespoke_constraints_implemented": False,
    }


def _matching_path(raw: Any, evidence_file: Path, candidates: Sequence[Evidence]) -> Evidence | None:
    if not isinstance(raw, str) or not raw:
        return None
    requested = Path(raw)
    paths = [requested]
    if not requested.is_absolute():
        paths.extend((evidence_file.parent / requested, ROOT / requested))
    resolved = {path.resolve() for path in paths}
    return next((candidate for candidate in candidates if candidate.path in resolved), None)


def _one_tib_result(
    evidence: Evidence,
    equal_accuracy: Evidence,
    adaptive: Sequence[Evidence],
) -> dict[str, Any]:
    payload = evidence.payload
    identity = _mapping(payload.get("identity"), label="one_tib.identity")
    source_input = _mapping(payload.get("input"), label="one_tib.input")
    result = _mapping(payload.get("result"), label="one_tib.result")
    chosen = _matching_path(
        source_input.get("evidence_record"),
        evidence.path,
        (equal_accuracy, *adaptive),
    )
    if chosen is None:
        raise FinalOutcomeError(
            "1 TiB projection is not path-bound to provided compression evidence"
        )
    compression = _finite_positive(source_input.get("same_error_local_dof_compression"), label="1 TiB compression")
    route_basis = payload.get("route_basis")
    if chosen.role == "equal_accuracy":
        if route_basis != "equal_accuracy_best_candidate":
            raise FinalOutcomeError(
                "1 TiB equal-accuracy evidence has the wrong route_basis"
            )
        equal_payload = chosen.payload
        selection = _mapping(
            equal_payload.get("selection"), label="equal_accuracy.selection"
        )
        best_id = selection.get("best_candidate_id")
        matches = [
            row
            for row in equal_payload.get("candidates", [])
            if isinstance(row, Mapping)
            and row.get("candidate_id") == best_id
            and row.get("status") == "equal_accuracy_qualified"
        ]
        if len(matches) != 1:
            raise FinalOutcomeError(
                "1 TiB equal-accuracy best candidate is not uniquely qualified"
            )
        best = matches[0]
        reference = _mapping(
            equal_payload.get("reference"), label="equal_accuracy.reference"
        )
        reference_costs = _mapping(
            reference.get("costs"), label="equal_accuracy.reference.costs"
        )
        candidate_costs = _mapping(
            best.get("costs"), label="equal_accuracy.best.costs"
        )
        reference_dofs = int(
            _finite_positive(
                reference_costs.get("local_dofs"),
                label="equal_accuracy reference local DoFs",
            )
        )
        candidate_dofs = int(
            _finite_positive(
                candidate_costs.get("local_dofs"),
                label="equal_accuracy candidate local DoFs",
            )
        )
        expected_compression = reference_dofs / candidate_dofs
        route_checks = bool(
            source_input.get("evidence_record_type")
            == "task033_global_equal_accuracy_efficiency"
            and source_input.get("evidence_schema_version")
            == "task033.case091.equal-accuracy.v1"
            and source_input.get("evidence_payload_sha256")
            == equal_payload.get("payload_sha256")
            and source_input.get("same_accuracy_status")
            == "equal_accuracy_qualified"
            and source_input.get("compression_source_unit")
            == "dimensionless_local_fe_row_ratio"
            and source_input.get("compression_baseline")
            == "measured_equal_accuracy_reference_local_dofs"
            and source_input.get("best_candidate_id") == best_id
            and source_input.get("best_candidate_label") == best.get("label")
            and source_input.get("reference_local_dofs") == reference_dofs
            and source_input.get("candidate_local_dofs") == candidate_dofs
        )
    else:
        if route_basis != "p2_adaptive_only":
            raise FinalOutcomeError(
                "1 TiB adaptive evidence has the wrong route_basis"
            )
        qualification = _mapping(
            chosen.payload.get("same_accuracy_qualification"),
            label="chosen adaptive qualification",
        )
        expected_compression = _finite_positive(
            qualification.get("compression"),
            label="adaptive compression",
        )
        route_checks = bool(
            source_input.get("same_accuracy_status")
            == qualification.get("status")
            and source_input.get("compression_source_unit")
            == qualification.get("compression_unit")
            and source_input.get("compression_baseline")
            == qualification.get("compression_baseline")
        )
    if not math.isclose(
        compression,
        expected_compression,
        rel_tol=1.0e-12,
        abs_tol=1.0e-15,
    ):
        raise FinalOutcomeError(
            "1 TiB projection compression disagrees with its evidence"
        )
    classification = result.get("classification")
    passed = bool(
        payload.get("status") == "classified"
        and source_input.get("qualified") is True
        and source_input.get("source_commit_sha") == evidence.source_sha
        and source_input.get("physical_equal_accuracy_qualified") is True
        and route_checks
        and classification in {"preferred", "candidate", "high-risk", "infeasible"}
        and identity.get("is_0p7nm_wavelength_transfer_validation") is False
        and identity.get("is_0p7nm_feasibility_proof") is False
    )
    return {
        "disposition": "pass" if passed else "failed",
        "classification": classification if classification in {"preferred", "candidate", "high-risk", "infeasible"} else None,
        "projected_local_fe_rows": result.get("projected_local_fe_rows"),
        "same_error_local_dof_compression": compression,
        "compression_evidence_role": chosen.role,
        "compression_evidence_sha256": chosen.sha256,
        "proves_0p7nm_feasible": False,
    }


def _core_pass(payload: Mapping[str, Any]) -> bool:
    identity = payload.get("identity")
    memory = payload.get("external_memory_watchdog")
    coverage = payload.get("coverage")
    expected = {(degree, mpi) for degree in (1, 2, 3, 4) for mpi in (1, 2, 4)}
    observed = {
        (row.get("degree"), row.get("mpi_size"))
        for row in coverage
        if isinstance(coverage, list) and isinstance(row, Mapping)
    } if isinstance(coverage, list) else set()
    return bool(
        payload.get("all_core_gates_passed") is True
        and isinstance(identity, Mapping)
        and identity.get("is_solver_pass") is True
        and payload.get("failures") == []
        and observed == expected
        and all(
            row.get("core_algebra_gates_passed") is True
            for row in coverage
            if isinstance(row, Mapping)
        )
        and isinstance(memory, Mapping)
        and memory.get("all_three_qualified") is True
    )


def _qep_pass(payload: Mapping[str, Any]) -> bool:
    return bool(
        qep_full_aggregate_gate(
            payload, require_evidence_descriptors=True
        ).get("pass")
        is True
    )


def _qep_p3_only_partial(payload: Mapping[str, Any]) -> bool:
    return bool(
        qep_p3_only_partial_aggregate_gate(
            payload, require_evidence_descriptors=True
        ).get("pass")
        is True
    )


def build_final_outcome(
    *,
    case090_core: Path | str,
    qep_mpi1_aggregate: Path | str,
    qep_mpi2_timeout_negative: Path | str,
    qep_mpi4_timeout_negative: Path | str,
    augmented_vs_minimal_p1: Path | str,
    augmented_vs_minimal_p3: Path | str,
    uniform_p_h_matrix: Path | str,
    equal_accuracy: Path | str,
    adaptive_p2_h5: Path | str,
    adaptive_p2_h3: Path | str,
    interface_buffer_tradeoff: Path | str,
    variable_p_capability_audit: Path | str,
    one_tib_projection: Path | str,
    expected_source_sha: str,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Classify Task033 from immutable formal inputs without promoting NOT_RUN."""

    root = Path(repo_root).resolve()
    requested = locals()
    evidence = {
        role: _load(role, requested[role], repo_root=root)
        for role in INPUT_ROLES
    }
    expected_sha = _full_sha(expected_source_sha, label="expected_source_sha")
    observed_shas = {item.source_sha for item in evidence.values()}
    if observed_shas != {expected_sha}:
        raise FinalOutcomeError(
            f"final outcome mixes clean-source SHAs: {sorted(observed_shas)!r}; expected {expected_sha}"
        )

    core_pass = _core_pass(evidence["case090_core"].payload)
    qep_pass = _qep_pass(evidence["qep_mpi1_aggregate"].payload)
    qep_p3_only_partial = _qep_p3_only_partial(
        evidence["qep_mpi1_aggregate"].payload
    )
    timeout2 = _timeout_result(evidence["qep_mpi2_timeout_negative"], 2)
    timeout4 = _timeout_result(evidence["qep_mpi4_timeout_negative"], 4)
    anchor1 = _anchor_result(evidence["augmented_vs_minimal_p1"], 1)
    anchor3 = _anchor_result(evidence["augmented_vs_minimal_p3"], 3)
    uniform_rows, uniform_result = _uniform_rows(evidence["uniform_p_h_matrix"])
    p3, p3_compressions = _degree_equal_accuracy(
        evidence["equal_accuracy"], uniform_rows, degree=3
    )
    p4, p4_compressions = _degree_equal_accuracy(
        evidence["equal_accuracy"], uniform_rows, degree=4
    )
    adaptive_h5 = _adaptive_result(evidence["adaptive_p2_h5"], 5.0)
    adaptive_h3 = _adaptive_result(evidence["adaptive_p2_h3"], 3.0)
    buffer = _buffer_result(evidence["interface_buffer_tradeoff"])
    variable_p = _variable_p_result(evidence["variable_p_capability_audit"])
    one_tib = _one_tib_result(
        evidence["one_tib_projection"],
        evidence["equal_accuracy"],
        (evidence["adaptive_p2_h5"], evidence["adaptive_p2_h3"]),
    )

    compression_candidates = [
        ("adaptive_p2_h3", float(adaptive_h3["compression"])),
        (
            f"one_tib/{one_tib['compression_evidence_role']}",
            float(one_tib["same_error_local_dof_compression"]),
        ),
        *[
            (f"equal_accuracy/{candidate_id}", ratio)
            for candidate_id, ratio in p3_compressions
        ],
        *[
            (f"equal_accuracy/{candidate_id}", ratio)
            for candidate_id, ratio in p4_compressions
        ],
    ]
    compression_source, best_compression = max(compression_candidates, key=lambda item: item[1])
    hp_classification = classify_compression(best_compression)

    mandatory_failures: list[str] = []
    if not core_pass:
        mandatory_failures.append("case090_core_not_qualified")
    if not qep_pass and not qep_p3_only_partial:
        mandatory_failures.append("qep_mpi1_aggregate_not_qualified")
    for name, result in (
        ("qep_mpi2_timeout_negative", timeout2),
        ("qep_mpi4_timeout_negative", timeout4),
        ("augmented_vs_minimal_p1", anchor1),
        ("augmented_vs_minimal_p3", anchor3),
        ("uniform_p_h_matrix", uniform_result),
        ("p3_equal_accuracy", p3),
        ("p4_equal_accuracy", p4),
        ("adaptive_p2_h5", adaptive_h5),
        ("adaptive_p2_h3", adaptive_h3),
        ("interface_buffer_tradeoff", buffer),
        ("one_tib_projection", one_tib),
    ):
        if result["disposition"] == "failed":
            mandatory_failures.append(f"{name}_failed")
    if variable_p["capability_disposition"] == "failed":
        mandatory_failures.append("variable_p_fail_closed_contract_failed")

    partial_reasons: list[str] = []
    if qep_p3_only_partial:
        partial_reasons.append("qep_p4_controlled_numeric_negative")
    if timeout2["disposition"] == "legitimate_not_run" and timeout4["disposition"] == "legitimate_not_run":
        partial_reasons.append("matching_interface_qep_mpi2_mpi4_not_positively_qualified")
    if p3["disposition"] == "negative":
        partial_reasons.append("p3_equal_accuracy_negative")
    if p4["disposition"] in {"negative", "legitimate_not_run"}:
        partial_reasons.append(f"p4_equal_accuracy_{p4['disposition']}")
    if uniform_result["modal_basis_capacity_negative_entries"]:
        partial_reasons.append("p1_h5_modal_basis_capacity_negative")
    if uniform_result["p1_terminal_physical_gate_negative_entries"]:
        partial_reasons.append("p1_terminal_physical_field_gate_negatives")
    if mandatory_failures:
        overall_disposition = "failed"
    elif partial_reasons:
        overall_disposition = "partial"
    else:
        overall_disposition = "pass"

    record: dict[str, Any] = {
        "schema_version": "task033.case091.final-outcome.v1",
        "record_type": "task033_final_outcome_classification",
        "task_id": "Task033",
        "status": "classified",
        "formal_source": {
            "commit_sha": expected_sha,
            "tracked_source_clean": True,
        },
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "consumes_formal_records": True,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "input_evidence": [evidence[role].descriptor() for role in INPUT_ROLES],
        "classifications": {
            "overall": {
                "disposition": overall_disposition,
                "classification": f"task033_{overall_disposition}",
                "mandatory_failures": mandatory_failures,
                "partial_reasons": partial_reasons,
            },
            "high_order_floquet": {
                "classification": (
                    "high_order_floquet_pass"
                    if core_pass and qep_pass
                    else "high_order_floquet_partial_p3_only"
                    if core_pass and qep_p3_only_partial
                    else "high_order_floquet_failed"
                ),
                "case090_core_pass": core_pass,
                "qep_mpi1_component_pass": qep_pass,
                "qep_mpi1_p3_only_partial": qep_p3_only_partial,
            },
            "distributed_qep": {
                "disposition": (
                    "partial"
                    if (
                        timeout2["disposition"]
                        == timeout4["disposition"]
                        == "legitimate_not_run"
                        and (qep_pass or qep_p3_only_partial)
                    )
                    else "failed"
                ),
                "mpi1_positive_qualified": qep_pass,
                "mpi1_p3_only_partial": qep_p3_only_partial,
                "mpi2": timeout2,
                "mpi4": timeout4,
                "matching_interface_mpi2_mpi4_positive_qualified": False,
                "timeout_attribution": "clean_wall_timeout_only_not_pep_or_mumps_boundary",
            },
            "augmented_vs_minimal_anchors": {
                "disposition": (
                    "pass"
                    if anchor1["disposition"] == anchor3["disposition"] == "pass"
                    else "failed"
                ),
                "p1": anchor1,
                "p3": anchor3,
            },
            "uniform_p_h_matrix": uniform_result,
            "equal_accuracy": {"p3": p3, "p4": p4},
            "adaptive": {"h5": adaptive_h5, "h3": adaptive_h3},
            "hp_compression": {
                "classification": hp_classification,
                "best_observed_same_accuracy_local_dof_compression": best_compression,
                "source": compression_source,
                "combination_rule": "maximum_observed_h3_reference_ratio_not_product_of_components",
            },
            "interface_buffer": buffer,
            "variable_p": variable_p,
            "one_tib": one_tib,
        },
        "limitations": [
            "QEP MPI2/MPI4 clean wall-timeouts prove only watchdog, source, resource, and timeout control; they do not identify a PEP or MUMPS boundary.",
            "Matching-interface QEP MPI2/MPI4 are not positively qualified, so this record cannot classify Task033 as a full pass.",
            "Compression ratios from different references are not multiplied; the Task033 class uses the best observed h3-reference same-accuracy local-DoF ratio.",
            "The 1 TiB result is a row-zone scenario transferred from 13.5 nm evidence, not a 0.7 nm PDE solve or feasibility proof.",
        ],
    }
    record["payload_sha256"] = _canonical_payload_sha(record, "payload_sha256")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(record), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(error.message for error in errors[:5])
        raise FinalOutcomeError(f"generated final outcome violates its schema: {details}")
    return record


__all__ = [
    "FinalOutcomeError",
    "INPUT_ROLES",
    "SCHEMA_PATH",
    "build_final_outcome",
    "classify_compression",
]
