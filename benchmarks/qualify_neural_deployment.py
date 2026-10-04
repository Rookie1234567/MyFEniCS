"""Minimal final-byte scalar tests and one ML import-only consumer regression."""

import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.neural_decision_scope import ROOT, implementation_hashes, window


def main():
    window.guard_worker_parent()
    folder = Path(os.environ["TASK042_V36_AUX_DIRECTORY"])
    hashes = implementation_hashes()
    for name in hashes:
        if name.endswith(".py"):
            compile((ROOT / name).read_bytes(), name, "exec")
    commands = [
        [
            sys.executable,
            "-m",
            "unittest",
            "-q",
            "src.test.test_neural_deployment_decision",
        ],
        [
            "bash",
            "-c",
            "set -e; export TASK042_CACHE_NAMESPACE=v46/cache TASK042_PREPARATION_SCOPE=v46; source scripts/activate_task042.sh ml; python -m unittest -q src.test.test_neural_deployment_decision.FrozenDataAndConfig.test_actual_fullmoment_method_calls_pure_consumer",
        ],
    ]
    rows = []
    for i, command in enumerate(commands):
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        (folder / f"command{i}.stdout").write_text(result.stdout)
        (folder / f"command{i}.stderr").write_text(result.stderr)
        rows.append({"command": command, "returncode": result.returncode})
        if result.returncode:
            write_json(
                folder / "tests.json",
                {
                    "status": "FAILED",
                    "commands": rows,
                    "numeric_actions": 0,
                    "implementation_hashes": hashes,
                },
            )
            raise RuntimeError(
                "minimal decision test failed; retain and repair affected fixture"
            )
    write_json(
        folder / "tests.json",
        {
            "status": "PASSED",
            "commands": rows,
            "implementation_hashes": hashes,
            "numeric_actions": 0,
            "ML_scope": "import and scalar mock evaluate only; no network instantiation/forward",
        },
    )
    print(
        json.dumps({"status": "V46_SCALAR_QUALIFICATION_PASSED", "numeric_actions": 0})
    )


if __name__ == "__main__":
    main()
