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


def validate_scalar_boundary(value, current, marker):
    """Accept a scoring receipt only for exactly the same committed arrays.

    The original resume ordering could save a timed metadata boundary before
    consuming its scalar receipt. Recover that specific case by proving exact
    equality, without repeating scoring or changing any optimization state.
    """
    if value["boundary_sha256"] == sha(current):
        return
    previous = current.parent / "previous_committed.json"
    if not previous.exists() or sha(previous) != value["boundary_sha256"]:
        raise ValueError("VALIDATION_NOT_FOR_CURRENT_COMMITTED_STATE")
    now, old = (json.loads(p.read_text()) for p in (current, previous))
    if (
        now["event"].get("kind") != "fixed_time_node"
        or old["event"].get("kind") != "scalar_validation_boundary"
        or old["event"].get("node") != value["node"]
        or any(now[k] != old[k] for k in
               ("binding", "chunks", "qr_replay", "columns", "iteration"))
        or any(now["algorithm_state"][k] != old["algorithm_state"][k]
               for k in ("visits", "accepted", "trials", "nonzero_q_updates",
                         "queue", "cursor", "round_id", "rng_state",
                         "validated_nodes"))
    ):
        raise ValueError("VALIDATION_STATE_CHANGED")
    for entry in (now["state"], old["state"]):
        if sha(entry["path"]) != entry["sha256"]:
            raise ValueError("VALIDATION_ARRAY_HASH_FAILED")
    with np.load(now["state"]["path"], allow_pickle=False) as a, np.load(
        old["state"]["path"], allow_pickle=False
    ) as b:
        if not all(np.array_equal(a[k], b[k]) for k in ("a", "c", "r", "R")):
            raise ValueError("VALIDATION_NUMERICAL_STATE_CHANGED")
    marker("scalar_receipt_metadata_boundary_pair", dict(
        scoring_boundary_sha256=value["boundary_sha256"],
        current_boundary_sha256=sha(current),
        a_c_r_R_bitwise_equal=True,
        q_T_chunks_and_QR_replay_equal=True,
        optimization_state_unchanged=True,
        failed_attempt_cost_retained=True,
    ))


def run_backfit(
    action, packet, space, blocks, anchor, design, manifest, artifact, marker
):
    route = manifest["spec"]["role"]
    complex_wave = design.get("campaign_version") == 34
    kind = "learned" if route in ("LEARNED_VARPRO_BACKFIT",
                                  "LEARNED_COMPLEX_WAVE_BACKFIT") else "deterministic"
    origin = manifest["route_origin_monotonic"]
    route_cap = 14400 if complex_wave else 10800
    trial_cap = 3072 if complex_wave else 2048
    deadline = min(manifest["worker_stop_monotonic"], origin + route_cap - 150)
    binding = dict(
        route=route,
        source_sha=manifest["source_sha"],
        design_sha256=manifest["design_sha256"],
        native_sha256=design["files"]["native"]["sha256"],
        moments_sha256=design["files"]["moments_q30"]["sha256"],
        anchor_sha256=design["anchor"]["boundary_sha256"],
        route_origin_monotonic=origin,
    )
    if complex_wave:
        binding["wave_representation"] = "oscillation+decay.v1"
    store = BackfitStore(artifact / "basis", binding, anchor)
    resumed = restore_backfit(space, blocks, store.directory, binding)
    rng = np.random.default_rng(4213401 if complex_wave else 4213301)
    state = (
        json.loads(json.dumps(resumed["algorithm_state"]))
        if resumed
        else dict(
            visits=0,
            accepted=0,
            nonzero_q_updates=0,
            nonzero_decay_updates=0,
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
        state.setdefault("nonzero_decay_updates", 0)
        rng.bit_generator.state = state["rng_state"]
        for k, v in state["action_counts"].items():
            action.counts[k] += v
            action.costs[k] += state["action_seconds"][k]
    if complex_wave:
        from src.solvers.neural_wave_decay import (
            ComplexActivityMoments, block_parameters, coordinate_contract,
            normalized_complex_gradients, physical_decay_seeds,
        )
        moments = ComplexActivityMoments(packet, 8)
    else:
        moments = WaveMoments(packet, 8)
    if resumed and complex_wave:
        for key, value in state.get("moments_counts", {}).items():
            moments.counts[key] += value
        for key, value in state.get("moments_seconds", {}).items():
            moments.seconds[key] += value
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
    while state["visits"] < 64 and state["trials"] < trial_cap:
        if monotonic() >= deadline:
            stop = "ROUTE_SAVE_RESERVE_REACHED"
            break
        elapsed = monotonic() - origin
        nodes = ((1, 16, 3600), (2, 32, 7200))
        if complex_wave:
            nodes = [(1, 32, 7200)]
            if "confirmation_visit" in state:
                nodes.append((2, state["confirmation_visit"], state["confirmation_time"]))
        due = [
            n
            for n, v, t in nodes
            if n not in state["validated_nodes"]
            and (state["visits"] >= v or elapsed >= t)
        ]
        if due:
            node = due[0]
            scalar = artifact / f"validation_scalars_{node}.json"
            current = store.directory / "committed.json"
            if scalar.exists():
                value = json.loads(scalar.read_text())
                validate_scalar_boundary(value, current, marker)
                state["validated_nodes"].append(node)
                if complex_wave and node == 1 and value["ineffective"]:
                    state["confirmation_visit"] = state["visits"] + 8
                    state["confirmation_time"] = elapsed + 1800
                if not value["continuation_allowed"]:
                    stop = ("COMPLEX_WAVE_NO_USEFUL_PROGRESS" if complex_wave
                            else "BACKFIT_NO_USEFUL_PROGRESS")
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
        # Consume matching validation before publishing a new timed boundary.
        for node in (1800, 3600, 7200, 10800, *([14400] if complex_wave else [])):
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
        if np.linalg.norm(space.r) / action.bnorm <= manifest["spec"]["native_target"]:
            stop = "ORIGINAL_RESIDUAL_TARGET_REACHED_PENDING_JOINT_GATE"
            break
        if not state["queue"]:
            start = perf_counter()
            scores = (normalized_complex_gradients(action, moments, space, blocks, k0)
                      if complex_wave else normalized_block_gradients(
                          action, moments, space, blocks, k0))
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
                    all_parameter_decay_groups_scored=complex_wave,
                    shared_AH_count=1,
                ),
            )
        block_id = state["queue"].pop(0)
        round_for_visit = state["round_id"]
        if not state["queue"]:
            state["round_id"] += 1
        block = blocks[block_id]
        before_native = float(np.linalg.norm(space.r) / action.bnorm)
        old_q = block_parameters(block) if complex_wave else block["wave_q"].copy()
        coordinate_options, seed_record = {}, None
        if complex_wave:
            scale, bounds, R = coordinate_contract(block, moments, k0)
            seeds, seed_record = physical_decay_seeds(
                block, moments, k0, complex(*design["decay"]["beta_si_nm_inverse"]))
            coordinate_options = dict(parameter_scale=scale, parameter_bounds=bounds,
                                      physical_seeds=seeds)
        started = perf_counter()
        visit = state["visits"]
        state["visits"] += 1
        accepted = False
        reason = None
        optimization = None
        # No whole QR rebuild is hidden here. rank-revealing inactive solve
        # and QR delete are a once-per-visit setup and are fully costed.
        F = InactiveComplement(
            action,
            space.U,
            space.Q,
            space.R,
            block["start"],
            block["stop"],
            center=(space.a, space.c),
            base_q=old_q,
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
                max_evaluations=min(48 if complex_wave else 32,
                                    trial_cap - state["trials"]),
                seed_trial=zero,
                **coordinate_options,
            )
            state["trials"] += optimization["complete_trial_calls"]
            delta = float(np.linalg.norm(best.q - old_q))
            q_delta = float(np.linalg.norm(best.q[:, :3] - old_q[:, :3])) if complex_wave else delta
            decay_delta = float(np.linalg.norm(best.q[:, 3:] - old_q[:, 3:])) if complex_wave else 0.
            if best.objective < before_native**2 / 2 and delta > 0:
                state["accepted"] += 1
                state["nonzero_q_updates"] += int(q_delta > 0)
                state["nonzero_decay_updates"] += int(decay_delta > 0)
                costs()
                event = dict(
                    kind="accepted_replacement",
                    visit=visit,
                    block_id=block_id,
                    before_native=before_native,
                    q_delta=q_delta,
                    decay_delta=decay_delta,
                    physical_seeds=seed_record,
                    native_relative=float(np.linalg.norm(best.r) / action.bnorm),
                    optimization=optimization,
                    rank=best.active_rank,
                    full_reduced_pair=best.pairing,
                    all_amplitudes_reoptimized=True,
                )
                try:
                    pair, b = accept_and_save(
                        space, blocks, block_id, F, best, store, event, state,
                        refresh_costs=costs,
                    )
                except BaseException:
                    state["accepted"] -= 1
                    state["nonzero_q_updates"] -= int(q_delta > 0)
                    state["nonzero_decay_updates"] -= int(decay_delta > 0)
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
            # A QR insertion rejection can occur AFTER a complete optimization.
            # Its already paid evaluations/iteration record must survive rollback.
            if optimization is None:
                optimization = dict(message=str(error), complete_trial_calls=0,
                                    actual_nit="NOT_RETAINED")
            else:
                optimization["commit_rejection"] = str(error)
            delta = 0.0
            q_delta, decay_delta = 0., 0.
            reason = str(error)
        finally:
            del F
        rec = dict(
            visit=visit,
            block_id=block_id,
            accepted=accepted,
            reason=reason,
            q_delta=q_delta,
            decay_delta=decay_delta,
            physical_seeds=seed_record,
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
        nonzero_decay_updates=state["nonzero_decay_updates"],
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
