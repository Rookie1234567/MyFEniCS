"""Pure and static contracts for the D2 first-half worker."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from benchmarks import run_task038_full3d_adaptive_coarse_d2 as runner


ROOT = Path(__file__).parents[2]
RUNNER_PATH = ROOT / "benchmarks" / "run_task038_full3d_adaptive_coarse_d2.py"


class _Comm:
    rank = 0
    size = 1

    def barrier(self):
        return None

    def bcast(self, value, root=0):
        del root
        return value


def test_marker_ledger_is_atomic_and_ordered(tmp_path: Path):
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    comm = _Comm()
    runner._write_marker(marker_dir, "preflight", "a" * 40, comm, phase=1)
    runner._write_marker(
        marker_dir, "mesh_mpc_topology", "a" * 40, comm, phase=2
    )
    ledger = runner._marker_ledger(marker_dir)
    assert [item["marker"] for item in ledger] == [
        "preflight",
        "mesh_mpc_topology",
    ]
    assert all(item["source_git_sha"] == "a" * 40 for item in ledger)
    with pytest.raises(FileExistsError):
        runner._write_marker(marker_dir, "preflight", "a" * 40, comm)


def test_controlled_negative_record_preserves_failure_and_plan(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    marker_dir = raw_dir / "markers"
    raw_dir.mkdir()
    marker_dir.mkdir()
    comm = _Comm()
    runner._write_marker(marker_dir, "preflight", "b" * 40, comm)
    record = tmp_path / "record.json"
    runner._write_failure_record(
        record,
        raw_dir,
        marker_dir,
        "b" * 40,
        ValueError("synthetic D2 failure"),
        planned=("mesh_mpc_topology", "trace_basis_build"),
        not_run=("online_az_e", "canonical_evidence"),
        comm=comm,
    )
    payload = json.loads(record.read_text(encoding="utf-8"))
    assert payload["classification"] == "controlled_negative"
    assert payload["failure"] == {
        "exception_type": "ValueError",
        "message": "synthetic D2 failure",
    }
    assert payload["last_marker"] == "preflight"
    assert payload["not_run"] == ["online_az_e", "canonical_evidence"]


def test_watchdog_compact_and_stage_peak_are_pure_facts():
    samples = [
        {
            "stage": "trace_basis_build",
            "authority": {
                "memory_authority_bytes": 12,
                "process_tree": {"swap_bytes": 0},
            },
        },
        {
            "stage": "online_az_e",
            "authority": {
                "memory_authority_bytes": 34,
                "process_tree": {"swap_bytes": 0},
            },
        },
    ]
    assert runner._stage_memory_peaks(samples) == {
        "trace_basis_build": 12,
        "online_az_e": 34,
    }
    compact = runner._watchdog_compact(
        "d" * 64,
        ("python", "worker"),
        "natural_exit",
        0,
        {"requested": False},
        samples,
    )
    assert compact["process_tree_peak_memory_authority_bytes"] == 34
    assert compact["process_tree_swap_gate"] is True
    assert compact["raw_sha256"] == "d" * 64


def test_watchdog_swap_gate_fails_closed_for_missing_or_bad_authority():
    base = {
        "stage": "online_az_e",
        "authority": {
            "memory_authority_bytes": 12,
            "process_tree": {"swap_bytes": 0},
        },
    }
    cases = (
        [],
        [{"stage": "online_az_e", "authority_error": "unreadable"}],
        [
            {
                "stage": "online_az_e",
                "authority": {
                    "memory_authority_bytes": 12,
                    "process_tree": {"swap_bytes": 1},
                },
            }
        ],
        [base, {"stage": "online_az_e", "authority_error": "late failure"}],
    )
    for samples in cases:
        compact = runner._watchdog_compact(
            "e" * 64,
            ("python", "worker"),
            "natural_exit",
            0,
            {"requested": False},
            samples,
        )
        assert compact["process_tree_swap_gate"] is False


def test_cleanup_measures_only_after_destroy_order():
    events = []

    class _Object:
        def __init__(self, name):
            self.name = name

        def destroy(self):
            events.append(self.name)

    measured = runner._destroy_and_measure(
        (_Object("coarse"), _Object("physical"), _Object("basis")),
        lambda: events.append("measure") or {"rss": 11},
    )
    assert events == ["coarse", "physical", "basis", "measure"]
    assert measured == {"rss": 11}


def test_watchdog_backfills_missing_record_as_honest_negative(tmp_path: Path):
    marker_dir = tmp_path / "raw" / "markers"
    marker_dir.mkdir(parents=True)
    raw_path = tmp_path / "watchdog.raw.json"
    compact_path = tmp_path / "watchdog.compact.json"
    raw_path.write_text("{\"samples\": []}\n", encoding="utf-8")
    compact_path.write_text("{\"peak\": 77}\n", encoding="utf-8")
    record_path = tmp_path / "missing-record.json"
    compact = {
        "process_tree_peak_memory_authority_bytes": 77,
        "process_tree_swap_gate": False,
    }
    runner._backfill_watchdog_record(
        record_path,
        marker_dir,
        raw_path,
        compact_path,
        compact,
        "hard_stop_12_gib",
        -15,
        {"method": "SIGTERM", "sigkill_required": False},
    )
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["classification"] == "controlled_negative"
    assert payload["source_identity"] == {
        "expected_sha": None,
        "source_git_sha": None,
        "tracked_status": "not_measured",
    }
    assert payload["resource_contract"]["status"] == "measured_controlled_negative"
    assert payload["resource_contract"]["stop_reason"] == "hard_stop_12_gib"
    assert payload["resource_contract"]["worker_returncode"] == -15


def test_worker_parser_is_frozen_p6_h10_rank64_contract(tmp_path: Path):
    args = runner._parse_worker_args(
        [
            "--stage",
            "d2",
            "--case",
            "p6-h10-mpi2",
            "--input",
            str(tmp_path / "input.dat"),
            "--raw-dir",
            str(tmp_path / "raw"),
            "--record",
            str(tmp_path / "record.json"),
            "--marker-dir",
            str(tmp_path / "markers"),
            "--expected-source-sha",
            "c" * 40,
            "--expected-mpi-size",
            "2",
        ]
    )
    assert args.case == "p6-h10-mpi2"
    assert args.expected_sha == "c" * 40
    assert runner.D2_RANK == 64
    assert runner.D2_PREFIXES == (16, 32, 48, 64)
    with pytest.raises(SystemExit):
        runner._parse_worker_args(
            [
                "--stage",
                "d2",
                "--case",
                "p6-h10-mpi1",
                "--input",
                "x",
                "--raw-dir",
                "r",
                "--record",
                "q",
                "--marker-dir",
                "m",
                "--expected-source-sha",
                "c" * 40,
                "--expected-mpi-size",
                "2",
            ]
        )


def test_runner_ast_has_one_basis_build_release_before_online_and_no_forbidden_path():
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "build"
    ]
    basis_builds = [
        node
        for node in calls
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "basis"
    ]
    assert len(basis_builds) == 1
    release_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "release_construction_workspace"
    ]
    coarse_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "FullspaceAdaptiveCoarse"
    ]
    assert len(release_lines) == 1
    assert coarse_lines
    assert release_lines[0] < min(coarse_lines)
    prefix_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "prefix_audit"
    ]
    assert len(prefix_lines) == 1
    forbidden_calls = {
        "build_candidate_a",
        "build_candidate_c",
        "createAIJ",
        "assemble_matrix",
    }
    assert not {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
    }
    text = RUNNER_PATH.read_text(encoding="utf-8")
    assert "fullspace_second_order_impedance" not in text
    assert "FullspaceAdaptiveCoarse" in text
    assert "build_candidate" not in text
    assert "numeric allgather" not in text.lower()
    assert not any(
        isinstance(node, ast.Name)
        and node.id in {
            "build_candidate_a",
            "build_candidate_c",
            "FirstOrderImpedanceTransmission",
            "FixedSecondOrderLocalImpedance",
        }
        for node in ast.walk(tree)
    )
    worker = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_worker"
    )
    marker_calls = [
        call.args[1].value
        for call in ast.walk(worker)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_write_marker"
        and len(call.args) > 1
        and isinstance(call.args[1], ast.Constant)
    ]
    assert marker_calls == [
        "preflight",
        "mesh_mpc_topology",
        "trace_basis_build",
        "trace_workspace_release",
        "physical_action_build",
        "online_az_e",
        "canonical_evidence",
        "cleanup",
        "failure",
    ]
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "allgather"
        for node in ast.walk(tree)
    )


def test_runner_ast_keeps_worker_and_watchdog_boundaries():
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "benchmarks.run_task038_full3d_t5" not in imported_modules
    text = RUNNER_PATH.read_text(encoding="utf-8")
    assert "resource_authority_sample" in text
    assert "terminate_process_tree" in text
    assert "worker_process_group_popen_kwargs" in text
    assert "--watchdog-timeout-seconds" in text
    assert "default=0.0" in text
    assert "D2_MEMORY_HARD_STOP_BYTES" in text
    assert "FullspacePhysicalAction" in text
    assert "source_git_sha" in text
    assert 'record["mode_manifest"] = dict(mode_descriptor)' in text
    assert 'record["artifacts"]["mode_manifest"] = dict(mode_descriptor)' in text


def test_mode_path_is_defined_before_rank_zero_branch_and_used_after_barrier():
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    worker = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run_worker"
    )
    assignments = [
        node
        for node in ast.walk(worker)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "mode_path"
            for target in node.targets
        )
    ]
    assert len(assignments) == 1
    root_branch = next(
        node
        for node in ast.walk(worker)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Attribute)
        and node.test.left.attr == "rank"
        and any(
            isinstance(name, ast.Name) and name.id == "mode_path"
            for name in ast.walk(node)
        )
    )
    assert assignments[0].lineno < root_branch.lineno
    mode_descriptor = next(
        node
        for node in ast.walk(worker)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "mode_descriptor"
            for target in node.targets
        )
    )
    assert mode_descriptor.lineno > root_branch.lineno
    assert any(
        isinstance(node, ast.Name)
        and node.id == "mode_path"
        and isinstance(node.ctx, ast.Load)
        for node in ast.walk(mode_descriptor)
    )
