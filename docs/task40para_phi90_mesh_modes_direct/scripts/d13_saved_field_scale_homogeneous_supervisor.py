"""Use the existing Task40 host-floor guard for the cutoff candidate worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from d13_saved_field_cutoff_stage_supervisor import run_supervised


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_worker_command(
    command: list[str], contract_path: Path, output_path: Path, contract: dict[str, Any]
) -> None:
    repo = Path(__file__).resolve().parents[3]
    expected_worker = (
        repo
        / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_saved_field_scale_homogeneous_worker.py"
    ).resolve()
    prefix = ["mpiexec", "-n", "1", "numactl", "--interleave=0,1", "taskset", "-c", "24"]
    if len(command) != 14 or command[:8] != prefix:
        raise ValueError("candidate worker must use MPI1 and rank-local interleave0-1/taskset24")
    python_path = (Path(os.environ["TASK40_SHARED_VENV_ROOT"]) / "bin/python").resolve()
    if Path(command[8]).resolve() != python_path:
        raise ValueError("candidate interpreter differs from qualified read-only Task40 Python")
    if Path(command[9]).resolve() != expected_worker:
        raise ValueError("worker command does not point to the candidate wrapper")
    if command[10:] != ["--contract", str(contract_path), "--output", str(output_path)]:
        raise ValueError("candidate worker args differ from the frozen contract/output")
    if contract.get("candidate_worker_script_sha256") != _sha256(expected_worker):
        raise ValueError("candidate worker script SHA differs from contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--supervision-output", required=True, type=Path)
    parser.add_argument("--watchdog-directory", required=True, type=Path)
    parser.add_argument("--worker-command-json", required=True)
    args = parser.parse_args()
    contract_path = args.contract.resolve()
    output_path = args.output.resolve()
    contract = json.loads(contract_path.read_text())
    if contract.get("execution_authorized") is not True:
        raise PermissionError("candidate package is review-only and cannot start its worker")
    command = json.loads(args.worker_command_json)
    if not isinstance(command, list) or any(not isinstance(token, str) for token in command):
        raise ValueError("worker-command-json must be a JSON string array")
    _validate_worker_command(command, contract_path, output_path, contract)
    result = run_supervised(
        command,
        watchdog_directory=args.watchdog_directory.resolve(),
        supervision_output_path=args.supervision_output.resolve(),
        contract=contract,
    )
    print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    return 0 if result["classification"] == "COMPLETED" and result["leader_exit_code"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
