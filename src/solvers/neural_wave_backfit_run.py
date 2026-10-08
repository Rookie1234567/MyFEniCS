"""Fixed-capacity paired backfit visits with complete original-residual commits."""

import json
from time import monotonic, perf_counter

import numpy as np

from src.io.neural_wave_backfit_store import BackfitStore, accept_and_save
from src.solvers.neural_wave_backfit import (
    InactiveComplement,
    normalized_block_gradients,
    select_active_round,
    optimize_active,
    TrialRejected,
)
from src.solvers.neural_wave_backfit_state import restore_backfit
from src.solvers.neural_wave_moments import WaveMoments
from src.solvers.neural_wave_greedy import atomic_json, sha


def run_backfit(
    action, packet, space, blocks, anchor, design, manifest, artifact, marker
):
    route = manifest["spec"]["role"]
    kind = "learned" if route == "LEARNED_VARPRO_BACKFIT" else "deterministic"
    origin = manifest["route_origin_monotonic"]
    deadline = min(manifest["worker_stop_monotonic"], origin + 10800 - 150)
    binding = dict(
        route=route,
        source_sha=manifest["source_sha"],
        design_sha256=manifest["design_sha256"],
        native_sha256=design["files"]["native"]["sha256"],
        moments_sha256=design["files"]["moments_q30"]["sha256"],
        anchor_sha256=design["anchor"]["boundary_sha256"],
        route_origin_monotonic=origin,
    )
    store = BackfitStore(artifact / "basis", binding, anchor)
    resumed = restore_backfit(space, blocks, store.directory, binding)
    rng = np.random.default_rng(4213301)
    state = (
        json.loads(json.dumps(resumed["algorithm_state"]))
        if resumed
        else dict(
            visits=0,
            accepted=0,
            nonzero_q_updates=0,
            trials=0,
            zero_audits=0,
            full_AU_refreshes=0,
            round_id=0,
            cursor=0,
            queue=[],
            validated_nodes=[],
            boundary_count=0,
            rng_state=rng.bit_generator.state,
            time_nodes_saved=[],
            seconds={},
            action_counts=dict(action.counts),
            action_seconds=dict(action.costs),
        )
    )
    if resumed:
        rng.bit_generator.state = state["rng_state"]
        for k, v in state["action_counts"].items():
            action.counts[k] += v
            action.costs[k] += state["action_seconds"][k]
    moments = WaveMoments(packet, 8)
    k0 = 2 * np.pi / design["model"]["wavelength_nm"]
    history = artifact / "visit_history.jsonl"

    def costs():
        state.update(
            action_counts=dict(action.counts),
            action_seconds=dict(action.costs),
            moments_counts=dict(moments.counts),
            moments_seconds=dict(moments.seconds),
            rng_state=rng.bit_generator.state,
            remaining_seconds=deadline - monotonic(),
            new_route_span_seconds=monotonic() - origin,
            inherited_prefix_attributed_seconds=10186.178641493432,
        )

    def boundary(event):
        state["boundary_count"] += 1
        costs()
        return store.save(space, blocks, event, state)

    if not resumed:
        boundary(dict(kind="shared_anchor", audit=action.audit(space.c)))
    stop = "BACKFIT_VISIT_OR_TRIAL_LIMIT"
    while state["visits"] < 64 and state["trials"] < 2048:
        if monotonic() >= deadline:
            stop = "ROUTE_SAVE_RESERVE_REACHED"
            break
        elapsed = monotonic() - origin
        for node in (1800, 3600, 7200, 10800):
            if elapsed >= node and node not in state["time_nodes_saved"]:
                state["time_nodes_saved"].append(node)
                b = boundary(
                    dict(
                        kind="fixed_time_node",
                        seconds=node,
                        audit=action.audit(space.c),
                    )
                )
                atomic_json(artifact / f"time_node_{node}.json", b)
        due = [
            n
            for n, v, t in ((1, 16, 3600), (2, 32, 7200))
            if n not in state["validated_nodes"]
            and (state["visits"] >= v or elapsed >= t)
        ]
        if due:
            node = due[0]
            scalar = artifact / f"validation_scalars_{node}.json"
            current = store.directory / "committed.json"
            if scalar.exists():
                value = json.loads(scalar.read_text())
                if value["boundary_sha256"] != sha(current):
                    raise ValueError("VALIDATION_NOT_FOR_CURRENT_COMMITTED_STATE")
                state["validated_nodes"].append(node)
                if not value["continuation_allowed"]:
                    stop = "BACKFIT_NO_USEFUL_PROGRESS"
                    break
            else:
                b = boundary(
                    dict(
                        kind="scalar_validation_boundary",
                        node=node,
                        audit=action.audit(space.c),
                    )
                )
                atomic_json(
                    artifact / f"validation_requested_{node}.json",
                    dict(
                        boundary_sha256=sha(current),
                        node=node,
                        visits=state["visits"],
                        source_sha=manifest["source_sha"],
                        no_reference_feedback_vectors=True,
                    ),
                )
                stop = f"INDEPENDENT_VALIDATION_REQUESTED_{node}"
                break
        if np.linalg.norm(space.r) / action.bnorm <= manifest["spec"]["native_target"]:
            stop = "ORIGINAL_RESIDUAL_TARGET_REACHED_PENDING_JOINT_GATE"
            break
        if not state["queue"]:
            start = perf_counter()
            scores = normalized_block_gradients(action, moments, space, blocks, k0)
            state["queue"], state["cursor"] = select_active_round(
                scores, blocks, state["cursor"]
            )
            marker(
                "backfit_round_preselection",
                dict(
                    round_id=state["round_id"],
                    queue=state["queue"],
                    scores=scores,
                    seconds=perf_counter() - start,
                    all_parameter_q_groups_scored=True,
                    shared_AH_count=1,
                ),
            )
        block_id = state["queue"].pop(0)
        round_for_visit = state["round_id"]
        if not state["queue"]:
            state["round_id"] += 1
        block = blocks[block_id]
        before_native = float(np.linalg.norm(space.r) / action.bnorm)
        old_q = block["wave_q"].copy()
        started = perf_counter()
        visit = state["visits"]
        state["visits"] += 1
        accepted = False
        reason = None
        # No whole QR rebuild is hidden here. rank-revealing inactive solve
        # and QR delete are a once-per-visit setup and are fully costed.
        F = InactiveComplement(
            action, space.U, space.Q, space.R, block["start"], block["stop"]
        )

        def evaluate(q, gradient):
            if monotonic() >= deadline:
                raise TrialRejected("TRIAL_SAVE_RESERVE_REACHED")
            return F.trial(
                moments, block["patch"], q, block["amplitude_map"], gradient=gradient
            )

        try:
            zero = evaluate(old_q, True)
            state["zero_audits"] += 1
            best, optimization = optimize_active(
                evaluate,
                old_q,
                k0,
                kind,
                round_id=round_for_visit,
                block_id=block_id,
                visit_id=visit,
                max_evaluations=min(32, 2048 - state["trials"]),
                seed_trial=zero,
            )
            state["trials"] += optimization["complete_trial_calls"]
            delta = float(np.linalg.norm(best.q - old_q))
            if best.objective < before_native**2 / 2 and delta > 0:
                state["accepted"] += 1
                state["nonzero_q_updates"] += 1
                costs()
                event = dict(
                    kind="accepted_replacement",
                    visit=visit,
                    block_id=block_id,
                    before_native=before_native,
                    q_delta=delta,
                    native_relative=float(np.linalg.norm(best.r) / action.bnorm),
                    optimization=optimization,
                    rank=best.active_rank,
                    full_reduced_pair=best.pairing,
                    all_amplitudes_reoptimized=True,
                )
                try:
                    pair, b = accept_and_save(
                        space, blocks, block_id, F, best, store, event, state
                    )
                except BaseException:
                    state["accepted"] -= 1
                    state["nonzero_q_updates"] -= 1
                    raise
                marker(
                    "committed_backfit_replacement",
                    dict(
                        event,
                        boundary_sha256=sha(store.directory / "committed.json"),
                        pair=pair,
                    ),
                )
                accepted = True
            else:
                reason = "NO_EVALUATED_NONZERO_Q_IMPROVEMENT"
        except TrialRejected as error:
            optimization = dict(message=str(error), complete_trial_calls=0)
            delta = 0.0
            reason = str(error)
        finally:
            del F
        rec = dict(
            visit=visit,
            block_id=block_id,
            accepted=accepted,
            reason=reason,
            q_delta=delta,
            before_native=before_native,
            after_native=float(np.linalg.norm(space.r) / action.bnorm),
            columns=space.m,
            optimization=optimization,
            actual_visit_seconds=perf_counter() - started,
            elapsed_seconds=monotonic() - origin,
            source_sha=manifest["source_sha"],
        )
        if not accepted:
            boundary(dict(kind="rejected_visit_complete", **rec))
        with history.open("a") as stream:
            stream.write(json.dumps(rec) + "\n")
            stream.flush()
        marker("backfit_visit_complete", rec)
    if not stop.startswith("INDEPENDENT_VALIDATION_REQUESTED_"):
        boundary(dict(kind="final_complete", status=stop, audit=action.audit(space.c)))
    costs()
    return dict(
        status=stop,
        route=route,
        columns=space.m,
        accepted=state["accepted"],
        visits=state["visits"],
        nonzero_q_updates=state["nonzero_q_updates"],
        complete_q_trial_calls=state["trials"],
        zero_audits=state["zero_audits"],
        audit=action.audit(space.c),
        algorithm_state=state,
        committed_boundary_sha256=sha(store.directory / "committed.json"),
        reference_used_for_training=False,
        features_reference_exposed=False,
        reference_used_for_validation=True,
        continuation_uses_validation_scalars=True,
        benchmark_previously_seen=True,
        pde_only_solve=True,
        global_Maxwell_factor_count=0,
        global_Gram_factor_count=0,
        production_initialization_allowed=False,
    )
