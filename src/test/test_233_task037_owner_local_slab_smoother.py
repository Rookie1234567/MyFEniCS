from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_slab_two_level import (
    DistributedPhysicalSlabSmoother,
    build_owner_local_slab_plan,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture


class _NoMatrixCondensedView:
    """Test-only view that fails if the candidate asks for a global matrix."""

    def __init__(self, system):
        self._system = system

    @property
    def matrix(self):
        raise AssertionError("owner-local smoother must not access condensed.matrix")

    def __getattr__(self, name):
        return getattr(self._system, name)


def _full_subdomains(plan):
    comm = plan.comm
    local = [
        rows.tolist() if owner == comm.rank else None
        for owner, rows in zip(plan.slab_owners, plan.owner_rows, strict=True)
    ]
    packets = comm.allgather(local)
    result = []
    for slab in range(len(plan.slab_owners)):
        rows = next(packet[slab] for packet in packets if packet[slab] is not None)
        result.append(np.asarray(rows, dtype=PETSc.IntType))
    return tuple(result)


def _set_probe(vector: PETSc.Vec, phase: float) -> None:
    start, end = vector.getOwnershipRange()
    indices = np.arange(start, end, dtype=np.float64)
    vector.getArray()[:] = np.sin(0.13 * indices + phase) + 1j * np.cos(
        0.09 * indices - phase
    )
    vector.assemble()


def _apply(smoother, source: PETSc.Vec) -> PETSc.Vec:
    target = source.duplicate()
    smoother.solve(source, target)
    return target


def _compare_vectors(left: PETSc.Vec, right: PETSc.Vec, comm) -> tuple[float, float]:
    difference = left.copy()
    difference.axpy(PETSc.ScalarType(-1.0), right)
    local_values = difference.getArray(readonly=True)
    local_max = float(np.max(np.abs(local_values))) if local_values.size else 0.0
    max_error = float(comm.allreduce(local_max, op=MPI.MAX))
    relative_error = float(difference.norm()) / max(float(right.norm()), 1.0e-30)
    difference.destroy()
    return max_error, relative_error


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2, 4),
    reason="M2b owner-local qualification uses serial/MPI2/MPI4",
)
def test_owner_local_factor_only_smoother_matches_assembled_oracle():
    comm = MPI.COMM_WORLD
    mesh, cell_tags, function_space, compiled = _build_fixture(comm)
    assembled = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
    )
    action_system = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    view = _NoMatrixCondensedView(action_system)
    plan = build_owner_local_slab_plan(
        view,
        mesh,
        domain_z=(0.0, 1.0),
        num_slabs=3,
        overlap_fraction=0.0,
    )
    full_subdomains = _full_subdomains(plan)
    partition_plan = build_owner_local_slab_plan(
        view,
        mesh,
        domain_z=(0.0, 1.0),
        num_slabs=3,
        overlap_fraction=0.125,
    )
    partition_subdomains = _full_subdomains(partition_plan)
    assembled_diagonal = assembled.create_active_vector()
    assembled.matrix.getDiagonal(assembled_diagonal)
    local_scale = float(
        np.max(
            np.abs(assembled_diagonal.getArray(readonly=True)),
            initial=0.0,
        )
    )
    global_scale = float(comm.allreduce(local_scale, op=MPI.MAX))
    assembled_shift = assembled_diagonal.duplicate()
    assembled_shift.getArray()[:] = (
        -1j
        * 0.1
        * np.maximum(
            np.abs(assembled_diagonal.getArray(readonly=True)),
            1.0e-12 * global_scale,
        )
    )
    ordinary = DistributedPhysicalSlabSmoother(
        assembled.matrix,
        full_subdomains,
        ilu_levels=0,
        local_ksp_iterations=1,
        factor_only_storage=True,
        diagonal_shift=assembled_shift,
        interpolation="basic",
        assembly_order="combined",
    )
    partition_oracle = DistributedPhysicalSlabSmoother(
        assembled.matrix,
        partition_subdomains,
        ilu_levels=0,
        local_ksp_iterations=1,
        factor_only_storage=True,
        diagonal_shift=assembled_shift,
        interpolation="partition",
        assembly_order="combined",
    )

    observer_events = []

    def setup_observer(event, payload):
        observer_events.append(event)
        comm.gather(payload, root=0)

    candidate = DistributedPhysicalSlabSmoother.from_owner_local_plan(
        view,
        plan,
        ilu_levels=0,
        setup_observer=setup_observer,
    )
    candidate_partition = DistributedPhysicalSlabSmoother.from_owner_local_plan(
        view,
        partition_plan,
        ilu_levels=0,
        interpolation="partition",
        precomputed_diagonal_shift=assembled_shift,
    )
    candidate_two = None
    ordinary_two = None
    shift_norm_before = float(assembled_shift.norm())
    try:
        assert action_system.matrix is None
        expected_events = [
            "first_owned_slab_submatrix_allocated",
            "first_owned_slab_factor_ready",
            "all_slab_factors_ready",
        ]
        assert comm.allgather(observer_events) == [expected_events] * comm.size
        assert candidate.subdomain_owners == plan.slab_owners
        local_partition_weights = [
            weights
            for weights in partition_plan.partition_weights_by_slab
            if weights.size
        ]
        assert all(
            len(weights) == len(partition_plan.owner_rows[slab])
            for slab, owner in enumerate(partition_plan.slab_owners)
            if owner == comm.rank
            for weights in (partition_plan.partition_weights_by_slab[slab],)
        )
        assert (
            comm.allreduce(
                sum(len(weights) for weights in local_partition_weights),
                op=MPI.SUM,
            )
            > 0
        )
        assert all(
            np.all(np.isfinite(np.real(weights)))
            and np.all(np.real(weights) > 0.0)
            and np.all(np.real(weights) <= 1.0)
            for weights in local_partition_weights
        )
        assert comm.allreduce(
            any(np.any(np.real(weights) < 1.0) for weights in local_partition_weights),
            op=MPI.LOR,
        )
        assert abs(
            float(
                comm.allreduce(
                    sum(
                        float(np.sum(np.real(weights)))
                        for weights in local_partition_weights
                    ),
                    op=MPI.SUM,
                )
            )
            - float(action_system.active_rows)
        ) <= 1.0e-12
        partition_diagnostics = candidate_partition.diagnostics
        assert partition_diagnostics["interpolation"] == "partition"
        assert partition_diagnostics["partition_weight_sum_error"] <= 1.0e-12
        assert partition_diagnostics["partition_weight_min"] > 0.0
        assert partition_diagnostics["partition_weight_max"] <= 1.0
        assert candidate.local_subdomains == tuple(
            slab for slab, owner in enumerate(plan.slab_owners) if owner == comm.rank
        )
        assert len(candidate._factors) == len(candidate.local_subdomains)
        assert all(factor.matrix is None for factor in candidate._factors)
        assert all(factor.ksp is None for factor in candidate._factors)
        assert all(factor.factor_matrix is not None for factor in candidate._factors)
        candidate_diagnostics = candidate.diagnostics
        ordinary_diagnostics = ordinary.diagnostics
        assert candidate_diagnostics["factor_only_storage"] is True
        assert (
            candidate_diagnostics["subdomain_owners"]
            == ordinary_diagnostics["subdomain_owners"]
        )
        assert (
            candidate_diagnostics["local_solver_type_counts"]
            == ordinary_diagnostics["local_solver_type_counts"]
        )
        for inventory_key in (
            "global_factor_rows",
            "global_factor_nnz",
            "global_stored_factor_nnz",
        ):
            assert (
                candidate_diagnostics[inventory_key]
                == ordinary_diagnostics[inventory_key]
            )
        candidate_fingerprints = candidate_diagnostics["factor_fingerprints"]
        ordinary_fingerprints = ordinary_diagnostics["factor_fingerprints"]
        num_slabs = len(plan.slab_owners)
        assert len(candidate_fingerprints) == num_slabs
        assert len(ordinary_fingerprints) == num_slabs
        expected_subdomains = list(range(num_slabs))
        assert [item["subdomain"] for item in candidate_fingerprints] == (
            expected_subdomains
        )
        assert [item["subdomain"] for item in ordinary_fingerprints] == (
            expected_subdomains
        )
        assert all(
            len(item["sha256"]) == 64
            and all(character in "0123456789abcdef" for character in item["sha256"])
            for item in candidate_fingerprints + ordinary_fingerprints
        )
        ordinary_two = DistributedPhysicalSlabSmoother(
            assembled.matrix,
            full_subdomains,
            ilu_levels=0,
            local_ksp_iterations=1,
            local_ksp_type="gmres",
            smoother_iterations=2,
            smoother_ksp_type="gmres",
            action_operator=assembled.matrix,
            diagonal_shift=assembled_shift,
            factor_only_storage=True,
            interpolation="basic",
            assembly_order="two_color",
        )
        candidate_two = DistributedPhysicalSlabSmoother.from_owner_local_plan(
            view,
            plan,
            ilu_levels=0,
            precomputed_diagonal_shift=assembled_shift,
            two_step_action_operator=assembled.matrix,
        )
        two_diagnostics = candidate_two.diagnostics
        assert two_diagnostics["assembly_order"] == "two_color"
        assert two_diagnostics["smoother_iterations"] == 2
        assert two_diagnostics["smoother_ksp_type"] == "gmres"
        assert two_diagnostics["factor_only_storage"] is True
        assert all(factor.matrix is None for factor in candidate_two._factors)
        assert all(factor.ksp is None for factor in candidate_two._factors)
        for phase in (0.17, 0.41, 0.83):
            source = assembled.create_active_vector()
            _set_probe(source, phase)
            candidate_result = _apply(candidate_two, source)
            ordinary_result = _apply(ordinary_two, source)
            max_error, relative_error = _compare_vectors(
                candidate_result, ordinary_result, comm
            )
            assert max_error <= 1.0e-11
            assert relative_error <= 1.0e-11
            candidate_result.destroy()
            ordinary_result.destroy()
            source.destroy()
        partition_source = assembled.create_active_vector()
        _set_probe(partition_source, 0.29)
        partition_result = _apply(candidate_partition, partition_source)
        partition_expected = _apply(partition_oracle, partition_source)
        max_error, relative_error = _compare_vectors(
            partition_result, partition_expected, comm
        )
        assert max_error <= 1.0e-11
        assert relative_error <= 1.0e-11
        partition_result.destroy()
        partition_expected.destroy()
        partition_source.destroy()
        local_owner_rows = [
            plan.owner_rows[slab] for slab in candidate.local_subdomains
        ]
        expected_union = (
            np.unique(np.concatenate(local_owner_rows))
            if local_owner_rows
            else np.empty(0, dtype=PETSc.IntType)
        )
        np.testing.assert_array_equal(candidate._union_indices, expected_union)
        if comm.size == 4:
            local_factor_counts = comm.allgather(len(candidate._factors))
            assert 0 in local_factor_counts

        sources = []
        for phase in (0.17, 0.41, 0.83):
            source = assembled.create_active_vector()
            _set_probe(source, phase)
            sources.append(source)
            candidate_result = _apply(candidate, source)
            ordinary_result = _apply(ordinary, source)
            max_error, relative_error = _compare_vectors(
                candidate_result, ordinary_result, comm
            )
            assert max_error <= 1.0e-11
            assert relative_error <= 1.0e-11
            candidate_result.destroy()
            ordinary_result.destroy()

        x, y = sources[:2]
        alpha = PETSc.ScalarType(0.37 - 0.19j)
        beta = PETSc.ScalarType(-0.23 + 0.41j)
        combined = x.copy()
        combined.scale(alpha)
        combined.axpy(beta, y)
        actual = _apply(candidate, combined)
        expected = _apply(candidate, x)
        expected.scale(alpha)
        y_result = _apply(candidate, y)
        expected.axpy(beta, y_result)
        max_error, relative_error = _compare_vectors(actual, expected, comm)
        assert max_error <= 1.0e-11
        assert relative_error <= 1.0e-11

        repeated = _apply(candidate, x)
        first = _apply(candidate, x)
        max_error, relative_error = _compare_vectors(repeated, first, comm)
        assert max_error <= 1.0e-11
        assert relative_error <= 1.0e-11

        repeated.destroy()
        first.destroy()
        y_result.destroy()
        expected.destroy()
        actual.destroy()
        combined.destroy()
        for source in sources:
            source.destroy()
    finally:
        candidate.destroy()
        candidate_partition.destroy()
        partition_oracle.destroy()
        if candidate_two is not None:
            candidate_two.destroy()
        if ordinary_two is not None:
            ordinary_two.destroy()
        assert abs(float(assembled_shift.norm()) - shift_norm_before) <= 1.0e-12
        assert candidate._factors == []
        assert candidate._gathered_targets == []
        assert candidate._destroyed is True
        candidate.destroy()
        ordinary.destroy()
        assembled_shift.destroy()
        assembled_diagonal.destroy()
        action_system.destroy()
        assembled.destroy()
