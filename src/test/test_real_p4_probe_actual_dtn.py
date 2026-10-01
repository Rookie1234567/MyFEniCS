"""A tiny real Fourier-DtN fixture without whole-case visualization imports.

This checks existing port wiring on a small p2 mesh, not G0 physics or p4
precision. The explicit modal sum is the same independent algebra oracle used
by test_271, with direct public configuration instead of its eager utilities.
"""

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_physical_rhs, build_same_mesh_physical_action, destroy_same_mesh_physical_action,
)
from src.solvers.dtn_port_3d import (
    _ReusableSurfaceComponentAssembler, _combine_owned_entries,
    _mode_projection_denominator, _traction_vector,
)
from src.solvers.real_p4_probe import _symbolic_parent_quadrature


def test_actual_p2_dtn_surface_matches_independent_modal_sum():
    cfg = target_stage4_config(degree=2, h_nm=100.)
    cfg.stage4_dtn_order_policy = "zero_order"
    cfg.diffraction_zero_order_only = True
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (2,), include_positive_coefficients=False)
    assert set(levels["spaces"]) == {2}
    assert int(levels["mesh"].topology.index_map(3).size_local) <= 32
    # The new exporter analyzes degree-six quadrature symbolically only.
    # Exercise that adapter on a tiny real mesh, with no p6 space allocation.
    quadrature, records = _symbolic_parent_quadrature(levels, cfg)
    assert len(quadrature) == 2 and records
    native = build_same_mesh_physical_action(levels, cfg, 2, volume_quadrature_metadata=quadrature)
    source = target = expected = None
    try:
        source, rhs_facts = build_physical_rhs(native)
        assert rhs_facts["generation"] == "dtn_port_modal_physical_rhs" and source.norm() > 0
        assert len(native["modes"]) == 4
        assemblers = {(side, component): _ReusableSurfaceComponentAssembler(
            levels["spaces"][2], levels["mesh_data"],
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component, quadrature_degree=native["dtn_quadrature_degree"],
        ) for side in ("top", "bottom") for component in (0, 1)}
        expected = source.duplicate()
        expected.set(0)
        amplitudes = np.empty(len(native["modes"]), dtype=np.complex128)
        start, _ = source.getOwnershipRange()
        for index, mode in enumerate(native["modes"]):
            components = tuple(assemblers[(mode.side, component)].assemble_entries(
                mode, levels["floquets"][2].mpc) for component in (0, 1))
            rows, values = _combine_owned_entries(components, (mode.e_vector[0], mode.e_vector[1]), comm=MPI.COMM_SELF)
            traction = _traction_vector(mode, cfg)
            coupling_rows, coupling_values = _combine_owned_entries(components, (-traction[0], -traction[1]), comm=MPI.COMM_SELF)
            amplitude = np.vdot(values, source.array[rows - start]) / _mode_projection_denominator(mode, cfg)
            amplitudes[index] = amplitude
            expected.array[coupling_rows - start] += amplitude * coupling_values
        target = source.duplicate()
        native["dtn_action"].apply(source, target)
        np.testing.assert_allclose(native["dtn_action"].recover_auxiliary(source), amplitudes, atol=1e-11, rtol=0)
        error = target.array - expected.array
        assert np.linalg.norm(error) / max(expected.norm(), np.finfo(float).tiny) <= 1e-11
        slaves = np.asarray(levels["floquets"][2].mpc.slaves, dtype=np.int64)
        assert np.all(target.array[slaves] == 0)
    finally:
        for vector in (source, target, expected):
            if vector is not None:
                vector.destroy()
        destroy_same_mesh_physical_action(native)
