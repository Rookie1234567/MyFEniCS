"""Independent square-root-whitened fixtures for the opt-in blocked oracle."""

from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import linalg

from src.solvers.neural_space_blocked import (
    BasisStore,
    PanelGram,
    Timers,
    StabilityFailure,
    build_basis,
    reference_projection,
    qualify_basis,
    small_metric,
    panel_fallback,
)
from src.solvers.feinn_gqr import ReadoutStop
from src.solvers.neural_wave_greedy import atomic_json


def fixture_cases(directory):
    rng = np.random.default_rng(4213601)
    n, m = 31, 7
    raw = rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))
    G = raw.conj().T @ raw + np.eye(n)
    root = linalg.cholesky(G, lower=False)
    U0 = rng.standard_normal((n, m)) + 1j * rng.standard_normal((n, m))
    reference = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    rows = []
    for case in (
        "complex_SPD",
        "duplicate",
        "near_duplicate",
        "different_scales",
        "strong_correlation",
    ):
        U = U0.copy()
        if case == "duplicate":
            U[:, -1] = U[:, 0]
        if case == "near_duplicate":
            U[:, -1] = U[:, 0] + 1e-14 * U[:, -1]
        if case == "strong_correlation":
            U[:, -1] = U[:, 0] + 1e-8 * U[:, -1]
        if case == "different_scales":
            U *= np.geomspace(1e-8, 1e8, m)
        store = BasisStore(Path(directory) / case, dict(case=case))
        basis, stats, action, timers = build_basis(
            U, G, store, deadline=perf_counter() + 60
        )
        arrays, stats = reference_projection(U, reference, basis, stats, action, timers)
        # Independent full G square root, rank revealing SVD of normalized GU.
        scales = np.linalg.norm(U, axis=0)
        z, _, rank, _ = linalg.lstsq(
            root @ U / scales, root @ reference, cond=1e-12, lapack_driver="gelsd"
        )
        independent = U @ (z / scales)
        pair = float(linalg.norm(arrays["c"] - independent) / linalg.norm(independent))
        if case == "strong_correlation":
            # Ideal orthogonality does not authorize an inaccurate backtransform.
            if (
                stats["actual_U_amplitude_pair_relative"] > 1e-10
                and stats["floating_numerical_qualified"]
            ):
                raise ValueError("ILL_CONDITIONED_MAP_FALSE_QUALIFICATION")
        elif pair > 1e-10 or stats["retained_rank"] != rank:
            raise ValueError(
                "INDEPENDENT_SQRT_QR_SVD_MISMATCH: " + str((case, pair, rank))
            )
        rows.append(
            dict(case=case, independent_pair=pair, independent_rank=int(rank), **stats)
        )
    return rows


def negative_cases(directory):
    rng = np.random.default_rng(4213602)
    U = rng.normal(size=(23, 6)) + 1j * rng.normal(size=(23, 6))
    G = np.diag(np.linspace(1.0, 3.0, 23))
    store = BasisStore(Path(directory) / "negatives", dict(instance="one"))
    basis, stats, action, timers = build_basis(
        U, G, store, deadline=perf_counter() + 60
    )
    tests = []
    for label, bad in (
        ("wrong_conjugate", dict(basis, V=basis["V"].conj())),
        ("wrong_transform_order", dict(basis, T=basis["R"] @ basis["L1"])),
        (
            "drop_column_false_full_rank",
            dict(basis, V=basis["V"][:, :-1], T=basis["T"][:-1]),
        ),
    ):
        try:
            qualify_basis(U, bad, action, timers)
        except StabilityFailure:
            tests.append(label)
        else:
            raise ValueError("CORRUPTED_BASIS_ACCEPTED: " + label)
    try:
        small_metric(np.array([[1.0, 2j], [3j, 1.0]]))
    except StabilityFailure:
        tests.append("nonHermitian_A_is_not_G")
    else:
        raise ValueError("NONHERMITIAN_METRIC_ACCEPTED")
    try:
        BasisStore(store.directory, dict(instance="other")).reopen()
    except ValueError:
        tests.append("mixed_resume_identity")
    else:
        raise ValueError("MIXED_RECOVERY_ACCEPTED")
    return tests


def preservation_cases(directory):
    root = Path(directory)
    store = BasisStore(root / "zero_timeout", dict(instance="stop"))
    try:
        build_basis(
            np.eye(4, dtype=complex), np.eye(4), store, deadline=perf_counter() - 1
        )
    except ReadoutStop as error:
        atomic_json(store.directory / "stop.json", dict(original_reason=str(error)))
    else:
        raise ValueError("ZERO_PROGRESS_TIMEOUT_NOT_ENFORCED")
    if store.reopen()[0]["stage"] != "LOADED":
        raise ValueError("ZERO_PROGRESS_BOUNDARY_NOT_RETAINED")
    partial = BasisStore(root / "half_panel", dict(instance="partial"))
    partial.save(
        "G_PANEL_COMPLETE",
        dict(V=np.eye(5)[:, :2], T=np.eye(2), scales=np.ones(5)),
        dict(next_column=2, rank=2, discarded_columns=[], splits=[], G_columns=2),
    )
    # An uncommitted temporary file never replaces the complete pointer.
    (partial.directory / "latest.json.tmp").write_text('{"broken":')
    if partial.reopen()[0]["record"]["next_column"] != 2:
        raise ValueError("PARTIAL_WRITE_REPLACED_COMMITTED_BOUNDARY")
    empty = BasisStore(root / "empty", dict(instance="empty"))
    try:
        build_basis(
            np.zeros((7, 3), complex), np.eye(7), empty, deadline=perf_counter() + 60
        )
    except StabilityFailure:
        pass
    else:
        raise ValueError("EMPTY_RANK_WAS_QUALIFIED")
    return [
        "zero_progress_timeout",
        "half_panel_reopen",
        "atomic_pointer_partial_write",
        "empty_rank",
    ]


def qualify(directory):
    start = perf_counter()
    rows = fixture_cases(directory)
    negative = negative_cases(directory)
    preservation = preservation_cases(directory)
    return dict(
        fixtures=rows,
        negative_controls=negative,
        preservation=preservation,
        wall_seconds=perf_counter() - start,
        labels_used_only_in_fixture_projection=True,
        global_G_factor_count=0,
        Gsolve_count=0,
        qualification_scope="small algebra; real fixed prefix separately required",
    )


def real_panel_interruption_case(directory):
    """Interrupt the real panel kernel, then resume the saved completed panel."""
    rng = np.random.default_rng(4213604)
    U = rng.normal(size=(89, 65)) + 1j * rng.normal(size=(89, 65))
    G = np.diag(np.linspace(1.0, 4.0, 89))
    store = BasisStore(Path(directory) / "real_panel", dict(instance="real_panel"))

    class StopSecondPanel(PanelGram):
        def __call__(self, x, role):
            if (
                role == "fallback_panel_reorthogonalization"
                and self.by_role.get(role, 0) >= 64
            ):
                raise ReadoutStop("TEST_HALF_SECOND_PANEL")
            return super().__call__(x, role)

    stopped = StopSecondPanel(G, limit=100000)
    store.action = stopped
    try:
        panel_fallback(U, stopped, store, Timers())
    except ReadoutStop as error:
        if str(error) != "TEST_HALF_SECOND_PANEL":
            raise
    else:
        raise ValueError("REAL_PANEL_INTERRUPT_NOT_EXERCISED")
    resume = store.reopen()
    if resume[0]["record"]["next_column"] != 32:
        raise ValueError("REAL_COMPLETED_PANEL_NOT_RETAINED")
    continued = PanelGram(G, limit=100000)
    continued.count = resume[0]["record"]["G_columns"]
    continued.by_role = dict(resume[0]["record"]["G_by_role"])
    store.action = continued
    basis, stats = panel_fallback(U, continued, store, Timers(), resume)
    if not stats["full_column_space_retained"] or stats["G_orthogonality_F"] > 1e-9:
        raise ValueError("RESUMED_PANEL_KERNEL_NOT_EQUIVALENT")
    return dict(
        next_column_before_resume=32,
        final_rank=stats["retained_rank"],
        complete_panel_resumed=True,
        inherited_G_columns_preserved=True,
    )
