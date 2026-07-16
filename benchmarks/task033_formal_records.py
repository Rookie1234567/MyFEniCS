"""Read-only, fail-closed builders for Task033 Case091 formal records.

The functions in this module only consume existing JSON evidence and return a
new JSON-compatible mapping.  They never run a solver, edit an input record,
or promote planning data to a physical pass.  Callers decide where to persist
the returned object; the companion CLI writes JSON to stdout only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from benchmarks.task033_evidence_checker import (
    ALLOWED_SOURCE_BINDINGS,
    REQUIRED_FORMAL_ROLES,
    ROLE_SPECS,
    _semantic_problems as checker_semantic_problems,
    final_outcome_manifest_closure_problems,
)
from benchmarks.task033_qep_qualification import (
    aggregate_qep_shards,
    qep_full_aggregate_gate,
    qep_p3_only_partial_aggregate_gate,
    qep_p4_controlled_negative_gate,
    source_identity_gate,
)
from benchmarks.task033_watchdog_launch import FORMAL_FUNNEL_MODES
from src.geometry.task033_periodic_graded_mesh import (
    PeriodicGradedHybridPlan,
    Task033Stage4Geometry,
    build_adaptive_planning_record,
)


ROOT = Path(__file__).resolve().parents[1]
CASE091 = Path("benchmarks/cases/091_hybrid_hp_adaptivity_feasibility")
FUNNEL_SCHEMA = (CASE091 / "hybrid_funnel_schema.json").as_posix()
FORMAL_SCHEMA = (CASE091 / "formal_evidence_manifest_schema.json").as_posix()
PUBLICATION_SCHEMA = (
    CASE091 / "formal_publication_descriptor_schema.json"
).as_posix()
UNIFORM_SCHEMA = f"{FORMAL_SCHEMA}#/$defs/uniformMatrixEvidence"
ADAPTIVE_SCHEMA = f"{FORMAL_SCHEMA}#/$defs/adaptiveEvidence"
TRADEOFF_SCHEMA = f"{FORMAL_SCHEMA}#/$defs/bufferTradeoffEvidence"
QEP_SCHEMA = Path("benchmarks/task033_qep_qualification_schema.json").as_posix()

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SELECTED_PLANE_FIELD_RELATIVE_MAX = 5.0e-3
EXPECTED_DEGREES = (1, 2, 3, 4)
EXPECTED_H_NM = (5.0, 3.0, 2.5, 2.0, 1.5)
BUFFER_INTERFACES: Mapping[float, tuple[float, float]] = {
    10.0: (10.0, 110.0),
    7.5: (7.5, 112.5),
    5.0: (5.0, 115.0),
    2.5: (2.5, 117.5),
}
ANCHOR_REQUALIFICATION_REQUIRED_CHECKS = (
    "explicit_task033_requalification_flag",
    "task032_reuse_anchor_is_the_selected_entry",
    "exact_p2_h3_anchor",
    "primary_uniform_10_110_minimal_path",
    "current_full_source_sha_valid",
    "complete_nonignored_worktree_clean",
    "canonical_resource_matrix",
    "canonical_resource_matrix_tracked",
    "external_watchdog_is_launch_authority",
    "one_required_funnel_mode_selected",
    "candidate_pool_is_twice_requested_modes",
)
APPROVED_SOURCE_BINDINGS: tuple[tuple[str, str, bool], ...] = (
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
)


class FormalRecordError(RuntimeError):
    """Raised when supplied evidence cannot support a formal record."""


@dataclass(frozen=True)
class EvidenceFile:
    """One immutable JSON evidence object and its byte-level identity."""

    path: Path
    payload: dict[str, Any]
    sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise FormalRecordError(f"cannot hash evidence file {path}: {exc}") from exc
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


def formal_publication_descriptor_problems(
    payload: Mapping[str, Any],
) -> list[str]:
    """Recompute the portable-path and self-hash publication semantics."""

    problems: list[str] = []
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return ["publication artifacts must be one object"]
    for role in ("formal_manifest", "formal_verification", "final_outcome"):
        descriptor = artifacts.get(role)
        descriptor = descriptor if isinstance(descriptor, Mapping) else {}
        path = descriptor.get("path")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or (
                len(path) >= 2
                and path[0].isalpha()
                and path[1] == ":"
            )
            or Path(path).is_absolute()
            or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            problems.append(
                f"publication {role} path is not portable repository-relative POSIX"
            )
    if payload.get("payload_sha256") != _canonical_payload_sha256(payload):
        problems.append("publication canonical payload SHA256 is invalid")
    return problems


def _repo_relative(path: Path | str, *, root: Path) -> tuple[Path, str]:
    """Resolve one path inside ``root`` and return its portable descriptor."""

    requested = Path(path)
    resolved = (
        requested.resolve()
        if requested.is_absolute()
        else (root / requested).resolve()
    )
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise FormalRecordError(
            f"formal evidence path escapes repository root: {path}"
        ) from exc
    return resolved, relative.as_posix()


def _read_json(path: Path | str) -> EvidenceFile:
    resolved = Path(path).resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalRecordError(f"cannot read JSON evidence {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FormalRecordError(f"{resolved} must contain one JSON object")
    return EvidenceFile(resolved, payload, _sha256(resolved))


def _pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise FormalRecordError(f"invalid JSON pointer {pointer!r}")
    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                raise FormalRecordError(
                    f"JSON pointer {pointer!r} is missing component {token!r}"
                )
            current = current[token]
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            try:
                current = current[int(token)]
            except (ValueError, IndexError) as exc:
                raise FormalRecordError(
                    f"JSON pointer {pointer!r} has invalid array component {token!r}"
                ) from exc
        else:
            raise FormalRecordError(
                f"JSON pointer {pointer!r} traverses a scalar at {token!r}"
            )
    return current


def _try_pointer(document: Mapping[str, Any], pointer: str) -> tuple[bool, Any]:
    try:
        return True, _pointer(document, pointer)
    except FormalRecordError:
        return False, None


def _schema_path(root: Path, schema_ref: str) -> tuple[Path, str]:
    path_text, separator, fragment = schema_ref.partition("#")
    raw = Path(path_text)
    path = raw if raw.is_absolute() else root / raw
    return path.resolve(), fragment if separator else ""


def _validate_payload(
    payload: Mapping[str, Any], schema_ref: str, *, root: Path = ROOT
) -> None:
    schema_path, fragment = _schema_path(root.resolve(), schema_ref)
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalRecordError(f"cannot read JSON schema {schema_path}: {exc}") from exc
    if not isinstance(schema, dict):
        raise FormalRecordError(f"JSON schema {schema_path} is not an object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise FormalRecordError(
            f"invalid JSON schema {schema_path}: {exc.message}"
        ) from exc
    selected: Any = schema
    if fragment:
        selected = _pointer(schema, fragment)
        if not isinstance(selected, Mapping):
            raise FormalRecordError(
                f"schema fragment {schema_ref!r} does not select an object"
            )
    try:
        Draft202012Validator(selected).validate(payload)
    except ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path)
        suffix = f" at /{location}" if location else ""
        raise FormalRecordError(
            f"JSON schema validation failed for {schema_ref}{suffix}: {exc.message}"
        ) from exc


def _full_sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or FULL_SHA_RE.fullmatch(value.lower()) is None:
        raise FormalRecordError(f"{label} must be one full 40-character Git SHA")
    return value.lower()


def _positive_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormalRecordError(f"{label} must be a positive measured number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise FormalRecordError(f"{label} must be a positive measured number")
    return result


def _nonnegative_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormalRecordError(f"{label} must be a non-negative measured number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise FormalRecordError(f"{label} must be a non-negative measured number")
    return result


def _same_source(shas: Sequence[str], *, context: str) -> str:
    unique = {sha.lower() for sha in shas}
    if not unique:
        raise FormalRecordError(f"{context} has no measured clean-source evidence")
    if len(unique) != 1:
        raise FormalRecordError(
            f"{context} mixes clean-source SHAs: {sorted(unique)!r}"
        )
    return next(iter(unique))


def build_qep_order_study(
    record_paths: Sequence[Path | str],
    *,
    mpi_size: int = 1,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Build one QEP h/p aggregate from measured external-watchdog summaries."""

    root = Path(repo_root).resolve()
    files = [
        _read_json(_repo_relative(path, root=root)[0]) for path in record_paths
    ]
    if not files:
        raise FormalRecordError("QEP order study requires measured shard files")
    source_shas: list[str] = []
    shards: list[Mapping[str, Any]] = []
    source_records: list[dict[str, Any]] = []
    negative_evidence: dict[tuple[str, int, float, int], dict[str, Any]] = {}
    for item in files:
        shard, source_sha, disposition, solver_descriptor = (
            _validated_qep_watchdog_summary(
                item, mpi_size=mpi_size, repo_root=root
            )
        )
        candidate = shard.get("candidate")
        if not isinstance(candidate, Mapping) or candidate.get("mpi_size") != mpi_size:
            raise FormalRecordError(
                f"QEP shard {item.path} is not bound to requested mpi_size={mpi_size}"
            )
        provenance = shard.get("provenance")
        gate = source_identity_gate(
            provenance if isinstance(provenance, Mapping) else None
        )
        if gate.get("pass") is not True:
            raise FormalRecordError(
                f"QEP shard {item.path} failed clean-source gate: "
                f"{gate.get('failures')!r}"
            )
        worker_sha = _full_sha(gate.get("head_sha"), label=str(item.path))
        if worker_sha != source_sha:
            raise FormalRecordError(
                f"QEP watchdog {item.path} and embedded worker record use different SHAs"
            )
        source_shas.append(source_sha)
        shards.append(shard)
        item_relative = _repo_relative(item.path, root=root)[1]
        source_record = {
            "candidate": {
                "material_kind": str(candidate.get("material_kind")),
                "degree": int(candidate.get("degree")),
                "h_nm": float(candidate.get("h_nm")),
                "mpi_size": int(candidate.get("mpi_size")),
            },
            "path": item_relative,
            "sha256": item.sha256,
            "disposition": disposition,
            "solver_record": solver_descriptor,
        }
        source_records.append(source_record)
        if disposition == "controlled_numeric_negative":
            key = (
                str(candidate.get("material_kind")),
                int(candidate.get("degree")),
                float(candidate.get("h_nm")),
                int(candidate.get("mpi_size")),
            )
            if key in negative_evidence:
                raise FormalRecordError(
                    f"duplicate controlled QEP negative candidate {key!r}"
                )
            negative_evidence[key] = {
                "watchdog_summary": {
                    "path": item_relative,
                    "sha256": item.sha256,
                },
                "solver_record": solver_descriptor,
                "watchdog_return_code": 2,
            }
    source_sha = _same_source(source_shas, context="QEP order study")
    aggregate = aggregate_qep_shards(
        shards,
        mpi_size=mpi_size,
        allow_p4_controlled_negative=True,
    )
    observations = aggregate.get("negative_observations")
    if isinstance(observations, list):
        for observation in observations:
            candidate = observation.get("candidate") if isinstance(observation, dict) else None
            candidate = candidate if isinstance(candidate, Mapping) else {}
            key = (
                str(candidate.get("material_kind")),
                int(candidate.get("degree")),
                float(candidate.get("h_nm")),
                int(candidate.get("mpi_size")),
            )
            evidence = negative_evidence.get(key)
            if evidence is None:
                raise FormalRecordError(
                    f"controlled QEP negative {key!r} lacks outer evidence"
                )
            observation["evidence"] = evidence
    accepted_partial = (
        aggregate.get("qualification_classification") == "partial_p3_only"
        and qep_p3_only_partial_aggregate_gate(
            {
                **aggregate,
                "source_records": source_records,
                "formal_source": {
                    "commit_sha": source_sha,
                    "tracked_source_clean": True,
                },
            },
            require_evidence_descriptors=True,
        ).get("pass")
        is True
    )
    if (
        aggregate.get("status") != "qep_component_aggregate_qualified"
        and not accepted_partial
    ):
        false_gates = [
            key for key, value in (aggregate.get("gates") or {}).items() if value is not True
        ]
        raise FormalRecordError(
            "native QEP aggregate did not qualify; "
            f"false_gates={false_gates!r}, "
            f"missing={aggregate.get('missing_candidates')!r}, "
            f"duplicates={aggregate.get('duplicate_count')!r}"
        )
    result = {
        **aggregate,
        "formal_source": {
            "commit_sha": source_sha,
            "tracked_source_clean": True,
        },
        "source_records": source_records,
    }
    if result.get("status") == "qep_component_aggregate_qualified":
        full_gate = qep_full_aggregate_gate(
            result, require_evidence_descriptors=True
        )
        if full_gate.get("pass") is not True:
            raise FormalRecordError(
                "qualified QEP aggregate failed full evidence closure: "
                f"{full_gate.get('failures')!r}"
            )
    else:
        partial_gate = qep_p3_only_partial_aggregate_gate(
            result, require_evidence_descriptors=True
        )
        if partial_gate.get("pass") is not True:
            raise FormalRecordError(
                "partial QEP aggregate failed p3-only evidence closure: "
                f"{partial_gate.get('failures')!r}"
            )
    _validate_payload(result, QEP_SCHEMA)
    return result


def _validated_funnel(item: EvidenceFile) -> tuple[Mapping[str, Any], str]:
    _validate_payload(item.payload, FUNNEL_SCHEMA)
    identity = item.payload.get("identity")
    qualification = item.payload.get("qualification")
    if not isinstance(identity, Mapping) or not isinstance(qualification, Mapping):
        raise FormalRecordError(f"funnel {item.path} lacks identity/qualification")
    conditions = {
        "status_qualified": item.payload.get("status") == "qualified",
        "solver_pass": identity.get("is_solver_pass") is True,
        "tracked_source_clean": identity.get("tracked_source_clean") is True,
        "mode_count_converged": qualification.get("mode_count_converged") is True,
        "all_sources_same_clean_sha": (
            qualification.get("all_sources_same_clean_sha") is True
        ),
        "all_external_watchdogs_pass": (
            qualification.get("all_external_watchdogs_pass") is True
        ),
        "no_failures": item.payload.get("failures") == [],
    }
    failed = [key for key, passed in conditions.items() if not passed]
    if failed:
        raise FormalRecordError(
            f"funnel {item.path} is not formal-qualified: {failed!r}"
        )
    source_sha = _full_sha(
        identity.get("source_commit_full_sha"), label=f"funnel {item.path} source"
    )
    return item.payload, source_sha


def _anchor_source(payload: Mapping[str, Any], *, path: Path) -> str:
    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise FormalRecordError(f"Task032 anchor {path} lacks source evidence")
    sha = _full_sha(source.get("commit_sha"), label=f"Task032 anchor {path} source")
    verified = source.get("verified_clean_sha")
    conditions = {
        "git_clean": source.get("git_dirty") is False,
        "tracked_source_clean": source.get("tracked_source_dirty") is False,
        "verified_clean_sha_matches": (
            isinstance(verified, str) and verified.lower() == sha
        ),
    }
    failed = [key for key, passed in conditions.items() if not passed]
    if failed:
        raise FormalRecordError(
            f"Task032 anchor {path} failed clean-source checks: {failed!r}"
        )
    return sha


def _validate_task032_anchor(
    item: EvidenceFile, resource_entry: Mapping[str, Any]
) -> str:
    measured = resource_entry.get("measured_anchor")
    if not isinstance(measured, Mapping):
        raise FormalRecordError(
            f"resource row {resource_entry.get('matrix_key')!r} lacks measured_anchor"
        )
    conditions = {
        "expected_decision": (
            resource_entry.get("planning_decision") == "reuse_task032_clean_anchor"
            and resource_entry.get("launch_decision") == "reuse_task032_clean_anchor"
        ),
        "measured_identity": measured.get("data_identity") == "measured",
        "degree_matches": measured.get("degree") == resource_entry.get("degree") == 2,
        "h_matches": measured.get("h_nm") == resource_entry.get("h_nm"),
        "benchmark_identity": (
            item.payload.get("benchmark_id")
            == "task032_external_simultaneous_memory_forensics"
        ),
        "numeric_pass": item.payload.get("numeric_pass") is True,
        "return_code_zero": item.payload.get("return_code") == 0,
        "no_swap": item.payload.get("no_swap") is True,
        "anchor_h_matches": item.payload.get("h_nm") == resource_entry.get("h_nm"),
        "mode_count_matches": (
            item.payload.get("requested_modes_per_direction")
            == measured.get("modes_per_direction")
        ),
    }
    failed = [key for key, passed in conditions.items() if not passed]
    if failed:
        raise FormalRecordError(
            f"Task032 anchor {item.path} is not reusable for "
            f"{resource_entry.get('matrix_key')!r}: {failed!r}"
        )
    return _anchor_source(item.payload, path=item.path)


def _validate_resource_matrix(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    identity = payload.get("identity")
    entries = payload.get("entries")
    if payload.get("schema_version") != 2 or not isinstance(entries, list):
        raise FormalRecordError("resource matrix must be the Task033 schema-v2 JSON record")
    if not isinstance(identity, Mapping):
        raise FormalRecordError("resource matrix identity is missing")
    if identity.get("is_pde_run") is not False or identity.get("is_solver_pass") is not False:
        raise FormalRecordError("resource matrix must remain a planning-only record")
    if len(entries) != 20 or not all(isinstance(row, Mapping) for row in entries):
        raise FormalRecordError("resource matrix must contain exactly 20 object rows")
    keys = [str(row.get("matrix_key")) for row in entries]
    expected_keys = {
        f"p{degree}_h{str(h_nm).replace('.', 'p').removesuffix('p0')}"
        for degree in EXPECTED_DEGREES
        for h_nm in EXPECTED_H_NM
    }
    if len(set(keys)) != 20 or set(keys) != expected_keys:
        raise FormalRecordError("resource matrix does not contain the frozen 4x5 p/h keys")
    observed = {
        (row.get("degree"), float(row.get("h_nm", -1.0))) for row in entries
    }
    expected = {
        (degree, h_nm) for degree in EXPECTED_DEGREES for h_nm in EXPECTED_H_NM
    }
    if observed != expected:
        raise FormalRecordError("resource matrix degree/h coordinates are incomplete")
    return entries


def build_uniform_p_h_matrix(
    resource_matrix_path: Path | str,
    *,
    funnel_paths: Mapping[str, Path | str],
    anchor_paths: Mapping[str, Path | str],
    watchdog_paths: Mapping[str, Path | str] | None = None,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Assemble all 20 p/h dispositions without converting NOT_RUN to pass."""

    root = Path(repo_root).resolve()
    resource_file = _read_json(
        _repo_relative(resource_matrix_path, root=root)[0]
    )
    rows = _validate_resource_matrix(resource_file.payload)
    watchdog_paths = watchdog_paths or {}
    row_keys = {str(row["matrix_key"]) for row in rows}
    supplied_keys = set(funnel_paths) | set(anchor_paths) | set(watchdog_paths)
    unknown = sorted(supplied_keys - row_keys)
    duplicates = sorted(
        (set(funnel_paths) & set(anchor_paths))
        | (set(funnel_paths) & set(watchdog_paths))
        | (set(anchor_paths) & set(watchdog_paths))
    )
    if unknown or duplicates:
        raise FormalRecordError(
            f"uniform matrix evidence bindings are invalid: "
            f"unknown={unknown!r}, duplicate={duplicates!r}"
        )

    source_shas: list[str] = []
    output_rows: list[dict[str, Any]] = []
    for row in rows:
        key = str(row["matrix_key"])
        memory_gated = bool(
            row.get("planning_decision") == "not_run_by_memory_gate"
            and row.get("launch_decision") == "not_run_by_memory_gate"
        )
        has_funnel = key in funnel_paths
        has_anchor = key in anchor_paths
        has_watchdog = key in watchdog_paths
        base = {
            "matrix_key": key,
            "degree": int(row["degree"]),
            "h_nm": float(row["h_nm"]),
            "planning_decision": row.get("planning_decision"),
            "launch_decision": row.get("launch_decision"),
        }
        if memory_gated:
            if has_funnel or has_anchor or has_watchdog:
                raise FormalRecordError(
                    f"{key} is frozen not_run_by_memory_gate but measured evidence was supplied"
                )
            output_rows.append(
                {
                    **base,
                    "evidence_disposition": "not_run_by_memory_gate",
                    "data_identity": "not_run",
                    "source_is_pde_run": False,
                    "source_is_solver_pass": False,
                    "source_record_path": None,
                    "source_record_sha256": None,
                }
            )
            continue
        if not has_funnel and not has_anchor and not has_watchdog:
            raise FormalRecordError(
                f"{key} is not memory-gated and lacks a measured "
                "funnel/watchdog/anchor binding"
            )
        if has_funnel:
            item = _read_json(_repo_relative(funnel_paths[key], root=root)[0])
            funnel, source_sha = _validated_funnel(item)
            case = funnel.get("case")
            if not isinstance(case, Mapping):
                raise FormalRecordError(f"funnel {item.path} lacks a case object")
            if case.get("degree") != row.get("degree") or case.get("h_nm") != row.get("h_nm"):
                raise FormalRecordError(
                    f"funnel {item.path} degree/h does not match resource row {key}"
                )
            source_shas.append(source_sha)
            output_rows.append(
                {
                    **base,
                    "evidence_disposition": "measured_qualified_funnel",
                    "data_identity": "measured",
                    "source_is_pde_run": funnel.get("identity", {}).get(
                        "is_pde_run"
                    ),
                    "source_is_solver_pass": funnel.get("identity", {}).get(
                        "is_solver_pass"
                    ),
                    "source_record_path": _repo_relative(
                        item.path, root=root
                    )[1],
                    "source_record_sha256": item.sha256,
                    "source_status": funnel.get("status"),
                    "source_commit_sha": source_sha,
                    "selected_mode_count_per_direction": (
                        funnel.get("qualification", {}).get(
                            "selected_mode_count_per_direction"
                        )
                    ),
                }
            )
            continue
        if has_watchdog:
            item = _read_json(
                _repo_relative(watchdog_paths[key], root=root)[0]
            )
            measurements, source_sha = _validated_watchdog_summary(
                item, target="hybrid"
            )
            case = measurements.get("case")
            qualification = measurements.get("qualification")
            if not isinstance(case, Mapping) or not isinstance(
                qualification, Mapping
            ):
                raise FormalRecordError(
                    f"Hybrid watchdog {item.path} lacks case/qualification fields"
                )
            if case.get("degree") != row.get("degree") or case.get(
                "h_nm"
            ) != row.get("h_nm"):
                raise FormalRecordError(
                    f"Hybrid watchdog {item.path} degree/h does not match {key}"
                )
            if not (
                qualification.get("integration_pass") is True
                and qualification.get("algebraic_chain_pass") is True
                and qualification.get("physical_field_gates_pass") is True
                and qualification.get("task033_physical_truncation_allowed") is True
            ):
                raise FormalRecordError(
                    f"Hybrid watchdog {item.path} lacks all physical qualification gates"
                )
            if row.get("planning_decision") == "reuse_task032_clean_anchor":
                requalification = item.payload.get("task033_anchor_requalification")
                if not isinstance(requalification, Mapping):
                    raise FormalRecordError(
                        f"{key} requires explicit same-SHA Task033 anchor requalification"
                    )
                checks = requalification.get("checks")
                checks = checks if isinstance(checks, Mapping) else {}
                required_checks_pass = bool(
                    checks
                    and all(
                        checks.get(name) is True
                        for name in ANCHOR_REQUALIFICATION_REQUIRED_CHECKS
                    )
                    and all(value is True for value in checks.values())
                )
                current_requested_mode = requalification.get(
                    "current_requested_mode"
                )
                requalification_ok = bool(
                    requalification.get("requested") is True
                    and requalification.get("allowed") is True
                    and requalification.get("reason")
                    == "Task033 same-SHA formal requalification"
                    and requalification.get("case_identity")
                    == "p2_h3_10_110_primary_modal_schur_memory_minimal"
                    and requalification.get("source_commit_full_sha") == source_sha
                    and current_requested_mode in FORMAL_FUNNEL_MODES
                    and current_requested_mode
                    == case.get("requested_modes_per_direction")
                    and requalification.get("required_complete_mode_funnel")
                    == list(FORMAL_FUNNEL_MODES)
                    and requalification.get(
                        "requires_same_case_and_source_sha_across_funnel"
                    )
                    is True
                    and requalification.get("does_not_replace_task032_anchor") is True
                    and required_checks_pass
                )
                if not requalification_ok:
                    raise FormalRecordError(
                        f"{key} Task033 anchor requalification contract is incomplete"
                    )
            source_shas.append(source_sha)
            hybrid = measurements.get("hybrid_system")
            hybrid = hybrid if isinstance(hybrid, Mapping) else {}
            output_rows.append(
                {
                    **base,
                    "evidence_disposition": "measured_external_watchdog_shard",
                    "data_identity": "measured",
                    "source_formal_pass": item.payload.get("formal_pass"),
                    "source_physical_qualified": item.payload.get(
                        "physical_qualified"
                    ),
                    "source_record_path": _repo_relative(
                        item.path, root=root
                    )[1],
                    "source_record_sha256": item.sha256,
                    "source_status": item.payload.get("status"),
                    "source_commit_sha": source_sha,
                    "selected_mode_count_per_direction": case.get(
                        "requested_modes_per_direction"
                    ),
                    "local_fe_dofs": (
                        None
                        if not isinstance(hybrid.get("bottom_local_fe_dofs"), int)
                        or not isinstance(hybrid.get("top_local_fe_dofs"), int)
                        else hybrid["bottom_local_fe_dofs"]
                        + hybrid["top_local_fe_dofs"]
                    ),
                }
            )
            continue
        item = _read_json(_repo_relative(anchor_paths[key], root=root)[0])
        source_sha = _validate_task032_anchor(item, row)
        source_shas.append(source_sha)
        output_rows.append(
            {
                **base,
                "evidence_disposition": "measured_task032_clean_anchor",
                "data_identity": "measured",
                "source_numeric_pass": item.payload.get("numeric_pass"),
                "source_record_path": _repo_relative(item.path, root=root)[1],
                "source_record_sha256": item.sha256,
                "source_status": "numeric_pass",
                "source_commit_sha": source_sha,
                "selected_mode_count_per_direction": item.payload.get(
                    "requested_modes_per_direction"
                ),
            }
        )

    source_sha = _same_source(source_shas, context="uniform p/h matrix")
    result = {
        "schema_version": "task033.case091.uniform-p-h-matrix.v1",
        "record_type": "task033_uniform_p_h_matrix",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "formal_matrix_complete",
        "formal_source": {
            "commit_sha": source_sha,
            "tracked_source_clean": True,
        },
        "identity": {
            "is_pde_matrix_record": True,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "matrix_shape": {"degrees": 4, "mesh_levels": 5, "entries": 20},
        "resource_matrix": {
            "path": _repo_relative(resource_file.path, root=root)[1],
            "sha256": resource_file.sha256,
            "data_identity": "planning_decisions_only",
        },
        "summary": {
            "measured_funnel_entries": sum(
                row["evidence_disposition"] == "measured_qualified_funnel"
                for row in output_rows
            ),
            "measured_anchor_entries": sum(
                row["evidence_disposition"] == "measured_task032_clean_anchor"
                for row in output_rows
            ),
            "measured_watchdog_entries": sum(
                row["evidence_disposition"] == "measured_external_watchdog_shard"
                for row in output_rows
            ),
            "not_run_by_memory_gate_entries": sum(
                row["evidence_disposition"] == "not_run_by_memory_gate"
                for row in output_rows
            ),
        },
        "entries": output_rows,
        "limitations": [
            "Matrix completeness records measured or memory-gated disposition; it does not turn a memory-gated row into a solver pass.",
            "No row in this aggregate proves 0.7 nm feasibility.",
        ],
    }
    _validate_payload(result, UNIFORM_SCHEMA)
    return result


def _plan_from_record(payload: Mapping[str, Any]) -> PeriodicGradedHybridPlan:
    raw_plan = payload.get("plan", payload)
    if not isinstance(raw_plan, Mapping):
        raise FormalRecordError("graded plan JSON lacks a plan object")
    axes = raw_plan.get("axis_coordinates_nm")
    if not isinstance(axes, Mapping):
        raise FormalRecordError("graded plan lacks explicit axis_coordinates_nm")
    geometry_payload = raw_plan.get("geometry", payload.get("geometry"))
    if geometry_payload is None:
        geometry = Task033Stage4Geometry()
    elif isinstance(geometry_payload, Mapping):
        allowed = set(Task033Stage4Geometry.__dataclass_fields__)
        unexpected = sorted(set(geometry_payload) - allowed)
        if unexpected:
            raise FormalRecordError(
                f"graded plan geometry has unsupported fields: {unexpected!r}"
            )
        try:
            geometry = Task033Stage4Geometry(
                **{key: float(value) for key, value in geometry_payload.items()}
            )
        except (TypeError, ValueError) as exc:
            raise FormalRecordError(f"invalid graded plan geometry: {exc}") from exc
    else:
        raise FormalRecordError("graded plan geometry must be an object")
    certificate = raw_plan.get("certificate")
    certificate = certificate if isinstance(certificate, Mapping) else {}
    try:
        plan = PeriodicGradedHybridPlan(
            geometry=geometry,
            reference_h_nm=float(raw_plan["reference_h_nm"]),
            cycle=int(raw_plan["cycle"]),
            x_values=axes["x"],
            y_values=axes["y"],
            bottom_z_values=axes["bottom_z"],
            top_z_values=axes["top_z"],
            policy=str(raw_plan["policy"]),
            parent_plan_hash=raw_plan.get("parent_plan_hash"),
            explicit_y_feature_planes_present=bool(
                raw_plan.get(
                    "explicit_y_feature_planes_present",
                    certificate.get("explicit_y_feature_planes_present", False),
                )
            ),
            max_neighbor_ratio=float(raw_plan.get("max_neighbor_ratio", 2.0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalRecordError(f"cannot reconstruct graded plan: {exc}") from exc
    declared_hash = raw_plan.get("plan_hash")
    if declared_hash != plan.plan_hash:
        raise FormalRecordError(
            f"graded plan hash mismatch: declared={declared_hash!r}, "
            f"recomputed={plan.plan_hash!r}"
        )
    if raw_plan.get("degree") != 2:
        raise FormalRecordError("Task033 adaptive formal evidence is fixed to degree=2")
    if plan.certificate().get("eligible_for_mesh_smoke") is not True:
        raise FormalRecordError("reconstructed graded plan failed its mesh certificate")
    return plan


def _complex_pair(value: Any, *, label: str) -> complex:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise FormalRecordError(f"{label} must be a [real, imag] pair")
    if len(value) != 2:
        raise FormalRecordError(f"{label} must be a [real, imag] pair")
    try:
        result = complex(float(value[0]), float(value[1]))
    except (TypeError, ValueError) as exc:
        raise FormalRecordError(f"{label} must be a finite complex pair") from exc
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise FormalRecordError(f"{label} must be a finite complex pair")
    return result


def _adaptive_funnel_bundle(
    item: EvidenceFile,
    *,
    repo_root: Path,
) -> tuple[Mapping[str, Any], EvidenceFile, Mapping[str, Any], str]:
    funnel, source_sha = _validated_funnel(item)
    watchdog_file = _selected_watchdog(
        item, funnel, repo_root=repo_root
    )
    measurements, watchdog_sha = _validated_watchdog_summary(
        watchdog_file, target="hybrid"
    )
    if watchdog_sha != source_sha:
        raise FormalRecordError(
            f"funnel {item.path} and selected watchdog use different source SHAs"
        )
    funnel_case = funnel.get("case")
    measured_case = measurements.get("case")
    if not isinstance(funnel_case, Mapping) or not isinstance(
        measured_case, Mapping
    ):
        raise FormalRecordError(f"funnel {item.path} lacks measured case fields")
    for key in (
        "degree",
        "h_nm",
        "wavelength_nm",
        "incident_grazing_deg",
        "polarization_kind",
        "bottom_interface_nm",
        "top_interface_nm",
        "graded_reference_h_nm",
        "graded_plan_hash",
    ):
        if funnel_case.get(key) != measured_case.get(key):
            raise FormalRecordError(
                f"funnel {item.path} selected watchdog differs at case.{key}"
            )
    if measured_case.get("requested_modes_per_direction") != funnel.get(
        "qualification", {}
    ).get("selected_mode_count_per_direction"):
        raise FormalRecordError(
            f"funnel {item.path} selected watchdog has the wrong mode count"
        )
    return funnel, watchdog_file, measurements, source_sha


def _local_fe_dofs(measurements: Mapping[str, Any], *, label: str) -> int:
    hybrid = measurements.get("hybrid_system")
    if not isinstance(hybrid, Mapping):
        raise FormalRecordError(f"{label} lacks hybrid_system")
    bottom = hybrid.get("bottom_local_fe_dofs")
    top = hybrid.get("top_local_fe_dofs")
    if type(bottom) is not int or type(top) is not int or bottom <= 0 or top <= 0:
        raise FormalRecordError(f"{label} lacks positive real local FE DoF counts")
    return bottom + top


def _port_and_order_deltas(
    reference: Mapping[str, Any], candidate: Mapping[str, Any]
) -> tuple[float, float]:
    reference_validation = reference.get("validation")
    candidate_validation = candidate.get("validation")
    if not isinstance(reference_validation, Mapping) or not isinstance(
        candidate_validation, Mapping
    ):
        raise FormalRecordError("adaptive watchdogs lack validation fields")
    reference_power = reference_validation.get("port_power")
    candidate_power = candidate_validation.get("port_power")
    if not isinstance(reference_power, Mapping) or not isinstance(
        candidate_power, Mapping
    ):
        raise FormalRecordError("adaptive watchdogs lack R/T/A fields")
    total_deltas: list[float] = []
    for key in ("R_total", "T_total", "A_balance"):
        try:
            first = float(reference_power[key])
            second = float(candidate_power[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise FormalRecordError(f"adaptive watchdogs lack finite {key}") from exc
        if not math.isfinite(first) or not math.isfinite(second):
            raise FormalRecordError(f"adaptive watchdogs lack finite {key}")
        total_deltas.append(abs(second - first))

    def indexed_orders(validation: Mapping[str, Any]) -> dict[tuple[Any, ...], Mapping[str, Any]]:
        rows = validation.get("external_diffraction_orders")
        if not isinstance(rows, list):
            raise FormalRecordError("adaptive watchdog lacks diffraction orders")
        result: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping) or row.get("propagating") is not True:
                continue
            try:
                key = (
                    str(row["side"]),
                    int(row["m"]),
                    int(row["n"]),
                    str(row["polarization"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise FormalRecordError("invalid propagating diffraction-order key") from exc
            if key in result:
                raise FormalRecordError("duplicate propagating diffraction-order key")
            result[key] = row
        return result

    first_orders = indexed_orders(reference_validation)
    second_orders = indexed_orders(candidate_validation)
    if not first_orders or set(first_orders) != set(second_orders):
        raise FormalRecordError(
            "adaptive reference/candidate propagating-order coverage differs"
        )
    relative_deltas: list[float] = []
    for key in sorted(first_orders):
        first = first_orders[key]
        second = second_orders[key]
        first_power = _nonnegative_number(
            first.get("power_ratio"), label=f"reference order {key} power"
        )
        second_power = _nonnegative_number(
            second.get("power_ratio"), label=f"candidate order {key} power"
        )
        if max(first_power, second_power) < 1.0e-8:
            continue
        first_amp = _complex_pair(
            first.get("outgoing_amplitude_at_boundary"),
            label=f"reference order {key} amplitude",
        )
        second_amp = _complex_pair(
            second.get("outgoing_amplitude_at_boundary"),
            label=f"candidate order {key} amplitude",
        )
        relative_deltas.append(
            abs(second_amp - first_amp) / max(abs(first_amp), abs(second_amp), 1.0e-30)
        )
    if not relative_deltas:
        raise FormalRecordError("adaptive comparison has no significant propagating order")
    return max(total_deltas), max(relative_deltas)


def _interface_errors(
    measurements: Mapping[str, Any], *, label: str
) -> tuple[float, float]:
    physical = measurements.get("physical_field_reconstruction")
    if not isinstance(physical, Mapping):
        raise FormalRecordError(f"{label} lacks physical field reconstruction")
    continuity = physical.get("interface_continuity")
    if not isinstance(continuity, Mapping):
        raise FormalRecordError(f"{label} lacks interface E/H evidence")
    electric: list[float] = []
    magnetic: list[float] = []
    for side in ("bottom", "top"):
        row = continuity.get(side)
        if not isinstance(row, Mapping):
            raise FormalRecordError(f"{label} lacks {side} interface evidence")
        electric_row = row.get("electric_tangential")
        magnetic_row = row.get("magnetic_tangential")
        if not isinstance(electric_row, Mapping) or not isinstance(
            magnetic_row, Mapping
        ):
            raise FormalRecordError(
                f"{label} lacks {side} interface E/H mappings"
            )
        electric.append(
            _nonnegative_number(
                electric_row.get("relative_l2"),
                label=f"{side} interface E relative error",
            )
        )
        magnetic.append(
            _nonnegative_number(
                magnetic_row.get("relative_l2"),
                label=f"{side} interface H relative error",
            )
        )
    return max(electric), max(magnetic)


def _positive_shape(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise FormalRecordError(f"{label} must be a positive integer shape")
    shape: list[int] = []
    for entry in value:
        if type(entry) is not int or entry <= 0:
            raise FormalRecordError(f"{label} must be a positive integer shape")
        shape.append(entry)
    if len(shape) != 4 or shape[-1] != 3:
        raise FormalRecordError(f"{label} must be [z, y, x, 3]")
    return tuple(shape)


def _selected_plane_reference(
    measurements: Mapping[str, Any], *, label: str
) -> dict[str, Any]:
    physical = measurements.get("physical_field_reconstruction")
    if not isinstance(physical, Mapping):
        raise FormalRecordError(f"{label} lacks physical field reconstruction")
    comparison = physical.get("selected_plane_full3d_comparison")
    if not isinstance(comparison, Mapping):
        raise FormalRecordError(f"{label} lacks pinned selected-plane field evidence")
    if comparison.get("reference_binding_verified") is not True:
        raise FormalRecordError(f"{label} selected-plane reference binding is not verified")

    binding: dict[str, str] = {}
    for key in (
        "reference_npz",
        "reference_record",
        "reference_record_sha256",
        "reference_record_source_commit_full_sha",
    ):
        value = comparison.get(key)
        if not isinstance(value, str) or not value:
            raise FormalRecordError(f"{label} lacks selected-plane binding field {key}")
        binding[key] = value.lower() if key.endswith("sha256") else value
    for key in (
        "reference_npz_sha256_expected",
        "reference_npz_sha256_observed",
        "reference_record_sha256",
    ):
        value = str(comparison.get(key, "")).lower()
        if SHA256_RE.fullmatch(value) is None:
            raise FormalRecordError(f"{label} has invalid {key}")
        binding[key] = value
    if (
        binding["reference_npz_sha256_expected"]
        != binding["reference_npz_sha256_observed"]
    ):
        raise FormalRecordError(f"{label} selected-plane NPZ SHA256 differs")
    binding["reference_record_source_commit_full_sha"] = _full_sha(
        comparison.get("reference_record_source_commit_full_sha"),
        label=f"{label} selected-plane reference source",
    )

    comparison_shape = _positive_shape(
        comparison.get("sample_shape_z_y_x_component"),
        label=f"{label} selected-plane comparison shape",
    )
    physical_shape = _positive_shape(
        physical.get("sample_grid_shape_z_y_x_component"),
        label=f"{label} selected-plane physical shape",
    )
    if comparison_shape != physical_shape:
        raise FormalRecordError(f"{label} selected-plane sample shapes differ")

    planes = comparison.get("planes")
    if not isinstance(planes, list) or len(planes) != comparison_shape[0]:
        raise FormalRecordError(f"{label} selected-plane coverage differs from shape")
    z_nm: list[float] = []
    electric: list[float] = []
    magnetic: list[float] = []
    for index, plane in enumerate(planes):
        if not isinstance(plane, Mapping):
            raise FormalRecordError(f"{label} selected plane {index} is invalid")
        z_value = _nonnegative_number(
            plane.get("z_nm"), label=f"{label} selected plane {index} z"
        )
        z_nm.append(z_value)
        for field, target in (("electric", electric), ("magnetic", magnetic)):
            metrics = plane.get(field)
            if not isinstance(metrics, Mapping):
                raise FormalRecordError(
                    f"{label} selected plane {index} lacks {field} metrics"
                )
            target.append(
                _nonnegative_number(
                    metrics.get("relative_l2"),
                    label=f"{label} selected plane {index} {field} relative L2",
                )
            )
    if len(z_nm) < 3 or any(second <= first for first, second in zip(z_nm, z_nm[1:])):
        raise FormalRecordError(f"{label} selected-plane z coverage is not increasing")
    max_e = max(electric[1:-1])
    max_h = max(magnetic[1:-1])
    reported_e = _nonnegative_number(
        comparison.get("max_middle_plane_electric_relative_l2"),
        label=f"{label} reported middle-plane E error",
    )
    reported_h = _nonnegative_number(
        comparison.get("max_middle_plane_magnetic_relative_l2"),
        label=f"{label} reported middle-plane H error",
    )
    if not math.isclose(reported_e, max_e, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise FormalRecordError(f"{label} middle-plane E summary is inconsistent")
    if not math.isclose(reported_h, max_h, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise FormalRecordError(f"{label} middle-plane H summary is inconsistent")
    if max(max_e, max_h) > SELECTED_PLANE_FIELD_RELATIVE_MAX:
        raise FormalRecordError(f"{label} selected middle-plane field Gate failed")
    full_volume = physical.get("full_middle_volume_reconstructed")
    if type(full_volume) is not bool:
        raise FormalRecordError(f"{label} lacks full-volume reconstruction status")
    return {
        "binding": binding,
        "sample_shape_z_y_x_component": list(comparison_shape),
        "z_nm": z_nm,
        "max_middle_plane_electric_relative_l2": max_e,
        "max_middle_plane_magnetic_relative_l2": max_h,
        "full_middle_volume_reconstructed": full_volume,
    }


def build_adaptive_evidence(
    graded_plan_path: Path | str,
    reference_evidence_path: Path | str,
    candidate_evidence_path: Path | str,
    *,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Recompute the native same-accuracy gate for one h5 or h3 graded plan."""

    root = Path(repo_root).resolve()
    plan_file = _read_json(_repo_relative(graded_plan_path, root=root)[0])
    reference_file = _read_json(
        _repo_relative(reference_evidence_path, root=root)[0]
    )
    candidate_file = _read_json(
        _repo_relative(candidate_evidence_path, root=root)[0]
    )
    plan = _plan_from_record(plan_file.payload)
    reference_funnel, reference_watchdog, reference_measurements, reference_sha = (
        _adaptive_funnel_bundle(reference_file, repo_root=root)
    )
    candidate_funnel, candidate_watchdog, candidate_measurements, candidate_sha = (
        _adaptive_funnel_bundle(candidate_file, repo_root=root)
    )
    source_sha = _same_source(
        [reference_sha, candidate_sha], context="adaptive same-accuracy evidence"
    )
    reference_case = reference_funnel.get("case", {})
    candidate_case = candidate_funnel.get("case", {})
    invariants = (
        "degree",
        "h_nm",
        "wavelength_nm",
        "incident_grazing_deg",
        "polarization_kind",
        "bottom_interface_nm",
        "top_interface_nm",
        "primary_solver_path",
    )
    if any(reference_case.get(key) != candidate_case.get(key) for key in invariants):
        raise FormalRecordError("adaptive reference/candidate physical identities differ")
    if reference_case.get("graded_reference_h_nm") is not None or reference_case.get(
        "graded_plan_hash"
    ) is not None:
        raise FormalRecordError("adaptive reference funnel must be the uniform reference")
    if candidate_case.get("graded_reference_h_nm") != plan.reference_h_nm or candidate_case.get(
        "graded_plan_hash"
    ) != plan.plan_hash:
        raise FormalRecordError("adaptive candidate funnel is not bound to the graded plan")
    physical_signature = hashlib.sha256(
        json.dumps(
            {key: reference_case.get(key) for key in invariants},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    max_rta, max_order = _port_and_order_deltas(
        reference_measurements, candidate_measurements
    )
    reference_selected_planes = _selected_plane_reference(
        reference_measurements, label="adaptive reference"
    )
    candidate_selected_planes = _selected_plane_reference(
        candidate_measurements, label="adaptive candidate"
    )
    if (
        reference_selected_planes["binding"]
        != candidate_selected_planes["binding"]
        or reference_selected_planes["sample_shape_z_y_x_component"]
        != candidate_selected_planes["sample_shape_z_y_x_component"]
        or reference_selected_planes["z_nm"] != candidate_selected_planes["z_nm"]
    ):
        raise FormalRecordError(
            "adaptive reference/candidate selected-plane bindings or coverage differ"
        )
    reference_interface_e, reference_interface_h = _interface_errors(
        reference_measurements, label="adaptive reference"
    )
    interface_e, interface_h = _interface_errors(
        candidate_measurements, label="adaptive candidate"
    )
    candidate_solve = candidate_measurements.get("solve")
    if not isinstance(candidate_solve, Mapping):
        raise FormalRecordError("adaptive candidate lacks solve residual")
    reference = {
        "data_identity": "measured",
        "source_clean": True,
        "degree": reference_case.get("degree"),
        "h_nm": reference_case.get("h_nm"),
        "local_fe_rows": _local_fe_dofs(
            reference_measurements, label="adaptive reference"
        ),
        "reference_field_evidence_available": True,
        "source_commit": reference_sha,
        "physics_signature": physical_signature,
    }
    candidate = {
        "data_identity": "measured",
        "source_clean": True,
        "degree": candidate_case.get("degree"),
        "h_nm": candidate_case.get("h_nm"),
        "local_fe_rows": _local_fe_dofs(
            candidate_measurements, label="adaptive candidate"
        ),
        "modal_truncation_gate_pass": True,
        "source_commit": candidate_sha,
        "physics_signature": physical_signature,
        "mesh_plan_hash": candidate_case.get("graded_plan_hash"),
        "true_residual": _nonnegative_number(
            candidate_solve.get("true_relative_residual"), label="true residual"
        ),
        "max_abs_rta_delta": max_rta,
        "max_significant_order_amplitude_relative_delta": max_order,
        "sampled_interface_e_relative_error": max(
            reference_interface_e, interface_e
        ),
        "sampled_interface_h_relative_error": max(
            reference_interface_h, interface_h
        ),
    }
    result = build_adaptive_planning_record(
        plan,
        reference_evidence=reference,
        candidate_evidence=candidate,
    )
    qualification = result.get("same_accuracy_qualification")
    if not isinstance(qualification, Mapping) or qualification.get(
        "mandatory_gate_pass"
    ) is not True:
        reasons = qualification.get("reasons") if isinstance(qualification, Mapping) else []
        raise FormalRecordError(
            f"native same-accuracy gate did not qualify: {reasons!r}"
        )
    result = {
        **result,
        "formal_source": {
            "commit_sha": source_sha,
            "tracked_source_clean": True,
        },
        "measured_evidence": {
            "graded_plan": {
                "path": _repo_relative(plan_file.path, root=root)[1],
                "sha256": plan_file.sha256,
                "plan_hash": plan.plan_hash,
            },
            "reference": {
                "path": _repo_relative(reference_file.path, root=root)[1],
                "sha256": reference_file.sha256,
                "selected_watchdog_path": _repo_relative(
                    reference_watchdog.path, root=root
                )[1],
                "selected_watchdog_sha256": reference_watchdog.sha256,
                "field_evidence_kind": (
                    "sampled_interface_EH_and_pinned_full3d_selected_planes"
                ),
                "sampled_interface_e_relative_error": reference_interface_e,
                "sampled_interface_h_relative_error": reference_interface_h,
                "selected_plane_reference": reference_selected_planes,
            },
            "candidate": {
                "path": _repo_relative(candidate_file.path, root=root)[1],
                "sha256": candidate_file.sha256,
                "selected_watchdog_path": _repo_relative(
                    candidate_watchdog.path, root=root
                )[1],
                "selected_watchdog_sha256": candidate_watchdog.sha256,
                "selected_plane_reference": candidate_selected_planes,
            },
        },
    }
    _validate_payload(result, ADAPTIVE_SCHEMA)
    return result


def _resolve_source_record(
    raw: Any, *, funnel_path: Path, repo_root: Path = ROOT
) -> Path:
    if not isinstance(raw, str) or not raw:
        raise FormalRecordError(f"funnel {funnel_path} has an invalid source-record path")
    requested = Path(raw)
    candidates: list[Path] = []
    if requested.is_absolute():
        candidates.append(requested)
    if raw.replace("\\", "/").startswith("/work/"):
        candidates.append(
            repo_root / raw.replace("\\", "/")[len("/work/") :]
        )
    if not requested.is_absolute():
        candidates.extend(
            (repo_root / requested, funnel_path.parent / requested)
        )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise FormalRecordError(
        f"funnel {funnel_path} selected watchdog source cannot be read: {raw!r}"
    )


def _watchdog_source_sha(payload: Mapping[str, Any], *, path: Path) -> str:
    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise FormalRecordError(f"watchdog summary {path} lacks source evidence")
    gate = source_identity_gate(source)
    if gate.get("pass") is True:
        return _full_sha(gate.get("head_sha"), label=f"watchdog {path} source")
    sha = _full_sha(
        source.get("commit_sha", source.get("source_commit_full_sha")),
        label=f"watchdog {path} source",
    )
    verified = source.get("verified_clean_sha")
    if not (
        source.get("tracked_source_dirty") is False
        and (verified is None or str(verified).lower() == sha)
        and source.get("source_clean_verified", True) is True
    ):
        raise FormalRecordError(
            f"watchdog summary {path} failed clean-source gate: {gate.get('failures')!r}"
        )
    return sha


def _validated_watchdog_summary(
    item: EvidenceFile, *, target: str
) -> tuple[Mapping[str, Any], str]:
    """Return embedded measured fields only from one passing external watchdog."""

    payload = item.payload
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    conditions = {
        "schema": payload.get("schema_version") == "task033.memory-watchdog.v2",
        "benchmark": payload.get("benchmark_id") == "task033_external_memory_watchdog",
        "target": payload.get("target") == target,
        "status": payload.get("status") == "measured_shard_pass",
        "formal_pass": payload.get("formal_pass") is True,
        "memory_authority_pass": payload.get("memory_authority_pass") is True,
        "return_code": payload.get("return_code") == 0,
        "no_swap": payload.get("no_swap") is True,
        "not_memory_terminated": payload.get("terminated_for_memory") is False,
        "not_timeout_terminated": payload.get("terminated_for_timeout") is False,
        "not_authority_terminated": (
            payload.get("terminated_for_authority_unreadable", False) is False
        ),
        "resource_gate": resource_gate.get("pass") is True,
    }
    failed = [key for key, passed in conditions.items() if not passed]
    if failed:
        raise FormalRecordError(
            f"watchdog summary {item.path} is not a measured {target} pass: {failed!r}"
        )
    measurements = payload.get("measurements")
    if not isinstance(measurements, Mapping):
        raise FormalRecordError(f"watchdog summary {item.path} lacks measurements")
    return measurements, _watchdog_source_sha(payload, path=item.path)


def _command_value(command: Any, option: str) -> str | None:
    if not isinstance(command, list):
        return None
    try:
        index = command.index(option)
    except ValueError:
        return None
    if index + 1 >= len(command):
        return None
    return str(command[index + 1])


def _validated_qep_solver_record(
    item: EvidenceFile, shard: Mapping[str, Any], *, repo_root: Path
) -> dict[str, str]:
    raw_path = item.payload.get("solver_record_ignored_path")
    solver_path = _resolve_source_record(
        raw_path, funnel_path=item.path, repo_root=repo_root
    )
    expected_sha = item.payload.get("solver_record_sha256")
    if not isinstance(expected_sha, str) or not SHA256_RE.fullmatch(
        expected_sha.lower()
    ):
        raise FormalRecordError(
            f"QEP watchdog {item.path} has no valid solver-record SHA256"
        )
    solver = _read_json(solver_path)
    if solver.sha256 != expected_sha.lower():
        raise FormalRecordError(
            f"QEP watchdog {item.path} solver-record SHA256 mismatch"
        )
    if solver.payload != dict(shard):
        raise FormalRecordError(
            f"QEP watchdog {item.path} embedded measurements differ from "
            "the preserved solver record"
        )
    return {
        "path": _repo_relative(solver.path, root=repo_root)[1],
        "sha256": solver.sha256,
    }


def _validated_qep_watchdog_summary(
    item: EvidenceFile, *, mpi_size: int, repo_root: Path
) -> tuple[Mapping[str, Any], str, str, dict[str, str]]:
    """Validate a QEP pass or the one controlled p4 numerical negative."""

    payload = item.payload
    measurements = payload.get("measurements")
    if not isinstance(measurements, Mapping):
        raise FormalRecordError(f"QEP watchdog {item.path} lacks a solver record")
    candidate = measurements.get("candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    resource = payload.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    source_gate = payload.get("source_gate")
    source_gate = source_gate if isinstance(source_gate, Mapping) else {}
    launch_gate = payload.get("launch_gate")
    launch_gate = launch_gate if isinstance(launch_gate, Mapping) else {}
    command = payload.get("command")
    common = {
        "schema": payload.get("schema_version") == "task033.memory-watchdog.v2",
        "benchmark": payload.get("benchmark_id")
        == "task033_external_memory_watchdog",
        "target": payload.get("target") == "qep",
        "memory_authority_pass": payload.get("memory_authority_pass") is True,
        "no_swap": payload.get("no_swap") is True,
        "not_memory_terminated": payload.get("terminated_for_memory") is False,
        "not_timeout_terminated": payload.get("terminated_for_timeout") is False,
        "not_authority_terminated": (
            payload.get("terminated_for_authority_unreadable") is False
        ),
        "resource_gate": resource_gate.get("pass") is True,
        "source_gate": source_gate.get("pass") is True,
        "launch_gate": launch_gate.get("pass") is True,
        "requested_modes_8": payload.get("requested_modes") == 8,
        "candidate_modes_16": payload.get("candidate_modes") == 16,
        "worker_requested_modes_8": _command_value(
            command, "--requested-modes"
        )
        == "8",
        "worker_left_candidate_modes_16": _command_value(
            command, "--left-candidate-modes"
        )
        == "16",
        "candidate_mpi_size": candidate.get("mpi_size") == mpi_size,
    }
    failed_common = [name for name, passed in common.items() if not passed]
    if failed_common:
        raise FormalRecordError(
            f"QEP watchdog {item.path} failed execution/source/resource "
            f"contract: {failed_common!r}"
        )
    source_sha = _watchdog_source_sha(payload, path=item.path)
    solver_descriptor = _validated_qep_solver_record(
        item, measurements, repo_root=repo_root
    )

    if payload.get("status") == "measured_shard_pass":
        pass_conditions = {
            "formal_pass": payload.get("formal_pass") is True,
            "numeric_pass": payload.get("numeric_pass") is True,
            "return_code": payload.get("return_code") == 0,
            "worker_status": measurements.get("status") == "measured_shard_pass",
        }
        failures = [name for name, passed in pass_conditions.items() if not passed]
        if failures:
            raise FormalRecordError(
                f"QEP watchdog {item.path} is not a complete measured pass: "
                f"{failures!r}"
            )
        disposition = "pass"
    elif payload.get("status") == "formal_not_pass":
        negative_conditions = {
            "formal_not_pass": payload.get("formal_pass") is False,
            "numeric_not_pass": payload.get("numeric_pass") is False,
            "return_code_2": payload.get("return_code") == 2,
            "worker_measured_shard_failed": (
                measurements.get("status") == "measured_shard_failed"
            ),
            "degree_4": candidate.get("degree") == 4,
        }
        failures = [
            name for name, passed in negative_conditions.items() if not passed
        ]
        controlled = qep_p4_controlled_negative_gate(
            measurements, mpi_size=mpi_size
        )
        if failures or controlled.get("pass") is not True:
            raise FormalRecordError(
                f"QEP watchdog {item.path} is not the controlled p4 numerical "
                f"negative: outer={failures!r}, "
                f"worker={controlled.get('failures')!r}"
            )
        disposition = "controlled_numeric_negative"
    else:
        raise FormalRecordError(
            f"QEP watchdog {item.path} has unsupported status "
            f"{payload.get('status')!r}"
        )
    return measurements, source_sha, disposition, solver_descriptor


def _selected_watchdog(
    funnel_file: EvidenceFile,
    funnel: Mapping[str, Any],
    *,
    repo_root: Path = ROOT,
) -> EvidenceFile:
    qualification = funnel.get("qualification")
    if not isinstance(qualification, Mapping):
        raise FormalRecordError(f"funnel {funnel_file.path} lacks qualification")
    selected_m = qualification.get("selected_mode_count_per_direction")
    descriptors = funnel.get("source_records")
    if not isinstance(descriptors, list):
        raise FormalRecordError(f"funnel {funnel_file.path} lacks source_records")
    selected = [
        row
        for row in descriptors
        if isinstance(row, Mapping)
        and row.get("mode_count_per_direction") == selected_m
    ]
    if len(selected) != 1:
        raise FormalRecordError(
            f"funnel {funnel_file.path} must bind selected M={selected_m!r} "
            "to exactly one watchdog source"
        )
    descriptor = selected[0]
    path = _resolve_source_record(
        descriptor.get("path"),
        funnel_path=funnel_file.path,
        repo_root=repo_root,
    )
    item = _read_json(path)
    if descriptor.get("sha256") != item.sha256:
        raise FormalRecordError(
            f"selected watchdog SHA256 mismatch for funnel {funnel_file.path}"
        )
    return item


def _joint_cost_metrics(
    summary_file: EvidenceFile,
    *,
    funnel: Mapping[str, Any],
    source_sha: str,
) -> dict[str, float]:
    summary = summary_file.payload
    conditions = {
        "status_measured": summary.get("status") == "measured_shard_pass",
        "formal_pass": summary.get("formal_pass") is True,
        "hybrid_target": summary.get("target") == "hybrid",
        "return_code_zero": summary.get("return_code") == 0,
        "no_swap": summary.get("no_swap") is True,
        "not_memory_terminated": summary.get("terminated_for_memory") is False,
        "not_timeout_terminated": summary.get("terminated_for_timeout") is False,
    }
    resource = summary.get("resource_authority")
    resource = resource if isinstance(resource, Mapping) else {}
    resource_gate = resource.get("gate")
    resource_gate = resource_gate if isinstance(resource_gate, Mapping) else {}
    conditions["resource_authority_pass"] = resource_gate.get("pass") is True
    failed = [key for key, passed in conditions.items() if not passed]
    if failed:
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} is not formal measured evidence: {failed!r}"
        )
    if _watchdog_source_sha(summary, path=summary_file.path) != source_sha:
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} source differs from its funnel"
        )
    measurements = summary.get("measurements")
    if not isinstance(measurements, Mapping):
        raise FormalRecordError(f"selected watchdog {summary_file.path} lacks measurements")
    measured_case = measurements.get("case")
    funnel_case = funnel.get("case")
    if not isinstance(measured_case, Mapping) or not isinstance(funnel_case, Mapping):
        raise FormalRecordError(f"selected watchdog {summary_file.path} lacks case identity")
    case_fields = (
        "degree",
        "h_nm",
        "bottom_interface_nm",
        "top_interface_nm",
        "wavelength_nm",
        "incident_grazing_deg",
        "polarization_kind",
    )
    mismatched = [
        key for key in case_fields if measured_case.get(key) != funnel_case.get(key)
    ]
    selected_m = funnel.get("qualification", {}).get(
        "selected_mode_count_per_direction"
    )
    if measured_case.get("requested_modes_per_direction") != selected_m:
        mismatched.append("requested_modes_per_direction")
    if mismatched:
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} differs from funnel case: {mismatched!r}"
        )
    hybrid = measurements.get("hybrid_system")
    ledger = measurements.get("object_payload_ledger")
    timings = measurements.get("timing_seconds_max_rank")
    if not isinstance(hybrid, Mapping) or not isinstance(ledger, Mapping) or not isinstance(
        timings, Mapping
    ):
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} lacks hybrid/ledger/timing cost fields"
        )
    bottom_dofs = _positive_number(
        hybrid.get("bottom_local_fe_dofs"), label="bottom_local_fe_dofs"
    )
    top_dofs = _positive_number(
        hybrid.get("top_local_fe_dofs"), label="top_local_fe_dofs"
    )
    internal_modes = _positive_number(
        hybrid.get("internal_unknown_count"), label="internal_unknown_count"
    )
    if internal_modes != 2.0 * float(selected_m):
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} internal modal unknowns "
            "do not equal 2M"
        )
    interface = ledger.get("interface_active_dofs")
    if not isinstance(interface, Mapping):
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} lacks interface_active_dofs"
        )
    interface_dofs = _positive_number(
        interface.get("bottom"), label="bottom interface active DoFs"
    ) + _positive_number(interface.get("top"), label="top interface active DoFs")
    qep_seconds = _nonnegative_number(
        timings.get("cross_section_and_qep_assembly"),
        label="cross_section_and_qep_assembly",
    ) + _nonnegative_number(
        timings.get("positive_and_negative_biorthogonal_bases"),
        label="positive_and_negative_biorthogonal_bases",
    )
    local_seconds = _positive_number(
        timings.get("two_local_fem_dtn_systems"), label="two_local_fem_dtn_systems"
    )
    interface_seconds = _nonnegative_number(
        timings.get("internal_modal_coupling"), label="internal_modal_coupling"
    ) + _nonnegative_number(
        timings.get("primary_system_build"), label="primary_system_build"
    )
    total_seconds = _positive_number(timings.get("total"), label="total time")
    if qep_seconds <= 0.0 or interface_seconds <= 0.0:
        raise FormalRecordError(
            f"selected watchdog {summary_file.path} has zero QEP/interface measured cost"
        )
    return {
        "local_fe_dofs": bottom_dofs + top_dofs,
        "selected_mode_count_per_direction": float(selected_m),
        "internal_modal_unknowns": internal_modes,
        "interface_trace_dofs": interface_dofs,
        "qep_and_mode_seconds": qep_seconds,
        "local_fem_seconds": local_seconds,
        "interface_and_schur_seconds": interface_seconds,
        "total_seconds": total_seconds,
        "memory_authority_bytes": _positive_number(
            resource.get("memory_authority_bytes"), label="memory_authority_bytes"
        ),
    }


def build_interface_buffer_tradeoff(
    funnel_paths: Sequence[Path | str],
    *,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Rank four qualified interface buffers using measured joint costs."""

    if len(funnel_paths) != 4:
        raise FormalRecordError("buffer tradeoff requires exactly four funnel files")
    root = Path(repo_root).resolve()
    by_buffer: dict[float, tuple[EvidenceFile, Mapping[str, Any], str]] = {}
    common_case: dict[str, Any] | None = None
    source_shas: list[str] = []
    for path in funnel_paths:
        item = _read_json(_repo_relative(path, root=root)[0])
        funnel, source_sha = _validated_funnel(item)
        case = funnel.get("case")
        if not isinstance(case, Mapping):
            raise FormalRecordError(f"funnel {item.path} lacks case identity")
        bottom = float(case.get("bottom_interface_nm", math.nan))
        top = float(case.get("top_interface_nm", math.nan))
        buffer_nm = next(
            (
                value
                for value, pair in BUFFER_INTERFACES.items()
                if math.isclose(bottom, pair[0], abs_tol=1.0e-12)
                and math.isclose(top, pair[1], abs_tol=1.0e-12)
            ),
            None,
        )
        if buffer_nm is None or buffer_nm in by_buffer:
            raise FormalRecordError(
                f"funnel {item.path} has an unsupported or duplicate interface buffer"
            )
        invariant = {
            key: case.get(key)
            for key in (
                "degree",
                "h_nm",
                "wavelength_nm",
                "incident_grazing_deg",
                "polarization_kind",
                "graded_reference_h_nm",
                "graded_plan_hash",
                "primary_solver_path",
            )
        }
        if common_case is None:
            common_case = invariant
        elif invariant != common_case:
            raise FormalRecordError(
                f"buffer funnel {item.path} changes non-interface physical identity"
            )
        by_buffer[buffer_nm] = (item, funnel, source_sha)
        source_shas.append(source_sha)
    if set(by_buffer) != set(BUFFER_INTERFACES):
        raise FormalRecordError("buffer funnels do not cover 10/7.5/5/2.5 nm exactly")
    source_sha = _same_source(source_shas, context="interface-buffer tradeoff")

    raw_rows: list[dict[str, Any]] = []
    for buffer_nm in BUFFER_INTERFACES:
        funnel_file, funnel, funnel_sha = by_buffer[buffer_nm]
        summary_file = _selected_watchdog(
            funnel_file, funnel, repo_root=root
        )
        metrics = _joint_cost_metrics(
            summary_file, funnel=funnel, source_sha=funnel_sha
        )
        raw_rows.append(
            {
                "buffer_nm": buffer_nm,
                "bottom_interface_nm": BUFFER_INTERFACES[buffer_nm][0],
                "top_interface_nm": BUFFER_INTERFACES[buffer_nm][1],
                "source_record_path": _repo_relative(
                    funnel_file.path, root=root
                )[1],
                "source_record_sha256": funnel_file.sha256,
                "selected_watchdog_path": _repo_relative(
                    summary_file.path, root=root
                )[1],
                "selected_watchdog_sha256": summary_file.sha256,
                "measured_costs": metrics,
            }
        )
    score_fields = (
        "local_fe_dofs",
        "selected_mode_count_per_direction",
        "interface_trace_dofs",
        "total_seconds",
        "memory_authority_bytes",
    )
    minima = {
        field: min(row["measured_costs"][field] for row in raw_rows)
        for field in score_fields
    }
    for row in raw_rows:
        normalized = {
            field: row["measured_costs"][field] / minima[field]
            for field in score_fields
        }
        row["normalized_cost_ratios_to_observed_minimum"] = normalized
        row["joint_cost_score"] = sum(normalized.values()) / len(normalized)
    ordered = sorted(raw_rows, key=lambda row: row["joint_cost_score"])
    if math.isclose(
        ordered[0]["joint_cost_score"],
        ordered[1]["joint_cost_score"],
        rel_tol=1.0e-12,
        abs_tol=1.0e-12,
    ):
        raise FormalRecordError(
            "joint measured cost has a first-place tie; no unique buffer can be selected"
        )
    selected_buffer = float(ordered[0]["buffer_nm"])
    result = {
        "schema_version": "task033.case091.interface-buffer-tradeoff.v1",
        "record_type": "task033_interface_buffer_tradeoff",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "qualified",
        "formal_source": {
            "commit_sha": source_sha,
            "tracked_source_clean": True,
        },
        "identity": {
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "case_invariants": common_case,
        "selection_policy": {
            "kind": "equal_weight_mean_of_ratios_to_observed_minimum",
            "score_fields": list(score_fields),
            "lower_is_better": True,
            "tie_policy": "fail_closed_no_selection",
            "interpretation": (
                "The score combines local FEM, modal, interface, runtime, and "
                "memory costs; it is not a physical-accuracy gate."
            ),
        },
        "candidates": raw_rows,
        "selected_buffer_nm": selected_buffer,
        "limitations": [
            "Selection applies only to the four measured funnels with one common physical identity.",
            "No candidate is selected when a cost field is absent or the best score is tied.",
        ],
    }
    _validate_payload(result, TRADEOFF_SCHEMA)
    return result


def _approved_binding(
    payload: Mapping[str, Any], *, role: str
) -> tuple[str, str, bool, str]:
    for sha_pointer, clean_pointer, expected in APPROVED_SOURCE_BINDINGS:
        if (sha_pointer, clean_pointer, expected) not in ALLOWED_SOURCE_BINDINGS:
            continue
        has_sha, sha_value = _try_pointer(payload, sha_pointer)
        has_clean, clean_value = _try_pointer(payload, clean_pointer)
        if not has_sha or not has_clean:
            continue
        source_sha = _full_sha(sha_value, label=f"{role} source")
        if clean_value is not expected:
            raise FormalRecordError(
                f"{role} source-clean value at {clean_pointer} is {clean_value!r}, "
                f"expected {expected!r}"
            )
        return sha_pointer, clean_pointer, expected, source_sha
    raise FormalRecordError(
        f"{role} has no approved clean-source pointer pair"
    )


def build_formal_manifest(
    role_paths: Mapping[str, Path | str], *, repo_root: Path | str = ROOT
) -> dict[str, Any]:
    """Build a 21-role manifest only after frozen schema/status/source checks."""

    root = Path(repo_root).resolve()
    missing = sorted(set(REQUIRED_FORMAL_ROLES) - set(role_paths))
    extra = sorted(set(role_paths) - set(REQUIRED_FORMAL_ROLES))
    if missing or extra:
        raise FormalRecordError(
            f"formal manifest role set is incomplete: missing={missing!r}, extra={extra!r}"
        )
    resolved: dict[str, tuple[EvidenceFile, str]] = {}
    for role in REQUIRED_FORMAL_ROLES:
        path, relative = _repo_relative(role_paths[role], root=root)
        resolved[role] = (_read_json(path), relative)
    if resolved["case090_clean_core"][0].path != resolved["case090_mpi_memory"][0].path:
        raise FormalRecordError(
            "case090_clean_core and case090_mpi_memory must use the same aggregate file"
        )
    paths_to_roles: dict[Path, list[str]] = {}
    for role, (item, _) in resolved.items():
        paths_to_roles.setdefault(item.path, []).append(role)
    for path, roles in paths_to_roles.items():
        if len(roles) > 1 and set(roles) != {
            "case090_clean_core",
            "case090_mpi_memory",
        }:
            raise FormalRecordError(
                f"formal evidence path {path} is reused by unrelated roles {roles!r}"
            )

    entries: list[dict[str, Any]] = []
    source_shas: list[str] = []
    for role in REQUIRED_FORMAL_ROLES:
        item, relative = resolved[role]
        spec = ROLE_SPECS[role]
        _validate_payload(item.payload, spec.schema_ref, root=root)
        status = _pointer(item.payload, spec.status_pointer)
        if status not in spec.accepted_statuses:
            raise FormalRecordError(
                f"{role} has unaccepted status {status!r}; "
                f"expected {spec.accepted_statuses!r}"
            )
        semantic = checker_semantic_problems(role, item.payload)
        if semantic:
            raise FormalRecordError(
                f"{role} failed frozen semantic checks: {'; '.join(semantic)}"
            )
        sha_pointer, clean_pointer, expected, source_sha = _approved_binding(
            item.payload, role=role
        )
        source_shas.append(source_sha)
        entries.append(
            {
                "role": role,
                "path": relative,
                "sha256": item.sha256,
                "schema_ref": spec.schema_ref,
                "source_sha_pointer": sha_pointer,
                "source_clean_pointer": clean_pointer,
                "source_clean_expected": expected,
            }
        )
    source_sha = _same_source(source_shas, context="formal evidence manifest")
    closure_problems = final_outcome_manifest_closure_problems(
        resolved["final_outcome"][0].payload,
        entries,
        source_sha,
    )
    if closure_problems:
        raise FormalRecordError(
            "final outcome is not closed by the formal manifest: "
            + "; ".join(closure_problems)
        )
    result = {
        "schema_version": "task033.case091.formal-evidence-manifest.v2",
        "record_type": "task033_formal_evidence_manifest",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "submitted_for_verification",
        "identity": {
            "is_formal_evidence_submission": True,
            "is_pde_run": False,
            "is_solver_pass": False,
            "claims_task033_complete": False,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "required_roles": list(REQUIRED_FORMAL_ROLES),
        "clean_source_sha": source_sha,
        "entries": entries,
        "reason": (
            "All frozen formal roles were supplied with schema-valid accepted "
            "status, semantic checks, file SHA256, and one clean source SHA."
        ),
        "limitations": [
            "This manifest is an integrity submission and is not itself a PDE or solver pass.",
            "The independent Task033 checker remains the authority that accepts or rejects the bundle.",
        ],
    }
    _validate_payload(result, FORMAL_SCHEMA, root=root)
    return result


def build_formal_publication_descriptor(
    formal_manifest: Path | str,
    formal_verification: Path | str,
    final_outcome: Path | str,
    *,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Bind manifest, checker report, and outcome without a hash cycle."""

    root = Path(repo_root).resolve()
    resolved: dict[str, tuple[EvidenceFile, str]] = {}
    for name, requested in (
        ("formal_manifest", formal_manifest),
        ("formal_verification", formal_verification),
        ("final_outcome", final_outcome),
    ):
        path, relative = _repo_relative(requested, root=root)
        resolved[name] = (_read_json(path), relative)

    manifest, manifest_relative = resolved["formal_manifest"]
    verification, verification_relative = resolved["formal_verification"]
    outcome, outcome_relative = resolved["final_outcome"]
    _validate_payload(manifest.payload, FORMAL_SCHEMA, root=root)
    _validate_payload(
        outcome.payload, ROLE_SPECS["final_outcome"].schema_ref, root=root
    )
    if manifest.payload.get("status") != "submitted_for_verification":
        raise FormalRecordError("publication manifest is not submitted for verification")
    clean_source_sha = _full_sha(
        manifest.payload.get("clean_source_sha"), label="publication manifest source"
    )
    outcome_source = _pointer(
        outcome.payload, "/formal_source/commit_sha"
    )
    if outcome_source != clean_source_sha:
        raise FormalRecordError(
            "publication final outcome source SHA differs from manifest"
        )
    semantic = checker_semantic_problems("final_outcome", outcome.payload)
    if semantic:
        raise FormalRecordError(
            "publication final outcome failed semantics: " + "; ".join(semantic)
        )

    final_entries = [
        entry
        for entry in manifest.payload.get("entries", [])
        if isinstance(entry, Mapping) and entry.get("role") == "final_outcome"
    ]
    if len(final_entries) != 1:
        raise FormalRecordError(
            "publication manifest must contain exactly one final_outcome role"
        )
    final_entry = final_entries[0]
    if (
        final_entry.get("path") != outcome_relative
        or final_entry.get("sha256") != outcome.sha256
    ):
        raise FormalRecordError(
            "publication final outcome differs from the manifest role binding"
        )

    report = verification.payload
    if (
        report.get("record_type") != "task033_evidence_verification_report"
        or report.get("mode") != "formal"
        or report.get("status") != "evidence_verified"
        or report.get("verified") is not True
        or report.get("problems") != []
    ):
        raise FormalRecordError(
            "publication verification report is not one clean formal verification"
        )
    manifest_checks = [
        check
        for check in report.get("checks", [])
        if isinstance(check, Mapping)
        and check.get("name") == "formal_manifest_schema"
    ]
    if len(manifest_checks) != 1:
        raise FormalRecordError(
            "publication verification lacks one formal_manifest_schema check"
        )
    manifest_check = manifest_checks[0]
    details = manifest_check.get("details", {})
    if (
        manifest_check.get("status") != "verified"
        or not isinstance(details, Mapping)
        or details.get("path") != manifest_relative
        or details.get("sha256") != manifest.sha256
    ):
        raise FormalRecordError(
            "publication verification is not bound to the supplied manifest hash"
        )
    checks_by_name = {
        str(check.get("name")): check
        for check in report.get("checks", [])
        if isinstance(check, Mapping) and isinstance(check.get("name"), str)
    }
    required_check_names = {
        "formal_manifest_schema",
        "formal_manifest_role_inventory",
        "formal_final_outcome_input_closure",
        *(f"formal_role:{role}" for role in REQUIRED_FORMAL_ROLES),
    }
    missing_or_unverified = sorted(
        name
        for name in required_check_names
        if name not in checks_by_name
        or checks_by_name[name].get("status") != "verified"
    )
    if missing_or_unverified:
        raise FormalRecordError(
            "publication verification lacks verified formal checks: "
            f"{missing_or_unverified!r}"
        )

    result: dict[str, Any] = {
        "schema_version": "task033.case091.formal-publication-descriptor.v1",
        "record_type": "task033_formal_publication_descriptor",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "publication_bound",
        "clean_source_sha": clean_source_sha,
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "is_formal_verification_report": False,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "artifacts": {
            "formal_manifest": {
                "path": manifest_relative,
                "sha256": manifest.sha256,
                "record_type": manifest.payload.get("record_type"),
                "status": manifest.payload.get("status"),
            },
            "formal_verification": {
                "path": verification_relative,
                "sha256": verification.sha256,
                "record_type": report.get("record_type"),
                "status": report.get("status"),
            },
            "final_outcome": {
                "path": outcome_relative,
                "sha256": outcome.sha256,
                "record_type": outcome.payload.get("record_type"),
                "status": outcome.payload.get("status"),
            },
        },
        "limitations": [
            "This descriptor is a publication hash binding, not a PDE run or solver qualification.",
            "The verification report stays outside the formal manifest to avoid a manifest-verification hash cycle.",
        ],
    }
    result["payload_sha256"] = _canonical_payload_sha256(result)
    _validate_payload(result, PUBLICATION_SCHEMA, root=root)
    semantic = formal_publication_descriptor_problems(result)
    if semantic:
        raise FormalRecordError(
            "generated publication descriptor failed semantics: "
            + "; ".join(semantic)
        )
    return result


__all__ = [
    "FormalRecordError",
    "build_adaptive_evidence",
    "build_formal_manifest",
    "build_formal_publication_descriptor",
    "build_interface_buffer_tradeoff",
    "build_qep_order_study",
    "build_uniform_p_h_matrix",
    "formal_publication_descriptor_problems",
]
