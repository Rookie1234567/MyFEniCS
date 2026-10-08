"""Bounded real complete-moment/gradient witnesses, without any reference label."""

from time import perf_counter

import numpy as np

from src.solvers.neural_wave_backfit import InactiveComplement, insert_block_qr
from src.solvers.neural_wave_moments import WaveMoments


def preregistered_blocks(blocks):
    selected = []
    for kind in (-1, 0, 1, 2):
        matches = [
            i
            for i, b in enumerate(blocks)
            if (-1 if b["patch"].kind == "global" else b["patch"].level) == kind
        ]
        if matches:
            selected.append(min(matches))
    for i in range(len(blocks)):
        if len(selected) >= 4:
            break
        if i not in selected:
            selected.append(i)
    return selected


def qualify_real(
    action,
    packet,
    space,
    blocks,
    k0,
    marker,
    *,
    artifact=None,
    anchor=None,
    binding=None,
):
    moments = WaveMoments(packet, 8)
    rng = np.random.default_rng(4213301)
    rows = []
    closed_loop = None
    for block_id in preregistered_blocks(blocks):
        started = perf_counter()
        b = blocks[block_id]
        first, last = b["start"], b["stop"]
        F = InactiveComplement(action, space.U, space.Q, space.R, first, last)
        zero = F.trial(
            moments, b["patch"], b["wave_q"], b["amplitude_map"], gradient=True
        )
        mapping = float(
            np.linalg.norm(zero.columns - space.U[:, first:last])
            / max(np.linalg.norm(space.U[:, first:last]), 1e-30)
        )
        coefficient = float(
            np.linalg.norm(zero.c - space.c) / max(np.linalg.norm(space.c), 1e-30)
        )
        residual = float(np.linalg.norm(zero.r - space.r) / action.bnorm)
        q, r = insert_block_qr(F, zero.applied)
        rebuilt_apply = q @ (r @ zero.amplitudes)
        factor_pair = float(
            np.linalg.norm(rebuilt_apply - action.apply(zero.c)) / action.bnorm
        )
        # Independent original A/AH chain, all components and full MPC retained.
        v = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        w = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        av = action.apply(v)
        ahw = action.apply(w, adjoint=True)
        adjoint = float(
            abs(np.vdot(w, av) - np.vdot(ahw, v))
            / max(np.linalg.norm(w) * np.linalg.norm(av), 1e-30)
        )
        direct = (
            WaveMoments(packet, 1).columns(b["patch"], b["wave_q"]) @ b["amplitude_map"]
        )
        batch = float(
            np.linalg.norm(direct - zero.columns) / max(np.linalg.norm(direct), 1e-30)
        )
        fd = []
        trials = 1
        best = zero
        # Exactly 3 directions *2 trials plus the zero state (<=8 per block).
        # h is preregistered in dimensionless q/k0 coordinates, not FE units.
        for j, h in enumerate((1e-4, 1e-5, 1e-6)):
            direction = rng.normal(size=b["wave_q"].shape)
            direction /= np.linalg.norm(direction)
            plus = F.trial(
                moments,
                b["patch"],
                b["wave_q"] + h * k0 * direction,
                b["amplitude_map"],
                gradient=False,
            )
            minus = F.trial(
                moments,
                b["patch"],
                b["wave_q"] - h * k0 * direction,
                b["amplitude_map"],
                gradient=False,
            )
            derivative = float((plus.objective - minus.objective) / (2 * h))
            expected = float(np.sum(zero.gradient * direction) * k0)
            fd.append(
                dict(
                    direction_id=j,
                    h=h,
                    finite_difference=derivative,
                    analytic=expected,
                    absolute_error=abs(derivative - expected),
                    relative_error=abs(derivative - expected)
                    / max(abs(expected), 1e-14),
                )
            )
            trials += 2
            for trial in (plus, minus):
                if trial.objective < best.objective:
                    best = trial
        gradient_pass = all(x["relative_error"] <= 1e-5 for x in fd)
        if closed_loop is None and artifact is not None:
            from src.io.neural_wave_backfit_store import (
                BackfitStore,
                accept_and_save,
                check_boundary,
            )
            from src.solvers.neural_wave_block_reconstruction import rebuild_stable

            saved = (
                space.U[:, first:last].copy(),
                space.Q,
                space.R,
                space.a,
                space.c,
                space.r,
                b["wave_q"].copy(),
            )
            store = BackfitStore(artifact / "short_block_closed_loop", binding, anchor)
            state = dict(accepted=0, visits=0, boundary_count=0)
            store.save(space, blocks, dict(kind="original_anchor"), state)
            try:
                state.update(accepted=1, visits=1)
                pair, receipt = accept_and_save(
                    space,
                    blocks,
                    block_id,
                    F,
                    best,
                    store,
                    dict(kind="qualified_short_block"),
                    state,
                )
                check_boundary(store.directory / "committed.json")
                actual, producer, _ = rebuild_stable(store.directory, packet, marker)
                model_pair = float(
                    np.linalg.norm(actual - producer)
                    / max(np.linalg.norm(producer), 1e-30)
                )
                closed_loop = dict(
                    block_id=block_id,
                    pair=pair,
                    model_pair=model_pair,
                    q_changed=bool(np.any(best.q != saved[-1])),
                    committed_source=receipt["binding"]["source_sha"],
                    pass_all=model_pair <= 1e-10,
                )
            finally:
                u, space.Q, space.R, space.a, space.c, space.r, b["wave_q"] = saved
                space.U[:, first:last] = u
        row = dict(
            block_id=block_id,
            level=b["patch"].level,
            kind=b["patch"].kind,
            width=len(b["wave_q"]),
            columns=last - first,
            complete_q_trials=trials,
            zero_column_map=mapping,
            zero_complete_c=coefficient,
            zero_residual_pair=residual,
            inserted_factor_pair=factor_pair,
            batch1_8=batch,
            real_A_AH_pair=adjoint,
            fd=fd,
            q_gradient_norm=float(np.linalg.norm(zero.gradient)),
            inactive_rank=F.solver.rank,
            active_rank=zero.active_rank,
            reduced_complete_pair=zero.pairing,
            setup_seconds=F.setup_seconds,
            total_seconds=perf_counter() - started,
            pass_all=bool(
                max(mapping, coefficient, residual, factor_pair, batch, adjoint)
                <= 1e-10
                and gradient_pass
            ),
        )
        rows.append(row)
        marker("real_backfit_block_qualification", row)
        del F, q, r, direct, zero, plus, minus
    return dict(
        implementation_qualified=all(r["pass_all"] for r in rows)
        and (closed_loop is None or closed_loop["pass_all"]),
        actual_short_block_closed_loop=closed_loop,
        rows=rows,
        reference_read_count=0,
        actual_q_trial_calls=sum(r["complete_q_trials"] for r in rows),
        anchor_restored_after_witnesses=True,
        actual_A_counts=dict(action.counts),
        moments_counts=moments.counts,
    )
