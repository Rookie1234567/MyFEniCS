"""No-FE identity checks for the M8N6 and M8N2 Gate-CD profiles."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.gate_cd_formal_once import (
    GATE_CD_FORMAL_PROFILES,
    _validate_live_profile_contract,
)
from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    _jsonable,
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_GATE_CD_M8N2_P6_DIRECT_PROFILE,
    TASK40_GATE_CD_M8N6_P6_DIRECT_PROFILE,
    _validate_task40_gate_cd_case,
    native_profile_facts,
)
from src.io.resolved_config import resolved_config_sha256
from src.io.run_specification import thaw
from src.runners.p6_condensed_direct import (
    _build_task40_rectangle_inventory,
    _direct_run_contract,
    _validate_resolved_profile,
)
from src.runners.task038_input_worker import (
    _load_and_validate_worker_payload,
)
from src.runners.task038_input_worker import (
    _parser as worker_parser,
)
from src.runners.task038_launcher import _write_bootstrap
from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

ROOT = Path(__file__).resolve().parents[2]
PARENT_SHA256 = "6cf60807239dffc209b47336581e8bb50a5f4d986cba5bbdc06500f6271d3865"
CASES = {
    TASK40_GATE_CD_M8N6_P6_DIRECT_PROFILE: {
        "input": ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_m8n6_p6_direct.dat",
        "bounds": (-8, 8, -6, 1),
        "count": 544,
        "active_sha256": "a01d69f201d3fa02b07fd208c3e2aefb8f9501a591f57045c6c2ca761004a243",
        "indices_sha256": "c18bb9b614aa570cf0f9171b1fcf5197651e902d1f9e39c52f491724f1728106",
        "keys_sha256": "f90e7470893a966fd0da352109f154bd2ae077ce860c1229311d99d965a70fac",
        "propagating": 416,
        "power_carrying": 482,
        "propagating_by_side": {"top": 210, "bottom": 206},
        "power_by_side": {"top": 210, "bottom": 272},
        "report_n": 6,
    },
    TASK40_GATE_CD_M8N2_P6_DIRECT_PROFILE: {
        "input": ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_m8n2_p6_direct.dat",
        "bounds": (-8, 8, -2, 1),
        "count": 272,
        "active_sha256": "fea54561d3765346bff604334fafd5506df2aeb0562be53129cf05dfdd36c2fd",
        "indices_sha256": "041f64f1b215e540c13f35f337fe558ace659a64ff7ffc11b45aa4ebc6ca7d93",
        "keys_sha256": "97b64f142862e4f88a558f3d4843fed884d027f2ace473a3ef6687c2c34f663a",
        "propagating": 144,
        "power_carrying": 210,
        "propagating_by_side": {"top": 74, "bottom": 70},
        "power_by_side": {"top": 74, "bottom": 136},
        "report_n": 2,
    },
}


@pytest.mark.parametrize("profile,expected", CASES.items())
def test_loader_and_direct_contract_bind_each_exact_small_rectangle(profile, expected):
    specification = load_and_resolve(expected["input"])
    resolved = specification.as_jsonable()
    facts = native_profile_facts(profile)
    route = _direct_run_contract(profile)
    mode = facts["component_options"]["mode_selection"]

    assert _validate_resolved_profile(resolved)["identity"] == profile
    assert specification.identity["run_id"] == profile
    assert specification.solver["native_capacity_profile"] == profile
    assert resolved["output"]["diffraction_order_max_m"] == 8
    assert resolved["output"]["diffraction_order_max_n"] == expected["report_n"]
    assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert facts["resources"]["resource_stop_policy"] == "host_available_floor_v1"
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert facts["resources"]["rss_hard_limit_bytes"] is None
    assert facts["component_options"]["surface_quadrature"]["degree"] == 81
    assert facts["component_options"]["volume_quadrature"]["degree"] == 21
    assert route["parent_count"] == 4488
    assert route["expected_mode_sha256"] == PARENT_SHA256
    assert route["parent_signed_bounds_mn"] == [-8, 8, -64, 1]
    assert route["signed_rectangle_bounds_mn"] == list(expected["bounds"])
    assert route["active_count"] == expected["count"]
    assert route["active_sha256"] == expected["active_sha256"]
    assert route["expected_selected_parent_indices_sha256"] == expected["indices_sha256"]
    assert route["expected_selected_signed_keys_sha256"] == expected["keys_sha256"]
    assert route["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert mode["policy"] == "explicit_signed_subrectangle_from_parent_v1"
    assert route["selection_policy"] == "explicit_signed_subrectangle_from_parent_v1"
    assert route["comparison_family"] == (
        f"GATE_CD_{mode['reference_mode_label']}_SIGNED_SUBRECTANGLE_FROM_M8N64_PARENT"
    )
    assert facts["campaign_authorization"]["direct_route"][
        "exact_cache_contract_required"
    ] is False


@pytest.mark.parametrize("profile,expected", CASES.items())
def test_production_parent_inventory_selects_exact_ordered_keys(profile, expected):
    specification = load_and_resolve(expected["input"])
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    route = _direct_run_contract(profile)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(route["parent_signed_bounds_mn"])
    cfg.stage4_dtn_quadrature_degree = route["surface_quadrature_degree"]
    cfg.task40_port_boundary_amplitude_scale_policy = route["mode_basis_scale_policy"]

    parent_inventory = build_dynamic_mode_inventory(cfg)
    assert parent_inventory[2] == PARENT_SHA256
    assert len(parent_inventory[0]) == len(parent_inventory[1]) == 4488
    active_inventory, selection, indices = _build_task40_rectangle_inventory(
        parent_inventory, cfg, route
    )
    modes, rows, active_sha = active_inventory
    assert len(modes) == len(rows) == expected["count"]
    assert active_sha == expected["active_sha256"]
    assert selection["active_signed_bounds_mn"] == list(expected["bounds"])
    assert selection["selected_parent_indices_sha256"] == expected["indices_sha256"]
    assert selection["selected_signed_keys_sha256"] == expected["keys_sha256"]
    assert sum(bool(mode.propagating) for mode in modes) == expected["propagating"]
    assert sum(float(mode.power_per_unit_amplitude) > 0 for mode in modes) == expected[
        "power_carrying"
    ]
    assert Counter(str(mode.side) for mode in modes if bool(mode.propagating)) == Counter(
        expected["propagating_by_side"]
    )
    assert Counter(
        str(mode.side) for mode in modes if float(mode.power_per_unit_amplitude) > 0
    ) == Counter(expected["power_by_side"])
    expected_keys = {
        (side, m, n, polarization)
        for side in ("top", "bottom")
        for m in range(-8, 9)
        for n in range(expected["bounds"][2], expected["bounds"][3] + 1)
        for polarization in ("s", "p")
    }
    actual_keys = {
        (str(row["side"]), int(row["m"]), int(row["n"]), str(row["polarization"]))
        for row in rows
    }
    assert actual_keys == expected_keys
    assert len(indices) == expected["count"]

    bad_route = dict(route)
    bad_route["signed_rectangle_bounds_mn"] = [-8, 8, -64, 1]
    with pytest.raises(ValueError, match="bounds differ from its envelope"):
        _build_task40_rectangle_inventory(parent_inventory, cfg, bad_route)


@pytest.mark.parametrize("profile,expected", CASES.items())
def test_loader_manifest_and_worker_payload_roundtrip(profile, expected, tmp_path):
    specification = load_and_resolve(expected["input"])
    run_directory = tmp_path / profile
    run_directory.mkdir()
    specification = replace(specification, expected_output_parent=tmp_path)
    source_sha = "a" * 64
    execution = build_execution_plan(
        specification,
        run_directory,
        source_sha=source_sha,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
        worker_cpus_override=[43],
    )
    assert execution.argv[:11] == (
        "/usr/bin/mpiexec", "-n", "1", "/usr/bin/numactl",
        "--interleave=0,1", "/usr/bin/taskset", "-c", "43",
        sys.executable, "-m", "src.runners.task038_input_worker",
    )
    with pytest.raises(Exception, match="dynamic one-CPU reservation"):
        build_execution_plan(
            specification,
            run_directory,
            source_sha=source_sha,
            python_executable=sys.executable,
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=[43, 44],
        )
    manifest, _resolved_sha = _write_bootstrap(
        specification,
        run_directory,
        source_sha=source_sha,
        adapter_identity=execution.adapter_identity,
        start_time="2026-11-03T00:00:00Z",
    )
    manifest["worker_command"] = list(execution.argv)
    manifest_path = run_directory / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    worker_index = execution.argv.index("src.runners.task038_input_worker")
    worker_args = execution.argv[worker_index + 1 :]
    parsed = worker_parser().parse_args(worker_args)
    resolved_payload, errors = _load_and_validate_worker_payload(
        resolved_config=parsed.resolved_config,
        manifest=parsed.manifest,
        expected_input_sha256=parsed.expected_input_sha256,
        expected_physical_model_sha256=parsed.expected_physical_model_sha256,
        expected_source_sha=parsed.expected_source_sha,
        expected_mpi_size=parsed.expected_mpi_size,
        expected_method=parsed.expected_method,
        expected_adapter=parsed.expected_adapter,
        expected_output_directory=parsed.expected_output_directory,
        expected_resolved_config_sha256=parsed.resolved_config_sha256,
        actual_mpi_size=1,
    )
    assert errors == []
    assert resolved_payload["derived"]["native_capacity_profile"] == thaw(
        specification.derived["native_capacity_profile"]
    )
    assert manifest["native_capacity_contract"]["direct_route"][
        "active_mode_count"
    ] == expected["count"]
    assert manifest["native_capacity_contract"]["direct_route"][
        "active_mode_sha256"
    ] == expected["active_sha256"]

    manifest["native_capacity_contract"]["direct_route"][
        "active_mode_count"
    ] += 1
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    _, errors = _load_and_validate_worker_payload(
        resolved_config=parsed.resolved_config,
        manifest=parsed.manifest,
        expected_input_sha256=parsed.expected_input_sha256,
        expected_physical_model_sha256=parsed.expected_physical_model_sha256,
        expected_source_sha=parsed.expected_source_sha,
        expected_mpi_size=parsed.expected_mpi_size,
        expected_method=parsed.expected_method,
        expected_adapter=parsed.expected_adapter,
        expected_output_directory=parsed.expected_output_directory,
        expected_resolved_config_sha256=parsed.resolved_config_sha256,
        actual_mpi_size=1,
    )
    assert "manifest condensed-direct route contract mismatch" in errors


@pytest.mark.parametrize("profile,expected", CASES.items())
def test_profile_validator_rejects_wrong_report_envelope(profile, expected):
    config = load_and_resolve(expected["input"]).as_jsonable()
    config["output"]["diffraction_order_max_n"] = 64
    with pytest.raises(Exception, match="reporting envelope"):
        _validate_task40_gate_cd_case(config, profile)


@pytest.mark.parametrize("profile,expected", CASES.items())
def test_formal_package_validator_binds_the_live_signed_operator(profile, expected):
    facts = native_profile_facts(profile)
    mode = facts["component_options"]["mode_selection"]
    package = {
        "profile_identity": profile,
        "quadrature_contract": {
            "surface_degree": facts["component_options"]["surface_quadrature"]["degree"],
            "surface_rule": facts["component_options"]["surface_quadrature"]["rule"],
            "volume_degree": facts["component_options"]["volume_quadrature"]["degree"],
            "volume_rule": facts["component_options"]["volume_quadrature"]["rule"],
        },
        "mapped_geometry_identity": "mapped_exact",
        "mapped_geometry_cache_policy": facts["component_options"][
            "mapped_geometry_cache_policy"
        ],
        "translation_normalized_cache": True,
        "finite_operator": {
            "active_mode_count": mode["expected_active_mode_count"],
            "active_mode_sha256": mode["expected_active_mode_sha256"],
            "active_signed_bounds_mn": mode["active_signed_bounds_mn"],
            "parent_mode_count": mode["expected_mode_count"],
            "parent_mode_sha256": mode["expected_mode_sha256"],
            "parent_signed_bounds_mn": mode["parent_signed_bounds_mn"],
            "selected_parent_indices_sha256": mode[
                "expected_selected_parent_indices_sha256"
            ],
            "selected_signed_keys_sha256": mode[
                "expected_selected_signed_keys_sha256"
            ],
            "propagating_mode_count": mode["expected_active_propagating_count"],
            "power_carrying_mode_count": mode[
                "expected_active_power_carrying_count"
            ],
        },
    }
    assert profile in GATE_CD_FORMAL_PROFILES
    _validate_live_profile_contract(package, facts)
    package["finite_operator"]["active_mode_count"] += 1
    with pytest.raises(ValueError, match="finite operator differs"):
        _validate_live_profile_contract(package, facts)


@pytest.mark.parametrize("profile,expected", CASES.items())
def test_one_worker_admission_and_runtime_cache_contract(profile, expected, tmp_path):
    from src.runners.task038_input_worker import _task40_gate_cd_runtime_cache_evidence
    from src.runners.task40_gate_cd_formal_admission import (
        GATE_CD_SCOPE_SCHEMA,
        _runtime_paths,
        _validate_gate_cd_scope,
    )

    specification = load_and_resolve(expected["input"])
    facts = native_profile_facts(profile)
    identity = _jsonable(
        {
            "profile_identity": profile,
            "run_id": profile,
            "input_path": str(expected["input"].resolve()),
            "input_sha256": specification.input_sha256,
            "physical_model_sha256": specification.physical_model_sha256,
            "resolved_config_sha256": resolved_config_sha256(specification),
            "resolved_output_parent_absolute": str(
                specification.expected_output_parent.resolve()
            ),
            "source_commit": "b" * 40,
            "direct_route_contract": facts["campaign_authorization"]["direct_route"],
        }
    )
    attempt_id = "halfwinadm001"
    scope = {
        "schema": GATE_CD_SCOPE_SCHEMA,
        "attempt_id": attempt_id,
        "identity": identity,
        "formal_route_readiness": {"launchable": True},
        "resource_contract": {
            "policy": "host_available_floor_v1",
            "minimum_available_bytes": 64 * 1024**3,
            "rss_hard_limit_bytes": None,
            "swap_policy": "observe_only",
            "stop_on_global_swap": False,
            "pss_sampling_policy": "disabled_by_profile",
            "uss_sampling_policy": "disabled_by_profile",
            "time_limit_mode": "none",
        },
        "cpu_policy": {
            "selection": "sampled_low_load_distinct_physical_cores_v1",
            "sample_seconds": 1.5,
            "busy_fallback_allowed": True,
            "exclusive_cpu_ownership": False,
            "worker_count": 1,
        },
        "parallel_neighbors": {
            "policy": "gate_cd_observational_neighbors_v1",
            "solver_candidates_block_admission": False,
            "unknown_solver_candidates_block_admission": False,
            "large_process_candidates_block_admission": False,
            "neighbors_modified": False,
        },
        "runtime_paths": _runtime_paths(profile, profile, attempt_id, tmp_path),
    }
    scope_path = tmp_path / f"{profile}.scope.json"
    scope_raw = (json.dumps(scope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    scope_path.write_bytes(scope_raw)
    scope_sha = hashlib.sha256(scope_raw).hexdigest()
    _validate_gate_cd_scope(
        scope_path,
        scope_sha,
        profile=profile,
        run_id=profile,
        expected_identity=identity,
        lock_directory=tmp_path,
    )
    with pytest.raises(Exception, match="exact reviewed profile/run"):
        _validate_gate_cd_scope(
            scope_path,
            scope_sha,
            profile=profile,
            run_id=f"{profile}-wrong",
            expected_identity=identity,
            lock_directory=tmp_path,
        )

    cache_root = tmp_path / f"{profile}.attempt-cache"
    cache_root.mkdir()
    cache_paths = {"root": cache_root}
    for key in ("tmp", "xdg", "pycache", "mpl"):
        cache_paths[key] = cache_root / key
        cache_paths[key].mkdir()
    (cache_paths["xdg"] / "fenics").mkdir()
    manifest = {
        "native_capacity_profile_identity": profile,
        "native_capacity_isolation": {
            "gate_cd_formal_admission": {
                "attempt_id": attempt_id,
                "attempt_cache_root": str(cache_root),
            }
        },
        "attempt_specific_runtime_cache": {
            "owner": "GateCD_formal_attempt_only",
            "attempt_id": attempt_id,
            **{key: str(path) for key, path in cache_paths.items()},
        },
    }
    environment = {
        "TMPDIR": str(cache_paths["tmp"]),
        "TMP": str(cache_paths["tmp"]),
        "TEMP": str(cache_paths["tmp"]),
        "XDG_CACHE_HOME": str(cache_paths["xdg"]),
        "PYTHONPYCACHEPREFIX": str(cache_paths["pycache"]),
        "MPLCONFIGDIR": str(cache_paths["mpl"]),
    }
    evidence = _task40_gate_cd_runtime_cache_evidence(
        manifest,
        environment=environment,
        jit_options_resolver=lambda: {
            "cache_dir": str(cache_paths["xdg"] / "fenics")
        },
    )
    assert evidence["cache_paths_verified_before_FE_dispatch"] is True
    assert "exact_cache_contract" not in evidence
    assert "tensor" not in evidence["environment"]
