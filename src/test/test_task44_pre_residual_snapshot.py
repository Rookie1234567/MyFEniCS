from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from src.solvers import dtn_port_3d
from src.solvers import task44_residual_snapshot as residual_snapshot

GIB = 1024**3


def _memory_authority(
    *, current_bytes: int | None = None, host_headroom_bytes: int = 512 * GIB,
    ancestor_headroom_bytes: int = 12 * GIB,
):
    cap = 16 * GIB
    warning = int(cap * 0.90)
    if current_bytes is None:
        current_bytes = warning - 8 * GIB
    return {
        "status": "readable",
        "scope": "current dedicated Task44 service cgroup",
        "whole_job_current_bytes": current_bytes,
        "whole_job_cap_bytes": cap,
        "whole_job_swap_current_bytes": 0,
        "warning_threshold_bytes": warning,
        "controlled_stop_threshold_bytes": int(cap * 0.95),
        "host_headroom_after_reserve_bytes": host_headroom_bytes,
        "ancestor_headroom_after_buffer_bytes": ancestor_headroom_bytes,
        "host_and_ancestor_headroom_after_reserves_bytes": min(
            host_headroom_bytes, ancestor_headroom_bytes
        ),
        "host_reserve_required_bytes": 384 * GIB,
        "task_buffer_required_bytes": 8 * GIB,
        "cgroup_limits": [{"path": "/sys/fs/cgroup/task44.service", "limit_bytes": cap}],
    }


class _FakeComm:
    def getSize(self):
        return 1


class _FakeVector:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128).copy()
        self.destroyed = False

    def getArray(self, readonly=False):
        del readonly
        return self.values

    def getSize(self):
        return int(self.values.size)

    def getOwnershipRange(self):
        return (0, self.getSize())

    def getComm(self):
        return _FakeComm()

    def duplicate(self):
        return _FakeVector(np.zeros_like(self.values))

    def destroy(self):
        self.destroyed = True

    def axpy(self, alpha, other):
        self.values += alpha * other.values

    def norm(self):
        return float(np.linalg.norm(self.values))


class _FakeMatrix:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128)

    def mult(self, source, target):
        target.values[:] = self.values @ source.values


class _FakeIndexMap:
    size_global = 3
    size_local = 3
    num_ghosts = 0


class _FakeDofMap:
    index_map = _FakeIndexMap()
    index_map_bs = 1

    def cell_dofs(self, cell):
        return np.asarray([cell, cell + 1, cell + 2], dtype=np.int32)


class _FakeTopology:
    dim = 3

    def index_map(self, dimension):
        assert dimension == 3
        return type("CellIndexMap", (), {"size_local": 1})()


class _FakeMesh:
    topology = _FakeTopology()
    geometry = type(
        "Geometry",
        (),
        {
            "x": np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
            "dofmap": np.asarray([[0, 1]], dtype=np.int32),
        },
    )()


class _FakeTags:
    indices = np.asarray([0], dtype=np.int32)
    values = np.asarray([7], dtype=np.int32)


class _FakeMeshData:
    mesh = _FakeMesh()
    cell_tags = _FakeTags()
    facet_tags = _FakeTags()
    mesh_cell_type_resolved = "hexahedron"
    mesh_cells_resolved = (1, 1, 1)


class _FakeFunctionSpace:
    dofmap = _FakeDofMap()
    mesh = _FakeMesh()


class _FakeConfig:
    physical_z_min = -1.0
    physical_z_max = 1.0
    geometry_identity = "task44-test-geometry"
    geometry_kind = "rectangular_block_grating"
    stage_case = "stage4_block_grating"
    wavevector = (0.0j, 0.0j, 1.5 + 0.2j)
    lambda0 = 0.7

    def as_jsonable(self):
        return {"case_name": "task44_snapshot_test", "wavelength_nm": 0.7}


class _FakeFloquetData:
    phase_x = 1.0 + 0.0j
    phase_y = -1.0 + 0.0j
    mpc = object()


class _FakeMode:
    side = "top"
    m = 1
    n = -2
    polarization = "s"
    alpha = 0.5 + 0.1j
    gamma = -0.25 + 0.2j
    beta = 1.0 + 0.3j
    k_vector = (0.5 + 0.1j, -0.25 + 0.2j, 3.0 + 0.5j)
    propagating = False


class _FakeCondensed:
    full_rows = 3
    trace_rows = 2
    active_rows = 2
    appended_rows = 1
    interior_rows = 1
    active_interior_rows = 1


def _snapshot_inputs(tmp_path: Path):
    output = tmp_path / "numerical_output"
    output.mkdir()
    vectors = {
        "reduced_solution": _FakeVector([1.0 + 2.0j, 3.0 - 1.0j]),
        "reduced_rhs": _FakeVector([2.0 + 1.0j, -2.0 + 0.5j]),
        "recovered_fe_solution": _FakeVector([0.25 + 0.5j, -1.0j, 2.0]),
        "full_rhs": _FakeVector([1.0, 0.5j, -3.0 + 0.2j]),
    }
    identity = {
        "schema": residual_snapshot.SNAPSHOT_SCHEMA,
        "output_directory": str(output),
        "phase_gauge_identity": {
            "active_solver_output_gauge": "global_z",
            "runtime_diagnostic_gauge_label": "global_z",
        },
    }
    return output, vectors, identity


def _write_run_identity(run_root: Path):
    run_root.mkdir(parents=True)
    raw_input = b"Task44 snapshot test input\n"
    input_sha = hashlib.sha256(raw_input).hexdigest()
    source_sha = "a" * 40
    physical_sha = "b" * 64
    resolved_bytes = json.dumps(
        {"method": {"dtn_phase_gauge": "global_z"}},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    (run_root / "source_sha.txt").write_text(source_sha + "\n", encoding="ascii")
    (run_root / "input_sha256.txt").write_text(input_sha + "\n", encoding="ascii")
    (run_root / "physical_model_sha256.txt").write_text(
        physical_sha + "\n", encoding="ascii"
    )
    (run_root / "input_original.dat").write_bytes(raw_input)
    (run_root / "resolved_config.json").write_bytes(resolved_bytes)
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "task44_snapshot_test",
                "source_sha": source_sha,
                "input_sha256": input_sha,
                "physical_model_sha256": physical_sha,
                "resolved_config_sha256": resolved_sha,
            }
        ),
        encoding="utf-8",
    )
    return input_sha, physical_sha


def test_snapshot_identity_binds_run_mesh_modes_and_cell_dofmap(tmp_path):
    run_root = tmp_path / "run"
    input_sha, physical_sha = _write_run_identity(run_root)
    output = run_root / "numerical_output"
    output.mkdir()

    identity = residual_snapshot.build_task44_residual_snapshot_identity(
        output_directory=output,
        cfg=_FakeConfig(),
        mesh_data=_FakeMeshData(),
        function_space=_FakeFunctionSpace(),
        floquet_data=_FakeFloquetData(),
        modes=[_FakeMode()],
        reduced_solution=_FakeVector([1.0, 2.0, 3.0]),
        condensed=_FakeCondensed(),
    )

    assert identity["run_manifest_identity"]["input_sha256"] == input_sha
    assert identity["run_manifest_identity"]["physical_model_sha256"] == physical_sha
    assert identity["run_identity_checks"] == {
        "source_sha_matches_run_manifest": True,
        "input_sha_matches_original_input": True,
        "input_sha_matches_run_manifest": True,
        "physical_model_sha_matches_run_manifest": True,
        "resolved_config_sha_matches_run_manifest": True,
    }
    assert len(identity["dof_identity"]["cell_dofmap_sha256"]) == 64
    assert identity["mode_keys_and_phases"][0]["key"] == ["top", 1, -2, "s"]
    assert identity["mode_keys_and_phases"][0]["boundary_plane_phase"] == [1.0, 0.0]
    assert identity["phase_gauge_identity"]["configured_solver_output_gauge"] == "global_z"
    assert len(identity["identity_sha256"]) == 64


def test_snapshot_identity_uses_validated_external_task44_binding(tmp_path, monkeypatch):
    output = tmp_path / "run" / "numerical_output"
    output.mkdir(parents=True)
    input_path = tmp_path / "task44-input.dat"
    input_path.write_bytes(b"bound input bytes\n")
    monkeypatch.setenv("MYFENICS_TASK44_SOURCE_SHA", "c" * 40)
    monkeypatch.setenv("MYFENICS_TASK44_INPUT_PATH", str(input_path))
    monkeypatch.setenv(
        "MYFENICS_TASK44_INPUT_SHA256",
        hashlib.sha256(input_path.read_bytes()).hexdigest(),
    )
    monkeypatch.setenv("MYFENICS_TASK44_PHYSICAL_MODEL_SHA256", "d" * 64)

    identity = residual_snapshot.build_task44_residual_snapshot_identity(
        output_directory=output,
        cfg=_FakeConfig(),
        mesh_data=_FakeMeshData(),
        function_space=_FakeFunctionSpace(),
        floquet_data=_FakeFloquetData(),
        modes=[_FakeMode()],
        reduced_solution=_FakeVector([1.0, 2.0, 3.0]),
        condensed=_FakeCondensed(),
    )

    assert identity["run_manifest_identity"]["identity_source"] == (
        "validated_task44_service_environment"
    )
    assert identity["run_identity_checks"]["input_sha_matches_input_path"] is True
    assert identity["run_identity_files"]["input_original.dat"]["path"] == str(input_path)


def test_pre_residual_snapshot_saves_vectors_and_reduced_ax_minus_b(tmp_path):
    _output, vectors, identity = _snapshot_inputs(tmp_path)
    reduced_residual = np.asarray([1.0 - 2.0j, 4.0 + 0.5j], dtype=np.complex128)
    budget = residual_snapshot.preflight_task44_residual_snapshot(
        vectors,
        mpi_size=1,
        include_reduced_residual=True,
        memory_authority=_memory_authority(),
    )

    receipt = residual_snapshot.write_task44_pre_residual_snapshot(
        identity=identity,
        vectors=vectors,
        reduced_metrics={"linear_system_residual_norm": float(np.linalg.norm(reduced_residual))},
        reduced_ax_minus_b=reduced_residual,
        budget=budget,
    )

    snapshot_dir = Path(receipt["snapshot_directory"])
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    arrays = np.load(snapshot_dir / "vectors.npz")
    for name, vector in vectors.items():
        np.testing.assert_array_equal(arrays[name], vector.values)
    np.testing.assert_array_equal(arrays["reduced_ax_minus_b"], reduced_residual)
    assert receipt["status"] == "snapshot_written_before_matrix_free_ufl_action"
    assert receipt["restartable"] is False
    assert receipt["official_solution"] is False
    assert manifest["restartable"] is False
    assert manifest["official_solution"] is False
    assert manifest["matrix_free_ufl_action_started"] is False
    assert manifest["snapshot_memory_budget"]["allowance_bytes"] == 32 * 1024**2
    assert manifest["snapshot_memory_budget"]["whole_job_memory_gate"][
        "whole_job_cap_bytes"
    ] == 16 * GIB
    assert manifest["snapshot_memory_budget"]["whole_job_memory_gate"][
        "host_reserve_required_bytes"
    ] == 384 * GIB
    assert manifest["snapshot_memory_budget"]["whole_job_memory_gate"][
        "task_buffer_required_bytes"
    ] == 8 * GIB
    assert manifest["reduced_system_residual"]["vector_status"] == "saved"
    assert manifest["vector_payload"]["arrays"]["reduced_ax_minus_b"]["semantic"] == (
        "reduced_matrix @ reduced_solution - reduced_rhs"
    )
    assert budget["allowance_bytes"] == 32 * 1024**2
    assert budget["predicted_peak_delta_bytes"] <= 32 * 1024**2
    assert budget["whole_job_memory_gate"]["status"] == "pass"


def test_snapshot_preflight_fails_closed_above_32_mib_without_vector_copy(
    tmp_path, monkeypatch
):
    _output, vectors, _identity = _snapshot_inputs(tmp_path)
    monkeypatch.setattr(residual_snapshot, "MAX_SNAPSHOT_PEAK_DELTA_BYTES", 1024)

    with pytest.raises(MemoryError, match="32 MiB allowance"):
        residual_snapshot.preflight_task44_residual_snapshot(
            vectors,
            mpi_size=1,
            include_reduced_residual=True,
            memory_authority=_memory_authority(),
        )


def test_p6_fresh5_vector_sizes_fit_the_32_mib_snapshot_peak_delta():
    vectors = {
        "reduced_solution": _FakeVector(np.zeros(6414, dtype=np.complex128)),
        "reduced_rhs": _FakeVector(np.zeros(6414, dtype=np.complex128)),
        "recovered_fe_solution": _FakeVector(np.zeros(19494, dtype=np.complex128)),
        "full_rhs": _FakeVector(np.zeros(19494, dtype=np.complex128)),
    }

    budget = residual_snapshot.preflight_task44_residual_snapshot(
        vectors,
        mpi_size=1,
        include_reduced_residual=True,
        memory_authority=_memory_authority(),
    )

    assert budget["vector_copy_bytes"] == 829_056
    assert budget["reduced_residual_temporary_and_copy_bytes"] == 307_872
    assert budget["predicted_peak_delta_bytes"] == 2_185_504
    assert budget["predicted_peak_delta_bytes"] < 32 * 1024**2


def test_snapshot_whole_job_warning_threshold_allows_exact_boundary_and_rejects_one_byte_over(
    tmp_path,
):
    _output, vectors, _identity = _snapshot_inputs(tmp_path)
    delta = residual_snapshot.preflight_task44_residual_snapshot(
        vectors,
        mpi_size=1,
        include_reduced_residual=True,
        memory_authority=_memory_authority(),
    )["predicted_peak_delta_bytes"]
    warning = int(16 * GIB * 0.90)

    boundary_authority = _memory_authority(current_bytes=warning - delta)
    exact = residual_snapshot.preflight_task44_residual_snapshot(
        vectors,
        mpi_size=1,
        include_reduced_residual=True,
        memory_authority=boundary_authority,
    )
    assert exact["whole_job_memory_gate"]["predicted_whole_job_peak_bytes"] == warning

    over_authority = _memory_authority(current_bytes=warning - delta + 1)
    with pytest.raises(MemoryError, match="warning threshold"):
        residual_snapshot.preflight_task44_residual_snapshot(
            vectors,
            mpi_size=1,
            include_reduced_residual=True,
            memory_authority=over_authority,
        )


def test_snapshot_preflight_rejects_host_or_ancestor_reserve_crossing(tmp_path):
    _output, vectors, _identity = _snapshot_inputs(tmp_path)
    with pytest.raises(MemoryError, match="host reserve or ancestor cgroup buffer"):
        residual_snapshot.preflight_task44_residual_snapshot(
            vectors,
            mpi_size=1,
            include_reduced_residual=True,
            memory_authority=_memory_authority(ancestor_headroom_bytes=1),
        )


def test_snapshot_preflight_fails_closed_when_live_authority_is_unreadable(
    tmp_path, monkeypatch
):
    _output, vectors, _identity = _snapshot_inputs(tmp_path)

    def unreadable_authority():
        raise RuntimeError("fake cgroup authority unavailable")

    monkeypatch.setattr(
        residual_snapshot,
        "_read_task44_whole_job_memory_authority",
        unreadable_authority,
    )
    with pytest.raises(RuntimeError, match="authority unavailable"):
        residual_snapshot.preflight_task44_residual_snapshot(
            vectors, mpi_size=1, include_reduced_residual=True
        )


def test_live_memory_authority_uses_existing_job_cgroup_and_shared_envelope(
    monkeypatch,
):
    from benchmarks import subreaper_watchdog, task034_wsl_resources

    cap = 16 * GIB
    monkeypatch.setattr(
        task034_wsl_resources,
        "cgroup_snapshot",
        lambda _pid: {
            "path": "/user.slice/user-1000.slice/task44-diagnostic.service",
            "readable": True,
            "dedicated_job_cgroup": True,
            "memory_current_bytes": 3 * GIB,
            "memory_peak_bytes": 4 * GIB,
            "memory_limit_bytes": cap,
            "swap_current_bytes": 0,
        },
    )
    monkeypatch.setattr(
        subreaper_watchdog,
        "memory_envelope",
        lambda *_args, **_kwargs: {
            "host_mem_available_bytes": 2 * 1024 * GIB,
            "reserve_bytes": 384 * GIB,
            "task_cgroup_available_bytes": 12 * GIB,
            "task_cgroup_reserve_bytes": 8 * GIB,
            "launch_cap_bytes": 4 * GIB,
            "cgroup_limits": [
                {"path": "/sys/fs/cgroup/task44-diagnostic.service", "limit_bytes": cap}
            ],
            "cgroup_memory_stats": [],
        },
    )

    authority = residual_snapshot._read_task44_whole_job_memory_authority()

    assert authority["whole_job_current_bytes"] == 3 * GIB
    assert authority["whole_job_cap_bytes"] == cap
    assert authority["warning_threshold_bytes"] == int(14.4 * GIB)
    assert authority["controlled_stop_threshold_bytes"] == int(15.2 * GIB)
    assert authority["host_reserve_required_bytes"] == 384 * GIB
    assert authority["task_buffer_required_bytes"] == 8 * GIB
    assert authority["ancestor_headroom_after_buffer_bytes"] == 4 * GIB


def test_residual_capture_failure_propagates_and_destroys_temporary_vector():
    b = _FakeVector([2.0 + 1.0j, -2.0 + 0.5j])
    captured = []

    def fail_capture(vector):
        captured.append(vector)
        raise OSError("fake residual snapshot capture failure")

    with pytest.raises(OSError, match="snapshot capture failure"):
        dtn_port_3d._linear_residual(
            _FakeMatrix([[2.0, 1.0j], [0.5, 3.0]]),
            b,
            _FakeVector([1.0 + 2.0j, 3.0 - 1.0j]),
            residual_capture=fail_capture,
        )

    assert len(captured) == 1
    assert captured[0].destroyed is True


def test_residual_capture_disabled_preserves_legacy_failure_metrics_and_destroys_vector():
    b = _FakeVector([2.0 + 1.0j, -2.0 + 0.5j])
    created = []

    class _FailingMatrix:
        def mult(self, _source, target):
            created.append(target)
            raise RuntimeError("legacy matrix action failed")

    result = dtn_port_3d._linear_residual(
        _FailingMatrix(),
        b,
        _FakeVector([1.0 + 2.0j, 3.0 - 1.0j]),
    )

    assert result == {
        "linear_system_rhs_norm": None,
        "linear_system_solution_norm": None,
        "linear_system_residual_norm": None,
        "linear_system_relative_residual": None,
    }
    assert len(created) == 1
    assert created[0].destroyed is True


def test_existing_snapshot_directory_is_not_overwritten(tmp_path, monkeypatch):
    output, vectors, identity = _snapshot_inputs(tmp_path)
    token = "fixed-token"

    class _FixedUuid:
        hex = token

    monkeypatch.setattr(residual_snapshot.time, "time_ns", lambda: 1234)
    monkeypatch.setattr(residual_snapshot.os, "getpid", lambda: 5678)
    monkeypatch.setattr(residual_snapshot.uuid, "uuid4", lambda: _FixedUuid())
    existing = output / f"task44_pre_operator_residual_1234_5678_{token}"
    existing.mkdir()
    raw = existing / "vectors.npz"
    raw.write_bytes(b"preserve-old-raw")
    before = raw.read_bytes()
    budget = residual_snapshot.preflight_task44_residual_snapshot(
        vectors,
        mpi_size=1,
        include_reduced_residual=False,
        memory_authority=_memory_authority(),
    )

    with pytest.raises(FileExistsError):
        residual_snapshot.write_task44_pre_residual_snapshot(
            identity=identity,
            vectors=vectors,
            reduced_metrics={"linear_system_residual_norm": 0.0},
            reduced_ax_minus_b=None,
            budget=budget,
        )

    assert raw.read_bytes() == before
    assert not (existing / "manifest.json").exists()


def test_snapshot_write_failure_precedes_matrix_free_ufl_action(tmp_path, monkeypatch):
    output, vectors, identity = _snapshot_inputs(tmp_path)
    ufl_action_started = False
    monkeypatch.setattr(
        residual_snapshot,
        "_read_task44_whole_job_memory_authority",
        _memory_authority,
    )

    def fail_write(*_args, **_kwargs):
        raise OSError("fake snapshot disk write failure")

    def start_action(*_args, **_kwargs):
        nonlocal ufl_action_started
        ufl_action_started = True
        raise AssertionError("matrix-free UFL action must not start after snapshot failure")

    monkeypatch.setattr(residual_snapshot.np, "savez", fail_write)
    monkeypatch.setattr(dtn_port_3d, "MpcFormActionContext", start_action)

    with pytest.raises(OSError, match="fake snapshot disk write failure"):
        dtn_port_3d._assembly_time_full_operator_residual(
            None,
            _FakeFloquetData(),
            vectors["recovered_fe_solution"],
            None,
            vectors["reduced_rhs"],
            vectors["reduced_solution"],
            None,
            vectors["full_rhs"],
            reduced_residual_norm=0.25,
            diagnostic_snapshot_identity=identity,
        )

    assert not ufl_action_started
    snapshot_dirs = list(output.glob("task44_pre_operator_residual_*"))
    assert len(snapshot_dirs) == 1
    assert not (snapshot_dirs[0] / "manifest.json").exists()


def test_successful_snapshot_precedes_matrix_free_ufl_action(tmp_path, monkeypatch):
    output, vectors, identity = _snapshot_inputs(tmp_path)
    action_started = []
    monkeypatch.setattr(
        residual_snapshot,
        "_read_task44_whole_job_memory_authority",
        _memory_authority,
    )

    class _ActionBoundary(Exception):
        pass

    def start_action(*_args, **_kwargs):
        action_started.append(True)
        raise _ActionBoundary

    monkeypatch.setattr(dtn_port_3d, "MpcFormActionContext", start_action)

    with pytest.raises(_ActionBoundary):
        dtn_port_3d._assembly_time_full_operator_residual(
            None,
            _FakeFloquetData(),
            vectors["recovered_fe_solution"],
            _FakeMatrix([[2.0, 1.0j], [0.5, 3.0]]),
            vectors["reduced_rhs"],
            vectors["reduced_solution"],
            None,
            vectors["full_rhs"],
            diagnostic_snapshot_identity=identity,
        )

    assert action_started == [True]
    snapshot_dirs = list(output.glob("task44_pre_operator_residual_*"))
    assert len(snapshot_dirs) == 1
    manifest = json.loads((snapshot_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    arrays = np.load(snapshot_dirs[0] / "vectors.npz")
    expected = _FakeMatrix([[2.0, 1.0j], [0.5, 3.0]]).values @ vectors["reduced_solution"].values
    expected -= vectors["reduced_rhs"].values
    np.testing.assert_array_equal(arrays["reduced_ax_minus_b"], expected)
    assert manifest["reduced_system_residual"]["vector_status"] == "saved"
    assert manifest["matrix_free_ufl_action_started"] is False
