"""Exercise the exact Task40 parallel-neighbor exception through run_case."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.runners import native_capacity
from src.runners import reviewed_workstation_admission as admission

REPO = Path(__file__).resolve().parents[2]
INPUT = REPO / "input/task40para_phi90_mesh_modes_direct/d15_z3_3_r13_p6_direct.dat"
ROOT_PID = 81001
MPI_PID = 81002
PROXY_PID = 81003
WORKER_PID = 81004
WRAPPER_PID = 81000
ANCHOR_PID = 80000
RUN_ID = "task41extra_b0_p6_phi90_07nm_iterative"
RUN_DIRECTORY_NAME = "task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z"


def _proc_stat(pid, ppid, start_ticks, *, user=100, system=4, cpu=24):
    fields = ["0"] * 37
    fields[0] = "S"
    fields[1] = str(ppid)
    fields[11] = str(user)
    fields[12] = str(system)
    fields[19] = str(start_ticks)
    fields[36] = str(cpu)
    return f"{pid} (python) " + " ".join(fields) + "\n"


def _write_process(proc_root, node, *, rss_bytes=100_000_000, thread=False):
    process = proc_root / str(node["pid"])
    process.mkdir(parents=True, exist_ok=True)
    (process / "stat").write_text(
        _proc_stat(node["pid"], node["ppid"], node["start_ticks"])
    )
    status = (
        f"Name:\tpython\nVmRSS:\t{rss_bytes // 1024} kB\nThreads:\t1\n"
        "Cpus_allowed_list:\t0-47\nMems_allowed_list:\t0-1\n"
    )
    (process / "status").write_text(status)
    (process / "cmdline").write_bytes(b"\0".join(
        value.encode() for value in node["argv"]
    ) + b"\0")
    (process / "cwd").symlink_to(node["cwd"])
    if thread:
        task = process / "task" / str(node["pid"])
        task.mkdir(parents=True)
        (task / "stat").write_text(
            _proc_stat(node["pid"], node["ppid"], node["start_ticks"])
        )
        (task / "status").write_text(status)


def _fixture(
    tmp_path, monkeypatch, *, large_neighbor=True, authorize=True,
    anchor_verified=True,
):
    proc_root = tmp_path / "proc"
    sys_root = tmp_path / "sys"
    cgroup = sys_root / "fs/cgroup/task40"
    cgroup.mkdir(parents=True)
    (cgroup / "cpuset.cpus.effective").write_text("0-47\n")
    (proc_root / "self").mkdir(parents=True)
    (proc_root / "self/status").write_text(
        "Mems_allowed_list:\t0-1\nCpus_allowed_list:\t0-47\n"
    )
    for node in (0, 1):
        base = sys_root / f"devices/system/node/node{node}"
        base.mkdir(parents=True)
        (base / "meminfo").write_text(
            f"Node {node} MemTotal: 1000000 kB\nNode {node} MemFree: 500000 kB\n"
        )
        (base / "cpulist").write_text("0-23\n" if node == 0 else "24-47\n")
    topology = sys_root / "devices/system/cpu/cpu24/topology"
    topology.mkdir(parents=True)
    (topology / "physical_package_id").write_text("0\n")
    (topology / "core_id").write_text("24\n")

    run_directory = (tmp_path / RUN_DIRECTORY_NAME).resolve()
    run_directory.mkdir(parents=True)
    input_path = INPUT.resolve()
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    resolved_path = run_directory / "resolved_config.json"
    resolved_raw = b'{"identity":"fixture-resolved"}\n'
    resolved_path.write_bytes(resolved_raw)
    resolved_sha = hashlib.sha256(resolved_raw).hexdigest()
    manifest = {
        "run_id": RUN_ID,
        "model_id": "task41extra_phi90_p50x50_g17x20",
        "input_sha256": input_sha,
        "physical_model_sha256": "a" * 64,
        "source_sha": "b" * 40,
        "resolved_config_sha256": resolved_sha,
        "method": "full3d_iterative",
        "output_directory": str(run_directory),
    }
    manifest_raw = json.dumps(manifest, sort_keys=True).encode() + b"\n"
    manifest_path = run_directory / "run_manifest.json"
    manifest_path.write_bytes(manifest_raw)

    python = "/shared/venv/bin/python"
    wrapper = {
        "role": "service_wrapper", "pid": WRAPPER_PID, "ppid": ANCHOR_PID,
        "start_ticks": 1000, "cwd": "/home/fenics/Projects/laptop_share",
        "argv": [python, "scripts/task40_v20_service_workflow.py", "run-service"],
    }
    root = {
        "role": "root", "pid": ROOT_PID, "ppid": WRAPPER_PID,
        "start_ticks": 1001, "cwd": "/home/fenics/Projects/laptop_share",
        "argv": [python, "scripts/run_case.py", str(input_path),
                 "--task41-p0-execution-contract", "/tmp/task41-contract.json"],
    }
    # This deliberately mirrors the live mpiexec argv: its command line embeds
    # the Python Task038 worker, so the production classifier sees it as a
    # second task038_input_worker solver candidate.
    mpi = {
        "role": "mpi", "pid": MPI_PID, "ppid": ROOT_PID,
        "start_ticks": 1002, "cwd": "/home/fenics/Projects/laptop_share",
        "argv": ["/usr/bin/mpiexec", "-n", "1", python, "-m",
                 "src.runners.task038_input_worker", "--resolved-config",
                 str(resolved_path), "--manifest", str(manifest_path),
                 "--expected-output-directory", str(run_directory)],
    }
    proxy = {
        "role": "proxy", "pid": PROXY_PID, "ppid": MPI_PID,
        "start_ticks": 1003, "cwd": "/home/fenics/Projects/laptop_share",
        "argv": ["/usr/bin/hydra_pmi_proxy", "--proxy-id", "0"],
    }
    worker = {
        "role": "worker", "pid": WORKER_PID, "ppid": PROXY_PID,
        "start_ticks": 1004, "cwd": "/home/fenics/Projects/laptop_share",
        "argv": [python, "-m", "src.runners.task038_input_worker",
                 "--resolved-config", str(resolved_path), "--manifest",
                 str(manifest_path), "--expected-output-directory", str(run_directory)],
    }
    nodes = [wrapper, root, mpi, proxy, worker]
    for node in nodes:
        rss = 120_000_000_000 if large_neighbor and node["role"] == "worker" else 50_000_000
        _write_process(proc_root, node, rss_bytes=rss,
                       thread=node["role"] in ("root", "worker"))
    anchor = {
        "pid": ANCHOR_PID, "ppid": 1, "start_ticks": 999,
        "cwd": "/", "argv": ["/sbin/init"],
    }
    if anchor_verified:
        _write_process(proc_root, anchor)

    cpu_record = {
        "sample_seconds": 3.0,
        "exclusive_cpu_claim": False,
        "neighbor_threads": [
            {"pid": ROOT_PID, "tid": ROOT_PID, "start_ticks": root["start_ticks"]},
            {"pid": WORKER_PID, "tid": WORKER_PID, "start_ticks": worker["start_ticks"]},
        ],
    }
    cpu_path = tmp_path / "cpu_sample.json"
    cpu_path.write_text(json.dumps(cpu_record, sort_keys=True) + "\n")
    parent_authority = {
        "schema": "task40.user_parallel_authority.v1",
        "scope": {"task": "Task40"},
        "authorized_neighbor_identity": [
            {"role": "root", "pid": ROOT_PID, "start_ticks": root["start_ticks"]},
            {"role": "MPI", "pid": MPI_PID, "start_ticks": mpi["start_ticks"]},
            {"role": "worker", "pid": WORKER_PID, "start_ticks": worker["start_ticks"]},
        ],
    }
    parent_path = tmp_path / "user_authority.json"
    parent_path.write_text(json.dumps(parent_authority, sort_keys=True) + "\n")
    parent_sha = hashlib.sha256(parent_path.read_bytes()).hexdigest()
    record = {
        "schema": "task40.cross_project_parallel_authority.v1",
        "scope": {"task40_runs": [
            {"profile_identity": "task40para_phi90_13p5_D15_Z3_3_p6_direct_v1",
             "run_id": "task40_phi90_13p5_D15_Z3_3_p6_direct_v1"},
            {"profile_identity": "task40para_phi90_13p5_D15_X2_p6_direct_v1",
             "run_id": "task40_phi90_13p5_D15_X2_p6_direct_v1"},
        ]},
        "parent_user_authority_path": str(parent_path),
        "parent_user_authority_sha256": parent_sha,
        "cpu_activity_sample_path": str(cpu_path),
        "cpu_activity_sample_sha256": hashlib.sha256(cpu_path.read_bytes()).hexdigest(),
        "task41_neighbor": {
            "run_id": RUN_ID,
            "run_directory": str(run_directory),
            "input_path": str(input_path),
            "input_sha256": input_sha,
            "run_manifest_path": str(manifest_path),
            "run_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "resolved_config_path": str(resolved_path),
            "resolved_config_sha256": resolved_sha,
            "model_id": manifest["model_id"],
            "physical_model_sha256": manifest["physical_model_sha256"],
            "source_sha": manifest["source_sha"],
            "method": manifest["method"],
            "output_directory": str(run_directory),
            "processes": nodes,
            "parent_anchor": (
                anchor if anchor_verified else {
                    "pid": ANCHOR_PID,
                    "identity_status": "proc_visibility_denied",
                }
            ),
        },
    }
    auth_path = tmp_path / "parallel_authority.json"
    auth_path.write_text(json.dumps(record, sort_keys=True) + "\n")
    auth_sha = hashlib.sha256(auth_path.read_bytes()).hexdigest()

    monkeypatch.setattr(admission, "_proc_root", lambda: proc_root)
    monkeypatch.setattr(admission, "_sys_root", lambda: sys_root)
    monkeypatch.setattr(admission, "_sleep_for_cpu_sample", lambda _seconds: None)
    monkeypatch.setattr(admission, "_interleave_probe", lambda: SimpleNamespace(
        returncode=0, stdout='["interleave 0-1"]', stderr=""
    ))
    import benchmarks.subreaper_watchdog as watchdog
    import benchmarks.task034_wsl_resources as resources_module
    monkeypatch.setattr(watchdog, "memory_envelope", lambda: {
        "effective_available_bytes": 2_000_000_000_000,
        "effective_total_bytes": 2_100_000_000_000,
    })
    monkeypatch.setattr(resources_module, "current_cgroup_path", lambda: cgroup)

    import src.runners.task038_launcher as launcher
    fake_run = tmp_path / "task40_fake_run"

    def fake_launch(_specification, **_kwargs):
        fake_run.mkdir(exist_ok=True)
        return {
            "run_directory": str(fake_run),
            "result_classification": "worker_exit0",
            "exit_status": 0,
        }

    monkeypatch.setattr(launcher, "launch_specification", fake_launch)
    monkeypatch.setattr(native_capacity, "_native_capacity_host_lock", lambda *_args: (
        tmp_path / "host.lock", tmp_path / "task-repository.git"
    ))
    monkeypatch.setattr(native_capacity, "_launch_swap_snapshot", dict)
    monkeypatch.setattr(native_capacity, "_validate_preexisting_swap", lambda *_a, **_k: "observe_only")
    monkeypatch.setattr(native_capacity, "_cpu_launch_snapshot", lambda _cpus: {"cpus": {}})
    monkeypatch.setattr(native_capacity.os, "sched_setaffinity", lambda *_args: None)
    monkeypatch.setattr(native_capacity.os, "sched_getaffinity", lambda _pid: {9})
    monkeypatch.setenv("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION", "1")
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
    monkeypatch.setenv("MKL_NUM_THREADS", "1")
    monkeypatch.setenv("BLIS_NUM_THREADS", "1")
    monkeypatch.setenv("NUMEXPR_NUM_THREADS", "1")
    if authorize:
        monkeypatch.setenv("TASK40_PARALLEL_AUTHORIZATION_FILE", str(auth_path))
        monkeypatch.setenv("TASK40_PARALLEL_AUTHORIZATION_SHA256", auth_sha)
    else:
        monkeypatch.delenv("TASK40_PARALLEL_AUTHORIZATION_FILE", raising=False)
        monkeypatch.delenv("TASK40_PARALLEL_AUTHORIZATION_SHA256", raising=False)
    return {
        "proc_root": proc_root,
        "nodes": nodes,
        "authorization_path": auth_path,
        "authorization_sha256": auth_sha,
        "fake_run": fake_run,
    }


def test_task40_run_case_allows_exact_authorized_task41_tree_including_mpiexec_worker_argv(
    tmp_path, monkeypatch, capsys
):
    state = _fixture(tmp_path, monkeypatch, large_neighbor=True, authorize=True)
    from scripts.run_case import main

    assert main([str(INPUT)]) == 0
    capsys.readouterr()
    isolation = json.loads((state["fake_run"] / "workstation_isolation.json").read_text())
    admission_result = isolation["node_memory_admission"]
    assert admission_result["parallel_neighbor_authorized"] is True
    assert admission_result["parallel_neighbor_authorization"]["parent_anchor"][
        "identity_verified"
    ] is True
    assert {row["pid"] for row in admission_result["parallel_authorized_solver_candidates"]} == {
        ROOT_PID, MPI_PID, WORKER_PID,
    }
    assert admission_result["blocking_active_solver_candidates"] == []
    assert admission_result["blocking_large_processes"] == []
    assert admission_result["minimum_available_bytes"] == 64 * 1024**3
    assert admission_result["rss_hard_limit_bytes"] is None
    assert admission_result["parallel_neighbor_authorization"][
        "cpu_activity_sample"]["exclusive_cpu_claim"] is False


def test_task40_run_case_keeps_default_deny_without_authorization(
    tmp_path, monkeypatch, capsys
):
    _fixture(tmp_path, monkeypatch, large_neighbor=False, authorize=False)
    from scripts.run_case import main

    assert main([str(INPUT)]) == 2
    assert "another active run_case/native solver process" in capsys.readouterr().err


def test_task40_run_case_does_not_claim_unreadable_anchor_was_verified(
    tmp_path, monkeypatch, capsys
):
    state = _fixture(
        tmp_path, monkeypatch, large_neighbor=False, authorize=True,
        anchor_verified=False,
    )
    from scripts.run_case import main

    assert main([str(INPUT)]) == 0
    capsys.readouterr()
    isolation = json.loads((state["fake_run"] / "workstation_isolation.json").read_text())
    anchor = isolation["node_memory_admission"]["parallel_neighbor_authorization"][
        "parent_anchor"
    ]
    assert anchor["identity_verified"] is False


@pytest.mark.parametrize("identity_field", ["start_ticks", "ppid", "cwd", "argv"])
def test_task40_run_case_rejects_task41_identity_drift_before_launch(
    identity_field, tmp_path, monkeypatch, capsys
):
    state = _fixture(tmp_path, monkeypatch, large_neighbor=False, authorize=True)
    node = next(item for item in state["nodes"] if item["role"] == "mpi")
    process = state["proc_root"] / str(node["pid"])
    if identity_field in ("start_ticks", "ppid"):
        changed_ticks = node["start_ticks"] + (1 if identity_field == "start_ticks" else 0)
        changed_ppid = node["ppid"] + (1 if identity_field == "ppid" else 0)
        (process / "stat").write_text(
            _proc_stat(node["pid"], changed_ppid, changed_ticks)
        )
    elif identity_field == "cwd":
        (process / "cwd").unlink()
        (process / "cwd").symlink_to("/tmp/other-worktree")
    else:
        (process / "cmdline").write_bytes(
            b"\0".join(value.encode() for value in node["argv"] + ["--different"]) + b"\0"
        )

    from scripts.run_case import main

    assert main([str(INPUT)]) == 2
    assert not state["fake_run"].exists()
    assert "differs from bound identity" in capsys.readouterr().err


def test_task40_run_case_rejects_unrelated_huge_process_even_with_task41_exception(
    tmp_path, monkeypatch, capsys
):
    state = _fixture(tmp_path, monkeypatch, large_neighbor=True, authorize=True)
    unrelated = {
        "role": "other", "pid": 81005, "ppid": 1, "start_ticks": 1010,
        "cwd": "/tmp", "argv": ["/usr/bin/python3", "-c", "sleep(10)"],
    }
    _write_process(state["proc_root"], unrelated, rss_bytes=120_000_000_000)
    from scripts.run_case import main

    assert main([str(INPUT)]) == 2
    assert not state["fake_run"].exists()
    assert "non-authorized process >=100 GB" in capsys.readouterr().err


def test_task40_run_case_rejects_unknown_worker_role_with_task41_exception(
    tmp_path, monkeypatch, capsys
):
    state = _fixture(tmp_path, monkeypatch, large_neighbor=False, authorize=True)
    unknown = {
        "role": "unknown", "pid": 81005, "ppid": 1, "start_ticks": 1010,
        "cwd": "/tmp", "argv": ["/shared/venv/bin/python", "task038_future_worker.py"],
    }
    _write_process(state["proc_root"], unknown)
    from scripts.run_case import main

    assert main([str(INPUT)]) == 2
    assert not state["fake_run"].exists()
    assert "unknown role" in capsys.readouterr().err


def test_task40_run_case_keeps_duplicate_task40_rejection_with_parallel_exception(
    tmp_path, monkeypatch, capsys
):
    state = _fixture(tmp_path, monkeypatch, large_neighbor=False, authorize=True)
    duplicate = {
        "role": "duplicate_task40", "pid": 81005, "ppid": 1, "start_ticks": 1010,
        "cwd": str(REPO),
        "argv": ["/shared/venv/bin/python", str(REPO / "scripts/run_case.py"),
                 str(REPO / "input/task40para_phi90_mesh_modes_direct/d15_x2_r13_p6_direct.dat")],
    }
    _write_process(state["proc_root"], duplicate)
    from scripts.run_case import main

    assert main([str(INPUT)]) == 2
    assert not state["fake_run"].exists()
    assert "another active run_case/native solver process" in capsys.readouterr().err


def test_task40_run_case_rechecks_full_task41_identity_after_cpu_sample(
    tmp_path, monkeypatch, capsys
):
    state = _fixture(tmp_path, monkeypatch, large_neighbor=False, authorize=True)
    mpi = next(item for item in state["nodes"] if item["role"] == "mpi")

    def replace_process_during_sample(_seconds):
        path = state["proc_root"] / str(MPI_PID) / "stat"
        path.write_text(_proc_stat(MPI_PID, mpi["ppid"], mpi["start_ticks"] + 1))

    monkeypatch.setattr(admission, "_sleep_for_cpu_sample", replace_process_during_sample)
    from scripts.run_case import main

    assert main([str(INPUT)]) == 2
    assert not state["fake_run"].exists()
    assert "Task41 mpi after CPU sample start_ticks differs" in capsys.readouterr().err


@pytest.mark.parametrize("field", ["start_ticks", "ppid", "cwd", "argv"])
def test_candidate_final_allow_requires_every_bound_process_field(field):
    node = {
        "role": "mpi", "pid": MPI_PID, "ppid": ROOT_PID, "start_ticks": 1002,
        "cwd": "/home/fenics/Projects/laptop_share", "argv": [
            "/usr/bin/mpiexec", "-n", "1", "/shared/venv/bin/python", "-m",
            "src.runners.task038_input_worker",
        ],
    }
    candidate = {
        "pid": MPI_PID, "ppid": ROOT_PID, "start_ticks": 1002,
        "cwd": node["cwd"], "argv": list(node["argv"]),
        "kind": "task_solver", "role": "task038_input_worker",
        "entrypoint": "src.runners.task038_input_worker",
    }
    expected = {
        "node": node,
        "classification": {
            "kind": "task_solver", "role": "task038_input_worker",
            "entrypoint": "src.runners.task038_input_worker",
        },
    }
    assert admission._candidate_matches_authorized_node(candidate, expected)
    mutated = dict(candidate)
    mutated[field] = {
        "argv": candidate["argv"] + ["--different"],
        "cwd": "/tmp/other-worktree",
        "ppid": 999,
        "start_ticks": 9999,
    }[field]
    assert not admission._candidate_matches_authorized_node(mutated, expected)
