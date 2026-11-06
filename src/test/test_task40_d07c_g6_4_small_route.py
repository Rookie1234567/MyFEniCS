"""Contract checks for the coarse G6_4 small case; no FE solve is performed."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise
from math import isclose
from pathlib import Path

import pytest

from src.geometry.task40_phi90_d07c_axis_plan import d07c_axis_plan
from src.io.input_loader import InputError
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    native_profile_facts,
    numeric_factor_blas_thread_choices,
    validate_native_case,
)
from src.runners.p6_condensed_direct import _direct_run_contract
from src.runners import task40_d07c_g5_join as d07c_join
from src.runners.task038_launcher import _validate_numeric_factor_cpu_reservation
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory


ROOT = Path(__file__).resolve().parents[2]
INPUT = (
    ROOT
    / "input/task40para_phi90_mesh_modes_direct/"
    "d07c_g6_4_m2_nminus2_to1_p6_direct.dat"
)
G6_N14_INPUT = (
    ROOT
    / "input/task40para_phi90_mesh_modes_direct/"
    "d07c_g6_m8_nminus14_to1_p6_direct.dat"
)
PROFILE = "task40para_phi90_0p7_D07C_G6_4_M2_N2_p6_direct_v1"
EXPECTED_MODE_SHA = "2bede60faefca7e1d30c1d2e89edfe98aa653e1b4e1e77ee4c3f2ce5185cb426"


def test_g6_4_axis_plan_preserves_g6_xz_and_exact_material_volumes():
    plan = d07c_axis_plan("G6_4")
    g6 = d07c_axis_plan("G6")
    assert plan["parent_case"] == "G6"
    assert plan["changed_axis"] == "y"
    assert plan["segment_cell_counts"] == {
        "x": [2, 2, 2],
        "y": [2, 2, 2],
        "z": [2, 4, 2],
    }
    assert plan["axis_cell_counts"] == [6, 6, 8]
    assert plan["expected_global_cell_count"] == 288
    assert plan["axes_nm"]["x"] == g6["axes_nm"]["x"]
    assert plan["axes_nm"]["z"] == g6["axes_nm"]["z"]
    assert plan["axes_nm"]["y"] == [0.0, 7.5, 15.0, 25.0, 35.0, 42.5, 50.0]
    assert plan["expected_material_tag_counts"] == {
        "1": 200,
        "2": 72,
        "3": 16,
    }

    # Independently classify cell centers and accumulate exact axis-aligned
    # volumes, rather than trusting the planner's cached material counts.
    cells_by_tag: Counter[str] = Counter()
    volume_by_tag: Counter[str] = Counter()
    axes = plan["axes_nm"]
    for x0, x1 in pairwise(axes["x"]):
        xc = (x0 + x1) / 2.0
        for y0, y1 in pairwise(axes["y"]):
            yc = (y0 + y1) / 2.0
            for z0, z1 in pairwise(axes["z"]):
                zc = (z0 + z1) / 2.0
                tag = (
                    "2"
                    if zc < 0.0
                    else "3"
                    if zc < 120.0 and 16.5 < xc < 33.5 and 15.0 < yc < 35.0
                    else "1"
                )
                cells_by_tag[tag] += 1
                volume_by_tag[tag] += (x1 - x0) * (y1 - y0) * (z1 - z0)
    assert dict(cells_by_tag) == {"1": 200, "2": 72, "3": 16}
    expected_volume = {"1": 284_200.0, "2": 25_000.0, "3": 40_800.0}
    for tag, volume in expected_volume.items():
        assert isclose(volume_by_tag[tag], volume, rel_tol=0.0, abs_tol=1e-9)
    assert sum(volume_by_tag.values()) == 50.0 * 50.0 * 140.0


def test_g6_4_input_route_and_production_inventory_are_exact():
    spec = load_and_resolve(INPUT)
    resolved = spec.as_jsonable()
    original = load_and_resolve(G6_N14_INPUT).as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    assert profile == PROFILE
    assert spec.identity.get("run_id") == PROFILE
    for section in ("geometry", "materials", "incidence", "boundary", "method", "execution"):
        assert resolved[section] == original[section]
    assert resolved["solver"] == {
        **original["solver"],
        "native_capacity_profile": PROFILE,
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
        key: value for key, value in original["discretization"].items()
        if key not in changed_discretization
    }
    validate_native_case(resolved)

    facts = native_profile_facts(PROFILE)
    route = _direct_run_contract(PROFILE)
    mode = facts["component_options"]["mode_selection"]
    assert facts["component_options"]["directional_mesh_comparison"]["case"] == "G6_4"
    assert facts["component_options"]["expected_global_cell_count"] == 288
    assert facts["component_options"]["surface_quadrature"]["degree"] == 81
    assert facts["campaign_authorization"]["direct_route"]["volume_quadrature_degree"] == 15
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert mode["policy"] == "explicit_signed_rectangle_v1"
    assert mode["parent_signed_bounds_mn"] == [-2, 2, -2, 1]
    assert mode["active_signed_bounds_mn"] == [-2, 2, -2, 1]
    assert mode["expected_mode_count"] == 80
    assert mode["expected_mode_sha256"] == EXPECTED_MODE_SHA
    assert mode["expected_active_propagating_count"] == 48
    assert mode["expected_active_power_carrying_count"] == 66
    assert route["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert route["active_count"] == 80
    assert route["write_visualization_files"] is False

    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(route["signed_rectangle_bounds_mn"])
    cfg.stage4_dtn_quadrature_degree = route["surface_quadrature_degree"]
    cfg.task40_port_boundary_amplitude_scale_policy = route["mode_basis_scale_policy"]
    modes, manifest, mode_sha = build_dynamic_mode_inventory(cfg)
    signed_keys = {
        (mode.side, int(mode.m), int(mode.n), mode.polarization) for mode in modes
    }
    expected_keys = {
        (side, m, n, polarization)
        for side in ("top", "bottom")
        for polarization in ("s", "p")
        for m in range(-2, 3)
        for n in range(-2, 2)
    }
    assert len(modes) == len(manifest) == 80
    assert signed_keys == expected_keys
    assert mode_sha == EXPECTED_MODE_SHA
    counts = Counter(f"{mode.side}_{mode.polarization}" for mode in modes)
    assert counts == {
        "top_s": 20,
        "top_p": 20,
        "bottom_s": 20,
        "bottom_p": 20,
    }
    assert sum(bool(mode.propagating) for mode in modes) == 48
    assert sum(float(mode.power_per_unit_amplitude) > 0.0 for mode in modes) == 66


def test_g6_4_blas_thread_choices_and_socket_reservations(monkeypatch):
    assert numeric_factor_blas_thread_choices(PROFILE) == {1, 8, 16, 24, 32}
    assert numeric_factor_blas_thread_choices(
        "task40para_phi90_0p7_D07C_G6_M8_N14_p6_direct_v1"
    ) == {1, 8}
    assert numeric_factor_blas_thread_choices("unrelated-profile") == frozenset()

    monkeypatch.setattr(d07c_join.os, "sched_getaffinity", lambda _pid: set(range(48)))
    monkeypatch.setattr(
        d07c_join, "_observe_process_affinities",
        lambda _proc_root: {"processes": [], "unreadable_process_count": 0},
    )
    monkeypatch.setattr(d07c_join, "_core", lambda cpu: (cpu // 24, cpu % 24))
    monkeypatch.setattr(d07c_join, "_siblings", lambda cpu: [cpu])
    monkeypatch.setattr(d07c_join.time, "sleep", lambda _seconds: None)
    snapshots = iter((
        {cpu: (0, 0) for cpu in range(48)},
        {cpu: (10, 10) for cpu in range(48)},
        {cpu: (0, 0) for cpu in range(48)},
        {cpu: (10, 10) for cpu in range(48)},
        {cpu: (0, 0) for cpu in range(48)},
        {cpu: (10, 10) for cpu in range(48)},
    ))
    monkeypatch.setattr(d07c_join, "_cpu_ticks", lambda _proc_root: next(snapshots))

    single = d07c_join.choose_g6_cpu_reservation(
        sample_seconds=0,
        worker_cpu_count=24,
        socket_policy="single_socket",
    )
    single_packages = {
        row["package"] for row in single["selected_topology"][1:]
    }
    assert len(single["worker_cpus"]) == 24
    assert len(single_packages) == 1
    assert single["supervisor_cpu"] not in single["worker_cpus"]

    cross = d07c_join.choose_g6_cpu_reservation(
        sample_seconds=0,
        worker_cpu_count=32,
        socket_policy="balanced_cross_socket",
    )
    cross_counts = Counter(row["package"] for row in cross["selected_topology"][1:])
    assert len(cross["worker_cpus"]) == 32
    assert cross_counts == {0: 16, 1: 16}
    assert cross["supervisor_cpu"] not in cross["worker_cpus"]

    isolation = {
        "supervisor_cpu": cross["supervisor_cpu"],
        "worker_affinity": cross["worker_cpus"],
        "sampled_cpu_reservation": cross,
    }
    monkeypatch.setattr(
        d07c_join.os,
        "sched_getaffinity",
        lambda _pid: {cross["supervisor_cpu"]},
    )
    assert _validate_numeric_factor_cpu_reservation(
        PROFILE, 32, isolation
    ) == cross["worker_cpus"]
    with pytest.raises(InputError, match="differs from its physical-core reservation"):
        _validate_numeric_factor_cpu_reservation(PROFILE, 24, isolation)
    with pytest.raises(InputError, match="reviewed physical-core reservation"):
        _validate_numeric_factor_cpu_reservation(PROFILE, None, None)

    monkeypatch.setattr(d07c_join.os, "sched_getaffinity", lambda _pid: set(range(48)))
    default = d07c_join.choose_g6_cpu_reservation(
        sample_seconds=0,
        worker_cpu_count=1,
        socket_policy="single_socket",
    )
    default_isolation = {
        "supervisor_cpu": default["supervisor_cpu"],
        "worker_affinity": default["worker_cpus"],
        "sampled_cpu_reservation": default,
    }
    monkeypatch.setattr(
        d07c_join.os,
        "sched_getaffinity",
        lambda _pid: {default["supervisor_cpu"]},
    )
    assert _validate_numeric_factor_cpu_reservation(
        PROFILE, None, default_isolation
    ) == default["worker_cpus"]
