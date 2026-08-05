"""Run the only authorized Task006 blind retries (two fresh processes/tuple)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FORWARD_ROOT = Path("/tmp/MyFEniCS-forward-fdf9615-verified")
OUTCOMES = ROOT / "surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes"
CASE143 = ROOT / "benchmarks/cases/143_task006_blind_retry_preflight/records/case143_check.json"
PLAN = OUTCOMES / "BLIND_RETRY_PLAN.json"
LOCK = OUTCOMES / "TASK006_MODEL_SELECTION_LOCK.json"
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/cases/144_task006_blind_retry_requalification"
MANIFEST = ARTIFACT_ROOT / "BLIND_RETRY_CAMPAIGN.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def response_vector(sample: dict[str, Any]) -> dict[str, Any]:
    orders = []
    for order in sample["mother_response"]["orders"]:
        components = order.get("components", {})
        orders.append({
            "side": order.get("side"), "m": int(order.get("m")), "n": int(order.get("n")),
            "power_carrying": bool(order.get("power_carrying")),
            "order_total_power": (None if order.get("order_total_power") is None else float(order["order_total_power"])),
            "s": {key: (None if components.get("s", {}).get(key) is None else float(components["s"][key]))
                  for key in ("amplitude_re", "amplitude_im", "power")},
            "p": {key: (None if components.get("p", {}).get(key) is None else float(components["p"][key]))
                  for key in ("amplitude_re", "amplitude_im", "power")},
        })
    return {"aggregates": {key: float(sample["aggregates"][key]) for key in ("R_total", "T_total", "A_balance")},
            "orders": orders}


def command(item: dict[str, Any], attempt: int, run_directory: Path) -> list[str]:
    return [str(ROOT / ".venv/bin/python"), str(ROOT / "src/surrogate/doe/forward_driver.py"),
            "--forward-root", str(FORWARD_ROOT), "--baseline-sha", "fdf961545f217d620e22800f2704ae9913a6d270",
            "--run-directory", str(run_directory), "--height", "117.5", "--width", "17.25",
            "--grazing", str(item["grazing_deg"]), "--azimuth", str(item["azimuth_deg"]),
            "--design-id", "task006_fixed_A05_A07_A09_hw_blind12_v1", "--design-index", str(item["original_design_index"]),
            "--split", "blind", "--sample-name", "task006_production_sample.json", "--timeout-seconds", "1800"]


def run_one(item: dict[str, Any], attempt: int) -> dict[str, Any]:
    run_directory = ARTIFACT_ROOT / "blind_retry" / "117.5_17.25" / item["angle_id"] / f"attempt_{attempt}"
    if run_directory.exists():
        raise RuntimeError(f"retry run directory already exists: {run_directory}")
    log = ARTIFACT_ROOT / "retry_logs" / f"117.5_17.25__{item['angle_id']}__attempt_{attempt}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command(item, attempt, run_directory), cwd=ROOT, env=env,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        started = time.monotonic()
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if int(elapsed) % 30 == 0:
                print(f"retry heartbeat {item['key']} attempt_{attempt}: elapsed={elapsed:.0f}s", flush=True)
            time.sleep(1.0)
        code = int(process.returncode)
    summary_path = run_directory / "task005_driver_summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    formal_path = run_directory / "results/task002_full3d_record.json"
    sample_path = run_directory / "task006_production_sample.json"
    sample = json.loads(sample_path.read_text()) if sample_path.is_file() else None
    return {
        "key": item["key"], "angle_id": item["angle_id"], "attempt": attempt,
        "run_directory": str(run_directory.resolve()), "log_path": str(log.resolve()),
        "return_code": code, "status": summary.get("status", "failed_runner"),
        "sample_path": str(sample_path.resolve()) if sample is not None else None,
        "formal_record_path": str(formal_path.resolve()) if formal_path.is_file() else None,
        "formal_record_sha256": sha(formal_path) if formal_path.is_file() else None,
        "execution_sha256": sha(run_directory / "execution.json") if (run_directory / "execution.json").is_file() else None,
        "sample_sha256": sha(sample_path) if sample is not None else None,
        "source_sha": summary.get("source_sha"),
        "response": response_vector(sample) if sample is not None and summary.get("status") == "measured_pass" else None,
    }


def response_consistent(left: dict[str, Any], right: dict[str, Any], tol: float = 1.0e-10) -> bool:
    if left["aggregates"].keys() != right["aggregates"].keys():
        return False
    if any(abs(left["aggregates"][key] - right["aggregates"][key]) > tol for key in left["aggregates"]):
        return False
    if len(left["orders"]) != len(right["orders"]):
        return False
    for a, b in zip(left["orders"], right["orders"]):
        if (a["side"], a["m"], a["n"], a["power_carrying"]) != (b["side"], b["m"], b["n"], b["power_carrying"]):
            return False
        for group in ("s", "p"):
            for key in ("amplitude_re", "amplitude_im", "power"):
                x, y = a[group][key], b[group][key]
                if x is None or y is None:
                    if x != y:
                        return False
                elif abs(x - y) > tol:
                    return False
        x, y = a["order_total_power"], b["order_total_power"]
        if x is None or y is None:
            if x != y:
                return False
        elif abs(x - y) > tol:
            return False
    return True


def main() -> int:
    case143 = json.loads(CASE143.read_text())
    plan = json.loads(PLAN.read_text())
    lock_sha = sha(LOCK)
    if case143.get("status") != "pass" or case143.get("retry_authorized") is not True:
        raise SystemExit("Case143 has not authorized retries")
    if plan.get("status") != "frozen_pending_case143" or plan.get("model_lock_sha256") != lock_sha:
        raise SystemExit("retry plan or model lock identity mismatch")
    if (ARTIFACT_ROOT / "blind_retry").exists():
        raise SystemExit("retry attempt directories already exist; refusing duplicate retry batch")
    if MANIFEST.exists():
        # The first orchestration attempt aborted in ABI preflight before any
        # solver/FEM directory was created.  Preserve it as separate evidence,
        # then allow the two contractual full solves per tuple to run once.
        old = json.loads(MANIFEST.read_text())
        records = old.get("records", [])
        if not records or not all(row.get("status") == "failed_runner" for row in records):
            raise SystemExit("retry manifest already exists with non-preflight records")
        abort_path = OUTCOMES / "BLIND_RETRY_PREFLIGHT_ABORT.json"
        write(abort_path, {"schema_version": "task006.blind-retry-preflight-abort.v1",
                           "status": "aborted_before_fem", "fem_count": 0,
                           "record_count": len(records), "reason": "ABI preflight failed because the first orchestration shell had a contaminated /mnt PATH",
                           "manifest_sha256": sha(MANIFEST), "records": records,
                           "original_case141_modified": False})
        MANIFEST.unlink()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in plan["failed_tuples"]:
        for attempt in (2, 3):
            print(f"retry start {item['key']} attempt_{attempt}", flush=True)
            rows.append(run_one(item, attempt))
    grouped = {key: [row for row in rows if row["key"] == key] for key in ("117.5,17.25/A07", "117.5,17.25/A09")}
    checks = {}
    for key, values in grouped.items():
        checks[key] = {
            "two_attempts": len(values) == 2,
            "both_measured_pass": all(value["status"] == "measured_pass" and value["return_code"] == 0 for value in values),
            "source_sha_fixed": all(value["source_sha"] == "fdf961545f217d620e22800f2704ae9913a6d270" for value in values),
            "response_consistent": len(values) == 2 and all(value["response"] is not None for value in values) and response_consistent(values[0]["response"], values[1]["response"]),
        }
    passed = all(all(value for value in check.values()) for check in checks.values())
    payload = {
        "schema_version": "task006.blind-retry-campaign.v1", "status": "pass" if passed else "controlled_stop",
        "qualification": "retry_reproducibly_qualified" if passed else "blind_forward_route_not_reproducibly_qualified",
        "generated_after_case143": True, "case143_sha256": sha(CASE143), "model_lock_sha256": lock_sha,
        "forward_solver_sha": "fdf961545f217d620e22800f2704ae9913a6d270",
        "max_fem_count": 4, "fem_count": len(rows), "records": rows, "checks": checks,
        "response_tolerance_absolute": 1.0e-10,
        "original_case141_modified": False,
        "model_tuned_after_retry": False,
    }
    write(MANIFEST, payload)
    print(json.dumps({key: value for key, value in payload.items() if key != "records"}, indent=2, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
