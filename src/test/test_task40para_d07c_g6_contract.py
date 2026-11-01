"""D07C G6 loader, finite-window, and live structured-mesh contract."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np

from src.geometry.mesh_builder_3d import build_airbox_mesh_3d, stage4_axis_plan
from src.geometry.task40_phi90_d07c_axis_plan import d07c_axis_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import native_profile_facts, validate_native_case
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _task40_d07c_mesh_evidence,
)
from src.runners.task038_input_worker import _task40_g6_runtime_cache_evidence
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

ROOT = Path(__file__).resolve().parents[2]
G6_INPUT = ROOT / "input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus64_to1_p6_direct.dat"
G5_INPUT = ROOT / "input/task40para_phi90_mesh_modes_direct/d07c_g5_m8_nminus64_to1_p6_direct.dat"
G6_PROFILE = "task40para_phi90_0p7_D07C_G6_M8_N64_p6_direct_v1"
N64_MODE_SHA = "e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0"
G6_TAGS = {"1": 6560, "2": 2400, "3": 640}


def _g6_resolved():
    specification = load_and_resolve(G6_INPUT)
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


def test_g6_loader_axis_plan_and_finite_mode_window():
    specification, resolved, profile, route, cfg = _g6_resolved()
    g5_resolved = load_and_resolve(G5_INPUT).as_jsonable()
    facts = native_profile_facts(profile)
    plan = d07c_axis_plan("G6")
    parent = d07c_axis_plan("G5")
    assert profile == G6_PROFILE
    assert resolved["output"]["export_fields"] is True
    assert resolved["output"]["export_modal_amplitudes"] is True
    assert resolved["output"]["export_reference_planes"] is True
    assert resolved["output"]["write_visualization_files"] is False
    # The G6 baseline is now a completed, preserved run; loading its contract
    # must continue to point at that same output parent without recreating it.
    assert specification.expected_output_parent.name == (
        f"{G6_PROFILE}__full3d_direct__mpi1__Mna"
    )
    for section in ("geometry", "materials", "incidence", "boundary", "method", "execution", "output"):
        assert resolved[section] == g5_resolved[section]
    assert resolved["solver"] == {
        **g5_resolved["solver"],
        "native_capacity_profile": G6_PROFILE,
    }
    changed_discretization = {
        "mesh_axis_cell_counts",
        "mesh_axis_y_values",
        "mesh_plan_id",
        "mesh_plan_sha256",
    }
    assert {
        key: value for key, value in resolved["discretization"].items()
        if key not in changed_discretization
    } == {
        key: value for key, value in g5_resolved["discretization"].items()
        if key not in changed_discretization
    }
    assert route["write_visualization_files"] is False
    assert route["surface_quadrature_degree"] == 81
    assert route["surface_quadrature_reference_degree"] == 161
    direct = facts["campaign_authorization"]["direct_route"]
    assert direct["volume_quadrature_degree"] == 15
    assert direct["volume_quadrature_rule"] == "default"
    assert route["sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert route["sparse_cutoff_relative_tolerance"] == 1e-13

    comparison = facts["component_options"]["directional_mesh_comparison"]
    assert comparison["parent_case"] == "G5"
    assert comparison["changed_axes"] == ["y"]
    assert comparison["mesh_comparison_reference_case"] == "G5_M8_N64"
    assert comparison["finite_window_context_reference_case"] == "G3_M8_N96"
    assert plan["parent_case"] == "G5"
    assert plan["segment_cell_counts"] == {
        "x": [2, 2, 2], "y": [60, 80, 60], "z": [2, 4, 2]
    }
    assert plan["axis_cell_counts"] == [6, 200, 8]
    assert plan["expected_global_cell_count"] == 9600
    assert plan["expected_material_tag_counts"] == G6_TAGS
    assert plan["axis_sha256_le_f64"]["x"] == parent["axis_sha256_le_f64"]["x"]
    assert plan["axis_sha256_le_f64"]["z"] == parent["axis_sha256_le_f64"]["z"]
    assert plan["axis_sha256_le_f64"]["y"] != parent["axis_sha256_le_f64"]["y"]
    y_steps = np.diff(np.asarray(plan["axes_nm"]["y"], dtype=np.float64))
    assert len(y_steps) == 200
    assert np.array_equal(y_steps, np.full(200, 0.25, dtype=np.float64))

    actual_plan = stage4_axis_plan(cfg, comm_size=1)
    actual_axes = {
        axis: tuple(float(value) for value in getattr(actual_plan, f"{axis}_values"))
        for axis in "xyz"
    }
    assert tuple(actual_plan.mesh_cells_resolved) == (6, 200, 8)
    assert actual_axes == {axis: tuple(plan["axes_nm"][axis]) for axis in "xyz"}
    modes, rows, mode_sha = build_dynamic_mode_inventory(cfg)
    assert len(modes) == len(rows) == 4488
    assert mode_sha == N64_MODE_SHA
    assert facts["component_options"]["mode_selection"]["expected_mode_sha256"] == N64_MODE_SHA
    assert sum(bool(mode.propagating) for mode in modes) == 4360
    assert sum(float(mode.power_per_unit_amplitude) > 0.0 for mode in modes) == 4426
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["resources"]["concurrent_neighbor_authorized"] is False
    assert facts["resources"]["parallel_admission_policy"] == "g6_scoped_observational_neighbors_v1"
    assert facts["native_execution"]["supervisor_cpu"] is None
    assert facts["native_execution"]["worker_cpus"] == []
    assert facts["native_execution"]["cpu_reservation_policy"] == (
        "sampled_low_load_distinct_physical_cores_v1"
    )
    assert specification.input_sha256
    validate_native_case(resolved)


def test_g6_live_mesh_axes_and_material_tags(tmp_path):
    _specification, _resolved, profile, route, cfg = _g6_resolved()
    levels = {
        "mesh_data": build_airbox_mesh_3d(cfg, tmp_path / "mesh")
    }
    evidence = _task40_d07c_mesh_evidence(levels, cfg, route)
    assert evidence["status"] == "PASS"
    assert evidence["parent_case"] == "G5"
    assert evidence["changed_axis"] == "y"
    assert evidence["axis_cell_counts"] == [6, 200, 8]
    assert evidence["actual_global_cell_count"] == 9600
    assert evidence["material_tag_counts"] == G6_TAGS
    assert evidence["axis_sha256_le_f64"] == d07c_axis_plan("G6")["axis_sha256_le_f64"]
    assert evidence["profile"] == profile
    suffixes = {path.suffix.lower() for path in (tmp_path / "mesh").iterdir()}
    assert {".vtu", ".vtk", ".vtx", ".pvd"}.isdisjoint(suffixes)


def test_g6_worker_runtime_cache_is_attempt_scoped_and_verified():
    attempt = f"g6cache{os.getpid()}"
    root = Path("/tmp") / f"task40_d07c_g6_attempt_{attempt}"
    paths = {
        "root": root,
        "tmp": root / "tmp",
        "xdg": root / "xdg",
        "pycache": root / "pycache",
        "mpl": root / "mpl",
    }
    try:
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        expected_environment = {
            "TMPDIR": str(paths["tmp"]),
            "TMP": str(paths["tmp"]),
            "TEMP": str(paths["tmp"]),
            "XDG_CACHE_HOME": str(paths["xdg"]),
            "PYTHONPYCACHEPREFIX": str(paths["pycache"]),
            "MPLCONFIGDIR": str(paths["mpl"]),
        }
        manifest = {
            "native_capacity_profile_identity": G6_PROFILE,
            "native_capacity_isolation": {
                "g6_observational_join": {"attempt_id": attempt},
            },
            "attempt_specific_runtime_cache": {
                **{key: str(value) for key, value in paths.items()},
                "owner": "G6_attempt_only",
            },
        }
        evidence = _task40_g6_runtime_cache_evidence(
            manifest,
            environment=expected_environment,
            jit_options_resolver=lambda: {"cache_dir": str(paths["xdg"] / "fenics")},
        )
        assert evidence["schema"] == "task40.d07c.g6_worker_cache_runtime.v1"
        assert evidence["cache_paths_verified_before_FE_dispatch"] is True
        assert evidence["dolfinx_jit_cache_dir"] == str(paths["xdg"] / "fenics")
    finally:
        shutil.rmtree(root, ignore_errors=True)
