"""Pure Task38 T4a contracts for the connected Full3D direct path."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.execution_plan import CONNECTED_METHODS, method_adapter_available
from src.io.input_loader import InputError
from src.io.input_validation import simulation_config_3d_from_normalized
from src.runners.task038_full3d_direct import run_full3d_direct
from src.runners.task038_input_worker import _dispatch_resolved_payload


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/full3d_direct_example.dat"
OFFICIAL = ROOT / "input/official/grazing1_phi0_full3d_direct_mpi8.dat"
SMOKE = ROOT / "input/smoke/full3d_direct_p2_h100_mpi1.dat"
ORDINARY_2D = ROOT / "input/templates/ordinary_2d_example.dat"


def _payload(path: Path = TEMPLATE) -> dict:
    return load_and_resolve(path).as_jsonable()


def _summary(**updates):
    value = {
        "case_status": "completed",
        "official_result": True,
        "linear_system_relative_residual": 1.0e-12,
        "R_total": 0.2,
        "T_total": 0.7,
        "A_volume_total": 0.1,
    }
    value.update(updates)
    return value


def test_shared_conversion_preserves_resolved_stage4_identity():
    specification = load_and_resolve(TEMPLATE)
    payload = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(payload)
    assert cfg.stage_case == "stage4_block_grating"
    assert cfg.geometry_kind == "rectangular_block_grating"
    assert cfg.lambda0 == specification.incidence["wavelength_nm"]
    assert cfg.period_x == specification.geometry["period_x_nm"]
    assert cfg.period_y == specification.geometry["period_y_nm"]
    assert cfg.incident_theta_deg == 90.0 - specification.incidence["grazing_angle_deg"]
    assert cfg.incident_phi_deg == specification.incidence["azimuth_deg"]
    assert cfg.nedelec_degree == specification.discretization["nedelec_degree"]
    assert cfg.mesh_target_size == specification.discretization["mesh_target_nm"]
    assert cfg.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
    assert cfg.matrix_diagnostics_assemble_only is False
    assert cfg.matrix_diagnostics_factorization_only is False
    assert cfg.use_floquet_xy is True
    assert cfg.stage4_dtn_assembly == "auxiliary"


def test_small_smoke_matches_old_target_stage4_factory():
    from src.common.config_3d import target_stage4_config

    specification = load_and_resolve(SMOKE)
    assert specification.output["export_canonical_vectors"] is False
    dat_cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    old_cfg = target_stage4_config(degree=2, h_nm=100.0)
    old_cfg.matrix_diagnostics_assemble_only = False
    old_json = old_cfg.as_jsonable()
    dat_json = dat_cfg.as_jsonable()
    for snapshot in (old_json, dat_json):
        snapshot.pop("case_name")
    assert dat_json == old_json
    assert dat_cfg.diffraction_order_max_m is None
    assert dat_cfg.diffraction_order_max_n is None


def test_full3d_order_requests_are_preserved_but_not_injected_into_pde_cfg():
    first = _payload()
    second = deepcopy(first)
    second["output"]["diffraction_order_max_m"] = 99
    second["output"]["diffraction_order_max_n"] = 101
    captured = []

    def fake_solver(cfg, output_directory, *, canonical_vector_export):
        captured.append((cfg, output_directory, canonical_vector_export))
        return _summary()

    first_result = run_full3d_direct(
        first, "/tmp/task038-t4a", solver_runner=fake_solver
    )
    second_result = run_full3d_direct(
        second, "/tmp/task038-t4a-2", solver_runner=fake_solver
    )
    assert first_result["passed"] is True
    assert second_result["passed"] is True
    assert first["output"]["diffraction_order_max_m"] == 2
    assert second["output"]["diffraction_order_max_m"] == 99
    assert captured[0][0].diffraction_order_max_m is None
    assert captured[0][0].diffraction_order_max_n is None
    assert (
        captured[0][0].diffraction_order_max_m == captured[1][0].diffraction_order_max_m
    )
    assert captured[0][0].mesh_target_size == captured[1][0].mesh_target_size


def test_adapter_passes_exact_cfg_output_and_canonical_export(tmp_path):
    payload = _payload()
    seen = {}

    def fake_solver(cfg, output_directory, *, canonical_vector_export):
        seen.update(
            cfg=cfg,
            output_directory=output_directory,
            canonical_vector_export=canonical_vector_export,
        )
        return _summary()

    result = run_full3d_direct(payload, tmp_path, solver_runner=fake_solver)
    assert result["passed"] is True
    assert seen["output_directory"] == tmp_path.resolve() / "numerical_output"
    assert seen["canonical_vector_export"] is True
    assert seen["cfg"].case_name == payload["model_id"]
    assert seen["cfg"].stage_case == "stage4_block_grating"


@pytest.mark.parametrize(
    "updates",
    (
        {"case_status": "diagnostic_assemble_only"},
        {"official_result": False},
        {"linear_system_relative_residual": 1.0e-8},
        {"R_total": None},
        {"T_total": float("inf")},
        {"A_volume_total": None},
    ),
)
def test_adapter_rejects_non_authoritative_solver_summary(tmp_path, updates):
    payload = _payload()
    result = run_full3d_direct(
        payload,
        tmp_path,
        solver_runner=lambda *_args, **_kwargs: _summary(**updates),
    )
    assert result["passed"] is False
    assert result["errors"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("dimension", 2, "dimension=3"),
        ("method", {"kind": "hybrid_direct"}, "method.kind=full3d_direct"),
        ("solver", {"linear_solver": "fgmres"}, "linear_solver=direct"),
        (
            "geometry",
            {"geometry_kind": "airbox"},
            "rectangular block grating",
        ),
    ),
)
def test_adapter_rejects_wrong_method_identity(field, value, message, tmp_path):
    payload = _payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        run_full3d_direct(payload, tmp_path, solver_runner=lambda *_a, **_k: _summary())


def test_full3d_and_hybrid_direct_are_connected_and_other_methods_fail_closed():
    assert CONNECTED_METHODS == {"full3d_direct", "hybrid_direct"}
    assert method_adapter_available("full3d_direct") is True
    assert method_adapter_available("hybrid_direct") is True
    for method in ("2d_scattered", "2d_port", "hybrid_iterative"):
        assert method_adapter_available(method) is False


def test_2d_still_rejects_the_3d_auto_cell_type(tmp_path):
    text = ORDINARY_2D.read_text(encoding="utf-8")
    text = text.replace('mesh_cell_type = "quadrilateral"', 'mesh_cell_type = "auto"')
    path = tmp_path / "bad_2d_auto.dat"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InputError, match="2D allows triangle or quadrilateral"):
        load_and_resolve(path)


@pytest.mark.parametrize("path", (OFFICIAL, SMOKE))
def test_official_and_smoke_inputs_are_strict_and_hash_stable(path):
    first = load_and_resolve(path)
    second = load_and_resolve(path)
    assert first.identity["dimension"] == 3
    assert first.method["kind"] == "full3d_direct"
    assert first.physical_model_sha256 == second.physical_model_sha256
    assert first.input_sha256 == second.input_sha256
    assert first.derived["internal"]["stage_case"] == "stage4_block_grating"


def test_worker_dispatch_uses_the_same_resolved_payload(monkeypatch, tmp_path):
    payload = _payload()
    received = []

    def fake_adapter(value, output_directory):
        received.append((value, output_directory))
        return {"passed": True, "errors": [], "summary": _summary()}

    import src.runners.task038_full3d_direct as adapter_module

    monkeypatch.setattr(adapter_module, "run_full3d_direct", fake_adapter)
    status, errors = _dispatch_resolved_payload(
        payload,
        expected_method="full3d_direct",
        output_directory=tmp_path,
    )
    assert status == 0
    assert errors == []
    assert received[0][0] is payload
    assert received[0][1] == tmp_path


def test_worker_dispatch_keeps_unconnected_methods_closed(tmp_path):
    status, errors = _dispatch_resolved_payload(
        _payload(), expected_method="hybrid_iterative", output_directory=tmp_path
    )
    assert status == 3
    assert "unavailable" in errors[0]
