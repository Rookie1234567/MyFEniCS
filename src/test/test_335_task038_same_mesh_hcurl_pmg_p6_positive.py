"""Focused contracts for the thin p6 same-mesh positive lane."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task038_full3d_same_mesh_hcurl_pmg_p6_positive as worker
from benchmarks import task038_full3d_same_mesh_hcurl_pmg_p6_positive_checker as checker


SOURCE_SHA = "a" * 40
REPO = Path(__file__).resolve().parents[2]
INPUT = REPO / "input/templates/full3d_iterative_example.dat"


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _command(root: Path, raw: Path, jit: Path, checkpoints: Path, record: Path) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        "-m",
        worker.MODULE,
        "--stage",
        worker.STAGE,
        "--case",
        worker.CASE,
        "--source",
        "random",
        "--raw-dir",
        str(raw),
        "--jit-cache-dir",
        str(jit),
        "--checkpoint-root",
        str(checkpoints),
        "--record",
        str(record),
        "--expected-source-sha",
        SOURCE_SHA,
        "--expected-mpi-size",
        "1",
        "--input",
        str(INPUT.resolve()),
    ]


def _make_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / "case"
    raw = root / "worker_raw"
    markers = raw / "markers"
    jit = root / "jit_cache"
    checkpoints = root / "checkpoints"
    record_path = root / "worker_record.json"
    raw.mkdir(parents=True)
    markers.mkdir()
    jit.mkdir()
    checkpoints.mkdir()

    source_values = np.asarray([1.0 + 2.0j, 0.0j, 2.0 - 1.0j], dtype=np.complex128)
    input_values = np.asarray([1.0 + 0.0j, 0.0j, 2.0 + 0.0j], dtype=np.complex128)
    rhs_values = np.asarray([2.0 + 0.0j, 0.0j, 4.0 + 0.0j], dtype=np.complex128)
    solution_values = np.asarray([1.0 + 0.0j, 0.0j, 2.0 + 0.0j], dtype=np.complex128)
    residual_values = np.zeros(3, dtype=np.complex128)
    npz_path = raw / "positive_probe.npz"
    np.savez_compressed(
        npz_path,
        source_before=source_values,
        source_after=source_values,
        input_before=input_values,
        input_after=input_values,
        rhs_before=rhs_values,
        rhs_after=rhs_values,
        rhs_repeat=rhs_values,
        final_solution=solution_values,
        final_action=rhs_values,
        final_true_residual=residual_values,
    )

    checkpoint_dir = checkpoints / "checkpoint-500"
    checkpoint_dir.mkdir()
    shard = checkpoint_dir / "solution_rank0.npy"
    np.save(shard, solution_values, allow_pickle=False)
    identities = {
        "input_identity_authority": {"source": "random", "input": "frozen"},
        "operator_identity_authority": {"levels": [6, 3, 1], "matrix_free": True},
        "physical_model_authority": {"same_mesh": True, "wavelength_nm": 13.5},
    }
    for name, value in list(identities.items()):
        identities[name.replace("_authority", "_sha256")] = _stable(value)
    descriptor = {
        "relative_path": shard.name,
        "bytes": shard.stat().st_size,
        "sha256": _sha(shard),
        "dtype": str(solution_values.dtype),
        "shape": list(solution_values.shape),
    }
    manifest = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 500,
        "explicit_true_residual": 0.0,
        **{name: identities[name] for name in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256")},
        "source_sha": SOURCE_SHA,
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "ranks": [{"rank": 0, "ownership": {"ownership_range": [0, 3]}, "solution": descriptor}],
    }
    manifest_path = checkpoint_dir / "manifest.json"
    _write_json(manifest_path, manifest)

    command = _command(root, raw, jit, checkpoints, record_path)
    cycles = []
    for index in range(25):
        start = index * 20
        cycles.append(
            {
                "cycle_index": index,
                "start_iteration": start,
                "end_iteration": start + 20,
                "iterations": 20,
                "reason": 1,
                "initial_guess_nonzero": index != 0,
                "reported_final_residual": 0.0,
                "explicit_true_residual": 0.0,
                "matvec_count": 20 if index == 0 else 21,
                "pc_apply_count": 21,
                "wall_seconds": 0.01,
                "resource": {"scope": "rank-root-diagnostic"},
                "ksp_destroyed": True,
            }
        )
    pc_rows = [
        {
            "apply_index": index,
            "p6_smoother_apply_count": 2,
            "p63_adjoint_count": 1,
            "p63_primal_count": 1,
            "lower_cycle_count": 1,
            "p1_solve_count": 1,
            "p1_relative_residual": 0.0,
            "output_finite": True,
            "owned_slave_max": 0.0,
        }
        for index in range(525)
    ]
    record = {
        "schema": worker.RECORD_SCHEMA,
        "stage": worker.STAGE,
        "case": worker.CASE,
        "source_name": "random",
        "mpi_size": 1,
        "branch": worker.BRANCH,
        "command": command,
        "raw_dir": str(raw),
        "record_path": str(record_path),
        "checkpoint_root": str(checkpoints),
        "provenance": {
            "source_sha": SOURCE_SHA,
            "branch": worker.BRANCH,
            "clean_source_tree": True,
            "qualified_activation": "1",
            "python_executable": command[0],
            "mpi_size": 1,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "threads": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
            "abi_modules": {name: str(root / f"{name}.so") for name in ("mpi4py", "petsc4py", "dolfinx", "basix")},
            "stage": worker.STAGE,
            "case": worker.CASE,
            "source_name": "random",
            "input_path": str(INPUT.resolve()),
            "input_sha256": _sha(INPUT),
            "raw_dir": str(raw),
            "checkpoint_root": str(checkpoints),
            "record_path": str(record_path),
            "jit_cache_dir": str(jit),
            "isolated_jit_cache": True,
            "command": command,
        },
        "identities": identities,
        "architecture": {
            "levels": [6, 3, 1],
            "pairs": [[6, 3], [3, 1]],
            "same_physical_mesh": True,
            "p6_matrix_free": True,
            "p3_sparse_allowed": True,
            "p1_sparse_allowed": True,
            "p6_global_aij": False,
            "high_order_global_aij": False,
            "global_dense_transfer": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "p6_factor": False,
            "physical_solve": False,
            "dtn": False,
            "recovery": False,
            "outer_ksp_created": True,
            "source_is_pde_rhs": False,
            "setup_audit": {
                "schema": "task038.same_mesh_hcurl_pmg.setup.v1",
                "profile": {"levels": [6, 3, 1], "same_physical_mesh": True},
                "architecture": {
                    "p6_matrix_free": True,
                    "p6_global_aij": False,
                    "global_dense_transfer": False,
                    "global_transfer_matrix": False,
                    "numeric_allgather": False,
                    "p6_factor": False,
                    "physical_solve": False,
                    "dtn": False,
                    "recovery": False,
                    "high_order_global_aij": False,
                    "outer_ksp_created": False,
                },
            },
        },
        "source": {
            "facts": {"primal_role": "full_fe", "phase_application": "algebraic_slave_zero_action_internal_finalized_mpc_once"},
            "source_generation": "build_frozen_fullspace_primal_source",
            "role": "full_fe_primal_diagnostic_solution",
            "owned_slave_indices": [1],
                "full_vector": {"array_sha256": worker._array_sha(source_values), "norm": float(np.linalg.norm(source_values))},
                "algebraic_input": {"array_sha256": worker._array_sha(input_values)},
        },
        "rhs": {"facts": {}, "repeat": {}, "generation": "same_exact_p6_matrix_free_action"},
        "npz": {"relative_path": npz_path.name, "bytes": npz_path.stat().st_size, "sha256": _sha(npz_path), "roles": ["source_before", "source_after", "input_before", "input_after", "rhs_before", "rhs_after", "rhs_repeat", "final_solution", "final_action", "final_true_residual"], "solution_only": False},
        "settings": {
            "ksp_type": "gmres", "pc_side": "right", "norm_type": "unpreconditioned", "restart": 20, "cycle_max_it": 20, "max_it": 10000, "residual_replacement": True, "zero_initial_guess": True, "checkpoint_interval": 500, "first_checkpoint_iteration": None, "residual_limit": 1.0e-8,
        },
        "krylov": {
            "settings": {"restart": 20},
            "initial_true_residual": 1.0,
            "cycles": cycles,
            "checkpoint_facts": [{"manifest_path": str(manifest_path), "manifest_sha256": _sha(manifest_path), "iteration": 500}],
            "iterations": 500,
            "reason": 1,
            "final_true_residual": 0.0,
            "matvec_count": 524,
            "pc_apply_count": 525,
            "explicit_action_count": 26,
            "driver_explicit_action_count": 26,
            "rhs_action_count": 2,
            "final_action_recheck_count": 1,
            "extra_action_count": 3,
            "explicit_action_count_total": 29,
            "action_calls_total": 553,
            "ksp_destroy_count": 25,
            "elapsed_seconds": 1.0,
            "pc_apply_facts": pc_rows,
            "final_output": {"owned_slave_max": 0.0},
        },
        "lifecycle": {"marker_relative_dir": "markers", "marker_names": list(worker.MARKERS), "retained_dwell_seconds": 2.0, "release_order": ["source_rhs", "retained_window", "krylov_result", "bundle"], "external_process_tree_authority": True},
        "raw_facts_only": True,
    }
    _write_json(record_path, record)
    marker_times = [
        1_000_000_000 * value for value in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11)
    ]
    for name, stamp in zip(worker.MARKERS, marker_times, strict=True):
        facts = {}
        if name == "record_written":
            facts = {"record_path": str(record_path), "record_sha256": _sha(record_path)}
        _write_json(markers / f"{name}.json", {"schema": worker.MARKER_SCHEMA, "marker": name, "source_sha": SOURCE_SHA, "wall_time_ns": stamp, "facts": facts})
    watchdog_raw = root / "watchdog.raw.jsonl"
    samples = []
    sample_times = (0, 1_500_000_000, 2_500_000_000, 4_500_000_000, 6_500_000_000, 8_500_000_000, 10_500_000_000, 12_000_000_000)
    for stamp in sample_times:
        samples.append({"wall_time_ns": stamp, "authority": {"process_tree": {"rss_bytes": 100_000_000, "swap_bytes": 0, "all_status_readable": True}}})
    watchdog_raw.write_text("".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in samples), encoding="utf-8")
    watchdog_log = root / "worker.log"
    watchdog_log.write_text("", encoding="utf-8")
    watchdog_compact = root / "watchdog.compact.json"
    _write_json(watchdog_compact, {"schema": checker.WATCHDOG_SCHEMA, "source_sha": SOURCE_SHA, "worker_command": command, "worker_raw_dir": str(raw), "worker_record": str(record_path), "watchdog_raw": str(watchdog_raw), "watchdog_log": str(watchdog_log), "returncode": 0, "natural_exit": True, "no_orphan": True, "stop_reason": "natural_exit", "sample_count": len(samples), "all_status_readable": True, "peak_process_tree_rss_bytes": 100_000_000, "max_process_tree_swap_bytes": 0, "watchdog_poll_seconds": 0.25, "watchdog_rss_limit_bytes": 2_000_000_000, "raw_sha256": _sha(watchdog_raw)})
    return record_path, watchdog_compact, record


def test_profile_paths_markers_and_import_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "paths"
    raw = root / "worker_raw"
    jit = root / "jit_cache"
    checkpoints = root / "checkpoints"
    record = root / "worker_record.json"
    root.mkdir()
    (root / "watchdog.raw.jsonl").write_text("", encoding="utf-8")
    (root / "watchdog.compact.json").write_text("", encoding="utf-8")
    (root / "worker.log").write_text("", encoding="utf-8")
    worker._prepare_paths(raw, jit, checkpoints, record)
    assert raw.is_dir() and (raw / "markers").is_dir() and jit.is_dir() and checkpoints.is_dir()
    with pytest.raises(FileExistsError):
        worker._prepare_paths(raw, jit, checkpoints, record)
    assert worker.SOURCES == ("random", "gradient", "curl", "checkerboard")
    executable_target = tmp_path / "resolved-python"
    executable_target.write_bytes(b"python")
    executable_link = tmp_path / "qualified-python-link"
    executable_link.symlink_to(executable_target)
    monkeypatch.setattr(worker.sys, "executable", str(executable_link))
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setattr(
        worker,
        "_git",
        lambda _root, *args: {
            ("rev-parse", "HEAD"): SOURCE_SHA,
            ("branch", "--show-current"): worker.BRANCH,
            ("status", "--porcelain", "--untracked-files=all"): "",
        }[args],
    )
    monkeypatch.setattr(
        worker.importlib,
        "import_module",
        lambda name: SimpleNamespace(__file__=str(tmp_path / f"{name}.so")),
    )
    facts = worker._source_facts(
        tmp_path,
        SOURCE_SHA,
        SimpleNamespace(size=1),
        SimpleNamespace(ScalarType=np.complex128, IntType=np.int32),
    )
    assert facts["python_executable"] == str(executable_target.resolve())
    for path in (Path(worker.__file__), Path(checker.__file__)):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name.startswith(("mpi4py", "petsc4py", "dolfinx", "src.solvers", "src.common")) for name in imported)


def _checker_mutation_case(tmp_path: Path, mutation: str) -> None:
    record_path, watchdog_path, record = _make_fixture(tmp_path)
    if mutation == "final_residual":
        record["krylov"]["final_true_residual"] = 1.0e-5
        _write_json(record_path, record)
    elif mutation == "source":
        record["source_name"] = "not-a-frozen-source"
        _write_json(record_path, record)
    elif mutation == "marker":
        marker = record_path.parent / "worker_raw/markers/source_built.json"
        value = json.loads(marker.read_text(encoding="utf-8"))
        value["source_sha"] = "b" * 40
        _write_json(marker, value)
    elif mutation == "checkpoint_hash":
        manifest = record_path.parent / "checkpoints/checkpoint-500/manifest.json"
        value = json.loads(manifest.read_text(encoding="utf-8"))
        value["ranks"][0]["solution"]["sha256"] = "0" * 64
        _write_json(manifest, value)
    elif mutation == "raw_residual":
        npz_path = record_path.parent / "worker_raw/positive_probe.npz"
        with np.load(npz_path, allow_pickle=False) as data:
            arrays = {name: np.asarray(data[name]) for name in data.files}
        mutated_residual = np.asarray([1.0 + 0.0j, 0.0j, 0.0j])
        arrays["final_true_residual"] = mutated_residual
        arrays["final_action"] = arrays["rhs_before"] - mutated_residual
        np.savez_compressed(npz_path, **arrays)
        record["npz"]["bytes"] = npz_path.stat().st_size
        record["npz"]["sha256"] = _sha(npz_path)
        _write_json(record_path, record)
        record_marker = record_path.parent / "worker_raw/markers/record_written.json"
        marker_value = json.loads(record_marker.read_text(encoding="utf-8"))
        marker_value["facts"]["record_sha256"] = _sha(record_path)
        _write_json(record_marker, marker_value)
    elif mutation == "action_ledger":
        record["krylov"]["action_calls_total"] = 1
        _write_json(record_path, record)
        record_marker = record_path.parent / "worker_raw/markers/record_written.json"
        marker_value = json.loads(record_marker.read_text(encoding="utf-8"))
        marker_value["facts"]["record_sha256"] = _sha(record_path)
        _write_json(record_marker, marker_value)
    else:
        raise AssertionError(mutation)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["passed"] is False
    assert result["classification"] in {"CONTRACT_INVALID", "C1_P6_POSITIVE_GATE_FAIL"}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("mutation", ("final_residual", "raw_residual", "source", "marker", "checkpoint_hash", "action_ledger"))
def test_checker_mutation_cases(tmp_path: Path, mutation: str) -> None:
    _checker_mutation_case(tmp_path, mutation)


def test_checker_valid_fixture(tmp_path: Path) -> None:
    record_path, watchdog_path, _ = _make_fixture(tmp_path)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["passed"] is True
    assert result["classification"] == "C1_P6_POSITIVE_PASS_MPI1"


@pytest.mark.parametrize(("rss", "swap", "warning", "readable"), ((1_900_000_000, 0, True, True), (2_000_000_000, 0, False, True), (100_000_000, 1, False, True), (100_000_000, 0, False, False)))
def test_watchdog_resource_boundaries(tmp_path: Path, rss: int, swap: int, warning: bool, readable: bool) -> None:
    record_path, watchdog_path, _ = _make_fixture(tmp_path)
    compact = json.loads(watchdog_path.read_text(encoding="utf-8"))
    raw_path = Path(compact["watchdog_raw"])
    rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        row["authority"]["process_tree"]["rss_bytes"] = rss
        row["authority"]["process_tree"]["swap_bytes"] = swap
        row["authority"]["process_tree"]["all_status_readable"] = readable
    raw_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
    compact["peak_process_tree_rss_bytes"] = rss
    compact["max_process_tree_swap_bytes"] = swap
    compact["all_status_readable"] = readable
    compact["raw_sha256"] = _sha(raw_path)
    _write_json(watchdog_path, compact)
    result = checker.check_record(record_path, watchdog_path, SOURCE_SHA)
    if not readable:
        assert result["passed"] is False and result["gate_failures"]
    elif warning:
        assert result["passed"] is True and result["warnings"]
        assert not result["gate_failures"]
    else:
        assert result["passed"] is False and result["gate_failures"]
