"""Actual event writer and sealed completed-rebuild recovery; no FE run."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners import neural_wave_worker as worker
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz, sha


def test_real_event_writer_complex_arrays_bool_and_reopen(tmp_path, capsys):
    worker.publish_event(tmp_path, "physical_model", dict(
        material=1.0 + 2.0j, modes=np.array([[1j, 2 - 3j]]),
        qualified=np.bool_(False), duration=np.float64(0.5),
    ))
    printed = json.loads(capsys.readouterr().out)
    reopened = json.loads((tmp_path / "events.jsonl").read_text())
    assert printed == reopened
    assert reopened["values"]["material"] == dict(real=1, imag=2)
    assert reopened["values"]["modes"][0][1] == dict(real=2, imag=-3)
    assert reopened["values"]["qualified"] is False


def test_nonfinite_event_refused_before_publish(tmp_path, capsys):
    with pytest.raises(ValueError):
        worker.publish_event(tmp_path, "bad", dict(x=np.nan))
    assert capsys.readouterr().out == ""
    assert not (tmp_path / "events.jsonl").exists()


def recovery_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    artifacts = tmp_path / "artifacts"
    monkeypatch.setattr(worker, "ARTIFACTS", artifacts)
    high = artifacts / "v30_wave_checks/moments_q60.npz"
    high.parent.mkdir(parents=True)
    high.write_bytes(b"frozen q60")
    native, moments = tmp_path / "native.bin", tmp_path / "moments.bin"
    native.write_bytes(b"frozen native")
    moments.write_bytes(b"frozen q30")
    design = tmp_path / "design.json"
    atomic_json(design, dict(files=dict(
        native=dict(path="native.bin"), moments_q30=dict(path="moments.bin"))))
    monkeypatch.setattr(worker, "DESIGN", design)
    source, directory, destination = (tmp_path / n for n in ("source", "model", "out"))
    for path in (source, directory / "basis", destination):
        path.mkdir(parents=True)
    c = np.array([1 + 2j, 3 - 4j, 0.2j], dtype=np.complex128)
    atomic_npz(directory / "basis/state.npz", c=c)
    boundary = dict(state=dict(path="state.npz", sha256=sha(directory / "basis/state.npz")))
    atomic_json(directory / "basis/committed.json", boundary)
    atomic_npz(source / "rebuild.npz", c30=c, c60=c + 1e-15, saved=c)
    receipt = dict(
        schema="neural-wave.completed-rebuild-recovery.v1",
        native_sha256=sha(native), moments_q30_sha256=sha(moments), moments_q60_sha256=sha(high),
        original_verifier_source_sha="79f363981765876e7020ac09cec326e8ba7e656e",
        records=dict(route=dict(file="rebuild.npz", sha256=sha(source / "rebuild.npz"),
            committed_sha256=sha(directory / "basis/committed.json"))),
    )
    atomic_json(source / "completed_rebuild_recovery.json", receipt)
    action = SimpleNamespace(size=3, a=dict(masters=np.arange(3)))
    packet = dict(master_native_rows=np.arange(3))
    return destination, source, directory, action, packet, receipt, c


def test_completed_pair_reused_without_forward_or_reference(tmp_path, monkeypatch):
    out, source, directory, action, packet, _, c = recovery_fixture(tmp_path, monkeypatch)
    actual, high, saved, boundary = worker.recover_rebuild(out, source, "route", directory, action, packet)
    np.testing.assert_array_equal(actual, c)
    np.testing.assert_array_equal(saved, c)
    np.testing.assert_array_equal(high, c + 1e-15)
    assert boundary["state"]["path"] == "state.npz"
    assert sha(out / "rebuild.npz") == sha(source / "rebuild.npz")


@pytest.mark.parametrize("kind", ["file", "source", "saved", "missing_q60", "master"])
def test_changed_partial_or_cross_state_rebuild_refused(tmp_path, monkeypatch, kind):
    out, source, directory, action, packet, receipt, c = recovery_fixture(tmp_path, monkeypatch)
    if kind == "file":
        with (source / "rebuild.npz").open("ab") as stream:
            stream.write(b"changed")
    elif kind == "source":
        receipt["original_verifier_source_sha"] = "other"
    elif kind in ("saved", "missing_q60"):
        data = dict(c30=c, saved=c + (1 if kind == "saved" else 0))
        if kind == "saved":
            data["c60"] = c
        atomic_npz(source / "rebuild.npz", **data)
        receipt["records"]["route"]["sha256"] = sha(source / "rebuild.npz")
    else:
        packet["master_native_rows"] = np.arange(3)[::-1]
    atomic_json(source / "completed_rebuild_recovery.json", receipt)
    with pytest.raises(ValueError):
        worker.recover_rebuild(out, source, "route", directory, action, packet)
    assert not (out / "rebuild.npz").exists()
