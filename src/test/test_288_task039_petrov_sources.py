from __future__ import annotations

import numpy as np
import pytest
from types import SimpleNamespace
from mpi4py import MPI

from src.coupling.hybrid_internal_modes import build_single_hybrid_interface_mode_owner
from src.solvers.hybrid_petrov_sources import (
    V6_PORT_MODAL_CHECKPOINTS,
    V6_PORT_MODAL_HOLDOUT_SPECS,
    _fill_partition_independent_random,
    build_v6_owner_row_basis_checkpoint,
    v6_port_modal_source_contract,
    v6_port_modal_training_schedule,
    v6_source_identity,
)


def test_v6_single_interface_rejects_degree_mismatch_before_build():
    system = SimpleNamespace(side="bottom", cfg=SimpleNamespace(nedelec_degree=2))
    spaces = SimpleNamespace(transverse_degree=3)
    with pytest.raises(ValueError, match="matching Nedelec"):
        build_single_hybrid_interface_mode_owner(system, spaces, None, None)


def test_v6_training_contract_is_factor_free_and_disjoint_from_holdout():
    contract = v6_port_modal_source_contract()
    training = contract["training"]
    holdout = contract["holdout"]
    assert len(training) == 512
    assert contract["checkpoints"] == list(V6_PORT_MODAL_CHECKPOINTS)
    assert all(item["factor_free"] and not item["holdout"] for item in training)
    assert all(item["holdout"] for item in holdout)
    assert {item["label"] for item in holdout} == {
        item["label"] for item in V6_PORT_MODAL_HOLDOUT_SPECS
    }
    assert contract["training_reads_holdout_files"] is False
    assert {
        (item["label"], item["seed"], item.get("resolved_column")) for item in holdout
    } == {
        (item["label"], item["seed"], item.get("resolved_column"))
        for item in V6_PORT_MODAL_HOLDOUT_SPECS
    }
    assert contract["external_count"] == 296
    assert all("right_family" in item and "left_family" in item for item in training)
    assert {item["right_family"] for item in training} >= {
        "positive_modal_traction",
        "negative_modal_traction",
        "external_c",
        "hcurl_near_null_gradient",
        "physical_rhs",
    }
    assert "fixed_random" not in {item["right_family"] for item in training}
    assert {item["left_family"] for item in training} == {
        "projection_dual",
        "positive_modal_dual",
        "negative_modal_dual",
        "external_dual",
    }
    assert len(contract["sha256"]) == 64


def test_v6_training_schedule_deterministic_and_column_bound():
    first = v6_port_modal_training_schedule(mode_count=480)
    second = v6_port_modal_training_schedule(mode_count=480)
    assert first == second
    assert all(
        0 <= item["right_selector"]["column"] < 480
        for item in first[1:]
        if "column" in item["right_selector"]
    )
    assert first[0]["right_selector"]["absent_if_zero"] is True
    assert first[0]["right_selector"]["fallback"]["selector"] == (
        "cross_section_discrete_gradient_potential"
    )
    assert first[0]["right_selector"]["fallback"]["potential_ordinal"] == 127
    hcurl_ordinals = [
        item["right_selector"]["potential_ordinal"]
        for item in first
        if item["right_family"] == "hcurl_near_null_gradient"
    ]
    assert hcurl_ordinals == list(range(127))
    assert 127 not in hcurl_ordinals
    assert all(
        "seed" not in item["right_selector"]
        for item in first
        if item["right_family"] == "hcurl_near_null_gradient"
    )
    assert all(
        item["right_selector"]["column"] < 296
        for item in first
        if item["right_family"] == "external_c"
    )
    for family, selector_key in (
        ("positive_modal_traction", "right_selector"),
        ("negative_modal_traction", "right_selector"),
        ("external_c", "right_selector"),
        ("positive_modal_dual", "left_selector"),
        ("negative_modal_dual", "left_selector"),
        ("external_dual", "left_selector"),
    ):
        columns = [
            item[selector_key]["column"]
            for item in first
            if item[
                "right_family" if selector_key == "right_selector" else "left_family"
            ]
            == family
        ]
        assert len(columns) == len(set(columns))
    assert all(
        "seed" in item["left_selector"]
        for item in first
        if item["left_family"] == "projection_dual"
    )


class _TinyOwnerVector:
    def __init__(self, first: int, last: int):
        self.first = first
        self.last = last
        self.values = np.zeros(last - first, dtype=np.complex128)

    def getOwnershipRange(self):
        return self.first, self.last

    def getArray(self):
        return self.values

    def assemble(self):
        return None


def test_v6_counter_random_is_partition_independent_and_high_rank():
    row_count = 96
    owned = np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    local = _TinyOwnerVector(int(owned[0]), int(owned[-1] + 1))
    _fill_partition_independent_random(local, 6039071)
    chunks = MPI.COMM_WORLD.allgather(local.values)
    serial = _TinyOwnerVector(0, row_count)
    _fill_partition_independent_random(serial, 6039071)
    np.testing.assert_allclose(np.concatenate(chunks), serial.values)

    seeds = [6039071 + 101 * index for index in range(32)]
    matrix = np.empty((row_count, len(seeds)), dtype=np.complex128)
    for column, seed in enumerate(seeds):
        vector = _TinyOwnerVector(0, row_count)
        _fill_partition_independent_random(vector, seed)
        matrix[:, column] = vector.values
    assert np.linalg.matrix_rank(matrix, tol=1.0e-10) == len(seeds)


def test_v6_owner_row_qr_uses_complex_adjoint_and_fixed_prefix():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused owner-row QR fixture supports MPI1/2/4")
    row_count = 96
    first, last = (
        np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[MPI.COMM_WORLD.rank][
            [0, -1]
        ]
        if MPI.COMM_WORLD.size > 1
        else (0, row_count - 1)
    )
    rng = np.random.default_rng(288)
    full_z = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    full_y = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    z = np.asarray(full_z[first : last + 1], dtype=np.complex128)
    y = np.asarray(full_y[first : last + 1], dtype=np.complex128)
    qz, qy, diagnostics = build_v6_owner_row_basis_checkpoint(z, y, 64)
    assert qz.shape == (last - first + 1, 64)
    assert qy.shape == (last - first + 1, 64)
    assert diagnostics["global_basis_materialized"] is False
    assert diagnostics["owner_row_local"] is True
    assert diagnostics["rank"] == 64
    assert diagnostics["z_orthogonality_error"] <= 1.0e-10
    assert diagnostics["y_orthogonality_error"] <= 1.0e-10
    assert diagnostics["z_reconstruction_relative_error"] <= 1.0e-12
    assert diagnostics["y_reconstruction_relative_error"] <= 1.0e-12
    assert np.isfinite(diagnostics["cross_yh_z_condition"])


def test_v6_owner_row_qr_prefixes_are_nested():
    if MPI.COMM_WORLD.size not in (1, 2, 4):
        pytest.skip("focused owner-row QR fixture supports MPI1/2/4")
    row_count = 192
    owned = np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    rng = np.random.default_rng(2881)
    full_z = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    full_y = rng.standard_normal((row_count, 512)) + 1j * rng.standard_normal(
        (row_count, 512)
    )
    z64, y64, _ = build_v6_owner_row_basis_checkpoint(full_z[owned], full_y[owned], 64)
    z128, y128, diagnostics = build_v6_owner_row_basis_checkpoint(
        full_z[owned], full_y[owned], 128
    )
    overlap_z = np.empty((64, 128), dtype=np.complex128)
    overlap_y = np.empty((64, 128), dtype=np.complex128)
    MPI.COMM_WORLD.Allreduce(z64.conj().T @ z128, overlap_z, op=MPI.SUM)
    MPI.COMM_WORLD.Allreduce(y64.conj().T @ y128, overlap_y, op=MPI.SUM)
    assert np.linalg.norm(overlap_z @ overlap_z.conj().T - np.eye(64)) <= 1.0e-10
    assert np.linalg.norm(overlap_y @ overlap_y.conj().T - np.eye(64)) <= 1.0e-10
    assert np.isfinite(diagnostics["cross_yh_z_condition"])


def test_v6_owner_row_qr_rank_failure_is_collective():
    row_count = 96
    owned = np.array_split(np.arange(row_count), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    column = np.ones((owned.size, 64), dtype=np.complex128)
    with pytest.raises(ValueError, match="rank deficient"):
        build_v6_owner_row_basis_checkpoint(column, column, 64)


def test_v6_source_identity_reduces_only_hash_metadata():
    global_rows = 2 * MPI.COMM_WORLD.size
    owned = np.array_split(np.arange(global_rows), MPI.COMM_WORLD.size)[
        MPI.COMM_WORLD.rank
    ]
    values = np.asarray(owned + 1.0j * (owned + 1.0), dtype=np.complex128)
    identity = v6_source_identity(
        values,
        label="external_c",
        seed=6039071,
        global_rows=global_rows,
        ownership_range=(int(owned[0]), int(owned[-1] + 1)),
    )
    assert identity["dtype"] == "complex128"
    assert identity["global_rows"] == global_rows
    assert identity["ownership_range"] == [int(owned[0]), int(owned[-1] + 1)]
    assert identity["owner_hashes"][0]["sha256"]
