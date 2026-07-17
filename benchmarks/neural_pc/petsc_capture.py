from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.neural_pc.data_contract import save_operator
from src.solvers.local_slab_solver import LocalCsrOperator


class LocalSlabCapture:
    """Bounded owner-rank capture for operators and real smoother samples."""

    def __init__(
        self,
        root: Path,
        *,
        rank: int,
        maximum_samples_per_slab: int = 128,
        sample_stride: int = 10,
        run_metadata: dict[str, Any] | None = None,
    ) -> None:
        if maximum_samples_per_slab < 1 or sample_stride < 1:
            raise ValueError("capture limit and stride must be positive")
        self.root = Path(root) / f"rank_{int(rank):04d}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.rank = int(rank)
        self.maximum_samples_per_slab = int(maximum_samples_per_slab)
        self.sample_stride = int(sample_stride)
        self.run_metadata = dict(run_metadata or {})
        self.seen: dict[int, int] = {}
        self.saved: dict[int, int] = {}
        self.operator_fingerprints: dict[int, str] = {}

    def observe_operator(self, slab: int, operator: LocalCsrOperator) -> None:
        slab_id = int(slab)
        directory = self.root / f"slab_{slab_id:03d}"
        metadata = dict(operator.metadata)
        metadata.update(self.run_metadata)
        portable = LocalCsrOperator(
            shape=operator.shape,
            indptr=operator.indptr,
            indices=operator.indices,
            values=operator.values,
            metadata=metadata,
        )
        save_operator(directory, portable)
        self.operator_fingerprints[slab_id] = portable.fingerprint

    def observe_sample(
        self,
        slab: int,
        rhs: np.ndarray,
        local_correction: np.ndarray,
        local_solver_type: str,
    ) -> None:
        slab_id = int(slab)
        seen = self.seen.get(slab_id, 0) + 1
        self.seen[slab_id] = seen
        saved = self.saved.get(slab_id, 0)
        if seen % self.sample_stride or saved >= self.maximum_samples_per_slab:
            return
        directory = self.root / f"slab_{slab_id:03d}" / "real_krylov"
        directory.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            directory / f"sample_{saved:06d}.npz",
            rhs=np.asarray(rhs, dtype=np.complex128),
            local_correction=np.asarray(local_correction, dtype=np.complex128),
            local_solver_type=np.asarray(str(local_solver_type)),
            apply_index=np.asarray(seen, dtype=np.int64),
        )
        self.saved[slab_id] = saved + 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "identity": "local_slab_capture",
            "rank": self.rank,
            "root": str(self.root),
            "sample_stride": self.sample_stride,
            "maximum_samples_per_slab": self.maximum_samples_per_slab,
            "seen_by_slab": {str(key): value for key, value in sorted(self.seen.items())},
            "saved_by_slab": {str(key): value for key, value in sorted(self.saved.items())},
            "operator_fingerprints": {
                str(key): value for key, value in sorted(self.operator_fingerprints.items())
            },
        }

    def write_manifest(self) -> None:
        (self.root / "capture.json").write_text(
            json.dumps(self.diagnostics, indent=2, sort_keys=True), encoding="utf-8"
        )
