"""Focused no-FE tests for the exact two-member Task40 parallel window."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io.input_loader import InputError
from src.runners import native_capacity
from src.runners import reviewed_workstation_admission as admission
from src.runners import task40_exact_parallel_pair as pair
from src.runners.task40_exact_parallel_pair import (
    MEMBERS,
    PAIR_ID,
    acquire_pair_runtime_locks,
    acquire_pair_submission_handshake,
    load_pair_scope,
    pair_member_registry_path,
    pair_submission_receipt_path,
    peer_authorized_process_nodes,
    publish_live_binding_once,
    record_pair_submission_once,
    reserve_pair_submission_once,
    role_for_identity,
    validate_active_roles,
    validate_live_binding_payload,
    verify_live_binding,
)

G3_ROLE = "0p7nm_g3_m8_n64"
FIVE_ROLE = "5nm_ten_layer_m7_n9"
G3_PROFILE = MEMBERS[G3_ROLE]["profile_identity"]
G3_RUN = MEMBERS[G3_ROLE]["run_id"]
FIVE_PROFILE = MEMBERS[FIVE_ROLE]["profile_identity"]
FIVE_RUN = MEMBERS[FIVE_ROLE]["run_id"]


def _review_scope():
    return {
        "cpu_reservation": {
            "assignment_is_pair_local_not_exclusive_host_ownership": True,
            "g3_m8_n64": {
                "supervisor_and_mpi_cpu": 9,
                "worker_cpu": 24,
                "expected_topology": {
                    "9": {"package": 0, "core": 11, "thread_siblings": "9"},
                    "24": {"package": 1, "core": 0, "thread_siblings": "24"},
                },
            },
            "ten_layer_m7_n9": {
                "supervisor_and_mpi_cpu": 25,
                "worker_cpu": 26,
                "expected_topology": {
                    "25": {"package": 1, "core": 1, "thread_siblings": "25"},
                    "26": {"package": 1, "core": 2, "thread_siblings": "26"},
                },
            },
        }
    }


def _scope_tree(tmp_path, monkeypatch, *, canonical_lock_path=None):
    if canonical_lock_path is not None:
        monkeypatch.setattr(pair, "CANONICAL_HEAVY_LOCK_PATH", Path(canonical_lock_path))
    root = tmp_path / "repository"
    evidence = root / "docs/task40para_phi90_multilayer5nm_exec/evidence/preflight"
    evidence.mkdir(parents=True)
    receipt_specs = {
        "reviewer_parallel_pair_coordination.json": "coordination",
        "reviewer_parallel_pair_proposal.json": "proposal",
        "reviewer_g3_inventory_receipt.json": "inventory",
        "reviewer_canonical_lock_path_correction.json": "canonical_lock_correction",
    }
    receipt_hashes = {}
    for name, value in receipt_specs.items():
        path = evidence / name
        path.write_text(json.dumps({"kind": value}, sort_keys=True) + "\n")
        receipt_hashes[value] = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(pair, "COORDINATION_SHA256", receipt_hashes["coordination"])
    monkeypatch.setattr(pair, "PROPOSAL_V2_SHA256", receipt_hashes["proposal"])
    monkeypatch.setattr(pair, "INVENTORY_SHA256", receipt_hashes["inventory"])
    members = []
    for role, member in MEMBERS.items():
        members.append({
            "role": role,
            "profile_identity": member["profile_identity"],
            "run_id": member["run_id"],
            "mode_count": member["mode_count"],
            "mode_sha256": member["mode_sha256"],
            "cpu_reservation_ref": (
                "cpu_reservation.g3_m8_n64" if role == G3_ROLE
                else "cpu_reservation.ten_layer_m7_n9"
            ),
        })
    coordination_path = "docs/task40para_phi90_multilayer5nm_exec/evidence/preflight/reviewer_parallel_pair_coordination.json"
    proposal_path = "docs/task40para_phi90_multilayer5nm_exec/evidence/preflight/reviewer_parallel_pair_proposal.json"
    inventory_path = "docs/task40para_phi90_multilayer5nm_exec/evidence/preflight/reviewer_g3_inventory_receipt.json"
    canonical_lock_correction_path = "docs/task40para_phi90_multilayer5nm_exec/evidence/preflight/reviewer_canonical_lock_path_correction.json"
    scope = {
        "schema": "task40.exact_parallel_pair_scope.v1",
        "pair_id": PAIR_ID,
        "status": "PAIR_SCOPE_AND_CPU_PLAN_REVIEW_PASS_NOT_FRESH_OR_PACKAGE_RELEASE",
        "max_concurrent_fe_cases": 2,
        "members": members,
        "canonical_host_lock": {
            "path": str(canonical_lock_path or pair.CANONICAL_HEAVY_LOCK_PATH),
            "pair_lock_path": str(pair.PAIR_LOCK_PATH),
            "handshake_lock_path": str(pair.PAIR_HANDSHAKE_PATH),
            "pair_membership_lock_mode": "shared_nonblocking",
            "all_non_pair_native_runs_lock_mode": "exclusive_nonblocking",
            "canonical_lock_must_preexist": True,
            "keep_canonical_lock": True,
        },
        "admission_contract": {
            "first_member_may_start_without_peer": True,
            "first_member_must_publish_live_binding_before_handshake_release": True,
            "second_member_must_bind_exact_active_peer": True,
            "second_member_may_overlap_peer_runtime": True,
            "fresh_and_submission_handshakes_are_serialized": True,
            "pending_peer_is_not_active": True,
            "unknown_active_heavy_jobs": "reject",
            "max_pair_members_active": 2,
            "minimum_available_bytes": 64 * 1024**3,
            "fixed_rss_cap_bytes": None,
            "swap_policy": "observe_only",
            "pss_policy": "disabled_by_profile",
            "uss_policy": "disabled_by_profile",
        },
        "cpu_reservation": _review_scope()["cpu_reservation"],
        "reviewer_coordination": {
            "path": coordination_path,
            "sha256": receipt_hashes["coordination"],
            "proposal_path": proposal_path,
            "proposal_sha256": receipt_hashes["proposal"],
            "inventory_receipt_path": inventory_path,
            "inventory_receipt_sha256": receipt_hashes["inventory"],
            "canonical_lock_correction_path": canonical_lock_correction_path,
            "canonical_lock_correction_sha256": receipt_hashes["canonical_lock_correction"],
        },
    }
    path = evidence / "exact_parallel_pair_scope.json"
    path.write_text(json.dumps(scope, sort_keys=True, indent=2) + "\n")
    scope_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(pair, "PAIR_SCOPE_SHA256", scope_sha)
    return root, path, scope_sha, scope


def test_pair_scope_is_hash_bound_exactly_two_members(tmp_path, monkeypatch):
    _root, path, scope_sha, _scope = _scope_tree(tmp_path, monkeypatch)
    scope = load_pair_scope(scope_path=path, expected_sha256=scope_sha)
    assert len(scope["members"]) == 2
    assert role_for_identity(G3_PROFILE, G3_RUN) == G3_ROLE
    assert role_for_identity(FIVE_PROFILE, FIVE_RUN) == FIVE_ROLE
    with pytest.raises(InputError, match="outside the two reviewed identities"):
        role_for_identity(G3_PROFILE, FIVE_RUN)
    with pytest.raises(InputError, match="outside the two reviewed identities"):
        role_for_identity("task40para_phi90_0p7_D07C_G3_M8_p6_direct_v1", G3_RUN)

    path.write_text(path.read_text() + " ")
    with pytest.raises(InputError, match="scope SHA256 mismatch"):
        load_pair_scope(scope_path=path, expected_sha256=scope_sha)


def test_pair_scope_rejects_third_or_mutated_member(tmp_path, monkeypatch):
    _root, path, _scope_sha, scope = _scope_tree(tmp_path, monkeypatch)
    scope["members"].append(dict(scope["members"][0], role="third"))
    path.write_text(json.dumps(scope, sort_keys=True, indent=2) + "\n")
    scope_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(pair, "PAIR_SCOPE_SHA256", scope_sha)
    with pytest.raises(InputError, match="exactly two members"):
        load_pair_scope(scope_path=path, expected_sha256=scope_sha)


def test_pair_roles_are_one_shot_and_allow_only_distinct_pair(tmp_path, monkeypatch):
    assert validate_active_roles([], current_role=G3_ROLE) == "first_member"
    assert validate_active_roles([G3_ROLE], current_role=FIVE_ROLE) == "second_member"
    with pytest.raises(InputError, match="same-role duplicate"):
        validate_active_roles([G3_ROLE], current_role=G3_ROLE)
    with pytest.raises(InputError, match="already contains two"):
        validate_active_roles([G3_ROLE, FIVE_ROLE], current_role=G3_ROLE)
    with pytest.raises(InputError, match="unknown active identity"):
        validate_active_roles(["third"], current_role=G3_ROLE)

    canonical = tmp_path / "canonical.lock"
    canonical.touch()
    pair_lock = tmp_path / "membership.lock"
    handshake = tmp_path / "handshake.lock"
    monkeypatch.setattr("src.runners.task40_exact_parallel_pair.PAIR_LOCK_PATH", pair_lock)
    _root, scope_path, scope_sha, _scope = _scope_tree(
        tmp_path / "scope", monkeypatch, canonical_lock_path=canonical
    )
    with acquire_pair_submission_handshake(
        role=G3_ROLE,
        profile_identity=G3_PROFILE,
        run_id=G3_RUN,
        scope_path=scope_path,
        scope_sha256=scope_sha,
        canonical_lock_path=canonical,
        directory=tmp_path,
        handshake_path=handshake,
    ):
        reservation_path = reserve_pair_submission_once(
            role=G3_ROLE,
            profile_identity=G3_PROFILE,
            run_id=G3_RUN,
            package_sha256="b" * 64,
            sidecar_sha256="c" * 64,
            service_unit="task40-g3-test.service",
            directory=tmp_path,
        )
        assert reservation_path.exists()
        with pytest.raises(InputError, match="handshake is already held"), acquire_pair_submission_handshake(
                role=FIVE_ROLE,
                profile_identity=FIVE_PROFILE,
                run_id=FIVE_RUN,
                scope_path=scope_path,
                scope_sha256=scope_sha,
                canonical_lock_path=canonical,
                directory=tmp_path,
                handshake_path=handshake,
            ):
            pass

    with pytest.raises(InputError, match="already consumed"), acquire_pair_submission_handshake(
            role=G3_ROLE,
            profile_identity=G3_PROFILE,
            run_id=G3_RUN,
            scope_path=scope_path,
            scope_sha256=scope_sha,
            canonical_lock_path=canonical,
            directory=tmp_path,
            handshake_path=handshake,
        ):
        pass

    receipt = {
        "submitted": True,
        "systemd_run_returncode": 0,
        "invocation_id": "a" * 32,
        "main_pid": 2501,
    }
    path = record_pair_submission_once(
        role=G3_ROLE,
        profile_identity=G3_PROFILE,
        run_id=G3_RUN,
        package_sha256="b" * 64,
        sidecar_sha256="c" * 64,
        service_unit="task40-g3-test.service",
        submission_receipt=receipt,
        directory=tmp_path,
    )
    assert path == pair_submission_receipt_path(G3_ROLE, directory=tmp_path)
    with pytest.raises(InputError, match="already consumed"):
        record_pair_submission_once(
            role=G3_ROLE,
            profile_identity=G3_PROFILE,
            run_id=G3_RUN,
            package_sha256="b" * 64,
            sidecar_sha256="c" * 64,
            service_unit="task40-g3-test.service",
            submission_receipt=receipt,
            directory=tmp_path,
        )
    assert PAIR_ID in path.name


def test_pair_runtime_lock_allows_two_members_blocks_third_and_legacy(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical-heavy.lock"
    canonical.touch()
    monkeypatch.setattr(pair, "CANONICAL_HEAVY_LOCK_PATH", canonical)
    pair_lock = tmp_path / "pair-membership.lock"
    monkeypatch.setattr("src.runners.task40_exact_parallel_pair.PAIR_LOCK_PATH", pair_lock)

    with ExitStack() as locks:
        locks.enter_context(acquire_pair_runtime_locks(
            role=G3_ROLE, canonical_lock_path=canonical, directory=tmp_path
        ))
        locks.enter_context(acquire_pair_runtime_locks(
            role=FIVE_ROLE, canonical_lock_path=canonical, directory=tmp_path
        ))
        with pytest.raises(InputError, match="role lock is already held"), acquire_pair_runtime_locks(
            role=G3_ROLE, canonical_lock_path=canonical, directory=tmp_path
        ):
            pass
        legacy = canonical.open("r")
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(legacy.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            legacy.close()
    legacy = canonical.open("r")
    try:
        fcntl.flock(legacy.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(legacy.fileno(), fcntl.LOCK_UN)
    finally:
        legacy.close()
    with pytest.raises(InputError, match="role is unknown"), acquire_pair_runtime_locks(
            role="third", canonical_lock_path=canonical, directory=tmp_path
        ):
        pass


def test_native_capacity_pair_dispatch_is_exact_and_shared(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical-heavy.lock"
    canonical.touch()
    common = tmp_path / "task-repository.git"
    subprocess.run(["git", "init", "--bare", str(common)], check=True, capture_output=True)
    monkeypatch.setattr(pair, "CANONICAL_COMMON_REPOSITORY", common)
    monkeypatch.setattr(pair, "PAIR_LOCK_PATH", tmp_path / "membership.lock")
    _root, scope_path, scope_sha, _scope = _scope_tree(
        tmp_path / "scope", monkeypatch, canonical_lock_path=canonical
    )
    monkeypatch.setattr(
        pair,
        "pair_member_runtime_lock_path",
        lambda role, *, directory="/tmp": tmp_path / f"{role}.runtime.lock",
    )
    monkeypatch.setenv(pair.PAIR_SCOPE_PATH_ENV, str(scope_path))
    monkeypatch.setenv(pair.PAIR_SCOPE_SHA_ENV, scope_sha)
    ordinary_clone = tmp_path / "ordinary-clone"
    subprocess.run(["git", "init", str(ordinary_clone)], check=True, capture_output=True)
    clone_common = subprocess.check_output(
        ["git", "-C", str(ordinary_clone), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
    ).strip()
    assert Path(clone_common).name == ".git"
    legacy_resolver_calls = []
    real_host_lock = native_capacity._native_capacity_host_lock

    def record_legacy_resolver(*args):
        legacy_resolver_calls.append(args)
        return real_host_lock(*args)

    monkeypatch.setattr(native_capacity, "_native_capacity_host_lock", record_legacy_resolver)

    with ExitStack() as locks:
        _lockset, lock_path, _common, g3_context = locks.enter_context(
            native_capacity._native_capacity_launch_lock(ordinary_clone, G3_PROFILE, G3_RUN)
        )
        assert g3_context["role"] == G3_ROLE
        assert lock_path == canonical
        assert _common == common.resolve()
        _peer_lockset, peer_lock_path, _peer_common, peer_context = locks.enter_context(
            native_capacity._native_capacity_launch_lock(ordinary_clone, FIVE_PROFILE, FIVE_RUN)
        )
        assert peer_context["role"] == FIVE_ROLE
        assert peer_lock_path == canonical
        assert _peer_common == common.resolve()
        with pytest.raises(InputError, match="role lock is already held"), native_capacity._native_capacity_launch_lock(
            ordinary_clone, G3_PROFILE, G3_RUN
        ):
            pass
        monkeypatch.delenv(pair.PAIR_SCOPE_PATH_ENV)
        monkeypatch.delenv(pair.PAIR_SCOPE_SHA_ENV)
        # Non-pair launches still use the legacy resolver/exclusive lock path.
        monkeypatch.setattr(
            native_capacity,
            "_native_capacity_host_lock",
            lambda *_args: (canonical, common),
        )
        with pytest.raises(InputError, match="heavy lock is held"), native_capacity._native_capacity_launch_lock(
            ordinary_clone, "task40_non_pair_profile", "task40_non_pair_run"
        ):
            pass
        monkeypatch.setenv(pair.PAIR_SCOPE_PATH_ENV, str(scope_path))
        monkeypatch.setenv(pair.PAIR_SCOPE_SHA_ENV, scope_sha)
        assert legacy_resolver_calls == []

    with pytest.raises(InputError, match="outside the two reviewed identities"), native_capacity._native_capacity_launch_lock(
            ordinary_clone, G3_PROFILE, FIVE_RUN
        ):
        pass


def test_membership_contention_releases_canonical_and_handshake(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical-heavy.lock"
    canonical.touch()
    membership = tmp_path / "pair-membership.lock"
    handshake = tmp_path / "pair-handshake.lock"
    monkeypatch.setattr(pair, "PAIR_LOCK_PATH", membership)
    monkeypatch.setattr(
        pair,
        "pair_member_runtime_lock_path",
        lambda role, *, directory="/tmp": tmp_path / f"{role}.runtime.lock",
    )
    _root, scope_path, scope_sha, _scope = _scope_tree(
        tmp_path / "scope", monkeypatch, canonical_lock_path=canonical
    )
    opened = []
    real_open = Path.open

    def capture_open(path, *args, **kwargs):
        stream = real_open(path, *args, **kwargs)
        if path in (canonical, handshake, membership):
            opened.append(stream)
        return stream

    with membership.open("a") as held_membership:
        fcntl.flock(held_membership.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        monkeypatch.setattr(Path, "open", capture_open)
        with pytest.raises(InputError, match="membership lock is held"), acquire_pair_submission_handshake(
            role=G3_ROLE,
            profile_identity=G3_PROFILE,
            run_id=G3_RUN,
            scope_path=scope_path,
            scope_sha256=scope_sha,
            canonical_lock_path=canonical,
            directory=tmp_path,
            handshake_path=handshake,
        ):
            pytest.fail("membership contention unexpectedly entered the handshake")
        assert opened and all(stream.closed for stream in opened)
        with real_open(canonical, "r") as canonical_probe:
            fcntl.flock(canonical_probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(canonical_probe.fileno(), fcntl.LOCK_UN)
        with real_open(handshake, "a") as handshake_probe:
            fcntl.flock(handshake_probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handshake_probe.fileno(), fcntl.LOCK_UN)


def test_pair_shared_lock_and_legacy_resolver_share_inode_and_exclude_both_ways(
    tmp_path, monkeypatch
):
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", str(seed)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.email", "pair-lock-test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(seed), "config", "user.name", "Pair Lock Test"],
        check=True,
        capture_output=True,
    )
    (seed / "tracked.txt").write_text("test only\n")
    subprocess.run(["git", "-C", str(seed), "add", "tracked.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(seed), "commit", "-m", "test"],
        check=True,
        capture_output=True,
    )
    common = tmp_path / "canonical" / "task-repository.git"
    common.parent.mkdir()
    subprocess.run(
        ["git", "clone", "--bare", str(seed), str(common)],
        check=True,
        capture_output=True,
    )
    legacy_root = tmp_path / "legacy-worktree"
    subprocess.run(
        ["git", "--git-dir", str(common), "worktree", "add", "--detach", str(legacy_root), "HEAD"],
        check=True,
        capture_output=True,
    )
    ordinary_clone = tmp_path / "ordinary-clone"
    subprocess.run(["git", "init", str(ordinary_clone)], check=True, capture_output=True)
    common_readback = subprocess.check_output(
        ["git", "-C", str(legacy_root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
    ).strip()
    assert Path(common_readback).resolve() == common.resolve()
    assert Path(common_readback).name == "task-repository.git"

    canonical_lock = common.parent / "native-capacity-heavy.lock"
    canonical_lock.touch()
    membership_lock = tmp_path / "pair-membership.lock"
    pair_role_lock_dir = tmp_path / "role-locks"
    pair_role_lock_dir.mkdir()
    monkeypatch.setattr(pair, "CANONICAL_COMMON_REPOSITORY", common)
    monkeypatch.setattr(pair, "CANONICAL_HEAVY_LOCK_PATH", canonical_lock)
    monkeypatch.setattr(pair, "PAIR_LOCK_PATH", membership_lock)
    monkeypatch.setattr(
        pair,
        "pair_member_runtime_lock_path",
        lambda role, *, directory="/tmp": pair_role_lock_dir / f"{role}.lock",
    )
    _root, scope_path, scope_sha, _scope = _scope_tree(
        tmp_path / "scope", monkeypatch, canonical_lock_path=canonical_lock
    )
    monkeypatch.setenv(pair.PAIR_SCOPE_PATH_ENV, str(scope_path))
    monkeypatch.setenv(pair.PAIR_SCOPE_SHA_ENV, scope_sha)

    from src.io.native_capacity_profile import TASK40_PHI90_P6_DIRECT_PROFILES

    legacy_profile = next(
        profile for profile in sorted(TASK40_PHI90_P6_DIRECT_PROFILES)
        if profile not in pair.PROFILE_TO_ROLE
    )
    legacy_run = f"{legacy_profile}_lock_inode_test"
    resolved_lock, resolved_common = native_capacity._native_capacity_host_lock(
        legacy_root, legacy_profile
    )
    assert resolved_common.resolve() == common.resolve()
    assert resolved_lock.resolve() == canonical_lock.resolve()
    assert os.stat(resolved_lock).st_ino == os.stat(canonical_lock).st_ino

    # Pair shared ownership blocks the legacy resolver's exclusive flock.
    with native_capacity._native_capacity_launch_lock(
        ordinary_clone, G3_PROFILE, G3_RUN
    ) as (_locks, pair_lock_path, pair_common, context):
        assert pair_lock_path.resolve() == resolved_lock.resolve()
        assert pair_common.resolve() == common.resolve()
        assert context["role"] == G3_ROLE
        monkeypatch.delenv(pair.PAIR_SCOPE_PATH_ENV)
        monkeypatch.delenv(pair.PAIR_SCOPE_SHA_ENV)
        with pytest.raises(InputError, match="heavy lock is held"), native_capacity._native_capacity_launch_lock(
            legacy_root, legacy_profile, legacy_run
        ):
            pytest.fail("legacy exclusive lock overlapped the pair's shared lock")
        monkeypatch.setenv(pair.PAIR_SCOPE_PATH_ENV, str(scope_path))
        monkeypatch.setenv(pair.PAIR_SCOPE_SHA_ENV, scope_sha)

    # Legacy exclusive ownership blocks the exact pair's shared acquisition.
    monkeypatch.delenv(pair.PAIR_SCOPE_PATH_ENV)
    monkeypatch.delenv(pair.PAIR_SCOPE_SHA_ENV)
    with native_capacity._native_capacity_launch_lock(
        legacy_root, legacy_profile, legacy_run
    ) as (_stream, legacy_lock_path, legacy_common, _context):
        assert legacy_lock_path.resolve() == canonical_lock.resolve()
        assert legacy_common.resolve() == common.resolve()
        monkeypatch.setenv(pair.PAIR_SCOPE_PATH_ENV, str(scope_path))
        monkeypatch.setenv(pair.PAIR_SCOPE_SHA_ENV, scope_sha)
        with pytest.raises(InputError, match="canonical, membership, or role lock is already held"), native_capacity._native_capacity_launch_lock(
            ordinary_clone, FIVE_PROFILE, FIVE_RUN
        ):
            pytest.fail("pair shared lock overlapped the legacy exclusive lock")


def _host_admission_tree(
    tmp_path, monkeypatch, *, stale_field=None, third_role=None, peer_active=True
):
    canonical = Path("/home/fenics/Projects/native-capacity-heavy.lock")
    _root, scope_path, scope_sha, _scope = _scope_tree(
        tmp_path / "scope", monkeypatch, canonical_lock_path=canonical
    )
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    self_status = proc_root / "self" / "status"
    self_status.parent.mkdir()
    self_status.write_text(
        "Name:\tpytest\nCpus_allowed_list:\t0-47\nMems_allowed_list:\t0-1\n"
    )
    service_cgroup = "/user.slice/task40-pair-five.service"
    peer_worktree = tmp_path / "peer-worktree"
    peer_worktree.mkdir()
    input_path = peer_worktree / "five.dat"
    input_path.write_text("five input\n")
    run_directory = peer_worktree / "results/five"
    run_directory.mkdir(parents=True)
    resolved = run_directory / "resolved_config.json"
    manifest = run_directory / "run_manifest.json"
    root_pid, mpi_pid, worker_pid = 4101, 4102, 4103
    root_argv = ["/qualified/python", "scripts/run_case.py", str(input_path)]
    mpi_argv = [
        "/usr/bin/mpiexec", "-n", "1", "/qualified/python", "-m",
        "src.runners.task038_input_worker", "--resolved-config", str(resolved),
        "--manifest", str(manifest), "--expected-output-directory", str(run_directory),
    ]
    worker_argv = [
        "/qualified/python", "-m", "src.runners.task038_input_worker",
        "--resolved-config", str(resolved), "--manifest", str(manifest),
        "--expected-output-directory", str(run_directory),
    ]
    peer_rows = {
        "root": {"pid": root_pid, "state": "R", "start_ticks": 1001,
                 "ppid": 999, "cwd": str(peer_worktree), "argv": root_argv,
                 "cgroup_path": service_cgroup, "affinity": [25]},
        "mpi": {"pid": mpi_pid, "state": "R", "start_ticks": 1002,
                "ppid": root_pid, "cwd": str(peer_worktree), "argv": mpi_argv,
                "cgroup_path": service_cgroup, "affinity": [25]},
        "worker": {"pid": worker_pid, "state": "R", "start_ticks": 1003,
                   "ppid": mpi_pid, "cwd": str(peer_worktree), "argv": worker_argv,
                   "cgroup_path": service_cgroup, "affinity": [26]},
    }
    bound_peer_rows = {name: dict(row) for name, row in peer_rows.items()}
    if stale_field in {"start_ticks", "ppid", "cwd", "argv"}:
        peer_rows["worker"][stale_field] = (
            [*peer_rows["worker"][stale_field], "--reused"]
            if stale_field == "argv"
            else peer_rows["worker"][stale_field] + 1
            if stale_field in {"start_ticks", "ppid"}
            else str(peer_worktree / "stale")
        )
    if peer_active:
        for row in peer_rows.values():
            _write_proc(
                proc_root, row["pid"], row["ppid"], row["start_ticks"],
                Path(row["cwd"]), row["argv"], service_cgroup,
                ",".join(map(str, row["affinity"])), row["affinity"][0],
            )
    if third_role == "known_solver":
        extra = peer_worktree / "third.dat"
        _write_proc(
            proc_root, 4201, 999, 2001, peer_worktree,
            ["/qualified/python", "scripts/run_case.py", str(extra)],
            "/user.slice/task40-third.service", "33", 33,
        )
    elif third_role == "unknown_solver":
        _write_proc(
            proc_root, 4202, 999, 2002, peer_worktree,
            ["/qualified/python", "-m", "src.runners.task038_unreviewed_worker"],
            "/user.slice/task40-third.service", "33", 33,
        )

    verified_peer = {
        "binding": {"member": {"role": FIVE_ROLE}},
        "live_processes": bound_peer_rows,
        "classifications": {
            name: admission._classify_task40_solver_argv(row["argv"])
            for name, row in bound_peer_rows.items()
        },
    }
    monkeypatch.setattr(
        pair, "load_peer_binding_if_present",
        lambda *_a, **_k: verified_peer if peer_active else None,
    )
    monkeypatch.setenv(pair.PAIR_BINDING_DIRECTORY_ENV, str(tmp_path / "binding"))

    sys_root = tmp_path / "sys"
    cgroup_root = sys_root / "fs/cgroup"
    cgroup = cgroup_root / "task40-admission"
    cgroup.mkdir(parents=True)
    (cgroup / "cpuset.cpus.effective").write_text("0-47\n")
    for cpu, package, core in ((9, 0, 11), (24, 1, 0)):
        topology = sys_root / f"devices/system/cpu/cpu{cpu}/topology"
        topology.mkdir(parents=True)
        (topology / "physical_package_id").write_text(f"{package}\n")
        (topology / "core_id").write_text(f"{core}\n")
        (topology / "thread_siblings_list").write_text(f"{cpu}\n")
    for node in (0, 1):
        node_root = sys_root / f"devices/system/node/node{node}"
        node_root.mkdir(parents=True)
        (node_root / "meminfo").write_text(
            f"Node {node} MemTotal: 1000000 kB\nNode {node} MemFree: 900000 kB\n"
        )
        (node_root / "cpulist").write_text("0-47\n")

    cgroup_modules = __import__("benchmarks.task034_wsl_resources", fromlist=["unused"])
    watchdog = __import__("benchmarks.subreaper_watchdog", fromlist=["unused"])
    monkeypatch.setattr(admission, "_proc_root", lambda: proc_root)
    monkeypatch.setattr(admission, "_sys_root", lambda: sys_root)
    monkeypatch.setattr(cgroup_modules, "current_cgroup_path", lambda: cgroup)
    monkeypatch.setattr(watchdog, "memory_envelope", lambda: {
        "effective_available_bytes": 256 * 1024**3,
    })
    monkeypatch.setattr(admission, "_interleave_probe", lambda: SimpleNamespace(
        returncode=0, stdout='[{"policy":"interleave:0-1"}]', stderr=""
    ))
    return scope_path, scope_sha


def test_host_floor_admission_allows_only_exact_live_pair_candidates(tmp_path, monkeypatch):
    scope_path, scope_sha = _host_admission_tree(tmp_path, monkeypatch)
    resources = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap_policy": "observe_only",
        "stop_on_global_swap": False,
        "pss_sampling_policy": "disabled_by_profile",
        "uss_sampling_policy": "disabled_by_profile",
        "time_limit_mode": "none",
    }
    result = admission.task40_host_floor_interleaved_admission(
        resources, [24], task_profile=G3_PROFILE, task_run_id=G3_RUN,
        pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
        pair_role=G3_ROLE, supervisor_cpu=9,
    )
    assert result["parallel_neighbor_authorized"] is True
    assert result["blocking_active_solver_candidates"] == []
    assert result["unknown_solver_role_candidates"] == []
    assert {row["role"] for row in result["parallel_authorized_solver_candidates"]} == {
        "standard_run_case", "task038_input_worker",
    }
    assert len(result["parallel_authorized_solver_candidates"]) == 3


def test_exact_pair_exemption_is_identity_bound_above_100gb(tmp_path, monkeypatch):
    scope_path, scope_sha = _host_admission_tree(tmp_path, monkeypatch)
    root_status = tmp_path / "proc/4101/status"
    root_status.write_text(root_status.read_text().replace(
        "VmRSS:\t4096 kB", "VmRSS:\t110000000 kB"
    ))
    resources = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap_policy": "observe_only",
        "stop_on_global_swap": False,
        "pss_sampling_policy": "disabled_by_profile",
        "uss_sampling_policy": "disabled_by_profile",
        "time_limit_mode": "none",
    }
    result = admission.task40_host_floor_interleaved_admission(
        resources, [24], task_profile=G3_PROFILE, task_run_id=G3_RUN,
        pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
        pair_role=G3_ROLE, supervisor_cpu=9,
    )
    assert [row["pid"] for row in result["blocking_large_processes"]] == []
    assert any(row["pid"] == 4101 for row in result["large_visible_processes"])


def test_host_floor_admission_allows_first_member_without_active_peer(tmp_path, monkeypatch):
    scope_path, scope_sha = _host_admission_tree(tmp_path, monkeypatch, peer_active=False)
    resources = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap_policy": "observe_only",
        "stop_on_global_swap": False,
        "pss_sampling_policy": "disabled_by_profile",
        "uss_sampling_policy": "disabled_by_profile",
        "time_limit_mode": "none",
    }
    result = admission.task40_host_floor_interleaved_admission(
        resources, [24], task_profile=G3_PROFILE, task_run_id=G3_RUN,
        pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
        pair_role=G3_ROLE, supervisor_cpu=9,
    )
    assert result["parallel_neighbor_authorized"] is False
    assert result["user_parallel_window_authorization"] is True
    assert result["blocking_active_solver_candidates"] == []


def test_host_floor_pair_admission_rejects_changed_floor_or_cpu(tmp_path, monkeypatch):
    scope_path, scope_sha = _host_admission_tree(tmp_path, monkeypatch, peer_active=False)
    resources = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "minimum_available_bytes": 32 * 1024**3,
        "swap_policy": "observe_only",
        "stop_on_global_swap": False,
        "pss_sampling_policy": "disabled_by_profile",
        "uss_sampling_policy": "disabled_by_profile",
        "time_limit_mode": "none",
    }
    with pytest.raises(InputError, match="resource profile differs"):
        admission.task40_host_floor_interleaved_admission(
            resources, [24], task_profile=G3_PROFILE, task_run_id=G3_RUN,
            pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
            pair_role=G3_ROLE, supervisor_cpu=9,
        )
    resources["minimum_available_bytes"] = 64 * 1024**3
    wrong_cpu_topology = tmp_path / "sys/devices/system/cpu/cpu25/topology"
    wrong_cpu_topology.mkdir(parents=True)
    (wrong_cpu_topology / "physical_package_id").write_text("1\n")
    (wrong_cpu_topology / "core_id").write_text("1\n")
    with pytest.raises(InputError, match="CPU assignment differs"):
        admission.task40_host_floor_interleaved_admission(
            resources, [25], task_profile=G3_PROFILE, task_run_id=G3_RUN,
            pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
            pair_role=G3_ROLE, supervisor_cpu=9,
        )


@pytest.mark.parametrize("stale_field", ["start_ticks", "ppid", "cwd", "argv"])
def test_host_floor_admission_rejects_live_peer_identity_drift(
    tmp_path, monkeypatch, stale_field
):
    scope_path, scope_sha = _host_admission_tree(
        tmp_path, monkeypatch, stale_field=stale_field
    )
    resources = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap_policy": "observe_only",
        "stop_on_global_swap": False,
        "pss_sampling_policy": "disabled_by_profile",
        "uss_sampling_policy": "disabled_by_profile",
        "time_limit_mode": "none",
    }
    with pytest.raises(InputError, match="authorized parallel solver roles"):
        admission.task40_host_floor_interleaved_admission(
            resources, [24], task_profile=G3_PROFILE, task_run_id=G3_RUN,
            pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
            pair_role=G3_ROLE, supervisor_cpu=9,
        )


@pytest.mark.parametrize("third_role", ["known_solver", "unknown_solver"])
def test_host_floor_admission_rejects_third_or_unknown_solver(
    tmp_path, monkeypatch, third_role
):
    scope_path, scope_sha = _host_admission_tree(
        tmp_path, monkeypatch, third_role=third_role
    )
    resources = {
        "resource_stop_policy": "host_available_floor_v1",
        "rss_hard_limit_bytes": None,
        "minimum_available_bytes": 64 * 1024**3,
        "swap_policy": "observe_only",
        "stop_on_global_swap": False,
        "pss_sampling_policy": "disabled_by_profile",
        "uss_sampling_policy": "disabled_by_profile",
        "time_limit_mode": "none",
    }
    message = "unknown role" if third_role == "unknown_solver" else "another active run_case"
    with pytest.raises(InputError, match=message):
        admission.task40_host_floor_interleaved_admission(
            resources, [24], task_profile=G3_PROFILE, task_run_id=G3_RUN,
            pair_scope_path=scope_path, pair_scope_sha256=scope_sha,
            pair_role=G3_ROLE, supervisor_cpu=9,
        )


def _live_binding_fixture(tmp_path):
    role = FIVE_ROLE
    member = MEMBERS[role]
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    input_path = worktree / "case.dat"
    input_path.write_text("input\n")
    run_directory = worktree / "results/run"
    run_directory.mkdir(parents=True)
    resolved_path = run_directory / "resolved_config.json"
    resolved_path.write_text('{"resolved":true}\n')
    source_sha = "d" * 40
    (run_directory / "source_sha.txt").write_text(source_sha + "\n")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    resolved_sha = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    physical_sha = "e" * 64
    manifest = {
        "run_id": FIVE_RUN,
        "model_id": "si_block_phi90_50x50_17x20_h120",
        "native_capacity_profile_identity": FIVE_PROFILE,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "output_directory": str(run_directory),
    }
    manifest_path = run_directory / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    review = {
        "status": "PASS",
        "profile_identity": FIVE_PROFILE,
        "run_id": FIVE_RUN,
        "source_sha": source_sha,
        "mode_count": member["mode_count"],
        "mode_sha256": member["mode_sha256"],
        "package_sha256": "f" * 64,
        "sidecar_sha256": "a" * 64,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
    }
    review_path = worktree / "package_review.json"
    review_path.write_text(json.dumps(review, sort_keys=True) + "\n")
    review_sha = hashlib.sha256(review_path.read_bytes()).hexdigest()

    service_unit = "task40-pair-five.service"
    cgroup = "/user.slice/task40-pair-five.service"
    root_pid, mpi_pid, worker_pid = 4101, 4102, 4103
    root_argv = ["/qualified/python", "scripts/run_case.py", str(input_path)]
    mpi_argv = [
        "/usr/bin/mpiexec", "-n", "1", "/qualified/python", "-m",
        "src.runners.task038_input_worker", "--resolved-config", str(resolved_path),
        "--manifest", str(manifest_path), "--expected-output-directory", str(run_directory),
    ]
    worker_argv = [
        "/qualified/python", "-m", "src.runners.task038_input_worker",
        "--resolved-config", str(resolved_path), "--manifest", str(manifest_path),
        "--expected-output-directory", str(run_directory),
    ]
    processes = {
        "root": {
        "pid": root_pid, "start_ticks": 1001, "ppid": 999,
            "cwd": str(worktree), "argv": root_argv, "cgroup_path": cgroup,
            "affinity": [25],
        },
        "mpi": {
            "pid": mpi_pid, "start_ticks": 1002, "ppid": root_pid,
            "cwd": str(worktree), "argv": mpi_argv, "cgroup_path": cgroup,
            "affinity": [25],
        },
        "worker": {
            "pid": worker_pid, "start_ticks": 1003, "ppid": mpi_pid,
            "cwd": str(worktree), "argv": worker_argv, "cgroup_path": cgroup,
            "affinity": [26],
        },
    }
    binding = {
        "schema": "task40.exact_parallel_pair_live_binding.v1",
        "pair_id": PAIR_ID,
        "status": "active",
        "member": {
            "role": role, "profile_identity": FIVE_PROFILE, "run_id": FIVE_RUN,
            "mode_count": member["mode_count"], "mode_sha256": member["mode_sha256"],
        },
        "package_review": {
            "status": "PASS", "record_path": str(review_path),
            "record_sha256": review_sha, "reviewed_source_sha": source_sha,
        },
        "service": {
            "unit": service_unit, "invocation_id": "f" * 32,
            "main_pid": root_pid, "main_start_ticks": 1001, "cgroup_path": cgroup,
        },
        "run": {
            "run_directory": str(run_directory), "run_manifest_path": str(manifest_path),
            "run_manifest_sha256": manifest_sha, "input_path": str(input_path),
            "input_sha256": input_sha, "resolved_config_path": str(resolved_path),
            "resolved_config_sha256": resolved_sha, "physical_model_sha256": physical_sha,
            "source_sha": source_sha,
        },
        "processes": processes,
        "cpu": {
            "supervisor_cpu": 25, "worker_cpu": 26,
            "activity_sample": {
                "sample_seconds": 3.0,
                "exclusive_cpu_claim": False,
                "thread_samples": [
                    {
                        "pid": root_pid, "tid": root_pid, "start_ticks": 1001,
                        "affinity": [25], "status": "sampled",
                        "delta_cpu_ticks": 3, "last_cpu_after": 25,
                    },
                    {
                        "pid": worker_pid, "tid": worker_pid, "start_ticks": 1003,
                        "affinity": [26], "status": "sampled",
                        "delta_cpu_ticks": 5, "last_cpu_after": 26,
                    },
                ],
            },
        },
    }
    scope = _review_scope()
    return binding, scope, {
        "worktree": worktree,
        "run_directory": run_directory,
        "manifest_path": manifest_path,
        "resolved_path": resolved_path,
        "input_path": input_path,
        "service_unit": service_unit,
        "cgroup": cgroup,
        "pids": {"root": root_pid, "mpi": mpi_pid, "worker": worker_pid},
        "argv": {"root": root_argv, "mpi": mpi_argv, "worker": worker_argv},
    }


def _write_proc(proc_root, pid, ppid, start_ticks, cwd, argv, cgroup, affinity, cpu):
    proc = proc_root / str(pid)
    proc.mkdir(parents=True)
    fields = ["0"] * 37
    fields[0] = "R"
    fields[1] = str(ppid)
    fields[19] = str(start_ticks)
    fields[36] = str(cpu)
    (proc / "stat").write_text(f"{pid} (python) " + " ".join(fields) + "\n")
    (proc / "status").write_text(
        "Name:\tpython\nVmRSS:\t4096 kB\nThreads:\t1\n"
        f"Cpus_allowed_list:\t{affinity}\nMems_allowed_list:\t0-1\n"
    )
    (proc / "cmdline").write_bytes(b"\0".join(x.encode() for x in argv) + b"\0")
    (proc / "cwd").symlink_to(cwd)
    (proc / "cgroup").write_text(f"0::{cgroup}\n")


def test_live_peer_binding_verifies_hashes_cgroup_pid_ticks_and_real_mpi_argv(tmp_path):
    binding, scope, extra = _live_binding_fixture(tmp_path)
    validate_live_binding_payload(
        binding, scope, expected_profile=FIVE_PROFILE, expected_run_id=FIVE_RUN
    )

    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    pids = extra["pids"]
    _write_proc(proc_root, pids["root"], 999, 1001, extra["worktree"],
                extra["argv"]["root"], extra["cgroup"], "25", 25)
    _write_proc(proc_root, pids["mpi"], pids["root"], 1002, extra["worktree"],
                extra["argv"]["mpi"], extra["cgroup"], "25", 25)
    _write_proc(proc_root, pids["worker"], pids["mpi"], 1003, extra["worktree"],
                extra["argv"]["worker"], extra["cgroup"], "26", 26)

    sys_root = tmp_path / "sys"
    for cpu, package, core in ((25, 1, 1), (26, 1, 2)):
        topology = sys_root / f"devices/system/cpu/cpu{cpu}/topology"
        topology.mkdir(parents=True)
        (topology / "physical_package_id").write_text(f"{package}\n")
        (topology / "core_id").write_text(f"{core}\n")
        (topology / "thread_siblings_list").write_text(f"{cpu}\n")

    unit_readback = {
        "InvocationID": "f" * 32,
        "MainPID": str(pids["root"]),
        "ControlGroup": extra["cgroup"],
        "ActiveState": "active",
        "SubState": "running",
    }
    result = verify_live_binding(
        _write_binding_file(tmp_path, binding), scope,
        expected_profile=FIVE_PROFILE,
        expected_run_id=FIVE_RUN,
        proc_root=proc_root,
        sys_root=sys_root,
        systemd_reader=lambda _unit: unit_readback,
    )
    solver_nodes, process_nodes = peer_authorized_process_nodes(result)
    assert set(solver_nodes) == {pids["root"], pids["mpi"], pids["worker"]}
    assert set(process_nodes) == {pids["root"], pids["mpi"], pids["worker"]}
    for pid, authorized in solver_nodes.items():
        candidate = {
            "pid": pid,
            "start_ticks": authorized["node"]["start_ticks"],
            "ppid": authorized["node"]["ppid"],
            "cwd": authorized["node"]["cwd"],
            "argv": authorized["node"]["argv"],
            **authorized["classification"],
        }
        assert admission._candidate_matches_authorized_node(candidate, authorized)
        candidate["start_ticks"] += 1
        assert not admission._candidate_matches_authorized_node(candidate, authorized)


def _write_binding_file(tmp_path, binding):
    path = tmp_path / "peer.live.json"
    path.write_text(json.dumps(binding, sort_keys=True) + "\n")
    return path


@pytest.mark.parametrize("field", ["input_sha256", "resolved_config_sha256", "source_sha"])
def test_live_binding_rejects_changed_peer_provenance(field, tmp_path):
    binding, scope, _extra = _live_binding_fixture(tmp_path)
    if field == "source_sha":
        binding["run"][field] = "a" * 40
    else:
        binding["run"][field] = "a" * 64
    with pytest.raises(InputError):
        validate_live_binding_payload(
            binding, scope, expected_profile=FIVE_PROFILE, expected_run_id=FIVE_RUN
        )


def test_live_binding_requires_exact_service_main_and_activity_leaders(tmp_path):
    binding, scope, _extra = _live_binding_fixture(tmp_path)
    binding["service"]["main_pid"] = 4999
    binding["service"]["main_start_ticks"] = 1999
    binding["service"]["main_process"] = {"pid": 4999, "start_ticks": 1999}
    with pytest.raises(InputError, match="wrapper identity is incomplete"):
        validate_live_binding_payload(
            binding, scope, expected_profile=FIVE_PROFILE, expected_run_id=FIVE_RUN
        )

    activity_root = tmp_path / "activity"
    activity_root.mkdir()
    binding, scope, _extra = _live_binding_fixture(activity_root)
    binding["cpu"]["activity_sample"]["thread_samples"][1]["start_ticks"] += 1
    with pytest.raises(InputError, match="does not bind the live worker leader"):
        validate_live_binding_payload(
            binding, scope, expected_profile=FIVE_PROFILE, expected_run_id=FIVE_RUN
        )


def test_publish_live_binding_is_one_shot(tmp_path):
    binding, _scope, _extra = _live_binding_fixture(tmp_path)
    path = publish_live_binding_once(role=FIVE_ROLE, binding=binding, directory=tmp_path)
    assert path == pair_member_registry_path(FIVE_ROLE, directory=tmp_path)
    with pytest.raises(InputError, match="already exists"):
        publish_live_binding_once(role=FIVE_ROLE, binding=binding, directory=tmp_path)
