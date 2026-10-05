"""Two-pass cache paired on saved, unlabelled complete neural boundaries."""

import json
import hashlib
from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.neural_wave_greedy import patch_inventory, sha, variable_projection
from src.solvers.neural_wave_local_action import LocalWaveAction
from src.solvers.neural_wave_moments import WaveMoments
from src.solvers.neural_wave_projection import ResidualProjectionCache
from src.solvers.neural_wave_subspace import WaveSubspace


def relative(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def prefix_space(action, directory, boundary, count):
    space = WaveSubspace(action, count + 1)
    for i, entry in enumerate(boundary["chunks"][:count]):
        file = directory / entry["path"]
        if sha(file) != entry["sha256"]:
            raise ValueError("SAVED_UNLABELLED_BASIS_HASH_FAILED")
        with np.load(file, allow_pickle=False) as arrays:
            space.U[:, i], space.Q[:, i] = arrays["u"], arrays["q"]
            space.R[:i + 1, i] = arrays["R_column"]
    state = directory / (
        boundary["state"]["path"] if count == boundary["columns"]
        else f"state_{count - 1:05d}.npz"
    )
    with np.load(state, allow_pickle=False) as arrays:
        space.c, space.r, space.a = (np.array(arrays[k]) for k in ("c", "r", "a"))
    space.m = count
    if relative(space.U[:, :count] @ space.a, space.c) > 1e-10:
        raise ValueError("SAVED_UNLABELLED_FIELD_RECONSTRUCTION_FAILED")
    if np.linalg.norm(action.f - action.apply(space.c) - space.r) > 1e-10 * action.bnorm:
        raise ValueError("SAVED_UNLABELLED_ORIGINAL_RESIDUAL_FAILED")
    return space, dict(
        columns=count, state_path=str(state), state_sha256=sha(state),
        basis_prefix_chunks_sha256=hashlib.sha256(
            json.dumps(boundary["chunks"][:count], sort_keys=True).encode()
        ).hexdigest(),
        native_relative=float(np.linalg.norm(space.r) / action.bnorm),
    )


def qualify(action, packet, design, directory, artifact, marker):
    start = perf_counter()
    directory = Path(directory)
    boundary_file = directory / "committed.json"
    boundary_bytes = boundary_file.read_bytes()
    boundary = json.loads(boundary_bytes)
    snapshot = Path(artifact) / "qualification_input_boundary.json"
    snapshot.write_bytes(boundary_bytes)
    if boundary["reference_used_for_training"] or boundary["columns"] < 256:
        raise ValueError("PROJECTION_REUSE_REQUIRES_REAL_UNLABELLED_ACCEPTED_PREFIX")
    rng = np.random.default_rng(4213010)
    checks = []
    for count, widths in ((64, (1,)), (256, (2,)), (boundary["columns"], (4, 8))):
        space, identity = prefix_space(action, directory, boundary, count)
        patches = patch_inventory(design["model"]["geometry"], 2)
        patch = patches[len(patches) // 2]
        moments = WaveMoments(packet, batch=8)
        rows = moments.rows[moments.cells(patch)].ravel()
        local = LocalWaveAction(action, rows[rows >= 0])
        before = perf_counter()
        cache = ResidualProjectionCache(space, local.output_rows, additional_cache_bytes=local.retained_bytes)
        setup = perf_counter() - before
        for width in widths:
            q = rng.normal(size=(width, 3))
            full_columns = moments.columns(patch, q)
            original_A = np.column_stack([action.apply(c) for c in full_columns.T])
            actual_A = local.columns(full_columns)
            old_projected = space.project(original_A)
            new_projected = cache.project(actual_A, supported=True)
            old = variable_projection(action, space, moments, patch, q, gradient=True)
            new = variable_projection(action, space, moments, patch, q, gradient=True, local=local, projector=cache)
            g = rng.normal(size=action.size) + 1j * rng.normal(size=action.size)
            old_adjoint, new_adjoint = action.apply(g, adjoint=True), local.adjoint(g)
            direction = rng.normal(size=q.shape)
            direction /= np.linalg.norm(direction)
            finite = []
            for step in (1e-4, 1e-5, 1e-6):
                plus = variable_projection(action, space, moments, patch, q + step * direction, gradient=False, local=local, projector=cache)[0]
                minus = variable_projection(action, space, moments, patch, q - step * direction, gradient=False, local=local, projector=cache)[0]
                fd = (plus - minus) / (2 * step * action.bnorm**2)
                exact = float(np.sum(new[4] * direction))
                finite.append(dict(step=step, derivative=fd, analytic=exact, relative=abs(fd - exact) / max(abs(exact), 1e-30)))
            times = dict(setup_s=setup, original_complete_call_s=[], cached_complete_call_s=[])
            for repeat in range(3):
                for name in (("original_complete_call_s", "cached_complete_call_s") if repeat % 2 == 0 else ("cached_complete_call_s", "original_complete_call_s")):
                    before = perf_counter()
                    variable_projection(
                        action, space, moments, patch, q, gradient=True,
                        local=local if name == "cached_complete_call_s" else None,
                        projector=cache if name == "cached_complete_call_s" else None,
                    )
                    times[name].append(perf_counter() - before)
            times["speed_including_first_setup"] = sum(times["original_complete_call_s"]) / (setup + sum(times["cached_complete_call_s"]))
            times["per_complete_call_ratio"] = sum(times["original_complete_call_s"]) / sum(times["cached_complete_call_s"])
            record = dict(
                saved_state=identity, module_width=width,
                complete_original_A_pair_relative=relative(actual_A, original_A),
                original_selected_AH_pair_relative=relative(new_adjoint[local.support], old_adjoint[local.support]),
                two_pass_projection_relative=relative(new_projected, old_projected),
                native_score_relative=abs(new[0] - old[0]) / max(old[0], 1e-30),
                actual_complete_wave_relative=relative(new[2], old[2]),
                original_real_gradient_relative=relative(new[4], old[4]),
                nonzero_direction_finite_differences=finite,
                retained_cache_bytes=cache.retained_bytes + local.retained_bytes,
                cost_pairs=times,
            )
            marker("complete_residual_projection_pair", {
                k: v for k, v in record.items() if k != "saved_state"
            })
            checks.append(record)
    qualified = all(
        all(v <= 1e-10 for k, v in item.items() if k.endswith("_relative"))
        and min(v["relative"] for v in item["nonzero_direction_finite_differences"]) <= 1e-5
        for item in checks
    )
    return dict(
        implementation_qualified=qualified, original_action_and_vjp_paired=qualified,
        bound_complete_boundary_sha256=hashlib.sha256(boundary_bytes).hexdigest(),
        bound_complete_boundary_snapshot_path=str(snapshot), checks=checks,
        stage_elapsed_seconds=perf_counter() - start,
        reference_loaded=False, global_Maxwell_factor_count=0, global_Gram_factor_count=0,
        small_Q_inner_product_role="cached Q*Q only; no inverse or factor; not FE Gram",
        original_default_unchanged=True,
    )
