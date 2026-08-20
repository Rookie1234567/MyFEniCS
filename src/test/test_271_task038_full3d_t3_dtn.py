"""Focused contracts for the dynamic full-space Fourier-DtN action."""

from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.common.modes_3d import outgoing_port_modes_3d
from src.solvers.fullspace_dtn_action import (
    FULLSPACE_DTN_BATCH_SIZE,
    FullspaceDtnCarrier,
    FullspaceDtnModeFunctional,
    build_dynamic_mode_inventory,
    build_fullspace_dtn_action,
    build_fullspace_dtn_carrier_from_surface,
    classify_port_mode,
)
from src.test.stage2_test_utils import stage4_block_config


def _identity(index: int, h: float) -> dict[str, object]:
    return {
        "schema": "synthetic-fullspace-dtn-mode",
        "mode_index": index,
        "side": "top",
        "m": index,
        "n": 0,
        "polarization": "s",
        "alpha": 0.0 + 0.0j,
        "gamma": 0.0 + 0.0j,
        "beta": 1.0 + 0.0j,
        "k_vector": (0.0 + 0.0j, 0.0 + 0.0j, 1.0 + 0.0j),
        "e_vector": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
        "h_vector": (0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j),
        "refractive_index": 1.0 + 0.0j,
        "vertical_sign": 1,
        "electric_tangential_norm_sq": 1.0,
        "power_per_unit_amplitude": 1.0,
        "propagating": True,
        "rayleigh_warning": False,
        "classification": "propagating",
        "rayleigh_tolerance": 1.0e-6,
        "projection_denominator": h,
        "traction_vector": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
    }


def _synthetic_carrier(
    global_rows: int,
    mode_count: int,
    *,
    batch_size: int,
    mark_first_row_slave: bool = False,
) -> FullspaceDtnCarrier:
    comm = MPI.COMM_WORLD
    ranges = comm.allgather(global_rows // comm.size)
    owned_start = int(sum(ranges[: comm.rank]))
    owned_end = owned_start + int(ranges[comm.rank])
    if comm.rank == comm.size - 1:
        owned_end = global_rows
    rows = np.arange(owned_start, owned_end, dtype=PETSc.IntType)
    entries = []
    for mode in range(mode_count):
        coupling = (mode + 1.0) * (1.0 + 0.03j * rows)
        projection = (0.25 + 0.02j * mode) * (1.0 - 0.01j * rows)
        h = 1.0 + 0.2 * mode
        entries.append(
            FullspaceDtnModeFunctional(
                mode_key=(mode, "synthetic"),
                coupling_rows=rows,
                coupling_values=coupling,
                projection_rows=rows,
                projection_values=projection,
                normalization_h=h,
                mode_identity=_identity(mode, h),
            )
        )
    return FullspaceDtnCarrier(
        entries,
        global_rows=global_rows,
        ownership_range=(owned_start, owned_end),
        slave_rows=rows[:1] if mark_first_row_slave else (),
        batch_size=batch_size,
        comm=comm,
    )


def _source(global_rows: int) -> PETSc.Vec:
    comm = MPI.COMM_WORLD
    ranges = comm.allgather(global_rows // comm.size)
    start = int(sum(ranges[: comm.rank]))
    end = start + int(ranges[comm.rank])
    if comm.rank == comm.size - 1:
        end = global_rows
    vector = PETSc.Vec().createMPI((end - start, global_rows), comm=comm)
    ids = np.arange(start, end, dtype=PETSc.IntType)
    vector.setValues(
        ids,
        np.asarray(1.0 + 0.1 * ids + 1j * (0.4 - 0.02 * ids), dtype=PETSc.ScalarType),
    )
    vector.assemble()
    return vector


def _source_for_carrier(carrier: FullspaceDtnCarrier) -> PETSc.Vec:
    start, stop = carrier.ownership_range
    vector = PETSc.Vec().createMPI(
        (stop - start, carrier.global_rows),
        comm=carrier.comm,
    )
    ids = np.arange(start, stop, dtype=PETSc.IntType)
    vector.setValues(
        ids,
        np.asarray(1.0 + 0.1 * ids + 1j * (0.4 - 0.02 * ids), dtype=PETSc.ScalarType),
    )
    vector.assemble()
    return vector


def _synthetic_modal_sum(
    global_rows: int, mode_count: int, source: PETSc.Vec
) -> tuple[PETSc.Vec, np.ndarray]:
    comm = source.getComm().tompi4py()
    start, stop = map(int, source.getOwnershipRange())
    source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    target = source.duplicate()
    target.set(0.0)
    target_values = target.getArray()
    rows = np.arange(start, stop, dtype=PETSc.IntType)
    amplitudes = np.empty(mode_count, dtype=np.complex128)
    for mode in range(mode_count):
        coupling = (mode + 1.0) * (1.0 + 0.03j * rows)
        projection = (0.25 + 0.02j * mode) * (1.0 - 0.01j * rows)
        h = 1.0 + 0.2 * mode
        local = np.dot(projection, source_values)
        amplitude = complex(comm.allreduce(local, op=MPI.SUM)) / h
        amplitudes[mode] = amplitude
        target_values += amplitude * coupling
    return target, amplitudes


def _independent_surface_modal_sum(
    modes, cfg, assemblers, mpc, source: PETSc.Vec
) -> tuple[PETSc.Vec, np.ndarray]:
    """Assemble a fresh modal sum without consulting the candidate carrier."""

    from src.solvers.dtn_port_3d import (
        _combine_owned_entries,
        _mode_projection_denominator,
        _traction_vector,
    )

    comm = source.getComm().tompi4py()
    start, _stop = map(int, source.getOwnershipRange())
    source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    target = source.duplicate()
    target.set(0.0)
    target_values = target.getArray()
    amplitudes = np.empty(len(modes), dtype=np.complex128)
    for index, mode in enumerate(modes):
        components = (
            assemblers[(mode.side, 0)].assemble_entries(mode, mpc),
            assemblers[(mode.side, 1)].assemble_entries(mode, mpc),
        )
        projection_rows, projection_values = _combine_owned_entries(
            components,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        traction = _traction_vector(mode, cfg)
        coupling_rows, coupling_values = _combine_owned_entries(
            components,
            (-traction[0], -traction[1]),
            comm=comm,
        )
        local = (
            np.vdot(
                projection_values,
                source_values[projection_rows - start],
            )
            if projection_rows.size
            else 0.0 + 0.0j
        )
        amplitude = complex(comm.allreduce(local, op=MPI.SUM))
        amplitude /= _mode_projection_denominator(mode, cfg)
        amplitudes[index] = amplitude
        if coupling_rows.size:
            target_values[coupling_rows - start] += amplitude * coupling_values
    return target, amplitudes


def _relative_error(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    try:
        return float(difference.norm() / max(right.norm(), 1.0e-30))
    finally:
        difference.destroy()


@pytest.mark.parametrize("degree", [2, 3])
def test_dynamic_action_and_recovery_match_independent_modal_sum(degree: int) -> None:
    mode_count = degree + 2
    carrier = _synthetic_carrier(12, mode_count, batch_size=FULLSPACE_DTN_BATCH_SIZE)
    assert carrier.slave_rows.size == 0
    source = _source(carrier.global_rows)
    expected, expected_amplitudes = _synthetic_modal_sum(
        carrier.global_rows, mode_count, source
    )
    action = build_fullspace_dtn_action(carrier)
    observed = source.duplicate()
    try:
        action.matrix.mult(source, observed)
        recovered = action.recover_auxiliary(source)
        assert _relative_error(observed, expected) <= 1.0e-11
        np.testing.assert_allclose(recovered, expected_amplitudes, atol=1.0e-11, rtol=0.0)
        audit = action.audit
        assert audit["normalization_nonidentity"] is True
        assert audit["explicit_c_matrix_count"] == 0
        assert audit["explicit_d_matrix_count"] == 0
        assert audit["numeric_allgather"] is False
        assert audit["batch_count"] == (degree + 2 + FULLSPACE_DTN_BATCH_SIZE - 1) // FULLSPACE_DTN_BATCH_SIZE
        base = source.copy()
        rhs = source.duplicate()
        modal_rhs = source.duplicate()
        action.compose_physical_rhs(base, recovered, rhs)
        action.apply_modal_rhs(recovered, modal_rhs)
        assert _relative_error(modal_rhs, expected) <= 1.0e-12
        expected_rhs = base.copy()
        expected_rhs.axpy(PETSc.ScalarType(1.0), expected)
        assert _relative_error(rhs, expected_rhs) <= 1.0e-12
        modal_rhs.destroy()
        rhs.destroy()
        expected_rhs.destroy()
        base.destroy()
    finally:
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()


def test_batch_sizes_are_equivalent_and_work_is_batch_bounded() -> None:
    carrier_one = _synthetic_carrier(12, 7, batch_size=1)
    carrier_three = _synthetic_carrier(12, 7, batch_size=3)
    source = _source(12)
    action_one = build_fullspace_dtn_action(carrier_one)
    action_three = build_fullspace_dtn_action(carrier_three)
    target_one = source.duplicate()
    target_three = source.duplicate()
    try:
        action_one.matrix.mult(source, target_one)
        action_three.matrix.mult(source, target_three)
        assert _relative_error(target_one, target_three) <= 1.0e-12
        np.testing.assert_allclose(
            action_one.recover_auxiliary(source),
            action_three.recover_auxiliary(source),
            atol=1.0e-12,
            rtol=0.0,
        )
        assert action_one.audit["batch_count"] == 7
        assert action_three.audit["batch_count"] == 3
        assert action_one.audit["bounded_work_bytes_local"] < action_three.audit["recovery_output_bytes"]
        assert action_three.audit["bounded_work_scales_with"] == "fixed_modal_batch_size"
    finally:
        target_one.destroy()
        target_three.destroy()
        source.destroy()
        action_one.destroy()
        action_three.destroy()


def test_carrier_rejects_functional_touching_local_slave_row() -> None:
    with pytest.raises(ValueError, match="slave row"):
        _synthetic_carrier(
            12,
            3,
            batch_size=FULLSPACE_DTN_BATCH_SIZE,
            mark_first_row_slave=True,
        )


def test_two_physical_inventories_and_classification_hash_are_dynamic() -> None:
    zero_cfg = stage4_block_config(stage4_dtn_order_policy="zero_order")
    auto_cfg = stage4_block_config(
        stage4_dtn_order_policy="auto_propagating",
        diffraction_zero_order_only=False,
    )
    zero_modes, zero_manifest, zero_sha = build_dynamic_mode_inventory(zero_cfg)
    auto_modes, auto_manifest, auto_sha = build_dynamic_mode_inventory(auto_cfg)
    assert len(zero_modes) == 4
    assert len(auto_modes) > len(zero_modes)
    assert len(auto_modes) != 80
    assert len(zero_manifest) == len(zero_modes)
    assert len(auto_manifest) == len(auto_modes)
    assert {row["classification"] for row in auto_manifest} <= {
        "propagating",
        "near-cutoff",
        "evanescent",
    }
    assert all(
        row["classification"]
        == classify_port_mode(mode)
        for mode, row in zip(auto_modes, auto_manifest, strict=True)
    )
    repeat_modes, repeat_manifest, repeat_sha = build_dynamic_mode_inventory(auto_cfg)
    assert [mode.side for mode in repeat_modes] == [mode.side for mode in auto_modes]
    assert repeat_manifest == auto_manifest
    assert repeat_sha == auto_sha
    assert zero_sha != auto_sha

    near_cutoff = SimpleNamespace(propagating=True, rayleigh_warning=True)
    evanescent = SimpleNamespace(propagating=False, rayleigh_warning=False)
    assert classify_port_mode(near_cutoff) == "near-cutoff"
    assert classify_port_mode(evanescent) == "evanescent"


def test_frozen_formal_identity_comes_from_t1_adapter_and_80_modes() -> None:
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from benchmarks.run_task038_full3d_t3 import (
        T3_EXPECTED_MODE_COUNT,
        _frozen_benchmark_identity,
    )

    specification = load_and_resolve("input/templates/full3d_iterative_example.dat")
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    identity = _frozen_benchmark_identity(
        specification, cfg, case="p6-h10", mode_count=T3_EXPECTED_MODE_COUNT
    )
    assert identity["wavelength_nm"] == 13.5
    assert identity["nedelec_degree"] == 6
    assert identity["mesh_target_nm"] == 10.0
    assert identity["discovered_mode_count"] == 80
    with pytest.raises(RuntimeError, match="identity"):
        _frozen_benchmark_identity(specification, cfg, case="p6-h10", mode_count=79)
    from benchmarks.task038_full3d_t3_checker import _benchmark_identity_errors

    broken = dict(identity)
    broken.pop("wavelength_nm")
    assert any(
        "benchmark identity field is missing: wavelength_nm" in message
        for message in _benchmark_identity_errors({"benchmark": broken}, Path("."))
    )


@dataclass
class _IndexMap:
    local_range: tuple[int, int]
    size_local: int
    size_global: int

    def local_to_global(self, rows):
        return np.asarray(rows, dtype=PETSc.IntType) + self.local_range[0]


class _SurfaceAssembler:
    def __init__(self, rows: np.ndarray, component: int, slave_row: int):
        self._rows = rows
        self._component = component
        self._slave_row = int(slave_row)

    def assemble_entries(self, mode, _mpc):
        if self._component == 1:
            return np.empty(0, dtype=PETSc.IntType), np.empty(0, dtype=np.complex128)
        active_rows = self._rows[self._rows != self._slave_row]
        values = (1.0 + 0.01j * active_rows) * (1.0 + 0.02 * abs(mode.m))
        return active_rows, values


def test_surface_builder_preserves_owner_local_mpc_rows_and_h_identity() -> None:
    comm = MPI.COMM_WORLD
    global_rows = 12
    ranges = comm.allgather(global_rows // comm.size)
    start = int(sum(ranges[: comm.rank]))
    end = start + int(ranges[comm.rank])
    if comm.rank == comm.size - 1:
        end = global_rows
    index_map = _IndexMap((start, end), end - start, global_rows)
    function_space = SimpleNamespace(
        dofmap=SimpleNamespace(index_map=index_map),
        mesh=SimpleNamespace(comm=comm),
    )
    mpc = SimpleNamespace(
        function_space=function_space,
        slaves=np.asarray([0], dtype=np.int32),
    )
    cfg = stage4_block_config(stage4_dtn_order_policy="zero_order")
    modes = tuple(outgoing_port_modes_3d(cfg))
    rows = np.arange(start, end, dtype=PETSc.IntType)
    assemblers = {
        (side, component): _SurfaceAssembler(rows, component, start)
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes,
        assemblers,
        mpc,
        cfg,
    )
    audit = carrier.audit
    assert audit["mode_count"] == len(modes)
    assert audit["owner_local_surface_functionals"] is True
    assert audit["slave_rows_local"] == 1
    assert audit["normalization"] == "explicit_diagonal_projection_denominator_H"
    assert audit["normalization_nonidentity"] is True
    assert audit["batch_size"] == FULLSPACE_DTN_BATCH_SIZE
    assert audit["slave_functional_rows_local"] == 0
    assert audit["global_aij_materialized"] is False
    assert audit["global_schur_materialized"] is False
    slave_rows = set(int(row) for row in carrier.slave_rows)
    assert all(int(row) in range(start, end) for item in carrier.entries for row in item.coupling_rows)
    assert all(
        int(row) not in slave_rows
        for item in carrier.entries
        for row in (*item.coupling_rows, *item.projection_rows)
    )
    action = build_fullspace_dtn_action(carrier)
    source = _source_for_carrier(carrier)
    target = source.duplicate()
    try:
        action.matrix.mult(source, target)
        start, _stop = carrier.ownership_range
        target_values = np.asarray(target.getArray(readonly=True))
        np.testing.assert_allclose(
            target_values[carrier.slave_rows - start],
            0.0,
            atol=0.0,
            rtol=0.0,
        )
        assert action.audit["slave_functional_rows_local"] == 0
    finally:
        target.destroy()
        source.destroy()
        action.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="the tiny assembled-surface p2/p3 fixture is serial; MPI ownership is covered above",
)
@pytest.mark.parametrize("degree", [2, 3])
def test_p2_p3_current_surface_functionals_match_modal_sum(
    tmp_path, degree: int
) -> None:
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import (
        _ReusableSurfaceComponentAssembler,
        _dtn_surface_quadrature_degree,
    )

    cfg = replace(
        stage4_block_config(
            stage4_dtn_order_policy="zero_order",
            diffraction_zero_order_only=True,
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=50.0,
        ),
        nedelec_degree=degree,
    )
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / f"mesh-p{degree}")
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, mesh_data, cfg)
    modes = tuple(outgoing_port_modes_3d(cfg))
    quadrature = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = {
        (side, component): _ReusableSurfaceComponentAssembler(
            V,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=quadrature,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes,
        assemblers,
        floquet_data.mpc,
        cfg,
    )
    oracle_assemblers = {
        (side, component): _ReusableSurfaceComponentAssembler(
            V,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=quadrature,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    from src.solvers.dtn_port_3d import _assemble_mpc_vector, _incident_top_traction_form

    source = _assemble_mpc_vector(
        _incident_top_traction_form(V, mesh_data, cfg),
        floquet_data.mpc,
        quadrature_degree=quadrature,
    )
    expected, expected_amplitudes = _independent_surface_modal_sum(
        modes, cfg, oracle_assemblers, floquet_data.mpc, source
    )
    action = build_fullspace_dtn_action(carrier)
    observed = source.duplicate()
    try:
        action.matrix.mult(source, observed)
        np.testing.assert_allclose(
            action.recover_auxiliary(source),
            expected_amplitudes,
            atol=1.0e-11,
            rtol=0.0,
        )
        assert _relative_error(observed, expected) <= 1.0e-11
        assert action.audit["normalization_nonidentity"] is True
        assert action.audit["owner_local_surface_functionals"] is True
    finally:
        observed.destroy()
        expected.destroy()
        source.destroy()
        action.destroy()


def test_checker_is_read_only_and_does_not_import_execution_stack() -> None:
    import benchmarks.task038_full3d_t3_checker as checker

    source = inspect.getsource(checker)
    assert "petsc4py" not in source
    assert "mpi4py" not in source
    assert "src.solvers" not in source
    assert "run_task038_full3d_t3" not in source
