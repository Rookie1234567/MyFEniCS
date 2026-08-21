"""Two-slab Candidate-A/C forward/backward residual-propagation sweep.

The module is deliberately a small composition layer around the current
matrix-free volume, DtN, MPC, and facet-transmission actions.  A slab is
restricted by the owned cells on the two sides of ``cfg.interface_z``; it is
not made by masking the result of a full-space operator.  The only retained
slab metadata is row support and inverse multiplicity weights.  No slab
matrix, Schur complement, factor, or numeric global gather is created.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

import hashlib
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import mesh

from ..constraints.floquet_3d_high_order import _local_dof_global_info
from .common_3d_forms import _build_variational_forms
from .fullspace_mpc_action import build_fullspace_mpc_form_action
from .fullspace_second_order_impedance import (
    FIXED_SECOND_ORDER_LOCAL_IMPEDANCE,
)


FULLSPACE_R4_PROFILE = "full3d_scalable_v1"
FULLSPACE_R4_SLAB_COUNT = 2
FULLSPACE_R4_FORWARD_ORDER = (0, 1)
FULLSPACE_R4_BACKWARD_ORDER = (1, 0)
FULLSPACE_R4_TRANSMISSION = "first_order_impedance_robin_v1"
FULLSPACE_R4_C_TRANSMISSION = FIXED_SECOND_ORDER_LOCAL_IMPEDANCE
FULLSPACE_R4_LOCAL_KSP_TYPE = "gmres"
FULLSPACE_R4_LOCAL_KSP_RESTART = 8
FULLSPACE_R4_LOCAL_KSP_MAX_IT = 8
FULLSPACE_R4_EXPECTED_DIVERGED_ITS = -3
FULLSPACE_R4_POU = "inverse_owner_multiplicity"


def candidate_a_audit() -> Mapping[str, object]:
    """Return the immutable Candidate-A contract before any source is used."""

    return MappingProxyType(
        {
            "profile": FULLSPACE_R4_PROFILE,
            "slab_count": FULLSPACE_R4_SLAB_COUNT,
            "forward_order": FULLSPACE_R4_FORWARD_ORDER,
            "backward_order": FULLSPACE_R4_BACKWARD_ORDER,
            "transmission": FULLSPACE_R4_TRANSMISSION,
            "transmission_q": "-i*k0*n_side",
            "local_ksp_type": FULLSPACE_R4_LOCAL_KSP_TYPE,
            "local_ksp_count": FULLSPACE_R4_SLAB_COUNT,
            "local_operator_type": "PETSc.MatShell",
            "global_ksp_created": False,
            "local_ksp_restart": FULLSPACE_R4_LOCAL_KSP_RESTART,
            "local_ksp_max_it": FULLSPACE_R4_LOCAL_KSP_MAX_IT,
            "expected_diverged_its": FULLSPACE_R4_EXPECTED_DIVERGED_ITS,
            "fixed_iteration_semantics": "DIVERGED_ITS_is_expected",
            "pou": FULLSPACE_R4_POU,
            "parameters_frozen_before_rho": True,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "dense_interface_materialized": False,
            "growing_slab_factor_materialized": False,
            "numeric_allgather": False,
        }
    )


@dataclass(frozen=True)
class SlabSupport:
    """Owner-local support and PoU data for one real cell-restricted slab."""

    slab_id: int
    owned_cells: np.ndarray
    owned_local_rows: np.ndarray
    owned_global_rows: np.ndarray
    weights: np.ndarray
    outer_side: str


@dataclass(frozen=True)
class FullspaceSlabPlan:
    """Two-slab ownership plan derived from the finalized function space."""

    mesh: Any
    function_space: Any
    supports: tuple[SlabSupport, SlabSupport]
    local_cell_counts: tuple[int, int]
    global_cell_counts: tuple[int, int]
    summed_slab_support_count: int
    global_unique_active_row_count: int
    audit: Mapping[str, object]


@dataclass
class SweepResult:
    """The compact result of one forward/backward Candidate-A sweep."""

    delta: PETSc.Vec
    action_delta: PETSc.Vec
    residual: PETSc.Vec
    ledger: tuple[Mapping[str, object], ...]
    audit: Mapping[str, object]


def _owned_global_row(index_map: Any, local_row: int) -> int:
    return int(index_map.local_to_global(np.asarray([local_row], dtype=np.int32))[0])


def _support_rows(
    topology: Any,
) -> tuple[list[set[int]], list[set[int]], list[list[tuple[int, int]]]]:
    """Collect row/slab metadata and exchange only sparse owner requests."""

    V = topology.function_space
    comm = V.mesh.comm
    index_map = V.dofmap.index_map
    owned_size = int(index_map.size_local)
    slave_rows = {int(row) for row in np.asarray(topology.floquet_data.local_slave_dofs)}
    local_owned: list[set[int]] = [set(), set()]
    local_global: list[set[int]] = [set(), set()]
    requests: list[set[tuple[int, int]]] = [set() for _rank in range(comm.size)]

    for cell, slab in enumerate(np.asarray(topology.owned_slab_ids, dtype=np.int8)):
        slab_id = int(slab)
        rows = np.asarray(V.dofmap.cell_dofs(int(cell)), dtype=np.int32)
        rows = np.unique(rows[~np.isin(rows, np.asarray(tuple(slave_rows), dtype=np.int32))])
        if rows.size == 0:
            continue
        globals_, owners, owned = _local_dof_global_info(V, rows)
        for local_row, global_row, owner, is_owned in zip(
            rows, globals_, owners, owned, strict=True
        ):
            global_int = int(global_row)
            local_global[slab_id].add(global_int)
            requests[int(owner)].add((global_int, slab_id))
            if bool(is_owned):
                local_owned[slab_id].add(int(local_row))

    incoming = comm.alltoall([sorted(packet) for packet in requests])
    owner_rows: list[dict[int, set[int]]] = [dict(), dict()]
    for packet in incoming:
        for global_row, slab_id in packet:
            owner_rows[int(slab_id)].setdefault(int(global_row), set()).add(int(slab_id))

    # Local cells are also an owner report when the row is owned here.  The
    # incoming packets close rows whose cell owner is a different rank.
    for slab_id in range(FULLSPACE_R4_SLAB_COUNT):
        for global_row in local_global[slab_id]:
            owner_rows[slab_id].setdefault(int(global_row), set()).add(slab_id)
    return local_owned, local_global, [
        sorted(owner_rows[slab_id]) for slab_id in range(FULLSPACE_R4_SLAB_COUNT)
    ]


def build_fullspace_slab_plan(topology: Any) -> FullspaceSlabPlan:
    """Build owner-local slab supports from ``cfg.interface_z`` cell ownership."""

    if candidate_a_audit()["slab_count"] != 2:
        raise RuntimeError("Candidate A requires exactly two slabs")
    V = topology.function_space
    comm = V.mesh.comm
    _local_owned, _local_global, owner_rows = _support_rows(topology)
    index_map = V.dofmap.index_map
    supports: list[SlabSupport] = []
    for slab_id in range(FULLSPACE_R4_SLAB_COUNT):
        global_rows = np.asarray(owner_rows[slab_id], dtype=np.int64)
        local_rows = np.asarray(
            [int(row - int(index_map.local_range[0])) for row in global_rows],
            dtype=np.int32,
        )
        owned_mask = (local_rows >= 0) & (local_rows < int(index_map.size_local))
        local_rows = local_rows[owned_mask]
        global_rows = global_rows[owned_mask]
        order = np.argsort(global_rows, kind="stable")
        local_rows = local_rows[order]
        global_rows = global_rows[order]
        supports.append(
            SlabSupport(
                slab_id=slab_id,
                owned_cells=np.flatnonzero(
                    np.asarray(topology.owned_slab_ids, dtype=np.int8) == slab_id
                ).astype(np.int32),
                owned_local_rows=local_rows,
                owned_global_rows=global_rows,
                weights=np.empty(global_rows.size, dtype=np.float64),
                outer_side="bottom" if slab_id == 0 else "top",
            )
        )

    row_sets = [set(map(int, support.owned_global_rows)) for support in supports]
    for slab_id, support in enumerate(supports):
        weights = np.asarray(
            [1.0 / (sum(int(row in rows) for rows in row_sets)) for row in support.owned_global_rows],
            dtype=np.float64,
        )
        object.__setattr__(support, "weights", weights)

    local_counts = tuple(int(np.asarray(topology.owned_slab_ids).tolist().count(slab)) for slab in (0, 1))
    global_counts = tuple(int(comm.allreduce(count, op=MPI.SUM)) for count in local_counts)
    summed_support_count = int(
        comm.allreduce(
            sum(len(support.owned_global_rows) for support in supports),
            op=MPI.SUM,
        )
    )
    local_unique_rows = {
        int(row)
        for support in supports
        for row in support.owned_global_rows
    }
    unique_active_count = int(
        comm.allreduce(len(local_unique_rows), op=MPI.SUM)
    )
    row_weight_error = max(
        [
            abs(sum(weight for support in supports for row, weight in zip(support.owned_global_rows, support.weights, strict=True) if int(row) == int(global_row)) - 1.0)
            for support in supports
            for global_row in support.owned_global_rows
        ]
        or [0.0]
    )
    row_weight_error = float(comm.allreduce(row_weight_error, op=MPI.MAX))
    if row_weight_error > 1.0e-14:
        raise RuntimeError("inverse-multiplicity PoU does not close")
    audit = {
        **dict(candidate_a_audit()),
        "cell_restriction": "owned_cells_partitioned_by_cfg.interface_z",
        "local_cell_counts": list(local_counts),
        "global_cell_counts": list(global_counts),
        "owner_local_row_support": True,
        "owner_local_numeric_requests": True,
        "summed_slab_support_count": summed_support_count,
        "global_unique_active_row_count": unique_active_count,
        "pou_max_error": row_weight_error,
        "outer_boundary_slab": {"bottom": 0, "top": 1},
        "outer_dtn_shared_action_side_restricted": True,
        "local_shell_external_rhs": "exact_zero_required",
    }
    return FullspaceSlabPlan(
        mesh=topology.mesh,
        function_space=V,
        supports=(supports[0], supports[1]),
        local_cell_counts=local_counts,
        global_cell_counts=global_counts,
        summed_slab_support_count=summed_support_count,
        global_unique_active_row_count=unique_active_count,
        audit=MappingProxyType(audit),
    )


def _slab_cell_tags(topology: Any, mesh_data: Any, slab_id: int) -> Any:
    """Filter the existing owned cell tags; never reclassify material by geometry."""

    msh = topology.mesh
    cell_map = msh.topology.index_map(msh.topology.dim)
    owned_count = int(cell_map.size_local)
    indices = np.asarray(mesh_data.cell_tags.indices, dtype=np.int32)
    values = np.asarray(mesh_data.cell_tags.values, dtype=np.int32)
    owned_mask = indices < owned_count
    owned_indices = indices[owned_mask]
    owned_values = values[owned_mask]
    selected_mask = (
        np.asarray(topology.owned_slab_ids, dtype=np.int8)[owned_indices]
        == int(slab_id)
    )
    selected_indices = owned_indices[selected_mask]
    selected_values = owned_values[selected_mask]
    order = np.argsort(selected_indices, kind="stable")
    return mesh.meshtags(
        msh,
        msh.topology.dim,
        selected_indices[order],
        selected_values[order],
    )


def build_slab_volume_actions(
    plan: FullspaceSlabPlan,
    topology: Any,
    mesh_data: Any,
    raw_function_space: Any,
    mpc: Any,
    cfg: Any,
) -> tuple[Any, Any]:
    """Create two cell-restricted matrix-free volume actions."""

    actions: list[Any] = []
    for slab_id in range(FULLSPACE_R4_SLAB_COUNT):
        slab_data = copy(mesh_data)
        slab_data.cell_tags = _slab_cell_tags(topology, mesh_data, slab_id)
        bilinear_form, _rhs = _build_variational_forms(
            topology.mesh,
            slab_data,
            cfg,
            raw_function_space,
            field_formulation="total_field",
        )
        actions.append(
            build_fullspace_mpc_form_action(
                bilinear_form,
                raw_function_space,
                mpc=mpc,
                slave_row_identity=False,
            )
        )
    return actions[0], actions[1]


def _owned_sha(vector: PETSc.Vec) -> str:
    values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128)
    return hashlib.sha256(np.ascontiguousarray(values).view(np.uint8)).hexdigest()


def _relative_vec(left: PETSc.Vec, right: PETSc.Vec) -> float:
    difference = left.duplicate()
    left.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), right)
    numerator = float(difference.norm())
    denominator = float(right.norm())
    difference.destroy()
    return numerator / max(denominator, np.finfo(float).tiny)


def _zero_outside(vector: PETSc.Vec, support: SlabSupport) -> None:
    values = vector.getArray()
    keep = np.zeros(values.size, dtype=bool)
    keep[support.owned_local_rows] = True
    values[~keep] = 0.0


class _LocalSlabShell:
    """One PETSc shell operator with a fixed, owner-local slab support."""

    def __init__(
        self,
        plan: FullspaceSlabPlan,
        support: SlabSupport,
        slab_id: int,
        volume_action: Any,
        dtn_action: Any,
        transmission: Any,
    ) -> None:
        self.plan = plan
        self.support = support
        self.slab_id = int(slab_id)
        self.volume_action = volume_action
        self.dtn_action = dtn_action
        self.transmission = transmission
        self.direction = "forward" if slab_id == 0 else "backward"
        index_map = plan.function_space.dofmap.index_map
        owned = int(index_map.size_local)
        global_size = int(index_map.size_global)
        self.matrix = PETSc.Mat().createPython(
            ((owned, global_size), (owned, global_size)),
            context=self,
            comm=plan.mesh.comm,
        )
        self.matrix.setUp()
        self._masked: PETSc.Vec | None = None
        self.apply_count = 0

    def _masked_source(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._masked is None:
            self._masked = source.duplicate()
        source.copy(self._masked)
        _zero_outside(self._masked, self.support)
        return self._masked

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        masked = self._masked_source(source)
        self.dtn_action.apply(masked, target)
        # FullspaceMpcFormAction.apply returns its documented reusable
        # internal buffer.  It is action-owned and must remain alive for the
        # next fixed MatMult; only the one-shot Robin result below is
        # caller-owned.  This Robin term belongs to L_j; it is not a
        # neighbor update or an outgoing-interface surrogate.
        volume_result = self.volume_action.apply(masked)
        target.axpy(PETSc.ScalarType(1.0), volume_result)
        robin_result = self.transmission.apply(masked, self.direction)
        try:
            target.axpy(PETSc.ScalarType(1.0), robin_result)
        finally:
            robin_result.destroy()
        values = target.getArray()
        source_values = source.getArray(readonly=True)
        keep = np.zeros(values.size, dtype=bool)
        keep[self.support.owned_local_rows] = True
        values[~keep] = source_values[~keep]
        self.apply_count += 1

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if getattr(self, "_destroyed", False):
            return
        self._destroyed = True
        if self._masked is not None:
            self._masked.destroy()
            self._masked = None
        matrix = self.matrix
        self.matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()


class CandidateASweep:
    """Fixed Candidate-A forward/backward sweep over the two local shells."""

    def __init__(
        self,
        plan: FullspaceSlabPlan,
        volume_actions: tuple[Any, Any],
        dtn_action: Any,
        transmission: Any,
        physical_action: Any,
    ) -> None:
        self.plan = plan
        self.volume_actions = volume_actions
        self.dtn_action = dtn_action
        self.transmission = transmission
        self.physical_action = physical_action
        self.shells = tuple(
            _LocalSlabShell(
                plan,
                plan.supports[slab_id],
                slab_id,
                volume_actions[slab_id],
                dtn_action,
                transmission,
            )
            for slab_id in range(FULLSPACE_R4_SLAB_COUNT)
        )
        self.ksps = tuple(self._build_ksp(shell) for shell in self.shells)
        self._sweep_count = 0
        self._exact_update_apply_count = 0
        self._destroyed = False
        support_metadata_components = {
            "owned_local_rows_bytes": int(
                sum(support.owned_local_rows.nbytes for support in plan.supports)
            ),
            "owned_global_rows_bytes": int(
                sum(support.owned_global_rows.nbytes for support in plan.supports)
            ),
            "inverse_pou_weights_bytes": int(
                sum(support.weights.nbytes for support in plan.supports)
            ),
        }
        retained_support_metadata_bytes = int(sum(support_metadata_components.values()))
        local_storage = int(
            plan.function_space.dofmap.index_map.size_local
            + plan.function_space.dofmap.index_map.num_ghosts
        )
        fixed_gmres_basis_vectors = int(
            FULLSPACE_R4_SLAB_COUNT * (FULLSPACE_R4_LOCAL_KSP_RESTART + 1)
        )
        fixed_gmres_basis_workspace = int(
            fixed_gmres_basis_vectors
            * local_storage
            * np.dtype(PETSc.ScalarType).itemsize
        )
        self._audit = {
            **dict(plan.audit),
            "candidate": "A",
            "local_solver": "PETSc.KSP.GMRES_MatShell_fixed_8",
            "ksp_reason_diverged_its_allowed": True,
            "transmission_sign_oracle": "q=-i*k0*n_side; forward=upper, backward=lower",
            "forward_backward_complete": True,
            "retained_support_metadata_bytes": retained_support_metadata_bytes,
            "retained_support_metadata_components": support_metadata_components,
            "retained_support_metadata_scaling": "O(local_owned_volume_rows)",
            "fixed_gmres_basis_vectors": fixed_gmres_basis_vectors,
            "fixed_gmres_arnoldi_basis_derived_bytes_per_rank": fixed_gmres_basis_workspace,
            "fixed_gmres_workspace_scaling": "O(fixed_restart * local_storage)",
            "fixed_gmres_workspace_scope": "Arnoldi_basis_derived_only; other_KSP_work_process_tree_measured",
            "split_volume_action_audits": [
                dict(getattr(action, "audit", {})) for action in volume_actions
            ],
            "volume_action_output_ownership": "reusable_internal_buffer_not_destroyed",
        }

    @staticmethod
    def _build_ksp(shell: _LocalSlabShell) -> PETSc.KSP:
        ksp = PETSc.KSP().create(shell.plan.mesh.comm)
        ksp.setOperators(shell.matrix)
        ksp.setType(PETSc.KSP.Type.GMRES)
        ksp.setGMRESRestart(FULLSPACE_R4_LOCAL_KSP_RESTART)
        ksp.setTolerances(
            rtol=0.0,
            atol=0.0,
            max_it=FULLSPACE_R4_LOCAL_KSP_MAX_IT,
        )
        ksp.setInitialGuessNonzero(False)
        ksp.setErrorIfNotConverged(False)
        ksp.setUp()
        return ksp

    def _restrict(self, source: PETSc.Vec, slab_id: int) -> PETSc.Vec:
        restricted = source.duplicate()
        source.copy(restricted)
        _zero_outside(restricted, self.plan.supports[slab_id])
        return restricted

    def _correction(self, solution: PETSc.Vec, slab_id: int) -> PETSc.Vec:
        """Apply the owner-local restriction/prolongation and inverse PoU."""

        support = self.plan.supports[slab_id]
        correction = solution.duplicate()
        solution.copy(correction)
        values = correction.getArray()
        keep = np.zeros(values.size, dtype=bool)
        keep[support.owned_local_rows] = True
        values[support.owned_local_rows] *= support.weights
        values[~keep] = 0.0
        return correction

    def _solve(self, slab_id: int, rhs: PETSc.Vec) -> tuple[PETSc.Vec, Mapping[str, object]]:
        support = self.plan.supports[slab_id]
        rhs_values = rhs.getArray(readonly=True)
        outside = np.ones(rhs_values.size, dtype=bool)
        outside[support.owned_local_rows] = False
        if np.any(rhs_values[outside] != 0.0):
            raise RuntimeError("local slab RHS has nonzero external shell rows")
        solution = rhs.duplicate()
        solution.set(0.0)
        self.ksps[slab_id].solve(rhs, solution)
        reason = int(self.ksps[slab_id].getConvergedReason())
        values = np.asarray(solution.getArray(readonly=True), dtype=np.complex128)
        if not np.all(np.isfinite(values)):
            raise FloatingPointError("fixed local KSP produced non-finite values")
        if reason < 0 and reason != FULLSPACE_R4_EXPECTED_DIVERGED_ITS:
            raise RuntimeError(f"fixed local KSP diverged with reason {reason}")
        _zero_outside(solution, support)
        return solution, {
            "slab": int(slab_id),
            "reason": reason,
            "reason_name": str(self.ksps[slab_id].getConvergedReason()),
            "iterations": int(self.ksps[slab_id].getIterationNumber()),
            "fixed_max_iterations": FULLSPACE_R4_LOCAL_KSP_MAX_IT,
        }

    def sweep(self, rhs: PETSc.Vec) -> SweepResult:
        """Run fixed residual-propagation forward and backward sweeps.

        The only data sent to the next slab is the restriction of the exact
        physical action of the current correction.  The Robin action remains
        solely inside each local shell operator.
        """

        if self._destroyed:
            raise RuntimeError("Candidate-A sweep has been destroyed")
        ledger: list[Mapping[str, object]] = []
        sweep_exact_update_apply_count = 0
        residual = rhs.copy()
        delta = rhs.duplicate()
        delta.set(0.0)
        for direction, order in (
            ("forward", FULLSPACE_R4_FORWARD_ORDER),
            ("backward", FULLSPACE_R4_BACKWARD_ORDER),
        ):
            for position, slab_id in enumerate(order):
                rhs_j = self._restrict(residual, slab_id)
                solution, solve = self._solve(slab_id, rhs_j)
                correction = self._correction(solution, slab_id)
                action_j = correction.duplicate()
                self.physical_action.apply(correction, action_j)
                sweep_exact_update_apply_count += 1

                residual.axpy(PETSc.ScalarType(-1.0), action_j)

                delta.axpy(PETSc.ScalarType(1.0), correction)
                next_slab = (
                    int(order[position + 1])
                    if position + 1 < len(order)
                    else None
                )
                neighbor_action_sha = None
                neighbor_residual_sha = None
                if next_slab is not None:
                    neighbor_action = self._restrict(action_j, next_slab)
                    neighbor_residual = self._restrict(residual, next_slab)
                    neighbor_action_sha = _owned_sha(neighbor_action)
                    neighbor_residual_sha = _owned_sha(neighbor_residual)
                    neighbor_action.destroy()
                    neighbor_residual.destroy()
                ledger.append(
                    {
                        "direction": direction,
                        "slab": int(slab_id),
                        "rhs_sha256": _owned_sha(rhs_j),
                        "correction_sha256": _owned_sha(correction),
                        "action_sha256": _owned_sha(action_j),
                        "residual_sha256": _owned_sha(residual),
                        "neighbor_slab": next_slab,
                        "neighbor_action_sha256": neighbor_action_sha,
                        "neighbor_residual_sha256": neighbor_residual_sha,
                        "outgoing_definition": (
                            "R_next(A_current_c_j)"
                            if next_slab is not None
                            else "updated_residual_after_A_current_c_j"
                        ),
                        "solve": solve,
                    }
                )
                for vector in (
                    rhs_j,
                    solution,
                    correction,
                    action_j,
                ):
                    vector.destroy()

        action_delta = delta.duplicate()
        self.physical_action.apply(delta, action_delta)
        sweep_exact_update_apply_count += 1
        independently_recomputed_residual = rhs.copy()
        independently_recomputed_residual.axpy(
            PETSc.ScalarType(-1.0), action_delta
        )
        recursive_residual_error = _relative_vec(
            residual, independently_recomputed_residual
        )
        residual.destroy()
        residual = independently_recomputed_residual
        self._sweep_count += 1
        if sweep_exact_update_apply_count != 5:
            raise RuntimeError("fixed Candidate-A sweep did not perform five exact updates")
        self._exact_update_apply_count += sweep_exact_update_apply_count
        audit = dict(self._audit)
        audit.update(
            {
                "sweep_count": self._sweep_count,
                "exact_update_apply_count": sweep_exact_update_apply_count,
                "exact_update_apply_count_cumulative": self._exact_update_apply_count,
                "ledger_entries": len(ledger),
                "residual_propagation": True,
                "recursive_residual_closure_relative_error": recursive_residual_error,
                "source_independent_parameters": True,
            }
        )
        return SweepResult(delta, action_delta, residual, tuple(ledger), MappingProxyType(audit))

    @property
    def audit(self) -> Mapping[str, object]:
        return MappingProxyType(
            dict(
                self._audit,
                sweep_count=self._sweep_count,
                exact_update_apply_count_cumulative=self._exact_update_apply_count,
            )
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        for ksp in self.ksps:
            ksp.destroy()
        for shell in self.shells:
            shell.destroy()
        for action in self.volume_actions:
            action.destroy()


def build_candidate_a(
    plan: FullspaceSlabPlan,
    volume_actions: tuple[Any, Any],
    dtn_action: Any,
    transmission: Any,
    physical_action: Any,
) -> CandidateASweep:
    """Build Candidate A from an already audited real slab restriction."""

    return CandidateASweep(
        plan,
        volume_actions,
        dtn_action,
        transmission,
        physical_action,
    )


class CandidateCSweep(CandidateASweep):
    """Reuse the fixed residual-propagation sweep with Candidate C."""

    def __init__(
        self,
        plan: FullspaceSlabPlan,
        volume_actions: tuple[Any, Any],
        dtn_action: Any,
        transmission: Any,
        physical_action: Any,
    ) -> None:
        super().__init__(
            plan,
            volume_actions,
            dtn_action,
            transmission,
            physical_action,
        )
        self._audit = {
            **self._audit,
            "candidate": "C",
            "transmission": FULLSPACE_R4_C_TRANSMISSION,
            "transmission_q": "fixed y0=-i*k0*n_neighbor",
            "transmission_sign_oracle": (
                "fixed second-order; forward=upper, backward=lower"
            ),
            "transmission_action_scope": "local_shell_only",
            "outgoing_definition": "exact_physical_action_of_current_correction",
            "transmission_audit": dict(transmission.audit),
        }


def build_candidate_c(
    plan: FullspaceSlabPlan,
    volume_actions: tuple[Any, Any],
    dtn_action: Any,
    transmission: Any,
    physical_action: Any,
) -> CandidateCSweep:
    """Build Candidate C without changing Candidate-A defaults."""

    return CandidateCSweep(
        plan,
        volume_actions,
        dtn_action,
        transmission,
        physical_action,
    )


__all__ = [
    "CandidateASweep",
    "CandidateCSweep",
    "FULLSPACE_R4_BACKWARD_ORDER",
    "FULLSPACE_R4_FORWARD_ORDER",
    "FULLSPACE_R4_LOCAL_KSP_MAX_IT",
    "FULLSPACE_R4_LOCAL_KSP_RESTART",
    "FULLSPACE_R4_LOCAL_KSP_TYPE",
    "FULLSPACE_R4_EXPECTED_DIVERGED_ITS",
    "FULLSPACE_R4_PROFILE",
    "FULLSPACE_R4_POU",
    "FULLSPACE_R4_SLAB_COUNT",
    "FULLSPACE_R4_TRANSMISSION",
    "FULLSPACE_R4_C_TRANSMISSION",
    "FullspaceSlabPlan",
    "SlabSupport",
    "SweepResult",
    "build_candidate_a",
    "build_candidate_c",
    "build_fullspace_slab_plan",
    "build_slab_volume_actions",
    "candidate_a_audit",
]
