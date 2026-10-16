"""Independent full-A6 and identity checker for the Task41 P0 A1 result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from src.geometry.task41_phi90_profile import task41_direct_summary_errors
from src.io import load_and_resolve
from src.runners.task41_p0_contract import (
    require_task41_p0_contract,
    sha256_file,
    validate_task41_specification,
)

CHECKER_SCHEMA = "task41.p0.direct_checker.v1"


def evaluate_task41_numerical_summary(
    summary: Mapping[str, Any], numerical_output_directory: str | Path
) -> list[str]:
    """Recompute Task41 native full-space A6, recovery, MUMPS, and energy gates."""
    return task41_direct_summary_errors(summary, numerical_output_directory)


def _json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def check_task41_p0(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_output: Path,
    contract_path: Path,
    contract_sha256: str,
    output_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    contract, contract_digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=True,
        require_clean_source=True,
    )
    case = contract["case"]
    source_sha = contract["source"]["sha"]
    specification = load_and_resolve(input_path)
    validate_task41_specification(
        specification, input_path, contract, current_root=repo_root
    )
    input_path = input_path.resolve()
    summary_path = summary_path.resolve()
    manifest_path = manifest_path.resolve()
    numerical_output = numerical_output.resolve()
    output_path = output_path.resolve()
    if input_path != (repo_root / case["input_path"]).resolve():
        raise ValueError("checker input path differs from the frozen Task41 DAT")
    if summary_path.parent != manifest_path.parent:
        raise ValueError("run summary and manifest do not share the same run directory")
    manifest = _json_object(manifest_path, "run manifest")
    launcher_summary = _json_object(summary_path, "launcher summary")
    output_summary_path = numerical_output / "run_summary.json"
    output_summary = _json_object(output_summary_path, "full numerical summary")
    run_directory = summary_path.parent
    expected_output_dir = Path(str(manifest.get("output_directory", ""))).resolve()
    expected_numerical_output = Path(
        str(manifest.get("numerical_output_directory", ""))
    ).resolve()
    if (
        summary_path != run_directory / "run_summary.json"
        or manifest_path != run_directory / "run_manifest.json"
        or expected_output_dir != run_directory
        or expected_numerical_output != numerical_output
        or Path(str(launcher_summary.get("output_directory", ""))).resolve() != run_directory
        or Path(str(launcher_summary.get("numerical_output_directory", ""))).resolve()
        != numerical_output
        or launcher_summary.get("run_id") != case["run_id"]
    ):
        raise ValueError("persisted run summary, manifest, and numerical-output paths disagree")
    expected_manifest = {
        "model_id": case["model_id"],
        "run_id": case["run_id"],
        "method": case["method"],
        "mpi_size": case["mpi_size"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "source_sha": source_sha,
    }
    identity_errors = [
        f"run manifest {key} differs from the Task41 contract"
        for key, expected in expected_manifest.items()
        if manifest.get(key) != expected
    ]
    copied_input = run_directory / "input_original.dat"
    resolved_config = run_directory / "resolved_config.json"
    if not copied_input.is_file() or sha256_file(copied_input) != case["input_sha256"]:
        identity_errors.append("copied original DAT is missing or has a different hash")
    if (
        not resolved_config.is_file()
        or hashlib.sha256(resolved_config.read_bytes()).hexdigest()
        != case["resolved_config_sha256"]
    ):
        identity_errors.append("saved resolved configuration is missing or has a different hash")
    numerical_errors = evaluate_task41_numerical_summary(output_summary, numerical_output)
    errors = identity_errors + numerical_errors
    passed = not errors
    payload = {
        "schema": CHECKER_SCHEMA,
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if passed else "FAIL",
        "checker_passed": passed,
        "full_pass": passed,
        "official_result": passed,
        "task_id": contract["task_id"],
        "run_id": case["run_id"],
        "source_sha": source_sha,
        "contract_sha256": contract_digest,
        "window_path": str((repo_root / contract["window"]["path"]).resolve()),
        "window_sha256": contract["window"]["sha256"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "run_manifest_sha256": sha256_file(manifest_path),
        "launcher_summary_sha256": sha256_file(summary_path),
        "numerical_summary_sha256": sha256_file(output_summary_path),
        "launcher_result_classification": launcher_summary.get("result_classification"),
        "errors": errors,
        "raw_evidence_retained": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--numerical-output", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    try:
        result = check_task41_p0(
            input_path=args.input,
            summary_path=args.summary,
            manifest_path=args.manifest,
            numerical_output=args.numerical_output,
            contract_path=args.contract,
            contract_sha256=args.contract_sha256,
            output_path=args.output,
            repo_root=root,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        result = {
            "schema": CHECKER_SCHEMA,
            "status": "FAIL",
            "checker_passed": False,
            "full_pass": False,
            "official_result": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "raw_evidence_retained": True,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("checker_passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
