"""Pure contract tests for the J3 split cold-staged parent and checker."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from benchmarks import run_task038_full3d_jit_solver_bundle as solver
from benchmarks import run_task038_full3d_jit_staged_parent as parent
from benchmarks import task038_full3d_jit_staging as staging
from benchmarks import task038_full3d_jit_staged_checker as checker


ROOT = Path(__file__).resolve().parents[2]
INPUT = (ROOT / "input/templates/full3d_iterative_example.dat").resolve()
SOURCE_SHA = "a" * 40
PYTHON = ROOT / ".venv" / "bin" / "python"
GROUP_COUNTS = {group: value[0] for group, value in checker.EXPECTED_GROUP_ROLES.items()}


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profile() -> dict[str, object]:
    return dict(checker.EXPECTED_PROFILE)


def _runtime() -> dict[str, object]:
    return {
        "source_sha": SOURCE_SHA,
        "branch": checker.BRANCH,
        "clean_source_tree": True,
        "qualified_activation": "1",
        "python_executable": str(PYTHON),
        "python_prefix": str(ROOT / ".venv"),
        "mpi_size": 1,
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
        "abi_modules": {name: str(ROOT / ".venv" / "lib" / f"{name}.so") for name in ("mpi4py", "petsc4py", "dolfinx", "basix")},
    }


def _physical_audit() -> dict[str, object]:
    components = {
        name: {
            "schema": "task038.fullspace-mpc-form-action.v1",
            "operator": "uncondensed_fullspace_curl_mass_form",
            "slave_row_identity": slave_identity,
            "global_matrix_materialized": False,
            "global_constraint_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "cell_schur_matrix_materialized": False,
            "slab_matrix_materialized": False,
        }
        for name, slave_identity in (
            ("curl_curl", True),
            ("complex_material_mass", False),
        )
    }
    return {
        "schema": "task038.fullspace-physical-action.v1",
        "operator": "A_volume_plus_dynamic_DtN",
        "physical_form": "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn",
        "volume_component_count": 2,
        "volume_components": ["curl_curl", "complex_material_mass"],
        "volume_action": {
            "schema": "task038.fullspace-split-volume-action.v1",
            "operator": "A_curl_curl_plus_A_complex_material_mass",
            "component_count": 2,
            "components": components,
            "constraint_identity_rows_exactly_once": True,
            "third_persistent_sum_vector": False,
        },
    }


def _member(pid: int, ppid: int, stage: str, rss: int, pss: int) -> dict[str, object]:
    return {"pid": pid, "ppid": ppid, "comm": "worker" if pid != 4242 else "python", "state": "S", "cmdline": "python -m worker", "stage": stage, "rss_bytes": rss, "pss_bytes": pss, "swap_bytes": 0, "timestamp_ns": 10, "exit_code": None}


def _sample(stage: str, timestamp: int, descendant: int | None) -> dict[str, object]:
    members = [_member(4242, 1, stage, 100, 50)]
    if descendant is not None:
        members.append(_member(descendant, 4242, stage, 50, 25))
    return {"schema": checker.SAMPLE_SCHEMA, "root_pid": 4242, "stage": stage, "timestamp_ns": timestamp, "exit_code": None, "members": members, "unreadable_pids": [], "vanished_pids": [], "all_status_readable": True, "readability_retry_count": 0, "compiler_descendant_count": 0, "rss_bytes": sum(item["rss_bytes"] for item in members), "swap_bytes": 0, "pss_all_readable": True, "pss_bytes": sum(item["pss_bytes"] for item in members)}


def _monitor(pid: int, started: int, ended: int, sample_count: int = 3) -> dict[str, object]:
    return {"pid": pid, "process_group_id": pid, "started_ns": started, "ended_ns": ended, "returncode": 0, "natural_exit": True, "stop_reason": "natural_exit", "sample_count": sample_count, "peak_rss_bytes": 150, "max_swap_bytes": 0, "all_status_readable": True, "compiler_descendant_peak": 0, "observed_descendant_pids": [pid], "last_sample": None, "signals": [], "required_sigkill": False, "process_group_gone": True, "descendants_gone": True}


def _valid_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    root = tmp_path / "j3-root"
    cache = root / "jit_cache"
    marker_dir = root / "markers"
    children_dir = root / "children"
    solver_dir = root / "solver"
    manifests_dir = root / "cache_manifests"
    for path in (root, cache, marker_dir, children_dir, solver_dir, manifests_dir):
        path.mkdir()
    record_path = root / "parent_record.json"
    sample_path = root / "parent_process.jsonl"
    marker_manifest_path = root / "marker_manifest.json"

    marker_entries = []
    for marker_name in checker.EXPECTED_MARKERS:
        index = checker.MARKER_ORDER.index(marker_name)
        solver_start = checker.EXPECTED_MARKERS.index("positive_setup_started")
        solver_end = checker.EXPECTED_MARKERS.index("bundle_built")
        marker_stage = "j3-split-cold-staged-solver" if solver_start <= index <= solver_end else "j3-split-cold-staged-parent"
        facts: dict[str, object] = {"stage": marker_stage, "artifact_root": str(root), "cache_dir": str(cache), "source_sha": SOURCE_SHA}
        if marker_name.startswith("precompile_") and marker_name.endswith("_started"):
            facts["command"] = [str(PYTHON), "-m", checker.CHILD_MODULE]
        if marker_name == "solver_child_started":
            facts["command"] = [str(PYTHON), "-m", checker.SOLVER_MODULE]
        if marker_name == "parent_complete":
            facts["compiler_descendant_count"] = 0
        path = marker_dir / f"{index:03d}_{marker_name}.json"
        _write(path, {"schema": checker.MARKER_SCHEMA, "name": marker_name, "marker_index": index, "timestamp_ns": index + 1, "facts": facts})
        marker_entries.append({"name": marker_name, "path": str(path), "sha256": _sha(path)})
    _write(marker_manifest_path, marker_entries)

    stages = [*(f"precompile:{group}" for group in checker.GROUPS), "precompile:parent-only", "solver"]
    sample_values = []
    for index, stage in enumerate(stages):
        descendant = 5000 + index if stage != "precompile:parent-only" else None
        if stage == "solver":
            descendant = 6000
        sample_values.extend((_sample(stage, 100 + index * 10, descendant), _sample(stage, 101 + index * 10, descendant), _sample(stage, 102 + index * 10, None)))
    sample_path.write_text("".join(json.dumps(value, separators=(",", ":")) + "\n" for value in sample_values), encoding="utf-8")

    initial_manifest_path = manifests_dir / "initial.json"
    initial_manifest = {"cache_dir": str(cache), "artifacts": [], "artifact_count": 0}
    _write(initial_manifest_path, initial_manifest)
    child_entries = []
    artifacts: list[dict[str, object]] = []
    module_index = 0
    for group_index, group in enumerate(checker.GROUPS):
        count, roles = checker.EXPECTED_GROUP_ROLES[group]
        added = []
        for _ in range(count):
            relative = f"module_{module_index}.so"
            target = cache / relative
            target.write_bytes(f"module-{module_index}".encode())
            item = {"relative_path": relative, "bytes": target.stat().st_size, "sha256": _sha(target)}
            artifacts.append(item)
            added.append(item)
            module_index += 1
        manifest = {"cache_dir": str(cache), "artifacts": list(artifacts), "artifact_count": len(artifacts)}
        manifest_path = manifests_dir / f"{group_index:02d}-{group.replace('-', '_')}.json"
        _write(manifest_path, manifest)
        child_record = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.json"
        child_command = [str(PYTHON), "-m", checker.CHILD_MODULE, "--group", group, "--cache-dir", str(cache), "--record", str(child_record), "--expected-source-sha", SOURCE_SHA, "--input", str(INPUT)]
        group_facts = {"compiled_form_count": count, "form_roles": list(roles)}
        if group in {"physical-volume-curl", "physical-volume-mass"}:
            group_facts.update({"component": "curl" if group.endswith("curl") else "mass", "component_count": 1})
        _write(child_record, {"schema": checker.CHILD_RECORD_SCHEMA, "stage": "j3-split-precompile-child", "group": group, "source_sha": SOURCE_SHA, "branch": checker.BRANCH, "command": child_command, "input": {"path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": _profile()}, "cache": {"cache_dir": str(cache), "jit_options": {}}, "facts": {"group_facts": group_facts}, "architecture": {"matrix": False, "factor": False, "pc": False, "rhs_vector": False, "surface_carrier": False, "dtn_carrier": False, "solve": False, "recovery": False, "compile": True, "mesh": True, "jit": True, "pde": False}, "runtime": _runtime(), "raw_facts_only": True})
        stdout = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.stdout"
        stderr = children_dir / f"{group_index:02d}-{group.replace('-', '_')}.stderr"
        stdout.write_bytes(b"")
        stderr.write_bytes(b"")
        pid = 5000 + group_index
        child_entries.append({"group": group, "command": child_command, "pid": pid, "returncode": 0, "natural_exit": True, "stop_reason": "natural_exit", "descendants_gone": True, "record_path": str(child_record), "record_sha256": _sha(child_record), "stdout_path": str(stdout), "stdout_sha256": _sha(stdout), "stderr_path": str(stderr), "stderr_sha256": _sha(stderr), "cache_manifest_path": str(manifest_path), "cache_manifest_sha256": _sha(manifest_path), "cache_artifact_count": len(artifacts), "added_artifacts": added, "new_module_basenames": [item["relative_path"] for item in added], "process": _monitor(pid, 100 + group_index * 10, 102 + group_index * 10)})

    before_path = manifests_dir / "before_solver.json"
    after_path = manifests_dir / "after_solver.json"
    final_manifest = {"cache_dir": str(cache), "artifacts": list(artifacts), "artifact_count": len(artifacts)}
    _write(before_path, final_manifest)
    _write(after_path, final_manifest)
    solver_record = solver_dir / "solver_record.json"
    module_names = sorted(f"module_{index}.so" for index in range(11))
    solver_module_indices = (0, 1, 2, 3, 4, 5, 6, 7, 9, 10)
    calls = [{"index": index, "module_name": f"module_{module_index}", "module_file": str(cache / f"module_{module_index}.so"), "code": [None, None], "cache_hit": True} for index, module_index in enumerate(solver_module_indices)]
    solver_command = [str(PYTHON), "-m", checker.SOLVER_MODULE, "--cache-dir", str(cache), "--record", str(solver_record), "--marker-dir", str(marker_dir), "--expected-source-sha", SOURCE_SHA, "--expected-mpi-size", "1", "--input", str(INPUT)]
    solver_architecture = {"p6_matrix_free": True, "p6_global_aij": False, "high_order_global_aij": False, "global_dense_transfer": False, "numeric_allgather": False, "p3_sparse_matrix_built": True, "p1_sparse_matrix_built": True, "p1_direct_factor_built": True, "same_mesh_pmg_built": True, "streaming_dtn_action_built": True, "dtn_carrier_built": True, "dtn_carrier_lifetime": "transient_released", "physical_volume_action_built": True, "volume_component_count": 2, "volume_components": ["curl_curl", "complex_material_mass"], "monolithic_physical_volume": False, "rhs_built": False, "outer_ksp_built": False, "solve_run": False, "recovery_run": False, "bundle_destroyed_before_record": True}
    _write(solver_record, {"schema": checker.SOLVER_RECORD_SCHEMA, "stage": "j3-split-cold-staged-solver", "source_sha": SOURCE_SHA, "branch": checker.BRANCH, "command": solver_command, "identity": {"input_path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": _profile()}, "paths": {"artifact_root": str(root), "cache_dir": str(cache), "marker_dir": str(marker_dir), "record": str(solver_record)}, "runtime": _runtime(), "mode": {"count": 1, "manifest_sha256": checker.MODE_MANIFEST_SHA256, "dtn_quadrature_degree": 1}, "ffcx_calls": calls, "expected_ffcx_call_count": 10, "setup_audit": {}, "physical_audit": _physical_audit(), "architecture": solver_architecture, "marker_names": list(checker.EXPECTED_MARKERS[:-1]), "raw_facts_only": True})
    solver_stdout = solver_dir / "solver.stdout"
    solver_stderr = solver_dir / "solver.stderr"
    solver_stdout.write_bytes(b"")
    solver_stderr.write_bytes(b"")
    solver_process = _monitor(6000, 180, 182)
    solver_process["last_sample"] = None
    solver_info = {"command": solver_command, "process": solver_process, "record_path": str(solver_record), "record_sha256": _sha(solver_record), "stdout_path": str(solver_stdout), "stdout_sha256": _sha(solver_stdout), "stderr_path": str(solver_stderr), "stderr_sha256": _sha(solver_stderr), "before_solver_manifest_sha256": _sha(before_path), "after_solver_manifest_sha256": _sha(after_path), "cache_unchanged": True}

    process_summary = parent._process_summary(sample_path)
    record = {"schema": checker.RECORD_SCHEMA, "stage": "j3-split-cold-staged-parent", "source_sha": SOURCE_SHA, "branch": checker.BRANCH, "command": [str(PYTHON), "-m", checker.PARENT_MODULE, "--artifact-root", str(root), "--record", str(record_path), "--source-sha", SOURCE_SHA, "--input", str(INPUT)], "identity": {"input_path": str(INPUT), "input_sha256": checker.INPUT_SHA256, "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256, "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256, "profile": _profile(), "runtime": _runtime()}, "paths": {"artifact_root": str(root), "cache_dir": str(cache), "marker_dir": str(marker_dir), "record": str(record_path), "process_samples": str(sample_path), "marker_manifest": str(marker_manifest_path), "children_dir": str(children_dir), "solver_dir": str(solver_dir), "cache_manifests_dir": str(manifests_dir)}, "marker_schema": checker.MARKER_SCHEMA, "sample_schema": checker.SAMPLE_SCHEMA, "markers": {"names": list(checker.EXPECTED_MARKERS), "manifest_path": str(marker_manifest_path), "manifest_sha256": _sha(marker_manifest_path)}, "process": process_summary, "children": child_entries, "solver": solver_info, "cache": {"initial_empty": True, "initial_manifest": {"path": str(initial_manifest_path), "sha256": _sha(initial_manifest_path), "artifact_count": 0, "manifest": initial_manifest}, "group_manifests": [{"group": group, "path": child["cache_manifest_path"], "sha256": child["cache_manifest_sha256"], "artifact_count": child["cache_artifact_count"], "new_module_basenames": child["new_module_basenames"]} for group, child in zip(checker.GROUPS, child_entries)], "before_solver": {"path": str(before_path), "sha256": _sha(before_path), "artifact_count": 11, "manifest": final_manifest}, "after_solver": {"path": str(after_path), "sha256": _sha(after_path), "artifact_count": 11, "manifest": final_manifest}, "precompiled_module_basenames": module_names, "deferred_incident_module_basenames": ["module_8.so"], "solver_unchanged": True}, "architecture": solver_architecture, "raw_facts_only": True}
    _write(record_path, record)
    return record_path, root, record


def test_fresh_root_and_marker_subsequence_are_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    cache = root / "jit_cache"
    paths = staging.prepare_fresh_root(root, cache)
    staging.write_marker(paths["marker_dir"], "parent_started", {})
    staging.create_fresh_cache(cache)
    staging.write_marker(paths["marker_dir"], "fresh_cache_created", {})
    with pytest.raises(ValueError):
        staging.write_marker(paths["marker_dir"], "parent_started", {})
    with pytest.raises(FileExistsError):
        staging.prepare_fresh_root(root, cache)


def test_process_jsonl_and_manifest_delta_are_flushable(tmp_path: Path) -> None:
    sample_path = tmp_path / "samples.jsonl"
    code = (
        "import json,subprocess,sys;"
        "from pathlib import Path;"
        "from benchmarks import run_task038_full3d_jit_staged_parent as parent;"
        "sample_path=Path(sys.argv[1]);"
        "child_code=\"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.25)']); time.sleep(0.35)\";"
        "process=subprocess.Popen([sys.executable,'-c',child_code],start_new_session=True);"
        "print(json.dumps(parent._monitor_child(process,sample_path,'test')))"
    )
    probe = subprocess.run(
        [sys.executable, "-c", code, str(sample_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    monitor = json.loads(probe.stdout)
    assert len(monitor["observed_descendant_pids"]) >= 2
    assert monitor["pid"] in monitor["observed_descendant_pids"]
    assert monitor["process_group_gone"] is True
    assert monitor["required_sigkill"] is False
    assert json.loads(sample_path.read_text(encoding="utf-8").splitlines()[0])["schema"] == staging.SAMPLE_SCHEMA
    previous = {"manifest": {"artifacts": [], "artifact_count": 0}}
    current = {"manifest": {"artifacts": [{"relative_path": "a.so", "sha256": "x"}], "artifact_count": 1}}
    assert parent._manifest_delta(previous, current) == current["manifest"]["artifacts"]


def test_checker_accepts_fake_unchanged_solver_cache(tmp_path: Path) -> None:
    record_path, _root, record = _valid_fixture(tmp_path)
    result = checker.check_record(record_path, SOURCE_SHA)
    assert result["passed"] is True
    assert result["classification"] == "J3_SPLIT_COLD_STAGED_PASS"
    assert result["identity"]["source_sha"] == SOURCE_SHA
    assert result["metrics"]["solver_ffcx_call_count"] == 10
    assert result["metrics"]["precompiled_module_count"] == 11


def test_checker_rejects_cache_mutation(tmp_path: Path) -> None:
    record_path, _root, record = _valid_fixture(tmp_path)
    after_path = Path(record["cache"]["after_solver"]["path"])
    changed = json.loads(after_path.read_text(encoding="utf-8"))
    changed["artifact_count"] = 99
    after_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE_SHA)

    child_root = tmp_path / "child-mutation"
    child_root.mkdir()
    record_path, _root, record = _valid_fixture(child_root)
    mutated = json.loads(record_path.read_text(encoding="utf-8"))
    mutated["children"][0]["process"]["pid"] += 1
    record_path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE_SHA)

    audit_root = tmp_path / "audit-mutation"
    audit_root.mkdir()
    record_path, _root, record = _valid_fixture(audit_root)
    solver_path = Path(record["solver"]["record_path"])
    solver_payload = json.loads(solver_path.read_text())
    solver_payload["physical_audit"]["volume_action"]["components"]["curl_curl"]["slave_row_identity"] = False
    solver_path.write_text(json.dumps(solver_payload), encoding="utf-8")
    mutated = json.loads(record_path.read_text())
    mutated["solver"]["record_sha256"] = _sha(solver_path)
    record_path.write_text(json.dumps(mutated), encoding="utf-8")
    with pytest.raises(checker.CheckError):
        checker.check_record(record_path, SOURCE_SHA)


def test_parent_and_solver_keep_heavy_imports_lazy() -> None:
    for path in (ROOT / "benchmarks/run_task038_full3d_jit_staged_parent.py", ROOT / "benchmarks/run_task038_full3d_jit_solver_bundle.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".", 1)[0])
        assert not names.intersection({"dolfinx", "mpi4py", "petsc4py", "ufl", "src"})
    assert parent.JIT_GROUPS == checker.GROUPS
    assert parent._child_command("positive-p6", Path("/x/cache"), Path("/x/r"), INPUT, SOURCE_SHA)[2] == checker.CHILD_MODULE
    module = SimpleNamespace(__name__="fake", __file__=str(ROOT / "fake.so"))
    results = [("compiled", module, (None, None)), ("compiled", module, ("header", "implementation"))]

    def original(*_args: object, **_kwargs: object) -> object:
        return results.pop(0)

    module.ffcx_jit = original
    calls, saved = solver._install_ffcx_observer(module)
    assert module.ffcx_jit()[2] == (None, None)
    assert module.ffcx_jit()[2] == ("header", "implementation")
    solver._restore_ffcx_observer(module, saved)
    assert calls[0]["code"] == [None, None] and calls[0]["cache_hit"] is True
    assert calls[1]["code"] == ["<non_none>", "<non_none>"] and calls[1]["cache_hit"] is False
