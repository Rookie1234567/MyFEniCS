from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.common.gate_cd_materials import (
    GATE_CD_REGION_TAGS,
    gate_cd_region_entries,
    validate_gate_cd_region_entries,
)
from src.common.materials import relative_permittivity
from src.io.input_validation import load_and_resolve
from src.io.native_capacity_profile import (
    P6_CONDENSED_DIRECT_PROFILES,
    TASK40_GATE_CD_P6_DIRECT_PROFILE,
)
from src.postprocessing.power_metrics import _volume_absorption_metrics
from src.postprocessing.rta_3d import (
    _validated_gate_cd_region_absorption,
    compute_volume_absorption_3d,
)
from src.runners.p6_condensed_direct import (
    _reject_unqualified_gate_cd_full_solve,
    _validate_resolved_profile,
)
from src.solvers.common_3d_forms import (
    _build_physical_volume_terms,
    _build_variational_forms,
)

_ROOT = Path(__file__).resolve().parents[2]
_INPUT = _ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_p6_staged.dat"

# Independent transcription of the user-preserved exact gate_cd material table.
_TAG_EPSILON = {
    101: 1.0 + 0.0j,
    102: 0.9997525478045688 + 0.000009266001361097818j,
    103: 0.9997525478045688 + 0.000009266001361097818j,
    104: 0.9997230630587056 + 0.00001782515900542709j,
    105: 0.9997525478045688 + 0.000009266001361097818j,
    106: 0.9997230630587056 + 0.00001782515900542709j,
    107: 0.9997243144507715 + 0.00001240364665357174j,
    108: 0.9997525478045688 + 0.000009266001361097818j,
    109: 0.9997455480845561 + 0.00007739189092108909j,
    110: 0.9997525478045688 + 0.000009266001361097818j,
    111: 0.9997455480845561 + 0.00007739189092108909j,
    112: 0.9997525478045688 + 0.000009266001361097818j,
    113: 0.9997455480845561 + 0.00007739189092108909j,
    114: 0.9997525478045688 + 0.000009266001361097818j,
    115: 0.9997455480845561 + 0.00007739189092108909j,
    116: 0.9997230630587056 + 0.00001782515900542709j,
    117: 0.9997455480845561 + 0.00007739189092108909j,
    118: 0.9997525478045688 + 0.000009266001361097818j,
    119: 0.9997455480845561 + 0.00007739189092108909j,
    120: 0.9997525478045688 + 0.000009266001361097818j,
    121: 0.9997455480845561 + 0.00007739189092108909j,
    122: 0.9997525478045688 + 0.000009266001361097818j,
    123: 0.9997455480845561 + 0.00007739189092108909j,
}


def _single_cell_per_region_fixture():
    ordered = tuple(_TAG_EPSILON)
    msh = mesh.create_box(
        MPI.COMM_SELF,
        [np.asarray((0.0, 0.0, 0.0)), np.asarray((23.0, 1.0, 1.0))],
        [23, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = msh.topology.dim
    tags = mesh.meshtags(
        msh,
        tdim,
        np.arange(23, dtype=np.int32),
        np.asarray(ordered, dtype=np.int32),
    )
    cfg = target_stage4_config(degree=1, h_nm=1.0)
    cfg.geometry_kind = "task40_gate_cd_mapped"
    cfg.lambda0 = 0.7
    cfg.physical_material_regions = gate_cd_region_entries()
    si_n = complex(0.999876266258, 0.00000463357401)
    cfg.n_substrate = si_n
    cfg.n_grating = si_n
    return msh, tags, SimpleNamespace(mesh=msh, cell_tags=tags), cfg


def _relative_matrix_error(actual, expected) -> float:
    difference = actual.copy()
    try:
        difference.axpy(
            PETSc.ScalarType(-1.0),
            expected,
            structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
        )
        denominator = max(float(expected.norm()), 1.0e-30)
        return float(difference.norm() / denominator)
    finally:
        difference.destroy()


def test_gate_cd_production_loader_profile_and_full_solve_fail_closed(tmp_path):
    specification = load_and_resolve(_INPUT)
    payload = specification.as_jsonable()
    facts = _validate_resolved_profile(payload)
    assert TASK40_GATE_CD_P6_DIRECT_PROFILE in P6_CONDENSED_DIRECT_PROFILES
    assert facts["identity"] == TASK40_GATE_CD_P6_DIRECT_PROFILE
    assert facts["component_options"]["mesh_axis_cell_counts"] == [5, 240, 23]
    assert facts["component_options"]["mesh_plan_sha256"]
    assert len(facts["component_options"]["physical_material_regions"]) == 23
    assert facts["resources"]["resource_stop_policy"] == "host_available_floor_v1"
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["component_options"]["direct_route_launchable"] is False
    with pytest.raises(RuntimeError, match="full P6 solve is not enabled"):
        _reject_unqualified_gate_cd_full_solve(facts)

    assert specification.derived["mesh_cells"] == (5, 240, 23)
    assert specification.physical_model_sha256

    changed = _INPUT.read_text(encoding="utf-8").replace(
        "wavelength_nm = 0.7", "wavelength_nm = 0.8"
    )
    altered = tmp_path / "wrong_wavelength.dat"
    altered.write_text(changed, encoding="utf-8")
    with pytest.raises(Exception, match="wavelength_nm"):
        load_and_resolve(altered)


def test_gate_cd_region_map_is_exact_and_requires_all_23_regions():
    entries = gate_cd_region_entries()
    normalized = validate_gate_cd_region_entries(entries)
    assert tuple(entry["label"] for entry in normalized) == tuple(GATE_CD_REGION_TAGS)
    assert {int(entry["tag"]) for entry in normalized} == set(_TAG_EPSILON)
    assert {int(entry["tag"]): complex(entry["epsilon_r"]) for entry in normalized} == _TAG_EPSILON

    with pytest.raises(ValueError, match="cover exactly"):
        validate_gate_cd_region_entries(entries[:-1])
    with pytest.raises(ValueError, match="unique"):
        validate_gate_cd_region_entries([*entries[:-1], entries[0]])


def test_gate_cd_missing_or_nonfinite_region_loss_fails_closed():
    expected_labels = tuple(f"region_{index}" for index in range(23))
    region_facts = {
        label: {
            "cell_count": 1,
            "status": "lossless" if index == 0 else "ok",
            "A_volume": 0.0 if index == 0 else 1.0e-4,
            "absorbed_power_code_units": 0.0 if index == 0 else 1.0e-5,
        }
        for index, label in enumerate(expected_labels)
    }
    values, total = _validated_gate_cd_region_absorption(region_facts, expected_labels)
    assert len(values) == 23
    assert total == pytest.approx(22.0e-4)

    missing = dict(region_facts)
    del missing["region_7"]
    with pytest.raises(ValueError, match="do not cover every"):
        _validated_gate_cd_region_absorption(missing, expected_labels)
    nonfinite = {key: dict(value) for key, value in region_facts.items()}
    nonfinite["region_7"]["A_volume"] = float("nan")
    with pytest.raises(ValueError, match="non-finite"):
        _validated_gate_cd_region_absorption(nonfinite, expected_labels)
    zero_cells = {key: dict(value) for key, value in region_facts.items()}
    zero_cells["region_7"]["cell_count"] = 0
    with pytest.raises(ValueError, match="no cells"):
        _validated_gate_cd_region_absorption(zero_cells, expected_labels)


def test_gate_cd_material_mapping_and_production_forms_match_independent_table(
    tmp_path,
):
    msh, cell_tags, mesh_data, cfg = _single_cell_per_region_fixture()
    eps = relative_permittivity(mesh_data, cfg)
    eps_space = eps.function_space
    for cell, tag in enumerate(_TAG_EPSILON):
        dofs = np.asarray(eps_space.dofmap.cell_dofs(cell), dtype=np.int64)
        assert dofs.size == 1
        assert complex(eps.x.array[int(dofs[0])]) == pytest.approx(_TAG_EPSILON[tag])
    assert np.all(np.isfinite(eps.x.array.real))
    assert np.all(np.isfinite(eps.x.array.imag))

    V = fem.functionspace(
        msh,
        element("N1curl", "hexahedron", 1, dtype=default_real_type),
    )
    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    dx = ufl.Measure(
        "dx", domain=msh, subdomain_data=cell_tags,
        metadata={"quadrature_degree": 4},
    )
    curl_term, mass_term = _build_physical_volume_terms(cfg, trial, test, dx)
    production_form = fem.form(curl_term + mass_term)

    # Independent transcription and summation, rather than reusing the
    # production material-map iterator.
    reference_form_ufl = PETSc.ScalarType(0.0) * ufl.inner(
        ufl.curl(trial), ufl.curl(test)
    ) * dx
    reference_form_ufl += PETSc.ScalarType(0.0) * ufl.inner(trial, test) * dx
    for tag, epsilon in _TAG_EPSILON.items():
        reference_form_ufl += ufl.inner(ufl.curl(trial), ufl.curl(test)) * dx(tag)
        reference_form_ufl += (
            -cfg.k0**2 * PETSc.ScalarType(epsilon) * ufl.inner(trial, test) * dx(tag)
        )
    reference_form = fem.form(reference_form_ufl)
    production = fem_petsc.assemble_matrix(production_form, bcs=[])
    reference = fem_petsc.assemble_matrix(reference_form, bcs=[])
    try:
        production.assemble()
        reference.assemble()
        assert production.getSize() == reference.getSize()
        assert _relative_matrix_error(production, reference) < 2.0e-13
    finally:
        production.destroy()
        reference.destroy()

    # The gate_cd contract only accepts the direct total-field RHS route.
    with pytest.raises(ValueError, match="only the direct total-field"):
        _build_variational_forms(
            msh,
            mesh_data,
            cfg,
            V,
            field_formulation="layered_scattered",
            incident_field=None,
        )


def test_gate_cd_all_region_volume_loss_matches_independent_analytic_constants(tmp_path):
    msh, _cell_tags, mesh_data, cfg = _single_cell_per_region_fixture()
    V = fem.functionspace(
        msh,
        element("N1curl", "hexahedron", 1, dtype=default_real_type),
    )
    field = fem.Function(V, name="constant_total_E")
    vector = np.asarray((1.0 + 0.25j, 0.5 - 0.1j, -0.3j), dtype=PETSc.ScalarType)
    field.interpolate(
        lambda x: np.vstack(
            [np.full(x.shape[1], value, dtype=PETSc.ScalarType) for value in vector]
        )
    )
    field.x.scatter_forward()
    field_norm_sq = float(np.vdot(vector, vector).real)
    incident_power = 3.7

    rta = compute_volume_absorption_3d(
        mesh_data,
        cfg,
        field,
        tmp_path / "rta",
        incident_power=incident_power,
    )
    assert set(rta["regions"]) == set(GATE_CD_REGION_TAGS)
    assert rta["A_volume_total"] == pytest.approx(
        sum(
            0.5 * cfg.k0 * epsilon.imag * field_norm_sq / incident_power
            for epsilon in _TAG_EPSILON.values()
        ),
        rel=2.0e-11,
    )
    assert json.loads((tmp_path / "rta/volume_absorption.json").read_text())["regions"]

    metrics = _volume_absorption_metrics(
        mesh_data,
        cfg,
        field,
        incident_power,
        field_model="total_field_test_fixture",
    )
    assert set(metrics["volume_absorption_by_physical_region"]) == set(GATE_CD_REGION_TAGS)
    assert metrics["absorbed_power_weighted"] == pytest.approx(
        sum(0.5 * cfg.k0**2 * epsilon.imag * field_norm_sq for epsilon in _TAG_EPSILON.values()),
        rel=2.0e-11,
    )
