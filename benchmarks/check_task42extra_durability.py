"""R0: own tiny process trees only; not a numerical solver or scheduler."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from benchmarks.subreaper_watchdog import supervise
from src.runners.durable_terminal import launch_tmux
from src.runners.feinn_resources import ROOT, envelope
from src.runners.guarded_exec import ticks


def atom(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def active(pid, start):
    try:
        parts = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(parts[19]) == start and parts[0] != "Z"
    except FileNotFoundError:
        return False


def wait_for(path, seconds=10):
    end = time.monotonic() + seconds
    while not path.exists() and time.monotonic() < end:
        time.sleep(0.05)
    if not path.exists():
        raise RuntimeError("bounded dummy did not write " + str(path))


def worker(directory):
    atom(
        directory / "worker.json",
        dict(
            pid=os.getpid(),
            ppid=os.getppid(),
            start_ticks=ticks(os.getpid()),
            session=os.getsid(0),
            group=os.getpgrp(),
            cgroup=Path("/proc/self/cgroup").read_text(),
            stdout=os.readlink("/proc/self/fd/1"),
        ),
    )
    for n in range(40):
        atom(directory / "dummy_checkpoint.json", dict(committed_tick=n))
        print("dummy", n, flush=True)
        time.sleep(0.1)
    atom(directory / "done.json", dict(complete=True))


def supervisor(directory, mode):
    atom(
        directory / "supervisor.json",
        dict(pid=os.getpid(), start_ticks=ticks(os.getpid())),
    )
    command = [
        sys.executable,
        "-m",
        "src.runners.guarded_exec",
        str(os.getpid()),
        str(ticks(os.getpid())),
        sys.executable,
        "-m",
        "benchmarks.check_task42extra_durability",
        "worker",
        str(directory),
    ]

    def health():
        if mode == "monitor_failure" and (directory / "dummy_checkpoint.json").exists():
            raise RuntimeError("own injected monitoring failure")
        return {}

    result = supervise(
        command,
        directory / "supervision",
        wall_seconds=20,
        interval=0.2,
        rss_hard_limit_bytes=2 * 2**30,
        rss_warning_bytes=int(1.75 * 2**30),
        memory_envelope_provider=lambda: envelope(2 * 2**30),
        include_pss=False,
        health_check=health,
    )
    atom(directory / "dummy_summary.json", result)


def main(directory):
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for mode in ("explicit_stop", "monitor_failure", "supervisor_death"):
        case = directory / mode
        case.mkdir()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "benchmarks.check_task42extra_durability",
                "supervisor",
                str(case),
                mode,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for(case / "worker.json")
        wait_for(case / "dummy_checkpoint.json")
        identity = json.loads((case / "worker.json").read_text())
        if mode == "explicit_stop":
            os.kill(process.pid, signal.SIGTERM)
        elif mode == "supervisor_death":
            os.kill(process.pid, signal.SIGKILL)
        code = process.wait(timeout=20)
        deadline = time.monotonic() + 5
        while (
            active(identity["pid"], identity["start_ticks"])
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        if active(identity["pid"], identity["start_ticks"]):
            raise RuntimeError("own unguarded dummy survived supervisor")
        row = dict(
            case=mode,
            supervisor_exit_code=code,
            worker_identity=identity,
            worker_no_longer_running=True,
            checkpoint=json.loads((case / "dummy_checkpoint.json").read_text()),
        )
        if mode != "supervisor_death":
            row["supervision"] = json.loads((case / "dummy_summary.json").read_text())
            if not row["supervision"]["descendants_cleared"]:
                raise RuntimeError("dummy descendants were not cleared")
        else:
            row["no_finally_or_summary_guarantee"] = True
        records.append(row)
    case = directory / "startup_disconnect"
    case.mkdir()
    # A short launching process owns a pipe that is deliberately closed. The
    # isolated tmux pane carries the entire dedicated supervisor, not a bare worker.
    starter = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "benchmarks.check_task42extra_durability",
            "start",
            str(case),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    starter.stdout.close()
    starter.stderr.close()
    if starter.wait(timeout=10) != 0:
        raise RuntimeError("tmux startup/output disconnect probe failed")
    wait_for(case / "dummy_summary.json", seconds=20)
    summary = json.loads((case / "dummy_summary.json").read_text())
    if (
        summary["classification"] != "COMPLETED"
        or not summary["descendants_cleared"]
        or not (case / "done.json").exists()
    ):
        raise RuntimeError("detached bounded supervised dummy did not complete")
    records.append(
        dict(
            case="startup_disconnect_and_closed_output_pipe",
            startup_exit_code=0,
            output_closed=True,
            supervision=summary,
            terminal_identity=json.loads((case / "terminal_identity.json").read_text()),
            scope="only this simulated starter exit; all client/cgroup recycling paths not claimed",
        )
    )
    result = dict(
        schema="task42extra.durability-process-checks.v4",
        status="OWN_SYNTHETIC_LIFECYCLE_PASS",
        cases=records,
        only_own_test_subtrees_signaled=True,
        no_services_or_platform_policy_changed=True,
    )
    atom(directory / "process_checks.json", result)
    print(json.dumps(dict(status=result["status"], cases=len(records))))


if __name__ == "__main__":
    mode, location = sys.argv[1], Path(sys.argv[2])
    if mode == "worker":
        worker(location)
    elif mode == "supervisor":
        supervisor(location, sys.argv[3])
    elif mode == "start":
        launch_tmux(
            location,
            "task42extra-v4-dummy",
            [
                sys.executable,
                "-m",
                "benchmarks.check_task42extra_durability",
                "supervisor",
                str(location),
                "complete",
            ],
            ROOT,
        )
    elif mode == "check":
        main(location)
    else:
        raise ValueError("unknown lifecycle test mode")
