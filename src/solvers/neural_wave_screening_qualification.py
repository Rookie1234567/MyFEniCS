"""Pair unchanged wave proposals with bounded, independent candidate batching.

All states are saved unlabelled native states. The old full A / two-pass
projection is an independent baseline. Timings compare the qualified local
backend with the batched version, including fresh cache build and release.
"""

import gc
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.neural_wave_greedy import (
    direction_dictionary, patch_inventory, variable_projection,
)
from src.solvers.neural_wave_local_action import LocalWaveAction
from src.solvers.neural_wave_moments import WaveMoments
from src.solvers.neural_wave_projection import ResidualProjectionCache
from src.solvers.neural_wave_projection_qualification import prefix_space, relative
from src.solvers.neural_wave_screening import screen_candidates


CHAIN = tuple(
    "src/solvers/neural_wave_" + name + ".py"
    for name in (
        "greedy", "subspace", "moments", "local_action", "projection",
        "reconstruction", "screening", "screening_qualification",
    )
)


def proposal_directions(design, iteration, width):
    strategy = design["strategy"]
    k0 = 2 * np.pi / design["model"]["wavelength_nm"]
    dictionary = direction_dictionary(k0, strategy["direction_resolutions"][0])
    return [
        dictionary[
            (iteration * strategy["screen_seeds"] + seed + np.arange(width) * 7)
            % len(dictionary)
        ].copy()
        for seed in range(strategy["screen_seeds"])
    ]


def refinements(design, best):
    strategy = design["strategy"]
    k0 = 2 * np.pi / design["model"]["wavelength_nm"]
    step = strategy["local_refinement_steps_k0"][0] * k0
    bound = strategy["q_component_bound_k0"] * k0
    values = []
    for axis in range(3):
        for sign in (-1, 1):
            q = best.copy()
            q[:, axis] += sign * step
            values.append(np.clip(q, -bound, bound))
    return values


def proposal(action, space, moments, patch, directions, design, *, local=None,
             projector=None, batched=False):
    def screen(values):
        if batched:
            return screen_candidates(action, space, moments, patch, values,
                                     local=local, projector=projector)
        result = []
        for q in values:
            try:
                result.append(variable_projection(
                    action, space, moments, patch, q, gradient=False,
                    local=local, projector=projector,
                ))
            except ValueError as error:
                if str(error) != "DEGENERATE_NEW_DIRECTION":
                    raise
                result.append(None)
        return result

    candidates = list(zip(directions, screen(directions), strict=True))
    usable = [(q, v) for q, v in candidates if v is not None]
    if not usable:
        raise ValueError("NO_VALID_FIXED_STRATEGY_SCREEN_DIRECTION")
    seed = max(usable, key=lambda v: v[1][0])[0]
    extra = refinements(design, seed)
    candidates.extend(zip(extra, screen(extra), strict=True))
    usable = [(q, v) for q, v in candidates if v is not None]
    selected = max(usable, key=lambda v: v[1][0])
    return candidates, selected


def qualify(action, packet, design, directory, artifact, marker):
    start = perf_counter()
    directory, artifact = Path(directory), Path(artifact)
    raw = (directory / "committed.json").read_bytes()
    boundary = json.loads(raw)
    if boundary["reference_used_for_training"] or boundary["columns"] < 512:
        raise ValueError("SAVED_UNLABELLED_SCREENING_PREFIX_REQUIRED")
    snapshot = artifact / "qualification_input_boundary.json"
    snapshot.write_bytes(raw)
    rng = np.random.default_rng(4213011)
    checks = []
    cases = ((64, 1, 0, 0), (256, 2, 1, 1),
             (boundary["columns"], 4, 2, 1),
             (boundary["columns"], 8, 2, 0))
    for count, width, level, interior in cases:
        space, identity = prefix_space(action, directory, boundary, count)
        patches = patch_inventory(design["model"]["geometry"], level)
        patch = patches[len(patches) // 2 if interior else 0]
        moments = WaveMoments(packet, batch=8)
        support = moments.rows[moments.cells(patch)].ravel()
        local = LocalWaveAction(action, support[support >= 0])
        cache = ResidualProjectionCache(
            space, local.output_rows, additional_cache_bytes=local.retained_bytes,
        )
        directions = proposal_directions(design, count, width)
        original, old_best = proposal(
            action, space, moments, patch, directions, design,
        )
        actual, new_best = proposal(
            action, space, moments, patch, directions, design,
            local=local, projector=cache, batched=True,
        )
        candidate_records = []
        for index, ((q0, old), (q1, new)) in enumerate(zip(original, actual, strict=True)):
            if old is None or new is None:
                candidate_records.append(dict(
                    index=index, both_degenerate=old is None and new is None,
                ))
                continue
            candidate_records.append(dict(
                index=index, both_degenerate=False,
                proposal_parameters_relative=relative(q1, q0),
                score_relative=abs(new[0] - old[0]) / max(old[0], 1e-30),
                full_coefficient_relative=relative(new[2], old[2]),
                amplitude_relative=relative(new[1], old[1]),
                rank_equal=new[3]["rank"] == old[3]["rank"],
            ))
        selected_pairs = dict(
            selected_parameters_relative=relative(new_best[0], old_best[0]),
            selected_full_coefficient_relative=relative(new_best[1][2], old_best[1][2]),
            selected_score_relative=abs(new_best[1][0] - old_best[1][0])
            / max(old_best[1][0], 1e-30),
        )
        old_gradient = variable_projection(
            action, space, moments, patch, old_best[0], gradient=True,
        )
        new_gradient = variable_projection(
            action, space, moments, patch, new_best[0], gradient=True,
            local=local, projector=cache,
        )
        selected_pairs["complete_original_real_gradient_relative"] = relative(
            new_gradient[4], old_gradient[4],
        )
        direction = rng.normal(size=new_best[0].shape)
        direction /= np.linalg.norm(direction)
        finite = []
        exact = float(np.sum(new_gradient[4] * direction))
        for step in (1e-4, 1e-5, 1e-6):
            plus = variable_projection(
                action, space, moments, patch, new_best[0] + step * direction,
                gradient=False, local=local, projector=cache,
            )[0]
            minus = variable_projection(
                action, space, moments, patch, new_best[0] - step * direction,
                gradient=False, local=local, projector=cache,
            )[0]
            fd = (plus - minus) / (2 * step * action.bnorm**2)
            finite.append(dict(step=step, analytic=exact, finite_difference=fd,
                               relative=abs(fd - exact) / max(abs(exact), 1e-30)))
        # Preserve the complete original proposed accepted step, not just loss.
        old_c, old_r = space.c.copy(), space.r.copy()
        old_a, old_m = space.a.copy(), space.m
        old_event = space.add(old_best[1][2])
        old_after_c, old_after_r = space.c.copy(), space.r.copy()
        space.m, space.c, space.r, space.a = old_m, old_c, old_r, old_a
        new_event = space.add(new_best[1][2])
        accepted_pair = dict(
            both_accepted=bool(old_event["accepted"] and new_event["accepted"]),
            full_committed_coefficient_relative=relative(space.c, old_after_c),
            full_true_residual_relative=relative(space.r, old_after_r),
        )
        space.m, space.c, space.r, space.a = old_m, old_c, old_r, old_a
        del cache
        space._small_basis_product = None
        space._small_basis_product_columns = 0
        before = perf_counter()
        space.small_basis_inner_product()
        times = dict(
            saved_prefix_Q_product_setup_s=perf_counter() - before,
            saved_prefix_Q_product_setup_scope="one startup after loading the saved prefix; shared existing accepted-basis cache thereafter",
            sequential_complete_proposal_s=[], batched_complete_proposal_s=[],
        )
        for repeat in range(3):
            ordering = (False, True) if repeat % 2 == 0 else (True, False)
            for batched in ordering:
                name = "batched_complete_proposal_s" if batched else "sequential_complete_proposal_s"
                before = perf_counter()
                # Bind and charge one new local/projection cache for every
                # complete proposal. Old/new receive exactly the same work.
                fresh_local = LocalWaveAction(action, support[support >= 0])
                fresh = ResidualProjectionCache(
                    space, fresh_local.output_rows,
                    additional_cache_bytes=fresh_local.retained_bytes,
                )
                proposal(action, space, moments, patch, directions, design,
                         local=fresh_local, projector=fresh, batched=batched)
                del fresh, fresh_local
                gc.collect()
                times[name].append(perf_counter() - before)
        times["complete_proposal_ratio_including_setup_release"] = (
            sum(times["sequential_complete_proposal_s"])
            / sum(times["batched_complete_proposal_s"])
        )
        times["ratio_with_one_saved_prefix_startup_charged_to_each_variant"] = (
            (times["saved_prefix_Q_product_setup_s"] + sum(times["sequential_complete_proposal_s"]))
            / (times["saved_prefix_Q_product_setup_s"] + sum(times["batched_complete_proposal_s"]))
        )
        record = dict(saved_state=identity, module_width=width, patch_level=level,
                      candidate_pairs=candidate_records, selected_pairs=selected_pairs,
                      nonzero_direction_finite_differences=finite,
                      accepted_step_pair=accepted_pair, costs=times,
                      moment_counts=dict(moments.counts),
                      moment_seconds=dict(moments.seconds))
        checks.append(record)
        marker("complete_independent_candidate_proposal_pair", record)
        del space, local
        gc.collect()
    def row_pass(row):
        pairs = row["candidate_pairs"]
        return (
            all(v["both_degenerate"] or (
                v.get("rank_equal", False)
                and all(x <= 1e-10 for k, x in v.items() if k.endswith("_relative"))
            ) for v in pairs)
            and all(x <= 1e-10 for x in row["selected_pairs"].values())
            and min(v["relative"] for v in row["nonzero_direction_finite_differences"]) <= 1e-5
            and row["accepted_step_pair"]["both_accepted"]
            and all(x <= 1e-10 for k, x in row["accepted_step_pair"].items()
                    if k.endswith("_relative"))
        )
    qualified = all(row_pass(row) for row in checks)
    selected_widths = [row["module_width"] for row in checks
                       if row_pass(row) and row["costs"]["complete_proposal_ratio_including_setup_release"] >= 1]
    return dict(
        implementation_qualified=qualified,
        equivalent_complete_proposal_qualified=qualified,
        complete_bounded_screening_selected=qualified and bool(selected_widths),
        selected_bounded_screening_widths=selected_widths if qualified else [],
        checks=checks, reference_loaded=False,
        bound_complete_boundary_sha256=hashlib.sha256(raw).hexdigest(),
        bound_complete_boundary_snapshot_path=str(snapshot),
        global_Maxwell_factor_count=0, global_Gram_factor_count=0,
        qualification_primitive_action_counts=dict(action.counts),
        qualification_primitive_action_seconds=dict(action.costs),
        maximum_independent_batched_proposals=8, maximum_batched_neurons=64,
        maximum_original_A_amplitude_columns_per_block=24,
        stage_elapsed_seconds=perf_counter() - start,
        original_default_unchanged=True,
    )
