from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
import src.solvers.hcurl_m6b_w8a_z_bubble_range as w8
from src.solvers.disk_backed_flexible_gmres import RawPositionalColumnStore


def _mesh_and_cfg() -> tuple[SimpleNamespace, SimpleNamespace]:
    planes = np.linspace(-10.0, 130.0, 15, dtype=np.float64)
    points = np.asarray([[0.2, -0.1, z] for z in planes], dtype=np.float64)
    return (
        SimpleNamespace(mesh=SimpleNamespace(geometry=SimpleNamespace(x=points))),
        SimpleNamespace(domain_z_min=-10.0, domain_z_max=130.0, period_x=5.0, kx=0.2, ky=-0.1j),
    )


def test_w8a_fixed_bubbles_are_endpoint_zero_and_full_degree_span():
    planes = np.linspace(-10.0, 130.0, 15, dtype=np.float64)
    assert len(w8.fixed_w8a_column_specs()) == 530
    added = w8.fixed_w8a_column_specs()[390:]
    assert len(added) == 140
    assert [(item.order_m, item.interval, item.bubble_degree, item.component) for item in added[:6]] == [
        (-7, 0, 2, 1), (-7, 0, 3, 1), (-7, 0, 4, 1),
        (-7, 0, 5, 1), (-7, 0, 6, 1), (-7, 1, 2, 1),
    ]
    assert (added[-1].order_m, added[-1].interval, added[-1].bubble_degree) == (-6, 13, 6)
    assert np.array_equal(w8.w8a_bubble_basis(np.asarray([-1.0, 1.0])), np.zeros((5, 2)))
    grid = np.asarray([[-1.0, 0.0, 1.0], [0.25, -1.0, 0.75]])
    grid_basis = w8.w8a_bubble_basis(grid)
    assert grid_basis.shape == (5, 2, 3)
    assert np.array_equal(grid_basis[:, 0, [0, 2]], np.zeros((5, 2)))
    assert np.array_equal(grid_basis[:, 1, 1], np.zeros(5))
    interior = np.linspace(-0.8, 0.8, 5)
    assert np.linalg.matrix_rank(w8.w8a_bubble_basis(interior)) == 5
    assert w8.w8a_bubble_value(planes[0], planes, 0, 2) == 0.0
    assert w8.w8a_bubble_value(planes[1], planes, 0, 2) == 0.0
    assert w8.w8a_bubble_value(planes[0] - 1.0, planes, 0, 2) == 0.0


def _synthetic_diagnostic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rows = 531
    old_hashes = []
    old_store = RawPositionalColumnStore(tmp_path / "old.bin", rows, 390)
    for column in range(390):
        value = np.zeros(rows, dtype=np.complex128)
        value[column] = 1.0 + 0.001j * column
        old_store.write_column(column, value)
        old_hashes.append(w8._array_sha256(value))
    new_columns = tuple(
        w8.W6ASparseColumn(
            np.asarray([390 + column], dtype=np.int32),
            np.asarray([1.0 + 0.002j * column], dtype=np.complex128),
        )
        for column in range(140)
    )
    old_data = np.asarray([1.0 + 0.001j * column for column in range(390)], dtype=np.complex128)
    old_indices = np.arange(390, dtype=np.int32)
    old_indptr = np.arange(391, dtype=np.int32)
    legacy = {
        "z_data": old_data,
        "z_indices": old_indices,
        "z_indptr": old_indptr,
        "gram": np.diag(np.abs(old_data) ** 2).astype(np.complex128),
        "az_store": old_store,
        "column_sha256": tuple(old_hashes),
        "az_column_sha256_aggregate": w8._json_sha256(old_hashes),
        "manifest_file_sha256": "a" * 64,
        "az_scratch": {"path": str(old_store.path), "bytes": old_store.allocated_bytes, "sha256": "old"},
    }
    monkeypatch.setattr(w8, "W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE", w8._json_sha256(old_hashes[:75]))
    action_calls = []

    def action(values):
        action_calls.append(np.array(values, copy=True))
        return np.asarray(values, dtype=np.complex128)

    diagnostic = w8.W8AMultiOrderRangeDiagnostic.from_legacy_and_added(
        legacy,
        new_columns,
        action,
        global_rows=rows,
        ownership_range=(0, rows),
        scratch_dir=tmp_path / "new_az",
        identity={"source_sha": "b" * 40, "operator_identity": "A=I"},
    )
    return diagnostic, old_store, action_calls


def test_w8a_composite_store_uses_only_new_scratch_and_fixed_actions(tmp_path, monkeypatch):
    diagnostic, old_store, action_calls = _synthetic_diagnostic(tmp_path, monkeypatch)
    try:
        assert len(action_calls) == 143
        assert diagnostic.action_counts == {
            "frozen_legacy": 0,
            "new_base": 140,
            "selected_repeat": 3,
            "total": 143,
        }
        assert diagnostic.new_az_store.capacity == 140
        assert diagnostic.new_az_store.write_count == 140
        assert old_store.write_count == 390
        assert diagnostic.audit["old_az_production_retained"] is False
        assert diagnostic.audit["az_production_retained"] is False
        rhs = np.zeros(530, dtype=np.complex128)
        rhs[500] = 2.0 - 0.5j
        rhs = np.pad(rhs, (0, 1))
        rhs[530] = 1.0 + 0.25j
        result = diagnostic.compare_range_orders(rhs)
        expected_rho530 = abs(rhs[530]) / np.linalg.norm(rhs)
        assert result["rho530"] == pytest.approx(expected_rho530, abs=1.0e-12)
        assert result["rho530"] <= result["rho390"] + 1.0e-12
    finally:
        diagnostic.close()


def test_w8a_parser_prediction_and_fixed_numeric_gate(tmp_path):
    args = runner._parser().parse_args(
        [
            "m6b-w8a-builder",
            "--run-dir", str(tmp_path / "run"),
            "--w6a-raw-dir", str(tmp_path / "w6a"),
            "--jit-cache-source", str(tmp_path / "jit"),
            "--expected-source-sha", "a" * 40,
        ]
    )
    assert args.command == "m6b-w8a-builder"
    assert not hasattr(args, "legacy_store_dir")
    assert not hasattr(args, "w5_raw_dir")
    assert runner._m6b_w8a_scope(prediction={"predicted_live_set_bytes": 1})["columns"] == 530
    prediction = runner._m6b_w8a_predicted_live_set(
        old_retained_bytes=100,
        new_retained_bytes=200,
        old_work_bytes=300,
        new_work_bytes=400,
    )
    assert prediction["predicted_live_set_bytes"] == runner.M6B_W7_S1_W5_CALIBRATED_PEAK_BYTES + 200
    assert prediction["base_measured_production_peak_bytes"] == runner.M6B_W7_S1_W5_CALIBRATED_PEAK_BYTES
    assert prediction["base_peak_authority"] == "W7_S1_W5_CALIBRATED_PEAK_BYTES"
    assert prediction["derived_not_measured"] is True
    assert runner._m6b_w8a_numeric_gate(
        {
            "w5_iter200": {"rho390": 0.9, "rho530": 0.8, "normal_closure": 0.0},
            "w7_cumulative400": {"rho390": 0.9, "rho530": 0.6, "normal_closure": 0.0},
        }
    )["pass"] is True
    assert runner._m6b_w8a_numeric_gate(
        {
            "w5_iter200": {"rho390": 0.9, "rho530": 0.9, "normal_closure": 0.0},
            "w7_cumulative400": {"rho390": 0.9, "rho530": 0.71, "normal_closure": 0.0},
        }
    )["pass"] is False
    assert runner._m6b_w8a_numeric_gate(
        {
            "w5_iter200": {"rho390": 0.9, "rho530": 0.8, "normal_closure": 2.0e-11},
            "w7_cumulative400": {"rho390": 0.9, "rho530": 0.6, "normal_closure": 0.0},
        }
    )["pass"] is False


def test_w8_legacy_store_path_is_explicit_and_w6a_bound(tmp_path, monkeypatch):
    raw = tmp_path / "w6a"
    store = raw / "sparse_range_store"
    store.mkdir(parents=True)
    (store / "manifest.json").write_bytes(b"manifest")
    assert runner._m6b_w8b_legacy_store_dir(raw) == store.resolve()
    descriptor = runner._artifact(raw, "sparse_range_store/manifest.json")
    monkeypatch.setattr(
        runner,
        "_m6b_w8a_w6a_authority",
        lambda _path: {"summary": {"store_manifest_artifact": descriptor}},
    )
    assert runner._m6b_w8a_legacy_store_dir(raw) == store.resolve()
    monkeypatch.setattr(
        runner,
        "_m6b_w8a_w6a_authority",
        lambda _path: {"summary": {"store_manifest_artifact": {**descriptor, "sha256": "0" * 64}}},
    )
    with pytest.raises(ValueError):
        runner._m6b_w8a_legacy_store_dir(raw)
    with pytest.raises(FileNotFoundError):
        runner._m6b_w8b_legacy_store_dir(tmp_path / "missing")


def test_w8a_validator_missing_store_fails_closed(tmp_path):
    result = w8.validate_w8a_store(tmp_path / "missing" / "manifest.json", legacy_store_dir=tmp_path / "legacy")
    assert result["pass"] is False


def test_w8a_fe_helper_reuses_one_work_vec_and_mpc_path(monkeypatch):
    mesh_data, cfg = _mesh_and_cfg()

    class FakeVec:
        def __init__(self, owned_size=4, ghost_size=0):
            self.owned_size = owned_size
            self.values = np.zeros(owned_size + ghost_size, dtype=np.complex128)
            self.duplicate_count = 0
            self.destroy_count = 0
            self.duplicate_result = None

        def duplicate(self):
            self.duplicate_count += 1
            self.duplicate_result = FakeVec(self.owned_size)
            return self.duplicate_result

        def getSize(self):
            return self.owned_size

        def getArray(self, readonly=False):
            return self.values if readonly else self.values[: self.owned_size]

        def assemble(self):
            return None

        def destroy(self):
            self.destroy_count += 1

    template = FakeVec()
    field_vec = FakeVec(ghost_size=2)
    counts = {"interpolate": 0, "homogenize": 0, "compress": 0}
    captured = []

    class FakeField:
        def __init__(self, _space):
            self.x = SimpleNamespace(petsc_vec=field_vec)

        def interpolate(self, callback):
            counts["interpolate"] += 1
            values = callback(
                np.asarray(
                    [[0.2, 0.2, 0.2, 0.2], [-0.1, -0.1, -0.1, -0.1], [7.3, 2.0, 0.2, 13.0]],
                    dtype=np.float64,
                )
            )
            field_vec.values[:4] = np.asarray(values).reshape(-1)[:4]
            field_vec.values[4:] = 123456.0 + 0.0j

    import dolfinx
    import src.solvers.physical_slab_two_level as slab

    monkeypatch.setattr(dolfinx.fem, "Function", FakeField)

    def compress(vector):
        counts["compress"] += 1
        captured.append(np.array(vector.getArray(), copy=True))
        return SimpleNamespace(
            indices=np.asarray([0], dtype=np.int32),
            values=np.asarray([1.0 + 0.0j], dtype=np.complex128),
        )

    monkeypatch.setattr(slab, "compress_petsc_vector", compress)
    floquet = SimpleNamespace(
        mpc=SimpleNamespace(homogenize=lambda _field: counts.__setitem__("homogenize", counts["homogenize"] + 1))
    )
    columns, audit = w8.build_w8a_bubble_columns_from_fe(
        object(), mesh_data, floquet, template, cfg, ownership_range=(0, 4)
    )

    assert len(columns) == 140
    assert counts == {"interpolate": 140, "homogenize": 140, "compress": 140}
    assert template.duplicate_count == 1 and template.destroy_count == 0
    assert template.duplicate_result is not template
    assert template.duplicate_result.destroy_count == 1
    assert field_vec.destroy_count == 0
    assert all(values.shape == (4,) and not np.any(values == 123456.0) for values in captured)
    assert [item["column_index"] for item in audit["column_audit"]] == list(range(390, 530))
    assert {item["order_m"] for item in audit["column_audit"]} == {-7, -6}
    assert {item["component"] for item in audit["column_audit"]} == {1}
    assert audit["dense_candidates_retained"] is False
    assert all(np.isfinite(item["norm"]) and item["norm"] == 1.0 for item in audit["column_audit"])


def _w8a_action_audit_fixture() -> dict:
    count = 143
    return {
        "frozen_legacy_action_count": 0,
        "new_base_action_count": 140,
        "selected_repeat_action_count": 3,
        "total_new_action_count": count,
        "outer_forward_apply_count": count,
        "bridge": {
            "fixed_work_vectors": 2,
            "vector_create_count": 2,
            "per_apply_vec_creation": 0,
            "forward_apply_count": count,
        },
        "outer_context": {
            "apply_count": count,
            "matrix_type": "python_action_only",
            "global_matrix": False,
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
        },
        "physical_action": {
            "apply_count": count,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
            "retained_dense_cell_tensor_count": 0,
            "dense_cell_tensor_materialized_per_apply": False,
            "factor_count": 0,
            "ksp_created": False,
            "cell_schur_matrix_nnz": 0,
            "slab_matrix_nnz": 0,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "ordinary_default_changed": False,
        },
        "dtn_action": {
            "apply_count": count,
            "mode_count": 80,
            "fine_space": "uncondensed_fullspace",
            "condensation": False,
            "static_condensed_operator_used": False,
            "trace_slab_pc_used": False,
            "global_matrix_materialized": False,
            "augmented_matrix_materialized": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "fe_sized_allgather": False,
            "modal_allreduce_count_per_apply": 1,
            "modal_allreduce_count_per_hermitian_apply": 1,
        },
    }


def test_w8a_formal_gate_executes_action_and_artifact_checks(monkeypatch, tmp_path):
    import src.solvers.hcurl_m6b_w8a_z_bubble_range as w8_module

    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    old_retained = 391 * 4 + 16
    prediction = runner._m6b_w8a_predicted_live_set(
        old_retained_bytes=old_retained,
        new_retained_bytes=200 + runner.M6B_W6A_MANIFEST_RESERVE_BYTES,
        old_work_bytes=300,
        new_work_bytes=500,
    )
    planes = np.linspace(-10.0, 130.0, 15).tolist()
    summary = {
        "schema": runner.M6B_W8A_SCHEMA,
        "status": "builder_complete",
        "source_at_start": source,
        "source_at_end": source,
        "p6_identity": {
            "global_cells": runner.M6B_GLOBAL_CELLS,
            "local_cells": runner.M6B_GLOBAL_CELLS,
            "local_nloc": runner.M6B_LOCAL_NLOC,
            "global_rows": runner.M6B_GLOBAL_ROWS,
            "constraint_count": runner.M6B_CONSTRAINTS,
        },
        "runtime_identity": {
            "qualified_activation": "1",
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "mpi_size": 1,
            "linux_abi": True,
            "sys_executable": "/tmp/.venv/bin/python",
            "threads": {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
            "package_paths": {
                "petsc4py": "/usr/lib/petsc4py.py",
                "slepc4py": "/usr/lib/slepc4py.py",
                "dolfinx": "/usr/lib/dolfinx.py",
                "mpi4py": "/usr/lib/mpi4py.py",
            },
            "compiler": {"id": "fixture"},
        },
        "scope": runner._m6b_w8a_scope(prediction=prediction),
        "prediction": prediction,
        "architecture": {
            "global_matrix": False,
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "dtn_matrix_free": True,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "az_builder_only": True,
            "az_production_retained": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
        },
        "action_audit": _w8a_action_audit_fixture(),
        "fe_audit": {"z_planes": planes},
    }
    summary = runner._attach_evidence(summary)

    class FakeDiagnostic:
        z_data = np.empty(0, dtype=np.complex128)
        z_indices = np.empty(0, dtype=np.int32)
        z_indptr = np.zeros(391, dtype=np.int32)
        r_factor = np.eye(1, dtype=np.complex128)
        audit = {
            "columns": 530,
            "action_counts": {"frozen_legacy": 0, "new_base": 140, "selected_repeat": 3, "total": 143},
            "retained_z_r_gate": True,
            "retained_z_r_bytes": 200,
            "bounded_work_bytes": 500,
            "repeat_exact": True,
            "factor_audit": {"rank": 530, "normal_closure": 0.0},
        }

        def close(self):
            return None

    monkeypatch.setattr(runner, "_read_json", lambda _path: summary)
    monkeypatch.setattr(runner, "_m6b_w8a_progress_valid", lambda _path: {"pass": True})
    monkeypatch.setattr(runner, "_m6b_w8a_artifact_inventory_valid", lambda *_args: True)
    monkeypatch.setattr(runner, "_m6b_w6a_jit_cache_valid", lambda *_args: True)
    monkeypatch.setattr(runner, "_m6b_w8a_legacy_store_dir", lambda _path: tmp_path / "legacy")
    monkeypatch.setattr(runner, "_m6b_w6a_w5_compact_authority", lambda: {"factor_compiler": {"id": "fixture"}})
    monkeypatch.setattr(
        runner,
        "_m6b_w8a_w6a_authority",
        lambda _path: {"summary": {"carrier_audit": {"bounded_work_bytes": 300}}},
    )
    monkeypatch.setattr(w8_module.W8AMultiOrderRangeDiagnostic, "load", staticmethod(lambda *_args, **_kwargs: FakeDiagnostic()))
    watchdog = {
        "schema": runner.M6B_W8A_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W8A_PHASE,
        "status": "measurement_complete",
        "raw_dir": str(tmp_path.resolve()),
        "watchdog_dir": str((tmp_path / "watchdog").resolve()),
        "command": [
            runner.sys.executable,
            "-m",
            "benchmarks.run_task037_extra_m6b",
            "m6b-w8a-builder",
            "--run-dir",
            str(tmp_path.resolve()),
            "--w6a-raw-dir",
            str((tmp_path / "w6a").resolve()),
            "--jit-cache-source",
            str((tmp_path / "jit").resolve()),
            "--expected-source-sha",
            "a" * 40,
        ],
        "source_at_start": source,
        "source_at_end": source,
        "source_end_clean": True,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W8A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W8A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W8A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "artifact_inventory": {"raw": [], "watchdog": []},
        "timeline": {"pass": True, "peak_rss_bytes": 100, "swap_bytes": 0, "compiler_descendant_pids": []},
        "process": {"return_code": 0, "termination": None, "peak_rss_bytes": 100, "swap_bytes": 0},
        "drain": {"gone": True},
    }
    watchdog = runner._attach_evidence(watchdog)
    monkeypatch.setattr(runner, "_m6b_w8a_timeline_valid", lambda _path: watchdog["timeline"])
    gate = runner._m6b_w8a_formal_gate(
        tmp_path, watchdog, tmp_path / "watchdog", tmp_path / "w6a", tmp_path / "jit", "a" * 40
    )
    assert gate["checks"]["action"] is True
    assert gate["pass"] is True
    tampered = copy.deepcopy(summary["action_audit"])
    tampered["new_base_action_count"] = 139
    monkeypatch.setattr(runner, "_read_json", lambda _path: {**summary, "action_audit": tampered})
    failed = runner._m6b_w8a_formal_gate(
        tmp_path, watchdog, tmp_path / "watchdog", tmp_path / "w6a", tmp_path / "jit", "a" * 40
    )
    assert failed["checks"]["action"] is False


def test_w8a_artifact_inventory_recomputes_disk_descriptors(tmp_path):
    raw = tmp_path / "raw"
    watchdog = tmp_path / "watchdog"
    raw_names = (
        "w8a_summary.json", "w8a_progress.jsonl", "sparse_range_store/manifest.json",
        "sparse_range_store/z_data.npy", "sparse_range_store/z_indices.npy",
        "sparse_range_store/z_indptr.npy", "sparse_range_store/gram.npy", "sparse_range_store/r_factor.npy",
    )
    watchdog_names = (
        f"{runner.M6B_W8A_PHASE}_timeline.jsonl",
        f"{runner.M6B_W8A_PHASE}_stdout.txt",
        f"{runner.M6B_W8A_PHASE}_root_pid.json",
    )
    for root, names in ((raw, raw_names), (watchdog, watchdog_names)):
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"w8a")
    inventory = {
        "raw": [runner._artifact(raw, name) for name in raw_names],
        "watchdog": [runner._artifact(watchdog, name) for name in watchdog_names],
    }
    assert runner._m6b_w8a_artifact_inventory_valid(inventory, raw, watchdog)
    tampered = copy.deepcopy(inventory)
    tampered["raw"][0]["sha256"] = "0" * 64
    assert not runner._m6b_w8a_artifact_inventory_valid(tampered, raw, watchdog)


def test_w8a_companion_fe_and_action_contracts_are_distinct():
    planes = np.linspace(-10.0, 130.0, 15, dtype=np.float64)
    records = []
    for spec in w8.fixed_w8a_column_specs()[390:]:
        records.append(
            {
                "column_index": spec.column_index,
                "order_m": spec.order_m,
                "interval": spec.interval,
                "bubble_degree": spec.bubble_degree,
                "component": spec.component,
                "nnz": 1,
                "norm": 1.0,
                "indices_array_sha256": "a" * 64,
                "values_array_sha256": "b" * 64,
            }
        )
    fe_audit = {
        "z_planes": planes.tolist(),
        "domain_z_min": -10.0,
        "domain_z_max": 130.0,
        "z_planes_array_sha256": w8._array_sha256(planes),
        "column_audit": records,
        "column_count": 140,
        "fixed_order": True,
        "dense_candidates_retained": False,
        "component": 1,
        "diffraction_orders": [-7, -6],
        "bubble_degrees": [2, 3, 4, 5, 6],
    }
    assert runner._m6b_w8a_fe_audit_valid(fe_audit)
    fe_audit["column_audit"][0]["column_index"] = 75
    assert not runner._m6b_w8a_fe_audit_valid(fe_audit)

    companion_action = _w8a_action_audit_fixture()
    companion_action["new_base_action_count"] = 0
    companion_action["total_new_action_count"] = 3
    companion_action["outer_forward_apply_count"] = 3
    for key in ("bridge", "outer_context", "physical_action", "dtn_action"):
        if key == "bridge":
            companion_action[key]["forward_apply_count"] = 3
        else:
            companion_action[key]["apply_count"] = 3
    assert runner._m6b_w8a_action_audit_valid(
        companion_action, expected_new_base=0, expected_repeat=3, expected_total=3
    )
    companion_action["bridge"]["forward_apply_count"] = 2
    assert not runner._m6b_w8a_action_audit_valid(
        companion_action, expected_new_base=0, expected_repeat=3, expected_total=3
    )


def _qualified_w8a_recovery_fixture(tmp_path: Path) -> dict:
    source_record = {
        "source_commit_full_sha": "c" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    checks = {
        name: True
        for name in (
            "producer_sha", "paths", "artifact_hashes", "source", "old_watchdog",
            "resource", "progress", "failure_boundary", "w6a_authority", "jit",
            "fixed_identity", "store", "retained_payload", "prediction", "companion",
            "source_delta", "recovery_checker_source",
        )
    }
    companion_checks = {name: True for name in (
        "summary", "source", "runtime", "p6", "fe", "architecture", "action",
        "sentinel", "progress", "frozen_w8a", "prediction", "jit", "watchdog",
        "resource", "artifacts",
    )}
    sentinel_actions = [
        {
            "column_index": column,
            "finite": True,
            "relative_error": 0.0,
            "old_az_array_sha256": "d" * 64,
        }
        for column in runner.M6B_W8A_COMPANION_SENTINEL_COLUMNS
    ]
    recovery = {
        "schema": runner.M6B_W8A_RECOVERY_SCHEMA,
        "status": "recovery_complete",
        "classification": "RECOVERED_QUALIFIED_FOR_W8B",
        "recovered_numeric_gate_pass": True,
        "companion_gate_pass": True,
        "qualified_for_w8b": True,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "original_builder_execution_pass": False,
        "old_watchdog_status": "gate_failed",
        "producer_source_sha": runner.M6B_W8A_RECOVERY_PRODUCER_SHA,
        "companion_source_sha": "c" * 40,
        "raw_dir": str((tmp_path / "w8a").resolve()),
        "checks": checks,
        "problems": [],
        "source_delta": {
            "pass": True,
            "ancestor": True,
            "paths_unchanged": True,
            "producer_source_sha": runner.M6B_W8A_RECOVERY_PRODUCER_SHA,
            "current_source_sha": "c" * 40,
            "allowlist": sorted(runner.M6B_W8A_RECOVERY_ALLOWED_CHANGED_PATHS),
        },
        "companion_verification": {
            "pass": True,
            "checks": companion_checks,
            "summary": {"sentinel_actions": sentinel_actions},
        },
        "producer_measurement": {
            "source_sha": runner.M6B_W8A_RECOVERY_PRODUCER_SHA,
            "watchdog_status": "gate_failed",
            "artifact_hashes": True,
            "old_watchdog": True,
            "resource": True,
            "failure_boundary": True,
            "progress": {"pass": True, "last_event": "gram_ready"},
            "store_validation": {"pass": True},
        },
        "recovery_checker_source": source_record,
    }
    return runner._attach_evidence(recovery)


def test_w8a_companion_parser_jsonable_recovery_and_w8b_authority(tmp_path):
    import inspect
    from types import MappingProxyType
    from benchmarks.run_task037_extra_h2 import _jsonable

    source = inspect.getsource(runner._run_m6b_w8a_builder)
    assert "from benchmarks.run_task037_extra_h2 import _jsonable" in source
    summary = runner._attach_evidence(
        {"audit": _jsonable({"nested": MappingProxyType({"value": 1})})}
    )
    assert runner._evidence_valid(summary)

    companion_args = runner._parser().parse_args(
        [
            "m6b-w8a-companion",
            "--run-dir", str(tmp_path / "companion"),
            "--w8a-raw-dir", str(tmp_path / "w8a"),
            "--w6a-raw-dir", str(tmp_path / "w6a"),
            "--jit-cache-source", str(tmp_path / "jit"),
            "--expected-source-sha", "c" * 40,
        ]
    )
    assert companion_args.command == "m6b-w8a-companion"
    recovery = _qualified_w8a_recovery_fixture(tmp_path)
    assert runner._m6b_w8a_w8b_authority_valid(
        recovery, w8a_raw_dir=tmp_path / "w8a", expected_source_sha="c" * 40
    )
    recovery["companion_gate_pass"] = False
    recovery = runner._attach_evidence(recovery)
    assert not runner._m6b_w8a_w8b_authority_valid(
        recovery, w8a_raw_dir=tmp_path / "w8a", expected_source_sha="c" * 40
    )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda value: value["checks"].update(resource=False),
        lambda value: value["checks"].update(artifact_hashes=False),
        lambda value: value["producer_measurement"].update(resource=False),
        lambda value: value["producer_measurement"]["progress"].update({"pass": False}),
        lambda value: value["producer_measurement"].update(failure_boundary=False),
        lambda value: value["source_delta"].update({"pass": False}),
        lambda value: value["companion_verification"]["checks"].update(sentinel=False),
        lambda value: value["companion_verification"]["summary"]["sentinel_actions"][0].update(
            relative_error=2.0e-11
        ),
        lambda value: value["recovery_checker_source"].update(source_commit_full_sha="d" * 40),
    ],
)
def test_w8a_recovery_authority_rejects_nested_tamper(tmp_path, tamper):
    value = _qualified_w8a_recovery_fixture(tmp_path)
    tamper(value)
    value = runner._attach_evidence(value)
    assert not runner._m6b_w8a_w8b_authority_valid(
        value, w8a_raw_dir=tmp_path / "w8a", expected_source_sha="c" * 40
    )
