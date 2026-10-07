"""Real full-moment block checks, isolated from all references and teachers."""

from pathlib import Path

import numpy as np

from src.solvers.neural_wave_block import BlockWaveSubspace, BlockBasisStore
from src.solvers.neural_wave_greedy import patch_inventory, variable_projection
from src.solvers.neural_wave_moments import WaveMoments
from src.solvers.neural_wave_subspace import WaveSubspace, optimal_amplitudes
from src.solvers.neural_wave_reconstruction import pointwise_moments
from src.solvers.neural_wave_block_reconstruction import rebuild_stable
from src.solvers.neural_wave_local_action import LocalWaveAction
from src.solvers.neural_wave_projection import ResidualProjectionCache

CHAIN = tuple(
    "src/solvers/" + name + ".py"
    for name in (
        "neural_wave_block",
        "neural_wave_greedy",
        "neural_wave_block_reconstruction",
        "neural_wave_subspace",
        "neural_wave_moments",
        "neural_wave_local_action",
        "neural_wave_projection",
        "neural_wave_reconstruction",
    )
)


def relative(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def qualify(action, packet, high, design, artifact, marker, binding):
    rng = np.random.default_rng(4213102)
    m8, m1 = WaveMoments(packet, batch=8), WaveMoments(packet, batch=1)
    space = BlockWaveSubspace(action, 64)
    store = BlockBasisStore(Path(artifact) / "qualification_basis", binding)
    checks = []
    for case, width in enumerate((1, 2, 4)):
        patches = patch_inventory(design["model"]["geometry"], case)
        patch = patches[len(patches) // 2]
        q = rng.uniform(-1.7, 1.7, (width, 3))
        p = rng.normal(size=(width, 3)) + 1j * rng.normal(size=(width, 3))
        C = m8.columns(patch, q)
        exact = np.column_stack(
            [
                pointwise_moments(
                    packet,
                    lambda x, j=j: patch.window(x)[:, None]
                    * np.exp(1j * (x - np.asarray(patch.center)) @ q[j // 3])[:, None]
                    * np.eye(3)[j % 3],
                    zero_outside_patch=patch,
                )
                for j in range(3 * width)
            ]
        )
        mapping = relative(C, exact)
        batch = relative(m1.columns(patch, q), C)
        g = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        gq, gp = m8.vjp(patch, q, p, g)
        dq = rng.normal(size=q.shape)
        dp = rng.normal(size=p.shape) + 1j * rng.normal(size=p.shape)
        slope = float(np.sum(gq * dq) + np.vdot(gp, dp).real)
        fd = []
        for h in (1e-4, 1e-5, 1e-6):
            actual = float(
                np.vdot(
                    g,
                    (
                        m8.forward(patch, q + h * dq, p + h * dp)
                        - m8.forward(patch, q - h * dq, p - h * dp)
                    )
                    / (2 * h),
                ).real
            )
            fd.append(
                dict(
                    h=h,
                    analytic=slope,
                    finite_difference=actual,
                    absolute=abs(actual - slope),
                    relative=abs(actual - slope) / max(abs(actual), abs(slope), 1e-30),
                )
            )
        support = m8.rows[m8.cells(patch)].ravel()
        local = LocalWaveAction(action, support[support >= 0])
        projector = ResidualProjectionCache(
            space, local.output_rows, additional_cache_bytes=local.retained_bytes
        )
        old = variable_projection(action, space, m8, patch, q, gradient=True)
        cached = variable_projection(
            action, space, m8, patch, q, gradient=True, local=local, projector=projector
        )
        score_pair = abs(old[0] - cached[0]) / max(abs(old[0]), 1e-30)
        gradient_pair = relative(old[4], cached[4])
        direction = rng.normal(size=q.shape)
        h = 1e-5
        plus = variable_projection(
            action, space, m8, patch, q + h * direction, gradient=False
        )[0]
        minus = variable_projection(
            action, space, m8, patch, q - h * direction, gradient=False
        )[0]
        predicted = float(np.sum(old[4] * direction)) * action.bnorm**2
        numerical = (plus - minus) / (2 * h)
        qfd = abs(predicted - numerical) / max(abs(predicted), abs(numerical), 1e-30)
        action_pairs = []
        for _ in range(3):
            amp = rng.normal(size=3 * width) + 1j * rng.normal(size=3 * width)
            c = C @ amp
            full = action.apply(c)
            limited = local.columns(c[:, None])[:, 0]
            adjoint = abs(
                np.vdot(g, full) - np.vdot(action.apply(g, adjoint=True), c)
            ) / max(abs(np.vdot(g, full)), 1e-30)
            action_pairs.append(
                dict(native_local=relative(limited, full), adjoint=float(adjoint))
            )
        before = space.r.copy()
        amp, _, rec = optimal_amplitudes(action, space, C)
        immediate = WaveSubspace(action, 64)
        immediate.m = space.m
        immediate.U[:, : space.m] = space.U[:, : space.m]
        immediate.Q[:, : space.m] = space.Q[:, : space.m]
        immediate.R[: space.m, : space.m] = space.R[: space.m, : space.m]
        immediate.a, immediate.c, immediate.r = (
            space.a.copy(),
            space.c.copy(),
            space.r.copy(),
        )
        event = space.add_block(exact)
        immediate.add(exact @ amp)
        same = float(np.linalg.norm(space.r - immediate.r) / action.bnorm)
        prediction = (
            abs(rec["score"] - event["actual_energy_decrease"]) / action.bnorm**2
        )
        store.commit(space, dict(patch=patch, q=q, p=p), case + 1, event, rng, 1e99)
        check = dict(
            width=width,
            level=case,
            full_moment_mapping_relative=mapping,
            batch_1_8=batch,
            real_direction_FD=fd,
            minimum_FD_relative=min(v["relative"] for v in fd),
            q_score_FD_relative=qfd,
            cached_score_relative=score_pair,
            cached_gradient_relative=gradient_pair,
            three_complex_action_pairs=action_pairs,
            immediate_single_block_residual_difference=same,
            predicted_actual_decrease_load_scaled=prediction,
            original_residual_nonincrease=bool(
                np.linalg.norm(space.r) <= np.linalg.norm(before) + 1e-10 * action.bnorm
            ),
            rank_added=event["rank_added"],
        )
        checks.append(check)
        marker("complete_real_block_qualification", check)
    c, saved, _ = rebuild_stable(store.directory, packet, marker)
    c60, _, _ = rebuild_stable(store.directory, high, marker)
    field_map = relative(c, saved)
    drift = relative(c, c60)
    action_drift = float(np.linalg.norm(action.apply(c - c60)) / action.bnorm)
    passed = all(
        v["full_moment_mapping_relative"] <= 1e-10
        and v["batch_1_8"] <= 1e-10
        and v["minimum_FD_relative"] <= 1e-5
        and v["q_score_FD_relative"] <= 1e-5
        and v["cached_score_relative"] <= 1e-10
        and v["cached_gradient_relative"] <= 1e-10
        and max(max(a.values()) for a in v["three_complex_action_pairs"]) <= 1e-10
        and v["immediate_single_block_residual_difference"] <= 1e-10
        and v["predicted_actual_decrease_load_scaled"] <= 1e-10
        and v["original_residual_nonincrease"]
        for v in checks
    )
    passed &= field_map <= 1e-10 and max(drift, action_drift) <= 1e-8
    return dict(
        implementation_qualified=bool(passed),
        checks=checks,
        complete_model_mapping_relative=field_map,
        coefficient_q30_q60_relative=drift,
        original_action_q30_q60_load_relative=action_drift,
        global_Gram_factor_count=0,
        global_Maxwell_factor_count=0,
        reference_used_for_training=False,
        qualification_scope="small actual full FE blocks, complete original moments and paired native action; not M5 numerical solve",
    )
