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


def test_v8_layer_block_main_dry_run_is_packet_free(tmp_path, capsys) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    run_directory = tmp_path / "v8-layer-block-main-dry-run"
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
                watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG,
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    route_flags = {
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG,
        "--v5-h4-setup-only",
        "--v5-h4-blr-side-component",
        "--v5-h4-fixed-budget-bottom-component",
        "--v6-h4-post-compaction-setup-only",
        "--v6-h4-port-modal-bottom-component",
        "--v7-h4-exact-side-limit-setup-only",
        "--v7-h4-exact-side-full-formal",
        "--v7-h4-streamed-bottom-producer",
        "--v7-h4-streamed-bottom-consumer",
    }
    assert [flag for flag in plan["argv"] if flag in route_flags] == [
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG
    ]
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 224000000000
    assert plan["watchdog"]["profile"] == (
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_PROFILE
    )
    assert plan["worker_contract"]["method"] == (
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_PROFILE
    )
    assert plan["worker_contract"]["exact_spool_root"] is None
    assert not any(
        argument.startswith("--selected-mode-packet-") for argument in plan["argv"]
    )
    assert not run_directory.exists()


def test_v8_layer_sweep_main_dry_run_freezes_bottom_contract(tmp_path, capsys) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    spool_root = Path(
        "results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/"
        "numerical_output"
    )
    run_directory = tmp_path / "v8-layer-sweep-main-dry-run"
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
                watchdog.V8_H4_LAYER_SWEEP_BOTTOM_FLAG,
                watchdog.V8_H4_LAYER_SWEEP_BOTTOM_EXACT_SPOOL_ROOT_FLAG,
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
    route_flags = {
        watchdog.V8_H4_LAYER_SWEEP_BOTTOM_FLAG,
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG,
        "--v5-h4-setup-only",
        "--v5-h4-blr-side-component",
        "--v5-h4-fixed-budget-bottom-component",
        "--v6-h4-post-compaction-setup-only",
        "--v6-h4-port-modal-bottom-component",
        "--v7-h4-exact-side-limit-setup-only",
        "--v7-h4-exact-side-full-formal",
        "--v7-h4-streamed-bottom-producer",
        "--v7-h4-streamed-bottom-consumer",
    }
    assert [flag for flag in plan["argv"] if flag in route_flags] == [
        watchdog.V8_H4_LAYER_SWEEP_BOTTOM_FLAG
    ]
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        watchdog.V8_H4_LAYER_SWEEP_BOTTOM_HARD_STOP_BYTES
    )
    assert plan["watchdog"]["profile"] == watchdog.V8_H4_LAYER_SWEEP_BOTTOM_PROFILE
    assert plan["worker_contract"]["method"] == (
        watchdog.V8_H4_LAYER_SWEEP_BOTTOM_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V8_H4_LAYER_SWEEP_BOTTOM_PROFILE
    )
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert watchdog.V8_H4_LAYER_SWEEP_BOTTOM_EXACT_SPOOL_ROOT_FLAG in plan["argv"]
    assert not run_directory.exists()


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


def test_v7_exact_side_limit_main_dry_run_freezes_lane_a_budget(
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
    run_directory = tmp_path / "v7-exact-side-limit-main-dry-run"
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
                watchdog.V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG,
                watchdog.V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG,
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
    assert plan["argv"].count(watchdog.V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG) == 1
    assert watchdog.V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG not in plan["argv"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        watchdog.V7_H4_EXACT_SIDE_LIMIT_HARD_STOP_BYTES
    )
    assert plan["worker_contract"]["method"] == (
        watchdog.V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V7_H4_EXACT_SIDE_LIMIT_PROFILE_ID
    )
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert not run_directory.exists()


def test_v7_full_formal_main_dry_run_freezes_direct_stop_and_timeout(
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
    run_directory = tmp_path / "v7-full-main-dry-run"
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
                watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG,
                watchdog.V7_H4_EXACT_SIDE_LIMIT_EXACT_SPOOL_ROOT_FLAG,
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
    assert plan["argv"].count(watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG) == 1
    assert watchdog.V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG not in plan["argv"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_HARD_STOP_BYTES
    )
    assert plan["watchdog"]["timeout_policy"] == {
        "default_seconds": 21600,
        "conditional_extension_seconds": 28800,
        "extension_requires_outer_and_decreasing_residual": True,
        "automatic_extension": False,
    }
    assert plan["worker_contract"]["method"] == (
        watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_PROFILE_ID
    )
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert not run_directory.exists()


def test_v6_port_modal_main_dry_run_freezes_bottom_route_and_budget(
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
    run_directory = tmp_path / "v6-port-modal-main-dry-run"
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
                watchdog.V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG,
                watchdog.V6_H4_PORT_MODAL_EXACT_SPOOL_ROOT_FLAG,
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
    assert plan["argv"].count(watchdog.V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG) == 1
    assert watchdog.V6_H4_PORT_MODAL_EXACT_SPOOL_ROOT_FLAG in plan["argv"]
    assert watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG not in plan["argv"]
    assert plan["worker_contract"]["method"] == (
        watchdog.V6_H4_PORT_MODAL_BOTTOM_COMPONENT_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V6_H4_PORT_MODAL_BOTTOM_COMPONENT_PROFILE
    )
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 23622320128
    assert not run_directory.exists()


def test_v7_streamed_bottom_producer_main_dry_run_is_packet_only(tmp_path, capsys):
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    run_directory = tmp_path / "v7-streamed-producer-main-dry-run"
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
                watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG,
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
    assert plan["argv"].count(watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG) == 1
    route_flags = (
        "--candidate-b-only",
        "--candidate-c-only",
        "--candidate-d-only",
        "--candidate-d-qualified",
        "--candidate-e-side-only",
        "--v5-h4-setup-only",
        "--v5-h4-blr-side-component",
        "--v5-h4-fixed-budget-bottom-component",
        "--v6-h4-post-compaction-setup-only",
        "--v6-h4-port-modal-bottom-component",
        "--v7-h4-exact-side-limit-setup-only",
        "--v7-h4-exact-side-full-formal",
        watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG,
    )
    assert sum(flag in plan["argv"] for flag in route_flags) == 1
    assert plan["worker_contract"]["method"] == (
        watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_PROFILE
    )
    assert plan["worker_contract"]["exact_spool_root"] is None
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        watchdog.V7_STREAMED_PETROV_HARD_STOP_BYTES
    )
    assert all("spool" not in argument for argument in plan["argv"])
    assert not run_directory.exists()


def test_v9_bare_f_main_dry_run_uses_frozen_spool_and_45gib_stop(tmp_path, capsys):
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    spool_root = Path(
        "results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/"
        "numerical_output"
    )
    run_directory = tmp_path / "v9-bare-f-main-dry-run"
    assert (
        watchdog.main(
            [
                "--dry-run",
                "--input",
                str(h4_input),
                "--run-directory",
                str(run_directory),
                "--source-sha",
                "b" * 40,
                watchdog.V9_H4_BARE_F_SIDE_FLAG,
                watchdog.V9_H4_BARE_F_SIDE_EXACT_SPOOL_ROOT_FLAG,
                str(spool_root),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"].count(watchdog.V9_H4_BARE_F_SIDE_FLAG) == 1
    assert plan["argv"].count(watchdog.V9_H4_BARE_F_SIDE_EXACT_SPOOL_ROOT_FLAG) == 1
    assert plan["worker_contract"]["method"] == watchdog.V9_H4_BARE_F_SIDE_METHOD
    assert plan["worker_contract"]["profile_id"] == watchdog.V9_H4_BARE_F_SIDE_PROFILE
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        watchdog.V9_H4_BARE_F_SIDE_HARD_STOP_BYTES
    )
    assert (
        sum(
            flag in plan["argv"]
            for flag in (
                watchdog.V9_H4_BARE_F_SIDE_FLAG,
                watchdog.V5_H4_SETUP_ONLY_FLAG,
                watchdog.V5_H4_BLR_SIDE_COMPONENT_FLAG,
                watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG,
                watchdog.V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG,
                watchdog.V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG,
                watchdog.V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG,
                watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG,
                watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG,
                watchdog.V7_STREAMED_PETROV_BOTTOM_CONSUMER_FLAG,
                watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG,
                watchdog.V8_H4_LAYER_SWEEP_BOTTOM_FLAG,
            )
        )
        == 1
    )
    assert not any("selected-mode-packet" in argument for argument in plan["argv"])
    assert not run_directory.exists()


def test_v9_layer_supernode_main_dry_run_uses_one_route_and_45gib_stop(
    tmp_path, capsys
):
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    spool_root = Path(
        "results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/"
        "numerical_output"
    )
    run_directory = tmp_path / "v9-supernode-main-dry-run"
    assert (
        watchdog.main(
            [
                "--dry-run",
                "--input",
                str(h4_input),
                "--run-directory",
                str(run_directory),
                "--source-sha",
                "c" * 40,
                watchdog.V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG,
                watchdog.V9_H4_LAYER_SUPERNODE_EXACT_SPOOL_ROOT_FLAG,
                str(spool_root),
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    route_flags = (
        watchdog.V5_H4_SETUP_ONLY_FLAG,
        watchdog.V5_H4_BLR_SIDE_COMPONENT_FLAG,
        watchdog.V5_H4_FIXED_BUDGET_BOTTOM_COMPONENT_FLAG,
        watchdog.V6_H4_POST_COMPACTION_SETUP_ONLY_FLAG,
        watchdog.V6_H4_PORT_MODAL_BOTTOM_COMPONENT_FLAG,
        watchdog.V7_H4_EXACT_SIDE_LIMIT_SETUP_ONLY_FLAG,
        watchdog.V7_H4_EXACT_SIDE_FULL_FORMAL_FLAG,
        watchdog.V7_STREAMED_PETROV_BOTTOM_PRODUCER_FLAG,
        watchdog.V7_STREAMED_PETROV_BOTTOM_CONSUMER_FLAG,
        watchdog.V8_H4_LAYER_BLOCK_RECONSTRUCTION_FLAG,
        watchdog.V8_H4_LAYER_SWEEP_BOTTOM_FLAG,
        watchdog.V9_H4_BARE_F_SIDE_FLAG,
        watchdog.V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG,
    )
    assert plan["argv"][1:3] == ["-n", "8"]
    assert sum(flag in plan["argv"] for flag in route_flags) == 1
    assert plan["argv"].count(watchdog.V9_H4_LAYER_SUPERNODE_BOTTOM_FLAG) == 1
    assert plan["argv"].count(watchdog.V9_H4_LAYER_SUPERNODE_EXACT_SPOOL_ROOT_FLAG) == 1
    assert plan["worker_contract"]["method"] == (watchdog.V9_H4_LAYER_SUPERNODE_METHOD)
    assert plan["worker_contract"]["profile_id"] == (
        watchdog.V9_H4_LAYER_SUPERNODE_PROFILE
    )
    assert plan["worker_contract"]["exact_spool_root"] == str(spool_root.resolve())
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        watchdog.V9_H4_LAYER_SUPERNODE_HARD_STOP_BYTES
    )
    assert not any("selected-mode-packet" in argument for argument in plan["argv"])
    assert not run_directory.exists()


def test_v9_bare_f_launch_passes_h4_identity_to_worker_dry_run(tmp_path):
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    spool_root = Path(
        "results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/"
        "numerical_output"
    )
    run_directory = tmp_path / "v9-bare-f-launch-dry-run"

    def dry_run_child(argv, **kwargs):
        rewritten = list(argv)
        rewritten[rewritten.index("--worker")] = "--dry-run"
        return subprocess.Popen(rewritten, **kwargs)

    def sample(_pid):
        return {
            "memory_authority_bytes": 0,
            "process_tree": {
                "root_pid": _pid,
                "rss_bytes": 0,
                "swap_bytes": 0,
                "all_status_readable": True,
                "smaps": {"complete": False},
            },
            "job_cgroup": {"dedicated_job_cgroup": False},
        }

    result = watchdog.launch_v3_7_with_task038_watchdog(
        h4_input,
        run_directory,
        source_sha="a" * 40,
        python_executable=sys.executable,
        v9_h4_bare_f_side=True,
        v9_h4_bare_f_side_exact_spool_root=spool_root,
        popen_factory=dry_run_child,
        sample_factory=sample,
    )
    assert result["exit_status"] == 0, result
    assert result["result_classification"] == "worker_exit0", result
    assert (run_directory / "worker_stdout.txt").stat().st_size > 0
