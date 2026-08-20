"""Dynamic owner-local Fourier-DtN action for the current 3D port contract.

The carrier keeps sparse surface functionals and one explicit projection
denominator ``H_i`` per mode.  Applying the action reduces the projection and
coupling in deterministic batches; it never creates numeric C/D matrices or a
FE-sized replicated vector.  Surface functionals are assembled by the
existing MPC-aware port machinery so Floquet phase and H(curl) orientation are
applied exactly once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


FULLSPACE_DTN_PROFILE = "full3d_scalable_v1"
FULLSPACE_DTN_BATCH_SIZE = 8
FULLSPACE_DTN_MANIFEST_SCHEMA = "fullspace-dtn.mode-manifest.v1"

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
        "h_vector",
        "refractive_index",
        "vertical_sign",
        "electric_tangential_norm_sq",
        "power_per_unit_amplitude",
        "propagating",
        "rayleigh_warning",
        "classification",
        "rayleigh_tolerance",
        "projection_denominator",
        "traction_vector",
    }
)


def _readonly(values: Any, dtype: np.dtype[Any]) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(values, dtype=dtype))
    array.flags.writeable = False
    return array


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        if not np.isfinite(value.real) or not np.isfinite(value.imag):
            raise ValueError("mode identity contains a non-finite complex value")
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("mode identity contains a non-finite float")
        return float(value)
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    raise TypeError(f"unsupported mode identity value: {type(value).__name__}")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def classify_port_mode(mode: Any) -> str:
    """Classify one current-tree port mode using the existing mode flags.

    ``near_rayleigh`` is deliberately checked first.  Thus a mode that is
    technically propagating but lies inside the frozen Rayleigh warning band
    is recorded as ``near-cutoff`` rather than silently treated as ordinary
    propagation.
    """

    if bool(mode.rayleigh_warning):
        return "near-cutoff"
    if bool(mode.propagating):
        return "propagating"
    return "evanescent"


def _mode_identity(index: int, mode: Any, cfg: Any, denominator: float) -> dict[str, Any]:
    from .dtn_port_3d import _traction_vector

    return {
        "schema": "fullspace-dtn.mode.v1",
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
        "h_vector": tuple(complex(value) for value in mode.h_vector),
        "refractive_index": complex(mode.refractive_index),
        "vertical_sign": int(mode.vertical_sign),
        "electric_tangential_norm_sq": float(mode.electric_tangential_norm_sq),
        "power_per_unit_amplitude": float(mode.power_per_unit_amplitude),
        "propagating": bool(mode.propagating),
        "rayleigh_warning": bool(mode.rayleigh_warning),
        "classification": classify_port_mode(mode),
        "rayleigh_tolerance": float(cfg.diffraction_rayleigh_tol),
        "projection_denominator": float(denominator),
        "traction_vector": tuple(
            complex(value) for value in _traction_vector(mode, cfg)
        ),
    }


def build_ordered_mode_manifest(
    modes: Sequence[Any], cfg: Any
) -> tuple[tuple[Mapping[str, Any], ...], bytes, str]:
    """Return the ordered physical mode manifest and its content hash."""

    from .dtn_port_3d import _mode_projection_denominator

    if not modes:
        raise ValueError("the dynamic DtN inventory must contain at least one mode")
    rows: list[Mapping[str, Any]] = []
    for index, mode in enumerate(modes):
        denominator = _mode_projection_denominator(mode, cfg)
        if not np.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("DtN projection denominator H must be finite and positive")
        rows.append(_mode_identity(index, mode, cfg, denominator))
    payload = {
        "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
        "profile": FULLSPACE_DTN_PROFILE,
        "mode_count": len(rows),
        "modes": rows,
    }
    encoded = _canonical_json_bytes(payload)
    return tuple(rows), encoded, hashlib.sha256(encoded).hexdigest()


def build_dynamic_mode_inventory(
    cfg: Any,
) -> tuple[tuple[Any, ...], tuple[Mapping[str, Any], ...], str]:
    """Resolve modes from the current physical configuration and hash them."""

    from ..common.modes_3d import outgoing_port_modes_3d

    modes = tuple(outgoing_port_modes_3d(cfg))
    manifest, _encoded, digest = build_ordered_mode_manifest(modes, cfg)
    return modes, manifest, digest


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
        raise ValueError("DtN sparse rows and values must have matching shapes")
    if row_array.size:
        if int(row_array.min()) < owned_start or int(row_array.max()) >= owned_end:
            raise ValueError("DtN sparse rows must be locally owned")
        order = np.argsort(row_array, kind="stable")
        row_array = row_array[order]
        value_array = value_array[order]
        if np.any(row_array[1:] == row_array[:-1]):
            raise ValueError("DtN sparse rows must be unique")
    if not np.all(np.isfinite(value_array)):
        raise ValueError("DtN sparse values must be finite")
    return _readonly(row_array, np.dtype(PETSc.IntType)), _readonly(
        value_array, np.dtype(np.complex128)
    )


@dataclass(frozen=True)
class FullspaceDtnModeFunctional:
    """One owner-local coupling/projection pair and its explicit H weight."""

    mode_key: tuple[Any, ...]
    coupling_rows: np.ndarray
    coupling_values: np.ndarray
    projection_rows: np.ndarray
    projection_values: np.ndarray
    normalization_h: float
    mode_identity: Mapping[str, Any]


class FullspaceDtnCarrier:
    """Immutable dynamic sparse carrier with no explicit C or D matrix."""

    def __init__(
        self,
        entries: Sequence[FullspaceDtnModeFunctional],
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        slave_rows: Any = (),
        batch_size: int = FULLSPACE_DTN_BATCH_SIZE,
        comm: MPI.Intracomm | None = None,
    ) -> None:
        self._comm = MPI.COMM_SELF if comm is None else comm
        self._global_rows = int(global_rows)
        self._owned_start, self._owned_end = map(int, ownership_range)
        if self._global_rows <= 0 or not 0 <= self._owned_start <= self._owned_end:
            raise ValueError("DtN carrier row identity is invalid")
        if self._owned_end > self._global_rows:
            raise ValueError("DtN carrier ownership exceeds global rows")
        if int(batch_size) <= 0:
            raise ValueError("DtN modal batch size must be positive")
        self._batch_size = int(batch_size)
        normalized: list[FullspaceDtnModeFunctional] = []
        seen_keys: set[tuple[Any, ...]] = set()
        seen_identity: set[bytes] = set()
        manifest_rows: list[Mapping[str, Any]] = []
        for index, item in enumerate(entries):
            if not isinstance(item, FullspaceDtnModeFunctional):
                raise TypeError("DtN carrier entries have an invalid type")
            if item.mode_key in seen_keys:
                raise ValueError("DtN mode keys are not unique")
            seen_keys.add(item.mode_key)
            identity = dict(item.mode_identity)
            if _MODE_IDENTITY_FIELDS.difference(identity):
                missing = ",".join(sorted(_MODE_IDENTITY_FIELDS.difference(identity)))
                raise ValueError(f"DtN mode identity is missing fields: {missing}")
            if identity.get("mode_index") != index:
                raise ValueError("DtN mode indices must follow carrier order")
            identity_bytes = _canonical_json_bytes(identity)
            if identity_bytes in seen_identity:
                raise ValueError("DtN mode identities are not unique")
            seen_identity.add(identity_bytes)
            coupling_rows, coupling_values = _sparse_entries(
                item.coupling_rows,
                item.coupling_values,
                owned_start=self._owned_start,
                owned_end=self._owned_end,
            )
            projection_rows, projection_values = _sparse_entries(
                item.projection_rows,
                item.projection_values,
                owned_start=self._owned_start,
                owned_end=self._owned_end,
            )
            h = float(item.normalization_h)
            if not np.isfinite(h) or h <= 0.0:
                raise ValueError("DtN normalization H must be finite and positive")
            normalized.append(
                FullspaceDtnModeFunctional(
                    tuple(item.mode_key),
                    coupling_rows,
                    coupling_values,
                    projection_rows,
                    projection_values,
                    h,
                    MappingProxyType(identity),
                )
            )
            manifest_rows.append(identity)
        if not normalized:
            raise ValueError("DtN carrier requires at least one dynamic mode")
        manifest = {
            "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
            "profile": FULLSPACE_DTN_PROFILE,
            "mode_count": len(manifest_rows),
            "modes": manifest_rows,
        }
        self._entries = tuple(normalized)
        self._mode_manifest = _canonical_json_bytes(manifest)
        self._mode_manifest_sha256 = hashlib.sha256(self._mode_manifest).hexdigest()
        slave_array = np.unique(np.asarray(slave_rows, dtype=PETSc.IntType).reshape(-1))
        if slave_array.size and (
            int(slave_array.min()) < self._owned_start
            or int(slave_array.max()) >= self._owned_end
        ):
            raise ValueError("DtN slave rows must be locally owned")
        self._slave_rows = _readonly(slave_array, np.dtype(PETSc.IntType))
        for item in self._entries:
            if np.intersect1d(item.coupling_rows, self._slave_rows).size:
                raise ValueError("DtN coupling functional intersects a local slave row")
            if np.intersect1d(item.projection_rows, self._slave_rows).size:
                raise ValueError("DtN projection functional intersects a local slave row")
        self._retained_numeric_bytes = int(self._slave_rows.nbytes)
        for item in self._entries:
            self._retained_numeric_bytes += int(
                item.coupling_rows.nbytes
                + item.coupling_values.nbytes
                + item.projection_rows.nbytes
                + item.projection_values.nbytes
                + np.dtype(np.float64).itemsize
            )
        self._retained_identity_bytes = len(self._mode_manifest)
        self._retained_numeric_global_sum = int(
            self._comm.allreduce(self._retained_numeric_bytes, op=MPI.SUM)
        )
        self._retained_numeric_global_max = int(
            self._comm.allreduce(self._retained_numeric_bytes, op=MPI.MAX)
        )

    @property
    def entries(self) -> tuple[FullspaceDtnModeFunctional, ...]:
        return self._entries

    @property
    def mode_manifest_bytes(self) -> bytes:
        return self._mode_manifest

    @property
    def mode_manifest_sha256(self) -> str:
        return self._mode_manifest_sha256

    @property
    def global_rows(self) -> int:
        return self._global_rows

    @property
    def ownership_range(self) -> tuple[int, int]:
        return self._owned_start, self._owned_end

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def comm(self) -> MPI.Intracomm:
        return self._comm

    @property
    def retained_numeric_bytes(self) -> int:
        return self._retained_numeric_bytes

    @property
    def slave_rows(self) -> np.ndarray:
        return self._slave_rows

    @property
    def audit(self) -> Mapping[str, Any]:
        mode_count = len(self._entries)
        h_values = np.asarray(
            [item.normalization_h for item in self._entries], dtype=np.float64
        )
        return MappingProxyType(
            {
                "schema": "fullspace-dtn.carrier.v1",
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": mode_count,
                "batch_size": self._batch_size,
                "batch_count": (mode_count + self._batch_size - 1) // self._batch_size,
                "mode_manifest_sha256": self._mode_manifest_sha256,
                "normalization": "explicit_diagonal_projection_denominator_H",
                "normalization_nonidentity": bool(
                    np.any(np.abs(h_values - 1.0) > 1.0e-14)
                ),
                "normalization_h_min": float(np.min(h_values)),
                "normalization_h_max": float(np.max(h_values)),
                "retained_numeric_bytes_local": self._retained_numeric_bytes,
                "retained_numeric_bytes_global_sum": self._retained_numeric_global_sum,
                "retained_numeric_bytes_global_max": self._retained_numeric_global_max,
                "retained_identity_bytes": self._retained_identity_bytes,
                "owner_local_surface_functionals": True,
                "slave_rows_local": int(self._slave_rows.size),
                "slave_functional_rows_local": 0,
                "slave_functional_rows_global": 0,
                "numeric_allgather": False,
                "explicit_c_matrix_count": 0,
                "explicit_d_matrix_count": 0,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "trace_matrix_materialized": False,
                "ksp_created": False,
                "pde_solved": False,
            }
        )


class FullspaceDtnAction:
    """PETSc MatPython wrapper around the bounded forward DtN action."""

    def __init__(self, carrier: FullspaceDtnCarrier, *, comm: MPI.Intracomm) -> None:
        self.carrier = carrier
        self.comm = comm
        self._local_modal = np.empty(carrier.batch_size, dtype=np.complex128)
        self._global_modal = np.empty_like(self._local_modal)
        owned = carrier.ownership_range[1] - carrier.ownership_range[0]
        self._matrix: PETSc.Mat | None = PETSc.Mat().createPython(
            ((owned, carrier.global_rows), (owned, carrier.global_rows)),
            context=self,
            comm=comm,
        )
        self._matrix.setUp()
        self._apply_count = 0
        self._modal_allreduce_count = 0
        self._apply_modal_allreduce_count = 0
        self._recovery_modal_allreduce_count = 0
        self._destroyed = False
        self._work_bytes = int(self._local_modal.nbytes + self._global_modal.nbytes)
        self._work_global_sum = int(self.comm.allreduce(self._work_bytes, op=MPI.SUM))
        self._work_global_max = int(self.comm.allreduce(self._work_bytes, op=MPI.MAX))

    @property
    def matrix(self) -> PETSc.Mat:
        if self._matrix is None:
            raise RuntimeError("DtN action has been destroyed")
        return self._matrix

    def _vector_values(self, vector: PETSc.Vec, *, writable: bool) -> np.ndarray:
        start, end = self.carrier.ownership_range
        values = np.asarray(
            vector.getArray() if writable else vector.getArray(readonly=True),
            dtype=np.complex128,
        )
        if (
            vector.getSize() != self.carrier.global_rows
            or tuple(map(int, vector.getOwnershipRange())) != (start, end)
            or values.size != end - start
        ):
            raise ValueError("DtN vector has an incompatible global/owned layout")
        return values

    def _modal_batch(
        self,
        source_values: np.ndarray,
        batch_start: int,
        batch_stop: int,
    ) -> np.ndarray:
        start, _end = self.carrier.ownership_range
        count = batch_stop - batch_start
        local = self._local_modal[:count]
        global_values = self._global_modal[:count]
        local.fill(0.0)
        for offset, item in enumerate(self.carrier.entries[batch_start:batch_stop]):
            if item.projection_rows.size:
                local[offset] = np.dot(
                    item.projection_values,
                    source_values[item.projection_rows - start],
                )
        self.comm.Allreduce(local, global_values, op=MPI.SUM)
        self._modal_allreduce_count += 1
        return global_values

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("DtN action has been destroyed")
        source_values = self._vector_values(source, writable=False)
        target_values = self._vector_values(target, writable=True)
        target_values.fill(0.0)
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            modal = self._modal_batch(source_values, batch_start, batch_stop)
            self._apply_modal_allreduce_count += 1
            start, _end = self.carrier.ownership_range
            for offset, item in enumerate(
                self.carrier.entries[batch_start:batch_stop]
            ):
                if item.coupling_rows.size:
                    target_values[item.coupling_rows - start] += (
                        modal[offset] / item.normalization_h * item.coupling_values
                    )
        self._apply_count += 1

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self.apply(source, target)

    def recover_auxiliary(self, source: PETSc.Vec) -> np.ndarray:
        """Recover ``a_i = H_i^{-1} D_i u`` without a total-mode work buffer."""

        if self._destroyed:
            raise RuntimeError("DtN action has been destroyed")
        source_values = self._vector_values(source, writable=False)
        recovered = np.empty(len(self.carrier.entries), dtype=np.complex128)
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            modal = self._modal_batch(source_values, batch_start, batch_stop)
            self._recovery_modal_allreduce_count += 1
            for offset, item in enumerate(
                self.carrier.entries[batch_start:batch_stop]
            ):
                recovered[batch_start + offset] = modal[offset] / item.normalization_h
        return recovered

    def compose_physical_rhs(
        self,
        base_incident_traction: PETSc.Vec,
        mode_amplitudes: Sequence[complex],
        target: PETSc.Vec,
    ) -> None:
        """Write ``base_incident_traction + C a`` using the retained carrier."""

        base_values = self._vector_values(base_incident_traction, writable=False)
        target_values = self._vector_values(target, writable=True)
        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        if amplitudes.shape != (len(self.carrier.entries),) or not np.all(
            np.isfinite(amplitudes)
        ):
            raise ValueError("DtN RHS amplitudes have an incompatible layout")
        target_values[:] = base_values
        start, _end = self.carrier.ownership_range
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            for offset, item in enumerate(
                self.carrier.entries[batch_start:batch_stop]
            ):
                if item.coupling_rows.size:
                    target_values[item.coupling_rows - start] += (
                        amplitudes[batch_start + offset] * item.coupling_values
                    )

    def apply_modal_rhs(
        self, mode_amplitudes: Sequence[complex], target: PETSc.Vec
    ) -> None:
        target_values = self._vector_values(target, writable=True)
        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        if amplitudes.shape != (len(self.carrier.entries),) or not np.all(
            np.isfinite(amplitudes)
        ):
            raise ValueError("DtN RHS amplitudes have an incompatible layout")
        target_values.fill(0.0)
        start, _end = self.carrier.ownership_range
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            for offset, item in enumerate(
                self.carrier.entries[batch_start:batch_stop]
            ):
                if item.coupling_rows.size:
                    target_values[item.coupling_rows - start] += (
                        amplitudes[batch_start + offset] * item.coupling_values
                    )

    @property
    def audit(self) -> Mapping[str, Any]:
        audit = dict(self.carrier.audit)
        audit.update(
            {
                "matrix_type": self.matrix.getType(),
                "apply_count": int(self._apply_count),
                "modal_allreduce_count": int(self._modal_allreduce_count),
                "apply_modal_allreduce_count": int(self._apply_modal_allreduce_count),
                "recovery_modal_allreduce_count": int(
                    self._recovery_modal_allreduce_count
                ),
                "modal_allreduce_count_per_apply": self.carrier.audit["batch_count"],
                "bounded_work_bytes_local": self._work_bytes,
                "bounded_work_bytes_global_sum": self._work_global_sum,
                "bounded_work_bytes_global_max": self._work_global_max,
                "bounded_work_scales_with": "fixed_modal_batch_size",
                "recovery_output_bytes": int(
                    len(self.carrier.entries) * np.dtype(np.complex128).itemsize
                ),
                "numeric_allgather": False,
                "explicit_c_matrix_count": 0,
                "explicit_d_matrix_count": 0,
            }
        )
        return MappingProxyType(audit)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        matrix = self._matrix
        self._matrix = None
        if matrix is not None:
            matrix.destroy()
        self._local_modal = np.empty(0, dtype=np.complex128)
        self._global_modal = np.empty(0, dtype=np.complex128)


def build_fullspace_dtn_action(
    carrier: FullspaceDtnCarrier,
    *,
    comm: MPI.Intracomm | None = None,
) -> FullspaceDtnAction:
    """Build the forward action from one validated dynamic carrier."""

    return FullspaceDtnAction(carrier, comm=carrier.comm if comm is None else comm)


def build_fullspace_dtn_carrier_from_surface(
    modes: Sequence[Any],
    surface_assemblers: Mapping[tuple[str, int], Any],
    mpc: Any,
    cfg: Any,
) -> FullspaceDtnCarrier:
    """Build the carrier from the current MPC-reduced surface functionals."""

    if mpc is None:
        raise ValueError("dynamic DtN surface carrier requires the finalized MPC")
    from .dtn_port_3d import _combine_owned_entries

    modes = tuple(modes)
    manifest_rows, _manifest_bytes, _manifest_sha = build_ordered_mode_manifest(
        modes, cfg
    )
    comm = mpc.function_space.mesh.comm
    index_map = mpc.function_space.dofmap.index_map
    owned_start = int(index_map.local_range[0])
    owned_end = owned_start + int(index_map.size_local)
    global_rows = int(index_map.size_global)
    component_cache: dict[
        tuple[str, int, int, complex, complex, complex],
        tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]],
    ] = {}

    def components_for(mode: Any):
        key = (
            str(mode.side),
            int(mode.m),
            int(mode.n),
            complex(mode.alpha),
            complex(mode.gamma),
            complex(mode.k_vector[2]),
        )
        components = component_cache.get(key)
        if components is None:
            components = (
                surface_assemblers[(mode.side, 0)].assemble_entries(mode, mpc),
                surface_assemblers[(mode.side, 1)].assemble_entries(mode, mpc),
            )
            component_cache[key] = components
        return components

    entries: list[FullspaceDtnModeFunctional] = []
    for index, mode in enumerate(modes):
        components = components_for(mode)
        projection_rows, projection_values = _combine_owned_entries(
            components,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=comm,
        )
        from .dtn_port_3d import _mode_projection_denominator, _traction_vector

        denominator = _mode_projection_denominator(mode, cfg)
        traction = _traction_vector(mode, cfg)
        coupling_rows, coupling_values = _combine_owned_entries(
            components,
            (-traction[0], -traction[1]),
            comm=comm,
        )
        entries.append(
            FullspaceDtnModeFunctional(
                mode_key=(int(index), str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)),
                coupling_rows=coupling_rows,
                coupling_values=_readonly(coupling_values, np.dtype(np.complex128)),
                projection_rows=projection_rows,
                projection_values=_readonly(
                    np.conjugate(projection_values), np.dtype(np.complex128)
                ),
                normalization_h=float(denominator),
                mode_identity=manifest_rows[index],
            )
        )
    slaves = np.asarray(mpc.slaves, dtype=np.int32)
    owned_slaves = slaves[slaves < int(index_map.size_local)]
    slave_rows = np.asarray(index_map.local_to_global(owned_slaves), dtype=PETSc.IntType)
    return FullspaceDtnCarrier(
        entries,
        global_rows=global_rows,
        ownership_range=(owned_start, owned_end),
        slave_rows=slave_rows,
        batch_size=FULLSPACE_DTN_BATCH_SIZE,
        comm=comm,
    )


__all__ = (
    "FULLSPACE_DTN_BATCH_SIZE",
    "FULLSPACE_DTN_MANIFEST_SCHEMA",
    "FULLSPACE_DTN_PROFILE",
    "FullspaceDtnAction",
    "FullspaceDtnCarrier",
    "FullspaceDtnModeFunctional",
    "build_dynamic_mode_inventory",
    "build_fullspace_dtn_action",
    "build_fullspace_dtn_carrier_from_surface",
    "build_ordered_mode_manifest",
    "classify_port_mode",
)
