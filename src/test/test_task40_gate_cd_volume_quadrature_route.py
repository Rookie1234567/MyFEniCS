"""No-FE checks that a selected Gate-CD volume rule reaches action and outputs."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.io.native_capacity_profile import TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE
from src.postprocessing import power_metrics, rta_3d
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task40_gate_cd_volume_quadrature_metadata,
)

_PRODUCTION = (
    {"quadrature_degree": 15, "quadrature_rule": "default"},
    {"quadrature_degree": 15, "quadrature_rule": "default"},
)


def test_gate_cd_volume_selector_binds_only_the_profiled_candidates():
    route = _direct_run_contract(TASK40_GATE_CD_M8N64_P6_DIRECT_PROFILE)
    assert route["gate_cd_case"] is True
    assert route["volume_quadrature"]["degree"] == 21
    assert route["volume_quadrature"]["candidate_degrees"] == [15, 21, 27]

    for degree in (15, 21, 27):
        selected_route = dict(route)
        selected_route["volume_quadrature"] = {
            **route["volume_quadrature"],
            "degree": degree,
            "rule": "default",
        }
        selected = _task40_gate_cd_volume_quadrature_metadata(
            selected_route, _PRODUCTION
        )
        assert selected == (
            {"quadrature_degree": degree, "quadrature_rule": "default"},
            {"quadrature_degree": degree, "quadrature_rule": "default"},
        )
    assert _PRODUCTION == (
        {"quadrature_degree": 15, "quadrature_rule": "default"},
        {"quadrature_degree": 15, "quadrature_rule": "default"},
    )

    bad_degree = dict(route)
    bad_degree["volume_quadrature"] = {
        **route["volume_quadrature"],
        "degree": 39,
    }
    with pytest.raises(ValueError, match="outside q15/q21/q27"):
        _task40_gate_cd_volume_quadrature_metadata(bad_degree, _PRODUCTION)

    bad_authority = (
        {"quadrature_degree": 15, "quadrature_rule": "default"},
        {"quadrature_degree": 14, "quadrature_rule": "default"},
    )
    with pytest.raises(ValueError, match="actual production FFCx"):
        _task40_gate_cd_volume_quadrature_metadata(route, bad_authority)


def _fake_measure_capture(monkeypatch, module):
    calls = []

    class Measure:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def __call__(self, *_args):
            return 1.0

    monkeypatch.setattr(module.ufl, "Measure", Measure)
    monkeypatch.setattr(module.ufl, "inner", lambda left, right: 1.0)
    monkeypatch.setattr(module.ufl, "real", lambda value: value)
    monkeypatch.setattr(module.ufl, "imag", lambda value: value.imag)
    monkeypatch.setattr(module.ufl, "form", lambda value: value, raising=False)
    monkeypatch.setattr(module.fem, "form", lambda value: value)
    monkeypatch.setattr(module.fem, "assemble_scalar", lambda _form: 2.0)
    return calls


def test_rta_absorbed_power_uses_selected_volume_measure_metadata(monkeypatch):
    calls = _fake_measure_capture(monkeypatch, rta_3d)
    mesh_data = SimpleNamespace(
        mesh=SimpleNamespace(comm=SimpleNamespace(allreduce=lambda value, op: value)),
        cell_tags=object(),
    )
    cfg = SimpleNamespace(geometry_kind="task40_gate_cd_mapped", k0=2.0)
    metadata = (
        {"quadrature_degree": 21, "quadrature_rule": "default"},
        {"quadrature_degree": 21, "quadrature_rule": "default"},
    )
    value = rta_3d._region_absorbed_power(
        mesh_data, cfg, object(), tag=7, eps_r=1.0 + 0.5j,
        volume_quadrature_metadata=metadata,
    )
    assert value == 2.0
    assert len(calls) == 1
    assert calls[0][1]["metadata"] == metadata[0]


def test_power_metrics_absorption_uses_same_selected_volume_measure(monkeypatch):
    calls = _fake_measure_capture(monkeypatch, power_metrics)
    monkeypatch.setattr(power_metrics, "relative_permittivity", lambda _mesh, _cfg: 1.0 + 0.2j)
    mesh_data = SimpleNamespace(
        mesh=SimpleNamespace(comm=SimpleNamespace(allreduce=lambda value, op: value)),
        cell_tags=object(),
    )
    cfg = SimpleNamespace(
        geometry_kind="task40_gate_cd_mapped",
        physical_material_regions=None,
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
        k0=2.0,
    )
    metadata = (
        {"quadrature_degree": 27, "quadrature_rule": "default"},
        {"quadrature_degree": 27, "quadrature_rule": "default"},
    )
    result = power_metrics._volume_absorption_metrics(
        mesh_data, cfg, object(), incident_power=1.0, field_model="test",
        volume_quadrature_metadata=metadata,
    )
    assert result["A_volume"] == result["absorbed_power_weighted"]
    assert len(calls) == 1
    assert calls[0][1]["metadata"] == metadata[0]


def test_direct_output_recovery_forwards_the_selected_volume_rule(monkeypatch, tmp_path):
    from src.common import modes_3d
    from src.postprocessing import diffraction_3d, postprocess_3d
    from src.solvers import dtn_port_3d, fullspace_same_mesh_hcurl_pmg_physical

    observed = {}
    fake_mesh_data = SimpleNamespace(mesh=SimpleNamespace(comm=SimpleNamespace()))
    field = SimpleNamespace(x=SimpleNamespace(array=np.zeros(1)))
    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_physical,
        "restore_p0_full_field",
        lambda *_args, **_kwargs: field,
    )
    monkeypatch.setattr(
        dtn_port_3d,
        "_port_power_metrics",
        lambda *_args: {"R_total": 0.2, "T_total": 0.7, "A_balance": 0.1},
    )
    monkeypatch.setattr(
        postprocess_3d,
        "save_airbox_3d_fields",
        lambda *_args, **_kwargs: {"electric_finite": True},
    )
    monkeypatch.setattr(modes_3d, "incident_power_3d", lambda _cfg: 1.0)
    monkeypatch.setattr(
        rta_3d,
        "compute_volume_absorption_3d",
        lambda *_args, **kwargs: observed.update(kwargs)
        or {"A_volume_total": 0.1},
    )
    monkeypatch.setattr(
        diffraction_3d,
        "compute_diffraction_orders_3d",
        lambda *_args, **_kwargs: {"diffraction_channel_count": 0},
    )

    metadata = (
        {"quadrature_degree": 21, "quadrature_rule": "default"},
        {"quadrature_degree": 21, "quadrature_rule": "default"},
    )
    cfg = SimpleNamespace(geometry_kind="task40_gate_cd_mapped")
    setup = {"floquets": {6: object()}, "mesh_data": fake_mesh_data}
    bundle = {
        "setup": setup,
        "cfg": cfg,
        "degree": 6,
        "modes": (),
        "mode_sha256": "0" * 64,
        "incident_projections": (),
        "dtn_sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
        "dtn_sparse_cutoff_relative_tolerance": 1e-13,
        "dtn_sparse_cutoff_identity_sha256": "1" * 64,
        "dtn_action": SimpleNamespace(
            recover_auxiliary=lambda _solution: np.zeros(0)
        ),
    }
    facts = fullspace_same_mesh_hcurl_pmg_physical.recover_p0_outputs(
        bundle,
        np.zeros(1, dtype=complex),
        tmp_path,
        volume_quadrature_metadata=metadata,
    )
    assert observed["volume_quadrature_metadata"] == metadata
    assert facts["volume_metrics"]["A_volume_total"] == 0.1


def test_non_gate_cd_output_cannot_opt_into_gate_cd_volume_rule():
    cfg = SimpleNamespace(geometry_kind="legacy")
    metadata = (
        {"quadrature_degree": 15, "quadrature_rule": "default"},
        {"quadrature_degree": 15, "quadrature_rule": "default"},
    )
    with pytest.raises(ValueError, match="restricted to Gate-CD"):
        rta_3d._gate_cd_volume_measure_metadata(cfg, metadata)
