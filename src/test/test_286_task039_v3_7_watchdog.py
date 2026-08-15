"""Import and parent-watchdog contracts for the lightweight V3-7 launcher."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import benchmarks.task039_v3_7_watchdog as watchdog


INPUT = Path("input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat")


def test_light_watchdog_import_is_free_of_numerical_stack() -> None:
    code = (
        "import sys; import benchmarks.task039_v3_7_watchdog; "
        "assert not any(name.startswith(('mpi4py', 'petsc4py', 'dolfinx', "
        "'slepc4py', 'benchmarks.task039_v3_7_orchestration', "
        "'benchmarks.run_task037b_hybrid_iterative')) for name in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_light_watchdog_runs_task038_worker_with_dry_run_child(tmp_path) -> None:
    direct = tmp_path / "direct"
    direct.mkdir()
    (direct / "run_manifest.json").write_text(
        json.dumps(
            {
                "model_id": "task039_5nm_v3_1deg_s5_hybrid_direct_m480",
                "method": "hybrid_direct",
                "mpi_size": 8,
                "source_sha": watchdog.V3_7_DIRECT_PRODUCER_SHA,
            }
        ),
        encoding="utf-8",
    )

    script = """
import subprocess
import sys
from pathlib import Path

assert not any(
    name.startswith(('mpi4py', 'petsc4py', 'dolfinx', 'slepc4py',
                     'benchmarks.task039_v3_7_orchestration',
                     'benchmarks.run_task037b_hybrid_iterative'))
    for name in sys.modules
)
import benchmarks.task039_v3_7_watchdog as watchdog

direct = Path(sys.argv[1])
run = Path(sys.argv[2])
watchdog.V3_7_DIRECT_RUN_ROOT = direct

def dry_run_child(argv, **kwargs):
    rewritten = list(argv)
    rewritten[rewritten.index('--worker')] = '--dry-run'
    return subprocess.Popen(rewritten, **kwargs)

def sample(pid):
    return {
        'memory_authority_bytes': 0,
        'process_tree': {
            'root_pid': pid,
            'rss_bytes': 0,
            'swap_bytes': 0,
            'all_status_readable': True,
            'smaps': {'complete': False},
        },
        'job_cgroup': {'dedicated_job_cgroup': False},
    }

result = watchdog.launch_v3_7_with_task038_watchdog(
    sys.argv[3], run, source_sha='a' * 40,
    python_executable=sys.executable,
    popen_factory=dry_run_child, sample_factory=sample,
)
assert result['exit_status'] == 0, result
assert result['result_classification'] == 'worker_exit0', result
assert (run / 'worker_stdout.txt').stat().st_size > 0
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(direct), str(tmp_path / "run"), str(INPUT)],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
        env={
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OMPI_COMM_WORLD_", "PMIX_", "PMI_"))
        },
    )
    assert completed.returncode == 0, completed.stderr


def test_light_watchdog_plan_keeps_mpi8_and_byte_hard_stop(tmp_path) -> None:
    plan = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "run",
        source_sha="a" * 40,
        python_executable=sys.executable,
    )
    assert plan["argv"][1:3] == ["-n", "8"]
    assert "--worker" in plan["argv"]
    assert "--launched-by-task038-watchdog" in plan["argv"]
    assert plan["watchdog"]["critical_action"] == "record_checkpoint_only"
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 224000000000
