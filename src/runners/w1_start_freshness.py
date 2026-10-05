"""Opt-in V29 launch freshness, separate from the unchanged resource thresholds.

A saved observation is evidence of its own instant, not a reusable permission.
The final observation follows setup and PSI qualification; both the launcher and
its actual child verify age, boot, live issuer, cpuset, dat/window and source.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

MAX_AGE_SECONDS = 15.0


def process_identity(pid, proc_root=Path("/proc")):
    path = proc_root / str(pid)
    fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
    return dict(pid=pid, start_ticks=int(fields[19]), uid=path.stat().st_uid)


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_cpuset():
    location = Path(__file__).with_name("w1_admission_scope.py")
    spec = importlib.util.spec_from_file_location("_w29_scope_reader", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.cpuset_cpus()


def capture_grant(spec, facts):
    return dict(
        schema="w1-worker-start-grant.v29",
        observed_after_cpu_monotonic=time.monotonic(),
        boot_id=boot_id(),
        issuer=process_identity(os.getpid()),
        cpuset_cpus=sorted(current_cpuset()),
        selected_cpu=facts["cpu"],
        source_sha=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        input_sha256=spec["input_sha256"],
        window_sha256=digest(spec["window_path"]),
        fresh_CPU_observation=True,
        PSI_qualification_is_separate=True,
    )


def validate_grant(
    grant,
    spec,
    source_sha,
    *,
    now=None,
    boot=None,
    cpuset=None,
    issuer=None,
    affinity=None,
):
    now = time.monotonic() if now is None else now
    boot = boot_id() if boot is None else boot
    cpuset = sorted(current_cpuset()) if cpuset is None else sorted(cpuset)
    issuer = process_identity(grant["issuer"]["pid"]) if issuer is None else issuer
    affinity = sorted(os.sched_getaffinity(0)) if affinity is None else sorted(affinity)
    age = now - grant["observed_after_cpu_monotonic"]
    if (
        grant.get("schema") != "w1-worker-start-grant.v29"
        or not 0 <= age <= MAX_AGE_SECONDS
        or grant.get("boot_id") != boot
        or grant.get("issuer") != issuer
        or grant.get("cpuset_cpus") != cpuset
        or affinity != [grant.get("selected_cpu")]
        or grant.get("selected_cpu") not in cpuset
        or grant.get("source_sha") != source_sha
        or grant.get("input_sha256") != spec["input_sha256"]
        or grant.get("window_sha256") != digest(spec["window_path"])
        or grant.get("fresh_CPU_observation") is not True
        or grant.get("PSI_qualification_is_separate") is not True
    ):
        raise ValueError("W29_WORKER_START_ADMISSION_NOT_FRESH_OR_IDENTITY_CHANGED")
    return dict(
        schema="w1-worker-start-freshness.v29",
        age_seconds=age,
        limit_seconds=MAX_AGE_SECONDS,
        boot_id=boot,
        issuer=issuer,
        actual_affinity=affinity,
        actual_cpuset=cpuset,
        passed=True,
        historical_samples_reused=False,
    )


def verify_binding_start(binding, run, atomic_json):
    """Called before the child imports any FE stack or performs numerical work."""
    grant = binding["worker_start_grant"]
    proof = validate_grant(grant, binding["spec"], binding["receiver_source_sha"])
    # The activation deliberately clears inherited watchdog environment flags;
    # the live OS parent identity is the actual supervisor authority.
    expected_parent = os.getppid()
    if grant["issuer"]["pid"] != expected_parent:
        raise ValueError("W29_LIVE_WATCHDOG_ISSUER_IDENTITY")
    proof.update(
        actual_child=process_identity(os.getpid()),
        grant_sha256=hashlib.sha256(
            json.dumps(grant, sort_keys=True).encode()
        ).hexdigest(),
    )
    atomic_json(Path(run) / "worker_start_freshness.json", proof)
    return proof
