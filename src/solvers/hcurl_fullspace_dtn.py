"""Research-only matrix-free full-space 80-mode DtN action.

The carrier stores only owner-local sparse surface functionals.  The fixed
non-condensed auxiliary block is the identity, so the forward action is
``-C @ D`` and auxiliary recovery for zero auxiliary right-hand side is
``-D @ u``.  No C/D PETSc matrix, augmented matrix, trace operator, or global
FE-sized numeric gather is created here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

M6_FULLSPACE_DTN_MODE_COUNT = 80
M6_RETAINED_PLUS_WORK_LIMIT_BYTES = 150_000_000
_MODE_IDENTITY_FIELDS = frozenset(
    {
        "schema",
        "mode_index",
        "side",
        "m",
        "n",
        "polarization",
        "alpha",
        "gamma",
        "beta",
        "k_vector",
        "e_vector",
        "power_per_unit_amplitude",
        "rayleigh_warning",
        "projection_denominator",
        "traction_vector",
        "refractive_index",
        "vertical_sign",
        "h_vector",
        "electric_tangential_norm_sq",
        "propagating",
    }
)

__all__ = (
    "FullspaceDtnModeEntries",
    "FullspaceDtnCarrier",
    "FullspaceDtnAction",
    "M6_FULLSPACE_DTN_MODE_COUNT",
    "M6_RETAINED_PLUS_WORK_LIMIT_BYTES",
    "build_fullspace_dtn_carrier_from_surface",
    "build_fullspace_dtn_action",
)


def _readonly_array(values: Any, dtype: np.dtype[Any]) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(values, dtype=dtype))
    array.flags.writeable = False
    return array


def _jsonable_identity(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable_identity(value.item())
    if isinstance(value, complex):
        if not np.isfinite(value.real) or not np.isfinite(value.imag):
            raise ValueError("DtN mode identity contains a non-finite complex value")
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("DtN mode identity contains a non-finite float")
        return float(value)
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable_identity(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_jsonable_identity(item) for item in value]
    raise TypeError(f"unsupported DtN mode identity value: {type(value).__name__}")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable_identity(value),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _byte_stats(comm: MPI.Intracomm, local_bytes: int) -> dict[str, int]:
    local = int(local_bytes)
    return {
        "local": local,
        "global_sum": int(comm.allreduce(local, op=MPI.SUM)),
        "global_max": int(comm.allreduce(local, op=MPI.MAX)),
    }


def _sparse_entries(
    rows: Any,
    values: Any,
    *,
    owned_start: int,
    owned_end: int,
) -> tuple[np.ndarray, np.ndarray]:
    row_array = np.asarray(rows, dtype=PETSc.IntType).reshape(-1)
    value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
    if row_array.shape != value_array.shape:
        raise ValueError("DtN sparse rows and values must have the same shape")
    if not np.all(np.isfinite(value_array)):
        raise ValueError("DtN sparse values must be finite")
    if row_array.size:
        if int(row_array.min()) < int(owned_start) or int(row_array.max()) >= int(
            owned_end
        ):
            raise ValueError("DtN sparse rows must be locally owned")
        order = np.argsort(row_array, kind="stable")
        row_array = row_array[order]
        value_array = value_array[order]
        if np.any(row_array[1:] == row_array[:-1]):
            raise ValueError("DtN sparse rows must be unique")
    return _readonly_array(row_array, np.dtype(PETSc.IntType)), _readonly_array(
        value_array, np.dtype(np.complex128)
    )


def _combine_exact_entries(
    component_entries: Sequence[tuple[np.ndarray, np.ndarray]],
    coefficients: Sequence[complex],
    *,
    owned_start: int,
    owned_end: int,
) -> tuple[np.ndarray, np.ndarray]:
    row_parts: list[np.ndarray] = []
    value_parts: list[np.ndarray] = []
    for (rows, values), coefficient in zip(component_entries, coefficients, strict=True):
        if len(rows) == 0 or complex(coefficient) == 0.0:
            continue
        row_parts.append(np.asarray(rows, dtype=PETSc.IntType))
        value_parts.append(
            complex(coefficient) * np.asarray(values, dtype=np.complex128)
        )
    if not row_parts:
        return _sparse_entries(
            np.empty(0, dtype=PETSc.IntType),
            np.empty(0, dtype=np.complex128),
            owned_start=owned_start,
            owned_end=owned_end,
        )
    rows = np.concatenate(row_parts).astype(PETSc.IntType, copy=False)
    values = np.concatenate(value_parts).astype(np.complex128, copy=False)
    order = np.argsort(rows, kind="mergesort")
    rows = rows[order]
    values = values[order]
    unique_rows, first = np.unique(rows, return_index=True)
    values = np.add.reduceat(values, first)
    keep = values != 0.0
    return _sparse_entries(
        unique_rows[keep],
        values[keep],
        owned_start=owned_start,
        owned_end=owned_end,
    )


@dataclass(frozen=True)
class FullspaceDtnModeEntries:
    """One fixed-mode owner-local C/D functional pair."""

    mode_key: tuple[Any, ...]
    c_rows: np.ndarray
    c_values: np.ndarray
    d_rows: np.ndarray
    d_values: np.ndarray
    mode_identity: Mapping[str, Any] | None = None


class FullspaceDtnCarrier:
    """Immutable owner-local sparse carrier for the fixed identity-H block."""

    def __init__(
        self,
        entries: Sequence[FullspaceDtnModeEntries],
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        slave_rows: Any = (),
        expected_mode_count: int | None = None,
        comm: MPI.Intracomm | None = None,
    ) -> None:
        self._global_rows = int(global_rows)
        self._owned_start, self._owned_end = map(int, ownership_range)
        self._comm = MPI.COMM_SELF if comm is None else comm
        if self._global_rows <= 0 or self._owned_end < self._owned_start:
            raise ValueError("DtN carrier row identity is invalid")
        if self._owned_start < 0 or self._owned_end > self._global_rows:
            raise ValueError("DtN carrier ownership range is invalid")
        if expected_mode_count is not None and len(entries) != int(expected_mode_count):
            raise ValueError("DtN carrier mode count differs from the fixed contract")
        if not entries:
            raise ValueError("DtN carrier requires at least one mode")
        slave_array = np.unique(np.asarray(slave_rows, dtype=PETSc.IntType).reshape(-1))
        if slave_array.size and (
            int(slave_array.min()) < self._owned_start
            or int(slave_array.max()) >= self._owned_end
        ):
            raise ValueError("DtN slave rows must be locally owned")
        self._slave_rows = _readonly_array(slave_array, np.dtype(PETSc.IntType))
        normalized: list[FullspaceDtnModeEntries] = []
        seen_keys: set[tuple[Any, ...]] = set()
        manifest_modes: list[Any] = []
        mode_indices: list[int] = []
        seen_identity_bytes: set[bytes] = set()
        for item in entries:
            if not isinstance(item, FullspaceDtnModeEntries):
                raise TypeError("DtN carrier entries have an invalid type")
            if item.mode_key in seen_keys:
                raise ValueError("DtN mode identities are not unique")
            seen_keys.add(item.mode_key)
            if item.mode_identity is None or not isinstance(item.mode_identity, Mapping):
                raise ValueError("DtN mode identity is required")
            missing_identity_fields = _MODE_IDENTITY_FIELDS.difference(
                item.mode_identity
            )
            if missing_identity_fields:
                raise ValueError(
                    "DtN mode identity is missing fields: "
                    + ",".join(sorted(missing_identity_fields))
                )
            identity = dict(item.mode_identity)
            mode_index = identity["mode_index"]
            if (
                isinstance(mode_index, bool)
                or not isinstance(mode_index, (int, np.integer))
                or not 0 <= int(mode_index) < len(entries)
                or int(mode_index) in mode_indices
            ):
                raise ValueError("DtN mode indices must be a unique 0..N-1 sequence")
            mode_indices.append(int(mode_index))
            identity_bytes = _canonical_json_bytes(identity)
            if identity_bytes in seen_identity_bytes:
                raise ValueError("DtN canonical mode identities are not unique")
            seen_identity_bytes.add(identity_bytes)
            manifest_modes.append(json.loads(identity_bytes))
            c_rows, c_values = _sparse_entries(
                item.c_rows,
                item.c_values,
                owned_start=self._owned_start,
                owned_end=self._owned_end,
            )
            d_rows, d_values = _sparse_entries(
                item.d_rows,
                item.d_values,
                owned_start=self._owned_start,
                owned_end=self._owned_end,
            )
            if np.intersect1d(c_rows, self._slave_rows).size:
                raise ValueError("DtN output carrier contains a slave row")
            if np.intersect1d(d_rows, self._slave_rows).size:
                raise ValueError("DtN input carrier reads a slave row")
            normalized.append(
                FullspaceDtnModeEntries(
                    item.mode_key,
                    c_rows,
                    c_values,
                    d_rows,
                    d_values,
                )
            )
        if sorted(mode_indices) != list(range(len(entries))):
            raise ValueError("DtN mode indices must cover the complete entry order")
        self._entries = tuple(normalized)
        self._mode_keys = tuple(item.mode_key for item in self._entries)
        self._mode_manifest = _canonical_json_bytes(
            {
                "schema": "m6-fullspace-dtn-mode-manifest-v1",
                "mode_count": len(manifest_modes),
                "modes": manifest_modes,
            }
        )
        self._mode_manifest_sha256 = hashlib.sha256(self._mode_manifest).hexdigest()
        numeric_components = {
            "c_rows_bytes": int(sum(item.c_rows.nbytes for item in self._entries)),
            "c_values_bytes": int(sum(item.c_values.nbytes for item in self._entries)),
            "d_rows_bytes": int(sum(item.d_rows.nbytes for item in self._entries)),
            "d_values_bytes": int(sum(item.d_values.nbytes for item in self._entries)),
        }
        components = dict(numeric_components)
        components["mode_manifest_bytes"] = len(self._mode_manifest)
        self._retained_numeric_components = MappingProxyType(numeric_components)
        self._retained_components = MappingProxyType(components)
        self._retained_numeric_bytes = int(sum(numeric_components.values()))
        self._retained_identity_bytes = len(self._mode_manifest)
        self._retained_bytes = self._retained_numeric_bytes + self._retained_identity_bytes
        self._retained_stats = _byte_stats(self._comm, self._retained_bytes)
        self._carrier_work_bytes = int(
            2 * len(self._entries) * np.dtype(np.complex128).itemsize
        )
        self._carrier_work_stats = _byte_stats(self._comm, self._carrier_work_bytes)
        self._retained_plus_work_stats = _byte_stats(
            self._comm,
            self._retained_bytes + self._carrier_work_bytes,
        )

    @property
    def entries(self) -> tuple[FullspaceDtnModeEntries, ...]:
        return self._entries

    @property
    def global_rows(self) -> int:
        return self._global_rows

    @property
    def ownership_range(self) -> tuple[int, int]:
        return self._owned_start, self._owned_end

    @property
    def mode_manifest_bytes(self) -> bytes:
        return self._mode_manifest

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "fine_space": "uncondensed_fullspace",
                "condensation": False,
                "static_condensed_operator_used": False,
                "trace_slab_pc_used": False,
                "global_matrix_materialized": False,
                "augmented_matrix_materialized": False,
                "explicit_C_materialized_count": 0,
                "explicit_D_materialized_count": 0,
                "mode_count": len(self._entries),
                "fixed_H": "identity",
                "mode_manifest_sha256": self._mode_manifest_sha256,
                "mode_manifest_bytes": len(self._mode_manifest),
                "global_rows": self._global_rows,
                "owned_rows": self._owned_end - self._owned_start,
                "ownership_range": [self._owned_start, self._owned_end],
                "slave_rows_owned": int(self._slave_rows.size),
                "slave_row_behavior": {
                    "input_slave_rows_ignored": True,
                    "output_slave_rows_zero": True,
                },
                "retained_components_bytes": dict(self._retained_components),
                "retained_numeric_components_bytes": dict(
                    self._retained_numeric_components
                ),
                "retained_numeric_bytes": self._retained_numeric_bytes,
                "retained_identity_bytes": self._retained_identity_bytes,
                "retained_bytes": self._retained_bytes,
                "retained_bytes_local": self._retained_stats["local"],
                "retained_bytes_global_sum": self._retained_stats["global_sum"],
                "retained_bytes_global_max": self._retained_stats["global_max"],
                "bounded_work_bytes_local": self._carrier_work_stats["local"],
                "bounded_work_bytes_global_sum": self._carrier_work_stats[
                    "global_sum"
                ],
                "bounded_work_bytes_global_max": self._carrier_work_stats[
                    "global_max"
                ],
                "retained_plus_work_local_bytes": self._retained_plus_work_stats[
                    "local"
                ],
                "retained_plus_work_bytes": self._retained_bytes
                + self._carrier_work_bytes,
                "retained_plus_work_global_sum_bytes": self._retained_plus_work_stats[
                    "global_sum"
                ],
                "retained_plus_work_global_max_bytes": self._retained_plus_work_stats[
                    "global_max"
                ],
                "retained_plus_work_limit_bytes": M6_RETAINED_PLUS_WORK_LIMIT_BYTES,
                "retained_plus_work_gate": (
                    self._retained_plus_work_stats["global_sum"]
                    <= M6_RETAINED_PLUS_WORK_LIMIT_BYTES
                ),
                "retained_payload_scope": (
                    "numpy arrays + retained canonical manifest bytes"
                ),
                "python_object_overhead_included": False,
                "petsc_object_overhead_included": False,
                "bounded_work_bytes": self._carrier_work_bytes,
                "ordinary_default": False,
            }
        )


class FullspaceDtnAction:
    """PETSc MatPython forward action with one modal allreduce per apply.

    ``apply_modal_incident_rhs`` writes only the modal correction ``C b``.
    ``compose_physical_rhs`` is the explicit entry point for the complete physical
    RHS, preserving the separately assembled incident traction before adding ``C b``.
    """

    def __init__(self, carrier: FullspaceDtnCarrier, comm: MPI.Intracomm) -> None:
        self.carrier = carrier
        self.comm = comm
        self._local_modal = np.zeros(len(carrier.entries), dtype=np.complex128)
        self._global_modal = np.zeros_like(self._local_modal)
        owned = carrier.ownership_range[1] - carrier.ownership_range[0]
        self._matrix = PETSc.Mat().createPython(
            ((owned, carrier.global_rows), (owned, carrier.global_rows)),
            context=self,
            comm=comm,
        )
        self._matrix.setUp()
        self._work_bytes = int(self._local_modal.nbytes + self._global_modal.nbytes)
        self._work_stats = _byte_stats(comm, self._work_bytes)
        self._retained_plus_work_stats = _byte_stats(
            comm,
            carrier._retained_bytes + self._work_bytes,
        )
        self._apply_count = 0
        self._hermitian_apply_count = 0
        self._destroyed = False

    @property
    def matrix(self) -> PETSc.Mat:
        if self._destroyed:
            raise RuntimeError("DtN action has been destroyed")
        return self._matrix

    def _modal_values(self, source: PETSc.Vec) -> np.ndarray:
        start, end = self.carrier.ownership_range
        source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        if (
            source_values.size != end - start
            or source.getSize() != self.carrier.global_rows
            or tuple(map(int, source.getOwnershipRange())) != (start, end)
        ):
            raise ValueError("DtN source has an incompatible owned/global layout")
        self._local_modal.fill(0.0)
        for index, item in enumerate(self.carrier.entries):
            if item.d_rows.size:
                self._local_modal[index] = np.dot(
                    item.d_values,
                    source_values[item.d_rows - start],
                )
        self.comm.Allreduce(self._local_modal, self._global_modal, op=MPI.SUM)
        return self._global_modal

    def _adjoint_modal_values(self, source: PETSc.Vec) -> np.ndarray:
        start, end = self.carrier.ownership_range
        source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        if (
            source_values.size != end - start
            or source.getSize() != self.carrier.global_rows
            or tuple(map(int, source.getOwnershipRange())) != (start, end)
        ):
            raise ValueError("DtN adjoint source has an incompatible owned/global layout")
        self._local_modal.fill(0.0)
        for index, item in enumerate(self.carrier.entries):
            if item.c_rows.size:
                self._local_modal[index] = np.vdot(
                    item.c_values,
                    source_values[item.c_rows - start],
                )
        self.comm.Allreduce(self._local_modal, self._global_modal, op=MPI.SUM)
        return self._global_modal

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        modal = self._modal_values(source)
        start, end = self.carrier.ownership_range
        target_values = np.asarray(target.getArray(), dtype=np.complex128)
        if (
            target_values.size != end - start
            or target.getSize() != self.carrier.global_rows
            or tuple(map(int, target.getOwnershipRange())) != (start, end)
        ):
            raise ValueError("DtN target has an incompatible owned/global layout")
        target_values.fill(0.0)
        for index, item in enumerate(self.carrier.entries):
            if item.c_rows.size:
                target_values[item.c_rows - start] += -modal[index] * item.c_values
        self._apply_count += 1

    def apply_hermitian(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the exact Euclidean Hermitian adjoint ``-conj(D) C^H``."""

        modal = self._adjoint_modal_values(source)
        start, end = self.carrier.ownership_range
        target_values = np.asarray(target.getArray(), dtype=np.complex128)
        if (
            target_values.size != end - start
            or target.getSize() != self.carrier.global_rows
            or tuple(map(int, target.getOwnershipRange())) != (start, end)
        ):
            raise ValueError("DtN adjoint target has an incompatible owned/global layout")
        target_values.fill(0.0)
        for index, item in enumerate(self.carrier.entries):
            if item.d_rows.size:
                target_values[item.d_rows - start] += (
                    -np.conjugate(item.d_values) * modal[index]
                )
        self._hermitian_apply_count += 1

    def recover_auxiliary(self, source: PETSc.Vec) -> np.ndarray:
        """Return ``a=-D u`` for the fixed ``b_aux=0`` auxiliary convention."""

        return -np.array(self._modal_values(source), dtype=np.complex128, copy=True)

    def apply_modal_incident_rhs(
        self,
        mode_amplitudes: Sequence[complex],
        target: PETSc.Vec,
    ) -> None:
        """Write only the modal correction ``sum_i C_i b_i`` to ``target``."""

        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        if amplitudes.shape != (len(self.carrier.entries),) or not np.all(
            np.isfinite(amplitudes)
        ):
            raise ValueError("DtN physical RHS amplitudes have an invalid layout")
        start, end = self.carrier.ownership_range
        target_values = np.asarray(target.getArray(), dtype=np.complex128)
        if (
            target_values.size != end - start
            or target.getSize() != self.carrier.global_rows
            or tuple(map(int, target.getOwnershipRange())) != (start, end)
        ):
            raise ValueError("DtN physical RHS target has an incompatible layout")
        target_values.fill(0.0)
        for amplitude, item in zip(amplitudes, self.carrier.entries, strict=True):
            if item.c_rows.size:
                target_values[item.c_rows - start] += amplitude * item.c_values

    def compose_physical_rhs(
        self,
        base_incident_traction: PETSc.Vec,
        mode_amplitudes: Sequence[complex],
        target: PETSc.Vec,
    ) -> None:
        """Write the complete physical RHS ``base_incident_traction + C b``."""

        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        start, end = self.carrier.ownership_range
        base_values = np.asarray(
            base_incident_traction.getArray(readonly=True), dtype=np.complex128
        )
        target_values = np.asarray(target.getArray(), dtype=np.complex128)
        if (
            amplitudes.shape != (len(self.carrier.entries),)
            or not np.all(np.isfinite(amplitudes))
            or base_values.size != end - start
            or target_values.size != end - start
            or base_incident_traction.getSize() != self.carrier.global_rows
            or target.getSize() != self.carrier.global_rows
            or tuple(map(int, base_incident_traction.getOwnershipRange()))
            != (start, end)
            or tuple(map(int, target.getOwnershipRange())) != (start, end)
        ):
            raise ValueError("DtN physical RHS inputs have an incompatible layout")
        target_values[:] = base_values
        for amplitude, item in zip(amplitudes, self.carrier.entries, strict=True):
            if item.c_rows.size:
                target_values[item.c_rows - start] += amplitude * item.c_values

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply(source, target)

    def multHermitian(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply_hermitian(source, target)

    @property
    def apply_count(self) -> int:
        return self._apply_count

    @property
    def audit(self) -> Mapping[str, Any]:
        result = dict(self.carrier.audit)
        result.update(
            {
                "bounded_work_bytes": int(
                    self._work_bytes
                ),
                "bounded_work_bytes_local": self._work_bytes,
                "bounded_work_bytes_global_sum": self._work_stats["global_sum"],
                "bounded_work_bytes_global_max": self._work_stats["global_max"],
                "retained_plus_work_local_bytes": self._retained_plus_work_stats[
                    "local"
                ],
                "retained_plus_work_global_sum_bytes": self._retained_plus_work_stats[
                    "global_sum"
                ],
                "retained_plus_work_global_max_bytes": self._retained_plus_work_stats[
                    "global_max"
                ],
                "retained_plus_work_limit_bytes": M6_RETAINED_PLUS_WORK_LIMIT_BYTES,
                "retained_plus_work_gate": (
                    self._retained_plus_work_stats["global_sum"]
                    <= M6_RETAINED_PLUS_WORK_LIMIT_BYTES
                ),
                "apply_count": self._apply_count,
                "hermitian_apply_count": self._hermitian_apply_count,
                "modal_allreduce_count_per_apply": 1,
                "modal_allreduce_count_per_hermitian_apply": 1,
                "fe_sized_allgather": False,
                "matrix_type": "python_action_only",
            }
        )
        return MappingProxyType(result)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if _matrix is None:
            self._matrix.destroy()


def build_fullspace_dtn_action(
    carrier: FullspaceDtnCarrier,
    *,
    comm: MPI.Intracomm,
) -> FullspaceDtnAction:
    """Build the fixed identity-H full-space action after carrier validation."""

    return FullspaceDtnAction(carrier, comm)


def build_fullspace_dtn_carrier_from_surface(
    modes: Sequence[Any],
    surface_assemblers: Mapping[tuple[str, int], Any],
    mpc: Any,
    cfg: Any,
    *,
    expected_mode_count: int = M6_FULLSPACE_DTN_MODE_COUNT,
) -> FullspaceDtnCarrier:
    """Build exact-zero owner-local C/D entries from MPC-aware surface forms."""

    if len(modes) != int(expected_mode_count):
        raise ValueError("M6 full-space DtN requires the fixed 80-mode list")
    from .dtn_port_3d import (
        _assemble_mpc_form_vector,
        _mode_projection_denominator,
        _set_scalar_constant,
        _traction_vector,
    )

    index_map = mpc.function_space.dofmap.index_map
    owned_start = int(index_map.local_range[0])
    owned_end = owned_start + int(index_map.size_local)
    global_rows = int(index_map.size_global)
    owned_slaves = np.asarray(mpc.slaves, dtype=np.int32)
    owned_slaves = owned_slaves[owned_slaves < int(index_map.size_local)]
    slave_rows = np.asarray(
        index_map.local_to_global(owned_slaves), dtype=PETSc.IntType
    )

    component_cache: dict[
        tuple[str, complex, complex, complex], tuple[tuple[np.ndarray, np.ndarray], ...]
    ] = {}

    def exact_component_entries(assembler: Any, mode: Any) -> tuple[np.ndarray, np.ndarray]:
        _set_scalar_constant(assembler.alpha, mode.alpha)
        _set_scalar_constant(assembler.gamma, mode.gamma)
        _set_scalar_constant(assembler.kz, mode.k_vector[2])
        vector = _assemble_mpc_form_vector(assembler.form, mpc)
        try:
            values = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
            start, end = map(int, vector.getOwnershipRange())
            rows = np.arange(start, end, dtype=PETSc.IntType)
            keep = values != 0.0
            return _readonly_array(rows[keep], np.dtype(PETSc.IntType)), _readonly_array(
                values[keep], np.dtype(np.complex128)
            )
        finally:
            vector.destroy()

    entries: list[FullspaceDtnModeEntries] = []
    for index, mode in enumerate(modes):
        component_key = (
            str(mode.side),
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.k_vector[2]),
        )
        components = component_cache.get(component_key)
        if components is None:
            components = (
                exact_component_entries(surface_assemblers[(mode.side, 0)], mode),
                exact_component_entries(surface_assemblers[(mode.side, 1)], mode),
            )
            component_cache[component_key] = components
        ell_rows, ell_values = _combine_exact_entries(
            components,
            (mode.e_vector[0], mode.e_vector[1]),
            owned_start=owned_start,
            owned_end=owned_end,
        )
        traction = _traction_vector(mode, cfg)
        traction_rows, traction_values = _combine_exact_entries(
            components,
            (traction[0], traction[1]),
            owned_start=owned_start,
            owned_end=owned_end,
        )
        denominator = _mode_projection_denominator(mode, cfg)
        if not np.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("DtN mode projection denominator is invalid")
        mode_key = (
            int(index),
            str(mode.side),
            int(mode.m),
            int(mode.n),
            str(mode.polarization),
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.beta),
            tuple(complex(value) for value in mode.k_vector),
            tuple(complex(value) for value in mode.e_vector),
            float(mode.power_per_unit_amplitude),
            bool(mode.rayleigh_warning),
        )
        mode_identity = {
            "schema": "m6-fullspace-dtn-mode-v1",
            "mode_index": int(index),
            "side": str(mode.side),
            "m": int(mode.m),
            "n": int(mode.n),
            "polarization": str(mode.polarization),
            "alpha": complex(mode.alpha),
            "gamma": complex(mode.gamma),
            "beta": complex(mode.beta),
            "k_vector": tuple(complex(value) for value in mode.k_vector),
            "e_vector": tuple(complex(value) for value in mode.e_vector),
            "power_per_unit_amplitude": float(mode.power_per_unit_amplitude),
            "rayleigh_warning": bool(mode.rayleigh_warning),
            "projection_denominator": float(denominator),
            "traction_vector": tuple(complex(value) for value in traction),
            "refractive_index": complex(mode.refractive_index),
            "vertical_sign": int(mode.vertical_sign),
            "h_vector": tuple(complex(value) for value in mode.h_vector),
            "electric_tangential_norm_sq": float(mode.electric_tangential_norm_sq),
            "propagating": bool(mode.propagating),
        }
        entries.append(
            FullspaceDtnModeEntries(
                mode_key,
                traction_rows,
                _readonly_array(-traction_values, np.dtype(np.complex128)),
                ell_rows,
                _readonly_array(-np.conjugate(ell_values) / denominator, np.dtype(np.complex128)),
                mode_identity,
            )
        )
    return FullspaceDtnCarrier(
        entries,
        global_rows=global_rows,
        ownership_range=(owned_start, owned_end),
        slave_rows=slave_rows,
        expected_mode_count=expected_mode_count,
        comm=mpc.function_space.mesh.comm,
    )
