from pathlib import Path
import shutil

from mpi4py import MPI
import numpy as np
import pytest

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
