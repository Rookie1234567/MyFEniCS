from __future__ import annotations

import hashlib
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
    SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE,
    SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE,
    SAXS_SIMPLE_GRATING_P6_DIRECT_CZ_PROFILE,
    SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE,
    TASK40_PHI90_D07C_G6_M8_N14_PROFILE,
    native_profile_facts,
    numeric_factor_blas_thread_choices,
)
from src.runners import (
    native_capacity,
    p6_condensed_direct,
    reviewed_workstation_admission,
    task038_input_worker,
)
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _preflight_task40_mode_inventories,
)
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import (
    _validate_numeric_factor_cpu_reservation,
    _write_bootstrap,
    _write_json,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/saxs_simple_grating_center_p6_direct.dat"
CXZ15_INPUT = ROOT / "input/saxs_simple_grating_center_cxz15_p6_direct.dat"
CX9Z10_INPUT = ROOT / "input/saxs_simple_grating_center_cx9z10_p6_direct.dat"
SOURCE_SHA = "a5c8" * 10
WORKER_CPUS = list(range(16, 24))


def _bootstrap_roundtrip(
    tmp_path, input_path=INPUT, *, worker_cpus_override=WORKER_CPUS
):
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
        worker_cpus_override=worker_cpus_override,
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


def _cx9z10_prelu_launcher_binding():
    repository_root = ROOT.resolve()
    profile_path = (
        repository_root / "profiles/cx9z10_prelu_port_blas8_v1.json"
    ).resolve()
    launcher_path = (repository_root / "src/runners/task038_launcher.py").resolve()
    worker_path = (repository_root / "src/runners/p6_condensed_direct.py").resolve()
    worker_environment = {
        "MYFENICS_CX9Z10_PRELU_PORT_PROFILE_ID": "CX9Z10_PRELU_LOCAL_PORT_BLAS8_V1",
        "MYFENICS_CX9Z10_PRELU_PROFILE_PATH": str(profile_path),
        "MYFENICS_CX9Z10_PRELU_LAUNCHER_PATH": str(launcher_path),
        "MYFENICS_CX9Z10_PRELU_WORKER_PATH": str(worker_path),
    }
    return {
        "schema": "cx9z10.prelu_launcher_binding.v1",
        "profile_id": "CX9Z10_PRELU_LOCAL_PORT_BLAS8_V1",
        "profile_path": str(profile_path),
        "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "launcher_path": str(launcher_path),
        "launcher_sha256": hashlib.sha256(launcher_path.read_bytes()).hexdigest(),
        "worker_path": str(worker_path),
        "worker_sha256": hashlib.sha256(worker_path.read_bytes()).hexdigest(),
        "worker_environment": worker_environment,
        "launch_authority": "external_main_review_and_fresh_gate_required",
    }


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


def _run_worker_main(monkeypatch, plan):
    class SerialComm:
        rank = 0
        size = 1

        @staticmethod
        def allreduce(value, op=None):
            return value

        @staticmethod
        def Barrier():
            return None

    monkeypatch.setitem(
        sys.modules,
        "mpi4py",
        SimpleNamespace(MPI=SimpleNamespace(COMM_WORLD=SerialComm(), LOR=object())),
    )
    argv = list(plan.argv)
    worker_args = argv[argv.index("src.runners.task038_input_worker") + 1 :]
    return task038_input_worker.main(worker_args)


def _install_fake_p6_dispatch(monkeypatch, events=None):
    calls = []

    def fake_run_p6(_payload, _directory, **kwargs):
        # Worker validation and production dispatch stay real; only FE work is stubbed.
        if events is not None:
            events.append("numeric-dispatch")
        calls.append(kwargs)
        return {"passed": True, "errors": []}

    monkeypatch.setattr(p6_condensed_direct, "run_p6_condensed_direct", fake_run_p6)
    return calls


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


def test_cxz15_profile_is_z_only_from_completed_cx_and_records_g6_lineage():
    from src.geometry.saxs_simple_grating_axis_plan import (
        saxs_cxz15_plan,
        saxs_one_axis_plan,
    )

    plan = saxs_cxz15_plan()
    cx_plan = saxs_one_axis_plan("x")
    resolved = load_and_resolve(CXZ15_INPUT).as_jsonable()
    cx_resolved = load_and_resolve(
        ROOT / "input/saxs_simple_grating_center_cx_p6_direct.dat"
    ).as_jsonable()
    facts = native_profile_facts(SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE)
    comparison = facts["component_options"]["directional_mesh_comparison"]
    direct = facts["campaign_authorization"]["direct_route"]
    route = _direct_run_contract(SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE)

    assert resolved["solver"]["native_capacity_profile"] == (
        SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE
    )
    assert resolved["run_id"].endswith("_cxz15_v1")
    assert resolved["discretization"]["mesh_axis_cell_counts"] == [12, 200, 12]
    assert resolved["discretization"]["mesh_axis_x_values"] == cx_plan["axes_nm"]["x"]
    assert resolved["discretization"]["mesh_axis_y_values"] == cx_plan["axes_nm"]["y"]
    assert resolved["discretization"]["mesh_axis_z_values"] == plan["axes_nm"]["z"]
    assert resolved["discretization"]["mesh_plan_id"] == plan["mesh_plan_id"]
    assert resolved["discretization"]["mesh_plan_sha256"] == plan[
        "mesh_plan_sha256"
    ]
    assert plan["changed_axes"] == ["z"]
    assert plan["changed_axes_vs_saxs_g6_baseline"] == ["x", "z"]
    assert plan["axis_sha256_le_f64"]["x"] == cx_plan["axis_sha256_le_f64"]["x"]
    assert plan["axis_sha256_le_f64"]["y"] == cx_plan["axis_sha256_le_f64"]["y"]
    assert plan["reference_run_timestamp"] == "20261108T144628.333953Z"
    assert plan["reference_source_sha256"] == (
        "0c8ab09edfd60f40a45785f5e637e7718c13abf2"
    )
    assert cx_plan["mesh_plan_sha256"] == (
        "48de59951bfc241d3df8630f74a678abe3b0bb878a50a51b3db77a70f532b7ab"
    )
    assert saxs_one_axis_plan("z")["mesh_plan_sha256"] == (
        "1f62374bddf01d12078f1fa07c21d1ef78bccb4a12aed88883ba8954729fcc8d"
    )
    assert plan["axis_cell_counts"] == [12, 200, 12]
    assert plan["expected_global_cell_count"] == 28800
    assert plan["expected_material_tag_counts"] == {
        "1": 21440,
        "2": 4800,
        "3": 2560,
    }
    assert plan["static_condensed_rows"]["augmented_rows"] == 5876288
    assert comparison["parent_case"] == "CX"
    assert comparison["changed_axes"] == ["z"]
    assert comparison["changed_axes_vs_saxs_g6_baseline"] == ["x", "z"]
    assert comparison["parent_axis_sha256_le_f64"] == plan[
        "reference_axis_sha256_le_f64"
    ]
    assert comparison["baseline_axis_sha256_le_f64"] == plan[
        "baseline_axis_sha256_le_f64"
    ]
    assert direct["changed_axes"] == ["z"]
    assert direct["changed_axes_vs_saxs_g6_baseline"] == ["x", "z"]
    assert facts["component_options"]["mode_selection"]["expected_active_mode_count"] == 1088
    cx_facts = native_profile_facts(SAXS_SIMPLE_GRATING_P6_DIRECT_CX_PROFILE)
    assert facts["component_options"]["mode_selection"] == cx_facts[
        "component_options"
    ]["mode_selection"]
    assert facts["component_options"]["surface_quadrature"]["degree"] == 81
    assert facts["component_options"]["volume_quadrature"]["degree"] == 15
    assert facts["condensed_route"]["expected_global_cell_count"] == 28800
    assert route["task40_mesh_plan_family"] == "saxs_cxz15"
    assert route["task40_parent_case"] == "CX"
    assert route["task40_changed_axes"] == ["z"]
    assert route["task40_changed_axes_vs_saxs_g6_baseline"] == ["x", "z"]
    assert route["expected_axis_cell_counts"] == [12, 200, 12]
    assert route["expected_global_cell_count"] == 28800
    assert numeric_factor_blas_thread_choices(
        SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE
    ) == {1, 8}
    for section in (
        "geometry",
        "materials",
        "incidence",
        "boundary",
        "method",
        "execution",
        "output",
    ):
        assert resolved[section] == cx_resolved[section]
    assert resolved["comparison_group"] == cx_resolved["comparison_group"]
    assert {
        key: value
        for key, value in resolved["solver"].items()
        if key != "native_capacity_profile"
    } == {
        key: value
        for key, value in cx_resolved["solver"].items()
        if key != "native_capacity_profile"
    }


def test_cxz15_actual_mesh_p6_mpc_and_lineage_evidence_without_form_or_factor():
    from mpi4py import MPI

    from src.geometry.saxs_simple_grating_axis_plan import saxs_cxz15_plan
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _build_same_mesh_levels,
    )

    specification = load_and_resolve(CXZ15_INPUT)
    resolved = specification.as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    route = _direct_run_contract(profile)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(
        int(value) for value in route["parent_signed_bounds_mn"]
    )
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route[
        "mode_basis_scale_policy"
    ]
    mode_preflight = _preflight_task40_mode_inventories(cfg, route)
    assert len(mode_preflight["parent_inventory"][0]) == 4488
    assert len(mode_preflight["active_inventory"][0]) == 1088
    assert route["active_sha256"] == (
        "cf26a40d59727fd7bbcaab83ed80427859acb405b1e66a869a75e57b276d896a"
    )
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
    )
    try:
        evidence = p6_condensed_direct._saxs_cxz15_mesh_evidence(
            levels, cfg, route
        )
        plan = saxs_cxz15_plan()
        assert evidence["status"] == "PASS"
        assert evidence["actual_global_cell_count"] == 28800
        assert evidence["axis_cell_counts"] == [12, 200, 12]
        assert evidence["material_tag_counts"] == {
            "1": 21440,
            "2": 4800,
            "3": 2560,
        }
        assert evidence["axis_sha256_le_f64"] == plan["axis_sha256_le_f64"]
        assert evidence["reference_axis_sha256_le_f64"] == plan[
            "reference_axis_sha256_le_f64"
        ]
        assert evidence["baseline_axis_sha256_le_f64"] == plan[
            "baseline_axis_sha256_le_f64"
        ]
        assert evidence["p6_space_degree"] == 6
        assert evidence["p6_global_dof_count"] > 0
        assert evidence["double_floquet_mpc_finalized"] is True
        assert evidence["floquet_constraint_mode_resolved"] == "topological_trace_p6"
        assert evidence["floquet_num_constraints"] > 0
        assert evidence["p6_matrix_assembly_started"] is False
        assert evidence["p6_factorization_started"] is False
    finally:
        for floquet in levels.get("floquets", {}).values():
            mpc = getattr(floquet, "mpc", None)
            if mpc is not None and hasattr(mpc, "destroy"):
                mpc.destroy()
        del levels


def test_cx9z10_input_profile_and_exact_target_axis_contract():
    from src.geometry.saxs_simple_grating_axis_plan import (
        saxs_cx9z10_plan,
        validate_saxs_cx9z10_plan,
    )

    specification = load_and_resolve(CX9Z10_INPUT)
    resolved = specification.as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    facts = native_profile_facts(profile)
    route = _direct_run_contract(profile)
    plan = saxs_cx9z10_plan()
    discretization = resolved["discretization"]
    axes = {
        "mesh_plan_id": discretization["mesh_plan_id"],
        "mesh_plan_sha256": discretization["mesh_plan_sha256"],
        "mesh_axis_cell_counts": discretization["mesh_axis_cell_counts"],
        "mesh_axis_x_values": discretization["mesh_axis_x_values"],
        "mesh_axis_y_values": discretization["mesh_axis_y_values"],
        "mesh_axis_z_values": discretization["mesh_axis_z_values"],
    }

    assert profile == SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE
    assert resolved["run_id"].endswith("_cx9z10_v1")
    assert validate_saxs_cx9z10_plan(axes) == {
        key: tuple(plan["axes_nm"][key]) for key in "xyz"
    }
    assert plan["axis_cell_counts"] == [9, 200, 16]
    assert plan["expected_global_cell_count"] == 28800
    assert plan["expected_material_tag_counts"] == {
        "1": 22320,
        "2": 3600,
        "3": 2880,
    }
    assert route["task40_mesh_plan_family"] == "saxs_cx9z10"
    assert route["task40_mesh_plan_id"] == plan["mesh_plan_id"]
    assert route["task40_mesh_plan_sha256"] == plan["mesh_plan_sha256"]
    assert route["expected_axis_cell_counts"] == [9, 200, 16]
    assert route["expected_global_cell_count"] == 28800
    assert route["expected_mode_count"] == 4488
    assert route["active_count"] == 1088
    assert route["signed_rectangle_bounds_mn"] == [-8, 8, -14, 1]
    assert route["surface_quadrature_degree"] == 81
    assert facts["component_options"]["volume_quadrature"]["degree"] == 15
    assert facts["component_options"]["visualization_output_policy"][
        "write_visualization_files"
    ] is False
    assert facts["component_options"]["pre_lu_port_assembly_gate"] == {
        "profile_id": "CX9Z10_PRELU_LOCAL_PORT_BLAS8_V1",
        "profile_path": "profiles/cx9z10_prelu_port_blas8_v1.json",
        "activation": "exact_CX9Z10_native_profile_and_launcher_manifest",
        "numeric_lu_is_independent": True,
    }
    assert numeric_factor_blas_thread_choices(profile) == {1, 8}


def test_cx9z10_worker_requires_bound_prelu_profile_and_forwards_numeric_lu8(
    tmp_path, monkeypatch
):
    _specification, run_directory, _resolved_sha, plan, manifest = (
        _bootstrap_roundtrip(tmp_path, CX9Z10_INPUT)
    )
    binding = _cx9z10_prelu_launcher_binding()
    manifest["pre_lu_port_assembly_gate"] = binding
    _write_json(run_directory / "run_manifest.json", manifest)
    for name, value in binding["worker_environment"].items():
        monkeypatch.setenv(name, value)
    observed = _install_fake_p6_dispatch(monkeypatch)

    assert manifest["native_capacity_profile_identity"] == (
        SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE
    )
    assert _run_worker_main(monkeypatch, plan) == 0
    assert observed == [
        {
            "source_sha": SOURCE_SHA,
            "numeric_factor_blas_threads": 8,
            "numeric_factor_worker_affinity": WORKER_CPUS,
        }
    ]


def test_cx9z10_actual_mesh_p6_mpc_and_exact_tag_qa_without_form_or_factor():
    from mpi4py import MPI

    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _build_same_mesh_levels,
    )

    specification = load_and_resolve(CX9Z10_INPUT)
    resolved = specification.as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    route = _direct_run_contract(profile)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(
        int(value) for value in route["parent_signed_bounds_mn"]
    )
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route[
        "mode_basis_scale_policy"
    ]
    mode_preflight = _preflight_task40_mode_inventories(cfg, route)
    assert len(mode_preflight["parent_inventory"][0]) == 4488
    assert len(mode_preflight["active_inventory"][0]) == 1088
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
    )
    try:
        evidence = p6_condensed_direct._saxs_cx9z10_mesh_evidence(
            levels, cfg, route
        )
        assert evidence["status"] == "PASS"
        assert evidence["actual_global_cell_count"] == 28800
        assert evidence["axis_cell_counts"] == [9, 200, 16]
        assert evidence["material_tag_counts"] == {
            str(cfg.tags.air): 22320,
            str(cfg.tags.substrate): 3600,
            str(cfg.tags.grating): 2880,
        }
        assert evidence["axis_sha256_le_f64"] == route[
            "task40_expected_axis_sha256_le_f64"
        ]
        assert evidence["p6_space_degree"] == 6
        assert evidence["p6_global_dof_count"] > 0
        assert evidence["double_floquet_mpc_finalized"] is True
        assert evidence["p6_matrix_assembly_started"] is False
        assert evidence["p6_factorization_started"] is False
    finally:
        for floquet in levels.get("floquets", {}).values():
            mpc = getattr(floquet, "mpc", None)
            if mpc is not None and hasattr(mpc, "destroy"):
                mpc.destroy()
        del levels


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
        pytest.param(SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE, id="cxz15"),
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
        pytest.param(
            CXZ15_INPUT,
            SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE,
            "saxs_cxz15",
            id="cxz15",
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


@pytest.mark.parametrize(
    ("input_path", "profile_identity"),
    [
        pytest.param(
            INPUT,
            SAXS_SIMPLE_GRATING_P6_DIRECT_PROFILE,
            id="baseline",
        ),
        pytest.param(
            ROOT / "input/saxs_simple_grating_center_cx_p6_direct.dat",
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX_PROFILE,
            id="cx",
        ),
        pytest.param(
            ROOT / "input/saxs_simple_grating_center_cz_p6_direct.dat",
            SAXS_SIMPLE_GRATING_P6_DIRECT_CZ_PROFILE,
            id="cz",
        ),
        pytest.param(
            CXZ15_INPUT,
            SAXS_SIMPLE_GRATING_P6_DIRECT_CXZ15_PROFILE,
            id="cxz15",
        ),
    ],
)
def test_worker_main_forwards_saxs_blas8_to_numeric_runner_without_fe(
    tmp_path, monkeypatch, input_path, profile_identity
):
    _specification, _run_directory, _resolved_sha, plan, manifest = (
        _bootstrap_roundtrip(tmp_path, input_path)
    )
    assert manifest["native_capacity_profile_identity"] == profile_identity
    observed = _install_fake_p6_dispatch(monkeypatch)

    assert _run_worker_main(monkeypatch, plan) == 0

    assert observed == [
        {
            "source_sha": SOURCE_SHA,
            "numeric_factor_blas_threads": 8,
            "numeric_factor_worker_affinity": WORKER_CPUS,
        }
    ]


def test_worker_main_keeps_saxs_missing_thread_count_as_none_default(
    tmp_path, monkeypatch
):
    _specification, run_directory, _resolved_sha, plan, manifest = _bootstrap_roundtrip(
        tmp_path, INPUT
    )
    manifest.pop("numeric_factor_blas_threads")
    manifest.pop("numeric_factor_blas_scope")
    _write_json(run_directory / "run_manifest.json", manifest)
    observed = _install_fake_p6_dispatch(monkeypatch)

    assert _run_worker_main(monkeypatch, plan) == 0

    assert observed[0]["numeric_factor_blas_threads"] is None


def test_worker_main_preserves_g6_cache_validation_and_thread_route(
    tmp_path, monkeypatch
):
    from src.runners.task40_d07c_g5_join import G6_N14_PROFILE

    input_path = ROOT / (
        "input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus14_to1_p6_direct.dat"
    )
    _specification, _run_directory, _resolved_sha, plan, manifest = (
        _bootstrap_roundtrip(tmp_path, input_path)
    )
    assert manifest["native_capacity_profile_identity"] == G6_N14_PROFILE
    events = []
    observed = _install_fake_p6_dispatch(monkeypatch, events)
    cache_evidence = {"owner": "G6_attempt_only", "verified": True}

    def verify_cache(received_manifest):
        events.append("cache-validated")
        assert received_manifest["native_capacity_profile_identity"] == G6_N14_PROFILE
        return cache_evidence

    def write_cache(_output_directory, evidence):
        events.append("cache-evidence-written")
        assert evidence == cache_evidence

    monkeypatch.setattr(
        task038_input_worker, "_task40_d07c_runtime_cache_evidence", verify_cache
    )
    monkeypatch.setattr(
        task038_input_worker, "_write_d07c_runtime_cache_evidence", write_cache
    )

    assert _run_worker_main(monkeypatch, plan) == 0

    assert events == ["cache-validated", "cache-evidence-written", "numeric-dispatch"]
    assert observed[0]["numeric_factor_blas_threads"] == 8


def test_worker_main_rejects_blas8_for_unqualified_legacy_g6_profile(
    tmp_path, monkeypatch, capsys
):
    input_path = ROOT / (
        "input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus64_to1_p6_direct.dat"
    )
    _specification, run_directory, _resolved_sha, plan, manifest = _bootstrap_roundtrip(
        tmp_path,
        input_path,
        worker_cpus_override=[WORKER_CPUS[0]],
    )
    manifest["native_capacity_isolation"]["worker_affinity"] = [WORKER_CPUS[0]]
    _write_json(run_directory / "run_manifest.json", manifest)
    dispatch_calls = _install_fake_p6_dispatch(monkeypatch)

    assert _run_worker_main(monkeypatch, plan) == 2
    assert dispatch_calls == []
    assert "outside the exact profile-scoped contract" in capsys.readouterr().out
