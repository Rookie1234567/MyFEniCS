"""No-FE tests for Gate-CD's exact one-shot and observational host admission."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.native_capacity_profile import native_profile_facts
from src.runners.reviewed_workstation_admission import (
    task40_host_floor_interleaved_admission,
)
from src.runners.task40_gate_cd_formal_admission import (
    GATE_CD_FORMAL_PROFILE,
    GATE_CD_M8N6_PROFILE,
    GATE_CD_M8N2_PROFILE,
    GATE_CD_PARALLEL32_WORKERS,
    GATE_CD_RAW_POOL_LOCK_PATH,
    GATE_CD_RAW_POOL_SCHEDULER_POLICY,
    GATE_CD_SCOPE_SCHEMA,
    _runtime_paths,
    _validate_gate_cd_scope,
    gate_cd_runtime_lease,
)


def _identity(profile=GATE_CD_FORMAL_PROFILE):
    return {
        "profile_identity": profile,
        "run_id": profile,
        "input_path": "/tmp/gate_cd/input.dat",
        "input_sha256": "1" * 64,
        "physical_model_sha256": "2" * 64,
        "resolved_config_sha256": "3" * 64,
        "resolved_output_parent_absolute": "/tmp/gate_cd/results",
        "source_commit": "4" * 40,
        "direct_route_contract": {"full_dtn_status": "FULL_DTN_NOT_VERIFIED"},
    }


def _scope(tmp_path, attempt="admtest0001", profile=GATE_CD_FORMAL_PROFILE):
    scope = {
        "schema": GATE_CD_SCOPE_SCHEMA,
        "attempt_id": attempt,
        "identity": _identity(profile),
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
            **(
                {
                    "worker_count": GATE_CD_PARALLEL32_WORKERS,
                    "avoid_observed_active_solver_cores_when_capacity_allows": True,
                }
                if profile in {GATE_CD_M8N6_PROFILE, GATE_CD_M8N2_PROFILE}
                else {}
            ),
        },
        "parallel_neighbors": {
            "policy": "gate_cd_observational_neighbors_v1",
            "solver_candidates_block_admission": False,
            "unknown_solver_candidates_block_admission": False,
            "large_process_candidates_block_admission": False,
            "neighbors_modified": False,
        },
        **(
            {
                "raw_tensor_pool_scheduler": {
                    "policy": GATE_CD_RAW_POOL_SCHEDULER_POLICY,
                    "lock_path": GATE_CD_RAW_POOL_LOCK_PATH,
                    "serialized_region": "raw_tensor_execution.run_batch_only",
                    "whole_run_serialization": False,
                }
            }
            if profile in {GATE_CD_M8N6_PROFILE, GATE_CD_M8N2_PROFILE}
            else {}
        ),
        "runtime_paths": _runtime_paths(profile, profile, attempt, tmp_path),
    }
    path = tmp_path / f"{attempt}.scope.json"
    raw = (json.dumps(scope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest(), scope


def _fake_proc(proc_root: Path, *, active_neighbors=True):
    (proc_root / "self").mkdir(parents=True)
    (proc_root / "self" / "status").write_text(
        "Name:\tguard\nMems_allowed_list:\t0-1\n"
    )
    def add(pid, ppid, start, argv, rss_kib=1024, name="python"):
        base = proc_root / str(pid)
        base.mkdir()
        cwd = base / "workdir"
        cwd.mkdir()
        (base / "cwd").symlink_to(cwd, target_is_directory=True)
        fields = ["S", str(ppid)] + ["0"] * 17 + [str(start)]
        (base / "stat").write_text(f"{pid} ({name}) " + " ".join(fields) + "\n")
        (base / "status").write_text(
            f"Name:\t{name}\nVmRSS:\t{rss_kib}\tkB\nMems_allowed_list:\t0-1\n"
        )
        (base / "cmdline").write_bytes(b"\0".join(x.encode() for x in argv) + b"\0")
    add(10, 1, 100, ["python", "guard.py"], name="guard")
    if active_neighbors:
        add(20, 1, 200, ["python", "run_case.py", "known-neighbor.dat"],
            rss_kib=120_000_000, name="python")
        add(30, 1, 300, ["python", "-m", "src.runners.task038_unknown"],
            rss_kib=1024, name="python")
        add(40, 1, 400, ["unrelated-worker"], rss_kib=120_000_000,
            name="unrelated-worker")


def _fake_sys(sys_root: Path):
    cpuset = sys_root / "fs" / "cgroup" / "task40"
    cpuset.mkdir(parents=True)
    (cpuset / "cpuset.cpus.effective").write_text("9,24\n")
    (sys_root / "devices" / "system" / "node" / "node0").mkdir(parents=True)
    (sys_root / "devices" / "system" / "node" / "node1").mkdir(parents=True)
    for node in (0, 1):
        base = sys_root / "devices" / "system" / "node" / f"node{node}"
        (base / "meminfo").write_text(f"Node {node} MemTotal: 1000 kB\nNode {node} MemFree: 500 kB\n")
        (base / "cpulist").write_text("0-47\n")
    for cpu in (9, 24):
        top = sys_root / "devices" / "system" / "cpu" / f"cpu{cpu}" / "topology"
        top.mkdir(parents=True)
        (top / "physical_package_id").write_text("0\n")
        (top / "core_id").write_text(f"{cpu}\n")


def _interleave_probe():
    return SimpleNamespace(returncode=0, stdout='["interleave:0-1"]', stderr="")


def test_scope_is_exact_and_one_shot_is_runtime_only(tmp_path):
    path, digest, _ = _scope(tmp_path)
    _validate_gate_cd_scope(
        path, digest, profile=GATE_CD_FORMAL_PROFILE,
        run_id=GATE_CD_FORMAL_PROFILE, expected_identity=_identity(),
        lock_directory=tmp_path,
    )
    cpu = lambda sample_seconds, proc_root: {
        "supervisor_cpu": 9, "worker_cpu": 24, "worker_cpus": [24],
        "exclusive_cpu_ownership": False,
    }
    with gate_cd_runtime_lease(
        GATE_CD_FORMAL_PROFILE, GATE_CD_FORMAL_PROFILE,
        scope_path=path, scope_sha256=digest, expected_identity=_identity(),
        submission_mode="fresh_check", lock_directory=tmp_path,
        cpu_selector=cpu,
    ) as lease:
        assert lease.summary()["canonical_heavy_lock_touched"] is False
        assert lease.summary()["cpu_reservation"]["worker_cpus"] == [24]
        assert not lease.reservation_path.exists()
        assert not lease.cache_root.exists()
    with gate_cd_runtime_lease(
        GATE_CD_FORMAL_PROFILE, GATE_CD_FORMAL_PROFILE,
        scope_path=path, scope_sha256=digest, expected_identity=_identity(),
        submission_mode="runtime", lock_directory=tmp_path,
        cpu_selector=cpu,
    ) as lease:
        cache = lease.prepare_attempt_cache()
        lease.commit_runtime_submission()
        assert cache["xdg"].is_dir()
        assert lease.reservation_path.is_file()
    with (
        pytest.raises(Exception, match="one-shot reservation already exists"),
        gate_cd_runtime_lease(
            GATE_CD_FORMAL_PROFILE, GATE_CD_FORMAL_PROFILE,
            scope_path=path, scope_sha256=digest, expected_identity=_identity(),
            submission_mode="runtime", lock_directory=tmp_path,
            cpu_selector=cpu,
        ),
    ):
        pass


@pytest.mark.parametrize(
    "profile",
    (GATE_CD_FORMAL_PROFILE, GATE_CD_M8N6_PROFILE, GATE_CD_M8N2_PROFILE),
)
def test_production_host_floor_guard_observes_neighbors_but_only_floor_blocks(
    tmp_path, monkeypatch, profile
):
    from benchmarks import subreaper_watchdog, task034_wsl_resources
    from src.runners import reviewed_workstation_admission as admission

    proc_root, sys_root = tmp_path / "proc", tmp_path / "sys"
    proc_root.mkdir()
    _fake_proc(proc_root)
    _fake_sys(sys_root)
    cgroup = sys_root / "fs" / "cgroup" / "task40"
    _, _, scope = _scope(tmp_path, f"hostfloor{len(profile):04d}", profile)
    monkeypatch.setattr(admission, "_proc_root", lambda: proc_root)
    monkeypatch.setattr(admission, "_sys_root", lambda: sys_root)
    monkeypatch.setattr(admission.os, "getpid", lambda: 10)
    monkeypatch.setattr(admission, "_interleave_probe", _interleave_probe)
    monkeypatch.setattr(task034_wsl_resources, "current_cgroup_path", lambda: cgroup)
    monkeypatch.setattr(
        subreaper_watchdog, "memory_envelope",
        lambda: {"effective_available_bytes": 128 * 1024**3},
    )
    resources = native_profile_facts(profile)["resources"]
    assert resources["parallel_admission_policy"] == (
        "gate_cd_exact_scope_one_shot_host_floor_v1"
    )
    admitted = task40_host_floor_interleaved_admission(
        resources, [24], task_profile=profile,
        task_run_id=profile, supervisor_cpu=9,
        gate_cd_scope=scope,
    )
    assert admitted["resource_stop_policy"] == "host_available_floor_v1"
    assert admitted["minimum_available_bytes"] == 64 * 1024**3
    assert admitted["rss_hard_limit_bytes"] is None
    assert admitted["blocking_active_solver_candidates"] == []
    assert admitted["blocking_unknown_solver_role_candidates"] == []
    assert admitted["blocking_large_processes"] == []
    assert admitted["gate_cd_parallel_neighbors_observed_only"] is True
    assert admitted["gate_cd_formal_observational_scope"][
        "unknown_solver_candidates_observed_not_blocking"
    ] >= 1

    monkeypatch.setattr(
        subreaper_watchdog, "memory_envelope",
        lambda: {"effective_available_bytes": 64 * 1024**3 - 1},
    )
    with pytest.raises(Exception, match="below its explicit floor"):
        task40_host_floor_interleaved_admission(
            resources, [24], task_profile=profile,
            task_run_id=profile, supervisor_cpu=9,
            gate_cd_scope=scope,
        )


def test_worker_cache_check_uses_exact_gate_cd_attempt_paths(tmp_path):
    from src.runners.task038_input_worker import _task40_gate_cd_runtime_cache_evidence

    root = tmp_path / "attempt"
    paths = {"root": root}
    root.mkdir()
    for key in ("tmp", "xdg", "pycache", "mpl"):
        paths[key] = root / key
        paths[key].mkdir()
    (paths["xdg"] / "fenics").mkdir()
    environment = {
        "TMPDIR": str(paths["tmp"]), "TMP": str(paths["tmp"]),
        "TEMP": str(paths["tmp"]), "XDG_CACHE_HOME": str(paths["xdg"]),
        "PYTHONPYCACHEPREFIX": str(paths["pycache"]),
        "MPLCONFIGDIR": str(paths["mpl"]),
    }
    manifest = {
        "native_capacity_profile_identity": GATE_CD_FORMAL_PROFILE,
        "native_capacity_isolation": {"gate_cd_formal_admission": {
            "attempt_id": "cachetest001", "attempt_cache_root": str(root),
        }},
        "attempt_specific_runtime_cache": {
            **{key: str(value) for key, value in paths.items()},
            "owner": "GateCD_formal_attempt_only", "attempt_id": "cachetest001",
        },
    }
    evidence = _task40_gate_cd_runtime_cache_evidence(
        manifest, environment=environment,
        jit_options_resolver=lambda: {"cache_dir": str(paths["xdg"] / "fenics")},
    )
    assert evidence["cache_paths_verified_before_FE_dispatch"] is True
    assert evidence["owner"] == "GateCD_formal_attempt_only"
    bad = dict(environment, XDG_CACHE_HOME=str(tmp_path / "wrong"))
    with pytest.raises(ValueError, match="environment differs"):
        _task40_gate_cd_runtime_cache_evidence(
            manifest, environment=bad,
            jit_options_resolver=lambda: {"cache_dir": str(paths["xdg"] / "fenics")},
        )


def test_native_capacity_launch_lock_uses_gate_cd_one_shot_not_legacy_lock(
    tmp_path, monkeypatch
):
    from contextlib import contextmanager

    from src.runners import native_capacity
    from src.runners import task40_gate_cd_formal_admission as gate_admission

    scope_path, scope_sha, _ = _scope(tmp_path, "locktest0001")
    monkeypatch.setenv(gate_admission.GATE_CD_SCOPE_PATH_ENV, str(scope_path))
    monkeypatch.setenv(gate_admission.GATE_CD_SCOPE_SHA_ENV, scope_sha)
    monkeypatch.setenv(gate_admission.GATE_CD_LOCK_DIRECTORY_ENV, str(tmp_path))
    for name in (
        "TASK40_PARALLEL_AUTHORIZATION_FILE", "TASK40_PARALLEL_AUTHORIZATION_SHA256",
        "TASK40_EXACT_PARALLEL_PAIR_SCOPE", "TASK40_EXACT_PARALLEL_PAIR_SCOPE_SHA256",
        "TASK40_D07C_G5_SCOPE_PATH", "TASK40_D07C_G5_SCOPE_SHA256",
    ):
        monkeypatch.delenv(name, raising=False)
    common = tmp_path / "task-repository.git"
    common.mkdir()
    monkeypatch.setattr(
        native_capacity.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=str(common), returncode=0),
    )
    monkeypatch.setattr(
        native_capacity, "_native_capacity_host_lock",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy lock used")),
    )
    observed = {}

    lease = SimpleNamespace(
        scope_path=scope_path, scope_sha256=scope_sha, member_stream=object(),
        member_path=tmp_path / "gate_cd_member.lock",
    )

    @contextmanager
    def fake_lease(profile, run_id, **kwargs):
        observed.update(profile=profile, run_id=run_id, **kwargs)
        yield lease

    monkeypatch.setattr(gate_admission, "gate_cd_runtime_lease", fake_lease)
    with native_capacity._native_capacity_launch_lock(
        tmp_path / "unused-root", GATE_CD_FORMAL_PROFILE,
        GATE_CD_FORMAL_PROFILE, expected_identity=_identity(),
        submission_mode="fresh_check",
    ) as (_stream, member_path, canonical_repository, context):
        assert member_path.name == "gate_cd_member.lock"
        assert canonical_repository == common
        assert context["scope_sha256"] == scope_sha
    assert observed["submission_mode"] == "fresh_check"
    assert observed["expected_identity"] == _identity()


def test_native_capacity_guard_uses_gate_cd_lease_summary_and_cleanup(
    tmp_path, monkeypatch
):
    from src.io import execution_plan
    from src.runners import native_capacity
    from src.runners import reviewed_workstation_admission as admission
    from src.runners import task40_gate_cd_formal_admission as gate_admission

    scope_path, scope_sha, scope = _scope(tmp_path, "guardpath0001")
    real_lease = gate_admission.gate_cd_runtime_lease

    def deterministic_lease(*args, **kwargs):
        kwargs["cpu_selector"] = lambda *_a: {
            "supervisor_cpu": 9,
            "worker_cpu": 24,
            "worker_cpus": [24],
            "exclusive_cpu_ownership": False,
        }
        return real_lease(*args, **kwargs)

    monkeypatch.setattr(gate_admission, "gate_cd_runtime_lease", deterministic_lease)
    monkeypatch.setattr(execution_plan, "native_memory_policy_prefix", lambda _policy: [])
    monkeypatch.setattr(native_capacity.os, "sched_setaffinity", lambda *_a: None)
    monkeypatch.setattr(native_capacity.os, "sched_getaffinity", lambda *_a: {9})
    monkeypatch.setattr(native_capacity, "_launch_swap_snapshot", lambda: {
        "stable_two_read_baseline": True,
        "preexisting_global_swap_bytes": 0,
    })
    monkeypatch.setattr(
        native_capacity, "_validate_preexisting_swap",
        lambda _snapshot, **_kwargs: "observe_only_zero_preexisting_global_swap",
    )
    monkeypatch.setattr(native_capacity, "_cpu_launch_snapshot", lambda _cpus: {})
    monkeypatch.setattr(
        admission,
        "task40_host_floor_interleaved_admission",
        lambda *_a, **_k: {
            "resource_stop_policy": "host_available_floor_v1",
            "minimum_available_bytes": 64 * 1024**3,
            "rss_hard_limit_bytes": None,
        },
    )
    monkeypatch.setenv("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setenv(gate_admission.GATE_CD_SCOPE_PATH_ENV, str(scope_path))
    monkeypatch.setenv(gate_admission.GATE_CD_SCOPE_SHA_ENV, scope_sha)
    monkeypatch.setenv(gate_admission.GATE_CD_LOCK_DIRECTORY_ENV, str(tmp_path))
    monkeypatch.setenv(gate_admission.GATE_CD_SUBMISSION_MODE_ENV, "fresh_check")

    with native_capacity.native_capacity_guard(
        GATE_CD_FORMAL_PROFILE,
        memory_policy="interleave_nodes0_1",
        task_run_id=GATE_CD_FORMAL_PROFILE,
        submission_mode="fresh_check",
        expected_identity=_identity(),
    ) as (root, isolation):
        assert root.is_dir()
        facts = isolation["gate_cd_formal_admission"]
        assert facts["attempt_id"] == "guardpath0001"
        assert facts["canonical_heavy_lock_touched"] is False
        assert isolation["exact_parallel_pair"] is None
        assert isolation["native_capacity_lock_scope"] == (
            "gate_cd_exact_one_shot_case_lease_no_canonical_lock"
        )
        paths = scope["runtime_paths"]
        reservation = Path(paths["one_shot_reservation"])
        cache_root = Path(paths["attempt_cache_root"])
        assert not reservation.exists()
        assert not cache_root.exists()
    assert not reservation.exists()
    assert not cache_root.exists()
