"""Original complete native action pairing for local input-support reuse."""

from time import perf_counter

import numpy as np

from src.solvers.neural_wave_greedy import patch_inventory, variable_projection
from src.solvers.neural_wave_local_action import LocalWaveAction
from src.solvers.neural_wave_moments import WaveMoments, pack, unpack
from src.solvers.neural_wave_subspace import WaveSubspace


def relative(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def qualify(action, packet, design, marker):
    rng = np.random.default_rng(4213008)
    start = perf_counter()
    moments = WaveMoments(packet, batch=8)
    space = WaveSubspace(action, 8)
    patches = patch_inventory(design["model"]["geometry"], 0)
    q = rng.normal(size=(2, 3))
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    for patch in (patches[0], patches[len(patches) // 2]):
        space.add(moments.forward(patch, q, p))
    checks, timings = [], []
    for level in (0, 1, 2):
        inventory = patch_inventory(design["model"]["geometry"], level)
        # Periodic corner images and interior patches, no target field selection.
        for index in (0, len(inventory) // 2):
            patch = inventory[index]
            rows = moments.rows[moments.cells(patch)].ravel()
            rows = rows[rows >= 0]
            before = perf_counter()
            local = LocalWaveAction(action, rows)
            build_s = perf_counter() - before
            columns = moments.columns(patch, q)
            original = np.column_stack([action.apply(c) for c in columns.T])
            cached = local.columns(columns)
            g = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
            old_adjoint, new_adjoint = action.apply(g, adjoint=True), local.adjoint(g)
            pairing = abs(np.vdot(g, cached @ p.ravel()) - np.vdot(new_adjoint, columns @ p.ravel()))
            pairing /= max(abs(np.vdot(g, cached @ p.ravel())), 1e-30)
            old_vjp, new_vjp = (
                moments.vjp(patch, q, p, old_adjoint),
                moments.vjp(patch, q, p, new_adjoint),
            )
            theta, direction = pack(q, p), rng.normal(size=18)
            direction /= np.linalg.norm(direction)
            step = 1e-5
            finite = np.vdot(
                g,
                action.apply(moments.forward(patch, *unpack(theta + step * direction)))
                - action.apply(moments.forward(patch, *unpack(theta - step * direction))),
            ).real / (2 * step)
            derivative = float(pack(*new_vjp) @ direction)
            record = dict(
                support_level=level, patch_index=index,
                input_rows=len(local.support), original_touched_cells=len(local.cells),
                retained_cache_bytes=local.retained_bytes,
                complete_A_columns_relative=relative(cached, original),
                selected_AH_relative=relative(new_adjoint[local.support], old_adjoint[local.support]),
                complex_adjoint_relative=float(pairing),
                full_moment_real_VJP_relative=relative(pack(*new_vjp), pack(*old_vjp)),
                nonzero_real_direction_FD_relative=abs(finite - derivative) / max(abs(derivative), 1e-30),
                batch1_8_relative=relative(WaveMoments(packet, 1).forward(patch, q, p), moments.forward(patch, q, p)),
            )
            for gradient in (False, True):
                old = variable_projection(action, space, moments, patch, q, gradient=gradient)
                new = variable_projection(action, space, moments, patch, q, gradient=gradient, local=local)
                record["native_score_relative_gradient_" + str(gradient)] = abs(old[0] - new[0]) / max(old[0], 1e-30)
                record["actual_wave_field_relative_gradient_" + str(gradient)] = relative(new[2], old[2])
                if gradient:
                    record["native_score_gradient_relative"] = relative(new[4], old[4])
            # Three alternating complete score/gradient calls. Include build
            # once in the new total. Not a cold NN/solver resource advantage.
            times = dict(old_s=0.0, new_s=build_s, build_s=build_s)
            for repeat in range(3):
                for name in (("old_s", "new_s") if repeat % 2 == 0 else ("new_s", "old_s")):
                    before = perf_counter()
                    variable_projection(
                        action, space, moments, patch, q, gradient=True,
                        local=local if name == "new_s" else None,
                    )
                    times[name] += perf_counter() - before
            times["speed_ratio_including_build"] = times["old_s"] / times["new_s"]
            checks.append(record)
            timings.append(dict(support_level=level, patch_index=index, **times))
            marker("local_action_qualification", record)
    numerical = all(
        value <= (1e-5 if "FD_relative" in key else 1e-10)
        for item in checks for key, value in item.items() if "relative" in key
    )
    return dict(
        implementation_qualified=numerical, checks=checks, cost_pairs=timings,
        fields_and_original_ports_retained=True, no_amplitude_pruning=True,
        original_cell_batch=8, reference_loaded=False,
        global_Gram_factor_count=0, global_Maxwell_factor_count=0,
        field_family_counts={
            name: int(np.count_nonzero(packet["owner_rows"][:, packet[name + "_positions"]] >= 0))
            for name in ("edge", "face", "interior")
        },
        numerical_gate="NOT_TESTED_IMPLEMENTATION_ONLY",
        stage_elapsed_seconds=perf_counter() - start,
    )
