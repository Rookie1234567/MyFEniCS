import numpy as np
import pytest

from src.solvers.carrier_checkpoint import CarrierCheckpoint


@pytest.fixture
def case():
    context = {
        name: "a" * 64
        for name in (
            "numerical_source_sha256",
            "mesh_sha256",
            "space_sha256",
            "mpc_sha256",
            "boundary_sha256",
            "material_incidence_sha256",
            "mode_manifest_sha256",
        )
    }
    context.update(
        surface_quadrature_degree=81,
        quadrature_rule="default",
        sparse_cutoff_policy="relative-only",
        sparse_cutoff_relative_tolerance=1e-13,
        global_rows=100,
        scalar_dtype="complex128",
        row_dtype="int64",
    )
    mode = {"side": "top", "m": -8, "n": -64, "polarization": "s"}
    arrays = {
        "coupling_rows": np.array([0, 3], dtype=np.int64),
        "coupling_values": np.array([1 + 2j, 3 - 4j], dtype=np.complex128),
        "projection_rows": np.array([2, 99], dtype=np.int64),
        "projection_values": np.array([-5 + 6j, 7 + 8j], dtype=np.complex128),
    }
    return context, mode, arrays


def test_carrier_exact_resume_and_prefix(tmp_path, case):
    context, mode, arrays = case
    store = CarrierCheckpoint(tmp_path, context)
    store.commit(0, mode, arrays, 2.5)
    store.commit(2, mode, arrays, 2.5)
    resumed = store.restore_prefix([mode, mode, mode])
    assert len(resumed) == 1  # Never claim a missing intermediate mode is restored.
    assert resumed[0]["normalization_h"] == 2.5
    for name, array in arrays.items():
        assert resumed[0]["arrays"][name].tobytes() == array.tobytes()
        assert not resumed[0]["arrays"][name].flags.writeable


@pytest.mark.parametrize(
    "field,value",
    [
        ("surface_quadrature_degree", 160),
        ("sparse_cutoff_policy", "legacy"),
        ("sparse_cutoff_relative_tolerance", 1e-12),
        ("mesh_sha256", "b" * 64),
        ("mpc_sha256", "b" * 64),
        ("runtime_abi", {"extension": "b" * 64}),
    ],
)
def test_carrier_changed_context_never_hits(tmp_path, case, field, value):
    context, mode, arrays = case
    first = CarrierCheckpoint(tmp_path, context)
    first.commit(0, mode, arrays, 2.5)
    second = CarrierCheckpoint(tmp_path, {**context, field: value})
    assert second.load(0, mode) is None


def test_carrier_corruption_mode_change_and_conflict(tmp_path, case):
    context, mode, arrays = case
    store = CarrierCheckpoint(tmp_path, context)
    store.commit(0, mode, arrays, 2.5)
    with pytest.raises(ValueError, match="mode identity"):
        store.load(0, {**mode, "n": -63})
    with pytest.raises(ValueError, match="conflicting"):
        store.commit(0, mode, arrays, 3.5)
    payload = store.root / "0/arrays.npz"
    payload.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.load(0, mode)


def test_carrier_uncommitted_payload_and_bad_rows(tmp_path, case):
    context, mode, arrays = case
    store = CarrierCheckpoint(tmp_path, context)
    folder = store.root / "0"
    folder.mkdir()
    np.savez(folder / "arrays.npz", **arrays)
    assert store.load(0, mode) is None
    arrays["coupling_rows"][1] = 100
    with pytest.raises(ValueError, match="outside bound"):
        store.commit(0, mode, arrays, 2.5)


def test_carrier_disk_budget_rejects_before_marker(tmp_path, case):
    context, mode, arrays = case
    store = CarrierCheckpoint(tmp_path, context, max_shard_bytes=1)
    with pytest.raises(RuntimeError, match="disk budget"):
        store.commit(0, mode, arrays, 2.5)
    assert store.load(0, mode) is None
