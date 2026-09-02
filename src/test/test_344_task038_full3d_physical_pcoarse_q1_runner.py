"""Pure contracts for the V16 source-authority runner and checker."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys

import pytest

from benchmarks import (
    run_task038_full3d_physical_pcoarse_q1_action as action_runner,
    task038_full3d_physical_pcoarse_q1_checker as checker,
    run_task038_full3d_physical_pcoarse_q1 as runner,
)


SOURCE_SHA = "a" * 40
_DIGEST = "b" * 64


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    )


def _source(size: int) -> dict[str, object]:
    return {
        "commit_sha": SOURCE_SHA,
        "branch": checker.BRANCH,
        "upstream": f"origin/{checker.BRANCH}",
        "upstream_sha": SOURCE_SHA,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
        "python_executable": "/repo/.venv/bin/python",
        "python_prefix": "/repo/.venv",
        "input_path": "/repo/input/templates/full3d_iterative_example.dat",
        "input_sha256": checker.INPUT_SHA256,
    }


def _cache_snapshot(path: Path) -> dict[str, object]:
    manifest = {
        "cache_dir": str(path.resolve()),
        "artifacts": [],
        "artifact_count": 0,
    }
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return {"artifact_count": 0, "manifest_sha256": hashlib.sha256(encoded).hexdigest()}


def _packet_line(key: dict[str, object], value: tuple[float, float]) -> bytes:
    key_bytes = json.dumps(
        key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    packet = {
        "schema_version": checker.SHARD_SCHEMA,
        "key": key,
        "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
        "value": list(value),
    }
    return (
        json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _make_artifact(base: Path, mpi_size: int, values: tuple[tuple[float, float], ...] | None = None) -> Path:
    root = base / f"mpi{mpi_size}"
    cache = root / "jit_cache"
    raw = root / "raw"
    marker_dir = root / "markers"
    canonical = raw / "canonical"
    cache.mkdir(parents=True)
    raw.mkdir()
    marker_dir.mkdir()
    canonical.mkdir()
    values = values or ((1.0, 0.0), (0.0, 2.0))
    keys = tuple({"tuple": ["full_fe_dual", f"key-{index}"]} for index in range(2))
    packet_lines = tuple(_packet_line(key, values[index]) for index, key in enumerate(keys))
    shard_rows: list[dict[str, object]] = []
    rank_packets = (
        (packet_lines,) if mpi_size == 1 else tuple((line,) for line in packet_lines)
    )
    for rank, lines in enumerate(rank_packets):
        shard_path = canonical / f"r3.rank{rank:04d}.jsonl"
        payload = b"".join(lines)
        shard_path.write_bytes(payload)
        shard_rows.append(
            {
                "filename": shard_path.name,
                "packet_count": len(lines),
                "file_sha256": hashlib.sha256(payload).hexdigest(),
                "key_digest_algorithm": checker.KEY_DIGEST_ALGORITHM,
                "dtype": "complex128",
                "schema_version": checker.SHARD_SCHEMA,
                "packet_finite": True,
                "local_duplicate_count": 0,
                "rank": rank,
            }
        )
    manifest = {
        "schema_version": checker.MANIFEST_SCHEMA,
        "role": "full_fe_dual",
        "mpi_size": mpi_size,
        "dtype": "complex128",
        "key_digest_algorithm": checker.KEY_DIGEST_ALGORITHM,
        "global_summed_packet_count": 2,
        "summed_local_duplicate_count": 0,
        "per_rank_shards": shard_rows,
        "extractor_audit": {
            "role": "full_fe_dual",
            "local_packet_count": len(rank_packets[0]),
            "local_duplicate_count": 0,
            "global_packet_count": 2,
            "summed_local_duplicate_count": 0,
            "trace_mass_norm": "not_qualified",
            "hcurl_norm": "not_qualified",
            "source": "build_r3_long_tail_derived_probe",
            "numeric_allgather": False,
            "slave_exclusion": True,
        },
    }
    manifest_path = canonical / "r3.manifest.json"
    _write_json(manifest_path, manifest)
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    for index, name in enumerate(checker.MARKER_ORDER):
        _write_json(
            marker_dir / f"{index:03d}_{name}.json",
            {
                "schema": checker.MARKER_SCHEMA,
                "name": name,
                "marker_index": index,
                "timestamp_ns": index + 1,
                "facts": {
                    "phase": checker.PHASE,
                    "workflow": checker.WORKFLOW,
                    "source_sha": SOURCE_SHA,
                    "mpi_size": mpi_size,
                },
            },
        )
    marker_rows = [
        {
            "name": name,
            "sha256": hashlib.sha256(
                (marker_dir / f"{index:03d}_{name}.json").read_bytes()
            ).hexdigest(),
        }
        for index, name in enumerate(checker.MARKER_ORDER)
    ]
    marker_manifest = root / "marker_manifest.json"
    _write_json(marker_manifest, marker_rows)

    samples: list[dict[str, object]] = []
    stage_results: list[dict[str, object]] = []
    stages = tuple(f"precompile:{group}" for group in checker.JIT_GROUPS) + ("worker",)
    for index, stage in enumerate(stages):
        rss = 100 + index
        for exit_code in (None, 0):
            samples.append(
                {
                    "schema": checker.PROCESS_SCHEMA,
                    "root_pid": 1,
                    "stage": stage,
                    "timestamp_ns": index * 2 + (1 if exit_code is None else 2),
                    "exit_code": exit_code,
                    "rss_bytes": rss,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                    "job_no_swap": True,
                    "compiler_descendant_count": 0,
                    "members": [],
                    "authority": {},
                }
            )
        stage_results.append(
            {
                "stage": stage,
                "argv": ["synthetic", stage],
                "returncode": 0,
                "stop_reason": None,
                "signals": [],
                "sample_count": 1,
                "peak_rss_bytes": rss,
                "max_swap_bytes": 0,
                "all_status_readable": True,
                "process_group_gone": True,
                "lifecycle_failure": False,
                "warning_crossed": False,
            }
        )
    process_path = root / "parent_process.jsonl"
    process_path.write_bytes(
        b"".join(
            (json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for sample in samples
        )
    )
    process = {
        "sample_count": len(samples),
        "peak_rss_bytes": max(sample["rss_bytes"] for sample in samples),
        "max_swap_bytes": 0,
        "all_status_readable": True,
    }
    worker_record = {
        "schema": checker.WORKER_SCHEMA,
        "raw_facts_only": True,
        "source": _source(mpi_size),
        "runtime": {
            "mpi_size": mpi_size,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "threads": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
            "abi_modules": {
                name: f"/repo/.venv/lib/{name}.so"
                for name in ("mpi4py", "petsc4py", "slepc4py", "dolfinx", "basix")
            },
        },
        "input": {
            "template_relative_path": "input.dat",
            "template_bytes": 1,
            "template_sha256": checker.INPUT_SHA256,
            "resolved_config_bytes": 1,
            "resolved_config_sha256": _DIGEST,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        },
        "cache": {
            "xdg_cache_home": str(cache.resolve()),
            "binding": True,
        },
        "target_mode": {
            "mode_count": 80,
            "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        },
        "paths": {"cache_dir": "jit_cache", "record": "raw/worker_record.json"},
        "old_authority": {
            "source_sha": checker.OLD_SOURCE_SHA,
            "manifest_relative_path": checker.OLD_MANIFEST.as_posix(),
            "manifest_sha256": checker.OLD_MANIFEST_SHA256,
            "shard_filename": checker.OLD_SHARD_FILENAME,
            "shard_sha256": checker.OLD_SHARD_SHA256,
            "packet_count": checker.OLD_PACKET_COUNT,
            "h10": {
                "selected_key_count": checker.OLD_PACKET_COUNT,
                "extracted_key_count": checker.OLD_PACKET_COUNT,
                "selected_finite": True,
                "extracted_finite": True,
                "extraction_repeat_finite": True,
                "reconstruction_relative_l2": 0.0,
                "extraction_repeat_relative_l2": 0.0,
                "input_before_digest": _DIGEST,
                "input_after_digest": _DIGEST,
                "input_unchanged": True,
                "extraction_digest": _DIGEST,
                "extraction_repeat_digest": _DIGEST,
                "source_role": "full_fe",
                "canonical_role": "full_fe",
            },
        },
        "h50_bridge": {
            "source_input_unchanged": True,
            "source_before_sha256": _DIGEST,
            "source_after_sha256": _DIGEST,
            "action_vector": {
                "role": "fullspace_slave_zero",
                "finite": True,
                "norm": 1.0,
                "owned_slave_max": 0.0,
                "owned_slave_count": 0,
                "array_sha256": _DIGEST,
            },
            "canonical_field": {
                "canonical_role": "full_fe",
                "finite": True,
                "norm": 1.0,
                "packet_count": 2,
                "array_sha256": _DIGEST,
            },
            "bridge_audit": {
                "schema": "task038.nonmatching_hcurl_primal_bridge.v1",
                "method": "dolfinx.create_interpolation_data+interpolate_nonmatching",
                "padding": 1.0e-10,
                "target_mpc_homogenize_count": 1,
                "target_mpc_backsubstitution_count": 1,
                "global_matrix": False,
                "numeric_allgather": False,
            },
        },
        "r3": {
            "schema": "task038.r3-long-tail-derived.current-h50.v1",
            "name": "r3_long_tail_derived",
            "formula": "r50=b50-A6*x50; r3=P63^H*r50",
            "mapped_primal_authority_role": "full_fe",
            "mapped_primal_action_storage": "fullspace_slave_zero",
            "residual_role": "full_fe_dual",
            "probe_role": "full_fe_dual",
            "apply_count": 2,
            "repeat_relative_l2": 0.0,
            "input_unchanged": True,
            "finite": True,
            "owned_slave_max": 0.0,
            "norm": 2.0,
            "physical_rhs_facts": {"finite": True},
            "action_input_before_sha256": _DIGEST,
            "action_input_after_first_sha256": _DIGEST,
            "action_input_after_second_sha256": _DIGEST,
            "manifest": {
                "manifest_relative_path": "raw/canonical/r3.manifest.json",
                "manifest_sha256": manifest_sha,
                "role": "full_fe_dual",
                "packet_count": 2,
                "mpi_size": mpi_size,
            },
        },
    }
    worker_path = raw / "worker_record.json"
    _write_json(worker_path, worker_record)
    stdout_path = root / "worker.stdout.log"
    stderr_path = root / "worker.stderr.log"
    stdout_path.write_bytes(b"")
    stderr_path.write_bytes(b"")
    worker_result = dict(stage_results[-1])
    worker_result.update(
        {
            "record_present": True,
            "record_sha256": hashlib.sha256(worker_path.read_bytes()).hexdigest(),
            "stdout_sha256": hashlib.sha256(b"").hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        }
    )
    cache_facts = _cache_snapshot(cache)
    parent = {
        "schema": checker.PARENT_SCHEMA,
        "source": _source(mpi_size),
        "command": {"argv": ["synthetic"], "worker_argv": ["synthetic"], "cwd": "/repo"},
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "worker_record": "raw/worker_record.json",
            "marker_manifest": "marker_manifest.json",
        },
        "children": [dict(item, group=group) for item, group in zip(stage_results[:-1], checker.JIT_GROUPS)],
        "cache": {
            "initial": cache_facts,
            "before_worker": cache_facts,
            "after_worker": cache_facts,
            "worker_binding": worker_record["cache"],
        },
        "process": process,
        "worker": worker_result,
        "markers": {
            "manifest_relative_path": "marker_manifest.json",
            "manifest_sha256": hashlib.sha256(marker_manifest.read_bytes()).hexdigest(),
            "names": list(checker.MARKER_ORDER),
        },
        "error": None,
    }
    parent_path = root / "parent_record.json"
    _write_json(parent_path, parent)
    return parent_path


def test_synthetic_artifact_and_pair_pass(tmp_path: Path) -> None:
    mpi1 = _make_artifact(tmp_path / "pass", 1)
    mpi2 = _make_artifact(tmp_path / "pass", 2)
    one = checker.check_artifact(mpi1, SOURCE_SHA, 1)
    pair = checker.check_pair(mpi1, mpi2, SOURCE_SHA)
    assert one["passed"], one
    assert pair["passed"], pair
    assert pair["classification"] == "SOURCE_AUTHORITY_MPI_PAIR_PASS"


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_key",
        "duplicate_json",
        "nonfinite_json",
        "cache_drift",
        "swap",
        "rss",
        "resource_watchdog",
        "pair_resource_watchdog",
        "missing_exit",
        "malformed_shard_metadata_single",
        "malformed_shard_metadata_pair",
        "marker_hash",
        "shard_duplicate",
        "shard_hash",
        "mpi_mismatch",
        "exit_race_accept",
        "exit_race_nonzero",
        "exit_race_fake",
        "exit_race_bool_code",
    ),
)
def test_checker_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    if mutation in {
        "mpi_mismatch",
        "pair_resource_watchdog",
        "malformed_shard_metadata_pair",
    }:
        mpi1 = _make_artifact(tmp_path / "pair", 1)
        mpi2_values = ((3.0, 0.0), (0.0, 4.0)) if mutation == "mpi_mismatch" else None
        mpi2 = _make_artifact(tmp_path / "pair", 2, mpi2_values)
        if mutation == "pair_resource_watchdog":
            parent_path = mpi2
            parent = json.loads(parent_path.read_text())
            parent["worker"]["stop_reason"] = "process_tree_rss_watchdog"
            _write_json(parent_path, parent)
        elif mutation == "malformed_shard_metadata_pair":
            manifest_path = mpi1.parent / "raw" / "canonical" / "r3.manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["per_rank_shards"][0] = ["not-a-metadata-object"]
            _write_json(manifest_path, manifest)
        result = checker.check_pair(mpi1, mpi2, SOURCE_SHA)
        assert not result["passed"], result
        if mutation == "mpi_mismatch":
            assert result["classification"] == "SOURCE_AUTHORITY_MPI_IDENTITY_FAIL"
        elif mutation in {
            "pair_resource_watchdog",
            "malformed_shard_metadata_pair",
        }:
            expected = (
                "SOURCE_AUTHORITY_RESOURCE_GATE_FAIL"
                if mutation == "pair_resource_watchdog"
                else "INFRASTRUCTURE_FAILURE_RETRYABLE"
            )
            assert result["classification"] == expected
        return
    parent_path = _make_artifact(tmp_path / mutation, 1)
    root = parent_path.parent
    if mutation == "missing_key":
        parent = json.loads(parent_path.read_text())
        del parent["source"]
        _write_json(parent_path, parent)
    elif mutation == "duplicate_json":
        parent_path.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
    elif mutation == "nonfinite_json":
        parent_path.write_text('{"schema":NaN}\n', encoding="utf-8")
    elif mutation == "cache_drift":
        (root / "jit_cache" / "drift.c").write_bytes(b"drift")
    elif mutation == "swap":
        process_path = root / "parent_process.jsonl"
        lines = process_path.read_text().splitlines()
        sample = json.loads(lines[0])
        sample["swap_bytes"] = 1
        lines[0] = json.dumps(sample, sort_keys=True, separators=(",", ":"))
        process_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mutation == "rss":
        process_path = root / "parent_process.jsonl"
        lines = process_path.read_text().splitlines()
        sample = json.loads(lines[0])
        sample["rss_bytes"] = checker.RSS_HARD
        lines[0] = json.dumps(sample, sort_keys=True, separators=(",", ":"))
        process_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mutation == "resource_watchdog":
        parent = json.loads(parent_path.read_text())
        parent["worker"]["stop_reason"] = "process_tree_rss_watchdog"
        _write_json(parent_path, parent)
        result = checker.check_artifact(parent_path, SOURCE_SHA, 1)
        assert not result["passed"], result
        assert result["classification"] == "SOURCE_AUTHORITY_RESOURCE_GATE_FAIL"
        return
    elif mutation == "missing_exit":
        process_path = root / "parent_process.jsonl"
        lines = process_path.read_text().splitlines()
        del lines[1]
        process_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif mutation == "malformed_shard_metadata_single":
        manifest_path = root / "raw" / "canonical" / "r3.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["per_rank_shards"][0] = ["not-a-metadata-object"]
        _write_json(manifest_path, manifest)
    elif mutation in {
        "exit_race_accept",
        "exit_race_nonzero",
        "exit_race_fake",
        "exit_race_bool_code",
    }:
        process_path = root / "parent_process.jsonl"
        lines = process_path.read_text().splitlines()
        sample = json.loads(lines[0])
        sample.update(
            {
                "all_status_readable": False,
                "rss_bytes": None,
                "swap_bytes": None,
            }
        )
        if mutation == "exit_race_accept":
            sample.update(
                {
                    "process_tree_exit_race_observed": True,
                    "worker_exit_code_observed_after_sample": 0,
                }
            )
        elif mutation == "exit_race_nonzero":
            sample.update(
                {
                    "process_tree_exit_race_observed": True,
                    "worker_exit_code_observed_after_sample": -15,
                }
            )
        elif mutation == "exit_race_bool_code":
            sample.update(
                {
                    "process_tree_exit_race_observed": True,
                    "worker_exit_code_observed_after_sample": False,
                }
            )
        else:
            sample.update(
                {
                    "all_status_readable": True,
                    "process_tree_exit_race_observed": True,
                    "worker_exit_code_observed_after_sample": 0,
                }
            )
        lines[0] = json.dumps(sample, sort_keys=True, separators=(",", ":"))
        process_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        parent = json.loads(parent_path.read_text())
        parent["children"][0]["peak_rss_bytes"] = 0
        _write_json(parent_path, parent)
    elif mutation == "marker_hash":
        marker = root / "markers" / "000_paths_ready.json"
        marker.write_bytes(marker.read_bytes() + b" ")
    elif mutation in {"shard_duplicate", "shard_hash"}:
        shard = root / "raw" / "canonical" / "r3.rank0000.jsonl"
        payload = shard.read_bytes()
        shard.write_bytes(payload + payload.splitlines(keepends=True)[0] if mutation == "shard_duplicate" else payload[:-1] + b"x\n")
    result = checker.check_artifact(parent_path, SOURCE_SHA, 1)
    if mutation == "exit_race_accept":
        assert result["passed"], result
        return
    assert not result["passed"], (mutation, result)
    if mutation in {"exit_race_nonzero", "exit_race_fake", "exit_race_bool_code"}:
        assert result["classification"] == "INFRASTRUCTURE_FAILURE_RETRYABLE"
    if mutation == "malformed_shard_metadata_single":
        assert result["classification"] == "INFRASTRUCTURE_FAILURE_RETRYABLE"


def test_runner_checker_import_and_ast_contract() -> None:
    forbidden = {"mpi4py", "petsc4py", "dolfinx", "basix", "slepc4py"}
    runner_source = Path(runner.__file__).read_text(encoding="utf-8")
    checker_source = Path(checker.__file__).read_text(encoding="utf-8")
    runner_tree = ast.parse(runner_source)
    checker_tree = ast.parse(checker_source)
    top_runner_imports = {
        node.module.split(".", 1)[0]
        for node in runner_tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    top_runner_imports.update(
        alias.name.split(".", 1)[0]
        for node in runner_tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not top_runner_imports & forbidden
    worker = next(node for node in runner_tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_worker")
    worker_imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(worker)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    worker_imports.update(
        alias.name.split(".", 1)[0]
        for node in ast.walk(worker)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert {"mpi4py", "petsc4py", "dolfinx"} <= worker_imports
    checker_imports = {
        node.module.split(".", 1)[0]
        for node in ast.walk(checker_tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    checker_imports.update(
        alias.name.split(".", 1)[0]
        for node in ast.walk(checker_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not checker_imports & forbidden
    marker_calls = [
        node
        for node in ast.walk(worker)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_worker_marker"
    ]
    assert len(marker_calls) == 8
    assert all(call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "comm" for call in marker_calls)
    assert "wanted_packets" not in runner_source
    parent = next(node for node in runner_tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_parent")
    assert "**worker_result" in ast.get_source_segment(runner_source, parent)
    assert "def check_pair" in checker_source


def test_action_rss_policy_preserves_default_and_disables_mpi2_kill() -> None:
    assert runner._run_parent_child.__kwdefaults__["rss_watchdog_bytes"] == runner.RSS_WATCHDOG
    assert action_runner._rss_watchdog_bytes(1) == runner.RSS_WATCHDOG
    assert action_runner._rss_watchdog_bytes(2) is None


def test_marker_rank0_and_fresh_root_contract(tmp_path: Path) -> None:
    root, cache = runner._prepare_parent_root(tmp_path / "fresh")
    assert root.is_dir() and cache.is_dir()
    with pytest.raises(FileExistsError):
        runner._prepare_parent_root(root)
    writes: list[str] = []
    barriers: list[int] = []

    class Comm:
        def __init__(self, rank: int):
            self.rank = rank

        def barrier(self) -> None:
            barriers.append(self.rank)

    original = runner.write_marker
    runner.write_marker = lambda _directory, name, _facts, **_kwargs: writes.append(name)
    try:
        runner._worker_marker(Comm(1), root, "ignored", SOURCE_SHA, mpi_size=2)
        runner._worker_marker(Comm(0), root, "first", SOURCE_SHA, mpi_size=2)
        runner._worker_marker(Comm(0), root, "second", SOURCE_SHA, mpi_size=2)
    finally:
        runner.write_marker = original
    assert writes == ["first", "second"]
    assert barriers == [1, 0, 0]


def test_parent_child_uses_repository_cwd_for_module_import(tmp_path: Path) -> None:
    sample_path = tmp_path / "parent_process.jsonl"
    stdout_path = tmp_path / "child.stdout.log"
    stderr_path = tmp_path / "child.stderr.log"
    result = runner._run_parent_child(
        [
            sys.executable,
            "-c",
            "import benchmarks, os; print(os.getcwd())",
        ],
        sample_path,
        "tiny-import-cwd",
        stdout_path,
        stderr_path,
    )
    assert result["returncode"] == 0, result
    assert result["stop_reason"] is None, result
    assert result["process_group_gone"] is True, result
    assert stdout_path.read_text(encoding="utf-8").strip() == str(runner.REPO_ROOT)


def test_sample_parent_uses_vanished_safe_snapshot(tmp_path: Path, monkeypatch) -> None:
    snapshot = {
        "rss_bytes": 321,
        "swap_bytes": 0,
        "all_status_readable": True,
        "compiler_descendant_count": 0,
        "members": [],
        "vanished_pids": [1234],
    }
    monkeypatch.setattr(runner, "process_tree_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(
        "benchmarks.task034_wsl_resources.cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": False,
            "memory_current_bytes": None,
            "swap_current_bytes": None,
        },
    )
    monkeypatch.setattr(
        "benchmarks.task034_wsl_resources.vmstat_swap_pages",
        lambda: {"pswpin_pages": 0, "pswpout_pages": 0},
    )
    sample_path = tmp_path / "samples.jsonl"
    sample = runner._sample_parent("vanished")
    runner.append_jsonl(sample_path, sample)
    written = json.loads(sample_path.read_text(encoding="utf-8"))
    assert sample["rss_bytes"] == 321
    assert sample["swap_bytes"] == 0
    assert sample["all_status_readable"] is True
    assert sample["job_no_swap"] is True
    assert sample["authority"]["process_tree"] is snapshot
    assert written["authority"]["process_tree"]["vanished_pids"] == [1234]


def test_sample_parent_unreadable_snapshot_fails_closed(tmp_path: Path, monkeypatch) -> None:
    snapshot = {
        "rss_bytes": None,
        "swap_bytes": None,
        "all_status_readable": False,
        "compiler_descendant_count": 0,
        "members": [],
        "unreadable_pids": [4321],
        "vanished_pids": [],
    }
    monkeypatch.setattr(runner, "process_tree_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(
        "benchmarks.task034_wsl_resources.cgroup_snapshot",
        lambda _pid: {
            "dedicated_job_cgroup": False,
            "memory_current_bytes": None,
            "swap_current_bytes": None,
        },
    )
    monkeypatch.setattr(
        "benchmarks.task034_wsl_resources.vmstat_swap_pages",
        lambda: {"pswpin_pages": 0, "pswpout_pages": 0},
    )
    sample_path = tmp_path / "samples.jsonl"
    sample = runner._sample_parent("unreadable")
    runner.append_jsonl(sample_path, sample)
    assert sample["rss_bytes"] is None
    assert sample["swap_bytes"] is None
    assert sample["all_status_readable"] is False
    assert sample["job_no_swap"] is False
    assert sample["authority"]["process_tree"]["unreadable_pids"] == [4321]
    summary = runner._process_summary(sample_path)
    assert summary == {
        "sample_count": 1,
        "peak_rss_bytes": 0,
        "max_swap_bytes": 0,
        "all_status_readable": False,
    }


def test_run_parent_child_confirms_rc0_after_bounded_exit_wait(
    tmp_path: Path, monkeypatch
) -> None:
    class Process:
        pid = 12345
        returncode = None
        wait_timeout = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.wait_timeout = timeout
            self.returncode = 0
            return self.returncode

    def sample(stage: str, exit_code=None) -> dict[str, object]:
        return {
            "schema": runner.PROCESS_SCHEMA,
            "root_pid": 1,
            "stage": stage,
            "timestamp_ns": 1,
            "exit_code": exit_code,
            "rss_bytes": None if exit_code is None else 17,
            "swap_bytes": None if exit_code is None else 0,
            "all_status_readable": exit_code is not None,
            "job_no_swap": exit_code is not None,
            "compiler_descendant_count": 0,
            "members": [],
            "authority": {},
        }

    process = Process()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(runner, "_sample_parent", sample)
    monkeypatch.setattr(runner, "_process_group_gone", lambda _pid: True)
    monkeypatch.setattr(
        runner.os,
        "killpg",
        lambda *args: (_ for _ in ()).throw(AssertionError("unexpected signal")),
    )
    sample_path = tmp_path / "samples.jsonl"
    result = runner._run_parent_child(
        ["tiny"], sample_path, "exit-race", tmp_path / "stdout", tmp_path / "stderr"
    )
    rows = [json.loads(line) for line in sample_path.read_text().splitlines()]
    assert result["returncode"] == 0
    assert result["stop_reason"] is None
    assert result["signals"] == []
    assert result["all_status_readable"] is True
    assert result["process_group_gone"] is True
    assert process.wait_timeout == runner.TERMINATION_GRACE_SECONDS
    assert rows[0]["all_status_readable"] is False
    assert rows[0]["rss_bytes"] is None and rows[0]["swap_bytes"] is None
    assert rows[0]["process_tree_exit_race_observed"] is True
    assert rows[0]["worker_exit_code_observed_after_sample"] == 0


def test_run_parent_child_does_not_exempt_live_unreadable(tmp_path: Path, monkeypatch) -> None:
    class Process:
        pid = 54321
        returncode = None

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            if self.returncode is None:
                raise runner.subprocess.TimeoutExpired(["tiny"], timeout)
            return self.returncode

    process = Process()
    sent: list[int] = []

    def sample(stage: str, exit_code=None) -> dict[str, object]:
        return {
            "schema": runner.PROCESS_SCHEMA,
            "root_pid": 1,
            "stage": stage,
            "timestamp_ns": 1,
            "exit_code": exit_code,
            "rss_bytes": None if exit_code is None else 17,
            "swap_bytes": None if exit_code is None else 0,
            "all_status_readable": exit_code is not None,
            "job_no_swap": exit_code is not None,
            "compiler_descendant_count": 0,
            "members": [],
            "authority": {},
        }

    def killpg(_pid: int, sig: int) -> None:
        sent.append(sig)
        if sig == runner.signal.SIGTERM:
            process.returncode = -15

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(runner, "_sample_parent", sample)
    monkeypatch.setattr(runner, "_process_group_gone", lambda _pid: True)
    monkeypatch.setattr(runner.os, "killpg", killpg)
    sample_path = tmp_path / "samples.jsonl"
    result = runner._run_parent_child(
        ["tiny"], sample_path, "live-unreadable", tmp_path / "stdout", tmp_path / "stderr"
    )
    rows = [json.loads(line) for line in sample_path.read_text().splitlines()]
    assert result["returncode"] == -15
    assert result["stop_reason"] == "authority_unreadable"
    assert result["signals"] == ["SIGTERM"]
    assert result["all_status_readable"] is False
    assert "process_tree_exit_race_observed" not in rows[0]
