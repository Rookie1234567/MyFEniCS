from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest
import benchmarks.run_task037_extra_m6b as runner
import src.solvers.hcurl_m6b_w6a_multi_order_range as w6a


def _mesh_and_cfg() -> tuple[SimpleNamespace, SimpleNamespace]:
    planes = np.asarray(
        np.linspace(-10.0, 130.0, 15),
        dtype=np.float64,
    )
    points = np.asarray([[0.2, -0.1, z] for z in planes], dtype=np.float64)
    return (
        SimpleNamespace(mesh=SimpleNamespace(geometry=SimpleNamespace(x=points))),
        SimpleNamespace(domain_z_min=-10.0, domain_z_max=130.0, period_x=5.0, kx=0.2, ky=-0.1j),
    )


def test_w6a_actual_planes_hat_and_fixed_added_order():
    mesh_data, cfg = _mesh_and_cfg()
    planes = w6a.w6a_actual_z_planes(mesh_data, cfg)
    assert planes.size == 15
    assert np.all(np.diff(planes) > 0.0)
    assert planes[0] == cfg.domain_z_min and planes[-1] == cfg.domain_z_max
    assert w6a.w6a_piecewise_hat(planes[0] - 1.0, planes, 0) == 0.0
    assert w6a.w6a_piecewise_hat(planes[0], planes, 0) == 1.0
    assert w6a.w6a_piecewise_hat(planes[1], planes, 0) == 0.0
    assert w6a.w6a_piecewise_hat(planes[7], planes, 7) == 1.0
    assert w6a.w6a_piecewise_hat(planes[-1] + 1.0, planes, 14) == 0.0
    nonuniform = np.asarray(
        [-10.0, -9.0, -7.0, -4.0, 0.0, 3.0, 8.0, 15.0, 25.0, 40.0, 58.0, 77.0, 95.0, 114.0, 130.0],
        dtype=np.float64,
    )
    assert w6a.w6a_piecewise_hat(nonuniform[0] - 1.0, nonuniform, 0) == 0.0
    assert w6a.w6a_piecewise_hat(nonuniform[1], nonuniform, 0) == 0.0
    assert w6a.w6a_piecewise_hat(nonuniform[-1] + 1.0, nonuniform, 14) == 0.0
    assert w6a.w6a_piecewise_hat(nonuniform[-1], nonuniform, 14) == 1.0
    added = w6a.fixed_w6a_column_specs()[75:]
    assert len(added) == 315
    assert [(item.order_m, item.z_plane, item.component) for item in added[:4]] == [
        (-7, 0, 0), (-7, 0, 1), (-7, 0, 2), (-7, 1, 0)
    ]
    assert (added[-1].order_m, added[-1].z_plane, added[-1].component) == (-1, 14, 2)
    phase = w6a.w6a_phase(0.25, -0.5, kx=0.2, ky=-0.1j, period_x=5.0, order_m=-7)
    expected = np.exp(1j * ((0.2 - 14.0 * np.pi / 5.0) * 0.25 + (-0.1j) * -0.5))
    assert abs(phase - expected) <= 1.0e-15


def test_w6a_fe_helper_reuses_one_work_vec_and_ignores_ghost_tail(monkeypatch):
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
    captured_owner_values = []

    class FakeField:
        def __init__(self, _space):
            self.x = SimpleNamespace(petsc_vec=field_vec)
            self.calls = 0

        def interpolate(self, callback):
            self.calls += 1
            values = callback(
                np.asarray(
                    [[0.2, 0.2, 0.2, 0.2], [-0.1, -0.1, -0.1, -0.1], [7.3, 2.0, 0.2, 13.0]],
                    dtype=np.float64,
                )
            )
            field_vec.values[:4] = np.asarray(values, dtype=np.complex128).reshape(-1)[:4]
            field_vec.values[4:] = 123456.0 + 0.0j

    import dolfinx
    import src.solvers.physical_slab_two_level as slab

    monkeypatch.setattr(dolfinx.fem, "Function", FakeField)
    monkeypatch.setattr(
        slab,
        "compress_petsc_vector",
        lambda vector: (
            captured_owner_values.append(np.array(vector.getArray(), copy=True))
            or SimpleNamespace(
                indices=np.asarray([0], dtype=np.int32),
                values=np.asarray([1.0 + 0.0j], dtype=np.complex128),
            )
        ),
    )
    floquet = SimpleNamespace(mpc=SimpleNamespace(homogenize=lambda _field: None))
    columns, audit = w6a.build_w6a_added_columns_from_fe(
        object(), mesh_data, floquet, template, cfg, ownership_range=(0, 4)
    )
    assert len(columns) == 315
    assert audit["column_count"] == 315
    assert audit["dense_candidates_retained"] is False
    work = template.duplicate_result
    assert template.duplicate_count == 1
    assert template.destroy_count == 0
    assert work is not template
    assert work.destroy_count == 1
    assert field_vec.destroy_count == 0
    assert len(captured_owner_values) == 315
    assert all(values.shape == (4,) for values in captured_owner_values)
    assert all(not np.any(values == 123456.0 + 0.0j) for values in captured_owner_values)
    assert all(np.isclose(np.linalg.norm(column.values), 1.0) for column in columns)


def _formal_gate_fixture() -> tuple[dict, dict, dict, dict, dict]:
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }
    prediction = runner._m6b_w6a_predicted_live_set(
        old_retained_bytes=100,
        new_retained_bytes=200,
        old_work_bytes=300,
        new_work_bytes=500,
    )
    planes = np.asarray(np.linspace(-10.0, 130.0, 15), dtype=np.float64)
    summary = {
        "schema": runner.M6B_W6A_SCHEMA,
        "status": "builder_complete",
        "formal_pass": False,
        "pde_pass": False,
        "p6_identity": {
            "global_cells": runner.M6B_GLOBAL_CELLS,
            "local_cells": runner.M6B_GLOBAL_CELLS,
            "local_nloc": runner.M6B_LOCAL_NLOC,
            "global_rows": runner.M6B_GLOBAL_ROWS,
            "constraint_count": runner.M6B_CONSTRAINTS,
        },
        "source_at_start": source,
        "source_at_end": source,
        "prediction": prediction,
        "scope": runner._m6b_w6a_scope(prediction=prediction),
        "z_planes": {
            "z_planes": planes.tolist(),
            "domain_z_min": -10.0,
            "domain_z_max": 130.0,
            "z_planes_array_sha256": w6a._array_sha256(planes),
            "column_count": runner.M6B_W6A_ADDED_COLUMNS,
            "column_audit": [
                {
                    "column_index": 75 + index,
                    "nnz": 1,
                    "norm": 1.0,
                    "indices_array_sha256": "b" * 64,
                    "values_array_sha256": "c" * 64,
                }
                for index in range(runner.M6B_W6A_ADDED_COLUMNS)
            ],
            "fixed_order": True,
            "dense_candidates_retained": False,
        },
        "action_audit": {
            "base": runner.M6B_W6A_COLUMNS,
            "selected_repeat": len(runner.M6B_W6A_REPEAT_COLUMNS),
            "total": runner.M6B_W6A_COLUMNS + len(runner.M6B_W6A_REPEAT_COLUMNS),
            "outer_forward_apply_count": 394,
            "bridge": {
                "vector_create_count": 2,
                "fixed_work_vectors": 2,
                "per_apply_vec_creation": 0,
                "forward_apply_count": 394,
            },
            "outer_context": {
                "apply_count": 394,
                "matrix_type": "python_action_only",
                "global_matrix": False,
                "augmented_matrix": False,
                "static_condensation": False,
                "trace_slab": False,
                "explicit_C_materialized_count": 0,
                "explicit_D_materialized_count": 0,
            },
            "physical_action": {
                "apply_count": 394,
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
                "apply_count": 394,
                "matrix_type": "python_action_only",
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
        },
        "carrier_audit": {
            "columns": 390,
            "action_counts": {"base": 390, "selected_repeat": 4, "total": 394},
            "repeat_exact": True,
            "az_production_retained": False,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "retained_z_r_gate": True,
            "z_retained_bytes": 120,
            "r_retained_bytes": 80,
            "retained_z_r_bytes": 200,
            "bounded_work_bytes": 500,
            "factor_audit": {"rank": runner.M6B_W6A_COLUMNS, "normal_closure": 0.0},
        },
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "global_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "dtn_matrix_free": True,
            "dense_z_retained": False,
            "dense_az_retained": False,
            "az_production_retained": False,
        },
    }
    summary = runner._attach_evidence(summary)
    watchdog = {
        "process": {"return_code": 0, "termination": None, "peak_rss_bytes": 100, "swap_bytes": 0},
        "drain": {"gone": True},
        "resource_limits": {
            "timeout_seconds": runner.M6B_W6A_BUILDER_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W6A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W6A_BUILDER_RSS_LIMIT_BYTES,
            "swap_bytes": 0,
        },
    }
    progress = {"pass": True, "records": 1}
    timeline = {"pass": True, "records": 1, "peak_rss_bytes": 100, "swap_bytes": 0, "compiler_descendant_pids": []}
    store = {"pass": True}
    numeric = {"pass": True, "problems": []}
    return summary, watchdog, progress, timeline, store, numeric


def test_w6a_formal_gate_fail_closed_on_resource_and_prediction():
    summary, watchdog, progress, timeline, store, numeric = _formal_gate_fixture()
    gate = runner._m6b_w6a_formal_gate(
        summary=summary,
        watchdog=watchdog,
        progress=progress,
        timeline=timeline,
        store_validation=store,
        numeric=numeric,
        artifact_inventory_ok=True,
        residual_files_ok=True,
        watchdog_contract_ok=True,
        expected_source_sha="a" * 40,
        runtime_identity_ok=True,
    )
    assert gate["pass"] is True
    for mutation in (
        lambda s, w, p: w["process"].update(peak_rss_bytes=runner.M6B_W6A_BUILDER_RSS_LIMIT_BYTES),
        lambda s, w, p: w["process"].update(peak_rss_bytes=100, swap_bytes=1),
        lambda s, w, p: s["prediction"].update(predicted_live_set_bytes=0),
        lambda s, w, p: p.__setitem__("pass", False),
    ):
        mutated_summary = copy.deepcopy(summary)
        mutated_watchdog = copy.deepcopy(watchdog)
        mutated_progress = copy.deepcopy(progress)
        mutation(mutated_summary, mutated_watchdog, mutated_progress)
        failed = runner._m6b_w6a_formal_gate(
            summary=mutated_summary,
            watchdog=mutated_watchdog,
            progress=mutated_progress,
            timeline=timeline,
            store_validation=store,
            numeric=numeric,
            artifact_inventory_ok=True,
            residual_files_ok=True,
            watchdog_contract_ok=True,
            expected_source_sha="a" * 40,
            runtime_identity_ok=True,
        )
        assert failed["pass"] is False


def test_w6a_formal_gate_rejects_status_resource_and_fe_tamper():
    summary, watchdog, progress, timeline, store, numeric = _formal_gate_fixture()

    for mutation in (
        lambda s, w, t: s.update(status="gate_failed"),
        lambda s, w, t: t.update(peak_rss_bytes=101),
        lambda s, w, t: s["z_planes"]["column_audit"][0].update(norm=0.5),
    ):
        mutated_summary = copy.deepcopy(summary)
        mutated_watchdog = copy.deepcopy(watchdog)
        mutated_timeline = copy.deepcopy(timeline)
        mutation(mutated_summary, mutated_watchdog, mutated_timeline)
        failed = runner._m6b_w6a_formal_gate(
            summary=mutated_summary,
            watchdog=mutated_watchdog,
            progress=progress,
            timeline=mutated_timeline,
            store_validation=store,
            numeric=numeric,
            artifact_inventory_ok=True,
            residual_files_ok=True,
            watchdog_contract_ok=True,
            expected_source_sha="a" * 40,
            runtime_identity_ok=True,
        )
        assert failed["pass"] is False


def test_w6a_formal_gate_rejects_self_consistent_but_wrong_actual_prediction():
    summary, watchdog, progress, timeline, store, numeric = _formal_gate_fixture()
    actual_store_audit = {
        **summary["carrier_audit"],
        "factor_audit": dict(summary["carrier_audit"]["factor_audit"]),
    }
    actual_prediction = runner._m6b_w6a_predicted_live_set(
        old_retained_bytes=100,
        new_retained_bytes=actual_store_audit["retained_z_r_bytes"]
        + runner.M6B_W6A_MANIFEST_RESERVE_BYTES,
        old_work_bytes=300,
        new_work_bytes=actual_store_audit["bounded_work_bytes"],
    )
    failed = runner._m6b_w6a_formal_gate(
        summary=summary,
        watchdog=watchdog,
        progress=progress,
        timeline=timeline,
        store_validation=store,
        numeric=numeric,
        artifact_inventory_ok=True,
        residual_files_ok=True,
        watchdog_contract_ok=True,
        expected_source_sha="a" * 40,
        runtime_identity_ok=True,
        actual_prediction=actual_prediction,
        actual_store_audit=actual_store_audit,
    )
    assert failed["checks"]["actual_payload_prediction"] is False
    assert failed["checks"]["actual_carrier_payload"] is True
    assert failed["pass"] is False


def test_w6a_progress_keeps_real_az_and_gram_boundaries(tmp_path):
    progress = tmp_path / "w6a_progress.jsonl"
    for event in runner.M6B_W6A_EVENTS:
        runner._m6b_w6a_progress_emit(progress, event, elapsed_wall_seconds=0.1)
    for completed in range(1, runner.M6B_W6A_COLUMNS + 1):
        runner._m6b_w6a_progress_emit(
            progress,
            "column_progress",
            elapsed_wall_seconds=0.2,
            completed_columns=completed,
            total_columns=runner.M6B_W6A_COLUMNS,
        )
    for completed, column in enumerate(runner.M6B_W6A_REPEAT_COLUMNS, 1):
        runner._m6b_w6a_progress_emit(
            progress,
            "repeat_ready",
            elapsed_wall_seconds=0.25,
            column_index=column,
            completed_repeats=completed,
            total_repeats=len(runner.M6B_W6A_REPEAT_COLUMNS),
        )
    for event in runner.M6B_W6A_TRAILING_EVENTS:
        runner._m6b_w6a_progress_emit(progress, event, elapsed_wall_seconds=0.3)
    checked = runner._m6b_w6a_progress_valid(progress)
    assert checked["pass"] is True
    assert checked["events"][-4:] == list(runner.M6B_W6A_TRAILING_EVENTS)


def test_w6a_jit_and_w5_authority_tamper_fail_closed(tmp_path, monkeypatch):
    source_path = tmp_path / "jit_source"
    target_path = tmp_path / "jit_target"
    source_path.mkdir()
    target_path.mkdir()

    class FakeH2B:
        @staticmethod
        def _cache_snapshot(_path):
            return [{"path": "module.o", "bytes": 7, "sha256": "d" * 64}]

        _canonical_json = staticmethod(runner._canonical_json)

    source_record = runner._m6b_w6a_cache_record(FakeH2B, source_path)
    target_record = runner._m6b_w6a_cache_record(FakeH2B, target_path)
    monkeypatch.setattr(
        runner, "M6B_W6A_JIT_INVENTORY_SHA256", source_record["inventory_sha256"]
    )
    jit = {
        "source": str(source_path),
        "target": str(target_path.resolve()),
        "source_before": source_record,
        "source_after_forward": source_record,
        "source_after_surface": source_record,
        "source_final": source_record,
        "target_before": target_record,
        "target_after_forward": target_record,
        "target_after_surface": target_record,
        "target_final": target_record,
        "source_unchanged": True,
        "target_frozen_unchanged": True,
    }
    assert runner._m6b_w6a_jit_cache_valid(jit, FakeH2B, source_path, target_path)
    tampered_jit = copy.deepcopy(jit)
    tampered_jit["target_final"] = {"inventory_sha256": "e" * 64}
    assert not runner._m6b_w6a_jit_cache_valid(
        tampered_jit, FakeH2B, source_path, target_path
    )

    w5_dir = tmp_path / "w5"
    raw_dir = tmp_path / "raw"
    w5_dir.mkdir()
    raw_dir.mkdir()
    records = {}
    compact_samples = {}
    for iteration in runner.M6B_W6A_W5_RESIDUAL_ITERATIONS:
        source_name = f"m6b_iter{iteration}_residual.npy"
        copy_name = f"m6b_w6a_residual_iter{iteration}.npy"
        values = np.zeros(runner.M6B_GLOBAL_ROWS, dtype=np.complex128)
        np.save(w5_dir / source_name, values)
        np.save(raw_dir / copy_name, values)
        source_artifact = runner._artifact(w5_dir, source_name)
        copy_artifact = runner._artifact(raw_dir, copy_name)
        array_sha = runner._m6b_w2_array_sha256(values)
        compact_samples[str(iteration)] = {
            "artifacts": {
                "residual": {
                    **source_artifact,
                    "array_sha256": array_sha,
                    "dtype": "complex128",
                    "shape": [runner.M6B_GLOBAL_ROWS],
                }
            }
        }
        records[str(iteration)] = {
            "source": source_artifact,
            "copy": copy_artifact,
            "path": copy_name,
            "present": True,
            "source_array_sha256": array_sha,
            "copy_array_sha256": array_sha,
        }
    compact = runner._attach_evidence(
        {
            "classification": "NUMERIC_FAIL",
            "producer_source_sha": runner.M6B_W6A_W5_SOURCE_SHA,
            "authority": {
                "factor_compiler": {
                    "probe_command": ["cc", "--version"],
                    "sysconfig_cc": "cc",
                    "version_line": "cc version",
                }
            },
            "screen": {"samples": compact_samples},
        }
    )
    assert runner._m6b_w6a_w5_residual_files_valid(
        records, raw_dir, w5_dir, compact_record=compact
    )
    tampered = np.zeros(runner.M6B_GLOBAL_ROWS, dtype=np.complex128)
    tampered[0] = 1.0
    np.save(w5_dir / "m6b_iter20_residual.npy", tampered)
    assert not runner._m6b_w6a_w5_residual_files_valid(
        records, raw_dir, w5_dir, compact_record=compact
    )


def test_w6a_w5_compact_hash_authority_fail_closed(monkeypatch):
    authority = runner._m6b_w6a_w5_compact_authority()
    assert authority["file_sha256"] == runner.M6B_W6A_W5_COMPACT_FILE_SHA256
    monkeypatch.setattr(runner, "M6B_W6A_W5_COMPACT_FILE_SHA256", "0" * 64)
    with pytest.raises(ValueError):
        runner._m6b_w6a_w5_compact_authority()


def test_w6a_runtime_identity_requires_frozen_compiler_and_abi():
    compiler = {
        "probe_command": ["cc", "--version"],
        "sysconfig_cc": "cc",
        "version_line": "cc version",
    }
    runtime = {
        "qualified_activation": "1",
        "sys_executable": "/opt/project/.venv/bin/python",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "mpi_size": 1,
        "linux_abi": True,
        "package_paths": {
            "petsc4py": "/opt/project/.venv/lib/petsc4py.py",
            "slepc4py": "/opt/project/.venv/lib/slepc4py.py",
            "dolfinx": "/opt/project/.venv/lib/dolfinx.py",
            "mpi4py": "/opt/project/.venv/lib/mpi4py.py",
        },
        "compiler": compiler,
    }
    assert runner._m6b_w6a_runtime_valid(runtime, frozen_compiler=compiler)
    tampered = copy.deepcopy(runtime)
    tampered["petsc_int_type"] = "int64"
    assert not runner._m6b_w6a_runtime_valid(tampered, frozen_compiler=compiler)
    tampered = copy.deepcopy(runtime)
    tampered["compiler"] = {**compiler, "version_line": "other"}
    assert not runner._m6b_w6a_runtime_valid(tampered, frozen_compiler=compiler)


def test_w6a_parser_exposes_real_builder_watchdog_and_formal_check():
    parser = runner._parser()
    builder = parser.parse_args(
        [
            "m6b-w6a-builder", "--run-dir", "raw", "--legacy-store-dir", "legacy",
            "--w5-raw-dir", "w5", "--jit-cache-source", "jit", "--expected-source-sha", "a" * 40,
        ]
    )
    watchdog = parser.parse_args(
        [
            "m6b-w6a-watchdog", "--run-dir", "raw", "--watchdog-dir", "watchdog",
            "--legacy-store-dir", "legacy", "--w5-raw-dir", "w5", "--jit-cache-source", "jit",
            "--expected-source-sha", "a" * 40,
        ]
    )
    formal = parser.parse_args(
        [
            "m6b-w6a-formal-check", "--raw-dir", "raw", "--watchdog-summary", "watchdog/w6a_watchdog_summary.json",
            "--legacy-store-dir", "legacy", "--w5-raw-dir", "w5", "--jit-cache-source", "jit",
            "--output", "out.json", "--expected-source-sha", "a" * 40,
        ]
    )
    assert builder.command == "m6b-w6a-builder"
    assert watchdog.command == "m6b-w6a-watchdog"
    assert formal.command == "m6b-w6a-formal-check"
