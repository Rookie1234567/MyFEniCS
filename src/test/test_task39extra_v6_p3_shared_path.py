"""Real p3 component regression of the same public optimizations as p4."""
from dataclasses import replace

import numpy as np
from dolfinx.la.petsc import create_vector
from mpi4py import MPI

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.runners.physical_retained_condensed_v20 import _compile_volume_form
from src.solvers.fullspace_physical_intermediate import apply_owned
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
)
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _tabulate_raw_tensor_class,
)
from src.solvers.hcurl_blocked_gram_tensor import HcurlBlockedGramTensor
from src.solvers.physical_equivalent_fast import build_packed_physical_action


def test_real_p3_original_integrals_and_complete_fused_action():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    spec = load_and_resolve(root/'input/task39extra_para_workstation_capacity/v6_5nm_full.dat')
    cfg = replace(simulation_config_3d_from_normalized(spec.as_jsonable()),
        nedelec_degree=3, mesh_axis_cell_counts=(3, 2, 3), mesh_axis_x_values=None,
        mesh_axis_y_values=None, mesh_axis_z_values=None, mesh_axis_z_profile=None,
        mesh_plan_id=None, mesh_plan_sha256=None)
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (3,))
    native = build_same_mesh_physical_action(levels, cfg, 3)
    fast = None
    vectors = []
    try:
        common = {'levels': levels, 'p4': native}
        fast = build_packed_physical_action(common, cfg, degree=3,
            sum_factorized_work=True, fuse_components=True, share_readonly_geometry=True)
        space = levels['floquets'][3].mpc.function_space
        form = _compile_volume_form(native['volume_action'])
        kernels = _cell_integral_kernels(form, sum_duplicate_cell_integrals=True)
        gram = HcurlBlockedGramTensor(space.element.basix_element, cfg,
            native['volume_action'].bilinear_form, compiled_form=form)
        representatives = {}
        tags = levels['mesh_data'].cell_tags
        for cell in range(levels['mesh'].topology.index_map(3).size_local):
            coordinates, widths = _canonical_axis_aligned_coordinates(levels['mesh'], cell,
                tolerance=1e-11, geometry_identity_policy='raw_unrounded')
            position = np.flatnonzero(tags.indices == cell)
            tag = int(tags.values[position[0]])
            representatives.setdefault((tag, *widths), coordinates)
        for key, coordinates in representatives.items():
            original = _tabulate_raw_tensor_class(form, kernels, coordinates,
                tag=key[0], dimension=space.element.space_dimension)
            candidate = gram(form, kernels, coordinates,
                tag=key[0], dimension=space.element.space_dimension)
            assert np.linalg.norm(candidate-original)/np.linalg.norm(original) <= 1e-10
        source = create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])
        vectors.append(source)
        indices = np.arange(source.getLocalSize())
        source.array[:] = np.sin(.07*indices)+1j*np.cos(.11*indices)
        source.array[levels['floquets'][3].mpc.slaves] = 0
        old = apply_owned(native['physical_action'], source)
        new = apply_owned(fast['physical_action'], source)
        vectors.extend((old, new))
        difference = new.copy()
        vectors.append(difference)
        difference.axpy(-1, old)
        assert difference.norm()/old.norm() <= 1e-10
        assert len(native['modes']) == 600
    finally:
        for vector in reversed(vectors):
            vector.destroy()
        if fast is not None:
            fast['physical_action'].destroy()
        native['physical_action'].destroy()
