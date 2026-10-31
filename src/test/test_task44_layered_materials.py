from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from scripts.task44_native_service import verify_task44_root
from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.runners.task038_full3d_direct import _stage4_authority_errors
from src.runners.task038_launcher import _environment_identity


def _layered_input(path: Path, label: str, thicknesses: tuple[float, ...]) -> Path:
    template = Path("input/templates/full3d_layered_direct_example.dat").read_text(
        encoding="utf-8"
    )
    total = sum(thicknesses)
    replacements = {
        "run_id": f'run_id = "sample_{label}"',
        "z_max_nm": f"z_max_nm = {total + 0.5}",
        "air_height_nm": f"air_height_nm = {total + 0.5}",
        "grating_height_nm": f"grating_height_nm = {total}",
    }
    for key, value in replacements.items():
        template, count = re.subn(rf"(?m)^{key}\s*=.*$", value, template, count=1)
        assert count == 1
    layer_array = "grating_layer_thicknesses_nm = [" + ", ".join(
        str(value) for value in thicknesses
    ) + "]"
    template, count = re.subn(
        r"(?m)^grating_layer_thicknesses_nm\s*=.*$", layer_array, template, count=1
    )
    assert count == 1
    path.write_text(template, encoding="utf-8")
    return path
from src.solvers.common_3d_case_flow import (
    _official_result_after_stage4_gates,
    _record_stage4_energy_closure_gate,
)


def test_official_result_requires_requested_explicit_true_residual():
    common = {
        "external_solver_snapshot": False,
        "external_rta_gate_pass": None,
        "task41_native_a6_gate_pass": None,
    }
    assert _official_result_after_stage4_gates(
        True,
        **common,
        linear_system_relative_residual=9.0e-7,
        true_residual_tolerance=1.0e-6,
    )
    assert not _official_result_after_stage4_gates(
        True,
        **common,
        linear_system_relative_residual=1.1e-6,
        true_residual_tolerance=1.0e-6,
    )
    assert not _official_result_after_stage4_gates(
        True,
        **common,
        linear_system_relative_residual=None,
        true_residual_tolerance=1.0e-6,
    )


class _SerialComm:
    rank = 0

    def barrier(self):
        pass

    def bcast(self, value, root=0):
        assert root == 0
        return value


def test_energy_closure_failure_disqualifies_rta_files(tmp_path):
    port_path = tmp_path / "port_power.json"
    port_path.write_text(json.dumps({"R_total": 0.5, "T_total": 0.5}), encoding="utf-8")
    summary = {
        "official_result": True,
        "case_status": "completed",
        "energy_closure_error_port_volume": 2.0e-5,
    }

    _record_stage4_energy_closure_gate(
        tmp_path,
        _SerialComm(),
        summary,
        tolerance=1.0e-5,
    )

    saved_port = json.loads(port_path.read_text(encoding="utf-8"))
    assert summary["official_result"] is False
    assert summary["diagnostic_only"] is True
    assert summary["case_status"] == "failed_stage4_energy_closure"
    assert summary["stage4_energy_closure_gate_pass"] is False
    assert saved_port["official_result"] is False
    assert saved_port["qualification_status"] == "failed_stage4_energy_closure"


def test_energy_closure_cannot_qualify_another_failed_gate(tmp_path):
    port_path = tmp_path / "port_power.json"
    port_path.write_text(json.dumps({"R_total": 0.5, "T_total": 0.5}), encoding="utf-8")
    summary = {
        "official_result": False,
        "case_status": "failed_stage4_true_residual_gate",
        "energy_closure_error_port_volume": 0.0,
    }

    _record_stage4_energy_closure_gate(
        tmp_path,
        _SerialComm(),
        summary,
        tolerance=1.0e-5,
    )

    saved_port = json.loads(port_path.read_text(encoding="utf-8"))
    assert summary["stage4_energy_closure_gate_pass"] is True
    assert summary["official_result"] is False
    assert saved_port["official_result"] is False
    assert saved_port["qualification_status"] == "failed_stage4_true_residual_gate"


def test_energy_closure_root_read_error_fails_closed_collectively(tmp_path, monkeypatch):
    port_path = tmp_path / "port_power.json"
    port_path.write_text(json.dumps({"R_total": 0.5, "T_total": 0.5}), encoding="utf-8")
    summary = {
        "official_result": True,
        "case_status": "completed",
        "energy_closure_error_port_volume": 0.0,
    }
    original_read_text = Path.read_text

    def fail_port_read(path, *args, **kwargs):
        if path == port_path:
            raise PermissionError("injected read denial")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_port_read)
    _record_stage4_energy_closure_gate(
        tmp_path,
        _SerialComm(),
        summary,
        tolerance=1.0e-5,
    )

    assert summary["official_result"] is False
    assert summary["stage4_energy_closure_gate_pass"] is False
    assert summary["case_status"] == "failed_stage4_energy_closure_artifact_io"
    assert any("read failed" in item for item in summary["stage4_energy_closure_gate_io_errors"])
    assert "R/T/A energy-closure evidence could not be written" in (
        _stage4_authority_errors(
            summary,
            expected_residual_tolerance=1.0e-6,
            expected_energy_closure_tolerance=1.0e-5,
        )
    )


def test_energy_closure_root_write_error_fails_closed_collectively(tmp_path, monkeypatch):
    port_path = tmp_path / "port_power.json"
    port_path.write_text(json.dumps({"R_total": 0.5, "T_total": 0.5}), encoding="utf-8")
    summary = {
        "official_result": True,
        "case_status": "completed",
        "energy_closure_error_port_volume": 0.0,
    }
    original_write_text = Path.write_text

    def fail_port_write(path, *args, **kwargs):
        if path == port_path:
            raise PermissionError("injected write denial")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_port_write)
    _record_stage4_energy_closure_gate(
        tmp_path,
        _SerialComm(),
        summary,
        tolerance=1.0e-5,
    )

    assert summary["official_result"] is False
    assert summary["stage4_energy_closure_gate_pass"] is False
    assert summary["case_status"] == "failed_stage4_energy_closure_artifact_io"
    assert any("write failed" in item for item in summary["stage4_energy_closure_gate_io_errors"])


def test_direct_adapter_enforces_configured_residual_and_energy_limits():
    summary = {
        "case_status": "completed",
        "official_result": True,
        "linear_system_relative_residual": 9.0e-7,
        "stage4_true_residual_tolerance": 1.0e-6,
        "R_total": 0.2,
        "T_total": 0.3,
        "A_volume_total": 0.5,
        "energy_closure_error_port_volume": 0.0,
        "stage4_energy_closure_tolerance": 1.0e-5,
        "stage4_energy_closure_gate_pass": True,
    }
    assert _stage4_authority_errors(summary) == []

    failed_closure = {**summary, "energy_closure_error_port_volume": 2.0e-5}
    assert "R/T/A energy closure is outside the configured authority limit" in (
        _stage4_authority_errors(failed_closure)
    )


def test_direct_adapter_binds_gate_limits_to_resolved_input():
    summary = {
        "case_status": "completed",
        "official_result": True,
        "linear_system_relative_residual": 8.0e-4,
        "stage4_true_residual_tolerance": 1.0e-3,
        "stage4_true_residual_gate_pass": True,
        "R_total": 0.2,
        "T_total": 0.3,
        "A_volume_total": 0.5,
        "energy_closure_error_port_volume": 0.0,
        "stage4_energy_closure_tolerance": 1.0e-2,
        "stage4_energy_closure_gate_pass": True,
    }
    errors = _stage4_authority_errors(
        summary,
        expected_residual_tolerance=1.0e-6,
        expected_energy_closure_tolerance=1.0e-5,
    )
    assert "reported true-residual limit differs from resolved input" in errors
    assert "linear-system residual is outside the Full3D authority limit" in errors
    assert "reported energy-closure limit differs from resolved input" in errors


def test_native_runtime_identity_does_not_require_task44_root_and_overrides_stale_wsl(
    monkeypatch,
):
    monkeypatch.setenv("MYFENICS_NATIVE_COMPLEX_ENV", "1")
    monkeypatch.delenv("MYFENICS_TASK44_ROOT", raising=False)
    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
    monkeypatch.delenv("TASK40_V29_STRICT_FACTOR_ONLY", raising=False)

    identity = _environment_identity()

    assert identity["qualified_activation"] == "MYFENICS_NATIVE_COMPLEX_ENV=1"
    assert identity["runtime_profile"] == "native_linux_complex"
    assert identity["native_complex_identity"]["task_root"] is None
    assert identity["native_complex_identity"]["task44_runtime_controls"] is None


def test_task44_service_root_binding_accepts_only_its_real_worktree(tmp_path):
    root = Path(__file__).resolve().parents[2]
    verify_task44_root(
        root,
        {
            "MYFENICS_NATIVE_COMPLEX_ENV": "1",
            "MYFENICS_TASK44_ROOT": str(root),
        },
    )
    with pytest.raises(RuntimeError, match="does not identify this Task44 worktree"):
        verify_task44_root(
            root,
            {
                "MYFENICS_NATIVE_COMPLEX_ENV": "1",
                "MYFENICS_TASK44_ROOT": str(tmp_path),
            },
        )
    with pytest.raises(RuntimeError, match="stale WSL activation marker"):
        verify_task44_root(
            root,
            {
                "MYFENICS_NATIVE_COMPLEX_ENV": "1",
                "MYFENICS_TASK44_ROOT": str(root),
                "_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1",
            },
        )


def test_zero_timeout_is_reserved_for_explicit_layered_material_inputs(tmp_path):
    layered = load_and_resolve(Path("input/templates/full3d_layered_direct_example.dat"))
    assert layered.execution["timeout_seconds"] == 0
    assert len(layered.as_jsonable()["geometry"]["grating_layer_thicknesses_nm"]) == 6

    ordinary_text = Path("input/templates/full3d_direct_example.dat").read_text(encoding="utf-8")
    ordinary_text = ordinary_text.replace("timeout_seconds = 7200", "timeout_seconds = 0")
    ordinary_path = tmp_path / "ordinary-no-timeout.dat"
    ordinary_path.write_text(ordinary_text, encoding="utf-8")
    with pytest.raises(InputError, match="execution.timeout_seconds"):
        load_and_resolve(ordinary_path)


def test_condensed_sample_a_input_preserves_model_and_selects_exact_mumps():
    from src.io.input_validation import simulation_config_3d_from_normalized

    template = load_and_resolve(
        Path("input/templates/full3d_layered_direct_example.dat")
    )
    sample = load_and_resolve(
        Path("input/task44_sample_a_condensed_direct_v1.dat")
    )
    template_data = template.as_jsonable()
    sample_data = sample.as_jsonable()
    for section in (
        "geometry",
        "materials",
        "incidence",
        "boundary",
        "method",
        "execution",
        "output",
    ):
        assert sample_data[section] == template_data[section]
    template_discretization = dict(template_data["discretization"])
    sample_discretization = dict(sample_data["discretization"])
    assert sample_discretization.pop("assembly_backend") == (
        "assembly_time_static_condensed"
    )
    assert template_discretization.pop("assembly_backend") == "standard_full"
    assert sample_discretization == template_discretization
    assert sample_data["discretization"]["mesh_axis_cell_counts"] == [3, 6, 8]
    template_solver = dict(template_data["solver"])
    sample_solver = dict(sample_data["solver"])
    assert sample_solver.pop("direct_solver_profile") == "mumps_exact"
    assert template_solver.pop("direct_solver_profile") == "default"
    assert sample_solver == template_solver
    template_cfg = simulation_config_3d_from_normalized(template_data)
    sample_cfg = simulation_config_3d_from_normalized(sample_data)
    assert sample_cfg.nedelec_degree == template_cfg.nedelec_degree == 6
    assert sample_cfg.grating_layers == template_cfg.grating_layers
    assert sample_cfg.stage4_dtn_order_policy == template_cfg.stage4_dtn_order_policy
    assert sample_cfg.stage4_dtn_assembly == template_cfg.stage4_dtn_assembly
    assert sample_cfg.stage4_full3d_assembly_backend == "assembly_time_static_condensed"
    assert sample_cfg.petsc_direct_solver_profile_requested == "mumps_exact"
    assert sample_data["solver"]["linear_solver"] == "direct"
    assert sample_data["run_id"] != template_data["run_id"]


def test_six_layer_mesh_has_six_distinct_tags_and_exact_volumes(tmp_path):
    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem

    from src.common.modes_3d import outgoing_port_modes_3d
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.io.input_validation import (
        load_and_resolve,
        simulation_config_3d_from_normalized,
    )
    from src.postprocessing.diffraction_3d import (
        _power_orders_for_reporting,
        _probe_z_locations,
    )
    from src.postprocessing.rta_3d import compute_volume_absorption_3d
    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.hcurl_assembly_time_condensation import _cell_integral_kernels

    cases = {
        "A": (0.5, 0.5, 0.5, 0.5, 0.5, 0.5),
        "B": (0.75, 0.75, 0.75, 0.75, 0.75, 0.75),
        "C": (1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        "D": (0.5, 1.0, 0.5, 1.0, 0.5, 1.0),
    }
    sample_a = None
    for label, thicknesses in cases.items():
        case_path = _layered_input(tmp_path / f"sample-{label}.dat", label, thicknesses)
        resolved = load_and_resolve(case_path)
        cfg_case = simulation_config_3d_from_normalized(resolved.as_jsonable())
        mesh_case = build_airbox_mesh_3d(cfg_case, tmp_path / f"mesh-{label}")

        expected_height = sum(thicknesses)
        assert len(cfg_case.grating_layers) == 6
        assert len({layer.tag for layer in cfg_case.grating_layers}) == 6
        assert len({layer.refractive_index for layer in cfg_case.grating_layers}) == 3
        assert cfg_case.grating_height == expected_height
        assert cfg_case.physical_z_max == expected_height + 0.5
        assert cfg_case.z_min == -0.5
        assert mesh_case.mesh_cells_resolved[:2] == (3, 6)
        assert mesh_case.mesh_cells_resolved[2] >= 8
        assert np.prod(mesh_case.mesh_cells_resolved) == (
            mesh_case.mesh_cells_resolved[0]
            * mesh_case.mesh_cells_resolved[1]
            * mesh_case.mesh_cells_resolved[2]
        )
        if label == "A":
            assert mesh_case.mesh_cells_resolved == (3, 6, 8)
            assert np.prod(mesh_case.mesh_cells_resolved) == 144
        assert mesh_case.material_plane_alignment["all_aligned"] is True

        msh_case = mesh_case.mesh
        cells_case = np.arange(
            msh_case.topology.index_map(msh_case.topology.dim).size_local,
            dtype=np.int32,
        )
        cell_vertices_case = msh_case.geometry.x[msh_case.geometry.dofmap[cells_case]]
        cell_volumes_case = np.prod(np.ptp(cell_vertices_case, axis=1), axis=1)
        assert np.all(cell_volumes_case > 0.0)
        jacobian = np.stack(
            (
                cell_vertices_case[:, 1] - cell_vertices_case[:, 0],
                cell_vertices_case[:, 3] - cell_vertices_case[:, 0],
                cell_vertices_case[:, 4] - cell_vertices_case[:, 0],
            ),
            axis=2,
        )
        assert np.all(np.linalg.det(jacobian) > 0.0)
        tags_case = mesh_case.cell_tags.values
        assert len(tags_case) == len(cells_case)
        layer_tags = {layer.tag for layer in cfg_case.grating_layers}
        assert layer_tags <= set(map(int, tags_case))
        for layer in cfg_case.grating_layers:
            in_layer = tags_case == layer.tag
            assert int(np.count_nonzero(in_layer)) > 0
            assert np.all(
                (cell_vertices_case[in_layer, :, 0] >= cfg_case.grating_x_min - 1.0e-12)
                & (cell_vertices_case[in_layer, :, 0] <= cfg_case.grating_x_max + 1.0e-12)
                & (cell_vertices_case[in_layer, :, 1] >= cfg_case.grating_y_min - 1.0e-12)
                & (cell_vertices_case[in_layer, :, 1] <= cfg_case.grating_y_max + 1.0e-12)
            )
            assert np.isclose(
                float(cell_volumes_case[in_layer].sum()),
                cfg_case.grating_width_x * cfg_case.grating_width_y * layer.thickness,
                rtol=0.0,
                atol=1.0e-12,
            )

        coordinates = msh_case.geometry.x
        for axis, other_axes in ((0, (1, 2)), (1, (0, 2))):
            low = float(coordinates[:, axis].min())
            high = float(coordinates[:, axis].max())
            low_face = np.unique(
                np.round(coordinates[np.isclose(coordinates[:, axis], low)][:, other_axes], 12),
                axis=0,
            )
            high_face = np.unique(
                np.round(coordinates[np.isclose(coordinates[:, axis], high)][:, other_axes], 12),
                axis=0,
            )
            assert low_face.shape == high_face.shape
            assert np.allclose(low_face, high_face, rtol=0.0, atol=1.0e-12)

        top_probe, bottom_probe = _probe_z_locations(cfg_case)
        assert np.isclose(top_probe, expected_height + 0.375, atol=1.0e-12)
        assert np.isclose(bottom_probe, -0.375, atol=1.0e-12)
        assert cfg_case.grating_z_max < top_probe < cfg_case.physical_z_max
        assert cfg_case.physical_z_min < bottom_probe < cfg_case.interface_z
        assert cfg_case.stage4_dtn_order_policy == "auto_propagating"
        assert cfg_case.reporting_diffraction_order_max_m >= 7
        assert cfg_case.reporting_diffraction_order_max_n >= 7
        assert cfg_case.diffraction_sample_count_x >= 15
        assert cfg_case.diffraction_sample_count_y >= 15
        assert len(_power_orders_for_reporting(cfg_case)) == 15 * 15
        modes = outgoing_port_modes_3d(cfg_case)
        assert {mode.polarization for mode in modes} >= {"s", "p"}
        assert all(mode.propagating or (mode.m == 0 and mode.n == 0) for mode in modes)
        if label == "A":
            sample_a = (cfg_case, mesh_case)

    assert sample_a is not None
    cfg, mesh_data = sample_a
    msh = mesh_data.mesh
    space = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 1, dtype=default_real_type),
    )
    curl_form, material_form = _build_physical_volume_terms(
        cfg,
        ufl.TrialFunction(space),
        ufl.TestFunction(space),
        ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags),
    )
    def numeric_subdomain_ids(form):
        return {
            int(subdomain_id)
            for subdomain_id in (integral.subdomain_id() for integral in form.integrals())
            if isinstance(subdomain_id, int)
            or str(subdomain_id).lstrip("-").isdigit()
        }

    curl_tags = numeric_subdomain_ids(curl_form)
    material_tags = numeric_subdomain_ids(material_form)
    assert {layer.tag for layer in cfg.grating_layers} <= curl_tags
    assert {layer.tag for layer in cfg.grating_layers} <= material_tags

    # FFCx may combine the curl and mass terms into one kernel per integral
    # ID.  Condensation needs every required tagged kernel, not an arbitrary
    # minimum multiplicity such as the old >=2 expectation.
    combined_kernels = _cell_integral_kernels(
        fem.form(curl_form + material_form),
        sum_duplicate_cell_integrals=True,
    )
    assert set(cfg.physical_material_tags) <= set(combined_kernels)
    assert all(
        len(combined_kernels[tag]) >= 1
        for tag in cfg.physical_material_tags
    )
    assert cfg.stage4_full3d_assembly_backend == "standard_full"

    field = fem.Function(space)
    field.x.array[:] = 0.0
    field.x.scatter_forward()
    volume = compute_volume_absorption_3d(
        mesh_data,
        cfg,
        field,
        tmp_path / "volume-absorption",
        incident_power=1.0,
        port_metrics={"R_total": 0.25, "T_total": 0.75, "A_balance": 0.0},
    )
    assert set(volume["A_volume_grating_layers"]) == {
        f"grating_layer_{index}" for index in range(1, 7)
    }
    assert all(value == 0.0 for value in volume["A_volume_grating_layers"].values())
    assert volume["A_volume_total"] == 0.0
    assert volume["energy_closure_error_port_volume"] == 0.0

    constant_e = np.asarray(
        (1.0 + 0.5j, -0.25 + 0.75j, 2.0 - 0.125j), dtype=np.complex128
    )
    field.interpolate(
        lambda x: np.repeat(constant_e[:, np.newaxis], x.shape[1], axis=1)
    )
    field.x.scatter_forward()
    nonzero_volume = compute_volume_absorption_3d(
        mesh_data,
        cfg,
        field,
        tmp_path / "constant-field-volume-absorption",
        incident_power=1.0,
        port_metrics={"R_total": 0.25, "T_total": 0.75, "A_balance": 0.0},
    )
    field_norm_squared = float(np.vdot(constant_e, constant_e).real)
    for index, layer in enumerate(cfg.grating_layers, start=1):
        key = f"grating_layer_{index}"
        region = nonzero_volume["regions"][key]
        expected = (
            0.5
            * cfg.k0
            * layer.eps_r.imag
            * field_norm_squared
            * region["volume_nm3"]
        )
        actual = region["absorbed_power_code_units"]
        assert actual > 0.0
        assert np.isclose(actual, expected, rtol=1.0e-10, atol=1.0e-16)

    missing_last_tag = replace(cfg.grating_layers[-1], tag=999)
    missing_layer_cfg = replace(
        cfg,
        grating_layers=(*cfg.grating_layers[:-1], missing_last_tag),
    )
    incomplete_volume = compute_volume_absorption_3d(
        mesh_data,
        missing_layer_cfg,
        field,
        tmp_path / "incomplete-volume-absorption",
        incident_power=1.0,
        port_metrics={"R_total": 0.25, "T_total": 0.75, "A_balance": 0.0},
    )
    assert incomplete_volume["A_volume_grating_layers"]["grating_layer_6"] is None
    assert incomplete_volume["A_volume_grating"] is None
    assert incomplete_volume["A_volume_total"] is None
    assert incomplete_volume["energy_closure_error_port_volume"] is None


def test_layered_static_condensation_matches_uncondensed_direct_system(tmp_path):
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    if MPI.COMM_WORLD.size != 1:
        pytest.skip("the independent full Ax-f reference is a serial fixture")

    resolved = load_and_resolve(Path("input/templates/full3d_layered_direct_example.dat"))
    base = simulation_config_3d_from_normalized(resolved.as_jsonable())
    base.nedelec_degree = 2
    base.visualization_degree = 2
    base.case_name = "task44_layered_p2_direct_equivalence"
    base.matrix_diagnostics_assemble_unconstrained = False
    base.matrix_diagnostics_assemble_only = False
    base.matrix_diagnostics_factorization_only = False
    base.direct_release_base_after_augmentation = False
    base.direct_release_solver_before_postprocess = False
    base.unique_output = False

    # Keep Task44's six materials, geometry, wavelength, Floquet phases and
    # complete auto-propagating DtN inventory.  P2 keeps this direct pair small
    # while still providing cell-interior modes for the condensation path.
    mesh_data = build_airbox_mesh_3d(base, tmp_path / "shared-mesh")
    assert tuple(mesh_data.mesh_cells_resolved) == (3, 6, 8)
    assert int(np.prod(mesh_data.mesh_cells_resolved)) == 144
    expected_layer_tags = {layer.tag for layer in base.grating_layers}
    assert expected_layer_tags <= set(map(int, mesh_data.cell_tags.values))

    reference: dict[str, object] = {}
    captures: dict[str, dict[str, object]] = {}

    def observe(name: str, out_dir: Path):
        def _observer(
            *, field, config, floquet_data, summary, linear_system, dtn_result, **_
        ):
            with np.load(out_dir / summary["scientific_field_npz_file"]) as saved:
                captures[name] = {
                    "fe_coefficients": np.asarray(field.x.array).copy(),
                    "E_total_V_per_m": np.asarray(saved["E_total_V_per_m"]).copy(),
                    "H_curl_A_per_m": np.asarray(saved["H_curl_A_per_m"]).copy(),
                    "coordinates_nm": np.asarray(saved["coordinates_nm"]).copy(),
                    "summary": {
                        key: summary.get(key)
                        for key in (
                            "R_total",
                            "T_total",
                            "A_volume_total",
                            "A_volume_grating_layers",
                            "energy_closure_error_port_volume",
                            "linear_system_relative_residual",
                            "stage4_true_residual_tolerance",
                            "official_result",
                            "case_status",
                        )
                    },
                }
            if name == "uncondensed":
                matrix = linear_system["A"]
                rhs = linear_system["b"]
                assert matrix is not None and rhs is not None
                reference["matrix"] = matrix.copy()
                reference["rhs"] = rhs.duplicate()
                rhs.copy(reference["rhs"])
                info = dtn_result["solver_info"]
                reference["num_fem_dofs"] = int(info["num_original_fem_dofs"])
                reference["num_auxiliary_dofs"] = int(info["num_auxiliary_dofs"])
                assert matrix.getSize() == (
                    reference["num_fem_dofs"] + reference["num_auxiliary_dofs"],
                    reference["num_fem_dofs"] + reference["num_auxiliary_dofs"],
                )
            else:
                assert name == "condensed"
                reference_matrix = reference["matrix"]
                reference_rhs = reference["rhs"]
                num_fem = int(reference["num_fem_dofs"])
                num_aux = int(reference["num_auxiliary_dofs"])
                fe_vector = field.x.petsc_vec
                start, end = map(int, fe_vector.getOwnershipRange())
                assert (start, end) == (0, num_fem)
                full_solution = reference_rhs.duplicate()
                residual = reference_matrix.createVecLeft()
                try:
                    full_solution.set(PETSc.ScalarType(0.0))
                    fe_values = np.asarray(
                        fe_vector.getArray(readonly=True), dtype=np.complex128
                    ).copy()
                    # The physical Function contains Floquet-backsubstituted
                    # slave values.  The assembled MPC system's unknown vector
                    # keeps those rows at zero, so restore that algebraic form
                    # before applying its matrix.
                    slave_rows = np.asarray(
                        floquet_data.mpc.slaves, dtype=PETSc.IntType
                    )
                    assert np.all((0 <= slave_rows) & (slave_rows < num_fem))
                    fe_values[slave_rows] = PETSc.ScalarType(0.0)
                    full_solution.setValues(
                        np.arange(start, end, dtype=PETSc.IntType),
                        fe_values,
                        addv=PETSc.InsertMode.INSERT_VALUES,
                    )
                    auxiliary_values = np.asarray(
                        dtn_result["goal_context"]["auxiliary_values"],
                        dtype=np.complex128,
                    )
                    assert auxiliary_values.shape == (num_aux,)
                    full_solution.setValues(
                        np.arange(num_fem, num_fem + num_aux, dtype=PETSc.IntType),
                        auxiliary_values,
                        addv=PETSc.InsertMode.INSERT_VALUES,
                    )
                    full_solution.assemblyBegin()
                    full_solution.assemblyEnd()
                    reference_matrix.mult(full_solution, residual)
                    residual.axpy(PETSc.ScalarType(-1.0), reference_rhs)
                    rhs_norm = float(reference_rhs.norm())
                    captures[name]["independent_uncondensed_Ax_minus_f_relative"] = (
                        float(residual.norm()) / max(rhs_norm, 1.0e-30)
                    )
                finally:
                    residual.destroy()
                    full_solution.destroy()

        return _observer

    try:
        standard = replace(
            base,
            stage4_full3d_assembly_backend="standard_full",
        )
        standard_out = tmp_path / "standard-full"
        standard_summary = run_stage4b_block_grating_3d_case(
            standard,
            standard_out,
            solution_observer=observe("uncondensed", standard_out),
            mesh_data_override=mesh_data,
        )
        condensed = replace(
            base,
            stage4_full3d_assembly_backend="assembly_time_static_condensed",
        )
        condensed_out = tmp_path / "assembly-time-condensed"
        condensed_summary = run_stage4b_block_grating_3d_case(
            condensed,
            condensed_out,
            solution_observer=observe("condensed", condensed_out),
            mesh_data_override=mesh_data,
        )

        assert standard_summary["case_status"] == "completed"
        assert condensed_summary["case_status"] == "completed"
        assert condensed_summary["official_result"] is True
        assert (
            condensed_summary["stage4_full3d_assembly_backend_actual"]
            == "assembly_time_static_condensed"
        )
        condensed_audit = condensed_summary["cell_static_condensation"]
        recovery = condensed_audit["recovery"]
        assert recovery["status"] == "full_field_recovered_without_full_global_matrix"
        assert recovery["recovered_interior_rows"] > 0
        assert condensed_audit["full_global_matrix_allocated"] is False
        assert condensed_audit["sum_duplicate_cell_integrals"] is True
        assert condensed_audit["strict_local_checks"] is True
        assert condensed_audit["preserve_exact_geometry"] is True
        assert condensed_audit["dense_appended_block"] is True
        assert condensed_audit["identity_cache_readonly"] is True

        kernel_classes = condensed_audit["raw_tensor_classes"]
        assert condensed_audit["raw_tensor_class_count_global_unique"] == len(
            kernel_classes
        )
        assert condensed_audit["raw_tensor_cell_use_count_sum"] == 144
        kernel_invocations = condensed_audit[
            "cell_form_kernel_invocation_count_global_unique"
        ]
        assert kernel_invocations == sum(
            sum(int(value) for value in row["active_kernel_counts"].values())
            for row in kernel_classes
        )
        assert kernel_invocations > 0
        assert expected_layer_tags <= {
            int(row["material_tag"]) for row in kernel_classes
        }

        residual = captures["condensed"]["independent_uncondensed_Ax_minus_f_relative"]
        assert residual <= base.stage4_official_true_residual_tolerance
        for name, values in captures.items():
            result = values["summary"]
            assert result["case_status"] == "completed", name
            assert result["official_result"] is True, name
            assert abs(result["energy_closure_error_port_volume"]) <= (
                base.stage4_official_energy_closure_tolerance
            )
            assert result["linear_system_relative_residual"] <= (
                base.stage4_official_true_residual_tolerance
            )
            for key in ("R_total", "T_total", "A_volume_total"):
                assert result[key] is not None and np.isfinite(result[key]), (name, key)
            assert set(result["A_volume_grating_layers"]) == {
                f"grating_layer_{index}" for index in range(1, 7)
            }
        for key in ("E_total_V_per_m", "H_curl_A_per_m"):
            np.testing.assert_allclose(
                captures["condensed"][key],
                captures["uncondensed"][key],
                rtol=2.0e-6,
                atol=1.0e-10,
            )
        np.testing.assert_allclose(
            captures["condensed"]["fe_coefficients"],
            captures["uncondensed"]["fe_coefficients"],
            rtol=2.0e-6,
            atol=1.0e-10,
        )
        np.testing.assert_allclose(
            captures["condensed"]["coordinates_nm"],
            captures["uncondensed"]["coordinates_nm"],
            rtol=0.0,
            atol=0.0,
        )
        for key in ("R_total", "T_total", "A_volume_total"):
            np.testing.assert_allclose(
                captures["condensed"]["summary"][key],
                captures["uncondensed"]["summary"][key],
                rtol=1.0e-6,
                atol=1.0e-9,
            )
        for key in captures["condensed"]["summary"]["A_volume_grating_layers"]:
            np.testing.assert_allclose(
                captures["condensed"]["summary"]["A_volume_grating_layers"][key],
                captures["uncondensed"]["summary"]["A_volume_grating_layers"][key],
                rtol=1.0e-6,
                atol=1.0e-9,
            )
        standard_summary = captures["uncondensed"]["summary"]
        condensed_summary = captures["condensed"]["summary"]
        field_differences = {
            key: float(
                np.max(
                    np.abs(captures["condensed"][key] - captures["uncondensed"][key]),
                    initial=0.0,
                )
            )
            for key in (
                "fe_coefficients",
                "E_total_V_per_m",
                "H_curl_A_per_m",
            )
        }
        observable_differences = {
            key: abs(
                float(condensed_summary[key]) - float(standard_summary[key])
            )
            for key in ("R_total", "T_total", "A_volume_total")
        }
        layer_absorption_differences = {
            key: abs(
                float(condensed_summary["A_volume_grating_layers"][key])
                - float(standard_summary["A_volume_grating_layers"][key])
            )
            for key in standard_summary["A_volume_grating_layers"]
        }
        evidence = {
            "schema": "task44.p2_condensed_direct_equivalence.v1",
            "classification": "numerical_sanity_only",
            "mesh_cells": list(mesh_data.mesh_cells_resolved),
            "global_cell_count": 144,
            "backends": {
                "standard": "standard_full",
                "condensed": "assembly_time_static_condensed",
            },
            "official_result": {
                "standard": True,
                "condensed": True,
            },
            "true_residual": {
                "tolerance": float(base.stage4_official_true_residual_tolerance),
                "standard_reported_relative": float(
                    standard_summary["linear_system_relative_residual"]
                ),
                "condensed_reported_relative": float(
                    condensed_summary["linear_system_relative_residual"]
                ),
                "condensed_independent_standard_matrix_ax_minus_b_relative": float(
                    residual
                ),
                "mpc_slave_rows_zeroed_for_assembled_algebraic_vector": True,
            },
            "observables": {
                "standard": {
                    key: float(standard_summary[key])
                    for key in ("R_total", "T_total", "A_volume_total")
                },
                "condensed": {
                    key: float(condensed_summary[key])
                    for key in ("R_total", "T_total", "A_volume_total")
                },
                "absolute_differences": observable_differences,
                "max_layer_absorption_absolute_difference": max(
                    layer_absorption_differences.values(), default=0.0
                ),
            },
            "field_comparison_max_absolute_difference": field_differences,
            "condensation_cache_audit": {
                "unique_raw_tensor_classes": int(
                    condensed_audit["raw_tensor_class_count_global_unique"]
                ),
                "cell_uses": int(condensed_audit["raw_tensor_cell_use_count_sum"]),
                "cell_reuse_count": int(
                    condensed_audit["raw_tensor_cell_reuse_count_global"]
                ),
                "compiled_kernel_invocations_by_unique_class": int(
                    kernel_invocations
                ),
                "active_material_tags": sorted(
                    int(row["material_tag"]) for row in kernel_classes
                ),
                "kernel_invocation_count_type": "derived_from_kernel_map_and_unique_classes",
            },
        }
        (tmp_path / "paired_direct_equivalence_evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    finally:
        matrix = reference.get("matrix")
        rhs = reference.get("rhs")
        if matrix is not None:
            matrix.destroy()
        if rhs is not None:
            rhs.destroy()
