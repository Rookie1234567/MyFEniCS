from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import gate_cd_formal_once as execution_helper
from scripts.gate_cd_formal_once import (
    _require_final_package,
    _require_systemd_unit_not_loaded,
    _validate_live_profile_contract,
    _validate_systemd_argv,
    _verify_prelaunch_output_parent,
    _wait_for_runtime_cpu_reservation,
    submit_once,
    validate_package_sidecar,
)


def _cache_policy(normalized=False, *, witnessed=False):
    return {
        "identity": "profile_selected_mapped_geometry_cache_v1",
        "geometry_identity_policy": "mapped_exact",
        "mapped_geometry_translation_invariant": normalized,
        "translation_normalized_candidate": True,
        "translation_equivalence_status": (
            "PASS_BOUNDED_TRANSLATION_EQUIVALENCE"
            if witnessed
            else "SELECTED_EXACT_PHYSICAL_COORDINATE_KEYS"
        ),
        "translation_equivalence_witness": (
            {
                "sha256": "f" * 64,
                "scope": "active_local_tensor_schur_recovery_trace_rhs_same_storage",
                "max_relative_error": 1.0e-12,
                "reviewed_tolerance": 1.0e-11,
            }
            if witnessed
            else None
        ),
        "cell_tensor_key_includes_material_tag": True,
        "local_recovery_key_includes_orientation": True,
    }


def _final_package():
    return {
        "schema": "task40.gate_cd.formal_package.v1",
        "execution_authorized": True,
        "route_readiness": {"launchable": True},
        "quadrature_contract": {
            "volume_degree": 21,
            "volume_rule": "default",
            "surface_degree": 81,
            "surface_rule": "default",
        },
        "mapped_geometry_identity": "mapped_exact",
        "translation_normalized_cache": True,
        "mapped_geometry_cache_policy": _cache_policy(True, witnessed=True),
    }


def _package():
    return {
        "schema": "task40.gate_cd.formal_package.v1",
        "execution_authorized": False,
        "route_readiness": {"launchable": False},
    }


def test_current_draft_package_is_explicitly_non_executable():
    with pytest.raises(ValueError, match="not executable"):
        _require_final_package(_package())


def test_frozen_package_requires_reviewed_q_and_exact_geometry_identity():
    package = _final_package()
    package["quadrature_contract"]["volume_degree"] = 27
    _require_final_package(package)
    package["quadrature_contract"]["volume_degree"] = 19
    with pytest.raises(ValueError, match="q15/q21/q27"):
        _require_final_package(package)
    package["quadrature_contract"]["volume_degree"] = 21
    package["translation_normalized_cache"] = False
    with pytest.raises(ValueError, match="cache identity and translation"):
        _require_final_package(package)


def test_translation_normalized_package_requires_matching_bounded_witness():
    package = _final_package()
    package["translation_normalized_cache"] = True
    package["mapped_geometry_cache_policy"] = _cache_policy(True, witnessed=True)
    _require_final_package(package)
    package["mapped_geometry_cache_policy"]["translation_equivalence_witness"] = None
    with pytest.raises(ValueError, match="bounded witness"):
        _require_final_package(package)


def test_live_profile_contract_uses_component_and_campaign_quadrature_and_cache():
    package = _final_package()
    volume = {
        "production_ffcx_metadata": {"degree": 15, "rule": "default"},
        "production_ffcx_metadata_role": (
            "pre_override_automatic_ffcx_default_baseline_not_selected_operator"
        ),
        "candidate_degrees": [15, 21, 27],
        "degree": 21,
        "rule": "default",
        "authority": "three_actual_cell_p6_q15_q21_q27_tensor_schur_recovery_witness",
        "status": "SELECTED_Q21_BOUNDED_LOCAL_CANDIDATE_NOT_GLOBAL_ERROR_BOUND",
        "selection_witness": {
            "path": "docs/task40para_phi90_mesh_modes_direct/outcomes/records/gate_cd_local_cache_quadrature_q21_witness_20261101.json",
            "sha256": "3b012b12005aed7fc809beb349a511c27c8f5a28b74b054f130429986951735e",
            "scope": "three_actual_tag106_worst_taper_cells; q15_vs_q21_and_q21_vs_q27_tensor_schur_recovery_trace_rhs",
            "selected_q21_vs_q27_max_relative_frobenius": 2.025688753701772e-08,
            "q15_vs_q21_max_relative_frobenius": 0.0004150388686260537,
            "global_quadrature_error_bound": "NOT_ESTABLISHED",
        },
    }
    facts = {
        "component_options": {
            "surface_quadrature": {"degree": 81, "rule": "default"},
            "volume_quadrature": volume,
            "mapped_geometry_cache_policy": _cache_policy(True, witnessed=True),
        },
        "campaign_authorization": {
            "direct_route": {
                "surface_quadrature_degree": 81,
                "volume_quadrature": dict(volume),
                "geometry_identity_policy": "mapped_exact",
                "mapped_geometry_cache_identity": "profile_selected_mapped_geometry_cache_v1",
                "mapped_geometry_translation_invariant": True,
            }
        },
        "condensed_route": {
            "geometry_identity_policy": "mapped_exact",
            "mapped_geometry_translation_invariant": True,
        },
    }
    _validate_live_profile_contract(package, facts)
    bad_facts = json.loads(json.dumps(facts))
    bad_facts["campaign_authorization"]["direct_route"][
        "surface_quadrature_degree"
    ] = 161
    with pytest.raises(ValueError, match="campaign surface"):
        _validate_live_profile_contract(package, bad_facts)
    bad_volume_witness = json.loads(json.dumps(facts))
    bad_volume_witness["campaign_authorization"]["direct_route"][
        "volume_quadrature"
    ]["selection_witness"]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="quadrature/witness"):
        _validate_live_profile_contract(package, bad_volume_witness)
    bad_cache = json.loads(json.dumps(facts))
    bad_cache["component_options"]["mapped_geometry_cache_policy"][
        "mapped_geometry_translation_invariant"
    ] = False
    with pytest.raises(ValueError, match="exact live profile facts"):
        _validate_live_profile_contract(package, bad_cache)


def test_sidecar_cannot_drift_from_package_bytes(tmp_path):
    package = _package()
    package["execution_authorized"] = True
    package["route_readiness"] = {"launchable": True}
    package["quadrature_contract"] = {
        "volume_degree": 15, "surface_degree": 81, "surface_rule": "default"
    }
    package["mapped_geometry_identity"] = "mapped_exact"
    package["translation_normalized_cache"] = False
    package["mapped_geometry_cache_policy"] = _cache_policy()
    package["source_commit"] = "a" * 40
    package["input_sha256"] = "b" * 64
    package["physical_model_sha256"] = "c" * 64
    package["resolved_config_sha256"] = "d" * 64
    package_path = tmp_path / "package.json"
    sidecar_path = tmp_path / "sidecar.json"
    package_path.write_text(json.dumps(package))
    sidecar_path.write_text(
        json.dumps(
            {
                "schema": "task40.gate_cd.formal_sidecar.v1",
                "package_sha256": "0" * 64,
                "source_commit": "a" * 40,
                "input_sha256": "b" * 64,
                "physical_model_sha256": "c" * 64,
                "resolved_config_sha256": "d" * 64,
            }
        )
    )
    with pytest.raises(ValueError, match="exact package bytes"):
        validate_package_sidecar(package_path, sidecar_path)


def test_systemd_argv_requires_one_reviewed_user_service_and_run_case(tmp_path):
    log = tmp_path / "service.log"
    unit = "task40-gate-cd-attempt.service"
    activation = "/work/scripts/activate_task40_phi90_pord64.sh"
    environment = {
        "HWLOC_COMPONENTS": "-x86",
        "TASK40_GATE_CD_SCOPE_PATH": "/tmp/scope.json",
        "TASK40_GATE_CD_SCOPE_SHA256": "e" * 64,
        "TASK40_GATE_CD_LOCK_DIRECTORY": "/tmp/gate-cd-lock",
        "TASK40_GATE_CD_SUBMISSION_MODE": "runtime",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION": "1",
        "TASK39EXTRA_INT64_ACTIVATION": "1",
        "TASK39EXTRA_PORD64_ACTIVATION": "1",
    }
    argv = [
        "systemd-run", "--user", "--no-block", f"--unit={unit}",
        "--property=Type=exec", "--property=Restart=no",
        "--property=RuntimeMaxSec=infinity", "--property=KillMode=mixed",
        "--property=TimeoutStopSec=infinity",
        "--property=LimitNOFILE=65536:1048576",
        f"--property=StandardOutput=append:{log}",
        f"--property=StandardError=append:{log}",
    ]
    argv.extend(f"--setenv={key}={value}" for key, value in environment.items())
    argv.extend(
        [
            "/bin/bash",
            "-lc",
            f"cd /work && source {activation} && exec python scripts/run_case.py input.dat",
        ]
    )
    sidecar = {
        "service_unit": unit,
        "append_log_path": str(log),
        "scope_path": "/tmp/scope.json",
        "scope_sha256": "e" * 64,
        "lock_directory": "/tmp/gate-cd-lock",
        "activation_script": activation,
        "shell_command": argv[-1],
        "service_environment": environment,
        "systemd_run_argv": argv,
    }
    assert _validate_systemd_argv(sidecar) == sidecar["systemd_run_argv"]
    sidecar["systemd_run_argv"].remove("--property=LimitNOFILE=65536:1048576")
    with pytest.raises(ValueError, match="LimitNOFILE=65536:1048576"):
        _validate_systemd_argv(sidecar)
    sidecar["systemd_run_argv"].insert(
        8, "--property=LimitNOFILE=65536:1048576"
    )
    sidecar["shell_command"] += " # stale declaration"
    with pytest.raises(ValueError, match="differs from the actual systemd argv"):
        _validate_systemd_argv(sidecar)
    sidecar["shell_command"] = argv[-1]
    sidecar["systemd_run_argv"][-1] = (
        "cd /repo && exec python -m src.runners.task038_input_worker"
    )
    sidecar["shell_command"] = sidecar["systemd_run_argv"][-1]
    with pytest.raises(ValueError, match="standard run_case"):
        _validate_systemd_argv(sidecar)


def test_z10_systemd_argv_accepts_full_nofile_and_cache_guard_shell(tmp_path):
    from src.runners.task40_gate_cd_prelu_pause import PRELU_ENVIRONMENT_FIELDS

    profile = "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
    attempt_id = "gcdz10m8n2-20261104-r1"
    unit = "task40-gcd-z10-m8n2-r1-4ec87416.service"
    attempt_root = Path("/tmp") / f"task40_gate_cd_formal_attempt_{attempt_id}"
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(
        json.dumps({"runtime_paths": {"attempt_cache_root": str(attempt_root)}}),
        encoding="utf-8",
    )
    activation = str(
        (tmp_path / "scripts" / "activate_task40_phi90_pord64.sh").resolve()
    )
    hook_directory = str(Path(activation).parent)
    contract_path = str((tmp_path / "cache_reuse_contract.json").resolve())
    contract_sha = "a" * 64
    log_path = str((tmp_path / "worker.log").resolve())
    pause = {
        "ready_path": str(attempt_root / "pre_lu_pause" / "ready.json"),
        "release_path": str(attempt_root / "pre_lu_pause" / "release.json"),
        "accepted_path": str(attempt_root / "pre_lu_pause" / "accepted.json"),
        "service_unit": unit,
        "attempt_id": attempt_id,
        "package_sha256": "b" * 64,
        "original272_unit": "task40-gcd-m8n2-9bf54c110b.service",
        "original272_invocation_id": "c3e29ca475ba40cba35251823ca7f699",
    }
    reuse = {
        "mode": "verified_cache_only_v1",
        "contract_path": contract_path,
        "contract_sha256": contract_sha,
        "target_attempt_cache_root": str(attempt_root),
        "hook_directory": hook_directory,
    }
    environment = {
        "HWLOC_COMPONENTS": "-x86",
        "TASK40_GATE_CD_SCOPE_PATH": str(scope_path.resolve()),
        "TASK40_GATE_CD_SCOPE_SHA256": "c" * 64,
        "TASK40_GATE_CD_LOCK_DIRECTORY": "/tmp",
        "TASK40_GATE_CD_SUBMISSION_MODE": "runtime",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "TASK40_GATE_CD_ATTEMPT_CACHE_ROOT": str(attempt_root),
        "TASK40_EXACT_CACHE_TEMPLATE_PATH": str(
            (tmp_path / "exact_cache_template.json").resolve()
        ),
        "TASK40_EXACT_CACHE_TEMPLATE_SHA256": "d" * 64,
        "TASK40_EXACT_CACHE_REUSE_MODE": reuse["mode"],
        "TASK40_EXACT_CACHE_REUSE_CONTRACT": contract_path,
        "TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256": contract_sha,
        "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION": "1",
        "TASK39EXTRA_INT64_ACTIVATION": "1",
        "TASK39EXTRA_PORD64_ACTIVATION": "1",
        **{
            env_name: pause[field]
            for field, env_name in PRELU_ENVIRONMENT_FIELDS.items()
        },
    }
    shell = (
        f"source {activation} && ulimit -Sn 65536 && "
        'test "$(ulimit -Sn)" = 65536 && '
        f"export PYTHONPATH={hook_directory}:$PYTHONPATH && "
        "python -c 'import os; assert os.environ.get("
        "\"TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE\") == \"1\"' && "
        "exec python scripts/run_case.py /tmp/recovery-input.dat"
    )
    argv = [
        "systemd-run", "--user", "--no-block", f"--unit={unit}",
        "--property=Type=exec", "--property=Restart=no",
        "--property=RuntimeMaxSec=infinity", "--property=KillMode=mixed",
        "--property=TimeoutStopSec=infinity",
        "--property=LimitNOFILE=65536:1048576",
        f"--property=StandardOutput=append:{log_path}",
        f"--property=StandardError=append:{log_path}",
    ]
    argv.extend(f"--setenv={key}={value}" for key, value in environment.items())
    argv.extend(["/bin/bash", "-lc", shell])
    sidecar = {
        "profile_identity": profile,
        "service_unit": unit,
        "scope_path": str(scope_path),
        "scope_sha256": environment["TASK40_GATE_CD_SCOPE_SHA256"],
        "lock_directory": "/tmp",
        "attempt_cache_root": str(attempt_root),
        "exact_cache_template_path": environment["TASK40_EXACT_CACHE_TEMPLATE_PATH"],
        "exact_cache_template_sha256": environment["TASK40_EXACT_CACHE_TEMPLATE_SHA256"],
        "activation_script": activation,
        "append_log_path": log_path,
        "shell_command": shell,
        "systemd_run_argv": argv,
        "service_environment": environment,
        "pre_lu_pause": pause,
        "verified_cache_reuse": reuse,
    }
    assert _validate_systemd_argv(sidecar) == argv
    sidecar["service_environment"]["TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE"] = "1"
    sidecar["systemd_run_argv"].insert(
        sidecar["systemd_run_argv"].index("/bin/bash"),
        "--setenv=TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE=1",
    )
    with pytest.raises(ValueError, match="active marker must be created by Python startup"):
        _validate_systemd_argv(sidecar)


def test_systemd_unit_state_query_is_bounded_and_fails_closed(monkeypatch):
    observed = []

    def run(argv, **kwargs):
        observed.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="LoadState=not-found\n", stderr="")

    monkeypatch.setattr(execution_helper.subprocess, "run", run)
    assert _require_systemd_unit_not_loaded("task40-gate-cd-test.service") == "not-found"
    assert observed[0][1]["timeout"] == 5.0

    monkeypatch.setattr(
        execution_helper.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="LoadState=loaded\n", stderr=""),
    )
    with pytest.raises(ValueError, match="already exists"):
        _require_systemd_unit_not_loaded("task40-gate-cd-test.service")

    monkeypatch.setattr(
        execution_helper.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="bus unavailable"),
    )
    with pytest.raises(RuntimeError, match="query failed"):
        _require_systemd_unit_not_loaded("task40-gate-cd-test.service")

    def timeout(*_a, **_k):
        raise execution_helper.subprocess.TimeoutExpired("systemctl", 5.0)

    monkeypatch.setattr(execution_helper.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="bounded unit-state query"):
        _require_systemd_unit_not_loaded("task40-gate-cd-test.service")


def _make_bootstrap_residue(tmp_path):
    import hashlib

    output_parent = tmp_path / "output-parent"
    attempt = output_parent / "20261101T100144.202495Z"
    attempt.mkdir(parents=True)
    profile = "task40_gate_cd_0p7_mapped_m8n64_p6_direct_v1"
    run_id = profile
    source = "c73f3ba7f934fc54a436e7f7f5d417dea2c9fc16"
    input_bytes = b"frozen input bytes\n"
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    physical_sha = "a" * 64
    resolved = {
        "run_id": run_id,
        "solver": {"native_capacity_profile": profile},
        "provenance": {
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "expected_output_parent": str(output_parent.resolve()),
        },
    }
    resolved_bytes = (json.dumps(resolved, sort_keys=True, indent=2) + "\n").encode()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    manifest = {
        "run_id": run_id,
        "source_sha": source,
        "input_path": str((tmp_path / "input.dat").resolve()),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "native_capacity_profile_identity": profile,
        "output_directory": str(attempt.resolve()),
    }
    summary = {
        "run_id": run_id,
        "status": "launching",
        "result_classification": "not_run",
        "exit_status": None,
        "resource_authority": {"status": "not_sampled"},
        "output_directory": str(attempt.resolve()),
        "numerical_output_directory": str(attempt / "numerical_output"),
    }
    files = {
        "input_original.dat": input_bytes,
        "input_sha256.txt": f"{input_sha}\n".encode(),
        "physical_model_sha256.txt": f"{physical_sha}\n".encode(),
        "resolved_config.json": resolved_bytes,
        "run_manifest.json": (json.dumps(manifest) + "\n").encode(),
        "run_summary.json": (json.dumps(summary) + "\n").encode(),
        "source_sha.txt": f"{source}\n".encode(),
    }
    for name, content in files.items():
        (attempt / name).write_bytes(content)
    package = {
        "input_path": str(tmp_path / "input.dat"),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "profile_identity": profile,
        "run_id": run_id,
        "source_commit": "d" * 40,
        "prelaunch_output_residue_allowlist": {
            "attempt_id": attempt.name,
            "attempt_directory": str(attempt.resolve()),
            "prior_source_commit": source,
            "files": {
                name: hashlib.sha256(content).hexdigest()
                for name, content in files.items()
            },
        },
    }
    expected_identity = {
        "profile_identity": profile,
        "run_id": run_id,
        "input_path": str((tmp_path / "input.dat").resolve()),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_output_parent_absolute": str(output_parent.resolve()),
    }
    return output_parent, package, expected_identity


def _make_raw_tensor_summary_residue(tmp_path):
    import hashlib

    output_parent = tmp_path / "output-parent"
    attempt_id = "20261104T010238.408463Z"
    attempt = output_parent / attempt_id
    (attempt / "numerical_output").mkdir(parents=True)
    (attempt / "watchdog").mkdir()
    profile = "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
    run_id = profile
    prior_source = "b" * 40
    input_path = str((tmp_path / "input.dat").resolve())
    input_bytes = b"frozen z10 M8N2 input\n"
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    physical_sha = "a" * 64
    resolved = {
        "run_id": run_id,
        "solver": {"native_capacity_profile": profile},
        "provenance": {
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "expected_output_parent": str(output_parent.resolve()),
        },
    }
    resolved_bytes = (json.dumps(resolved, sort_keys=True, indent=2) + "\n").encode()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    (tmp_path / "input.dat").write_bytes(input_bytes)

    cache_root = tmp_path / "failed-attempt-cache" / "tensor"
    cache_root.mkdir(parents=True)
    tensor_bytes = [b"tensor-a", b"tensor-b"]
    for index, payload in enumerate(tensor_bytes):
        folder = cache_root / f"key-{index}"
        folder.mkdir()
        (folder / "tensor.npy").write_bytes(payload)
        (folder / "complete.json").write_text("{}\n")
    cache_evidence = {
        "root": str(cache_root.resolve()),
        "complete_marker_count": 2,
        "tensor_payload_count": 2,
        "tensor_payload_bytes": sum(map(len, tensor_bytes)),
    }
    expected_failure = (
        "global raw tensor evaluation failed before broadcast: rank 0: "
        "OSError: [Errno 24] Too many open files"
    )
    workflow = {
        "phase": "setup",
        "facts": {
            "failed_stage": "p6_direct_raw_tensor_pool_lock",
            "exception_type": "RuntimeError",
            "exception_message": expected_failure,
        },
    }
    direct_summary = {
        "status": "FAILED",
        "failed_phase": "setup",
        "failed_stage": "p6_direct_raw_tensor_pool_lock",
        "exception_type": "RuntimeError",
        "exception_message": expected_failure,
        "run_id": run_id,
        "profile": profile,
        "source_sha": prior_source,
        "outer_ksp": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "p4_operator": "NOT_BUILT",
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        "exact_cache_execution": {"raw": {"root": str(cache_root.resolve())}},
    }
    stage_rows = [
        {
            "stage": "p6_direct_raw_tensor_class_progress",
            "facts": {"done": 2, "total": 2},
        },
        {
            "stage": "p6_direct_raw_tensor_pool_lock",
            "facts": {
                "event_type": "raw_tensor_pool_lock_released",
                "batch_completed": True,
                "batch_classes": 2,
            },
        },
        {
            "stage": "TASK40_GATE_CD_FIN0_STI_Z10_M8N2_P6_DIRECT_M8N64_FAILED",
            "facts": {
                "failed_stage": "p6_direct_raw_tensor_pool_lock",
                "exception_message": expected_failure,
            },
        },
    ]
    manifest = {
        "run_id": run_id,
        "source_sha": prior_source,
        "input_path": input_path,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "native_capacity_profile_identity": profile,
        "output_directory": str(attempt.resolve()),
    }
    summary = {
        "run_id": run_id,
        "status": "finished",
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
        "output_directory": str(attempt.resolve()),
        "numerical_output_directory": str((attempt / "numerical_output").resolve()),
        "resource_authority": {
            "classification": "WORKER_FAILED",
            "leader_exit_code": 4,
            "descendants_cleared": True,
            "remaining_child_pids": [],
        },
    }
    watchdog = {
        "classification": "WORKER_FAILED",
        "leader_exit_code": 4,
        "descendants_cleared": True,
        "remaining_child_pids": [],
    }
    files = {
        "exact_cache_runtime_contract.json": b'{"schema":"test"}\n',
        "gate_cd_runtime_environment.json": b'{"schema":"test"}\n',
        "input_original.dat": input_bytes,
        "input_sha256.txt": f"{input_sha}\n".encode(),
        "p6_condensed_direct_summary.json": json.dumps(direct_summary).encode() + b"\n",
        "physical_model_sha256.txt": f"{physical_sha}\n".encode(),
        "resolved_config.json": resolved_bytes,
        "run_manifest.json": json.dumps(manifest).encode() + b"\n",
        "run_summary.json": json.dumps(summary).encode() + b"\n",
        "source_sha.txt": f"{prior_source}\n".encode(),
        "stages.jsonl": b"".join(
            json.dumps(row).encode() + b"\n" for row in stage_rows
        ),
        "task40_gate-cd_m8n64_finite_parent_parent_mode_manifest.json": b"{}\n",
        "task40_m8n64_active_mode_manifest.json": b"{}\n",
        "task40_m8n64_mode_index_map.json": b"{}\n",
        "workflow_phase.json": json.dumps(workflow).encode() + b"\n",
        "workstation_isolation.json": b'{"schema":"test"}\n',
        "watchdog/resources.jsonl": b'{"sample":1}\n',
        "watchdog/summary.json": json.dumps(watchdog).encode() + b"\n",
        "watchdog/worker.log": expected_failure.encode() + b"\n",
    }
    for relative, content in files.items():
        (attempt / relative).write_bytes(content)

    package = {
        "profile_identity": profile,
        "run_id": run_id,
        "source_commit": "c" * 40,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "prelaunch_output_residue_allowlist": {
            "schema": "task40.gate_cd.prelaunch_output_residue_allowlist.v2",
            "attempts": [
                {
                    "attempt_id": attempt_id,
                    "attempt_directory": str(attempt.resolve()),
                    "prior_source_commit": prior_source,
                    "classification": "worker_failed_gate_cd_raw_tensor_summary",
                    "files": {
                        relative: hashlib.sha256(content).hexdigest()
                        for relative, content in files.items()
                    },
                    "directories": ["numerical_output", "watchdog"],
                    "raw_tensor_cache_evidence": cache_evidence,
                }
            ],
        },
    }
    expected_identity = {
        "profile_identity": profile,
        "run_id": run_id,
        "input_path": input_path,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_output_parent_absolute": str(output_parent.resolve()),
    }
    return output_parent, package, expected_identity, cache_root


def _make_signed_mode_selection_residue(tmp_path):
    import hashlib

    from scripts.gate_cd_formal_once import _GATE_CD_SIGNED_SELECTION_RESIDUE

    output_parent = tmp_path / "output-parent"
    attempt_id = _GATE_CD_SIGNED_SELECTION_RESIDUE["attempt_id"]
    attempt = output_parent / attempt_id
    (attempt / "numerical_output").mkdir(parents=True)
    (attempt / "watchdog").mkdir()
    profile = "task40_gate_cd_0p7_mapped_m8n14_p6_direct_parallel32_v1"
    run_id = profile
    prior_source = _GATE_CD_SIGNED_SELECTION_RESIDUE["source_commit"]
    input_path = str((tmp_path / "input.dat").resolve())
    input_bytes = b"Gate-CD M8N14 signed-window input\n"
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    physical_sha = "a" * 64
    resolved = {
        "run_id": run_id,
        "solver": {"native_capacity_profile": profile},
        "provenance": {
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "expected_output_parent": str(output_parent.resolve()),
        },
    }
    resolved_bytes = (json.dumps(resolved, sort_keys=True, indent=2) + "\n").encode()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    manifest = {
        "run_id": run_id,
        "source_sha": prior_source,
        "input_path": input_path,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "native_capacity_profile_identity": profile,
        "output_directory": str(attempt.resolve()),
        "status": "finished",
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
    }
    summary = {
        "run_id": run_id,
        "status": "finished",
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
        "output_directory": str(attempt.resolve()),
        "numerical_output_directory": str((attempt / "numerical_output").resolve()),
        "resource_authority": {
            "classification": "WORKER_FAILED",
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "leader_exit_code": 4,
        },
    }
    workflow = {
        "phase": "setup",
        "facts": {
            "failed_stage": "physical_mode_inventory_reused",
            "exception_type": "ValueError",
            "exception_message": "operator selection policy is unsupported",
        },
    }
    mode_inventory = {
        "active_mode_count": 1088,
        "active_mode_sha256": (
            "333e201cd5bd368a6f1a70a02949ff3099fdb2c8f6c05e93fc419a77430be353"
        ),
    }
    direct_summary = {
        "status": "FAILED",
        "result_classification": "TASK40_GATE_CD_M8N14_P6_DIRECT_M8N64_FAILED",
        "run_id": run_id,
        "profile": profile,
        "source_sha": prior_source,
        "failed_phase": "setup",
        "failed_stage": "physical_mode_inventory_reused",
        "exception_type": "ValueError",
        "exception_message": "operator selection policy is unsupported",
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        "mode_inventory": mode_inventory,
        "mesh_evidence": {
            "status": "PASS",
            "scope": "LIVE_MAPPED_MESH_AND_P6_SPACE_NO_MATRIX_OR_FACTOR",
            "global_matrix_built": False,
            "factor_built": False,
        },
        "outer_ksp": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "p4_operator": "NOT_BUILT",
    }
    stages = [
        {"stage": "workflow_started", "facts": {}},
        {"stage": "p6_direct_resolved_profile_bound", "facts": {}},
        {"stage": "p6_direct_mesh_setup_started", "facts": {}},
        {"stage": "p6_direct_actual_mesh_qa_complete", "facts": {"status": "PASS"}},
        {"stage": "p6_direct_gate_cd_finite_mode_identity_complete", "facts": {}},
        {"stage": "p6_direct_mode_inventory_complete", "facts": mode_inventory},
        {
            "stage": "physical_mode_inventory_reused",
            "facts": {
                "mode_count": 1088,
                "mode_sha256": mode_inventory["active_mode_sha256"],
            },
        },
        {
            "stage": "TASK40_GATE_CD_M8N14_P6_DIRECT_M8N64_FAILED",
            "facts": workflow["facts"],
        },
    ]
    watchdog = {
        "classification": "WORKER_FAILED",
        "descendants_cleared": True,
        "remaining_child_pids": [],
    }
    files = {
        "exact_cache_runtime_contract.json": b'{"schema":"exact-cache-test"}\n',
        "gate_cd_runtime_environment.json": b'{"schema":"runtime-env-test"}\n',
        "input_original.dat": input_bytes,
        "input_sha256.txt": f"{input_sha}\n".encode(),
        "p6_condensed_direct_summary.json": json.dumps(direct_summary).encode() + b"\n",
        "physical_model_sha256.txt": f"{physical_sha}\n".encode(),
        "resolved_config.json": resolved_bytes,
        "run_manifest.json": json.dumps(manifest).encode() + b"\n",
        "run_summary.json": json.dumps(summary).encode() + b"\n",
        "source_sha.txt": f"{prior_source}\n".encode(),
        "stages.jsonl": b"".join(
            json.dumps(item).encode() + b"\n" for item in stages
        ),
        "task40_gate-cd_m8n64_finite_parent_parent_mode_manifest.json": b"{}\n",
        "task40_m8n64_active_mode_manifest.json": b"{}\n",
        "task40_m8n64_mode_index_map.json": b"{}\n",
        "workflow_phase.json": json.dumps(workflow).encode() + b"\n",
        "workstation_isolation.json": b'{"schema":"isolation-test"}\n',
        "watchdog/resources.jsonl": b'{"sample":1}\n',
        "watchdog/summary.json": json.dumps(watchdog).encode() + b"\n",
        "watchdog/worker.log": b"exact signed-mode selector error\n",
    }
    for relative, content in files.items():
        (attempt / relative).write_bytes(content)

    live_capture_path = tmp_path / "live-capture.json"
    start_receipt_path = tmp_path / "start-receipt.json"
    live_capture_path.write_text('{"invocation_id":"captured"}\n')
    start_receipt_path.write_text('{"submitted":true}\n')
    prior_service = {
        "unit": _GATE_CD_SIGNED_SELECTION_RESIDUE["service_unit"],
        "invocation_id": _GATE_CD_SIGNED_SELECTION_RESIDUE["invocation_id"],
        "observed_after_gc": True,
        "active_state_after_gc": "inactive",
        "sub_state_after_gc": "dead",
        "journal_main_exit_status": 3,
        "journal_main_exit_text": "3/NOTIMPLEMENTED",
        "journal_unit_result": "exit-code",
        "worker_exit_status": 4,
        "n_restarts": 0,
        "live_capture_path": str(live_capture_path.resolve()),
        "live_capture_sha256": hashlib.sha256(live_capture_path.read_bytes()).hexdigest(),
        "start_receipt_path": str(start_receipt_path.resolve()),
        "start_receipt_sha256": hashlib.sha256(start_receipt_path.read_bytes()).hexdigest(),
    }
    package = {
        "profile_identity": profile,
        "run_id": run_id,
        "source_commit": "d" * 40,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "prelaunch_output_residue_allowlist": {
            "schema": "task40.gate_cd.prelaunch_output_residue_allowlist.v2",
            "attempts": [
                {
                    "attempt_id": attempt_id,
                    "attempt_directory": str(attempt.resolve()),
                    "prior_source_commit": prior_source,
                    "classification": "worker_failed_gate_cd_signed_mode_selection",
                    "files": {
                        relative: hashlib.sha256(content).hexdigest()
                        for relative, content in files.items()
                    },
                    "directories": ["numerical_output", "watchdog"],
                    "prior_service": prior_service,
                }
            ],
        },
    }
    expected_identity = {
        "profile_identity": profile,
        "run_id": run_id,
        "input_path": input_path,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_output_parent_absolute": str(output_parent.resolve()),
    }
    return output_parent, package, expected_identity


def test_prelaunch_output_parent_accepts_only_exact_hashed_bootstrap_residue(tmp_path):
    output_parent, package, expected_identity = _make_bootstrap_residue(tmp_path)
    result = _verify_prelaunch_output_parent(
        output_parent, package, expected_identity
    )
    assert result["status"] == "accepted_exact_prelaunch_bootstrap_only"
    assert len(result["files"]) == 7


def test_prelaunch_output_parent_rejects_changed_or_extra_residue_files(tmp_path):
    output_parent, package, expected_identity = _make_bootstrap_residue(tmp_path)
    attempt = output_parent / package["prelaunch_output_residue_allowlist"]["attempt_id"]
    with pytest.raises(ValueError, match="hash changed"):
        (attempt / "source_sha.txt").write_text("changed\n")
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)

    output_parent, package, expected_identity = _make_bootstrap_residue(tmp_path / "extra")
    attempt = output_parent / package["prelaunch_output_residue_allowlist"]["attempt_id"]
    (attempt / "unexpected.txt").write_text("extra\n")
    with pytest.raises(ValueError, match="missing, extra"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)


def test_prelaunch_output_parent_rejects_identity_drift(tmp_path):
    output_parent, package, expected_identity = _make_bootstrap_residue(tmp_path)
    expected_identity["run_id"] = "different-run"
    with pytest.raises(ValueError, match="identity differs"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)


def test_prelaunch_output_parent_accepts_only_exact_signed_mode_selection_failure(tmp_path):
    import hashlib

    output_parent, package, expected_identity = _make_signed_mode_selection_residue(
        tmp_path / "accepted"
    )
    result = _verify_prelaunch_output_parent(
        output_parent, package, expected_identity
    )
    assert result["status"] == "accepted_exact_prelaunch_residue_set"
    record = result["residues"][0]
    assert record["attempt_id"] == "20261102T151803.010130Z"
    assert record["classification"] == "worker_failed_gate_cd_signed_mode_selection"
    assert len(record["files"]) == 19
    assert record["directories"] == ["numerical_output", "watchdog"]
    assert record["prior_service"]["journal_main_exit_status"] == 3
    assert record["prior_service"]["worker_exit_status"] == 4
    assert record["prior_service"]["observed_after_gc"] is True

    output_parent, package, expected_identity = _make_signed_mode_selection_residue(
        tmp_path / "wrong-classification"
    )
    package["prelaunch_output_residue_allowlist"]["attempts"][0][
        "classification"
    ] = "worker_failed_gate_cd_mesh_setup"
    with pytest.raises(ValueError, match="mesh-setup residue"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)

    output_parent, package, expected_identity = _make_signed_mode_selection_residue(
        tmp_path / "wrong-stage"
    )
    attempt = output_parent / "20261102T151803.010130Z"
    workflow_path = attempt / "workflow_phase.json"
    workflow = json.loads(workflow_path.read_text())
    workflow["facts"]["failed_stage"] = "p6_direct_mesh_setup_started"
    workflow_path.write_text(json.dumps(workflow) + "\n")
    package["prelaunch_output_residue_allowlist"]["attempts"][0]["files"][
        "workflow_phase.json"
    ] = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="exact cleared pre-carrier failure"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)

    output_parent, package, expected_identity = _make_signed_mode_selection_residue(
        tmp_path / "extra-entry"
    )
    attempt = output_parent / "20261102T151803.010130Z"
    (attempt / "unexpected.json").write_text("{}\n")
    with pytest.raises(ValueError, match="missing, extra, or unlisted entries"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)


def test_prelaunch_output_parent_accepts_only_exact_post_cache_emfile_failure(tmp_path):
    output_parent, package, expected_identity, cache_root = (
        _make_raw_tensor_summary_residue(tmp_path)
    )
    result = _verify_prelaunch_output_parent(
        output_parent, package, expected_identity
    )
    assert result["status"] == "accepted_exact_prelaunch_residue_set"
    record = result["residues"][0]
    assert record["classification"] == "worker_failed_gate_cd_raw_tensor_summary"
    assert record["raw_tensor_cache_evidence"]["root"] == str(cache_root.resolve())
    assert record["raw_tensor_cache_evidence"]["complete_marker_count"] == 2

    output_parent, package, expected_identity, cache_root = (
        _make_raw_tensor_summary_residue(tmp_path / "missing-marker")
    )
    (cache_root / "key-1" / "complete.json").unlink()
    with pytest.raises(ValueError, match="exact cleared post-cache EMFILE failure"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)


def test_prelaunch_output_parent_accepts_exact_bootstrap_and_cleared_mesh_failure(tmp_path):
    import hashlib

    output_parent, package, expected_identity = _make_bootstrap_residue(tmp_path)
    bootstrap = package["prelaunch_output_residue_allowlist"]
    failed_id = "20261101T101730.329471Z"
    failed_dir = output_parent / failed_id
    (failed_dir / "numerical_output").mkdir(parents=True)
    (failed_dir / "watchdog").mkdir()
    prior_source = "b" * 40
    input_path = expected_identity["input_path"]
    input_sha = expected_identity["input_sha256"]
    physical_sha = expected_identity["physical_model_sha256"]
    resolved_sha = expected_identity["resolved_config_sha256"]
    resolved_bytes = (output_parent / bootstrap["attempt_id"] / "resolved_config.json").read_bytes()
    manifest = {
        "run_id": expected_identity["run_id"],
        "source_sha": prior_source,
        "input_path": input_path,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "native_capacity_profile_identity": expected_identity["profile_identity"],
        "output_directory": str(failed_dir.resolve()),
    }
    summary = {
        "status": "finished",
        "run_id": expected_identity["run_id"],
        "exit_status": 4,
        "result_classification": "WORKER_FAILED",
        "output_directory": str(failed_dir.resolve()),
        "numerical_output_directory": str((failed_dir / "numerical_output").resolve()),
        "resource_authority": {
            "classification": "WORKER_FAILED",
            "descendants_cleared": True,
            "remaining_child_pids": [],
        },
    }
    workflow = {
        "phase": "setup",
        "facts": {
            "failed_stage": "p6_direct_mesh_setup_started",
            "exception_type": "ValueError",
            "exception_message": (
                "invalid frozen mesh input: R13 input does not identify the frozen mesh plan"
            ),
        },
    }
    direct_summary = {
        "status": "FAILED",
        "run_id": expected_identity["run_id"],
        "profile": expected_identity["profile_identity"],
        "source_sha": prior_source,
        "failed_stage": "p6_direct_mesh_setup_started",
        "outer_ksp": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "p4_operator": "NOT_BUILT",
    }
    files = {
        "gate_cd_runtime_environment.json": b'{"schema":"test"}\n',
        "input_original.dat": b"frozen input bytes\n",
        "input_sha256.txt": f"{input_sha}\n".encode(),
        "p6_condensed_direct_summary.json": json.dumps(direct_summary).encode() + b"\n",
        "physical_model_sha256.txt": f"{physical_sha}\n".encode(),
        "resolved_config.json": resolved_bytes,
        "run_manifest.json": json.dumps(manifest).encode() + b"\n",
        "run_summary.json": json.dumps(summary).encode() + b"\n",
        "source_sha.txt": f"{prior_source}\n".encode(),
        "stages.jsonl": b'{"stage":"mesh_setup_started"}\n',
        "workflow_phase.json": json.dumps(workflow).encode() + b"\n",
        "workstation_isolation.json": b'{"schema":"test"}\n',
        "watchdog/resources.jsonl": b'{"sample":1}\n',
        "watchdog/summary.json": b'{"descendants_cleared":true}\n',
        "watchdog/worker.log": b"worker failed during mapped mesh setup\n",
    }
    for relative, content in files.items():
        target = failed_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    package["prelaunch_output_residue_allowlist"] = {
        "schema": "task40.gate_cd.prelaunch_output_residue_allowlist.v2",
        "attempts": [
            {
                **bootstrap,
                "classification": "bootstrap_only_preworker",
                "directories": [],
                "prior_service": {"unit": "gate-cd-a2.service", "exec_main_status": 2},
            },
            {
                "attempt_id": failed_id,
                "attempt_directory": str(failed_dir.resolve()),
                "prior_source_commit": prior_source,
                "classification": "worker_failed_gate_cd_mesh_setup",
                "files": {
                    relative: hashlib.sha256(content).hexdigest()
                    for relative, content in files.items()
                },
                "directories": ["numerical_output", "watchdog"],
                "prior_service": {
                    "unit": "gate-cd-a4.service",
                    "invocation_id": "c" * 32,
                    "exec_main_status": 3,
                },
            },
        ],
    }
    result = _verify_prelaunch_output_parent(output_parent, package, expected_identity)
    assert result["status"] == "accepted_exact_prelaunch_residue_set"
    assert [item["attempt_id"] for item in result["residues"]] == [
        bootstrap["attempt_id"], failed_id
    ]
    assert result["residues"][1]["classification"] == (
        "worker_failed_gate_cd_mesh_setup"
    )


def test_prelaunch_output_parent_rejects_unlisted_attempt_in_residue_set(tmp_path):
    output_parent, package, expected_identity = _make_bootstrap_residue(tmp_path)
    package["prelaunch_output_residue_allowlist"] = {
        "schema": "task40.gate_cd.prelaunch_output_residue_allowlist.v2",
        "attempts": [
            {
                **package["prelaunch_output_residue_allowlist"],
                "classification": "bootstrap_only_preworker",
                "directories": [],
            }
        ],
    }
    (output_parent / "unreviewed-attempt").mkdir()
    with pytest.raises(ValueError, match="unapproved attempt directory"):
        _verify_prelaunch_output_parent(output_parent, package, expected_identity)


def test_submission_consumes_exactly_one_marker_even_on_systemd_error(
    tmp_path, monkeypatch
):
    package = {
        "schema": "task40.gate_cd.formal_package.v1",
        "execution_authorized": True,
        "route_readiness": {"launchable": True},
        "quadrature_contract": {
            "volume_degree": 15,
            "surface_degree": 81,
            "surface_rule": "default",
        },
        "mapped_geometry_identity": "mapped_exact",
        "translation_normalized_cache": False,
        "mapped_geometry_cache_policy": _cache_policy(),
        "source_commit": "a" * 40,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "resolved_config_sha256": "d" * 64,
    }
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package))
    package_sha = execution_helper.sha256_file(package_path)
    sidecar = {
        "schema": "task40.gate_cd.formal_sidecar.v1",
        "package_sha256": package_sha,
        "source_commit": package["source_commit"],
        "input_sha256": package["input_sha256"],
        "physical_model_sha256": package["physical_model_sha256"],
        "resolved_config_sha256": package["resolved_config_sha256"],
        "service_unit": "task40-gate-cd-once.service",
    }
    sidecar_path = tmp_path / "sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar))
    sidecar_sha = execution_helper.sha256_file(sidecar_path)
    fresh_path = tmp_path / "fresh.json"
    fresh_path.write_text(
        json.dumps(
            {
                "fresh_pass": True,
                "launch_not_started": True,
                "package_sha256": package_sha,
                "sidecar_sha256": sidecar_sha,
                "source_commit": package["source_commit"],
                "input_sha256": package["input_sha256"],
                "physical_model_sha256": package["physical_model_sha256"],
                "resolved_config_sha256": package["resolved_config_sha256"],
            }
        )
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps(
            {
                "status": "PASS_GATE_CD_SYSTEMD_AND_FRESH",
                "bindings": {
                    "package_sha256": package_sha,
                    "sidecar_sha256": sidecar_sha,
                    "source_commit": package["source_commit"],
                    "input_sha256": package["input_sha256"],
                    "physical_model_sha256": package["physical_model_sha256"],
                    "resolved_config_sha256": package["resolved_config_sha256"],
                },
            }
        )
    )
    monkeypatch.setattr(
        execution_helper.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="LoadState=not-found", stderr=""),
    )
    monkeypatch.setattr(
        execution_helper,
        "_validate_systemd_argv",
        lambda _sidecar: ["systemd-run", "--user", "--no-block", "--unit=test.service"],
    )
    marker = tmp_path / "submitted.once"
    calls = []

    def failed_systemd(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=1, stdout="", stderr="mock bus failure")

    paths = [
        package_path,
        sidecar_path,
        fresh_path,
        review_path,
        marker,
        tmp_path / "start.json",
        tmp_path / "live.json",
    ]
    with pytest.raises(RuntimeError, match="no retry"):
        submit_once(*paths, run_command=failed_systemd)
    assert len(calls) == 1
    with pytest.raises(FileExistsError):
        submit_once(*paths, run_command=failed_systemd)
    assert len(calls) == 1
    assert json.loads((tmp_path / "start.json").read_text())["returncode"] == 1


def test_runtime_cpu_affinity_comes_from_committed_runtime_lease(tmp_path, monkeypatch):
    profile = "task40_gate_cd_0p7_mapped_m8n64_p6_direct_v1"
    reservation_path = tmp_path / "lease" / "runtime.json"
    reservation_path.parent.mkdir()
    scope = {
        "schema": "task40.gate_cd_formal_exact_execution_scope.v1",
        "attempt_id": "attempt_live_01",
        "identity": {"profile_identity": profile, "run_id": profile},
        "runtime_paths": {
            "lock_directory": str(reservation_path.parent),
            "one_shot_reservation": str(reservation_path),
        },
    }
    scope_path = tmp_path / "scope.json"
    scope_raw = json.dumps(scope, sort_keys=True).encode()
    scope_path.write_bytes(scope_raw)
    scope_sha = execution_helper.hashlib.sha256(scope_raw).hexdigest()
    sidecar = {
        "scope_path": str(scope_path),
        "scope_sha256": scope_sha,
        "lock_directory": str(reservation_path.parent),
    }
    reservation = {
        "schema": "task40.gate_cd.formal_one_shot_submission.v1",
        "profile_identity": profile,
        "run_id": profile,
        "attempt_id": "attempt_live_01",
        "scope_sha256": scope_sha,
        "submission_mode": "runtime",
        "cpu_reservation": {
            "supervisor_cpu": 9,
            "worker_cpu": 23,
            "worker_cpus": [23],
        },
    }
    reservation_raw = json.dumps(reservation, sort_keys=True).encode()
    reservation_path.write_bytes(reservation_raw)
    loaded, reservation_sha, observed_scope_sha = _wait_for_runtime_cpu_reservation(
        sidecar,
        {"profile_identity": profile, "run_id": profile},
        timeout_seconds=0,
    )
    assert loaded == reservation
    assert reservation_sha == execution_helper.hashlib.sha256(reservation_raw).hexdigest()
    assert observed_scope_sha == scope_sha
    bad_reservation = dict(reservation)
    bad_reservation["cpu_reservation"] = {
        **reservation["cpu_reservation"],
        "worker_cpu": 24,
    }
    reservation_path.write_text(json.dumps(bad_reservation))
    with pytest.raises(ValueError, match="worker_cpu and worker_cpus disagree"):
        _wait_for_runtime_cpu_reservation(
            sidecar,
            {"profile_identity": profile, "run_id": profile},
            timeout_seconds=0,
        )
    reservation_path.write_bytes(reservation_raw)

    package = _final_package()
    package.update(
        profile_identity=profile,
        run_id=profile,
        source_commit="a" * 40,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        resolved_config_sha256="d" * 64,
    )
    package_path = tmp_path / "package-live.json"
    package_path.write_text(json.dumps(package))
    package_sha = execution_helper.sha256_file(package_path)
    sidecar.update(
        schema="task40.gate_cd.formal_sidecar.v1",
        package_sha256=package_sha,
        source_commit=package["source_commit"],
        input_sha256=package["input_sha256"],
        physical_model_sha256=package["physical_model_sha256"],
        resolved_config_sha256=package["resolved_config_sha256"],
        service_unit="task40-gate-cd-runtime-cpu.service",
    )
    sidecar_path = tmp_path / "sidecar-live.json"
    sidecar_path.write_text(json.dumps(sidecar))
    sidecar_sha = execution_helper.sha256_file(sidecar_path)
    fresh_path = tmp_path / "fresh-live.json"
    fresh_path.write_text(
        json.dumps(
            {
                "fresh_pass": True,
                "launch_not_started": True,
                "package_sha256": package_sha,
                "sidecar_sha256": sidecar_sha,
                "source_commit": package["source_commit"],
                "input_sha256": package["input_sha256"],
                "physical_model_sha256": package["physical_model_sha256"],
                "resolved_config_sha256": package["resolved_config_sha256"],
                # Intentionally differs from the runtime lease's worker CPU.
                "host_and_lease_facts": {"worker_affinity": [17]},
            }
        )
    )
    review_path = tmp_path / "review-live.json"
    review_path.write_text(
        json.dumps(
            {
                "status": "PASS_GATE_CD_SYSTEMD_AND_FRESH",
                "bindings": {
                    "package_sha256": package_sha,
                    "sidecar_sha256": sidecar_sha,
                    "source_commit": package["source_commit"],
                    "input_sha256": package["input_sha256"],
                    "physical_model_sha256": package["physical_model_sha256"],
                    "resolved_config_sha256": package["resolved_config_sha256"],
                },
            }
        )
    )
    monkeypatch.setattr(
        execution_helper.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="LoadState=not-found", stderr=""),
    )
    monkeypatch.setattr(
        execution_helper,
        "_validate_systemd_argv",
        lambda _sidecar: ["systemd-run", "--user", "--no-block", "--unit=test.service"],
    )
    monkeypatch.setattr(execution_helper, "capture_unit", lambda _unit: {"unit": _unit})
    observed = {}

    def capture_validator(_capture, _root, cpus, _threads):
        observed["worker_cpus"] = cpus

    monkeypatch.setattr(execution_helper, "_require_live_capture", capture_validator)
    calls = []

    def one_systemd_submission(argv, **_kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="submitted", stderr="")

    start_path = tmp_path / "start-live.json"
    live_path = tmp_path / "live-live.json"
    marker_path = tmp_path / "marker-live.json"
    result = submit_once(
        package_path,
        sidecar_path,
        fresh_path,
        review_path,
        marker_path,
        start_path,
        live_path,
        run_command=one_systemd_submission,
    )
    assert len(calls) == 1
    assert observed["worker_cpus"] == [23]
    assert result["runtime_cpu_reservation"]["cpu_reservation"]["worker_cpus"] == [23]
    assert result["affinity_authority"] == (
        "committed_runtime_one_shot_reservation_not_fresh_sample"
    )


def test_live_capture_accepts_bound_exact_cache_values_and_rejects_drift(tmp_path):
    import copy
    import hashlib

    worker_cpus = list(range(32))
    attempt_id = "gcd1088-live-capture-test"
    template_sha = "a" * 64
    cache_root = (tmp_path / "attempt-cache").resolve()
    contract = {
        "attempt_id": attempt_id,
        "worker_cpus": worker_cpus,
        "template_sha256": template_sha,
        "attempt_cache_root": str(cache_root),
        "tensor_root": str(cache_root / "tensor"),
        "carrier_root": str(cache_root / "carrier"),
    }
    contract_path = tmp_path / "exact-cache-contract.json"
    contract_raw = json.dumps(contract, sort_keys=True).encode() + b"\n"
    contract_path.write_bytes(contract_raw)
    contract_sha = hashlib.sha256(contract_raw).hexdigest()
    environment = {
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION": "1",
        "TASK39EXTRA_INT64_ACTIVATION": "1",
        "TASK39EXTRA_PORD64_ACTIVATION": "1",
        "TASK40_EXACT_CACHE_ATTEMPT_ID": attempt_id,
        "TASK40_EXACT_CACHE_CONTRACT": str(contract_path.resolve()),
        "TASK40_EXACT_CACHE_CONTRACT_SHA256": contract_sha,
        "TASK40_EXACT_CACHE_RUNTIME_TEMPLATE_SHA256": template_sha,
        "TASK40_EXACT_CACHE_WORKER_CPUS": json.dumps(
            worker_cpus, separators=(",", ":")
        ),
    }
    capture = {
        "unit": "gate-cd-test.service",
        "unit_properties": {
            "MainPID": "101",
            "InvocationID": "b" * 32,
            "ControlGroup": "/user.slice/test.service",
        },
        "main_pid_identity": {"ppid": 81},
        "roles": {
            "root": [
                {"pid": 101, "ppid": 81, "cwd": str(tmp_path.resolve())}
            ],
            "mpi": [{"pid": 102, "ppid": 101}],
            "worker": [
                {
                    "pid": 103,
                    "ppid": 102,
                    "cpus_allowed_list": "0-31",
                    "max_open_files_soft": 65536,
                    "max_open_files_hard": 1048576,
                    "threads": [{"cpus_allowed_list": "0-31"}],
                    "libpetsc_mappings": [
                        "/qualified/pord64-overlay/petsc/lib/libpetsc.so"
                    ],
                    "numa_maps_summary": {"interleave_0_1_vmas": 1},
                    "environment": environment,
                }
            ],
        },
    }
    package = {
        "attempt_id": attempt_id,
        "exact_cache_contract": {"template_sha256": template_sha},
    }
    execution_helper._require_live_capture(
        capture, tmp_path, worker_cpus, 1, package=package
    )

    bad_nofile = copy.deepcopy(capture)
    bad_nofile["roles"]["worker"][0]["max_open_files_soft"] = 1024
    with pytest.raises(ValueError, match="Max open files limit"):
        execution_helper._require_live_capture(
            bad_nofile, tmp_path, worker_cpus, 1, package=package
        )

    bad_affinity = copy.deepcopy(capture)
    bad_affinity["roles"]["worker"][0]["environment"][
        "TASK40_EXACT_CACHE_WORKER_CPUS"
    ] = json.dumps(worker_cpus[:-1], separators=(",", ":"))
    with pytest.raises(ValueError, match="lease/template environment differs"):
        execution_helper._require_live_capture(
            bad_affinity, tmp_path, worker_cpus, 1, package=package
        )

    bad_contract = copy.deepcopy(capture)
    bad_contract["roles"]["worker"][0]["environment"][
        "TASK40_EXACT_CACHE_CONTRACT_SHA256"
    ] = "f" * 64
    with pytest.raises(ValueError, match="runtime contract hash differs"):
        execution_helper._require_live_capture(
            bad_contract, tmp_path, worker_cpus, 1, package=package
        )
