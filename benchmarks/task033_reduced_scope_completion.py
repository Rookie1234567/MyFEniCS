"""Fail-closed Task033 reduced-scope completion record.

This checker is deliberately separate from the original 21-role full-scope
manifest.  It binds the user-approved reduced scope while preserving the
original Task033 full-scope ``NOT_RUN`` identity.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORD = Path(
    "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/"
    "task033_reduced_scope_completion.json"
)
MANIFEST_PATH = Path(
    "docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/"
    "selective_merge_manifest.csv"
)
TEST_SUMMARY_PATH = Path(
    "docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/"
    "test_summary.md"
)


class ReducedScopeCompletionError(ValueError):
    """Raised when one reduced-scope completion contract fails."""


def _canonical_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(_canonical_bytes(path)).hexdigest()


def _canonical_size(path: Path) -> int:
    return len(_canonical_bytes(path))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReducedScopeCompletionError(
            f"cannot read JSON evidence {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReducedScopeCompletionError(
            f"JSON evidence must be an object: {path}"
        )
    return payload


def _status(expected: str) -> Callable[[dict[str, Any]], bool]:
    return lambda payload: payload.get("status") == expected


JSON_EVIDENCE: tuple[
    tuple[str, Path, Callable[[dict[str, Any]], bool], str], ...
] = (
    (
        "case090_and_qep_tracking",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage1_high_order/stage_summary.json"
        ),
        lambda payload: (
            payload.get("case090", {}).get("all_core_gates_passed") is True
            and payload.get("case090", {}).get("total_pde_count") == 144
            and payload.get("qep_phaseA", {}).get(
                "all_selected_positive_formal_passed"
            )
            is True
        ),
        "Case090 core and selected p3/p4 QEP tracking pass",
    ),
    (
        "phaseB_matched_trace",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage2_matched_trace/phaseB_summary.json"
        ),
        _status("phaseB_p3_p4_matched_trace_pass"),
        "p3/p4 matching trace accepted",
    ),
    (
        "p3_h5_full3d_closure",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage3_p3_h5/full3d_closure_summary.json"
        ),
        _status("same_degree_p3_h5_hybrid_full3d_numerical_closure_pass"),
        "same-degree p3/h5 closure accepted",
    ),
    (
        "p4_resource_negative",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage4_p4_h5/calibration_summary.json"
        ),
        _status("p4_h5_target_solve_not_launched_by_measured_memory_gate"),
        "p4 target is a resource-gated negative",
    ),
    (
        "d1_fixed_p_equal_accuracy",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage5_equal_accuracy/reduced_equal_accuracy_summary.json"
        ),
        _status("fixed_p_equal_accuracy_clear_success_with_qualifications"),
        "p3/h7.5 fixed-p clear success with reference qualifications",
    ),
    (
        "d2_variable_p_capability",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/variable_p_capability_audit.json"
        ),
        _status("not_qualified_fail_closed"),
        "native cellwise variable-p H(curl) remains fail closed",
    ),
    (
        "p3_h5_source_compatibility",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage5_equal_accuracy/source_compatibility_audit.json"
        ),
        lambda payload: payload.get("compatible") is True,
        "p3/h5 direct-to-Hybrid numerical source compatible",
    ),
    (
        "d1_source_compatibility",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/stage5_equal_accuracy/d1_source_compatibility_audit.json"
        ),
        _status("d1_source_splits_numerically_compatible"),
        "p3/h10 and p3/h7.5 D1 source splits are descriptor-only",
    ),
    (
        "original_full_scope_not_run",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/formal_evidence_manifest_NOT_RUN.json"
        ),
        lambda payload: (
            payload.get("status") == "not_run"
            and payload.get("identity", {}).get("claims_task033_complete")
            is False
        ),
        "original 21-role full scope remains NOT_RUN",
    ),
    (
        "one_tib_projection_not_qualified",
        Path(
            "benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/"
            "records/one_tib_projection_plan.json"
        ),
        _status("not_qualified"),
        "old 1 TiB projection is not a feasibility claim",
    ),
)

REQUIRED_EXCLUDES = {
    "benchmarks/run_task033_adaptive_mesh.py",
    "src/geometry/task033_periodic_graded_mesh.py",
    "src/test/test_55_task033_periodic_graded_mesh.py",
    "benchmarks/run_task033_one_tib_projection.py",
    "benchmarks/task033_one_tib_projection.py",
    "benchmarks/scripts/run_task033_formal.ps1",
    "src/test/test_64_task033_campaign_script.py",
}


def _manifest_contract(path: Path, *, root: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise ReducedScopeCompletionError(
            f"cannot read selective merge manifest: {exc}"
        ) from exc
    if not rows or "path" not in rows[0] or "decision" not in rows[0]:
        raise ReducedScopeCompletionError(
            "selective merge manifest lacks path/decision rows"
        )
    invalid_exact_paths = sorted(
        {
            str(row.get("path", ""))
            for row in rows
            if any(
                token in str(row.get("path", ""))
                for token in ("*", "?", "[", "]", ";")
            )
        }
    )
    if invalid_exact_paths:
        raise ReducedScopeCompletionError(
            "manifest contains non-exact paths: "
            + ", ".join(invalid_exact_paths)
        )
    include_paths = [
        str(row["path"])
        for row in rows
        if row.get("decision") == "include"
    ]
    exclude_paths = {
        str(row["path"])
        for row in rows
        if row.get("decision") == "exclude"
    }
    # The completion record declares itself in the merge manifest.  It cannot
    # exist before the first deterministic build, so permit only that one
    # bootstrap path to be absent.  Verification after generation still binds
    # the tracked record through exact equality.
    self_record = DEFAULT_RECORD.as_posix()
    missing_includes = sorted(
        path
        for path in include_paths
        if path != self_record and not (root / path).is_file()
    )
    if self_record not in include_paths:
        raise ReducedScopeCompletionError(
            "manifest does not include the reduced-scope completion record"
        )
    if missing_includes:
        raise ReducedScopeCompletionError(
            "manifest includes missing files: " + ", ".join(missing_includes)
        )
    missing_required_excludes = sorted(REQUIRED_EXCLUDES - exclude_paths)
    if missing_required_excludes:
        raise ReducedScopeCompletionError(
            "manifest misses required exclusions: "
            + ", ".join(missing_required_excludes)
        )
    return {
        "row_count": len(rows),
        "include_count": len(include_paths),
        "exclude_count": len(exclude_paths),
        "all_paths_file_level_exact": True,
        "missing_include_paths": missing_includes,
        "required_excludes_present": sorted(REQUIRED_EXCLUDES),
    }


def build_reduced_scope_completion(
    *, repo_root: Path | str = ROOT
) -> dict[str, Any]:
    """Build a deterministic, hash-bound reduced-scope completion record."""

    root = Path(repo_root).resolve()
    evidence: dict[str, Any] = {}
    for name, relative, validator, interpretation in JSON_EVIDENCE:
        path = root / relative
        payload = _load_json(path)
        if not validator(payload):
            raise ReducedScopeCompletionError(
                f"{name} does not satisfy its accepted status contract"
            )
        evidence[name] = {
            "path": relative.as_posix(),
            "sha256": _sha256(path),
            "bytes": _canonical_size(path),
            "record_type": payload.get("record_type"),
            "status": payload.get("status"),
            "accepted_interpretation": interpretation,
        }

    manifest_path = root / MANIFEST_PATH
    test_summary_path = root / TEST_SUMMARY_PATH
    manifest = _manifest_contract(manifest_path, root=root)
    test_summary = test_summary_path.read_text(encoding="utf-8")
    if "F0_MERGE_VALIDATION = PASS" not in test_summary:
        raise ReducedScopeCompletionError(
            "test summary lacks the F0 merge validation marker"
        )
    evidence["selective_merge_manifest"] = {
        "path": MANIFEST_PATH.as_posix(),
        "sha256": _sha256(manifest_path),
        "bytes": _canonical_size(manifest_path),
        **manifest,
    }
    evidence["test_summary"] = {
        "path": TEST_SUMMARY_PATH.as_posix(),
        "sha256": _sha256(test_summary_path),
        "bytes": _canonical_size(test_summary_path),
        "f0_merge_validation_pass": True,
    }

    record: dict[str, Any] = {
        "schema_version": "task033.reduced-scope-completion.v1",
        "record_type": "task033_reduced_scope_completion",
        "status": "task033_reduced_scope_complete",
        "review_authority": (
            "docs/task033_high_order_floquet_hybrid_hp_adaptivity/"
            "review_report_v6.md"
        ),
        "hash_policy": (
            "sha256_and_bytes_of_utf8_text_after_lf_line_ending_canonicalization"
        ),
        "identity": {
            "is_pde_run": False,
            "is_solver_pass": False,
            "task033_reduced_scope_complete": True,
            "original_task033_full_scope_complete": False,
            "adaptive_transferred_to_next_task": True,
            "ordinary_default_changed": False,
            "proves_0p7nm_feasible": False,
        },
        "scope_dispositions": {
            "p2_h5_conforming_graded_h": "transferred_to_next_task",
            "p2_h3_adaptive_compression": "transferred_to_next_task",
            "adaptive_measured_compression": "transferred_to_next_task",
            "one_tib_0p7nm_update": (
                "transferred_to_adaptive_scalability_task"
            ),
            "interface_buffer_sweep": (
                "deferred_until_defect_or_nonuniform_end_geometry"
            ),
            "p4_target": "resource_gated_until_new_candidate_specific_gate",
            "p3_h3": "not_required_in_task033_reduced_scope",
            "variable_p_target_prototype": (
                "not_required_by_capability_gate"
            ),
        },
        "evidence": evidence,
        "checks": {
            "all_required_evidence_statuses_accepted": True,
            "all_evidence_hashes_recorded": True,
            "tracked_text_hashes_checkout_independent": True,
            "selective_merge_manifest_file_level_exact": True,
            "adaptive_transfer_explicit": True,
            "original_full_scope_not_upgraded": True,
            "ordinary_default_unchanged": True,
        },
        "failures": [],
    }
    canonical = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    record["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return record


def verify_reduced_scope_completion(
    record_path: Path | str = DEFAULT_RECORD,
    *,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Rebuild the record and require exact equality with the tracked copy."""

    root = Path(repo_root).resolve()
    requested = Path(record_path)
    path = requested if requested.is_absolute() else root / requested
    stored = _load_json(path)
    rebuilt = build_reduced_scope_completion(repo_root=root)
    if stored != rebuilt:
        raise ReducedScopeCompletionError(
            "tracked reduced-scope completion record is stale or modified"
        )
    return {
        "status": "task033_reduced_scope_completion_verified",
        "verified": True,
        "record_path": path.relative_to(root).as_posix(),
        "record_sha256": _sha256(path),
        "payload_sha256": stored["payload_sha256"],
    }


__all__ = [
    "DEFAULT_RECORD",
    "ReducedScopeCompletionError",
    "build_reduced_scope_completion",
    "verify_reduced_scope_completion",
]
