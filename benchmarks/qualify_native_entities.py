"""V41 supervised ABI/getter, focused wiring tests and source compilation."""

import json
import os
import subprocess
import sys
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_entity_scope import ROOT, implementation_hashes, window


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
            "src/test/test_native_entities.py",
            "--junitxml=" + str(folder / "pytest.xml"),
        ],
    ]
    if "--focused-owner-checker" in sys.argv:
        i = commands[1].index("src/test/test_native_entities.py")
        commands[1][i] += "::test_literal_owner_checker_end_to_end_inventory_faults"
    commands.append(
        [
            "/home/fenics/Projects/Metrology/.venv/bin/ruff",
            "check",
            *[
                p
                for p in hashes
                if p.endswith(".py")
                and (
                    "native_entit" in p
                    or p
                    in ("src/io/port_preparation.py", "src/runners/port_preparation.py")
                )
            ],
        ]
    )
    if "--inspect" in sys.argv:
        commands.append(
            [
                sys.executable,
                "-c",
                "from dolfinx import mesh, la; import inspect; print(inspect.signature(mesh.create_mesh)); print(mesh.create_cell_partitioner.__doc__); print(la.Vector.scatter_reverse.__doc__)",
            ]
        )
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
            raise RuntimeError("V41 focused qualification failed; raw logs retained")
    write_json(
        folder / "tests.json",
        {
            "status": "PASSED",
            "commands": records,
            "implementation_hashes": hashes,
            "ABI": json.loads((folder / "command0.stdout").read_text()),
            "compiled_python_files": sum(n.endswith(".py") for n in hashes),
        },
    )


if __name__ == "__main__":
    main()
