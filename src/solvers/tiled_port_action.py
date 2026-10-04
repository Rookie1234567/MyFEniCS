"""Two-pass DtN port action with bounded, unthresholded surface tiles.

Rows can repeat between tiles: they are assembled with addition. Within each
mode D is a bilinear row and C is independent. Only one tile is leased at a
time; the first traversal reduces a scalar, the second scatters its traction.
The source supplies bounded geometry/readers, never a full target FE vector.
"""

import hashlib
import weakref
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from src.solvers.bounded_port_provider import content_hash, json_bytes


@dataclass(frozen=True)
class PortTile:
    tile_id: str
    coupling_rows: np.ndarray
    coupling_values: np.ndarray
    projection_rows: np.ndarray
    projection_values: np.ndarray

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
        return sum(a.nbytes for a in self.arrays.values())


class TiledPortAction:
    def __init__(
        self,
        identities,
        source,
        *,
        source_identity,
        global_rows,
        ownership_range,
        tile_bytes=2**20,
        cache_bytes=64 * 2**20,
        max_modes=64,
        reduce_sum=None,
        collective_all=None,
    ):
        self.identities = tuple(dict(i) for i in identities)
        self.identity_bytes = tuple(json_bytes(i) for i in self.identities)
        self.source, self.source_identity = source, str(source_identity)
        self.global_rows, self.ownership_range = (
            int(global_rows),
            tuple(ownership_range),
        )
        if not 0 < tile_bytes <= cache_bytes <= 64 * 2**20 or not 0 < max_modes <= 64:
            raise ValueError("tile/cache/mode capacity")
        a, b = self.ownership_range
        if not 0 <= a <= b <= self.global_rows:
            raise ValueError("canonical ownership")
        self.tile_bytes, self.max_modes = tile_bytes, max_modes
        self.reduce_sum = reduce_sum or (lambda x: x)
        self.collective_all = collective_all or (lambda x: x)
        self.plans = []
        error = None
        try:
            shared = getattr(source, "shared_tile_plans", None)
            tables = {} if shared is None else {k: tuple(v) for k, v in shared.items()}
            self.shared_plan_hash = hashlib.sha256(json_bytes(tables)).hexdigest()
            for i, row in enumerate(self.identities):
                if row["mode_index"] != i or not 0 < row[
                    "projection_denominator"
                ] < float("inf"):
                    raise ValueError("ordered mode/H identity")
                if shared is None:
                    plan = tuple(source.tile_ids(i))
                    expected = tuple(row["tile_ids"])
                else:
                    plan = tables[row["tile_plan_key"]]
                    expected = plan
                    if row["tile_plan_sha256"] != self.shared_plan_hash:
                        raise ValueError("shared ordered plan identity")
                if len(set(plan)) != len(plan) or plan != expected:
                    raise ValueError("missing/duplicate/reordered face inventory")
                self.plans.append(plan)
        except Exception as exc:  # noqa: BLE001 - propagate every local MPI stage failure
            error = exc
        self._agree(error, "mode/H/ordered inventory")
        self.receipts, self.references = {}, []
        self.active = False
        self.stats = {
            "tile_loads": 0,
            "numeric_cache_peak_bytes": 0,
            "creator_seconds": 0.0,
            "hash_seconds": 0.0,
            "projection_seconds": 0.0,
            "reduction_seconds": 0.0,
            "scatter_seconds": 0.0,
            "visits": 0,
            "passes": 0,
        }

    def _agree(self, error, stage):
        """All participants leave a failing stage before any later reduction."""
        if not self.collective_all(error is None):
            if error is not None:
                raise error
            raise ValueError("collective " + stage + " rejected on another rank")

    def _pass(self, index, consumer):
        identity = self.identities[index]
        error = None
        try:
            if json_bytes(identity) != self.identity_bytes[index]:
                raise ValueError("immutable mode/H identity changed")
            if hasattr(self.source, "shared_tile_plans"):
                digest = hashlib.sha256(
                    json_bytes(
                        {k: tuple(v) for k, v in self.source.shared_tile_plans.items()}
                    )
                ).hexdigest()
                if digest != self.shared_plan_hash:
                    raise ValueError("immutable shared ordered tile identity changed")
            elif tuple(self.source.tile_ids(index)) != self.plans[index]:
                raise ValueError("immutable ordered tile identity changed")
        except Exception as exc:  # noqa: BLE001 - propagate every local MPI stage failure
            error = exc
        self._agree(error, "identity")
        error = None
        try:
            safe = all(
                self.source.upper_bytes(index, t) <= self.tile_bytes
                for t in self.plans[index]
            )
        except Exception as exc:  # noqa: BLE001 - collective source failure
            error = exc
        self._agree(error, "capacity declaration")
        if not self.collective_all(safe):
            raise MemoryError("collective tile capacity rejected before allocation")
        digest = hashlib.sha256(json_bytes([self.source_identity, identity]))
        for tile_id in self.plans[index]:
            error = None
            try:
                if any(ref() is not None for ref in self.references):
                    raise RuntimeError("tile numeric arrays retained across lease")
                began = perf_counter()
                tile = self.source.load_tile(index, tile_id, self.source_identity)
                self.stats["creator_seconds"] += perf_counter() - began
                if (
                    not isinstance(tile, PortTile)
                    or tile.tile_id != tile_id
                    or tile.nbytes > self.source.upper_bytes(index, tile_id)
                ):
                    raise ValueError("tile schema/id/declared bound")
                a, b = self.ownership_range
                for side in ("coupling", "projection"):
                    rows, values = (
                        getattr(tile, side + "_rows"),
                        getattr(tile, side + "_values"),
                    )
                    if (
                        rows.dtype != np.int64
                        or values.dtype != np.complex128
                        or rows.shape != values.shape
                        or np.any((rows < a) | (rows >= b))
                        or np.any(np.diff(rows) <= 0)
                        or not np.isfinite(values).all()
                        or rows.flags.writeable
                        or values.flags.writeable
                    ):
                        raise ValueError("tile canonical rows/dtype/finite/readonly")
                began = perf_counter()
                numeric = content_hash(tile.arrays)
                expected = getattr(self.source, "expected_hash", lambda *_: None)(
                    index, tile_id
                )
                if expected is not None and numeric != expected:
                    raise ValueError("tile content hash")
                digest.update(json_bytes([tile_id, numeric]))
                self.stats["hash_seconds"] += perf_counter() - began
            except Exception as exc:  # noqa: BLE001 - propagate every local MPI stage failure
                error = exc
            self._agree(error, "load/schema/hash/row")
            self.stats["tile_loads"] += 1
            self.stats["numeric_cache_peak_bytes"] = max(
                self.stats["numeric_cache_peak_bytes"], tile.nbytes
            )
            self.references = [weakref.ref(v) for v in tile.arrays.values()]
            error = None
            try:
                consumer(tile)
            except Exception as exc:  # noqa: BLE001 - propagate every local MPI stage failure
                error = exc
            self._agree(error, "consumer")
            del rows, values, tile
        value = digest.hexdigest()
        previous = self.receipts.get(index)
        error = (
            ValueError("replay changed tile/H/source content")
            if previous is not None and previous["sha256"] != value
            else None
        )
        self._agree(error, "replay")
        self.receipts[index] = {
            "index": index,
            "sha256": value,
            "passes": (previous or {}).get("passes", 0) + 1,
            "tiles": len(self.plans[index]),
            "H": identity["projection_denominator"],
            "source": self.source_identity,
        }
        self.stats["passes"] += 1

    def _consume(self, x, *, adjoint=False, amplitudes_only=False, modal=False):
        if self.active:
            raise RuntimeError("one tiled operation at a time")
        a, b = self.ownership_range
        x = np.asarray(x, dtype=np.complex128)
        if (
            x.shape != ((len(self.identities),) if modal else (b - a,))
            or not np.isfinite(x).all()
        ):
            error = ValueError("owned FE/complete modal vector")
        else:
            error = None
        self._agree(error, "input shape/finite")
        out = np.zeros(
            (len(self.identities),) if amplitudes_only else (b - a,),
            dtype=np.complex128,
        )
        self.active = True
        try:
            for start in range(0, len(self.identities), self.max_modes):
                stop = min(start + self.max_modes, len(self.identities))
                scalars = (
                    x[start:stop].copy()
                    if modal
                    else np.zeros(stop - start, dtype=np.complex128)
                )
                if not modal:
                    for i in range(start, stop):

                        def project(tile, i=i, start=start, scalars=scalars):
                            began = perf_counter()
                            if adjoint:
                                scalars[i - start] += np.vdot(
                                    tile.coupling_values, x[tile.coupling_rows - a]
                                )
                            else:
                                scalars[i - start] += np.dot(
                                    tile.projection_values, x[tile.projection_rows - a]
                                )
                            self.stats["projection_seconds"] += perf_counter() - began

                        self._pass(i, project)
                    began = perf_counter()
                    scalars = self.reduce_sum(scalars)
                    self.stats["reduction_seconds"] += perf_counter() - began
                for i in range(start, stop):
                    h = self.identities[i]["projection_denominator"]
                    alpha = scalars[i - start] / (1 if modal else h)
                    if amplitudes_only:
                        out[i] = alpha
                    else:

                        def scatter(tile, alpha=alpha):
                            began = perf_counter()
                            if adjoint:
                                np.add.at(
                                    out,
                                    tile.projection_rows - a,
                                    tile.projection_values.conj() * alpha,
                                )
                            else:
                                np.add.at(
                                    out,
                                    tile.coupling_rows - a,
                                    tile.coupling_values * alpha,
                                )
                            self.stats["scatter_seconds"] += perf_counter() - began

                        self._pass(i, scatter)
            self.stats["visits"] += 1
            return out
        finally:
            self.active = False

    def apply(self, x, *, adjoint=False):
        return self._consume(x, adjoint=adjoint)

    def recover(self, x):
        return self._consume(x, amplitudes_only=True)

    def modal_rhs(self, alpha):
        return self._consume(alpha, modal=True)
