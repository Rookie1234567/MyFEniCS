from dataclasses import replace
from types import SimpleNamespace

import pytest

import src.solvers.common_3d_case_flow as common_flow
import src.solvers.dtn_port_3d as dtn_port_3d
import src.solvers.solve_maxwell_3d_stage_4b_block_grating as stage4b
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)


def test_stage4b_wrapper_forwards_linear_solver_port(monkeypatch, tmp_path):
    port = object()
    cfg = SimpleNamespace(stage_case="stage4_block_grating")

    def flow(*_args, **kwargs):
        assert kwargs["linear_solver_port"] is port
        return {"stage4b": True}

    monkeypatch.setattr(stage4b, "run_prepared_3d_case_flow", flow)
    assert stage4b.run_stage4b_block_grating_3d_case(
        cfg, tmp_path, linear_solver_port=port
    ) == {"stage4b": True}


def test_public_dtn_wrapper_forwards_linear_solver_port(monkeypatch, tmp_path):
    port = object()
    result = object()

    def implementation(**kwargs):
        assert kwargs["linear_solver_port"] is port
        return result

    monkeypatch.setattr(
        dtn_port_3d,
        "_solve_stage4_dtn_port_total_field_impl",
        implementation,
    )
    returned = dtn_port_3d.solve_stage4_dtn_port_total_field(
        a=None,
        L=None,
        V=None,
        mesh_data=None,
        cfg=None,
        floquet_data=None,
        petsc_options={},
        out_dir=tmp_path,
        log=lambda *_args: None,
        linear_solver_port=port,
    )
    assert returned is result


def test_static_external_preflight_bypasses_direct_setup(monkeypatch, tmp_path):
    cfg = replace(
        target_stage4_config(degree=2, h_nm=50.0),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    )

    def direct_options(*_args, **_kwargs):
        pytest.fail("direct LU options were prepared")

    def mumps_ooc(*_args, **_kwargs):
        pytest.fail("MUMPS OOC runtime was prepared")

    def mesh_sentinel(*_args, **_kwargs):
        raise RuntimeError("mesh sentinel")

    monkeypatch.setattr(
        common_flow, "_prepare_direct_lu_options_for_comm", direct_options
    )
    monkeypatch.setattr(common_flow, "_prepare_mumps_ooc_runtime", mumps_ooc)
    monkeypatch.setattr(common_flow, "build_airbox_mesh_3d", mesh_sentinel)
    monkeypatch.setattr(common_flow, "_write_progress_event", lambda *_a, **_k: None)
    monkeypatch.setattr(common_flow, "_finish_timed_stage", lambda *_a, **_k: None)

    with pytest.raises(RuntimeError, match="mesh sentinel"):
        common_flow.run_prepared_3d_case_flow(
            cfg,
            tmp_path,
            expected_stage_case="stage4_block_grating",
            field_formulation="total_field_dtn_port",
            solve_stage4_dtn_port=True,
            apply_strong_boundary_bc=False,
            linear_solver_port=object(),
        )
