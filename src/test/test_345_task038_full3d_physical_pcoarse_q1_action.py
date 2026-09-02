"""Pure contracts for the V16 Q1.1 action identity checker."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks import (
    run_task038_full3d_physical_pcoarse_q1_action as action_runner,
    task038_full3d_physical_pcoarse_q1_action_checker as checker,
)


SOURCE_SHA = "a" * 40
DIGEST = "b" * 64


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
        "input_sha256": checker.INPUT_SHA256,
    }


def _packet_line(key: dict[str, object], value: complex) -> bytes:
    key_bytes = json.dumps(
        key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    packet = {
        "schema_version": "task037.canonical-vector-shard.v1",
        "key": key,
        "key_sha256": hashlib.sha256(key_bytes).hexdigest(),
        "value": [float(value.real), float(value.imag)],
    }
    return (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _cache_facts(cache: Path) -> dict[str, object]:
    return checker._cache_snapshot(cache)


def _action_audit() -> dict[str, object]:
    return {
        "schema": "task038.fullspace-physical-action.v1",
        "volume_phase_application": checker.VOLUME_PHASE,
        "dtn_mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        "dtn_mode_count": 80,
        "global_aij_materialized": False,
        "global_schur_materialized": False,
        "ksp_created": False,
        "numeric_allgather": False,
        "trace_matrix_materialized": False,
        "global_volume_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "dense_cell_tensor_materialized": False,
        "factor_count": 0,
        "explicit_c_matrix_count": 0,
        "explicit_d_matrix_count": 0,
    }


def _make_artifact(base: Path, mpi_size: int, mismatch: bool = False) -> Path:
    root = base / f"mpi{mpi_size}"
    cache = root / "jit_cache"
    canonical = root / "raw" / "canonical"
    marker_dir = root / "markers"
    cache.mkdir(parents=True)
    canonical.mkdir(parents=True)
    marker_dir.mkdir()
    keys = (
        {"tuple": ["full_fe_dual", "edge-0"]},
        {"tuple": ["full_fe_dual", "edge-1"]},
    )
    values = (1.0 + 0.0j, 0.0 + (4.0 if mismatch else 2.0) * 1.0j)
    descriptors: dict[str, dict[str, dict[str, object]]] = {}
    for probe in checker.PROBE_NAMES:
        descriptors[probe] = {}
        for output in checker.OUTPUT_NAMES:
            scale = checker.ALPHA if output.endswith("scaled") else 1.0
            output_values = tuple(scale * value for value in values)
            rank_packets = (
                (tuple(zip(keys, output_values, strict=True)),)
                if mpi_size == 1
                else tuple(((keys[index], output_values[index]),) for index in range(2))
            )
            shard_rows = []
            for rank, packets in enumerate(rank_packets):
                path = canonical / f"{probe}.{output}.rank{rank:04d}.jsonl"
                payload = b"".join(_packet_line(key, value) for key, value in packets)
                path.write_bytes(payload)
                shard_rows.append(
                    {
                        "filename": path.name,
                        "packet_count": len(packets),
                        "file_sha256": _sha256(path),
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
                    "global_packet_count": 2,
                    "probe": probe,
                    "output": output,
                },
            }
            manifest_path = canonical / f"{probe}.{output}.manifest.json"
            _write_json(manifest_path, manifest)
            descriptors[probe][output] = {
                "manifest_relative_path": f"raw/canonical/{manifest_path.name}",
                "manifest_sha256": _sha256(manifest_path),
                "role": "full_fe_dual",
                "packet_count": 2,
                "mpi_size": mpi_size,
            }

    action_manifest = {
        "schema": checker.ACTION_MANIFEST_SCHEMA,
        "role": "full_fe_dual_action_outputs",
        "mpi_size": mpi_size,
        "probe_order": list(checker.PROBE_NAMES),
        "outputs": descriptors,
    }
    action_manifest_path = canonical / "action.manifest.json"
    _write_json(action_manifest_path, action_manifest)
    action_manifest_sha256 = _sha256(action_manifest_path)

    markers = []
    for index, name in enumerate(checker.MARKER_ORDER):
        marker_path = marker_dir / f"{index:03d}_{name}.json"
        _write_json(
            marker_path,
            {
                "schema": checker.MARKER_SCHEMA,
                "name": name,
                "marker_index": index,
                "timestamp_ns": index + 1,
                "facts": {
                    "source_sha": SOURCE_SHA,
                    "mpi_size": mpi_size,
                },
            },
        )
        markers.append({"name": name, "sha256": _sha256(marker_path)})
    marker_manifest = root / "marker_manifest.json"
    _write_json(marker_manifest, markers)

    stages = tuple(f"precompile:{group}" for group in checker.JIT_GROUPS) + ("worker",)
    samples = []
    results = []
    watchdog = checker.RSS_WATCHDOG if mpi_size == 1 else None
    for index, stage in enumerate(stages):
        rss = 1000 + index
        for exit_code, sample_rss in ((None, rss), (0, rss)):
            samples.append(
                {
                    "schema": checker.PROCESS_SCHEMA,
                    "root_pid": 1,
                    "stage": stage,
                    "timestamp_ns": index * 2 + (1 if exit_code is None else 2),
                    "exit_code": exit_code,
                    "rss_bytes": sample_rss,
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
            "rss_watchdog_bytes": watchdog,
        }
        results.append(result)
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

    probes = []
    for name in checker.PROBE_NAMES:
        source_generation: dict[str, object] = {"name": name}
        if name == "physical_component_derived":
            source_generation.update(
                {
                    "formula": "physical_rhs_compose_then_p63_adjoint",
                    "dual_role": "full_fe_dual",
                }
            )
        elif name == "r3_long_tail_derived":
            source_generation.update(
                {
                    "role": "full_fe_dual",
                    "source": "q1_source_authority_v7/r3.manifest.json",
                    "reconstruction": "reconstruct_canonical_full_fe_dual_vector",
                }
            )
        facts = {
            "array_sha256": DIGEST,
            "finite": True,
            "owned_slave_max": 0.0,
        }
        probes.append(
            {
                "name": name,
                "source_generation": source_generation,
                "source_before": facts,
                "source_after": dict(facts),
                "source_rank_facts": [
                    {
                        "rank": rank,
                        "before_sha256": DIGEST,
                        "after_sha256": DIGEST,
                        "input_unchanged": True,
                    }
                    for rank in range(mpi_size)
                ],
                "source_input_unchanged_relative": 0.0,
                "direct": dict(facts),
                "composed": dict(facts),
                "physical_galerkin_relative": 0.0,
                "repeat_relative_l2": 0.0,
                "linearity_relative_l2": 0.0,
                "p_p_h_work_identity_relative": 0.0,
                "work_lhs": [0.0, 0.0],
                "work_rhs": [0.0, 0.0],
                "projected_full_constraint_residual": 0.0,
                "algebraic_owned_slave_max": 0.0,
                "phase_application": "finalized_floquet_mpc_once",
            }
        )
    worker_path = root / "raw" / "worker_record.json"
    worker = {
        "schema": checker.WORKER_SCHEMA,
        "raw_facts_only": True,
        "source": _source(),
        "runtime": {
            "mpi_size": mpi_size,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
        },
        "input": {
            "template_relative_path": "input/templates/full3d_iterative_example.dat",
            "template_sha256": checker.INPUT_SHA256,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        },
        "cache": {"xdg_cache_home": str(cache.resolve()), "binding": True},
        "mode_inventory": {
            "mode_count": 80,
            "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
            "tested_pair": [6, 3],
            "tested_mesh_target_size_nm": 50.0,
        },
        "paths": {
            "cache_dir": "jit_cache",
            "record": "raw/worker_record.json",
            "action_manifest": "raw/canonical/action.manifest.json",
        },
        "action_manifest_sha256": action_manifest_sha256,
        "architecture": {
            "p3_action": _action_audit(),
            "p6_action": _action_audit(),
            "p63": {
                "operator": "same_mesh_owner_transfer",
                "numeric_allgather": False,
                "global_matrix_materialized": False,
            },
            "canonical_output_role": "full_fe_dual",
            "phase_once": "finalized_floquet_mpc_once",
        },
        "r3_authority": {
            "source_sha": checker.R3_SOURCE_SHA,
            "manifest_sha256": checker.R3_MANIFEST_SHA256,
            "shard_sha256": checker.R3_SHARD_SHA256,
            "packet_count": checker.R3_PACKET_COUNT,
            "role": "full_fe_dual",
            "selected_packet_count": checker.R3_PACKET_COUNT,
            "selected_facts": {"file_sha256": checker.R3_SHARD_SHA256},
        },
        "probes": probes,
    }
    _write_json(worker_path, worker)
    stdout = root / "worker.stdout.log"
    stderr = root / "worker.stderr.log"
    stdout.write_bytes(b"")
    stderr.write_bytes(b"")
    worker_result = dict(results[-1])
    worker_result.update(
        {
            "record_present": True,
            "record_sha256": _sha256(worker_path),
            "stdout_sha256": _sha256(stdout),
            "stderr_sha256": _sha256(stderr),
        }
    )
    parent = {
        "schema": checker.PARENT_SCHEMA,
        "source": _source(),
        "workflow": checker.WORKFLOW,
        "phase": checker.PHASE,
        "expected_mpi_size": mpi_size,
        "rss_watchdog_bytes": watchdog,
        "command": {"argv": ["synthetic"], "worker_argv": ["synthetic"], "cwd": "/repo"},
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "worker_record": "raw/worker_record.json",
            "action_manifest": "raw/canonical/action.manifest.json",
            "marker_manifest": "marker_manifest.json",
        },
        "jit_groups": list(checker.JIT_GROUPS),
        "cache": {
            "initial": _cache_facts(cache),
            "before_worker": _cache_facts(cache),
            "after_worker": _cache_facts(cache),
        },
        "children": [dict(result, group=group) for result, group in zip(results[:-1], checker.JIT_GROUPS, strict=True)],
        "process": process,
        "worker": worker_result,
        "markers": {
            "manifest_relative_path": "marker_manifest.json",
            "manifest_sha256": _sha256(marker_manifest),
            "names": list(checker.MARKER_ORDER),
        },
        "error": None,
    }
    parent_path = root / "parent_record.json"
    _write_json(parent_path, parent)
    return parent_path


def test_action_checker_synthetic_single_and_pair_pass(tmp_path: Path) -> None:
    mpi1 = _make_artifact(tmp_path / "pass", 1)
    mpi2 = _make_artifact(tmp_path / "pass", 2)
    single = checker.check_artifact(mpi1, SOURCE_SHA, 1)
    pair = checker.check_pair(mpi1, mpi2, SOURCE_SHA)
    assert single["passed"], single
    assert pair["passed"], pair
    assert pair["classification"] == "Q1_PHYSICAL_ACTION_IDENTITY_MPI_PAIR_PASS"
    assert all(
        set(values) == {"direct", "composed"}
        for values in pair["metrics"]["mpi_relative"].values()
    )


@pytest.mark.parametrize(
    "mutation", ("mpi_mismatch", "resource", "audit_binding", "single_gate")
)
def test_action_checker_mutations_fail_closed(tmp_path: Path, mutation: str) -> None:
    mpi1 = _make_artifact(tmp_path / mutation, 1)
    mpi2 = _make_artifact(
        tmp_path / mutation,
        2,
        mismatch=mutation == "mpi_mismatch",
    )
    if mutation == "resource":
        root = mpi1.parent
        parent = json.loads(root.joinpath("parent_record.json").read_text())
        samples = root.joinpath("parent_process.jsonl").read_text().splitlines()
        first = json.loads(samples[0])
        first["rss_bytes"] = checker.RSS_HARD
        samples[0] = json.dumps(first, sort_keys=True, separators=(",", ":"))
        root.joinpath("parent_process.jsonl").write_text("\n".join(samples) + "\n")
        parent["process"]["peak_rss_bytes"] = checker.RSS_HARD
        _write_json(root.joinpath("parent_record.json"), parent)
        result = checker.check_artifact(mpi1, SOURCE_SHA, 1)
        assert result["classification"] == "Q1_PHYSICAL_ACTION_RESOURCE_GATE_FAIL"
        return
    if mutation == "audit_binding":
        root = mpi1.parent
        manifest_path = root / "raw" / "canonical" / "random.direct.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["extractor_audit"]["output"] = "composed"
        _write_json(manifest_path, manifest)
        action_path = root / "raw" / "canonical" / "action.manifest.json"
        action = json.loads(action_path.read_text())
        action["outputs"]["random"]["direct"]["manifest_sha256"] = _sha256(manifest_path)
        _write_json(action_path, action)
        worker_path = root / "raw" / "worker_record.json"
        worker = json.loads(worker_path.read_text())
        worker["action_manifest_sha256"] = _sha256(action_path)
        _write_json(worker_path, worker)
        parent_path = root / "parent_record.json"
        parent = json.loads(parent_path.read_text())
        parent["worker"]["record_sha256"] = _sha256(worker_path)
        _write_json(parent_path, parent)
        result = checker.check_artifact(mpi1, SOURCE_SHA, 1)
        assert not result["passed"]
        assert result["classification"] == "INFRASTRUCTURE_FAILURE_RETRYABLE"
        assert any("extractor audit binding mismatch" in error for error in result["errors"])
        return
    if mutation == "single_gate":
        root = mpi1.parent
        shard_path = root / "raw" / "canonical" / "random.direct.rank0000.jsonl"
        shard_lines = shard_path.read_text().splitlines()
        packet = json.loads(shard_lines[0])
        packet["value"][0] = float(packet["value"][0]) + 1.0
        shard_lines[0] = json.dumps(packet, sort_keys=True, separators=(",", ":"))
        shard_path.write_text("\n".join(shard_lines) + "\n")
        manifest_path = root / "raw" / "canonical" / "random.direct.manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["per_rank_shards"][0]["file_sha256"] = _sha256(shard_path)
        _write_json(manifest_path, manifest)
        action_path = root / "raw" / "canonical" / "action.manifest.json"
        action = json.loads(action_path.read_text())
        action["outputs"]["random"]["direct"]["manifest_sha256"] = _sha256(manifest_path)
        _write_json(action_path, action)
        worker_path = root / "raw" / "worker_record.json"
        worker = json.loads(worker_path.read_text())
        worker["action_manifest_sha256"] = _sha256(action_path)
        _write_json(worker_path, worker)
        parent_path = root / "parent_record.json"
        parent = json.loads(parent_path.read_text())
        parent["worker"]["record_sha256"] = _sha256(worker_path)
        _write_json(parent_path, parent)
        result = checker.check_artifact(mpi1, SOURCE_SHA, 1)
        assert not result["passed"], result
        assert result["classification"] == "Q1_PHYSICAL_ACTION_IDENTITY_GATE_FAIL"
        assert any("probe:random" in error for error in result["errors"])
        return
    result = checker.check_pair(mpi1, mpi2, SOURCE_SHA)
    assert not result["passed"], result
    assert result["classification"] == "Q1_PHYSICAL_ACTION_MPI_IDENTITY_GATE_FAIL"


def test_action_import_boundary_and_policy_are_static() -> None:
    forbidden = {"mpi4py", "petsc4py", "dolfinx", "basix", "slepc4py"}
    for module in (action_runner, checker):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_imports = {
            node.module.split(".", 1)[0]
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
        }
        top_imports.update(
            alias.name.split(".", 1)[0]
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not top_imports & forbidden
        if module is checker:
            assert not top_imports & {"benchmarks", "src"}
    assert action_runner._rss_watchdog_bytes(1) == action_runner.authority_runner.RSS_WATCHDOG
    assert action_runner._rss_watchdog_bytes(2) is None
