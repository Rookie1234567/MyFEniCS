from __future__ import annotations

from collections import Counter
from itertools import pairwise
from math import prod
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_d5_axis_plan import (
    D5_BASE_AXIS_SHA256_LE_F64,
    D5_CASES,
    d5_axis_plan,
)
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_D5_B_P6_DIRECT_PROFILE,
    TASK40_PHI90_D5_PROFILES,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import _direct_run_contract
from src.solvers.dtn_port_3d import (
    _incident_projection_onto_top_mode,
    _mode_boundary_phase,
    _mode_power_at_boundary,
    _mode_projection_denominator,
    _mode_projection_from_solution,
    _ReusableSurfaceComponentAssembler,
)
from src.solvers.fullspace_dtn_action import (
    build_dynamic_mode_inventory,
)

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "input" / "task40para_phi90_mesh_modes_direct"
DAT_FILES = {
    case: INPUTS / f"d5_{case.lower()}_r5_p6_direct.dat"
    for case in ("B", "X", "Y", "Z")
}
EXPECTED_TAGS = {
    "B": {"1": 5188, "2": 920, "3": 792},
    "X": {"1": 10376, "2": 1840, "3": 1584},
    "Y": {"1": 10376, "2": 1840, "3": 1584},
    "Z": {"1": 10376, "2": 1840, "3": 1584},
}


def _independent_midpoint_tags(plan):
    axes = plan["axes_nm"]
    tags: list[int] = []
    for z0, z1 in pairwise(axes["z"]):
        zmid = 0.5 * (z0 + z1)
        for y0, y1 in pairwise(axes["y"]):
            ymid = 0.5 * (y0 + y1)
            for x0, x1 in pairwise(axes["x"]):
                xmid = 0.5 * (x0 + x1)
                if zmid < 0.0:
                    tag = 2
                elif zmid >= 120.0:
                    tag = 1
                elif 16.5 < xmid < 33.5 and 15.0 < ymid < 35.0:
                    tag = 3
                else:
                    tag = 1
                tags.append(tag)
    return Counter(map(int, tags))


@pytest.mark.parametrize("case", ("B", "X", "Y", "Z"))
def test_d5_dat_and_public_stage4_planner_bind_exact_one_axis_plan(case):
    plan = d5_axis_plan(case)
    specification = load_and_resolve(DAT_FILES[case])
    resolved = specification.as_jsonable()
    cfg = simulation_config_3d_from_normalized(resolved)
    actual = stage4_axis_plan(cfg, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual, f"{axis}_values"))
        for axis in ("x", "y", "z")
    }

    assert tuple(actual.mesh_cells_resolved) == tuple(plan["axis_cell_counts"])
    assert actual.mesh_spacing_mode_resolved == "task40_phi90_d5_frozen_axes"
    for axis in ("x", "y", "z"):
        assert actual_axes[axis] == tuple(plan["axes_nm"][axis])
    assert plan["parent_axis_sha256_le_f64"] == D5_BASE_AXIS_SHA256_LE_F64
    assert _independent_midpoint_tags(plan) == Counter(
        {int(key): int(value) for key, value in EXPECTED_TAGS[case].items()}
    )

    facts = native_profile_facts(resolved["solver"]["native_capacity_profile"])
    comparison = facts["component_options"]["directional_mesh_comparison"]
    assert comparison["expected_material_tag_counts"] == EXPECTED_TAGS[case]
    assert facts["component_options"]["expected_global_cell_count"] == prod(
        plan["axis_cell_counts"]
    )
    assert facts["component_options"]["surface_quadrature"]["degree"] == 39
    assert facts["component_options"]["volume_quadrature"]["degree"] == 15
    assert resolved["model_id"] == "si_block_phi90_50x50_17x20_h120"
    assert resolved["incidence"]["wavelength_nm"] == 5.0
    assert resolved["discretization"]["nedelec_degree"] == 6

    changed_axis = D5_CASES[case]["changed_axis"]
    for axis in ("x", "y", "z"):
        if changed_axis is None or axis != changed_axis:
            assert plan["actual_axis_sha256_le_f64"][axis] == (
                D5_BASE_AXIS_SHA256_LE_F64[axis]
            )
        else:
            assert plan["actual_axis_sha256_le_f64"][axis] != (
                D5_BASE_AXIS_SHA256_LE_F64[axis]
            )


def test_d5_tag_contract_rejects_wrong_whole_z_middle_as_grating():
    plan = d5_axis_plan("B")
    facts = native_profile_facts(TASK40_PHI90_D5_B_P6_DIRECT_PROFILE)
    expected = facts["component_options"]["directional_mesh_comparison"][
        "expected_material_tag_counts"
    ]
    axes = plan["axes_nm"]
    wrong = Counter()
    for z0, z1 in pairwise(axes["z"]):
        zmid = 0.5 * (z0 + z1)
        for y0, y1 in pairwise(axes["y"]):
            for x0, x1 in pairwise(axes["x"]):
                if zmid < 0.0:
                    wrong[2] += 1
                elif zmid >= 120.0:
                    wrong[1] += 1
                else:
                    wrong[3] += 1
    assert wrong == Counter({1: 920, 2: 920, 3: 5060})
    assert wrong != Counter({int(k): int(v) for k, v in expected.items()})


def test_d5_wrong_axis_and_wrong_material_inputs_are_rejected():
    loaded = load_dat_input(DAT_FILES["Y"])
    config = _validate_sections(_plain(loaded.document))
    wrong_axes = d5_axis_plan("Y")
    wrong_y = tuple(wrong_axes["axes_nm"]["y"])
    config["discretization"]["mesh_axis_y_values"] = list(
        wrong_y[:-1] + (float(wrong_y[-1]) - 0.125,)
    )
    with pytest.raises(InputError, match="invalid frozen D5 axes"):
        validate_native_case(config)

    loaded = load_dat_input(DAT_FILES["B"])
    config = _validate_sections(_plain(loaded.document))
    config["materials"]["n_grating"] = [0.99396854453, 0.00435380770]
    with pytest.raises(InputError, match="materials.n_grating"):
        validate_native_case(config)


def test_production_r5_inventory_is_complete_and_boundary_scaled_hash_is_frozen():
    specification = load_and_resolve(DAT_FILES["B"])
    resolved = specification.as_jsonable()
    profile_identity = resolved["solver"]["native_capacity_profile"]
    assert profile_identity in TASK40_PHI90_D5_PROFILES
    route = _direct_run_contract(profile_identity)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_rectangle"
    cfg.task40_dtn_rectangle_max_m = 11
    cfg.task40_dtn_rectangle_max_n = 20
    cfg.stage4_dtn_quadrature_degree = 39

    unscaled_modes = outgoing_port_modes_3d(cfg)
    assert len(unscaled_modes) == 3772
    with pytest.raises(ValueError, match="finite and positive"):
        build_dynamic_mode_inventory(cfg)

    cfg.task40_port_boundary_amplitude_scale_policy = route[
        "mode_basis_scale_policy"
    ]
    modes, rows, digest = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == route["parent_count"] == 3772
    assert digest == route["expected_mode_sha256"] == (
        "752333bbc4082b9d7f9f1c935433eeb8e4c8b5e44a74a27310944b6b8aa531bc"
    )
    assert {(row["m"], row["n"]) for row in rows} == {
        (m, n) for m in range(-11, 12) for n in range(-20, 21)
    }
    assert all(np.isfinite(row["projection_denominator"])
               and row["projection_denominator"] > 0.0 for row in rows)
    assert all(row["boundary_amplitude_scale_policy"] == (
        "boundary_magnitude_scaled_r5_v1"
    ) for row in rows)
    assert max(row["boundary_amplitude_scale"] for row in rows) < 2.0e215
    assert route["surface_quadrature_degree"] == 39
    assert route["surface_quadrature_envelope_max_abs_m_n"] == [12, 21]


def test_d5_mode_basis_scaling_preserves_carrier_action_and_boundary_field():
    scale = 1.0e80
    projection = np.asarray([1.25 - 0.75j], dtype=np.complex128)
    coupling = np.asarray([-0.4 + 2.0j], dtype=np.complex128)
    x = 0.6 + 0.2j
    h = 3.0e-150
    h_scaled = scale * scale * h
    original_action = coupling * (projection * x / h)
    scaled_action = (scale * coupling) * ((scale * projection) * x / h_scaled)
    np.testing.assert_allclose(scaled_action, original_action, rtol=3e-15, atol=0.0)

    original_aux = projection[0] * x / h
    scaled_aux = (scale * projection[0]) * x / h_scaled
    port_phase = 0.8 - 0.3j
    original_boundary = original_aux * port_phase
    scaled_boundary = scaled_aux * scale * port_phase
    np.testing.assert_allclose(scaled_boundary, original_boundary, rtol=3e-15, atol=0.0)

    cfg = SimpleNamespace(
        x_min=0.0,
        x_max=2.0,
        y_min=0.0,
        y_max=3.0,
        physical_z_max=4.0,
        kz=0.9 + 0.2j,
        incident_amplitude=1.0,
        polarization_vector=np.asarray([1.0 + 0j, 0.0 + 0j, 0.0 + 0j]),
        k0=1.0,
        mu_r=1.0 + 0j,
    )
    power_mode = SimpleNamespace(
        side="top",
        m=0,
        n=0,
        k_vector=np.asarray([0.0 + 0j, 0.0 + 0j, 0.8 + 0.1j]),
        e_vector=np.asarray([1.0 + 0j, 0.0 + 0j, 0.0 + 0j]),
        electric_tangential_norm_sq=1.0,
        power_per_unit_amplitude=1.0,
        boundary_amplitude_scale=1.0,
        boundary_amplitude_log_scale=0.0,
    )
    physical_amplitude = 0.3 - 0.7j
    reference_power = _mode_power_at_boundary(power_mode, cfg, physical_amplitude)
    power_mode.boundary_amplitude_scale = scale
    power_mode.boundary_amplitude_log_scale = float(np.log(scale))
    scaled_power = _mode_power_at_boundary(
        power_mode, cfg, physical_amplitude / scale
    )
    assert scaled_power == pytest.approx(reference_power, rel=1e-14, abs=0.0)
    incident_coefficient = -0.25 + 0.5j
    scaled_incident_coefficient = incident_coefficient / scale
    assert scale * scaled_incident_coefficient == pytest.approx(
        incident_coefficient
    )


def test_d5_scaled_boundary_phase_avoids_q_squared_overflow_and_h_underflow():
    log_scale = 400.0
    scale = float(np.exp(log_scale))
    with np.errstate(over="ignore"):
        assert not np.isfinite(scale * scale)
    cfg = SimpleNamespace(
        x_min=0.0,
        x_max=2.0,
        y_min=0.0,
        y_max=3.0,
        physical_z_max=1.0,
        physical_z_min=-1.0,
        kz=400.0j,
        incident_amplitude=1.0,
        polarization_vector=np.asarray([1.0 + 0j, 0.0 + 0j, 0.0 + 0j]),
    )
    mode = SimpleNamespace(
        side="top",
        m=1,
        n=0,
        k_vector=np.asarray([0.0 + 0j, 0.0 + 0j, 400.0j]),
        e_vector=np.asarray([1.0 + 0j, 0.0 + 0j, 0.0 + 0j]),
        electric_tangential_norm_sq=1.0,
        boundary_amplitude_scale=scale,
        boundary_amplitude_log_scale=log_scale,
    )
    raw_phase = np.exp(1j * mode.k_vector[2] * cfg.physical_z_max)
    assert raw_phase != 0.0
    assert float(abs(raw_phase) ** 2) == 0.0
    stable_phase = _mode_boundary_phase(mode, cfg)
    assert stable_phase == pytest.approx(1.0 + 0.0j)
    assert _mode_projection_denominator(mode, cfg) == pytest.approx(6.0)
    original_boundary = 1.0 * raw_phase
    rescaled_boundary = (1.0 / scale) * stable_phase
    assert rescaled_boundary == pytest.approx(original_boundary, rel=3e-14, abs=0.0)


def test_d5_independent_projection_uses_scaled_basis_before_complex_integration(
    monkeypatch,
):
    import src.solvers.dtn_port_3d as dtn_port

    class ProjectionForm:
        def __init__(self, electric, reference):
            self.electric = tuple(electric)
            self.reference = tuple(reference)

        def __mul__(self, _measure):
            return self

    class FakeUFL:
        @staticmethod
        def SpatialCoordinate(mesh):
            return mesh.coordinates

        @staticmethod
        def exp(value):
            return np.exp(value)

        @staticmethod
        def as_vector(values):
            return tuple(values)

        @staticmethod
        def inner(electric, reference):
            return ProjectionForm(electric, reference)

        @staticmethod
        def Measure(_kind, *, domain, subdomain_data):
            del domain, subdomain_data
            return lambda _tag: object()

    class FakeComm:
        @staticmethod
        def allreduce(value, op):
            del op
            return value

    coordinates = (0.5, 0.25, 1.0)
    area = 6.0
    mesh = SimpleNamespace(coordinates=coordinates, comm=FakeComm())
    mesh_data = SimpleNamespace(
        mesh=mesh,
        facet_tags=object(),
    )
    cfg = SimpleNamespace(
        tags=SimpleNamespace(z_min=1, z_max=2),
        x_min=0.0,
        x_max=2.0,
        y_min=0.0,
        y_max=3.0,
        physical_z_min=-1.0,
        physical_z_max=1.0,
    )

    monkeypatch.setattr(dtn_port, "ufl", FakeUFL)
    monkeypatch.setattr(dtn_port.fem, "form", lambda expression: expression)
    monkeypatch.setattr(
        dtn_port.fem,
        "assemble_scalar",
        lambda expression: area
        * sum(
            electric * np.conj(reference)
            for electric, reference in zip(
                expression.electric, expression.reference, strict=True
            )
        ),
    )
    monkeypatch.setattr(
        dtn_port,
        "_with_quadrature_degree",
        lambda expression, _degree: expression,
    )

    alpha = 0.31 + 0.0j
    gamma = -0.27 + 0.0j
    kz = 0.7 + 500.0j
    e_vector = np.asarray([1.0 + 0.25j, -0.3 + 0.4j, 0.0j])
    amplitude = -0.6 + 0.2j
    log_scale = 500.0
    scale = float(np.exp(log_scale))
    with np.errstate(over="ignore"):
        assert not np.isfinite(scale * scale)
    mode = SimpleNamespace(
        side="top",
        m=2,
        n=-1,
        polarization="s",
        alpha=alpha,
        gamma=gamma,
        k_vector=np.asarray([alpha, gamma, kz], dtype=np.complex128),
        e_vector=e_vector,
        electric_tangential_norm_sq=float(np.vdot(e_vector[:2], e_vector[:2]).real),
        boundary_amplitude_scale=scale,
        boundary_amplitude_log_scale=log_scale,
    )
    raw_phase = np.exp(
        1j
        * (
            alpha * coordinates[0]
            + gamma * coordinates[1]
            + kz * coordinates[2]
        )
    )
    field = amplitude * raw_phase * e_vector
    scaled_coefficient = _mode_projection_from_solution(
        field,
        mode,
        mesh_data,
        cfg,
        quadrature_degree=28,
    )
    assert _mode_projection_denominator(mode, cfg) > 0.0
    assert scaled_coefficient == pytest.approx(amplitude / scale, rel=2e-13, abs=0.0)
    scaled_boundary_phase = _mode_boundary_phase(mode, cfg)
    recovered_boundary_field = (
        scaled_coefficient
        * scaled_boundary_phase
        * np.exp(1j * (alpha * coordinates[0] + gamma * coordinates[1]))
        * e_vector
    )
    np.testing.assert_allclose(recovered_boundary_field, field, rtol=3e-13, atol=0.0)

    # The q=1 legacy expression still projects with its original unscaled basis.
    legacy_mode = SimpleNamespace(
        **{
            **vars(mode),
            "k_vector": np.asarray([alpha, gamma, 0.7 + 0.2j]),
            "boundary_amplitude_scale": 1.0,
            "boundary_amplitude_log_scale": 0.0,
        }
    )
    legacy_phase = np.exp(
        1j
        * (
            alpha * coordinates[0]
            + gamma * coordinates[1]
            + legacy_mode.k_vector[2] * coordinates[2]
        )
    )
    legacy_field = amplitude * legacy_phase * e_vector
    assert _mode_projection_from_solution(
        legacy_field,
        legacy_mode,
        mesh_data,
        cfg,
        quadrature_degree=28,
    ) == pytest.approx(amplitude, rel=2e-14, abs=0.0)


def test_d5_native_surface_form_applies_log_scale_before_assembly(monkeypatch):
    import src.solvers.dtn_port_3d as dtn_port

    class Expr:
        def __init__(self, value):
            self.tree = value

        @staticmethod
        def _value(other):
            return other.tree if isinstance(other, Expr) else other

        def __add__(self, other):
            return Expr(("add", self.tree, self._value(other)))

        def __radd__(self, other):
            return Expr(("add", self._value(other), self.tree))

        def __mul__(self, other):
            return Expr(("mul", self.tree, self._value(other)))

        def __rmul__(self, other):
            return Expr(("mul", self._value(other), self.tree))

    class FakeConstant(Expr):
        def __init__(self, _mesh, value, label):
            super().__init__(("constant", label))
            self.value = value

    class FakeUfl:
        @staticmethod
        def SpatialCoordinate(_mesh):
            return tuple(Expr(("x", index)) for index in range(3))

        @staticmethod
        def exp(value):
            return Expr(("exp", Expr._value(value)))

        @staticmethod
        def as_vector(values):
            return Expr(("vector", tuple(Expr._value(value) for value in values)))

        @staticmethod
        def TestFunction(_space):
            return Expr("test")

        @staticmethod
        def Measure(_name, *, domain, subdomain_data):
            return lambda tag: Expr(("measure", id(domain), id(subdomain_data), tag))

        @staticmethod
        def inner(left, right):
            return Expr(("inner", Expr._value(left), Expr._value(right)))

    class FakeVector:
        def destroy(self):
            self.destroyed = True

    mesh = SimpleNamespace(comm=object())
    mesh_data = SimpleNamespace(mesh=mesh, facet_tags=object())
    constants = []
    captured_log_scales = []
    fake_fem = SimpleNamespace(
        Constant=lambda mesh_arg, value: FakeConstant(
            mesh_arg, value, f"constant_{len(constants)}"
        ),
        form=lambda value, **_kwargs: value,
    )
    original_constant = fake_fem.Constant

    def make_constant(mesh_arg, value):
        constant = original_constant(mesh_arg, value)
        constants.append(constant)
        return constant

    fake_fem.Constant = make_constant
    monkeypatch.setattr(dtn_port, "fem", fake_fem)
    monkeypatch.setattr(dtn_port, "ufl", FakeUfl())
    monkeypatch.setattr(dtn_port, "_with_quadrature_degree", lambda form, _q: form)

    scaled = _ReusableSurfaceComponentAssembler(
        object(), mesh_data, 5, 0, scaled_mode_basis=True
    )
    assert "constant_3" in repr(scaled.form.tree)
    monkeypatch.setattr(
        dtn_port,
        "_assemble_mpc_form_vector",
        lambda _form, _mpc: (
            captured_log_scales.append(scaled.log_amplitude_scale.value)
            or FakeVector()
        ),
    )
    monkeypatch.setattr(
        dtn_port,
        "_vec_nonzero_owned_entries",
        lambda _vec, **_kwargs: (
            np.asarray([0], dtype=np.int64),
            np.asarray([1.0 + 0.0j], dtype=np.complex128),
        ),
    )
    mode = SimpleNamespace(
        alpha=0.0 + 0.0j,
        gamma=0.0 + 0.0j,
        k_vector=np.asarray([0.0 + 0.0j, 0.0 + 0.0j, 400.0j]),
        boundary_amplitude_log_scale=400.0,
    )
    scaled.assemble_entries(mode, object())
    assert captured_log_scales == [400.0]

    legacy = _ReusableSurfaceComponentAssembler(
        object(), mesh_data, 5, 0, scaled_mode_basis=False
    )
    assert "constant_3" not in repr(legacy.form.tree)


def test_mode_boundary_scale_keeps_h_and_incident_projection_consistent():
    cfg = SimpleNamespace(
        x_min=0.0,
        x_max=2.0,
        y_min=0.0,
        y_max=3.0,
        physical_z_max=4.0,
        kz=0.9 + 0.2j,
        incident_amplitude=1.0,
        polarization_vector=np.asarray([1.0 + 0j, 0.0 + 0j, 0.0 + 0j]),
    )
    mode = SimpleNamespace(
        side="top",
        m=0,
        n=0,
        k_vector=np.asarray([0.0 + 0j, 0.0 + 0j, 0.8 + 0.1j]),
        e_vector=np.asarray([1.0 + 0j, 0.0 + 0j, 0.0 + 0j]),
        electric_tangential_norm_sq=1.0,
        boundary_amplitude_scale=1.0,
    )
    old_h = _mode_projection_denominator(mode, cfg)
    old_inc = _incident_projection_onto_top_mode(mode, cfg)
    scale = 1.0e40
    mode.boundary_amplitude_scale = scale
    mode.boundary_amplitude_log_scale = float(np.log(scale))
    new_h = _mode_projection_denominator(mode, cfg)
    new_inc = _incident_projection_onto_top_mode(mode, cfg)
    assert new_h == pytest.approx(old_h * scale * scale)
    assert new_inc == pytest.approx(old_inc / scale)
    assert _mode_boundary_phase(mode, cfg) == pytest.approx(
        scale * np.exp(1j * mode.k_vector[2] * cfg.physical_z_max)
    )


def test_d13_legacy_mode_manifest_hash_is_unchanged_without_d5_policy():
    specification = load_and_resolve(
        INPUTS / "d13_y2_r13_p6_direct.dat"
    )
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    from src.runners.p6_condensed_direct import _direct_run_contract

    route = _direct_run_contract(
        specification.as_jsonable()["derived"]["native_capacity_profile"][
            "identity"
        ]
    )
    cfg.stage4_dtn_order_policy = "explicit_rectangle"
    cfg.task40_dtn_rectangle_max_m = route[
        "parent_rectangle_max_abs_m_n"
    ][0]
    cfg.task40_dtn_rectangle_max_n = route[
        "parent_rectangle_max_abs_m_n"
    ][1]
    cfg.stage4_dtn_quadrature_degree = route["surface_quadrature_degree"]
    modes, rows, digest = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == 612
    assert digest == "1987a2b30de90aae9c253852f25c4192c7370e44d8793e91fc83dd28cf7e522e"
    assert all("boundary_amplitude_scale_policy" not in row for row in rows)
    assert all("boundary_amplitude_scale" not in row for row in rows)
