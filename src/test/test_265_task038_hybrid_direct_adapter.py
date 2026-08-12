"""Pure Task38 contracts for the supported Case080 Hybrid direct adapter."""

from __future__ import annotations

from copy import deepcopy
import inspect
from pathlib import Path

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.input_validation import simulation_config_3d_from_normalized
from benchmarks.run_task032_phase6_augmented import _reference_sampling_grid
from src.runners.task038_hybrid_direct import run_hybrid_direct
from src.runners.task038_input_worker import _dispatch_resolved_payload


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "input/templates/hybrid_direct_example.dat"
OFFICIAL = ROOT / "input/official/grazing10_phi0_p2h5_hybrid_direct_m160_mpi4.dat"


def _payload(path: Path = TEMPLATE) -> dict:
    return load_and_resolve(path).as_jsonable()


def _variant(tmp_path: Path, replacements: list[tuple[str, str]]):
    text = TEMPLATE.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new, 1)
    path = tmp_path / "variant.dat"
    path.write_text(text, encoding="utf-8")
    return path


def _record(*, integration_pass=True):
    return {
        "qualification": {
            "integration_pass": integration_pass,
            "official_record": False,
        },
        "solve": {"true_relative_residual": 2.0e-12},
        "validation": {
            "port_power": {"R_total": 0.1, "T_total": 0.8},
            "external_diffraction_orders": [{"m": 0, "n": 0, "power_ratio": 0.8}],
        },
        "physical_field_reconstruction": {
            "volume_absorption": {
                "A_volume_total": 0.1,
                "energy_closure_error": 2.0e-12,
            }
        },
    }


def test_supported_dat_maps_physics_argv_and_fixed_candidate_pool(tmp_path):
    payload = _payload()
    calls = {}

    def fake_runner(argv, cfg):
        calls["argv"] = argv
        calls["cfg"] = cfg
        return _record()

    source_sha = "a" * 40
    result = run_hybrid_direct(
        payload, tmp_path, runner=fake_runner, source_sha=source_sha
    )
    assert result["passed"] is True
    assert calls["cfg"].nedelec_degree == 2
    assert calls["cfg"].mesh_target_size == 5.0
    assert calls["cfg"].incident_theta_deg == 80.0
    assert calls["cfg"].incident_phi_deg == 0.0
    assert calls["cfg"].polarization_kind == "s"
    assert calls["cfg"].geometry_kind == "rectangular_block_grating"
    assert calls["cfg"].stage4_full3d_assembly_backend == "standard_full"
    assert calls["cfg"].n_substrate == complex(0.999002304859, 0.00182649365)
    assert calls["argv"][calls["argv"].index("--requested-modes") + 1] == "160"
    assert calls["argv"][calls["argv"].index("--candidate-modes") + 1] == "320"
    assert calls["argv"][calls["argv"].index("--output") + 1].endswith(
        "numerical_output/run_summary.json"
    )
    assert calls["argv"][calls["argv"].index("--verified-clean-sha") + 1] == source_sha


def test_variant_dat_maps_phi_geometry_and_material_to_adapter(tmp_path):
    path = _variant(
        tmp_path,
        [
            ("azimuth_deg = 0.0", "azimuth_deg = 5.0"),
            ("period_x_nm = 50.0", "period_x_nm = 51.0"),
            (
                "n_grating = [0.999002304859, 0.00182649365]",
                "n_grating = [0.999102304859, 0.00182649365]",
            ),
        ],
    )
    payload = load_and_resolve(path).as_jsonable()
    calls = {}

    def fake_runner(argv, cfg):
        calls["argv"] = argv
        calls["cfg"] = cfg
        return _record()

    result = run_hybrid_direct(payload, tmp_path, runner=fake_runner)

    assert result["passed"] is True
    assert calls["cfg"].incident_phi_deg == 5.0
    assert calls["cfg"].period_x == 51.0
    assert calls["cfg"].n_grating == complex(0.999102304859, 0.00182649365)


@pytest.mark.parametrize(
    ("path", "message"),
    (
        (OFFICIAL, ""),
        (TEMPLATE, ""),
    ),
)
def test_template_and_official_resolve_as_supported_hybrid(path, message):
    specification = load_and_resolve(path)
    assert specification.method["kind"] == "hybrid_direct", message
    assert specification.method["requested_modes_per_direction"] == 160
    assert specification.incidence["grazing_angle_deg"] == 10.0
    assert specification.output["export_canonical_vectors"] is False


def test_nondefault_profile_and_canonical_export_fail_closed(tmp_path):
    payload = _payload()
    nondefault = deepcopy(payload)
    nondefault["solver"]["direct_solver_profile"] = "mumps_ooc"
    with pytest.raises(ValueError, match="direct_solver_profile=default"):
        run_hybrid_direct(nondefault, tmp_path, runner=lambda *_a: _record())

    canonical = deepcopy(payload)
    canonical["output"]["export_canonical_vectors"] = True
    with pytest.raises(ValueError, match="canonical_vectors"):
        run_hybrid_direct(canonical, tmp_path, runner=lambda *_a: _record())


@pytest.mark.parametrize(
    ("replacements", "message"),
    (
        (
            [
                (
                    'direct_solver_profile = "default"',
                    'direct_solver_profile = "mumps_ooc"',
                )
            ],
            "direct_solver_profile",
        ),
        (
            [("export_canonical_vectors = false", "export_canonical_vectors = true")],
            "canonical vector export",
        ),
        (
            [
                (
                    'propagation_model = "continuous_beta"',
                    'propagation_model = "full3d_uniform_cg"',
                ),
                (
                    'traction_model = "continuous_qep_beta"',
                    'traction_model = "scalar_cg_discrete_derivative"',
                ),
            ],
            "continuous_beta",
        ),
        (
            [
                (
                    'assembly_backend = "standard_full"',
                    'assembly_backend = "assembly_time_static_condensed"',
                )
            ],
            "standard_full",
        ),
        (
            [("nedelec_degree = 2", "nedelec_degree = 6")],
            "degrees 1 through 4",
        ),
        (
            [
                (
                    "requested_modes_per_direction = 160",
                    "requested_modes_per_direction = 1",
                )
            ],
            "at least two modes",
        ),
    ),
)
def test_public_validation_rejects_unsupported_hybrid_direct_capabilities(
    tmp_path, replacements, message
):
    with pytest.raises(InputError, match=message):
        load_and_resolve(_variant(tmp_path, replacements))


def test_authority_does_not_require_historical_official_record(tmp_path):
    result = run_hybrid_direct(
        _payload(), tmp_path, runner=lambda *_a: _record(integration_pass=True)
    )
    assert result["passed"] is True
    assert result["record"]["qualification"]["official_record"] is False


def test_task38_reference_sampling_uses_resolved_output_request():
    cfg = simulation_config_3d_from_normalized(_payload())
    sample_x, sample_y, sample_z = _reference_sampling_grid(cfg, 10.0, 110.0)
    assert len(sample_x) == 40
    assert len(sample_y) == 20
    assert sample_z.tolist() == [10.0, 30.0, 60.0, 90.0, 110.0]


def test_worker_dispatch_forwards_source_attestation(monkeypatch, tmp_path):
    import src.runners.task038_hybrid_direct as adapter_module

    seen = {}

    def fake_adapter(payload, output_directory, *, source_sha=None):
        seen["source_sha"] = source_sha
        seen["payload"] = payload
        return {"passed": True, "errors": []}

    monkeypatch.setattr(adapter_module, "run_hybrid_direct", fake_adapter)
    source_sha = "b" * 40
    status, errors = _dispatch_resolved_payload(
        _payload(),
        expected_method="hybrid_direct",
        output_directory=tmp_path,
        expected_source_sha=source_sha,
    )
    assert status == 0
    assert errors == []
    assert seen["source_sha"] == source_sha


def test_failed_integration_or_missing_orders_is_rejected(tmp_path):
    failed = _record(integration_pass=False)
    result = run_hybrid_direct(_payload(), tmp_path, runner=lambda *_a: failed)
    assert result["passed"] is False
    assert any("integration_pass" in error for error in result["errors"])

    incomplete = _record()
    incomplete["validation"]["external_diffraction_orders"] = []
    result = run_hybrid_direct(_payload(), tmp_path, runner=lambda *_a: incomplete)
    assert result["passed"] is False
    assert any("diffraction-order" in error for error in result["errors"])


def test_legacy_reference_defaults_true_and_task38_adapter_opts_out(monkeypatch):
    import benchmarks.run_task032_phase6_augmented as legacy
    from src.runners import task038_hybrid_direct as adapter

    assert (
        inspect.signature(legacy.main).parameters["use_case080_reference"].default
        is True
    )
    seen = {}

    def fake_main(argv, **kwargs):
        seen.update(kwargs)
        return _record()

    monkeypatch.setattr(legacy, "main", fake_main)
    adapter._default_legacy_runner(["--output", "record.json"], object())
    assert seen["use_case080_reference"] is False
