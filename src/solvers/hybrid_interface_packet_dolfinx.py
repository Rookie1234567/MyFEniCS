"""Task040 owner-local canonical Gamma layouts for DOLFINx planes.

The packet kernel stores canonical rows, while this module supplies the
finite-element bridge: one edge/face block at a time is mapped from the
current condensed Gamma order to the physical canonical identity.  Numerical
arrays remain owner-local; only small row-count/hash summaries participate in
MPI collectives.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI

from .hcurl_canonical_vector_dolfinx import (
    iter_canonical_active_trace_plane_blocks,
)
from .hybrid_interface_packet import canonical_key_json, canonical_key_sha256

__all__ = (
    "GammaEntityBlock",
    "GammaBlockPlacement",
    "GammaCanonicalLayout",
    "CanonicalOwnerLocalBasis",
    "RawOwnerLocalBasis",
    "make_gamma_entity_block",
    "build_gamma_canonical_layout",
    "build_dolfinx_plane_gamma_layout",
    "canonicalize_owner_local_basis_in_place",
    "reconstruct_owner_local_basis",
    "audit_owner_local_basis_round_trip",
)


def _complex_pair(value: complex) -> list[float]:
    value = complex(value)
    if not np.isfinite(value.real) or not np.isfinite(value.imag):
        raise ValueError("Gamma Floquet coefficient is nonfinite")
    return [float(value.real), float(value.imag)]


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        return _complex_pair(value)
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"Gamma metadata is not JSON-safe: {type(value)!r}")


def _normalise_key(key: Any) -> str:
    if isinstance(key, str):
        try:
            key = json.loads(key)
        except json.JSONDecodeError as exc:
            raise ValueError("Gamma key is not encoded JSON") from exc
    return canonical_key_json(key)


def _normalise_keys(keys: Iterable[Any]) -> tuple[str, ...]:
    result = tuple(_normalise_key(key) for key in keys)
    if len(set(result)) != len(result):
        raise ValueError("Gamma canonical keys are duplicated")
    return result


def _summary_hash(records: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        [_json_safe(record) for record in records],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class GammaEntityBlock:
    """One owner-local edge/face block in current Gamma row positions."""

    name: str
    entity_dimension: int
    physical_entity: Any
    raw_row_ids: np.ndarray
    canonical_keys: tuple[str, ...]
    raw_to_canonical: np.ndarray
    canonical_to_raw: np.ndarray
    orientation_state: Any
    floquet_master: Any
    floquet_coefficient: complex

    def __post_init__(self) -> None:
        rows = np.asarray(self.raw_row_ids, dtype=np.int64)
        keys = _normalise_keys(self.canonical_keys)
        raw_to_canonical = np.asarray(self.raw_to_canonical, dtype=np.complex128)
        canonical_to_raw = np.asarray(self.canonical_to_raw, dtype=np.complex128)
        size = len(rows)
        if not self.name or len(np.unique(rows)) != size:
            raise ValueError("Gamma entity block rows must be unique and named")
        if len(keys) != size:
            raise ValueError("Gamma entity block key count differs from rows")
        if raw_to_canonical.shape != (size, size) or canonical_to_raw.shape != (
            size,
            size,
        ):
            raise ValueError("Gamma entity block transform has the wrong shape")
        if (
            not np.isfinite(raw_to_canonical).all()
            or not np.isfinite(canonical_to_raw).all()
        ):
            raise ValueError("Gamma entity block transform is nonfinite")
        if not np.allclose(
            raw_to_canonical @ canonical_to_raw,
            np.eye(size, dtype=np.complex128),
            rtol=0.0,
            atol=1.0e-11,
        ):
            raise ValueError("Gamma entity block transforms are not inverse")
        object.__setattr__(self, "raw_row_ids", rows)
        object.__setattr__(self, "canonical_keys", keys)
        object.__setattr__(self, "raw_to_canonical", raw_to_canonical)
        object.__setattr__(self, "canonical_to_raw", canonical_to_raw)
        object.__setattr__(
            self, "floquet_coefficient", complex(self.floquet_coefficient)
        )


@dataclass(frozen=True)
class GammaBlockPlacement:
    """A block plus its current owner-local Gamma row positions."""

    block: GammaEntityBlock
    positions: np.ndarray

    def __post_init__(self) -> None:
        positions = np.asarray(self.positions, dtype=np.int64)
        if positions.ndim != 1 or len(positions) != len(self.block.raw_row_ids):
            raise ValueError("Gamma block positions have the wrong shape")
        object.__setattr__(self, "positions", positions)


@dataclass(frozen=True)
class GammaCanonicalLayout:
    """Owner-local canonical key order and block transforms."""

    gamma_rows_local: np.ndarray
    blocks: tuple[GammaBlockPlacement, ...]
    canonical_keys: tuple[str, ...]
    plane_identity: Mapping[str, Any]
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        rows = np.asarray(self.gamma_rows_local, dtype=np.int64)
        if rows.ndim != 1 or len(np.unique(rows)) != len(rows):
            raise ValueError("Gamma owner rows must be a unique one-dimensional array")
        keys = _normalise_keys(self.canonical_keys)
        if len(keys) != len(rows):
            raise ValueError("Gamma canonical keys do not cover local rows")
        object.__setattr__(self, "gamma_rows_local", rows)
        object.__setattr__(self, "canonical_keys", keys)


def make_gamma_entity_block(
    *,
    name: str,
    entity_dimension: int,
    physical_entity: Any,
    raw_row_ids: Iterable[int],
    canonical_to_raw: np.ndarray,
    orientation_state: Any,
    floquet_master: Any = None,
    floquet_coefficient: complex = 1.0 + 0.0j,
    canonical_key_records: Sequence[Mapping[str, Any]] | None = None,
) -> GammaEntityBlock:
    """Build one block using ``stored_raw = phase * E * canonical``."""

    rows = np.asarray(tuple(raw_row_ids), dtype=np.int64)
    phase = complex(floquet_coefficient)
    if canonical_key_records is None:
        canonical_key_records = tuple(
            {
                "role": "active_trace",
                "entity_dimension": int(entity_dimension),
                "physical_entity": physical_entity,
                "entity_local_basis_index": int(index),
                "orientation_state": orientation_state,
                "floquet_master": floquet_master,
                "floquet_coefficient": _complex_pair(phase),
            }
            for index in range(len(rows))
        )
    keys = tuple(canonical_key_json(record) for record in canonical_key_records)
    canonical_to_raw = np.asarray(canonical_to_raw, dtype=np.complex128)
    if canonical_to_raw.shape != (len(rows), len(rows)):
        raise ValueError("canonical-to-raw transform has the wrong shape")
    raw_to_canonical = np.linalg.solve(canonical_to_raw, np.eye(len(rows)))
    return GammaEntityBlock(
        name=str(name),
        entity_dimension=int(entity_dimension),
        physical_entity=physical_entity,
        raw_row_ids=rows,
        canonical_keys=keys,
        raw_to_canonical=raw_to_canonical,
        canonical_to_raw=canonical_to_raw,
        orientation_state=orientation_state,
        floquet_master=floquet_master,
        floquet_coefficient=phase,
    )


def build_gamma_canonical_layout(
    blocks: Iterable[GammaEntityBlock],
    gamma_rows_local: Iterable[int],
    *,
    plane_identity: Mapping[str, Any],
    comm: MPI.Intracomm | None = None,
) -> GammaCanonicalLayout:
    """Bind entity blocks to current Gamma positions without global key copies."""

    local_error: str | None = None
    rows: np.ndarray | None = None
    placements: tuple[GammaBlockPlacement, ...] | None = None
    canonical_keys: tuple[str, ...] | None = None
    try:
        rows = np.asarray(tuple(gamma_rows_local), dtype=np.int64)
        if rows.ndim != 1 or len(np.unique(rows)) != len(rows):
            raise ValueError("Gamma owner rows must be unique")
        row_positions = {int(row): index for index, row in enumerate(rows)}
        ordered_blocks = tuple(
            sorted(tuple(blocks), key=lambda block: (block.canonical_keys, block.name))
        )
        keys_by_position: list[str | None] = [None] * len(rows)
        local_placements: list[GammaBlockPlacement] = []
        seen_positions: set[int] = set()
        seen_keys: set[str] = set()
        for block in ordered_blocks:
            try:
                positions = np.asarray(
                    [row_positions[int(row)] for row in block.raw_row_ids],
                    dtype=np.int64,
                )
            except KeyError as exc:
                raise ValueError(
                    "Gamma block row is outside the local Gamma layout"
                ) from exc
            if len(set(positions.tolist())) != len(positions):
                raise ValueError("Gamma block positions are duplicated")
            if seen_positions.intersection(positions.tolist()):
                raise ValueError("Gamma entity blocks overlap in owner rows")
            if seen_keys.intersection(block.canonical_keys):
                raise ValueError("Gamma entity blocks duplicate canonical keys")
            seen_positions.update(int(value) for value in positions)
            seen_keys.update(block.canonical_keys)
            for position, key in zip(positions, block.canonical_keys, strict=True):
                keys_by_position[int(position)] = key
            local_placements.append(GammaBlockPlacement(block, positions))
        if len(seen_positions) != len(rows) or any(
            key is None for key in keys_by_position
        ):
            raise ValueError("Gamma canonical layout does not cover every local row")
        canonical_keys = tuple(key for key in keys_by_position if key is not None)
        placements = tuple(local_placements)
        GammaCanonicalLayout(
            gamma_rows_local=rows,
            blocks=placements,
            canonical_keys=canonical_keys,
            plane_identity=_json_safe(plane_identity),
            audit={},
        )
    except Exception as error:
        local_error = str(error)
    if comm is not None:
        errors = comm.allgather(local_error)
        first_error = next((error for error in errors if error), None)
        if first_error is not None:
            raise ValueError(f"Gamma layout construction failed: {first_error}")
    elif local_error is not None:
        raise ValueError(f"Gamma layout construction failed: {local_error}")

    assert rows is not None
    assert placements is not None
    assert canonical_keys is not None
    summary = {
        "local_count": len(canonical_keys),
        "key_order_sha256": canonical_key_sha256(canonical_keys),
    }
    summaries = [summary]
    global_count = len(rows)
    if comm is not None:
        summary = {"rank": int(comm.rank), **summary}
        summaries = comm.allgather(summary)
        global_count = sum(int(item["local_count"]) for item in summaries)
    summaries = sorted(summaries, key=lambda item: int(item.get("rank", 0)))
    audit = {
        "local_row_count": int(len(rows)),
        "global_row_count": int(global_count),
        "local_block_count": int(len(placements)),
        "canonical_key_order_sha256": canonical_key_sha256(canonical_keys),
        "global_key_summary_sha256": _summary_hash(summaries),
        "global_key_bijection": "requires_independent_checker",
        "basis_global_replicated": False,
        "fe_numeric_allgather": False,
        "plane_identity": _json_safe(plane_identity),
    }
    return GammaCanonicalLayout(
        gamma_rows_local=rows,
        blocks=placements,
        canonical_keys=canonical_keys,
        plane_identity=_json_safe(plane_identity),
        audit=audit,
    )


def build_dolfinx_plane_gamma_layout(
    *,
    function_space: Any,
    condensed: Any,
    floquet_data: Any | None,
    interface_z_nm: float,
    plane_cell_side: str,
    plane_original_dofs: Iterable[int],
    gamma_rows_local: Iterable[int],
    plane_identity: Mapping[str, Any] | None = None,
) -> GammaCanonicalLayout:
    """Build a real owner-local layout from the existing DOLFINx plane path."""

    comm = function_space.mesh.comm
    plane_original_dofs = tuple(plane_original_dofs)
    gamma_rows_local = tuple(gamma_rows_local)
    local_error: str | None = None
    blocks: list[GammaEntityBlock] = []
    try:
        for index, record in enumerate(
            iter_canonical_active_trace_plane_blocks(
                condensed,
                function_space,
                floquet_data,
                plane_z=float(interface_z_nm),
                plane_original_dofs=plane_original_dofs,
                gamma_rows_local=gamma_rows_local,
            )
        ):
            blocks.append(
                GammaEntityBlock(
                    name=f"dim{record['entity_dimension']}_block{index}",
                    entity_dimension=int(record["entity_dimension"]),
                    physical_entity=record["physical_entity"],
                    raw_row_ids=np.asarray(record["active_row_ids"], dtype=np.int64),
                    canonical_keys=tuple(
                        canonical_key_json(key) for key in record["canonical_keys"]
                    ),
                    raw_to_canonical=record["raw_to_canonical"],
                    canonical_to_raw=record["canonical_to_raw"],
                    orientation_state=record["orientation_state"],
                    floquet_master=record["floquet_master"],
                    floquet_coefficient=record["floquet_coefficient"],
                )
            )
        identity = _json_safe(plane_identity or {})
        identity.update(
            {
                "interface_z_nm": float(interface_z_nm),
                "plane_cell_side": str(plane_cell_side),
                "phase_convention": "stored_raw=phase*E*canonical",
            }
        )
    except Exception as error:
        local_error = str(error)
        identity = None
    errors = comm.allgather(local_error)
    first_error = next((error for error in errors if error), None)
    if first_error is not None:
        raise ValueError(f"DOLFINx Gamma layout construction failed: {first_error}")
    assert identity is not None
    return build_gamma_canonical_layout(
        blocks,
        gamma_rows_local,
        plane_identity=identity,
        comm=comm,
    )


@dataclass(frozen=True)
class CanonicalOwnerLocalBasis:
    """Finalized owner-local U/V arrays and their packet key order."""

    keys: tuple[str, ...]
    U: np.ndarray
    V: np.ndarray


@dataclass(frozen=True)
class RawOwnerLocalBasis:
    """Finalized owner-local U/V arrays in the current raw Gamma layout."""

    gamma_rows_local: np.ndarray
    U: np.ndarray
    V: np.ndarray


def _validate_basis_arrays(
    layout: GammaCanonicalLayout, U: np.ndarray, V: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    U = np.asarray(U)
    V = np.asarray(V)
    rows = len(layout.gamma_rows_local)
    if (
        U.dtype != np.dtype(np.complex128)
        or V.dtype != np.dtype(np.complex128)
        or U.ndim != 2
        or V.shape != U.shape
        or U.shape[0] != rows
    ):
        raise ValueError("owner-local U/V arrays have the wrong complex128 shape")
    if not np.isfinite(U).all() or not np.isfinite(V).all():
        raise ValueError("owner-local U/V arrays are nonfinite")
    return U, V


def canonicalize_owner_local_basis_in_place(
    layout: GammaCanonicalLayout,
    raw_U: np.ndarray,
    raw_V: np.ndarray,
) -> CanonicalOwnerLocalBasis:
    """Canonicalize raw U/V block-by-block without a full-group copy."""

    U, V = _validate_basis_arrays(layout, raw_U, raw_V)
    for placement in layout.blocks:
        positions = placement.positions
        raw_u_block = U[positions, :]
        raw_v_block = V[positions, :]
        U[positions, :] = placement.block.raw_to_canonical @ raw_u_block
        V[positions, :] = placement.block.raw_to_canonical @ raw_v_block
    return CanonicalOwnerLocalBasis(layout.canonical_keys, U, V)


def reconstruct_owner_local_basis(
    layout: GammaCanonicalLayout,
    canonical_keys: Sequence[Any],
    canonical_U: np.ndarray,
    canonical_V: np.ndarray,
) -> RawOwnerLocalBasis:
    """Rebuild one current raw layout using only block-sized temporary arrays."""

    source_keys = _normalise_keys(canonical_keys)
    U, V = np.asarray(canonical_U), np.asarray(canonical_V)
    if (
        U.dtype != np.dtype(np.complex128)
        or V.dtype != np.dtype(np.complex128)
        or U.ndim != 2
        or V.shape != U.shape
        or U.shape[0] != len(source_keys)
    ):
        raise ValueError("loaded canonical U/V arrays have the wrong shape")
    if set(source_keys) != set(layout.canonical_keys):
        raise ValueError("loaded canonical keys do not cover the current layout")
    source_positions = {key: index for index, key in enumerate(source_keys)}
    raw_U = np.empty((len(layout.gamma_rows_local), U.shape[1]), dtype=np.complex128)
    raw_V = np.empty_like(raw_U)
    for placement in layout.blocks:
        positions = placement.positions
        source = np.asarray(
            [source_positions[key] for key in placement.block.canonical_keys],
            dtype=np.int64,
        )
        canonical_u_block = U[source, :]
        canonical_v_block = V[source, :]
        raw_U[positions, :] = placement.block.canonical_to_raw @ canonical_u_block
        raw_V[positions, :] = placement.block.canonical_to_raw @ canonical_v_block
    if not np.isfinite(raw_U).all() or not np.isfinite(raw_V).all():
        raise ValueError("reconstructed owner-local U/V arrays are nonfinite")
    return RawOwnerLocalBasis(layout.gamma_rows_local, raw_U, raw_V)


def audit_owner_local_basis_round_trip(
    layout: GammaCanonicalLayout,
    raw_U: np.ndarray,
    raw_V: np.ndarray,
    canonical_basis: CanonicalOwnerLocalBasis,
    *,
    tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    """Audit canonical-packet to raw owner-row reconstruction blockwise.

    Only one entity block is materialized at a time.  The returned errors are
    owner-local diagnostics; no FE-sized numeric array is gathered or copied.
    """

    raw_U, raw_V = _validate_basis_arrays(layout, raw_U, raw_V)
    keys = _normalise_keys(canonical_basis.keys)
    canonical_U = np.asarray(canonical_basis.U)
    canonical_V = np.asarray(canonical_basis.V)
    if (
        canonical_U.dtype != np.dtype(np.complex128)
        or canonical_V.dtype != np.dtype(np.complex128)
        or canonical_U.ndim != 2
        or canonical_V.shape != canonical_U.shape
        or canonical_U.shape[0] != len(keys)
    ):
        raise ValueError("canonical packet U/V arrays have the wrong shape")
    if not np.isfinite(canonical_U).all() or not np.isfinite(canonical_V).all():
        raise ValueError("canonical packet U/V arrays are nonfinite")
    if set(keys) != set(layout.canonical_keys):
        raise ValueError("canonical packet keys do not cover the current layout")
    source_positions = {key: index for index, key in enumerate(keys)}
    u_error = 0.0
    v_error = 0.0
    for placement in layout.blocks:
        block = placement.block
        positions = placement.positions
        source = np.asarray(
            [source_positions[key] for key in block.canonical_keys],
            dtype=np.int64,
        )
        expected_U = block.canonical_to_raw @ canonical_U[source, :]
        expected_V = block.canonical_to_raw @ canonical_V[source, :]
        actual_U = raw_U[positions, :]
        actual_V = raw_V[positions, :]
        u_error = max(
            u_error,
            float(np.linalg.norm(actual_U - expected_U))
            / max(float(np.linalg.norm(expected_U)), 1.0e-30),
        )
        v_error = max(
            v_error,
            float(np.linalg.norm(actual_V - expected_V))
            / max(float(np.linalg.norm(expected_V)), 1.0e-30),
        )
    maximum = max(u_error, v_error)
    return {
        "U_relative_error": u_error,
        "V_relative_error": v_error,
        "max_relative_error": maximum,
        "tolerance": float(tolerance),
        "pass": bool(np.isfinite(maximum) and maximum <= tolerance),
        "block_count": len(layout.blocks),
        "basis_global_replicated": False,
    }
