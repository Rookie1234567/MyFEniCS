"""Complex POD and full original-equation loss, without FE or global LU."""

import numpy as np

from src.solvers.learned_reduced_correction import (
    complex_linear_real_matrix,
    oracle_feature_batch,
    streaming_snapshot_pod,
)


def test_streamed_complex_pod_matches_independent_svd_subspace(tmp_path):
    rng = np.random.default_rng(42)
    e = rng.standard_normal((32, 48)) + 1j * rng.standard_normal((32, 48))
    files = []
    for i, batch in enumerate(np.split(e, 2)):
        path = tmp_path / f"e{i}.npz"
        np.savez(path, error=batch)
        files.append(path)
    q, _ = streaming_snapshot_pod(files, rank=16)
    exact, _, _ = np.linalg.svd(e.T, full_matrices=False)
    np.testing.assert_allclose(q.conj().T @ q, np.eye(16), atol=2e-14)
    np.testing.assert_allclose(
        q @ q.conj().T, exact[:, :16] @ exact[:, :16].conj().T, atol=2e-13
    )


def test_gram_loss_includes_unrepresented_native_equation_and_real_channels():
    rng = np.random.default_rng(420)
    a = rng.standard_normal((7, 7)) + 1j * rng.standard_normal((7, 7))
    w = rng.standard_normal((11, 7)) + 1j * rng.standard_normal((11, 7))
    q, _ = np.linalg.qr(rng.standard_normal((7, 3)) + 1j * rng.standard_normal((7, 3)))
    images = w @ a @ q
    u, r = np.linalg.qr(images)

    class B0:
        def apply_array(self, rhs):
            return 0.01 * rhs

    x = rng.standard_normal((2, 7)) + 1j * rng.standard_normal((2, 7))
    raw = x @ a.T
    rows, f = oracle_feature_batch(
        raw, x, np.ones(2), B0(), q, images, u, r, lambda v: a @ v, lambda v: w @ v
    )
    c = rng.standard_normal((2, 3)) + 1j * rng.standard_normal((2, 3))
    gram = images.conj().T @ images
    compressed = (
        np.einsum("bi,ij,bj->b", c.conj(), gram, c).real
        - 2 * np.sum(c.conj() * f["native_cross"], axis=1).real
        + f["native_constant"]
    )
    gap = (raw - 0.01 * raw @ a.T) @ w.T
    actual = np.linalg.norm(gap - c @ images.T, axis=1) ** 2
    np.testing.assert_allclose(compressed, actual, rtol=2e-14)
    assert all(0 < row["best_native_residual_ratio"] < 1 for row in rows)
    packed = np.concatenate((c.real, c.imag), axis=1)
    mapping = complex_linear_real_matrix(r)
    predicted = packed @ mapping.T
    expected = c @ r.T
    np.testing.assert_allclose(
        predicted, np.concatenate((expected.real, expected.imag), axis=1), atol=1e-14
    )


def test_linear_pc_keeps_full_b0_and_attains_native_subspace_minimum():
    from src.solvers.learned_reduced_correction import ReducedCorrectionPC

    rng = np.random.default_rng(44)
    a = rng.standard_normal((6, 6)) + 1j * rng.standard_normal((6, 6))
    w = rng.standard_normal((9, 6)) + 1j * rng.standard_normal((9, 6))
    q, _ = np.linalg.qr(rng.standard_normal((6, 3)) + 1j * rng.standard_normal((6, 3)))
    images = w @ a @ q
    u, r = np.linalg.qr(images)

    class B0:
        rows = 6
        factors = ()
        factor_bytes = 0
        declarations = ()

        def apply_array(self, rhs):
            return 0.1 * rhs

    pc = ReducedCorrectionPC(B0(), q, u, r, lambda v: a @ v, lambda v: w @ v)
    rhs = rng.standard_normal(6) + 1j * rng.standard_normal(6)
    z = pc.apply_array(rhs)
    gap = w @ (rhs - a @ (0.1 * rhs))
    expected = gap - u @ (u.conj().T @ gap)
    np.testing.assert_allclose(w @ (rhs - a @ z), expected, atol=2e-13)
    np.testing.assert_array_equal(pc.apply_array(np.zeros(6, dtype=np.complex128)), 0)
    assert pc.declarations[-1].rows == 3 and pc.declarations[-1].scope == "bottom"
    assert pc.representation_bytes < 512 * 2**20 and not pc.q.flags.writeable
