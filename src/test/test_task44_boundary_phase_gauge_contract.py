from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from src.io import InputError, load_and_resolve, resolved_config_sha256
from src.io.input_validation import simulation_config_3d_from_normalized

TEMPLATE = Path("input/templates/full3d_direct_example.dat")


def _write_case(
    tmp_path: Path,
    *,
    gauge: str | None,
    mpi_size: int = 8,
    order_policy: str = "auto_propagating",
    n_air: str = "[1.0, 0.0]",
    method: str = "full3d_direct",
) -> Path:
    text = TEMPLATE.read_text(encoding="utf-8")
    text, count = re.subn(
        r"(?m)^mpi_size\s*=.*$",
        f"mpi_size = {mpi_size}",
        text,
        count=1,
    )
    assert count == 1
    text, count = re.subn(
        r"(?m)^dtn_order_policy\s*=.*$",
        f'dtn_order_policy = "{order_policy}"',
        text,
        count=1,
    )
    assert count == 1
    text, count = re.subn(
        r"(?m)^n_air\s*=.*$",
        f"n_air = {n_air}",
        text,
        count=1,
    )
    assert count == 1
    text, count = re.subn(
        r"(?m)^kind\s*=\s*\"full3d_direct\"$",
        f'kind = "{method}"',
        text,
        count=1,
    )
    assert count == 1
    if gauge is not None:
        text, count = re.subn(
            r'(?m)^(dtn_assembly\s*=\s*"auxiliary")$',
            rf'\1\nboundary.dtn_phase_gauge = "{gauge}"',
            text,
            count=1,
        )
        # The public key belongs inside the [boundary] table.
        assert count == 1
        text = text.replace(
            f'boundary.dtn_phase_gauge = "{gauge}"',
            f'dtn_phase_gauge = "{gauge}"',
            1,
        )
    path = tmp_path / f"case-{gauge or 'default'}-{mpi_size}-{order_policy}.dat"
    path.write_text(text, encoding="utf-8")
    return path


def test_default_and_explicit_plane_gauge_resolve_into_runtime_config(tmp_path):
    default_spec = load_and_resolve(_write_case(tmp_path, gauge=None))
    plane_spec = load_and_resolve(
        _write_case(tmp_path, gauge="boundary_plane", mpi_size=1)
    )

    assert default_spec.boundary["dtn_phase_gauge"] == "global_z"
    assert plane_spec.boundary["dtn_phase_gauge"] == "boundary_plane"
    default_cfg = simulation_config_3d_from_normalized(default_spec.as_jsonable())
    plane_cfg = simulation_config_3d_from_normalized(plane_spec.as_jsonable())
    assert default_cfg.dtn_phase_gauge == "global_z"
    assert default_cfg.as_jsonable()["dtn_phase_gauge"] == "global_z"
    assert plane_cfg.dtn_phase_gauge == "boundary_plane"
    assert plane_cfg.as_jsonable()["dtn_phase_gauge"] == "boundary_plane"
    assert resolved_config_sha256(default_spec) != resolved_config_sha256(plane_spec)


def test_invalid_and_unsupported_plane_gauge_inputs_fail_closed(tmp_path):
    with pytest.raises(InputError, match="boundary.dtn_phase_gauge"):
        load_and_resolve(_write_case(tmp_path, gauge="unsupported", mpi_size=1))

    with pytest.raises(InputError, match="requires MPI1"):
        load_and_resolve(_write_case(tmp_path, gauge="boundary_plane", mpi_size=8))

    with pytest.raises(InputError, match="n_air=1"):
        load_and_resolve(
            _write_case(
                tmp_path,
                gauge="boundary_plane",
                mpi_size=1,
                n_air="[1.2, 0.0]",
            )
        )

    with pytest.raises(InputError, match="zero-order local-Robin shortcut"):
        load_and_resolve(
            _write_case(
                tmp_path,
                gauge="boundary_plane",
                mpi_size=1,
                order_policy="zero_order",
            )
        )

    with pytest.raises(InputError, match="not applicable"):
        load_and_resolve(
            _write_case(
                tmp_path,
                gauge="boundary_plane",
                mpi_size=1,
                method="full3d_iterative",
            )
        )


def test_public_direct_solver_entrypoint_enforces_and_passes_plane_gauge(monkeypatch):
    from types import SimpleNamespace

    from mpi4py import MPI

    from src.solvers import dtn_port_3d
    from src.test.stage2_test_utils import stage4_block_config

    cfg = stage4_block_config(
        stage4_boundary_model="dtn_port",
        stage4_dtn_assembly="auxiliary",
        stage4_dtn_order_policy="auto_propagating",
        dtn_phase_gauge="boundary_plane",
    )
    mesh_data = SimpleNamespace(mesh=SimpleNamespace(comm=MPI.COMM_SELF))
    sentinel = object()
    observed = {}

    def fake_impl(**kwargs):
        observed.update(kwargs)
        return sentinel

    monkeypatch.setattr(dtn_port_3d, "_solve_stage4_dtn_port_total_field_impl", fake_impl)
    result = dtn_port_3d.solve_stage4_dtn_port_total_field(
        a=None,
        L=None,
        V=None,
        mesh_data=mesh_data,
        cfg=cfg,
        floquet_data=None,
        petsc_options={},
        out_dir=Path("unused"),
        log=None,
    )

    assert result is sentinel
    assert observed["cfg"] is cfg
    assert observed["cfg"].dtn_phase_gauge == "boundary_plane"

    with pytest.raises(NotImplementedError, match="external and matrix-free"):
        dtn_port_3d.solve_stage4_dtn_port_total_field(
            a=None,
            L=None,
            V=None,
            mesh_data=mesh_data,
            cfg=cfg,
            floquet_data=None,
            petsc_options={},
            out_dir=Path("unused"),
            log=None,
            linear_solver_port=object(),
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="the small assembled-surface gauge fixture is serial",
)
def test_boundary_plane_surface_vectors_match_raw_dual_transform(tmp_path):
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_boundary_phase_gauge import (
        _conversion_scale,
        plane_port_rhs_from_global,
    )
    from src.solvers.dtn_port_3d import (
        _dtn_surface_quadrature_degree,
        _mode_projection_denominator,
        _ReusableSurfaceComponentAssembler,
    )
    from src.test.stage2_test_utils import stage4_block_config

    cfg = stage4_block_config(
        stage4_dtn_order_policy="manual",
        diffraction_order_max_m=15,
        diffraction_order_max_n=8,
        incident_theta_deg=60.0,
        n_substrate=0.8 + 0.05j,
        z_min=-30.0,
        z_max=30.0,
        substrate_thickness=30.0,
        air_height=30.0,
        grating_height=10.0,
        use_pml=False,
        pml_top_thickness=0.0,
        pml_bottom_thickness=0.0,
        mesh_target_size=50.0,
        nedelec_degree=1,
    )
    mesh_data = build_airbox_mesh_3d(cfg, tmp_path / "gauge-surface-mesh")
    V = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(V, mesh_data, cfg)
    modes = outgoing_port_modes_3d(cfg)
    representatives = (
        next(
            mode
            for mode in modes
            if mode.side == "top"
            and mode.m == 0
            and mode.n == 0
            and mode.propagating
        ),
        next(
            mode
            for mode in modes
            if mode.side == "bottom"
            and mode.m == 0
            and mode.n == 0
            and not mode.propagating
            and mode.power_per_unit_amplitude > 0.0
        ),
        next(
            mode
            for mode in modes
            if mode.side == "top"
            and mode.m == 6
            and mode.n == 0
            and not mode.propagating
        ),
    )
    quadrature = _dtn_surface_quadrature_degree(cfg, list(representatives))
    for mode in representatives:
        tag = cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min
        plane_z = cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min
        scale = _conversion_scale(mode, cfg, "boundary_plane")
        h_global = _mode_projection_denominator(mode, cfg)
        h_plane = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min) * (
            mode.electric_tangential_norm_sq
        )
        np.testing.assert_allclose(
            h_plane,
            h_global / abs(scale) ** 2,
            rtol=3.0e-12,
            atol=1.0e-13,
        )
        for component in (0, 1):
            global_assembler = _ReusableSurfaceComponentAssembler(
                V,
                mesh_data,
                tag,
                component,
                quadrature_degree=quadrature,
            )
            plane_assembler = _ReusableSurfaceComponentAssembler(
                V,
                mesh_data,
                tag,
                component,
                quadrature_degree=quadrature,
                boundary_reference_z=plane_z,
            )
            global_rows, global_values = global_assembler.assemble_entries(
                mode, floquet_data.mpc
            )
            plane_rows, plane_values = plane_assembler.assemble_entries(
                mode, floquet_data.mpc
            )
            np.testing.assert_array_equal(plane_rows, global_rows)
            np.testing.assert_allclose(
                plane_values,
                global_values / scale,
                rtol=2.0e-10,
                atol=1.0e-13,
            )
            # The assembled surface load is linear in the centered phase.
            # Its conjugate is the raw modal dual; H normalization then maps
            # the direct auxiliary row by s, as required by the coordinate
            # transform b = s*a_global.
            global_raw_dual = np.conjugate(global_values)
            plane_raw_dual = np.conjugate(plane_values)
            np.testing.assert_allclose(
                plane_raw_dual,
                global_raw_dual / np.conjugate(scale),
                rtol=2.0e-10,
                atol=1.0e-13,
            )
            global_normalized_row = global_raw_dual / h_global
            plane_normalized_row = plane_raw_dual / h_plane
            np.testing.assert_allclose(
                plane_normalized_row,
                scale * global_normalized_row,
                rtol=2.0e-10,
                atol=1.0e-13,
            )
            raw_rhs = np.asarray([0.37 - 0.19j], dtype=np.complex128)
            converted_rhs = plane_port_rhs_from_global(
                raw_rhs,
                (mode,),
                cfg,
                "boundary_plane",
            )
            np.testing.assert_allclose(
                converted_rhs,
                raw_rhs / np.conjugate(scale),
                rtol=2.0e-13,
                atol=1.0e-13,
            )
