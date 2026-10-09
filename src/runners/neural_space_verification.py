"""Frozen-space physical verification, followed by a separate pure checker."""

import gc
import json
from time import monotonic


from src.io.neural_wave_campaign import ROOT, digest, profile_paths
from src.io.neural_space_campaign import field_policy
from src.solvers.neural_wave_greedy import atomic_json


def recover_budget_record(profile, design, current_manifest):
    """Only seal a proven budget-stop/writer failure, never replay projection.

    Both the original failure and the lack of a committed oracle remain part
    of the record. No reference coefficients, native action or G are used.
    """
    directory = profile["artifacts"] / "v35_labelled_field_oracle"
    target = directory / "result.json"
    if target.exists():
        return json.loads(target.read_text())
    actual = profile["root"] / "durable" / "v35_labelled_field_oracle_attempt1"
    summary_file = actual / "run_summary.json"
    manifest_file = actual / "run_manifest.json"
    log_file = actual / "supervised/worker.log"
    event_file = actual / "events.jsonl"
    previous = json.loads(manifest_file.read_text())
    summary = json.loads(summary_file.read_text())
    log = log_file.read_text()
    names = list(design["spaces"])
    if (
        summary["classification"] != "WORKER_FAILED"
        or summary["leader_exit_code"] != 1
        or summary["descendants_cleared"] is not True
        or previous["design_sha256"] != current_manifest["design_sha256"]
        or previous["spec"]["role"] != "space_oracle"
        or previous["source_sha"] != summary["source_state"]["source_sha"]
        or "ReadoutStop: READOUT_SAVE_WINDOW_REACHED" not in log
        or "FileNotFoundError:" not in log
        or str(directory / names[0] / "space_record.json.tmp") not in log
        or monotonic() < previous["worker_stop_monotonic"]
        or any(directory.rglob("committed.json"))
        or any(directory.rglob("projection_arrays.npz"))
    ):
        raise ValueError("ORACLE_BUDGET_FAILURE_RECOVERY_NOT_PROVEN")
    events = [json.loads(line) for line in event_file.read_text().splitlines() if line]
    if any(e["stage"] == "fixed_space_oracle_frozen" for e in events):
        raise ValueError("HEALTHY_ORACLE_MUST_NOT_BE_REPLACED_BY_RECOVERY")
    progress = [e["values"] for e in events if e["stage"] == "G_QR"]
    if not progress:
        raise ValueError("NO_RETAINED_ORACLE_PROGRESS")
    from src.io.neural_space_campaign import POLICY

    records = {
        name: dict(
            status="CONTROLLED_STOP_NUMERICAL_BUDGET" if i == 0 else "NOT_RUN_NUMERICAL_BUDGET",
            reason="READOUT_SAVE_WINDOW_REACHED",
            oracle_field="NOT_RETAINED_NO_COMMITTED_STATE",
            final_rank="UNKNOWN",
            **POLICY,
        )
        for i, name in enumerate(names)
    }
    A_file = profile["artifacts"] / "v35_unlabelled_readout_audit/result.json"
    A_events = profile["root"] / "durable/v35_unlabelled_readout_audit_attempt2/events.jsonl"
    sealed_A = [json.loads(line) for line in A_events.read_text().splitlines() if line]
    if not any(e.get("stage") == "stage_frozen" and e["values"].get("result_sha256") == digest(A_file) for e in sealed_A):
        raise ValueError("PRE_REFERENCE_A_FROZEN_RESULT_CHANGED")
    result = dict(
        records=records,
        bound_unlabelled_result_sha256=digest(A_file),
        source_sha=previous["source_sha"],
        input_sha256=previous["input_sha256"],
        design_sha256=previous["design_sha256"],
        metadata_recovery_source_sha=current_manifest["source_sha"],
        original_worker_classification="WORKER_FAILED",
        original_failure="Budget stop followed by missing per-space directory during record write",
        last_logged_progress_not_final_rank=progress[-1],
        partial_basis_and_weights="NOT_RETAINED",
        new_projection_count=0,
        reference_coefficients_read_count_during_recovery=0,
        original_failure_bindings={
            key: dict(path=str(p.relative_to(ROOT)), sha256=digest(p))
            for key,p in (("summary",summary_file),("manifest",manifest_file),("log",log_file),("events",event_file))
        },
        **POLICY,
    )
    for name, record in records.items():
        (directory / name).mkdir(parents=True, exist_ok=True)
        atomic_json(directory / name / "space_record.json", record)
    atomic_json(target, result)
    return result


def compare(action, packet, design, artifact, marker, manifest):
    from src.runners.neural_wave_worker import verify
    from benchmarks.subreaper_watchdog import supervise

    profile = profile_paths(manifest["spec"])
    A = json.loads(
        (profile["artifacts"] / "v35_unlabelled_readout_audit/result.json").read_text()
    )
    B = recover_budget_record(profile, design, manifest)
    reused, routes = {}, []
    old_path = ROOT / design["old_checker"]["path"]
    if digest(old_path) != design["old_checker"]["sha256"]:
        raise ValueError("UNCHANGED_FIELD_GATE_HASH_CHANGED")
    old = json.loads(old_path.read_text())
    if old["statuses_trusted"] is not False or old["reference_pass"] is not True:
        raise ValueError("ONLY_PRIOR_INDEPENDENT_GATE_REUSE")
    for name, record in A["records"].items():
        if "model" not in record:
            continue
        if record["old_field_bitwise_reused"]:
            reused[name] = dict(
                records={k: old["records"][k] for k in (name, name + "_PRODUCER")},
                original_checker=design["old_checker"],
                field_arrays_bitwise_unchanged=True,
                new_network_forward=0,
                new_FE_postprocessing=0,
            )
        else:
            routes.append(
                ("v35_unlabelled_readout_audit/" + name, name + "_UNLABELLED")
            )
    for name, record in B["records"].items():
        if "model" in record:
            routes.append(("v35_labelled_field_oracle/" + name, name + "_ORACLE"))
    if not routes:
        return dict(
            unchanged_unlabelled_gates=reused,
            new_fields="NOT_RUN_NO_NEW_FROZEN_FIELDS",
            new_network_forward=0,
            new_FE_postprocessing=0,
            CURRENT_DENSE_WAVE_SOLVER_FAMILY_CLOSED=True,
            candidate_decision="NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE",
        )
    # Only new fields are evaluated. The old unlabelled fields remain untouched.
    for stage, _ in routes:
        (artifact / (stage + "_rebuild.npz")).parent.mkdir(parents=True, exist_ok=True)
    result = verify(
        design,
        action,
        packet,
        artifact,
        marker,
        include_producer=True,
        routes=routes,
        route_root=profile["artifacts"],
        stable_rebuild=True,
        reference_exposed=True,
    )
    for name, record in result["comparisons"].items():
        record.update(field_policy(name))
        record["qualified"] = False
    for name, record in result["physics"]["records"].items():
        if name != "REFERENCE":
            record.update(field_policy(name))
    atomic_json(artifact / "verifier_result.json", result)
    result = None
    gc.collect()
    command = [
        "bash",
        "-lc",
        "source scripts/activate_task42extra.sh pure && exec python -m src.postprocessing.neural_space_saved "
        + str(artifact.relative_to(ROOT)),
    ]
    summary = supervise(
        command,
        artifact / "independent_pure_checker",
        wall_seconds=max(1, manifest["worker_stop_monotonic"] - monotonic()),
        rss_hard_limit_bytes=2 * 2**30,
        rss_warning_bytes=int(1.875 * 2**30),
        hard_stop_immediate=True,
        resource_stop_policy="measured_tree_rss_only_v3",
        source_state=dict(
            source_sha=manifest["source_sha"], role="independent_saved_field_checker"
        ),
    )
    if (
        summary["classification"] != "COMPLETED"
        or summary["leader_exit_code"] != 0
        or not summary["descendants_cleared"]
    ):
        raise ValueError("INDEPENDENT_SAVED_CHECKER_FAILED")
    checked = json.loads((artifact / "saved_checker.json").read_text())
    return dict(
        new_fields=checked,
        unchanged_unlabelled_gates=reused,
        verifier_result=dict(
            path=str((artifact / "verifier_result.json").relative_to(ROOT)),
            sha256=digest(artifact / "verifier_result.json"),
        ),
        independent_checker_summary=summary,
        candidate_decision="NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE",
        new_nonlinear_training=0,
        new_reference_solve=0,
        CURRENT_DENSE_WAVE_SOLVER_FAMILY_CLOSED=True,
        cold_N1="UNKNOWN",
        full_original_target_qualified=False,
    )
