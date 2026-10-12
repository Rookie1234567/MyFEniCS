import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.runners.task40_v29_contract import (
    V29ContractError,
    qualified_activation_identity,
    require_authorized_contract,
    require_strict_factor_only_status,
    resolve_approved_path,
    validate_live_resource_contract,
    verify_file_record,
)


def test_native_v29_activation_identity_is_not_the_legacy_wsl_marker():
    native = {
        "TASK40_V29_STRICT_FACTOR_ONLY": "1",
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_QUALIFICATION_SCOPE": "imports_only_C1_FE_JIT_NOT_RUN",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": "a" * 64,
    }
    assert qualified_activation_identity(native) == f"native_linux_imports_only:{'a' * 64}"
    assert qualified_activation_identity(
        {**native, "_MYFENICS_CLOUD_RUNTIME_PROFILE": "local_wsl2_authorized"}
    ) is None
    assert qualified_activation_identity(
        {"TASK40_V29_STRICT_FACTOR_ONLY": "1", "_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1"}
    ) is None
    assert qualified_activation_identity({"_MYFENICS_WSL_QUALIFIED_ACTIVATION": "1"}) == "1"


def test_native_activation_helper_uses_existing_profile_from_a_cold_shell(tmp_path, monkeypatch):
    from scripts import task40_v20_service_workflow as workflow

    repo_root = tmp_path / "checkout"
    runtime_prefix = tmp_path / "runtime"
    abi_receipt = tmp_path / "abi_receipt.json"
    jit_cache = tmp_path / "jit-cache"
    qualified_env = {
        "PATH": f"{runtime_prefix}/bin:/usr/bin",
        "_MYFENICS_CLOUD_QUALIFIED_ACTIVATION": "1",
        "_MYFENICS_CLOUD_RUNTIME_PROFILE": "native_linux",
        "_MYFENICS_CLOUD_QUALIFICATION_SCOPE": "imports_only_C1_FE_JIT_NOT_RUN",
        "_MYFENICS_CLOUD_ABI_MANIFEST_SHA256": "b" * 64,
    }
    env_bytes = b"\0".join(
        f"{key}={value}".encode() for key, value in qualified_env.items()
    ) + b"\0"

    def fake_run(argv, *, cwd, stdout, stderr):
        assert argv[0:2] == ["/usr/bin/bash", "-lc"]
        assert cwd == repo_root
        assert stdout == workflow.subprocess.PIPE
        assert stderr == workflow.subprocess.PIPE
        assert "activate_native_complex.sh" in argv[2]
        assert 'native_linux' in argv[2]
        assert "unset _MYFENICS_WSL_QUALIFIED_ACTIVATION" in argv[2]
        assert "activate_local_wsl_complex.sh" not in argv[2]
        return SimpleNamespace(returncode=0, stdout=env_bytes, stderr=b"")

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)
    environment, command, return_code, stderr = workflow._activation_environment(
        repo_root,
        runtime_prefix,
        abi_receipt,
        jit_cache,
        runtime_profile="native_linux",
    )

    assert return_code == 0
    assert stderr == ""
    assert command.startswith("/usr/bin/bash -lc ")
    assert environment["TASK40_V29_STRICT_FACTOR_ONLY"] == "1"
    assert environment["_MYFENICS_CLOUD_RUNTIME_PROFILE"] == "native_linux"
    assert "_MYFENICS_WSL_QUALIFIED_ACTIVATION" not in environment
    assert workflow._qualified_activation_identity(environment) == (
        f"native_linux_imports_only:{'b' * 64}"
    )


def test_v29_systemd_launcher_activates_before_runtime_python():
    wrapper = Path(__file__).resolve().parents[2] / "scripts/run_case_in_user_service.sh"
    source = wrapper.read_text(encoding="utf-8")
    assert 'cd -- "$repo_root" && python3 -m src.runners.task40_v29_contract' in source
    assert 'python3 "$repo_root/src/runners/task40_v29_contract.py"' not in source
    v29_branch = source.split("if (( use_v29 )); then", 1)[1].split("fi; case", 1)[0]
    assert "python3 -m src.runners.task40_v29_contract" in v29_branch
    assert "activate_native_complex.sh" in v29_branch
    assert "native_linux" in v29_branch
    assert "python\" -S" not in v29_branch


def test_pending_contract_cannot_become_a_launch_authorization(tmp_path):
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema": "task40extra.review_v29_execution_contract.v1",
                "authorization_status": "PENDING_USER_AUTHORIZATION",
                "execution": {"execution_host": None, "execution_root": None},
            }
        )
    )

    with pytest.raises(V29ContractError, match="launch held.*PENDING_USER_AUTHORIZATION"):
        require_authorized_contract(contract)


def test_strict_factor_only_never_routes_incomplete_or_unqualified_data_to_auto():
    require_strict_factor_only_status(
        {"status": "COMPLETE_CSR"},
        {"status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"},
    )

    with pytest.raises(V29ContractError, match="before adapter/fill/readback"):
        require_strict_factor_only_status(
            {"status": "NUMERIC_FILL_INCOMPLETE"},
            {"status": "MISSING"},
        )


def test_root_mapping_is_confined_to_the_approved_task40_tree(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "approved"
    source.mkdir()
    target.mkdir()
    assert resolve_approved_path(
        source / "results" / "q0.json",
        source_root=source,
        execution_root=target,
    ) == target / "results" / "q0.json"

    with pytest.raises(V29ContractError, match="outside the approved source"):
        resolve_approved_path(
            tmp_path / "other" / "secret.json",
            source_root=source,
            execution_root=target,
        )

    escape = source / "escape"
    escape.symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(V29ContractError, match="outside the approved source"):
        resolve_approved_path(
            escape / "file.json",
            source_root=source,
            execution_root=target,
        )


def test_content_hash_change_is_reported_at_the_concrete_dependency(tmp_path):
    target = tmp_path / "dependency.bin"
    target.write_bytes(b"original bytes")
    expected = hashlib.sha256(b"original bytes").hexdigest()
    result = verify_file_record(
        target,
        expected_bytes=len(b"original bytes"),
        expected_sha256=expected,
        purpose="native witness",
    )
    assert result["sha256"] == expected

    target.write_bytes(b"changed bytes")
    with pytest.raises(V29ContractError, match="SHA-256 mismatch.*dependency.bin"):
        verify_file_record(
            target,
            expected_bytes=len(b"changed bytes"),
            expected_sha256=expected,
            purpose="native witness",
        )


def test_live_resource_gate_requires_the_same_cap_and_host_reserve():
    contract = {
        "execution": {
            "resources": {
                "task_memory_max_bytes": 549_755_813_888,
                "host_reserve_bytes": 68_719_476_736,
            }
        }
    }
    validate_live_resource_contract(
        contract,
        cgroup_limit_bytes=549_755_813_888,
        cgroup_current_bytes=10_000,
        host_effective_available_bytes=68_719_496_736,
        additional_request_bytes=10_000,
    )

    with pytest.raises(V29ContractError, match="cgroup limit differs"):
        validate_live_resource_contract(
            contract,
            cgroup_limit_bytes=17_179_869_184,
            cgroup_current_bytes=10_000,
            host_effective_available_bytes=68_719_496_736,
            additional_request_bytes=10_000,
        )


def test_v29_live_resource_gate_uses_real_snapshot_and_admission(monkeypatch):
    from benchmarks import (
        subreaper_watchdog,
        task034_wsl_resources,
        task038_full3d_jit_staging,
    )
    from scripts import task40_v20_service_workflow as workflow
    from src.solvers.task40_v22_operator_probe import _ProbeResourceBlocked

    task_cap = 549_755_813_888
    host_reserve = 68_719_476_736
    host_available = 137_438_953_472
    cgroup_current = 1_048_576
    contract = {
        "execution": {
            "resources": {
                "task_memory_max_bytes": task_cap,
                "host_reserve_bytes": host_reserve,
                "memory_swap_max_bytes": 0,
            }
        }
    }

    def set_live_samples(*, swap_current_bytes):
        cgroup = {
            "path": "/user.slice/user-1000.slice/user@1000.service/app.slice/v29-test.scope",
            "readable": True,
            "dedicated_job_cgroup": True,
            "member_count": 1,
            "memory_current_bytes": cgroup_current,
            "memory_peak_bytes": cgroup_current,
            "memory_limit_bytes": task_cap,
            "swap_current_bytes": swap_current_bytes,
        }
        monkeypatch.setattr(
            task034_wsl_resources,
            "cgroup_snapshot",
            lambda pid="self": dict(cgroup),
        )
        monkeypatch.setattr(
            task038_full3d_jit_staging,
            "process_tree_snapshot",
            lambda *args, **kwargs: {
                "rss_bytes": 1_048_576,
                "identity_complete": True,
                "identity_count": 1,
                "all_status_readable": True,
            },
        )

        def memory_sample(
            memory_policy, *, host_reserve_bytes, task_cgroup_reserve_bytes
        ):
            assert memory_policy == subreaper_watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY
            assert host_reserve_bytes == host_reserve
            assert task_cgroup_reserve_bytes == 0
            host_room = host_available - host_reserve
            cgroup_room = task_cap - cgroup_current
            launch_cap = min(host_room, cgroup_room)
            return {
                "mem_total_bytes": 1_099_511_627_776,
                "mem_available_bytes": host_available,
                "effective_total_bytes": 1_099_511_627_776,
                "effective_available_bytes": host_available,
                "host_mem_available_bytes": host_available,
                "task_cgroup_available_bytes": cgroup_room,
                "host_launch_available_bytes": host_room,
                "task_cgroup_reserve_bytes": 0,
                "task_cgroup_launch_available_bytes": cgroup_room,
                "reserve_domains_separated": True,
                "effective_available_after_reserves_bytes": launch_cap,
                "reserve_bytes": host_reserve,
                "launch_cap_bytes": launch_cap,
                "memory_policy": memory_policy,
            }

        monkeypatch.setattr(subreaper_watchdog, "memory_envelope", memory_sample)

    set_live_samples(swap_current_bytes=0)
    result = workflow._v29_live_resource_gate(contract, stage="v29_fixture")
    admission = result["resource_admission"]
    cgroup = admission["current_process_cgroup"]
    assert result["passed"] is True
    assert result["task_memory_max_bytes"] == task_cap
    assert result["host_reserve_bytes"] == host_reserve
    assert result["memory_swap_max_bytes"] == 0
    assert result["cgroup_limit_bytes"] == task_cap
    assert result["cgroup_current_bytes"] == cgroup_current
    assert result["host_effective_available_bytes"] == host_available
    assert cgroup["readable"] is True
    assert cgroup["dedicated_job_cgroup"] is True
    assert cgroup["memory_limit_bytes"] == task_cap
    assert cgroup["memory_current_bytes"] == cgroup_current
    assert cgroup["swap_current_bytes"] == 0
    assert admission["task_cgroup_gate_passed"] is True
    assert admission["memory_envelope"]["reserve_bytes"] == host_reserve

    set_live_samples(swap_current_bytes=1)
    with pytest.raises(
        _ProbeResourceBlocked,
        match="resource admission blocked before v29_fixture",
    ) as blocked:
        workflow._v29_live_resource_gate(contract, stage="v29_fixture")
    assert blocked.value.facts["current_process_cgroup"]["swap_current_bytes"] == 1
    assert blocked.value.facts["task_cgroup_gate_passed"] is False


def test_v29_campaign_loader_binds_new_t0_review_and_approval(tmp_path, monkeypatch):
    from src.runners import task40_v10_campaign as campaign

    repository = tmp_path / "checkout"
    synthetic_module_path = repository / "src/runners/task40_v10_campaign.py"
    monkeypatch.setattr(campaign, "__file__", str(synthetic_module_path))
    relative_window = campaign.TASK40_V29_CAMPAIGN_WINDOW
    window_path = repository / relative_window
    window_path.parent.mkdir(parents=True)

    approval = {
        "scope": "V29_Q0_FACTOR_ONLY",
        "resources": {
            "task_memory_max_bytes": 549_755_813_888,
            "host_reserve_bytes": 68_719_476_736,
            "memory_swap_max_bytes": 0,
            "mpi_ranks": 1,
            "math_threads": 1,
        },
    }
    approval_sha = hashlib.sha256(
        json.dumps(
            approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    t0 = "2030-01-01T00:00:00Z"
    t0_ns = campaign._utc_ns(t0)
    boot_id = "12345678-1234-1234-1234-123456789abc"
    payload = {
        "schema": campaign.CAMPAIGN_SCHEMA,
        "campaign": campaign.TASK40_V29_CAMPAIGN_ID,
        "authority": "User-authorized Review V29 first qualified q0 factor execution",
        "active_review_sha": campaign.TASK40_V29_REVIEW_COMMIT,
        "active_review_path": campaign.TASK40_V29_REVIEW_PATH,
        "active_review_sha256": campaign.TASK40_V29_REVIEW_SHA256,
        "review_at_registration": campaign.TASK40_V29_REVIEW_COMMIT,
        "source_at_entry": "b" * 40,
        "user_approval": approval,
        "user_approval_sha256": approval_sha,
        "t0_utc": t0,
        "deadline_utc": "2030-01-01T06:00:00Z",
        "campaign_seconds": campaign.TASK40_V29_CAMPAIGN_SECONDS,
        "closeout_reserve_seconds": campaign.TASK40_V29_CLOSEOUT_RESERVE_SECONDS,
        "time_policy": campaign.CONSERVATIVE_REALTIME,
        "stage_scope": list(campaign.TASK40_V29_STAGE_SCOPE),
        "forbidden_scope": list(campaign.TASK40_V29_FORBIDDEN_SCOPE),
        "window_refreshed": False,
        "old_costs_and_unknowns_preserved": True,
        "artifact_execution_identity_separate": True,
        "first_full_three_clock_sample": {
            "monotonic": 2.0,
            "boottime": 1.0,
            "utc_ns": t0_ns + 1_000_000_000,
            "boot_id": boot_id,
        },
        "initial_boot_id": boot_id,
        "bootstrap_utc_elapsed_seconds": 1.0,
        "bootstrap_boottime_elapsed_seconds": 1.0,
        "bootstrap_time_treatment": "new V29 T0 sampled after explicit authorization",
    }
    window_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = campaign.load_fixed_campaign_window(
        window_path,
        require_current_boot=False,
    )

    assert loaded.total_seconds == 21_600
    assert loaded.closeout_seconds == 1_200
    assert loaded.t0_utc_ns == t0_ns
    assert loaded.path == window_path.resolve()

    wrong_scope = dict(payload)
    wrong_scope["user_approval"] = {**approval, "scope": "OTHER_TASK"}
    wrong_scope["user_approval_sha256"] = hashlib.sha256(
        json.dumps(
            wrong_scope["user_approval"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    window_path.write_text(json.dumps(wrong_scope), encoding="utf-8")
    with pytest.raises(ValueError, match="user_approval_scope"):
        campaign.load_fixed_campaign_window(window_path, require_current_boot=False)

    reused_window = dict(payload)
    reused_t0 = "2026-10-11T23:24:00Z"
    reused_window["t0_utc"] = reused_t0
    reused_window["deadline_utc"] = "2026-10-12T05:24:00Z"
    reused_window["first_full_three_clock_sample"] = {
        **payload["first_full_three_clock_sample"],
        "utc_ns": campaign._utc_ns(reused_t0) + 1_000_000_000,
    }
    window_path.write_text(json.dumps(reused_window), encoding="utf-8")
    with pytest.raises(ValueError, match="t0_utc_reuses_v28"):
        campaign.load_fixed_campaign_window(window_path, require_current_boot=False)
