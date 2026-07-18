from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Mapping

import numpy as np
from petsc4py import PETSc


TINY = np.finfo(float).tiny


@dataclass(frozen=True)
class BorrowedSlabLayout:
    slab_id: int
    owner_rank: int
    union_positions: np.ndarray

    def __post_init__(self) -> None:
        positions = np.asarray(self.union_positions, dtype=PETSc.IntType)
        if positions.ndim != 1 or positions.size == 0:
            raise ValueError("borrowed slab union positions must be a nonempty vector")
        if np.any(positions[1:] <= positions[:-1]):
            raise ValueError("borrowed slab union positions must be strictly increasing")
        object.__setattr__(self, "union_positions", positions)


@dataclass(frozen=True)
class BorrowedExactAuditResult:
    slab_id: int
    owner_rank: int
    local_size: int
    rhs_norm: float
    residual_norm: float
    rho: float
    scatter_lift_s: float
    operator_action_s: float
    scatter_restrict_s: float
    total_s: float
    local_action: np.ndarray | None

    def summary(self) -> dict[str, float | int]:
        return {
            "slab_id": self.slab_id,
            "owner_rank": self.owner_rank,
            "local_size": self.local_size,
            "rhs_norm": self.rhs_norm,
            "residual_norm": self.residual_norm,
            "rho": self.rho,
            "scatter_lift_s": self.scatter_lift_s,
            "operator_action_s": self.operator_action_s,
            "scatter_restrict_s": self.scatter_restrict_s,
            "total_s": self.total_s,
        }


class BorrowedLocalExactAuditor:
    """Collective exact local action using an existing global PETSc operator.

    The auditor owns only four persistent work vectors. The shifted global
    operator and the owner-union scatter are borrowed from the live smoother;
    no local matrix or CSR array is created or retained.
    """

    def __init__(
        self,
        *,
        action_operator: PETSc.Mat,
        union_scatter: PETSc.Scatter,
        union_size: int,
        slab_owners: tuple[int, ...],
        local_layouts: Mapping[int, BorrowedSlabLayout],
    ) -> None:
        self.comm = action_operator.getComm().tompi4py()
        self.rank = int(self.comm.rank)
        self._action_operator = action_operator
        self._union_scatter = union_scatter
        self._slab_owners = tuple(int(owner) for owner in slab_owners)
        if not self._slab_owners:
            raise ValueError("borrowed auditor needs at least one slab")
        if any(owner < 0 or owner >= self.comm.size for owner in self._slab_owners):
            raise ValueError("borrowed auditor slab owner is outside the communicator")
        self._local_layouts = {
            int(slab_id): layout for slab_id, layout in local_layouts.items()
        }
        expected_local = {
            slab_id
            for slab_id, owner in enumerate(self._slab_owners)
            if owner == self.rank
        }
        if set(self._local_layouts) != expected_local:
            raise ValueError("borrowed auditor local layouts do not match slab ownership")
        for slab_id, layout in self._local_layouts.items():
            if layout.slab_id != slab_id or layout.owner_rank != self.rank:
                raise ValueError("borrowed auditor local layout identity mismatch")
            if int(layout.union_positions[-1]) >= int(union_size):
                raise ValueError("borrowed slab position is outside the owner union")

        self._global_input = action_operator.createVecRight()
        self._global_output = action_operator.createVecLeft()
        self._union_input = PETSc.Vec().createSeq(
            int(union_size), comm=PETSc.COMM_SELF
        )
        self._union_output = self._union_input.duplicate()
        scalar_bytes = np.dtype(PETSc.ScalarType).itemsize
        self._persistent_work_vector_bytes_local = int(
            scalar_bytes
            * (
                self._global_input.getLocalSize()
                + self._global_output.getLocalSize()
                + self._union_input.getLocalSize()
                + self._union_output.getLocalSize()
            )
        )
        self._layout_metadata_bytes_local = int(
            sum(
                layout.union_positions.nbytes
                for layout in self._local_layouts.values()
            )
        )
        self._destroyed = False
        self._audit_count = 0
        self._elapsed_s = 0.0

    def _collective_validation_error(
        self,
        slab_id: int,
        rhs: np.ndarray | None,
        correction: np.ndarray | None,
    ) -> str:
        if slab_id < 0 or slab_id >= len(self._slab_owners):
            return f"slab {slab_id} is outside the borrowed-audit partition"
        requested = self.comm.allgather(int(slab_id))
        if any(value != slab_id for value in requested):
            return "all ranks must audit the same slab in the same collective call"
        owner = self._slab_owners[slab_id]
        if self.rank != owner:
            if rhs is not None or correction is not None:
                return "only the slab owner may provide local audit arrays"
            return ""
        layout = self._local_layouts[slab_id]
        if rhs is None or correction is None:
            return "the slab owner must provide rhs and correction"
        rhs_array = np.asarray(rhs)
        correction_array = np.asarray(correction)
        expected_shape = (layout.union_positions.size,)
        if rhs_array.shape != expected_shape or correction_array.shape != expected_shape:
            return "borrowed audit rhs/correction shape mismatch"
        if not np.all(np.isfinite(rhs_array)) or not np.all(
            np.isfinite(correction_array)
        ):
            return "borrowed audit rhs/correction must be finite"
        return ""

    def audit(
        self,
        slab_id: int,
        *,
        rhs: np.ndarray | None,
        correction: np.ndarray | None,
    ) -> BorrowedExactAuditResult:
        if self._destroyed:
            raise RuntimeError("borrowed exact auditor has been destroyed")
        slab_id = int(slab_id)
        local_error = self._collective_validation_error(slab_id, rhs, correction)
        errors = [message for message in self.comm.allgather(local_error) if message]
        if errors:
            raise ValueError(errors[0])

        owner = self._slab_owners[slab_id]
        total_started = time.perf_counter()
        self._global_input.set(0.0)
        self._global_output.set(0.0)
        self._union_input.set(0.0)
        self._union_output.set(0.0)
        if self.rank == owner:
            layout = self._local_layouts[slab_id]
            self._union_input.getArray()[layout.union_positions] = np.asarray(
                correction, dtype=PETSc.ScalarType
            )

        lift_started = time.perf_counter()
        self._union_scatter.scatter(
            self._union_input,
            self._global_input,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        scatter_lift_s = time.perf_counter() - lift_started

        action_started = time.perf_counter()
        self._action_operator.mult(self._global_input, self._global_output)
        operator_action_s = time.perf_counter() - action_started

        restrict_started = time.perf_counter()
        self._union_scatter.scatter(
            self._global_output,
            self._union_output,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        scatter_restrict_s = time.perf_counter() - restrict_started

        local_action: np.ndarray | None = None
        local_summary: tuple[int, float, float, float]
        if self.rank == owner:
            layout = self._local_layouts[slab_id]
            local_action = np.asarray(
                self._union_output.getArray(readonly=True)[layout.union_positions],
                dtype=np.complex128,
            ).copy()
            rhs_array = np.asarray(rhs, dtype=np.complex128)
            residual_norm = float(np.linalg.norm(rhs_array - local_action))
            rhs_norm = float(np.linalg.norm(rhs_array))
            local_summary = (
                int(layout.union_positions.size),
                rhs_norm,
                residual_norm,
                residual_norm / max(rhs_norm, TINY),
            )
        else:
            local_summary = (0, 0.0, 0.0, 0.0)
        local_size, rhs_norm, residual_norm, rho = self.comm.bcast(
            local_summary, root=owner
        )
        total_s = time.perf_counter() - total_started
        self._audit_count += 1
        self._elapsed_s += total_s
        return BorrowedExactAuditResult(
            slab_id=slab_id,
            owner_rank=owner,
            local_size=local_size,
            rhs_norm=rhs_norm,
            residual_norm=residual_norm,
            rho=rho,
            scatter_lift_s=scatter_lift_s,
            operator_action_s=operator_action_s,
            scatter_restrict_s=scatter_restrict_s,
            total_s=total_s,
            local_action=local_action,
        )

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "identity": "borrowed_global_action",
            "audit_count": self._audit_count,
            "mean_audit_s": self._elapsed_s / max(self._audit_count, 1),
            "work_vectors_created": 4,
            "persistent_work_vector_bytes_local": (
                self._persistent_work_vector_bytes_local
            ),
            "layout_metadata_bytes_local": self._layout_metadata_bytes_local,
            "private_persistent_local_csr_bytes": 0,
            "owns_action_operator": False,
            "owns_union_scatter": False,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._union_output.destroy()
        self._union_input.destroy()
        self._global_output.destroy()
        self._global_input.destroy()
        self._destroyed = True
