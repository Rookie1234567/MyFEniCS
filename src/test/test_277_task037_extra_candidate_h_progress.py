"""Focused H1R.0 progress-marker tests without constructing a FE worker."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import time

import benchmarks.run_task037_extra_candidate_h as candidate_h


class _FlushBuffer(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1
        return super().flush()


class _FakeComm:
    rank = 0
    size = 1

    def allreduce(self, value, op=None):
        del op
        return value

    def gather(self, value, root=0):
        del root
        return [value]

    def bcast(self, value, root=0):
        del root
        return value


class _FakeVec:
    def __init__(self, values):
        self.array = values.copy()
        self.destroyed = False

    def duplicate(self):
        return _FakeVec(self.array * 0.0)

    def getArray(self, readonly=False):
        del readonly
        return self.array

    def set(self, value):
        self.array.fill(value)

    def copy(self, result=None):
        if result is None:
            return _FakeVec(self.array)
        result.array[...] = self.array
        return result

    def axpy(self, alpha, other):
        self.array[...] += alpha * other.array

    def norm(self):
        import numpy as np

        return float(np.linalg.norm(self.array))

    def destroy(self):
        self.destroyed = True


class _FakeReference:
    apply_count = 0

    def mult(self, matrix, source, target):
        del matrix
        self.apply_count += 1
        source.copy(result=target)


class _FakeMatrix:
    def __init__(self):
        self.calls = 0

    def mult(self, source, target):
        self.calls += 1
        source.copy(result=target)


def test_h1r_progress_marker_schema_and_flush():
    stream = _FlushBuffer()
    started = time.perf_counter() - 0.01
    candidate_h._emit_h1r_progress(
        stream,
        event="mesh_build_started",
        worker_started=started,
        rank=0,
    )
    assert stream.flush_count == 1
    record = json.loads(stream.getvalue())
    assert set(record) == {
        "schema",
        "event",
        "elapsed_wall_seconds",
        "rank",
        "rss_bytes",
        "pss_bytes",
        "uss_bytes",
        "source_label",
        "apply_count",
        "cell_count",
        "local_rows",
        "global_rows",
    }
    assert record["schema"] == candidate_h.H1R_PROGRESS_SCHEMA
    assert record["event"] == "mesh_build_started"
    assert record["rank"] == 0
    assert record["source_label"] is None
    assert record["apply_count"] is None
    assert record["cell_count"] is None
    assert record["local_rows"] is None
    assert record["global_rows"] is None
    assert record["elapsed_wall_seconds"] >= 0.0
    for field in ("rss_bytes", "pss_bytes", "uss_bytes"):
        assert record[field] is None or isinstance(record[field], int)

    candidate_h._emit_h1r_progress(
        stream,
        event="function_space_ready",
        worker_started=started,
        rank=0,
        source_label="seed_17037",
        apply_count=2,
        cell_count=7,
        local_rows=11,
        global_rows=13,
    )
    assert stream.flush_count == 2
    known = json.loads(stream.getvalue().splitlines()[1])
    assert known["source_label"] == "seed_17037"
    assert known["apply_count"] == 2
    assert known["cell_count"] == 7
    assert known["local_rows"] == 11
    assert known["global_rows"] == 13


def test_h1r_action_markers_wrap_two_candidate_applies_and_export(
    monkeypatch, tmp_path: Path
):
    import numpy as np

    monkeypatch.setattr(
        candidate_h,
        "iter_canonical_full_fe_dual_packets",
        lambda *args, **kwargs: iter(()),
        raising=False,
    )
    monkeypatch.setattr(
        candidate_h,
        "write_canonical_packet_shard",
        lambda path, packets: (
            list(packets), {"local_packet_count": 0}
        )[1],
    )
    monkeypatch.setattr(
        candidate_h,
        "canonical_shard_manifest",
        lambda **kwargs: {"global_summed_packet_count": 0},
    )

    def write_manifest(path, manifest):
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr(candidate_h, "write_canonical_manifest", write_manifest)

    comm = _FakeComm()
    function_space = SimpleNamespace(mesh=SimpleNamespace(comm=comm))
    source = _FakeVec(np.asarray([1.0 + 2.0j, -0.5 + 0.25j]))
    reference = _FakeReference()
    matrix = _FakeMatrix()
    candidate = SimpleNamespace(matrix=matrix)
    cfg = SimpleNamespace(
        wavevector=(1.0 + 0.1j, 0.5 - 0.2j, 0.25 + 0.0j),
        polarization_vector=(1.0 + 0.0j, 0.25 + 0.5j, -0.5 + 0.0j),
        incident_amplitude=1.0 + 0.25j,
    )
    stream = _FlushBuffer()

    result = candidate_h._action_record(
        reference,
        candidate,
        source,
        run_dir=tmp_path,
        label="seed_17037",
        cfg=cfg,
        function_space=function_space,
        mpc=object(),
        tolerance=1.0e-12,
        progress_writer=stream,
        progress_started=time.perf_counter() - 0.01,
        progress_rank=0,
        progress_cell_count=7,
        progress_local_rows=11,
        progress_global_rows=13,
    )

    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert events == [
        "reference_apply_started",
        "reference_apply_ready",
        "candidate_apply_1_started",
        "candidate_apply_1_ready",
        "candidate_apply_2_started",
        "candidate_apply_2_ready",
        "canonical_export_started",
        "canonical_export_ready",
    ]
    assert stream.flush_count == len(events)
    assert matrix.calls == 2
    assert reference.apply_count == 1
    assert result["candidate_repeat_equal"] is True
    assert result["deterministic"] is True
    assert result["finite"] is True
    assert result["candidate_canonical_packet_count"] == 0
