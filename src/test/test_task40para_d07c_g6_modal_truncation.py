"""G6 same-mesh signed-window identities and worker launch contracts."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.task40_phi90_d07c_axis_plan import d07c_axis_plan
from src.io.execution_plan import build_execution_plan
from src.io.input_validation import load_and_resolve, simulation_config_3d_from_normalized
from src.io.native_capacity_profile import native_profile_facts, validate_native_case
from src.io.resolved_config import resolved_config_sha256
from src.runners.p6_condensed_direct import (
    _build_task40_rectangle_inventory,
    _direct_run_contract,
    _task40_d07c_mesh_evidence,
)
from src.runners.task038_input_worker import _task40_g6_runtime_cache_evidence
from src.runners.task40_d07c_g5_join import G6_PROFILE, G6_N14_PROFILE, G6_N32_PROFILE
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

ROOT = Path(__file__).resolve().parents[2]
INPUTS = {
    "N64": ROOT / "input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus64_to1_p6_direct.dat",
    "N32": ROOT / "input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus32_to1_p6_direct.dat",
    "N14": ROOT / "input/task40para_phi90_mesh_modes_direct/d07c_g6_m8_nminus14_to1_p6_direct.dat",
}
EXPECTED = {
    "N64": {
        "profile": G6_PROFILE,
        "bounds": (-8, 8, -64, 1),
        "count": 4488,
        "mode_sha": "e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0",
    },
    "N32": {
        "profile": G6_N32_PROFILE,
        "bounds": (-8, 8, -32, 1),
        "count": 2312,
        "mode_sha": "f81d3ff08f8950abcb4fa17736ee167e860d89c51baebc85a74fbea1b24493a4",
        "parent_indices_sha": "86d4e9d09a0a91680b98814e5a39b07a30910e13622f709cb61fcba654ca17e6",
        "signed_keys_sha": "6c69e73eff8b237ee4d2c2242be5a4a9e7466ceb8a9000eed780dda75f559ded",
        "propagating": 2184,
        "power_carrying": 2250,
    },
    "N14": {
        "profile": G6_N14_PROFILE,
        "bounds": (-8, 8, -14, 1),
        "count": 1088,
        "mode_sha": "8d7eda75f7bb3476fc2363231c6dde8ff6bdd225876cb41a4112c21a4799b158",
        "parent_indices_sha": "1fc6bb7886a9858e3288ae45ee3ae50fea0bdf75881f03b52f45a26a3fe41fe1",
        "signed_keys_sha": "03c5894de4fd5597da93a2971a1914ffca955b61e39a9f8db173d0fd39beebb0",
        "propagating": 960,
        "power_carrying": 1026,
    },
}
G6_AXIS_SHA = {
    "x": "bb1d6be1e2cec153c7bd67a71e29f5967b3035b4928cd06f51ee2c0b6f2a5361",
    "y": "b7422d323609a23b128a49be40ae337c796fa78b7b9abc36d53b7f8ef1a815aa",
    "z": "b603d8672fe0097d827859e5b4cab92ad139ba71427d4f75fa421bbd8bc25501",
}
G6_TAGS = {"1": 6560, "2": 2400, "3": 640}


def _resolved_case(label: str):
    specification = load_and_resolve(INPUTS[label])
    resolved = specification.as_jsonable()
    profile = resolved["solver"]["native_capacity_profile"]
    route = _direct_run_contract(profile)
    cfg = simulation_config_3d_from_normalized(resolved)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(route["parent_signed_bounds_mn"])
    cfg.stage4_dtn_quadrature_degree = int(route["surface_quadrature_degree"])
    cfg.task40_port_boundary_amplitude_scale_policy = route["mode_basis_scale_policy"]
    return specification, resolved, profile, route, cfg


def _ordered_keys(modes):
    return [
        (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
        for mode in modes
    ]


def _argument(argv, option):
    return argv[argv.index(option) + 1]


def test_g6_modal_windows_are_nested_signed_subsets_on_the_exact_g6_mesh():
    base_spec, base_resolved, _base_profile, base_route, base_cfg = _resolved_case("N64")
    parent_inventory = build_dynamic_mode_inventory(base_cfg)
    assert len(parent_inventory[0]) == EXPECTED["N64"]["count"]
    assert parent_inventory[2] == EXPECTED["N64"]["mode_sha"]
    parent_keys = _ordered_keys(parent_inventory[0])

    selected_keys = {}
    for label in ("N32", "N14"):
        specification, resolved, profile, route, cfg = _resolved_case(label)
        facts = native_profile_facts(profile)
        direct = facts["campaign_authorization"]["direct_route"]
        expected = EXPECTED[label]

        assert profile == expected["profile"]
        assert tuple(route["signed_rectangle_bounds_mn"]) == expected["bounds"]
        assert route["parent_signed_bounds_mn"] == [-8, 8, -64, 1]
        assert route["parent_count"] == len(parent_inventory[0])
        assert route["expected_mode_sha256"] == parent_inventory[2]
        assert route["active_count"] == expected["count"]
        assert route["active_sha256"] == expected["mode_sha"]
        assert route["expected_selected_parent_indices_sha256"] == expected[
            "parent_indices_sha"
        ]
        assert route["expected_selected_signed_keys_sha256"] == expected[
            "signed_keys_sha"
        ]
        assert route["propagating_count"] == expected["propagating"]
        assert route["power_carrying_count"] == expected["power_carrying"]

        active_inventory, selection, indices = _build_task40_rectangle_inventory(
            parent_inventory, cfg, route
        )
        active_keys = _ordered_keys(active_inventory[0])
        assert len(active_inventory[0]) == len(active_inventory[1]) == expected["count"]
        assert active_inventory[2] == expected["mode_sha"]
        assert active_keys == [parent_keys[index] for index in indices]
        assert selection["selected_parent_indices_sha256"] == expected[
            "parent_indices_sha"
        ]
        assert selection["selected_signed_keys_sha256"] == expected["signed_keys_sha"]
        assert set(active_keys).issubset(parent_keys)
        selected_keys[label] = active_keys

        assert specification.physical_model_sha256 == base_spec.physical_model_sha256
        assert resolved["discretization"] == base_resolved["discretization"]
        for section in (
            "geometry", "materials", "incidence", "boundary", "method",
            "execution", "output",
        ):
            assert resolved[section] == base_resolved[section]
        assert resolved["solver"] == {
            **base_resolved["solver"],
            "native_capacity_profile": profile,
        }
        validate_native_case(resolved)

        assert route["task40_mesh_case"] == "G6"
        assert route["task40_expected_axis_sha256_le_f64"] == G6_AXIS_SHA
        assert route["task40_mesh_plan_id"] == base_route["task40_mesh_plan_id"]
        assert route["task40_mesh_plan_sha256"] == base_route["task40_mesh_plan_sha256"]
        assert route["expected_axis_cell_counts"] == [6, 200, 8]
        assert route["expected_global_cell_count"] == 9600
        assert direct["surface_quadrature_degree"] == 81
        assert direct["surface_quadrature_reference_degree"] == 161
        assert direct["volume_quadrature_degree"] == 15
        assert direct["volume_quadrature_rule"] == "default"
        assert route["sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
        assert route["sparse_cutoff_relative_tolerance"] == 1e-13
        assert route["write_visualization_files"] is False
        assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
        assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
        assert facts["resources"]["rss_hard_limit_bytes"] is None
        assert facts["resources"]["pss_sampling_policy"] == "disabled_by_profile"

    assert set(selected_keys["N14"]).issubset(selected_keys["N32"])


def test_g6_modal_truncation_live_mesh_and_visualization_output_policy(tmp_path):
    _specification, _resolved, _profile, _route, cfg = _resolved_case("N32")
    mesh_dir = tmp_path / "mesh"
    levels = {"mesh_data": build_airbox_mesh_3d(cfg, mesh_dir)}
    suffixes = {path.suffix.lower() for path in mesh_dir.iterdir()}
    assert {".vtu", ".vtk", ".vtx", ".pvd"}.isdisjoint(suffixes)
    for label in ("N32", "N14"):
        _specification, _resolved, profile, route, _cfg = _resolved_case(label)
        evidence = _task40_d07c_mesh_evidence(levels, cfg, route)
        assert evidence["status"] == "PASS"
        assert evidence["profile"] == profile
        assert evidence["parent_case"] == "G5"
        assert evidence["changed_axis"] == "y"
        assert evidence["axis_cell_counts"] == [6, 200, 8]
        assert evidence["actual_global_cell_count"] == 9600
        assert evidence["material_tag_counts"] == G6_TAGS
        assert evidence["axis_sha256_le_f64"] == d07c_axis_plan("G6")[
            "axis_sha256_le_f64"
        ]


def test_g6_modal_truncation_builds_dynamic_cpu_formal_worker_argv(tmp_path):
    for label in ("N32", "N14"):
        specification, _resolved, profile, route, _cfg = _resolved_case(label)
        run_dir = tmp_path / label / "run"
        run_dir.mkdir(parents=True)
        plan = build_execution_plan(
            specification,
            run_dir,
            source_sha="a" * 40,
            python_executable="/qualified/shared/bin/python",
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=[17],
        )
        argv = plan.argv
        assert argv[:9] == (
            "/usr/bin/mpiexec", "-n", "1", "/usr/bin/numactl",
            "--interleave=0,1", "/usr/bin/taskset", "-c", "17",
            "/qualified/shared/bin/python",
        )
        assert plan.input_sha256 == specification.input_sha256
        assert plan.physical_model_sha256 == specification.physical_model_sha256
        assert _argument(argv, "--expected-input-sha256") == specification.input_sha256
        assert _argument(argv, "--expected-physical-model-sha256") == (
            specification.physical_model_sha256
        )
        assert _argument(argv, "--expected-source-sha") == "a" * 40
        assert _argument(argv, "--expected-mpi-size") == "1"
        assert _argument(argv, "--expected-method") == "full3d_direct"
        assert _argument(argv, "--expected-adapter") == "task038.full3d_direct"
        assert _argument(argv, "--resolved-config-sha256") == resolved_config_sha256(
            specification
        )
        assert route["profile_identity"] == profile


def test_g6_modal_truncation_worker_cache_is_unique_and_verified(tmp_path):
    for case, profile in (("G6_M8_N32", G6_N32_PROFILE), ("G6_M8_N14", G6_N14_PROFILE)):
        attempt = f"{case.lower()}-{uuid.uuid4().hex[:16]}"
        root = Path("/tmp") / f"task40_d07c_{case.lower()}_attempt_{attempt}"
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
            environment = {
                "TMPDIR": str(paths["tmp"]),
                "TMP": str(paths["tmp"]),
                "TEMP": str(paths["tmp"]),
                "XDG_CACHE_HOME": str(paths["xdg"]),
                "PYTHONPYCACHEPREFIX": str(paths["pycache"]),
                "MPLCONFIGDIR": str(paths["mpl"]),
            }
            join_key = f"{case.lower()}_observational_join"
            manifest = {
                "native_capacity_profile_identity": profile,
                "native_capacity_isolation": {join_key: {"attempt_id": attempt}},
                "attempt_specific_runtime_cache": {
                    **{key: str(value) for key, value in paths.items()},
                    "owner": f"{case}_attempt_only",
                },
            }
            evidence = _task40_g6_runtime_cache_evidence(
                manifest,
                environment=environment,
                jit_options_resolver=lambda: {"cache_dir": str(paths["xdg"] / "fenics")},
            )
            assert evidence["schema"] == f"task40.d07c.{case.lower()}_worker_cache_runtime.v1"
            assert evidence["attempt_id"] == attempt
            assert evidence["cache_paths_verified_before_FE_dispatch"] is True
        finally:
            shutil.rmtree(root, ignore_errors=True)
