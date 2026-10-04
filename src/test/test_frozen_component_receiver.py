"""Receiver safety and identity tests; no mesh, FE action or factorization."""

import hashlib
import json
from pathlib import Path

import pytest

from src.runners.fresh_component_receiver import (
    DEPENDENCY, INPUT_SHA, atomic_json, load_receiver, native_command, remaining,
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
