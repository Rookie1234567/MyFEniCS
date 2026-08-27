"""Pure contracts for the p6 setup-only worker and its independent checker."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_setup import (
    CASE,
    MARKER_SCHEMA,
    MODULE,
    RECORD_SCHEMA,
    STAGE,
    _emit_marker,
    _prepare_isolated_jit_cache,
    validate_record_staging,
    validate_setup_profile,
)
from benchmarks.task038_full3d_same_mesh_hcurl_pmg_setup_checker import (
    CHECKER_SCHEMA,
    check_record,
)


SOURCE_SHA = "a" * 40


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_case(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    case_root = tmp_path / "case"
    case_root.mkdir(parents=True)
    raw_dir = tmp_path / "artifact" / "worker_raw"
    marker_dir = raw_dir / "markers"
    jit_cache_dir = raw_dir.parent / "jit_cache"
    record_path = tmp_path / "tracked" / "worker_record.json"
    watchdog_raw = case_root / "watchdog.raw.jsonl"
    watchdog_compact = case_root / "watchdog.compact.json"
    input_path = case_root / "full3d_iterative_example.dat"
    marker_dir.mkdir(parents=True)
    jit_cache_dir.mkdir()
    record_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"frozen input\n")

    command = [
        "/opt/qualified/bin/python",
        "-m",
        MODULE,
        "--stage",
        STAGE,
        "--case",
        CASE,
        "--raw-dir",
        str(raw_dir.resolve()),
        "--jit-cache-dir",
        str(jit_cache_dir.resolve()),
        "--record",
        str(record_path.resolve()),
        "--expected-source-sha",
        SOURCE_SHA,
        "--expected-mpi-size",
        "1",
        "--input",
        str(input_path.resolve()),
    ]
    provenance = {
        "source_sha": SOURCE_SHA,
        "branch": "codex/20260820-task38-extra-full3d-iterative-0p7nm",
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": command[0],
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        },
        "abi_modules": {
            "mpi4py": "/opt/qualified/lib/mpi4py/__init__.py",
            "petsc4py": "/opt/qualified/lib/petsc4py/__init__.py",
            "dolfinx": "/opt/qualified/lib/dolfinx/__init__.py",
            "basix": "/opt/qualified/lib/basix/__init__.py",
        },
        "input_path": str(input_path.resolve()),
        "input_sha256": _sha256(input_path),
        "jit_cache_dir": str(jit_cache_dir.resolve()),
        "isolated_jit_cache": True,
        "command": command,
    }
    architecture = {
        "p6_matrix_free": True,
        "p6_global_aij": False,
        "p3_sparse_allowed": True,
        "p1_sparse_allowed": True,
        "global_dense_transfer": False,
        "global_transfer_matrix": False,
        "numeric_allgather": False,
        "p6_factor": False,
        "outer_ksp_created": False,
        "restart_reserve": False,
        "physical_solve": False,
        "dtn": False,
        "recovery": False,
        "high_order_global_aij": False,
    }

    components = {
        "p6_action_retained_local_bytes": 64,
        "p6_exact_diagonal_local_numeric_bytes": 96,
    }
    audit = {
        "schema": "task038.same_mesh_hcurl_pmg.setup.v1",
        "profile": {
            "wavelength_nm": 13.5,
            "mesh_target_size_nm": 10.0,
            "levels": [6, 3, 1],
            "pairs": [[6, 3], [3, 1]],
            "same_physical_mesh": True,
            "finalized_double_floquet_mpc_count": 3,
        },
        "layouts": {"6": {"local_owned_rows": 6}},
        "p1_factor": {
            "factor_matrix_rows": 6,
            "factor_matrix_nnz": 6,
            "setup_count": 1,
            "solve_count": 10,
        },
        "retained_ledger": {
            "components_local_bytes": components,
            "global_facts": {"p6_exact_diagonal_global_numeric_bytes": 96},
            "known_component_local_bytes": sum(
                value for value in components.values() if value is not None
            ),
            "not_included": ["restart20_reserve", "outer_ksp", "source"],
        },
        "architecture": architecture,
        "ownership": {"destroy_order": ["upper_cycle", "p3_p1_matrices", "python_fe_objects"]},
    }

    x = np.asarray([1 + 1j, 2 - 1j, 0.5 + 0.25j, -1 + 0.5j], dtype=np.complex128)
    y = np.asarray([0.5 - 2j, -1 + 3j, 2 + 0.5j, 0.25 - 1j], dtype=np.complex128)
    combo = (0.37 - 0.19j) * x + (-0.23 + 0.41j) * y
    alpha_x = (0.37 - 0.19j) * x
    beta_y = (-0.23 + 0.41j) * y
    before = np.vstack((x, y, combo, alpha_x, beta_y))
    before[:, 1] = 0.0
    outputs = before[[0, 1, 0, 2, 3, 4, 0, 1, 2, 1]].copy()
    np.savez_compressed(
        raw_dir / "setup_probes.npz",
        input_before=before,
        input_after=before.copy(),
        outputs=outputs,
    )
    npz_facts = {
        "relative_path": "setup_probes.npz",
        "bytes": int((raw_dir / "setup_probes.npz").stat().st_size),
        "sha256": _sha256(raw_dir / "setup_probes.npz"),
        "roles": ["input_before", "input_after", "outputs"],
    }
    rows = [
        {
            "label": label,
            "input_label": ["x", "y", "combo", "alpha_x", "beta_y"][index],
            "p6_smoother_apply_count": 2,
            "p63_adjoint_count": 1,
            "p63_primal_count": 1,
            "lower_cycle_count": 1,
            "p1_solve_count": 1,
            "p1_relative_residual": 1e-15,
        }
        for label, index in zip(
            [
                "x",
                "y",
                "x_repeat",
                "combo",
                "alpha_x",
                "beta_y",
                "x_repeat_2",
                "y_repeat",
                "combo_repeat",
                "y_repeat_2",
            ],
            [0, 1, 0, 2, 3, 4, 0, 1, 2, 1],
        )
    ]
    probe = {
        "apply_count": 10,
        "apply_labels": [
            "x",
            "y",
            "x_repeat",
            "combo",
            "alpha_x",
            "beta_y",
            "x_repeat_2",
            "y_repeat",
            "combo_repeat",
            "y_repeat_2",
        ],
        "apply_input_indices": [0, 1, 0, 2, 3, 4, 0, 1, 2, 1],
        "input_labels": ["x", "y", "combo", "alpha_x", "beta_y"],
        "alpha": {"real": 0.37, "imag": -0.19},
        "beta": {"real": -0.23, "imag": 0.41},
        "probe_kind": "canonical_diagnostic_dual",
        "no_pde_rhs": True,
        "no_physical_solve": True,
        "no_outer_ksp": True,
        "source_facts": [
            {
                "schema": "task038.v13.c0.physical-canonical-source.v1",
                "source_generation": "physical_canonical_key_sha256_v1",
                "role": "full_fe_dual",
                "fixed_seed": seed,
                "source_finite": True,
                "source_nonzero": True,
                "dependent_value_authority": "slave_zero_dual_storage",
                "phase_application": "dual_source_slave_zero_no_phase_reapplication",
            }
            for seed in (
                "task038.v13.c1.p6-setup-probe-x-v1",
                "task038.v13.c1.p6-setup-probe-y-v1",
            )
        ],
        "rows": rows,
        "owned_slave_indices": [1],
        "ownership": {"rank": 0, "local_size": 6, "global_size": 6, "ownership_range": [0, 6]},
        "npz": npz_facts,
    }
    record = {
        "schema": RECORD_SCHEMA,
        "stage": STAGE,
        "case": CASE,
        "raw_dir": str(raw_dir.resolve()),
        "record_path": str(record_path.resolve()),
        "jit_cache_dir": str(jit_cache_dir.resolve()),
        "isolated_jit_cache": True,
        "command": command,
        "provenance": provenance,
        "setup_audit": audit,
        "reserve": {
            "basis_count": 21,
            "auxiliary_vector_count": 4,
            "vector_count": 25,
            "touched": True,
            "local_entries_per_vector": 6,
            "local_numeric_bytes": 2400,
        },
        "probes": probe,
        "lifecycle": {
            "marker_relative_dir": "markers",
            "marker_names": [
                "paths_ready",
                "bundle_built",
                "audit_ready",
                "reserve_built",
                "pc_applies_complete",
                "retained_ready",
                "reserve_destroyed",
                "bundle_destroyed",
                "record_written",
            ],
            "destroy_order": ["reserve", "bundle"],
            "record_written_after_destroy": True,
        },
    }
    _write_json(record_path, record)
    marker_times = {
        name: 1_000_000_000 * (index + 1)
        for index, name in enumerate(
            [
                "paths_ready",
                "bundle_built",
                "audit_ready",
                "reserve_built",
                "pc_applies_complete",
                "retained_ready",
                "reserve_destroyed",
                "bundle_destroyed",
                "record_written",
            ]
        )
    }
    for name, wall_time_ns in marker_times.items():
        _write_json(
            marker_dir / f"{name}.json",
            {
                "schema": MARKER_SCHEMA,
                "marker": name,
                "source_sha": SOURCE_SHA,
                "wall_time_ns": wall_time_ns,
                "facts": {},
            },
        )
    samples = [
        (1_000_000_000, 120_000_000),
        (6_500_000_000, 130_000_000),
        (8_500_000_000, 125_000_000),
    ]
    watchdog_raw.write_text(
        "".join(
            json.dumps(
                {
                    "wall_time_ns": wall,
                    "authority": {
                        "process_tree": {
                            "rss_bytes": rss,
                            "swap_bytes": 0,
                            "all_status_readable": True,
                        }
                    },
                },
                sort_keys=True,
            )
            + "\n"
            for wall, rss in samples
        ),
        encoding="utf-8",
    )
    _write_json(
        watchdog_compact,
        {
            "schema": "task038.lor-native-complex-hx.foundation-e-watchdog.v1",
            "source_sha": SOURCE_SHA,
            "worker_command": command,
            "worker_raw_dir": str(raw_dir.resolve()),
            "worker_record": str(record_path.resolve()),
            "watchdog_raw": str(watchdog_raw.resolve()),
            "raw_sha256": _sha256(watchdog_raw),
            "returncode": 0,
            "natural_exit": True,
            "no_orphan": True,
            "all_status_readable": True,
            "sample_count": 3,
            "peak_process_tree_rss_bytes": 130_000_000,
            "max_process_tree_swap_bytes": 0,
            "watchdog_poll_seconds": 0.25,
            "watchdog_rss_limit_bytes": 2_000_000_000,
        },
    )
    return record_path, watchdog_compact, record


def test_setup_profile_and_staging_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validate_setup_profile(STAGE, CASE, 1)
    with pytest.raises(ValueError):
        validate_setup_profile(STAGE, CASE, 2)
    raw_dir = tmp_path / "artifact" / "worker_raw"
    record_path = tmp_path / "tracked" / "worker_record.json"
    record_path.parent.mkdir(parents=True)
    validate_record_staging(raw_dir, record_path)
    assert raw_dir.is_dir() and (raw_dir / "markers").is_dir()
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    jit_cache_dir = _prepare_isolated_jit_cache(raw_dir, raw_dir.parent / "jit_cache")
    assert jit_cache_dir == raw_dir.parent / "jit_cache"
    assert os.environ["XDG_CACHE_HOME"] == str(jit_cache_dir)
    with pytest.raises(FileExistsError):
        _prepare_isolated_jit_cache(raw_dir, jit_cache_dir)
    with pytest.raises(ValueError):
        _prepare_isolated_jit_cache(raw_dir, raw_dir.parent / "other_jit_cache")
    worker_source = (
        Path(__file__).parents[2] / "benchmarks" / "run_task038_full3d_same_mesh_hcurl_pmg_setup.py"
    ).read_text(encoding="utf-8")
    assert worker_source.index("    _prepare_isolated_jit_cache(raw_dir, jit_cache_dir)") < worker_source.index(
        "    from src.common.config_3d"
    )
    _emit_marker(raw_dir, "paths_ready", SOURCE_SHA, worker_raw_dir=str(raw_dir))
    marker = json.loads(
        (raw_dir / "markers" / "paths_ready.json").read_text(encoding="utf-8")
    )
    assert marker["facts"]["worker_raw_dir"] == str(raw_dir)
    with pytest.raises(ValueError):
        invalid = tmp_path / "invalid" / "worker_raw"
        validate_record_staging(invalid, invalid)


def test_checker_accepts_valid_setup_record(tmp_path: Path) -> None:
    record_path, watchdog_path, _ = _valid_case(tmp_path)
    result = check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["schema"] == CHECKER_SCHEMA
    assert result["passed"] is True
    assert result["classification"] == "C1_P6_SETUP_PASS"
    assert result["metrics"]["probe"]["local_entries"] == 4
    assert result["resource"]["retained_sample_count"] == 1


def test_checker_fails_closed_for_reserve_and_resource_mutations(tmp_path: Path) -> None:
    record_path, watchdog_path, record = _valid_case(tmp_path)
    record["reserve"]["vector_count"] = 24
    _write_json(record_path, record)
    result = check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["passed"] is False
    assert result["classification"] == "CONTRACT_INVALID"

    record_path, watchdog_path, record = _valid_case(tmp_path / "jit-path")
    record["jit_cache_dir"] = str(Path(record["raw_dir"]).parent / "not-jit-cache")
    _write_json(record_path, record)
    result = check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["passed"] is False
    assert result["classification"] == "CONTRACT_INVALID"
    assert any("jit_cache_dir" in item for item in result["contract_errors"])

    record_path, watchdog_path, _ = _valid_case(tmp_path / "resource")
    compact = json.loads(watchdog_path.read_text(encoding="utf-8"))
    compact["watchdog_rss_limit_bytes"] = 1
    _write_json(watchdog_path, compact)
    result = check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["passed"] is False
    assert any("watchdog_rss_limit_bytes" in item for item in result["contract_errors"])

    record_path, watchdog_path, record = _valid_case(tmp_path / "slave")
    npz_path = Path(record["raw_dir"]) / "setup_probes.npz"
    with np.load(npz_path, allow_pickle=False) as data:
        before = np.asarray(data["input_before"])
        after = np.asarray(data["input_after"])
        outputs = np.asarray(data["outputs"])
    outputs[0, 1] = 1.0 + 0.0j
    np.savez_compressed(npz_path, input_before=before, input_after=after, outputs=outputs)
    record["probes"]["npz"]["bytes"] = int(npz_path.stat().st_size)
    record["probes"]["npz"]["sha256"] = _sha256(npz_path)
    _write_json(record_path, record)
    result = check_record(record_path, watchdog_path, SOURCE_SHA)
    assert result["passed"] is False
    assert result["classification"] == "C1_P6_SETUP_GATE_FAIL"
    assert result["contract_errors"] == []


def test_checker_is_independent_and_static_import_boundary() -> None:
    checker_path = Path(__file__).parents[1].parent / "benchmarks" / "task038_full3d_same_mesh_hcurl_pmg_setup_checker.py"
    tree = ast.parse(checker_path.read_text(encoding="utf-8"))
    roots = {
        node.names[0].name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
    }
    roots.update(
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert roots <= {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "pathlib",
        "typing",
        "numpy",
    }
