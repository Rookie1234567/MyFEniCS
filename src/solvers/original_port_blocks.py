"""Isolated design prototype. Not integrated or numerically qualified.

Original H is the modal normalization block, not the condensed Hhat. This
module never infers D from B, reduces the mode set, or restricts a 3D field.
The carrier construction path owns only an M-entry complex128 diagonal.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Mapping
from typing import Any, Sequence

import numpy as np


def _keys(keys: Sequence[tuple[Any, ...]], count: int) -> tuple[tuple[Any, ...], ...]:
    result = tuple(tuple(key) for key in keys)
    if len(result) != count or len(set(result)) != count:
        raise ValueError("ordered mode keys must be complete and unique")
    # The current physical keys contain only strings and integers.
    json.dumps(result, allow_nan=False)
    return result


def _rhs(values: Any, count: int) -> np.ndarray:
    result = np.asarray(values, dtype=np.complex128)
    if result.ndim not in (1, 2) or result.shape[0] != count:
        raise ValueError("port vector/multiRHS has incompatible shape")
    if not np.isfinite(result).all():
        raise ValueError("port vector/multiRHS is nonfinite")
    return result


def _identity(kind: str, keys: tuple[tuple[Any, ...], ...], payload: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(b"original-port-block.staging.v1\0")
    digest.update(kind.encode("ascii") + b"\0")
    digest.update(json.dumps(keys, separators=(",", ":")).encode("utf-8"))
    digest.update(np.ascontiguousarray(payload, dtype="<c16").tobytes())
    return digest.hexdigest()


class DiagonalOriginalPortBlock:
    """Own one original-H diagonal; perform exactly M operations per RHS."""

    representation = "diagonal_original_H"

    def __init__(self, diagonal: Any, mode_keys: Sequence[tuple[Any, ...]]):
        values = np.asarray(diagonal, dtype=np.complex128)
        if values.ndim != 1 or not len(values):
            raise ValueError("original H diagonal must be a nonempty vector")
        if not np.isfinite(values).all() or np.any(values == 0):
            raise ValueError("original H diagonal must be finite and nonsingular")
        self.mode_keys = _keys(mode_keys, len(values))
        self._diagonal = np.array(values, dtype=np.complex128, copy=True, order="C")
        self._diagonal.flags.writeable = False
        self.identity_sha256 = _identity(self.representation, self.mode_keys, self._diagonal)

    @classmethod
    def from_carrier(cls, entries: Sequence[Any]):
        entries = tuple(entries)
        # Validate the actual FullspaceDtnModeFunctional schema without
        # importing PETSc or requiring a global carrier/matrix allocation.
        for index, item in enumerate(entries):
            required = ("mode_key", "normalization_h", "mode_identity",
                        "coupling_rows", "coupling_values", "projection_rows", "projection_values")
            if any(not hasattr(item, name) for name in required):
                raise TypeError("entry does not expose the actual fullspace carrier schema")
            identity = item.mode_identity
            if not isinstance(identity, Mapping):
                raise TypeError("carrier mode_identity must be a mapping")
            try:
                expected_key = (index, str(identity["side"]), int(identity["m"]),
                                int(identity["n"]), str(identity["polarization"]))
                identity_index = int(identity["mode_index"])
                identity_h = identity["projection_denominator"]
                if isinstance(identity_h, Mapping):
                    identity_h = complex(identity_h["real"], identity_h["imag"])
                else:
                    identity_h = complex(identity_h)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("carrier mode identity is incomplete or invalid") from error
            if identity_index != index or tuple(item.mode_key) != expected_key:
                raise ValueError("carrier mode order/key differs from its physical identity")
            if complex(item.normalization_h) != identity_h:
                raise ValueError("carrier original H differs from its physical identity")
        return cls(
            [complex(item.normalization_h) for item in entries],
            [tuple(item.mode_key) for item in entries],
        )

    @property
    def count(self) -> int:
        return len(self._diagonal)

    @property
    def diagonal(self) -> np.ndarray:
        """Borrow a readonly view; do not materialize an M-by-M array."""
        view = self._diagonal.view()
        view.flags.writeable = False
        return view

    def apply(self, values: Any) -> np.ndarray:
        values = _rhs(values, self.count)
        scale = self._diagonal if values.ndim == 1 else self._diagonal[:, None]
        return np.ascontiguousarray(scale * values)

    def solve(self, values: Any) -> np.ndarray:
        values = _rhs(values, self.count)
        scale = self._diagonal if values.ndim == 1 else self._diagonal[:, None]
        result = np.ascontiguousarray(values / scale)
        if not np.isfinite(result).all():
            raise FloatingPointError("original H solve returned nonfinite values")
        return result

    @property
    def numeric_arrays(self) -> tuple[np.ndarray, ...]:
        return (self._diagonal,)

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "representation": self.representation,
            "mode_count": self.count,
            "identity_sha256": self.identity_sha256,
            "resident_numeric_bytes": int(self._diagonal.nbytes),
            "resident_square_arrays": 0,
            "apply_complex_multiplications_per_rhs": self.count,
            "solve_complex_divisions_per_rhs": self.count,
            "dense_factorization_calls": 0,
            "retained_Hhat": False,
            "qualified": False,
        }

    def materialize_for_small_oracle(self, *, max_bytes: int) -> np.ndarray:
        required = 16 * self.count**2
        if required > int(max_bytes):
            raise MemoryError("explicit small-oracle H budget exceeded")
        result = np.zeros((self.count, self.count), dtype=np.complex128)
        indices = np.arange(self.count)
        result[indices, indices] = self._diagonal
        return result


class DenseOriginalPortBlock:
    """Explicit generic fallback for a genuinely nondiagonal original H.

    The caller must supply a reason and an allocation bound. This path keeps
    existing general complex/non-Hermitian semantics; it is not scalable.
    """

    representation = "explicit_generic_dense_original_H"

    def __init__(self, matrix: Any, mode_keys: Sequence[tuple[Any, ...]], *,
                 reason: str, max_bytes: int):
        values = np.asarray(matrix)
        if values.ndim != 2 or values.shape[0] != values.shape[1] or not len(values):
            raise ValueError("generic original H must be a nonempty square matrix")
        if not reason.strip():
            raise ValueError("generic fallback needs an explicit reason")
        if 16 * values.size > int(max_bytes):
            raise MemoryError("generic original-H allocation budget exceeded")
        if not np.isfinite(values).all():
            raise ValueError("generic original H is nonfinite")
        self.mode_keys = _keys(mode_keys, len(values))
        self.reason = reason
        self._matrix = np.array(values, dtype=np.complex128, copy=True, order="C")
        self._matrix.flags.writeable = False
        self.identity_sha256 = _identity(self.representation, self.mode_keys, self._matrix)

    @property
    def count(self) -> int:
        return len(self._matrix)

    def apply(self, values: Any) -> np.ndarray:
        return np.ascontiguousarray(self._matrix @ _rhs(values, self.count))

    def solve(self, values: Any) -> np.ndarray:
        result = np.ascontiguousarray(np.linalg.solve(self._matrix, _rhs(values, self.count)))
        if not np.isfinite(result).all():
            raise FloatingPointError("generic original H solve returned nonfinite values")
        return result

    @property
    def numeric_arrays(self) -> tuple[np.ndarray, ...]:
        return (self._matrix,)


@dataclass(frozen=True)
class CachedPortCorrection:
    """Borrow cached non-Hermitian Di and XiB; never create Di @ XiB."""

    port_indices: np.ndarray
    Di: np.ndarray
    XiB: np.ndarray


class CachedCondensedPortBlock:
    """Apply Hhat = original H + sum(local Di XiB) without a square Hhat.

    XiB must already be cached by the existing exact local condensation.
    This class performs no LU solves and does not replace original-H solve.
    """

    def __init__(self, original_h: Any, corrections: Sequence[CachedPortCorrection] = ()):
        if not isinstance(original_h, (DiagonalOriginalPortBlock, DenseOriginalPortBlock)):
            raise TypeError("Hhat needs an explicit original-H representation")
        self.original_h = original_h
        self._corrections = tuple(corrections)
        for correction in self._corrections:
            ports, di, xib = correction.port_indices, correction.Di, correction.XiB
            if not all(isinstance(a, np.ndarray) for a in (ports, di, xib)):
                raise TypeError("correction arrays must be borrowed NumPy arrays")
            if ports.ndim != 1 or ports.dtype.kind not in "iu":
                raise ValueError("correction ports must be integer indices")
            if len(np.unique(ports)) != len(ports) or np.any(ports < 0) or np.any(ports >= original_h.count):
                raise ValueError("correction ports are duplicate or out of range")
            if di.dtype != np.complex128 or xib.dtype != np.complex128:
                raise ValueError("cached Di and XiB must be complex128")
            if di.ndim != 2 or xib.ndim != 2 or di.shape != (len(ports), xib.shape[0]) or xib.shape[1] != len(ports):
                raise ValueError("cached Di/XiB dimensions are incompatible")
            if not np.isfinite(di).all() or not np.isfinite(xib).all():
                raise ValueError("cached Di/XiB is nonfinite")
            if di.flags.writeable or xib.flags.writeable or ports.flags.writeable:
                raise ValueError("borrowed cached correction arrays must be readonly")

    def apply(self, values: Any) -> np.ndarray:
        values = _rhs(values, self.original_h.count)
        result = self.original_h.apply(values)
        for correction in self._corrections:
            result[correction.port_indices] += correction.Di @ (
                correction.XiB @ values[correction.port_indices]
            )
        return np.ascontiguousarray(result)

    @property
    def numeric_arrays(self) -> tuple[np.ndarray, ...]:
        return self.original_h.numeric_arrays + tuple(
            array for correction in self._corrections
            for array in (correction.port_indices, correction.Di, correction.XiB)
        )

    @property
    def audit(self) -> dict[str, Any]:
        owners = {}
        for array in self.numeric_arrays:
            owner = array
            while isinstance(getattr(owner, "base", None), np.ndarray):
                owner = owner.base
            owners[id(owner)] = int(owner.nbytes)
        return {
            "representation": "original_H_plus_borrowed_cached_Di_XiB",
            "correction_count": len(self._corrections),
            "new_square_Hhat_arrays": 0,
            "new_correction_factor_copies": 0,
            "new_local_LU_solves_per_apply": 0,
            "named_unique_backing_bytes_including_borrowed": sum(owners.values()),
            "correction_complex_matmul_terms_per_rhs": sum(
                2 * len(c.port_indices) * c.XiB.shape[0] for c in self._corrections
            ),
            "byte_scope": "named backing inventory, not process RSS or added bytes",
            "qualified": False,
        }
