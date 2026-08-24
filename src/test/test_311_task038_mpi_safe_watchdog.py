from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


SOURCE_SHA = "a" * 40


def _qualified_python() -> str:
    executable = str(Path(sys.executable).absolute())
    assert Path(executable).is_absolute()
    return executable


def test_watchdog_import_boundary_is_mpi_safe() -> None:
    repo = Path(__file__).resolve().parents[2]
    probe = """
import json
import sys
sys.argv = ["foundation-module", "--watchdog"]
import benchmarks.run_task038_full3d_lor_hx_foundation
names = (
    "mpi4py.MPI",
    "petsc4py.PETSc",
    "dolfinx",
    "benchmarks.run_task038_full3d_lor_hx",
    "benchmarks.run_task038_full3d_lor_hx_krylov",
    "src.solvers.fullspace_memory_first_krylov",
    "src.solvers.fullspace_lor_hx_root_cause",
    "src.solvers.fullspace_lor_native_hx_fixture",
)
print(json.dumps({name: name in sys.modules for name in names}, sort_keys=True))
"""
    result = subprocess.run(
        [_qualified_python(), "-c", probe],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    assert all(value is False for value in loaded.values()), loaded


def test_watchdog_mpi2_rank_probe_and_reuse_fail_closed(tmp_path: Path) -> None:
    mpiexec = Path("/usr/bin/mpiexec")
    if not mpiexec.is_file():
        pytest.skip("qualified /usr/bin/mpiexec is unavailable")
    repo = Path(__file__).resolve().parents[2]
    qualified_python = _qualified_python()
    worker_raw = tmp_path / "worker_raw"
    watchdog_raw = tmp_path / "watchdog.raw.jsonl"
    watchdog_compact = tmp_path / "watchdog.json"
    watchdog_log = tmp_path / "worker.log"
    worker_record = tmp_path / "record.json"
    rank_probe = (
        "from mpi4py import MPI; from petsc4py import PETSc; import json; "
        "comm=MPI.COMM_WORLD; print(json.dumps({'rank': comm.rank, 'size': comm.size, "
        "'scalar': PETSc.ScalarType.__name__, 'int': PETSc.IntType.__name__}), flush=True)"
    )
    worker_command = [
        str(mpiexec),
        "-n",
        "2",
        qualified_python,
        "-c",
        rank_probe,
    ]
    command = [
        qualified_python,
        "-m",
        "benchmarks.run_task038_full3d_lor_hx_foundation",
        "--watchdog",
        "--watchdog-raw",
        str(watchdog_raw),
        "--watchdog-compact",
        str(watchdog_compact),
        "--watchdog-log",
        str(watchdog_log),
        "--worker-raw-dir",
        str(worker_raw),
        "--worker-record",
        str(worker_record),
        "--source-sha",
        SOURCE_SHA,
        "--watchdog-rss-limit-bytes",
        "500000000",
        "--worker-command",
        "--",
        *worker_command,
    ]
    first = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr + first.stdout
    compact = json.loads(watchdog_compact.read_text(encoding="utf-8"))
    samples = [
        json.loads(line)
        for line in watchdog_raw.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert compact["worker_command"] == worker_command
    assert compact["natural_exit"] is True
    assert compact["no_orphan"] is True
    assert compact["returncode"] == 0
    assert compact["stop_reason"] == "natural_exit"
    assert compact["sample_count"] == len(samples) > 0
    assert compact["all_status_readable"] is True
    assert compact["max_process_tree_swap_bytes"] == 0
    assert compact["peak_process_tree_rss_bytes"] < 500_000_000
    assert compact["raw_sha256"] == hashlib.sha256(watchdog_raw.read_bytes()).hexdigest()
    observations = []
    for line in watchdog_log.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("size") == 2:
            observations.append(item)
    assert {item["rank"] for item in observations} == {0, 1}
    assert all(item["scalar"] == "complex128" and item["int"] == "int32" for item in observations)

    second = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    assert second.returncode != 0
    assert "FileExistsError" in second.stderr
    assert not worker_raw.exists()
