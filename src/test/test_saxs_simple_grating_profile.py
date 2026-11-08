from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    SAXS_SIMPLE_GRATING_P6_DIRECT_CX_PROFILE,
    SAXS_SIMPLE_GRATING_P6_DIRECT_CZ_PROFILE,
    SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE,
    TASK40_PHI90_D07C_G6_M8_N14_PROFILE,
    native_profile_facts,
    numeric_factor_blas_thread_choices,
)
from src.runners.p6_condensed_direct import _direct_run_contract
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import (
    _validate_numeric_factor_cpu_reservation,
    _write_bootstrap,
    _write_json,
)
from src.runners.p6_condensed_direct import _preflight_task40_mode_inventories
from src.runners import native_capacity, reviewed_workstation_admission


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/saxs_simple_grating_center_p6_direct.dat"
SOURCE_SHA = "a5c8" * 10
WORKER_CPUS = list(range(16, 24))


def _bootstrap_roundtrip(tmp_path, input_path=INPUT):
    specification = load_and_resolve(input_path)
    run_directory = (tmp_path / f"{input_path.stem}-run").resolve()
    run_directory.mkdir()
    specification = replace(
        specification,
        expected_output_parent=run_directory.parent,
    )
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
        worker_cpus_override=WORKER_CPUS,
    )
    manifest, resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=SOURCE_SHA,
        adapter_identity=plan.adapter_identity,
        start_time="2026-11-08T00:00:00Z",
    )
    manifest["numeric_factor_blas_threads"] = 8
    manifest["numeric_factor_blas_scope"] = "MUMPS_numeric_factorization_only"
    manifest["native_capacity_isolation"] = {"worker_affinity": WORKER_CPUS}
    manifest["worker_command"] = list(plan.argv)
    _write_json(run_directory / "run_manifest.json", manifest)
    return specification, run_directory, resolved_sha, plan, manifest


def _validate_worker(specification, run_directory, resolved_sha, plan):
    return _load_and_validate_worker_payload(
        resolved_config=run_directory / "resolved_config.json",
        manifest=run_directory / "run_manifest.json",
        expected_input_sha256=specification.input_sha256,
        expected_physical_model_sha256=specification.physical_model_sha256,
        expected_source_sha=SOURCE_SHA,
        expected_mpi_size=1,
        expected_method="full3d_direct",
        expected_adapter=plan.adapter_identity,
        expected_output_directory=run_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )


def test_center_profile_has_independent_physics_modes_and_preserves_old_g6():
    specification = load_and_resolve(INPUT).as_jsonable()
    facts = native_profile_facts(SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE)
    old_g6 = native_profile_facts(TASK40_PHI90_D07C_G6_M8_N14_PROFILE)
    modes = facts["component_options"]["mode_selection"]

    assert specification["model_id"] == "si_block_saxs_0p7135_50x50_17x20_h120"
    assert specification["incidence"] == {
        "wavelength_nm": 0.7135227949132827,
        "grazing_angle_deg": 0.9,
        "azimuth_deg": 84.0,
        "polarization": "s",
        "electric_amplitude": 1.0,
    }
    assert facts["physical_comparison_family"] == "saxs_simple_grating_center"
    assert facts["component_options"]["directional_mesh_comparison"][
        "axis_grid_reuse_scope"
    ] == "mesh_coordinates_only"
    assert modes["parent_signed_bounds_mn"] == [-8, 8, -64, 1]
    assert modes["active_signed_bounds_mn"] == [-8, 8, -14, 1]
    assert modes["expected_mode_count"] == 4488
    assert modes["expected_active_mode_count"] == 1088
    assert modes["expected_mode_sha256"] == (
        "1d612391c6d662f28a9579428e6e276ce5bbe8345eee159773a01d6739fc0f0c"
    )
    assert modes["expected_active_mode_sha256"] == (
        "cf26a40d59727fd7bbcaab83ed80427859acb405b1e66a869a75e57b276d896a"
    )
    assert (modes["expected_parent_propagating_count"], modes[
        "expected_parent_power_carrying_count"
    ]) == (4378, 4434)
    assert (modes["expected_active_propagating_count"], modes[
        "expected_active_power_carrying_count"
    ]) == (978, 1034)
    assert old_g6["wavelength_nm"] == 0.7
    assert old_g6["component_options"]["mode_selection"][
        "expected_active_mode_sha256"
    ] == (
        "8d7eda75f7bb3476fc2363231c6dde8ff6bdd225876cb41a4112c21a4799b158"
    )
    assert numeric_factor_blas_thread_choices(SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE) == {
        1, 8
    }
    comparison = facts["component_options"]["directional_mesh_comparison"]
    assert comparison["same_mesh_modal_reference_mode_sha256"] is None
    assert comparison["finite_window_context_reference_case"] is None
    assert comparison["parent_case_scope"] == "mesh_axes_only"
    quadrature = facts["component_options"]["surface_quadrature"]
    assert quadrature["verified_max_scaled_functional_error"] is None
    assert "not revalidated" in quadrature["authority"]
    assert facts["diagnostic_scope"].startswith("SAXS center:")
    assert facts["condensed_route"]["omitted_auto_propagating_mode_count"] is None
    direct = facts["campaign_authorization"]["direct_route"]
    assert direct["parent_mode_rectangle_max_abs_m_n"] == [8, 64]
    assert direct["active_mode_rectangle_max_abs_m_n"] == [8, 14]


def test_one_axis_candidates_load_with_additive_profiles_and_keep_center_baseline():
    from src.geometry.saxs_simple_grating_axis_plan import saxs_one_axis_plan

    candidates = (
        (
            "x",
            ROOT / "input/saxs_simple_grating_center_cx_p6_direct.dat",
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX_PROFILE,
        ),
        (
            "z",
            ROOT / "input/saxs_simple_grating_center_cz_p6_direct.dat",
            SAXS_SIMPLE_GRATING_P6_DIRECT_CZ_PROFILE,
        ),
    )
    original = native_profile_facts(SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE)
    original_comparison = original["component_options"][
        "directional_mesh_comparison"
    ]
    original_resolved = load_and_resolve(INPUT).as_jsonable()

    for axis, path, identity in candidates:
        plan = saxs_one_axis_plan(axis)
        resolved = load_and_resolve(path).as_jsonable()
        facts = native_profile_facts(identity)
        comparison = facts["component_options"]["directional_mesh_comparison"]
        direct = facts["campaign_authorization"]["direct_route"]
        route = _direct_run_contract(identity)

        assert resolved["solver"]["native_capacity_profile"] == identity
        assert resolved["run_id"].endswith(f"_c{axis}_v1")
        assert resolved["discretization"]["mesh_axis_cell_counts"] == plan[
            "axis_cell_counts"
        ]
        assert {
            key: resolved["discretization"][f"mesh_axis_{key}_values"]
            for key in "xyz"
        } == plan["axes_nm"]
        assert resolved["discretization"]["mesh_plan_id"] == plan["mesh_plan_id"]
        assert resolved["discretization"]["mesh_plan_sha256"] == plan[
            "mesh_plan_sha256"
        ]
        assert resolved["derived"]["native_capacity_profile"] == facts
        assert comparison["case"] == plan["case"]
        assert comparison["parent_case"] == "SAXS_G6_BASELINE"
        assert comparison["changed_axis"] == axis
        assert comparison["changed_axes"] == [axis]
        assert comparison["changed_axes_vs_d07c_b"] == plan[
            "changed_axes_vs_d07c_b"
        ]
        assert comparison["expected_axis_sha256_le_f64"] == plan[
            "axis_sha256_le_f64"
        ]
        assert comparison["static_condensed_rows"] == plan["static_condensed_rows"]
        assert facts["component_options"]["mode_selection"] == original[
            "component_options"
        ]["mode_selection"]
        assert facts["component_options"]["surface_quadrature"]["degree"] == 81
        assert facts["component_options"]["volume_quadrature"]["degree"] == 15
        assert facts["condensed_route"]["name"] == original["condensed_route"]["name"]
        assert numeric_factor_blas_thread_choices(identity) == {1, 8}
        assert direct["mesh_plan_id"] == plan["mesh_plan_id"]
        assert direct["static_condensed_rows"] == plan["static_condensed_rows"]
        assert route["family"] == "task40_phi90"
        assert route["comparison_family"] == "saxs_simple_grating_center"
        assert route["task40_mesh_plan_family"] == "saxs_one_axis"
        assert route["task40_mesh_case"] == plan["case"]
        assert route["task40_changed_axes"] == [axis]
        assert route["task40_changed_axes_vs_d07c_b"] == plan[
            "changed_axes_vs_d07c_b"
        ]
        assert route["d13_case"] is None
        assert route["parent_count"] == 4488
        assert route["active_count"] == 1088
        assert route["surface_quadrature_degree"] == 81
        assert route["direct_factor_evidence"]["mode_keys"] == [
            [side, m, 0, pol]
            for side in ("top", "bottom")
            for m, pol in ((-8, "p"), (0, "s"), (8, "p"))
        ]

    # Candidate fact construction must not mutate the already published SAXS baseline.
    baseline_after = native_profile_facts(SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE)
    assert baseline_after == original
    assert original_resolved["solver"]["native_capacity_profile"] == (
        SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE
    )
    assert original_resolved["discretization"]["mesh_axis_cell_counts"] == [6, 200, 8]
    assert original_comparison["axis_grid_reuse_scope"] == "mesh_coordinates_only"
    assert original_resolved["discretization"]["mesh_plan_id"] == (
        original_comparison["mesh_plan_id"]
    )


def test_center_live_inventory_preflight_uses_runner_boundary_scaling():
    specification = load_and_resolve(INPUT)
    resolved = specification.as_jsonable()
    route = _direct_run_contract(SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(
        int(value) for value in route["parent_signed_bounds_mn"]
    )
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route[
        "mode_basis_scale_policy"
    ]

    preflight = _preflight_task40_mode_inventories(cfg, route)

    assert route["mode_basis_scale_policy"] == "boundary_magnitude_scaled_r5_v1"
    assert route["parent_sha256"] == (
        "1d612391c6d662f28a9579428e6e276ce5bbe8345eee159773a01d6739fc0f0c"
    )
    assert route["active_sha256"] == (
        "cf26a40d59727fd7bbcaab83ed80427859acb405b1e66a869a75e57b276d896a"
    )
    assert route["parent_count"] == len(preflight["parent_inventory"][0]) == 4488
    assert route["active_count"] == len(preflight["active_inventory"][0]) == 1088
    assert preflight["parent_propagating_count"] == 4378
    assert preflight["parent_power_carrying_count"] == 4434
    assert preflight["active_propagating_count"] == 978
    assert preflight["active_power_carrying_count"] == 1034


@pytest.mark.parametrize(
    "profile_identity",
    [
        pytest.param(SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE, id="baseline"),
        pytest.param(SAXS_SIMPLE_GRATING_P6_DIRECT_CX_PROFILE, id="cx"),
        pytest.param(SAXS_SIMPLE_GRATING_P6_DIRECT_CZ_PROFILE, id="cz"),
    ],
)
def test_center_native_guard_uses_sampled_one_socket_reservation(
    monkeypatch, tmp_path, profile_identity
):
    from src.runners import task40_d07c_g5_join

    reservation = {
        "policy": "sampled_low_load_distinct_physical_cores_v1",
        "socket_policy": "single_socket",
        "sample_seconds": 0.0,
        "supervisor_cpu": 8,
        "worker_cpu": 0,
        "worker_cpus": list(range(8)),
        "worker_cpu_count": 8,
        "selected_topology": [
            {"cpu": cpu, "package": 0, "core": cpu}
            for cpu in [8, *range(8)]
        ],
        "candidate_topology_and_load": [],
        "allowed_affinity_at_selection": list(range(9)),
        "observed_heavy_neighbor_cores": [],
        "heavy_neighbor_affinity_avoidance": "preferred_when_possible_busy_fallback_allowed",
        "exclusive_cpu_ownership": False,
        "neighbor_observation": {"processes_modified": False},
    }
    admission_calls = []

    @contextmanager
    def fake_lock(*_args, **_kwargs):
        yield object(), tmp_path / "native-capacity-heavy.lock", tmp_path / "task-repository.git", None

    monkeypatch.setenv("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION", "1")
    for name in (
        "PHYSICAL_NATIVE_CAPACITY", "PHYSICAL_NATIVE_NODE_CAP_BYTES",
        "OMPI_MCA_hwloc_base_binding_policy",
    ):
        monkeypatch.setenv(name, "test-original")
    monkeypatch.setattr(native_capacity, "_native_capacity_launch_lock", fake_lock)
    monkeypatch.setattr(native_capacity, "_launch_swap_snapshot", lambda: {"snapshot": "test"})
    monkeypatch.setattr(native_capacity, "_validate_preexisting_swap", lambda *_a, **_k: "observe_only")
    monkeypatch.setattr(native_capacity, "_cpu_launch_snapshot", lambda cpus: {"cpus": sorted(cpus)})
    monkeypatch.setattr(native_capacity.os, "sched_setaffinity", lambda *_a: None)
    monkeypatch.setattr(native_capacity.os, "sched_getaffinity", lambda _pid: {8})
    monkeypatch.setattr(native_capacity.os, "statvfs", lambda _path: SimpleNamespace(f_favail=7))
    monkeypatch.setattr(
        native_capacity.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=1234),
    )
    monkeypatch.setattr(
        task40_d07c_g5_join,
        "choose_sampled_cpu_reservation",
        lambda **kwargs: (admission_calls.append(("cpu", kwargs)) or reservation),
    )

    def fake_admission(resources, worker_cpus, **kwargs):
        admission_calls.append(("memory", resources, list(worker_cpus), kwargs))
        return {"policy": "interleave_nodes0_1", "neighbors_modified": False}

    monkeypatch.setattr(
        reviewed_workstation_admission,
        "task40_host_floor_interleaved_admission",
        fake_admission,
    )

    with native_capacity.native_capacity_guard(
        profile_identity,
        memory_policy="interleave_nodes0_1",
        numeric_factor_blas_threads=8,
    ) as (_root, isolation):
        assert isolation["sampled_cpu_reservation"] == reservation
        assert isolation["supervisor_cpu"] == 8
        assert isolation["supervisor_affinity"] == [8]
        assert isolation["worker_affinity"] == list(range(8))
        assert isolation["native_capacity_lock_scope"] == (
            "saxs_center_shared_task40_host_heavy_lock"
        )
        assert isolation["g6_observational_join"] is None
        assert isolation["node_memory_admission"]["policy"] == "interleave_nodes0_1"
        assert _validate_numeric_factor_cpu_reservation(
            profile_identity,
            8,
            isolation,
        ) == list(range(8))

    assert admission_calls[0] == (
        "cpu",
        {"worker_cpu_count": 8, "socket_policy": "single_socket"},
    )
    assert admission_calls[1][0] == "memory"
    assert admission_calls[1][2] == list(range(8))
    assert admission_calls[1][3]["supervisor_cpu"] == 8


@pytest.mark.parametrize(
    ("input_path", "profile_identity", "mesh_plan_family"),
    [
        pytest.param(
            INPUT,
            SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE,
            "d07c",
            id="baseline",
        ),
        pytest.param(
            ROOT / "input/saxs_simple_grating_center_cx_p6_direct.dat",
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX_PROFILE,
            "saxs_one_axis",
            id="cx",
        ),
        pytest.param(
            ROOT / "input/saxs_simple_grating_center_cz_p6_direct.dat",
            SAXS_SIMPLE_GRATING_P6_DIRECT_CZ_PROFILE,
            "saxs_one_axis",
            id="cz",
        ),
    ],
)
def test_profile_contract_and_real_loader_to_plan_manifest_worker_roundtrip(
    tmp_path, input_path, profile_identity, mesh_plan_family
):
    specification, run_directory, resolved_sha, plan, manifest = _bootstrap_roundtrip(
        tmp_path, input_path
    )
    route = _direct_run_contract(profile_identity)

    assert route["family"] == "task40_phi90"  # internal finite-window P6 route
    assert route["comparison_family"] == "saxs_simple_grating_center"
    assert route["task40_mesh_plan_family"] == mesh_plan_family
    assert route["profile_identity"] == profile_identity
    assert route["parent_count"] == 4488
    assert route["active_count"] == 1088
    assert route["signed_rectangle_bounds_mn"] == [-8, 8, -14, 1]
    assert manifest["native_capacity_profile_identity"] == (
        profile_identity
    )
    assert manifest["native_capacity_contract"]["resource_stop_policy"] == (
        "host_available_floor_v1"
    )
    assert manifest["native_capacity_contract"]["rss_hard_limit_bytes"] is None
    assert manifest["native_capacity_contract"]["minimum_available_bytes"] == 64 * 1024**3
    assert manifest["native_capacity_contract"][
        "legacy_execution_memory_fields_authority"
    ].startswith("diagnostic_only")
    assert len(WORKER_CPUS) == 8
    assert "-c" in plan.argv

    resolved, errors = _validate_worker(
        specification, run_directory, resolved_sha, plan
    )
    assert errors == []
    assert resolved is not None
    assert resolved["derived"]["native_capacity_profile"] == manifest[
        "native_capacity_profile"
    ]
