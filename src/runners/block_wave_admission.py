"""V31 separates successful safety checks from actual rejected-window cost."""

import json
import os
from pathlib import Path
from time import monotonic

from src.io.neural_wave_campaign import ROOT
from src.solvers.neural_wave_greedy import atomic_json

POOL = ROOT / "tmp/task42extra/v31/resource_rejected_wait.jsonl"


def rejected_wait_seconds():
    if not POOL.exists():
        return 0.0
    return sum(json.loads(line)["seconds"] for line in POOL.read_text().splitlines())


def charge_rejected_wait(start, reason, directory):
    elapsed = monotonic() - start
    POOL.parent.mkdir(parents=True, exist_ok=True)
    with POOL.open("a") as stream:
        stream.write(
            json.dumps(
                dict(seconds=elapsed, reason=str(reason), directory=str(directory))
            )
            + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
    return elapsed


def fresh_admission(directory, hard, *, scope=None, prefix="admission", **_):
    from src.runners.feinn_resources import admission

    directory = Path(directory)
    start = monotonic()
    rejected_start = None
    try:
        for i in range(8):
            if (
                rejected_wait_seconds()
                + (monotonic() - rejected_start if rejected_start else 0)
                >= 1800
            ):
                raise RuntimeError("V31_FAILED_RESOURCE_WAIT_LIMIT_REACHED")
            if monotonic() - start >= 20:
                break
            file = directory / f"{prefix}_sample_{i:02d}.json"
            if file.exists():
                raise ValueError("ADMISSION_SAMPLE_ALREADY_EXISTS")
            sampled = monotonic()
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
                rejected_start = sampled if rejected_start is None else rejected_start
                if not file.exists() or json.loads(file.read_text())["failures"] != [
                    "No audited unoccupied physical core; do not overlap a busy worker/SMT sibling"
                ]:
                    raise
        raise RuntimeError(
            "RESOURCE_WINDOW_UNAVAILABLE: bounded fresh CPU samples exhausted"
        )
    finally:
        if rejected_start is not None:
            charge_rejected_wait(
                rejected_start,
                "actual rejected admission and bounded resampling",
                directory,
            )


def stable_window(directory, hard, seconds=60):
    from src.runners.feinn_resources import stable_window as original

    if rejected_wait_seconds() >= 1800:
        raise RuntimeError("V31_FAILED_RESOURCE_WAIT_LIMIT_REACHED")
    start = monotonic()
    try:
        return original(directory, hard, seconds=seconds)
    except Exception as error:
        charge_rejected_wait(start, error, directory)
        raise
