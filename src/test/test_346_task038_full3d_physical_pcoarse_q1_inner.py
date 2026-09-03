"""Focused pure contracts for the V16 Q1.2 inner-solve lane."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks import (
    run_task038_full3d_physical_pcoarse_q1_inner as runner,
    task038_full3d_physical_pcoarse_q1_inner_checker as checker,
)


SOURCE_SHA = "a" * 40


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode()
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source() -> dict[str, object]:
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


def _packet_line(key: dict[str, object], value: complex) -> bytes:
    key_bytes = json.dumps(
        key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return (
        json.dumps(
            {
                "schema_version": checker.SHARD_SCHEMA,
                "key": key,
                "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
                "value": [float(value.real), float(value.imag)],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _make_artifact(base: Path, mpi_size: int = 1) -> Path:
    root = base / f"mpi{mpi_size}"
    cache = root / "jit_cache"
    canonical = root / "raw" / "canonical"
    marker_dir = root / "markers"
    cache.mkdir(parents=True)
    canonical.mkdir(parents=True)
    marker_dir.mkdir()
    initial = checker._cache_snapshot(cache)
    (cache / "form.c").write_bytes(b"cached-form")
    cache_snapshot = checker._cache_snapshot(cache)

    for source_name, value in (("physical_rhs", 1.0), ("random", 2.0)):
        key = {"tuple": ["full_fe_dual", source_name, "0"]}
        shard_name = f"{source_name}.rank0000.jsonl"
        shard_path = canonical / shard_name
        shard_path.write_bytes(_packet_line(key, complex(value, 0.25)))
        shard = {
            "filename": shard_name,
            "packet_count": 1,
            "file_sha256": _sha256(shard_path),
            "key_digest_algorithm": checker.KEY_DIGEST,
            "dtype": "complex128",
            "packet_finite": True,
            "local_duplicate_count": 0,
            "rank": 0,
        }
        manifest = {
            "schema_version": checker.MANIFEST_SCHEMA,
            "role": "full_fe_dual",
            "mpi_size": mpi_size,
            "dtype": "complex128",
            "key_digest_algorithm": checker.KEY_DIGEST,
            "global_summed_packet_count": 1,
            "summed_local_duplicate_count": 0,
            "per_rank_shards": [shard],
            "extractor_audit": {
                "source": source_name,
                "role": "full_fe_dual",
            },
        }
        manifest_path = canonical / f"{source_name}.manifest.json"
        _write_json(manifest_path, manifest)

    markers = []
    for index, name in enumerate(checker.MARKER_ORDER):
        path = marker_dir / f"{index:03d}_{name}.json"
        _write_json(
            path,
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
        markers.append({"name": name, "sha256": _sha256(path)})
    marker_path = root / "marker_manifest.json"
    _write_json(marker_path, markers)

    samples = []
    children = []
    stages = tuple(f"precompile:{group}" for group in checker.JIT_GROUPS) + ("worker",)
    for index, stage in enumerate(stages):
        rss = 1000 + index
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
        result = {
            "stage": stage,
            "group": stage.split(":", 1)[1] if stage != "worker" else None,
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
            "rss_watchdog_bytes": 1_950_000_000,
            "record": f"children/{index:02d}.json",
        }
        if stage == "worker":
            _write_json(root / "worker.stdout.log", {})
            _write_json(root / "worker.stderr.log", {})
        else:
            children.append(result)
    process_path = root / "parent_process.jsonl"
    process_path.write_bytes(
        b"".join(
            (json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for sample in samples
        )
    )
    worker_result = {
        "stage": "worker",
        "argv": ["synthetic", "worker"],
        "returncode": 0,
        "stop_reason": None,
        "signals": [],
        "sample_count": 1,
        "peak_rss_bytes": 1000 + len(checker.JIT_GROUPS),
        "max_swap_bytes": 0,
        "all_status_readable": True,
        "process_group_gone": True,
        "lifecycle_failure": False,
        "warning_crossed": False,
        "rss_watchdog_bytes": 500_000_000 if mpi_size == 1 else None,
        "record_present": True,
    }

    source_records = []
    for source_name in checker.SOURCE_NAMES:
        role = (
            "physical_dual_rhs"
            if source_name == "physical_rhs"
            else "random_primal_to_physical_dual_rhs"
        )
        generation = {
            "name": source_name,
            "role": role,
            "formula": (
                "build_physical_rhs at degree-3 physical action"
                if source_name == "physical_rhs"
                else "A3 * finalized algebraic random primal"
            ),
        }
        if source_name == "physical_rhs":
            generation["rhs_facts"] = {"degree": 3}
        if source_name == "random":
            generation["source_input_unchanged_relative"] = 0.0
        before = {
            "finite": True,
            "norm": 1.0,
            "array_sha256": "b" * 64,
        }
        after = dict(before)
        pc = {
            "repeat_relative": 0.0,
            "linearity_relative": 0.0,
            "input_unchanged_relative": 0.0,
            "finite": True,
            "primal_finite": True,
            "owned_slave_max": 0.0,
        }
        cycle = {
            "cycle_index": 0,
            "start_iteration": 0,
            "end_iteration": 20,
            "iterations": 20,
            "reason": 1,
            "reported_final_residual": 0.0,
            "explicit_true_residual": 0.0,
            "matvec_count": 20,
            "pc_apply_count": 20,
            "wall_seconds": 0.01,
            "resource": {
                "memory_authority_bytes": 1000,
                "process_tree": {
                    "rss_bytes": 1000,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                },
                "job_no_swap": True,
            },
            "ksp_destroyed": True,
        }
        solver = {
            "settings": {
                "ksp_type": "fgmres",
                "pc_side": "right",
                "norm_type": "unpreconditioned",
                "restart": 20,
                "cycle_max_it": 20,
                "max_it": 5000,
                "start_iteration": 0,
                "residual_limit": 1.0e-6,
                "residual_replacement": True,
                "initial_guess_nonzero": False,
                "first_checkpoint_iteration": None,
                "checkpoint_interval": 20,
            },
            "initial_true_residual": 1.0,
            "cycles": [cycle],
            "iterations": 20,
            "final_true_residual": 0.0,
            "matvec_count": 20,
            "pc_apply_count": 20,
            "explicit_action_count": 2,
            "ksp_destroy_count": 1,
            "elapsed_seconds": 0.01,
            "resource_summary": {
                "sample_count": 1,
                "peak_memory_authority_bytes": 1000,
                "max_swap_bytes": 0,
                "all_status_readable": True,
            },
        }
        source_records.append(
            {
                "name": source_name,
                "generation": generation,
                "rhs_before": before,
                "rhs_after": after,
                "rank_input_facts": [
                    {
                        "rank": 0,
                        "before_sha256": "b" * 64,
                        "after_sha256": "b" * 64,
                    }
                ],
                "pc": pc,
                "solver": solver,
                "canonical": {
                    "manifest_relative_path": f"raw/canonical/{source_name}.manifest.json",
                    "manifest_sha256": _sha256(
                        canonical / f"{source_name}.manifest.json"
                    ),
                    "role": "full_fe_dual",
                    "packet_count": 1,
                    "mpi_size": mpi_size,
                },
            }
        )

    worker_record = {
        "schema": checker.WORKER_SCHEMA,
        "raw_facts_only": True,
        "source": _source(),
        "runtime": {
            "mpi_size": mpi_size,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "threads": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            },
            "abi_modules": {},
        },
        "input": {
            "template_relative_path": "input/templates/full3d_iterative_example.dat",
            "template_bytes": 2119,
            "template_sha256": checker.INPUT_SHA256,
            "resolved_config_bytes": 4076,
            "resolved_config_sha256": checker.RESOLVED_SHA256,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        },
        "mode_inventory": {
            "mode_count": 80,
            "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
            "degree": 3,
            "mesh_target_size_nm": 50.0,
        },
        "cache": {
            "path": "jit_cache",
            "xdg_cache_home": str(cache.resolve()),
            "binding": True,
            "snapshot": cache_snapshot,
        },
        "paths": {
            "cache_dir": "jit_cache",
            "record": "raw/worker_record.json",
            "canonical_dir": "raw/canonical",
        },
        "architecture": {
            "levels": [3, 1],
            "p3_only": True,
            "p6_shell": False,
            "p6_action": False,
            "global_physical_aij": False,
            "global_dense_dtn": False,
            "physical_factor": False,
            "numeric_allgather": False,
            "phase_once": "finalized_floquet_mpc_once_no_wrapper_reapply",
            "physical_action": {
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
                "trace_matrix_materialized": False,
                "global_volume_matrix_materialized": False,
                "global_constraint_matrix_materialized": False,
                "global_condensed_schur_materialized": False,
                "dense_cell_tensor_materialized": False,
                "dtn_mode_count": 80,
                "dtn_mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
                "factor_count": 0,
            },
            "positive_pmg": {
                "method": "same_mesh_hcurl_pmg_v1",
                "levels": [3, 1],
                "numeric_allgather": False,
                "physical_solve": False,
            },
        },
        "sources": source_records,
    }
    worker_path = root / "raw" / "worker_record.json"
    _write_json(worker_path, worker_record)
    worker_result["record_sha256"] = _sha256(worker_path)
    worker_result["stdout_sha256"] = _sha256(root / "worker.stdout.log")
    worker_result["stderr_sha256"] = _sha256(root / "worker.stderr.log")

    peak = max(sample["rss_bytes"] for sample in samples)
    parent_record = {
        "schema": checker.PARENT_SCHEMA,
        "source": _source(),
        "workflow": checker.WORKFLOW,
        "phase": checker.PHASE,
        "expected_mpi_size": mpi_size,
        "rss_watchdog_bytes": 500_000_000 if mpi_size == 1 else None,
        "staging_rss_watchdog_bytes": 1_950_000_000,
        "command": {"argv": ["synthetic"], "worker_argv": ["synthetic"], "cwd": "/repo"},
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "worker_record": "raw/worker_record.json",
            "marker_manifest": "marker_manifest.json",
        },
        "jit_groups": list(checker.JIT_GROUPS),
        "cache": {"initial": initial, "before_worker": cache_snapshot, "after_worker": cache_snapshot},
        "children": children,
        "process": {
            "sample_count": len(samples),
            "peak_rss_bytes": peak,
            "max_swap_bytes": 0,
            "all_status_readable": True,
        },
        "worker": worker_result,
        "markers": {
            "manifest_relative_path": "marker_manifest.json",
            "manifest_sha256": _sha256(marker_path),
            "names": list(checker.MARKER_ORDER),
        },
        "error": None,
    }
    _write_json(root / "parent_record.json", parent_record)
    return root


def test_checker_passes_minimal_mpi1_artifact(tmp_path: Path) -> None:
    root = _make_artifact(tmp_path)
    result = checker.check_artifact(root / "parent_record.json", SOURCE_SHA, 1)
    assert result["passed"] is True
    assert result["classification"] == "Q1_PHYSICAL_INNER_PASS"
    assert result["errors"] == []


def test_checker_pair_compares_canonical_maps(monkeypatch) -> None:
    maps = {
        1: {
            name: {"key": complex(index + 1, 0.25)}
            for index, name in enumerate(checker.SOURCE_NAMES)
        },
        2: {
            name: {"key": complex(index + 1, 0.25)}
            for index, name in enumerate(checker.SOURCE_NAMES)
        },
    }

    def fake_check_one(_path, _source_sha, mpi_size):
        return {"mpi_size": mpi_size}, maps[mpi_size]

    monkeypatch.setattr(checker, "_check_one", fake_check_one)
    passed = checker.check_pair("mpi1.json", "mpi2.json", SOURCE_SHA)
    assert passed["passed"] is True
    maps[2]["random"]["key"] += 1.0e-6
    failed = checker.check_pair("mpi1.json", "mpi2.json", SOURCE_SHA)
    assert failed["passed"] is False
    assert failed["classification"] == "Q1_PHYSICAL_INNER_MPI_IDENTITY_GATE_FAIL"


@pytest.mark.parametrize(
    ("mutation", "classification"),
    (
        ("residual", "Q1_PHYSICAL_INNER_NUMERICAL_GATE_FAIL"),
        ("worker_rss", "Q1_PHYSICAL_INNER_RESOURCE_GATE_FAIL"),
        ("resource_error", "Q1_PHYSICAL_INNER_RESOURCE_GATE_FAIL"),
        ("cache", "INFRASTRUCTURE_FAILURE_RETRYABLE"),
        ("ksp", "INFRASTRUCTURE_FAILURE_RETRYABLE"),
        ("input", "INFRASTRUCTURE_FAILURE_RETRYABLE"),
    ),
)
def test_checker_fails_closed_for_core_mutations(
    tmp_path: Path, mutation: str, classification: str
) -> None:
    root = _make_artifact(tmp_path)
    path = root / "parent_record.json"
    record = json.loads(path.read_text())
    if mutation == "residual":
        record["worker"] = record["worker"]
        worker = json.loads((root / "raw/worker_record.json").read_text())
        worker["sources"][0]["solver"]["final_true_residual"] = 2.0
        _write_json(root / "raw/worker_record.json", worker)
        record["worker"]["record_sha256"] = _sha256(root / "raw/worker_record.json")
    elif mutation == "worker_rss":
        limit = checker.MPI1_SOLVER_RSS_LIMIT
        record["worker"]["peak_rss_bytes"] = limit
        samples = [
            json.loads(line)
            for line in (root / "parent_process.jsonl").read_text().splitlines()
        ]
        for sample in samples:
            if sample["stage"] == "worker":
                sample["rss_bytes"] = limit
        (root / "parent_process.jsonl").write_text(
            "".join(
                json.dumps(sample, sort_keys=True, separators=(",", ":")) + "\n"
                for sample in samples
            )
        )
        record["process"]["peak_rss_bytes"] = limit
    elif mutation == "resource_error":
        record["error"] = "worker stopped"
        record["worker"]["stop_reason"] = "process_tree_rss_watchdog"
    elif mutation == "cache":
        record["cache"]["after_worker"]["manifest_sha256"] = "c" * 64
    elif mutation == "ksp":
        worker = json.loads((root / "raw/worker_record.json").read_text())
        worker["sources"][0]["solver"]["settings"]["ksp_type"] = "gmres"
        _write_json(root / "raw/worker_record.json", worker)
        record["worker"]["record_sha256"] = _sha256(root / "raw/worker_record.json")
    else:
        worker = json.loads((root / "raw/worker_record.json").read_text())
        worker["input"]["physical_model_sha256"] = "d" * 64
        _write_json(root / "raw/worker_record.json", worker)
        record["worker"]["record_sha256"] = _sha256(root / "raw/worker_record.json")
    _write_json(path, record)
    result = checker.check_artifact(path, SOURCE_SHA, 1)
    assert result["passed"] is False
    assert result["classification"] == classification


def test_runner_and_checker_import_boundaries() -> None:
    runner_tree = ast.parse(Path(runner.__file__).read_text())
    checker_tree = ast.parse(Path(checker.__file__).read_text())
    banned = {"mpi4py", "petsc4py", "dolfinx", "basix", "slepc4py"}
    checker_imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(checker_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert checker_imports.isdisjoint(banned)
    top_level_imports = []
    for node in runner_tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module.split(".", 1)[0])
    assert set(top_level_imports).isdisjoint(banned)


def test_parent_cli_keeps_fixed_inner_contract() -> None:
    args = runner.parse_args(
        [
            "--phase",
            runner.PHASE,
            "--mode",
            "parent",
            "--artifact-root",
            "/tmp/root",
            "--record",
            "/tmp/root/parent_record.json",
            "--source-sha",
            SOURCE_SHA,
            "--input",
            "/repo/input/templates/full3d_iterative_example.dat",
            "--mpi-size",
            "1",
        ]
    )
    assert args.phase == runner.PHASE
    assert args.mpi_size == 1
    assert runner.INNER_MAX_IT == 5000
    assert runner.INNER_RESTART == 20
    assert tuple(runner.JIT_GROUPS) == tuple(checker.JIT_GROUPS)
    assert runner.JIT_GROUPS[-1] == "q1-inner-p3-h50"
