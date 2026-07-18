from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .batched_reduced_smoother import FrozenLinearReducedMap


TINY = np.finfo(float).tiny
SCHEMA = "myfenics.task006.low_storage_proxy.v1"
_UINT64_MASK = np.uint64(0xFFFFFFFFFFFFFFFF)


def _splitmix64(values: np.ndarray, seed: int) -> np.ndarray:
    data = np.asarray(values, dtype=np.uint64) + np.uint64(seed)
    with np.errstate(over="ignore"):
        data = (data + np.uint64(0x9E3779B97F4A7C15)) & _UINT64_MASK
        data = ((data ^ (data >> np.uint64(30))) * np.uint64(
            0xBF58476D1CE4E5B9
        )) & _UINT64_MASK
        data = ((data ^ (data >> np.uint64(27))) * np.uint64(
            0x94D049BB133111EB
        )) & _UINT64_MASK
        return data ^ (data >> np.uint64(31))


def count_sketch_hash_sign(
    size: int, *, q: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    if size <= 0 or q <= 0:
        raise ValueError("CountSketch size and q must be positive")
    hashed = _splitmix64(np.arange(size, dtype=np.uint64), seed)
    buckets = np.asarray(hashed % np.uint64(q), dtype=np.int64)
    signs = np.where((hashed >> np.uint64(63)) == 0, 1.0, -1.0)
    return buckets, signs


def procedural_count_sketch(
    values: np.ndarray, *, q: int, seed: int
) -> np.ndarray:
    source = np.asarray(values, dtype=np.complex128)
    if source.ndim not in {1, 2}:
        raise ValueError("procedural CountSketch expects a vector or row batch")
    was_vector = source.ndim == 1
    batch = source[None, :] if was_vector else source
    buckets, signs = count_sketch_hash_sign(batch.shape[1], q=q, seed=seed)
    target = np.zeros((batch.shape[0], q), dtype=np.complex128)
    row_indices = np.broadcast_to(
        np.arange(batch.shape[0], dtype=np.int64)[:, None], batch.shape
    )
    bucket_indices = np.broadcast_to(buckets[None, :], batch.shape)
    np.add.at(target, (row_indices, bucket_indices), batch * signs[None, :])
    return target[0] if was_vector else target


@dataclass(frozen=True)
class ProxyDecision:
    accepted: bool
    reason: str
    rho_reduced: float
    rho_sketches: tuple[float, ...]
    composite_score: float
    baseline_composite_score: float
    input_norm: float
    output_norm: float
    correction_input_ratio: float


@dataclass(frozen=True)
class LowStorageProxyCertificate:
    slab_id: int
    operator_fingerprint: str
    checkpoint_sha256: str
    reduced_operator: np.ndarray
    sketch_products: tuple[np.ndarray, ...]
    sketch_q: int
    sketch_seeds: tuple[int, ...]
    score_scales: tuple[float, ...]
    acceptance_threshold: float
    nondegradation_ratio_threshold: float
    input_norm_range: tuple[float, float]
    output_norm_range: tuple[float, float]
    correction_input_ratio_range: tuple[float, float]

    def __post_init__(self) -> None:
        reduced = np.asarray(self.reduced_operator, dtype=np.complex128)
        products = tuple(
            np.asarray(product, dtype=np.complex128)
            for product in self.sketch_products
        )
        if reduced.ndim != 2 or reduced.shape[0] != reduced.shape[1]:
            raise ValueError("reduced proxy operator must be square")
        if len(products) != len(self.sketch_seeds) or not products:
            raise ValueError("proxy sketch products and seeds must be nonempty")
        if any(
            product.shape != (self.sketch_q, reduced.shape[1])
            for product in products
        ):
            raise ValueError("proxy sketch product shape mismatch")
        if len(self.score_scales) != 1 + len(products):
            raise ValueError("proxy score scales must cover reduced and sketches")
        if (
            not np.all(np.isfinite(reduced))
            or not all(np.all(np.isfinite(product)) for product in products)
            or not all(np.isfinite(value) and value > 0 for value in self.score_scales)
        ):
            raise ValueError("proxy certificate contains invalid values")
        object.__setattr__(self, "reduced_operator", reduced)
        object.__setattr__(self, "sketch_products", products)

    @property
    def storage_bytes(self) -> int:
        arrays = self.reduced_operator.nbytes + sum(
            product.nbytes for product in self.sketch_products
        )
        metadata = (
            len(self.sketch_seeds) * np.dtype(np.int64).itemsize
            + len(self.score_scales) * np.dtype(np.float64).itemsize
            + 7 * np.dtype(np.float64).itemsize
        )
        return int(arrays + metadata)

    def save(self, directory: Path) -> None:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        arrays = {"reduced_operator": self.reduced_operator}
        arrays.update(
            {
                f"sketch_product_{index}": product
                for index, product in enumerate(self.sketch_products)
            }
        )
        np.savez_compressed(target / "certificate.npz", **arrays)
        metadata = {
            "schema": SCHEMA,
            "slab_id": self.slab_id,
            "operator_fingerprint": self.operator_fingerprint,
            "checkpoint_sha256": self.checkpoint_sha256,
            "sketch_q": self.sketch_q,
            "sketch_seeds": list(self.sketch_seeds),
            "score_scales": list(self.score_scales),
            "acceptance_threshold": self.acceptance_threshold,
            "nondegradation_ratio_threshold": (
                self.nondegradation_ratio_threshold
            ),
            "input_norm_range": list(self.input_norm_range),
            "output_norm_range": list(self.output_norm_range),
            "correction_input_ratio_range": list(
                self.correction_input_ratio_range
            ),
            "storage_bytes": self.storage_bytes,
        }
        (target / "certificate.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )


class LowStorageAuditProxy:
    def __init__(
        self,
        model: FrozenLinearReducedMap,
        certificate: LowStorageProxyCertificate,
    ) -> None:
        if model.operator_fingerprint != certificate.operator_fingerprint:
            raise ValueError("proxy model/operator fingerprint mismatch")
        if model.checkpoint_sha256 != certificate.checkpoint_sha256:
            raise ValueError("proxy checkpoint checksum mismatch")
        rank = model.output_basis.shape[1]
        if certificate.reduced_operator.shape != (rank, rank):
            raise ValueError("proxy/model reduced rank mismatch")
        self.model = model
        self.certificate = certificate
        self.apply_count = 0
        self.accept_count = 0
        self._destroyed = False

    def evaluate(
        self,
        rhs: np.ndarray,
        correction: np.ndarray,
        *,
        baseline_correction: np.ndarray | None = None,
        slab_id: int,
        operator_fingerprint: str,
        checkpoint_sha256: str,
    ) -> ProxyDecision:
        if self._destroyed:
            raise RuntimeError("low-storage proxy has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        candidate = np.asarray(correction, dtype=np.complex128)
        baseline = (
            None
            if baseline_correction is None
            else np.asarray(baseline_correction, dtype=np.complex128)
        )
        if source.shape != (self.model.size,) or candidate.shape != source.shape:
            raise ValueError("proxy rhs/correction shape mismatch")
        if baseline is not None and baseline.shape != source.shape:
            raise ValueError("proxy baseline correction shape mismatch")
        identity_ok = (
            int(slab_id) == self.certificate.slab_id
            and operator_fingerprint == self.certificate.operator_fingerprint
            and checkpoint_sha256 == self.certificate.checkpoint_sha256
        )
        finite = bool(
            np.all(np.isfinite(source))
            and np.all(np.isfinite(candidate))
            and (baseline is None or np.all(np.isfinite(baseline)))
        )
        if not finite:
            return self._decision(False, "nonfinite", source, candidate)
        if not identity_ok:
            return self._decision(False, "identity_mismatch", source, candidate)

        input_norm = float(np.linalg.norm(source))
        output_norm = float(np.linalg.norm(candidate))
        ratio = output_norm / max(input_norm, TINY)
        if not _within(input_norm, self.certificate.input_norm_range):
            return self._decision(False, "input_norm", source, candidate)
        if not _within(output_norm, self.certificate.output_norm_range):
            return self._decision(False, "output_norm", source, candidate)
        if not _within(
            ratio, self.certificate.correction_input_ratio_range
        ):
            return self._decision(False, "correction_input_ratio", source, candidate)

        rho_reduced, rho_sketches, composite = self._score(source, candidate)
        baseline_composite = (
            float("inf")
            if baseline is None
            else self._score(source, baseline)[2]
        )
        accepted = bool(
            composite <= self.certificate.acceptance_threshold
            and (
                baseline is None
                or composite
                <= self.certificate.nondegradation_ratio_threshold
                * max(baseline_composite, TINY)
            )
        )
        self.apply_count += 1
        self.accept_count += int(accepted)
        return ProxyDecision(
            accepted=accepted,
            reason="accepted" if accepted else "composite_score",
            rho_reduced=rho_reduced,
            rho_sketches=tuple(rho_sketches),
            composite_score=float(composite),
            baseline_composite_score=baseline_composite,
            input_norm=input_norm,
            output_norm=output_norm,
            correction_input_ratio=ratio,
        )

    def _decision(
        self,
        accepted: bool,
        reason: str,
        source: np.ndarray,
        candidate: np.ndarray,
    ) -> ProxyDecision:
        input_norm = float(np.linalg.norm(source))
        output_norm = float(np.linalg.norm(candidate))
        self.apply_count += 1
        self.accept_count += int(accepted)
        return ProxyDecision(
            accepted=accepted,
            reason=reason,
            rho_reduced=float("inf"),
            rho_sketches=tuple(
                float("inf") for _ in self.certificate.sketch_seeds
            ),
            composite_score=float("inf"),
            baseline_composite_score=float("inf"),
            input_norm=input_norm,
            output_norm=output_norm,
            correction_input_ratio=output_norm / max(input_norm, TINY),
        )

    def _score(
        self, source: np.ndarray, correction: np.ndarray
    ) -> tuple[float, tuple[float, ...], float]:
        input_coordinates = self.model.input_basis.conj().T @ source
        output_coordinates = self.model.output_basis.conj().T @ correction
        reduced_residual = (
            input_coordinates
            - self.certificate.reduced_operator @ output_coordinates
        )
        rho_reduced = float(
            np.linalg.norm(reduced_residual)
            / max(float(np.linalg.norm(input_coordinates)), TINY)
        )
        rho_sketches = []
        for seed, product in zip(
            self.certificate.sketch_seeds,
            self.certificate.sketch_products,
            strict=True,
        ):
            sketched_rhs = procedural_count_sketch(
                source, q=self.certificate.sketch_q, seed=seed
            )
            sketched_residual = sketched_rhs - product @ output_coordinates
            rho_sketches.append(
                float(
                    np.linalg.norm(sketched_residual)
                    / max(float(np.linalg.norm(sketched_rhs)), TINY)
                )
            )
        components = (rho_reduced, *rho_sketches)
        composite = max(
            scale * value
            for scale, value in zip(
                self.certificate.score_scales, components, strict=True
            )
        )
        return rho_reduced, tuple(rho_sketches), float(composite)

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "identity": "low_storage_composite_proxy",
            "apply_count": self.apply_count,
            "accept_count": self.accept_count,
            "accept_fraction": self.accept_count / max(self.apply_count, 1),
            "proxy_storage_bytes": self.certificate.storage_bytes,
            "private_persistent_local_csr_bytes": 0,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        self._destroyed = True


def _within(value: float, bounds: Sequence[float]) -> bool:
    return bool(np.isfinite(value) and float(bounds[0]) <= value <= float(bounds[1]))


def certificate_content_hash(
    certificate: LowStorageProxyCertificate,
) -> str:
    digest = hashlib.sha256()
    digest.update(certificate.reduced_operator.tobytes())
    for product in certificate.sketch_products:
        digest.update(product.tobytes())
    digest.update(
        json.dumps(
            {
                "slab": certificate.slab_id,
                "fingerprint": certificate.operator_fingerprint,
                "checkpoint": certificate.checkpoint_sha256,
                "q": certificate.sketch_q,
                "seeds": certificate.sketch_seeds,
                "scales": certificate.score_scales,
                "threshold": certificate.acceptance_threshold,
                "ratio_threshold": certificate.nondegradation_ratio_threshold,
                "input": certificate.input_norm_range,
                "output": certificate.output_norm_range,
                "ratio": certificate.correction_input_ratio_range,
            },
            sort_keys=True,
        ).encode()
    )
    return digest.hexdigest()
