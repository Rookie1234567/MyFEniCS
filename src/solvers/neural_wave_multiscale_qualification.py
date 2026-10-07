"""Targeted real global/local full moments and residual-selection qualification."""

import numpy as np

from src.io.neural_wave_campaign import ROOT, digest, training_open_allowed
from src.solvers.neural_wave_moments import WaveMoments
from src.solvers.neural_wave_multiscale import (
    MultiscaleSupportPolicy,
    bounded_direction_optimize,
)
from src.solvers.neural_wave_greedy import variable_projection
from src.solvers.neural_wave_block import BlockWaveSubspace, BlockBasisStore
from src.solvers.neural_wave_reconstruction import pointwise_moments
from src.solvers.neural_wave_block_reconstruction import rebuild_stable


def relative(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def qualify(action, packet, design, artifact, marker):
    moments = WaveMoments(packet, 8)
    policy = MultiscaleSupportPolicy(design["model"]["geometry"], moments)
    rng = np.random.default_rng(4213202)
    space = BlockWaveSubspace(action, 64)
    binding = dict(
        route="QUALIFICATION",
        source_sha="qualification-bound-by-run-manifest",
        design_sha256=digest(ROOT / "input/task042extra_feinn_5nm/design_v32.json"),
        native_sha256=design["files"]["native"]["sha256"],
        moments_sha256=design["files"]["moments_q30"]["sha256"],
    )
    store = BlockBasisStore(artifact / "qualification_basis", binding)
    records = []
    patches = [policy.global_patch] + [pool[len(pool) // 2] for pool in policy.pools]
    for i, patch in enumerate(patches):
        q = rng.uniform(-1.7, 1.7, (1, 3))
        p = rng.normal(size=(1, 3)) + 1j * rng.normal(size=(1, 3))
        C = moments.columns(patch, q)

        def field(x):
            return patch.window(x)[:, None] * (
                np.exp(1j * (x - np.array(patch.center)) @ q.T) @ p
            )

        direct = pointwise_moments(packet, field, zero_outside_patch=patch)
        g = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
        dq = rng.normal(size=q.shape)
        gq, gp = moments.vjp(patch, q, p, g)
        slope = float(np.sum(gq * dq))
        fd = []
        for h in (1e-4, 1e-5, 1e-6):
            difference = (
                moments.forward(patch, q + h * dq, p)
                - moments.forward(patch, q - h * dq, p)
            ) / (2 * h)
            value = np.vdot(g, difference).real
            fd.append(
                dict(
                    step=h,
                    absolute=float(abs(value - slope)),
                    relative=float(
                        abs(value - slope) / max(abs(value), abs(slope), 1e-30)
                    ),
                )
            )
        z = action.apply(C @ p.ravel())
        AH = action.apply(g, adjoint=True)
        dot = abs(np.vdot(g, z) - np.vdot(AH, C @ p.ravel())) / max(
            abs(np.vdot(g, z)), abs(np.vdot(AH, C @ p.ravel())), 1e-30
        )
        before = variable_projection(action, space, moments, patch, q, gradient=True)
        local_pair = 0.0
        if patch.kind == "local":
            from src.solvers.neural_wave_local_action import LocalWaveAction
            from src.solvers.neural_wave_projection import ResidualProjectionCache

            rows = moments.rows[moments.cells(patch)].ravel()
            local = LocalWaveAction(action, rows[rows >= 0], support_kind=patch.kind)
            cached = variable_projection(
                action,
                space,
                moments,
                patch,
                q,
                gradient=True,
                local=local,
                projector=ResidualProjectionCache(space, local.output_rows),
            )
            local_pair = max(
                relative(cached[4], before[4]),
                abs(cached[0] - before[0]) / max(abs(before[0]), 1e-30),
            )
        vfd = []
        for h in (1e-4, 1e-5, 1e-6):
            plus = variable_projection(
                action, space, moments, patch, q + h * dq, gradient=False
            )[0]
            minus = variable_projection(
                action, space, moments, patch, q - h * dq, gradient=False
            )[0]
            value = (plus - minus) / (2 * h) / action.bnorm**2
            exact = float(np.sum(before[4] * dq))
            vfd.append(float(abs(value - exact) / max(abs(value), abs(exact), 1e-30)))
        event = space.add_block(C)
        if event["accepted"]:
            store.commit(space, dict(patch=patch, q=q), i + 1, event, rng, 1e30)
        record = dict(
            kind=patch.kind,
            level=patch.level,
            complete_mapping_relative=relative(C @ p.ravel(), direct),
            batch_relative=relative(WaveMoments(packet, 1).columns(patch, q), C),
            real_complex_q_FD=fd,
            amplitude_gradient_relative=relative(gp, (C.conj().T @ g).reshape(-1, 3)),
            original_A_AH_real_adjoint_relative=float(dot),
            projected_score_FD=vfd,
            local_complete_score_gradient_pair=local_pair,
            block_accepted=event["accepted"],
            small_full_action_pair=event.get("small_full_action_pair_relative"),
        )
        marker("multiscale_full_moment_qualification", record)
        records.append(record)
    rebuilt, saved, _ = rebuild_stable(artifact / "qualification_basis", packet, marker)
    restored = BlockWaveSubspace(action, 64)
    BlockBasisStore(artifact / "qualification_basis", binding).restore(
        restored, np.random.default_rng(0)
    )
    selections = []
    sensitivity = action.apply(space.r, adjoint=True)
    for step in (0, 8, 32, 128, 1024, 4096):
        pools, _, _ = policy.preselect(sensitivity, step)
        selections.append(
            dict(
                iteration=step,
                levels=sorted(set(p.level for p in pools)),
                count=len(pools),
            )
        )
    # An adversarial optimizer consumes exactly its hard limit; no result.x evaluation.
    calls = []

    def objective(q):
        calls.append(q.copy())
        return (float(-np.sum((q - 0.37) ** 2)), None, None, None, -2 * (q - 0.37))

    _, _, limited = bounded_direction_optimize(
        objective,
        np.array([[0.9, 0.8, 0.7]]),
        objective(np.array([[0.9, 0.8, 0.7]])),
        4,
        maxeval=2,
    )
    fixture_A = np.array([[1, 4], [2, 0]], complex)
    r = np.array([1, 0], complex)
    scores = [
        abs(np.vdot(fixture_A[:, j], r)) ** 2
        / np.vdot(fixture_A[:, j], fixture_A[:, j]).real
        for j in range(2)
    ]
    test_design = dict(
        design,
        active_training_artifact=str(artifact.parent / "v32_fixed_multiscale_wave"),
    )
    labels_rejected = all(
        not training_open_allowed(ROOT / path, test_design)
        for path in (
            "benchmarks/artifacts/task42extra/index_e3_reference.json",
            "benchmarks/artifacts/task42extra/v31/v31_learned_block_wave/basis/state_03858.npz",
            "benchmarks/artifacts/task42extra/v32/v32_fixed_validate_1/scoring_record.json",
        )
    )
    from src.solvers.neural_wave_local_action import LocalWaveAction

    cache_type_rejected = False
    try:
        LocalWaveAction(action, np.arange(action.size), support_kind="global")
    except ValueError as error:
        cache_type_rejected = str(error) == "GLOBAL_SUPPORT_MUST_USE_COMPLETE_ACTION"
    result = dict(
        actual_native_sha256=design["files"]["native"]["sha256"],
        actual_moments_sha256=design["files"]["moments_q30"]["sha256"],
        records=records,
        complete_model_reconstruction_relative=relative(rebuilt, saved),
        restored_coefficients_relative=relative(restored.c, space.c),
        persistent_scale_selections=selections,
        q_hard_limit_witness=limited,
        R_vs_AH_fixture_scores=scores,
        label_isolation_pass=labels_rejected,
        nonunit_floquet_coefficients=int(
            np.count_nonzero(abs(action.a["evals"] - 1) > 1e-12)
        ),
        global_support_covers_cells=len(moments.cells(policy.global_patch)),
        global_local_cache_bypassed=cache_type_rejected,
        reference_loaded=False,
    )
    result["implementation_qualified"] = bool(
        all(
            v["complete_mapping_relative"] <= 1e-10
            and v["batch_relative"] <= 1e-10
            and v["amplitude_gradient_relative"] <= 1e-10
            and v["original_A_AH_real_adjoint_relative"] <= 1e-10
            and min(x["relative"] for x in v["real_complex_q_FD"]) <= 1e-5
            and min(v["projected_score_FD"]) <= 1e-5
            and v["local_complete_score_gradient_pair"] <= 1e-10
            and v["block_accepted"]
            for v in records
        )
        and max(
            result["complete_model_reconstruction_relative"],
            result["restored_coefficients_relative"],
        )
        <= 1e-10
        and labels_rejected
        and cache_type_rejected
        and all(set(v["levels"]) == {-1, 0, 1, 2} for v in selections)
        and limited["function_calls"] <= 2
        and result["nonunit_floquet_coefficients"] > 0
    )
    return result
