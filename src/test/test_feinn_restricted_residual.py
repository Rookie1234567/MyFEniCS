"""Independent SVD witnesses for non-Hermitian restricted actions and layout."""

import ast
from pathlib import Path

import numpy as np
import pytest

from src.solvers.feinn_restricted_residual import (
    original_readout,
    restricted_solve,
    load_basis,
    PROJECTION_KEYS,
)


@pytest.mark.parametrize(
    "kind", ["full_rank", "duplicate", "near_rank_deficient", "scales", "imaginary"]
)
def test_complex_householder_small_R_against_independent_SVD(kind):
    rng = np.random.default_rng(421601)
    A = rng.normal(size=(21, 21)) + 1j * rng.normal(size=(21, 21))
    Q = rng.normal(size=(21, 5)) + 1j * rng.normal(size=(21, 5))
    if kind == "duplicate":
        Q[:, 4] = Q[:, 1]
    if kind == "near_rank_deficient":
        Q[:, 4] = Q[:, 1] + 1e-13 * Q[:, 4]
    if kind == "scales":
        Q *= [1e-5, 1e3, 1, 1e-2, 1e5]
    f = rng.normal(size=21) + 1j * rng.normal(size=21)
    if kind == "imaginary":
        f = A @ Q @ (1j * np.arange(1, 6))
    B = A @ Q
    arrays, stats = restricted_solve(B, f)
    U, s, vh = np.linalg.svd(B / np.linalg.norm(f), full_matrices=False)
    keep = s > s[0] * 1e-12
    projected = U[:, keep] @ (U[:, keep].conj().T @ f)
    assert np.linalg.norm(B @ arrays["y"] - projected) / np.linalg.norm(f) < 1e-9
    assert stats["retained_rank"] == sum(keep)
    assert stats["QR_reconstruction_relative"] < 1e-12
    assert stats["QR_orthogonality_F"] < 1e-12
    assert stats["retained_optimality"] < 1e-9
    assert stats["residual_projection_defect"] < 1e-9


def test_old_G_permutation_is_independent_of_new_B_pivoting():
    rng = np.random.default_rng(421601)
    pi = rng.permutation(195)
    scales = np.linspace(0.2, 5, 195)
    vh = np.linalg.qr(rng.normal(size=(195, 195)) + 1j * rng.normal(size=(195, 195)))[0]
    singular = np.linspace(10, 0.2, 195)
    basis = dict(permutation=pi, scales=scales, vh=vh, singular_values=singular)
    y = rng.normal(size=195) + 1j * rng.normal(size=195)
    a = original_readout(y, basis)
    assert (
        np.linalg.norm(singular * (vh @ (scales[pi] * a[pi])) - y) / np.linalg.norm(y)
        < 1e-12
    )


def test_projection_whitelist_does_not_deserialize_forbidden_arrays(tmp_path):
    path = tmp_path / "projection.npz"
    values = {k: np.ones(2) for k in PROJECTION_KEYS}
    # A forbidden pickle member would raise if touched under allow_pickle=False.
    np.savez(
        path,
        **values,
        delta_ideal=np.array([object()], dtype=object),
        delta_columns=np.array([object()], dtype=object),
        delta_a=np.array([object()], dtype=object),
    )
    assert set(load_basis(path)) == set(PROJECTION_KEYS)


def test_main_has_no_reference_loading_or_training_calls():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / "src/solvers/feinn_residual_readout.py").read_text())
    calls = [ast.unparse(x.func) for x in ast.walk(tree) if isinstance(x, ast.Call)]
    for name in (
        "load_anchor",
        "load_problem",
        "reference_label",
        "feature_columns",
        "project",
        "Adam",
        "LBFGS",
        "solve",
    ):
        assert all(x.split(".")[-1] != name for x in calls)
    from src.io.feinn_pilot import load_pilot

    for path in (root / "input/task042extra_feinn_5nm").glob("v6_*.dat"):
        spec = load_pilot(path)
        assert spec.derived["features_reference_exposed"]
        assert not spec.derived["readout_rhs_uses_reference"]
        assert not spec.derived["official_candidate_results"]
