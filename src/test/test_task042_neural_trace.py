"""Material boundary, physical geometry and complex residual contracts."""

import copy
import json

import numpy as np
import pytest

from src.geometry.neural_micro_pilot import air_orders, hexa_inventory, material_tags
from src.io.input_loader import InputError
from src.io.neural_fe_interface import DESIGN_PATH, load_interface
from src.io.task042_profile import ROOT
from src.solvers.neural_trace import directional_check, residual_gradient


def test_n0_geometry_is_aligned_and_actually_notched_in_y_and_z():
    design = json.loads(DESIGN_PATH.read_text())
    g = design["geometry"]
    axes = [
        np.linspace(*bounds, cells + 1)
        for bounds, cells in zip(g["bounds_nm"], g["cells"], strict=True)
    ]
    for axis in axes:
        assert np.allclose(np.diff(axis), 0.175, atol=1e-14, rtol=0)
    midpoints = [
        (x, y, z)
        for z in (axes[2][:-1] + axes[2][1:]) / 2
        for y in (axes[1][:-1] + axes[1][1:]) / 2
        for x in (axes[0][:-1] + axes[0][1:]) / 2
    ]
    tags, notch = material_tags(
        midpoints,
        substrate_z=g["substrate_z_nm"],
        block_bounds=g["block_bounds_nm"],
        notch_bounds=g["notch_bounds_nm"],
    )
    assert len(tags) == 384 and notch.sum() == 8
    assert [np.count_nonzero(tags == tag) for tag in (1, 2, 3)] == [200, 48, 136]
    for point, expected in (
        ([0.1, 0.0, 0.5], 1),
        ([0.1, 0.3, 0.5], 3),
        ([0.1, 0.0, 0.8], 3),
    ):
        actual, _ = material_tags(
            [point],
            substrate_z=g["substrate_z_nm"],
            block_bounds=g["block_bounds_nm"],
            notch_bounds=g["notch_bounds_nm"],
        )
        assert actual[0] == expected


@pytest.mark.parametrize("p,full,trace", [(3, 34050, 18144), (4, 78936, 33792)])
def test_geometric_inventory_and_resource_limits(p, full, trace):
    inventory = hexa_inventory((8, 6, 8), p)
    assert inventory["full_fe_rows"] == full <= 200000
    assert inventory["independent_trace_rows"] == trace <= 100000
    assert inventory["full_trace_rows"] + inventory["interior_rows"] == full


def test_unknown_si_never_becomes_a_complete_port_inventory():
    design = json.loads(DESIGN_PATH.read_text())
    inventory = air_orders(design)
    assert inventory["top_channels"] > 0
    assert inventory["bottom_channels"] is None and inventory["total_channels"] is None
    assert design["materials"]["si_n"] is None


@pytest.mark.parametrize(
    "filename,stage",
    [
        ("v6_geometry_interface.dat", "V6-FE-INTERFACE"),
        ("v6_neural_vjp_interface.dat", "V6-ML-INTERFACE"),
    ],
)
def test_explicit_one_run_input_is_material_independent(filename, stage):
    specification = load_interface(
        ROOT / "input/task042_neural_coarse_inverse" / filename
    )
    assert specification.derived["stage"] == stage
    assert specification.materials["si_n"] is None
    assert specification.derived["physical_operator_sha256"] is None
    assert specification.method["kind"] == "material_independent_interface_only"


def test_no_ordinary_physical_case_is_intercepted():
    assert (
        load_interface(ROOT / "input/task042_neural_coarse_inverse/v5_d0_shared.dat")
        is None
    )


@pytest.mark.parametrize(
    "extra",
    ["[materials]\nn_substrate=[1.0,0.0]\n", '[solver]\npreconditioner="default"\n'],
)
def test_interface_cannot_smuggle_physics_or_solver(tmp_path, extra):
    text = (
        ROOT / "input/task042_neural_coarse_inverse/v6_geometry_interface.dat"
    ).read_text()
    path = tmp_path / "case.dat"
    path.write_text(text + extra)
    with pytest.raises(InputError):
        load_interface(path)


def test_complex_nonhermitian_gradient_has_correct_real_imaginary_signs():
    matrix = np.array([[1 + 2j, 3, 2j], [2 - 1j, 4j, 1], [3j, 2, 1 - 2j]])
    rhs = np.array([2 + 1j, 1 - 2j, 3 + 4j])
    parameters = np.arange(6) / 7 + 0.1
    z = parameters[:3] + 1j * parameters[3:]
    _, _, dual = residual_gradient(
        lambda x: matrix @ x, lambda x: matrix.conj().T @ x, z, rhs
    )
    gradient = np.r_[dual.real, dual.imag]

    def loss_at(value):
        return residual_gradient(
            lambda x: matrix @ x,
            lambda x: matrix.conj().T @ x,
            value[:3] + 1j * value[3:],
            rhs,
        )[0]

    checks = directional_check(
        loss_at, parameters, gradient, np.eye(6)[:3] + np.eye(6)[3:]
    )
    assert all(
        all(sample["passed"] for sample in record["samples"]) for record in checks
    )
    wrong = residual_gradient(lambda x: matrix @ x, lambda x: matrix.T @ x, z, rhs)[2]
    assert np.linalg.norm(wrong - dual) > 1e-2


@pytest.mark.parametrize("rhs", [np.zeros(3), np.array([1, np.nan, 2])])
def test_real_scattering_loss_refuses_fake_zero_or_nonfinite_rhs(rhs):
    with pytest.raises(ValueError):
        residual_gradient(lambda x: x, lambda x: x, np.ones(3), rhs)


def test_assembled_residual_norm_is_not_sum_of_local_squared_norms():
    # Neighboring contributions cancel in a shared FE row.
    contributions = [np.array([1 + 1j]), np.array([-1 - 1j])]
    assembled = np.sum(contributions, axis=0)
    assert np.vdot(assembled, assembled).real == 0
    assert sum(np.vdot(r, r).real for r in contributions) == 4


def test_legacy_freeze_design_not_mutated_by_air_inventory():
    design = json.loads(DESIGN_PATH.read_text())
    before = copy.deepcopy(design)
    air_orders(design)
    assert design == before and design["old_route"] == "CLOSED_RESEARCH_NEGATIVE"
