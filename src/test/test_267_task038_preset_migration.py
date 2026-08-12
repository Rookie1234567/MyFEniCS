"""Pure Task38 T7 checks for ordinary preset migration and runtime seams."""

import json
from pathlib import Path

import pytest

from src import main
from src.io import load_and_resolve
from src.io.execution_plan import CONNECTED_METHODS
from src.io.input_loader import InputError
from src.io.input_validation import (
    simulation_config_3d_from_normalized,
)
from src.io.preset_migration import MIGRATED_PRESET_DATS
from src.common.modes_3d import outgoing_port_modes_3d
from src.postprocessing.diffraction_3d import _power_orders_for_reporting
from src.runners.task038_2d import run_2d


ROOT = Path(__file__).resolve().parents[2]
ORDINARY_2D = ROOT / "input/templates/ordinary_2d_example.dat"


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
    specification = load_and_resolve(ROOT / "input/smoke/2d_tm_dtn_explicit_smoke.dat")
    assert specification.boundary["dtn_assembly"] == "explicit"
    assert specification.boundary["dtn_order_policy"] == "auto_propagating"

    received = {}

    def fake_solver(cfg, output_directory, constraint_backend):
        received.update(cfg=cfg, output_directory=output_directory)
        return _summary()

    result = run_2d(specification.as_jsonable(), tmp_path, solver_runner=fake_solver)
    assert result["passed"] is True
    assert received["cfg"].port_dtn_assembly == "explicit"
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
    assert set(MIGRATED_PRESET_DATS) <= set(main.available_preset_names())
    assert not set(MIGRATED_PRESET_DATS) & set(main.PRESET_INFO)
    retained = set(main.PRESETS_3D)
    assert retained == {
        "3d_stage4b_demo_direct_h5",
        "3d_stage4b_demo_direct_h3",
        "3d_stage4b_demo_mumps_ooc",
        "3d_stage4b_demo_mumps_blr",
        "3d_target_grating_direct_h5",
        "3d_target_grating_direct_h3",
    }


def test_t7_compact_evidence_is_present_and_hash_bound():
    record_path = (
        ROOT
        / "docs/task038_input_driven_configuration/outcomes/records/"
        / "t7_preset_migration_equivalence_v1.json"
    )
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "formal_pde_equivalence_pass"
    assert record["source_sha"] == "f86a7e42dc2c44d36c8e5ab6dfa1d9bb8ef8ed42"
    assert set(record["formal_runs"]) == {
        "A_legacy_2d",
        "A_dat_2d",
        "B_legacy_stage1",
        "B_dat_stage1",
    }
    assert record["comparison"]["A_legacy_vs_dat"]["status"] == "pass"
    assert record["comparison"]["B_legacy_vs_dat"]["status"] == "pass"
    assert record["boundaries"]["research_history_presets_retained"] == 6


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
