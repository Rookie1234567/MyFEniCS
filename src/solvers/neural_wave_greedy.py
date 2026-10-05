"""Residual-driven continuous wave learning and equally capable fixed control.

No reference, Gram inverse, full FE inverse, teacher or legacy NN is loaded.
Continuous q uses the envelope derivative of an exact tiny amplitude SVD.
"""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from time import monotonic

import numpy as np
from scipy.optimize import minimize

from src.solvers.neural_wave_moments import Patch, WaveMoments
from src.solvers.neural_wave_subspace import WaveSubspace, optimal_amplitudes


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:

        def convert(item):
            if isinstance(item, complex):
                return dict(real=item.real, imag=item.imag)
            if hasattr(item, "tolist"):
                return item.tolist()
            raise TypeError(type(item).__name__)

        json.dump(value, stream, indent=2, allow_nan=False, default=convert)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_npz(path, **arrays):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def patch_inventory(geometry, level):
    bounds = np.asarray(geometry["bounds_nm"], dtype=float)
    counts = [(2, 2, 2), (4, 3, 4), tuple(geometry["cells"])][level]
    axes = [
        np.linspace(a, b, count + 1)
        for (a, b), count in zip(bounds, counts, strict=True)
    ]
    radius = tuple((bounds[:, 1] - bounds[:, 0]) / np.asarray(counts))
    return [
        Patch(tuple(point), radius, level)
        for point in np.array(np.meshgrid(*axes, indexing="ij")).reshape(3, -1).T
    ]


def direction_dictionary(k0, resolution):
    golden = np.pi * (3 - np.sqrt(5))
    index = np.arange(resolution)
    z = 1 - 2 * (index + 0.5) / resolution
    radius = np.sqrt(1 - z * z)
    sphere = np.column_stack(
        (radius * np.cos(golden * index), radius * np.sin(golden * index), z)
    )
    inc = np.array([np.cos(np.deg2rad(1)), 0, -np.sin(np.deg2rad(1))])
    fixed = np.vstack((inc, inc * np.array([1, 1, -1]), np.eye(3), -np.eye(3)))
    # Zero and fixed 0.5/1/2/4 k0 magnitudes, identical for the two routes.
    return np.vstack(
        (
            np.zeros((1, 3)),
            *(
                k0 * scale * np.vstack((fixed, sphere))
                for scale in (0.5, 1.0, 2.0, 4.0)
            ),
        )
    )


def select_patch(patches, moments, residual, iteration):
    # Deterministic native residual energy; no reference or inverse direction.
    scores = []
    for patch in patches:
        rows = moments.rows[moments.cells(patch)].ravel()
        rows = rows[rows >= 0]
        scores.append(float(np.vdot(residual[rows], residual[rows]).real))
    order = np.argsort(-np.asarray(scores), kind="stable")
    return patches[int(order[iteration % min(8, len(order))])]


class BasisStore:
    """Append-only column chunks, then atomic complete-boundary publication."""

    def __init__(self, directory, binding):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.binding = binding
        self.chunks = []

    def commit(
        self, subspace, model, iteration, event, rng, deadline, algorithm_state=None
    ):
        i = subspace.m - 1
        chunk = self.directory / f"basis_{i:05d}.npz"
        if chunk.exists():
            if any(entry["path"] == chunk.name for entry in self.chunks):
                raise ValueError("IMMUTABLE_BASIS_CHUNK_ALREADY_EXISTS")
            # Preserve an orphan trial from interruption before publication.
            # A recovery appends a new version, never overwrites the raw trial.
            chunk = (
                self.directory / f"basis_{i:05d}_recovery_{int(monotonic() * 1e6)}.npz"
            )
        atomic_npz(
            chunk,
            u=subspace.U[:, i],
            q=subspace.Q[:, i],
            R_column=subspace.R[: subspace.m, i],
            wave_q=np.asarray(model["q"]),
            amplitude_real=np.asarray(model["p"]).real,
            amplitude_imag=np.asarray(model["p"]).imag,
            center=np.asarray(model["patch"].center),
            radius=np.asarray(model["patch"].radius),
            scale=np.asarray(event["scale"]),
        )
        self.chunks.append(
            dict(
                path=chunk.name,
                sha256=sha(chunk),
                source_sha=self.binding["source_sha"],
            )
        )
        state = self.directory / f"state_{i:05d}.npz"
        if state.exists():
            state = (
                self.directory / f"state_{i:05d}_recovery_{int(monotonic() * 1e6)}.npz"
            )
        atomic_npz(state, c=subspace.c, r=subspace.r, a=subspace.a)
        current = self.directory / "committed.json"
        if current.exists():
            atomic_json(
                self.directory / "previous_committed.json",
                json.loads(current.read_text()),
            )
        value = dict(
            schema="neural-wave.complete-boundary.v1",
            binding=self.binding,
            chunks=self.chunks,
            state=dict(path=state.name, sha256=sha(state)),
            columns=subspace.m,
            iteration=iteration,
            patch_level=model["patch"].level,
            rng_state=rng.bit_generator.state,
            remaining_seconds=deadline - monotonic(),
            event=event,
            committed=True,
            reference_used_for_training=False,
            optimizer_state="module frozen; next module starts fresh by design",
        )
        value["algorithm_state"] = algorithm_state or {}
        atomic_json(current, value)
        # Reopen all boundary metadata and the newly written arrays before audit.
        reread = json.loads(current.read_text())
        if (
            reread["state"]["sha256"] != sha(state)
            or sha(chunk) != self.chunks[-1]["sha256"]
        ):
            raise ValueError("ATOMIC_BOUNDARY_REOPEN_FAILED")
        return value

    def restore(self, subspace, rng):
        path = self.directory / "committed.json"
        if not path.exists():
            return None
        value = json.loads(path.read_text())
        # Source may change after an explicitly tested repair; mathematical
        # input identity and the fixed original deadline never change implicitly.
        for key in ("route", "design_sha256", "native_sha256", "moments_sha256"):
            if key in self.binding and value["binding"].get(key) != self.binding[key]:
                raise ValueError("RECOVERY_BINDING_MISMATCH: " + key)
        count = value["columns"]
        if count > subspace.capacity or len(value["chunks"]) != count:
            raise ValueError("RECOVERY_COLUMN_COVERAGE_CORRUPT")
        for i, entry in enumerate(value["chunks"]):
            file = self.directory / entry["path"]
            if sha(file) != entry["sha256"]:
                raise ValueError("RECOVERY_BASIS_HASH_FAILED")
            with np.load(file, allow_pickle=False) as arrays:
                subspace.U[:, i] = arrays["u"]
                subspace.Q[:, i] = arrays["q"]
                subspace.R[: i + 1, i] = arrays["R_column"]
        state = self.directory / value["state"]["path"]
        if sha(state) != value["state"]["sha256"]:
            raise ValueError("RECOVERY_STATE_HASH_FAILED")
        with np.load(state, allow_pickle=False) as arrays:
            subspace.a, subspace.c, subspace.r = (
                np.array(arrays[k]) for k in ("a", "c", "r")
            )
        subspace.m = count
        if (
            np.linalg.norm(
                subspace.action.f - subspace.action.apply(subspace.c) - subspace.r
            )
            > 1e-10 * subspace.action.bnorm
        ):
            raise ValueError("RECOVERY_COMPLETE_ORIGINAL_RESIDUAL_FAILED")
        if np.linalg.norm(
            subspace.U[:, :count] @ subspace.a - subspace.c
        ) > 1e-10 * max(np.linalg.norm(subspace.c), 1e-30):
            raise ValueError("RECOVERY_COEFFICIENT_RECONSTRUCTION_FAILED")
        rng.bit_generator.state = value["rng_state"]
        self.chunks = value["chunks"]
        return value


def variable_projection(action, subspace, moments, patch, q, *, gradient, local=None, projector=None):
    columns = moments.columns(patch, q)
    p, z, record = optimal_amplitudes(
        action, subspace, columns,
        applied_columns=local.columns(columns) if local is not None else None,
        projector=projector,
    )
    amplitude = p.reshape(-1, 3)
    score = record["score"]
    if not gradient:
        return score, amplitude, columns @ p, record, None
    # Envelope derivative of ||r-Zp||^2; p is the tiny SVD minimizer.
    fallback = record["original_two_pass_rounding_fallback"]
    projected = (
        subspace.project(subspace.r - z) if projector is None or fallback
        else projector.project(subspace.r - z)
    )
    cotangent = (
        action.apply(projected, adjoint=True)
        if local is None or fallback else local.adjoint(projected)
    )
    gq, _ = moments.vjp(patch, q, amplitude, cotangent)
    gq *= 2 / float(np.vdot(action.f, action.f).real)
    return score, amplitude, columns @ p, record, gq


def run_greedy(action, packet, design, artifact, binding, deadline, marker):
    learned = binding["route"] == "LEARNED_WAVE_GREEDY"
    strategy = design["strategy"]
    capacity = strategy["max_columns"]
    n = action.size
    bytes_plan = 2 * 16 * n * capacity + 3 * 16 * capacity**2 + 2 * 2**30
    if bytes_plan > 12 * 2**30:
        raise ValueError("AUTHORIZED_CAPACITY_PLANNING_LINE_EXCEEDED")
    moments = WaveMoments(packet, batch=8)
    local_actions = {}
    projection_costs = dict(build_s=0.0, project_s=0.0, calls=0, stable_fallbacks=0)
    space = WaveSubspace(action, capacity)
    store = BasisStore(Path(artifact) / "basis", binding)
    rng = np.random.default_rng(strategy["seed"])
    level, width, resolution_index, stagnant = 0, 1, 0, 0
    iteration, failures, learning_updates = 0, 0, 0
    primitive_history_complete = True
    previous = store.restore(space, rng)
    if previous:
        iteration = previous["iteration"]
        saved = previous["algorithm_state"]
        primitive_history_complete = saved.get("primitive_history_complete", False)
        level, width, resolution_index, stagnant = (
            saved[k] for k in ("level", "width", "resolution_index", "stagnant")
        )
        failures, learning_updates = saved["failures"], saved["learning_updates"]
        prior_costs = saved.get("cost_state")
        if prior_costs:
            # Restoration has already checked the complete original residual.
            # Retain that fresh cost as well as the previous measured counters.
            for key in action.counts:
                action.counts[key] += prior_costs["action_counts"][key]
                action.costs[key] += prior_costs["action_seconds"][key]
            moments.counts.update(prior_costs["moment_counts"])
            moments.seconds.update(prior_costs["moment_seconds"])
            space.seconds.update(prior_costs["qr_seconds"])
            projection_costs.update(prior_costs.get("projection_reuse", {}))
        marker(
            "complete_boundary_recovered",
            dict(
                columns=space.m,
                iteration=iteration,
                prior_source=previous["binding"]["source_sha"],
            ),
        )
    history = Path(artifact) / "basis_growth.jsonl"
    stop = None
    while space.m < capacity:
        comparison = Path(artifact) / "common_comparison_boundary.json"
        if (
            not comparison.exists()
            and monotonic() - binding["route_origin_monotonic"]
            >= strategy["common_comparison_seconds"]
        ):
            # This is a persisted work node to give the other route its common
            # budget, not numerical completion or a review/handoff boundary.
            atomic_json(
                comparison,
                dict(
                    columns=space.m,
                    native_relative=float(np.linalg.norm(space.r) / action.bnorm),
                    elapsed_seconds=monotonic() - binding["route_origin_monotonic"],
                    source_sha=binding["source_sha"],
                    continuation_allowed_within_original_campaign=True,
                ),
            )
            stop = "COMMON_COST_WORK_NODE_FROZEN_NOT_FINAL"
            break
        if monotonic() > deadline - 600:
            stop = "CAMPAIGN_OR_ROUTE_BUDGET_SAVE_RESERVE"
            break
        norm_before = float(np.linalg.norm(space.r))
        if norm_before / action.bnorm <= strategy["native_target"]:
            stop = "NATIVE_TARGET_REACHED_PENDING_INDEPENDENT_GATES"
            break
        # Support grows even when small but measurable descent persists.
        level = max(level, 1 if space.m >= 32 else 0, 2 if space.m >= 128 else 0)
        width = max(
            width,
            2 if space.m >= 256 else 1,
            4 if space.m >= 1024 else 1,
            8 if space.m >= 2048 else 1,
        )
        patch = select_patch(
            patch_inventory(design["model"]["geometry"], level),
            moments,
            space.r,
            iteration,
        )
        local = None
        projector = None
        if binding.get("exact_local_input_support_reuse", False):
            from src.solvers.neural_wave_local_action import LocalWaveAction

            if patch not in local_actions:
                support = moments.rows[moments.cells(patch)].ravel()
                local_actions[patch] = LocalWaveAction(action, support[support >= 0])
                if sum(x.retained_bytes for x in local_actions.values()) > 2 * 2**30:
                    raise MemoryError("LOCAL_NUMERIC_CACHE_AUTHORIZED_2GIB_EXCEEDED")
            local = local_actions[patch]
        if binding.get("exact_two_pass_projection_reuse", False):
            from src.solvers.neural_wave_projection import ResidualProjectionCache

            projector = ResidualProjectionCache(
                space, local.output_rows,
                additional_cache_bytes=sum(x.retained_bytes for x in local_actions.values()),
            )
            projection_costs["build_s"] += projector.seconds["build"]
            projector_charged = dict(project_s=0.0, calls=0, stable_fallbacks=0)

        def charge_projection():
            if projector is None:
                return
            current = dict(
                project_s=projector.seconds["project"],
                calls=projector.counts["project"],
                stable_fallbacks=projector.counts["explicit_two_pass_fallback"],
            )
            for key, value in current.items():
                projection_costs[key] += value - projector_charged[key]
                projector_charged[key] = value
        resolution = strategy["direction_resolutions"][resolution_index]
        dictionary = direction_dictionary(
            2 * np.pi / design["model"]["wavelength_nm"], resolution
        )
        candidates = []
        for seed_number in range(strategy["screen_seeds"]):
            offset = (iteration * strategy["screen_seeds"] + seed_number) % len(
                dictionary
            )
            q = dictionary[(offset + np.arange(width) * 7) % len(dictionary)].copy()
            try:
                value = variable_projection(
                    action, space, moments, patch, q, gradient=False, local=local, projector=projector
                )
                candidates.append((value[0], q, value))
            except ValueError as error:
                if str(error) != "DEGENERATE_NEW_DIRECTION":
                    raise
                failures += 1
        iteration += 1
        # Deterministic local refinement receives exactly the same opportunity
        # on both routes. It is additional to the physical/spherical dictionary.
        if candidates:
            _, seed_q, _ = max(candidates, key=lambda x: x[0])
            step = (
                strategy["local_refinement_steps_k0"][resolution_index]
                * 2
                * np.pi
                / design["model"]["wavelength_nm"]
            )
            for axis in range(3):
                for sign in (-1, 1):
                    refined = seed_q.copy()
                    refined[:, axis] += sign * step
                    bound = (
                        strategy["q_component_bound_k0"]
                        * 2
                        * np.pi
                        / design["model"]["wavelength_nm"]
                    )
                    refined = np.clip(refined, -bound, bound)
                    try:
                        value = variable_projection(
                            action, space, moments, patch, refined, gradient=False, local=local, projector=projector
                        )
                        candidates.append((value[0], refined, value))
                    except ValueError as error:
                        if str(error) != "DEGENERATE_NEW_DIRECTION":
                            raise
        if not candidates:
            charge_projection()
            stagnant += 1
        else:
            _, q0, best = max(candidates, key=lambda x: x[0])
            initial_q = q0.copy()
            initial_p = best[1].copy()
            q = q0
            optimize_record = dict(executed=False, function_calls=0)
            if learned:
                bound = (
                    strategy["q_component_bound_k0"]
                    * 2
                    * np.pi
                    / design["model"]["wavelength_nm"]
                )
                calls = []
                p_seed = (
                    np.tile(np.array([0.1 + 0.05j, 1.0, -0.05 + 0.1j]), (width, 1))
                    / width
                )
                seed_c = moments.forward(patch, q, p_seed)
                seed_action = (
                    action.apply(seed_c) if local is None
                    else local.columns(seed_c[:, None])[:, 0]
                )
                seed_z = (
                    space.project(seed_action) if projector is None
                    else projector.project(seed_action, supported=True)
                )
                projected_seed = (
                    space.project(seed_z - space.r) if projector is None
                    else projector.project(seed_z - space.r)
                )
                _, gp = moments.vjp(
                    patch,
                    q,
                    p_seed,
                    2 * (
                        action.apply(projected_seed, adjoint=True)
                        if local is None else local.adjoint(projected_seed)
                    ),
                )
                amplitude_learning = dict(
                    initial_seed_real=p_seed.real.tolist(),
                    initial_seed_imag=p_seed.imag.tolist(),
                    initial_gradient_norm=float(np.linalg.norm(gp) / action.bnorm**2),
                    update_norm=float(np.linalg.norm(initial_p - p_seed)),
                    method="tiny amplitude SVD then variable projection",
                    gradient_objective="||r-P A c_seed||^2 / ||f||^2 before the exact tiny amplitude solve",
                )

                def objective(flat):
                    if monotonic() >= deadline - 600:
                        raise TimeoutError("MODULE_SAVE_RESERVE")
                    value = variable_projection(
                        action,
                        space,
                        moments,
                        patch,
                        flat.reshape(width, 3),
                        gradient=True,
                        local=local,
                        projector=projector,
                    )
                    calls.append(
                        dict(
                            score=value[0],
                            gradient_norm=float(np.linalg.norm(value[4])),
                        )
                    )
                    return -value[0] / action.bnorm**2, -value[4].ravel()

                try:
                    result = minimize(
                        objective,
                        q0.ravel(),
                        jac=True,
                        method="L-BFGS-B",
                        bounds=[(-bound, bound)] * (3 * width),
                        options=dict(
                            maxiter=strategy["module_max_iterations"],
                            maxfun=strategy["module_max_evaluations"],
                            maxls=12,
                            ftol=1e-12,
                            gtol=1e-10,
                            maxcor=10,
                        ),
                    )
                    trial_q = result.x.reshape(width, 3)
                    trial = variable_projection(
                        action, space, moments, patch, trial_q, gradient=False, local=local, projector=projector
                    )
                    if trial[0] >= best[0]:
                        q, best = trial_q, trial
                    optimize_record = dict(
                        executed=True,
                        function_calls=len(calls),
                        initial_gradient_norm=calls[0]["gradient_norm"],
                        final_gradient_norm=calls[-1]["gradient_norm"],
                        q_update_norm=float(np.linalg.norm(q - initial_q)),
                        amplitude_update_norm=float(
                            np.linalg.norm(best[1] - initial_p)
                        ),
                        scipy_status=int(result.status),
                        messages=str(result.message),
                    )
                    optimize_record["amplitude_learning"] = amplitude_learning
                    learning_updates += int(optimize_record["q_update_norm"] > 1e-12)
                except TimeoutError:
                    charge_projection()
                    stop = "MODULE_INTERRUPTED_AT_SAVE_RESERVE"
                    break
            charge_projection()
            # Optimization uses the qualified sparse maps; the accepted field
            # always uses the original complete point-value matrix and geometry.
            from src.solvers.neural_wave_reconstruction import pointwise_moments

            actual_column = pointwise_moments(
                packet,
                lambda x: patch.window(x)[:, None]
                * (np.exp(1j * (x - np.array(patch.center)) @ q.T) @ best[1]),
                zero_outside_patch=patch,
            )
            mapping_pair = float(
                np.linalg.norm(actual_column - best[2])
                / max(np.linalg.norm(actual_column), 1e-30)
            )
            event = (
                space.add(actual_column)
                if mapping_pair <= 1e-10
                else dict(accepted=False, reason="TENSOR_FULL_MAPPING_PAIR_FAILED")
            )
            event["tensor_full_mapping_relative"] = mapping_pair
            event.update(
                module=iteration,
                route=binding["route"],
                neurons=width,
                patch=asdict(patch),
                seed_q=initial_q.tolist(),
                learned_q=q.tolist(),
                training=optimize_record,
                score=best[0],
                amplitude_norm=float(np.linalg.norm(best[1])),
                elapsed_seconds=monotonic() - binding["route_origin_monotonic"],
            )
            if event["accepted"]:
                event["predicted_actual_decrease_load_scaled_absolute"] = (
                    abs(best[0] - event["actual_energy_decrease"]) / action.bnorm**2
                )
            if event["accepted"]:
                model = dict(patch=patch, q=q, p=best[1])
                stagnant = (
                    stagnant + 1
                    if norm_before - np.linalg.norm(space.r)
                    <= 64 * np.finfo(float).eps * action.bnorm
                    else 0
                )
                # Compute the complete native/augmented audit before saving;
                # the public committed row is still published only afterwards.
                event["audit"] = action.audit(space.c)
                store.commit(
                    space,
                    model,
                    iteration,
                    event,
                    rng,
                    deadline,
                    dict(
                        level=level,
                        width=width,
                        resolution_index=resolution_index,
                        stagnant=stagnant,
                        failures=failures,
                        learning_updates=learning_updates,
                        primitive_history_complete=primitive_history_complete,
                        cost_state=dict(
                            action_counts=action.counts.copy(),
                            action_seconds=action.costs.copy(),
                            moment_counts=moments.counts.copy(),
                            moment_seconds=moments.seconds.copy(),
                            qr_seconds=space.seconds.copy(),
                            projection_reuse=projection_costs.copy(),
                        ),
                    ),
                )
                # Publishing the audit follows durable commit, never precedes it.
                with history.open("a") as stream:
                    stream.write(json.dumps(event) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                marker("wave_committed", event)
                if space.m in strategy["capacity_milestones"]:
                    rank = space.rank_audit()
                    atomic_json(Path(artifact) / f"rank_{space.m}.json", rank)
            else:
                stagnant += 1
                marker("wave_rejected", event)
        if stagnant >= 8:
            if resolution_index < len(strategy["direction_resolutions"]) - 1:
                resolution_index += 1
            elif width < 8:
                width *= 2
                resolution_index = 0
            elif level < 2:
                level += 1
                resolution_index = 0
            else:
                # Retain rejected module costs; proceed with new deterministic seeds.
                failures += 1
            stagnant = 0
    if stop is None:
        stop = "AUTHORIZED_COLUMN_CAPACITY_EXHAUSTED"
    for name in ("final_state.npz", "result.json"):
        old = Path(artifact) / name
        if old.exists():
            os.replace(
                old,
                old.with_name(
                    old.stem + f"_previous_{int(monotonic() * 1e6)}" + old.suffix
                ),
            )
    atomic_npz(Path(artifact) / "final_state.npz", c=space.c, r=space.r, a=space.a)
    result = dict(
        status=stop,
        route=binding["route"],
        columns=space.m,
        modules=iteration,
        learned_direction_updates=learning_updates,
        degenerate_modules=failures,
        audit=action.audit(space.c),
        reference_used_for_training=False,
        features_reference_exposed=False,
        pde_only_solve=True,
        benchmark_previously_seen=True,
        production_initialization_allowed=False,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        action_counts=action.counts,
        action_seconds=action.costs,
        moment_counts=moments.counts,
        moment_seconds=moments.seconds,
        qr_seconds=space.seconds,
        capacity_plan_bytes=bytes_plan,
        numerical_gate="PENDING_INDEPENDENT_FULL_FIELD_CHECKER",
        exact_local_input_support_reuse=binding.get("exact_local_input_support_reuse", False),
        local_numeric_cache_bytes=sum(x.retained_bytes for x in local_actions.values()),
        local_action_costs=[dict(counts=x.counts, seconds=x.seconds) for x in local_actions.values()],
        inherited_primitive_counters_retained=primitive_history_complete,
        exact_two_pass_projection_reuse=binding.get("exact_two_pass_projection_reuse", False),
        projection_reuse_costs=projection_costs,
    )
    atomic_json(Path(artifact) / "result.json", result)
    return result
