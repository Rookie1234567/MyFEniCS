"""Export a safely retained resource-stop boundary; never resume optimization.

The original complete PT remains immutable. This creates only an NPZ view and
an explicit partial-run record for independent reconstruction/FE comparison.
"""

from copy import deepcopy
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.feinn_derivative_reuse import frozen_entries, load_recovery
from src.solvers.feinn_phase_training import configure, policy, install_data_guard
from src.solvers.feinn_native import load_native
from src.solvers.feinn_torch import CompleteMomentMap
from src.solvers.feinn_validation import load_moments, parameters, paired
from src.solvers.optimization_checkpoint import atomic_write
from src.solvers.neural_fe_action_packet import array_hash


def freeze_resource_boundary(design, native, qualification, artifact, marker, manifest):
    configure()
    boundary = manifest["resource_boundary"]
    original = frozen_entries()["phase_gn"]
    allowed = [
        original[k]["path"] for k in ("checkpoint", "durable_final", "checkpoint_index")
    ]
    allowed += [
        boundary[k]["path"]
        for k in (
            "checkpoint_pointer",
            "durable_final",
            "history",
            "prior_manifest",
            "prior_summary",
        )
    ]
    allowed += [
        native["files"]["native"]["path"],
        qualification["files"]["moments"]["path"],
    ]
    reads = install_data_guard(allowed, artifact, supervised=False)
    model, c, saved = load_recovery(design, original, boundary)
    mapping = CompleteMomentMap(load_moments(qualification["files"]["moments"]["path"]))
    pair = paired(mapping.forward(model), c)
    if pair["relative"] > 1e-12:
        raise ValueError("RESOURCE_BOUNDARY_NETWORK_C_MISMATCH")
    packet = load_native(native["files"]["native"]["path"])
    audit = packet.audit(c)
    pointer = json.loads(Path(boundary["checkpoint_pointer"]["path"]).read_text())[
        "current"
    ]
    meta = saved["metadata"]
    flags = policy(False)
    buffers = {n: b.detach().numpy().copy() for n, b in model.named_buffers()}
    path = artifact / "frozen_checkpoint.npz"
    atomic_write(
        path,
        lambda stream: np.savez(
            stream,
            parameters=parameters(model),
            c=c,
            source_sha=meta["source_sha"],
            export_source_sha=manifest["source_sha"],
            input_sha256=meta["input_sha256"],
            export_input_sha256=manifest["input_sha256"],
            state_kind="retained_resource_boundary",
            route=meta["route"],
            phase=True,
            durable_checkpoint_sha256=boundary["durable_final"]["sha256"],
            **buffers,
            **flags,
        ),
    )
    history = artifact / "freeze_history.jsonl"
    history.write_text(
        json.dumps(
            dict(
                kind="RESOURCE_BOUNDARY_FROZEN",
                checkpoint_sha256=boundary["durable_final"]["sha256"],
                accepted_outer=meta["accepted_outer"],
            )
        )
        + "\n"
    )
    counts = boundary["spent_counts_lower_bound"]
    jac = boundary["spent_JVP_VJP_lower_bound"]
    inherited = meta["inherited_counts"]
    inherited_jac = meta["inherited_JVP_VJP_counts"]
    old_accepted = meta["inherited_accepted_outer"]
    prefix = (
        boundary["original_V9_logical_prefix_seconds"]
        + manifest["phase_training_attempt_seconds"]
    )
    elapsed = perf_counter() - manifest["supervision_budget_origin_monotonic"]
    result = dict(
        status="RESOURCE_STOP_COMPLETE_BOUNDARY_FROZEN",
        route=meta["route"],
        phase=True,
        supervised=False,
        stop_reason="RESOURCE_WINDOW_UNAVAILABLE",
        failure=dict(
            kind="RESOURCE_WINDOW_UNAVAILABLE",
            reason="repeated system PSI stop; no third training start",
        ),
        retained_resource_export=True,
        numerical_failure_claim=False,
        normal_budget_stop_claim=False,
        counts=counts,
        JVP_VJP_counts=jac,
        inherited_counts=inherited,
        inherited_JVP_VJP_counts=inherited_jac,
        cumulative_counts={k: inherited.get(k, 0) + v for k, v in counts.items()},
        cumulative_JVP_VJP_counts={
            k: inherited_jac.get(k, 0) + v for k, v in jac.items()
        },
        inherited_accepted_outer=old_accepted,
        new_accepted_outer=meta["accepted_outer"] - old_accepted,
        cumulative_accepted_outer=meta["accepted_outer"],
        accepted_updates_this_attempt=0,
        inherited_V10_accepted_outer=meta["accepted_outer"] - old_accepted,
        new_Adam_updates=0,
        inherited_committed_Adam_updates=500,
        old_optimizer_history_loaded=True,
        scale_reestimated=False,
        consistent_optimizer_state_saved=True,
        original_PT_unmodified=True,
        final_checkpoint=pointer,
        final_c_sha256=array_hash(c),
        final_parameters_sha256=array_hash(parameters(model)),
        buffers_sha256=meta["buffers_sha256"],
        h0=meta["h0"],
        mu_final=meta["mu"],
        d_G=meta["d_G"],
        d_ref=None,
        final_audit=audit,
        initial_audit=audit,
        audits=[],
        accepted_history=[],
        PC_builds=[],
        Gram_factor=None,
        Gsolve_count=None,
        G_matvec_count=0,
        Gram_lifetime_record="NOT_RETAINED; partial setup in original stage markers; all walls charged",
        Maxwell_factor_created=False,
        global_Maxwell_matrix_created=False,
        label_identity=None,
        training_data_read_whitelist=allowed,
        actual_artifact_reads=sorted(set(reads)),
        native_action_counts=packet.counts,
        native_action_costs=packet.costs,
        JVP_VJP_costs=dict(
            scope="NOT_RETAINED for complete failed lifetime; saved-boundary lower bounds",
            saved_boundary_lower_bound=deepcopy(meta["derivative_cache"]["costs"]),
        ),
        nested_timers={},
        derivative_cache=deepcopy(meta["derivative_cache"]),
        budget_frontier=deepcopy(meta["budget_frontier"]),
        initialization_identity=original,
        fault_recovery=boundary,
        initialization_kind="OWN_V10_RESOURCE_BOUNDARY_EXPORT_NO_TRAINING",
        inherited_prefix_seconds=prefix,
        inherited_prior_attempt_seconds=manifest["phase_training_attempt_seconds"],
        launcher_charged_seconds=elapsed,
        logical_path_seconds=prefix + elapsed,
        saved_boundary_logical_path_seconds=meta["logical_path_seconds"],
        parameter_origin_source_sha=meta["source_sha"],
        export_source_sha=manifest["source_sha"],
        parameters_to_saved_c=pair,
        frozen_state_selection=boundary["selection"],
        **flags,
    )
    marker(
        "resource_boundary_frozen",
        dict(
            accepted_outer=meta["accepted_outer"],
            native=audit["native_relative"],
            parameter_source_sha=meta["source_sha"],
            no_training=True,
            no_factor=True,
        ),
    )
    return result, dict(
        checkpoint=path,
        durable_final=Path(boundary["durable_final"]["path"]),
        checkpoint_index=Path(boundary["checkpoint_pointer"]["path"]),
        history=history,
    )
