"""D07C G5 mesh, mode, loader, and no-visualization output contract."""

from __future__ import annotations

import sys
from dataclasses import replace
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.geometry.mesh_builder_3d import stage4_axis_plan
from src.geometry.task40_phi90_d07c_axis_plan import d07c_axis_plan
from src.io.execution_plan import build_execution_plan
from src.io.input_loader import InputError, load_dat_input
from src.io.input_validation import (
    _plain,
    _validate_sections,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_PHI90_D07C_PROFILE_BY_CASE,
    native_profile_facts,
    validate_native_case,
)
from src.runners.p6_condensed_direct import (
    _direct_output_policy,
    _direct_run_contract,
)
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task40para_phi90_mesh_modes_direct"
G5_INPUT = INPUT_DIR / "d07c_g5_m8_nminus64_to1_p6_direct.dat"
N64_MODE_SHA = "e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0"
G5_TAGS = {"1": 5476, "2": 2004, "3": 536}
SOURCE_SHA = "d07c-g5-contract-test"


def _g5_resolved():
    specification = load_and_resolve(G5_INPUT)
    resolved = specification.as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    route = _direct_run_contract(profile)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(
        int(value) for value in route["signed_rectangle_bounds_mn"]
    )
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route[
        "mode_basis_scale_policy"
    ]
    return specification, resolved, profile, route, cfg


def test_g5_profile_loader_axes_modes_and_output_contract():
    _specification, resolved, profile, route, cfg = _g5_resolved()
    facts = native_profile_facts(profile)
    plan = d07c_axis_plan("G5")
    assert profile == "task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1"
    assert TASK40_PHI90_D07C_PROFILE_BY_CASE["G5_M8_N64"] == profile
    assert resolved["output"]["export_fields"] is True
    assert resolved["output"]["write_visualization_files"] is False
    assert resolved["output"]["export_reference_planes"] is True
    assert resolved["output"]["sample_count_y"] == 64
    assert route["write_visualization_files"] is False
    assert _direct_output_policy(route)["write_visualization_files"] is False
    assert facts["component_options"]["visualization_output_policy"] == {
        "write_visualization_files": False,
        "retained_field_samples": "full3d_reference_sample_npz",
        "field_recovery_and_energy_metrics": "unchanged",
        "visualization_files": "disabled_by_explicit_G5_profile",
    }
    comparison = facts["component_options"]["directional_mesh_comparison"]
    assert comparison["parent_case"] == "G3"
    assert comparison["mesh_comparison_reference_case"] == "G3_M8_N64"
    assert comparison["finite_window_context_reference_case"] == "G3_M8_N96"
    assert facts["component_options"]["mode_selection"][
        "mesh_comparison_reference_mode_sha256"
    ] == N64_MODE_SHA
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["resources"]["concurrent_neighbor_authorized"] is False

    assert plan["parent_case"] == "G3"
    assert plan["segment_cell_counts"] == {
        "x": [2, 2, 2], "y": [50, 67, 50], "z": [2, 4, 2]
    }
    assert plan["axis_cell_counts"] == [6, 167, 8]
    assert plan["expected_global_cell_count"] == 8016
    assert plan["expected_material_tag_counts"] == G5_TAGS
    assert plan["axis_sha256_le_f64"]["x"] == plan[
        "parent_axis_sha256_le_f64"
    ]["x"]
    assert plan["axis_sha256_le_f64"]["z"] == plan[
        "parent_axis_sha256_le_f64"
    ]["z"]
    assert plan["axis_sha256_le_f64"]["y"] != plan[
        "parent_axis_sha256_le_f64"
    ]["y"]
    y_steps = np.diff(np.asarray(plan["axes_nm"]["y"], dtype=np.float64))
    assert len(y_steps) == 167
    assert np.max(y_steps) <= 0.30000000000001
    assert np.min(y_steps) >= 0.2985074626865
    assert plan["static_geometry_only"]["axis_aligned_cell_jacobian_determinant_positive"]
    assert plan["static_geometry_only"]["maximum_cell_aspect_ratio"] > 100.0

    actual_plan = stage4_axis_plan(cfg, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual_plan, f"{axis}_values"))
        for axis in "xyz"
    }
    assert tuple(actual_plan.mesh_cells_resolved) == (6, 167, 8)
    assert actual_axes == {
        axis: tuple(plan["axes_nm"][axis]) for axis in "xyz"
    }
    modes, rows, mode_sha = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == 4488
    assert mode_sha == N64_MODE_SHA
    assert sum(bool(mode.propagating) for mode in modes) == 4360
    assert sum(float(mode.power_per_unit_amplitude) > 0.0 for mode in modes) == 4426

    legacy_spec = load_and_resolve(
        INPUT_DIR / "d07c_g3_m8_nminus64_to1_p6_direct.dat"
    )
    legacy_resolved = legacy_spec.as_jsonable()
    legacy_profile = legacy_resolved["solver"]["native_capacity_profile"]
    assert "write_visualization_files" not in legacy_resolved["output"]
    assert _direct_run_contract(legacy_profile)["write_visualization_files"] is True


def test_g5_real_manifest_worker_path_and_output_policy_drift_rejection(tmp_path):
    specification, _resolved, profile, _route, _cfg = _g5_resolved()
    run_dir = (tmp_path / "d07c-g5-run").resolve()
    run_dir.mkdir()
    specification = replace(specification, expected_output_parent=run_dir.parent)
    execution = build_execution_plan(
        specification,
        run_dir,
        source_sha=SOURCE_SHA,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
        worker_cpus_override=[17],
    )
    assert execution.argv[:8] == (
        "/usr/bin/mpiexec", "-n", "1", "/usr/bin/numactl",
        "--interleave=0,1", "/usr/bin/taskset", "-c", "17",
    )
    with pytest.raises(InputError, match="dynamic one-CPU reservation"):
        build_execution_plan(
            specification,
            run_dir,
            source_sha=SOURCE_SHA,
            python_executable=sys.executable,
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=[True],
        )
    legacy_spec = load_and_resolve(
        INPUT_DIR / "d07c_g3_m8_nminus64_to1_p6_direct.dat"
    )
    with pytest.raises(InputError, match="dynamic G5 worker CPUs cannot override another profile"):
        build_execution_plan(
            legacy_spec,
            run_dir,
            source_sha=SOURCE_SHA,
            python_executable=sys.executable,
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=[17],
        )
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_dir,
        source_sha=SOURCE_SHA,
        adapter_identity=execution.adapter_identity,
        start_time="2026-10-31T00:00:00Z",
    )
    loaded, errors = _load_and_validate_worker_payload(
        resolved_config=run_dir / "resolved_config.json",
        manifest=run_dir / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=execution.adapter_identity,
        expected_output_directory=run_dir,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )
    assert errors == []
    assert loaded["derived"]["native_capacity_profile"]["identity"] == profile
    direct = manifest["native_capacity_contract"]["direct_route"]
    assert direct["active_mode_count"] == 4488
    assert direct["write_visualization_files"] is False
    assert loaded["output"]["write_visualization_files"] is False

    parsed = _validate_sections(_plain(load_dat_input(G5_INPUT).document))
    bad_g5 = {**parsed, "output": {**parsed["output"], "write_visualization_files": True}}
    with pytest.raises(InputError, match="output.write_visualization_files"):
        validate_native_case(bad_g5)

    legacy_path = INPUT_DIR / "d07c_g3_m8_nminus64_to1_p6_direct.dat"
    legacy = _validate_sections(_plain(load_dat_input(legacy_path).document))
    bad_legacy = {
        **legacy,
        "output": {**legacy["output"], "write_visualization_files": False},
    }
    with pytest.raises(InputError, match="output.write_visualization_files"):
        validate_native_case(bad_legacy)


def test_g5_mesh_evidence_checks_all_frozen_axes_and_independent_midpoint_tags():
    plan = d07c_axis_plan("G5")
    _, _, profile, route, _ = _g5_resolved()
    mesh = SimpleNamespace(
        geometry=SimpleNamespace(
            x=np.asarray(
                list(product(plan["axes_nm"]["x"], plan["axes_nm"]["y"], plan["axes_nm"]["z"])),
                dtype=np.float64,
            )
        ),
        topology=SimpleNamespace(
            dim=3,
            index_map=lambda _dimension: SimpleNamespace(size_global=8016),
            cell_name=lambda: "hexahedron",
        ),
    )
    tags = []
    for z0, z1 in zip(plan["axes_nm"]["z"], plan["axes_nm"]["z"][1:]):
        zm = (z0 + z1) / 2.0
        for y0, y1 in zip(plan["axes_nm"]["y"], plan["axes_nm"]["y"][1:]):
            ym = (y0 + y1) / 2.0
            for x0, x1 in zip(plan["axes_nm"]["x"], plan["axes_nm"]["x"][1:]):
                xm = (x0 + x1) / 2.0
                tags.append(
                    2 if zm < 0.0 else
                    3 if zm < 120.0 and 16.5 < xm < 33.5 and 15.0 < ym < 35.0 else
                    1
                )
    levels = {
        "mesh_data": SimpleNamespace(
            mesh=mesh,
            cell_tags=SimpleNamespace(values=np.asarray(tags, dtype=np.int32)),
        )
    }
    cfg = SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3))
    from src.runners.p6_condensed_direct import _task40_d07c_mesh_evidence

    evidence = _task40_d07c_mesh_evidence(levels, cfg, route)
    assert evidence["status"] == "PASS"
    assert evidence["parent_case"] == "G3"
    assert evidence["axis_cell_counts"] == [6, 167, 8]
    assert evidence["actual_global_cell_count"] == 8016
    assert evidence["material_tag_counts"] == G5_TAGS
    assert evidence["axis_sha256_le_f64"] == plan["axis_sha256_le_f64"]
    assert native_profile_facts(profile)["component_options"][
        "directional_mesh_comparison"
    ]["expected_material_tag_counts"] == G5_TAGS

    bad_levels = {
        "mesh_data": SimpleNamespace(
            mesh=mesh,
            cell_tags=SimpleNamespace(
                values=np.asarray(tags[:-1] + [3 if tags[-1] != 3 else 1], dtype=np.int32)
            ),
        )
    }
    with pytest.raises(ValueError, match="material tags differ"):
        _task40_d07c_mesh_evidence(bad_levels, cfg, route)


class _FakeComm:
    size = 1
    rank = 0

    @staticmethod
    def allreduce(value, op=None):
        del op
        return value

    @staticmethod
    def barrier():
        return None


class _FakeGrid:
    def __init__(self, points):
        self.points = np.asarray(points, dtype=np.float64)
        self.n_points = len(self.points)
        self.n_cells = 1
        self.point_data = {}
        self.cell_data = {}
        self.field_data = {}

    def copy(self):
        return self

    def extract_cells(self, _cells):
        return self

    def save(self, _path):
        raise AssertionError("visualization files must not be written for G5")


def test_no_visualization_mode_keeps_reference_npz_and_writes_no_vtk(tmp_path, monkeypatch):
    from src.postprocessing import postprocess_3d as postprocess

    class _IndexMap:
        size_local = 1

    class _Topology:
        dim = 3

        @staticmethod
        def index_map(_dimension):
            return _IndexMap()

    mesh = SimpleNamespace(comm=_FakeComm(), topology=_Topology())

    class _DofMap:
        @staticmethod
        def cell_dofs(_cell):
            return np.asarray([0, 1], dtype=np.int32)

    vector_element = SimpleNamespace(interpolation_points=lambda: np.zeros((1, 3)))
    V_dg = SimpleNamespace(mesh=mesh, dofmap=_DofMap(), element=vector_element)

    class _FakeField:
        def __init__(self, _space, name=""):
            del _space
            self.name = name
            self.x = SimpleNamespace(
                array=np.zeros(6, dtype=np.complex128),
                scatter_forward=lambda: None,
            )

        def interpolate(self, _expression):
            if self.name == "H_A_per_m_from_curl":
                self.x.array[:] = np.asarray([0, 0, 1, 0, 0, 1], dtype=np.complex128)
            else:
                self.x.array[:] = np.asarray([1, 0, 0, 1, 0, 0], dtype=np.complex128)

    monkeypatch.setattr(postprocess.fem, "functionspace", lambda *_args: V_dg)
    monkeypatch.setattr(postprocess.fem, "Function", _FakeField)
    monkeypatch.setattr(postprocess.fem, "Expression", lambda expr, _pts: expr)
    monkeypatch.setattr(
        postprocess.ufl, "curl", lambda _field: np.asarray([0.0, 0.0, 1.0])
    )
    monkeypatch.setattr(
        postprocess,
        "_field_grid",
        lambda _space: (_FakeGrid([[0, 0, 10], [1, 1, 110]]), np.asarray([[0, 0, 10], [1, 1, 110]])),
    )

    def _write_sample_archive(_cfg, _electric, _magnetic, out_dir):
        sample = Path(out_dir) / "full3d_reference_samples.npz"
        np.savez_compressed(sample, E=np.asarray([1.0]), H=np.asarray([2.0]))
        return {"full3d_reference_archive": str(sample), "sample_status": "written"}

    monkeypatch.setattr(postprocess, "export_full3d_reference_samples", _write_sample_archive)
    monkeypatch.setattr(postprocess, "_field_component_l2_metrics", lambda *_: {})
    monkeypatch.setattr(
        postprocess.io,
        "VTXWriter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("VTX writer must not be constructed for G5")
        ),
        raising=False,
    )
    mesh_data = SimpleNamespace(
        mesh=mesh,
        cell_tags=SimpleNamespace(
            indices=np.asarray([0], dtype=np.int32),
            values=np.asarray([3], dtype=np.int32),
        ),
    )
    cfg = SimpleNamespace(
        visualization_degree=6,
        stage_case="stage4_block_grating",
        electric_field_scale_V_per_m=1.0,
        magnetic_field_scale_A_per_m=1.0,
        k0=1.0,
        mu_r=1.0,
        full3d_reference_export=True,
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
        domain_z_min=-10.0,
        domain_z_max=130.0,
        physical_z_min=0.0,
        physical_z_max=120.0,
        direction_vector=np.asarray([0.0, 0.0, 1.0]),
    )
    field = SimpleNamespace(x=SimpleNamespace(array=np.asarray([1.0 + 0.0j])))
    output = postprocess.save_airbox_3d_fields(
        mesh_data,
        cfg,
        field,
        tmp_path,
        write_visualization_files=False,
    )
    assert output["visualization_output_status"] == "disabled_by_profile"
    assert output["paraview_file"] is None
    assert output["vtx_3d_output_status"] == "disabled_by_profile"
    assert output["visualization_files_written"] == []
    sample = tmp_path / "full3d_reference_samples.npz"
    assert sample.is_file()
    assert np.load(sample).files == ["E", "H"]
    assert not list(tmp_path.glob("*.bp"))
    assert not list(tmp_path.glob("*.vtu"))
    assert not list(tmp_path.glob("*.pvd"))


def test_recover_p0_outputs_forwards_visualization_policy(tmp_path, monkeypatch):
    from src.common import modes_3d
    from src.postprocessing import diffraction_3d, postprocess_3d, rta_3d
    from src.solvers import dtn_port_3d, fullspace_same_mesh_hcurl_pmg_physical

    calls = []
    fake_field = SimpleNamespace(x=SimpleNamespace(array=np.asarray([1.0 + 0.0j])))
    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_physical,
        "restore_p0_full_field",
        lambda *_args, **_kwargs: fake_field,
    )
    monkeypatch.setattr(
        dtn_port_3d,
        "_port_power_metrics",
        lambda *_args, **_kwargs: {"power": 1.0},
    )

    def _save_fields(*_args, **kwargs):
        calls.append(kwargs["write_visualization_files"])
        return {"visualization_output_status": "disabled_by_profile"}

    monkeypatch.setattr(postprocess_3d, "save_airbox_3d_fields", _save_fields)
    monkeypatch.setattr(
        rta_3d,
        "compute_volume_absorption_3d",
        lambda *_args, **_kwargs: {
            "energy_closure_error_port_volume": 0.0,
        },
    )
    monkeypatch.setattr(
        diffraction_3d,
        "compute_diffraction_orders_3d",
        lambda *_args, **_kwargs: {"diffraction_channel_count": 1},
    )
    monkeypatch.setattr(modes_3d, "incident_power_3d", lambda _cfg: 1.0)
    bundle = {
        "setup": {"floquets": [None] * 7, "mesh_data": object()},
        "dtn_action": SimpleNamespace(
            recover_auxiliary=lambda _solution: np.asarray([1.0 + 0.0j])
        ),
        "modes": [object()],
        "incident_projections": [0.0],
        "cfg": object(),
    }
    result = fullspace_same_mesh_hcurl_pmg_physical.recover_p0_outputs(
        bundle,
        object(),
        tmp_path,
        write_visualization_files=False,
    )
    assert calls == [False]
    assert result["field_export"]["visualization_output_status"] == "disabled_by_profile"
