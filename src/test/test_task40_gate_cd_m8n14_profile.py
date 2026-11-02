"""No-FE checks for Gate-CD's exact 1088-mode, 32-tensor-worker route."""
from __future__ import annotations

import hashlib
import json
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

from src.common.modes_3d import outgoing_port_modes_3d
from src.io.execution_plan import build_execution_plan
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
)
from src.io.native_capacity_profile import (
    TASK40_GATE_CD_M8N14_PARALLEL32_P6_DIRECT_PROFILE,
    native_profile_facts,
)
from src.runners.exact_cache_contract import (
    EXACT_CACHE_TEMPLATE_SCHEMA,
    GATE_CD_EXACT_CACHE_WORKER_POLICY,
    load_exact_cache_contract,
    materialize_gate_cd_exact_cache_contract,
)
from src.runners.p6_condensed_direct import (
    _build_task40_rectangle_inventory,
    _direct_run_contract,
    _validate_resolved_profile,
)
from src.runners.task40_gate_cd_formal_admission import (
    GATE_CD_PARALLEL32_PROFILE,
    GATE_CD_PARALLEL32_WORKERS,
    GATE_CD_SCOPE_SCHEMA,
    _choose_cpu_reservation,
    _runtime_paths,
    _validate_gate_cd_scope,
    gate_cd_runtime_lease,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/task40_gate_cd/gate_cd_0p7_mapped_m8n14_p6_direct_parallel32.dat"
PROFILE = TASK40_GATE_CD_M8N14_PARALLEL32_P6_DIRECT_PROFILE
PARENT_SHA = "6cf60807239dffc209b47336581e8bb50a5f4d986cba5bbdc06500f6271d3865"
ACTIVE_SHA = "333e201cd5bd368a6f1a70a02949ff3099fdb2c8f6c05e93fc419a77430be353"
INDICES_SHA = "1fc6bb7886a9858e3288ae45ee3ae50fea0bdf75881f03b52f45a26a3fe41fe1"
KEYS_SHA = "03c5894de4fd5597da93a2971a1914ffca955b61e39a9f8db173d0fd39beebb0"


def test_loader_binds_exact_1088_mode_profile_without_finite_dtn_claim():
    specification = load_and_resolve(INPUT)
    resolved = specification.as_jsonable()
    facts = native_profile_facts(PROFILE)
    route = _direct_run_contract(PROFILE)

    assert _validate_resolved_profile(resolved)["identity"] == PROFILE
    assert specification.identity["run_id"] == PROFILE
    assert resolved["comparison_group"] == "task40_gate_cd_m8n14_signed_subrectangle_parallel32"
    assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert facts["component_options"]["expected_global_cell_count"] == 27_600
    assert facts["component_options"]["mesh_axis_cell_counts"] == [5, 240, 23]
    assert facts["component_options"]["surface_quadrature"]["degree"] == 81
    assert facts["component_options"]["volume_quadrature"]["degree"] == 21
    assert facts["native_execution"]["mpi_size"] == 1
    assert facts["native_execution"]["math_threads"] == 1
    assert facts["native_execution"]["tensor_worker_count"] == 32
    assert facts["native_execution"]["lu_execution"] == "serial_single_mpi_rank_v1"
    assert facts["resources"]["minimum_available_bytes"] == 64 * 1024**3
    assert route["parent_count"] == 4488
    assert route["expected_mode_sha256"] == PARENT_SHA
    assert route["active_count"] == 1088
    assert route["active_sha256"] == ACTIVE_SHA
    assert route["signed_rectangle_bounds_mn"] == [-8, 8, -14, 1]
    assert route["selection_policy"] == "explicit_signed_subrectangle_from_parent_v1"
    assert resolved["output"]["write_visualization_files"] is False
    assert resolved["output"]["diffraction_order_max_n"] == 14


def test_actual_mode_objects_select_the_parent_ordered_signed_subrectangle(monkeypatch):
    specification = load_and_resolve(INPUT)
    payload = specification.as_jsonable()
    route = _direct_run_contract(PROFILE)
    cfg = simulation_config_3d_from_normalized(payload)
    cfg.stage4_dtn_order_policy = "explicit_signed_rectangle"
    cfg.task40_dtn_signed_rectangle_bounds_mn = tuple(route["parent_signed_bounds_mn"])
    cfg.stage4_dtn_quadrature_degree = 81
    cfg.task40_port_boundary_amplitude_scale_policy = "boundary_magnitude_scaled_r5_v1"

    parent_modes = tuple(outgoing_port_modes_3d(cfg))
    assert len(parent_modes) == 4488
    parent_rows = tuple(
        {
            "mode_index": index,
            "side": mode.side,
            "m": mode.m,
            "n": mode.n,
            "polarization": mode.polarization,
        }
        for index, mode in enumerate(parent_modes)
    )

    # The full manifest builder imports the MPI/PETSc solver module.  The
    # selector's key/index/order contract is exercised here with a no-solve
    # stub; the actual parent and active SHA are independently checked against
    # the production mode-object serialization in the case audit record.
    manifest_module = types.ModuleType("src.solvers.fullspace_dtn_action")
    manifest_module._canonical_json_bytes = lambda value: json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")

    def manifest_builder(modes, _cfg):
        assert len(modes) == 1088
        assert all(-8 <= int(mode.m) <= 8 and -14 <= int(mode.n) <= 1 for mode in modes)
        return tuple({"mode_index": index} for index, _mode in enumerate(modes)), b"", ACTIVE_SHA

    manifest_module.build_ordered_mode_manifest = manifest_builder
    monkeypatch.setitem(sys.modules, "src.solvers.fullspace_dtn_action", manifest_module)

    active, selection, indices = _build_task40_rectangle_inventory(
        (parent_modes, parent_rows, PARENT_SHA), cfg, route
    )
    assert len(active[0]) == 1088
    assert active[2] == ACTIVE_SHA
    assert selection["selected_parent_indices_sha256"] == INDICES_SHA
    assert selection["selected_signed_keys_sha256"] == KEYS_SHA
    assert len(indices) == 1088
    assert sum(mode.propagating for mode in active[0]) == 960
    assert sum(mode.power_per_unit_amplitude > 0 for mode in active[0]) == 1026


def test_execution_plan_uses_one_mpi_rank_with_32_exact_dynamic_cpus(tmp_path):
    specification = load_and_resolve(INPUT)
    run_directory = tmp_path / "gate-cd-m8n14"
    run_directory.mkdir()
    specification = replace(specification, expected_output_parent=tmp_path)
    cpus = list(range(32))
    plan = build_execution_plan(
        specification,
        run_directory,
        source_sha="a" * 64,
        python_executable=sys.executable,
        mpiexec_command="/usr/bin/mpiexec",
        worker_cpus_override=cpus,
    )
    assert plan.argv[:8] == (
        "/usr/bin/mpiexec", "-n", "1", "/usr/bin/numactl",
        "--interleave=0,1", "/usr/bin/taskset", "-c", ",".join(map(str, cpus)),
    )
    with pytest.raises(Exception, match="dynamic 32-CPU reservation"):
        build_execution_plan(
            specification,
            run_directory,
            source_sha="a" * 64,
            python_executable=sys.executable,
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=cpus[:-1],
        )
    with pytest.raises(Exception, match="dynamic 32-CPU reservation"):
        build_execution_plan(
            specification,
            run_directory,
            source_sha="a" * 64,
            python_executable=sys.executable,
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=[*cpus[:-1], cpus[-2]],
        )


def _parallel32_identity(tmp_path, template_sha256):
    return {
        "profile_identity": GATE_CD_PARALLEL32_PROFILE,
        "run_id": GATE_CD_PARALLEL32_PROFILE,
        "input_path": str(INPUT.resolve()),
        "input_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "physical_model_sha256": "2" * 64,
        "resolved_config_sha256": "3" * 64,
        "resolved_output_parent_absolute": str(tmp_path / "results"),
        "source_commit": "4" * 40,
        "direct_route_contract": {
            "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
            "exact_cache_contract_template_sha256": template_sha256,
        },
    }


def _parallel32_scope(tmp_path, template_sha256, *, worker_count=32, avoid=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    attempt_id = "n14attempt0001"
    identity = _parallel32_identity(tmp_path, template_sha256)
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
            "worker_count": worker_count,
            "avoid_active_solver_affinity_overlap": avoid,
        },
        "parallel_neighbors": {
            "policy": "gate_cd_observational_neighbors_v1",
            "solver_candidates_block_admission": False,
            "unknown_solver_candidates_block_admission": False,
            "large_process_candidates_block_admission": False,
            "neighbors_modified": False,
        },
        "runtime_paths": _runtime_paths(
            GATE_CD_PARALLEL32_PROFILE,
            GATE_CD_PARALLEL32_PROFILE,
            attempt_id,
            tmp_path,
        ),
    }
    path = tmp_path / "n14.scope.json"
    raw = (json.dumps(scope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest(), scope, identity


def test_parallel32_scope_and_fresh_lease_require_32_distinct_cpus(tmp_path):
    template_sha256 = "a" * 64
    path, scope_sha256, _scope, identity = _parallel32_scope(
        tmp_path, template_sha256
    )
    _validate_gate_cd_scope(
        path,
        scope_sha256,
        profile=GATE_CD_PARALLEL32_PROFILE,
        run_id=GATE_CD_PARALLEL32_PROFILE,
        expected_identity=identity,
        lock_directory=tmp_path,
    )

    selected_cpus = list(range(32))

    def selector(sample_seconds, proc_root, *, worker_count):
        assert sample_seconds == 1.5
        assert worker_count == GATE_CD_PARALLEL32_WORKERS
        return {
            "supervisor_cpu": 32,
            "worker_cpus": selected_cpus,
            "worker_count": worker_count,
            "active_solver_affinity_avoidance": True,
            "exclusive_cpu_ownership": False,
        }

    with gate_cd_runtime_lease(
        GATE_CD_PARALLEL32_PROFILE,
        GATE_CD_PARALLEL32_PROFILE,
        scope_path=path,
        scope_sha256=scope_sha256,
        expected_identity=identity,
        submission_mode="fresh_check",
        lock_directory=tmp_path,
        cpu_selector=selector,
    ) as lease:
        evidence = lease.summary()
        assert evidence["cpu_reservation"]["worker_cpus"] == selected_cpus
        assert evidence["canonical_heavy_lock_touched"] is False
        assert not lease.reservation_path.exists()
        assert not lease.cache_root.exists()

    bad_path, bad_sha, _, bad_identity = _parallel32_scope(
        tmp_path / "bad_count", template_sha256, worker_count=31
    )
    with pytest.raises(Exception, match="dynamic shared-CPU policy"):
        _validate_gate_cd_scope(
            bad_path,
            bad_sha,
            profile=GATE_CD_PARALLEL32_PROFILE,
            run_id=GATE_CD_PARALLEL32_PROFILE,
            expected_identity=bad_identity,
            lock_directory=tmp_path / "bad_count",
        )
    bad_path, bad_sha, _, bad_identity = _parallel32_scope(
        tmp_path / "no_avoidance", template_sha256, avoid=False
    )
    with pytest.raises(Exception, match="dynamic shared-CPU policy"):
        _validate_gate_cd_scope(
            bad_path,
            bad_sha,
            profile=GATE_CD_PARALLEL32_PROFILE,
            run_id=GATE_CD_PARALLEL32_PROFILE,
            expected_identity=bad_identity,
            lock_directory=tmp_path / "no_avoidance",
        )


def test_cpu_selector_avoids_active_solver_cores_and_keeps_supervisor_distinct(
    monkeypatch,
):
    from src.runners import task40_d07c_g5_join as g5

    candidates = [
        {
            "cpu": cpu,
            "package": 0,
            "core": cpu,
            "sampled_utilization": cpu / 1000,
            "heavy_neighbor_affinity_overlap": False,
        }
        for cpu in range(40)
    ]
    sampled = {
        "candidate_topology_and_load": candidates,
        "neighbor_observation": {
            "processes": [
                {"solver_role_observation": True, "affinity": [4, 5]},
            ]
        },
    }
    monkeypatch.setattr(g5, "_core", lambda cpu: (0, int(cpu)))
    monkeypatch.setattr(
        g5,
        "choose_g5_cpu_reservation",
        lambda **_kwargs: sampled,
    )
    reservation = _choose_cpu_reservation(
        1.5, "/unused", worker_count=GATE_CD_PARALLEL32_WORKERS
    )
    assert len(reservation["worker_cpus"]) == 32
    assert len(set(reservation["worker_cpus"])) == 32
    assert reservation["supervisor_cpu"] not in reservation["worker_cpus"]
    assert not ({4, 5} & set(reservation["worker_cpus"]))
    assert not ({4, 5} & {reservation["supervisor_cpu"]})
    assert reservation["active_solver_affinity_avoidance"] is True


def test_exact_cache_template_materializes_and_loads_attempt_bound_contract(tmp_path):
    payload = {"resolved": "Gate-CD M8/N14", "degree": 6, "q": 21}
    payload_sha256 = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    source_sha = "b" * 40
    attempt_root = tmp_path / "attempt"
    (attempt_root / "tensor").mkdir(parents=True)
    (attempt_root / "carrier").mkdir()
    template = {
        "schema": EXACT_CACHE_TEMPLATE_SCHEMA,
        "source_sha": source_sha,
        "resolved_payload_sha256": payload_sha256,
        "worker_cpu_policy": GATE_CD_EXACT_CACHE_WORKER_POLICY,
        "worker_count": 32,
        "tensor_root_policy": "attempt_cache_root/tensor",
        "carrier_root_policy": "attempt_cache_root/carrier",
        "operator_identity": {"scalar": "complex128", "q": 21, "degree": 6},
    }
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template, sort_keys=True, separators=(",", ":")))
    template_sha256 = hashlib.sha256(template_path.read_bytes()).hexdigest()
    worker_cpus = list(range(32))
    runtime = materialize_gate_cd_exact_cache_contract(
        template_path,
        template_sha256,
        target_path=tmp_path / "run" / "exact_cache_runtime_contract.json",
        source_sha=source_sha,
        resolved_payload=payload,
        runtime_cache_root=attempt_root,
        worker_cpus=worker_cpus,
        attempt_id="n14attempt0001",
    )
    loaded = load_exact_cache_contract(
        runtime["path"],
        runtime["sha256"],
        source_sha=source_sha,
        resolved_payload=payload,
        expected_worker_cpus=worker_cpus,
        expected_attempt_id="n14attempt0001",
        expected_template_sha256=template_sha256,
        expected_cache_root=attempt_root,
    )
    assert loaded["raw"]["cpus"] == worker_cpus
    assert Path(loaded["raw"]["root"]) == attempt_root / "tensor"
    assert Path(loaded["carrier"]["root"]) == attempt_root / "carrier"
    with pytest.raises(ValueError, match="CPU list differs"):
        load_exact_cache_contract(
            runtime["path"],
            runtime["sha256"],
            source_sha=source_sha,
            resolved_payload=payload,
            expected_worker_cpus=worker_cpus[::-1],
            expected_attempt_id="n14attempt0001",
            expected_template_sha256=template_sha256,
            expected_cache_root=attempt_root,
        )


def test_formal_helper_accepts_the_exact_32_cpu_runtime_reservation(tmp_path):
    from scripts.gate_cd_formal_once import (
        _parse_cpu_list,
        _wait_for_runtime_cpu_reservation,
    )

    assert _parse_cpu_list("0-3,7,10-11") == {0, 1, 2, 3, 7, 10, 11}
    template_sha256 = "a" * 64
    path, scope_sha256, scope, _identity = _parallel32_scope(
        tmp_path, template_sha256
    )
    worker_cpus = list(range(32))
    cpu_reservation = {
        "supervisor_cpu": 32,
        "worker_cpu": worker_cpus[0],
        "worker_cpus": worker_cpus,
        "active_solver_affinity_avoidance": True,
        "excluded_active_solver_cpus": [39],
        "excluded_active_solver_cores": [[0, 39]],
        "selected_topology": [
            {"cpu": cpu, "package": 0, "core": cpu}
            for cpu in [32, *worker_cpus]
        ],
    }
    reservation = {
        "schema": "task40.gate_cd.formal_one_shot_submission.v1",
        "profile_identity": GATE_CD_PARALLEL32_PROFILE,
        "run_id": GATE_CD_PARALLEL32_PROFILE,
        "attempt_id": scope["attempt_id"],
        "scope_sha256": scope_sha256,
        "submission_mode": "runtime",
        "cpu_reservation": cpu_reservation,
    }
    reservation_path = Path(scope["runtime_paths"]["one_shot_reservation"])
    reservation_path.write_text(json.dumps(reservation))
    sidecar = {
        "scope_path": str(path),
        "scope_sha256": scope_sha256,
        "lock_directory": str(tmp_path.resolve()),
    }
    package = {
        "profile_identity": GATE_CD_PARALLEL32_PROFILE,
        "run_id": GATE_CD_PARALLEL32_PROFILE,
        "attempt_id": scope["attempt_id"],
    }
    actual, _, _ = _wait_for_runtime_cpu_reservation(
        sidecar, package, timeout_seconds=0
    )
    assert actual["cpu_reservation"]["worker_cpus"] == worker_cpus
