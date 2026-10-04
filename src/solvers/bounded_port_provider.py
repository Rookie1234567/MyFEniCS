"""Opt-in byte-bounded owner-local DtN supply and consumption.

No volume action or solver is implemented here. D is a bilinear row (dot),
not C^H; the adjoint uses its own conjugated coefficients. Only mode metadata
and O(Nport) amplitudes may outlive a visit. The source must not retain numeric
functionals. A consumer retaining an evicted functional is rejected.
"""

import hashlib
import json
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from types import MappingProxyType

import numpy as np


def json_bytes(value):
    def convert(v):
        if isinstance(v, (dict, MappingProxyType)):
            return {str(k): convert(w) for k, w in v.items()}
        if isinstance(v, (list, tuple, np.ndarray)):
            return [convert(w) for w in v]
        if isinstance(v, (complex, np.complexfloating)):
            return {"real": float(v.real), "imag": float(v.imag)}
        if isinstance(v, np.generic):
            return v.item()
        return v

    return json.dumps(
        convert(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def content_hash(arrays):
    h = hashlib.sha256()
    for key, value in sorted(arrays.items()):
        a = np.asarray(value)
        h.update(json_bytes([key, a.dtype.str, list(a.shape)]))
        h.update(memoryview(np.ascontiguousarray(a)).cast("B"))
    return h.hexdigest()


@dataclass(frozen=True)
class PortFunctional:
    mode_key: tuple
    coupling_rows: np.ndarray
    coupling_values: np.ndarray
    projection_rows: np.ndarray
    projection_values: np.ndarray
    normalization_h: float
    mode_identity: dict

    @property
    def arrays(self):
        return {
            k: getattr(self, k)
            for k in (
                "coupling_rows",
                "coupling_values",
                "projection_rows",
                "projection_values",
            )
        }

    @property
    def nbytes(self):
        return sum(a.nbytes for a in self.arrays.values()) + 8


class BoundedPortProvider:
    """Deterministic single-lease supply. Limits apply to cache and batch.

    A loader's ``upper_bytes(index)`` must bound the completed functional before
    allocation, and its creator workspace is reported separately. Persistent
    source numeric arrays are forbidden except an explicitly read-only file.
    Restart replays a complete visit, never resumes a partial collective.
    """

    def __init__(
        self,
        keys,
        identities,
        loader,
        *,
        source_identity,
        global_rows,
        ownership_range,
        slave_rows=(),
        max_modes=64,
        cache_bytes=64 * 2**20,
        collective_batch_stop=None,
    ):
        self.keys = tuple(tuple(k) for k in keys)
        self.identities = tuple(dict(i) for i in identities)
        if not self.keys or len(set(self.keys)) != len(self.keys):
            raise ValueError("ordered mode inventory: empty/duplicate keys")
        if len(self.keys) != len(self.identities):
            raise ValueError("ordered mode inventory length")
        for i, (key, row) in enumerate(zip(self.keys, self.identities, strict=True)):
            if row["mode_index"] != i or key != (
                i,
                row["side"],
                row["m"],
                row["n"],
                row["polarization"],
            ):
                raise ValueError("ordered mode identity mismatch")
        if not 0 < max_modes <= 64 or not 0 < cache_bytes <= 64 * 2**20:
            raise ValueError("fixed maximum mode/cache capacity")
        self.loader, self.source_identity = loader, str(source_identity)
        self.global_rows = int(global_rows)
        self.ownership_range = tuple(map(int, ownership_range))
        a, b = self.ownership_range
        if not 0 <= a <= b <= self.global_rows:
            raise ValueError("canonical ownership range")
        self.slaves = np.asarray(slave_rows, dtype=np.int64).copy()
        self.slaves.flags.writeable = False
        if np.any((self.slaves < a) | (self.slaves >= b)):
            raise ValueError("slave ownership")
        self.max_modes, self.cache_bytes = int(max_modes), int(cache_bytes)
        self.cache, self.references, self.array_references = OrderedDict(), [], []
        self.active = False
        self.collective_batch_stop = collective_batch_stop or (lambda stop: stop)
        self.stats = {
            "loads": 0,
            "hits": 0,
            "evictions": 0,
            "visits": 0,
            "cache_peak_bytes": 0,
            "lease_peak_bytes": 0,
            "created_live_peak": 0,
            "active_batches_peak": 0,
            "identity_bytes": len(json_bytes(self.identities)),
            "loading_seconds": 0.0,
            "hashing_seconds": 0.0,
        }
        self.batch_records = []  # scalar/hash-only receipts, never functional refs

    def _check_references(self):
        cached_ids = {id(v) for v in self.cache.values()}
        live = [ref for ref in self.references if ref() is not None]
        if any(id(ref()) not in cached_ids for ref in live):
            raise RuntimeError(
                "evicted numeric functional retained by creator/consumer"
            )
        self.references = live
        cached_arrays = {id(a) for f in self.cache.values() for a in f.arrays.values()}
        live_arrays = [ref for ref in self.array_references if ref() is not None]
        if any(id(ref()) not in cached_arrays for ref in live_arrays):
            raise RuntimeError("evicted numeric array retained by creator/consumer")
        self.array_references = live_arrays
        self.stats["created_live_peak"] = max(
            self.stats["created_live_peak"], len(live)
        )

    def clear(self):
        if self.active:
            raise RuntimeError("cannot clear a live batch")
        self.cache.clear()
        self._check_references()

    def invalidate(self, source_identity):
        self.clear()
        self.source_identity = str(source_identity)

    def _load(self, index):
        if index in self.cache:
            self.stats["hits"] += 1
            return self.cache[index]
        upper = int(self.loader.upper_bytes(index))
        if upper > self.cache_bytes:
            raise MemoryError(
                f"single-mode upper {upper} exceeds {self.cache_bytes}; surface-row tiling required"
            )
        while self.cache and (
            len(self.cache) >= self.max_modes
            or sum(f.nbytes for f in self.cache.values()) + upper > self.cache_bytes
        ):
            self.cache.popitem(last=False)
            self.stats["evictions"] += 1
        self._check_references()
        began = perf_counter()
        f = self.loader(index, self.source_identity)
        self.stats["loading_seconds"] += perf_counter() - began
        if (
            not isinstance(f, PortFunctional)
            or f.mode_key != self.keys[index]
            or json_bytes(f.mode_identity) != json_bytes(self.identities[index])
        ):
            raise ValueError("source/schema/ordered functional identity mismatch")
        if not 0 < f.normalization_h < float("inf") or f.nbytes > upper:
            raise ValueError("normalization/declared single-mode capacity")
        a, b = self.ownership_range
        for side in ("coupling", "projection"):
            rows, values = getattr(f, side + "_rows"), getattr(f, side + "_values")
            if (
                rows.dtype != np.int64
                or values.dtype != np.complex128
                or rows.shape != values.shape
            ):
                raise ValueError("functional dtype/shape")
            if (
                np.any((rows < a) | (rows >= b))
                or np.any(np.diff(rows) <= 0)
                or np.intersect1d(rows, self.slaves).size
                or not np.isfinite(values).all()
            ):
                raise ValueError("canonical owner/slave/finite functional")
            if rows.flags.writeable or values.flags.writeable:
                raise ValueError("source functionals must be read-only")
        began = perf_counter()
        digest = content_hash(f.arrays)
        expected = getattr(self.loader, "expected_hash", lambda _: None)(index)
        if expected is not None and expected != digest:
            raise ValueError("functional numeric content hash mismatch")
        self.stats["hashing_seconds"] += perf_counter() - began
        self.cache[index] = f
        self.references.append(weakref.ref(f))
        self.array_references.extend(weakref.ref(a) for a in f.arrays.values())
        self.stats["loads"] += 1
        self.stats["cache_peak_bytes"] = max(
            self.stats["cache_peak_bytes"], sum(v.nbytes for v in self.cache.values())
        )
        self.stats["created_live_peak"] = max(
            self.stats["created_live_peak"], len(self.references)
        )
        self.batch_records.append(
            {
                "index": index,
                "key": list(f.mode_key),
                "sha256": digest,
                "numeric_bytes": f.nbytes,
                "source_identity": self.source_identity,
            }
        )
        return f

    @contextmanager
    def batch(self, start):
        if self.active or not 0 <= start < len(self.keys):
            raise ValueError("single live batch/valid start required")
        stop, size, oversize = start, 0, False
        while stop < min(start + self.max_modes, len(self.keys)):
            upper = int(self.loader.upper_bytes(stop))
            if upper > self.cache_bytes:
                oversize = True
                break
            if size + upper > self.cache_bytes:
                break
            size += upper
            stop += 1
        # Every rank, including an empty owner, must take the same collective
        # path. One oversized rank publishes start; all ranks reject together.
        stop = int(self.collective_batch_stop(start if oversize else stop))
        if stop <= start:
            raise MemoryError(
                "single-mode upper exceeds cache; surface-row tiling required"
            )
        fs = tuple(self._load(i) for i in range(start, stop))
        self.active = True
        self.stats["active_batches_peak"] = 1
        self.stats["lease_peak_bytes"] = max(
            self.stats["lease_peak_bytes"], sum(v.nbytes for v in fs)
        )
        try:
            yield fs
        finally:
            self.active = False
            del fs

    def visit(self, consumer):
        start = 0
        try:
            while start < len(self.keys):
                with self.batch(start) as fs:
                    stop = start + len(fs)
                    consumer(start, fs)
                del fs
                start = stop
            self.stats["visits"] += 1
        except BaseException:
            # No partial output is published by the action. Reentry starts at 0.
            self.active = False
            raise


class BoundedPortAction:
    """Owner-local arrays and fixed collective order; no PETSc Mat required."""

    def __init__(self, provider, *, allreduce=None):
        self.provider = provider
        self.reduce = (lambda x: x.copy()) if allreduce is None else allreduce
        self.costs = {
            "apply": 0.0,
            "adjoint": 0.0,
            "recovery": 0.0,
            "modal_rhs": 0.0,
            "reduction": 0.0,
        }
        self.counts = {
            "apply": 0,
            "adjoint": 0,
            "recovery": 0,
            "modal_rhs": 0,
            "reductions": 0,
        }

    def _input(self, x):
        x = np.asarray(x, dtype=np.complex128)
        a, b = self.provider.ownership_range
        if x.shape != (b - a,) or not np.isfinite(x).all():
            raise ValueError("owner-local input layout/finite")
        return x

    def _reduce(self, x):
        began = perf_counter()
        y = self.reduce(x)
        self.costs["reduction"] += perf_counter() - began
        self.counts["reductions"] += 1
        return y

    def apply(self, x, *, adjoint=False):
        x = self._input(x)
        y = np.zeros_like(x)
        begin = self.provider.ownership_range[0]
        role = "adjoint" if adjoint else "apply"
        began = perf_counter()

        def consume(start, fs):
            local = np.zeros(len(fs), dtype=np.complex128)
            for i, f in enumerate(fs):
                local[i] = (
                    np.vdot(f.coupling_values, x[f.coupling_rows - begin])
                    if adjoint
                    else np.dot(f.projection_values, x[f.projection_rows - begin])
                )
            modal = self._reduce(local)
            for i, f in enumerate(fs):
                if adjoint:
                    y[f.projection_rows - begin] += (
                        modal[i] / f.normalization_h * f.projection_values.conj()
                    )
                else:
                    y[f.coupling_rows - begin] += (
                        modal[i] / f.normalization_h * f.coupling_values
                    )

        self.provider.visit(consume)
        self.costs[role] += perf_counter() - began
        self.counts[role] += 1
        return y

    def recover(self, x):
        x = self._input(x)
        y = np.empty(len(self.provider.keys), dtype=np.complex128)
        begin = self.provider.ownership_range[0]
        began = perf_counter()

        def consume(start, fs):
            local = np.array(
                [np.dot(f.projection_values, x[f.projection_rows - begin]) for f in fs]
            )
            y[start : start + len(fs)] = self._reduce(local) / np.array(
                [f.normalization_h for f in fs]
            )

        self.provider.visit(consume)
        self.costs["recovery"] += perf_counter() - began
        self.counts["recovery"] += 1
        return y

    def modal_rhs(self, alpha):
        alpha = np.asarray(alpha, dtype=np.complex128)
        if alpha.shape != (len(self.provider.keys),) or not np.isfinite(alpha).all():
            raise ValueError("complete ordered modal amplitudes required")
        begin, end = self.provider.ownership_range
        y = np.zeros(end - begin, dtype=np.complex128)
        began = perf_counter()

        def consume(start, fs):
            for i, f in enumerate(fs):
                y[f.coupling_rows - begin] += alpha[start + i] * f.coupling_values

        self.provider.visit(consume)
        self.costs["modal_rhs"] += perf_counter() - began
        self.counts["modal_rhs"] += 1
        return y
