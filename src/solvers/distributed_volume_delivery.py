"""Consume frozen finite interfaces and report the conditional target gate."""

import json
import os
from pathlib import Path

from benchmarks.check_boundary_witness import metric, read_arrays
from src.solvers.distributed_volume_scope import ROOT, stage, window
from src.solvers.native_recovery_packets import sha


def target_decision(
    *, finite_passed, neighbors, backend_ready, predicted_peak, exclusive_lock_verified
):
    reasons = []
    if not finite_passed:
        reasons.append("FINITE_NUMERICAL_GATE_FAILED")
    if neighbors:
        reasons.append("OTHER_HEAVY_PRESENT")
    if not exclusive_lock_verified:
        reasons.append("MACHINE_EXCLUSIVITY_NOT_VERIFIED")
    if not backend_ready:
        reasons.append("TARGET_CANONICAL_VOLUME_BACKEND_NOT_IMPLEMENTED")
    if predicted_peak is None:
        reasons.append("CONSERVATIVE_TARGET_RSS_PREDICTION_UNKNOWN")
    elif predicted_peak > 32 * 2**30:
        reasons.append("TARGET_PREDICTED_RSS_ABOVE_32_GIB")
    return {"admitted": not reasons, "reasons": reasons}


def target_gate():
    checked, checked_path = stage("CHECK")
    run = Path(os.environ["TASK042_V36_AUX_DIRECTORY"])
    baseline = json.loads((run / "resource_baseline.json").read_text())
    # This is an admission/stop record, never a target numerical launch.
    # The already observed neighbors are retained verbatim for independent review.
    decision = target_decision(
        finite_passed=checked["passed"],
        neighbors=baseline["neighbor_processes"],
        backend_ready=False,
        predicted_peak=None,
        exclusive_lock_verified=False,
    )
    return dict(
        decision,
        status="TARGET_NOT_RUN_AFTER_FINITE_GATE",
        parent={"path": str(checked_path), "sha256": sha(checked_path)},
        resource_baseline={
            "path": str(run / "resource_baseline.json"),
            "sha256": sha(run / "resource_baseline.json"),
        },
        observed_neighbors=baseline["neighbor_processes"],
        machine_lock={
            "acquired": False,
            "reason": "no target launch after failed finite numerical gate",
        },
        target_action_calls=0,
        target_LU=0,
        target_Krylov=0,
        training=0,
        clock=window.snapshot(),
    )


def deploy(folder):
    """New MPI2 process consumes A/B without constructing mesh, kernel or factor."""
    from mpi4py import MPI

    from src.solvers.distributed_entity_volume import (
        NativeDistributedAction,
        cell_transform,
    )
    from src.solvers.distributed_recovery_study import producer_store
    from src.solvers.distributed_saved_recovery import (
        SavedRecoveryConsumer,
        native_transfer,
    )
    from src.solvers.distributed_volume_study import (
        element,
        require_live_envelope,
        store,
    )
    from src.solvers.native_entity_study import save_rank

    require_live_envelope()
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        raise ValueError("frozen consumer owner directory requires actual MPI2")
    checked, _ = stage("CHECK")
    if not checked["volume_action_passed"] or not checked["recovery"]["passed"]:
        raise ValueError("untrusted finite action/recovery cannot be deployed")
    e = element()
    arow, apath = stage("VOLUME2")
    ap = arow["packets"][comm.rank]
    vector = read_arrays(ap["numeric"])
    literal = read_arrays(ap["metadata"]["parent"])
    s = store()
    classes = stage("CLASSES")[0]
    matrices = [s.read(n + "_tensor")[1]["raw"] for n in classes["class_names"]]
    actor = NativeDistributedAction(
        comm,
        literal,
        matrices,
        ap["metadata"]["class_ids"],
        e,
        ap["metadata"]["owned_rows"],
        ap["metadata"]["owned_cells"],
    )
    ax = actor.apply_original(vector["x"])
    ay = actor.apply_original_adjoint(vector["y"])
    checks = [
        dict(kind="A_consumer_original", **metric(ax, vector["forward"])),
        dict(kind="A_consumer_adjoint", **metric(ay, vector["adjoint"])),
    ]
    arrays = {
        "A_forward": ax,
        "A_adjoint": ay,
        "A_owned_global_ids": vector["owned_global_ids"],
    }
    # Release the finite A kernels before the port-coupled B consumer is built.
    del actor, matrices, literal
    brow, bpath = stage("RECOVERY2")
    bp = brow["packets"][comm.rank]
    if bp["metadata"]["live_consumer_source"] != sha(
        ROOT / "src/solvers/distributed_saved_recovery.py"
    ):
        raise ValueError("live finite consumer implementation changed")
    saved_bridge = read_arrays(bp["numeric"])
    old, _ = producer_store()
    _, literal = old.read("geometry")
    system, numbering = old.read("system")
    _, saved = old.read("recovery")
    factors = [old.read(c["name"])[1] for c in system["metadata"]["classes"]]
    cells = saved_bridge["producer_cells"]
    perms = saved_bridge["consumer_permutations"]
    owner_bridge = {
        "producer_cells": cells,
        "owned_cells": int(saved_bridge["owned_cells"][0]),
        "producer_owner": saved_bridge["producer_row_owners"],
        "transfer": [
            native_transfer(e, literal["cell_permutations"][c], p)
            for c, p in zip(cells, perms, strict=True)
        ],
        "native_transforms": [cell_transform(e, p) for p in perms],
    }
    b = SavedRecoveryConsumer(
        comm,
        literal,
        numbering,
        factors,
        owner_bridge,
        saved["C_adapter"],
        saved["D_adapter"],
    )
    own = b.owned_ids
    bx = b.apply_original(saved["a_x"][own], coupled=True)
    by = b.apply_original(saved["b_x"][own], adjoint=True, coupled=True)
    u = b.recover(saved["z"], saved["f"])
    Vu = b.apply_original(u)
    Du = comm.allreduce(b.D @ u)
    rport = saved["g"] + Du - saved["alpha"]
    rFE = saved["f"][own] - Vu - b.C @ saved["alpha"]
    rnative = rFE - b.C @ rport
    rhs = b.reduced_rhs(saved["f"], saved["g"])
    checks.extend(
        [
            dict(kind="B_consumer_original", **metric(bx, saved["a_action"][own])),
            dict(kind="B_consumer_adjoint", **metric(by, saved["b_adjoint"][own])),
            dict(kind="B_affine_recover", **metric(u, saved["u"][own])),
            dict(kind="B_complete_port", **metric(rport, saved["rport"])),
            dict(kind="B_full_residual", **metric(rnative, saved["rnative"][own])),
            dict(kind="B_nonzero_rhs", **metric(rhs, saved["reduced_rhs"])),
        ]
    )
    arrays.update(
        B_forward=bx,
        B_adjoint=by,
        B_recovered=u,
        B_native_residual=rnative,
        B_port=rport,
        B_reduced_rhs=rhs,
        B_owned_rows=own,
    )
    packets = save_rank(
        folder,
        arrays,
        {
            "checks": checks,
            "new_mesh": 0,
            "new_LU": 0,
            "new_form_JIT": 0,
            "B_calls": b.calls,
            "owner_binding": "immutable qualified actual MPI2 native owner directory",
            "A_numbering": "V41 BRIDGE2 frozen actual native global IDs/owners; full saved literal mapping",
            "parents": [{"path": str(p), "sha256": sha(p)} for p in (apath, bpath)],
        },
        name="consumer",
    )
    passed = comm.allreduce(int(all(c["passed"] for c in checks))) == comm.size
    return {
        "status": "FINITE_ACTION_AND_B_RECOVERY_CONSUMER_QUALIFIED"
        if passed
        else "CONSUMER_FAILED",
        "passed": passed,
        "checks": checks,
        "packets": packets,
        "MPI_size": comm.size,
        "A_internal_recovery_qualified": False,
        "target_callable": False,
        "interface": {
            "original": "NativeDistributedAction.apply_original / SavedRecoveryConsumer.apply_original",
            "adjoint": "apply_original_adjoint / apply_original(adjoint=True)",
            "boundary_extract": "original D @ owned plus MPI sum",
            "boundary_dual": "original C and D.conjugate().T; independent non-mutual carriers",
            "finite_recover": "SavedRecoveryConsumer.recover(z, full_rhs)",
            "original_residual": "r_FE - C @ r_port, full owned coverage",
        },
        "new_mesh": 0,
        "new_LU": 0,
        "NN_training": 0,
    }


def capacity():
    check, checked_path = stage("CHECK")
    gate, gate_path = stage("TARGET_GATE")
    return {
        "status": "CAPACITY_AND_NEURAL_BOUNDARY_RECORDED",
        "parents": [
            {"path": str(p), "sha256": sha(p)} for p in (checked_path, gate_path)
        ],
        "actual": {
            "finite_action_passed": check["volume_action_passed"],
            "B_recovery_passed": check["recovery"]["passed"],
            "A_recovery_passed": check["volume_status"] == "FINITE_VOLUME_QUALIFIED"
            and check["independent_internal_audit"]["passed"],
            "target_action": "NOT_RUN",
            "full_PDE": "NOT_QUALIFIED",
            "NN20": "NOT_DEMONSTRATED",
        },
        "payload_scenario_bytes": {
            "one_native_vector_including_slaves": 345771066 * 16,
            "one_canonical_trace_plus_interior": 344183904 * 16,
            "four_canonical_vectors": 4 * 344183904 * 16,
            "raw270_matrices": 270 * 882 * 882 * 16,
            "rank_private306_matrices": 306 * 882 * 882 * 16,
            "unbuilt_oriented858_matrices": 858 * 882 * 882 * 16,
        },
        "target_peak_RSS_prediction": "unknown; payload is not a conservative RSS bound",
        "target_setup_action_recovery_IO_seconds": "unknown; finite native numbering/router is not the target decoder",
        "48h_K_budget": "unknown: T_setup, T_solve_action, T_PC, T_communication, T_recovery, T_audit, T_IO and required K missing",
        "neural_scope": "FE action/adjoint and original residual are prerequisites for checking neural fields, not neural benefits",
        "NN20_required": {
            "correctness": "same full original equation, fields/channels/power",
            "time": "T_NN_total <= 0.8*T_best_qualified_nonNN_total; memory compliant",
            "memory": "M_NN_simultaneous_peak <= 0.8*M_best_qualified_nonNN_peak; time compliant",
            "included": [
                "data",
                "training",
                "construction",
                "load",
                "inference",
                "correction",
                "recovery",
                "audit",
                "IO",
            ],
            "best_qualified_full_nonNN_baseline": "unknown",
            "current_neural_increment": "none",
        },
        "remaining_solver_fields": [
            "target entity-volume backend",
            "qualified target recovery",
            "original physical incident RHS",
            "matched PC/convergence strategy",
            "h/p/mode accuracy",
            "full original residual and fields/power",
        ],
        "next_minimum_proposal_only": "one frozen neural-trace to canonical-entity/original-residual/adjoint-gradient integration on the qualified finite B packet, with same-correctness non-neural cost control; no automatic training",
        "reasons_not_run": gate["reasons"],
        "old_costs": "retain supervised lower bound and unmetered unknown",
    }
