"""Thin FE-only campaign: existing durable terminal/watchdog, independent ledger.

The old launcher assumes M5 and historical NN budgets. This adapter changes
only stage admission/provenance and delegates all numerical work to solvers.
"""

from datetime import datetime, timezone
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback

from src.io.fixed_phase_pilot import ROOT, DESIGN
from src.runners.feinn_resources import (
    ARTIFACTS,
    Health,
    admission,
    envelope,
    stable_window,
)

BATCH = ROOT / "tmp/task42extra/v20"
CAPS = dict(implementation=10800, A=3600, B=14400, C=5400, D=3600)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(2**20):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    def convert(x):
        if isinstance(x, complex):
            return dict(real=x.real, imag=x.imag)
        if hasattr(x, "tolist"):
            return x.tolist()
        raise TypeError(type(x).__name__)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".tmp-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
                default=convert,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def batch_remaining(now=None):
    c = json.loads((BATCH / "clock.json").read_text())
    return c["batch_limit_seconds"] - (
        (time.monotonic() if now is None else now) - c["start_monotonic"]
    )


def prior_runs():
    rows = []
    for path in sorted(
        (ROOT / "results/task42extra").glob("task42extra_v20_*/run_manifest.json")
    ):
        m = json.loads(path.read_text())
        summary = path.with_name("run_summary.json")
        if not summary.exists():
            raise RuntimeError("V20_PRIOR_RUN_NOT_SETTLED:" + str(path.parent))
        row = json.loads(summary.read_text())
        if not row["descendants_cleared"]:
            raise RuntimeError("V20_PRIOR_TREE_NOT_CLEARED")
        rows.append(
            dict(
                stage=m["stage"],
                group=m["group"],
                seconds=row["launch_to_summary_seconds_monotonic"],
                path=str(summary),
            )
        )
    return rows


def selected(stage):
    candidates = sorted(ARTIFACTS.glob("index_" + stage + "_attempt*.json"))
    good = []
    for path in candidates:
        record = json.loads(path.read_text())
        if record["result"].get("stage_qualified"):
            for v in record["files"].values():
                p = Path(v["path"])
                if (
                    not p.resolve().is_relative_to(ARTIFACTS.resolve())
                    or sha(p) != v["sha256"]
                ):
                    raise RuntimeError("V20_SAVED_IDENTITY_CHANGED")
            good.append(record)
    if len(good) != 1:
        raise RuntimeError("V20_UNIQUE_QUALIFIED_DEPENDENCY_REQUIRED:" + stage)
    return good[0]


def retained_roles():
    """Available frozen physical states, including explicitly negative ones.

    Missing reference is a partial diagnostic, never a silently qualified role.
    Same-input repaired attempts prefer the unique algebra-qualified state.
    """
    records = {}
    for role in ("O3", "E3", "E4", "O6"):
        paths = sorted(ARTIFACTS.glob("index_v20_" + role.lower() + "_attempt*.json"))
        candidates = [json.loads(p.read_text()) for p in paths]
        candidates = [
            c
            for c in candidates
            if all(k in c["files"] for k in ("native", "field", "observables"))
        ]
        qualified = [c for c in candidates if c["result"].get("stage_qualified")]
        if len(qualified) > 1:
            raise RuntimeError("V20_AMBIGUOUS_RETAINED_ROLE:" + role)
        if not candidates:
            continue
        record = qualified[0] if qualified else candidates[-1]
        for v in record["files"].values():
            p = Path(v["path"])
            if (
                not p.resolve().is_relative_to(ARTIFACTS.resolve())
                or sha(p) != v["sha256"]
            ):
                raise RuntimeError("V20_RETAINED_IDENTITY_CHANGED")
        records[role] = record
    return records


def launch(spec):
    from benchmarks.subreaper_watchdog import supervise
    from src.runners.guarded_exec import ticks

    origin = float(os.environ.get("TASK42EXTRA_V20_LAUNCH_ORIGIN_MONOTONIC", "0"))
    if not 0 < origin <= time.monotonic():
        raise RuntimeError("V20_DURABLE_IMPORT_CLOCK_NOT_BOUND")
    stage = spec.derived["stage"]
    if (
        Path.cwd() != ROOT
        or os.environ.get("TASK42EXTRA_ACTIVATION") != "1"
        or os.environ.get("TASK42EXTRA_ENV_MODE") != spec.derived["environment_mode"]
    ):
        raise RuntimeError("V20_QUALIFIED_NATIVE_ACTIVATION_REQUIRED")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], text=True
    ).strip()
    if branch != "task42extra_feinn_5nm" or subprocess.check_output(
        ["git", "status", "--porcelain"]
    ):
        raise RuntimeError("V20_CLEAN_EXACT_SOURCE_REQUIRED")
    namespace = os.environ.get("TASK42EXTRA_DURABLE_NAMESPACE", "")
    proof = ROOT / "tmp/task42extra/durable" / namespace / "terminal_identity.json"
    if not namespace.startswith(stage) or not proof.is_file():
        raise RuntimeError("V20_DURABLE_SUPERVISED_LAUNCH_REQUIRED")
    attempt = int(namespace.rsplit("_attempt", 1)[1]) if "_attempt" in namespace else 1
    terminal = json.loads(proof.read_text())
    if (ARTIFACTS / f"index_{stage}_attempt{attempt}.json").exists():
        raise RuntimeError("V20_DUPLICATE_STAGE_FORBIDDEN")
    old = prior_runs()
    group = spec.derived["group"]
    if stage == "v20_phase_qualification":
        selected("v20_control_checks")
    if group == "B":
        if sum(r["group"] == "B" for r in old) >= 6:
            raise RuntimeError("V20_SIX_B_LIFECYCLES_EXHAUSTED")
        if not selected("v20_phase_qualification")["result"]["checker"]["passed"]:
            raise RuntimeError("V20_A_NOT_QUALIFIED")
    if stage == "v20_e4":
        selected("v20_e3")
    used = sum(r["seconds"] for r in old if r["group"] == group)
    limit = min(
        spec.execution["timeout_seconds"], CAPS[group] - used, batch_remaining() - 1800
    )
    if limit <= 150:
        raise RuntimeError("V20_SAVE_RESERVE_UNAVAILABLE")
    directory = spec.expected_output_parent / (
        spec.identity["run_id"]
        + "_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    directory.mkdir(parents=True)
    artifact = ARTIFACTS / directory.name
    artifact.mkdir(parents=True)
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    state = dict(
        schema="fixed_phase.run.v1",
        source_sha=source,
        branch=branch,
        stage=stage,
        group=group,
        role=spec.derived["role"],
        attempt=attempt,
        stage_limit_seconds=limit,
        supervision_budget_origin_monotonic=origin,
        numerical_cutoff_monotonic=origin + limit - 150,
        batch_remaining_seconds_at_launch=batch_remaining(),
        old_costs_preserved=True,
        design_sha256=sha(DESIGN),
        input_sha256=spec.input_sha256,
        input_path=str(spec.source_path),
        artifact_directory=str(artifact),
        durable_terminal_identity_sha256=sha(proof),
        environment_mode=spec.derived["environment_mode"],
        mpi_size=1,
        math_threads=1,
        cpu_only=True,
        neural_training_count=0,
        Gram_factor_count=0,
        production_qualified=False,
        field_space="actual identity bound before any solve",
        prior_runs=old,
    )
    write(directory / "run_manifest.json", state)
    try:
        with (ROOT / "tmp/task42extra/numerical.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            hard = spec.execution["terminate_memory_gib"] * 2**30
            baseline = admission(hard)
            if stage == "v20_o6":
                lookup = BATCH / "O6_lookup.json"
                old_ref = json.loads(lookup.read_text())
                if (
                    old_ref["status"] != "NO_QUALIFIED_SAVED_O6"
                    or old_ref["lookup_seconds"] > 600
                ):
                    raise RuntimeError("O6_ONE_NEW_REFERENCE_NOT_ADMITTED")
                state["O6_saved_reference_lookup"] = dict(
                    path=str(lookup), sha256=sha(lookup)
                )
            write(directory / "admission.json", baseline)
            os.sched_setaffinity(0, {baseline["cpu"]})
            os.nice(10)
            subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
            if spec.derived["environment_mode"] == "fe":
                stable_window(directory, hard)
            state.update(
                cpu=baseline["cpu"],
                ABI_record={
                    "path": str(
                        ROOT
                        / "tmp/task42extra/setup"
                        / (spec.derived["environment_mode"] + "_abi.json")
                    )
                },
            )
            write(directory / "run_manifest.json", state)
            command = [
                sys.executable,
                "-m",
                "src.runners.guarded_exec",
                str(os.getpid()),
                str(ticks(os.getpid())),
                sys.executable,
                "-m",
                "src.runners.fixed_phase_campaign",
                str(directory),
            ]
            result = supervise(
                command,
                directory / "supervision",
                wall_seconds=state["numerical_cutoff_monotonic"] - time.monotonic(),
                interval=0.5,
                rss_hard_limit_bytes=hard,
                rss_warning_bytes=int(spec.execution["warning_memory_gib"] * 2**30),
                hard_stop_immediate=True,
                memory_envelope_provider=lambda: envelope(hard),
                health_check=Health(directory, hard, baseline["neighbor_processes"]),
                include_pss=False,
                stop_on_global_swap=False,
                sampled_root_identity={
                    k: terminal["server"][k] for k in ("pid", "start_ticks")
                },
                source_state=dict(
                    source_sha=source,
                    clean_worktree=True,
                    branch=branch,
                    input_sha256=spec.input_sha256,
                    design_sha256=sha(DESIGN),
                    identity="new fixed-phase FE research stage, not legacy M5",
                ),
            )
    except BaseException as exc:
        result = dict(
            classification="LAUNCH_GATE_REJECTED",
            leader_exit_code=1,
            descendants_cleared=True,
            reason=str(exc),
            exception=type(exc).__name__,
            traceback=traceback.format_exc(),
        )
    result.update(
        launch_to_summary_seconds_monotonic=time.monotonic() - origin,
        source_sha=source,
        run_directory=str(directory),
        artifact_directory=str(artifact),
        stage=stage,
    )
    write(directory / "run_summary.json", result)
    return result


def worker(directory):
    directory = Path(directory)
    m = json.loads((directory / "run_manifest.json").read_text())
    artifact = Path(m["artifact_directory"])
    began = time.monotonic()

    def marker(phase, record):
        row = dict(
            phase=phase,
            monotonic=time.monotonic(),
            worker_elapsed_seconds=time.monotonic() - began,
            values=record,
        )
        with (directory / "events.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    row,
                    default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x),
                )
                + "\n"
            )
            stream.flush()
        print(phase, flush=True)

    def budget(phase):
        if time.monotonic() >= m["numerical_cutoff_monotonic"]:
            raise RuntimeError("V20_STOP_SAVE_RESERVE:" + phase)

    try:
        if (
            subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
            != m["source_sha"]
            or sha(DESIGN) != m["design_sha256"]
        ):
            raise RuntimeError("V20_SOURCE_OR_DESIGN_CHANGED")
        design = json.loads(DESIGN.read_text())
        if m["stage"] == "v20_control_checks":
            from benchmarks.fixed_phase_control_checks import control_checks

            result, files = control_checks(directory, artifact, marker, m), {}
        elif m["stage"] == "v20_phase_qualification":
            from src.solvers.fixed_phase_qualification import qualify
            from benchmarks.fixed_phase_checker import qualification

            result = qualify(design["fixture"], marker)
            result["checker"] = qualification(result)
            result["stage_qualified"] = result["checker"]["passed"]
            files = {}
        elif m["group"] == "B":
            from src.solvers.fixed_phase_reference import reference

            result, files = reference(design, m["role"], artifact, marker, budget)
        elif m["stage"] == "v20_saved_checker":
            import numpy as np
            from benchmarks.fixed_phase_checker import compare_from_arrays

            indices = retained_roles()
            compare_index = selected("v20_physical_compare")
            with np.load(
                compare_index["files"]["integrals"]["path"], allow_pickle=False
            ) as z:
                raw = {k: np.array(z[k]) for k in z.files}
            observables = {}
            for role, idx in indices.items():
                with np.load(
                    idx["files"]["observables"]["path"], allow_pickle=False
                ) as z:
                    observables[role] = {k: np.array(z[k]) for k in z.files}
            result = compare_from_arrays(
                raw,
                observables,
                {r: i["result"]["full_equation"] for r, i in indices.items()},
            )
            result["stage_qualified"] = True
            files = {}
        elif m["group"] == "C":
            from src.solvers.fixed_phase_comparison import compare

            result, files = compare(
                retained_roles(),
                artifact,
                marker,
                budget,
            )
        else:
            raise RuntimeError("V20_STAGE_NOT_IMPLEMENTED")
        result.update(
            worker_wall_seconds=time.monotonic() - began,
            neural_gain="NOT_TESTED",
            production_qualified=False,
        )
        write(artifact / "result.json", result)
        files["result"] = artifact / "result.json"
        record = dict(
            stage=m["stage"],
            attempt=m["attempt"],
            source_sha=m["source_sha"],
            run_directory=str(directory),
            result=result,
            files={k: dict(path=str(p), sha256=sha(p)) for k, p in files.items()},
        )
        index = ARTIFACTS / f"index_{m['stage']}_attempt{m['attempt']}.json"
        if index.exists():
            raise RuntimeError("V20_INDEX_IMMUTABLE")
        write(index, record)
        marker(
            "frozen",
            dict(index=str(index), stage_qualified=result.get("stage_qualified")),
        )
        return 0
    except BaseException as exc:
        write(
            directory / "worker_failure.json",
            dict(
                reason=str(exc),
                kind=type(exc).__name__,
                traceback=traceback.format_exc(),
                wall_seconds=time.monotonic() - began,
                source_sha=m["source_sha"],
            ),
        )
        traceback.print_exc()
        return 1
    finally:
        gc.collect()


if __name__ == "__main__":
    raise SystemExit(worker(sys.argv[1]))
