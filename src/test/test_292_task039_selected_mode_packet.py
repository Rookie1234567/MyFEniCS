import gc
import inspect
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest

from benchmarks.task039_v4_selected_mode_packet import (
    hydrate_task039_v4_selected_mode_packet,
    load_task039_v4_selected_mode_packet,
    write_task039_v4_selected_mode_packet,
)
from src.modes.selected_mode_packet import (
    MODE_PACKET_SCHEMA,
    write_selected_mode_packet,
)
import src.modes.selected_mode_packet as selected_mode_packet
from src.modes.stable_propagation import build_two_sided_propagation


V4_PACKET_SCOPE = "task039_v4_h4_m480"


def _shared_directory(tmp_path: Path) -> tuple[Path, MPI.Intracomm]:
    comm = MPI.COMM_WORLD
    directory = Path(comm.bcast(str(tmp_path), root=0))
    if comm.rank == 0:
        shutil.rmtree(directory, ignore_errors=True)
    comm.barrier()
    return directory, comm


def _identity(comm: MPI.Intracomm) -> dict[str, object]:
    return {
        "source_sha": "0123456789abcdef0123456789abcdef01234567",
        "input_sha256": "input-sha",
        "resolved_sha256": "resolved-sha",
        "physical_sha256": "physical-sha",
        "mesh": "mesh-sha",
        "mode_count": 480,
        "external_keys": "external-key-set-sha",
        "mpi": comm.size,
    }


def _metadata() -> dict[str, object]:
    return {
        "trace_mapping": {"layout": "cross_section_rows"},
        "canonical_mapping": {"active": "selected_mode_columns"},
        "gram_authority": {
            "positive": {"condition": 1.25, "max_identity_error": 2.0e-13},
            "negative": {"condition": 1.30, "max_identity_error": 3.0e-13},
        },
        "qep_diagnostics": {
            "positive": {"right_residual_max": 3.0e-14},
            "negative": {"right_residual_max": 4.0e-14},
        },
        "selection_diagnostics": {
            "positive": {"candidate_count": 960, "selected_count": 480},
            "negative": {"candidate_count": 960, "selected_count": 480},
        },
    }


def _branches(comm: MPI.Intracomm) -> tuple[dict[str, object], tuple[int, int]]:
    rows = 3
    start = rows * comm.rank
    base = np.arange(rows * 480, dtype=np.float64).reshape(rows, 480)
    beta = (
        np.arange(480, dtype=np.float64) + 1j * np.arange(480, dtype=np.float64) / 100.0
    )
    return {
        "positive": {
            "right_full": (base + 1.0 + comm.rank).astype(np.complex128),
            "left_full": (2.0 * base + 2.0 + 1j * comm.rank).astype(np.complex128),
            "beta": beta,
            "direction": "forward",
        },
        "negative": {
            "right_full": (3.0 * base + 3.0 + 2j * comm.rank).astype(np.complex128),
            "left_full": (4.0 * base + 4.0 + 3j * comm.rank).astype(np.complex128),
            "beta": beta * -1.0,
            "direction": "backward",
        },
    }, (start, start + rows)


class _FakeVec:
    def __init__(self, values: np.ndarray, start: int) -> None:
        self.values = np.asarray(values, dtype=np.complex128)
        self.start = int(start)

    def getOwnershipRange(self) -> tuple[int, int]:
        return self.start, self.start + self.values.size

    def getArray(self, *, readonly: bool = False) -> np.ndarray:
        assert readonly
        return self.values


def _fake_basis(
    branch: dict[str, object], ownership: tuple[int, int]
) -> SimpleNamespace:
    modes = []
    for index, beta in enumerate(branch["beta"]):
        modes.append(
            SimpleNamespace(
                right=SimpleNamespace(
                    right_full=_FakeVec(branch["right_full"][:, index], ownership[0])
                ),
                left_full=_FakeVec(branch["left_full"][:, index], ownership[0]),
                beta=beta,
                kind="propagating",
                direction=branch["direction"],
                passive_branch_valid=True,
            )
        )
    groups = tuple(
        SimpleNamespace(indices=tuple(range(start, start + 8)))
        for start in range(0, 480, 8)
    )
    return SimpleNamespace(modes=modes, groups=groups)


def _make_petsc_vec(
    values: np.ndarray, ownership: tuple[int, int], comm: MPI.Intracomm
):
    local_size = ownership[1] - ownership[0]
    vector = PETSc.Vec().createMPI((local_size, local_size * comm.size), comm=comm)
    assert tuple(int(value) for value in vector.getOwnershipRange()) == ownership
    vector.getArray()[:] = values
    return vector


def test_task039_v4_streaming_roundtrip_hydrates_two_bases_and_collective_gram(
    tmp_path: Path,
) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    positive_basis = _fake_basis(branches["positive"], ownership)
    negative_basis = _fake_basis(branches["negative"], ownership)
    result = write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=positive_basis,
        negative_basis=negative_basis,
        identity=_identity(comm),
        metadata=_metadata(),
        comm=comm,
    )
    loaded = load_task039_v4_selected_mode_packet(
        directory / "manifest.json",
        identity=_identity(comm),
        expected_manifest_sha256=result["manifest_sha256"],
        comm=comm,
    )
    assert loaded["schema"] == MODE_PACKET_SCHEMA
    assert loaded["scope"] == V4_PACKET_SCOPE
    assert loaded["global_size"] == 3 * comm.size
    for branch_name in ("positive", "negative"):
        for side in ("right_full", "left_full"):
            array = loaded[branch_name][side]
            assert isinstance(array, np.memmap)
            assert array.shape == (480, ownership[1] - ownership[0])
            assert array.flags.writeable is False
        assert loaded["selection"][branch_name]["passive_branch_valid"] == [True] * 480
    hydrated = hydrate_task039_v4_selected_mode_packet(loaded, comm=comm)
    assert len(hydrated.positive_basis.modes) == 480
    assert len(hydrated.negative_basis.modes) == 480
    assert hydrated.positive_basis is not hydrated.negative_basis
    old_propagation = build_two_sided_propagation(
        [*positive_basis.modes, *negative_basis.modes], 1.0
    )
    new_propagation = build_two_sided_propagation(
        [*hydrated.positive_basis.modes, *hydrated.negative_basis.modes], 1.0
    )
    assert old_propagation.forward.factors == new_propagation.forward.factors
    assert old_propagation.backward.factors == new_propagation.backward.factors
    old_vectors = []
    try:
        for index in (0, 239, 479):
            old_left = _make_petsc_vec(
                branches["positive"]["left_full"][:, index], ownership, comm
            )
            old_right = _make_petsc_vec(
                branches["positive"]["right_full"][:, index], ownership, comm
            )
            old_vectors.extend((old_left, old_right))
            new_mode = hydrated.positive_basis.modes[index]
            assert np.isclose(
                complex(old_left.dot(old_right)),
                complex(new_mode.left_full.dot(new_mode.right.right_full)),
            )
    finally:
        for vector in old_vectors:
            vector.destroy()
    diagnostics = hydrated.packet_consumer_diagnostics
    assert diagnostics["qep_calls"] == 0
    assert diagnostics["consumer_qep_required"] is False
    assert diagnostics["rank_historical_peak_rss_after_hydrate"] > 0.0
    assert diagnostics["hydrate_rss_delta_mib"] == "not_measured"
    hydrated.destroy()
    assert diagnostics["destroyed"] is True
    assert diagnostics["vector_count_after_destroy"] == 0
    del hydrated, loaded, result
    gc.collect()
    comm.barrier()


def test_selected_mode_packet_requires_explicit_scope(tmp_path: Path) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    bases = {
        name: _fake_basis(branches[name], ownership)
        for name in ("positive", "negative")
    }
    with pytest.raises(ValueError, match="explicit scope"):
        write_selected_mode_packet(
            directory,
            bases,
            identity=_identity(comm),
            metadata=_metadata(),
            comm=comm,
        )
    comm.barrier()


def test_selected_mode_packet_hash_corruption_is_rejected(tmp_path: Path) -> None:
    directory, comm = _shared_directory(tmp_path)
    branches, ownership = _branches(comm)
    bases = {
        name: _fake_basis(branches[name], ownership)
        for name in ("positive", "negative")
    }
    result = write_task039_v4_selected_mode_packet(
        directory,
        positive_basis=bases["positive"],
        negative_basis=bases["negative"],
        identity=_identity(comm),
        metadata=_metadata(),
        comm=comm,
    )
    comm.barrier()
    with (directory / f"rank{comm.rank:04d}_positive_right.npy").open("ab") as stream:
        stream.write(b"corruption")
    comm.barrier()
    with pytest.raises(ValueError, match="shard hash mismatch"):
        load_task039_v4_selected_mode_packet(
            directory / "manifest.json",
            expected_manifest_sha256=result["manifest_sha256"],
            comm=comm,
        )
    comm.barrier()


def test_task039_v4_scope_binds_mode_count() -> None:
    identity = {"mode_count": 479}
    with pytest.raises(ValueError, match="mode_count=480"):
        from benchmarks.task039_v4_selected_mode_packet import (
            _require_task039_identity,
        )

        _require_task039_identity(identity)


def test_packet_core_has_no_solver_or_qep_dependency() -> None:
    source = inspect.getsource(selected_mode_packet)
    assert "petsc4py" not in source
    assert "quadratic_beta_eigenproblem" not in source
    assert "npz" not in source
    assert "read_bytes" in source
    assert selected_mode_packet.MODE_PACKET_SCHEMA == MODE_PACKET_SCHEMA
    manifest = {"qep_workspace_persisted": False, "consumer_qep_required": False}
    assert not {"eps", "st", "ksp", "pc", "factor", "workspace"}.intersection(manifest)
    json.dumps(manifest)
