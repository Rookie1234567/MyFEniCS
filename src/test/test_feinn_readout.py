"""Independent small white-space SVD and frozen-output layout witnesses."""

import numpy as np
import pytest

from src.solvers.feinn_gqr import GramColumns, project, ReadoutStop


@pytest.mark.parametrize(
    "kind",
    ["full_rank", "duplicate", "near_correlated", "different_scales", "pure_imaginary"],
)
def test_G_QR_against_independent_whitened_SVD(kind):
    rng = np.random.default_rng(421501)
    B = rng.standard_normal((13, 13)) + 1j * rng.standard_normal((13, 13))
    G = B.conj().T @ B + np.eye(13)
    P = rng.standard_normal((13, 5)) + 1j * rng.standard_normal((13, 5))
    if kind == "duplicate":
        P[:, 4] = P[:, 1]
    if kind == "near_correlated":
        P[:, 4] = P[:, 1] + 1e-13 * P[:, 4]
    if kind == "different_scales":
        P *= np.array([1e-9, 1e3, 1e9, 1e-3, 1])
    d = rng.standard_normal(13) + 1j * rng.standard_normal(13)
    if kind == "pure_imaginary":
        d = P @ (1j * np.arange(1, 6))
    action = GramColumns(G)
    values, stats = project(P, d, d, action)
    # L^H whitens the field, using a factor only for this synthetic SPD test.
    W = np.linalg.cholesky(G).conj().T
    Pw = W @ P
    scaled = Pw / np.linalg.norm(Pw, axis=0)
    left, singular, vh = np.linalg.svd(scaled, full_matrices=False)
    keep = singular > singular[0] * 1e-12
    expected_w = left[:, keep] @ (left[:, keep].conj().T @ (W @ d))
    actual_w = W @ (P @ values["delta_a"])
    assert np.linalg.norm(actual_w - expected_w) / np.linalg.norm(W @ d) < 1e-10
    assert stats["retained_rank"] == sum(keep)
    assert stats["G_orthogonality_F"] < 1e-12
    assert stats["normalized_QR_G_F_relative"] < 1e-12
    assert stats["retained_optimality"] < 1e-12
    assert stats["nonincrease"]
    assert stats["pythagorean_defect"] < 1e-12
    assert action.count == sum(action.by_role.values())


def test_matmat_charges_every_column_and_expired_clock_starts_no_work():
    action = GramColumns(np.eye(4), limit=3)
    action(np.eye(4)[:, :3], "batch")
    assert action.count == 3
    with pytest.raises(ReadoutStop, match="G_COLUMN_BUDGET"):
        action(np.ones(4), "another")
    expired = GramColumns(np.eye(4), deadline=0)
    with pytest.raises(ReadoutStop, match="SAVE_WINDOW"):
        expired(np.ones(4), "never")
    assert expired.count == 0


def test_negative_G_norm_is_not_clipped():
    with pytest.raises(ValueError, match="NONPOSITIVE"):
        project(
            np.eye(2, dtype=complex),
            np.ones(2, complex),
            np.ones(2, complex),
            GramColumns(-np.eye(2)),
        )
