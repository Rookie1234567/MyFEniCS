"""V42 supervised compile, ABI and minimal relevant regressions."""

import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.distributed_volume_scope import ROOT, implementation_hashes, window


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
            "-c",
            "import json; from src.solvers.native_entity_study import environment; print(json.dumps(environment()))",
        ],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=" + str(folder / "fixtures"),
            "src/test/test_distributed_volume.py",
            "src/test/test_native_entities.py",
            "src/test/test_task042_shared_watchdog.py::test_deadline_clears_own_detached_child_and_preserves_sibling",
            "--junitxml=" + str(folder / "pytest.xml"),
        ],
    ]
    records = []
    for i, command in enumerate(commands):
        r = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False
        )
        (folder / f"command{i}.stdout").write_text(r.stdout)
        (folder / f"command{i}.stderr").write_text(r.stderr)
        records.append({"command": command, "returncode": r.returncode})
        if r.returncode:
            write_json(folder / "tests.json", {"status": "FAILED", "commands": records})
            raise RuntimeError(
                "V42 targeted qualification failed; raw evidence retained"
            )
    write_json(
        folder / "tests.json",
        {
            "status": "PASSED",
            "commands": records,
            "implementation_hashes": hashes,
            "ABI": json.loads((folder / "command0.stdout").read_text()),
        },
    )


if __name__ == "__main__":
    main()
