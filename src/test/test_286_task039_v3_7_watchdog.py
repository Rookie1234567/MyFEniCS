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


def test_v5_fixed_budget_main_dry_run_freezes_bottom_component(
    tmp_path, capsys
) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    run_directory = tmp_path / "fixed-budget-main-dry-run"
    assert (
        watchdog.main(
            [
                "--dry-run",
                "--input",
                str(h4_input),
                "--run-directory",
                str(run_directory),
                "--source-sha",
                "a" * 40,
                watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG,
                watchdog.V5_H4_FIXED_BUDGET_EXACT_SPOOL_ROOT_FLAG,
                str(
                    Path(
                        "results/task039_v5_h4_mumps_blr_side_component_mpi8_"
                        "7e5d9b57_1e3/numerical_output"
                    )
                ),
                "--selected-mode-packet-manifest",
                str(packet_root / "manifest.json"),
                "--selected-mode-packet-identity",
                str(packet_root / "identity.json"),
                "--selected-mode-packet-manifest-sha256",
                "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"].count(watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG) == 1
    assert "--v5-h4-blr-side-component" not in plan["argv"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 224000000000
    assert plan["worker_contract"]["fixed_budget"] == 32
    assert plan["worker_contract"]["method"] == (
        watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_METHOD
    )
    assert not run_directory.exists()


def test_v6_post_compaction_main_dry_run_freezes_h4_route_and_budget(
    tmp_path, capsys
) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    spool_root = Path(
        "results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/"
        "numerical_output"
    )
    run_directory = tmp_path / "v6-post-compaction-main-dry-run"
    assert (
        watchdog.main(
            [
                "--dry-run",
                "--input",
                str(h4_input),
                "--run-directory",
                str(run_directory),
                "--source-sha",
                "a" * 40,
                watchdog.V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG,
                watchdog.V6_H4_EXACT_SPOOL_ROOT_FLAG,
                str(spool_root),
                "--selected-mode-packet-manifest",
                str(packet_root / "manifest.json"),
                "--selected-mode-packet-identity",
                str(packet_root / "identity.json"),
                "--selected-mode-packet-manifest-sha256",
                "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"].count(watchdog.V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG) == 1
    assert watchdog.V5_H4_SETUP_ONLY_FLAG not in plan["argv"]
    assert watchdog.V5_H4_BLR_SIDE_COMPONENT_FLAG not in plan["argv"]
    assert watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG not in plan["argv"]
    assert watchdog.V6_H4_EXACT_SPOOL_ROOT_FLAG in plan["argv"]
    assert str(spool_root.resolve()) in plan["argv"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 45118258790
    assert plan["worker_contract"]["method"] == (
        watchdog.V6_H4_POST_COMPACTION_SETUP_ONLY_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V6_H4_POST_COMPACTION_PROFILE_ID
    )
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert plan["worker_contract"]["absolute_terminate_memory_bytes"] == 45118258790
    assert "--v5-h4-exact-spool-root" not in plan["argv"]
    assert not run_directory.exists()
