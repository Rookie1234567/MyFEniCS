from __future__ import annotations

from dataclasses import replace
import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers import hcurl_p_split_owner_transfer as owner_transfer
from src.solvers.hcurl_canonical_vector import compare_canonical_packets
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_packets,
    iter_canonical_full_fe_owner_packets,
)
from src.solvers.hcurl_p_split_owner_transfer import (
    P4P6MPCCarrier,
    build_owner_local_p4_p6_transfer,
)


def _analytic_hcurl(x: np.ndarray) -> np.ndarray:
    return np.vstack(
        (
            1.0 + 0.2 * x[0] - 0.11 * x[2],
            -0.4 + 0.13 * x[1] + 0.07 * x[2],
            0.25 + 0.09 * x[0] - 0.17 * x[1],
        )
    ).astype(np.complex128)


def _relative_owned(observed, expected) -> float:
    observed = np.asarray(observed, dtype=np.complex128)
    expected = np.asarray(expected, dtype=np.complex128)
    return float(
        np.linalg.norm(observed - expected)
        / max(np.linalg.norm(expected), 1.0e-30)
    )


def _global_relative_owned(observed, expected, comm) -> float:
    observed = np.asarray(observed, dtype=np.complex128)
    expected = np.asarray(expected, dtype=np.complex128)
    numerator = comm.allreduce(
        float(np.vdot(observed - expected, observed - expected).real),
        op=MPI.SUM,
    )
    denominator = comm.allreduce(
        float(np.vdot(expected, expected).real),
        op=MPI.SUM,
    )
    return float(np.sqrt(numerator) / max(np.sqrt(denominator), 1.0e-30))


def _canonical_owned_signature(vector, comm) -> tuple[float, complex]:
    """Return a scalar partition-smoke signature, not a full vector identity."""
    start, stop = map(int, vector.getOwnershipRange())
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    global_ids = np.arange(start, stop, dtype=np.float64) + 1.0
    norm_squared = comm.allreduce(
        float(np.vdot(values, values).real),
        op=MPI.SUM,
    )
    weighted_sum = comm.allreduce(
        complex(np.dot(global_ids.astype(np.complex128), values)),
        op=MPI.SUM,
    )
    return float(np.sqrt(norm_squared)), complex(weighted_sum)


def _assert_local_finite(vector) -> None:
    with vector.localForm() as local:
        assert np.isfinite(np.asarray(local.array_r)).all()


def _new_mpc_vector(mpc):
    index_map = mpc.function_space.dofmap.index_map
    return create_vector([(index_map, mpc.function_space.dofmap.index_map_bs)])


def _function_to_mpc_vector(function, mpc):
    vector = _new_mpc_vector(mpc)
    owned = int(mpc.function_space.dofmap.index_map.size_local)
    with vector.localForm() as local:
        local.set(0.0)
        local.array_w[:owned] = function.x.array[:owned]
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    mpc.backsubstitution(vector)
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )
    return vector


def _spaces(comm, *, nx: int = 1):
    msh = mesh.create_unit_cube(
        comm,
        nx,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    spaces = tuple(
        fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                degree,
                dtype=default_real_type,
            ),
        )
        for degree in (4, 6)
    )
    return msh, spaces


def _small_floquet_mesh_data(comm):
    """Use test272's 2x2x2 production mesh/config without its unrelated UFL form."""

    cfg = replace(
        target_stage4_config(degree=6, h_nm=1000.0),
        incident_theta_deg=37.0,
        incident_phi_deg=23.0,
    )
    points = (
        np.asarray(
            (cfg.x_min, cfg.y_min, cfg.domain_z_min),
            dtype=np.float64,
        ),
        np.asarray(
            (cfg.x_max, cfg.y_max, cfg.domain_z_max),
            dtype=np.float64,
        ),
    )
    msh = mesh.create_box(
        comm,
        points,
        (2, 2, 2),
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    fdim = msh.topology.dim - 1
    boundary_specs = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
    )
    facet_indices = []
    facet_values = []
    for tag, marker in boundary_specs:
        facets = mesh.locate_entities_boundary(msh, fdim, marker)
        facet_indices.append(facets)
        facet_values.append(np.full(len(facets), tag, dtype=np.int32))
    facet_index = np.concatenate(facet_indices).astype(np.int32)
    facet_value = np.concatenate(facet_values).astype(np.int32)
    order = np.argsort(facet_index)
    mesh_data = SimpleNamespace(
        mesh=msh,
        facet_tags=mesh.meshtags(
            msh,
            fdim,
            facet_index[order],
            facet_value[order],
        ),
    )
    return cfg, mesh_data


def _fill_owned(vector, seed: float) -> None:
    start, stop = map(int, vector.getOwnershipRange())
    with vector.localForm() as local:
        local.set(0.0)
        ids = np.arange(start, stop, dtype=np.float64)
        local.array_w[: stop - start] = (
            np.sin(seed + 0.013 * ids)
            + 1j * np.cos(seed * 0.7 - 0.017 * ids)
        )
    vector.ghostUpdate(
        addv=PETSc.InsertMode.INSERT_VALUES,
        mode=PETSc.ScatterMode.FORWARD,
    )


def test_original_local_prefix_is_preserved_before_appended_ghosts() -> None:
    class _IndexMap:
        def __init__(self, global_ids: tuple[int, ...], owned: int) -> None:
            self._global_ids = np.asarray(global_ids, dtype=np.int64)
            self.size_local = int(owned)
            self.num_ghosts = int(len(global_ids) - owned)

        def local_to_global(self, local_ids: np.ndarray) -> np.ndarray:
            return self._global_ids[np.asarray(local_ids, dtype=np.int32)]

    def _space(global_ids: tuple[int, ...], owned: int) -> SimpleNamespace:
        return SimpleNamespace(
            dofmap=SimpleNamespace(index_map=_IndexMap(global_ids, owned))
        )

    original = _space((10, 11, 12, 90), 3)
    appended = _space((10, 11, 12, 90, 140), 3)
    shuffled = _space((10, 11, 90, 12, 140), 3)
    assert owner_transfer._original_local_prefix_preserved(original, appended)
    assert owner_transfer._original_local_prefix_preserved(original, original)
    assert not owner_transfer._original_local_prefix_preserved(original, shuffled)


def test_mpc_carrier_phase_once_and_local_adjoint() -> None:
    phase = np.exp(0.37j)
    carrier = P4P6MPCCarrier.from_relations(
        global_rows=4,
        owned_rows=3,
        local_rows=4,
        relations={
            2: (
                np.asarray([0], dtype=np.int32),
                np.asarray([phase], dtype=np.complex128),
            )
        },
    )
    x = np.asarray(
        [0.2 + 0.4j, -0.3 + 0.1j, 0.0j, 0.7 - 0.2j],
        dtype=np.complex128,
    )
    y = np.asarray(
        [-0.4 + 0.2j, 0.5 - 0.3j, 0.7 + 0.1j, -0.2 + 0.6j],
        dtype=np.complex128,
    )
    lifted = x.copy()
    carrier.lift_in_place(lifted)
    assert lifted[2] == pytest.approx(phase * x[0])
    phase_twice_value = phase**2 * x[0]
    assert abs(lifted[2] - phase_twice_value) > 1.0e-6
    restricted = y.copy()
    carrier.adjoint_in_place(restricted)
    np.testing.assert_allclose(np.vdot(lifted, y), np.vdot(x, restricted))
    assert carrier.audit["phase_coefficients_applied_once"] is True
    assert carrier.coefficients.flags.writeable is False
    assert carrier.slave_indices.flags.writeable is False
    assert carrier.audit["numeric_allgather"] is False


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial owner fixture")
def test_serial_owner_local_fullspace_apply_and_adjoint() -> None:
    _mesh, (p4_space, p6_space) = _spaces(MPI.COMM_WORLD)
    transfer = build_owner_local_p4_p6_transfer(p4_space, p6_space)
    repeat_transfer = None
    source_function = fem.Function(p4_space)
    image_function = fem.Function(p6_space)
    expected_function = fem.Function(p6_space)
    dual_function = fem.Function(p6_space)
    adjoint_function = fem.Function(p4_space)
    repeat_image_function = fem.Function(p6_space)
    repeat_adjoint_function = fem.Function(p4_space)
    source = source_function.x.petsc_vec
    image = image_function.x.petsc_vec
    expected = expected_function.x.petsc_vec
    dual = dual_function.x.petsc_vec
    adjoint = adjoint_function.x.petsc_vec
    try:
        source_function.interpolate(_analytic_hcurl)
        source_function.x.scatter_forward()
        expected_function.interpolate(_analytic_hcurl)
        expected_function.x.scatter_forward()
        _fill_owned(dual, 0.31)
        transfer.apply(source, image)
        relative_interpolation_error = _relative_owned(
            image.getArray(readonly=True), expected.getArray(readonly=True)
        )
        assert relative_interpolation_error <= 1.0e-11
        transfer.apply(source, repeat_image_function.x.petsc_vec)
        assert np.array_equal(
            image.getArray(readonly=True),
            repeat_image_function.x.petsc_vec.getArray(readonly=True),
        )
        transfer.apply_adjoint(dual, adjoint)
        transfer.apply_adjoint(
            dual,
            repeat_adjoint_function.x.petsc_vec,
        )
        lhs = complex(image.dot(dual))
        rhs = complex(source.dot(adjoint))
        relative = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1.0)
        assert relative <= 1.0e-11
        assert np.array_equal(
            adjoint.getArray(readonly=True),
            repeat_adjoint_function.x.petsc_vec.getArray(readonly=True),
        )
        for vector in (
            source,
            image,
            expected,
            dual,
            adjoint,
            repeat_image_function.x.petsc_vec,
            repeat_adjoint_function.x.petsc_vec,
        ):
            _assert_local_finite(vector)
        repeat_transfer = build_owner_local_p4_p6_transfer(
            p4_space,
            p6_space,
        )
        audit = transfer.audit
        assert audit["reference_transform_sha256"] == repeat_transfer.audit[
            "reference_transform_sha256"
        ]
        assert audit["reference_hcurl_expansion_sha256"] == repeat_transfer.audit[
            "reference_hcurl_expansion_sha256"
        ]
        assert audit["p4_global_rows"] == int(p4_space.dofmap.index_map.size_global)
        assert audit["p6_global_rows"] == int(p6_space.dofmap.index_map.size_global)
        assert audit["missing_owned_p6_rows"] == 0
        assert audit["extra_owned_p6_rows"] == 0
        assert audit["duplicate_owned_p6_designations"] == 0
        assert audit["global_owner_designation_complete"] is True
        components = audit["retained_numeric_payload_components"]
        assert audit["retained_numeric_payload_bytes"] == sum(
            components.values()
        )
        for component in (
            "p4_reference_hcurl_to_p6_bytes",
            "p4_reference_h1_to_q6_bytes",
            "p4_reference_discrete_gradient_bytes",
            "p4_reference_trace_dofs_bytes",
            "p4_reference_interior_dofs_bytes",
            "p6_reference_hcurl_to_p6_bytes",
            "p6_reference_h1_to_q6_bytes",
            "p6_reference_discrete_gradient_bytes",
            "p6_reference_trace_dofs_bytes",
            "p6_reference_interior_dofs_bytes",
        ):
            assert component in components
        assert audit["retained_transfer_numeric_payload_bytes"] == (
            audit["retained_numeric_payload_bytes"]
            + audit["lazy_p6_work_vec_bytes"]
        )
        assert audit["retained_transfer_numeric_payload_gate"] is True
        assert audit["lazy_p6_work_vec_allocated_at_build"] is False
        assert audit["construction_transient_numeric_payload_bytes"] is None
        assert audit["measured_process_tree_rss_bytes"] is None
        assert audit["structural_build_pass"] is True
        assert audit["measurement_qualification"] == "not_run"
        assert audit["m1_gate_pass"] is False
        assert audit["p4_mpc_original_prefix_preserved"] is True
        assert audit["p6_mpc_original_prefix_preserved"] is True
        assert audit["bounded_apply_workspace_gate"] is True
        assert audit["global_transfer_matrix_materialized"] is False
        assert audit["global_matrix_materialized"] is False
        assert audit["global_constraint_matrix_materialized"] is False
        assert audit["condensed_path"] is False
        assert audit["trace_only_path"] is False
        assert audit["ordinary_default_changed"] is False
        assert audit["owned_cell_count_local"] == 1
        assert audit["designating_cell_count_local"] == 1
        assert audit["orientation_cell_count_global"] == 1
        assert audit["orientation_nonzero_cell_count_global"] >= 0
    finally:
        transfer.destroy()
        if repeat_transfer is not None:
            repeat_transfer.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="M1 MPI2 owner fixture")
def test_mpi2_owner_transfer_is_partition_independent() -> None:
    _mesh, (p4_space, p6_space) = _spaces(MPI.COMM_WORLD, nx=2)
    transfer = build_owner_local_p4_p6_transfer(p4_space, p6_space)
    repeat_transfer = build_owner_local_p4_p6_transfer(p4_space, p6_space)
    source_function = fem.Function(p4_space)
    image_function = fem.Function(p6_space)
    expected_function = fem.Function(p6_space)
    dual_function = fem.Function(p6_space)
    adjoint_function = fem.Function(p4_space)
    repeat_image_function = fem.Function(p6_space)
    repeat_adjoint_function = fem.Function(p4_space)
    source = source_function.x.petsc_vec
    image = image_function.x.petsc_vec
    expected = expected_function.x.petsc_vec
    dual = dual_function.x.petsc_vec
    adjoint = adjoint_function.x.petsc_vec
    try:
        source_function.interpolate(_analytic_hcurl)
        source_function.x.scatter_forward()
        expected_function.interpolate(_analytic_hcurl)
        expected_function.x.scatter_forward()
        _fill_owned(dual, 0.31)
        transfer.apply(source, image)
        transfer.apply_adjoint(dual, adjoint)
        transfer.apply(source, repeat_image_function.x.petsc_vec)
        transfer.apply_adjoint(
            dual,
            repeat_adjoint_function.x.petsc_vec,
        )
        lhs = complex(image.dot(dual))
        rhs = complex(source.dot(adjoint))
        relative = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1.0)
        assert relative <= 1.0e-11
        assert _global_relative_owned(
            image.getArray(readonly=True),
            expected.getArray(readonly=True),
            MPI.COMM_WORLD,
        ) <= 1.0e-11
        assert np.array_equal(
            image.getArray(readonly=True),
            repeat_image_function.x.petsc_vec.getArray(readonly=True),
        )
        assert np.array_equal(
            adjoint.getArray(readonly=True),
            repeat_adjoint_function.x.petsc_vec.getArray(readonly=True),
        )
        for vector in (
            source,
            image,
            expected,
            dual,
            adjoint,
            repeat_image_function.x.petsc_vec,
            repeat_adjoint_function.x.petsc_vec,
        ):
            _assert_local_finite(vector)
        image_signature = _canonical_owned_signature(image, MPI.COMM_WORLD)
        repeat_image_signature = _canonical_owned_signature(
            repeat_image_function.x.petsc_vec,
            MPI.COMM_WORLD,
        )
        adjoint_signature = _canonical_owned_signature(
            adjoint,
            MPI.COMM_WORLD,
        )
        repeat_adjoint_signature = _canonical_owned_signature(
            repeat_adjoint_function.x.petsc_vec,
            MPI.COMM_WORLD,
        )
        assert image_signature == repeat_image_signature
        assert adjoint_signature == repeat_adjoint_signature
        audit = transfer.audit
        assert audit["mpi_size"] == 2
        assert audit["global_owner_designation_complete"] is True
        assert audit["global_owner_designation_duplicate_count"] == 0
        hashes = MPI.COMM_WORLD.allgather(
            audit["global_ownership_binding_sha256"]
        )
        assert len(set(hashes)) == 1
        assert audit["metadata_row_designation_allgather"] is True
        assert audit["numeric_allgather"] is False
        assert audit["reference_transform_sha256"] == repeat_transfer.audit[
            "reference_transform_sha256"
        ]
        assert len(
            set(
                MPI.COMM_WORLD.allgather(
                    audit["reference_transform_sha256"]
                )
            )
        ) == 1
    finally:
        transfer.destroy()
        repeat_transfer.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="M1 Floquet owner fixture is qualified for MPI1/MPI2",
)
def test_real_floquet_mpc_owner_transfer_phase_and_orientation() -> None:
    cfg, mesh_data = _small_floquet_mesh_data(MPI.COMM_WORLD)
    p6_space = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    floquet6 = build_double_floquet_mpc(p6_space, mesh_data, cfg)
    p4_space = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            4,
            dtype=default_real_type,
        ),
    )
    floquet4 = build_double_floquet_mpc(
        p4_space,
        mesh_data,
        replace(cfg, nedelec_degree=4),
    )
    transfer = build_owner_local_p4_p6_transfer(
        p4_space,
        p6_space,
        p4_mpc=floquet4.mpc,
        p6_mpc=floquet6.mpc,
    )
    source_function = fem.Function(p4_space)
    dual_function = fem.Function(p6_space)
    source_function.interpolate(_analytic_hcurl)
    source_function.x.scatter_forward()
    dual_function.interpolate(_analytic_hcurl)
    dual_function.x.scatter_forward()
    source = _function_to_mpc_vector(source_function, floquet4.mpc)
    image = _new_mpc_vector(floquet6.mpc)
    dual = _function_to_mpc_vector(dual_function, floquet6.mpc)
    adjoint = _new_mpc_vector(floquet4.mpc)
    repeat_image = _new_mpc_vector(floquet6.mpc)
    repeat_adjoint = _new_mpc_vector(floquet4.mpc)
    owned_vectors = (source, image, dual, adjoint, repeat_image, repeat_adjoint)
    try:
        transfer.apply(source, image)
        transfer.apply_adjoint(dual, adjoint)
        transfer.apply(source, repeat_image)
        transfer.apply_adjoint(dual, repeat_adjoint)
        lhs = complex(image.dot(dual))
        rhs = complex(source.dot(adjoint))
        relative = abs(lhs - rhs) / max(abs(lhs), abs(rhs), 1.0)
        assert relative <= 1.0e-11
        assert np.array_equal(
            image.getArray(readonly=True),
            repeat_image.getArray(readonly=True),
        )
        assert np.array_equal(
            adjoint.getArray(readonly=True),
            repeat_adjoint.getArray(readonly=True),
        )
        _assert_local_finite(image)
        _assert_local_finite(adjoint)
        assert floquet4.num_edge_constraints > 0
        assert floquet4.num_face_constraints > 0
        assert floquet6.num_edge_constraints > 0
        assert floquet6.num_face_constraints > 0
        assert transfer.audit["p4_owned_constraint_count_global"] == (
            floquet4.num_constraints
        )
        assert transfer.audit["p6_owned_constraint_count_global"] == (
            floquet6.num_constraints
        )
        for prefix in ("p4", "p6"):
            assert transfer.audit[f"{prefix}_mpc_extended_local_rows"] >= transfer.audit[
                f"{prefix}_original_local_rows"
            ]
            assert transfer.audit[f"{prefix}_mpc_extended_ghost_rows"] >= transfer.audit[
                f"{prefix}_original_ghost_rows"
            ]
            assert transfer.audit[f"{prefix}_mpc_added_master_ghost_rows"] <= transfer.audit[
                f"{prefix}_mpc_extended_ghost_rows"
            ]
            assert transfer.audit[f"{prefix}_mpc_extended_local_work_bytes"] == (
                transfer.audit[f"{prefix}_mpc_extended_local_rows"] * np.dtype(np.complex128).itemsize
            )
        assert abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-8
        assert abs(complex(cfg.floquet_phase_y) - 1.0) > 1.0e-8
        assert np.max(np.abs(transfer.p4_constraints.coefficients - 1.0)) > 1.0e-8
        assert np.max(np.abs(transfer.p6_constraints.coefficients - 1.0)) > 1.0e-8
        phase_once = complex(cfg.floquet_phase_x)
        phase_twice = phase_once * phase_once
        assert abs(phase_twice - phase_once) > 1.0e-6
        assert transfer.audit["p4_mpc_phase_applied_once"] is True
        assert transfer.audit["p6_mpc_phase_applied_once"] is True
        topology = mesh_data.mesh.topology
        topology.create_entity_permutations()
        cell_count = int(topology.index_map(3).size_local)
        cell_info = np.asarray(
            topology.get_cell_permutation_info(),
            dtype=np.uint32,
        )[:cell_count]
        assert MPI.COMM_WORLD.allreduce(
            bool(np.any(cell_info != 0)),
            op=MPI.LOR,
        )
        assert transfer.audit["orientation_cell_count_global"] >= cell_count
        assert transfer.audit["orientation_metadata_sha256"]
    finally:
        transfer.destroy()
        for vector in owned_vectors:
            vector.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="owner-local canonical equivalence is qualified for MPI1/MPI2",
)
def test_owner_canonical_iterator_matches_reference_extractor() -> None:
    cfg, mesh_data = _small_floquet_mesh_data(MPI.COMM_WORLD)
    p6_space = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    floquet6 = build_double_floquet_mpc(p6_space, mesh_data, cfg)
    function = fem.Function(p6_space)
    function.interpolate(_analytic_hcurl)
    function.x.scatter_forward()
    vector = _function_to_mpc_vector(function, floquet6.mpc)
    try:
        owner_packets = tuple(
            iter_canonical_full_fe_owner_packets(
                p6_space, floquet6.mpc, vector, floquet6
            )
        )
        reference_packets, _audit = extract_canonical_full_fe_packets(
            p6_space, vector, floquet6
        )
        comparison = compare_canonical_packets(
            owner_packets,
            reference_packets,
            relative_tolerance=1.0e-12,
        )
        assert comparison["duplicate_left_count"] == 0
        assert comparison["duplicate_right_count"] == 0
        assert comparison["missing_key_count"] == 0
        assert comparison["extra_key_count"] == 0
        assert comparison["relative_coefficient_l2"] <= 1.0e-12
    finally:
        vector.destroy()


def test_owner_transfer_has_no_forbidden_materialization_path() -> None:
    source = inspect.getsource(owner_transfer)
    assert "PETSc.Mat" not in source
    assert "build_variable_p_global_transfer" not in source
    assert "CondensedGalerkinCoarse" not in source
    assert "global_transfer_matrix_materialized" in source
    assert "replicated_global_numeric_vector" in source
