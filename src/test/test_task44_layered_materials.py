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
