"""Owner-local coarse action data for the D2 trace-harmonic basis.

This module builds only ``Z``, ``AZ`` and the small coefficient matrix
``E = Z^H A Z``.  It deliberately does not solve a coarse system and does not
own the basis or the physical action supplied by the caller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


COARSE_RANK64_Z_AZ_LIMIT_BYTES = 355_946_496
COARSE_TOTAL_RETAINED_LIMIT_BYTES = 424_000_000


def _byte_stats(comm: Any, local_bytes: int) -> dict[str, int]:
    value = int(local_bytes)
    return {
        "local": value,
        "global_sum": int(comm.allreduce(value, op=MPI.SUM)),
        "global_max": int(comm.allreduce(value, op=MPI.MAX)),
    }


class FullspaceAdaptiveCoarse:
    """Build owner-local ``AZ`` and small coarse algebra from an exact action."""

    def __init__(
        self,
        basis: Any,
        physical_action: Any,
        full_vector_factory: Callable[[], PETSc.Vec],
    ) -> None:
        if basis is None or physical_action is None:
            raise ValueError("coarse data requires a basis and physical action")
        if basis.audit["construction_workspace_released"] is not True:
            raise RuntimeError("adaptive coarse requires released basis workspace")
        z = basis.columns
        if z.ndim != 2 or not np.iscomplexobj(z):
            raise ValueError("basis columns must be a complex two-dimensional array")
        if z.flags.writeable:
            raise ValueError("basis columns must be a read-only owner-local view")
        self._basis = basis
        self._physical_action = physical_action
        self._vector_factory = full_vector_factory
        self._z = z
        self._comm = basis.comm
        self._az: np.ndarray | None = None
        self._e: np.ndarray | None = None
        self._metadata: np.ndarray | None = None
        self._input: PETSc.Vec | None = None
        self._output: PETSc.Vec | None = None
        self._repeat: PETSc.Vec | None = None
        self._audit: dict[str, Any] = {}
        self._destroyed = False

    @property
    def z(self) -> np.ndarray:
        return self._z

    @property
    def az(self) -> np.ndarray:
        if self._az is None:
            raise RuntimeError("coarse data has not been built")
        return self._az

    @property
    def e(self) -> np.ndarray:
        if self._e is None:
            raise RuntimeError("coarse data has not been built")
        return self._e

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(self._audit)

    def _release_owned(self) -> None:
        for name in ("_input", "_output", "_repeat"):
            vector = getattr(self, name)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        self._az = None
        self._e = None
        self._metadata = None
        self._audit = {}

    def _set_owned_values(self, vector: PETSc.Vec, values: np.ndarray) -> None:
        with vector.localForm() as local:
            local.set(0.0)
            local.array_w[: values.size] = values
        vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )

    @staticmethod
    def _owned_values(vector: PETSc.Vec, owned_rows: int) -> np.ndarray:
        return vector.getArray(readonly=True)[: int(owned_rows)]

    def build(self) -> None:
        if self._destroyed:
            raise RuntimeError("coarse data has been destroyed")
        self._release_owned()
        owned_rows, rank = map(int, self._z.shape)
        if rank < 1:
            raise ValueError("coarse basis must contain at least one column")
        try:
            self._input = self._vector_factory()
            self._output = self._vector_factory()
            self._repeat = self._vector_factory()
            self._az = np.empty_like(self._z, order="C")
            repeat_difference_sq = 0.0
            repeat_reference_sq = 0.0
            for column in range(rank):
                self._set_owned_values(
                    self._input, self._z[:, column]
                )
                self._physical_action.apply(self._input, self._output)
                output_values = self._owned_values(self._output, owned_rows)
                self._az[:, column] = output_values
                if not np.all(np.isfinite(output_values)):
                    raise RuntimeError("physical action produced non-finite AZ")
                self._physical_action.apply(self._input, self._repeat)
                repeat_values = self._owned_values(self._repeat, owned_rows)
                difference = repeat_values - output_values
                repeat_difference_sq += float(
                    np.vdot(difference, difference).real
                )
                repeat_reference_sq += float(
                    np.vdot(output_values, output_values).real
                )
            repeat_difference_sq = float(
                self._comm.allreduce(repeat_difference_sq, op=MPI.SUM)
            )
            repeat_reference_sq = float(
                self._comm.allreduce(repeat_reference_sq, op=MPI.SUM)
            )
            repeat_relative = float(
                np.sqrt(repeat_difference_sq)
                / max(np.sqrt(repeat_reference_sq), np.finfo(float).tiny)
            )
            if not np.isfinite(repeat_relative) or repeat_relative > 1.0e-11:
                raise RuntimeError("coarse AZ repeat identity exceeds 1e-11")
            self._az.flags.writeable = False

            z_gram = np.asarray(
                self._comm.allreduce(
                    self._z.conj().T @ self._z,
                    op=MPI.SUM,
                ),
                dtype=np.complex128,
            )
            z_orthogonality_defect = float(
                np.linalg.norm(z_gram - np.eye(rank, dtype=np.complex128))
            )
            if not np.isfinite(z_orthogonality_defect) or z_orthogonality_defect > 1.0e-10:
                raise RuntimeError("coarse basis orthogonality defect exceeds 1e-10")

            self._e = np.asarray(
                self._comm.allreduce(
                    self._z.conj().T @ self._az,
                    op=MPI.SUM,
                ),
                dtype=np.complex128,
            )
            if not np.all(np.isfinite(self._e)):
                raise RuntimeError("coarse E contains non-finite values")
            self._e.flags.writeable = False
            condition = float(np.linalg.cond(self._e))
            if not np.isfinite(condition) or condition > 1.0e12:
                raise RuntimeError("coarse E condition number exceeds 1e12")
            hermitian_defect = float(
                np.linalg.norm(self._e - self._e.conj().T)
                / max(np.linalg.norm(self._e), np.finfo(float).tiny)
            )

            q_raw = np.arange(1, rank + 1, dtype=np.complex128)
            q_raw += 1j * np.arange(rank, 0, -1, dtype=np.float64)
            q = q_raw / np.linalg.norm(q_raw)
            input_values = self._input.getArray()[:owned_rows]
            np.matmul(self._z, q, out=input_values)
            self._input.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            self._physical_action.apply(self._input, self._output)
            physical_values = self._owned_values(self._output, owned_rows)
            np.matmul(self._az, q, out=input_values)
            consistency_difference = physical_values - input_values
            consistency_difference_sq = float(
                self._comm.allreduce(
                    np.vdot(consistency_difference, consistency_difference).real,
                    op=MPI.SUM,
                )
            )
            consistency_reference_sq = float(
                self._comm.allreduce(
                    np.vdot(physical_values, physical_values).real,
                    op=MPI.SUM,
                )
            )
            consistency_relative = float(
                np.sqrt(consistency_difference_sq)
                / max(np.sqrt(consistency_reference_sq), np.finfo(float).tiny)
            )
            if not np.isfinite(consistency_relative) or consistency_relative > 1.0e-11:
                raise RuntimeError("coarse physical consistency exceeds 1e-11")

            self._metadata = np.asarray((owned_rows, rank), dtype=np.int64)
            z_bytes = _byte_stats(self._comm, self._z.nbytes)
            az_bytes = _byte_stats(self._comm, self._az.nbytes)
            e_bytes = _byte_stats(self._comm, self._e.nbytes)
            metadata_bytes = _byte_stats(self._comm, self._metadata.nbytes)
            retained_global = sum(
                item["global_sum"]
                for item in (z_bytes, az_bytes, e_bytes, metadata_bytes)
            )
            work_bytes = sum(
                int(vector.getArray(readonly=True).nbytes)
                for vector in (self._input, self._output, self._repeat)
            )
            work_stats = _byte_stats(self._comm, work_bytes)
            retained_global += work_stats["global_sum"]
            z_az_global = z_bytes["global_sum"] + az_bytes["global_sum"]
            if rank == 64 and z_az_global > COARSE_RANK64_Z_AZ_LIMIT_BYTES:
                raise RuntimeError("rank-64 Z+AZ retained bytes exceed hard limit")
            if retained_global > COARSE_TOTAL_RETAINED_LIMIT_BYTES:
                raise RuntimeError("coarse retained bytes exceed hard limit")
            self._audit = {
                "schema": "fullspace.adaptive-coarse.v1",
                "rank": rank,
                "physical_action_apply_count": int(2 * rank + 1),
                "z_orthogonality_defect": z_orthogonality_defect,
                "az_repeat_relative_frobenius": repeat_relative,
                "e_condition_number": condition,
                "e_hermitian_relative_defect": hermitian_defect,
                "physical_consistency_relative": consistency_relative,
                "small_numeric_collective": "scalars_and_r_by_r_allreduce_only",
                "numeric_allgather": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "factor_materialized": False,
                "retained_z_bytes": z_bytes,
                "retained_az_bytes": az_bytes,
                "retained_e_bytes": e_bytes,
                "retained_metadata_bytes": metadata_bytes,
                "work_vector_bytes": work_stats,
                "retained_coarse_bytes_global_sum": int(retained_global),
                "work_vector_bytes_provenance": "exact_PETSc_local_array_nbytes",
                "rank64_z_az_hard_limit_bytes": COARSE_RANK64_Z_AZ_LIMIT_BYTES,
                "total_coarse_retained_hard_limit_bytes": COARSE_TOTAL_RETAINED_LIMIT_BYTES,
            }
        except Exception:
            self._release_owned()
            raise

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._release_owned()


__all__ = (
    "COARSE_RANK64_Z_AZ_LIMIT_BYTES",
    "COARSE_TOTAL_RETAINED_LIMIT_BYTES",
    "FullspaceAdaptiveCoarse",
)
