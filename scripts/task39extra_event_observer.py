#!/usr/bin/env python3
"""Read-only lifecycle observer for one Task39extra run.

This is deliberately outside the FEM watchdog contract.  It reads only the
fixed run files and fixed root/worker identities, emits deduplicated events,
and delegates notification to the existing one-shot notify-v2 helper.  It
never sends a signal, restarts a process, or changes a run file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_HELPER = "/home/fenics/Projects/Maxwell3D-Lab/task-control/codex-thread-notify-v2.py"
TERMINAL_STATUS = {"finished", "completed", "failed", "stopped", "terminated"}
MAJOR_STAGES = frozenset({
    "h6_original_window_and_packed_action_complete",
    "reference_volume_complete",
    "reference_symbolic_started",
    "reference_symbolic_complete",
    "reference_symbolic_resource",
    "reference_budget_evaluated",
    "reference_numeric_preflight",
    "reference_numeric_complete",
    "solve_started",
    "recovery_started",
    "checker_started",
})
TAIL_BYTES = 64 * 1024
MAX_READ_BYTES = 1024 * 1024


def _json_line(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _proc_identity(pid: int) -> dict[str, Any]:
    """Read only /proc/<pid>/stat; no command line or environment is read."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return {"state": "absent", "pid": pid}
    except OSError as exc:
        return {"state": "unreadable", "pid": pid, "error": str(exc)}
    try:
        _, rest = raw.rsplit(") ", 1)
        fields = rest.split()
        return {"state": "present", "pid": pid, "start_ticks": int(fields[19])}
    except (IndexError, ValueError) as exc:
        return {"state": "unreadable", "pid": pid, "error": str(exc)}


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    return value if isinstance(value, dict) else None, None


def _read_integer(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError):
        return None


def _hardware_snapshot(cpu: int, worker_pid: int, worker_start_ticks: int,
                       sysfs_root: Path = Path("/sys")) -> dict[str, Any]:
    """Read available sysfs side evidence; never classify or stop a run."""
    cpu_root = sysfs_root / "devices/system/cpu" / f"cpu{cpu}"
    frequency: dict[str, Any] = {}
    for name in ("scaling_cur_freq", "cpuinfo_cur_freq"):
        path = cpu_root / "cpufreq" / name
        frequency[name] = {
            "path": str(path),
            "value_khz": _read_integer(path),
            "interpretation": "sysfs side evidence; not measured busy frequency",
        }

    throttle: dict[str, int | None] = {}
    throttle_root = cpu_root / "thermal_throttle"
    try:
        throttle_paths = sorted(path for path in throttle_root.iterdir() if path.is_file())
    except OSError:
        throttle_paths = []
    for path in throttle_paths:
        throttle[path.name] = _read_integer(path)

    sensors: list[dict[str, Any]] = []
    try:
        hwmon_dirs = sorted((sysfs_root / "class/hwmon").glob("hwmon*"))
    except OSError:
        hwmon_dirs = []
    for hwmon in hwmon_dirs:
        try:
            chip = (hwmon / "name").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            chip = None
        try:
            temperature_paths = sorted(hwmon.glob("temp*_input"))
        except OSError:
            temperature_paths = []
        for path in temperature_paths:
            label_path = path.with_name(path.name.removesuffix("_input") + "_label")
            try:
                label = label_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                label = None
            sensors.append({
                "kind": "hwmon",
                "chip": chip,
                "label": label,
                "path": str(path),
                "milli_celsius": _read_integer(path),
            })
    try:
        thermal_zones = sorted((sysfs_root / "class/thermal").glob("thermal_zone*"))
    except OSError:
        thermal_zones = []
    for zone in thermal_zones:
        try:
            zone_type = (zone / "type").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            zone_type = None
        sensors.append({
            "kind": "thermal_zone",
            "chip": zone_type,
            "label": None,
            "path": str(zone / "temp"),
            "milli_celsius": _read_integer(zone / "temp"),
        })

    return {
        "cpu": cpu,
        "worker_identity": {"pid": worker_pid, "start_ticks": worker_start_ticks},
        "worker_identity_observed": _proc_identity(worker_pid),
        "sysfs_frequency": frequency,
        "thermal_throttle_counters": throttle,
        "temperature_sensors": sensors,
        "busy_frequency_mhz": None,
        "busy_frequency_status": "unknown; no APERF/MPERF/MSR measurement is made here",
        "gate_effect": "record_only; missing sensors/counters do not stop or fail the run",
    }


class Observer:
    def __init__(self, *, run_dir: Path, log_path: Path, thread: str,
                 root_pid: int, root_start_ticks: int, worker_pid: int,
                 worker_start_ticks: int, helper: str, interval: float,
                 hardware_cpu: int | None = None,
                 sysfs_root: Path = Path("/sys")) -> None:
        self.run_dir = run_dir
        self.log_path = log_path
        self.thread = thread
        self.identities = {
            "root": (root_pid, root_start_ticks),
            "worker": (worker_pid, worker_start_ticks),
        }
        self.helper = helper
        self.interval = interval
        self.hardware_cpu = hardware_cpu
        self.sysfs_root = sysfs_root
        self.offsets: dict[str, int] = {}
        self.last_rows: dict[str, dict[str, Any]] = {}
        self.seen_events: set[str] = set()
        self.pending_events: dict[str, tuple[str, dict[str, Any]]] = {}
        self.started_monotonic = time.monotonic()
        self.startup_grace = max(30.0, 2.0 * interval)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, record: dict[str, Any]) -> None:
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(_json_line({"observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), **record}) + "\n")

    def _append_rows(self, name: str) -> tuple[list[dict[str, Any]], str | None]:
        path = self.run_dir / name
        first_read = name not in self.offsets
        offset = self.offsets.get(name, 0)
        try:
            size = path.stat().st_size
            if size < offset:
                first_read = True
                offset = 0
            with path.open("rb") as stream:
                if first_read:
                    offset = max(0, size - TAIL_BYTES)
                    stream.seek(offset)
                    if offset:
                        stream.readline()  # discard the partial tail line
                        offset = stream.tell()
                else:
                    stream.seek(offset)
                data = stream.read(MAX_READ_BYTES)
        except FileNotFoundError:
            return [], "missing"
        except OSError as exc:
            return [], str(exc)
        complete_end = data.rfind(b"\n") + 1
        if complete_end == 0:
            return [], None
        self.offsets[name] = offset + complete_end
        rows: list[dict[str, Any]] = []
        for line in data[:complete_end].splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                return rows, "invalid_json_line"
            if isinstance(row, dict):
                rows.append(row)
        return rows, None

    def _notify(self, event: str, evidence: dict[str, Any]) -> dict[str, Any]:
        message = f"task39extra observer event={event} run={self.run_dir} evidence={_json_line(evidence)}"
        try:
            query = subprocess.run(
                [sys.executable, self.helper, "--thread", self.thread, "--turns"],
                text=True, capture_output=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"stage": "query", "ack": False, "error": str(exc)}
        if query.returncode != 0:
            return {"stage": "query", "ack": False, "returncode": query.returncode,
                    "stdout": query.stdout[-2000:], "stderr": query.stderr[-2000:]}
        active_turn = None
        try:
            response = json.loads(query.stdout)
            active_turn = self._find_active_turn(response)
        except json.JSONDecodeError as exc:
            return {"stage": "query", "ack": False, "error": str(exc),
                    "stdout": query.stdout[-2000:]}
        if active_turn:
            command = [sys.executable, self.helper, "--thread", self.thread,
                       "--turn", active_turn, "--message", message]
        else:
            command = [sys.executable, self.helper, "--thread", self.thread,
                       "--start", "--message", message]
        try:
            result = subprocess.run(command, text=True, capture_output=True,
                                    timeout=20, check=False)
            return {
                "query_returncode": query.returncode,
                "query_stdout": query.stdout[-2000:],
                "action": "turn" if active_turn else "start",
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:],
                "ack": result.returncode == 0,
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "query_returncode": query.returncode,
                "action": "turn" if active_turn else "start",
                "ack": False,
                "error": str(exc),
            }

    @staticmethod
    def _find_active_turn(value: Any) -> str | None:
        result = value.get("result") if isinstance(value, dict) else None
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, list):
            for item in data:
                if (isinstance(item, dict) and
                        str(item.get("status", "")).lower() in
                        {"inprogress", "in_progress", "running", "active"} and
                        item.get("id")):
                    return str(item["id"])
        return None

    def _event(self, key: str, event: str, evidence: dict[str, Any]) -> None:
        if key in self.seen_events or key in self.pending_events:
            return
        self.pending_events[key] = (event, evidence)
        self._attempt_event(key, event, evidence)

    def _attempt_event(self, key: str, event: str, evidence: dict[str, Any]) -> None:
        notification = self._notify(event, evidence)
        self._log({"kind": "notification_attempt", "event": event,
                   "evidence": evidence, "notification": notification,
                   "pending": not notification.get("ack", False)})
        if notification.get("ack", False):
            self.pending_events.pop(key, None)
            self.seen_events.add(key)
            self._log({"kind": "event_ack", "event": event, "evidence": evidence})

    def _retry_pending(self) -> None:
        for key, (event, evidence) in list(self.pending_events.items()):
            self._attempt_event(key, event, evidence)

    def _check_identity(self) -> None:
        missing: dict[str, Any] = {}
        for role, (pid, expected_ticks) in self.identities.items():
            observed = _proc_identity(pid)
            if observed.get("state") != "present":
                missing[role] = observed
            elif observed.get("start_ticks") != expected_ticks:
                missing[role] = {**observed, "expected_start_ticks": expected_ticks}
        if missing:
            self._event("identity_or_scope_changed", "identity_or_scope_changed", missing)

    def _record_hardware(self) -> None:
        if self.hardware_cpu is None:
            return
        self._log({"kind": "hardware_sample", **_hardware_snapshot(
            self.hardware_cpu, *self.identities["worker"], self.sysfs_root
        )})

    def _resource_age_seconds(self, row: dict[str, Any], path: Path) -> float | None:
        timestamp_ns = row.get("timestamp_ns")
        if isinstance(timestamp_ns, (int, float)):
            return max(0.0, (time.time_ns() - int(timestamp_ns)) / 1.0e9)
        parent_clock = row.get("parent_clock")
        if isinstance(parent_clock, dict) and isinstance(parent_clock.get("monotonic"), (int, float)):
            return max(0.0, time.monotonic() - float(parent_clock["monotonic"]))
        try:
            return max(0.0, time.time() - path.stat().st_mtime)
        except OSError:
            return None

    def _check_resources(self) -> None:
        path = self.run_dir / "watchdog" / "resources.jsonl"
        rows, error = self._append_rows("watchdog/resources.jsonl")
        if error == "missing" and time.monotonic() - self.started_monotonic > self.startup_grace:
            self._event("resources:file_missing", "resource_log_missing", {"path": str(path)})
        if error and error != "missing":
            self._event("resources:read_error:" + error, "resource_observer_read_error", {"error": error})
        if rows:
            self.last_rows["resources"] = rows[-1]
        row = self.last_rows.get("resources")
        if row is None:
            return
        readable = row.get("all_status_readable", row.get("readable", True))
        age = self._resource_age_seconds(row, path)
        stale = age is None or age > max(30.0, 2.0 * self.interval)
        if readable is False or stale:
            reason = "unreadable" if readable is False else "stale"
            self._event("resources:" + reason, "resource_samples_not_fresh", {
                "reason": reason, "sample_age_seconds": age,
                "latest": row,
            })

    def _check_stages(self) -> None:
        rows, error = self._append_rows("stages.jsonl")
        if error and error != "missing":
            self._event("stages:read_error:" + error, "stage_log_read_error", {"error": error})
        for row in rows:
            stage = row.get("stage") or row.get("phase")
            if not stage:
                continue
            stage_text = str(stage)
            if stage_text not in MAJOR_STAGES:
                continue
            kind = "p2_or_budget" if stage_text.startswith("reference_") else "stage_changed"
            self._event("stage:" + stage_text, kind, row)

    def _check_terminal(self) -> bool:
        summary, error = _read_json(self.run_dir / "run_summary.json")
        if error and error != "missing":
            self._event("summary:read_error:" + error, "run_summary_read_error", {"error": error})
        watchdog, _ = _read_json(self.run_dir / "watchdog" / "summary.json")
        status = str((summary or {}).get("status", "")).lower()
        classification = str((summary or {}).get("result_classification", "")).lower()
        watchdog_done = bool((watchdog or {}).get("descendants_cleared")) and bool(watchdog)
        terminal = status in TERMINAL_STATUS or classification in TERMINAL_STATUS or watchdog_done
        if terminal:
            evidence = {"run_summary": summary, "watchdog_summary": watchdog}
            self._event("terminal", "run_terminal", evidence)
        return terminal

    def poll_once(self) -> bool:
        self._retry_pending()
        terminal = self._check_terminal()
        if terminal:
            return "terminal" in self.seen_events
        self._check_stages()
        self._check_resources()
        self._check_identity()
        self._record_hardware()
        return False

    def run(self) -> int:
        self._log({"kind": "observer_started", "run_dir": str(self.run_dir),
                   "identities": self.identities, "interval_seconds": self.interval,
                   "hardware_cpu": self.hardware_cpu,
                   "hardware_sampling": "read-only record-only" if self.hardware_cpu is not None else None})
        while True:
            if self.poll_once():
                self._log({"kind": "observer_finished", "reason": "terminal"})
                return 0
            time.sleep(self.interval)


def _self_test() -> int:
    """Exercise routing, retry, stale detection, and terminal acknowledgement."""
    with tempfile.TemporaryDirectory(prefix="task39extra-observer-") as temp:
        root = Path(temp)
        run = root / "run"
        run.mkdir()
        sysfs = root / "sysfs"
        cpu24 = sysfs / "devices/system/cpu/cpu24"
        (cpu24 / "cpufreq").mkdir(parents=True)
        (cpu24 / "cpufreq/scaling_cur_freq").write_text("3600000\n", encoding="ascii")
        (cpu24 / "thermal_throttle").mkdir()
        (cpu24 / "thermal_throttle/core_throttle_count").write_text("0\n", encoding="ascii")
        hwmon = sysfs / "class/hwmon/hwmon0"
        hwmon.mkdir(parents=True)
        (hwmon / "name").write_text("fixture\n", encoding="utf-8")
        (hwmon / "temp1_input").write_text("52000\n", encoding="ascii")
        (hwmon / "temp1_label").write_text("Package\n", encoding="utf-8")
        (run / "stages.jsonl").write_text(
            _json_line({"stage": "reference_symbolic_complete", "elapsed_monotonic_seconds": 1.0}) + "\n",
            encoding="utf-8")
        (run / "run_summary.json").write_text(_json_line({"status": "RUNNING"}), encoding="utf-8")
        calls = root / "notify_calls.jsonl"
        state = root / "notify_state"
        helper = root / "fake_notify.py"
        helper.write_text(
            "import json,sys\n"
            f"open({str(calls)!r}, 'a').write(json.dumps(sys.argv[1:])+'\\n')\n"
            f"state={str(state)!r}\n"
            "if '--turns' in sys.argv:\n"
            " print(json.dumps({'result': {'data': [{'id': 'active-turn', 'status': 'inProgress'}]}}))\n"
            "else:\n"
            " n=int(open(state).read()) if __import__('os').path.exists(state) else 0\n"
            " open(state,'w').write(str(n+1))\n"
            " if n == 0:\n"
            "  print(json.dumps({'error': {'message': 'selftest send failure'}})); raise SystemExit(1)\n"
            " print(json.dumps({'result': {'turnId': 'active-turn'}}))\n",
            encoding="utf-8")
        identity = _proc_identity(os.getpid())
        observer = Observer(run_dir=run, log_path=root / "observer.jsonl",
            thread="selftest", root_pid=os.getpid(),
            root_start_ticks=int(identity["start_ticks"]), worker_pid=os.getpid(),
            worker_start_ticks=int(identity["start_ticks"]), helper=str(helper), interval=10.,
            hardware_cpu=24, sysfs_root=sysfs)
        assert observer.poll_once() is False
        records = [json.loads(line) for line in
                   (root / "observer.jsonl").read_text(encoding="utf-8").splitlines()]
        hardware = next(record for record in records if record.get("kind") == "hardware_sample")
        assert hardware["worker_identity"]["start_ticks"] == int(identity["start_ticks"])
        assert hardware["sysfs_frequency"]["scaling_cur_freq"]["value_khz"] == 3600000
        assert hardware["thermal_throttle_counters"]["core_throttle_count"] == 0
        assert hardware["temperature_sensors"][0]["milli_celsius"] == 52000
        assert hardware["busy_frequency_mhz"] is None
        assert hardware["gate_effect"].startswith("record_only")
        assert hardware["sysfs_frequency"]["cpuinfo_cur_freq"]["value_khz"] is None
        assert not observer.seen_events and observer.pending_events
        assert observer.poll_once() is False
        (run / "watchdog").mkdir()
        (run / "watchdog" / "resources.jsonl").write_text(
            _json_line({"timestamp_ns": time.time_ns() - 100_000_000_000,
                        "parent_clock": {"monotonic": time.monotonic() - 100.0},
                        "all_status_readable": True}) + "\n", encoding="utf-8")
        assert observer.poll_once() is False
        (run / "run_summary.json").write_text(
            _json_line({"status": "finished", "result_classification": "WORKER_FAILED"}),
            encoding="utf-8")
        assert observer.poll_once() is True
        log = (root / "observer.jsonl").read_text(encoding="utf-8").splitlines()
        calls_read = calls.read_text(encoding="utf-8").splitlines()
        actions = [json.loads(line) for line in calls_read]
        send_actions = [action for action in actions if "--turn" in action and "--turns" not in action]
        assert len(send_actions) == 4 and all("active-turn" in action for action in send_actions)
        assert all("--start" not in action for action in send_actions)
        assert sum('"kind":"notification_attempt"' in line for line in log) == 4
        assert sum('"kind":"event_ack"' in line for line in log) == 3
        print(_json_line({"status": "PASS", "event_records": 3,
                          "notification_attempts": 4,
                          "notify_send_actions": len(send_actions),
                          "active_turn_schema": "result.data[0].id/status",
                          "retry_after_failure": True, "stale_after_sampling_stop": True,
                          "terminal_ack_exit": True, "hardware_sample_pid_ticks_bound": True,
                          "missing_sensor_record_only": True,
                          "busy_frequency_unknown_not_inferred": True,
                          "pde_started": False}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--thread")
    parser.add_argument("--root-pid", type=int)
    parser.add_argument("--root-start-ticks", type=int)
    parser.add_argument("--worker-pid", type=int)
    parser.add_argument("--worker-start-ticks", type=int)
    parser.add_argument("--hardware-cpu", type=int)
    parser.add_argument("--helper", default=DEFAULT_HELPER)
    parser.add_argument("--interval", type=float, default=15.0)
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    required = (args.run_dir, args.log, args.thread, args.root_pid,
                args.root_start_ticks, args.worker_pid, args.worker_start_ticks)
    if any(value is None for value in required):
        parser.error("normal mode requires run/log/thread and fixed root/worker identities")
    if not 10.0 <= args.interval <= 30.0:
        parser.error("--interval must be between 10 and 30 seconds")
    return Observer(run_dir=args.run_dir, log_path=args.log, thread=args.thread,
        root_pid=args.root_pid, root_start_ticks=args.root_start_ticks,
        worker_pid=args.worker_pid, worker_start_ticks=args.worker_start_ticks,
        helper=args.helper, interval=args.interval, hardware_cpu=args.hardware_cpu).run()


if __name__ == "__main__":
    raise SystemExit(main())
