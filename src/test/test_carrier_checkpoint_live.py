"""Real q81/MPC carrier resume, including an interrupted committed prefix."""

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh

from src.common.modes_3d import outgoing_port_modes_3d
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler
from src.solvers.dtn_sparse_policy import SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY
from src.solvers.fullspace_dtn_action import build_fullspace_dtn_carrier_from_surface
from src.test.test_task40_gate_cd_mapped_p6_condensation import (
    _small_gate_cd_swept_fixture,
)


def test_actual_q81_carrier_interruption_and_reuse(tmp_path):
    degree = int(os.environ.get("CACHE_VALIDATION_DEGREE", "2"))
    msh, _, data, cfg = _small_gate_cd_swept_fixture()
    cfg.nedelec_degree = degree
    cfg.stage4_dtn_order_policy = "zero_order"
    cfg.diffraction_zero_order_only = True
    indices = list(data.facet_tags.indices)
    values = list(data.facet_tags.values)
    for z, tag in [(cfg.z_min, cfg.tags.z_min), (cfg.z_max, cfg.tags.z_max)]:
        faces = mesh.locate_entities_boundary(
            msh, 2, lambda x, z=z: np.isclose(x[2], z)
        )
        indices.extend(faces)
        values.extend([tag] * len(faces))
    order = np.argsort(indices)
    data = SimpleNamespace(
        mesh=msh,
        facet_tags=mesh.meshtags(
            msh,
            2,
            np.asarray(indices, dtype=np.int32)[order],
            np.asarray(values, dtype=np.int32)[order],
        ),
    )
    V = fem.functionspace(
        msh, element("N1curl", "hexahedron", degree, dtype=default_real_type)
    )
    floquet = build_double_floquet_mpc(V, data, cfg)
    modes = tuple(outgoing_port_modes_3d(cfg))
    assert len(modes) == 4
    assemblers = {
        (side, c): _ReusableSurfaceComponentAssembler(
            V,
            data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            c,
            quadrature_degree=81,
        )
        for side in ("top", "bottom")
        for c in (0, 1)
    }
    kwargs = {
        "degree": degree,
        "quadrature_degree": 81,
        "progress_interval": 1,
        "sparse_cutoff_policy": SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
        "sparse_cutoff_relative_tolerance": 1e-13,
    }
    reference = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, floquet.mpc, cfg, **kwargs
    )
    checkpoint = {
        "root": str(tmp_path / "cache"),
        "numerical_source_sha256": hashlib.sha256(b"live-test-source").hexdigest(),
    }

    class Interrupted(Exception):
        pass

    def stop(name, facts):
        if name == "surface_carrier_mode_progress" and facts["completed_modes"] == 2:
            raise Interrupted()

    with pytest.raises(Interrupted):
        build_fullspace_dtn_carrier_from_surface(
            modes,
            assemblers,
            floquet.mpc,
            cfg,
            carrier_checkpoint_config=checkpoint,
            stage_callback=stop,
            **kwargs,
        )
    facts = []
    resumed = build_fullspace_dtn_carrier_from_surface(
        modes,
        assemblers,
        floquet.mpc,
        cfg,
        carrier_checkpoint_config=checkpoint,
        stage_callback=lambda n, f: facts.append((n, f)),
        **kwargs,
    )
    assert (
        next(
            f["restored_functional_prefix_count"]
            for n, f in facts
            if n == "surface_carrier_assembly_started"
        )
        == 2
    )

    def forbid(*a, **k):
        raise AssertionError("warm checkpoint recomputed a surface mode")

    for a in assemblers.values():
        a.assemble_entries = forbid
    warm = build_fullspace_dtn_carrier_from_surface(
        modes,
        assemblers,
        floquet.mpc,
        cfg,
        carrier_checkpoint_config=checkpoint,
        **kwargs,
    )
    for observed in (resumed, warm):
        for a, b in zip(reference.entries, observed.entries, strict=True):
            assert a.normalization_h == b.normalization_h
            for field in (
                "coupling_rows",
                "coupling_values",
                "projection_rows",
                "projection_values",
            ):
                assert getattr(a, field).tobytes() == getattr(b, field).tobytes()
    report = {
        "degree": degree,
        "q": 81,
        "modes": 4,
        "restored_prefix": 2,
        "bitwise_equal": True,
        "warm_surface_calls": 0,
    }
    destination = os.environ.get("CACHE_CARRIER_REPORT")
    if destination:
        import json

        Path(destination).write_text(json.dumps(report, indent=2) + "\n")
