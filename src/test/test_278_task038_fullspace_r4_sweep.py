"""Focused R4 Candidate-A contracts and real split-action oracles."""

from __future__ import annotations

from pathlib import Path
import ast
import hashlib
import json

import numpy as np
import pytest
from mpi4py import MPI

from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.common_3d_fields import incident_air_plane_wave_field
from src.solvers.dtn_port_3d import (
    _dtn_surface_quadrature_degree,
)
from src.solvers.fullspace_dtn_action import (
    build_dynamic_mode_inventory,
    build_fullspace_dtn_action,
    build_fullspace_dtn_carrier_from_surface,
)
from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
from src.solvers.fullspace_physical_action import FullspacePhysicalAction
from src.solvers.fullspace_slab_interface import FirstOrderImpedanceTransmission
from src.solvers.fullspace_sweep import (
    FULLSPACE_R4_BACKWARD_ORDER,
    FULLSPACE_R4_FORWARD_ORDER,
    FULLSPACE_R4_LOCAL_KSP_MAX_IT,
    FULLSPACE_R4_LOCAL_KSP_RESTART,
    FULLSPACE_R4_SLAB_COUNT,
    build_fullspace_slab_plan,
    build_slab_volume_actions,
    build_candidate_a,
    candidate_a_audit,
)
from src.test.test_272_task038_full3d_t4_slab_interface import _real_fixture


def _relative_owned(left, right, comm: MPI.Comm) -> float:
    difference = np.asarray(left - right, dtype=np.complex128)
    reference = np.asarray(right, dtype=np.complex128)
    numerator = comm.allreduce(float(np.vdot(difference, difference).real), op=MPI.SUM)
    denominator = comm.allreduce(float(np.vdot(reference, reference).real), op=MPI.SUM)
    return float(np.sqrt(numerator) / max(np.sqrt(denominator), np.finfo(float).tiny))


def _mask(source, support):
    masked = source.duplicate()
    source.copy(masked)
    values = masked.getArray()
    keep = np.zeros(values.size, dtype=bool)
    keep[support.owned_local_rows] = True
    values[~keep] = 0.0
    return masked


def _surface_assemblers(space, mesh_data, cfg, qdegree):
    from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler

    return {
        (side, component): _ReusableSurfaceComponentAssembler(
            space,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=qdegree,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }


def _real_split_case(tmp_path: Path, degree: int):
    cfg, mesh_data, space, floquet_data, topology = _real_fixture(tmp_path, degree)
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    plan = build_fullspace_slab_plan(topology)
    bilinear, _rhs = _build_variational_forms(
        mesh_data.mesh, mesh_data, cfg, raw_space, field_formulation="total_field"
    )
    full_volume = build_fullspace_mpc_form_action(
        bilinear, raw_space, mpc=floquet_data.mpc
    )
    split_volume = build_slab_volume_actions(
        plan,
        topology,
        mesh_data,
        raw_space,
        floquet_data.mpc,
        cfg,
    )
    modes, _manifest, _digest = build_dynamic_mode_inventory(cfg)
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = _surface_assemblers(raw_space, mesh_data, cfg, qdegree)
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, floquet_data.mpc, cfg
    )
    dtn = build_fullspace_dtn_action(carrier, comm=MPI.COMM_WORLD)
    field = incident_air_plane_wave_field(space, cfg)
    field.x.scatter_forward()
    floquet_data.mpc.homogenize(field)
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    source = field.x.petsc_vec.duplicate()
    field.x.petsc_vec.copy(source)
    return cfg, mesh_data, space, floquet_data, topology, plan, full_volume, split_volume, dtn, field, source


def _destroy_case(case):
    _cfg, _mesh_data, _space, _floquet, _topology, _plan, full, split, dtn, field, source = case
    for action in (full, *split):
        action.destroy()
    dtn.destroy()
    source.destroy()


def test_candidate_a_frozen_contract() -> None:
    audit = candidate_a_audit()
    assert audit["profile"] == "full3d_scalable_v1"
    assert audit["slab_count"] == FULLSPACE_R4_SLAB_COUNT == 2
    assert audit["forward_order"] == FULLSPACE_R4_FORWARD_ORDER == (0, 1)
    assert audit["backward_order"] == FULLSPACE_R4_BACKWARD_ORDER == (1, 0)
    assert audit["transmission_q"] == "-i*k0*n_side"
    assert audit["local_ksp_count"] == 2
    assert audit["local_operator_type"] == "PETSc.MatShell"
    assert audit["global_ksp_created"] is False
    assert audit["local_ksp_restart"] == FULLSPACE_R4_LOCAL_KSP_RESTART == 8
    assert audit["local_ksp_max_it"] == FULLSPACE_R4_LOCAL_KSP_MAX_IT == 8
    assert audit["pou"] == "inverse_owner_multiplicity"
    assert audit["parameters_frozen_before_rho"] is True
    assert audit["global_aij_materialized"] is False
    assert audit["global_schur_materialized"] is False
    assert audit["dense_interface_materialized"] is False
    assert audit["growing_slab_factor_materialized"] is False


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial split-action oracle")
@pytest.mark.parametrize("degree", [2, 3])
def test_serial_split_volume_and_side_dtn_oracles(tmp_path: Path, degree: int) -> None:
    case = _real_split_case(tmp_path, degree)
    try:
        _cfg, _mesh_data, _space, _floquet, _topology, plan, full, split, dtn, _field, source = case
        full_result = full.apply(source)
        full_values = np.asarray(
            full_result.getArray(readonly=True), dtype=np.complex128
        ).copy()
        split_values = []
        for action in split:
            result = action.apply(source)
            split_values.append(np.asarray(result.getArray(readonly=True), dtype=np.complex128).copy())
        split_sum = split_values[0] + split_values[1]
        slave_rows = np.asarray(
            _floquet.local_slave_dofs,
            dtype=np.int32,
        )
        slave_rows = slave_rows[slave_rows < source.getArray(readonly=True).size]
        active = np.ones(split_sum.size, dtype=bool)
        active[slave_rows] = False
        assert _relative_owned(split_sum[active], full_values[active], MPI.COMM_WORLD) <= 1.0e-12
        for action in split:
            audit = action.audit
            assert audit["slave_row_identity"] is False
            assert audit["global_matrix_materialized"] is False
            assert audit["global_condensed_schur_materialized"] is False
            assert audit["factor_count"] == 0
            assert audit["ksp_created"] is False
            assert audit["numeric_allgather"] is False
        assert np.max(np.abs(split_sum[slave_rows]), initial=0.0) == 0.0
        assert np.max(
            np.abs(full_values[slave_rows] - source.getArray(readonly=True)[slave_rows]),
            initial=0.0,
        ) <= 1.0e-14

        full_dtn = source.duplicate()
        dtn.apply(source, full_dtn)
        side_values = []
        for support in plan.supports:
            masked = _mask(source, support)
            side = source.duplicate()
            dtn.apply(masked, side)
            side_values.append(np.asarray(side.getArray(readonly=True), dtype=np.complex128).copy())
            masked.destroy()
            side.destroy()
        assert _relative_owned(side_values[0] + side_values[1], full_dtn.getArray(readonly=True), MPI.COMM_WORLD) <= 1.0e-12
        assert plan.audit["cell_restriction"] == "owned_cells_partitioned_by_cfg.interface_z"
        assert plan.audit["summed_slab_support_count"] >= plan.audit["global_unique_active_row_count"]
        assert plan.audit["pou_max_error"] <= 1.0e-14
        assert plan.supports[0].outer_side == "bottom"
        assert plan.supports[1].outer_side == "top"
        full_dtn.destroy()
    finally:
        _destroy_case(case)


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 split-action oracle")
@pytest.mark.parametrize("degree", [2, 3])
def test_mpi2_split_volume_and_side_dtn_oracles(tmp_path: Path, degree: int) -> None:
    # This is the same owner-local numerical oracle as the serial test.  The
    # fixture is collective; no rank constructs a second COMM_WORLD mesh.
    case = _real_split_case(tmp_path, degree)
    try:
        _cfg, _mesh_data, _space, _floquet, _topology, plan, full, split, dtn, _field, source = case
        full_result = full.apply(source)
        full_values = np.asarray(
            full_result.getArray(readonly=True), dtype=np.complex128
        ).copy()
        split_values = [
            np.asarray(action.apply(source).getArray(readonly=True), dtype=np.complex128).copy()
            for action in split
        ]
        slave_rows = np.asarray(
            _floquet.local_slave_dofs,
            dtype=np.int32,
        )
        slave_rows = slave_rows[slave_rows < source.getArray(readonly=True).size]
        split_sum = split_values[0] + split_values[1]
        active = np.ones(split_sum.size, dtype=bool)
        active[slave_rows] = False
        assert _relative_owned(split_sum[active], full_values[active], MPI.COMM_WORLD) <= 1.0e-12
        for action in split:
            audit = action.audit
            assert audit["slave_row_identity"] is False
            assert audit["global_matrix_materialized"] is False
            assert audit["global_condensed_schur_materialized"] is False
            assert audit["factor_count"] == 0
            assert audit["ksp_created"] is False
            assert audit["numeric_allgather"] is False
        assert np.max(np.abs(split_sum[slave_rows]), initial=0.0) == 0.0
        full_dtn = source.duplicate()
        dtn.apply(source, full_dtn)
        side_values = []
        for support in plan.supports:
            masked = _mask(source, support)
            side = source.duplicate()
            dtn.apply(masked, side)
            side_values.append(np.asarray(side.getArray(readonly=True), dtype=np.complex128).copy())
            masked.destroy()
            side.destroy()
        assert _relative_owned(side_values[0] + side_values[1], full_dtn.getArray(readonly=True), MPI.COMM_WORLD) <= 1.0e-12
        assert plan.audit["numeric_allgather"] is False
        assert plan.audit["global_unique_active_row_count"] > 0
        full_dtn.destroy()
    finally:
        _destroy_case(case)


def test_checkerboard_source_formula_is_fixed() -> None:
    source = Path("benchmarks/run_task038_full3d_r4.py").read_text(encoding="utf-8")
    assert "8.0 * kx" in source
    assert "8.0 * ky" in source
    assert "8.0 * kz" in source
    assert "rho" not in source[source.index("def _analytic_primal"):source.index("def _read_long_tail")]


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial Candidate-A sweep smoke")
def test_serial_candidate_a_runs_complete_fixed_ledger(tmp_path: Path) -> None:
    case = _real_split_case(tmp_path, 2)
    cfg, _mesh_data, space, floquet_data, topology, plan, full, split, dtn, _field, source = case
    transmission = FirstOrderImpedanceTransmission(space, topology, mpc=floquet_data.mpc)
    physical = FullspacePhysicalAction(full, dtn)
    candidate = build_candidate_a(plan, split, dtn, transmission, physical)
    try:
        result = candidate.sweep(source)
        try:
            assert len(result.ledger) == 4
            assert [(row["direction"], row["slab"]) for row in result.ledger] == [
                ("forward", 0),
                ("forward", 1),
                ("backward", 1),
                ("backward", 0),
            ]
            assert [row["neighbor_slab"] for row in result.ledger] == [1, None, 0, None]
            assert all(row["action_sha256"] and row["residual_sha256"] for row in result.ledger)
            assert result.audit["exact_update_apply_count"] == 5
            assert result.audit["exact_update_apply_count_cumulative"] == 5
            assert result.audit["local_ksp_count"] == 2
            assert result.audit["local_operator_type"] == "PETSc.MatShell"
            assert result.audit["global_ksp_created"] is False
            assert result.audit["residual_propagation"] is True
            assert result.audit["recursive_residual_closure_relative_error"] <= 1.0e-11
            assert all(
                audit["slave_row_identity"] is False
                for audit in result.audit["split_volume_action_audits"]
            )
            assert np.all(np.isfinite(result.residual.getArray(readonly=True)))
            assert result.audit["fixed_iteration_semantics"] == "DIVERGED_ITS_is_expected"
        finally:
            first_delta = np.asarray(result.delta.getArray(readonly=True), dtype=np.complex128).copy()
            first_residual = np.asarray(result.residual.getArray(readonly=True), dtype=np.complex128).copy()
            first_ledger = result.ledger
            result.delta.destroy()
            result.action_delta.destroy()
            result.residual.destroy()
        repeat = candidate.sweep(source)
        try:
            assert repeat.ledger == first_ledger
            assert np.array_equal(repeat.delta.getArray(readonly=True), first_delta)
            assert np.array_equal(repeat.residual.getArray(readonly=True), first_residual)
            assert repeat.audit["exact_update_apply_count"] == 5
            assert repeat.audit["exact_update_apply_count_cumulative"] == 10
            assert repeat.audit["recursive_residual_closure_relative_error"] <= 1.0e-11
        finally:
            repeat.delta.destroy()
            repeat.action_delta.destroy()
            repeat.residual.destroy()
    finally:
        candidate.destroy()
        transmission.destroy()
        physical.destroy()
        source.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="MPI2 Candidate-A ownership smoke")
def test_mpi2_candidate_a_runs_complete_fixed_ledger(tmp_path: Path) -> None:
    case = _real_split_case(tmp_path, 2)
    _cfg, _mesh_data, space, floquet_data, topology, plan, full, split, dtn, _field, source = case
    transmission = FirstOrderImpedanceTransmission(space, topology, mpc=floquet_data.mpc)
    physical = FullspacePhysicalAction(full, dtn)
    candidate = build_candidate_a(plan, split, dtn, transmission, physical)
    try:
        result = candidate.sweep(source)
        try:
            assert len(result.ledger) == 4
            assert [row["neighbor_slab"] for row in result.ledger] == [1, None, 0, None]
            assert result.audit["exact_update_apply_count"] == 5
            assert result.audit["exact_update_apply_count_cumulative"] == 5
            assert result.audit["local_ksp_count"] == 2
            assert result.audit["local_operator_type"] == "PETSc.MatShell"
            assert result.audit["global_ksp_created"] is False
            assert result.audit["residual_propagation"] is True
            assert result.audit["recursive_residual_closure_relative_error"] <= 1.0e-11
            assert np.all(np.isfinite(result.residual.getArray(readonly=True)))
            assert result.audit["numeric_allgather"] is False
        finally:
            result.delta.destroy()
            result.action_delta.destroy()
            result.residual.destroy()
    finally:
        candidate.destroy()
        transmission.destroy()
        physical.destroy()
        source.destroy()


def test_r4_checker_is_read_only_and_identity_fail_closed(tmp_path: Path) -> None:
    from benchmarks.task038_full3d_r4_checker import check_record

    checker_source = Path("benchmarks/task038_full3d_r4_checker.py").read_text(encoding="utf-8")
    assert "task038.t5.external-process-tree-raw.v1" in checker_source
    assert "task038.t5.external-process-tree-compact.v1" in checker_source
    assert "external_process_tree_watchdog.v1" not in checker_source
    assert "--watchdog-raw" in checker_source
    assert "--watchdog-compact" in checker_source
    tree = ast.parse(checker_source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.startswith(("src.solvers", "petsc4py", "mpi4py")) for name in imports)
    record_path = tmp_path / "record.json"
    record_path.write_text(
        json.dumps({"schema": "task038.full3d.iterative.r4.candidate-a-record.v1", "source_name": "physical_rhs"}),
        encoding="utf-8",
    )
    result = check_record(record_path)
    assert result["status"] == "FAIL"
    assert any("source_identity" in error for error in result["errors"])
    assert any("input_identity" in error for error in result["errors"])


def test_r4_watchdog_uses_t5_pair_and_binds_worker_command(tmp_path: Path) -> None:
    from benchmarks.task038_full3d_r4_checker import _check_watchdog

    record_path = tmp_path / "record.json"
    expected_sha = "a" * 40
    record = {
        "source_name": "gradient",
        "mpi_size": 1,
        "source_identity": {"expected_sha": expected_sha},
    }
    command = [
        "python",
        "benchmarks/run_task038_full3d_r4.py",
        "--record",
        str(record_path.resolve()),
        "--source",
        "gradient",
        "--expected-source-sha",
        expected_sha,
        "--degree",
        "6",
        "--mesh-target",
        "10.0",
        "--expected-mpi-size",
        "1",
    ]
    raw = {
        "schema": "task038.t5.external-process-tree-raw.v1",
        "command": command,
        "samples": [
            {
                "process_tree": {
                    "rss_bytes": 123,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                },
                "job_cgroup": {"dedicated_job_cgroup": False},
                "memory_authority_bytes": 456,
                "job_no_swap": True,
            }
        ],
        "returncode": 0,
        "stop_reason": None,
        "termination": {"process_group_exited": True, "sigkill_required": False},
    }
    raw_path = tmp_path / "watchdog.raw.json"
    compact_path = tmp_path / "watchdog.compact.json"
    raw_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    compact = {
        "schema": "task038.t5.external-process-tree-compact.v1",
        "status": "measured_pass",
        "process_tree_peak_rss_bytes": 123,
        "process_tree_peak_swap_bytes": 0,
        "dedicated_cgroup_peak_swap_bytes": 0,
        "memory_authority_peak_bytes": 456,
        "process_tree_memory_ceiling_bytes": 6 * 1024**3,
        "hard_stop_memory_bytes": 12 * 1024**3,
        "swap_required_bytes": 0,
        "sample_count": 1,
        "all_status_readable": True,
        "stop_reason": None,
        "returncode": 0,
        "termination": raw["termination"],
        "raw_report_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    }
    compact_path.write_text(json.dumps(compact, sort_keys=True), encoding="utf-8")
    gate, _facts, errors = _check_watchdog(raw_path, compact_path, record_path, record)
    assert gate == "pass", errors
    raw["command"][raw["command"].index("--source") + 1] = "curl"
    raw_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    compact["raw_report_sha256"] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    compact_path.write_text(json.dumps(compact, sort_keys=True), encoding="utf-8")
    gate, _facts, errors = _check_watchdog(raw_path, compact_path, record_path, record)
    assert gate == "fail"
    assert any("--source" in error for error in errors)


def test_r4_runner_owns_only_duplicate_vectors() -> None:
    source = Path("benchmarks/run_task038_full3d_r4.py").read_text(encoding="utf-8")
    assert "source_field.x.petsc_vec.destroy()" not in source
    assert "np.zeros_like(sx)" in source
    assert "build_candidate_a(\n        plan," in source
