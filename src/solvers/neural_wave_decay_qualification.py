"""Four bounded real oscillation/decay witnesses; no reference or inverse."""

from time import perf_counter

import numpy as np

from src.solvers.neural_wave_backfit import InactiveComplement, insert_block_qr
from src.solvers.neural_wave_backfit_qualification import preregistered_blocks
from src.solvers.neural_wave_decay import (
    ComplexActivityMoments,
    block_parameters,
    coordinate_contract,
    physical_decay_seeds,
)
from src.solvers.neural_wave_moments import WaveMoments


def relative(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def saved_witness_gate(rows, saved_loop, restored):
    """Recompute gates; the original residual always uses the original RHS.

    ``zero_pairs.r`` is an additional diagnostic normalized by the nonzero
    saved residual, not the contracted original-equation denominator. Keep it
    in the raw record, but do not substitute it for ``r_original``.
    """

    def bounded(values, tolerance):
        return all(np.isfinite(v) and 0 <= v <= tolerance for v in values)

    if len(rows) != 4 or len({r["block_id"] for r in rows}) != 4:
        return False
    if {(-1 if r["kind"] == "global" else r["level"]) for r in rows} != {-1, 0, 1, 2}:
        return False
    for row in rows:
        z = row["zero_pairs"]
        fd = row["finite_differences"]
        probes = row["decay_probes"]
        if not (
            row["actual_complete_trials"] == 8
            and bounded(row["kappa_zero_regression"].values(), 1e-10)
            and bounded(
                (z[k] for k in ("columns", "c", "r_original", "inserted_A")), 1e-10
            )
            and {r["kind"] for r in fd} == {"q_only", "kappa_only", "mixed"}
            and len(fd) == 3
            and bounded((r["relative_error"] for r in fd), 1e-5)
            and len(probes) == 2
            and {p["sign"] for p in probes} == {-1, 1}
        ):
            return False
        for p in probes:
            if not (
                bounded(
                    (
                        p[k]
                        for k in (
                            "independent_map",
                            "batch1_8",
                            "A_AH",
                            "original_MPC_expand_pullback",
                        )
                    ),
                    1e-10,
                )
                and p["nonunit_original_Floquet_entries"] > 0
                and bounded(
                    (p[k] for k in ("quadrature_q30_q60", "original_A_quadrature")),
                    1e-8,
                )
                and bounded((p["full_VJP_FD_relative"],), 1e-5)
                and set(p["families"]) == {"edge", "face", "interior"}
                and all(
                    v["count"] > 0
                    and v["norm"] > 0
                    and bounded((v["full_map"],), 1e-10)
                    for v in p["families"].values()
                )
            ):
                return False
    return bool(
        restored
        and saved_loop["complete_trial_budget_not_exceeded"]
        and bounded(
            (saved_loop["model_pair"], saved_loop["pair"]["pair_relative"]), 1e-10
        )
    )


def qualify_decay(
    action, packet, high, space, blocks, k0, beta, artifact, anchor, binding, marker
):
    from src.solvers.neural_trace import moment_packet_values

    m = ComplexActivityMoments(packet, 8)
    m1 = ComplexActivityMoments(packet, 1)
    hmap = ComplexActivityMoments(high, 8)
    original = WaveMoments(packet, 8)
    rng = np.random.default_rng(4213401)
    rows, saved_loop = [], None
    anchor_c, anchor_r = space.c.copy(), space.r.copy()
    for bid in preregistered_blocks(blocks):
        start = perf_counter()
        block = blocks[bid]
        patch = block["patch"]
        z0 = block_parameters(block)
        scale, _, R = coordinate_contract(block, m, k0)
        first, last = block["start"], block["stop"]
        width = len(z0)
        p = rng.normal(size=(width, 3)) + 1j * rng.normal(size=(width, 3))
        cot = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        new0, old0 = m.columns(patch, z0), original.columns(patch, z0[:, :3])
        g0, gp0 = m.vjp(patch, z0, p, cot)
        oldg, oldp = original.vjp(patch, z0[:, :3], p, cot)
        regressions = dict(
            columns=relative(new0, old0),
            A=relative(action.apply(new0 @ p.ravel()), action.apply(old0 @ p.ravel())),
            VJP_q=relative(g0[:, :3], oldg),
            VJP_p=relative(gp0, oldp),
        )
        # Nonzero, pure decay, both z signs and every vector component. This
        # independent dense point->original full matrix path uses no producer
        # column contraction or VJP. No magnitude term is removed.
        probes = []
        for sign in (1, -1):
            z = z0.copy()
            z[:, 3:] = sign * np.array([0.21, -0.17, 0.29]) / R
            if sign == -1:
                z[:, :3] = 0

            def raw(x):
                return patch.window(x)[:, None] * (
                    np.exp((x - patch.center) @ (1j * z[:, :3] - z[:, 3:]).T) @ p
                )

            c = m.columns(patch, z) @ p.ravel()
            independent = moment_packet_values(packet, raw)
            c1 = m1.columns(patch, z) @ p.ravel()
            ch = hmap.columns(patch, z) @ p.ravel()
            families = {}
            for family in ("edge", "face", "interior"):
                ids = packet["owner_rows"][:, packet[family + "_positions"]].ravel()
                ids = ids[ids >= 0]
                families[family] = dict(
                    count=len(ids),
                    norm=float(np.linalg.norm(c[ids])),
                    full_map=relative(c[ids], independent[ids]),
                )
            v = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
            av, ah = action.apply(c), action.apply(v, adjoint=True)
            adj = float(
                abs(np.vdot(v, av) - np.vdot(ah, c))
                / max(np.linalg.norm(v) * np.linalg.norm(av), 1e-30)
            )
            g, _ = m.vjp(patch, z, p, cot)
            local_cot = rng.normal(size=(action.nc, action.dim)) + 1j * rng.normal(
                size=(action.nc, action.dim)
            )
            expanded = action.expand(c)
            pulled = action.pullback(local_cot)
            mpc_adjoint = float(
                abs(np.vdot(local_cot, expanded) - np.vdot(pulled, c))
                / max(np.linalg.norm(local_cot) * np.linalg.norm(expanded), 1e-30)
            )
            direction = rng.normal(size=z.shape) * scale
            step = 1e-6
            cp = m.delta_columns(patch, z + step * direction, z) @ p.ravel()
            cm = m.delta_columns(patch, z - step * direction, z) @ p.ravel()
            fd = float(np.vdot(cot, cp - cm).real / (2 * step))
            exact = float(np.sum(g * direction))
            probe = dict(
                sign=sign,
                pure_decay=sign == -1,
                independent_map=relative(c, independent),
                batch1_8=relative(c1, c),
                quadrature_q30_q60=relative(c, ch),
                original_A_quadrature=relative(action.apply(c), action.apply(ch)),
                A_AH=adj,
                original_MPC_expand_pullback=mpc_adjoint,
                nonunit_original_Floquet_entries=int(
                    np.count_nonzero(abs(action.a["evals"] - 1) > 1e-10)
                ),
                full_VJP_FD_relative=abs(fd - exact) / max(abs(exact), 1e-14),
                full_VJP_FD_absolute=abs(fd - exact),
                families=families,
            )
            probes.append(probe)
            marker("complex_point_moment_probe", dict(block_id=bid, **probe))
        F = InactiveComplement(
            action,
            space.U,
            space.Q,
            space.R,
            first,
            last,
            center=(space.a, space.c),
            base_q=z0,
        )
        zero = F.trial(m, patch, z0, block["amplitude_map"], gradient=True)
        qrq, qrr = insert_block_qr(F, zero.applied)
        zero_pairs = dict(
            columns=relative(zero.columns, space.U[:, first:last]),
            c=relative(zero.c, space.c),
            r=relative(zero.r, space.r),
            r_original=float(np.linalg.norm(zero.r - space.r) / action.bnorm),
            inserted_A=float(
                np.linalg.norm(qrq @ (qrr @ zero.amplitudes) - action.apply(zero.c))
                / action.bnorm
            ),
        )
        fdrows, trials, best = [], 1, zero
        for j, (kind, step) in enumerate(
            zip(("q_only", "kappa_only", "mixed"), (1e-4, 1e-5, 1e-6), strict=True)
        ):
            v = rng.normal(size=z0.shape)
            if kind == "q_only":
                v[:, 3:] = 0
            elif kind == "kappa_only":
                v[:, :3] = 0
            v /= np.linalg.norm(v)
            probe = 1e-6
            dp = m.delta_columns(patch, z0 + probe * scale * v, z0)
            dm = m.delta_columns(patch, z0 - probe * scale * v, z0)
            tangent = (
                (dp - dm)
                @ block["amplitude_map"]
                @ zero.amplitudes[first:last]
                / (2 * probe)
            )
            sensitivity = float(np.linalg.norm(action.apply(tangent)) / action.bnorm)
            v /= max(1.0, sensitivity)
            plus = F.trial(
                m, patch, z0 + step * scale * v, block["amplitude_map"], gradient=False
            )
            minus = F.trial(
                m, patch, z0 - step * scale * v, block["amplitude_map"], gradient=False
            )
            derivative = float(
                -np.vdot(
                    plus.r + minus.r,
                    action.apply(plus.centered_change - minus.centered_change),
                ).real
                / (4 * step * action.bnorm**2)
            )
            represented = (plus.q - minus.q) / (2 * step)
            expected = float(np.sum(zero.gradient * represented))
            row = dict(
                kind=kind,
                h=step,
                finite_difference=derivative,
                analytic=expected,
                represented_direction=represented,
                sensitivity=sensitivity,
                absolute_error=abs(derivative - expected),
                relative_error=abs(derivative - expected) / max(abs(expected), 1e-14),
                additional_moment_only_probe_calls=2,
                complete_trial_calls=2,
            )
            fdrows.append(row)
            marker("complex_varpro_real_FD", dict(block_id=bid, **row))
            trials += 2
            for trial in (plus, minus):
                if trial.objective < best.objective:
                    best = trial
        seeds, seed_record = physical_decay_seeds(block, m, k0, beta)
        seed = F.trial(m, patch, seeds[0], block["amplitude_map"], gradient=False)
        trials += 1
        if seed.objective < best.objective:
            best = seed
        if saved_loop is None:
            from src.io.neural_wave_backfit_store import (
                BackfitStore,
                accept_and_save,
                check_boundary,
            )
            from src.solvers.neural_wave_block_reconstruction import rebuild_stable

            snapshot = (
                space.U[:, first:last].copy(),
                space.Q,
                space.R,
                space.a,
                space.c,
                space.r,
                block["wave_q"].copy(),
                block["decay_kappa"].copy(),
            )
            store = BackfitStore(artifact / "complex_short_block", binding, anchor)
            state = dict(accepted=0, visits=0, boundary_count=0)
            store.save(space, blocks, dict(kind="kappa_zero_anchor"), state)
            try:
                state.update(accepted=1, visits=1)
                pair, receipt = accept_and_save(
                    space,
                    blocks,
                    bid,
                    F,
                    best,
                    store,
                    dict(kind="complex_short_block"),
                    state,
                )
                check_boundary(store.directory / "committed.json")
                actual, producer, _ = rebuild_stable(store.directory, packet, marker)
                saved_loop = dict(
                    block_id=bid,
                    pair=pair,
                    model_pair=relative(actual, producer),
                    nonzero_decay=bool(np.any(block["decay_kappa"] != 0)),
                    source=receipt["binding"]["source_sha"],
                    complete_trial_budget_not_exceeded=trials <= 8,
                )
            finally:
                (
                    u,
                    space.Q,
                    space.R,
                    space.a,
                    space.c,
                    space.r,
                    block["wave_q"],
                    block["decay_kappa"],
                ) = snapshot
                space.U[:, first:last] = u
        passed = (
            max(regressions.values()) <= 1e-10
            and max(zero_pairs[k] for k in ("columns", "c", "r_original", "inserted_A"))
            <= 1e-10
            and all(r["relative_error"] <= 1e-5 for r in fdrows)
            and all(
                max(
                    p["independent_map"],
                    p["batch1_8"],
                    p["A_AH"],
                    p["original_MPC_expand_pullback"],
                )
                <= 1e-10
                and p["nonunit_original_Floquet_entries"] > 0
                and max(p["quadrature_q30_q60"], p["original_A_quadrature"]) <= 1e-8
                and p["full_VJP_FD_relative"] <= 1e-5
                for p in probes
            )
        )
        row = dict(
            block_id=bid,
            kind=patch.kind,
            level=patch.level,
            R=R,
            kappa_zero_regression=regressions,
            zero_pairs=zero_pairs,
            decay_probes=probes,
            finite_differences=fdrows,
            physical_seeds=seed_record,
            seed_native=float(np.linalg.norm(seed.r) / action.bnorm),
            actual_complete_trials=trials,
            pass_all=bool(passed),
            seconds=perf_counter() - start,
        )
        rows.append(row)
        marker("complex_wave_block_qualified", row)
        del F, zero, seed, best, plus, minus, qrq, qrr
    restored = np.array_equal(space.c, anchor_c) and np.array_equal(space.r, anchor_r)
    return dict(
        implementation_qualified=saved_witness_gate(rows, saved_loop, restored),
        rows=rows,
        actual_saved_loop=saved_loop,
        anchor_restored_bitwise=restored,
        actual_complete_trials=sum(x["actual_complete_trials"] for x in rows),
        original_action_counts=dict(action.counts),
        moments_counts=dict(m.counts),
        reference_read_count=0,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
    )
