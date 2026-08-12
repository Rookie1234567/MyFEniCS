"""Pure Task38 T7 checks for ordinary preset migration and runtime seams."""

from pathlib import Path

import pytest

from src import main
from src.io import load_and_resolve
from src.io.execution_plan import CONNECTED_METHODS
from src.io.input_loader import InputError
from src.io.input_validation import (
    simulation_config_2d_from_normalized,
    simulation_config_3d_from_normalized,
)
from src.io.preset_migration import MIGRATED_PRESET_DATS
from src.common.modes_3d import outgoing_port_modes_3d
from src.postprocessing.diffraction_3d import _power_orders_for_reporting
from src.runners import run_3d_cases
from src.runners import run_cases
from src.runners.task038_2d import run_2d


ROOT = Path(__file__).resolve().parents[2]
ORDINARY_2D = ROOT / "input/templates/ordinary_2d_example.dat"
MIGRATED_3D_CASES = (
    (
        "3d_stage1_airbox_smoke",
        {"case_name", "stage4_boundary_model"},
    ),
    (
        "3d_stage2a_floquet_smoke",
        {
            "case_name",
            "eps_substrate",
            "n_substrate",
            "pml_bottom_thickness",
            "pml_top_thickness",
            "stage4_boundary_model",
            "substrate_thickness",
        },
    ),
    (
        "3d_stage2b_pml_smoke",
        {
            "case_name",
            "eps_substrate",
            "n_substrate",
            "stage4_boundary_model",
            "substrate_thickness",
        },
    ),
    (
        "3d_stage2c_fresnel_smoke",
        {"case_name", "stage4_boundary_model", "substrate_thickness"},
    ),
    (
        "3d_stage4a_flat_layer_direct",
        {
            "case_name",
            "diffraction_order_max_m",
            "diffraction_order_max_n",
            "eps_grating",
            "grating_index",
            "grating_material_label",
            "n_grating",
            "reporting_diffraction_order_max_m",
            "reporting_diffraction_order_max_n",
        },
    ),
)
MIGRATED_2D_CASES = (
    (
        "2d_tm_pml_floquet_smoke",
        {"case_name", "port_boundary_model", "port_dtn_order_count"},
    ),
    (
        "2d_tm_dtn_auxiliary_smoke",
        {
            "case_name",
            "pml_bottom_thickness",
            "pml_top_thickness",
            "port_dtn_order_count",
        },
    ),
    (
        "2d_tm_dtn_explicit_smoke",
        {
            "case_name",
            "pml_bottom_thickness",
            "pml_top_thickness",
            "port_dtn_order_count",
        },
    ),
    (
        "2d_te_port_smoke",
        {
            "case_name",
            "pml_bottom_thickness",
            "pml_top_thickness",
            "port_dtn_order_count",
        },
    ),
    (
        "2d_complex_absorption",
        {
            "case_name",
            "pml_bottom_thickness",
            "pml_top_thickness",
            "port_dtn_order_count",
        },
    ),
    (
        "2d_euv_grating_direct",
        {
            "case_name",
            "pml_bottom_thickness",
            "pml_top_thickness",
            "port_dtn_order_count",
        },
    ),
)


def _captured_legacy_3d_config(name, tmp_path):
    captured = []
    original = run_3d_cases._run_stage_config
    run_3d_cases._run_stage_config = lambda cfg, _out_dir: captured.append(cfg) or {}
    try:
        _, argv = main.preset_cli_args(name)
        run_3d_cases.main([*argv, "--results-root", str(tmp_path / f"legacy_{name}")])
    finally:
        run_3d_cases._run_stage_config = original
    assert len(captured) == 1
    return captured[0]


def _captured_legacy_2d_config(name, tmp_path):
    captured = []
    originals = {
        key: getattr(run_cases, key)
        for key in ("run_case", "run_te_case", "run_port_case", "run_te_port_case")
    }

    def fake_solver(cfg, *_args, **_kwargs):
        captured.append(cfg)
        return {
            "case_name": cfg.case_name,
            "config": cfg.as_jsonable(),
            "power_metrics": {},
        }

    for key in originals:
        setattr(run_cases, key, fake_solver)
    try:
        _, argv = main.preset_cli_args(name)
        run_cases.main([*argv, "--results-root", str(tmp_path / f"legacy_{name}")])
    finally:
        for key, value in originals.items():
            setattr(run_cases, key, value)
    assert len(captured) == 1
    return captured[0]


def _summary():
    return {
        "reduced_linear_residual": 1.0e-12,
        "power_metrics": {"R_total": 0.2, "T_total": 0.7, "R_plus_T": 0.9},
    }


def test_shared_2d_mapping_and_scattered_adapter_use_resolved_payload(tmp_path):
    specification = load_and_resolve(ORDINARY_2D)
    received = {}

    def fake_solver(cfg, output_directory, constraint_backend):
        received.update(
            cfg=cfg,
            output_directory=output_directory,
            constraint_backend=constraint_backend,
        )
        return _summary()

    result = run_2d(specification.as_jsonable(), tmp_path, solver_runner=fake_solver)

    assert result["passed"] is True
    assert received["cfg"].calculation_method == "scattered"
    assert received["cfg"].polarization_type == "TM"
    assert received["cfg"].period_x == specification.geometry["period_x_nm"]
    assert received["cfg"].incident_angle_deg == 0.0
    assert received["constraint_backend"] == "mpc_auto"
    assert received["output_directory"] == tmp_path.resolve() / "numerical_output"


def test_te_port_adapter_uses_the_existing_port_entrypoint(tmp_path):
    text = ORDINARY_2D.read_text(encoding="utf-8")
    text = text.replace('kind = "2d_scattered"', 'kind = "2d_port"', 1)
    text = text.replace('polarization = "tm"', 'polarization = "te"', 1)
    text = text.replace('vertical_boundary = "pml"', 'vertical_boundary = "robin"', 1)
    text = text.replace("use_pml = true", "use_pml = false", 1)
    for line in (
        "pml_top_thickness_nm = 25.0\n",
        "pml_bottom_thickness_nm = 25.0\n",
        "pml_alpha = 5.0\n",
    ):
        text = text.replace(line, "", 1)
    text = text.replace(
        'constraint_backend = "mpc_auto"', 'constraint_backend = "manual"', 1
    )
    path = tmp_path / "te_port.dat"
    path.write_text(text, encoding="utf-8")
    specification = load_and_resolve(path)
    received = {}

    def fake_solver(cfg, output_directory, constraint_backend):
        received.update(
            cfg=cfg,
            output_directory=output_directory,
            constraint_backend=constraint_backend,
        )
        return _summary()

    result = run_2d(
        specification.as_jsonable(), tmp_path / "run", solver_runner=fake_solver
    )

    assert result["passed"] is True
    assert received["cfg"].calculation_method == "port"
    assert received["cfg"].port_boundary_model == "robin"
    assert received["cfg"].polarization_type == "TE"
    assert received["constraint_backend"] == "manual"


def test_explicit_dtn_keeps_legacy_auto_order_semantics(tmp_path):
    legacy = main.PRESETS_2D["2d_tm_dtn_explicit_smoke"]
    specification = load_and_resolve(ROOT / "input/smoke/2d_tm_dtn_explicit_smoke.dat")
    assert legacy.port_dtn_assembly == "explicit"
    assert legacy.port_use_diffraction_orders is True
    assert specification.boundary["dtn_assembly"] == "explicit"
    assert specification.boundary["dtn_order_policy"] == "auto_propagating"

    received = {}

    def fake_solver(cfg, output_directory, constraint_backend):
        received.update(cfg=cfg, output_directory=output_directory)
        return _summary()

    result = run_2d(specification.as_jsonable(), tmp_path, solver_runner=fake_solver)
    assert result["passed"] is True
    assert received["cfg"].port_dtn_assembly == legacy.port_dtn_assembly
    assert received["cfg"].port_use_diffraction_orders is True


def test_task38_plan_connects_both_2d_public_methods():
    assert {"2d_scattered", "2d_port"}.issubset(CONNECTED_METHODS)


def test_flat_layer_rejects_nonzero_grating_dimensions(tmp_path):
    source = (ROOT / "input/smoke/3d_stage4a_flat_layer_direct.dat").read_text(
        encoding="utf-8"
    )
    bad = source.replace("grating_width_x_nm = 0.0", "grating_width_x_nm = 1.0", 1)
    path = tmp_path / "bad_flat.dat"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(InputError, match="omitted or zero for non-grating geometry"):
        load_and_resolve(path)


def test_flat_dtn_zero_order_is_independent_of_reporting_bounds():
    specification = load_and_resolve(
        ROOT / "input/smoke/3d_stage4a_flat_layer_direct.dat"
    )
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    modes = outgoing_port_modes_3d(cfg)
    assert cfg.stage4_dtn_order_policy == "zero_order"
    assert cfg.diffraction_zero_order_only is False
    assert {(mode.m, mode.n) for mode in modes} == {(0, 0)}
    orders = _power_orders_for_reporting(cfg)
    assert {(order.m, order.n) for order in orders} == {
        (m, n) for m in range(-2, 3) for n in range(-2, 3)
    }
    second_payload = specification.as_jsonable()
    second_payload["output"]["diffraction_order_max_m"] = 1
    second_payload["output"]["diffraction_order_max_n"] = 1
    cfg2 = simulation_config_3d_from_normalized(second_payload)
    assert {(mode.m, mode.n) for mode in outgoing_port_modes_3d(cfg2)} == {
        (mode.m, mode.n) for mode in modes
    }
    assert {(order.m, order.n) for order in _power_orders_for_reporting(cfg2)} == {
        (m, n) for m in range(-1, 2) for n in range(-1, 2)
    }


def test_2d_adapter_rejects_negative_residual(tmp_path):
    specification = load_and_resolve(ORDINARY_2D)

    def fake_solver(*_args):
        return {
            "reduced_linear_residual": -1.0,
            "power_metrics": {"R_total": 0.2, "T_total": 0.7, "R_plus_T": 0.9},
        }

    result = run_2d(specification.as_jsonable(), tmp_path, solver_runner=fake_solver)
    assert result["passed"] is False
    assert result["errors"]


def test_2d_adapter_rejects_requested_power_without_metrics(tmp_path):
    specification = load_and_resolve(ORDINARY_2D)

    result = run_2d(
        specification.as_jsonable(),
        tmp_path,
        solver_runner=lambda *_args: {"reduced_linear_residual": 1.0e-12},
    )
    assert result["passed"] is False
    assert any("power metric" in error for error in result["errors"])


@pytest.mark.parametrize("name,excluded_fields", MIGRATED_3D_CASES)
def test_migrated_3d_dat_matches_legacy_parser_runtime(name, excluded_fields, tmp_path):
    legacy_cfg = _captured_legacy_3d_config(name, tmp_path)
    dat_path = ROOT / MIGRATED_PRESET_DATS[name]
    specification = load_and_resolve(dat_path)
    dat_cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    legacy = legacy_cfg.as_jsonable()
    migrated = dat_cfg.as_jsonable()
    diffs = {
        key: (legacy.get(key), migrated.get(key))
        for key in sorted(set(legacy) | set(migrated))
        if legacy.get(key) != migrated.get(key)
    }
    assert set(diffs) == excluded_fields
    assert legacy["stage_case"] == migrated["stage_case"]
    assert legacy["geometry_kind"] == migrated["geometry_kind"]
    assert legacy["period_x"] == migrated["period_x"]
    assert legacy["period_y"] == migrated["period_y"]
    assert legacy["lambda0"] == migrated["lambda0"]
    assert legacy["incident_theta_deg"] == migrated["incident_theta_deg"]
    assert legacy["incident_phi_deg"] == migrated["incident_phi_deg"]
    assert legacy["polarization_kind"] == migrated["polarization_kind"]
    assert legacy["use_floquet_xy"] == migrated["use_floquet_xy"]
    assert legacy["use_pml"] == migrated["use_pml"]
    assert legacy["z_min"] == migrated["z_min"]
    assert legacy["z_max"] == migrated["z_max"]


@pytest.mark.parametrize("name,excluded_fields", MIGRATED_2D_CASES)
def test_migrated_2d_dat_matches_legacy_parser_runtime(name, excluded_fields, tmp_path):
    legacy_cfg = _captured_legacy_2d_config(name, tmp_path)
    dat_path = ROOT / MIGRATED_PRESET_DATS[name]
    specification = load_and_resolve(dat_path)
    dat_cfg = simulation_config_2d_from_normalized(specification.as_jsonable())
    legacy = legacy_cfg.as_jsonable()
    migrated = dat_cfg.as_jsonable()
    diffs = {
        key: (legacy.get(key), migrated.get(key))
        for key in sorted(set(legacy) | set(migrated))
        if legacy.get(key) != migrated.get(key)
    }
    assert set(diffs) == excluded_fields
    for key in (
        "period_x",
        "air_height",
        "substrate_thickness",
        "grating_width",
        "grating_height",
        "lambda0",
        "incident_angle_deg",
        "k0",
        "kx",
        "ky",
        "polarization_type",
        "calculation_method",
        "constraint_backend",
        "scattering_background",
        "use_pml",
        "port_use_pml",
        "port_use_diffraction_orders",
        "port_dtn_assembly",
    ):
        assert legacy[key] == migrated[key], key
    assert len(specification.physical_model_sha256) == 64


def test_te_dtn_auto_is_rejected_but_zero_order_is_resolvable(tmp_path):
    source = (ROOT / "input/smoke/2d_tm_dtn_auxiliary_smoke.dat").read_text(
        encoding="utf-8"
    )
    auto_path = tmp_path / "te_dtn_auto.dat"
    auto_path.write_text(
        source.replace('polarization = "tm"', 'polarization = "te"'), encoding="utf-8"
    )
    with pytest.raises(
        InputError, match="TE Fourier DtN currently supports only zero_order"
    ):
        load_and_resolve(auto_path)

    zero_path = tmp_path / "te_dtn_zero.dat"
    zero_path.write_text(
        source.replace('polarization = "tm"', 'polarization = "te"').replace(
            'dtn_order_policy = "auto_propagating"',
            'dtn_order_policy = "zero_order"',
        ),
        encoding="utf-8",
    )
    specification = load_and_resolve(zero_path)
    assert specification.incidence["polarization"] == "te"
    assert specification.boundary["dtn_order_policy"] == "zero_order"


@pytest.mark.parametrize("name", tuple(MIGRATED_PRESET_DATS))
def test_every_migrated_dat_has_serial_direct_execution_contract(name):
    specification = load_and_resolve(ROOT / MIGRATED_PRESET_DATS[name])
    assert specification.execution["mpi_size"] == 1
    assert specification.solver["linear_solver"] == "direct"
    assert len(specification.physical_model_sha256) == 64


def test_preset_mapping_has_exact_scope_and_retains_history():
    assert len(MIGRATED_PRESET_DATS) == 11
    assert len(set(MIGRATED_PRESET_DATS.values())) == 11
    assert all((ROOT / path).is_file() for path in MIGRATED_PRESET_DATS.values())
    assert set(MIGRATED_PRESET_DATS) <= set(main.PRESET_INFO)
    retained = set(main.PRESETS_3D) - {
        name for name in MIGRATED_PRESET_DATS if name.startswith("3d_")
    }
    assert retained == {
        "3d_stage4b_demo_direct_h5",
        "3d_stage4b_demo_direct_h3",
        "3d_stage4b_demo_mumps_ooc",
        "3d_stage4b_demo_mumps_blr",
        "3d_target_grating_direct_h5",
        "3d_target_grating_direct_h3",
    }


def test_iterative_mpi1_dat_preserves_mpi8_physical_identity():
    mpi8 = load_and_resolve(
        ROOT / "input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat"
    )
    mpi1 = load_and_resolve(
        ROOT / "input/official/grazing1_phi0_hybrid_iterative_m120_mpi1.dat"
    )
    assert mpi8.physical_model_sha256 == mpi1.physical_model_sha256
    assert mpi8.method == mpi1.method
    assert mpi8.solver == mpi1.solver
    assert mpi8.method["requested_modes_per_direction"] == 120
    assert mpi1.execution["mpi_size"] == 1
    assert mpi8.execution["mpi_size"] == 8
