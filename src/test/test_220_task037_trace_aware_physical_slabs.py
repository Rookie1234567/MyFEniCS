from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers import physical_slab_two_level as slab_module


class _FakeMatrix:
    def getComm(self):
        return self

    def tompi4py(self):
        return MPI.COMM_WORLD


def _fake_condensed(permutation):
    parts = np.array_split(np.arange(3), MPI.COMM_WORLD.size)
    owned = [int(cell) for cell in parts[MPI.COMM_WORLD.rank]]
    originals = ((10, 11), (20, 21), (30, 31))
    old_rows = (
        ((0,), (1,)),
        ((1, 2), (3,)),
        ((3,), (4,)),
    )
    expansion = {}
    recovery_maps = []
    for cell in owned:
        recovery_maps.append(
            SimpleNamespace(trace_original_dofs=np.asarray(originals[cell]))
        )
        for original, rows in zip(originals[cell], old_rows[cell], strict=True):
            expansion[original] = (
                np.asarray([permutation[row] for row in rows], dtype=PETSc.IntType),
                np.ones(len(rows), dtype=np.complex128),
            )
    return SimpleNamespace(
        matrix=_FakeMatrix(),
        cell_recovery_maps=tuple(recovery_maps),
        trace_constraints=SimpleNamespace(expansion_by_original=expansion),
        active_rows=5,
        appended_rows=80,
    )


def test_nonuniform_trace_support_is_partition_independent(monkeypatch):
    parts = np.array_split(np.arange(3), MPI.COMM_WORLD.size)
    z_bounds = ((0.0, 0.4), (0.4, 1.6), (1.6, 2.0))

    def fake_canonical_owned_cell_ids(_mesh):
        owned = [int(cell) for cell in parts[MPI.COMM_WORLD.rank]]
        records = [
            SimpleNamespace(
                coordinates=np.asarray(
                    [[0.0, 0.0, z_bounds[cell][0]], [0.0, 0.0, z_bounds[cell][1]]]
                )
            )
            for cell in owned
        ]
        return np.asarray(owned, dtype=np.int64), records, []

    monkeypatch.setattr(
        slab_module, "canonical_owned_cell_ids", fake_canonical_owned_cell_ids
    )
    original, original_audit = slab_module.build_trace_aware_physical_slab_partition(
        _fake_condensed(tuple(range(5))),
        SimpleNamespace(),
        domain_z=(0.0, 2.0),
        num_slabs=2,
        overlap_fraction=0.25,
    )
    np.testing.assert_array_equal(original[0], [0, 1, 2, 3])
    np.testing.assert_array_equal(original[1], [1, 2, 3, 4])
    assert original_audit["active_rows"] == 5
    assert original_audit["appended_rows"] == 80
    assert original_audit["auxiliary_rows_in_subdomains"] == 0
    assert original_audit["coverage_pass"]
    assert original_audit["union_rows"] == 5
    assert original_audit["out_of_range_rows"] == 0
    assert original_audit["slab_row_counts"] == [4, 4]
    assert original_audit["multiplicity_histogram"] == {"1": 2, "2": 3}
    assert original_audit["max_multiplicity"] == 2
    assert original_audit["multiplicity_gt_one_rows"] == 3
    assert original_audit["multiplicity_eq_one_rows"] == 2

    permuted, permuted_audit = slab_module.build_trace_aware_physical_slab_partition(
        _fake_condensed((4, 3, 2, 1, 0)),
        SimpleNamespace(),
        domain_z=(0.0, 2.0),
        num_slabs=2,
        overlap_fraction=0.25,
    )
    np.testing.assert_array_equal(permuted[0], [1, 2, 3, 4])
    np.testing.assert_array_equal(permuted[1], [0, 1, 2, 3])
    assert (
        permuted_audit["global_support_hash"] == original_audit["global_support_hash"]
    )
    assert (
        permuted_audit["per_slab_support_hashes"]
        == original_audit["per_slab_support_hashes"]
    )
    assert original_audit["global_support_hash"] == (
        "2119712198d6d28763045097e335397cc0005eb78d1150e8ed9cf47c86692c03"
    )
    assert original_audit["per_slab_support_hashes"] == [
        "bc4ee47116820b6a57153ecac146c47ec91132ef34ec3012e2d4dee3aa91bb88",
        "2e5f12c36705c7bc34deb3f9c733ad4656422f56e6896f27be7c25e6d2c1d63b",
    ]
