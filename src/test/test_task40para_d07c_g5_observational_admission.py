"""G5-only production admission and dynamic CPU route, with no FE launch."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.input_validation import load_and_resolve
from src.io.native_capacity_profile import (
    TASK40_PHI90_D07C_PROFILE_BY_CASE,
    native_profile_facts,
)
from src.io.resolved_config import resolved_config_sha256
from src.runners import native_capacity
from src.runners import reviewed_workstation_admission as admission
from src.runners import task40_d07c_g5_join as g5_join
from src.runners.task038_input_worker import _task40_g5_runtime_cache_evidence

W = Path(__file__).resolve().parents[2]
G5_INPUT = W / "input/task40para_phi90_mesh_modes_direct/d07c_g5_m8_nminus64_to1_p6_direct.dat"
G5_PROFILE = "task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1"
G5_RUN_ID = G5_PROFILE


def _scope(tmp_path: Path, identity: dict | None = None, *, attempt_id="g5test2026"):
    member, reservation = g5_join._case_lock_paths(G5_PROFILE, G5_RUN_ID, tmp_path)
    value = {
        "schema": g5_join.G5_SCOPE_SCHEMA,
        "attempt_id": attempt_id,
        "identity": identity or {
            "profile_identity": G5_PROFILE,
            "run_id": G5_RUN_ID,
        },
        "resource_contract": {
            "mode": "host_available_floor_v1",
            "minimum_available_bytes": 64 * 1024**3,
            "rss_hard_limit_bytes": None,
            "swap_policy": "observe_only",
            "stop_on_global_swap": False,
            "pss_uss_sampling": "disabled",
        },
        "neighbor_policy": {
            "policy": "g5_scoped_observational_neighbors_v1",
            "neighbors_block_admission": False,
            "unknown_solver_candidates_block_admission": False,
            "large_process_candidates_block_admission": False,
            "neighbors_modified": False,
        },
        "cpu_policy": {
            "selection": "sampled_low_load_distinct_physical_cores_v1",
            "sample_seconds": 1.5,
            "busy_fallback_allowed": True,
            "exclusive_cpu_ownership": False,
        },
        "runtime_paths": {
            "member_lock": str(member),
            "one_shot_reservation": str(reservation),
            "attempt_cache_root": str(g5_join._attempt_cache_root(attempt_id)),
        },
    }
    path = tmp_path / f"{attempt_id}.scope.json"
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest(), value


def _proc_identity(proc_root: Path, pid: int, argv: list[str], *, rss_kb=1024, affinity="0-47"):
    proc = proc_root / str(pid)
    proc.mkdir(parents=True)
    fields = ["0"] * 37
    fields[0], fields[1], fields[19] = "S", "1", str(pid * 17)
    (proc / "stat").write_text(f"{pid} (python) " + " ".join(fields) + "\n")
    (proc / "status").write_text(
        f"Name:\tpython\nVmRSS:\t{rss_kb} kB\nThreads:\t1\n"
        f"Cpus_allowed_list:\t{affinity}\nMems_allowed_list:\t0-1\n"
    )
    (proc / "cmdline").write_bytes(b"\0".join(x.encode() for x in argv) + b"\0")
    cwd = proc_root / f"cwd-{pid}"
    cwd.mkdir()
    (proc / "cwd").symlink_to(cwd)


def _admission_roots(tmp_path: Path, monkeypatch, *, candidates=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    proc_root = tmp_path / "proc"
    sys_root = tmp_path / "sys"
    proc_root.mkdir()
    (proc_root / "self").mkdir()
    (proc_root / "self/status").write_text(
        "Mems_allowed_list:\t0-1\nCpus_allowed_list:\t0-47\n"
    )
    cgroup = sys_root / "fs/cgroup/task40"
    cgroup.mkdir(parents=True)
    (cgroup / "cpuset.cpus.effective").write_text("0-47\n")
    for node in (0, 1):
        node_root = sys_root / f"devices/system/node/node{node}"
        node_root.mkdir(parents=True)
        (node_root / "meminfo").write_text(
            f"Node {node} MemTotal: 1000000 kB\nNode {node} MemFree: 800000 kB\n"
        )
        (node_root / "cpulist").write_text("0-47\n")
    for cpu, core in ((3, 3), (17, 17), (9, 9), (24, 24)):
        topology = sys_root / f"devices/system/cpu/cpu{cpu}/topology"
        topology.mkdir(parents=True)
        (topology / "physical_package_id").write_text("0\n")
        (topology / "core_id").write_text(f"{core}\n")
        (topology / "thread_siblings_list").write_text(f"{cpu}\n")
    if candidates:
        _proc_identity(
            proc_root, 51001,
            ["/shared/python", str(W / "scripts/run_case.py"), "neighbor.dat"],
            rss_kb=125_000_000,
        )
        _proc_identity(
            proc_root, 51002,
            ["/shared/python", "-m", "src.runners.task038_future_worker"],
        )
    monkeypatch.setattr(admission, "_proc_root", lambda: proc_root)
    monkeypatch.setattr(admission, "_sys_root", lambda: sys_root)
    monkeypatch.setattr(admission, "_interleave_probe", lambda: SimpleNamespace(
        returncode=0, stdout=json.dumps(["7f0000000000 default anon=1024 interleave:0-1"]), stderr=""
    ))
    import benchmarks.subreaper_watchdog as watchdog
    import benchmarks.task034_wsl_resources as resources

    monkeypatch.setattr(watchdog, "memory_envelope", lambda: {
        "effective_available_bytes": 2 * 1024**4,
        "effective_total_bytes": 2 * 1024**4,
    })
    monkeypatch.setattr(resources, "current_cgroup_path", lambda: cgroup)
    return proc_root, sys_root, cgroup


def test_g5_scope_is_exact_and_g5_profile_has_no_fixed_cpu_reservation(tmp_path):
    path, digest, value = _scope(tmp_path)
    loaded = g5_join.load_g5_scope(
        path, digest, profile=G5_PROFILE, run_id=G5_RUN_ID,
        lock_directory=tmp_path,
    )
    assert loaded == value
    with pytest.raises(g5_join.InputError, match="exact profile/run"):
        g5_join.load_g5_scope(path, digest, profile="other", run_id="other")
    with pytest.raises(g5_join.InputError, match="identity differs"):
        g5_join.load_g5_scope(
            path, digest, profile=G5_PROFILE, run_id=G5_RUN_ID,
            expected_identity={"profile_identity": G5_PROFILE, "run_id": G5_RUN_ID, "source_commit": "wrong"},
        )
    facts = native_profile_facts(G5_PROFILE)
    assert facts["native_execution"]["supervisor_cpu"] is None
    assert facts["native_execution"]["worker_cpus"] == []
    assert facts["resources"]["parallel_admission_policy"] == "g5_scoped_observational_neighbors_v1"
    assert facts["resources"]["concurrent_neighbor_authorized"] is False


def test_exact_g5_host_floor_observes_other_solvers_and_large_processes_without_blocking(
    tmp_path, monkeypatch
):
    _admission_roots(tmp_path, monkeypatch)
    scope_path, scope_sha, _ = _scope(tmp_path)
    resources = native_profile_facts(G5_PROFILE)["resources"]
    result = admission.task40_host_floor_interleaved_admission(
        resources,
        [17],
        task_profile=G5_PROFILE,
        task_run_id=G5_RUN_ID,
        supervisor_cpu=3,
        g5_observational_scope_path=scope_path,
        g5_observational_scope_sha256=scope_sha,
        g5_lock_directory=tmp_path,
    )
    assert result["resource_stop_policy"] == "host_available_floor_v1"
    assert result["rss_hard_limit_bytes"] is None
    assert result["minimum_available_bytes"] == 64 * 1024**3
    assert result["g5_parallel_authorized_by_exact_scope"] is True
    assert result["neighbor_admission_mode"] == "g5_scoped_observational_neighbors_v1"
    assert len(result["g5_observational_scope"]["observed_only_candidate_details"]["active_solver_candidates"]) == 1
    assert len(result["g5_observational_scope"]["observed_only_candidate_details"]["unknown_solver_role_candidates"]) == 1
    assert len(result["g5_observational_scope"]["observed_only_candidate_details"]["large_process_candidates_at_or_above_100gb"]) == 1
    assert result["blocking_active_solver_candidates"] == []
    assert result["blocking_unknown_solver_role_candidates"] == []
    assert len(result["unknown_solver_role_candidates"]) == 1
    assert result["blocking_large_processes"] == []
    assert result["neighbors_modified"] is False


def test_g5_parallel_scope_does_not_weaken_other_profiles_or_host_floor(tmp_path, monkeypatch):
    _admission_roots(tmp_path, monkeypatch)
    scope_path, scope_sha, _ = _scope(tmp_path)
    legacy_profile = TASK40_PHI90_D07C_PROFILE_BY_CASE["B"]
    legacy_resources = native_profile_facts(legacy_profile)["resources"]
    with pytest.raises(admission.InputError, match="G5 observational scope cannot authorize another profile"):
        admission.task40_host_floor_interleaved_admission(
            legacy_resources, [24], task_profile=legacy_profile,
            task_run_id="task40_phi90_0p7_D07C_B_p6_direct_v1",
            g5_observational_scope_path=scope_path,
            g5_observational_scope_sha256=scope_sha,
        )
    import benchmarks.subreaper_watchdog as watchdog
    monkeypatch.setattr(watchdog, "memory_envelope", lambda: {
        "effective_available_bytes": 32 * 1024**3,
        "effective_total_bytes": 2 * 1024**4,
    })
    with pytest.raises(admission.InputError, match="below its explicit floor"):
        admission.task40_host_floor_interleaved_admission(
            native_profile_facts(G5_PROFILE)["resources"], [17],
            task_profile=G5_PROFILE, task_run_id=G5_RUN_ID,
            supervisor_cpu=3,
            g5_observational_scope_path=scope_path,
            g5_observational_scope_sha256=scope_sha,
            g5_lock_directory=tmp_path,
        )


def test_dynamic_execution_plan_places_numactl_then_reserved_taskset_inside_mpiexec(tmp_path):
    specification = load_and_resolve(G5_INPUT)
    from src.io.execution_plan import build_execution_plan

    plan = build_execution_plan(
        specification,
        tmp_path / "run",
        source_sha="d" * 40,
        python_executable="/qualified/shared/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
        worker_cpus_override=[17],
    )
    assert plan.argv[:9] == (
        "/usr/bin/mpiexec", "-n", "1", "/usr/bin/numactl",
        "--interleave=0,1", "/usr/bin/taskset", "-c", "17",
        "/qualified/shared/bin/python",
    )
    from src.io.input_loader import InputError
    with pytest.raises(InputError, match="dynamic one-CPU reservation"):
        build_execution_plan(
            specification,
            tmp_path / "run-no-cpu",
            source_sha="d" * 40,
            python_executable="/qualified/shared/bin/python",
            mpiexec_command="/usr/bin/mpiexec",
        )


def test_g5_cpu_reservation_uses_sampled_load_and_neighbor_affinity(monkeypatch):
    monkeypatch.setattr(g5_join.os, "sched_getaffinity", lambda _pid: {10, 11, 12})
    monkeypatch.setattr(g5_join, "_core", lambda cpu: (0, int(cpu)))
    monkeypatch.setattr(g5_join, "_siblings", lambda cpu: {int(cpu)})
    monkeypatch.setattr(g5_join, "_observe_process_affinities", lambda _root: {
        "scope": "read_only_cpu_affinity_observation",
        "processes": [{"pid": 99, "affinity": [11]}],
        "processes_modified": False,
    })
    before = {cpu: (100, 10) for cpu in (10, 11, 12)}
    after = {
        10: (200, 20),   # 90% busy
        11: (200, 95),   # 15% busy, but overlaps the observed neighbor
        12: (200, 80),   # 30% busy, no observed neighbor affinity
    }
    samples = iter((before, after))
    monkeypatch.setattr(g5_join, "_cpu_ticks", lambda _root: next(samples))
    monkeypatch.setattr(g5_join.time, "sleep", lambda _seconds: None)

    result = g5_join.choose_g5_cpu_reservation(sample_seconds=1.5, proc_root="/fake/proc")

    assert (result["supervisor_cpu"], result["worker_cpu"]) == (12, 10)
    assert result["policy"] == "sampled_low_load_distinct_physical_cores_v1"
    assert result["sample_seconds"] == 1.5
    assert result["exclusive_cpu_ownership"] is False
    assert result["heavy_neighbor_affinity_avoidance"] == (
        "preferred_when_possible_busy_fallback_allowed"
    )
    by_cpu = {row["cpu"]: row for row in result["candidate_topology_and_load"]}
    assert by_cpu[11]["heavy_neighbor_affinity_overlap"] is True
    assert by_cpu[12]["sampled_utilization"] < by_cpu[10]["sampled_utilization"]


def test_g5_worker_verifies_attempt_environment_and_actual_jit_cache_before_fe():
    attempt = "cachetest" + uuid.uuid4().hex[:12]
    root = g5_join._attempt_cache_root(attempt)
    try:
        paths = {
            "root": root,
            "tmp": root / "tmp",
            "xdg": root / "xdg",
            "pycache": root / "pycache",
            "mpl": root / "mpl",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        expected_environment = {
            "TMPDIR": str(paths["tmp"]),
            "TMP": str(paths["tmp"]),
            "TEMP": str(paths["tmp"]),
            "XDG_CACHE_HOME": str(paths["xdg"]),
            "PYTHONPYCACHEPREFIX": str(paths["pycache"]),
            "MPLCONFIGDIR": str(paths["mpl"]),
        }
        manifest = {
            "native_capacity_profile_identity": G5_PROFILE,
            "native_capacity_isolation": {
                "g5_observational_join": {"attempt_id": attempt},
            },
            "attempt_specific_runtime_cache": {
                **{key: str(value) for key, value in paths.items()},
                "owner": "G5_attempt_only",
            },
        }
        evidence = _task40_g5_runtime_cache_evidence(
            manifest,
            environment=expected_environment,
            jit_options_resolver=lambda: {"cache_dir": str(paths["xdg"] / "fenics")},
        )
        assert evidence["cache_paths_verified_before_FE_dispatch"] is True
        assert evidence["dolfinx_jit_cache_dir"] == str(paths["xdg"] / "fenics")
        with pytest.raises(ValueError, match="cache environment differs"):
            _task40_g5_runtime_cache_evidence(
                manifest,
                environment={**expected_environment, "XDG_CACHE_HOME": "/shared/.cache"},
                jit_options_resolver=lambda: {"cache_dir": str(paths["xdg"] / "fenics")},
            )
        with pytest.raises(ValueError, match="DOLFINx JIT cache"):
            _task40_g5_runtime_cache_evidence(
                manifest,
                environment=expected_environment,
                jit_options_resolver=lambda: {"cache_dir": "/shared/.cache/fenics"},
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_run_case_to_native_guard_commits_one_g5_reservation_without_fe(tmp_path, monkeypatch, capsys):
    specification = load_and_resolve(G5_INPUT)
    commit = __import__("subprocess").check_output(
        ["git", "rev-parse", "HEAD"], cwd=W, text=True
    ).strip()
    identity = {
        "profile_identity": G5_PROFILE,
        "run_id": G5_RUN_ID,
        "input_path": str(specification.source_path.resolve()),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_config_sha256(specification),
        "resolved_output_parent_absolute": str(specification.expected_output_parent.resolve()),
        "source_commit": commit,
    }
    scope_path, scope_sha, value = _scope(tmp_path, identity, attempt_id="g5prod2026")
    member, reservation = g5_join._case_lock_paths(G5_PROFILE, G5_RUN_ID, tmp_path)
    value["runtime_paths"].update(
        member_lock=str(member), one_shot_reservation=str(reservation)
    )
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    scope_path.write_bytes(raw)
    scope_sha = hashlib.sha256(raw).hexdigest()
    monkeypatch.setenv("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setenv(g5_join.G5_SCOPE_PATH_ENV, str(scope_path))
    monkeypatch.setenv(g5_join.G5_SCOPE_SHA_ENV, scope_sha)
    monkeypatch.setenv("TASK40_D07C_G5_LOCK_DIRECTORY", str(tmp_path))
    monkeypatch.delenv("TASK40_PARALLEL_AUTHORIZATION_FILE", raising=False)
    monkeypatch.delenv("TASK40_PARALLEL_AUTHORIZATION_SHA256", raising=False)
    monkeypatch.delenv("TASK40_EXACT_PARALLEL_PAIR_SCOPE_PATH", raising=False)
    monkeypatch.delenv("TASK40_EXACT_PARALLEL_PAIR_SCOPE_SHA256", raising=False)
    _admission_roots(tmp_path / "host", monkeypatch, candidates=True)
    monkeypatch.setattr(g5_join, "choose_g5_cpu_reservation", lambda **_kwargs: {
        "policy": "sampled_low_load_distinct_physical_cores_v1",
        "sample_seconds": 1.5,
        "supervisor_cpu": 3,
        "worker_cpu": 17,
        "selected_topology": [{"cpu": 3}, {"cpu": 17}],
        "exclusive_cpu_ownership": False,
    })
    monkeypatch.setattr(native_capacity.os, "sched_setaffinity", lambda *_args: None)
    monkeypatch.setattr(native_capacity, "_launch_swap_snapshot", lambda: {"fake": True})
    monkeypatch.setattr(native_capacity, "_validate_preexisting_swap", lambda _s, *, observe_only: "observe_only")
    monkeypatch.setattr(native_capacity, "_cpu_launch_snapshot", lambda _cpus: {"sampled": True})

    import src.runners.task038_launcher as launcher
    from src.io.execution_plan import build_execution_plan

    run_dir = tmp_path / "fake-launched-run"

    def fake_launch(spec, *, prelaunch_isolation, **_kwargs):
        run_dir.mkdir()
        plan = build_execution_plan(
            spec, run_dir, source_sha=commit,
            python_executable="/qualified/shared/bin/python",
            mpiexec_command="/usr/bin/mpiexec",
            worker_cpus_override=prelaunch_isolation["worker_affinity"],
        )
        assert plan.argv[:8] == (
            "/usr/bin/mpiexec", "-n", "1", "/usr/bin/numactl",
            "--interleave=0,1", "/usr/bin/taskset", "-c", "17",
        )
        assert prelaunch_isolation["native_capacity_lock_scope"] == "g5_case_level_member_lock_no_canonical"
        assert prelaunch_isolation["native_capacity_heavy_lock"] == str(member.resolve())
        assert prelaunch_isolation["node_memory_admission"]["g5_parallel_authorized_by_exact_scope"] is True
        assert prelaunch_isolation["node_memory_admission"]["minimum_available_bytes"] == 64 * 1024**3
        assert prelaunch_isolation["native_capacity_lock_scope"] != "canonical_host_shared_with_task39_worktrees"
        return {"run_directory": str(run_dir), "exit_status": 0, "result_classification": "worker_exit0"}

    monkeypatch.setattr(launcher, "launch_specification", fake_launch)
    from scripts.run_case import main as run_case_main

    status = run_case_main([str(G5_INPUT)])
    assert status == 0
    result_line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(result_line)["result_classification"] == "worker_exit0"
    assert reservation.is_file()
    with (
        pytest.raises(admission.InputError, match="one-shot reservation already exists"),
        native_capacity._native_capacity_launch_lock(
            W, G5_PROFILE, G5_RUN_ID,
            expected_identity=identity, submission_mode="fresh_check",
        ),
    ):
        pass
