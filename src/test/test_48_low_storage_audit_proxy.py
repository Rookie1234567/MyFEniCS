from __future__ import annotations

import numpy as np
import pytest

from src.solvers.batched_reduced_smoother import FrozenLinearReducedMap
from src.solvers.low_storage_audit_proxy import (
    LowStorageAuditProxy,
    LowStorageProxyCertificate,
    count_sketch_hash_sign,
    procedural_count_sketch,
)


def _proxy() -> LowStorageAuditProxy:
    size, rank, q = 12, 3, 5
    input_basis = np.eye(size, rank, dtype=np.complex128)
    output_basis = np.eye(size, rank, dtype=np.complex128)
    model = FrozenLinearReducedMap(
        input_basis,
        np.eye(rank, dtype=np.complex128),
        output_basis,
        "operator",
        "checkpoint",
    )
    seeds = (17, 29)
    products = tuple(
        procedural_count_sketch(output_basis.T, q=q, seed=seed).T
        for seed in seeds
    )
    certificate = LowStorageProxyCertificate(
        slab_id=2,
        operator_fingerprint="operator",
        checkpoint_sha256="checkpoint",
        reduced_operator=np.eye(rank, dtype=np.complex128),
        sketch_products=products,
        sketch_q=q,
        sketch_seeds=seeds,
        score_scales=(1.0, 1.0, 1.0),
        acceptance_threshold=1.0e-12,
        input_norm_range=(0.1, 10.0),
        output_norm_range=(0.1, 10.0),
        correction_input_ratio_range=(0.1, 2.0),
    )
    return LowStorageAuditProxy(model, certificate)


def test_procedural_count_sketch_is_deterministic_and_batch_equal() -> None:
    rng = np.random.default_rng(41)
    values = rng.standard_normal((7, 31)) + 1j * rng.standard_normal((7, 31))
    batched = procedural_count_sketch(values, q=11, seed=73)
    independent = np.stack(
        [procedural_count_sketch(row, q=11, seed=73) for row in values]
    )
    np.testing.assert_array_equal(batched, independent)
    buckets, signs = count_sketch_hash_sign(31, q=11, seed=73)
    assert buckets.shape == signs.shape == (31,)
    assert set(np.unique(signs)) <= {-1.0, 1.0}
    assert buckets.nbytes + signs.nbytes < 11 * 31 * 8


def test_low_storage_proxy_accepts_exact_reduced_action_and_has_no_csr() -> None:
    proxy = _proxy()
    rhs = np.asarray([1.0, 0.5j, -0.25] + [0.0] * 9, dtype=np.complex128)
    decision = proxy.evaluate(
        rhs,
        rhs,
        slab_id=2,
        operator_fingerprint="operator",
        checkpoint_sha256="checkpoint",
    )
    assert decision.accepted is True
    assert decision.composite_score <= 1.0e-12
    assert proxy.diagnostics["private_persistent_local_csr_bytes"] == 0
    assert proxy.diagnostics["proxy_storage_bytes"] > 0


@pytest.mark.parametrize("kind", ("nan", "identity", "norm"))
def test_low_storage_proxy_fails_closed(kind: str) -> None:
    proxy = _proxy()
    rhs = np.asarray([1.0, 0.5j, -0.25] + [0.0] * 9, dtype=np.complex128)
    candidate = rhs.copy()
    slab_id = 2
    if kind == "nan":
        candidate[0] = np.nan
    elif kind == "identity":
        slab_id = 3
    else:
        candidate *= 100.0
    decision = proxy.evaluate(
        rhs,
        candidate,
        slab_id=slab_id,
        operator_fingerprint="operator",
        checkpoint_sha256="checkpoint",
    )
    assert decision.accepted is False
    proxy.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        proxy.evaluate(
            rhs,
            rhs,
            slab_id=2,
            operator_fingerprint="operator",
            checkpoint_sha256="checkpoint",
        )
