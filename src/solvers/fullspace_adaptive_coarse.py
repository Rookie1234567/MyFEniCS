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

from .fullspace_trace_harmonic_distributed import D2_RANK_PREFIXES


COARSE_RANK64_Z_AZ_LIMIT_BYTES = 355_946_496
COARSE_TOTAL_RETAINED_LIMIT_BYTES = 424_000_000


def _byte_stats(comm: Any, local_bytes: int) -> dict[str, int]:
    value = int(local_bytes)
    return {
        "local": value,
        "global_sum": int(comm.allreduce(value, op=MPI.SUM)),
        "global_max": int(comm.allreduce(value, op=MPI.MAX)),
    }


def _deterministic_q(rank: int) -> np.ndarray:
    q = np.arange(1, int(rank) + 1, dtype=np.complex128)
    q += 1j * np.arange(int(rank), 0, -1, dtype=np.float64)
    return q / np.linalg.norm(q)


def _bitwise_equal(left: np.ndarray, right: np.ndarray) -> bool:
    return bool(
        np.array_equal(left.view(np.uint8), right.view(np.uint8))
    )


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
        self._repeat_difference_sq_by_column: np.ndarray | None = None
        self._repeat_reference_sq_by_column: np.ndarray | None = None
        self._repeat_exact_by_column: tuple[bool, ...] = ()
        self._prefix_cache: dict[int, Mapping[str, Any]] = {}
        self._physical_action_apply_count = 0
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
        self._repeat_difference_sq_by_column = None
        self._repeat_reference_sq_by_column = None
        self._repeat_exact_by_column = ()
        self._prefix_cache = {}
        self._physical_action_apply_count = 0
        self._audit = {}

    def _set_owned_values(self, vector: PETSc.Vec, values: np.ndarray) -> None:
        owned_rows = int(self._z.shape[0])
        if int(values.size) != owned_rows:
            raise RuntimeError(
                "basis column does not match physical Vec owned rows: "
                f"values={int(values.size)}, owned_rows={owned_rows}"
            )
        if int(vector.getLocalSize()) != owned_rows:
            raise RuntimeError(
                "physical Vec local size does not match basis row order: "
                f"vec={int(vector.getLocalSize())}, owned_rows={owned_rows}"
            )
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

    def _prefix_audit_for(self, prefix: int) -> Mapping[str, Any]:
        if self._az is None or self._e is None:
            raise RuntimeError("coarse data has not been built")
        if self._input is None or self._output is None or self._repeat is None:
            raise RuntimeError("coarse work vectors are unavailable")
        owned_rows, rank = map(int, self._z.shape)
        prefix = int(prefix)
        if prefix < 1 or prefix > rank:
            raise ValueError("coarse prefix is outside the constructed rank")
        cached = self._prefix_cache.get(prefix)
        if cached is not None:
            return cached

        z_prefix = self._z[:, :prefix]
        az_prefix = self._az[:, :prefix]
        z_gram = np.asarray(
            self._comm.allreduce(z_prefix.conj().T @ z_prefix, op=MPI.SUM),
            dtype=np.complex128,
        )
        z_orthogonality_defect = float(
            np.linalg.norm(z_gram - np.eye(prefix, dtype=np.complex128))
        )
        if (
            not np.isfinite(z_orthogonality_defect)
            or z_orthogonality_defect > 1.0e-10
        ):
            raise RuntimeError(
                "coarse basis orthogonality gate failed: "
                f"value={z_orthogonality_defect:.17g}, limit=1e-10"
            )

        if prefix == rank:
            e_prefix = self._e
        else:
            e_prefix = np.asarray(
                self._comm.allreduce(
                    z_prefix.conj().T @ az_prefix,
                    op=MPI.SUM,
                ),
                dtype=np.complex128,
            )
        if not np.all(np.isfinite(e_prefix)):
            raise RuntimeError(
                "coarse prefix E finite gate failed: value=non-finite"
            )
        e_leading = self._e[:prefix, :prefix]
        e_prefix_leading_difference = e_prefix - e_leading
        e_prefix_leading_relative = float(
            np.linalg.norm(e_prefix_leading_difference)
            / max(np.linalg.norm(e_leading), np.finfo(float).tiny)
        )
        if (
            not np.isfinite(e_prefix_leading_relative)
            or e_prefix_leading_relative > 1.0e-12
        ):
            raise RuntimeError(
                "coarse prefix E identity gate failed: "
                f"value={e_prefix_leading_relative:.17g}, limit=1e-12"
            )
        e_prefix_leading_exact = _bitwise_equal(e_prefix, e_leading)
        condition = float(np.linalg.cond(e_prefix))
        if not np.isfinite(condition) or condition > 1.0e12:
            raise RuntimeError(
                "coarse prefix E condition gate failed: "
                f"value={condition:.17g}, limit=1e12"
            )
        hermitian_defect = float(
            np.linalg.norm(e_prefix - e_prefix.conj().T)
            / max(np.linalg.norm(e_prefix), np.finfo(float).tiny)
        )

        difference_sq = self._repeat_difference_sq_by_column
        reference_sq = self._repeat_reference_sq_by_column
        exact_by_column = self._repeat_exact_by_column
        if difference_sq is None or reference_sq is None:
            raise RuntimeError("coarse repeat facts are unavailable")
        repeat_difference_sq = float(np.sum(difference_sq[:prefix]))
        repeat_reference_sq = float(np.sum(reference_sq[:prefix]))
        repeat_relative = float(
            np.sqrt(repeat_difference_sq)
            / max(np.sqrt(repeat_reference_sq), np.finfo(float).tiny)
        )
        repeat_exact = bool(all(exact_by_column[:prefix]))
        if not repeat_exact:
            raise RuntimeError(
                "coarse AZ repeat exact gate failed: "
                f"exact={repeat_exact}, relative={repeat_relative:.17g}, "
                "limit=1e-11"
            )
        if not np.isfinite(repeat_relative) or repeat_relative > 1.0e-11:
            raise RuntimeError(
                "coarse AZ repeat relative gate failed: "
                f"value={repeat_relative:.17g}, limit=1e-11"
            )

        q = _deterministic_q(prefix)
        input_values = self._input.getArray()[:owned_rows]
        np.matmul(z_prefix, q, out=input_values)
        self._input.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._physical_action.apply(self._input, self._output)
        self._physical_action_apply_count += 1
        physical_values = self._owned_values(self._output, owned_rows)
        np.matmul(az_prefix, q, out=input_values)
        input_values -= physical_values
        consistency_difference_sq = float(
            self._comm.allreduce(
                np.vdot(input_values, input_values).real,
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
        if (
            not np.isfinite(consistency_relative)
            or consistency_relative > 1.0e-11
        ):
            raise RuntimeError(
                "coarse physical consistency gate failed: "
                f"value={consistency_relative:.17g}, limit=1e-11"
            )

        finite = bool(
            np.all(np.isfinite(z_prefix))
            and np.all(np.isfinite(az_prefix))
            and np.all(np.isfinite(e_prefix))
            and np.isfinite(consistency_relative)
        )
        if not finite:
            raise RuntimeError(
                "coarse prefix finite gate failed: value=non-finite"
            )

        if self._metadata is None:
            raise RuntimeError("coarse metadata is unavailable")
        resident_z_bytes = _byte_stats(self._comm, int(self._z.nbytes))
        resident_az_bytes = _byte_stats(self._comm, int(self._az.nbytes))
        resident_e_bytes = _byte_stats(self._comm, int(self._e.nbytes))
        logical_prefix_z_bytes = (
            resident_z_bytes
            if prefix == rank
            else _byte_stats(self._comm, int(z_prefix.nbytes))
        )
        logical_prefix_az_bytes = (
            resident_az_bytes
            if prefix == rank
            else _byte_stats(self._comm, int(az_prefix.nbytes))
        )
        logical_prefix_e_bytes = (
            resident_e_bytes
            if prefix == rank
            else _byte_stats(
                self._comm,
                int(prefix * prefix * np.dtype(np.complex128).itemsize),
            )
        )
        metadata_bytes = _byte_stats(self._comm, int(self._metadata.nbytes))
        work_bytes = sum(
            int(vector.getArray(readonly=True).nbytes)
            for vector in (self._input, self._output, self._repeat)
        )
        work_stats = _byte_stats(self._comm, work_bytes)
        resident_global = sum(
            item["global_sum"]
            for item in (
                resident_z_bytes,
                resident_az_bytes,
                resident_e_bytes,
                metadata_bytes,
                work_stats,
            )
        )
        logical_prefix_global = sum(
            item["global_sum"]
            for item in (
                logical_prefix_z_bytes,
                logical_prefix_az_bytes,
                logical_prefix_e_bytes,
                metadata_bytes,
                work_stats,
            )
        )
        resident_z_az_global = (
            resident_z_bytes["global_sum"]
            + resident_az_bytes["global_sum"]
        )
        if rank == 64 and resident_z_az_global > COARSE_RANK64_Z_AZ_LIMIT_BYTES:
            raise RuntimeError(
                "rank-64 resident Z+AZ memory gate failed: "
                f"value={resident_z_az_global} B, "
                f"limit={COARSE_RANK64_Z_AZ_LIMIT_BYTES} B"
            )
        if resident_global > COARSE_TOTAL_RETAINED_LIMIT_BYTES:
            raise RuntimeError(
                "resident coarse memory gate failed: "
                f"value={resident_global} B, "
                f"limit={COARSE_TOTAL_RETAINED_LIMIT_BYTES} B"
            )

        result = {
            "prefix": prefix,
            "finite": finite,
            "z_orthogonality_defect": z_orthogonality_defect,
            "az_repeat_relative_frobenius": repeat_relative,
            "az_repeat_exact": repeat_exact,
            "az_repeat_exact_by_column": tuple(exact_by_column[:prefix]),
            "az_repeat_difference_sq": repeat_difference_sq,
            "az_repeat_reference_sq": repeat_reference_sq,
            "e_prefix_leading_relative": e_prefix_leading_relative,
            "e_prefix_leading_exact": e_prefix_leading_exact,
            "e_condition_number": condition,
            "e_hermitian_relative_defect": hermitian_defect,
            "physical_consistency_relative": consistency_relative,
            "logical_prefix_z_bytes": logical_prefix_z_bytes,
            "logical_prefix_az_bytes": logical_prefix_az_bytes,
            "logical_prefix_e_bytes": logical_prefix_e_bytes,
            "logical_prefix_bytes_provenance": "derived_exact_array_size",
            "logical_prefix_coarse_total_global_sum": int(logical_prefix_global),
            "resident_z_bytes": resident_z_bytes,
            "resident_az_bytes": resident_az_bytes,
            "resident_e_bytes": resident_e_bytes,
            "resident_metadata_bytes": metadata_bytes,
            "resident_work_vector_bytes": work_stats,
            "resident_coarse_total_global_sum": int(resident_global),
            "resident_bytes_provenance": "exact_current_retained_objects",
            "retained_z_bytes": resident_z_bytes,
            "retained_az_bytes": resident_az_bytes,
            "retained_e_bytes": resident_e_bytes,
            "retained_metadata_bytes": metadata_bytes,
            "work_vector_bytes": work_stats,
            "retained_coarse_bytes_global_sum": int(resident_global),
            "rank64_z_az_hard_limit_bytes": COARSE_RANK64_Z_AZ_LIMIT_BYTES,
            "total_coarse_retained_hard_limit_bytes": COARSE_TOTAL_RETAINED_LIMIT_BYTES,
            "small_numeric_collective": "scalars_and_r_by_r_allreduce_only",
        }
        readonly = MappingProxyType(result)
        self._prefix_cache[prefix] = readonly
        return readonly

    def _prefix_audits_for(
        self, prefixes: tuple[int, ...]
    ) -> tuple[Mapping[str, Any], ...]:
        rank = int(self._z.shape[1])
        ordered = tuple(int(prefix) for prefix in prefixes)
        if ordered != tuple(sorted(set(ordered))):
            raise ValueError("coarse prefixes must be sorted and unique")
        if any(prefix < 1 or prefix > rank for prefix in ordered):
            raise ValueError("coarse prefix is outside the constructed rank")
        audits = tuple(self._prefix_audit_for(prefix) for prefix in ordered)
        if self._audit:
            self._audit["physical_action_apply_count"] = int(
                self._physical_action_apply_count
            )
            self._audit["prefix_audits"] = tuple(
                self._prefix_cache[prefix]
                for prefix in sorted(self._prefix_cache)
            )
        return audits

    def prefix_audit(self) -> tuple[Mapping[str, Any], ...]:
        """Evaluate the fixed D2 rank ladder without rebuilding ``Z``."""

        prefixes = tuple(
            prefix for prefix in D2_RANK_PREFIXES if prefix <= self._z.shape[1]
        )
        return self._prefix_audits_for(prefixes)

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
            local_difference_sq = np.zeros(rank, dtype=np.float64)
            local_reference_sq = np.zeros(rank, dtype=np.float64)
            local_exact = []
            for column in range(rank):
                self._set_owned_values(self._input, self._z[:, column])
                self._physical_action.apply(self._input, self._output)
                self._physical_action_apply_count += 1
                output_values = self._owned_values(self._output, owned_rows)
                self._az[:, column] = output_values
                if not np.all(np.isfinite(output_values)):
                    raise RuntimeError(
                        "physical action AZ finite gate failed: value=non-finite"
                    )
                self._physical_action.apply(self._input, self._repeat)
                self._physical_action_apply_count += 1
                repeat_values = self._repeat.getArray()[:owned_rows]
                local_exact.append(_bitwise_equal(repeat_values, output_values))
                repeat_values -= output_values
                local_difference_sq[column] = float(
                    np.vdot(repeat_values, repeat_values).real
                )
                local_reference_sq[column] = float(
                    np.vdot(output_values, output_values).real
                )
            self._repeat_difference_sq_by_column = np.asarray(
                self._comm.allreduce(local_difference_sq, op=MPI.SUM),
                dtype=np.float64,
            )
            self._repeat_reference_sq_by_column = np.asarray(
                self._comm.allreduce(local_reference_sq, op=MPI.SUM),
                dtype=np.float64,
            )
            self._repeat_exact_by_column = tuple(
                bool(self._comm.allreduce(flag, op=MPI.LAND))
                for flag in local_exact
            )
            self._az.flags.writeable = False
            self._e = np.asarray(
                self._comm.allreduce(
                    self._z.conj().T @ self._az,
                    op=MPI.SUM,
                ),
                dtype=np.complex128,
            )
            if not np.all(np.isfinite(self._e)):
                raise RuntimeError("coarse E finite gate failed: value=non-finite")
            self._e.flags.writeable = False
            self._metadata = np.asarray((owned_rows, rank), dtype=np.int64)
            full_prefix = self._prefix_audit_for(rank)
            self._audit = {
                "schema": "fullspace.adaptive-coarse.v1",
                "rank": rank,
                "basis_row_order": self._basis.audit.get(
                    "row_order", "canonical_owner_local_order"
                ),
                "basis_physical_owned_rows": self._basis.audit.get(
                    "physical_owned_rows", owned_rows
                ),
                "physical_action_apply_count": int(
                    self._physical_action_apply_count
                ),
                "az_repeat_exact": full_prefix["az_repeat_exact"],
                "az_repeat_exact_by_column": self._repeat_exact_by_column,
                "az_repeat_difference_sq_by_column": tuple(
                    float(value)
                    for value in self._repeat_difference_sq_by_column
                ),
                "az_repeat_reference_sq_by_column": tuple(
                    float(value)
                    for value in self._repeat_reference_sq_by_column
                ),
                "z_orthogonality_defect": full_prefix[
                    "z_orthogonality_defect"
                ],
                "az_repeat_relative_frobenius": full_prefix[
                    "az_repeat_relative_frobenius"
                ],
                "e_condition_number": full_prefix["e_condition_number"],
                "e_hermitian_relative_defect": full_prefix[
                    "e_hermitian_relative_defect"
                ],
                "physical_consistency_relative": full_prefix[
                    "physical_consistency_relative"
                ],
                "prefix_audits": (full_prefix,),
                "small_numeric_collective": "scalars_and_r_by_r_allreduce_only",
                "numeric_allgather": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "factor_materialized": False,
                "resident_z_bytes": full_prefix["resident_z_bytes"],
                "resident_az_bytes": full_prefix["resident_az_bytes"],
                "resident_e_bytes": full_prefix["resident_e_bytes"],
                "resident_metadata_bytes": full_prefix[
                    "resident_metadata_bytes"
                ],
                "resident_work_vector_bytes": full_prefix[
                    "resident_work_vector_bytes"
                ],
                "resident_coarse_total_global_sum": full_prefix[
                    "resident_coarse_total_global_sum"
                ],
                "retained_z_bytes": full_prefix["retained_z_bytes"],
                "retained_az_bytes": full_prefix["retained_az_bytes"],
                "retained_e_bytes": full_prefix["retained_e_bytes"],
                "retained_metadata_bytes": full_prefix[
                    "retained_metadata_bytes"
                ],
                "work_vector_bytes": full_prefix["work_vector_bytes"],
                "retained_coarse_bytes_global_sum": full_prefix[
                    "retained_coarse_bytes_global_sum"
                ],
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
