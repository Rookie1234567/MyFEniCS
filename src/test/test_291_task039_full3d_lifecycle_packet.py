import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task041_exact_side_workflow import _write_rank_pid_affinity
from src.solvers.full3d_lifecycle_packet import (
    _ownership_is_contiguous,
    load_packet,
    write_packet,
)


def _shared_packet_dir(tmp_path: Path) -> tuple[Path, MPI.Intracomm]:
    comm = MPI.COMM_WORLD
    directory = Path(comm.bcast(str(tmp_path), root=0))
    if comm.rank == 0:
        shutil.rmtree(directory, ignore_errors=True)
    comm.barrier()
    return directory, comm


def test_pre_recovery_packet_roundtrip_hash_and_no_solver_objects(
    tmp_path: Path,
) -> None:
    tmp_path, comm = _shared_packet_dir(tmp_path)
    identity = {"source_sha": "abc", "physical_sha256": "def", "mpi": comm.size}
    ownership = (2 * comm.rank, 2 * (comm.rank + 1))
    result = write_packet(
        tmp_path,
        np.asarray([1 + 2j, 3 - 4j], dtype=np.complex128),
        np.asarray([5 - 6j, 7 + 8j], dtype=np.complex128),
        identity=identity,
        metadata={"external_keys": [["top", 0, 0, "s"]], "residual": 1.0e-12},
        ownership_range=ownership,
        comm=comm,
    )
    assert result["pass"] is True
    loaded = load_packet(
        tmp_path / "manifest.json",
        identity=identity,
        expected_manifest_sha256=result["manifest_sha256"],
        comm=comm,
    )
    np.testing.assert_array_equal(loaded["solution"], [1 + 2j, 3 - 4j])
    np.testing.assert_array_equal(loaded["rhs"], [5 - 6j, 7 + 8j])
    assert loaded["metadata"]["residual"] == 1.0e-12
    assert "ksp" not in loaded and "pc" not in loaded and "factor" not in loaded
    assert loaded["ownership_range"] == ownership
    assert loaded["global_size"] == 2 * comm.size
    assert result["manifest_sha256"] == loaded["manifest_sha256"]
    comm.barrier()


def test_pre_recovery_packet_roundtrip_from_petsc_vec_preserves_metadata(
    tmp_path: Path,
) -> None:
    tmp_path, comm = _shared_packet_dir(tmp_path)
    solution_vec = PETSc.Vec().createMPI((2, 2 * comm.size), comm=comm)
    rhs_vec = PETSc.Vec().createMPI((2, 2 * comm.size), comm=comm)
    try:
        solution_vec.getArray()[:] = np.asarray(
            [1.0 + 0.5j + comm.rank, 2.0 - 0.25j - comm.rank],
            dtype=np.complex128,
        )
        rhs_vec.getArray()[:] = np.asarray(
            [3.0 + 0.75j, 4.0 - 0.5j], dtype=np.complex128
        )
        ownership = tuple(int(value) for value in solution_vec.getOwnershipRange())
        rank_offset = 2 * int(comm.rank)
        identity = {
            "source_sha": "a" * 40,
            "input_sha256": "b" * 64,
            "mpi_size": comm.size,
        }
        metadata = {
            "layout": {
                "type": "HybridAugmentedLayout",
                "global_size": 2 * comm.size,
                "bottom_ranges": [[rank, rank + 1] for rank in range(comm.size)],
                "top_ranges": [[rank, rank + 1] for rank in range(comm.size)],
                "combined_offsets": [2 * rank for rank in range(comm.size)],
                "rank_offset": rank_offset,
                "bottom_local_sizes": [1 for _ in range(comm.size)],
                "top_local_sizes": [1 for _ in range(comm.size)],
                "modal_count": 0,
                "modal_owner": comm.size - 1,
            },
            "solve_report": {
                "pass": False,
                "relative_residual": 2.5e-8,
                "reason": "diagnostic_failed_gate",
                "backsolve_count": 1,
            },
            "qualification": "diagnostic-only",
        }
        result = write_packet(
            tmp_path,
            solution_vec.getArray(readonly=True),
            rhs_vec.getArray(readonly=True),
            identity=identity,
            metadata=metadata,
            ownership_range=ownership,
            comm=comm,
        )
        assert result["pass"] is True
        loaded = load_packet(
            tmp_path / "manifest.json",
            identity=identity,
            expected_manifest_sha256=result["manifest_sha256"],
            comm=comm,
        )
        np.testing.assert_array_equal(
            loaded["solution"], solution_vec.getArray(readonly=True)
        )
        np.testing.assert_array_equal(loaded["rhs"], rhs_vec.getArray(readonly=True))
        assert loaded["ownership_range"] == ownership
        assert loaded["metadata"]["layout"]["modal_count"] == 0
        assert loaded["metadata"]["solve_report"] == metadata["solve_report"]
        assert loaded["metadata"]["qualification"] == "diagnostic-only"
    finally:
        solution_vec.destroy()
        rhs_vec.destroy()
    comm.barrier()


def test_pre_recovery_packet_nonfinite_diagnostic_is_global_failure(tmp_path: Path):
    tmp_path, comm = _shared_packet_dir(tmp_path)
    solution_vec = PETSc.Vec().createMPI((2, 2 * comm.size), comm=comm)
    rhs_vec = PETSc.Vec().createMPI((2, 2 * comm.size), comm=comm)
    try:
        solution_vec.getArray()[:] = np.asarray(
            [1.0 + 1.0j, 2.0 - 1.0j], dtype=np.complex128
        )
        if comm.rank == 0:
            solution_vec.getArray()[0] = np.nan + 0.0j
        rhs_vec.getArray()[:] = np.asarray(
            [1.0 + 0.0j, 2.0 + 0.0j], dtype=np.complex128
        )
        identity = {"source_sha": "c" * 40, "mpi_size": comm.size}
        ownership = tuple(int(value) for value in solution_vec.getOwnershipRange())
        result = write_packet(
            tmp_path,
            solution_vec.getArray(readonly=True),
            rhs_vec.getArray(readonly=True),
            identity=identity,
            metadata={
                "solve_report": {"pass": False, "reason": "nonfinite_residual"},
                "qualification": "diagnostic-only",
            },
            ownership_range=ownership,
            comm=comm,
            allow_nonfinite_diagnostic=True,
        )
        assert result["pass"] is False
        loaded = load_packet(
            tmp_path / "manifest.json",
            identity=identity,
            expected_manifest_sha256=result["manifest_sha256"],
            comm=comm,
        )
        if comm.rank == 0:
            assert np.isnan(loaded["solution"][0])
            manifest = json.loads((tmp_path / "manifest.json").read_text())
            assert manifest["diagnostic_nonfinite"] is True
        else:
            assert np.isfinite(loaded["solution"]).all()
        assert loaded["metadata"]["qualification"] == "diagnostic-only"
    finally:
        solution_vec.destroy()
        rhs_vec.destroy()
    comm.barrier()


def test_rank_pid_affinity_map_uses_one_real_comm_gather(tmp_path: Path):
    tmp_path, comm = _shared_packet_dir(tmp_path)
    if comm.rank == 0:
        tmp_path.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    _write_rank_pid_affinity(
        tmp_path,
        phase="consumer",
        source_sha="d" * 40,
        comm=comm,
    )
    mapping = json.loads(
        (tmp_path / "rank_pid_affinity.json").read_text(encoding="utf-8")
    )
    assert mapping["mpi_size"] == comm.size
    assert mapping["record_count"] == comm.size
    own = next(row for row in mapping["records"] if row["rank"] == comm.rank)
    assert own["pid"] == os.getpid()
    assert own["cpu_affinity_status"] in {"measured", "not_measured"}
    comm.barrier()


def test_pre_recovery_packet_manifest_tamper_is_rejected(tmp_path: Path) -> None:
    tmp_path, comm = _shared_packet_dir(tmp_path)
    result = write_packet(
        tmp_path,
        np.ones(2, dtype=np.complex128),
        np.ones(2, dtype=np.complex128),
        identity={"source_sha": "abc"},
        metadata={},
        ownership_range=(2 * comm.rank, 2 * (comm.rank + 1)),
        comm=comm,
    )
    manifest = tmp_path / "manifest.json"
    if comm.rank == 0:
        manifest.write_bytes(manifest.read_bytes().replace(b'"abc"', b'"tampered"'))
    comm.barrier()
    try:
        load_packet(
            manifest,
            expected_manifest_sha256=result["manifest_sha256"],
            comm=comm,
        )
    except ValueError as exc:
        assert "manifest hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered manifest was accepted")
    comm.barrier()


def test_pre_recovery_packet_rejects_overlapping_ownership() -> None:
    shards = [
        {"rank": 0, "size": 2, "ownership_range": [0, 2]},
        {"rank": 1, "size": 2, "ownership_range": [1, 3]},
    ]
    assert _ownership_is_contiguous(shards) is False


def test_pre_recovery_packet_rejects_rank_identity_mismatch(tmp_path: Path) -> None:
    tmp_path, comm = _shared_packet_dir(tmp_path)
    if comm.size < 2:
        pytest.skip("identity consistency requires multiple ranks")
    with pytest.raises(ValueError, match="identity hash differs"):
        write_packet(
            tmp_path,
            np.ones(2, dtype=np.complex128),
            np.ones(2, dtype=np.complex128),
            identity={"rank": comm.rank},
            metadata={},
            ownership_range=(2 * comm.rank, 2 * (comm.rank + 1)),
            comm=comm,
        )
    comm.barrier()
