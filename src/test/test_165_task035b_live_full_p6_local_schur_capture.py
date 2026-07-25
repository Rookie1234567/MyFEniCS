"""Live standard-p6 local Schur capture beside the fixed-trace operator."""

from __future__ import annotations

from inspect import signature

import basix
import numpy as np
import pytest
from basix.ufl import wrap_element
from dolfinx import fem, mesh
from mpi4py import MPI

from src.adaptivity.hcurl_regionwise_p import (
    fixed_trace_hcurl_ufl_element,
)
from src.adaptivity.physical_missing_p6_action_only_complement import (
    FullP6LocalSchurClassCollector,
)
from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorSpec,
)
from src.solvers.hcurl_assembly_time_condensation import (
    _capture_full_p6_storage_local_schur_classes,
    _qualified_trace_orientation_block,
    build_unconstrained_assembly_time_condensation,
)


def _one_cell_mesh_and_tags():
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.asarray([0], dtype=np.int32),
        np.asarray([1], dtype=np.int32),
    )
    return msh, tags


def _tensor_spec() -> AffineIsotropicMaxwellTensorSpec:
    return AffineIsotropicMaxwellTensorSpec(
        curl_coefficient=1.3 - 0.1j,
        mass_coefficient_by_tag={1: -2.1 + 0.3j},
    )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial contract; MPI2 has a dedicated collective test",
)
def test_live_capture_is_explicit_opt_in_and_wrong_space_fails_closed() -> None:
    parameter = signature(
        build_unconstrained_assembly_time_condensation
    ).parameters["full_p6_storage_local_schur_observer"]
    assert parameter.default is None

    collector = FullP6LocalSchurClassCollector()
    try:
        _capture_full_p6_storage_local_schur_classes(
            communicator=MPI.COMM_SELF,
            observer=collector,
            cell_raw_metadata=[],
            cell_permutations=np.empty(0, dtype=np.uint32),
            retained_trace_dimension=299,
            retained_interior_dimension=450,
            affine_isotropic_tensor_spec=_tensor_spec(),
        )
    except RuntimeError as error:
        assert "p5-trace/p6-interior" in str(error)
    else:
        raise AssertionError("wrong retained trace dimension was accepted")


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial Basix/DOLFINx signature regression",
)
def test_standard_p6_nonzero_cell_permutations_are_safe_and_exact() -> None:
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        3,
        2,
        4,
        cell_type=mesh.CellType.hexahedron,
    )
    msh.topology.create_entity_permutations()
    permutations = np.unique(
        msh.topology.get_cell_permutation_info()
    )
    assert len(permutations) >= 5
    full_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    interior = np.asarray(
        full_element.entity_dofs[3][0],
        dtype=np.int32,
    )
    trace = np.setdiff1d(
        np.arange(full_element.dim, dtype=np.int32),
        interior,
        assume_unique=True,
    )
    for permutation in permutations:
        transform, audit = _qualified_trace_orientation_block(
            full_element,
            trace_positions=trace,
            interior_positions=interior,
            cell_info=int(permutation),
        )
        assert transform.shape == (432, 432)
        assert audit["block_diagonal_trace_interior_proven"] is True
        assert audit["interior_from_trace_max_abs"] == 0.0
        assert audit["trace_from_interior_max_abs"] == 0.0
        assert audit["interior_identity_max_abs"] == 0.0


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial numerical identity; MPI2 has a collective test",
)
def test_live_capture_matches_standard_p6_one_cell_schur_exactly() -> None:
    msh, tags = _one_cell_mesh_and_tags()
    retained_space = fem.functionspace(
        msh,
        fixed_trace_hcurl_ufl_element(5, 6),
    )
    collector = FullP6LocalSchurClassCollector()
    captured = build_unconstrained_assembly_time_condensation(
        None,
        retained_space,
        tags,
        affine_isotropic_tensor_spec=_tensor_spec(),
        full_p6_storage_local_schur_observer=collector,
    )
    audit = captured.build_audit[
        "full_p6_storage_local_schur_capture"
    ]
    assert audit["pass"] is True
    assert audit["evidence_class"] == "live_core_capture"
    assert audit["storage_trace_dimension"] == 432
    assert audit["cell_interior_dimension"] == 450
    assert audit["retained_trace_dimension"] == 300
    assert audit["retained_interior_dimension"] == 450
    assert audit["owned_cell_count_global"] == 1
    assert audit["oriented_class_count_sum"] == 1
    assert audit["observer_payload_recomputed_and_matched"] is True
    assert audit["full_p6_function_space_created"] is False
    assert audit["full_p6_global_vector_created"] is False
    assert audit["full_p6_trace_matrix_materialized"] is False
    assert audit["inactive_missing_p6_rows_allocated"] == 0
    assert audit["ordinary_default_changed"] is False

    full_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    full_space = fem.functionspace(msh, wrap_element(full_element))
    standard = build_unconstrained_assembly_time_condensation(
        None,
        full_space,
        tags,
        affine_isotropic_tensor_spec=_tensor_spec(),
    )
    observed_classes = dict(collector.schur_by_class)
    assert len(observed_classes) == 1
    observed = next(iter(observed_classes.values()))
    rows = np.arange(432, dtype=np.int32)
    standard_values = np.asarray(
        standard.matrix.getValues(rows, rows),
        dtype=np.complex128,
    )
    relative_error = float(
        np.linalg.norm(observed - standard_values)
        / max(np.linalg.norm(standard_values), 1.0e-30)
    )
    assert relative_error < 2.0e-12
    assert captured.matrix.getSize() == (300, 300)
    assert standard.matrix.getSize() == (432, 432)

    standard.destroy()
    captured.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="run with mpiexec -n 2",
)
def test_mpi2_capture_is_bound_to_the_world_communicator() -> None:
    comm = MPI.COMM_WORLD
    collector = FullP6LocalSchurClassCollector()
    owns_cell = comm.rank == 0
    audit = _capture_full_p6_storage_local_schur_classes(
        communicator=comm,
        observer=collector,
        cell_raw_metadata=(
            [((1, 1.0, 1.0, 1.0), "high", ("high", 1))]
            if owns_cell
            else []
        ),
        cell_permutations=(
            np.asarray([0], dtype=np.uint32)
            if owns_cell
            else np.empty(0, dtype=np.uint32)
        ),
        retained_trace_dimension=300,
        retained_interior_dimension=450,
        affine_isotropic_tensor_spec=_tensor_spec(),
    )
    assert audit["owned_cell_count_global"] == 1
    assert audit["oriented_class_count_sum"] == 1
    assert audit["communicator_size"] == 2
    assert audit["communicator_ordered_world_ranks"] == [0, 1]
    assert len(set(comm.allgather(audit["collective_content_sha256"]))) == 1
    assert audit["owned_cell_count_local"] == int(owns_cell)
    assert len(collector.cell_class_keys) == int(owns_cell)
