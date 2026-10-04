"""Exact boundary-plane modal coordinates for the research direct authority.

The physical augmented blocks and all reported alpha values stay unchanged.
Only the direct solver's coordinates/equation units change, avoiding tiny
evanescent origin-phase diagonals. This is not a new Maxwell PC or a shift.
"""

import numpy as np


def scales(fe_rows, H, phase):
    H, phase = np.asarray(H, float), np.asarray(phase, complex)
    if (
        H.shape != phase.shape
        or not np.isfinite(H).all()
        or not np.isfinite(phase).all()
        or np.any(H <= 0)
        or np.any(abs(phase) == 0)
    ):
        raise ValueError("EXACT_PORT_COORDINATES_NONFINITE_OR_SINGULAR")
    right = np.r_[np.ones(fe_rows), 1 / phase]
    left = np.r_[np.ones(fe_rows), phase / H]
    if not np.isfinite(right).all() or not np.isfinite(left).all():
        raise ValueError("EXACT_PORT_COORDINATES_OVERFLOW")
    return left, right


def transform(matrix, rhs, fe_rows, H, phase):
    """L*[V B; -D H]*T with beta=phase*alpha and unit port diagonal."""
    left, right = scales(fe_rows, H, phase)
    out = matrix.copy().tocsr()
    # Bounded row chunks; no dense global matrix or full COO conversion.
    for first in range(0, out.shape[0], 4096):
        last = min(first + 4096, out.shape[0])
        section = slice(out.indptr[first], out.indptr[last])
        out.data[section] *= right[out.indices[section]]
        out.data[section] *= np.repeat(
            left[first:last], np.diff(out.indptr[first : last + 1])
        )
    if not np.isfinite(out.data).all():
        raise ValueError("EXACT_PORT_COORDINATES_MATRIX_OVERFLOW")
    return out, left * np.asarray(rhs), left, right


class BoundaryPortCondensation:
    """Wrap the qualified exact interior recovery, changing only modal units."""

    def __init__(self, original, phases, artifact):
        self.original = original
        self.phase = np.asarray(phases, complex)
        self.packet = original.packet
        self.t = original.t
        self.artifact = artifact
        self.left, self.right = scales(
            len(original.trace), self.packet.a["H"], self.phase
        )
        self.rhs = self.left * original.rhs

    def recover(self, vector):
        return self.original.recover(self.right * np.asarray(vector))

    def assemble(self, model, packet, marker):
        from src.solvers.feinn_discretization_audit import atomic_npz

        raw, pair = self.original.assemble(
            model, packet, marker, save=self.artifact / "condensed_csr_recovery.npz"
        )
        scaled, rhs, left, right = transform(
            raw, self.original.rhs, len(self.original.trace), packet.a["H"], self.phase
        )
        rng = np.random.default_rng(422023)
        pairs = []
        for _ in range(3):
            z = rng.standard_normal(len(rhs)) + 1j * rng.standard_normal(len(rhs))
            first = scaled @ z - rhs
            second = left * (raw @ (right * z) - self.original.rhs)
            pairs.append(
                float(
                    np.linalg.norm(first - second) / max(np.linalg.norm(second), 1e-30)
                )
            )
        if max(pairs) > 1e-10:
            raise ValueError("EXACT_PORT_COORDINATES_PAIR_FAILED")
        atomic_npz(
            self.artifact / "boundary_coordinate_csr.npz",
            indptr=scaled.indptr,
            indices=scaled.indices,
            data=scaled.data,
            shape=np.asarray(scaled.shape),
            rhs=rhs,
            left=left,
            right=right,
            phase=self.phase,
            original_H=packet.a["H"],
        )
        marker(
            "exact_boundary_port_coordinates",
            dict(
                beta_definition="beta=physical_boundary_phase*alpha_origin",
                original_equations_unchanged=True,
                field_coefficients_unchanged=True,
                row_scale="phase/H",
                column_scale="1/phase",
                phase_magnitude_min=float(abs(self.phase).min()),
                phase_magnitude_max=float(abs(self.phase).max()),
                pairs=pairs,
                port_diagonal_max_difference=float(
                    np.max(abs(scaled.diagonal()[-packet.np :] - 1))
                ),
                not_PC=True,
                not_shift=True,
            ),
        )
        return scaled, max(pair, max(pairs))
