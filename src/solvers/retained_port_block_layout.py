"""NEW_UNQUALIFIED retained-port reconstruction, authored after source loss.

This is new numerical code, not recovered historical bytes or qualification.
The bounded cached-cell contract borrows existing readonly ports/Di/XiB and
admits only absent or exactly zero Hlocal. Nonzero direct Hlocal is unsupported
even when the caller supplies a dense original-H block: its incorporation
cannot be established here, so construction stops rather than omitting it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

import numpy as np

from .original_port_blocks import (
    CachedCondensedPortBlock,
    CachedPortCorrection,
    DenseOriginalPortBlock,
    DiagonalOriginalPortBlock,
)


LEGACY_PORT_LAYOUT = "dense_legacy"
RESEARCH_PORT_LAYOUT = "cached_representation_research"
RECONSTRUCTION_STATUS = "NEW_UNQUALIFIED"
HHAT_RECIPE = "original_H+sum(scatter(Di@(XiB@gather(alpha))))"


@dataclass(frozen=True)
class _RetainedCellPortInventory:
    """Every supplied cell, in order, including zero-port cells."""

    ports: np.ndarray
    Di: np.ndarray
    XiB: np.ndarray
    Hlocal: np.ndarray | None


def _borrow_array(value: Any, name: str, *, integer: bool = False) -> np.ndarray:
    if not isinstance(value, np.ndarray):
        raise TypeError(f"{name} must be an actual borrowed NumPy array")
    if integer:
        if value.ndim != 1 or value.dtype.kind not in "iu":
            raise ValueError(f"{name} must be a one-dimensional integer array")
    elif value.dtype != np.dtype(np.complex128) or value.ndim != 2:
        raise ValueError(f"{name} must be a two-dimensional complex128 array")
    if value.flags.writeable:
        raise ValueError(f"{name} must already be readonly; the helper cannot freeze its owner")
    if not np.isfinite(value).all():
        raise ValueError(f"{name} must be finite")
    return value


def _validate_original(original: Any) -> None:
    if not isinstance(original, (DiagonalOriginalPortBlock, DenseOriginalPortBlock)):
        raise TypeError("original H must have an explicit diagonal or admitted dense representation")
    keys = tuple(tuple(key) for key in original.mode_keys)
    if len(keys) != original.count or len(set(keys)) != original.count:
        raise ValueError("original H mode keys must be complete and unique")
    json.dumps(keys, allow_nan=False)
    arrays = original.numeric_arrays
    if len(arrays) != 1:
        raise ValueError("original H must expose exactly its numerical payload")
    payload = arrays[0]
    if (not isinstance(payload, np.ndarray) or payload.dtype != np.dtype(np.complex128)
            or payload.flags.writeable or not np.isfinite(payload).all()):
        raise ValueError("original H payload must be finite readonly complex128")
    expected_shape = (original.count,) if isinstance(original, DiagonalOriginalPortBlock) else (original.count, original.count)
    if payload.shape != expected_shape or original.count <= 0:
        raise ValueError("original H payload shape differs from its representation")
    if isinstance(original, DiagonalOriginalPortBlock) and np.any(payload == 0):
        raise ValueError("original H diagonal must remain nonsingular")
    digest = hashlib.sha256(b"original-port-block.staging.v1\0")
    digest.update(original.representation.encode("ascii") + b"\0")
    digest.update(json.dumps(keys, separators=(",", ":")).encode("utf-8"))
    # Rowwise hashing reads an existing dense fallback without copying it.
    for row in payload:
        digest.update(np.asarray(row, dtype="<c16").tobytes(order="C"))
    if digest.hexdigest() != original.identity_sha256:
        raise ValueError("original H payload or ordered keys changed after construction")


def _validate_cell(cell: Any, index: int, mode_count: int) -> _RetainedCellPortInventory:
    for name in ("ports", "Di", "XiB", "Hlocal"):
        if not hasattr(cell, name):
            raise TypeError(f"cells[{index}] lacks the cached-cell field {name}")
    ports = _borrow_array(cell.ports, f"cells[{index}].ports", integer=True)
    di = _borrow_array(cell.Di, f"cells[{index}].Di")
    xib = _borrow_array(cell.XiB, f"cells[{index}].XiB")
    if (len(np.unique(ports)) != len(ports) or np.any(ports < 0)
            or np.any(ports >= mode_count)):
        raise ValueError(f"cells[{index}].ports are duplicate or outside original H")
    if di.shape != (len(ports), xib.shape[0]) or xib.shape[1] != len(ports):
        raise ValueError(f"cells[{index}] cached Di/XiB dimensions differ")
    hlocal = cell.Hlocal
    if hlocal is not None:
        hlocal = _borrow_array(hlocal, f"cells[{index}].Hlocal")
        if hlocal.shape != (len(ports), len(ports)):
            raise ValueError(f"cells[{index}].Hlocal shape differs from its ports")
        if np.any(hlocal != 0):
            raise NotImplementedError(
                "NEW_UNQUALIFIED cached-cell contract does not admit nonzero Hlocal; "
                "an explicit separately reviewed original-H incorporation is required"
            )
    return _RetainedCellPortInventory(ports, di, xib, hlocal)


def build_cached_port_representation(
    original_port_block: DiagonalOriginalPortBlock | DenseOriginalPortBlock,
    cells: Iterable[Any],
) -> tuple[DiagonalOriginalPortBlock | DenseOriginalPortBlock, CachedCondensedPortBlock]:
    """Borrow cached cell terms without an H/Hhat square or new solve/factor.

    The caller must pass its complete ordered cached-cell sequence. This helper
    records every supplied cell and detects later omission or replacement in
    that retained inventory; it cannot discover cells the caller never passed.
    No Bi, LU, trace cache, or provider is accessed. The existing original-H
    solve remains on the returned original object, separate from Hhat action.
    """

    _validate_original(original_port_block)
    inventory = tuple(_validate_cell(cell, index, original_port_block.count)
                      for index, cell in enumerate(cells))
    corrections = tuple(CachedPortCorrection(cell.ports, cell.Di, cell.XiB)
                        for cell in inventory if len(cell.ports))
    condensed = CachedCondensedPortBlock(original_port_block, corrections)
    # Existing provider/evidence code iterates only nonempty corrections.
    # Empty cells and optional Hlocal are retained separately, without copies.
    condensed._retained_cell_port_inventory = inventory
    condensed._retained_complete_cell_count = len(inventory)
    return original_port_block, condensed


def _payload_sha256(array: np.ndarray, *, native: bool) -> str:
    """Bounded rowwise hash; legacy correction hashes keep complex casting."""

    dtype = array.dtype if native else np.dtype(np.complex128)
    digest = hashlib.sha256(repr((array.shape, str(dtype))).encode("utf-8"))
    for row in array:
        digest.update(np.asarray(row, dtype=dtype).tobytes(order="C"))
    return digest.hexdigest()


def _backing_owner(array: np.ndarray) -> Any:
    owner: Any = array
    visited: set[int] = set()
    while id(owner) not in visited:
        visited.add(id(owner))
        if isinstance(owner, np.ndarray) and owner.base is not None:
            owner = owner.base
        elif isinstance(owner, memoryview):
            owner = owner.obj
        else:
            return owner
    raise ValueError("cyclic numerical backing ownership is unsupported")


def _unique_backing_inventory(named_arrays: list[tuple[str, np.ndarray]]) -> dict[str, Any]:
    owners: dict[int, dict[str, Any]] = {}
    for name, array in named_arrays:
        owner = _backing_owner(array)
        if id(owner) not in owners:
            if isinstance(owner, np.ndarray):
                byte_count = int(owner.nbytes)
            else:
                try:
                    byte_count = int(memoryview(owner).nbytes)
                except TypeError as error:
                    raise TypeError("cannot measure a borrowed array's backing buffer") from error
            owners[id(owner)] = {
                "backing_index": len(owners),
                "backing_type": type(owner).__name__,
                "backing_bytes": byte_count,
                "array_roles": [],
            }
        owners[id(owner)]["array_roles"].append(name)
    return {
        "unique_backing_count": len(owners),
        "named_unique_backing_bytes_including_borrowed": sum(item["backing_bytes"] for item in owners.values()),
        "backings": list(owners.values()),
        "named_inventory_is_not_RSS": True,
        "byte_scope": "named unique backing inventory including borrowed owners; not RSS or incremental allocation",
        "new_helper_owned_numeric_arrays": 0,
    }


def port_block_representation_identity(
    original_port_block: DiagonalOriginalPortBlock | DenseOriginalPortBlock,
    condensed_port_block: CachedCondensedPortBlock,
    *,
    layout: str = RESEARCH_PORT_LAYOUT,
) -> dict[str, Any]:
    """Hash all mode keys, original H, corrections, and the complete cell list.

    Compatible port_block/N hashes enumerate original H then only nonempty
    corrections. Native cell hashes additionally bind integer dtype, every
    zero-port cell and each absent/zero Hlocal sentinel. Backing bytes are a
    separate allocation inventory and never enter the numerical digest.
    """

    if layout != RESEARCH_PORT_LAYOUT:
        raise ValueError("this reconstructed identity supports only the explicit cached research layout")
    _validate_original(original_port_block)
    if not isinstance(condensed_port_block, CachedCondensedPortBlock):
        raise TypeError("condensed port block must be the cached representation")
    if condensed_port_block.original_h is not original_port_block:
        raise ValueError("condensed representation does not borrow this original H")
    inventory = getattr(condensed_port_block, "_retained_cell_port_inventory", None)
    count = getattr(condensed_port_block, "_retained_complete_cell_count", None)
    if not isinstance(inventory, tuple) or count != len(inventory):
        raise ValueError("complete retained cached-cell inventory is missing or truncated")
    expected_corrections = []
    cell_records = []
    cell_hashes = {}
    named_arrays = [(f"port_block/{index}", array)
                    for index, array in enumerate(condensed_port_block.numeric_arrays)]
    for index, cell in enumerate(inventory):
        if not isinstance(cell, _RetainedCellPortInventory):
            raise TypeError("retained inventory contains a foreign cell entry")
        _validate_cell(cell, index, original_port_block.count)
        arrays = (("ports", cell.ports), ("Di", cell.Di), ("XiB", cell.XiB))
        if cell.Hlocal is not None:
            arrays += (("Hlocal", cell.Hlocal),)
        names = {}
        for field, array in arrays:
            name = f"cell/{index}/{field}"
            names[field] = name
            cell_hashes[name] = _payload_sha256(array, native=True)
            named_arrays.append((name, array))
        cell_records.append({
            "cell_index": index,
            "port_count": len(cell.ports),
            "interior_count": cell.XiB.shape[0],
            "Hlocal_is_None": cell.Hlocal is None,
            "array_roles": names,
        })
        if len(cell.ports):
            expected_corrections.append(cell)
    corrections = condensed_port_block._corrections
    if len(corrections) != len(expected_corrections):
        raise ValueError("cached correction sequence omits or adds a retained nonempty cell")
    for correction, cell in zip(corrections, expected_corrections, strict=True):
        if (not isinstance(correction, CachedPortCorrection)
                or correction.port_indices is not cell.ports
                or correction.Di is not cell.Di or correction.XiB is not cell.XiB):
            raise ValueError("cached correction is not the exact ordered borrowed cell recipe")
    identity = {
        "schema": "retained-port-block-layout.new-unqualified.v1",
        "reconstruction_status": RECONSTRUCTION_STATUS,
        "qualified": False,
        "layout": layout,
        "ordered_mode_keys": [list(key) for key in original_port_block.mode_keys],
        "original_H_kind": original_port_block.representation,
        "original_H_identity_sha256": original_port_block.identity_sha256,
        "Hhat_recipe": HHAT_RECIPE,
        "all_cell_count": len(inventory),
        "correction_count": len(corrections),
        "cell_inventory": cell_records,
        "array_sha256": {f"port_block/{index}": _payload_sha256(array, native=False)
                         for index, array in enumerate(condensed_port_block.numeric_arrays)},
        "cell_array_sha256": cell_hashes,
        "Hlocal_contract": "None_or_exact_zero_only; nonzero_controlled_stop",
        "complete_cell_inventory_scope": "complete supplied ordered sequence; caller proves fixture completeness",
    }
    identity["numerical_identity_sha256"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    identity["backing_inventory"] = _unique_backing_inventory(named_arrays)
    return identity
