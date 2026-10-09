"""Opt-in fixed neural-space projection; no global factor or inverse.

Householder coordinates precede the small, condition-qualified Gram solve.
The deterministic panel fallback operates on this same frozen column space.
Labels are consumed only after the basis and its numerical rank are frozen.
"""

from contextlib import contextmanager
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import linalg

from src.solvers.feinn_gqr import GramColumns, squared_norm
from src.solvers.neural_wave_block import compensated_columns
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz, sha

RCOND = 1e-12


class StabilityFailure(ValueError):
    """A measured numerical qualification failure, enabling panel fallback."""


class Timers:
    def __init__(self):
        self.seconds = {}

    @contextmanager
    def phase(self, name):
        start = perf_counter()
        try:
            yield
        finally:
            self.seconds[name] = self.seconds.get(name, 0.0) + perf_counter() - start


class PanelGram(GramColumns):
    def __call__(self, x, role):
        if x.ndim == 1:
            return super().__call__(x, role)
        value = np.empty_like(x, dtype=np.complex128, order="F")
        for first in range(0, x.shape[1], 32):
            value[:, first : first + 32] = super().__call__(
                x[:, first : first + 32], role
            )
        return value


class BasisStore:
    """Immutable complete boundaries, plus an atomic hash-bound latest pointer."""

    def __init__(self, directory, binding, marker=lambda *_: None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.binding, self.marker = binding, marker

    def save(self, stage, arrays, record):
        suffix = f"{stage}_{len(list(self.directory.glob('boundary_*.json'))):04d}"
        file = self.directory / (suffix + ".npz")
        atomic_npz(file, **arrays)
        record = dict(record)
        if hasattr(self, "action"):
            record.update(
                G_columns=self.action.count,
                G_by_role=dict(self.action.by_role),
                G_seconds_nested=self.action.seconds,
            )
        receipt = dict(
            stage=stage,
            binding=self.binding,
            arrays=dict(path=file.name, sha256=sha(file)),
            record=record,
            committed=True,
        )
        atomic_json(self.directory / ("boundary_" + suffix + ".json"), receipt)
        atomic_json(self.directory / "latest.json", receipt)
        self.marker(
            "oracle_boundary_committed",
            dict(stage=stage, arrays_sha256=receipt["arrays"]["sha256"], **record),
        )
        if stage == "G_PANEL_COMPLETE":
            # Registered derived checkpoints only: retain two full panel banks.
            # Old boundary receipts (including hashes) remain; original U never
            # enters this directory and is never deleted or rewritten here.
            old = sorted(self.directory.glob("G_PANEL_COMPLETE_*.npz"))[:-2]
            for derived in old:
                self.marker(
                    "derived_panel_checkpoint_recycled",
                    dict(
                        path=derived.name,
                        sha256=sha(derived),
                        reason="registered two-version panel retention after new pointer fsync",
                    ),
                )
                derived.unlink()
        return receipt

    def reopen(self):
        file = self.directory / "latest.json"
        if not file.exists():
            return None
        receipt = json.loads(file.read_text())
        if receipt["binding"] != self.binding or receipt["committed"] is not True:
            raise ValueError("ORACLE_RECOVERY_IDENTITY_MISMATCH")
        path = self.directory / receipt["arrays"]["path"]
        if sha(path) != receipt["arrays"]["sha256"]:
            raise ValueError("ORACLE_RECOVERY_ARRAY_HASH_MISMATCH")
        with np.load(path, allow_pickle=False) as z:
            arrays = {k: np.array(z[k], order="F") for k in z.files}
        return receipt, arrays


def small_metric(H):
    defect = float(linalg.norm(H - H.conj().T) / max(linalg.norm(H), 1e-300))
    if not np.isfinite(H).all() or defect > 1e-12:
        raise StabilityFailure("REDUCED_GRAM_HERMITIAN_DEFECT")
    H = (H + H.conj().T) / 2
    eig = linalg.eigvalsh(H, check_finite=False)
    if not len(eig) or eig[0] <= 0:
        raise StabilityFailure("REDUCED_GRAM_NOT_POSITIVE")
    cond = float(eig[-1] / eig[0])
    if np.finfo(float).eps * cond > 1e-8:
        raise StabilityFailure("REDUCED_GRAM_CONDITION_LIMIT")
    return H, dict(
        Hermitian_relative=defect,
        lambda_min=float(eig[0]),
        lambda_max=float(eig[-1]),
        cond2=cond,
        machine_epsilon_condition=float(np.finfo(float).eps * cond),
        roundoff_symmetrization=True,
    )


def right_triangular(X, L):
    # X @ inv(L); plain transpose here, not conjugate transpose.
    return np.asfortranarray(
        linalg.solve_triangular(L.T, X.T, lower=True, check_finite=False).T
    )


def map_coefficients(basis, b):
    if basis["method"] == "HOUSEHOLDER_SMALL_GRAM":
        z = b
        if "L2" in basis:
            z = linalg.solve_triangular(basis["L2"], z, check_finite=False)
        z = linalg.solve_triangular(basis["L1"], z, check_finite=False)
        z = linalg.solve_triangular(basis["R"], z, check_finite=False)
    else:
        left, singular, vh = linalg.svd(
            basis["T"], full_matrices=False, check_finite=False
        )
        keep = singular > RCOND * singular[0]
        z = vh[keep].conj().T @ ((left[:, keep].conj().T @ b) / singular[keep])
    return z / basis["scales"]


def qualify_basis(U, basis, action, timers):
    V, T = basis["V"], basis["T"]
    with timers.phase("G_action"):
        GV = action(V, "basis_final_original_G")
    with timers.phase("independent_basis_qualification"):
        M = V.conj().T @ GV
        orth_numerator = float(linalg.norm(M - np.eye(V.shape[1])))
        # Continuous BLAS3 panels; never an N by N projector.
        num2, den2 = 0.0, 0.0
        for first in range(0, U.shape[1], 64):
            action.check()
            X = U[:, first : first + 64] / basis["scales"][first : first + 64]
            num2 += float(linalg.norm(X - V @ T[:, first : first + 64]) ** 2)
            den2 += float(linalg.norm(X) ** 2)
        reconstruction = np.sqrt(num2 / max(den2, 1e-300))
        singular = linalg.svdvals(T, check_finite=False)
        retained = (
            int(np.count_nonzero(singular > RCOND * singular[0]))
            if len(singular)
            else 0
        )
    stats = dict(
        G_orthogonality_F=orth_numerator,
        G_orthogonality_numerator=orth_numerator,
        G_orthogonality_denominator=1.0,
        transform_reconstruction_relative=float(reconstruction),
        transform_reconstruction_numerator=float(np.sqrt(num2)),
        transform_reconstruction_denominator=float(np.sqrt(den2)),
        singular_values=singular.tolist(),
        retained_rank=retained,
        original_columns=U.shape[1],
        SVD_rcond=RCOND,
        full_column_space_retained=retained == U.shape[1] == V.shape[1],
        exact_interval_certificate=False,
    )
    if orth_numerator > 1e-9 or reconstruction > 1e-10:
        raise StabilityFailure("G_BASIS_OR_TRANSFORM_QUALIFICATION: " + str(stats))
    if retained < V.shape[1]:
        raise StabilityFailure("BASIS_TRANSFORM_NUMERICAL_RANK_UNRESOLVED")
    basis["M"] = M
    return stats


def householder(U, action, store, timers, resume=None):
    n, m = U.shape
    if resume and resume[0]["stage"] in ("EUCLIDEAN_QR", "GRAM_REDUCED"):
        rec, data = resume
        Z, R, scales = data["Z"], data["R"], data["scales"]
        if rec["stage"] == "GRAM_REDUCED":
            H = data["H"]
        else:
            H = None
    else:
        with timers.phase("column_normalization_and_QR"):
            action.check()
            scales = np.linalg.norm(U, axis=0)
            if not np.isfinite(scales).all() or np.any(scales <= 0):
                raise StabilityFailure("ZERO_OR_NONFINITE_ORIGINAL_COLUMN")
            X = np.asfortranarray(U / scales)
            Z, R = linalg.qr(X, mode="economic", overwrite_a=True, check_finite=False)
        with timers.phase("save"):
            store.save("EUCLIDEAN_QR", dict(Z=Z, R=R, scales=scales), dict(columns=m))
        H = None
    action.check()
    if H is None:
        with timers.phase("G_action"):
            GZ = action(Z, "Householder_reduced_Gram")
        with timers.phase("reduced_Gram_BLAS3"):
            H = Z.conj().T @ GZ
        del GZ
        with timers.phase("save"):
            store.save(
                "GRAM_REDUCED", dict(Z=Z, R=R, scales=scales, H=H), dict(columns=m)
            )
    with timers.phase("small_factor_and_whitening"):
        H, Hstats = small_metric(H)
        singular_R = linalg.svdvals(R, check_finite=False)
        if np.count_nonzero(singular_R > RCOND * singular_R[0]) != m:
            raise StabilityFailure("HOUSEHOLDER_R_NUMERICAL_RANK_REQUIRES_PANEL")
        L1 = linalg.cholesky(H, lower=False, check_finite=False)
        V = right_triangular(Z, L1)
        T = L1 @ R
    del Z
    basis = dict(V=V, T=T, R=R, L1=L1, scales=scales, method="HOUSEHOLDER_SMALL_GRAM")
    with timers.phase("G_action"):
        GV = action(V, "first_whitening_orthogonality")
    with timers.phase("small_factor_and_whitening"):
        M1 = V.conj().T @ GV
        rho1 = float(linalg.norm(M1 - np.eye(m)))
        reorth = None
        if rho1 > 1e-9:
            M1, reorth = small_metric(M1)
            L2 = linalg.cholesky(M1, lower=False, check_finite=False)
            basis.update(V=right_triangular(V, L2), T=L2 @ T, L2=L2)
    del GV
    stats = qualify_basis(U, basis, action, timers)
    stats.update(
        method=basis["method"],
        reduced_Gram=Hstats,
        first_whitening_G_orthogonality_F=rho1,
        second_whitening=reorth,
        Householder_R_singular_values=singular_R.tolist(),
        triangle_order="L2 L1 R" if reorth else "L1 R",
    )
    return basis, stats


def panel_fallback(U, action, store, timers, resume=None):
    """Original order, MGS2 of panels, deterministic difficult-panel splitting."""
    n, m = U.shape
    scales = np.linalg.norm(U, axis=0)
    if np.any(scales <= 0) or not np.isfinite(scales).all():
        raise StabilityFailure("ZERO_OR_NONFINITE_ORIGINAL_COLUMN")
    V = np.empty((n, m), complex, order="F")
    T = np.zeros((m, m), complex, order="F")
    rank, first, discarded, splits = 0, 0, [], []
    if resume and resume[0]["stage"] == "G_PANEL_COMPLETE":
        rec, data = resume
        first, rank = rec["record"]["next_column"], data["V"].shape[1]
        V[:, :rank], T[:rank, :first] = data["V"], data["T"]
        discarded = rec["record"]["discarded_columns"]
        splits = rec["record"]["splits"]
    with timers.phase("G_action"):
        GV = (
            action(V[:, :rank], "fallback_resume_GV")
            if rank
            else np.empty((n, 0), complex)
        )

    def accept(lo, hi):
        nonlocal rank, GV
        action.check()
        P = np.asfortranarray(U[:, lo:hi] / scales[lo:hi])
        coefficients = np.zeros((rank, hi - lo), complex)
        for _ in range(2):
            with timers.phase("G_action"):
                GP = action(P, "fallback_panel_reorthogonalization")
            with timers.phase("panel_projection_BLAS3"):
                if rank:
                    h = V[:, :rank].conj().T @ GP
                    P -= V[:, :rank] @ h
                    coefficients += h
        width = hi - lo
        try:
            with timers.phase("panel_QR_and_small_factor"):
                Z, R = linalg.qr(P, mode="economic", check_finite=False)
                singular = linalg.svdvals(R, check_finite=False)
                if len(singular) < width or singular[-1] <= RCOND:
                    raise StabilityFailure("DIFFICULT_PANEL_RANK")
            with timers.phase("G_action"):
                GZ = action(Z, "fallback_panel_inner_Gram")
            with timers.phase("panel_QR_and_small_factor"):
                H, _ = small_metric(Z.conj().T @ GZ)
                L = linalg.cholesky(H, lower=False, check_finite=False)
                W = right_triangular(Z, L)
                local_T = L @ R
            with timers.phase("G_action"):
                GW = action(W, "fallback_panel_whitening_verification")
            with timers.phase("panel_QR_and_small_factor"):
                M = W.conj().T @ GW
                if linalg.norm(M - np.eye(width)) > 1e-10:
                    M, _ = small_metric(M)
                    L2 = linalg.cholesky(M, lower=False, check_finite=False)
                    W = right_triangular(W, L2)
                    GW = right_triangular(GW, L2)
                    local_T = L2 @ local_T
                if linalg.norm(W.conj().T @ GW - np.eye(width)) > 1e-9:
                    raise StabilityFailure("DIFFICULT_PANEL_ORTHOGONALITY")
        except StabilityFailure:
            if width > 1:
                splits.append(dict(first=lo, stop=hi, split=(lo + hi) // 2))
                mid = (lo + hi) // 2
                accept(lo, mid)
                accept(mid, hi)
                return
            with timers.phase("G_action"):
                GP = action(P, "fallback_single_column_rank_check")
            norm = np.sqrt(squared_norm(P[:, 0], GP[:, 0]))
            if norm <= RCOND:
                T[:rank, lo:hi] = coefficients
                discarded.append(lo)
                return
            W, GW, local_T = P / norm, GP / norm, np.array([[norm]], complex)
        T[:rank, lo:hi] = coefficients
        T[rank : rank + width, lo:hi] = local_T
        V[:, rank : rank + width] = W
        GV = np.concatenate((GV, GW), axis=1)
        rank += width

    while first < m:
        stop = min(m, first + 32)
        accept(first, stop)
        first = stop
        with timers.phase("save"):
            store.save(
                "G_PANEL_COMPLETE",
                dict(V=V[:, :rank], T=T[:rank, :first], scales=scales),
                dict(
                    next_column=first,
                    rank=rank,
                    discarded_columns=discarded,
                    splits=splits,
                    G_columns=action.count,
                ),
            )
    if not rank:
        raise StabilityFailure("EMPTY_NUMERICAL_ORACLE_SPACE")
    basis = dict(
        V=np.asfortranarray(V[:, :rank]),
        T=T[:rank],
        scales=scales,
        method="DETERMINISTIC_PANEL_G_REORTHOGONALIZATION",
    )
    stats = qualify_basis(U, basis, action, timers)
    stats.update(method=basis["method"], discarded_columns=discarded, splits=splits)
    return basis, stats


def build_basis(U, G, store, *, deadline, timers=None):
    timers = timers or Timers()
    action = PanelGram(G, limit=100000, deadline=deadline)
    U = np.asarray(U, dtype=np.complex128, order="F")
    if U.ndim != 2 or not np.isfinite(U).all() or U.shape[0] < U.shape[1]:
        raise ValueError("FROZEN_SPACE_MATRIX_INVALID")
    resume = store.reopen()
    store.action = action
    if resume:
        previous = resume[0]["record"]
        action.count = previous.get("G_columns", 0)
        action.by_role = dict(previous.get("G_by_role", {}))
        action.seconds = previous.get("G_seconds_nested", 0.0)
    if resume and resume[0]["stage"] == "G_BASIS_QUALIFIED":
        rec, basis = resume
        basis["method"] = rec["record"]["method"]
        return basis, rec["record"], action, timers
    if not resume:
        store.save("LOADED", {}, dict(shape=list(U.shape), G_columns=0))
    action.check()
    failure = None
    try:
        if resume and resume[0]["stage"] == "G_PANEL_COMPLETE":
            raise StabilityFailure("CONTINUE_SAVED_PANEL_FALLBACK")
        basis, stats = householder(U, action, store, timers, resume)
    except StabilityFailure as error:
        failure = str(error)
        store.marker("primary_stability_requires_panel_fallback", dict(reason=failure))
        basis, stats = panel_fallback(U, action, store, timers, resume)
    stats.update(
        primary_stability_failure=failure,
        G_columns=action.count,
        G_by_role=action.by_role,
        primary_or_fallback_selected_without_reference=True,
    )
    arrays = {k: v for k, v in basis.items() if k != "method"}
    with timers.phase("save"):
        store.save("G_BASIS_QUALIFIED", arrays, stats)
    return basis, stats, action, timers


def reference_projection(U, reference, basis, stats, action, timers):
    """Labelled readout only; original coefficient field is always recomputed."""
    V, M = basis["V"], basis["M"]
    with timers.phase("G_action"):
        Gref = action(reference, "reference_rhs_and_denominator")
    with timers.phase("amplitude_backtransform_and_actual_field"):
        rhs = V.conj().T @ Gref
        b = linalg.solve(M, rhs, assume_a="her", check_finite=False)
        a = map_coefficients(basis, b)
        c = compensated_columns(U, a)
        ideal = V @ b
        e = reference - c
        pair_num, pair_den = float(linalg.norm(c - ideal)), float(linalg.norm(ideal))
    with timers.phase("G_action"):
        Ge = action(e, "actual_error_original_G")
    with timers.phase("independent_projection_qualification"):
        dref, energy = squared_norm(reference, Gref), squared_norm(e, Ge)
        s = V.conj().T @ Ge
        rho = float(linalg.norm(M - np.eye(M.shape[0])))
        gap = float(np.vdot(s, linalg.solve(M, s, assume_a="her")).real)
        bound = float(np.vdot(s, s).real / (1 - rho)) if rho < 1 else None
        lower = np.sqrt(max(0.0, energy - bound) / dref) if bound is not None else None
        optimum = float(linalg.norm(s) / np.sqrt(dref))
        pair = pair_num / max(pair_den, 1e-300)
        qualified = bool(rho <= 1e-9 and pair <= 1e-10 and optimum <= 1e-9)
    result = dict(
        stats,
        actual_E_G=float(np.sqrt(energy / dref)),
        actual_error_G_energy=energy,
        reference_G_energy=dref,
        small_M_orthogonality_F=rho,
        actual_U_amplitude_pair_relative=pair,
        actual_U_amplitude_pair_numerator=pair_num,
        actual_U_amplitude_pair_denominator=pair_den,
        retained_optimality=optimum,
        optimality_numerator=float(linalg.norm(s)),
        optimality_denominator=float(np.sqrt(dref)),
        optimum_gap_G_energy_small_M=gap,
        optimum_gap_G_energy_upper=bound,
        numerical_optimum_E_G_lower=float(lower) if lower is not None else None,
        numerical_optimum_E_G_upper=float(np.sqrt(energy / dref)),
        floating_numerical_qualified=qualified,
        exact_interval_certificate=False,
        field_precision_conclusion=(
            "FROZEN_FULL_SPACE_FIELD_THRESHOLD_EXCLUDED_NUMERICALLY"
            if qualified and stats["full_column_space_retained"] and lower > 1e-4 + 1e-8
            else "INCONCLUSIVE"
        ),
        G_columns=action.count,
        G_by_role=action.by_role,
        G_seconds_nested=action.seconds,
        phase_seconds_exclusive=timers.seconds,
        G_stream_columns_max=32,
        dense_panel_columns_max=64,
        global_G_factor_count=0,
        Gsolve_count=0,
        truncated_minimum_is_full_space_upper_bound=True,
    )
    return dict(a=a, c=c, error=e, ideal=ideal, b=b, stationarity=s), result
