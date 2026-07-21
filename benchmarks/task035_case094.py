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
) -> list[str]:
    failures: list[str] = []
    for index, binding in enumerate(bindings):
        path = _repo_path(binding.get("path"), repo_root)
        expected = binding.get("sha256")
        item = f"{label}[{index}]"
        if not _valid_sha256(expected):
            failures.append(f"{item}:invalid_sha256")
        elif not path.is_file():
            failures.append(f"{item}:tracked_file_missing")
        elif _sha256(path) != expected:
            failures.append(f"{item}:tracked_hash_mismatch")
    return failures


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
    source = manifest.get("source", {})
    base_sha = source.get("task034_final_master_sha")
    if not isinstance(base_sha, str) or len(base_sha) != 40:
        failures.append("task034_final_master_sha")
    if source.get("task035_base_sha") != base_sha:
        failures.append("task035_base_sha")

    bindings = manifest.get("tracked_bindings", {})
    for key in ("case093_compact_records", "identity_files", "theory_documents"):
        value = bindings.get(key)
        if not isinstance(value, list) or not value:
            failures.append(f"tracked_bindings:{key}")
            continue
        failures.extend(
            _validate_tracked_bindings(value, repo_root=repo_root, label=key)
        )

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
    ):
        if declared_gates.get(gate) is not True:
            failures.append(f"declared_gate:{gate}")

    return {
        "status": "phase_a_gate_pass" if not failures else "phase_a_gate_fail",
        "verify_artifacts": verify_artifacts,
        "failures": failures,
        "artifact_results": artifact_results,
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


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--verify-artifacts", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = check_base_manifest(
        args.manifest,
        verify_artifacts=args.verify_artifacts,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "phase_a_gate_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
