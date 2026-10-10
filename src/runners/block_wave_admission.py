"""V31 separates successful safety checks from actual rejected-window cost."""

import json
import os
from pathlib import Path
from time import monotonic

from src.io.neural_wave_campaign import ROOT
from src.solvers.neural_wave_greedy import atomic_json

POOL = ROOT / "tmp/task42extra/v31/resource_rejected_wait.jsonl"


def pool(directory=None):
    if directory is not None and Path(directory).resolve().is_relative_to(ROOT / "tmp/task42extra/v40"):
        return ROOT / "tmp/task42extra/v40/resource_rejected_wait.jsonl"
    if directory is not None and Path(directory).resolve().is_relative_to(ROOT / "tmp/task42extra/v39"):
        return ROOT / "tmp/task42extra/v39/resource_rejected_wait.jsonl"
    if directory is not None and Path(directory).resolve().is_relative_to(ROOT / "tmp/task42extra/v38"):
        return ROOT / "tmp/task42extra/v38/resource_rejected_wait.jsonl"
    if directory is not None and Path(directory).resolve().is_relative_to(
        ROOT / "tmp/task42extra/v36"
    ):
        return ROOT / "tmp/task42extra/v36/resource_rejected_wait.jsonl"
    if directory is not None and Path(directory).resolve().is_relative_to(
        ROOT / "tmp/task42extra/v35"
    ):
        return ROOT / "tmp/task42extra/v35/resource_rejected_wait.jsonl"
    if directory is not None and Path(directory).resolve().is_relative_to(
        ROOT / "tmp/task42extra/v34"
    ):
        return ROOT / "tmp/task42extra/v34/resource_rejected_wait.jsonl"
    if directory is not None and Path(directory).resolve().is_relative_to(
        ROOT / "tmp/task42extra/v33"
    ):
        return ROOT / "tmp/task42extra/v33/resource_rejected_wait.jsonl"
    return (
        ROOT / "tmp/task42extra/v32/resource_rejected_wait.jsonl"
        if directory is not None
        and Path(directory).resolve().is_relative_to(ROOT / "tmp/task42extra/v32")
        else POOL
    )


def rejected_wait_seconds(directory=None):
    POOL = pool(directory)
    if not POOL.exists():
        return 0.0
    return sum(json.loads(line)["seconds"] for line in POOL.read_text().splitlines())


def wait_limit(directory):
    return 900 if pool(directory).parent.name in ("v35", "v36", "v38", "v39", "v40") else 1800


def charge_rejected_wait(start, reason, directory):
    elapsed = monotonic() - start
    POOL = pool(directory)
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
                rejected_wait_seconds(directory)
                + (monotonic() - rejected_start if rejected_start else 0)
                >= wait_limit(directory)
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

    if rejected_wait_seconds(directory) >= wait_limit(directory):
        raise RuntimeError("V31_FAILED_RESOURCE_WAIT_LIMIT_REACHED")
    start = monotonic()
    try:
        return original(directory, hard, seconds=seconds)
    except Exception as error:
        charge_rejected_wait(start, error, directory)
        raise
