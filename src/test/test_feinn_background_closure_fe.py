"""Single eight-cell check of the newly reused affine transfer adapter."""

from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np


def test_background_adapter_embeds_complex_field_with_nonunit_MPC_once():
    import basix.ufl
    from dolfinx import fem
    from src.io.feinn_pilot import DESIGN
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.solvers.feinn_interpolation import full_space
    from src.solvers.feinn_bounded_field_integrals import BoundedFieldIntegrals
    from src.solvers.feinn_saved_field_diagnostics import background_embedding
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import restore_p0_full_field

    design = deepcopy(json.loads(DESIGN.read_text()))
    design["geometry"]["cells"] = [2, 2, 2]
    cfg, data, s3, *_ = full_space(design, 3)
    s4 = fem.functionspace(data.mesh, basix.ufl.element("N1curl", "hexahedron", 4))
    f3 = build_double_floquet_mpc(s3, data, cfg)
    f4 = build_double_floquet_mpc(s4, data, replace(cfg, nedelec_degree=4))
    rng = np.random.default_rng(4211302)
    storage = rng.normal(size=s3.dofmap.index_map.size_local) + 1j * rng.normal(
        size=s3.dofmap.index_map.size_local
    )
    storage[f3.mpc.slaves] = 0
    field3 = restore_p0_full_field(f3, storage)
    masters = np.setdiff1d(np.arange(s4.dofmap.index_map.size_local), f4.mpc.slaves)
    packet4 = SimpleNamespace(a=dict(slaves=f4.mpc.slaves, masters=masters))
    embedded, pair = background_embedding(
        field3, s4, f4, packet4, BoundedFieldIntegrals(data.mesh, cfg.k0)
    )
    assert embedded.shape == masters.shape and np.linalg.norm(embedded) > 0
    assert max(pair["common_E_scaled_curl_relative"]) < 1e-10
    assert pair["MPC_operation_relative"] < 1e-10
    assert len(np.unique(data.mesh.topology.get_cell_permutation_info())) > 1
