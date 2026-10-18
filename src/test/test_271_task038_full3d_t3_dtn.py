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


def test_sparse_dtn_entry_filters_are_scale_homogeneous_across_mpi_ranks() -> None:
    from src.solvers.dtn_port_3d import (
        _combine_owned_entries,
        _vec_nonzero_owned_entries,
    )

    comm = MPI.COMM_WORLD
    local_size = 4
    vector = PETSc.Vec().createMPI(
        (local_size, local_size * comm.size), comm=comm
    )
    scaled_vector = vector.duplicate()
    zero_vector = vector.duplicate()
    start, end = map(int, vector.getOwnershipRange())
    rank_scale = 10.0 ** (-comm.rank)
    base_values = 1.0e-20 * rank_scale * np.asarray(
        [1.0 + 2.0j, 1.0e-14 - 3.0e-15j, 2.0e-2 + 1.0e-2j, 0.0j],
        dtype=np.complex128,
    )
    complex_scale = 1.0e-50 * (0.6 + 0.8j)
    vector.array[:] = base_values
    scaled_vector.array[:] = complex_scale * base_values
    zero_vector.set(0.0)

    try:
        rows, values = _vec_nonzero_owned_entries(vector)
        scaled_rows, scaled_values = _vec_nonzero_owned_entries(scaled_vector)
        zero_rows, zero_values = _vec_nonzero_owned_entries(zero_vector)
        expected_rows = np.asarray([start, start + 2], dtype=PETSc.IntType)
        assert np.array_equal(rows, expected_rows)
        assert np.array_equal(scaled_rows, rows)
        np.testing.assert_allclose(
            scaled_values / complex_scale, values, rtol=1.0e-13, atol=0.0
        )
        assert zero_rows.size == 0
        assert zero_values.size == 0

        row_x = np.asarray([start, start + 1, start + 2], dtype=PETSc.IntType)
        row_y = np.asarray([start, start + 2], dtype=PETSc.IntType)
        component_x = base_values[[0, 1, 2]]
        component_y = base_values[[0, 2]] * np.asarray(
            [0.3 + 0.1j, -0.5 + 0.25j], dtype=np.complex128
        )
        coefficients = (0.8 + 0.3j, -0.2 + 0.7j)
        combined_rows, combined_values = _combine_owned_entries(
            ((row_x, component_x), (row_y, component_y)),
            coefficients,
            comm=comm,
        )
        scaled_rows, scaled_values = _combine_owned_entries(
            (
                (row_x, complex_scale * component_x),
                (row_y, complex_scale * component_y),
            ),
            coefficients,
            comm=comm,
        )
        assert np.array_equal(combined_rows, expected_rows)
        assert np.array_equal(scaled_rows, combined_rows)
        np.testing.assert_allclose(
            scaled_values / complex_scale, combined_values, rtol=1.0e-13, atol=0.0
        )
    finally:
        zero_vector.destroy()
        scaled_vector.destroy()
        vector.destroy()


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


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="shared output initialization regression runs under MPI2",
)
def test_mpi2_shared_raw_initialization_is_rank0_owned(tmp_path: Path) -> None:
    from benchmarks.run_task038_full3d_t3 import _prepare_raw_dir

    comm = MPI.COMM_WORLD
    shared_root = Path(
        comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0)
    ) / "shared-output"
    raw_dir = shared_root / "raw"
    record_path = shared_root / "record.json"
    if comm.rank == 0:
        shared_root.mkdir(parents=True)
    comm.barrier()
    _prepare_raw_dir(raw_dir, record_path, comm)
    assert raw_dir.is_dir()
    comm.barrier()

    existing_raw = shared_root / "existing-raw"
    if comm.rank == 0:
        existing_raw.mkdir()
    comm.barrier()
    with pytest.raises(FileExistsError, match="already exists"):
        _prepare_raw_dir(existing_raw, shared_root / "new-record.json", comm)
    comm.barrier()


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


def test_resumable_carrier_progress_reports_only_durable_appends(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import src.solvers.fullspace_dtn_action as module

    modes = tuple(
        SimpleNamespace(side="top", m=index, n=0, polarization="s")
        for index in range(2)
    )
    mode_identities = tuple(_identity(index, 1.0) for index in range(2))
    mode_rows = tuple({"projection_denominator": 1.0} for _ in modes)
    physical_sha = "a" * 64
    assembly_sha = "b" * 64
    monkeypatch.setattr(
        module,
        "build_ordered_mode_manifest",
        lambda *_args: (mode_rows, b"fixture-manifest", physical_sha),
    )
    monkeypatch.setattr(
        module,
        "_resumable_carrier_mode_identity",
        lambda *_args, **_kwargs: (
            mode_identities,
            np.ones(2, dtype=np.float64),
            assembly_sha,
            {"fixture_execution_identity": "same-window"},
        ),
    )

    def functional_iterator(
        _modes,
        _assemblers,
        _mpc,
        _cfg,
        *,
        mode_indices,
        audit,
        progress_callback,
        **_kwargs,
    ):
        audit.update(
            physical_generator_manifest_sha256=physical_sha,
            assembly_context_sha256=assembly_sha,
            peak_component_cache_unique_backing_bytes=64,
            current_component_cache_unique_backing_bytes=0,
        )
        for completed, index in enumerate(mode_indices, start=1):
            entry = FullspaceDtnModeFunctional(
                mode_key=(index, "top", index, 0, "s"),
                coupling_rows=np.asarray([0], dtype=np.int32),
                coupling_values=np.asarray([1.0 + index * 1.0j], dtype=np.complex128),
                projection_rows=np.asarray([0], dtype=np.int32),
                projection_values=np.asarray([2.0 + index * 1.0j], dtype=np.complex128),
                normalization_h=1.0,
                mode_identity=mode_identities[index],
            )
            progress_callback(
                {
                    "phase": "dtn_carrier_mode",
                    "status": "PROGRESS",
                    "completed": completed,
                    "total": 2,
                    "mode_index": index,
                }
            )
            yield entry

    monkeypatch.setattr(
        module, "iter_fullspace_dtn_functionals_from_surface", functional_iterator
    )

    class IndexMap:
        local_range = (0, 2)
        size_local = 2
        size_global = 2

        @staticmethod
        def local_to_global(rows):
            return rows

    fake_mpc = SimpleNamespace(
        slaves=np.asarray([], dtype=np.int32),
        function_space=SimpleNamespace(
            mesh=SimpleNamespace(comm=MPI.COMM_SELF),
            dofmap=SimpleNamespace(index_map=IndexMap()),
        ),
    )
    stream_path = tmp_path / "carrier_surface_functionals.bin"
    progress = []

    def committed_progress(facts):
        checkpoint = json.loads(Path(str(stream_path) + ".checkpoint.json").read_text())
        assert facts["progress_semantics"] == "durably_committed"
        assert facts["completed"] == facts["committed_mode_count"]
        assert facts["generated_mode_count"] >= facts["committed_mode_count"]
        assert checkpoint["committed_mode_count"] == facts["committed_mode_count"]
        assert checkpoint["committed_bytes"] == facts["committed_bytes"]
        assert stream_path.stat().st_size == facts["committed_bytes"]
        progress.append(dict(facts))

    carrier = build_fullspace_dtn_carrier_from_surface(
        modes,
        {},
        fake_mpc,
        SimpleNamespace(),
        persistence_path=stream_path,
        persistence_identity={
            "source_sha": "c" * 40,
            "input_sha256": "d" * 64,
            "campaign_window_sha256": "e" * 64,
        },
        progress_callback=committed_progress,
        progress_interval=1,
    )
    assert [row["committed_mode_count"] for row in progress] == [1, 2]
    assert [row["generated_mode_count"] for row in progress] == [1, 2]
    assert carrier.persistence_facts["committed_mode_count"] == 2


def test_resumable_surface_stream_reopens_appends_suffix_and_rejects_bad_prefix(
    tmp_path,
):
    import hashlib
    import json
    from types import SimpleNamespace

    import src.solvers.fullspace_dtn_action as module

    modes = tuple(
        SimpleNamespace(side="top", m=index, n=0, polarization="s")
        for index in range(3)
    )
    mode_identities = tuple(_identity(index, h) for index, h in enumerate((1.0, 1.25, 2.5)))
    normalization_h = (1.0, 1.25, 2.5)
    identity = {
        "source_sha": "a" * 40,
        "input_sha256": "b" * 64,
        "staged_input_sha256": "c" * 64,
        "campaign_window_sha256": "d" * 64,
        "surface_scope": "local",
        "twist_index": 2,
    }
    stream_path = tmp_path / "surface-functionals.bin"

    def stream_for(execution_identity=identity):
        return module._ResumableSurfaceFunctionalStream(
            stream_path,
            identity=execution_identity,
            modes=modes,
            mode_identities=mode_identities,
            normalization_h=normalization_h,
        )

    entries = (
        FullspaceDtnModeFunctional(
            mode_key=(0, "top", 0, 0, "s"),
            coupling_rows=np.asarray([], dtype=np.int32),
            coupling_values=np.asarray([], dtype=np.complex128),
            projection_rows=np.asarray([1, 4], dtype=np.int32),
            projection_values=np.asarray([1.0 + 2.0j, -3.0 + 0.25j]),
            normalization_h=1.0,
            mode_identity=mode_identities[0],
        ),
        FullspaceDtnModeFunctional(
            mode_key=(1, "top", 1, 0, "s"),
            coupling_rows=np.asarray([0, 3], dtype=np.int32),
            coupling_values=np.asarray([0.25 - 0.5j, 2.5 + 1.25j]),
            projection_rows=np.asarray([], dtype=np.int32),
            projection_values=np.asarray([], dtype=np.complex128),
            normalization_h=1.25,
            mode_identity=mode_identities[1],
        ),
        FullspaceDtnModeFunctional(
            mode_key=(2, "top", 2, 0, "s"),
            coupling_rows=np.asarray([2], dtype=np.int32),
            coupling_values=np.asarray([-1.5 + 0.75j]),
            projection_rows=np.asarray([0, 5], dtype=np.int32),
            projection_values=np.asarray([4.0 - 2.0j, 0.125 + 0.5j]),
            normalization_h=2.5,
            mode_identity=mode_identities[2],
        ),
    )

    initial = stream_for()
    assert initial.open() == ([], 0)
    initial.append(entries[0], peak_component_cache_bytes=64)

    resumed = stream_for()
    prefix, prefix_peak = resumed.open()
    assert len(prefix) == 1
    assert prefix_peak == 64
    _assert_surface_functional_equal(prefix[0], entries[0])
    resumed.append(entries[1], peak_component_cache_bytes=32)
    resumed.append(entries[2], peak_component_cache_bytes=128)

    reopened = stream_for()
    restored, restored_peak = reopened.open()
    assert len(restored) == 3
    assert restored_peak == 128
    for actual, expected in zip(restored, entries, strict=True):
        _assert_surface_functional_equal(actual, expected)

    manifest = json.loads(Path(str(stream_path) + ".manifest.json").read_text())
    checkpoint = json.loads(Path(str(stream_path) + ".checkpoint.json").read_text())
    offset_path = tmp_path / "validated-offsets.i64"
    source = module.ReadOnlySurfaceFunctionalSource(
        stream_path,
        expected_manifest_sha256=hashlib.sha256(
            Path(str(stream_path) + ".manifest.json").read_bytes()
        ).hexdigest(),
        expected_checkpoint_sha256=hashlib.sha256(
            Path(str(stream_path) + ".checkpoint.json").read_bytes()
        ).hexdigest(),
        expected_identity_sha256=manifest["identity_sha256"],
        expected_prefix_sha256=checkpoint["committed_prefix_sha256"],
        expected_mode_count=3,
        expected_committed_bytes=checkpoint["committed_bytes"],
        max_batch_modes=2,
        offset_index_path=offset_path,
        expected_mode_keys=tuple((index, "top", index, 0, "s") for index in range(3)),
        expected_normalization_h=normalization_h,
        global_rows=6,
        ownership_range=(0, 6),
    )
    persisted = source.audit["persisted_offset_index"]
    assert persisted["complete_stream_validation_preceded_persistence"] is True
    assert persisted["committed_prefix_sha256"] == checkpoint["committed_prefix_sha256"]
    assert hashlib.sha256(offset_path.read_bytes()).hexdigest() == persisted["offset_index_sha256"]
    assert np.fromfile(offset_path, dtype="<i8").tolist() == source._offsets.tolist()
    assert Path(persisted["offset_index_metadata_path"]).is_file()

    raw_before_rejection = stream_path.read_bytes()
    with pytest.raises(ValueError, match="manifest identity changed"):
        stream_for({**identity, "twist_index": 3}).open()
    assert stream_path.read_bytes() == raw_before_rejection

    stream_path.write_bytes(raw_before_rejection[:-1])
    with pytest.raises(IOError, match="outside its committed prefix"):
        stream_for().open()


def _assert_surface_functional_equal(actual, expected):
    assert actual.mode_key == expected.mode_key
    assert actual.normalization_h == expected.normalization_h
    assert actual.mode_identity == expected.mode_identity
    np.testing.assert_array_equal(actual.coupling_rows, expected.coupling_rows)
    np.testing.assert_array_equal(actual.coupling_values, expected.coupling_values)
    np.testing.assert_array_equal(actual.projection_rows, expected.projection_rows)
    np.testing.assert_array_equal(actual.projection_values, expected.projection_values)


def test_resumable_carrier_identity_retains_staged_input_and_local_twist(
    monkeypatch,
):
    from types import SimpleNamespace

    import src.solvers.fullspace_dtn_action as module
    import src.solvers.dtn_boundary_phase_gauge as gauge

    mode = SimpleNamespace(side="top", m=1, n=-1, polarization="p")
    cfg = SimpleNamespace(floquet_phase_x=0.125, floquet_phase_y=-0.25)
    assembly_context = {
        "schema": "fixture-assembly-context",
        "source_sha256": "f" * 64,
        "mesh": {"mesh_sha256": "a" * 64},
        "cell_dofmap_sha256": "b" * 64,
        "orientation": {"orientation_sha256": "c" * 64},
        "basix_coefficients": {"basix_sha256": "d" * 64},
        "MPC": {"mpc_sha256": "e" * 64},
        "config_sha256": "1" * 64,
        "gauss": {"quadrature_degree": 4},
        "ABI": {"petsc_scalar": "complex128", "petsc_int": "int32"},
    }
    execution_identity = {
        "source_sha": "2" * 40,
        "input_sha256": "3" * 64,
        "staged_input_sha256": "4" * 64,
        "campaign_window_sha256": "5" * 64,
        "surface_scope": "local",
        "twist_index": 2,
    }
    monkeypatch.setattr(gauge, "assembly_projection_denominator", lambda *_args: 1.5)
    monkeypatch.setattr(
        gauge, "phase_gauge_descriptor", lambda *_args: {"schema": "fixture-gauge"}
    )
    monkeypatch.setattr(
        module,
        "_mode_identity",
        lambda index, _mode, _cfg, h: {"mode_index": index, "projection_denominator": h},
    )

    _mode_identities, h_values, _assembly_sha, identity = (
        module._resumable_carrier_mode_identity(
            (mode,),
            cfg,
            phase_gauge=gauge.BOUNDARY_PLANE,
            assembly_context=assembly_context,
            execution_identity=execution_identity,
            mode_rows=({"projection_denominator": 1.5},),
            physical_manifest_sha256="6" * 64,
        )
    )

    assert h_values.tolist() == [1.5]
    assert identity["staged_input_sha256"] == execution_identity["staged_input_sha256"]
    assert identity["surface_scope"] == "local"
    assert identity["twist_index"] == 2
