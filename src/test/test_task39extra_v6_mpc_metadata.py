"""Exact MPC metadata borrowing and small real-FE diagonal regression."""

from __future__ import annotations

import numpy as np
import pytest

from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import (
    _cell_expansion_workspace,
    _fill_cell_expansion,
    _mpc_expansion_metadata,
)


@pytest.mark.parametrize("offset_dtype", [np.int32, np.int64])
def test_mpc_borrowed_metadata_preserves_complex_expansion_and_provider_dtype(
    offset_dtype,
):
    class Masters:
        def __init__(self):
            self.calls = 0

        def links(self, row):
            self.calls += 1
            return {
                2: np.array([0, 1], dtype=np.int32),
                3: np.array([1], dtype=np.int32),
            }[int(row)]

    class MPC:
        def __init__(self):
            self.slaves = np.array([2, 3], dtype=np.int32)
            self._masters = Masters()
            self.master_property_calls = 0
            self.coefficient_calls = 0
            self.values = np.array(
                [.7 + .2j, -.1 + .3j, .5 - .2j], dtype=np.complex128
            )
            self.offsets = np.array([0, 0, 0, 2, 3], dtype=offset_dtype)

        @property
        def masters(self):
            self.master_property_calls += 1
            return self._masters

        def coefficients(self):
            self.coefficient_calls += 1
            return self.values, self.offsets

    mpc = MPC()
    metadata = _mpc_expansion_metadata(mpc)
    assert metadata[0] is mpc.values
    assert metadata[1] is mpc.offsets
    assert metadata[1].dtype == np.dtype(offset_dtype)
    assert metadata[2] is mpc._masters
    _, mask, targets, coefficients = _cell_expansion_workspace(
        mpc, 4, 3, expansion_metadata=metadata
    )
    optimized = []
    cells = (np.array([0, 2, 3]), np.array([1, 2, 3]))
    for local_dofs in cells:
        _fill_cell_expansion(
            local_dofs, mpc, 4, mask, targets, coefficients,
            expansion_metadata=metadata,
        )
        optimized.append((targets.copy(), coefficients.copy()))
    assert mpc.coefficient_calls == 1
    assert mpc.master_property_calls == 1
    optimized_master_calls = mpc._masters.calls

    for local_dofs, expected in zip(cells, optimized, strict=True):
        _fill_cell_expansion(local_dofs, mpc, 4, mask, targets, coefficients)
        np.testing.assert_array_equal(targets, expected[0])
        np.testing.assert_array_equal(coefficients, expected[1])
    assert mpc.coefficient_calls == 3
    assert mpc.master_property_calls == 5
    assert mpc._masters.calls == optimized_master_calls + 4


@pytest.mark.parametrize("offsets", [np.array([0.0, 1.0]), np.array([False, True])])
def test_mpc_borrowed_offsets_reject_nonintegral_provider_metadata(offsets):
    class MPC:
        def coefficients(self):
            return np.array([1 + .2j]), offsets

    with pytest.raises(ValueError, match="coefficient/offset metadata"):
        _mpc_expansion_metadata(MPC())


def test_p3_metric_diagonal_matches_ffcx_for_physical_and_artificial_mpc():
    from dolfinx import fem
    from mpi4py import MPI

    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_lor_native_hx_fixture import (
        _piecewise_positive_coefficients,
    )
    from src.solvers.fullspace_metric_positive_diagonal import (
        build_reference_metric_positive_diagonal,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        build_small_same_mesh_positive_case,
        destroy_small_same_mesh_positive_case,
        same_mesh_positive_form,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_p6 import (
        build_constrained_jacobi_diagonal,
    )

    cfg = target_stage4_config(degree=3, h_nm=50.0)
    case = build_small_same_mesh_positive_case(
        cfg, MPI.COMM_WORLD, source_name="random"
    )
    diagonal = reference = difference = None
    actual_diagonal = actual_reference = actual_difference = None
    mu = mass = None
    try:
        space = case["fine_space"]
        assert int(space.element.basix_element.degree) == 3
        cell_dofs = np.asarray(space.dofmap.cell_dofs(0), dtype=np.int32)
        slave_multi, master_a, master_b, slave_merge = map(int, cell_dofs[:4])

        # Keep the FE mesh and FFCx form real; this explicit MPC-compatible
        # map forces the shared-target complex multi-master branch because the
        # physical Floquet map on this small fixture has singleton rows only.
        class Masters:
            def links(self, row):
                return {
                    slave_multi: np.array([master_a, master_b], dtype=np.int32),
                    slave_merge: np.array([master_b], dtype=np.int32),
                }[int(row)]

        class MPC:
            def __init__(self):
                self.function_space = space
                self.slaves = np.array([slave_multi, slave_merge], dtype=np.int32)
                self.masters = Masters()
                self.offsets = np.zeros(
                    int(space.dofmap.index_map.size_local)
                    + int(space.dofmap.index_map.num_ghosts)
                    + 1,
                    dtype=np.int32,
                )
                self.coefficient_values = []
                for row in range(self.offsets.size - 1):
                    if row == slave_multi:
                        self.coefficient_values.extend([.7 + .2j, -.1 + .3j])
                    elif row == slave_merge:
                        self.coefficient_values.append(.5 - .2j)
                    self.offsets[row + 1] = len(self.coefficient_values)
                self.coefficient_values = np.asarray(
                    self.coefficient_values, dtype=np.complex128
                )

            def coefficients(self):
                return self.coefficient_values, self.offsets

        mpc = MPC()
        assert np.max(np.diff(mpc.offsets), initial=0) == 2
        assert np.max(np.abs(mpc.coefficient_values.imag), initial=0.0) > 0.0

        mu, mass, _ = _piecewise_positive_coefficients(
            case["mesh"], case["mesh_data"].cell_tags, cfg
        )
        compiled = fem.form(
            same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
        )

        physical_mpc = case["fine_floquet"].mpc
        _, physical_offsets = physical_mpc.coefficients()
        assert np.max(np.diff(np.asarray(physical_offsets)), initial=0) == 1
        physical_audit = {}
        actual_diagonal = build_reference_metric_positive_diagonal(
            space, mu, mass, physical_mpc, audit=physical_audit
        )
        actual_reference = build_constrained_jacobi_diagonal(compiled, physical_mpc)
        actual_difference = actual_diagonal.copy()
        actual_difference.axpy(-1.0, actual_reference)
        actual_relative = float(actual_difference.norm()) / max(
            float(actual_reference.norm()), np.finfo(np.float64).tiny
        )
        actual_local_max = float(
            np.max(np.abs(actual_difference.array), initial=0.0)
        )
        actual_maximum = float(
            MPI.COMM_WORLD.allreduce(actual_local_max, op=MPI.MAX)
        )
        assert actual_relative <= 1.0e-11
        assert actual_maximum <= 1.0e-10
        assert physical_audit["mpc_coefficient_provider_calls"] == 1
        assert physical_audit["mpc_offsets_dtype"] == str(np.asarray(physical_offsets).dtype)

        # Artificial multi-master mapping below is a separate fallback witness;
        # it does not represent this physical singleton Floquet map.
        audit = {}
        diagonal = build_reference_metric_positive_diagonal(
            space, mu, mass, mpc, audit=audit
        )
        reference = build_constrained_jacobi_diagonal(compiled, mpc)
        difference = diagonal.copy()
        difference.axpy(-1.0, reference)
        relative = float(difference.norm()) / max(
            float(reference.norm()), np.finfo(np.float64).tiny
        )
        local_max = float(np.max(np.abs(difference.array), initial=0.0))
        maximum = float(MPI.COMM_WORLD.allreduce(local_max, op=MPI.MAX))
        assert relative <= 1.0e-11
        assert maximum <= 1.0e-10
        assert audit["mpc_expansion_metadata_policy"] == "borrowed_once_for_this_build"
        assert audit["mpc_coefficient_provider_calls"] == 1
        assert audit["mpc_offsets_dtype"] == str(mpc.offsets.dtype)
        assert audit["mpc_offsets_array_bytes"] == mpc.offsets.nbytes
        assert audit["mpc_global_offset_conversion_copies"] == 0
        assert audit["mpc_expansion_metadata_retained_after_return"] is False
        assert audit["target_merge_fallbacks"] > 0
        assert audit["target_cross_terms_preserved_by_fallback"] is True
    finally:
        for vector in (
            difference,
            reference,
            diagonal,
            actual_difference,
            actual_reference,
            actual_diagonal,
        ):
            if vector is not None:
                vector.destroy()
        del mu, mass
        destroy_small_same_mesh_positive_case(case)
