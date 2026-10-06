"""Thin serial V30 dependencies under the existing live terminal/watchdog.

No admission threshold changes. A completed payload can hand its continuously
supervised resource window to a separately activated verifier/checker process.
"""

import json
import os
from pathlib import Path
import sys
from time import monotonic, time_ns

from src.io.neural_wave_campaign import ROOT, ARTIFACTS, digest, load_wave
from src.solvers.neural_wave_greedy import atomic_json


def resource_observation_cost(root=None):
    root = Path(root or ROOT / "tmp/task42extra/v30")
    stability = sum(
        json.loads(p.read_text())["observed_seconds"]
        for p in root.rglob("pressure_stable_window.json")
    )
    unique = {}
    for p in [*root.rglob("*admission*.json"), *root.glob("continuation_recheck_*.json")]:
        value = json.loads(p.read_text())
        if "sample_interval_seconds" in value:
            unique[value["utc"]] = value["sample_interval_seconds"]
    # The actual earlier 12s delay and a conservative 2s diagnostic allowance.
    explicit = 14.0 if root == ROOT / "tmp/task42extra/v30" else 0.0
    return stability + sum(unique.values()) + explicit


def fresh_admission(directory, hard, *, scope=None, prefix="admission", reserve_s=0):
    """At most eight foreground fresh samples; never waive a rejected core."""
    from src.runners.feinn_resources import admission

    directory = Path(directory)
    start = monotonic()
    for index in range(8):
        if monotonic() - start >= 20 or resource_observation_cost() + reserve_s + 2 >= 1200:
            raise RuntimeError("V30_RESOURCE_OBSERVATION_BUDGET_REACHED")
        file = directory / f"{prefix}_sample_{index:02d}.json"
        if file.exists():
            raise ValueError("ADMISSION_SAMPLE_ALREADY_EXISTS")
        try:
            result = admission(
                hard,
                compensate_self=len(os.sched_getaffinity(0)) == 1,
                candidate_scope=scope,
                observation_sink=lambda v: atomic_json(file, v),
            )
            atomic_json(directory / f"{prefix}.json", result)
            return result
        except RuntimeError:
            if not file.exists():
                raise
            failed = json.loads(file.read_text())
            if failed.get("failures") != [
                "No audited unoccupied physical core; do not overlap a busy worker/SMT sibling"
            ]:
                raise
    raise RuntimeError("RESOURCE_WINDOW_UNAVAILABLE: bounded fresh CPU samples exhausted")


def continuity_receipt(resources, *, now_ns=None, root_pid=None):
    """Require an actual recent complete 60s of the same live supervised tree."""
    files = [Path(p) for p in resources] if isinstance(resources, (list, tuple)) else [Path(resources)]
    lines = []
    for file in files:
        with file.open("rb") as stream:
            stream.seek(max(0, file.stat().st_size - 4 * 2**20))
            lines.extend(stream.read().splitlines())
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        raise ValueError("CONTINUOUS_RESOURCE_HISTORY_UNAVAILABLE")
    rows = sorted({v["timestamp_ns"]: v for v in rows}.values(), key=lambda v: v["timestamp_ns"])
    last = rows[-1]["timestamp_ns"]
    age = ((time_ns() if now_ns is None else now_ns) - last) / 1e9
    selected = [v for v in rows if v["timestamp_ns"] >= last - 61 * 10**9]
    if age < 0 or age > 15 or not selected or last - selected[0]["timestamp_ns"] < 60 * 10**9:
        raise ValueError("CONTINUOUS_RESOURCE_HISTORY_STALE_OR_INCOMPLETE")
    if any(b["timestamp_ns"] - a["timestamp_ns"] > 15 * 10**9 for a, b in zip(selected, selected[1:])):
        raise ValueError("CONTINUOUS_RESOURCE_HISTORY_HAS_GAP")
    for row in selected:
        h = row["opt_in_health_check"]
        p = h["memory_pressure"]
        if (
            not row["all_status_readable"] or row["swap_bytes"] != 0
            or h["stop_reason"] is not None
            or p["some"]["avg10"] >= 1 or p["full"]["avg10"] >= 0.1
            or h["memory"]["launch_cap_bytes"] < h["memory"]["planning_cap_bytes"]
            or row["rss_bytes"] > h["memory"]["planning_cap_bytes"]
            or (root_pid is not None and row["root_pid"] != root_pid)
        ):
            raise ValueError("CONTINUOUS_RESOURCE_HISTORY_NOT_QUALIFIED")
    return dict(resources=[str(file.relative_to(ROOT)) if file.is_relative_to(ROOT) else str(file) for file in files],
        source_sha256=[digest(file) for file in files], sample_count=len(selected),
        covered_seconds=(last - selected[0]["timestamp_ns"]) / 1e9,
        age_seconds=age, last_timestamp_ns=last, root_pid=root_pid,
        all_actual_rows_qualified=True)


def run_admitted(spec):
    """Only a guarded dependent FE/pure run_case entry can use this branch."""
    from src.runners.neural_wave_campaign import source_gate
    from src.runners.guarded_exec import ticks
    from src.runners.neural_wave_worker import main

    directory = (ROOT / os.environ["TASK42EXTRA_WAVE_ADMITTED_CHILD"]).resolve()
    if not directory.is_relative_to(ROOT / "tmp/task42extra/v30/durable"):
        raise ValueError("DEPENDENCY_NAMESPACE_OUTSIDE_OWN_TREE")
    manifest = json.loads((directory / "run_manifest.json").read_text())
    parent = manifest["dependency_parent"]
    if (
        spec != manifest["spec"] or spec["role"] not in ("verify", "saved_audit")
        or source_gate() != manifest["source_sha"]
        or os.getppid() != parent["pid"]
        or ticks(parent["pid"]) != parent["start_ticks"]
        or not manifest["continuous_resource_receipt"]["all_actual_rows_qualified"]
        or not 0 <= monotonic() - manifest["fresh_admission_completed_monotonic"] <= 15
        or not 0 <= (time_ns() - manifest["continuous_resource_receipt"]["last_timestamp_ns"]) / 1e9 <= 15
        or os.sched_getaffinity(0) != {manifest["cpu"]}
        or os.environ.get("TASK42EXTRA_ENV_MODE") != spec["mode"]
        or os.environ.get("TASK42EXTRA_PARENT_DEATH_GUARD") != f"{parent['pid']}:{parent['start_ticks']}:SIGKILL"
    ):
        raise ValueError("UNVERIFIED_ADMITTED_DEPENDENCY")
    sys.argv = [sys.argv[0], str(directory.relative_to(ROOT))]
    main()
    return 0


def followups(directory, manifest, terminal, preceding_summary):
    """Serial official one-run FE and pure entries; no new server or operator."""
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.feinn_resources import Health, envelope
    from src.runners.fresh_component_receiver import bind_own_terminal_core
    from src.runners.guarded_exec import ticks
    from src.runners.neural_wave_campaign import source_gate
    import shlex

    directory = Path(directory)
    if preceding_summary["classification"] != "COMPLETED" or preceding_summary["leader_exit_code"] != 0:
        return []
    finished = json.loads((ARTIFACTS / manifest["spec"]["stage"] / "result.json").read_text())
    if finished.get("status") == "COMMON_COST_WORK_NODE_FROZEN_NOT_FINAL":
        return []
    preceding_resources = [directory / "supervised/resources.jsonl"]
    summaries = []
    for stage in ("v30_m5_verify", "v30_m5_saved_audit"):
        receipt = continuity_receipt(preceding_resources, root_pid=terminal["server"]["pid"])
        source = source_gate()
        spec = load_wave(ROOT / f"input/task042extra_feinn_5nm/{stage}.dat")
        child = directory / "dependencies" / stage
        child.mkdir(parents=True, exist_ok=False)
        artifact = ARTIFACTS / stage
        if (artifact / "result.json").exists():
            raise ValueError("DEPENDENCY_ALREADY_FROZEN_DO_NOT_REPLAY_PRODUCER")
        artifact.mkdir(parents=True, exist_ok=True)
        hard = (16 if spec["mode"] == "fe" else 2) * 2**30
        facts = fresh_admission(child, hard, scope=terminal["allowed_scope"])
        admitted = monotonic()
        bind_own_terminal_core(terminal, facts["cpu"])
        os.sched_setaffinity(0, {facts["cpu"]})
        deadline = min(monotonic() + spec["max_seconds"], manifest["campaign"]["deadline_monotonic"] - 1800)
        if deadline - monotonic() < 300:
            raise TimeoutError("DEPENDENCY_FINAL_SAVE_RESERVE_UNAVAILABLE")
        dependent = {**manifest, "spec": spec, "source_sha": source,
            "artifact": str(artifact.relative_to(ROOT)), "cpu": facts["cpu"],
            "route_origin_monotonic": monotonic(), "worker_stop_monotonic": deadline - 150,
            "stage_deadline_monotonic": deadline, "input_sha256": spec["input_sha256"],
            "pde_only_solve": False, "rss_hard_bytes": hard,
            "rss_warn_bytes": min(12 * 2**30, int(0.875 * hard)),
            "dependency_parent": dict(pid=os.getpid(), start_ticks=ticks(os.getpid())),
            "fresh_admission_completed_monotonic": admitted,
            "continuous_resource_receipt": receipt,
            "mode_selected_by_fresh_activation": spec["mode"],
            "python_executable": None,
            "python_executable_scope": "actual separately activated worker records abi.json",
            "environment": {"TASK42EXTRA_ENV_MODE": spec["mode"],
                "scope": "mode declaration; full actual worker environment is qualified by abi.json"}}
        atomic_json(child / "run_manifest.json", dependent)
        atomic_json(artifact / f"run_manifest_{directory.name}_dependency.json", dependent)
        (child / "input_original.dat").write_bytes((ROOT / spec["input"]).read_bytes())
        atomic_json(directory / "dependent_stage_current.json", dict(stage=stage, directory=str(child.relative_to(ROOT))))
        command = ["bash", "-lc", "source scripts/activate_task42extra.sh " + spec["mode"]
            + " && export TASK42EXTRA_WAVE_ADMITTED_CHILD=" + shlex.quote(str(child.relative_to(ROOT)))
            + " && exec python -m src.runners.guarded_exec " + str(os.getpid()) + " "
            + str(ticks(os.getpid())) + " python scripts/run_case.py " + shlex.quote(spec["input"])]
        result = supervise(command, child / "supervised", wall_seconds=deadline-monotonic(),
            rss_hard_limit_bytes=hard, rss_warning_bytes=dependent["rss_warn_bytes"],
            hard_stop_immediate=True, source_state=dependent,
            memory_envelope_provider=lambda: envelope(hard),
            health_check=Health(child, hard, [], artifact_root=ARTIFACTS),
            sampled_root_identity=terminal["server"])
        result["source_sha"] = source
        atomic_json(child / "run_summary.json", result)
        summaries.append(dict(stage=stage, directory=str(child.relative_to(ROOT)), summary=result))
        if result["classification"] != "COMPLETED" or result["leader_exit_code"] != 0:
            break
        preceding_resources.append(child / "supervised/resources.jsonl")
    return summaries
