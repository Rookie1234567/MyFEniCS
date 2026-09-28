"""Task042 streamed POD and fixed low-rank PC.

The rank is at most 128; all deployment arrays are counted. No global A4 LU.
"""

import time

import numpy as np
from scipy.linalg import eigh, solve_triangular
from scipy.special import erf


def streaming_snapshot_pod(files, *, rank=128):
    """Files hold <=32 normalized B0 error snapshots as row vectors.

    Form a small snapshot Gram matrix with at most two streamed batches;
    reconstruct only the retained Q. Never load all full-field teacher data.
    """
    sizes = []
    for path in files:
        with np.load(path, allow_pickle=False) as packet:
            shape = packet["error"].shape
            if len(shape) != 2 or not 0 < shape[0] <= 32:
                raise ValueError("invalid snapshot batch")
            sizes.append(shape[0])
    offsets = np.cumsum([0] + sizes)
    count = int(offsets[-1])
    if count > 1024 or rank not in (16, 32, 64, 128) or count < rank:
        raise ValueError("bounded POD snapshot/rank Gate failed")
    gram = np.zeros((count, count), dtype=np.complex128)
    for i, left in enumerate(files):
        with np.load(left, allow_pickle=False) as packet:
            a = packet["error"]
        for j in range(i, len(files)):
            with np.load(files[j], allow_pickle=False) as packet:
                b = packet["error"]
            block = a.conj() @ b.T
            gram[offsets[i] : offsets[i + 1], offsets[j] : offsets[j + 1]] = block
            gram[offsets[j] : offsets[j + 1], offsets[i] : offsets[i + 1]] = (
                block.conj().T
            )
    eigenvalues, vectors = eigh(gram, subset_by_index=(count - rank, count - 1))
    order = np.arange(rank - 1, -1, -1)
    eigenvalues, vectors = eigenvalues[order], vectors[:, order]
    if eigenvalues[-1] <= eigenvalues[0] * 1.0e-13:
        raise ValueError("snapshot basis numerically deficient at registered rank")
    q = None
    weights = vectors / np.sqrt(eigenvalues)[None, :]
    for i, path in enumerate(files):
        with np.load(path, allow_pickle=False) as packet:
            batch = packet["error"]
        contribution = batch.T @ weights[offsets[i] : offsets[i + 1]]
        q = contribution if q is None else q + contribution
    q, _ = np.linalg.qr(q, mode="reduced")
    return np.asarray(q, dtype=np.complex128), eigenvalues


def packed_complex(values):
    return np.concatenate((values.real, values.imag), axis=-1).astype(np.float64)


def unpacked_complex(values):
    k = values.shape[-1] // 2
    return np.asarray(values[..., :k] + 1j * values[..., k:], dtype=np.complex128)


def oracle_feature_batch(
    raw, solution, native_scales, b0, q, images, u, r, matrix_apply, native_map
):
    """Full original-equation diagnostics and bounded compressed loss features.

    Q projects teacher errors; QR of the full native A4 images gives the
    best residual correction in Q. The Gram loss includes the component
    perpendicular to U, rather than dropping that equation residual.
    """
    from scipy.linalg import solve_triangular

    if not 0 < len(raw) <= 32:
        raise ValueError("at most 32 RHS per oracle batch")
    rows, features = [], []
    for rhs, exact, native_scale in zip(raw, solution, native_scales, strict=True):
        z = b0.apply_array(rhs)
        error = exact - z
        gap = native_map(rhs - matrix_apply(z))
        target = q.conj().T @ error
        encoded = u.conj().T @ gap
        coefficient = solve_triangular(r, encoded, check_finite=False)
        projected = q @ target
        residual = gap - images @ coefficient
        error_norm, gap_norm = np.linalg.norm(error), np.linalg.norm(gap)
        rows.append(
            {
                "error_projection_ratio": float(
                    np.linalg.norm(error - projected)
                    / max(error_norm, np.finfo(float).tiny)
                ),
                "best_native_residual_ratio": float(
                    np.linalg.norm(residual) / max(gap_norm, np.finfo(float).tiny)
                ),
                "b0_native_relative": float(
                    gap_norm / max(native_scale, np.finfo(float).tiny)
                ),
                "linear_native_relative": float(
                    np.linalg.norm(residual) / max(native_scale, np.finfo(float).tiny)
                ),
            }
        )
        features.append(
            {
                "encoded": encoded,
                "target": target,
                "native_cross": images.conj().T @ gap,
                "native_constant": float(gap_norm**2),
                "native_denominator": float(native_scale**2),
            }
        )
    return rows, {key: np.stack([f[key] for f in features]) for key in features[0]}


def complex_linear_real_matrix(matrix):
    """Pack a complex linear map for float64 real/imag channels."""
    return np.block([[matrix.real, -matrix.imag], [matrix.imag, matrix.real]])


def numpy_mlp(encoded, weights):
    def gelu(value):
        return 0.5 * value * (1.0 + erf(value / np.sqrt(2.0)))

    h1 = gelu(encoded @ weights["hidden1_weight"].T + weights["hidden1_bias"])
    h2 = gelu(h1 @ weights["hidden2_weight"].T + weights["hidden2_bias"])
    return (
        encoded @ weights["skip_weight"].T
        + weights["skip_bias"]
        + h2 @ weights["output_weight"].T
        + weights["output_bias"]
    )


class ReducedCorrectionPC:
    """Same raw residual encoder and B0 for analytical LIN and frozen FP64 NN.

    B0 handles the full space. Encoder U^H (r-A B0 r) normalizes by ||r||;
    Q maps coefficients back to a correction. LIN is the exact least-squares
    minimizer in this fixed output subspace, not a global inverse surrogate.
    """

    def __init__(self, b0, q, u, r, matrix_apply, native_residual_map, *, weights=None):
        self.b0 = b0
        self.q, self.u_h, self.r = q, np.ascontiguousarray(u.conj().T), r
        self.matrix_apply = matrix_apply
        self.native_residual_map = native_residual_map
        self.weights = weights
        self.factors = b0.factors
        self.factor_bytes = b0.factor_bytes
        self.seconds = 0.0
        self.representation_bytes = sum(a.nbytes for a in (q, u, r))
        self.representation_bytes += (
            6 * q.shape[0] + 4 * u.shape[0] + 10 * q.shape[1]
        ) * 16
        if weights is not None:
            self.representation_bytes += sum(a.nbytes for a in weights.values())
            if any(
                a.dtype != np.float64 or not np.isfinite(a).all()
                for a in weights.values()
            ):
                raise ValueError("NN weight dtype/finite Gate failed")
        if q.shape[1] > 128 or self.representation_bytes > 512 * 2**20:
            raise ValueError("representation capacity exceeded")

    @property
    def declarations(self):
        return self.b0.declarations

    def encode(self, residual):
        z = self.b0.apply_array(residual)
        gap = residual - self.matrix_apply(z)
        scale = float(np.linalg.norm(residual))
        return (
            z,
            gap,
            self.u_h @ self.native_residual_map(gap) / max(scale, np.finfo(float).tiny),
            scale,
        )

    def apply_array(self, source):
        started = time.perf_counter()
        if not np.any(source):
            return np.zeros_like(source)
        z, _, encoded, scale = self.encode(source)
        if self.weights is None:
            coefficients = solve_triangular(self.r, encoded, check_finite=False)
        else:
            coefficients = unpacked_complex(
                numpy_mlp(packed_complex(encoded), self.weights)
            )
        result = z + self.q @ (scale * coefficients)
        self.seconds += time.perf_counter() - started
        return result

    def apply(self, _pc, source, target):
        target.array[:] = self.apply_array(source.getArray(readonly=True))
