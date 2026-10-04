from __future__ import annotations

import builtins
import copy
import hashlib
import json

import numpy as np
import pytest

from benchmarks import check_fresh_c1_p6_component as checker
from benchmarks import run_fresh_c1_p6_component as runner


def test_native_element_pin_is_exactly_runtime_profile_scoped(monkeypatch):
    native = checker._native_element_metadata("native_linux")
    local = checker._native_element_metadata("local_wsl2_authorized")
    assert native == checker.NATIVE_ELEMENT
    assert local == checker.LOCAL_WSL2_ELEMENT
    assert native["coefficient_matrix_C_sha256"] == (
        "780d9a4529041f8cb8138a78c8314d757822a1f5bc984f254c5790db208e911d")
    assert local["coefficient_matrix_C_sha256"] == (
        "1b22898a8793c497d4e7bb5083c69b0049b696c7513b899953cf79223911918a")
    assert {key: value for key, value in native.items()
            if key != "coefficient_matrix_C_sha256"} == {
                key: value for key, value in local.items()
                if key != "coefficient_matrix_C_sha256"}

    original_import = builtins.__import__
    fe_roots = {"basix", "dolfinx", "ufl", "petsc4py", "slepc4py", "mpi4py"}

    def reject_fe_import(name, *args, **kwargs):
        if name.partition(".")[0] in fe_roots:
            pytest.fail("profile metadata rejection imported the FE stack: " + name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", reject_fe_import)
    with pytest.raises(ValueError, match="profile-specific native element metadata"):
        checker._native_element(local, lambda *_: None, runtime_profile="native_linux")
    with pytest.raises(ValueError, match="qualified Task40 runtime profile"):
        checker._native_element_metadata("unknown")


def test_original_tensor_gate_receives_runtime_profile_before_orientation_reads(monkeypatch):
    class Reader:
        def ref(self, reference, **_kwargs):
            if reference == "raw":
                return np.zeros((882, 882), dtype=np.complex128)
            coordinates = np.asarray([(x, y, z) for x in (0., 1.)
                                      for y in (0., 1.) for z in (0., 1.)])
            return coordinates.reshape(-1)

    descriptor = {"representation": checker.NATIVE_TENSOR_REPRESENTATION,
        "recipe": checker.NATIVE_TENSOR_RECIPE, "raw_tensor": "raw",
        "shape": [882, 882], "dtype": "complex128",
        "native_element": dict(checker.LOCAL_WSL2_ELEMENT)}
    entry = {"class_index": 0, "class_key": [0, 1., 1., 1., 7],
             "raw_tensor": "raw", "original_tensor": descriptor}
    monkeypatch.setattr(checker, "_native_element_identity",
                        lambda _element: dict(checker.LOCAL_WSL2_ELEMENT))
    with pytest.raises(ValueError, match="profile-specific original tensor metadata"):
        checker._original_tensor(Reader(), {}, entry, {"coordinates": "coords"},
            lambda *_: None, object(), None, None, object(), runtime_profile="native_linux")


def test_source_delta_allowlist_accepts_only_checker_and_runner():
    worker = {
        "benchmarks/check_fresh_c1_p6_component.py": "a" * 64,
        "benchmarks/run_fresh_c1_p6_component.py": "b" * 64,
        "src/solvers/fresh_c1_p6_component.py": "c" * 64,
    }
    current = {**worker,
        "benchmarks/check_fresh_c1_p6_component.py": "d" * 64,
        "benchmarks/run_fresh_c1_p6_component.py": "e" * 64,
    }
    changed = checker._source_change_allowlist_deltas(worker, current)
    assert set(changed) == {
        "benchmarks/check_fresh_c1_p6_component.py",
        "benchmarks/run_fresh_c1_p6_component.py",
    }
    bad = {**current, "src/solvers/fresh_c1_p6_component.py": "f" * 64}
    with pytest.raises(ValueError, match="non-allowlisted source"):
        checker._source_change_allowlist_deltas(worker, bad)
    with pytest.raises(ValueError, match="same complete file set"):
        checker._source_change_allowlist_deltas(worker, {"only-one": "0" * 64})


def _checker_continuation_source_fixture(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    assert len(checker.W0_SOURCE_FILES) == 26
    worker_files = {}
    for name in checker.W0_SOURCE_FILES:
        path = repo_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        old_bytes = ("frozen worker fixture source: " + name + "\n").encode("utf-8")
        path.write_bytes(old_bytes)
        worker_files[name] = hashlib.sha256(old_bytes).hexdigest()

    old_allowlist = {
        name: worker_files[name]
        for name in checker.CHECKER_CONTINUATION_ALLOWED_OLD_SOURCE_SHA256
    }
    for name in old_allowlist:
        (repo_root / name).write_text("checker-only continuation fixture: " + name + "\n")
    old_manifest_sha256 = checker._source_manifest_sha256(worker_files)
    monkeypatch.setattr(checker, "__file__",
        str(repo_root / "benchmarks/check_fresh_c1_p6_component.py"))
    monkeypatch.setattr(checker, "CHECKER_CONTINUATION_WORKER_SOURCE_MANIFEST_SHA256",
                        old_manifest_sha256)
    monkeypatch.setattr(checker, "CHECKER_CONTINUATION_ALLOWED_OLD_SOURCE_SHA256",
                        old_allowlist)

    worker_root = repo_root / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4"
    raw_root = worker_root / "raw"
    raw_root.mkdir(parents=True)
    name = "fixture/control-vector"
    member = {"name": name, "shape": [3], "dtype": "float64", "numeric_bytes": 24,
        "sha256": hashlib.sha256(b"fixture-array-v1").hexdigest()}
    report = {
        "schema": checker.WORKER_SCHEMA,
        "status": "worker_component_controls_passed_independent_checker_pending",
        "PDE_solved": False,
        "official_results": False,
        "source_identity": {
            "schema": "task40extra.fresh-c1-p6-source-identity.v1",
            "files": worker_files,
            "manifest_sha256": old_manifest_sha256,
            "source_status": "NEW_UNQUALIFIED",
        },
        "snapshot": {
            "members": [member], "unique_member_count": 1,
            "numeric_bytes": member["numeric_bytes"],
            "archive_members_bytes_upper": member["numeric_bytes"] + 4096,
        },
    }
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("ascii")
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    monkeypatch.setattr(checker, "CHECKER_CONTINUATION_WORKER_REPORT_SHA256", report_sha256)

    files = [{
        "name": name,
        "filename": hashlib.sha256(name.encode("utf-8")).hexdigest() + ".npy",
        "file_size_bytes": 152,
        "file_sha256": hashlib.sha256(b"fixture-raw-file-v1").hexdigest(),
        "array_sha256": member["sha256"],
        "shape": member["shape"],
        "dtype": member["dtype"],
        "numeric_bytes": member["numeric_bytes"],
    }]
    raw_manifest = {
        "schema": "task40extra.w0-checker-only-raw-manifest.v1",
        "raw_root": str(raw_root.resolve()),
        "files": files,
        "member_count": 1,
        "file_bytes": 152,
        "raw_files_copied": False,
    }
    raw_manifest["manifest_sha256"] = checker._raw_member_manifest_sha256(files)
    return report, report_sha256, raw_manifest, worker_root, repo_root


def test_full_checker_continuation_source_binding_builds_and_validates(tmp_path, monkeypatch):
    from benchmarks.task40_runtime_profile import LOCAL_WSL2_PROFILE

    report, report_sha256, raw_manifest, worker_root, repo_root = (
        _checker_continuation_source_fixture(tmp_path, monkeypatch))
    record = checker.build_checker_continuation_record(report,
        worker_root=worker_root,
        worker_report_bytes_sha256=report_sha256,
        runtime_profile=LOCAL_WSL2_PROFILE,
        raw_member_manifest=raw_manifest,
        checker_git_sha="a" * 40)

    validated = checker._validate_source_identity(report,
        continuation_record=record,
        worker_report_bytes_sha256=report_sha256)
    validated_raw = checker._validate_checker_continuation_record(report, record,
        runtime_profile=LOCAL_WSL2_PROFILE,
        worker_report_bytes_sha256=report_sha256)
    assert validated["file_count"] == len(checker.W0_SOURCE_FILES)
    assert set(validated["changed_files"]) == set(
        checker.CHECKER_CONTINUATION_ALLOWED_OLD_SOURCE_SHA256)
    assert validated_raw == raw_manifest
    assert record["worker_git_sha"] == checker.CHECKER_CONTINUATION_WORKER_GIT_SHA
    assert record["worker_source_files"] == report["source_identity"]["files"]
    expected_checker_files = {
        name: hashlib.sha256((repo_root / name).read_bytes()).hexdigest()
        for name in checker.W0_SOURCE_FILES
    }
    assert record["checker_source_files"] == expected_checker_files


def test_full_checker_continuation_source_binding_rejects_tampered_compatibility(
        tmp_path, monkeypatch):
    from benchmarks.task40_runtime_profile import LOCAL_WSL2_PROFILE

    report, report_sha256, raw_manifest, worker_root, _repo_root = (
        _checker_continuation_source_fixture(tmp_path, monkeypatch))
    record = checker.build_checker_continuation_record(report,
        worker_root=worker_root,
        worker_report_bytes_sha256=report_sha256,
        runtime_profile=LOCAL_WSL2_PROFILE,
        raw_member_manifest=raw_manifest,
        checker_git_sha="a" * 40)
    tampered = copy.deepcopy(record)
    tampered["checker_source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source manifest/checker SHA binding differs"):
        checker._validate_source_identity(report, continuation_record=tampered,
            worker_report_bytes_sha256=report_sha256)


def _write_one_raw_member(tmp_path):
    raw_root = tmp_path / "worker" / "raw"
    raw_root.mkdir(parents=True)
    name = "fixture/control-vector"
    value = np.asarray([1.25, -2.5, 3.75], dtype=np.float64)
    filename = hashlib.sha256(name.encode("utf-8")).hexdigest() + ".npy"
    path = raw_root / filename
    with path.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    reference = {"name": name, "shape": list(value.shape), "dtype": str(value.dtype),
        "numeric_bytes": value.nbytes, "sha256": checker._sha(value)}
    report = {"snapshot": {"members": [reference], "unique_member_count": 1,
        "numeric_bytes": value.nbytes, "archive_members_bytes_upper": value.nbytes + 4096}}
    return raw_root, path, value, reference, report


def test_checker_only_raw_manifest_and_loader_bind_file_bytes_without_copy(tmp_path):
    raw_root, path, expected, reference, report = _write_one_raw_member(tmp_path)
    manifest = runner._raw_member_manifest(raw_root, report)
    assert manifest["member_count"] == 1
    assert manifest["file_bytes"] == path.stat().st_size
    assert manifest["raw_files_copied"] is False
    assert manifest["files"][0]["file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()

    reference = {**reference, "callback_reference": str(path)}
    load = runner._checker_raw_loader(raw_root.parent, manifest, np)
    loaded = load(reference)
    np.testing.assert_array_equal(loaded, expected)
    assert not loaded.flags.writeable
    loaded._mmap.close()

    wrong_path = {**reference, "callback_reference": str(tmp_path / "outside.npy")}
    with pytest.raises(ValueError, match="outside its canonical artifact directory"):
        load(wrong_path)

    path.write_bytes(path.read_bytes() + b"tampered")
    load_changed = runner._checker_raw_loader(raw_root.parent, manifest, np)
    with pytest.raises(ValueError, match="bytes changed after binding"):
        load_changed(reference)


def test_checker_only_raw_inventory_rejects_extra_files_and_disk_guard_counts_old_root(tmp_path):
    raw_root, _path, _value, _reference, report = _write_one_raw_member(tmp_path)
    output_root = tmp_path / "new-output"
    output_root.mkdir()
    extra = raw_root / "unexpected.npy"
    extra.write_bytes(b"x")
    with pytest.raises(ValueError, match="exactly match"):
        runner._raw_member_manifest(raw_root, report)
    extra.unlink()
    facts = runner._disk_facts(output_root, raw_root=raw_root)
    assert facts["category_bytes"]["raw"] == sum(path.stat().st_size for path in raw_root.iterdir())
    assert "immutable worker raw-member" in facts["scope"]


def test_checker_only_cli_routes_to_supervised_checker_without_worker(monkeypatch, tmp_path):
    received = {}
    def fake_route(*args):
        received["args"] = args
        return 0
    monkeypatch.setattr(runner, "_checker_only_supervised_cli", fake_route)
    rc = runner.main(["--checker-only-supervised", "--output-dir", str(tmp_path / "out"),
        "--abi-receipt", str(tmp_path / "out/abi_receipt.json"),
        "--worker-root", str(runner.CHECKER_ONLY_WORKER_ROOT),
        "--total-deadline-utc", "2026-10-04T17:04:57Z"])
    assert rc == 0
    args = received["args"]
    assert args[0] == tmp_path / "out"
    assert args[1] == runner.CHECKER_ONLY_WORKER_ROOT
    assert args[3] == "2026-10-04T17:04:57Z"


def test_checker_only_supervisor_rejects_a_duplicate_output_raw_tree(tmp_path, monkeypatch):
    worker_root = tmp_path / "worker"
    (worker_root / "raw").mkdir(parents=True)
    monkeypatch.setattr(runner, "CHECKER_ONLY_WORKER_ROOT", worker_root)
    output_root = tmp_path / "output"
    output_root.mkdir()
    receipt = output_root / "abi_receipt.json"
    receipt.write_text("{}\n")
    (output_root / "raw").mkdir()

    with pytest.raises(FileExistsError, match="must not contain a duplicate raw directory"):
        runner._checker_only_supervised_cli(output_root, worker_root,
            receipt, "2026-10-04T17:04:57Z")


def test_clean_git_identity_rejects_dirty_head(monkeypatch):
    class Result:
        def __init__(self, stdout="", returncode=0):
            self.stdout, self.returncode = stdout, returncode

    def fake_run(command, **_kwargs):
        if command[1:3] == ["rev-parse", "HEAD"]:
            return Result("a" * 40 + "\n")
        if command[1:3] == ["branch", "--show-current"]:
            return Result("task40extra_0p7nm_engineering\n")
        if command[1:3] == ["status", "--porcelain"]:
            return Result(" M checker.py\n")
        if command[1:3] == ["merge-base", "--is-ancestor"]:
            return Result(returncode=0)
        raise AssertionError(command)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="reviewed clean Task40 branch HEAD"):
        runner._current_clean_git_identity()
