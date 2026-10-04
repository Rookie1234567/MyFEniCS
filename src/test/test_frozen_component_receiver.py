"""Receiver safety and identity tests; no mesh, FE action or factorization."""

import hashlib
import json
from pathlib import Path

import pytest

from src.runners.fresh_component_receiver import (
    DEPENDENCY, INPUT_SHA, atomic_json, load_receiver, native_command, remaining,
    WORKER_SHA, bind_own_terminal_core, set_own_low_priority,
)
from src.runners.frozen_source_snapshot import validate_manifest, verify_snapshot


def fixture(tmp_path):
    (tmp_path / "src").mkdir()
    data = b"def unchanged_component():\n    return 1\n"
    (tmp_path / "src/component.py").write_bytes(data)
    return {"schema": "frozen-component-source.v1", "commit": DEPENDENCY,
            "files": [{"path": "src/component.py", "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest()}]}


def test_exact_source_bytes_and_no_unbound_members(tmp_path):
    record = fixture(tmp_path)
    assert verify_snapshot(record, tmp_path)["verified"]
    (tmp_path / "unexpected.py").write_text("new algorithm")
    with pytest.raises(ValueError, match="extra"):
        verify_snapshot(record, tmp_path)


def test_changed_or_missing_source_rejected(tmp_path):
    record = fixture(tmp_path)
    member = tmp_path / "src/component.py"
    member.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify_snapshot(record, tmp_path)
    member.unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_snapshot(record, tmp_path)


@pytest.mark.parametrize("path", ["/tmp/escape.py", "../escape.py", "a/../escape.py"])
def test_escaping_manifest_rejected(tmp_path, path):
    record = fixture(tmp_path)
    record["files"][0]["path"] = path
    with pytest.raises(ValueError, match="escapes"):
        validate_manifest(record)


def test_symlink_and_duplicate_binding_rejected(tmp_path):
    record = fixture(tmp_path)
    row = record["files"][0]
    record["files"].append(dict(row))
    with pytest.raises(ValueError, match="duplicate"):
        validate_manifest(record)
    record["files"].pop()
    (tmp_path / "src/link.py").symlink_to("component.py")
    with pytest.raises(ValueError, match="symlinked"):
        verify_snapshot(record, tmp_path)


def test_only_exact_component_input_admitted(tmp_path):
    path = tmp_path / "receiver.dat"
    original = ('receiver_schema = 1\ncomponent = "fresh_c1_same80_p6"\n'
                'mode = "w0"\n'
                f'dependency_commit = "{DEPENDENCY}"\ninput_sha256 = "{INPUT_SHA}"\n')
    path.write_text(original)
    assert load_receiver(path)["mode"] == "w0"
    path.write_text(original.replace('mode = "w0"', 'mode = "w1"'))
    with pytest.raises(ValueError, match="frozen W0"):
        load_receiver(path)
    path.write_text(original + 'memory_limit_gib = 100\n')
    with pytest.raises(ValueError, match="fields"):
        load_receiver(path)


def test_ordinary_input_not_reclassified(tmp_path):
    path = tmp_path / "ordinary.dat"
    path.write_text('schema_version = 1\nmodel_id = "ordinary"\n')
    assert load_receiver(path) is None


def test_monotonic_deadline_never_renewed():
    window = {"schema": "task42extra.w0-receiver-window.v1", "budget_seconds": 14400,
              "old_main_window_reset": False, "deadline_monotonic": 500}
    assert remaining(window, 100) == 400
    assert remaining(window, 501) == -1
    window["old_main_window_reset"] = True
    with pytest.raises(ValueError):
        remaining(window, 100)


def test_single_shell_activation_and_original_supervision(tmp_path):
    command = native_command(tmp_path / "source", tmp_path / "run", "2030-01-01T01:00:00Z", False)
    text = command[-1]
    assert command[:2] == ["/bin/bash", "-c"]
    assert text.index("qualify_imports_only.py") < text.index("activate_native_complex.sh")
    assert "--supervised" in text and "--worker " not in text
    assert "OMP_NUM_THREADS=1" in text and "PYTHONDONTWRITEBYTECODE=1" in text
    assert "--total-deadline-utc 2030-01-01T01:00:00Z" in text
    assert "--control-smoke" not in text
    assert "--control-smoke" in native_command(tmp_path, tmp_path, "2030-01-01T01:00:00Z", True)[-1]


def test_atomic_saved_record_is_complete_and_readable(tmp_path):
    path = tmp_path / "record.json"
    atomic_json(path, {"old": 1})
    atomic_json(path, {"complete": [1, 2, 3]})
    assert json.loads(path.read_text()) == {"complete": [1, 2, 3]}
    assert not Path(str(path) + ".tmp").exists()


def test_saved_checker_binds_exact_completed_worker(tmp_path):
    path = tmp_path / "check.dat"
    base = ('receiver_schema = 1\ncomponent = "fresh_c1_same80_p6"\nmode = "saved_check"\n'
            f'dependency_commit = "{DEPENDENCY}"\ninput_sha256 = "{INPUT_SHA}"\n')
    path.write_text(base + f'worker_report_sha256 = "{WORKER_SHA}"\n')
    assert load_receiver(path)["mode"] == "saved_check"
    path.write_text(base + 'worker_report_sha256 = "wrong"\n')
    with pytest.raises(ValueError, match="unique frozen"):
        load_receiver(path)
    text = native_command(tmp_path, tmp_path, "2030-01-01T01:00:00Z", False, saved_check=True)[-1]
    assert "saved_component_checker.py" in text and WORKER_SHA in text
    assert "--supervised" not in text and "--worker " not in text


def test_tracked_saved_checker_input_uses_public_validation():
    import subprocess
    import sys
    from src.runners.fresh_component_receiver import ROOT

    result = subprocess.run([
        sys.executable, str(ROOT / "scripts/run_case.py"), "--validate-only",
        str(ROOT / "input/task042extra_feinn_5nm/v24_w0_saved_check.dat"),
    ], capture_output=True, text=True, check=True)
    record = json.loads(result.stdout)
    assert record["mode"] == "saved_check" and record["worker_report_sha256"] == WORKER_SHA


def test_pinned_observer_compensation_keeps_external_work_and_other_cores():
    from src.runners.task042_shared import compensate_pinned_observer, spare_cores

    before = {1: (0,) * 8}
    after = {1: (100, 0, 0, 0, 0, 0, 0, 0)}
    busy = {1: .40, 24: 1.0}
    adjusted, proof = compensate_pinned_observer(busy, before, after, 1, .38, 100)
    assert abs(adjusted[1] - .04) < 1e-15 and adjusted[24] == 1
    assert busy[1] == .40 and proof["subtracted_ticks"] == 36
    topology = [{"cpu": 1, "siblings": [1]}]
    neighbors = [{"threads": [{"tid": 9, "affinity": [1], "cpu": 1}]}]
    assert spare_cores(topology, neighbors, adjusted, {}) == []
    assert spare_cores(topology, [], adjusted, {}) == [1]


def test_only_recorded_second_saved_checker_launch_allowed(tmp_path):
    from src.runners.fresh_component_receiver import ROOT

    path = ROOT / "input/task042extra_feinn_5nm/v24_w0_saved_check_repair.dat"
    record = load_receiver(path)
    assert record["repair_attempt"] == 2
    altered = tmp_path / "altered.dat"
    altered.write_text(path.read_text().replace("repair_attempt = 2", "repair_attempt = 3"))
    with pytest.raises(ValueError, match="second checker"):
        load_receiver(altered)


def test_priority_only_lowers_self(monkeypatch):
    import src.runners.fresh_component_receiver as module
    actions = []
    monkeypatch.setattr(module.os, "getpid", lambda: 123)
    monkeypatch.setattr(module.os, "getpriority", lambda *_: 12)
    monkeypatch.setattr(module.os, "setpriority", lambda *args: actions.append(args))
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kw: actions.append(command))
    assert set_own_low_priority()["nice"] == 12
    assert actions == [(module.os.PRIO_PROCESS, 0, 12), ["ionice", "-c", "3", "-p", "123"]]


def terminal_fixture(tmp_path, monkeypatch):
    import src.runners.fresh_component_receiver as module
    terminal = {"server": {"pid": 42, "start_ticks": 100}, "pane": {"pid": 43, "start_ticks": 101},
                "socket": str(tmp_path / "own.sock")}
    for row in (terminal["server"], terminal["pane"]):
        path = tmp_path / str(row["pid"])
        path.mkdir()
        fields = ["0"] * 20
        fields[19] = str(row["start_ticks"])
        (path / "stat").write_text(f'{row["pid"]} (own) ' + " ".join(fields))
    (tmp_path / "42/cmdline").write_bytes(b"tmux\0-S\0" + str(tmp_path / "own.sock").encode() + b"\0")
    monkeypatch.setattr(module.os, "getpid", lambda: 43)
    monkeypatch.setattr(module.os, "getppid", lambda: 42)
    monkeypatch.setattr(module.os, "getpriority", lambda *_: 10)
    monkeypatch.setattr(module.os, "sched_getaffinity", lambda *_: {5})
    actions = []
    monkeypatch.setattr(module.os, "setpriority", lambda *a: actions.append(("priority", a)))
    monkeypatch.setattr(module.os, "sched_setaffinity", lambda *a: actions.append(("affinity", a)))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: actions.append(("io", a)))
    return terminal, actions


def test_terminal_affinity_targets_only_bound_own_parent(tmp_path, monkeypatch):
    terminal, actions = terminal_fixture(tmp_path, monkeypatch)
    result = bind_own_terminal_core(terminal, 5, proc_root=tmp_path)
    assert result["neighbor_changes"] == 0 and result["server_affinity"] == [5]
    assert ("affinity", (42, {5})) in actions


@pytest.mark.parametrize("corruption", ["parent", "birth", "socket"])
def test_foreign_or_reused_terminal_rejected_before_changes(tmp_path, monkeypatch, corruption):
    terminal, actions = terminal_fixture(tmp_path, monkeypatch)
    if corruption == "parent":
        terminal["server"]["pid"] = 44
    elif corruption == "birth":
        terminal["server"]["start_ticks"] = 999
    else:
        terminal["socket"] = str(tmp_path / "other.sock")
    with pytest.raises(ValueError):
        bind_own_terminal_core(terminal, 5, proc_root=tmp_path)
    assert actions == []
