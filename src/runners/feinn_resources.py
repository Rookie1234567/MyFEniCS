"""Task-local admission and sampled supervision, never signals a neighbor."""

import json
import shutil
import time
from pathlib import Path

from benchmarks.subreaper_watchdog import memory_envelope
from src.runners.task042_shared import audit as observed_audit, pressure

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "benchmarks/artifacts/task42extra"
GROWTH = 384 * 2**30


def envelope(hard=16 * 2**30):
    value = memory_envelope()
    reserve = max(128 * 2**30, int(value["effective_total_bytes"] * 0.1))
    value.update(
        system_reserve_bytes=reserve,
        neighbor_growth_allowance_bytes=GROWTH,
        reserve_bytes=reserve + GROWTH,
        launch_cap_bytes=min(
            hard, value["effective_available_bytes"] - reserve - GROWTH
        ),
        planning_cap_bytes=hard,
        shared_workstation=True,
    )
    return value


def admission(
    hard=16 * 2**30,
    *,
    compensate_self=False,
    candidate_scope=None,
    observation_sink=None,
):
    value = observed_audit(
        observed_activity=True,
        compensate_self=compensate_self,
        candidate_scope=candidate_scope,
        observation_sink=observation_sink,
    )
    value["memory"] = envelope(hard)
    if observation_sink is not None:
        observation_sink(value)
    if value["memory"]["launch_cap_bytes"] < hard:
        raise RuntimeError(
            "RESOURCE_WINDOW_UNAVAILABLE: system reserve + neighbor growth + task cap"
        )
    # CPU12 is merely a preference among freshly audited idle physical cores.
    cpus = value["candidate_cpus"]
    preferred = candidate_scope.get("preferred_cpu") if candidate_scope else 12
    value["cpu"] = preferred if preferred in cpus else (12 if 12 in cpus else cpus[0])
    value["schema"] = "task42extra.resource-admission.v1"
    value["growth_basis"] = {
        "Task39": "observed solve, tree hard 1300000000000 B; remaining growth about 150 GB",
        "Task041": "observed consumer, immutable cap 49.566070556640625 GiB; current about 40 GiB",
        "Metrology": "observed two GPU workers; reserve 128 GiB additional host growth",
        "other_controls": "16 GiB allowance; aggregate rounded conservatively to 384 GiB",
        "basis_kind": "conservative planning reserve; not a bound on another task's future behavior",
    }
    return value


def stable_window(directory, hard=16 * 2**30, *, seconds=60):
    """One bounded observation; never waits for a future resource window."""
    start = time.monotonic()
    samples = []
    while True:
        psi, env = pressure(), envelope(hard)
        sample = dict(
            elapsed_seconds=time.monotonic() - start, memory_pressure=psi, memory=env
        )
        samples.append(sample)
        bad = (
            psi["some"]["avg10"] >= 1
            or psi["full"]["avg10"] >= 0.1
            or env["launch_cap_bytes"] < hard
        )
        if bad or sample["elapsed_seconds"] >= seconds:
            break
        time.sleep(min(5, seconds - sample["elapsed_seconds"]))
    result = dict(
        passed=not bad and samples[-1]["elapsed_seconds"] >= seconds,
        required_seconds=seconds,
        samples=samples,
        thresholds=dict(some_avg10=1.0, full_avg10=0.1),
        watchdog_bad_samples_to_stop=3,
        observed_seconds=time.monotonic() - start,
        source_of_system_pressure="UNKNOWN",
        automatic_wait_or_restart=False,
    )
    Path(directory, "pressure_stable_window.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    if not result["passed"]:
        raise RuntimeError(
            "RESOURCE_WINDOW_UNAVAILABLE: 60s PSI stability not established"
        )
    return result


class Health:
    def __init__(self, directory, hard, neighbors):
        self.directory, self.hard, self.neighbors = directory, hard, neighbors
        self.last, self.pressure_count, self.result = 0.0, 0, {}

    def __call__(self):
        if time.monotonic() - self.last < 5:
            return self.result
        self.last = time.monotonic()
        psi = pressure()
        disk = shutil.disk_usage(ROOT).free
        artifact_bytes = sum(
            p.stat().st_size for p in ARTIFACTS.rglob("*") if p.is_file()
        )
        bad = psi["some"]["avg10"] >= 1 or psi["full"]["avg10"] >= 0.1
        self.pressure_count = self.pressure_count + 1 if bad else 0
        env = envelope(self.hard)
        reason = None
        if self.pressure_count >= 3 or env["launch_cap_bytes"] < self.hard:
            reason = "RESOURCE_WINDOW_UNAVAILABLE"
        if disk < 50 * 2**30 or artifact_bytes > 20 * 2**30:
            reason = "STORAGE_CONTROLLED_STOP"
        samples = []
        for neighbor in self.neighbors:
            try:
                parts = (
                    Path(f"/proc/{neighbor['pid']}/stat")
                    .read_text()
                    .rsplit(")", 1)[1]
                    .split()
                )
                if int(parts[19]) == neighbor["start_ticks"]:
                    samples.append(
                        dict(
                            pid=neighbor["pid"],
                            start_ticks=int(parts[19]),
                            cpu_ticks=int(parts[11]) + int(parts[12]),
                            cpu=int(parts[36]),
                        )
                    )
            except (OSError, ValueError):
                continue
        self.result = dict(
            memory_pressure=psi,
            disk_free_bytes=disk,
            artifact_bytes=artifact_bytes,
            memory=env,
            neighbor_identity_ticks=samples,
            stop_reason=reason,
        )
        with (self.directory / "health.jsonl").open("a") as stream:
            stream.write(json.dumps(self.result) + "\n")
        return self.result
