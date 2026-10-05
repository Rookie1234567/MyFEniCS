"""Task042-only shared-workstation admission and foreground subreaper adapter.

The user's 2026-09-28 authorization supersedes only Task042's heavy exclusivity.
Never inspects another task's smaps, acquires its lock, or sends it a signal.
"""

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.subreaper_watchdog import memory_envelope, supervise
from src.io.task042_profile import ROOT, TASK042_PROFILES

HARD = 16 * 2**30
WARNING = 12 * 2**30
GROWTH = 128 * 2**30
ARTIFACTS = ROOT / "benchmarks/artifacts/task042"


def write_json(path, value):
    def convert(item):
        if isinstance(item, complex):
            return {"real": float(item.real), "imag": float(item.imag)}
        if hasattr(item, "tolist"):
            return item.tolist()
        if hasattr(item, "item"):
            return item.item()
        raise TypeError(type(item).__name__)

    path.write_text(
        json.dumps(
            value, ensure_ascii=False, indent=2, allow_nan=False, default=convert
        )
        + "\n"
    )


def proc_stats():
    result = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            result[int(entry.name)] = {
                "ppid": int(fields[1]),
                "start_ticks": int(fields[19]),
                "ticks": int(fields[11]) + int(fields[12]),
                "cpu": int(fields[36]),
            }
        except (OSError, ValueError, IndexError):
            continue
    return result


def details(pid, stat):
    path = Path("/proc") / str(pid)
    status = dict(
        line.split(":", 1)
        for line in (path / "status").read_text().splitlines()
        if ":" in line
    )
    threads = []
    for entry in (path / "task").iterdir():
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            threads.append(
                {
                    "tid": int(entry.name),
                    "start_ticks": int(fields[19]),
                    "affinity": sorted(os.sched_getaffinity(int(entry.name))),
                    "cpu": int(fields[36]),
                }
            )
        except (OSError, ValueError, IndexError):
            continue
    # Save only source/input path arguments, never arbitrary arguments or environment secrets.
    paths = [
        word
        for word in (path / "cmdline").read_bytes().decode(errors="replace").split("\0")
        if word.endswith((".py", ".dat", "phase.json"))
    ]
    phase_path = None
    try:
        for item in (path / "environ").read_bytes().split(b"\0"):
            if item.startswith(b"PHYSICAL_WATCHDOG_PHASE_PATH="):
                phase_path = item.split(b"=", 1)[1].decode()
                break
    except OSError:
        pass
    return dict(
        pid=pid,
        **stat,
        name=status["Name"].strip(),
        state=status["State"].strip(),
        rss_bytes=int(status.get("VmRSS", "0 kB").split()[0]) * 1024,
        swap_bytes=int(status.get("VmSwap", "0 kB").split()[0]) * 1024,
        affinity=sorted(os.sched_getaffinity(pid)),
        threads=threads,
        source_input_paths=paths,
        public_phase_path=phase_path,
    )


def shared_envelope():
    env = memory_envelope()
    reserve = max(128 * 2**30, int(0.10 * env["effective_total_bytes"]))
    env.update(
        system_reserve_bytes=reserve,
        neighbor_growth_allowance_bytes=GROWTH,
        reserve_bytes=reserve + GROWTH,
        launch_cap_bytes=min(HARD, env["effective_available_bytes"] - reserve - GROWTH),
        planning_cap_bytes=HARD,
        shared_workstation=True,
    )
    return env


def pressure():
    rows = {}
    for line in Path("/proc/pressure/memory").read_text().splitlines():
        name, *fields = line.split()
        rows[name] = {
            key: float(value) for key, value in (word.split("=") for word in fields)
        }
    return rows


def _cpu_ticks():
    return {
        int(fields[0][3:]): tuple(map(int, fields[1:9]))
        for line in Path("/proc/stat").read_text().splitlines()
        if (fields := line.split())
        and fields[0].startswith("cpu")
        and fields[0][3:].isdigit()
    }


def _thread_ticks():
    result = {}
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            for thread in (process / "task").iterdir():
                try:
                    fields = (thread / "stat").read_text().rsplit(")", 1)[1].split()
                    result[int(thread.name)] = (
                        int(fields[19]),
                        int(fields[11]) + int(fields[12]),
                    )
                except (OSError, ValueError, IndexError):
                    pass
        except OSError:
            pass
    return result


def spare_cores(topology, neighbors, cpu_busy_fraction, thread_deltas):
    """V3: reserve narrow affinities; exclude active wide threads and busy CPUs.

    A sleeping wide controller's last PSR is not a reservation of that core.
    Wide controllers may migrate later; this is admission, not zero-impact proof.
    """
    excluded = {cpu for cpu, fraction in cpu_busy_fraction.items() if fraction > 0.05}
    for row in neighbors:
        for thread in row["threads"]:
            if len(thread["affinity"]) <= 16:
                excluded.update(thread["affinity"])
            elif thread_deltas.get(thread["tid"], 1) > 0:
                excluded.add(thread["cpu"])
    return [t["cpu"] for t in topology if not set(t["siblings"]) & excluded]


def compensate_pinned_observer(busy, before, after, cpu, cpu_seconds, ticks_per_second):
    """Subtract only measured own CPU work, with two ticks kept conservatively."""
    elapsed_ticks = max(sum(after[cpu]) - sum(before[cpu]), 1)
    own_ticks = max(0, int(cpu_seconds * ticks_per_second) - 2)
    adjusted = dict(busy)
    adjusted[cpu] = max(0.0, busy[cpu] - own_ticks / elapsed_ticks)
    return adjusted, {
        "cpu": cpu,
        "own_cpu_seconds": cpu_seconds,
        "subtracted_ticks": own_ticks,
        "retained_safety_ticks": 2,
        "scope": "this single-thread pinned observer only",
    }


def audit(
    *,
    observed_activity=False,
    compensate_self=False,
    candidate_scope=None,
    observation_sink=None,
):
    """Two short CPU samples; include worker parents, siblings and descendants."""
    before = proc_stats()
    own_affinity = sorted(os.sched_getaffinity(0))
    allowed = own_affinity
    if candidate_scope is not None:
        from src.runners.w1_admission_scope import validate_scope

        allowed = validate_scope(candidate_scope)
    if compensate_self and (
        not observed_activity
        or len(own_affinity) != 1
        or len(list(Path("/proc/self/task").iterdir())) != 1
    ):
        raise ValueError("self compensation requires a single-thread pinned observer")
    own_cpu_before = time.process_time()
    cpu_before = _cpu_ticks() if observed_activity else None
    threads_before = _thread_ticks() if observed_activity else None
    started = time.monotonic()
    time.sleep(1)
    after = proc_stats()
    cpu_after = _cpu_ticks() if observed_activity else None
    own_cpu_seconds = time.process_time() - own_cpu_before
    threads_after = _thread_ticks() if observed_activity else None
    interval = time.monotonic() - started
    ticks_per_s = os.sysconf("SC_CLK_TCK")
    busy = set()
    for pid, s in after.items():
        if (
            pid in before
            and before[pid]["start_ticks"] == s["start_ticks"]
            and (s["ticks"] - before[pid]["ticks"]) / ticks_per_s / interval > 0.15
        ):
            busy.add(pid)
        try:
            p = Path("/proc") / str(pid)
            name = (p / "comm").read_text().strip()
            if (
                name.startswith("python")
                and int((p / "statm").read_text().split()[1])
                * os.sysconf("SC_PAGE_SIZE")
                > 256 * 2**20
            ):
                busy.add(pid)
        except (OSError, ValueError):
            pass
    busy.discard(os.getpid())
    # The inherited Task39 observer is a separate session; do not omit it
    # merely because its current CPU/RSS is small. Match start identity.
    if after.get(341987, {}).get("start_ticks") == 17219061:
        busy.add(341987)
    selected = set(busy)
    for pid in list(busy):
        parent = after[pid]["ppid"]
        while parent not in (0, 1) and parent in after:
            try:
                name = Path(f"/proc/{parent}/comm").read_text().strip()
            except OSError:
                break
            if not (
                name.startswith("python")
                or name
                in ("mpiexec", "pt_elastic", "bash", "timeout", "nice", "ionice")
            ):
                break
            selected.add(parent)
            parent = after[parent]["ppid"]
    # Include data loaders and supervisor siblings, even if asleep in the sample.
    changed = True
    while changed:
        old = len(selected)
        selected.update(pid for pid, s in after.items() if s["ppid"] in selected)
        changed = len(selected) != old
    selected.discard(os.getpid())
    rows = []
    excluded = set()
    for pid in sorted(selected):
        try:
            row = details(pid, after[pid])
            rows.append(row)
            for thread in row["threads"]:
                # A wide migrating control process is recorded, not treated as a busy worker on every core.
                excluded.update(
                    thread["affinity"]
                    if len(thread["affinity"]) <= 16
                    else [thread["cpu"]]
                )
        except (OSError, ValueError):
            continue
    topology = []
    for cpu in allowed:
        path = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        siblings_text = (path / "thread_siblings_list").read_text().strip()
        siblings = set()
        for item in siblings_text.split(","):
            pair = item.split("-")
            siblings.update(range(int(pair[0]), int(pair[-1]) + 1))
        topology.append(
            {
                "cpu": cpu,
                "core": int((path / "core_id").read_text()),
                "socket": int((path / "physical_package_id").read_text()),
                "siblings": sorted(siblings),
            }
        )
    candidates = [t["cpu"] for t in topology if not set(t["siblings"]) & excluded]
    cpu_busy_fraction = {}
    raw_cpu_busy_fraction = {}
    self_compensation = None
    thread_deltas = {}
    if observed_activity:
        for cpu, first in cpu_before.items():
            last = cpu_after[cpu]
            elapsed = max(sum(last) - sum(first), 1)
            idle = last[3] - first[3] + last[4] - first[4]
            cpu_busy_fraction[cpu] = 1.0 - idle / elapsed
        raw_cpu_busy_fraction = dict(cpu_busy_fraction)
        if compensate_self:
            if sorted(os.sched_getaffinity(0)) != own_affinity:
                raise ValueError("pinned observer affinity changed during the sample")
            own = os.getpid()
            matching = (
                own in threads_before
                and own in threads_after
                and threads_before[own][0] == threads_after[own][0]
                and own in before
                and own in after
                and before[own]["start_ticks"] == after[own]["start_ticks"]
            )
            if candidate_scope is None:
                cpu_busy_fraction, self_compensation = compensate_pinned_observer(
                    cpu_busy_fraction,
                    cpu_before,
                    cpu_after,
                    own_affinity[0],
                    own_cpu_seconds,
                    ticks_per_s,
                )
            elif matching:
                measured = min(
                    own_cpu_seconds,
                    (threads_after[own][1] - threads_before[own][1]) / ticks_per_s,
                )
                cpu_busy_fraction, self_compensation = compensate_pinned_observer(
                    cpu_busy_fraction,
                    cpu_before,
                    cpu_after,
                    own_affinity[0],
                    measured,
                    ticks_per_s,
                )
                self_compensation["identity_matched"] = True
            else:
                self_compensation = {
                    "identity_matched": False,
                    "subtracted_ticks": 0,
                    "reason": "UNKNOWN_UNMATCHED_SELF_COUNTERS",
                }
        thread_deltas = {
            tid: last[1] - threads_before[tid][1]
            for tid, last in threads_after.items()
            if tid in threads_before and last[0] == threads_before[tid][0]
        }
        candidates = spare_cores(topology, rows, cpu_busy_fraction, thread_deltas)
    failures = []
    if not candidates:
        failures.append(
            "No audited unoccupied physical core; do not overlap a busy worker/SMT sibling"
        )
    env = shared_envelope()
    if env["launch_cap_bytes"] < HARD:
        failures.append(
            "Insufficient reserve + neighbor growth allowance + Task042 hard budget"
        )
    disk = shutil.disk_usage(ROOT).free
    if disk < 50 * 2**30:
        failures.append("Disk headroom below 50 GiB")
    psi = pressure()
    if psi["some"]["avg10"] >= 1.0 or psi["full"]["avg10"] >= 0.1:
        failures.append("Memory pressure already present")
    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,compute_mode,utilization.gpu,memory.used,memory.total",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    from benchmarks.task034_wsl_resources import current_cgroup_path

    cg = current_cgroup_path()
    ancestors = []
    parent = cg
    while parent.is_relative_to("/sys/fs/cgroup"):
        ancestors.append(
            {
                "path": str(parent),
                **{
                    name: (parent / name).read_text().strip()
                    for name in (
                        "memory.max",
                        "memory.current",
                        "memory.high",
                        "memory.swap.max",
                    )
                    if (parent / name).is_file()
                },
            }
        )
        if parent == Path("/sys/fs/cgroup"):
            break
        parent = parent.parent
    cgroup = {
        "path": str(cg),
        "delegated_writable": os.access(cg / "cgroup.procs", os.W_OK),
        "ancestors": ancestors,
        "implementation": "process-tree sampled enforcement; no kernel cgroup limit claimed",
    }
    result = {
        "schema": "task042.shared-resource-baseline.v2",
        "utc": datetime.now(timezone.utc).isoformat(),
        "cpu": candidates[0] if candidates else None,
        "candidate_cpus": candidates,
        "admission_policy": "V3 observed CPU/thread activity"
        if observed_activity
        else "V2 conservative last-PSR",
        "cpu_busy_fractions": cpu_busy_fraction,
        "raw_cpu_busy_fractions": raw_cpu_busy_fraction,
        "pinned_observer_self_compensation": self_compensation,
        "candidate_scope": candidate_scope,
        "allowed_candidate_cpus": allowed,
        "observer_affinity": own_affinity,
        "sample_interval_seconds": interval,
        "cpu_counter_before": cpu_before,
        "cpu_counter_after": cpu_after,
        "failures": failures,
        "thread_delta_ticks": thread_deltas,
        "topology": topology,
        "neighbor_processes": rows,
        "memory": env,
        "memory_pressure": psi,
        "disk_free_bytes": disk,
        "cgroup": cgroup,
        "gpu_snapshot": gpu.stdout.strip(),
        "gpu_returncode": gpu.returncode,
        "route": "CPU-only; no GPU allocation",
        "performance_identity": "shared-workstation",
        "migration_caveat": "Wide supervisor affinities retained; observed cores excluded. No claim of zero interference.",
    }
    if candidate_scope is not None or observation_sink is not None:
        from src.runners.w1_admission_scope import exclusion_reasons

        result["per_core_exclusion_reasons"] = exclusion_reasons(
            topology, rows, cpu_busy_fraction, thread_deltas
        )
    if observation_sink is not None:
        observation_sink(result)
    if failures:
        raise RuntimeError(failures[0])
    return result


class SharedHealth:
    def __init__(self, directory, neighbors=()):
        self.directory = directory
        self.neighbors = list(neighbors)
        self.last = 0.0
        self.pressure_count = 0
        self.result = {}

    def __call__(self):
        if time.monotonic() - self.last < 5.0:
            return self.result
        self.last = time.monotonic()
        psi = pressure()
        disk = shutil.disk_usage(ROOT).free
        payload = sum(p.stat().st_size for p in ARTIFACTS.rglob("*") if p.is_file())
        pressured = psi["some"]["avg10"] >= 1.0 or psi["full"]["avg10"] >= 0.1
        self.pressure_count = self.pressure_count + 1 if pressured else 0
        stop = self.pressure_count >= 3 or disk < 50 * 2**30 or payload > 20 * 2**30
        neighbor_samples = []
        for n in self.neighbors:
            try:
                fields = (
                    Path(f"/proc/{n['pid']}/stat").read_text().rsplit(")", 1)[1].split()
                )
                if int(fields[19]) != n["start_ticks"]:
                    continue
                phase = None
                if n.get("public_phase_path"):
                    q = Path(n["public_phase_path"])
                    if q.is_file() and q.stat().st_size < 65536:
                        phase = json.loads(q.read_text())
                neighbor_samples.append(
                    {
                        "pid": n["pid"],
                        "start_ticks": n["start_ticks"],
                        "cpu_ticks": int(fields[11]) + int(fields[12]),
                        "cpu": int(fields[36]),
                        "phase": phase,
                    }
                )
            except (OSError, ValueError):
                continue
        self.result = {
            "memory_pressure": psi,
            "pressure_consecutive_samples": self.pressure_count,
            "disk_free_bytes": disk,
            "artifact_bytes": payload,
            "neighbor_short_stage_observations": neighbor_samples,
            "stop_reason": "RESOURCE_CONTROLLED_STOP" if stop else None,
        }
        with (self.directory / "shared_health.jsonl").open("a") as stream:
            stream.write(json.dumps(self.result) + "\n")
        return self.result


def launch(specification):
    if Path.cwd().resolve() != ROOT or os.environ.get("TASK042_ACTIVATION") != "1":
        raise RuntimeError("Task042 local activation required")
    if (
        subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
        != "task42_neural_coarse_inverse"
    ):
        raise RuntimeError("Wrong execution branch")
    status = subprocess.check_output(["git", "status", "--porcelain"], text=True)
    if status:
        raise RuntimeError("Formal Task042 stage requires clean committed source")
    profile = specification.solver["preconditioner"]
    stage = TASK042_PROFILES[profile]
    expected_mode = "ml" if stage in ("F3-train", "V6-ML-INTERFACE") else "fe"
    if stage.startswith("V7-"):
        expected_mode = specification.derived["environment_mode"]
        from src.runners.neural_fe_continuation import budget_snapshot

        remaining_budget = budget_snapshot()["remaining_seconds"]
        if remaining_budget <= 0:
            raise RuntimeError("V6+V7 cumulative numerical budget exhausted")
    if os.environ.get("TASK042_ENV_MODE") != expected_mode:
        raise RuntimeError(
            f"Task042 {stage} requires independent {expected_mode} environment"
        )
    lock_path = ROOT / "tmp/task042/task042_shared.lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        baseline = audit(
            observed_activity=stage in ("V3-reuse", "V3-overlap")
            or stage.startswith(("V4-", "V5-", "V6-", "V7-"))
        )
        os.sched_setaffinity(0, {baseline["cpu"]})
        os.nice(10)
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=True)
        name = (
            specification.identity["run_id"]
            + "_"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        directory = ROOT / "results/task042" / name
        directory.mkdir()
        write_json(directory / "resource_baseline.json", baseline)
        write_json(directory / "resolved_config.json", specification.as_jsonable())
        (directory / "input_original.dat").write_bytes(specification.raw_input_bytes)
        source = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
        state = {
            "source_sha": source,
            "git_status": status,
            "stage": stage,
            "formal_pde": False,
            "formal_fe_stage": expected_mode == "fe",
            "input_sha256": specification.input_sha256,
            "physical_model_sha256": specification.physical_model_sha256,
            "shared_workstation": True,
            "cpu": baseline["cpu"],
            "mpi_size": 1,
            "math_threads": 1,
            "user_authorization": "2026-09-28 Task042 controlled parallel CPU stages; replaces only Task042 §2.3 exclusivity",
            "lock": str(lock_path),
            "nice": os.getpriority(os.PRIO_PROCESS, 0),
            "io_priority": subprocess.check_output(
                ["ionice", "-p", str(os.getpid())], text=True
            ).strip(),
        }
        if stage.startswith("V6-"):
            state.update(
                physical_model_complete=False,
                physical_operator_sha256=None,
                physical_hash_meaning="unresolved material-blocked design only",
                material_status="MATERIAL_0P7NM_BLOCKED",
                operator_constructed=False,
            )
        if stage.startswith("V7-"):
            state.update(
                physical_model_complete=specification.derived[
                    "physical_model_complete"
                ],
                physical_operator_sha256=specification.derived[
                    "physical_operator_sha256"
                ],
                physical_hash_meaning=specification.derived["identity_hash_meaning"],
                material_status="MATERIAL_READY_USER_SUPPLIED",
                formal_pde=stage != "V7-M0",
            )
        write_json(directory / "run_manifest.json", state)
        for filename, text in (
            ("source_sha.txt", source),
            ("input_sha256.txt", specification.input_sha256),
            ("physical_model_sha256.txt", specification.physical_model_sha256),
        ):
            (directory / filename).write_text(text + "\n")
        command = [
            sys.executable,
            "-m",
            "src.runners.task042_training"
            if stage == "F3-train"
            else "src.runners.neural_fe_interface"
            if stage.startswith("V6-")
            else "src.runners.neural_fe_continuation"
            if stage.startswith("V7-")
            else "src.runners.task042_experiment",
            str(specification.source_path),
            str(directory),
        ]
        result = supervise(
            command,
            directory / "supervision",
            wall_seconds=min(
                specification.execution["timeout_seconds"], remaining_budget
            )
            if stage.startswith("V7-")
            else 600
            if stage.startswith("V6-")
            else 10800,
            interval=0.5,
            source_state=state,
            worker_environment={"TASK042_WATCHDOG_PARENT_PID": str(os.getpid())},
            hard_stop_immediate=True,
            rss_hard_limit_bytes=HARD,
            rss_warning_bytes=WARNING,
            memory_envelope_provider=shared_envelope,
            health_check=SharedHealth(directory, baseline["neighbor_processes"]),
            include_pss=False,
            resource_stop_policy="legacy",
            stop_on_global_swap=False,
        )
        result.update(directory=str(directory), stage=stage, shared_workstation=True)
        write_json(directory / "run_summary.json", result)
        if stage.startswith("V4-"):
            from src.io.task042_v4_gate import publish

            publish(stage, directory)
        if stage.startswith("V5-"):
            from src.io.task042_v4_gate import publish

            index = ROOT / "tmp/task042/v5/stage_index.json"
            index.parent.mkdir(parents=True, exist_ok=True)
            publish(stage, directory, index_file=index)
        return {
            key: result[key]
            for key in (
                "directory",
                "stage",
                "classification",
                "leader_exit_code",
                "descendants_cleared",
                "elapsed_seconds",
                "sampled_process_tree_rss_peak_bytes",
                "sampled_process_tree_swap_peak_bytes",
                "shared_workstation",
            )
        }
