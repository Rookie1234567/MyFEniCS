"""Hash-bound own GN recovery discovery; no Torch, PDE action or label read."""

import hashlib
import json
from pathlib import Path


def file_identity(path):
    path = Path(path)
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(2**20):
            value.update(block)
    return dict(path=str(path.resolve()), sha256=value.hexdigest())


def recovery_boundary(root, stage, prior):
    """Use the latest own fsynced boundary; spent incomplete work stays charged."""
    metric_pilot = stage.startswith("v11_")
    if len(prior) > (1 if metric_pilot else 2):
        raise RuntimeError("V10_ROUTE_FAULT_RECOVERY_LIMIT")
    candidates = []
    for row in prior:
        run = Path(row["path"]).parent
        artifact = Path(root) / "benchmarks/artifacts/task42extra" / run.name
        pointer = artifact / "durable_checkpoints/current.json"
        if pointer.exists():
            candidates.append((run, artifact, pointer))
    if not candidates:
        return None
    run, artifact, pointer = sorted(candidates)[-1]
    summary = json.loads((run / "run_summary.json").read_text())
    manifest = json.loads((run / "run_manifest.json").read_text())
    if not summary["descendants_cleared"] or summary["classification"] not in (
        "RESOURCE_WINDOW_UNAVAILABLE",
        "WORKER_FAILED",
    ):
        raise RuntimeError("RECOVERY_REQUIRES_CLEARED_FAILED_OWN_ATTEMPT")
    record = json.loads(pointer.read_text())["current"]
    meta = record["metadata"]
    phase, supervised = "phase" in stage, "fit" in stage
    route = ("V10-PHASE" if phase else "V10-PLAIN") + (
        "-CACHED-FIT-GN-CONTINUE" if supervised else "-CACHED-GN-CONTINUE"
    )
    if metric_pilot:
        route = "V11-PHASE-" + (
            "IDENTITY-METRIC-CONTROL" if "identity" in stage else "BLOCK-METRIC"
        )
    if meta["route"] != route or meta["stage"] != "DAMPED_GN":
        raise RuntimeError("RECOVERY_NETWORK_OR_OPTIMIZER_STAGE_CHANGED")
    if manifest["stage"] != stage or meta["run_id"] != run.name:
        raise RuntimeError("RECOVERY_ROUTE_IDENTITY_CHANGED")
    if meta["source_sha"] != manifest["source_sha"] or meta["state_kind"] not in (
        "accepted_outer",
        "final_committed",
        "retained_failure_boundary",
    ):
        raise RuntimeError("RECOVERY_NOT_COMPLETE_OWN_GN_BOUNDARY")
    for key, expected in dict(
        reference_used_for_training=supervised,
        features_reference_exposed=supervised,
        pde_only_solve=not supervised,
        production_initialization_allowed=False,
    ).items():
        if meta[key] is not expected:
            raise RuntimeError("RECOVERY_LABEL_BOUNDARY_CHANGED:" + key)
    pt = (pointer.parent / record["name"]).resolve()
    if (
        pt.parent != pointer.parent.resolve()
        or file_identity(pt)["sha256"] != record["sha256"]
    ):
        raise RuntimeError("RECOVERY_CHECKPOINT_HASH_CHANGED")
    history = artifact / "history.jsonl"
    events = []
    for line in history.read_text().splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # The successfully parsed journal is a lower bound. Wall still
            # charges any interrupted write/operation not present in it.
            pass
    matches = [
        i
        for i, x in enumerate(events)
        if x.get("kind") == "DURABLE_ACCEPTED"
        and x.get("checkpoint_sha256") == record["sha256"]
    ]
    if not matches:
        raise RuntimeError("RECOVERY_COMMITTED_JOURNAL_NOT_RETAINED")
    tail = events[matches[-1] + 1 :]
    if any(
        x.get("operation") == "PC_BUILD" and x.get("phase") == "begin" for x in tail
    ):
        raise RuntimeError("RECOVERY_UNCOMMITTED_PC_STATE_NOT_RETAINED")
    spent = dict(meta["counts"])
    jac = dict(meta["JVP_VJP_counts"])
    pending = set()
    for x in tail:
        for key, value in x.get("counts", {}).items():
            spent[key] = max(spent.get(key, 0), value)
        for key, value in x.get("JVP_VJP_counts", {}).items():
            jac[key] = max(jac.get(key, 0), value)
        if x.get("kind") == "WORK_EVENT":
            if x.get("phase") == "begin":
                pending.add(x["operation"])
            else:
                pending.discard(x["operation"])
    reserve = dict(
        K=int("K" in pending),
        JVP_VJP=2 * int("K" in pending) + int("GRADIENT" in pending),
        trial=int("TRUE_TRIAL" in pending),
    )
    earlier = meta.get("fault_recovery")
    if earlier:
        for key, value in earlier["incomplete_work_quota_reserve"].items():
            reserve[key] += value
    return dict(
        schema="task42extra.gn-fault-recovery.v11"
        if metric_pilot
        else "task42extra.gn-fault-recovery.v10",
        stage=stage,
        phase=phase,
        supervised=supervised,
        checkpoint_pointer=file_identity(pointer),
        durable_final=file_identity(pt),
        history=file_identity(history),
        prior_manifest=file_identity(run / "run_manifest.json"),
        prior_summary=file_identity(run / "run_summary.json"),
        prior_source_sha=manifest["source_sha"],
        committed_metadata=meta,
        original_V9_logical_prefix_seconds=meta["inherited_prefix_seconds"]
        - manifest.get("route_inherited_failed_attempt_seconds", 0),
        spent_counts_lower_bound=spent,
        spent_JVP_VJP_lower_bound=jac,
        unfinished_operations=sorted(pending),
        incomplete_work_quota_reserve=reserve,
        unknown_interrupted_suboperation_cost="NOT_RETAINED; entire launcher wall charged",
        fresh_cache_required=True,
        selection="LATEST_OWN_DURABLE_NOT_BEST_OR_TRIAL",
    )
