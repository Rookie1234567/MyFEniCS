"""Direct orthonormal neural FE decoder, explicitly separate from raw MLP heads.

Only tall/thin Householder QR and fixed GELSD are used.  The physical action
and its forty-port closure are borrowed; no global operator/inverse is built.
"""

from time import perf_counter

import numpy as np

from src.solvers.stable_head_varpro import homogeneous_recovery_pair
from src.solvers.tangent_head_model import bar_action

FAMILY = "ORTHONORMAL_NEURAL_FE_BASIS"
COND = 1e-12
LIMITS = dict(basis_evaluations=10, thin_LS_calls=24, thin_RHS=28,
              original_audits=80, new_profiles=2, field_states=10)


class OrthonormalTraceBasis:
    """One current P/Q/A; the actual forward is Qc, never R^{-1}c/raw gamma."""

    def __init__(self, packet, P, ports, *, reverse_rows=False, saved_A=None,
                 count=lambda *args: None, guard=lambda *args, **kw: None,
                 event=lambda *args, **kw: None, expected_columns=1560):
        from scipy.linalg import qr, svdvals

        if P.shape != (packet.nt, expected_columns) or P.dtype != np.complex128:
            raise ValueError("canonical complex128 feature inventory differs")
        if not np.isfinite(P).all():
            raise ValueError("nonfinite current P")
        count("basis_evaluations")
        guard(large=True)
        self.packet, self.ports = packet, ports
        self.reverse_rows = reverse_rows
        self.count, self.guard = count, guard
        self.times = {}
        began = perf_counter()
        # A row permutation is only a numerical sensitivity witness.  Restore
        # the original canonical FE row order BEFORE any original action.
        input_P = P[::-1] if reverse_rows else P
        Q, R = qr(input_P, mode="economic", pivoting=False, check_finite=False)
        self.Q = np.array(Q[::-1], order="F") if reverse_rows else Q
        self.R = R
        del Q, input_P
        self.times["P_householder_QR"] = perf_counter() - began
        error2 = norm2 = 0.
        for start in range(0, packet.nt, 128):
            block = P[start:start+128]
            error2 += np.linalg.norm(block-self.Q[start:start+128]@R)**2
            norm2 += np.linalg.norm(block)**2
        self.reconstruction = float(np.sqrt(error2/max(norm2, 1e-300)))
        gram = self.Q.conj().T@self.Q
        gram.flat[::expected_columns+1] -= 1
        self.orthogonality = float(np.linalg.norm(gram)/np.sqrt(expected_columns))
        del gram
        p_singular = svdvals(R, check_finite=False)
        self.rank_P = int(np.count_nonzero(p_singular > COND*p_singular[0]))
        self.p_range = [float(p_singular[-1]), float(p_singular[0])]
        if max(self.reconstruction, self.orthogonality) > 1e-10 or self.rank_P != expected_columns:
            raise ValueError("ORTHO P/QR/rank unqualified")
        self.pairing = []
        self.saved_A_rejected = False
        if saved_A is not None:
            self.pairing = self.check_pairing(saved_A)
            if max(self.pairing) > 1e-10:
                self.saved_A_rejected = True
                saved_A = None
                count("basis_evaluations")  # One authorized original-A rebuild.
        began = perf_counter()
        if saved_A is None:
            self.A = np.empty_like(self.Q, order="F")
            for j in range(expected_columns):
                guard(extra_actions=1)
                self.A[:, j], _ = bar_action(packet, ports, self.Q[:, j])
                if j % 128 == 0 or j == expected_columns-1:
                    event("original_A_columns", completed=j+1, total=expected_columns)
            self.fresh_A_columns = expected_columns
        else:
            self.A = saved_A
            self.fresh_A_columns = 0
        self.times["original_barS_columns"] = perf_counter()-began
        # The actual-residual stationarity test uses the Euclidean column
        # space.  This is a thin QR, not a large dense projection matrix.
        guard(large=True)
        began = perf_counter()
        self.U, self.RA = qr(self.A, mode="economic", pivoting=False, check_finite=False)
        self.times["A_economic_QR_stationarity"] = perf_counter()-began
        self.columns = expected_columns

    def check_pairing(self, A):
        if A.shape != self.Q.shape or A.dtype != np.complex128 or not np.isfinite(A).all():
            raise ValueError("saved A inventory differs")
        errors = []
        for j in (0, self.Q.shape[1]//2, self.Q.shape[1]-1):
            self.guard(extra_actions=1)
            actual, _ = bar_action(self.packet, self.ports, self.Q[:, j])
            errors.append(float(np.linalg.norm(actual-A[:, j])/max(np.linalg.norm(A[:, j]), 1e-300)))
        for seed in (421411, 421412):
            rng = np.random.default_rng(seed)
            c = rng.standard_normal(A.shape[1])+1j*rng.standard_normal(A.shape[1])
            c /= np.linalg.norm(c)
            self.guard(extra_actions=1)
            actual, _ = bar_action(self.packet, self.ports, self.Q@c)
            expected = A@c
            errors.append(float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected), 1e-300)))
        return errors

    def decomposition(self):
        return dict(family=FAMILY, main_forward="trace_EQUALS_Q_times_c",
                    raw_gamma_writeback=False, reverse_row_QR=self.reverse_rows,
                    P_reconstruction=self.reconstruction, Q_orthogonality=self.orthogonality,
                    rank_P=self.rank_P, P_singular_range=self.p_range,
                    saved_A_pairing=self.pairing, saved_A_rejected=self.saved_A_rejected,
                    fresh_A_columns=self.fresh_A_columns, Hhat_condition=self.ports.cond_H,
                    basis_times_seconds=self.times, numerical_full_column_rank=True,
                    exact_full_space_optimum_claimed=False,
                    payload_bytes=dict(Q=self.Q.nbytes, R=self.R.nbytes, A=self.A.nbytes,
                                       U=self.U.nbytes, RA=self.RA.nbytes))

    def evaluate(self, c, rhs):
        self.guard(extra_actions=2)
        trace = self.Q@c
        z, trace_action = self.ports.closed(trace, rhs)
        residual = rhs-self.packet.apply(z)
        thin = self.ports.reduced_rhs(rhs)-self.A@c
        scale = max(np.linalg.norm(rhs), 1e-300)
        port_rhs = rhs[self.packet.nt:]-trace_action[self.packet.nt:]
        port_error = self.ports.H@z[self.packet.nt:]-port_rhs
        port_scale = np.linalg.norm(self.ports.H)*np.linalg.norm(z[self.packet.nt:])+np.linalg.norm(port_rhs)
        return dict(c=c.copy(), trace=trace, port=z[self.packet.nt:].copy(), z=z,
                    residual=residual, thin_residual=thin,
                    numeric=dict(Phi=float(np.vdot(residual, residual).real/(2*scale**2)),
                        schur_relative=float(np.linalg.norm(residual)/scale),
                        c_norm=float(np.linalg.norm(c)), rhs_sha256=None,
                        actual_vs_thin_fixed_rhs=float(np.linalg.norm(residual[:self.packet.nt]-thin)/scale),
                        stationarity_UHr_fixed_rhs=float(np.linalg.norm(self.U.conj().T@residual[:self.packet.nt])/scale),
                        AHr_absolute=float(np.linalg.norm(self.A.conj().T@residual[:self.packet.nt])),
                        Hhat_solve_operation_relative=float(np.linalg.norm(port_error)/max(port_scale, 1e-300)),
                        port_absolute=float(np.linalg.norm(residual[self.packet.nt:]))))

    def solve(self, rhs):
        from scipy.linalg import lstsq

        rhs = np.asarray(rhs, np.complex128)
        if rhs.shape != (self.packet.size,) or not np.isfinite(rhs).all() or np.linalg.norm(rhs) == 0:
            raise ValueError("complete nonzero original or manufactured RHS required")
        self.guard(large=True)
        self.count("thin_LS_calls"); self.count("thin_RHS")
        began = perf_counter()
        c, _, rank, singular = lstsq(self.A, self.ports.reduced_rhs(rhs), cond=COND,
                                    lapack_driver="gelsd", check_finite=False)
        elapsed = perf_counter()-began
        point = self.evaluate(c, rhs)
        initial = point["numeric"].copy()
        corrections = 0
        if rank == self.columns and not decoder_gate(point["numeric"]):
            self.count("thin_LS_calls"); self.count("thin_RHS")
            began = perf_counter()
            dc, _, rank, singular = lstsq(self.A, point["residual"][:self.packet.nt], cond=COND,
                                         lapack_driver="gelsd", check_finite=False)
            elapsed += perf_counter()-began
            point = self.evaluate(c+dc, rhs)
            corrections = 1
        repeated = self.evaluate(point["c"], rhs)
        dr = np.linalg.norm(repeated["residual"]-point["residual"])
        rhsnorm = np.linalg.norm(rhs)
        thin_difference = np.linalg.norm(point["residual"][:self.packet.nt]-point["thin_residual"])
        induced = (np.linalg.norm(point["residual"])*thin_difference+.5*thin_difference**2)/rhsnorm**2
        delta = max(abs(repeated["numeric"]["Phi"]-point["numeric"]["Phi"]),
                    induced, 100*np.finfo(float).eps*max(1., point["numeric"]["Phi"]))
        point["numeric"].update(rank_A=int(rank), A_singular_range=[float(singular[-1]),float(singular[0])],
                    numerical_full_column_rank=bool(rank==self.columns), exact_optimum_claimed=False,
                    correction_count=corrections, initial_checks=initial,
                    least_squares_seconds=elapsed, driver="gelsd", cond=COND,
                    repeated_Phi=repeated["numeric"]["Phi"], repeated_residual_difference=float(dr),
                    thin_induced_Phi_scale=float(induced), delta_i=float(delta),
                    decoder_gate=bool(rank==self.columns and decoder_gate(point["numeric"])))
        return point


def decoder_gate(row):
    keys = ("actual_vs_thin_fixed_rhs", "stationarity_UHr_fixed_rhs")
    return (all(np.isfinite(row[k]) and row[k] <= 1e-8 for k in keys)
            and np.isfinite(row["Hhat_solve_operation_relative"])
            and row["Hhat_solve_operation_relative"] <= 1e-12)


def manufactured_witness(basis, known, name):
    rhs = basis.packet.apply(known)
    recovered = basis.solve(rhs)
    difference = float(np.linalg.norm(recovered["z"]-known)/np.linalg.norm(known))
    homogeneous = homogeneous_recovery_pair(basis.packet, known, recovered["z"])
    row = dict(name=name, numeric=recovered["numeric"], known_z_relative=difference,
               homogeneous_recovery_operation_relative=homogeneous,
               full_manufactured_RHS_from_original_action=True,
               reference_used=False, physical_b_overwritten=False)
    row["qualified"] = bool(recovered["numeric"]["decoder_gate"]
        and recovered["numeric"]["schur_relative"] <= 1e-8
        and difference <= 1e-6 and homogeneous <= 1e-10)
    return recovered, rhs, row


def comparison_margin(first, second, basis_delta):
    return float(max(1e-10, 100*max(first["delta_i"],second["delta_i"],basis_delta)))


def profile_progress(origin, point, basis_delta):
    from src.solvers.actual_loss_block_descent import qualified_audit
    gain = origin["numeric"]["Phi"]-point["numeric"]["Phi"]
    margin = comparison_margin(origin["numeric"],point["numeric"],basis_delta)
    qualified = (point["numeric"]["decoder_gate"] and qualified_audit(point["audit"])
                 and point["audit"]["native_relative"] <= 1.05*origin["audit"]["native_relative"])
    return dict(relative_gain=float(gain/origin["numeric"]["Phi"]), absolute_gain=float(gain),
                comparison_margin=margin, qualified_for_selection=bool(qualified),
                O3_admitted=bool(qualified and gain >= 1e-4*origin["numeric"]["Phi"] and gain > margin))


def ray_identity(origin_hidden, trial_zero_hidden, trial_hidden, s):
    expected = origin_hidden+s*(trial_zero_hidden-origin_hidden)
    error = np.linalg.norm(trial_hidden-expected)
    rounding_scale = 100*np.finfo(float).eps*max(1.,np.linalg.norm(origin_hidden))
    return dict(s=float(s), absolute_difference=float(error), rounding_scale=float(rounding_scale),
                consistent=bool(error<=rounding_scale), derived_ray_not_recovered_old_LS=True)
