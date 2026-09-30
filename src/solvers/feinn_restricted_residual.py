"""Complex restricted least squares; two distinct QR coordinate systems.

No FE inverse, normal equation, reference, Torch, or Gram factor is needed.
"""

import numpy as np
from scipy.linalg import qr, svd

RCOND = 1e-12
PROJECTION_KEYS = (
    "Q_eff",
    "Q",
    "R",
    "left",
    "vh",
    "singular_values",
    "permutation",
    "scales",
)
POLICY = dict(
    reference_used_for_training=True,
    features_reference_exposed=True,
    readout_rhs_uses_reference=False,
    pde_only_solve=False,
    production_initialization_allowed=False,
    pde_only_solver_qualified=False,
    official_candidate_results=False,
)
ROUTE = "FEINN-FROZEN-FEATURE-RESIDUAL-READOUT"


def load_basis(path):
    """NpzFile lazy access: forbidden supervised corrections are never read."""
    with np.load(path, allow_pickle=False) as data:
        return {key: np.array(data[key]) for key in PROJECTION_KEYS}


def original_readout(y, basis):
    s = basis["singular_values"]
    p = basis["permutation"]
    if len(s) != 195 or np.any(s <= RCOND * s[0]) or len(p) != 195:
        raise ValueError("V5_FULL_RETAINED_BASIS_REQUIRED")
    a = np.empty(195, dtype=np.complex128)
    a[p] = (basis["vh"].conj().T @ (y / s)) / basis["scales"][p]
    return a


def restricted_solve(B, f):
    """Economic pivoted Householder QR, SVD only of its small R.

    The new B permutation affects y only, never the old G-to-readout map.
    Residual is computed by direct subtraction even near a perfect fit.
    """
    B, f = np.asarray(B, complex), np.asarray(f, complex)
    if B.ndim != 2 or B.shape[0] < B.shape[1] or f.shape != (len(B),):
        raise ValueError("RESTRICTED_SHAPE")
    scale = float(np.linalg.norm(f))
    if scale <= 0 or not np.isfinite(B).all() or not np.isfinite(f).all():
        raise ValueError("RESTRICTED_FINITE_NONZERO_LOAD")
    Bh, fh = B / scale, f / scale
    Z, R, permutation = qr(Bh, mode="economic", pivoting=True)
    left, singular, vh = svd(R, full_matrices=False)
    keep = singular > RCOND * singular[0]
    zeff = Z @ left[:, keep]
    beta = zeff.conj().T @ fh
    yp = vh[keep].conj().T @ (beta / singular[keep])
    y = np.zeros(B.shape[1], dtype=np.complex128)
    y[permutation] = yp
    projected = Bh @ y
    residual = projected - fh
    rho = float(np.linalg.norm(residual))
    norms = np.linalg.norm(Bh, axis=0)
    correlation = Bh.conj().T @ residual
    correlation[norms > 0] /= norms[norms > 0]
    stats = dict(
        retained_rank=int(sum(keep)),
        column_count=B.shape[1],
        rcond=RCOND,
        singular_values=singular.tolist(),
        cutoff=float(RCOND * singular[0]),
        discarded_indices=np.flatnonzero(~keep).tolist(),
        QR_reconstruction_relative=float(
            np.linalg.norm(Bh[:, permutation] - Z @ R) / np.linalg.norm(Bh)
        ),
        QR_orthogonality_F=float(np.linalg.norm(Z.conj().T @ Z - np.eye(Z.shape[1]))),
        retained_optimality=float(np.linalg.norm(zeff.conj().T @ residual)),
        all_original_normalized_column_correlations=[
            dict(real=z.real, imag=z.imag) for z in correlation
        ],
        maximum_original_column_correlation=float(np.max(abs(correlation))),
        rho=rho,
        projected_rhs_energy=float(np.vdot(projected, projected).real),
        residual_projection_defect=abs(1 - rho**2 - np.vdot(projected, projected).real),
        y_norm=float(np.linalg.norm(y)),
        load_norm=scale,
    )
    return dict(
        B=B,
        Z=Z,
        R_B=R,
        left_B=left,
        vh_B=vh,
        singular_B=singular,
        permutation_B=permutation,
        y=y,
        residual_hat=residual,
    ), stats
