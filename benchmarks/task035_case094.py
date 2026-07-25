"""Hermetic Phase A validation for Task035 Case094.

The default validation path only reads tracked descriptors.  Ignored heavy
artifacts are inspected exclusively when ``--verify-artifacts`` is requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    ROOT
    / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/base_manifest.json"
)
DEFAULT_CONFIG = (
    ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/config.json"
)
DEFAULT_EXPECTED = (
    ROOT / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/expected.json"
)
DEFAULT_SUCCESSOR_BINDINGS = (
    ROOT
    / "benchmarks/cases/095_high_order_local_hp_resource_envelope/records"
    / "task035b_successor_bindings.json"
)
REQUIRED_BASELINE_ROLES = {
    "p4_h5_full3d",
    "p4_h5_hybrid_m160",
    "p4_h5_hybrid_funnel",
    "p3_h3_full3d",
    "p3_h3_hybrid_m160",
    "p3_h3_hybrid_funnel",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(path_value: Any, repo_root: Path) -> Path:
    path = Path(str(path_value))
    return path if path.is_absolute() else repo_root / path


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _validate_tracked_bindings(
    bindings: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path,
    label: str,
    approved_successors: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    failures: list[str] = []
    successor_results: list[dict[str, Any]] = []
    for index, binding in enumerate(bindings):
        path = _repo_path(binding.get("path"), repo_root)
        expected = binding.get("sha256")
        item = f"{label}[{index}]"
        if not _valid_sha256(expected):
            failures.append(f"{item}:invalid_sha256")
        elif not path.is_file():
            failures.append(f"{item}:tracked_file_missing")
        else:
            actual = _sha256(path)
            if actual == expected:
                continue
            matches = [
                replacement
                for replacement in approved_successors
                if replacement.get("binding_group") == label
                and replacement.get("binding_index") == index
                and replacement.get("path") == binding.get("path")
                and replacement.get("predecessor_sha256") == expected
                and replacement.get("successor_sha256") == actual
            ]
            if len(matches) != 1:
                failures.append(f"{item}:tracked_hash_mismatch")
                continue
            successor_results.append(
                {
                    "binding": item,
                    "path": str(binding.get("path")),
                    "status": "approved_successor_hash_match",
                    "predecessor_sha256": expected,
                    "current_sha256": actual,
                    "introduced_by_commit": matches[0].get(
                        "introduced_by_commit"
                    ),
                }
            )
    return failures, successor_results


def _load_approved_successors(
    *,
    repo_root: Path,
    predecessor_manifest: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Load exact, evidence-bound Task035b replacements for frozen bindings."""

    path = repo_root / DEFAULT_SUCCESSOR_BINDINGS.relative_to(ROOT)
    if not path.is_file():
        return []
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema_version") != "task035b.case095-successor-bindings.v1":
        return []
    if record.get("status") != "active_research_successor_binding":
        return []
    predecessor = record.get("predecessor_manifest", {})
    manifest_path = _repo_path(predecessor.get("path"), repo_root)
    if not manifest_path.is_file():
        return []
    if predecessor.get("sha256") != _sha256(manifest_path):
        return []
    frozen_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        frozen_manifest.get("schema_version")
        != predecessor_manifest.get("schema_version")
        or frozen_manifest.get("source") != predecessor_manifest.get("source")
        or frozen_manifest.get("tracked_bindings")
        != predecessor_manifest.get("tracked_bindings")
    ):
        return []
    evidence = record.get("evidence", [])
    if not isinstance(evidence, list) or not evidence:
        return []
    for item in evidence:
        evidence_path = _repo_path(item.get("path"), repo_root)
        if (
            not evidence_path.is_file()
            or not _valid_sha256(item.get("sha256"))
            or _sha256(evidence_path) != item["sha256"]
        ):
            return []
    replacements = record.get("approved_replacements", [])
    if not isinstance(replacements, list):
        return []
    for replacement in replacements:
        if (
            not isinstance(replacement, Mapping)
            or not _valid_sha256(replacement.get("predecessor_sha256"))
            or not _valid_sha256(replacement.get("successor_sha256"))
            or not isinstance(replacement.get("introduced_by_commit"), str)
            or len(replacement["introduced_by_commit"]) != 40
            or replacement.get("ordinary_default_changed") is not False
        ):
            return []
    return replacements


def validate_base_manifest(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = ROOT,
    verify_artifacts: bool = False,
) -> dict[str, Any]:
    """Recompute Phase A descriptor gates without invoking a solver."""

    failures: list[str] = []
    if manifest.get("schema_version") != "task035.case094.base-manifest.v1":
        failures.append("schema_version")
    if manifest.get("status") != "phase_a_gate_pass":
        failures.append("manifest_status")
    source = manifest.get("source", {})
    base_sha = source.get("task034_final_master_sha")
    if not isinstance(base_sha, str) or len(base_sha) != 40:
        failures.append("task034_final_master_sha")
    if source.get("task035_base_sha") != base_sha:
        failures.append("task035_base_sha")

    bindings = manifest.get("tracked_bindings", {})
    approved_successors = _load_approved_successors(
        repo_root=repo_root,
        predecessor_manifest=manifest,
    )
    successor_binding_results: list[dict[str, Any]] = []
    for key in ("case093_compact_records", "identity_files", "theory_documents"):
        value = bindings.get(key)
        if not isinstance(value, list) or not value:
            failures.append(f"tracked_bindings:{key}")
            continue
        binding_failures, binding_successors = _validate_tracked_bindings(
            value,
            repo_root=repo_root,
            label=key,
            approved_successors=approved_successors,
        )
        failures.extend(binding_failures)
        successor_binding_results.extend(binding_successors)

    artifacts = manifest.get("baseline_artifacts", [])
    roles = {item.get("role") for item in artifacts if isinstance(item, Mapping)}
    if roles != REQUIRED_BASELINE_ROLES:
        failures.append("baseline_artifact_roles")

    artifact_results: list[dict[str, Any]] = []
    for item in artifacts:
        if not isinstance(item, Mapping):
            failures.append("baseline_artifact_entry")
            continue
        role = str(item.get("role"))
        expected = item.get("expected_sha256")
        attested = item.get("observed_sha256")
        if not _valid_sha256(expected) or attested != expected:
            failures.append(f"{role}:descriptor_hash_binding")
        result = {"role": role, "status": "descriptor_only"}
        if verify_artifacts:
            path = _repo_path(item.get("path"), repo_root)
            if not path.is_file():
                result["status"] = "artifact_not_materialized"
                failures.append(f"{role}:artifact_not_materialized")
            else:
                actual = _sha256(path)
                result["actual_sha256"] = actual
                result["status"] = (
                    "materialized_hash_match"
                    if actual == expected
                    else "artifact_hash_mismatch"
                )
                if actual != expected:
                    failures.append(f"{role}:artifact_hash_mismatch")
        artifact_results.append(result)

    environment = manifest.get("environment_qualification", {})
    if environment.get("status") != "environment_gate_pass":
        failures.append("environment_gate")
    if verify_artifacts:
        raw_path = _repo_path(environment.get("raw_json_path"), repo_root)
        raw_hash = environment.get("raw_json_sha256")
        if not raw_path.is_file():
            failures.append("environment:artifact_not_materialized")
        elif not _valid_sha256(raw_hash) or _sha256(raw_path) != raw_hash:
            failures.append("environment:artifact_hash_mismatch")
        else:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            if raw.get("status") != "environment_gate_pass":
                failures.append("environment:raw_status")
            raw_source = raw.get("source", {})
            if raw_source.get("head_before_sha") != base_sha:
                failures.append("environment:head_before_sha")
            if raw_source.get("head_after_sha") != base_sha:
                failures.append("environment:head_after_sha")

    declared_gates = manifest.get("gates", {})
    for gate in (
        "environment",
        "source_and_abi",
        "baseline_binding",
        "required_artifacts",
        "ordinary_checker_hermetic",
        "full_regression",
    ):
        if declared_gates.get(gate) is not True:
            failures.append(f"declared_gate:{gate}")

    return {
        "status": "phase_a_gate_pass" if not failures else "phase_a_gate_fail",
        "verify_artifacts": verify_artifacts,
        "failures": failures,
        "artifact_results": artifact_results,
        "successor_binding_results": successor_binding_results,
    }


def check_base_manifest(
    manifest_path: str | Path = DEFAULT_MANIFEST,
    *,
    verify_artifacts: bool = False,
) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return validate_base_manifest(
        manifest,
        repo_root=ROOT,
        verify_artifacts=verify_artifacts,
    )


def check_case094(
    config_path: str | Path = DEFAULT_CONFIG,
    expected_path: str | Path = DEFAULT_EXPECTED,
) -> dict[str, Any]:
    """Validate the compact Review-V6 authority without running a PDE."""

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    expected = json.loads(Path(expected_path).read_text(encoding="utf-8"))
    failures: list[str] = []
    if config.get("schema_version") != "task035.case094.compact-authority.v2":
        failures.append("config_schema")
    if expected.get("schema_version") != "task035.case094.compact-expected.v2":
        failures.append("expected_schema")
    for key in (
        "status",
        "canonical",
        "production_qualified",
        "pde_run",
        "ordinary_default_changed",
    ):
        if config.get(key) != expected.get(key):
            failures.append(f"expected_mismatch:{key}")
    if config.get("ordinary_default_changed") is not False:
        failures.append("ordinary_default_changed")

    records = config.get("authority_records")
    if not isinstance(records, list) or len(records) != expected.get(
        "authority_record_count"
    ):
        failures.append("authority_record_count")
        records = []
    record_results: list[dict[str, Any]] = []
    for index, item in enumerate(records):
        path = _repo_path(item.get("path"), ROOT)
        result = {"path": str(item.get("path")), "status": "fail"}
        if not path.is_file():
            failures.append(f"record[{index}]:missing")
        elif not _valid_sha256(item.get("sha256")):
            failures.append(f"record[{index}]:invalid_sha256")
        elif _sha256(path) != item["sha256"]:
            failures.append(f"record[{index}]:hash_mismatch")
        else:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("status") != item.get("expected_status"):
                failures.append(f"record[{index}]:status_mismatch")
            else:
                result["status"] = "hash_and_status_match"
        record_results.append(result)

    # The compact authority intentionally excludes most frozen Task035 raw
    # bindings.  Its default checker validates the retained base manifest as
    # one exact hash/status-bound historical record and must not reopen the
    # legacy dependency closure.  Users can still request that independent,
    # larger audit explicitly with ``--manifest``/``--verify-artifacts``.
    base_manifest_status = (
        records[0].get("expected_status") if records else None
    )
    status = (
        "case094_compact_authority_pass"
        if not failures
        else "case094_compact_authority_fail"
    )
    return {
        "status": status,
        "failures": failures,
        "authority_record_count": len(records),
        "record_results": record_results,
        "base_manifest_status": base_manifest_status,
        "starts_pde": False,
        "reads_ignored_artifacts": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--verify-artifacts", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = (
        check_base_manifest(
            args.manifest,
            verify_artifacts=args.verify_artifacts,
        )
        if args.manifest is not None or args.verify_artifacts
        else check_case094()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return (
        0
        if result["status"]
        in {"phase_a_gate_pass", "case094_compact_authority_pass"}
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
