"""One immutable R/B admission ledger, shared by outer and inner samplers."""

import fcntl
import json
from pathlib import Path
import time

from src.io.finite_json import atomic_json


def update_budget(window_path, event=None, *, before_admission=False):
    path = Path(window_path)
    window = json.loads(path.read_text())
    v28 = window.get("schema") == "task42extra.w1-v28-batch-window.v1"
    if window.get("schema") != "task42extra.w1-receiver-P0RB-window.v27" and not v28:
        return None
    ledger = path.parent / "resource_samples.json"
    with (path.parent / "resource_samples.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = (
            json.loads(ledger.read_text())
            if ledger.exists()
            else {"schema": "w1-shared-admission-budget.v27", "events": []}
        )
        count = sum(e["kind"] == "admission" for e in value["events"])
        waited = sum(e.get("elapsed_seconds", 0) for e in value["events"])
        if event is None:
            limit = 24 if v28 else 12
            exhausted = count >= limit if before_admission or not v28 else count > limit
            if exhausted or waited >= (900 if v28 else 300):
                raise TimeoutError("W1_SHARED_RESOURCE_SAMPLES_OR_WAIT_EXHAUSTED")
        else:
            value["events"].append(event)
            value["admission_samples"] = count + (event["kind"] == "admission")
            value["foreground_wait_seconds"] = waited + event["elapsed_seconds"]
            atomic_json(ledger, value)
        return value


def admit(spec, directory, hard, *, inner=False, scope=None):
    from src.runners.feinn_resources import admission

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    update_budget(spec["window_path"], before_admission=True)
    started = time.monotonic()
    observed = {}

    def save(value):
        observed.update(json.loads(json.dumps(value)))
        atomic_json(directory / "admission_observation.json", observed)

    try:
        facts = admission(
            hard, compensate_self=inner, candidate_scope=scope, observation_sink=save
        )
        facts = json.loads(json.dumps(facts))
        save(facts)
        return facts
    except Exception as error:
        save(
            {
                **observed,
                "admission_exception": type(error).__name__,
                "admission_reason": str(error),
                "unobserved_fields": "UNKNOWN" if not observed else [],
            }
        )
        raise
    finally:
        update_budget(
            spec["window_path"],
            {
                "kind": "admission",
                "inner": inner,
                "stage": spec["stage"],
                "origin_monotonic": started,
                "elapsed_seconds": time.monotonic() - started,
                "observation_path": str(directory / "admission_observation.json"),
            },
        )


def stable(spec, directory, hard):
    from src.runners.feinn_resources import stable_window

    value = update_budget(spec["window_path"])
    window = json.loads(Path(spec["window_path"]).read_text())
    cap = 900 if window.get("schema") == "task42extra.w1-v28-batch-window.v1" else 300
    if value and value.get("foreground_wait_seconds", 0) > cap - 60:
        raise TimeoutError("W1_PSI_STABLE_WINDOW_WOULD_EXCEED_SHARED_WAIT")
    started = time.monotonic()
    try:
        return stable_window(directory, hard)
    finally:
        update_budget(
            spec["window_path"],
            {
                "kind": "PSI_stable_window",
                "stage": spec["stage"],
                "origin_monotonic": started,
                "elapsed_seconds": time.monotonic() - started,
            },
        )
