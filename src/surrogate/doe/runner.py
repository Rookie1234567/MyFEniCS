"""Task005 M1 campaign runner and production-step audit orchestration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
from typing import Any

from .design import (
    ANGLE_CANDIDATES, AUDIT_ANGLE_IDS, FORWARD_SOLVER_SHA, H0, W0,
    MODEL_ID, ROUTE_ID, build_m0_artifacts,
)
from .sensitivity import build_step_audit, write_json


SURROGATE_ROOT = Path(__file__).resolve().parents[3]
FORWARD_ROOT = Path("/home/shenjh/Projects/MyFEniCS-forward-fdf9615")
CASE_ID = "task005_m1_audit_v1"
STATES = ("H-", "H+", "W-", "W+")
STEPS = {"coarse": {"delta_h_nm": 2.5, "delta_w_nm": 0.5},
         "half": {"delta_h_nm": 1.25, "delta_w_nm": 0.25}}


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _angle_map() -> dict[str, tuple[float, float]]:
    return {row[0]: (float(row[1]), float(row[2])) for row in ANGLE_CANDIDATES}


def _state_geometry(step: str, state: str) -> tuple[float, float]:
    delta = STEPS[step]
    return {
        "H-": (H0 - delta["delta_h_nm"], W0),
        "H+": (H0 + delta["delta_h_nm"], W0),
        "W-": (H0, W0 - delta["delta_w_nm"]),
        "W+": (H0, W0 + delta["delta_w_nm"]),
    }[state]


def _load_nominal_records(train_dir: Path) -> dict[str, dict[str, Any]]:
    rows = [json.loads(line) for line in (train_dir / "sample_records.jsonl").read_text().splitlines() if line.strip()]
    result: dict[str, dict[str, Any]] = {}
    angles = _angle_map()
    for row in rows:
        inputs = row.get("inputs", [])
        for angle_id, (grazing, azimuth) in angles.items():
            if inputs == [H0, W0, grazing, azimuth]:
                result[angle_id] = row
    if set(result) != set(angles):
        raise RuntimeError("nominal train112 records do not cover the frozen audit angles")
    return result


def _expected_rows(*, artifact_root: Path) -> dict[str, dict[str, Any]]:
    angle_map = _angle_map()
    rows: dict[str, dict[str, Any]] = {}
    index = 0
    for angle_id in AUDIT_ANGLE_IDS:
        grazing, azimuth = angle_map[angle_id]
        for step in STEPS:
            h, w = _state_geometry(step, "H-")
            # The directory/index is deterministic but the actual state value
            # is filled below for each state.
            for state in STATES:
                h, w = _state_geometry(step, state)
                key = f"{angle_id}/{step}/{state}"
                rows[key] = {
                    "key": key, "angle_id": angle_id, "step": step, "state": state,
                    "design_index": index, "grazing_deg": grazing, "azimuth_deg": azimuth,
                    "height_nm": h, "width_nm": w,
                    "run_directory": str((artifact_root / "m1" / angle_id / step / state).resolve()),
                    "status": "reserved", "attempted": False,
                }
                index += 1
    return rows


def _command(*, root: Path, driver: Path, row: dict[str, Any], baseline_sha: str,
             timeout_seconds: float) -> str:
    values = {
        "root": root, "driver": driver,
        "baseline": baseline_sha, "run": Path(row["run_directory"]),
    }
    args = [
        "python", str(driver), "--forward-root", str(root),
        "--baseline-sha", baseline_sha, "--run-directory", str(Path(row["run_directory"])),
        "--height", str(row["height_nm"]), "--width", str(row["width_nm"]),
        "--grazing", str(row["grazing_deg"]), "--azimuth", str(row["azimuth_deg"]),
        "--design-id", CASE_ID, "--design-index", str(row["design_index"]),
        "--timeout-seconds", str(timeout_seconds),
    ]
    # Activate from the surrogate repository.  The forward worktree is a
    # read-only SHA worktree whose branch name is intentionally different and
    # therefore must not be passed through the surrogate branch guard.
    return "cd " + shlex.quote(str(SURROGATE_ROOT)) + " && source scripts/activate_myfenics_surrogate_wsl.sh && " + " ".join(shlex.quote(item) for item in args)


def _run_with_heartbeat(command: str, *, cwd: Path, log_path: Path,
                        label: str, heartbeat_seconds: float = 30.0,
                        phase: str = "M1") -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            ["bash", "-lc", command], cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        start = time.monotonic(); next_heartbeat = start + heartbeat_seconds
        while True:
            return_code = process.poll()
            if return_code is not None:
                return int(return_code)
            now = time.monotonic()
            if now >= next_heartbeat:
                elapsed = now - start
                print(f"{phase} heartbeat {label}: process alive, elapsed={elapsed:.0f}s", flush=True)
                next_heartbeat = now + heartbeat_seconds
            time.sleep(1.0)


def run_m1(*, outcomes_dir: Path, train_dir: Path, artifact_root: Path,
           forward_root: Path = FORWARD_ROOT, timeout_seconds: float = 1800.0,
           resume: bool = True) -> dict[str, Any]:
    """Run the exact 40-state M1 campaign, stopping at the first failure."""

    outcomes_dir.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)
    manifest_path = outcomes_dir / "M1_AUDIT_CAMPAIGN.json"
    rows = _expected_rows(artifact_root=artifact_root)
    payload = {
        "schema_version": "task005.m1-audit-campaign.v1",
        "campaign_id": CASE_ID, "forward_solver_sha": FORWARD_SOLVER_SHA,
        "model_id": MODEL_ID, "solver_route_id": ROUTE_ID,
        "mumps_icntl_14": 40, "mpi_ranks": 2, "threads_per_rank": 1,
        "max_new_fem": 40, "new_fem_count": 0,
        "audit_angle_ids": list(AUDIT_ANGLE_IDS), "steps": STEPS,
        "states": list(STATES), "status": "reserved", "stop_reason": None,
        "validation_target_accessed": False, "records": rows,
    }
    if manifest_path.is_file() and resume:
        old = json.loads(manifest_path.read_text())
        if old.get("campaign_id") != CASE_ID or old.get("forward_solver_sha") != FORWARD_SOLVER_SHA:
            raise RuntimeError("existing M1 manifest has incompatible identity")
        payload.update({key: old.get(key, value) for key, value in payload.items()})
        # Preserve the exact reserved design table while allowing an interrupted
        # campaign to resume from measured_pass records.
        payload["records"] = old.get("records", rows)
        payload["new_fem_count"] = int(old.get("new_fem_count", 0))
    _write(manifest_path, payload)

    # M0 is rechecked before any subprocess capable of launching MPI.
    checker = SURROGATE_ROOT / "benchmarks/cases/131_task005_design_and_step_audit/checker.py"
    checker_cmd = "cd " + shlex.quote(str(SURROGATE_ROOT)) + " && source scripts/activate_myfenics_surrogate_wsl.sh && python " + shlex.quote(str(checker))
    checker_result = subprocess.run(["bash", "-lc", checker_cmd], cwd=SURROGATE_ROOT,
                                    capture_output=True, text=True, check=False)
    (outcomes_dir / "M0_checker_stdout.txt").write_text(checker_result.stdout + checker_result.stderr)
    if checker_result.returncode != 0:
        payload["status"] = "controlled_stop"
        payload["stop_reason"] = "M0_checker_failed"
        _write(manifest_path, payload)
        raise RuntimeError("Task005 M0 checker failed; M1 was not launched")

    driver = SURROGATE_ROOT / "src/surrogate/doe/forward_driver.py"
    preflight_cmd = "cd " + shlex.quote(str(SURROGATE_ROOT)) + " && source scripts/activate_myfenics_surrogate_wsl.sh && python " + shlex.quote(str(driver)) + " --forward-root " + shlex.quote(str(forward_root)) + " --baseline-sha " + FORWARD_SOLVER_SHA + " --run-directory " + shlex.quote(str(artifact_root / "preflight")) + " --preflight-only"
    preflight = subprocess.run(["bash", "-lc", preflight_cmd], cwd=SURROGATE_ROOT,
                               capture_output=True, text=True, check=False)
    (outcomes_dir / "M1_RESOURCE_PREFLIGHT.txt").write_text(preflight.stdout + preflight.stderr)
    if preflight.returncode != 0:
        payload["status"] = "controlled_stop"
        payload["stop_reason"] = "forward_preflight_failed"
        _write(manifest_path, payload)
        raise RuntimeError("forward preflight failed; M1 FEM was not launched")

    nominal = _load_nominal_records(train_dir)
    for key, row in payload["records"].items():
        if row.get("status") == "measured_pass" and resume:
            sample = Path(row["run_directory"]) / "task005_production_sample.json"
            if sample.is_file():
                continue
            row["status"] = "reserved"
        print(f"M1 start {key}: h={row['height_nm']} w={row['width_nm']} g={row['grazing_deg']} a={row['azimuth_deg']}", flush=True)
        row["attempted"] = True
        row["attempt_number"] = int(row.get("attempt_number", 0)) + 1
        row["status"] = "running"
        _write(manifest_path, payload)
        command = _command(root=forward_root, driver=driver, row=row,
                           baseline_sha=FORWARD_SOLVER_SHA, timeout_seconds=timeout_seconds)
        # Keep the watchdog log outside the run directory.  The formal
        # forward helper intentionally requires that directory not to exist
        # before it creates its own parameters/results tree.
        log_name = key.replace("/", "__").replace("+", "plus").replace("-", "minus") + ".log"
        log_path = artifact_root / "m1_logs" / log_name
        return_code = _run_with_heartbeat(command, cwd=forward_root, log_path=log_path, label=key)
        summary_path = Path(row["run_directory"]) / "task005_driver_summary.json"
        summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
        row.update({
            "return_code": return_code, "status": summary.get("status", "failed_runner"),
            "formal_record_path": summary.get("formal_record_path"),
            "sample_path": summary.get("sample_path"),
            "formal_record_sha256": summary.get("formal_record_sha256"),
            "execution_sha256": summary.get("execution_sha256"),
            "watchdog": summary.get("watchdog"),
            "source_sha": summary.get("source_sha"),
        })
        payload["new_fem_count"] = int(payload.get("new_fem_count", 0)) + 1
        _write(manifest_path, payload)
        if return_code != 0 or row["status"] != "measured_pass":
            payload["status"] = "controlled_stop"
            payload["stop_reason"] = f"first_unexplained_failure:{key}:{row['status']}"
            _write(manifest_path, payload)
            print(f"M1 STOP {payload['stop_reason']}", flush=True)
            return payload

    records_by_key: dict[str, dict[str, Any]] = {}
    for key, row in payload["records"].items():
        path = Path(row["sample_path"])
        if not path.is_file():
            payload["status"] = "controlled_stop"
            payload["stop_reason"] = f"missing_sample:{key}"
            _write(manifest_path, payload)
            return payload
        records_by_key[key] = json.loads(path.read_text())
    audit = build_step_audit(nominal_by_angle=nominal, records_by_key=records_by_key)
    write_json(outcomes_dir / "FINITE_DIFFERENCE_STEP_AUDIT.json", audit)
    md_lines = [
        "# Task005 M1 finite-difference step audit", "",
        f"Status: **{audit['status']}**", "",
        "The audit compares noise-whitened central derivatives from coarse and half steps. "
        "N1/N2 are provisional diagonal DOE scenarios, not calibrated experimental covariance.", "",
        "| contract/parameter | passing audit angles | gate |", "|---|---:|---|",
    ]
    for key, value in audit["angle_gate"].items():
        md_lines.append(f"| {key} | {value['pass_count']}/5 | {value['at_least_4_of_5']} |")
    md_lines += ["", "Failure reasons:", ""] + [f"- `{item}`" for item in audit["failure_reasons"]]
    (outcomes_dir / "FINITE_DIFFERENCE_STEP_AUDIT.md").write_text("\n".join(md_lines) + "\n")
    payload["status"] = "pass" if audit["status"] == "pass" else "controlled_stop"
    payload["stop_reason"] = None if audit["status"] == "pass" else "finite_difference_gate_failed"
    payload["audit_status"] = audit["status"]
    payload["production_step_recommendation"] = audit.get("production_step_recommendation")
    _write(manifest_path, payload)
    if audit["status"] == "pass":
        lock = {
            "schema_version": "task005.production-step-lock.v1",
            "status": "frozen", "forward_solver_sha": FORWARD_SOLVER_SHA,
            "audit_sha256": __import__("hashlib").sha256((outcomes_dir / "FINITE_DIFFERENCE_STEP_AUDIT.json").read_bytes()).hexdigest(),
            "selected_steps": audit["production_step_recommendation"],
            "method": "central finite differences; Richardson retained diagnostic-only",
            "audit_angle_ids": list(AUDIT_ANGLE_IDS), "new_fem_count": payload["new_fem_count"],
        }
        write_json(outcomes_dir / "PRODUCTION_STEP_LOCK.json", lock)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, default=SURROGATE_ROOT / "surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/outcomes")
    parser.add_argument("--train-dir", type=Path, default=SURROGATE_ROOT / "benchmarks/artifacts/cases/127_task004_active_learning_round1/train112")
    parser.add_argument("--artifact-root", type=Path, default=SURROGATE_ROOT / "benchmarks/artifacts/cases/131_task005_design_and_step_audit")
    parser.add_argument("--forward-root", type=Path, default=FORWARD_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    result = run_m1(outcomes_dir=args.outcomes.resolve(), train_dir=args.train_dir.resolve(),
                    artifact_root=args.artifact_root.resolve(), forward_root=args.forward_root.resolve(),
                    timeout_seconds=args.timeout_seconds, resume=not args.no_resume)
    print(json.dumps({"status": result.get("status"), "stop_reason": result.get("stop_reason"),
                      "new_fem_count": result.get("new_fem_count")}, indent=2))
    return 0 if result.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
