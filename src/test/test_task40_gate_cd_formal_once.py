from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import gate_cd_formal_once as execution_helper
from scripts.gate_cd_formal_once import (
    _require_final_package,
    _validate_live_profile_contract,
    _validate_systemd_argv,
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
