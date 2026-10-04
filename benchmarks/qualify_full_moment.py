"""Supervised final-byte compile, ML threads, focused wiring and timeout gates."""

import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.full_moment_scope import (
    ROOT,
    implementation_hashes,
    window,
)


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
            "import sys,json,torch; from src.solvers.neighborhood_residual_models import configure_threads; configure_threads(); assert not any(n in sys.modules for n in ('petsc4py','dolfinx','mpi4py')); print(json.dumps({'executable':sys.executable,'Torch':torch.__version__,'intra':torch.get_num_threads(),'interop':torch.get_num_interop_threads(),'CUDA':torch.cuda.is_available(),'Loader':0}))",
        ],
        [
            sys.executable,
            "-m",
            "benchmarks.qualified_ml_pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=" + str(folder / "fixtures"),
            "src/test/test_full_moment_hierarchy.py",
            "src/test/test_neighborhood_late_error.py",
            "src/test/test_neighborhood_residual.py",
            "src/test/test_task042_shared_watchdog.py::test_deadline_clears_own_detached_child_and_preserves_sibling",
            "src/test/test_task042_shared_watchdog.py::test_opt_in_tree_limit_clears_orphan_without_signalling_sibling",
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
                "V45 targeted qualification failed; preserve raw and minimally repair"
            )
    write_json(
        folder / "tests.json",
        {
            "status": "PASSED",
            "commands": records,
            "implementation_hashes": hashes,
            "ML_environment": json.loads((folder / "command0.stdout").read_text()),
        },
    )


if __name__ == "__main__":
    main()
