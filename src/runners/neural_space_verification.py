"""Frozen-space physical verification, followed by a separate pure checker."""

import gc
import json
from time import monotonic


from src.io.neural_wave_campaign import ROOT, digest, profile_paths
from src.io.neural_space_campaign import field_policy
from src.solvers.neural_wave_greedy import atomic_json


def compare(action, packet, design, artifact, marker, manifest):
    from src.runners.neural_wave_worker import verify
    from benchmarks.subreaper_watchdog import supervise

    profile = profile_paths(manifest["spec"])
    A = json.loads(
        (profile["artifacts"] / "v35_unlabelled_readout_audit/result.json").read_text()
    )
    B = json.loads(
        (profile["artifacts"] / "v35_labelled_field_oracle/result.json").read_text()
    )
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
