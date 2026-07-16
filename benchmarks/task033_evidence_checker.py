"""Fail-closed evidence verification for the Task033 Case090/Case091 bundle.

The default mode verifies only committed planning identities.  Formal mode
verifies a caller-supplied manifest and every referenced evidence object; it
never turns a planning record, a manifest, or this checker's report into a PDE
or solver pass.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from benchmarks.task033_qep_qualification import (
    qep_full_aggregate_gate,
    qep_p3_only_partial_aggregate_gate,
    qep_source_record_file_gate,
)
from benchmarks.task033_hybrid_funnel import (
    _controlled_physical_truncation_negative,
    is_controlled_p1_h5_capacity_funnel,
)


ROOT = Path(__file__).resolve().parents[1]
CASE090 = Path("benchmarks/cases/090_high_order_3d_floquet_hcurl")
CASE091 = Path("benchmarks/cases/091_hybrid_hp_adaptivity_feasibility")
FORMAL_SCHEMA = CASE091 / "formal_evidence_manifest_schema.json"
DEFAULT_FORMAL_MANIFEST = CASE091 / "records/formal_evidence_manifest_NOT_RUN.json"

CASE090_SCHEMA = (CASE090 / "schema.json").as_posix()
CASE090_CORE_SCHEMA = (CASE090 / "pde_core_schema.json").as_posix()
QEP_SCHEMA = Path("benchmarks/task033_qep_qualification_schema.json").as_posix()
FUNNEL_SCHEMA = (CASE091 / "hybrid_funnel_schema.json").as_posix()
EQUAL_ACCURACY_SCHEMA = (CASE091 / "equal_accuracy_schema.json").as_posix()
VARIABLE_P_SCHEMA = (CASE091 / "variable_p_capability_schema.json").as_posix()
ONE_TIB_SCHEMA = (CASE091 / "one_tib_projection_schema.json").as_posix()
FINAL_OUTCOME_SCHEMA = (CASE091 / "final_outcome_schema.json").as_posix()
FORMAL_SCHEMA_POSIX = FORMAL_SCHEMA.as_posix()


REQUIRED_FORMAL_ROLES: tuple[str, ...] = (
    "case090_clean_core",
    "case090_mpi_memory",
    "qep_order_study",
    "qep_mpi2_timeout_negative",
    "qep_mpi4_timeout_negative",
    "hybrid_funnel_p1",
    "hybrid_funnel_p3",
    "augmented_vs_minimal_p1",
    "augmented_vs_minimal_p3",
    "uniform_p_h_matrix",
    "adaptive_p2_h5",
    "adaptive_p2_h3",
    "interface_buffer_10",
    "interface_buffer_7p5",
    "interface_buffer_5",
    "interface_buffer_2p5",
    "interface_buffer_tradeoff",
    "equal_accuracy",
    "variable_p_capability_audit",
    "one_tib_projection",
    "final_outcome",
)


FINAL_OUTCOME_INPUT_ROLE_MAP: tuple[tuple[str, str], ...] = (
    ("case090_core", "case090_clean_core"),
    ("qep_mpi1_aggregate", "qep_order_study"),
    ("qep_mpi2_timeout_negative", "qep_mpi2_timeout_negative"),
    ("qep_mpi4_timeout_negative", "qep_mpi4_timeout_negative"),
    ("augmented_vs_minimal_p1", "augmented_vs_minimal_p1"),
    ("augmented_vs_minimal_p3", "augmented_vs_minimal_p3"),
    ("uniform_p_h_matrix", "uniform_p_h_matrix"),
    ("equal_accuracy", "equal_accuracy"),
    ("adaptive_p2_h5", "adaptive_p2_h5"),
    ("adaptive_p2_h3", "adaptive_p2_h3"),
    ("interface_buffer_tradeoff", "interface_buffer_tradeoff"),
    ("variable_p_capability_audit", "variable_p_capability_audit"),
    ("one_tib_projection", "one_tib_projection"),
)


@dataclass(frozen=True)
class RoleSpec:
    """Immutable verifier policy for one formal evidence role."""

    schema_ref: str
    status_pointer: str
    accepted_statuses: tuple[Any, ...]


ROLE_SPECS: Mapping[str, RoleSpec] = {
    "case090_clean_core": RoleSpec(
        CASE090_CORE_SCHEMA, "/all_core_gates_passed", (True,)
    ),
    "case090_mpi_memory": RoleSpec(
        CASE090_CORE_SCHEMA,
        "/external_memory_watchdog/all_three_qualified",
        (True,),
    ),
    "qep_order_study": RoleSpec(
        QEP_SCHEMA,
        "/status",
        (
            "qep_component_aggregate_qualified",
            "qep_component_aggregate_not_qualified",
        ),
    ),
    "qep_mpi2_timeout_negative": RoleSpec(
        QEP_SCHEMA, "/status", ("formal_not_pass",)
    ),
    "qep_mpi4_timeout_negative": RoleSpec(
        QEP_SCHEMA, "/status", ("formal_not_pass",)
    ),
    "hybrid_funnel_p1": RoleSpec(
        FUNNEL_SCHEMA, "/status", ("qualified", "not_qualified")
    ),
    "hybrid_funnel_p3": RoleSpec(FUNNEL_SCHEMA, "/status", ("qualified",)),
    "augmented_vs_minimal_p1": RoleSpec(
        QEP_SCHEMA, "/status", ("formal_not_pass", "measured_shard_pass")
    ),
    "augmented_vs_minimal_p3": RoleSpec(
        QEP_SCHEMA, "/status", ("measured_shard_pass",)
    ),
    "uniform_p_h_matrix": RoleSpec(
        f"{FORMAL_SCHEMA_POSIX}#/$defs/uniformMatrixEvidence",
        "/status",
        ("formal_matrix_complete",),
    ),
    "adaptive_p2_h5": RoleSpec(
        f"{FORMAL_SCHEMA_POSIX}#/$defs/adaptiveEvidence",
        "/status",
        ("measured_same_accuracy_qualification_attached",),
    ),
    "adaptive_p2_h3": RoleSpec(
        f"{FORMAL_SCHEMA_POSIX}#/$defs/adaptiveEvidence",
        "/status",
        ("measured_same_accuracy_qualification_attached",),
    ),
    "interface_buffer_10": RoleSpec(
        FUNNEL_SCHEMA, "/status", ("qualified",)
    ),
    "interface_buffer_7p5": RoleSpec(
        FUNNEL_SCHEMA, "/status", ("qualified",)
    ),
    "interface_buffer_5": RoleSpec(
        FUNNEL_SCHEMA, "/status", ("qualified",)
    ),
    "interface_buffer_2p5": RoleSpec(
        FUNNEL_SCHEMA, "/status", ("qualified",)
    ),
    "interface_buffer_tradeoff": RoleSpec(
        f"{FORMAL_SCHEMA_POSIX}#/$defs/bufferTradeoffEvidence",
        "/status",
        ("qualified",),
    ),
    "equal_accuracy": RoleSpec(
        EQUAL_ACCURACY_SCHEMA, "/status", ("qualified",)
    ),
    "variable_p_capability_audit": RoleSpec(
        VARIABLE_P_SCHEMA, "/status", ("not_qualified_fail_closed",)
    ),
    "one_tib_projection": RoleSpec(
        ONE_TIB_SCHEMA, "/status", ("classified",)
    ),
    "final_outcome": RoleSpec(
        FINAL_OUTCOME_SCHEMA, "/status", ("classified",)
    ),
}


ALLOWED_SOURCE_BINDINGS: frozenset[tuple[str, str, bool]] = frozenset(
    {
        (
            "/identity/source_commit_full_sha",
            "/identity/tracked_source_dirty",
            False,
        ),
        (
            "/identity/source_commit_full_sha",
            "/identity/tracked_source_clean",
            True,
        ),
        (
            "/identity/source_commit_full_sha",
            "/identity/all_qualified_inputs_same_clean_sha",
            True,
        ),
        ("/source/commit_sha", "/source/source_clean_verified", True),
        ("/formal_source/commit_sha", "/formal_source/tracked_source_clean", True),
    }
)


class EvidenceCheckError(RuntimeError):
    """Raised when an evidence contract is absent or inconsistent."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceCheckError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvidenceCheckError(f"{path} must contain one JSON object")
    return payload


def _repo_path(root: Path, value: str | Path) -> Path:
    raw = Path(value)
    if raw.is_absolute():
        raise EvidenceCheckError(f"evidence path must be repository-relative: {raw}")
    resolved_root = root.resolve()
    resolved = (resolved_root / raw).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise EvidenceCheckError(f"evidence path escapes repository root: {raw}") from exc
    return resolved


def _portable_repo_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    if value.startswith("/") or (
        len(value) >= 2 and value[0].isalpha() and value[1] == ":"
    ):
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceCheckError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_payload_sha256(
    payload: Mapping[str, Any], *, field: str = "payload_sha256"
) -> str:
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


def _command_mpi_size(command: Any) -> int | None:
    if not isinstance(command, Sequence) or isinstance(
        command, (str, bytes, bytearray)
    ):
        return None
    values = [str(item) for item in command]
    try:
        return int(values[values.index("-n") + 1])
    except (ValueError, IndexError):
        return None


def _pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise EvidenceCheckError(f"invalid JSON pointer {pointer!r}")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise EvidenceCheckError(
                    f"JSON pointer {pointer!r} is missing component {token!r}"
                )
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise EvidenceCheckError(
                    f"JSON pointer {pointer!r} has invalid array component {token!r}"
                ) from exc
        else:
            raise EvidenceCheckError(
                f"JSON pointer {pointer!r} traverses a scalar at {token!r}"
            )
    return current


def _schema_document(root: Path, schema_ref: str) -> tuple[dict[str, Any], Any]:
    path_text, separator, fragment = schema_ref.partition("#")
    schema_path = _repo_path(root, path_text)
    schema = _load_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise EvidenceCheckError(f"invalid JSON schema {schema_path}: {exc.message}") from exc
    selected: Any = schema
    if separator and fragment:
        selected = _pointer(schema, fragment)
        if not isinstance(selected, Mapping):
            raise EvidenceCheckError(
                f"schema fragment {schema_ref!r} does not select an object"
            )
    return schema, selected


def _validate_instance(root: Path, payload: Mapping[str, Any], schema_ref: str) -> None:
    _, selected = _schema_document(root, schema_ref)
    try:
        Draft202012Validator(selected).validate(payload)
    except ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path)
        suffix = f" at /{location}" if location else ""
        raise EvidenceCheckError(
            f"JSON schema validation failed for {schema_ref}{suffix}: {exc.message}"
        ) from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceCheckError(message)


def _schema_paths(root: Path) -> list[Path]:
    paths = {
        _repo_path(root, CASE090 / "schema.json"),
        _repo_path(root, CASE090 / "pde_core_schema.json"),
        _repo_path(root, Path("benchmarks/task033_qep_qualification_schema.json")),
        _repo_path(root, FORMAL_SCHEMA),
    }
    case091 = _repo_path(root, CASE091)
    if not case091.is_dir():
        raise EvidenceCheckError(f"missing Case091 directory: {case091}")
    paths.update(case091.glob("*schema*.json"))
    return sorted(paths)


def _check_all_schemas(root: Path) -> dict[str, Any]:
    paths = _schema_paths(root)
    for path in paths:
        schema = _load_json(path)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise EvidenceCheckError(f"invalid JSON schema {path}: {exc.message}") from exc
    return {
        "schema_count": len(paths),
        "schemas": [path.relative_to(root).as_posix() for path in paths],
    }


def _check_case090_oracle(root: Path) -> dict[str, Any]:
    record = _load_json(_repo_path(root, CASE090 / "records/analytic_oracles.json"))
    _validate_instance(root, record, CASE090_SCHEMA)
    identity = record.get("identity", {})
    _require(record.get("status") == "not_run", "Case090 oracle must remain not_run")
    _require(identity.get("is_pde_run") is False, "Case090 oracle cannot be a PDE run")
    _require(identity.get("is_solver_pass") is False, "Case090 oracle cannot be a solver pass")
    return {"status": record["status"], "oracle_count": len(record.get("oracles", {}))}


def _check_case090_planner(root: Path) -> dict[str, Any]:
    record = _load_json(_repo_path(root, CASE090 / "records/analytic_oracles.json"))
    matrix = record.get("execution_matrix")
    _require(isinstance(matrix, list) and matrix, "Case090 planner matrix is missing")
    _require(
        all(
            isinstance(row, Mapping)
            and row.get("result_identity") == "not_run"
            and row.get("is_pde_run") is False
            and row.get("is_solver_pass") is False
            and str(row.get("execution_status", "")).startswith("not_run")
            for row in matrix
        ),
        "Case090 planner contains a non-NOT_RUN matrix row",
    )
    core_gate = record.get("core_gate", {})
    _require(core_gate.get("status") == "not_provided", "Case090 planning core gate must be absent")
    _require(core_gate.get("evidence_sha256") is None, "Case090 planner must not invent core evidence")
    return {"matrix_rows": len(matrix), "core_gate_status": core_gate["status"]}


def _check_case090_core_not_run(root: Path) -> dict[str, Any]:
    record = _load_json(_repo_path(root, CASE090 / "records/pde_core_NOT_RUN.json"))
    schema_ref = f"{FORMAL_SCHEMA_POSIX}#/$defs/case090CoreNotRun"
    _validate_instance(root, record, schema_ref)
    return {"status": record["status"], "required_shards": record["required_shards"]}


def _check_case091_resources(root: Path) -> dict[str, Any]:
    json_path = _repo_path(root, CASE091 / "records/resource_matrix.json")
    csv_path = _repo_path(root, CASE091 / "records/resource_matrix.csv")
    record = _load_json(json_path)
    entries = record.get("entries")
    _require(isinstance(entries, list) and len(entries) == 20, "Case091 resource JSON must have 20 entries")
    identity = record.get("identity", {})
    _require(identity.get("is_pde_run") is False, "resource planning JSON cannot be a PDE run")
    _require(identity.get("is_solver_pass") is False, "resource planning JSON cannot be a solver pass")
    json_keys = [row.get("matrix_key") for row in entries if isinstance(row, Mapping)]
    _require(len(json_keys) == 20 and len(set(json_keys)) == 20, "resource JSON matrix keys are not unique")
    try:
        with csv_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise EvidenceCheckError(f"cannot read resource CSV {csv_path}: {exc}") from exc
    csv_keys: list[str | None] = []
    for row in rows:
        raw_key = row.get("matrix_key")
        try:
            decoded = json.loads(raw_key) if raw_key is not None else None
        except json.JSONDecodeError:
            decoded = raw_key
        csv_keys.append(decoded if isinstance(decoded, str) else raw_key)
    _require(len(rows) == 20, "Case091 resource CSV must have 20 rows")
    _require(set(csv_keys) == set(json_keys), "resource JSON/CSV matrix keys differ")
    return {"json_entries": len(entries), "csv_rows": len(rows), "status": record.get("status")}


def _check_schema_record(
    root: Path,
    record_path: Path,
    schema_ref: str,
    expected_status: str,
) -> dict[str, Any]:
    record = _load_json(_repo_path(root, record_path))
    _validate_instance(root, record, schema_ref)
    _require(record.get("status") == expected_status, f"{record_path} must have status={expected_status}")
    identity = record.get("identity", {})
    _require(identity.get("is_pde_run") is False, f"{record_path} cannot claim a PDE run")
    _require(identity.get("is_solver_pass") is False, f"{record_path} cannot claim a solver pass")
    return {"status": record["status"], "schema_version": record.get("schema_version")}


def _check_qep_plan(root: Path) -> dict[str, Any]:
    details = _check_schema_record(
        root,
        CASE091 / "records/qep_matrix_plan.json",
        (CASE091 / "qep_measurement_schema.json").as_posix(),
        "not_run",
    )
    record = _load_json(_repo_path(root, CASE091 / "records/qep_matrix_plan.json"))
    summary = record.get("summary", {})
    _require(summary.get("measured_entries") == 0, "QEP plan contains measured entries")
    _require(summary.get("solver_pass_entries") == 0, "QEP plan contains solver passes")
    details["entries"] = summary.get("entries")
    return details


def _check_variable_p_plan(root: Path) -> dict[str, Any]:
    return _check_schema_record(
        root,
        CASE091 / "records/variable_p_capability_audit.json",
        VARIABLE_P_SCHEMA,
        "not_qualified_fail_closed",
    )


def _check_one_tib_plan(root: Path) -> dict[str, Any]:
    return _check_schema_record(
        root,
        CASE091 / "records/one_tib_projection_plan.json",
        ONE_TIB_SCHEMA,
        "not_qualified",
    )


def _check_current_not_run_manifest(root: Path) -> dict[str, Any]:
    record = _load_json(_repo_path(root, DEFAULT_FORMAL_MANIFEST))
    _validate_instance(root, record, FORMAL_SCHEMA_POSIX)
    _require(record.get("status") == "not_run", "committed formal manifest must remain NOT_RUN")
    _require(record.get("entries") == [], "NOT_RUN formal manifest cannot contain evidence entries")
    return {"status": record["status"], "entry_count": 0}


PlanningCheck = tuple[str, Callable[[Path], dict[str, Any]]]
PLANNING_CHECKS: tuple[PlanningCheck, ...] = (
    ("all_task033_schemas_parse", _check_all_schemas),
    ("case090_analytic_oracle_not_run", _check_case090_oracle),
    ("case090_planner_not_run", _check_case090_planner),
    ("case090_core_not_run", _check_case090_core_not_run),
    ("case091_resource_json_csv", _check_case091_resources),
    ("case091_qep_plan", _check_qep_plan),
    ("case091_variable_p_audit", _check_variable_p_plan),
    ("case091_one_tib_plan", _check_one_tib_plan),
    ("case091_formal_manifest_not_run", _check_current_not_run_manifest),
)


def _run_check(name: str, check: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        details = check()
    except (EvidenceCheckError, KeyError, TypeError, ValueError) as exc:
        return {"name": name, "status": "invalid", "details": {}, "problems": [str(exc)]}
    return {"name": name, "status": "verified", "details": details, "problems": []}


def check_planning_evidence(root: Path = ROOT) -> list[dict[str, Any]]:
    """Verify the committed planning-only Task033 evidence bundle."""

    resolved_root = Path(root).resolve()
    return [
        _run_check(name, lambda check=check: check(resolved_root))
        for name, check in PLANNING_CHECKS
    ]


def _manifest_path(root: Path, requested: Path | str) -> Path:
    path = Path(requested)
    return path.resolve() if path.is_absolute() else _repo_path(root, path)


def _manifest_structure_problems(
    manifest: Mapping[str, Any], *, root: Path
) -> list[str]:
    problems: list[str] = []
    if manifest.get("status") != "submitted_for_verification":
        problems.append("formal manifest status must be submitted_for_verification")
    if tuple(manifest.get("required_roles", ())) != REQUIRED_FORMAL_ROLES:
        problems.append("formal manifest required_roles does not match the frozen role list")
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return [*problems, "formal manifest entries must be a list"]
    roles = [entry.get("role") for entry in entries if isinstance(entry, Mapping)]
    missing = sorted(set(REQUIRED_FORMAL_ROLES) - set(roles))
    extra = sorted(set(roles) - set(REQUIRED_FORMAL_ROLES))
    duplicates = sorted({role for role in roles if roles.count(role) > 1})
    if missing:
        problems.append(f"formal manifest missing roles: {missing}")
    if extra:
        problems.append(f"formal manifest has unknown roles: {extra}")
    if duplicates:
        problems.append(f"formal manifest has duplicate roles: {duplicates}")
    entries_by_role = {
        entry.get("role"): entry
        for entry in entries
        if isinstance(entry, Mapping)
    }
    canonical_paths: dict[Any, Path] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        role = entry.get("role")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            problems.append(f"formal manifest role {role!r} has no evidence path")
            continue
        try:
            resolved = _repo_path(root, raw_path)
        except EvidenceCheckError as exc:
            problems.append(str(exc))
            continue
        canonical = resolved.relative_to(root.resolve()).as_posix()
        if raw_path != canonical:
            problems.append(
                f"formal manifest path {raw_path!r} is not canonical "
                f"repository-relative POSIX; expected {canonical!r}"
            )
        canonical_paths[role] = resolved
    core_entry = entries_by_role.get("case090_clean_core")
    memory_entry = entries_by_role.get("case090_mpi_memory")
    if isinstance(core_entry, Mapping) and isinstance(memory_entry, Mapping):
        if canonical_paths.get("case090_clean_core") != canonical_paths.get(
            "case090_mpi_memory"
        ):
            problems.append(
                "Case090 core and MPI-memory roles must reference the same "
                "authoritative aggregate"
            )
    roles_by_path: dict[Path, set[Any]] = {}
    for entry in entries:
        if isinstance(entry, Mapping):
            role = entry.get("role")
            resolved = canonical_paths.get(role)
            if resolved is not None:
                roles_by_path.setdefault(resolved, set()).add(role)
    allowed_shared_roles = {"case090_clean_core", "case090_mpi_memory"}
    for path, path_roles in roles_by_path.items():
        if len(path_roles) > 1 and path_roles != allowed_shared_roles:
            problems.append(
                f"formal manifest reuses evidence path {path!r} for unrelated roles"
            )
    return problems


def _all_true(mapping: Any) -> bool:
    return isinstance(mapping, Mapping) and bool(mapping) and all(
        value is True for value in mapping.values()
    )


def _semantic_problems(role: str, payload: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    identity = payload.get("identity", {})
    if role == "case090_clean_core":
        if payload.get("all_core_gates_passed") is not True:
            problems.append("Case090 core gates are not all true")
        if not isinstance(identity, Mapping) or identity.get("is_solver_pass") is not True:
            problems.append("Case090 clean core does not identify a solver pass")
        if payload.get("failures") != []:
            problems.append("Case090 clean core contains failures")
    elif role == "case090_mpi_memory":
        memory = payload.get("external_memory_watchdog", {})
        if not isinstance(memory, Mapping):
            problems.append("Case090 external-memory aggregate is missing")
        else:
            if memory.get("all_three_qualified") is not True:
                problems.append("Case090 MPI1/2/4 watchdog summaries are not all qualified")
            evidence = memory.get("summary_evidence_sha256")
            peaks = memory.get("observed_memory_peak_bytes")
            expected_keys = {"mpi1", "mpi2", "mpi4"}
            if not isinstance(evidence, Mapping) or set(evidence) != expected_keys:
                problems.append("Case090 watchdog evidence does not cover MPI1/2/4 exactly")
            if not isinstance(peaks, Mapping) or set(peaks) != expected_keys:
                problems.append("Case090 watchdog peaks do not cover MPI1/2/4 exactly")
    elif role == "qep_order_study":
        if payload.get("status") == "qep_component_aggregate_qualified":
            full = qep_full_aggregate_gate(
                payload, require_evidence_descriptors=True
            )
            if full.get("pass") is not True:
                problems.append(
                    "QEP qualified aggregate lacks full 36-record closure: "
                    f"{full.get('failures')!r}"
                )
        else:
            partial = qep_p3_only_partial_aggregate_gate(
                payload, require_evidence_descriptors=True
            )
            if partial.get("pass") is not True:
                problems.append(
                    "QEP not-qualified aggregate is not the narrow p4-only "
                    f"partial: {partial.get('failures')!r}"
                )
        for index, row in enumerate(payload.get("source_records", [])):
            row = row if isinstance(row, Mapping) else {}
            solver = row.get("solver_record")
            solver = solver if isinstance(solver, Mapping) else {}
            if not _portable_repo_path(row.get("path")):
                problems.append(
                    f"QEP source record {index} watchdog path is not portable"
                )
            if not _portable_repo_path(solver.get("path")):
                problems.append(
                    f"QEP source record {index} solver path is not portable"
                )
    elif role in {
        "qep_mpi2_timeout_negative",
        "qep_mpi4_timeout_negative",
    }:
        expected_mpi = 2 if role.startswith("qep_mpi2") else 4
        source_gate = payload.get("source_gate", {})
        resource_gate = payload.get("resource_authority", {})
        launch_gate = payload.get("launch_gate", {})
        return_code = payload.get("return_code")
        checks = {
            "watchdog_identity": payload.get("schema_version")
            == "task033.memory-watchdog.v2"
            and payload.get("target") == "qep",
            "formal_not_pass": payload.get("status") == "formal_not_pass"
            and payload.get("formal_pass") is False
            and payload.get("numeric_pass") is False,
            "nonzero_integer_return_code": isinstance(return_code, int)
            and not isinstance(return_code, bool)
            and return_code != 0,
            "wall_timeout_only": payload.get("terminated_for_timeout") is True
            and payload.get("terminated_for_memory") is False
            and payload.get("terminated_for_authority_unreadable") is False,
            "expected_mpi_size": _command_mpi_size(payload.get("command"))
            == expected_mpi,
            "memory_authority": payload.get("memory_authority_pass") is True
            and payload.get("no_swap") is True
            and isinstance(resource_gate, Mapping)
            and isinstance(resource_gate.get("gate"), Mapping)
            and resource_gate["gate"].get("pass") is True,
            "source_gate": isinstance(source_gate, Mapping)
            and source_gate.get("pass") is True
            and _all_true(source_gate.get("checks")),
            "launch_gate": isinstance(launch_gate, Mapping)
            and launch_gate.get("pass") is True,
        }
        problems.extend(
            f"{role} failed {name}" for name, passed in checks.items() if not passed
        )
    elif role in {"augmented_vs_minimal_p1", "augmented_vs_minimal_p3"}:
        expected_degree = 1 if role.endswith("p1") else 3
        source_gate = payload.get("source_gate", {})
        resource_gate = payload.get("resource_authority", {})
        launch_gate = payload.get("launch_gate", {})
        measurements = payload.get("measurements", {})
        case = measurements.get("case", {}) if isinstance(measurements, Mapping) else {}
        hybrid = (
            measurements.get("hybrid_system", {})
            if isinstance(measurements, Mapping)
            else {}
        )
        comparison = (
            measurements.get("modal_schur_comparison", {})
            if isinstance(measurements, Mapping)
            else {}
        )
        expected_modes = 120 if expected_degree == 1 else 160
        formal_watchdog_pass = bool(
            (
                payload.get("status") == "measured_shard_pass"
                and payload.get("formal_pass") is True
                and payload.get("numeric_pass") is True
            )
            or (
                expected_degree == 1
                and _controlled_physical_truncation_negative(payload)
            )
        )
        checks = {
            "watchdog_identity": payload.get("schema_version")
            == "task033.memory-watchdog.v2"
            and payload.get("target") == "hybrid",
            "formal_watchdog_pass_or_controlled_p1_physical_negative": (
                formal_watchdog_pass
            ),
            "no_termination_or_swap": payload.get("terminated_for_timeout")
            is False
            and payload.get("terminated_for_memory") is False
            and payload.get("terminated_for_authority_unreadable") is False
            and payload.get("no_swap") is True,
            "source_resource_launch": isinstance(source_gate, Mapping)
            and source_gate.get("pass") is True
            and _all_true(source_gate.get("checks"))
            and payload.get("memory_authority_pass") is True
            and isinstance(resource_gate, Mapping)
            and isinstance(resource_gate.get("gate"), Mapping)
            and resource_gate["gate"].get("pass") is True
            and isinstance(launch_gate, Mapping)
            and launch_gate.get("pass") is True,
            "case_identity": isinstance(case, Mapping)
            and case.get("degree") == expected_degree
            and case.get("h_nm") == 5.0
            and _command_mpi_size(payload.get("command")) == 4
            and payload.get("requested_modes") == expected_modes
            and payload.get("candidate_modes") == 2 * expected_modes,
            "augmented_primary": isinstance(hybrid, Mapping)
            and hybrid.get("primary_solver_path") == "augmented",
            "minimal_comparison": isinstance(comparison, Mapping)
            and comparison.get("status") == "pass"
            and comparison.get("comparison_solver_path")
            == "modal-schur-memory-minimal"
            and comparison.get("comparison_solver_path_argument") == "minimal",
            "sparse_comparison": isinstance(comparison, Mapping)
            and comparison.get("dense_interface_square_formed") is False,
            "comparison_gates": isinstance(comparison, Mapping)
            and _all_true(comparison.get("gates")),
        }
        problems.extend(
            f"{role} failed {name}" for name, passed in checks.items() if not passed
        )
    elif role.startswith("hybrid_funnel_") or role.startswith("interface_buffer_") and role != "interface_buffer_tradeoff":
        qualification = payload.get("qualification", {})
        case = payload.get("case", {})
        p1_capacity_negative = bool(
            role == "hybrid_funnel_p1"
            and is_controlled_p1_h5_capacity_funnel(payload)
        )
        if (
            not isinstance(identity, Mapping)
            or identity.get("is_solver_pass") is not True
        ) and not p1_capacity_negative:
            problems.append("Hybrid funnel is neither qualified nor the p1/h5 capacity negative")
        if (
            not isinstance(qualification, Mapping)
            or qualification.get("mode_count_converged") is not True
        ) and not p1_capacity_negative:
            problems.append("Hybrid funnel mode count did not converge")
        if role == "hybrid_funnel_p1" and case.get("degree") != 1:
            problems.append("p1 funnel role does not contain degree=1")
        if role == "hybrid_funnel_p3" and case.get("degree") != 3:
            problems.append("p3 funnel role does not contain degree=3")
        expected_buffers = {
            "interface_buffer_10": (10.0, 110.0),
            "interface_buffer_7p5": (7.5, 112.5),
            "interface_buffer_5": (5.0, 115.0),
            "interface_buffer_2p5": (2.5, 117.5),
        }
        if role in expected_buffers:
            bottom, top = expected_buffers[role]
            if case.get("bottom_interface_nm") != bottom or case.get("top_interface_nm") != top:
                problems.append(f"{role} contains the wrong interface positions")
    elif role == "uniform_p_h_matrix":
        if len(payload.get("entries", [])) != 20:
            problems.append("uniform p/h matrix must contain exactly 20 entries")
        resource = payload.get("resource_matrix")
        resource = resource if isinstance(resource, Mapping) else {}
        if not _portable_repo_path(resource.get("path")):
            problems.append("uniform p/h resource-matrix path is not portable")
        for index, row in enumerate(payload.get("entries", [])):
            if not isinstance(row, Mapping):
                continue
            source_path = row.get("source_record_path")
            if source_path is not None and not _portable_repo_path(source_path):
                problems.append(
                    f"uniform p/h entry {index} source path is not portable"
                )
    elif role in {"adaptive_p2_h5", "adaptive_p2_h3"}:
        expected_h = 5.0 if role.endswith("h5") else 3.0
        if payload.get("plan", {}).get("reference_h_nm") != expected_h:
            problems.append(f"{role} has the wrong reference_h_nm")
        if payload.get("same_accuracy_qualification", {}).get("mandatory_gate_pass") is not True:
            problems.append(f"{role} lacks mandatory same-accuracy qualification")
        measured = payload.get("measured_evidence")
        measured = measured if isinstance(measured, Mapping) else {}
        for name in ("graded_plan", "reference", "candidate"):
            descriptor = measured.get(name)
            descriptor = descriptor if isinstance(descriptor, Mapping) else {}
            if not _portable_repo_path(descriptor.get("path")):
                problems.append(f"{role} {name} path is not portable")
            selected = descriptor.get("selected_watchdog_path")
            if name != "graded_plan" and not _portable_repo_path(selected):
                problems.append(
                    f"{role} {name} selected-watchdog path is not portable"
                )
    elif role == "interface_buffer_tradeoff":
        observed = {
            float(row.get("buffer_nm"))
            for row in payload.get("candidates", [])
            if isinstance(row, Mapping) and row.get("buffer_nm") is not None
        }
        if observed != {10.0, 7.5, 5.0, 2.5}:
            problems.append("buffer tradeoff does not contain all four required buffers")
        for index, row in enumerate(payload.get("candidates", [])):
            row = row if isinstance(row, Mapping) else {}
            if not _portable_repo_path(row.get("source_record_path")):
                problems.append(
                    f"buffer tradeoff candidate {index} source path is not portable"
                )
            if not _portable_repo_path(row.get("selected_watchdog_path")):
                problems.append(
                    f"buffer tradeoff candidate {index} watchdog path is not portable"
                )
    elif role == "equal_accuracy":
        identity = payload.get("identity", {})
        if (
            not isinstance(identity, Mapping)
            or identity.get("all_qualified_inputs_same_clean_sha") is not True
        ):
            problems.append("equal-accuracy inputs do not attest one clean SHA")
        if payload.get("payload_sha256") != _canonical_payload_sha256(payload):
            problems.append("equal-accuracy canonical payload SHA256 is invalid")
    elif role == "variable_p_capability_audit":
        decision = payload.get("decision", {})
        if decision.get("implement_bespoke_arbitrary_variable_p_constraints") is not False:
            problems.append("variable-p audit attempts a bespoke constraint implementation")
    elif role == "one_tib_projection":
        result = payload.get("result", {})
        if result.get("classification") is None:
            problems.append("1 TiB projection has no measured-compression classification")
    elif role == "final_outcome":
        overall = payload.get("classifications", {}).get("overall", {})
        disposition = overall.get("disposition") if isinstance(overall, Mapping) else None
        if disposition not in {"pass", "partial"}:
            problems.append("final outcome is failed rather than pass/partial")
        if (
            disposition in {"pass", "partial"}
            and overall.get("classification") != f"task033_{disposition}"
        ):
            problems.append("final outcome disposition/classification disagree")
        if payload.get("payload_sha256") != _canonical_payload_sha256(payload):
            problems.append("final outcome canonical payload SHA256 is invalid")
    return problems


def final_outcome_manifest_closure_problems(
    payload: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    manifest_sha: str,
) -> list[str]:
    """Bind every final-outcome input descriptor to one formal manifest role."""

    problems: list[str] = []
    raw_descriptors = payload.get("input_evidence")
    if not isinstance(raw_descriptors, list) or not all(
        isinstance(item, Mapping) for item in raw_descriptors
    ):
        return ["final outcome input_evidence must be an array of objects"]
    expected_input_roles = tuple(
        input_role for input_role, _ in FINAL_OUTCOME_INPUT_ROLE_MAP
    )
    observed_input_roles = tuple(item.get("role") for item in raw_descriptors)
    if observed_input_roles != expected_input_roles:
        problems.append(
            "final outcome input_evidence does not match the frozen 13-role order"
        )
    if len(set(observed_input_roles)) != len(observed_input_roles):
        problems.append("final outcome input_evidence contains duplicate roles")
    descriptors = {
        str(item.get("role")): item
        for item in raw_descriptors
        if isinstance(item.get("role"), str)
    }
    entries_by_role = {
        str(item.get("role")): item
        for item in entries
        if isinstance(item, Mapping) and isinstance(item.get("role"), str)
    }
    for input_role, manifest_role in FINAL_OUTCOME_INPUT_ROLE_MAP:
        descriptor = descriptors.get(input_role)
        entry = entries_by_role.get(manifest_role)
        if descriptor is None or entry is None:
            problems.append(
                f"final outcome closure lacks {input_role}->{manifest_role}"
            )
            continue
        descriptor_path = descriptor.get("path")
        if not _portable_repo_path(descriptor_path):
            problems.append(
                f"final outcome {input_role} path is not portable repository-relative POSIX"
            )
        if descriptor_path != entry.get("path"):
            problems.append(
                f"final outcome {input_role} path differs from manifest role {manifest_role}"
            )
        if descriptor.get("sha256") != entry.get("sha256"):
            problems.append(
                f"final outcome {input_role} SHA256 differs from manifest role {manifest_role}"
            )
        if descriptor.get("source_commit_sha") != manifest_sha:
            problems.append(
                f"final outcome {input_role} source SHA differs from manifest SHA"
            )
        if descriptor.get("source_clean") is not True:
            problems.append(f"final outcome {input_role} is not source-clean")
    source = payload.get("formal_source", {})
    if not isinstance(source, Mapping) or source.get("commit_sha") != manifest_sha:
        problems.append("final outcome formal source SHA differs from manifest SHA")
    if not isinstance(source, Mapping) or source.get("tracked_source_clean") is not True:
        problems.append("final outcome formal source is not tracked-source-clean")
    return problems


def _check_final_outcome_manifest_closure(
    *,
    root: Path,
    final_entry: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    manifest_sha: str,
) -> dict[str, Any]:
    payload = _load_json(_repo_path(root, str(final_entry.get("path"))))
    problems = final_outcome_manifest_closure_problems(
        payload, entries, manifest_sha
    )
    if problems:
        raise EvidenceCheckError("; ".join(problems))
    return {
        "input_role_count": len(FINAL_OUTCOME_INPUT_ROLE_MAP),
        "final_outcome_sha256": final_entry.get("sha256"),
    }


def _check_formal_entry(
    root: Path,
    entry: Mapping[str, Any],
    manifest_sha: str,
) -> dict[str, Any]:
    role = entry.get("role")
    if role not in ROLE_SPECS:
        raise EvidenceCheckError(f"unknown formal evidence role {role!r}")
    spec = ROLE_SPECS[role]
    if entry.get("schema_ref") != spec.schema_ref:
        raise EvidenceCheckError(
            f"{role} must use frozen schema_ref {spec.schema_ref!r}"
        )
    binding = (
        str(entry.get("source_sha_pointer")),
        str(entry.get("source_clean_pointer")),
        entry.get("source_clean_expected"),
    )
    if binding not in ALLOWED_SOURCE_BINDINGS:
        raise EvidenceCheckError(f"{role} uses an unapproved source binding {binding!r}")
    evidence_path = _repo_path(root, str(entry.get("path")))
    expected_digest = str(entry.get("sha256", ""))
    actual_digest = _sha256(evidence_path)
    if actual_digest != expected_digest:
        raise EvidenceCheckError(
            f"{role} SHA256 mismatch: manifest={expected_digest}, actual={actual_digest}"
        )
    payload = _load_json(evidence_path)
    _validate_instance(root, payload, spec.schema_ref)
    status = _pointer(payload, spec.status_pointer)
    if status not in spec.accepted_statuses:
        raise EvidenceCheckError(
            f"{role} has unaccepted status {status!r}; expected {spec.accepted_statuses!r}"
        )
    source_sha = _pointer(payload, binding[0])
    clean_value = _pointer(payload, binding[1])
    if source_sha != manifest_sha:
        raise EvidenceCheckError(
            f"{role} source SHA {source_sha!r} differs from manifest SHA {manifest_sha!r}"
        )
    if clean_value is not binding[2]:
        raise EvidenceCheckError(
            f"{role} source-clean value {clean_value!r} differs from required {binding[2]!r}"
        )
    semantic = _semantic_problems(role, payload)
    if semantic:
        raise EvidenceCheckError(f"{role} semantic checks failed: {'; '.join(semantic)}")
    if role == "qep_order_study":
        files = qep_source_record_file_gate(payload, root=root)
        if files.get("pass") is not True:
            raise EvidenceCheckError(
                "qep_order_study source-record files failed independent hash/"
                f"binding checks: {files.get('failures')!r}"
            )
    return {
        "role": role,
        "path": evidence_path.relative_to(root).as_posix(),
        "sha256": actual_digest,
        "schema_ref": spec.schema_ref,
        "accepted_status": status,
        "clean_source_sha": source_sha,
    }


def check_formal_evidence(
    manifest_path: Path | str,
    root: Path = ROOT,
) -> list[dict[str, Any]]:
    """Verify a complete formal role manifest and every referenced JSON file."""

    resolved_root = Path(root).resolve()
    path = _manifest_path(resolved_root, manifest_path)
    manifest = _load_json(path)
    try:
        report_manifest_path = path.relative_to(resolved_root).as_posix()
    except ValueError:
        report_manifest_path = str(path)
    checks = [
        _run_check(
            "formal_manifest_schema",
            lambda: (
                _validate_instance(resolved_root, manifest, FORMAL_SCHEMA_POSIX)
                or {
                    "path": report_manifest_path,
                    "sha256": _sha256(path),
                    "status": manifest.get("status"),
                }
            ),
        )
    ]
    structure_problems = _manifest_structure_problems(
        manifest, root=resolved_root
    )
    checks.append(
        {
            "name": "formal_manifest_role_inventory",
            "status": "invalid" if structure_problems else "verified",
            "details": {"required_role_count": len(REQUIRED_FORMAL_ROLES)},
            "problems": structure_problems,
        }
    )
    if structure_problems:
        return checks
    manifest_sha = manifest.get("clean_source_sha")
    if not isinstance(manifest_sha, str):
        checks.append(
            {
                "name": "formal_manifest_clean_source_sha",
                "status": "invalid",
                "details": {},
                "problems": ["formal manifest clean_source_sha is missing"],
            }
        )
        return checks
    entries = {entry["role"]: entry for entry in manifest["entries"]}
    checks.extend(
        _run_check(
            f"formal_role:{role}",
            lambda role=role: _check_formal_entry(
                resolved_root, entries[role], manifest_sha
            ),
        )
        for role in REQUIRED_FORMAL_ROLES
    )
    checks.append(
        _run_check(
            "formal_final_outcome_input_closure",
            lambda: _check_final_outcome_manifest_closure(
                root=resolved_root,
                final_entry=entries["final_outcome"],
                entries=manifest["entries"],
                manifest_sha=manifest_sha,
            ),
        )
    )
    return checks


def _report(mode: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    problems = [
        f"{check['name']}: {problem}"
        for check in checks
        for problem in check.get("problems", [])
    ]
    verified = not problems and all(check.get("status") == "verified" for check in checks)
    return {
        "schema_version": "task033.evidence-checker-report.v1",
        "record_type": "task033_evidence_verification_report",
        "mode": mode,
        "status": "evidence_verified" if verified else "fail_closed",
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "claims_task033_complete": False,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "verified": verified,
        "checks": checks,
        "problems": problems,
        "interpretation": (
            "Evidence verification checks integrity and frozen contracts only; "
            "it is not a solver or physical qualification record."
        ),
    }


def check_task033(
    *,
    root: Path = ROOT,
    formal_manifest: Path | str | None = None,
    require_formal: bool = False,
) -> dict[str, Any]:
    """Run planning checks and, when requested, the formal fail-closed checks."""

    planning = check_planning_evidence(root)
    formal_requested = require_formal or formal_manifest is not None
    if not formal_requested:
        return _report("planning", planning)
    selected = formal_manifest or DEFAULT_FORMAL_MANIFEST
    formal = check_formal_evidence(selected, root)
    return _report("formal", [*planning, *formal])


__all__ = [
    "DEFAULT_FORMAL_MANIFEST",
    "FINAL_OUTCOME_INPUT_ROLE_MAP",
    "FORMAL_SCHEMA",
    "REQUIRED_FORMAL_ROLES",
    "ROLE_SPECS",
    "check_formal_evidence",
    "check_planning_evidence",
    "check_task033",
    "final_outcome_manifest_closure_problems",
]
