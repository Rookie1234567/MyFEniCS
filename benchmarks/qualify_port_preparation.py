"""One paid pre/post command: actual compile, focused tests and MPI fixtures."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from src.runners.task042_shared import write_json
from src.solvers.port_preparation_window import ROOT, implementation_hashes, window


def main():
    namespace = os.environ.get("TASK042_PREPARATION_SCOPE", "v36")
    if namespace == "v40":
        from src.solvers.native_recovery_scope import (
            implementation_hashes as selected_hashes,
        )
        from src.solvers.native_recovery_scope import window as selected_window
    elif namespace == "v39":
        from src.solvers.native_integration_scope import (
            implementation_hashes as selected_hashes,
        )
        from src.solvers.native_integration_scope import window as selected_window
    elif namespace == "v38":
        from src.solvers.boundary_structure_scope import (
            implementation_hashes as selected_hashes,
        )
        from src.solvers.boundary_structure_scope import window as selected_window
    elif namespace == "v37":
        from src.solvers.boundary_witness_scope import (
            implementation_hashes as selected_hashes,
        )
        from src.solvers.boundary_witness_scope import window as selected_window
    else:
        selected_window, selected_hashes = window, implementation_hashes
    selected_window.guard_worker_parent()
    folder = Path(os.environ["TASK042_V36_AUX_DIRECTORY"])
    began = perf_counter()
    before_style = selected_hashes()
    if "--finish-style" in sys.argv:
        # Optional authoring pass, before compilation or any numerical test.
        # Only new files are changed. Before/after identities remain explicit.
        files = [
            p
            for p in before_style
            if p.endswith(".py")
            and p not in ("scripts/run_case.py", "src/test/test_task042_v35_cache.py")
        ]
        ruff = "/home/fenics/Projects/Metrology/.venv/bin/ruff"
        commands = [
            [
                ruff,
                "check",
                "--select",
                "C408,UP031,PERF102,SIM101,RUF059",
                "--fix",
                "--unsafe-fixes",
                *files,
            ],
            [ruff, "format", *files],
            [ruff, "check", *files],
        ]
        for i, command in enumerate(commands):
            run = subprocess.run(command, capture_output=True, text=True, check=False)
            (folder / f"authoring{i}.stdout").write_text(run.stdout)
            (folder / f"authoring{i}.stderr").write_text(run.stderr)
            if run.returncode:
                raise RuntimeError("final new-file style check failed")
    hashes = selected_hashes()
    for file in hashes:
        if file.endswith(".py"):
            compile((ROOT / file).read_bytes(), file, "exec")
    # MPI initialization in this parent changes singleton OpenMPI state. Keep
    # the ABI probe in a separate interpreter before launching MPI fixtures.
    abi_command = [
        sys.executable,
        "-c",
        (
            "import json; from src.solvers.port_component_study import environment; "
            "print(json.dumps(environment(fe=True)))"
        ),
    ]
    abi = subprocess.run(
        abi_command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    (folder / "abi.stdout").write_text(abi.stdout)
    (folder / "abi.stderr").write_text(abi.stderr)
    if abi.returncode:
        raise RuntimeError("qualified ABI subprocess failed: see abi.stderr")
    env = json.loads(abi.stdout)
    commands = [
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=" + str(folder / "fixtures"),
            "src/test/test_task042_v36_ports.py",
            "src/test/test_task042_v36_checker.py",
            *(
                ["src/test/test_boundary_witness.py"]
                if namespace in ("v37", "v38")
                else []
            ),
            *(["src/test/test_boundary_structure.py"] if namespace == "v38" else []),
            "src/test/test_task042_v35_cache.py::test_verify_barrier_does_not_read_reference_after_numeric_negative",
            "--junitxml=" + str(folder / "pytest.xml"),
        ]
    ]
    if namespace == "v39":
        commands[0] = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=" + str(folder / "fixtures"),
            "src/test/test_native_integration.py",
            "src/test/test_boundary_structure.py::test_tensor_matches_independent_complete_facet_sum",
            "--junitxml=" + str(folder / "pytest.xml"),
        ]
    if namespace == "v40":
        commands[0] = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=" + str(folder / "fixtures"),
            "src/test/test_native_recovery.py",
            "src/test/test_native_integration.py",
            "--junitxml=" + str(folder / "pytest.xml"),
        ]
    if "--targeted-new" in sys.argv:
        if namespace != "v38":
            raise ValueError("targeted qualification scope")
        commands[0] = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=" + str(folder / "fixtures"),
            "src/test/test_boundary_structure.py",
            "src/test/test_boundary_witness.py",
            "--junitxml=" + str(folder / "pytest.xml"),
        ]
    commands += [
        [
            "mpiexec",
            "--bind-to",
            "none",
            "-n",
            str(n),
            sys.executable,
            "-m",
            "src.test.tiled_port_mpi_fixture"
            if namespace in ("v37", "v38", "v39", "v40")
            else "src.test.port_provider_mpi_fixture",
            str(folder / f"mpi{n}.json"),
        ]
        for n in (2, 4)
    ]
    rows = []
    for i, command in enumerate(commands):
        started = perf_counter()
        with (
            (folder / f"check{i}.stdout").open("w") as out,
            (folder / f"check{i}.stderr").open("w") as err,
        ):
            run = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, check=False)
        rows.append(
            {
                "command": command,
                "returncode": run.returncode,
                "seconds": perf_counter() - started,
            }
        )
        if run.returncode:
            break
    if (
        "--recheck-cache" in sys.argv
        and len(rows) == len(commands)
        and all(r["returncode"] == 0 for r in rows)
    ):
        from benchmarks.check_port_preparation import check_saved

        write_json(folder / "saved_cache_recheck.json", check_saved())
    receipt = {
        "status": "PASSED"
        if len(rows) == len(commands) and all(r["returncode"] == 0 for r in rows)
        else "FAILED",
        "implementation_hashes": hashes,
        "before_authoring_hashes": before_style,
        "commands": rows,
        "compiled": list(hashes),
        "environment": env,
        "loaded_wall_seconds": perf_counter() - began,
        "raw_files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.iterdir()
            if p.is_file()
        },
        "volume_action_count": 0,
        "LU_count": 0,
        "QR_count": 0,
        "reference_read": False,
    }
    write_json(folder / "tests.json", receipt)
    print(
        json.dumps(
            {"status": receipt["status"], "commands": len(rows), "folder": str(folder)}
        ),
        flush=True,
    )
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
