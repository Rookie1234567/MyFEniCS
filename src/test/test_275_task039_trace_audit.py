from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import src.coupling.hybrid_internal_modes as hybrid_modes
from benchmarks.task039_trace_audit import write_trace_audit_capture


def _capture_fixture() -> dict[str, object]:
    def side_capture(offset: float) -> dict[str, object]:
        gram = np.asarray(
            [[2.0 + offset, 0.1j], [-0.1j, 1.5 + offset]],
            dtype=np.complex128,
        )
        mapping = np.asarray(
            [[0.8 + 0.05j, -0.1j], [0.2, 0.9 - 0.02j]],
            dtype=np.complex128,
        )
        raw = gram @ mapping
        repeat_gram = gram + (1.0e-13 + 0.0j)
        repeat_mapping = mapping + (2.0e-13 + 0.0j)
        repeat_raw = repeat_gram @ repeat_mapping
        return {
            "surface_gram": gram,
            "raw_negative_overlap": raw,
            "canonical_negative_overlap": raw,
            "canonical_mapping": mapping,
            "repeat_surface_gram": repeat_gram,
            "repeat_raw_overlap": repeat_raw,
            "repeat_canonical_negative_overlap": repeat_raw,
            "repeat_canonical_mapping": repeat_mapping,
            "lift_queries": {"first": 8, "repeat": 8},
            "gram_condition": float(np.linalg.cond(gram)),
            "repeat_gram_condition": float(np.linalg.cond(repeat_gram)),
        }

    return {
        "schema": "task039.review-v1.m960-trace-capture.v1",
        "mode_count": 2,
        "column_keys": [[0, "backward", 1.0, 0.0], [1, "backward", 1.1, 0.0]],
        "mode_identifiers": [
            {
                "index": 0,
                "key": [0, "backward", 1.0, 0.0],
                "direction": "backward",
                "beta": [1.0, 0.0],
            },
            {
                "index": 1,
                "key": [1, "backward", 1.1, 0.0],
                "direction": "backward",
                "beta": [1.1, 0.0],
            },
        ],
        "degenerate_groups": [
            {
                "indices": [0, 1],
                "keys": [[0, "backward", 1.0, 0.0], [1, "backward", 1.1, 0.0]],
            }
        ],
        "sides": {"bottom": side_capture(0.0), "top": side_capture(0.01)},
    }


def test_capture_writer_roundtrip_records_independent_repeats(tmp_path: Path):
    capture = _capture_fixture()
    descriptor = write_trace_audit_capture(
        capture,
        tmp_path,
        metadata={
            "source_commit_sha": "a" * 40,
            "mpi_size": 8,
            "historical_m_modes": {
                "bottom": {
                    "120": {"raw_forward_error": 1.0e-12},
                    "240": {"raw_forward_error": 2.0e-12},
                    "480": {"raw_forward_error": 3.0e-12},
                },
                "top": {
                    "120": {"raw_forward_error": 4.0e-12},
                    "240": {"raw_forward_error": 5.0e-12},
                    "480": {"raw_forward_error": 6.0e-12},
                },
            },
        },
    )
    npz_path = Path(descriptor["npz_path"])
    metadata_path = Path(descriptor["metadata_path"])
    assert descriptor["npz_sha256"] == hashlib.sha256(npz_path.read_bytes()).hexdigest()
    assert (
        descriptor["metadata_sha256"]
        == hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    )
    with np.load(npz_path, allow_pickle=False) as archive:
        assert "bottom_surface_gram" in archive.files
        assert "top_repeat_surface_gram" in archive.files
        assert not np.array_equal(
            archive["bottom_surface_gram"], archive["bottom_repeat_surface_gram"]
        )
    record = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert record["capture"]["column_keys"] == capture["column_keys"]
    assert record["capture"]["degenerate_groups"][0]["keys"]
    assert (
        record["capture"]["sides"]["bottom"]["audit"]["historical"]["120"][
            "raw_forward_error"
        ]
        == 1.0e-12
    )
    assert (
        record["capture"]["sides"]["top"]["audit"]["historical"]["120"][
            "raw_forward_error"
        ]
        == 4.0e-12
    )


def test_capture_writer_rejects_nonfinite_and_wrong_shape(tmp_path: Path):
    capture = _capture_fixture()
    capture["sides"]["top"]["surface_gram"][0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        write_trace_audit_capture(capture, tmp_path / "nonfinite")

    capture = _capture_fixture()
    capture["sides"]["bottom"]["surface_gram"] = np.zeros((2, 1), dtype=np.complex128)
    with pytest.raises(ValueError, match="square"):
        write_trace_audit_capture(capture, tmp_path / "shape")


def test_research_capture_uses_two_fresh_passes_and_no_solve_path(monkeypatch):
    n = 2
    surface_objects = []
    lifter_objects = []
    calls = []

    class FakeProjection:
        def __init__(self, _spaces, basis):
            self.right_traces = [object() for _ in basis.modes]

        def project(self, trace):
            return np.ones(n, dtype=np.complex128) * (1.0 if trace else 2.0)

        def destroy(self):
            pass

    def fake_surface(system):
        value = SimpleNamespace(side=system.side)
        surface_objects.append(value)
        return value

    def fake_lifter(system, *, target_space):
        value = SimpleNamespace(side=system.side, target_space=target_space)
        lifter_objects.append(value)
        return value

    def fake_overlaps(system, _projection, _raw, _canonical, surface, lifter, _log):
        calls.append((system.side, id(surface), id(lifter)))
        scale = float(len(calls))
        matrix = np.eye(n, dtype=np.complex128) * scale
        return [], 2, matrix, matrix.copy(), matrix.copy()

    monkeypatch.setattr(hybrid_modes, "ModalTraceProjection", FakeProjection)
    monkeypatch.setattr(
        hybrid_modes,
        "_trace_from_full_mode_vector",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        hybrid_modes,
        "_canonicalized_negative_traces",
        lambda _projection, mapping: [object() for _ in range(mapping.shape[1])],
    )
    monkeypatch.setattr(hybrid_modes, "_ReusableInterfaceSurfaceLoad", fake_surface)
    monkeypatch.setattr(hybrid_modes, "_ReusableInterfaceLifter", fake_lifter)
    monkeypatch.setattr(
        hybrid_modes, "_assemble_canonical_trace_overlaps", fake_overlaps
    )
    monkeypatch.setattr(
        hybrid_modes,
        "_canonical_trace_consistency_audit",
        lambda *_args, **_kwargs: {"pass": True},
    )
    modes = [
        SimpleNamespace(
            direction="backward",
            beta=1.0 + 0.1j,
            right=SimpleNamespace(right_full=object()),
        )
        for _ in range(n)
    ]
    basis = SimpleNamespace(modes=modes, groups=[])
    groups = [
        SimpleNamespace(
            indices=(0, 1), beta_center=1.0 + 0.1j, max_relative_beta_spread=0.0
        )
    ]
    basis.groups = groups
    systems = (
        SimpleNamespace(side="bottom", V=object()),
        SimpleNamespace(side="top", V=object()),
    )
    capture = hybrid_modes.capture_hybrid_trace_audit(object(), basis, basis, *systems)
    assert len(calls) == 4
    assert len({call[1] for call in calls}) == 4
    assert len({call[2] for call in calls}) == 4
    assert not np.array_equal(
        capture["sides"]["bottom"]["surface_gram"],
        capture["sides"]["bottom"]["repeat_surface_gram"],
    )
    assert capture["column_keys"][0][1] == "backward"
    assert capture["degenerate_groups"][0]["keys"][0] == capture["column_keys"][0]
    source = inspect.getsource(hybrid_modes.capture_hybrid_trace_audit)
    assert "_build_interface_blocks" not in source
    assert "build_exact_one_cell_traction_matrices" not in source
    assert "solve_hybrid" not in source


def test_projection_helper_failure_destroys_matrix(monkeypatch):
    matrix = SimpleNamespace(destroy=lambda: setattr(matrix, "destroyed", 1))
    matrix.destroyed = 0
    comm = SimpleNamespace(rank=0, size=1)
    system = SimpleNamespace(
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm)),
        global_size=1,
        A=SimpleNamespace(getLocalSize=lambda: (1, 1)),
    )
    projection = SimpleNamespace(left_traces=[object()])

    monkeypatch.setattr(
        hybrid_modes, "_create_rectangular_aij", lambda *_args, **_kwargs: matrix
    )

    def fail(*_args, **_kwargs):
        raise RuntimeError("independent assembly failed")

    monkeypatch.setattr(hybrid_modes, "_assemble_canonical_trace_overlaps", fail)
    with pytest.raises(RuntimeError, match="independent assembly failed"):
        hybrid_modes._build_projection_matrix(
            system,
            projection,
            (),
            (),
            np.zeros((1, 1), dtype=np.complex128),
            object(),
            object(),
        )
    assert matrix.destroyed == 1


def test_default_runner_forwards_explicit_capture_only(monkeypatch, tmp_path: Path):
    import benchmarks.run_task032_phase6_augmented as augmented
    from src.runners.task039_hybrid_direct import _default_runner

    captured = {}

    def fake_main(_argv, **kwargs):
        captured.update(kwargs)
        return {"status": "controlled_stop"}

    monkeypatch.setattr(augmented, "main", fake_main)
    _default_runner(
        [],
        object(),
        "task039_direct",
        {},
        tmp_path / "exact_one_cell",
        tmp_path / "trace_capture",
        {"source_commit_sha": "b" * 40},
    )
    assert captured["trace_audit_capture_dir"] == tmp_path / "trace_capture"
    assert captured["trace_audit_metadata"] == {"source_commit_sha": "b" * 40}
    assert captured["qep_solver_tolerance"] == 1.0e-12


def test_task039_trace_lane_records_stage_path_and_keeps_source_last(
    monkeypatch, tmp_path: Path
):
    from src.io import load_and_resolve
    import src.runners.task039_hybrid_direct as adapter

    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h10_hybrid_direct_m120_mpi8.dat")
    ).as_jsonable()
    captured = {}

    def fake_runner(*args):
        captured["args"] = args
        return {
            "status": "controlled_stop",
            "trace_audit_capture": {"individual_capture_complete": True},
        }

    monkeypatch.setattr(adapter, "_default_runner", fake_runner)
    result = adapter.run_task039_hybrid_direct(
        payload,
        tmp_path,
        source_sha="a" * 40,
        trace_audit_capture_dir=tmp_path / "capture",
        trace_audit_metadata={"source_commit_sha": "b" * 40},
    )
    assert result["passed"] is True
    argv = captured["args"][0]
    assert argv[-2:] == [
        "--memory-stages",
        str(tmp_path / "numerical_output" / "task039_trace_audit_stages.jsonl"),
    ]
    assert captured["args"][-1]["source_commit_sha"] == "a" * 40


def test_execution_plan_trace_flag_is_task039_only(tmp_path: Path):
    from src.io import load_and_resolve
    from src.io.execution_plan import build_execution_plan
    from src.io.input_loader import InputError

    path = Path("input/official/task039/5nm_p6h10_hybrid_direct_m120_mpi8.dat")
    specification = load_and_resolve(path)
    plan = build_execution_plan(
        specification,
        tmp_path,
        source_sha="c" * 40,
        python_executable="/opt/python",
        mpiexec_command="/opt/mpiexec",
        task039_trace_audit=True,
    )
    assert plan.task039_trace_audit is True
    assert plan.argv[-1] == "--task039-trace-audit"
    with pytest.raises(InputError, match="cannot be combined"):
        build_execution_plan(
            specification,
            tmp_path,
            source_sha="c" * 40,
            task039_trace_audit=True,
            contract_probe=True,
        )


def test_worker_trace_flag_dispatches_mock_capture_without_authority(
    monkeypatch, tmp_path: Path
):
    from src.io import load_and_resolve
    from src.runners.task038_input_worker import _dispatch_resolved_payload

    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h10_hybrid_direct_m120_mpi8.dat")
    ).as_jsonable()
    captured = {}

    def fake_adapter(_payload, _directory, **kwargs):
        captured.update(kwargs)
        return {
            "passed": True,
            "errors": [],
            "record": {
                "status": "controlled_stop",
                "trace_audit_capture": {"individual_capture_complete": True},
            },
        }

    import src.runners.task039_hybrid_direct as adapter

    monkeypatch.setattr(adapter, "run_task039_hybrid_direct", fake_adapter)
    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="hybrid_direct",
        output_directory=tmp_path,
        expected_source_sha="d" * 40,
        expected_resolved_config_sha256="e" * 64,
        task039_trace_audit=True,
    )
    assert status == 0
    assert errors == []
    assert captured["trace_audit_capture_dir"] == (
        tmp_path / "numerical_output" / "task039_trace_audit"
    )


def test_worker_trace_flag_mock_dispatch_is_mpi2_safe(monkeypatch, tmp_path: Path):
    from mpi4py import MPI
    from src.io import load_and_resolve
    from src.runners.task038_input_worker import _dispatch_resolved_payload

    if MPI.COMM_WORLD.size not in (1, 2):
        pytest.skip("tiny contract is intended for serial or MPI2")
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h10_hybrid_direct_m120_mpi8.dat")
    ).as_jsonable()
    import src.runners.task039_hybrid_direct as adapter

    monkeypatch.setattr(
        adapter,
        "run_task039_hybrid_direct",
        lambda *_args, **_kwargs: {
            "passed": True,
            "errors": [],
            "record": {
                "status": "controlled_stop",
                "trace_audit_capture": {"individual_capture_complete": True},
            },
        },
    )
    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="hybrid_direct",
        output_directory=tmp_path,
        expected_source_sha="f" * 40,
        expected_resolved_config_sha256="0" * 64,
        task039_trace_audit=True,
    )
    assert status == 0
    assert errors == []
    MPI.COMM_WORLD.Barrier()


def test_trace_writer_helper_calls_rank_zero_once_and_broadcasts(
    monkeypatch, tmp_path: Path
):
    from mpi4py import MPI

    if MPI.COMM_WORLD.size != 2:
        pytest.skip("writer ownership contract is intended for MPI2")
    import benchmarks.run_task032_phase6_augmented as augmented
    import benchmarks.task039_trace_audit as writer

    calls = 0

    def fake_writer(_capture, _output_dir, *, metadata):
        nonlocal calls
        calls += 1
        return {"status": "ok", "metadata": metadata}

    monkeypatch.setattr(writer, "write_trace_audit_capture", fake_writer)
    descriptor = augmented._task039_write_trace_capture_mpi(
        MPI.COMM_WORLD,
        _capture_fixture(),
        tmp_path / "capture",
        {"source_commit_sha": "a" * 40},
    )
    assert MPI.COMM_WORLD.allreduce(calls, op=MPI.SUM) == 1
    assert MPI.COMM_WORLD.allgather(descriptor) == [descriptor, descriptor]


def test_trace_writer_helper_broadcasts_rank_zero_error(monkeypatch, tmp_path: Path):
    import benchmarks.task039_trace_audit as writer
    import benchmarks.run_task032_phase6_augmented as augmented

    class RankZeroComm:
        rank = 0

        @staticmethod
        def bcast(value, root):
            assert root == 0
            return value

    def fail_writer(*_args, **_kwargs):
        raise RuntimeError("writer failure")

    monkeypatch.setattr(writer, "write_trace_audit_capture", fail_writer)
    with pytest.raises(RuntimeError, match="writer failure"):
        augmented._task039_write_trace_capture_mpi(
            RankZeroComm(),
            _capture_fixture(),
            tmp_path / "capture",
            {},
        )
