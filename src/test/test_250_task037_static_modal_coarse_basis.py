import numpy as np
import pytest
import ufl
from basix.ufl import element, mixed_element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.coupling.hybrid_internal_modes import _DistributedTwoDimensionalEvaluator
from src.geometry.tetra_mesh_audit import mesh_coordinate_tolerance
from src.modes.stable_propagation import (
    DirectionalPropagationBlock,
    TwoSidedPropagation,
)
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.static_modal_coarse_basis import (
    OwnerLocalBasis,
    audit_owner_local_action_space,
    build_middle_modal_active_column,
    normalize_owner_local_columns,
    solve_homogeneous_prescribed_interface,
)
from src.solvers.hcurl_canonical_vector_dolfinx import (
    extract_canonical_active_trace_packets,
)


def _aij(values: np.ndarray) -> PETSc.Mat:
    values = np.asarray(values, dtype=PETSc.ScalarType)
    rows, columns = values.shape
    matrix = PETSc.Mat().createAIJ(
        size=(rows, columns),
        nnz=columns,
        comm=MPI.COMM_SELF,
    )
    matrix.setUp()
    matrix.setValues(
        np.arange(rows, dtype=PETSc.IntType),
        np.arange(columns, dtype=PETSc.IntType),
        values,
    )
    matrix.assemble()
    return matrix


def test_research_opt_in_normalization_and_owner_local_action_identity():
    local = np.asarray(
        [
            [1.0 + 1.0j, 0.0, 1.0],
            [1.0 + 1.0j, 0.0, 0.0],
            [0.0, 2.0 - 2.0j, 0.0],
            [0.0, 0.0, 1.0j],
        ],
        dtype=np.complex128,
    )
    with pytest.raises(ValueError, match="research-only"):
        OwnerLocalBasis.from_local_array(
            local,
            global_rows=4,
            comm=MPI.COMM_SELF,
            label="Z",
        )
    basis = OwnerLocalBasis.from_local_array(
        local,
        global_rows=4,
        comm=MPI.COMM_SELF,
        label="Z",
        research_opt_in=True,
    )
    normalized, audits = normalize_owner_local_columns(
        basis,
        research_opt_in=True,
    )
    operator = _aij(
        np.asarray(
            [
                [2.0 + 0.1j, 0.2 - 0.1j, 0.0, 0.0],
                [0.0, 1.5 - 0.2j, 0.3, 0.0],
                [0.1, 0.0, 1.2 + 0.3j, 0.2j],
                [0.0, 0.0, 0.4, 0.8 - 0.1j],
            ]
        )
    )
    action = normalized.apply(operator, research_opt_in=True)
    rng = np.random.default_rng(17037)
    coefficient = rng.standard_normal(3) + 1j * rng.standard_normal(3)
    source = normalized.combine(coefficient, research_opt_in=True)
    observed = action.combine(coefficient, research_opt_in=True)
    expected = operator.createVecLeft()
    difference = expected.duplicate()
    try:
        operator.mult(source, expected)
        expected.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), observed)
        assert difference.norm() <= 1.0e-13
        assert audits[0].pivot_global_row == 0
        assert all(abs(audit.norm_after - 1.0) <= 1.0e-13 for audit in audits)
        for vector, audit in zip(normalized.columns, audits, strict=True):
            values = vector.getArray(readonly=True)
            pivot = values[audit.pivot_global_row]
            assert pivot.real >= -1.0e-14
            assert abs(pivot.imag) <= 1.0e-14
            assert normalized.ownership_range == (0, 4)
        assert normalized.local_matrix().shape == (4, 3)
        action_audit = audit_owner_local_action_space(
            action,
            research_opt_in=True,
        )
        assert action_audit.effective_rank == 3
        assert np.isfinite(action_audit.retained_condition_number)
        assert action_audit.normal_equations_used is False
    finally:
        difference.destroy()
        expected.destroy()
        observed.destroy()
        source.destroy()
        action.destroy()
        operator.destroy()
        normalized.destroy()
        basis.destroy()


def test_stacked_r_svd_reports_known_rank_without_normal_equations():
    basis = OwnerLocalBasis.from_local_array(
        np.asarray(
            [
                [1.0, 0.0, 1.0],
                [0.0, 1.0, 1.0],
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
            ]
        ),
        global_rows=4,
        comm=MPI.COMM_SELF,
        label="Y",
        research_opt_in=True,
    )
    try:
        audit = audit_owner_local_action_space(
            basis,
            rank_tolerance=1.0e-12,
            research_opt_in=True,
        )
        assert audit.effective_rank == 2
        assert np.isfinite(audit.retained_condition_number)
        assert audit.retained_condition_number == pytest.approx(np.sqrt(3.0))
        assert audit.local_qr_method == "scipy.linalg.qr"
        assert audit.stacked_r_svd_method.endswith("scipy.linalg.svd")
        assert audit.normal_equations_used is False
        assert len(audit.singular_values) == 3
    finally:
        basis.destroy()


class _FixtureFactor:
    def __init__(self, matrix: np.ndarray):
        self.matrix = matrix
        self.destroyed = False

    def solve(self, rhs: np.ndarray) -> np.ndarray:
        return np.linalg.solve(self.matrix, rhs)

    def destroy(self) -> None:
        self.destroyed = True


def test_prescribed_interface_partition_solves_retained_rows_and_releases_factor():
    matrix = np.asarray(
        [
            [2.0 + 0.2j, 0.3, 1.0 - 0.5j],
            [0.1, 1.5 - 0.1j, -0.4j],
            [0.7 + 0.2j, 0.4, 2.0 + 0.3j],
        ],
        dtype=np.complex128,
    )
    factor_box: list[_FixtureFactor] = []

    def make_factor(retained_matrix: np.ndarray) -> _FixtureFactor:
        factor = _FixtureFactor(retained_matrix)
        factor_box.append(factor)
        return factor

    result = solve_homogeneous_prescribed_interface(
        matrix,
        interface_rows=(2,),
        interface_values=(1.0 - 2.0j,),
        factor_factory=make_factor,
        research_opt_in=True,
    )
    assert result.interface_rows == (2,)
    assert result.retained_rows == (0, 1)
    assert result.factor_released is True
    assert factor_box[0].destroyed is True
    assert result.values[2] == 1.0 - 2.0j
    assert result.retained_residual_norm <= 1.0e-12
    assert result.retained_residual_relative <= 1.0e-12


def test_comm_world_owner_local_collective_semantics():
    comm = MPI.COMM_WORLD
    local_rows = 2
    global_rows = local_rows * comm.size
    local = np.zeros((local_rows, 2), dtype=np.complex128)
    local[0, 1] = 1.0 + 0.0j
    if comm.rank == 0:
        local[0, 0] = 1.0 + 1.0j
    if comm.rank == comm.size - 1:
        local[-1, 0] = 1.0 + 1.0j
    basis = OwnerLocalBasis.from_local_array(
        local,
        global_rows=global_rows,
        comm=comm,
        label="Z_mpi",
        research_opt_in=True,
    )
    normalized, audits = normalize_owner_local_columns(
        basis,
        research_opt_in=True,
    )
    operator = PETSc.Mat().createAIJ(
        size=(global_rows, global_rows),
        nnz=1,
        comm=comm,
    )
    operator.setUp()
    first, last = map(int, operator.getOwnershipRange())
    for row in range(first, last):
        operator.setValue(row, row, PETSc.ScalarType(1.0 + 0.25j))
    operator.assemble()
    action = normalized.apply(operator, research_opt_in=True)
    coefficients = np.asarray(
        [0.25 - 0.5j, -0.75 + 0.125j],
        dtype=np.complex128,
    )
    source = normalized.combine(coefficients, research_opt_in=True)
    observed = action.combine(coefficients, research_opt_in=True)
    expected = operator.createVecLeft()
    difference = expected.duplicate()
    try:
        operator.mult(source, expected)
        expected.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), observed)
        assert difference.norm() <= 1.0e-13
        assert audits[0].pivot_global_row == 0
        assert all(abs(audit.norm_after - 1.0) <= 1.0e-13 for audit in audits)
        pivot_values = []
        first, last = map(int, normalized.columns[0].getOwnershipRange())
        values = normalized.columns[0].getArray(readonly=True)
        for row in (0, global_rows - 1):
            pivot_values.append(
                complex(values[row - first]) if first <= row < last else None
            )
        gathered = comm.allgather(pivot_values)
        owned_pivots = [
            value for packet in gathered for value in packet if value is not None
        ]
        assert len(owned_pivots) == 2
        assert abs(owned_pivots[0].imag) <= 1.0e-14
        assert owned_pivots[0].real > 0.0
        audit = audit_owner_local_action_space(
            action,
            research_opt_in=True,
        )
        assert audit.effective_rank == 2
        assert np.isfinite(audit.retained_condition_number)
        assert comm.allreduce(audit.effective_rank, op=MPI.MIN) == 2
        assert comm.allreduce(audit.effective_rank, op=MPI.MAX) == 2
    finally:
        difference.destroy()
        expected.destroy()
        observed.destroy()
        source.destroy()
        action.destroy()
        operator.destroy()
        normalized.destroy()
        basis.destroy()


def _middle_modal_fixture():
    target_mesh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        1,
        1,
        4,
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = target_mesh.topology.dim
    owned_cells = int(target_mesh.topology.index_map(tdim).size_local)
    cell_tags = mesh.meshtags(
        target_mesh,
        tdim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    target_space = fem.functionspace(
        target_mesh,
        element(
            "N1curl",
            target_mesh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    u = ufl.TrialFunction(target_space)
    v = ufl.TestFunction(target_space)
    dx = ufl.Measure("dx", domain=target_mesh, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.0 - 0.1j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        target_space,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
    )
    source_mesh = mesh.create_unit_square(
        MPI.COMM_SELF,
        2,
        2,
        cell_type=mesh.CellType.quadrilateral,
    )
    mixed_space = fem.functionspace(
        source_mesh,
        mixed_element(
            [
                element(
                    "N1curl",
                    source_mesh.basix_cell(),
                    1,
                    dtype=default_real_type,
                ),
                element(
                    "Lagrange",
                    source_mesh.basix_cell(),
                    1,
                    dtype=default_real_type,
                ),
            ]
        ),
    )
    transverse_space, transverse_to_mixed = mixed_space.sub(0).collapse()
    longitudinal_space, longitudinal_to_mixed = mixed_space.sub(1).collapse()
    transverse = fem.Function(transverse_space)
    transverse.interpolate(
        lambda x: np.vstack(
            (
                1.0 + 0.0 * x[0],
                2.0 + 0.0 * x[0],
            )
        )
    )
    longitudinal = fem.Function(longitudinal_space)
    longitudinal.interpolate(lambda x: 3.0 + 0.0 * x[0])
    source = fem.Function(mixed_space)
    source.x.array[np.asarray(transverse_to_mixed, dtype=np.int32)] = transverse.x.array
    source.x.array[np.asarray(longitudinal_to_mixed, dtype=np.int32)] = (
        longitudinal.x.array
    )
    source.x.scatter_forward()
    evaluator = _DistributedTwoDimensionalEvaluator(
        source,
        padding=1.0e-12,
        components=(transverse, longitudinal),
    )
    evaluator.set_source(source, components=(transverse, longitudinal))
    length = 0.5
    effective_beta = 2.0 + 0.25j

    def make_propagation(beta: complex) -> TwoSidedPropagation:
        def make_block(direction: str) -> DirectionalPropagationBlock:
            travel_factor = (
                np.exp(1j * beta * length)
                if direction == "forward"
                else np.exp(-1j * beta * length)
            )
            return DirectionalPropagationBlock(
                direction=direction,
                length_nm=length,
                source_indices=(0,),
                beta_per_nm=(17.0 + 0.5j,),
                effective_beta_per_nm=(beta,),
                propagation_model="continuous_beta",
                factors=(complex(travel_factor),),
                log_magnitudes=(float(np.log(abs(travel_factor))),),
                phase_advances_rad=(float(np.angle(travel_factor)),),
                phase_corrections_rad=(0.0,),
                log_magnitude_corrections=(0.0,),
                roundoff_growth_clipped=(False,),
            )

        return TwoSidedPropagation(
            length_nm=length,
            forward=make_block("forward"),
            backward=make_block("backward"),
        )

    propagation = make_propagation(effective_beta)
    reference_propagation = make_propagation(0.0 + 0.0j)
    return (
        target_space,
        condensed,
        evaluator,
        source,
        propagation,
        reference_propagation,
        effective_beta,
    )


def test_middle_modal_column_uses_pointwise_effective_beta_and_zero_endcaps():
    (
        target_space,
        condensed,
        evaluator,
        _source,
        propagation,
        reference_propagation,
        effective_beta,
    ) = _middle_modal_fixture()
    bottom = 1.0 / 4.0
    top = 3.0 / 4.0
    tolerance = mesh_coordinate_tolerance(target_space.mesh)
    try:
        for direction in ("forward", "backward"):
            active, audit = build_middle_modal_active_column(
                condensed,
                target_space,
                None,
                evaluator,
                propagation,
                mode_index=0,
                direction=direction,
                bottom_z_nm=bottom,
                top_z_nm=top,
                research_opt_in=True,
            )
            reference, reference_audit = build_middle_modal_active_column(
                condensed,
                target_space,
                None,
                evaluator,
                reference_propagation,
                mode_index=0,
                direction=direction,
                bottom_z_nm=bottom,
                top_z_nm=top,
                research_opt_in=True,
            )
            repeat, repeat_audit = build_middle_modal_active_column(
                condensed,
                target_space,
                None,
                evaluator,
                propagation,
                mode_index=0,
                direction=direction,
                bottom_z_nm=bottom,
                top_z_nm=top,
                research_opt_in=True,
            )
            difference = active.copy()
            difference.axpy(PETSc.ScalarType(-1.0), repeat)
            repeat_error = difference.norm() / max(active.norm(), 1.0e-30)
            assert repeat_error <= 1.0e-12
            assert repeat_audit["global_nonzero_active_rows"] > 0
            assert audit["global_nonzero_active_rows"] > 0
            assert reference_audit["global_nonzero_active_rows"] > 0
            assert (
                audit["owned_active_rows_expected"]
                == audit["owned_active_rows_written"]
            )
            observed_packets, _observed_audit = extract_canonical_active_trace_packets(
                condensed,
                target_space,
                None,
                active,
            )
            reference_packets, _reference_packet_audit = (
                extract_canonical_active_trace_packets(
                    condensed,
                    target_space,
                    None,
                    reference,
                )
            )
            observed_by_key = dict(observed_packets)
            reference_by_key = dict(reference_packets)
            for plane in (bottom, 0.5, top):
                plane_key = int(round(plane / tolerance))
                candidates = [
                    key
                    for key, value in reference_packets
                    if abs(value) > 1.0e-12
                    and all(abs(point[2] - plane_key) <= 10 for point in key[2])
                ]
                assert candidates, f"no nonzero reference packet on z={plane}"
                reference_z = bottom if direction == "forward" else top
                expected_ratio = np.exp(1j * effective_beta * (plane - reference_z))
                for key in candidates:
                    assert key in observed_by_key
                    assert key in reference_by_key
                    ratio = observed_by_key[key] / reference_by_key[key]
                    assert abs(ratio - expected_ratio) <= 1.0e-11

            bottom_key = int(round(bottom / tolerance))
            top_key = int(round(top / tolerance))
            endcap_values = [
                abs(value)
                for key, value in observed_packets
                if (
                    (
                        max(point[2] for point in key[2]) <= bottom_key + 10
                        and min(point[2] for point in key[2]) < bottom_key - 10
                    )
                    or (
                        min(point[2] for point in key[2]) >= top_key - 10
                        and max(point[2] for point in key[2]) > top_key + 10
                    )
                )
            ]
            assert endcap_values
            assert max(endcap_values) <= 1.0e-12
            difference.destroy()
            repeat.destroy()
            reference.destroy()
            active.destroy()
    finally:
        condensed.destroy()
