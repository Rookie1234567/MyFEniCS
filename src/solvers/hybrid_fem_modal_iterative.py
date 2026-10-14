"""Action-only block oracle for the Task037b Hybrid system.

Terminal blocks may be borrowed assembled H2a blocks or exact action-only H2b
local blocks.  The global Hybrid operator is always a PETSc MatPython action;
this production context never forms a monolithic AIJ matrix.
"""

from __future__ import annotations

import hashlib

import numpy as np
from petsc4py import PETSc

from ..coupling.hybrid_internal_modes import HybridInternalModeCoupling
from .hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    internal_modal_constraint_matrix,
)
from .hybrid_local_dtn import HybridLocalDtnSystem

__all__ = ("HybridBlockOperator", "create_hybrid_assembled_block_action")


def _set_owned_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


def _gather_owned_small(vector: PETSc.Vec, expected_size: int) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    values = None
    if comm.rank == comm.size - 1:
        values = np.asarray(
            vector.getValues(np.arange(expected_size, dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(values, root=comm.size - 1), dtype=np.complex128)


class HybridBlockOperator:
    """MatPython context for exact Hybrid block multiplication.

    Terminal ``A`` blocks are borrowed, either assembled for H2a or action-only
    for H2b.  Coupling matrices are also borrowed and applied as actions. Only
    scratch vectors are owned here; no global monolithic matrix is formed.
    """

    def __init__(
        self,
        bottom_system: HybridLocalDtnSystem,
        top_system: HybridLocalDtnSystem,
        coupling: HybridInternalModeCoupling,
    ) -> None:
        self.bottom_system = bottom_system
        self.top_system = top_system
        self.coupling = coupling
        self.layout = HybridAugmentedLayout.build(
            bottom_system,
            top_system,
            coupling.internal_unknown_count,
        )
        self.mode_count = int(coupling.mode_count_per_direction)
        self._forward_factors = np.asarray(
            coupling.propagation.forward.factors, dtype=np.complex128
        )
        self._backward_factors = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
        self.modal_constraint = internal_modal_constraint_matrix(coupling)
        self._bottom_source = bottom_system.A.createVecRight()
        self._top_source = top_system.A.createVecRight()
        self._bottom_target = bottom_system.A.createVecLeft()
        self._top_target = top_system.A.createVecLeft()
        self._bottom_positive_source = (
            coupling.bottom.positive_traction.createVecRight()
        )
        self._bottom_negative_source = (
            coupling.bottom.negative_traction.createVecRight()
        )
        self._top_positive_source = coupling.top.positive_traction.createVecRight()
        self._top_negative_source = coupling.top.negative_traction.createVecRight()
        self._bottom_positive_target = coupling.bottom.positive_traction.createVecLeft()
        self._bottom_negative_target = coupling.bottom.negative_traction.createVecLeft()
        self._top_positive_target = coupling.top.positive_traction.createVecLeft()
        self._top_negative_target = coupling.top.negative_traction.createVecLeft()
        self._bottom_projection_target = coupling.bottom.projection.createVecLeft()
        self._top_projection_target = coupling.top.projection.createVecLeft()
        self._destroyed = False
        self._matmult_call_count = 0
        self._v13_modal_row_capture_request: dict[str, int] | None = None
        self._v13_modal_row_capture_result: dict[str, object] | None = None
        bottom_inventory = getattr(bottom_system, "inventory", {})
        top_inventory = getattr(top_system, "inventory", {})
        bottom_a_materialized = bool(
            bottom_inventory.get("global_A_materialized", True)
        )
        top_a_materialized = bool(top_inventory.get("global_A_materialized", True))
        bottom_f_materialized = bool(
            bottom_inventory.get("global_F_materialized", bottom_a_materialized)
        )
        top_f_materialized = bool(
            top_inventory.get("global_F_materialized", top_a_materialized)
        )
        side_c_counts = (
            int(bottom_inventory.get("explicit_external_c_matrix_count", 1)),
            int(top_inventory.get("explicit_external_c_matrix_count", 1)),
        )
        side_d_counts = (
            int(bottom_inventory.get("explicit_external_d_matrix_count", 1)),
            int(top_inventory.get("explicit_external_d_matrix_count", 1)),
        )
        factor_counts = (
            bottom_inventory.get("direct_factor_count"),
            top_inventory.get("direct_factor_count"),
        )
        self.inventory = {
            "matrix_type": "python",
            "matrix_free": True,
            "global_A_materialized": False,
            "bottom_A_assembled": bottom_a_materialized,
            "top_A_assembled": top_a_materialized,
            "bottom_global_F_materialized": bottom_f_materialized,
            "top_global_F_materialized": top_f_materialized,
            "bottom_explicit_external_c_matrix_count": int(
                bottom_inventory.get("explicit_external_c_matrix_count", 1)
            ),
            "bottom_explicit_external_d_matrix_count": int(
                bottom_inventory.get("explicit_external_d_matrix_count", 1)
            ),
            "top_explicit_external_c_matrix_count": int(
                top_inventory.get("explicit_external_c_matrix_count", 1)
            ),
            "top_explicit_external_d_matrix_count": int(
                top_inventory.get("explicit_external_d_matrix_count", 1)
            ),
            "bottom_direct_factor_count": bottom_inventory.get("direct_factor_count"),
            "top_direct_factor_count": top_inventory.get("direct_factor_count"),
            "explicit_external_c_matrix_count": sum(side_c_counts),
            "explicit_external_d_matrix_count": sum(side_d_counts),
            "p6_direct_factor_count": (
                sum(int(value) for value in factor_counts)
                if all(value is not None for value in factor_counts)
                else None
            ),
            "global_size": self.layout.global_size,
            "local_size": self.layout.local_size,
            "modal_count": self.layout.modal_count,
        }
        self._check_layouts()

    def _check_layouts(self) -> None:
        checks = (
            (
                self._bottom_source,
                self.layout.bottom_local_sizes[self.layout.comm.rank],
            ),
            (self._top_source, self.layout.top_local_sizes[self.layout.comm.rank]),
            (
                self._bottom_target,
                self.layout.bottom_local_sizes[self.layout.comm.rank],
            ),
            (self._top_target, self.layout.top_local_sizes[self.layout.comm.rank]),
        )
        for vector, expected in checks:
            if vector.getLocalSize() != expected:
                raise ValueError("Hybrid block ownership does not match layout.")
        if self._bottom_positive_source.getSize() != self.mode_count:
            raise ValueError("Bottom positive traction modal size is incorrect.")
        if self._bottom_negative_source.getSize() != self.mode_count:
            raise ValueError("Bottom negative traction modal size is incorrect.")
        if self._top_positive_source.getSize() != self.mode_count:
            raise ValueError("Top positive traction modal size is incorrect.")
        if self._top_negative_source.getSize() != self.mode_count:
            raise ValueError("Top negative traction modal size is incorrect.")

    def _modal_values(self, source: PETSc.Vec) -> np.ndarray:
        rank = self.layout.comm.rank
        local = (
            np.asarray(
                source.getArray(readonly=True)[self.layout.local_modal_slice]
            ).copy()
            if rank == self.layout.modal_owner
            else None
        )
        return np.asarray(
            self.layout.comm.bcast(local, root=self.layout.modal_owner),
            dtype=np.complex128,
        )

    def _modal_source(self, vector: PETSc.Vec, values: np.ndarray) -> None:
        _set_owned_values(vector, np.asarray(values, dtype=np.complex128))

    @staticmethod
    def _local_array_sha256(values: np.ndarray) -> str:
        array = np.asarray(values)
        if not array.flags.c_contiguous:
            raise ValueError("V13 original-A captured array must be contiguous")
        digest = hashlib.sha256()
        view = memoryview(array).cast("B")
        for start in range(0, len(view), 1 << 20):
            digest.update(view[start : start + (1 << 20)])
        return digest.hexdigest()

    def arm_v13_modal_row_capture(
        self,
        token: int,
        *,
        matrix_handle: int,
        pc_source_handle: int,
        pc_target_handle: int,
        operator_input_handle: int,
        operator_output_handle: int,
    ) -> None:
        """Arm one identified original-A MatMult; ordinary calls are not cached."""

        if self._destroyed:
            raise RuntimeError("original Hybrid operator has been destroyed")
        if self._v13_modal_row_capture_request is not None or (
            self._v13_modal_row_capture_result is not None
        ):
            raise RuntimeError("a V13 modal-row capture is already armed or unread")
        if type(token) is not int or token <= 0:
            raise ValueError("V13 modal-row capture token must be a positive integer")
        self._v13_modal_row_capture_request = {
            "token": token,
            "matrix_handle": matrix_handle,
            "pc_source_handle": pc_source_handle,
            "pc_target_handle": pc_target_handle,
            "operator_input_handle": operator_input_handle,
            "operator_output_handle": operator_output_handle,
        }

    def consume_v13_modal_row_capture(self, token: int) -> dict[str, object]:
        capture = self._v13_modal_row_capture_result
        if capture is None or capture.get("token") != token:
            raise RuntimeError("V13 original-A capture is missing or stale")
        self._v13_modal_row_capture_result = None
        return {
            key: value.copy() if isinstance(value, np.ndarray) else value
            for key, value in capture.items()
        }

    def clear_v13_modal_row_capture(self, token: int) -> None:
        request = self._v13_modal_row_capture_request
        if request is not None and request.get("token") == token:
            self._v13_modal_row_capture_request = None
        capture = self._v13_modal_row_capture_result
        if capture is not None and capture.get("token") == token:
            self._v13_modal_row_capture_result = None

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self._matmult_call_count += 1
        capture_request = self._v13_modal_row_capture_request
        # Consume the arm before touching borrowed/PETSc state so exceptions
        # cannot leave a request available to a later ordinary MatMult.
        self._v13_modal_row_capture_request = None
        capture_call_id = self._matmult_call_count
        source_handle = int(source.handle)
        target_handle = int(target.handle)
        matrix_handle = int(_matrix.handle)
        if capture_request is not None:
            expected = (
                capture_request["matrix_handle"],
                capture_request["operator_input_handle"],
                capture_request["operator_output_handle"],
            )
            observed = (matrix_handle, source_handle, target_handle)
            if expected != observed:
                raise RuntimeError(
                    "V13 original-A capture identity mismatch: "
                    f"expected={expected}, observed={observed}"
                )
            if (
                capture_request["pc_source_handle"]
                == capture_request["pc_target_handle"]
                or source_handle == target_handle
            ):
                raise ValueError("V13 original-A capture vectors alias")
        input_before_sha = (
            self._local_array_sha256(
                np.asarray(source.getArray(readonly=True))
            )
            if capture_request is not None
            else None
        )
        source_values = np.asarray(source.getArray(readonly=True))
        bottom_local = source_values[self.layout.local_bottom_slice]
        top_local = source_values[self.layout.local_top_slice]
        self._bottom_source.getArray()[:] = bottom_local
        self._top_source.getArray()[:] = top_local
        modal = self._modal_values(source)
        mode_count = self.mode_count
        self._modal_source(self._bottom_positive_source, modal[:mode_count])
        self._modal_source(
            self._bottom_negative_source,
            self._backward_factors * modal[mode_count:],
        )
        self._modal_source(
            self._top_positive_source,
            self._forward_factors * modal[:mode_count],
        )
        self._modal_source(self._top_negative_source, modal[mode_count:])
        self.bottom_system.A.mult(self._bottom_source, self._bottom_target)
        self.top_system.A.mult(self._top_source, self._top_target)
        self.coupling.bottom.positive_traction.mult(
            self._bottom_positive_source, self._bottom_positive_target
        )
        self.coupling.bottom.negative_traction.mult(
            self._bottom_negative_source, self._bottom_negative_target
        )
        self.coupling.top.positive_traction.mult(
            self._top_positive_source, self._top_positive_target
        )
        self.coupling.top.negative_traction.mult(
            self._top_negative_source, self._top_negative_target
        )
        self._bottom_target.axpy(1.0, self._bottom_positive_target)
        self._bottom_target.axpy(1.0, self._bottom_negative_target)
        self._top_target.axpy(1.0, self._top_positive_target)
        self._top_target.axpy(1.0, self._top_negative_target)
        self.coupling.bottom.projection.mult(
            self._bottom_source, self._bottom_projection_target
        )
        self.coupling.top.projection.mult(self._top_source, self._top_projection_target)
        modal_result = self.modal_constraint @ modal
        t_constraint = modal_result.copy() if capture_request is not None else None
        t_bottom = _gather_owned_small(self._bottom_projection_target, mode_count)
        t_bottom_capture = None
        if capture_request is not None:
            t_bottom_capture = np.zeros_like(modal_result)
            t_bottom_capture[:mode_count] = t_bottom
        modal_result[:mode_count] += t_bottom
        t_top = _gather_owned_small(self._top_projection_target, mode_count)
        t_top_capture = None
        if capture_request is not None:
            t_top_capture = np.zeros_like(modal_result)
            t_top_capture[mode_count:] = t_top
        modal_result[mode_count:] += t_top
        target_local = target.getArray()
        target_local[self.layout.local_bottom_slice] = self._bottom_target.getArray(
            readonly=True
        )
        target_local[self.layout.local_top_slice] = self._top_target.getArray(
            readonly=True
        )
        if self.layout.comm.rank == self.layout.modal_owner:
            target_local[self.layout.local_modal_slice] = modal_result
        if capture_request is not None:
            local_w_modal = (
                np.asarray(
                    target_local[self.layout.local_modal_slice],
                    dtype=np.complex128,
                ).copy()
                if self.layout.comm.rank == self.layout.modal_owner
                else None
            )
            output_matches_components = (
                local_w_modal is not None
                and np.array_equal(local_w_modal, modal_result)
            ) if self.layout.comm.rank == self.layout.modal_owner else True
            if not output_matches_components:
                raise RuntimeError(
                    "V13 captured components differ from the original-A output row"
                )
            input_after_sha = self._local_array_sha256(
                np.asarray(source.getArray(readonly=True))
            )
            self._v13_modal_row_capture_result = {
                "token": capture_request["token"],
                "matrix_handle": matrix_handle,
                "context_identity": id(self),
                "matmult_call_id": capture_call_id,
                "pc_source_handle": capture_request["pc_source_handle"],
                "pc_target_handle": capture_request["pc_target_handle"],
                "operator_input_handle": source_handle,
                "operator_output_handle": target_handle,
                "operator_input_range": tuple(
                    int(value) for value in source.getOwnershipRange()
                ),
                "operator_output_range": tuple(
                    int(value) for value in target.getOwnershipRange()
                ),
                "operator_input_sha256_before": input_before_sha,
                "operator_input_sha256_after": input_after_sha,
                "operator_input_unchanged": input_before_sha == input_after_sha,
                "w_modal": local_w_modal,
                "t_bottom": t_bottom_capture,
                "t_top": t_top_capture,
                "t_constraint": t_constraint.copy(),
                "output_matches_components": output_matches_components,
            }

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        for vector in (
            self._top_projection_target,
            self._bottom_projection_target,
            self._top_negative_target,
            self._top_positive_target,
            self._bottom_negative_target,
            self._bottom_positive_target,
            self._top_negative_source,
            self._top_positive_source,
            self._bottom_negative_source,
            self._bottom_positive_source,
            self._top_target,
            self._bottom_target,
            self._top_source,
            self._bottom_source,
        ):
            vector.destroy()
        self._destroyed = True


def create_hybrid_assembled_block_action(
    bottom_system: HybridLocalDtnSystem,
    top_system: HybridLocalDtnSystem,
    coupling: HybridInternalModeCoupling,
) -> tuple[PETSc.Mat, HybridBlockOperator]:
    """Create the action-only H2a Hybrid operator and its owned context."""

    context = HybridBlockOperator(bottom_system, top_system, coupling)
    matrix = PETSc.Mat().createPython(
        ((context.layout.local_size, context.layout.global_size),) * 2,
        context=context,
        comm=context.layout.comm,
    )
    matrix.setUp()
    return matrix, context
