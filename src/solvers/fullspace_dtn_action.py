"""Dynamic owner-local Fourier-DtN action for the current 3D port contract.

The carrier keeps sparse surface functionals and one explicit projection
denominator ``H_i`` per mode.  Applying the action reduces the projection and
coupling in deterministic batches; it never creates numeric C/D matrices or a
FE-sized replicated vector.  Surface functionals are assembled by the
existing MPC-aware port machinery so Floquet phase and H(curl) orientation are
applied exactly once.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .dtn_sparse_policy import (
    LEGACY_DTN_SPARSE_CUTOFF_POLICY,
    SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
    normalize_dtn_sparse_cutoff_policy,
)

FULLSPACE_DTN_PROFILE = "full3d_scalable_v1"
FULLSPACE_DTN_BATCH_SIZE = 8
FULLSPACE_DTN_MANIFEST_SCHEMA = "fullspace-dtn.mode-manifest.v1"
_SURFACE_PROGRESS_MAX_INTERVAL_SECONDS = 300.0
N0_PARENT_MODE_COUNT = 32060
N0_PARENT_MODE_SHA256 = (
    "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"
)
N0_ACTIVE_MODE_COUNT = 572
N0_EXPECTED_ACTIVE_MODE_SHA256 = (
    "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
)

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

    identity = {
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
    scale_policy = getattr(
        cfg, "task40_port_boundary_amplitude_scale_policy", None
    )
    if scale_policy is not None:
        identity["boundary_amplitude_scale_policy"] = str(scale_policy)
        identity["boundary_amplitude_scale"] = float(
            getattr(mode, "boundary_amplitude_scale", 1.0)
        )
        identity["boundary_amplitude_log_scale"] = float(
            getattr(mode, "boundary_amplitude_log_scale", 0.0)
        )
    return identity


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


def build_n0_mode_inventory(
    parent_inventory: tuple[Sequence[Any], Sequence[Mapping[str, Any]], str],
    cfg: Any,
) -> tuple[
    tuple[tuple[Any, ...], tuple[Mapping[str, Any], ...], str],
    dict[str, Any],
    tuple[int, ...],
]:
    """Return the active N0 inventory, its selection identity, and parent indices.

    The caller retains the full parent inventory separately as the quadrature
    authority. Filtering is an operator change, so both parent and active
    ordered manifest identities are carried in ``selection``.
    """

    parent_modes, parent_rows, parent_sha = parent_inventory
    parent_modes = tuple(parent_modes)
    parent_rows = tuple(parent_rows)
    parent_sha = str(parent_sha)
    if (
        len(parent_modes) != N0_PARENT_MODE_COUNT
        or len(parent_rows) != N0_PARENT_MODE_COUNT
        or parent_sha != N0_PARENT_MODE_SHA256
    ):
        raise ValueError("N0 selection requires the exact full 32060-mode parent inventory")
    if any(
        not isinstance(row, Mapping)
        or int(row.get("mode_index", -1)) != index
        or int(row.get("n", 999999)) != int(mode.n)
        or str(row.get("side")) != str(mode.side)
        or str(row.get("polarization")) != str(mode.polarization)
        or int(row.get("m", 999999)) != int(mode.m)
        for index, (mode, row) in enumerate(zip(parent_modes, parent_rows, strict=True))
    ):
        raise ValueError("N0 parent mode rows do not bind the live mode objects")
    parent_indices = tuple(
        index for index, row in enumerate(parent_rows) if int(row["n"]) == 0
    )
    if len(parent_indices) != N0_ACTIVE_MODE_COUNT:
        raise ValueError("N0 parent selection did not produce exactly 572 modes")
    active_modes = tuple(parent_modes[index] for index in parent_indices)
    per_group: Counter[tuple[str, str]] = Counter(
        (str(mode.side), str(mode.polarization)) for mode in active_modes
    )
    expected_groups = {
        (side, polarization): 143
        for side in ("bottom", "top")
        for polarization in ("s", "p")
    }
    if dict(per_group) != expected_groups:
        raise ValueError("N0 selection must contain 143 modes per side/polarization")
    for side in ("bottom", "top"):
        for polarization in ("s", "p"):
            orders = {
                int(mode.m)
                for mode in active_modes
                if str(mode.side) == side and str(mode.polarization) == polarization
            }
            if orders != set(range(-142, 1)):
                raise ValueError("N0 selection m orders must be exactly -142 through 0")
    active_rows, _encoded, active_sha = build_ordered_mode_manifest(active_modes, cfg)
    if active_sha != N0_EXPECTED_ACTIVE_MODE_SHA256:
        raise ValueError("N0 active manifest differs from the independently reviewed identity")
    index_payload = _canonical_json_bytes(list(parent_indices))
    selection = {
        "schema": "task39extra.dtn-mode-selection.v1",
        "policy": "n_equals_zero_both_ports_both_polarizations",
        "parent_mode_count": N0_PARENT_MODE_COUNT,
        "parent_mode_sha256": parent_sha,
        "active_mode_count": len(active_modes),
        "active_mode_sha256": active_sha,
        "expected_active_mode_sha256": N0_EXPECTED_ACTIVE_MODE_SHA256,
        "selected_parent_indices_sha256": hashlib.sha256(index_payload).hexdigest(),
        "side_polarization_counts": {
            f"{side}_{polarization}": 143
            for side, polarization in sorted(expected_groups)
        },
        "m_range_in_each_side_polarization": [-142, 0],
        "quadrature_inventory": "full_parent_modes",
        "operator_scope": "n0_filtered_dtn_not_full_dtn",
    }
    return (active_modes, active_rows, active_sha), selection, parent_indices


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
        n0_parent_store: Any | None = None,
        sparse_cutoff_policy: str = LEGACY_DTN_SPARSE_CUTOFF_POLICY,
        sparse_cutoff_relative_tolerance: float = 1.0e-13,
    ) -> None:
        sparse_cutoff_policy = normalize_dtn_sparse_cutoff_policy(
            sparse_cutoff_policy
        )
        sparse_cutoff_relative_tolerance = float(sparse_cutoff_relative_tolerance)
        if (
            not np.isfinite(sparse_cutoff_relative_tolerance)
            or not 0.0 < sparse_cutoff_relative_tolerance < 1.0
        ):
            raise ValueError("DtN sparse cutoff relative tolerance is invalid")
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
        self._n0_parent_store = n0_parent_store
        self._mode_manifest = _canonical_json_bytes(manifest)
        self._mode_manifest_sha256 = hashlib.sha256(self._mode_manifest).hexdigest()
        self._sparse_cutoff_policy = sparse_cutoff_policy
        self._sparse_cutoff_relative_tolerance = sparse_cutoff_relative_tolerance
        self._sparse_cutoff_identity_manifest = _canonical_json_bytes(
            {
                "schema": "fullspace-dtn.sparse-functional-identity.v2",
                "mode_manifest_sha256": self._mode_manifest_sha256,
                "sparse_cutoff_policy": self._sparse_cutoff_policy,
                "sparse_cutoff_relative_tolerance": (
                    self._sparse_cutoff_relative_tolerance
                ),
            }
        )
        self._sparse_cutoff_identity_sha256 = hashlib.sha256(
            self._sparse_cutoff_identity_manifest
        ).hexdigest()
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
    def n0_parent_store(self) -> Any | None:
        """Read-only handle for the closed, validated N0 parent store."""

        return self._n0_parent_store

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
                "sparse_cutoff_policy": self._sparse_cutoff_policy,
                "sparse_cutoff_relative_tolerance": (
                    self._sparse_cutoff_relative_tolerance
                ),
                "sparse_cutoff_identity_sha256": self._sparse_cutoff_identity_sha256,
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
    *,
    reuse_surface_vector: bool = False,
    reuse_surface_geometry_cache: bool = False,
    collect_surface_timings: bool = False,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    degree: int | None = None,
    progress_interval: int = 1024,
    quadrature_degree: int | None = None,
    functional_store_config: Mapping[str, Any] | None = None,
    operator_selection: Mapping[str, Any] | None = None,
    parent_mode_rows: Sequence[Mapping[str, Any]] | None = None,
    selected_parent_indices: Sequence[int] | None = None,
    sparse_cutoff_policy: str = LEGACY_DTN_SPARSE_CUTOFF_POLICY,
    sparse_cutoff_relative_tolerance: float = 1.0e-13,
) -> FullspaceDtnCarrier:
    """Build the carrier from the current MPC-reduced surface functionals."""

    if mpc is None:
        raise ValueError("dynamic DtN surface carrier requires the finalized MPC")
    if int(progress_interval) <= 0:
        raise ValueError("surface carrier progress interval must be positive")
    if collect_surface_timings and stage_callback is None:
        raise ValueError("surface timings require a scalar stage callback")
    if collect_surface_timings and not reuse_surface_vector:
        raise ValueError("surface timings require the reused-vector opt-in")
    if reuse_surface_geometry_cache and (
        not reuse_surface_vector or degree != 6
    ):
        raise ValueError("surface geometry caching requires the p6 reused-vector route")
    sparse_cutoff_policy = normalize_dtn_sparse_cutoff_policy(sparse_cutoff_policy)
    sparse_cutoff_relative_tolerance = float(sparse_cutoff_relative_tolerance)
    if (
        not np.isfinite(sparse_cutoff_relative_tolerance)
        or not 0.0 < sparse_cutoff_relative_tolerance < 1.0
    ):
        raise ValueError("DtN sparse cutoff relative tolerance is invalid")
    if (
        (
            sparse_cutoff_policy != LEGACY_DTN_SPARSE_CUTOFF_POLICY
            or sparse_cutoff_relative_tolerance != 1.0e-13
        )
        and functional_store_config is not None
    ):
        raise ValueError(
            "scale-homogeneous DtN functionals cannot use a persistent store "
            "whose identity schema omits the cutoff policy/tolerance"
        )
    from .dtn_port_3d import _combine_owned_entries

    modes = tuple(modes)
    manifest_rows, _manifest_bytes, manifest_sha = build_ordered_mode_manifest(
        modes, cfg
    )
    comm = mpc.function_space.mesh.comm
    index_map = mpc.function_space.dofmap.index_map
    owned_start = int(index_map.local_range[0])
    owned_end = owned_start + int(index_map.size_local)
    global_rows = int(index_map.size_global)
    functional_store = None
    store_slave_rows = None
    entries: list[FullspaceDtnModeFunctional] = []
    resume_prefix_count = 0
    remaining_uses = None
    component_cache: dict[
        tuple[Any, ...],
        tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]],
    ] = {}
    surface_contexts = {
        id(context): context
        for assembler in surface_assemblers.values()
        if (context := getattr(assembler, "context", None)) is not None
    }
    geometry_cache_context = None
    if reuse_surface_geometry_cache:
        from .fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

        if len(surface_assemblers) != 4 or len(surface_contexts) != 1:
            raise ValueError(
                "geometry cache requires four assemblers sharing one p6 context"
            )
        geometry_cache_context = next(iter(surface_contexts.values()))
        if (
            getattr(geometry_cache_context, "backend", None)
            != SURFACE_COMPONENT_PAIR_BACKEND
            or not getattr(geometry_cache_context, "_geometry_cache_enabled", False)
            or any(
                getattr(assembler, "context", None) is not geometry_cache_context
                or getattr(assembler, "surface_backend", None)
                != SURFACE_COMPONENT_PAIR_BACKEND
                for assembler in surface_assemblers.values()
            )
        ):
            raise ValueError(
                "all four p6 surface assemblers must share the opted-in paired context"
            )
    if functional_store_config is not None:
        if degree not in (3, 6) or quadrature_degree is None:
            raise ValueError("functional store requires an explicit p3/p6 quadrature identity")
        required_store_keys = {
            "root",
            "source_sha256",
            "resolved_config_sha256",
            "input_sha256",
            "physical_model_sha256",
            "max_shard_working_bytes",
            "max_total_disk_bytes",
            "disk_reserve_bytes",
        }
        missing_store_keys = required_store_keys.difference(functional_store_config)
        if missing_store_keys:
            raise ValueError(
                "functional-store configuration lacks: "
                + ", ".join(sorted(missing_store_keys))
            )
        from pathlib import Path

        from .fullspace_dtn_functional_store import PortFunctionalShardStore

        configured_root = Path(functional_store_config["root"])
        if not configured_root.is_absolute():
            raise ValueError("functional-store root must be an absolute path")

        all_slaves = np.asarray(mpc.slaves).reshape(-1)
        if not np.issubdtype(all_slaves.dtype, np.integer):
            raise ValueError("functional-store MPC slave indices must be integers")
        owned_slaves = all_slaves[all_slaves < int(index_map.size_local)]
        store_slave_rows = np.asarray(
            index_map.local_to_global(owned_slaves), dtype=PETSc.IntType
        )
        if store_slave_rows.size:
            store_slave_rows = np.unique(store_slave_rows)
        backend_identity = getattr(
            surface_assemblers[("bottom", 0)], "surface_backend", None
        )
        if backend_identity is None and int(degree) == 3:
            backend_identity = "native_ffcx"
        compiled_surface_assemblers = functional_store_config.get(
            "compiled_surface_assemblers"
        )
        if int(degree) == 6 and compiled_surface_assemblers is not None:
            raise ValueError(
                "p6 functional-store route uses its live paired context, not injected native Forms"
            )
        store_root = configured_root / f"p{int(degree)}"
        functional_store = PortFunctionalShardStore.for_surface(
            store_root,
            source_sha256=str(functional_store_config["source_sha256"]),
            resolved_config_sha256=str(
                functional_store_config["resolved_config_sha256"]
            ),
            input_sha256=str(functional_store_config["input_sha256"]),
            physical_model_sha256=str(
                functional_store_config["physical_model_sha256"]
            ),
            degree=int(degree),
            backend=str(backend_identity),
            quadrature_degree=int(quadrature_degree),
            mode_identities=manifest_rows,
            mode_manifest_sha256=manifest_sha,
            surface_assemblers=surface_assemblers,
            compiled_surface_assemblers=(
                None if int(degree) == 6 else compiled_surface_assemblers
            ),
            mpc=mpc,
            ownership_range=(owned_start, owned_end),
            slave_rows=store_slave_rows,
            row_dtype=PETSc.IntType,
            producer_provenance=functional_store_config.get(
                "producer_provenance", {}
            ),
            max_shard_working_bytes=int(
                functional_store_config["max_shard_working_bytes"]
            ),
            max_total_disk_bytes=int(
                functional_store_config["max_total_disk_bytes"]
            ),
            disk_reserve_bytes=int(functional_store_config["disk_reserve_bytes"]),
            operator_selection=operator_selection,
        )
        try:
            for stored in functional_store.restore_prefix():
                entries.append(
                    FullspaceDtnModeFunctional(
                        mode_key=tuple(stored["mode_key"]),
                        coupling_rows=stored["coupling_rows"],
                        coupling_values=stored["coupling_values"],
                        projection_rows=stored["projection_rows"],
                        projection_values=stored["projection_values"],
                        normalization_h=float(stored["normalization_h"]),
                        mode_identity=stored["mode_identity"],
                    )
                )
            if operator_selection is not None:
                if parent_mode_rows is None or selected_parent_indices is None:
                    raise ValueError(
                        "N0 store import requires the live parent rows and selected indices"
                    )
                parent_compatibility = functional_store_config.get(
                    "parent_compatibility"
                )
                if parent_compatibility is None:
                    functional_store.disable_parent_import(
                        "no reviewed parent compatibility mapping was configured"
                    )
                else:
                    functional_store.prepare_compatible_parent_import(
                        parent_compatibility,
                        parent_mode_rows,
                        selected_parent_indices,
                    )
            elif parent_mode_rows is not None or selected_parent_indices is not None:
                raise ValueError(
                    "parent import metadata requires an explicit N0 operator selection"
                )
        except Exception:
            functional_store.close()
            raise
    resume_prefix_count = len(entries)
    remaining_uses = (
        _remaining_dtn_component_phase_uses(modes, resume_prefix_count)
        if reuse_surface_vector
        else None
    )
    workspace = None

    def notify(name: str, facts: Mapping[str, Any]) -> None:
        if stage_callback is not None:
            payload = dict(facts)
            if degree is not None:
                payload["space_degree"] = int(degree)
            stage_callback(name, payload)

    def components_for(mode: Any):
        phase_key = _dtn_component_phase_key(mode)
        cache_key = (
            sparse_cutoff_policy,
            sparse_cutoff_relative_tolerance,
            *phase_key,
        )
        components = component_cache.get(cache_key)
        if components is None:
            left_assembler = surface_assemblers[(mode.side, 0)]
            right_assembler = surface_assemblers[(mode.side, 1)]
            from .fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

            left_is_pair = (
                getattr(left_assembler, "surface_backend", None)
                == SURFACE_COMPONENT_PAIR_BACKEND
            )
            right_is_pair = (
                getattr(right_assembler, "surface_backend", None)
                == SURFACE_COMPONENT_PAIR_BACKEND
            )
            if left_is_pair or right_is_pair:
                if not left_is_pair or not right_is_pair:
                    raise RuntimeError(
                        "component-pair backend is not selected for both surface components"
                    )
                if workspace is None:
                    raise RuntimeError(
                        "component-pair backend requires the one-Vec workspace"
                    )
                pair_assemble = getattr(left_assembler, "assemble_pair_entries", None)
                if not callable(pair_assemble):
                    raise RuntimeError(
                        "component-pair backend has no paired assembly entry point"
                    )
                left, right = pair_assemble(
                    right_assembler, mode, mpc, workspace=workspace
                )
            elif workspace is None:
                extract_policy = (
                    {}
                    if sparse_cutoff_policy == LEGACY_DTN_SPARSE_CUTOFF_POLICY
                    and sparse_cutoff_relative_tolerance == 1.0e-13
                    else {
                        "sparse_cutoff_policy": sparse_cutoff_policy,
                        "sparse_cutoff_relative_tolerance": (
                            sparse_cutoff_relative_tolerance
                        ),
                    }
                )
                left = left_assembler.assemble_entries(
                    mode, mpc, **extract_policy
                )
                right = right_assembler.assemble_entries(
                    mode, mpc, **extract_policy
                )
            else:
                extract_policy = (
                    {}
                    if sparse_cutoff_policy == LEGACY_DTN_SPARSE_CUTOFF_POLICY
                    and sparse_cutoff_relative_tolerance == 1.0e-13
                    else {
                        "sparse_cutoff_policy": sparse_cutoff_policy,
                        "sparse_cutoff_relative_tolerance": (
                            sparse_cutoff_relative_tolerance
                        ),
                    }
                )
                left = left_assembler.assemble_entries(
                    mode, mpc, workspace=workspace, **extract_policy
                )
                right = right_assembler.assemble_entries(
                    mode, mpc, workspace=workspace, **extract_policy
                )
            components = (
                left,
                right,
            )
            component_cache[cache_key] = components
        return components

    try:
        has_missing_modes = resume_prefix_count < len(modes)
        if geometry_cache_context is not None and has_missing_modes:
            geometry_cache_context.begin_geometry_cache()
        if reuse_surface_vector and has_missing_modes:
            from .dtn_port_3d import _SurfaceMpcVectorWorkspace

            first_assembler = next(iter(surface_assemblers.values()))
            workspace_policy_kwargs = (
                {}
                if sparse_cutoff_policy == LEGACY_DTN_SPARSE_CUTOFF_POLICY
                and sparse_cutoff_relative_tolerance == 1.0e-13
                else {
                    "sparse_cutoff_policy": sparse_cutoff_policy,
                    "sparse_cutoff_relative_tolerance": (
                        sparse_cutoff_relative_tolerance
                    ),
                }
            )
            workspace = _SurfaceMpcVectorWorkspace(
                first_assembler.function_space,
                first_assembler.mesh_data,
                mpc,
                surface_assemblers,
                collect_timings=collect_surface_timings,
                **workspace_policy_kwargs,
            )
        if workspace is not None:
            notify("surface_carrier_workspace_ready", workspace.facts)
        notify(
            "surface_carrier_assembly_started",
            {
                "mode_count": len(modes),
                "mode_sha256": manifest_sha,
                "restored_functional_prefix_count": resume_prefix_count,
            },
        )
        last_progress_time = (
            time.monotonic()
            if workspace is not None and stage_callback is not None
            else None
        )
        for index in range(resume_prefix_count, len(modes)):
            mode = modes[index]
            phase_key = _dtn_component_phase_key(mode)
            cache_key = (
                sparse_cutoff_policy,
                sparse_cutoff_relative_tolerance,
                *phase_key,
            )
            stored_functional = (
                functional_store.try_import_compatible_parent_functional(index)
                if functional_store is not None and operator_selection is not None
                else None
            )
            if stored_functional is not None:
                entry = FullspaceDtnModeFunctional(
                    mode_key=tuple(stored_functional["mode_key"]),
                    coupling_rows=stored_functional["coupling_rows"],
                    coupling_values=stored_functional["coupling_values"],
                    projection_rows=stored_functional["projection_rows"],
                    projection_values=stored_functional["projection_values"],
                    normalization_h=float(stored_functional["normalization_h"]),
                    mode_identity=stored_functional["mode_identity"],
                )
                components = None
            else:
                fallback_assembly_started = (
                    time.perf_counter()
                    if functional_store is not None and operator_selection is not None
                    else None
                )
                try:
                    components = components_for(mode)
                finally:
                    if fallback_assembly_started is not None:
                        functional_store.record_n0_parent_fallback_assembly_seconds(
                            time.perf_counter() - fallback_assembly_started
                        )
                combine_started = (
                    time.perf_counter()
                    if workspace is not None and workspace.timing_totals is not None
                    else None
                )
                merge_policy_kwargs = (
                    {}
                    if sparse_cutoff_policy == LEGACY_DTN_SPARSE_CUTOFF_POLICY
                    and sparse_cutoff_relative_tolerance == 1.0e-13
                    else {
                        "sparse_cutoff_policy": sparse_cutoff_policy,
                        "relative_tol": sparse_cutoff_relative_tolerance,
                    }
                )
                projection_rows, projection_values = _combine_owned_entries(
                    components,
                    (mode.e_vector[0], mode.e_vector[1]),
                    comm=comm,
                    **merge_policy_kwargs,
                )
                from .dtn_port_3d import _mode_projection_denominator, _traction_vector

                denominator = _mode_projection_denominator(mode, cfg)
                traction = _traction_vector(mode, cfg)
                coupling_rows, coupling_values = _combine_owned_entries(
                    components,
                    (-traction[0], -traction[1]),
                    comm=comm,
                    **merge_policy_kwargs,
                )
                if combine_started is not None:
                    workspace.timing_totals["carrier_combine_seconds"] += (
                        time.perf_counter() - combine_started
                    )
                entry = FullspaceDtnModeFunctional(
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
                if functional_store is not None:
                    commit_started = time.perf_counter()
                    try:
                        functional_store.commit(entry, mode_index=index)
                    finally:
                        functional_store.record_active_store_commit_seconds(
                            time.perf_counter() - commit_started
                        )
            entries.append(entry)
            if remaining_uses is not None:
                remaining_uses[phase_key] -= 1
                if remaining_uses[phase_key] == 0:
                    del remaining_uses[phase_key]
                    component_cache.pop(cache_key, None)
                    for context in surface_contexts.values():
                        context.release_mode(mode)
                # The carrier arrays are copies from concatenate; no cached
                # component array is needed after this mode's two combines.
                if components is not None:
                    del components
            completed = index + 1
            time_due = False
            if last_progress_time is not None:
                completed_at = time.monotonic()
                time_due = (
                    completed_at - last_progress_time
                    >= _SURFACE_PROGRESS_MAX_INTERVAL_SECONDS
                )
            if (
                completed % int(progress_interval) == 0
                or completed == len(modes)
                or time_due
            ):
                notify(
                    "surface_carrier_mode_progress",
                    {
                        "completed_modes": completed,
                        "total_modes": len(modes),
                        "mode_sha256": manifest_sha,
                    },
                )
                if last_progress_time is not None:
                    last_progress_time = completed_at

        notify(
            "surface_carrier_assembly_complete",
            {
                "completed_modes": len(modes),
                "mode_count": len(modes),
                "mode_sha256": manifest_sha,
                "component_pair_stats_by_degree": {
                    f"p{int(context.degree)}": context.component_pair_stats_facts()
                    for context in surface_contexts.values()
                    if getattr(context, "backend", None)
                    == "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1"
                },
            },
        )
        if store_slave_rows is None:
            slaves = np.asarray(mpc.slaves, dtype=np.int32)
            owned_slaves = slaves[slaves < int(index_map.size_local)]
            slave_rows = np.asarray(
                index_map.local_to_global(owned_slaves), dtype=PETSc.IntType
            )
        else:
            slave_rows = store_slave_rows
        normalization_started = (
            time.perf_counter()
            if workspace is not None and workspace.timing_totals is not None
            else None
        )
        notify(
            "surface_carrier_normalize_validate_started",
            {"mode_count": len(modes), "mode_sha256": manifest_sha},
        )
        carrier = FullspaceDtnCarrier(
            entries,
            global_rows=global_rows,
            ownership_range=(owned_start, owned_end),
            slave_rows=slave_rows,
            batch_size=FULLSPACE_DTN_BATCH_SIZE,
            comm=comm,
            n0_parent_store=(
                functional_store
                if functional_store is not None and operator_selection is not None
                else None
            ),
            sparse_cutoff_policy=sparse_cutoff_policy,
            sparse_cutoff_relative_tolerance=sparse_cutoff_relative_tolerance,
        )
        if normalization_started is not None:
            workspace.timing_totals["carrier_normalize_validate_seconds"] += (
                time.perf_counter() - normalization_started
            )
        notify(
            "surface_carrier_normalize_validate_complete",
            {
                "mode_count": len(modes),
                "mode_sha256": manifest_sha,
                "normalized_entries": len(carrier.entries),
                **(
                    {"timing_seconds": dict(workspace.timing_totals)}
                    if workspace is not None and workspace.timing_totals is not None
                    else {}
                ),
                **(
                    {"functional_store": functional_store.audit}
                    if functional_store is not None
                    else {}
                ),
            },
        )
        return carrier
    finally:
        try:
            if geometry_cache_context is not None:
                geometry_cache_context.end_geometry_cache()
        finally:
            try:
                for context in surface_contexts.values():
                    release = getattr(
                        context, "release_prepared_trace_contractions", None
                    )
                    if callable(release):
                        release()
            finally:
                try:
                    if workspace is not None:
                        workspace.destroy()
                finally:
                    if functional_store is not None:
                        functional_store.close()


def _dtn_component_phase_key(
    mode: Any,
) -> tuple[str, int, int, complex, complex, complex, float, float]:
    """Return the existing phase-cache identity for one polarization mode."""

    return (
        str(mode.side),
        int(mode.m),
        int(mode.n),
        complex(mode.alpha),
        complex(mode.gamma),
        complex(mode.k_vector[2]),
        float(getattr(mode, "boundary_amplitude_scale", 1.0)),
        float(getattr(mode, "boundary_amplitude_log_scale", 0.0)),
    )


def _remaining_dtn_component_phase_uses(
    modes: Sequence[Any], completed_prefix_count: int
) -> Counter:
    """Rebuild only the shared phase-cache uses after a durable mode prefix."""

    prefix = int(completed_prefix_count)
    if prefix < 0 or prefix > len(modes):
        raise ValueError("functional-store prefix is outside the ordered mode manifest")
    return Counter(_dtn_component_phase_key(mode) for mode in modes[prefix:])


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
