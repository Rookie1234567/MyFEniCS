"""Factor-free owner-local Krylov action for physical trace slabs."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .physical_slab_two_level import OwnerLocalSlabPlan

__all__ = ("FactorFreeLocalSlabKrylovPc",)

_TINY = np.finfo(float).tiny


class FactorFreeLocalSlabKrylovPc:
    """Two-step owner-local GMRES without slab matrices or factors.

    The supplied fine action and shifted diagonal are borrowed.  Every rank
    participates in every slab action so that the borrowed distributed action
    keeps its collective semantics; only the deterministic slab owner stores
    the local right-hand side and correction.
    """

    def __init__(
        self,
        fine_operator: PETSc.Mat,
        plan: OwnerLocalSlabPlan,
        shifted_diagonal: PETSc.Vec,
    ) -> None:
        self.fine_operator = fine_operator
        self.plan = plan
        self.comm = plan.comm
        self.rank = int(self.comm.rank)
        self.num_slabs = len(plan.slab_owners)
        self.local_slabs = tuple(
            slab for slab, owner in enumerate(plan.slab_owners) if owner == self.rank
        )
        fine_size = tuple(map(int, fine_operator.getSize()))
        if fine_size[0] != fine_size[1] or fine_size[0] != int(plan.active_rows):
            raise ValueError("fine action and owner-local plan have different sizes")
        if int(shifted_diagonal.getSize()) != fine_size[0]:
            raise ValueError("shifted diagonal and fine action have different sizes")
        template = fine_operator.createVecRight()
        if tuple(map(int, shifted_diagonal.getOwnershipRange())) != tuple(
            map(int, template.getOwnershipRange())
        ):
            template.destroy()
            raise ValueError(
                "shifted diagonal and fine action have different ownership"
            )

        local_indices = [plan.owner_rows[slab] for slab in self.local_slabs]
        if local_indices:
            self._union_indices = np.unique(np.concatenate(local_indices)).astype(
                PETSc.IntType, copy=False
            )
        else:
            self._union_indices = np.empty(0, dtype=PETSc.IntType)
        self._positions_by_slab = {}
        for slab in self.local_slabs:
            rows = plan.owner_rows[slab]
            positions = np.searchsorted(self._union_indices, rows).astype(
                PETSc.IntType, copy=False
            )
            if np.any(self._union_indices[positions] != rows):
                raise RuntimeError("owner rows are absent from the local union")
            if positions.size != rows.size:
                raise RuntimeError("owner row positions are not aligned")
            self._positions_by_slab[slab] = positions

        self._global_source = template.duplicate()
        self._global_target = template.duplicate()
        self._local_source = PETSc.Vec().createSeq(
            self._union_indices.size, comm=PETSc.COMM_SELF
        )
        self._local_result = self._local_source.duplicate()
        self._local_correction = self._local_source.duplicate()
        self._local_shift_vec = self._local_source.duplicate()
        global_is = PETSc.IS().createGeneral(self._union_indices, comm=PETSc.COMM_SELF)
        local_is = PETSc.IS().createStride(
            self._union_indices.size, first=0, step=1, comm=PETSc.COMM_SELF
        )
        self._scatter = PETSc.Scatter().create(
            template, global_is, self._local_source, local_is
        )
        local_is.destroy()
        global_is.destroy()
        self._scatter.scatter(
            shifted_diagonal,
            self._local_shift_vec,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._local_shift = np.asarray(
            self._local_shift_vec.getArray(readonly=True),
            dtype=PETSc.ScalarType,
        ).copy()
        self._local_shift_vec.destroy()

        local_weight_values = self._partition_weight_error_values()
        if local_weight_values.size:
            real_weights = np.real(local_weight_values)
            local_invalid = bool(
                not np.all(np.isfinite(real_weights))
                or np.any(real_weights <= 0.0)
                or np.any(real_weights > 1.0)
            )
        else:
            local_invalid = False
        if self.comm.allreduce(local_invalid, op=MPI.LOR):
            template.destroy()
            raise RuntimeError("partition weights are not finite in (0, 1]")
        weight_sum = template.duplicate()
        weight_sum.set(0.0)
        self._local_source.set(0.0)
        local_weight_array = self._local_source.getArray()
        for slab in self.local_slabs:
            positions = self._positions_by_slab[slab]
            local_weight_array[positions] += np.asarray(
                self.plan.partition_weights_by_slab[slab],
                dtype=PETSc.ScalarType,
            )
        self._scatter.scatter(
            self._local_source,
            weight_sum,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        local_error = (
            np.asarray(weight_sum.getArray(readonly=True), dtype=PETSc.ScalarType) - 1.0
        )
        self._partition_weight_sum_error_value = float(
            self.comm.allreduce(
                float(np.max(np.abs(local_error), initial=0.0)), op=MPI.MAX
            )
        )
        self._partition_weight_min_value = float(
            self.comm.allreduce(
                float(np.min(np.real(local_weight_values)))
                if local_weight_values.size
                else 1.0,
                op=MPI.MIN,
            )
        )
        self._partition_weight_max_value = float(
            self.comm.allreduce(
                float(np.max(np.real(local_weight_values)))
                if local_weight_values.size
                else 0.0,
                op=MPI.MAX,
            )
        )
        weight_sum.destroy()
        template.destroy()
        if self._partition_weight_sum_error_value > 1.0e-12:
            raise RuntimeError("partition weights do not form a unity sum")

        self._destroyed = False
        self.apply_count = 0
        self._action_calls = 0
        self._happy_breakdowns_local = 0
        self._happy_breakdowns_global = 0
        self._apply_elapsed_s = 0.0

    def _restricted_action(self, slab: int, values: np.ndarray) -> np.ndarray:
        """Apply ``R_s (fine + shifted diagonal) R_s^T`` collectively."""

        owner = int(self.plan.slab_owners[slab])
        self._local_source.set(0.0)
        if self.rank == owner:
            positions = self._positions_by_slab[slab]
            local_values = self._local_source.getArray()
            local_values[positions] = np.asarray(values, dtype=PETSc.ScalarType)
        self._global_source.set(0.0)
        self._scatter.scatter(
            self._local_source,
            self._global_source,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self.fine_operator.mult(self._global_source, self._global_target)
        self._scatter.scatter(
            self._global_target,
            self._local_result,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._action_calls += 1
        if self.rank != owner:
            return np.empty(0, dtype=PETSc.ScalarType)
        positions = self._positions_by_slab[slab]
        result = np.asarray(
            self._local_result.getArray(readonly=True)[positions],
            dtype=PETSc.ScalarType,
        ).copy()
        result += self._local_shift[positions] * np.asarray(
            values, dtype=PETSc.ScalarType
        )
        return result

    def _two_step_gmres(self, slab: int, rhs: np.ndarray) -> tuple[np.ndarray, bool]:
        """Run exactly two Arnoldi steps and solve the small least-squares system."""

        owner = int(self.plan.slab_owners[slab])
        if self.rank != owner:
            rhs = np.empty(0, dtype=PETSc.ScalarType)
        rhs = np.asarray(rhs, dtype=PETSc.ScalarType)
        beta = float(np.linalg.norm(rhs))
        q0 = rhs / beta if beta > _TINY else np.zeros_like(rhs)
        w0 = self._restricted_action(slab, q0)
        h00 = np.vdot(q0, w0) if q0.size else PETSc.ScalarType(0.0)
        w0 = w0 - h00 * q0
        h10 = float(np.linalg.norm(w0))
        q1 = w0 / h10 if h10 > _TINY else np.zeros_like(w0)
        w1 = self._restricted_action(slab, q1)
        h01 = np.vdot(q0, w1) if q0.size else PETSc.ScalarType(0.0)
        h11 = np.vdot(q1, w1) if q1.size else PETSc.ScalarType(0.0)
        h21 = float(np.linalg.norm(w1 - h01 * q0 - h11 * q1))
        if beta <= _TINY or h10 <= _TINY:
            self._happy_breakdowns_local += 1
        H = np.zeros((3, 2), dtype=PETSc.ScalarType)
        H[0, 0] = h00
        H[1, 0] = h10
        H[0, 1] = h01
        H[1, 1] = h11
        H[2, 1] = h21
        g = np.asarray((beta, 0.0, 0.0), dtype=PETSc.ScalarType)
        coefficients, *_ = np.linalg.lstsq(H, g, rcond=None)
        correction = q0 * coefficients[0] + q1 * coefficients[1]
        return correction, beta <= _TINY or h10 <= _TINY

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the fixed two-step weighted additive-Schwarz action."""

        if self._destroyed:
            raise RuntimeError("factor-free local slab PC has been destroyed")
        started = time.perf_counter()
        target.set(0.0)
        self._scatter.scatter(
            source,
            self._local_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        source_values = np.asarray(
            self._local_source.getArray(readonly=True), dtype=PETSc.ScalarType
        ).copy()
        self._local_correction.set(0.0)
        correction_values = self._local_correction.getArray()
        for slab in range(self.num_slabs):
            if self.rank == int(self.plan.slab_owners[slab]):
                positions = self._positions_by_slab[slab]
                rhs = source_values[positions].copy()
            else:
                positions = np.empty(0, dtype=PETSc.IntType)
                rhs = np.empty(0, dtype=PETSc.ScalarType)
            correction, _happy_breakdown = self._two_step_gmres(slab, rhs)
            if self.rank == int(self.plan.slab_owners[slab]):
                weights = np.asarray(
                    self.plan.partition_weights_by_slab[slab],
                    dtype=PETSc.ScalarType,
                )
                if weights.size != positions.size:
                    raise RuntimeError("partition weights are not owner-row aligned")
                correction_values[positions] += weights * correction
        self._scatter.scatter(
            self._local_correction,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self.apply_count += 1
        self._happy_breakdowns_global = int(
            self.comm.allreduce(self._happy_breakdowns_local, op=MPI.SUM)
        )
        self._apply_elapsed_s += time.perf_counter() - started

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "profile": "factor_free_local_slab_krylov",
            "num_slabs": self.num_slabs,
            "slab_owners": list(self.plan.slab_owners),
            "local_slabs": list(self.local_slabs),
            "local_krylov_type": "gmres",
            "local_krylov_steps": 2,
            "local_inner_preconditioner": "none",
            "outer_requires_fgmres": True,
            "partition_weighted_additive_schwarz": True,
            "partition_weight_sum_error": self._partition_weight_sum_error_value,
            "partition_weight_min": self._partition_weight_min_value,
            "partition_weight_max": self._partition_weight_max_value,
            "p6_slab_matrix_materialized": False,
            "p6_slab_matrix_count": 0,
            "p6_factor_count": 0,
            "p6_factor_nnz": 0,
            "global_A_materialized_by_pc": False,
            "fine_operator_borrowed": True,
            "shifted_diagonal_borrowed": True,
            "retained_slab_matrix_count": 0,
            "apply_count": self.apply_count,
            "restricted_action_calls": self._action_calls,
            "expected_action_calls": 2 * self.num_slabs * self.apply_count,
            "happy_breakdown_count": self._happy_breakdowns_global,
            "local_union_rows": int(self._union_indices.size),
            "local_work_vector_bytes": int(
                4 * self._union_indices.size * np.dtype(PETSc.ScalarType).itemsize
            ),
            "one_level_mean_apply_s": self._apply_elapsed_s / max(self.apply_count, 1),
        }

    def _partition_weight_error_values(self) -> np.ndarray:
        values = []
        for slab in self.local_slabs:
            values.extend(
                np.asarray(
                    self.plan.partition_weights_by_slab[slab], dtype=PETSc.ScalarType
                )
            )
        return np.asarray(values, dtype=PETSc.ScalarType)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._scatter.destroy()
        self._global_source.destroy()
        self._global_target.destroy()
        self._local_source.destroy()
        self._local_result.destroy()
        self._local_correction.destroy()
        self._destroyed = True
