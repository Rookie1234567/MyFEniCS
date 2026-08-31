"""Independent, streaming checker for the raw J3 split cold-staged record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


CHECKER_SCHEMA = "task038.v14.j3.split-cold-staged.checker.v1"
RECORD_SCHEMA = "task038.v14.j3.split-cold-staged.parent-record.v1"
CHILD_RECORD_SCHEMA = "task038.full3d.jit-split.child-record.v1"
SOLVER_RECORD_SCHEMA = "task038.v14.j3.split-cold-staged.solver-record.v1"
MARKER_SCHEMA = "task038.v14.j3.marker.v1"
SAMPLE_SCHEMA = "task038.v14.j3.process-sample.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PARENT_MODULE = "benchmarks.run_task038_full3d_jit_staged_parent"
CHILD_MODULE = "benchmarks.run_task038_full3d_jit_precompile"
SOLVER_MODULE = "benchmarks.run_task038_full3d_jit_solver_bundle"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
EXPECTED_PROFILE = {
    "model_id": "euv_grazing1_phi0",
    "run_id": "euv_grazing1_phi0_full3d_iterative_mpi1",
    "comparison_group": "euv_grazing1_phi0",
    "wavelength_nm": 13.5,
    "grazing_angle_deg": 1.0,
    "incident_theta_deg": 89.0,
    "incident_phi_deg": 0.0,
    "polarization": "s",
    "nedelec_degree": 6,
    "mesh_target_size_nm": 10.0,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
    "boundary_model": "dtn_port",
    "dtn_order_policy": "auto_propagating",
    "dtn_assembly": "auxiliary",
}
MARKER_ORDER = (
    "parent_started", "fresh_cache_created",
    "precompile_positive_p6_started", "precompile_positive_p6_complete",
    "precompile_positive_p3_started", "precompile_positive_p3_complete",
    "precompile_positive_p1_started", "precompile_positive_p1_complete",
    "precompile_dtn_surface_started", "precompile_dtn_surface_complete",
    "precompile_incident_rhs_started", "precompile_incident_rhs_complete",
    "precompile_physical_volume_started",
    "precompile_physical_volume_curl_started",
    "precompile_physical_volume_curl_complete",
    "precompile_physical_volume_mass_started",
    "precompile_physical_volume_mass_complete",
    "precompile_physical_volume_complete",
    "all_precompile_children_gone", "solver_child_started",
    "positive_setup_started", "positive_setup_complete",
    "mode_inventory_started", "mode_inventory_complete",
    "surface_assemblers_started", "surface_assemblers_complete",
    "dtn_carrier_started", "dtn_carrier_complete", "dtn_action_complete",
    "physical_volume_action_started", "physical_volume_action_complete",
    "bundle_built", "source_built", "one_action_complete", "one_pc_complete",
    "solve_started", "solve_complete", "solver_stack_release_started",
    "solver_stack_release_complete", "recovery_started", "recovery_complete",
    "parent_complete",
)
EXPECTED_MARKERS = MARKER_ORDER[: MARKER_ORDER.index("bundle_built") + 1] + ("parent_complete",)
GROUPS = (
    "positive-p6", "positive-p3", "positive-p1", "dtn-surface", "incident-rhs",
    "physical-volume-curl", "physical-volume-mass",
)
EXPECTED_GROUP_ROLES = {
    "positive-p6": (2, ("positive_p6_action", "positive_p6_bilinear")),
    "positive-p3": (1, ("positive_p3_bilinear",)),
    "positive-p1": (1, ("positive_p1_bilinear",)),
    "dtn-surface": (4, ("dtn_surface_top_0", "dtn_surface_top_1", "dtn_surface_bottom_0", "dtn_surface_bottom_1")),
    "incident-rhs": (1, ("incident_top_traction",)),
    "physical-volume-curl": (1, ("physical_volume_curl_action",)),
    "physical-volume-mass": (1, ("physical_volume_mass_action",)),
}
EXPECTED_PROCESS_STAGES = tuple(f"precompile:{group}" for group in GROUPS) + ("precompile:parent-only", "solver")
RSS_LIMIT = 2_000_000_000
COMPILER_NAMES = frozenset({"gcc", "g++", "cc1", "cc1plus", "clang", "clang++", "ld", "collect2"})


class CheckError(Exception):
    def __init__(self, message: str, kind: str = "contract") -> None:
        super().__init__(message)
        self.kind = kind


def _fail(condition: bool, message: str, kind: str = "contract") -> None:
    if not condition:
        raise CheckError(message, kind)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as error:
        raise CheckError(f"cannot read JSON {path}: {error}") from error


def _absolute(value: Any) -> Path:
    _fail(isinstance(value, str) and os.path.isabs(value), f"path is not absolute: {value!r}")
    return Path(os.path.abspath(value))


def _option(argv: list[str], name: str) -> str:
    _fail(name in argv, f"command lacks {name}")
    index = argv.index(name)
    _fail(index + 1 < len(argv), f"command lacks value for {name}")
    return argv[index + 1]


def _compiler(fact: dict[str, Any], root_pid: int) -> bool:
    if int(fact["pid"]) == int(root_pid):
        return False
    names = {str(fact["comm"])}
    names.update(Path(token).name for token in str(fact["cmdline"]).split())
    return bool(names & COMPILER_NAMES)


def _check_runtime(runtime: Any, source_sha: str, label: str) -> None:
    repo = Path(__file__).resolve().parents[1]
    expected_executable = repo / ".venv" / "bin" / "python"
    expected_prefix = repo / ".venv"
    _fail(isinstance(runtime, dict), f"{label} runtime facts are missing")
    _fail(runtime.get("source_sha") == source_sha and runtime.get("branch") == BRANCH, f"{label} runtime source identity mismatch")
    _fail(runtime.get("qualified_activation") == "1" and runtime.get("mpi_size") == 1, f"{label} runtime qualification mismatch")
    _fail(runtime.get("petsc_scalar_type") == "complex128" and runtime.get("petsc_int_type") == "int32", f"{label} runtime PETSc ABI mismatch")
    _fail(runtime.get("threads") == {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}, f"{label} runtime thread facts mismatch")
    _fail(runtime.get("python_executable") == str(expected_executable), f"{label} executable is not the checkout lexical .venv")
    _fail(runtime.get("python_prefix") == str(expected_prefix), f"{label} prefix is not the checkout lexical .venv")
    modules = runtime.get("abi_modules")
    _fail(isinstance(modules, dict) and set(modules) == {"mpi4py", "petsc4py", "dolfinx", "basix"}, f"{label} ABI module facts are incomplete")
    _fail(all(isinstance(value, str) and Path(value).is_absolute() for value in modules.values()), f"{label} ABI module paths are invalid")


def _check_identity(record: dict[str, Any], expected_source_sha: str) -> None:
    _fail(re.fullmatch(r"[0-9a-f]{40}", expected_source_sha) is not None, "invalid expected source SHA")
    _fail(record.get("schema") == RECORD_SCHEMA, "parent record schema mismatch")
    _fail(record.get("stage") == "j3-split-cold-staged-parent", "parent stage mismatch")
    _fail(record.get("source_sha") == expected_source_sha and record.get("branch") == BRANCH, "parent source identity mismatch")
    _fail(record.get("raw_facts_only") is True and record.get("partial") is not True, "parent record is not a complete raw record")
    _fail(not any(key in record for key in ("passed", "classification", "status")), "parent record contains checker decision")
    identity = record.get("identity")
    _fail(isinstance(identity, dict), "parent identity is missing")
    _fail(identity.get("input_sha256") == INPUT_SHA256, "input SHA mismatch")
    _fail(identity.get("physical_model_sha256") == PHYSICAL_MODEL_SHA256, "physical model SHA mismatch")
    _fail(identity.get("mode_manifest_sha256") == MODE_MANIFEST_SHA256, "mode manifest SHA mismatch")
    _fail(identity.get("profile") == EXPECTED_PROFILE, "exact profile mismatch")
    architecture = record.get("architecture")
    _fail(
        isinstance(architecture, dict)
        and architecture.get("volume_component_count") == 2
        and architecture.get("volume_components") == ["curl_curl", "complex_material_mass"]
        and architecture.get("monolithic_physical_volume") is False
        and architecture.get("physical_volume_action_built") is True,
        "parent split-volume architecture facts are missing",
        "jit",
    )
    _check_runtime(identity.get("runtime"), expected_source_sha, "parent")
    input_path = _absolute(identity.get("input_path"))
    _fail(input_path.is_file() and _sha256(input_path) == INPUT_SHA256, "frozen input file/hash mismatch")
    command = record.get("command")
    expected_executable = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    _fail(isinstance(command, list) and command[1:3] == ["-m", PARENT_MODULE], "parent command is invalid")
    _fail(Path(command[0]) == expected_executable, "parent command is not the checkout lexical .venv")
    _fail(_option(command, "--source-sha") == expected_source_sha, "parent command source mismatch")
    _fail(_option(command, "--input") == str(input_path), "parent command input mismatch")


def _check_paths(record: dict[str, Any], record_argument: Path) -> dict[str, Path]:
    raw = record.get("paths")
    _fail(isinstance(raw, dict), "parent paths are missing")
    names = ("artifact_root", "cache_dir", "marker_dir", "record", "process_samples", "marker_manifest", "children_dir", "solver_dir", "cache_manifests_dir")
    paths = {name: _absolute(raw.get(name)) for name in names}
    root = paths["artifact_root"]
    _fail(root.is_dir(), "artifact root is missing")
    _fail(paths["cache_dir"] == root / "jit_cache" and paths["marker_dir"] == root / "markers", "fresh root layout mismatch")
    _fail(paths["record"] == record_argument == root / "parent_record.json", "parent record must be artifact_root/parent_record.json")
    command = record.get("command")
    _fail(_option(command, "--artifact-root") == str(root) and _option(command, "--record") == str(record_argument), "parent command paths mismatch")
    for name, path in paths.items():
        if name != "record":
            _fail(path.is_relative_to(root), f"{name} escapes artifact root")
            _fail(path.exists(), f"parent path is missing: {name}")
    return paths


def _check_markers(record: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    marker_dir = paths["marker_dir"]
    files = sorted(marker_dir.glob("*.json"), key=lambda path: int(path.name.split("_", 1)[0]))
    names = [path.name.split("_", 1)[1].rsplit(".", 1)[0] for path in files]
    _fail(tuple(names) == EXPECTED_MARKERS, "J3 marker sequence is not the required subsequence")
    calculated = []
    for path, name in zip(files, names):
        index = int(path.name.split("_", 1)[0])
        payload = _read_json(path)
        _fail(index == MARKER_ORDER.index(name), f"marker index mismatch: {name}")
        _fail(payload.get("schema") == MARKER_SCHEMA and payload.get("name") == name and payload.get("marker_index") == index, f"marker identity mismatch: {name}")
        _fail(type(payload.get("timestamp_ns")) is int and payload["timestamp_ns"] > 0, f"marker timestamp invalid: {name}")
        facts = payload.get("facts")
        _fail(isinstance(facts, dict), f"marker facts missing: {name}")
        solver_start = EXPECTED_MARKERS.index("positive_setup_started")
        solver_end = EXPECTED_MARKERS.index("bundle_built")
        expected_stage = (
            "j3-split-cold-staged-solver"
            if solver_start <= index <= solver_end
            else "j3-split-cold-staged-parent"
        )
        _fail(facts.get("stage") == expected_stage and facts.get("artifact_root") == str(paths["artifact_root"]) and facts.get("cache_dir") == str(paths["cache_dir"]) and facts.get("source_sha") == record["source_sha"], f"marker common facts mismatch: {name}")
        if name.startswith("precompile_") and name.endswith("_started") or name == "solver_child_started":
            _fail(isinstance(facts.get("command"), list), f"marker command missing: {name}")
        if name == "parent_complete":
            _fail(facts.get("compiler_descendant_count") == 0, "parent complete compiler count is not zero")
        calculated.append({"name": name, "path": str(path), "sha256": _sha256(path)})
    manifest_path = paths["marker_manifest"]
    _fail(_read_json(manifest_path) == calculated, "marker manifest does not close marker hashes")
    markers = record.get("markers", {})
    _fail(markers.get("names") == names and markers.get("manifest_path") == str(manifest_path) and markers.get("manifest_sha256") == _sha256(manifest_path), "record marker facts do not close")
    return names


def _check_sample(sample: dict[str, Any], parent_pid: int) -> int:
    _fail(sample.get("schema") == SAMPLE_SCHEMA and sample.get("root_pid") == parent_pid, "process sample identity mismatch", "process")
    _fail(isinstance(sample.get("stage"), str) and type(sample.get("timestamp_ns")) is int and sample["timestamp_ns"] > 0, "process sample timestamp/stage invalid", "process")
    _fail(sample.get("unreadable_pids") == [] and sample.get("all_status_readable") is True, "process sample is unreadable", "process")
    vanished = sample.get("vanished_pids")
    _fail(isinstance(vanished, list) and all(type(pid) is int and pid > 0 for pid in vanished) and len(vanished) == len(set(vanished)), "process vanished PID facts are invalid", "process")
    _fail(sample.get("exit_code") is None or type(sample.get("exit_code")) is int, "process sample exit code invalid", "process")
    members = sample.get("members")
    _fail(isinstance(members, list) and members, "process sample members missing", "process")
    pids = []
    for fact in members:
        required = ("pid", "ppid", "comm", "state", "cmdline", "stage", "rss_bytes", "pss_bytes", "swap_bytes", "timestamp_ns", "exit_code")
        _fail(isinstance(fact, dict) and all(key in fact for key in required), "process member fields incomplete", "process")
        _fail(type(fact["pid"]) is int and fact["pid"] > 0 and type(fact["ppid"]) is int and fact["ppid"] >= 0, "process member PID facts invalid", "process")
        _fail(all(isinstance(fact[key], str) for key in ("comm", "state", "cmdline", "stage")), "process member text invalid", "process")
        _fail(type(fact["rss_bytes"]) is int and fact["rss_bytes"] >= 0 and (fact["pss_bytes"] is None or type(fact["pss_bytes"]) is int and fact["pss_bytes"] >= 0) and type(fact["swap_bytes"]) is int and fact["swap_bytes"] >= 0, "process member memory facts invalid", "process")
        _fail(type(fact["timestamp_ns"]) is int and fact["timestamp_ns"] > 0 and fact["exit_code"] is None, "process member lifecycle facts invalid", "process")
        pids.append(fact["pid"])
    _fail(len(pids) == len(set(pids)) and parent_pid in pids, "process member PID set invalid", "process")
    _fail(set(vanished).isdisjoint(pids) and set(vanished).isdisjoint(sample["unreadable_pids"]), "process vanished PID overlaps a live or unreadable PID", "process")
    pss_ready = all(fact["pss_bytes"] is not None for fact in members)
    _fail(sample.get("pss_all_readable") is pss_ready, "process PSS readability mismatch", "process")
    _fail(sample.get("rss_bytes") == sum(fact["rss_bytes"] for fact in members) and sample.get("swap_bytes") == sum(fact["swap_bytes"] for fact in members), "process RSS/swap aggregate mismatch", "process")
    _fail(sample.get("pss_bytes") == (sum(fact["pss_bytes"] for fact in members) if pss_ready else None), "process PSS aggregate mismatch", "process")
    compiler_count = sum(_compiler(fact, parent_pid) for fact in members)
    _fail(sample.get("compiler_descendant_count") == compiler_count, "compiler count mismatch", "process")
    _fail(sample["rss_bytes"] < RSS_LIMIT and sample["swap_bytes"] == 0, "process resource gate failed", "resource")
    return compiler_count


def _stage_update(stats: dict[str, Any], sample: dict[str, Any], compiler_count: int, parent_pid: int) -> None:
    timestamp = int(sample["timestamp_ns"])
    stage = str(sample["stage"])
    fact = stats.setdefault(stage, {"sample_count": 0, "first_timestamp_ns": timestamp, "last_timestamp_ns": timestamp, "peak_rss_bytes": None, "max_swap_bytes": None, "all_status_readable": True, "compiler_descendant_peak": 0, "observed_descendant_pids": set(), "last_sample": None})
    fact["sample_count"] += 1
    fact["last_timestamp_ns"] = timestamp
    rss = sample.get("rss_bytes")
    swap = sample.get("swap_bytes")
    fact["peak_rss_bytes"] = rss if fact["peak_rss_bytes"] is None else max(fact["peak_rss_bytes"], rss)
    fact["max_swap_bytes"] = swap if fact["max_swap_bytes"] is None else max(fact["max_swap_bytes"], swap)
    fact["all_status_readable"] = fact["all_status_readable"] and sample.get("all_status_readable") is True
    fact["compiler_descendant_peak"] = max(fact["compiler_descendant_peak"], compiler_count)
    fact["observed_descendant_pids"].update(int(member["pid"]) for member in sample["members"] if int(member["pid"]) != parent_pid)
    fact["last_sample"] = sample


def _check_process(record: dict[str, Any], paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    process = record.get("process")
    _fail(isinstance(process, dict), "parent process facts are missing")
    sample_path = _absolute(process.get("sample_path"))
    _fail(sample_path == paths["process_samples"] and sample_path.is_file(), "process sample path is invalid", "process")
    _fail(process.get("sample_sha256") == _sha256(sample_path), "process sample hash mismatch", "process")
    parent_pid = process.get("parent_pid")
    _fail(type(parent_pid) is int and parent_pid > 0, "parent PID fact is invalid", "process")
    stats: dict[str, dict[str, Any]] = {}
    count = 0
    first: int | None = None
    last: int | None = None
    peak: int | None = None
    max_swap: int | None = None
    compiler_peak = 0
    all_readable = True
    observed: set[int] = set()
    last_sample: dict[str, Any] | None = None
    with sample_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            sample = json.loads(line)
            compiler_count = _check_sample(sample, parent_pid)
            timestamp = int(sample["timestamp_ns"])
            _fail(last is None or timestamp > last, "process sample timestamps are not strictly increasing", "process")
            count += 1
            first = timestamp if first is None else first
            last = timestamp
            rss = sample["rss_bytes"]
            swap = sample["swap_bytes"]
            peak = rss if peak is None else max(peak, rss)
            max_swap = swap if max_swap is None else max(max_swap, swap)
            compiler_peak = max(compiler_peak, compiler_count)
            all_readable = all_readable and sample["all_status_readable"] is True
            observed.update(int(member["pid"]) for member in sample["members"] if int(member["pid"]) != parent_pid)
            _stage_update(stats, sample, compiler_count, parent_pid)
            last_sample = sample
    _fail(count > 0 and process.get("sample_count") == count, "process sample count mismatch", "process")
    _fail(process.get("first_timestamp_ns") == first and process.get("last_timestamp_ns") == last, "process timestamp summary mismatch", "process")
    _fail(process.get("all_status_readable") is all_readable and process.get("peak_rss_bytes") == peak and process.get("max_swap_bytes") == max_swap and process.get("compiler_descendant_peak") == compiler_peak, "process global summary mismatch", "process")
    _fail(process.get("observed_descendant_pids") == sorted(observed) and process.get("last_sample") == last_sample, "process observed-PID summary mismatch", "process")
    _fail(set(stats) == set(EXPECTED_PROCESS_STAGES), "process stages are incomplete or contain extras", "process")
    reported_stages = process.get("stage_summaries")
    _fail(isinstance(reported_stages, dict) and set(reported_stages) == set(stats), "stage summary inventory mismatch", "process")
    for stage, fact in stats.items():
        reported = reported_stages[stage]
        fact["observed_descendant_pids"] = sorted(fact["observed_descendant_pids"])
        for key in ("sample_count", "first_timestamp_ns", "last_timestamp_ns", "peak_rss_bytes", "max_swap_bytes", "all_status_readable", "compiler_descendant_peak", "observed_descendant_pids", "last_sample"):
            _fail(reported.get(key) == fact[key], f"stage summary mismatch: {stage}:{key}", "process")
        if stage in {"precompile:parent-only", "solver"}:
            _fail(fact["compiler_descendant_peak"] == 0, f"compiler observed in {stage}", "jit")
            if stage == "precompile:parent-only":
                _fail(fact["observed_descendant_pids"] == [], "parent-only observed descendants", "process")
                _fail([member["pid"] for member in fact["last_sample"]["members"]] == [parent_pid], "parent-only sample contains a descendant", "process")
    return stats


def _check_monitor(monitor: Any, stage: dict[str, Any], expected_pid: int, label: str) -> None:
    _fail(isinstance(monitor, dict), f"{label} monitor is missing", "process")
    _fail(monitor.get("pid") == expected_pid, f"{label} monitor pid mismatch", "process")
    for key in ("sample_count", "started_ns", "ended_ns", "peak_rss_bytes", "max_swap_bytes", "all_status_readable", "compiler_descendant_peak", "observed_descendant_pids"):
        stage_key = {"started_ns": "first_timestamp_ns", "ended_ns": "last_timestamp_ns"}.get(key, key)
        _fail(monitor.get(key) == stage.get(stage_key), f"{label} monitor/{stage_key} mismatch", "process")
    _fail(expected_pid in monitor["observed_descendant_pids"] and monitor.get("process_group_gone") is True and monitor.get("required_sigkill") is False and monitor.get("natural_exit") is True and monitor.get("returncode") == 0, f"{label} process group did not close naturally", "process")


def _check_child_record(child: dict[str, Any], group: str, expected_source_sha: str, cache_dir: Path, input_path: Path) -> dict[str, Any]:
    record_path = _absolute(child.get("record_path"))
    _fail(record_path.is_file() and child.get("record_sha256") == _sha256(record_path), f"child record/hash missing: {group}", "jit")
    payload = _read_json(record_path)
    _fail(payload.get("schema") == CHILD_RECORD_SCHEMA and payload.get("group") == group and payload.get("source_sha") == expected_source_sha and payload.get("branch") == BRANCH, f"child identity mismatch: {group}")
    _fail(payload.get("stage") == "j3-split-precompile-child", f"child stage mismatch: {group}")
    _fail(payload.get("raw_facts_only") is True and not any(key in payload for key in ("passed", "classification", "status")), f"child contains checker decision: {group}")
    command = payload.get("command")
    expected_executable = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    _fail(isinstance(command, list) and Path(command[0]) == expected_executable and command[1:3] == ["-m", CHILD_MODULE], f"child command mismatch: {group}")
    _fail(_option(command, "--group") == group and _option(command, "--cache-dir") == str(cache_dir) and _option(command, "--record") == str(record_path) and _option(command, "--input") == str(input_path) and _option(command, "--expected-source-sha") == expected_source_sha, f"child command arguments mismatch: {group}")
    identity = payload.get("input")
    _fail(isinstance(identity, dict) and identity.get("path") == str(input_path) and identity.get("input_sha256") == INPUT_SHA256 and identity.get("physical_model_sha256") == PHYSICAL_MODEL_SHA256 and identity.get("mode_manifest_sha256") == MODE_MANIFEST_SHA256 and identity.get("profile") == EXPECTED_PROFILE, f"child profile mismatch: {group}")
    _check_runtime(payload.get("runtime"), expected_source_sha, f"child {group}")
    _fail(payload.get("cache", {}).get("jit_options") == {}, f"child JIT options mismatch: {group}")
    count, roles = EXPECTED_GROUP_ROLES[group]
    group_facts = payload.get("facts", {}).get("group_facts")
    _fail(isinstance(group_facts, dict) and group_facts.get("compiled_form_count") == count and tuple(group_facts.get("form_roles", ())) == roles, f"child form inventory mismatch: {group}", "jit")
    if group in {"physical-volume-curl", "physical-volume-mass"}:
        component = "curl" if group.endswith("curl") else "mass"
        _fail(group_facts.get("component") == component and group_facts.get("component_count") == 1, f"child physical component facts mismatch: {group}", "jit")
    architecture = payload.get("architecture")
    _fail(isinstance(architecture, dict), f"child architecture missing: {group}")
    for key in ("matrix", "factor", "pc", "rhs_vector", "surface_carrier", "dtn_carrier", "solve", "recovery", "pde"):
        _fail(architecture.get(key) is False, f"child forbidden object fact is true: {group}:{key}", "jit")
    _fail(architecture.get("compile") is True and architecture.get("mesh") is True and architecture.get("jit") is True, f"child compile facts mismatch: {group}", "jit")
    for path_key in ("stdout_path", "stderr_path"):
        path = _absolute(child.get(path_key))
        _fail(path.is_file() and child.get(path_key.replace("_path", "_sha256")) == _sha256(path), f"child output hash mismatch: {group}", "process")
    _fail(child.get("returncode") == 0 and child.get("natural_exit") is True and child.get("process_group_gone") is not False and child.get("required_sigkill", False) is False, f"child lifecycle facts mismatch: {group}", "process")
    return payload


def _manifest(path: Path, cache_dir: Path) -> dict[str, Any]:
    value = _read_json(path)
    _fail(value.get("cache_dir") == str(cache_dir), f"cache manifest directory mismatch: {path}", "jit")
    artifacts = value.get("artifacts")
    _fail(isinstance(artifacts, list) and value.get("artifact_count") == len(artifacts), f"cache manifest count mismatch: {path}", "jit")
    for item in artifacts:
        _fail(isinstance(item, dict) and set(item) == {"relative_path", "bytes", "sha256"}, f"cache artifact fact invalid: {path}", "jit")
        relative = item["relative_path"]
        _fail(isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts and Path(relative).suffix in {".c", ".o", ".so"}, f"cache artifact path invalid: {relative}", "jit")
        target = cache_dir / relative
        _fail(target.is_file() and target.stat().st_size == item["bytes"] and _sha256(target) == item["sha256"], f"cache artifact hash mismatch: {relative}", "jit")
    return value


def _check_physical_audit(value: Any) -> None:
    _fail(isinstance(value, dict), "solver physical audit is missing", "jit")
    _fail(
        value.get("schema") == "task038.fullspace-physical-action.v1"
        and value.get("operator") == "A_volume_plus_dynamic_DtN"
        and value.get("physical_form")
        == "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn"
        and value.get("volume_component_count") == 2
        and value.get("volume_components")
        == ["curl_curl", "complex_material_mass"],
        "solver physical audit top-level split facts mismatch",
        "jit",
    )
    volume = value.get("volume_action")
    _fail(
        isinstance(volume, dict)
        and volume.get("schema") == "task038.fullspace-split-volume-action.v1"
        and volume.get("operator") == "A_curl_curl_plus_A_complex_material_mass"
        and volume.get("component_count") == 2
        and volume.get("constraint_identity_rows_exactly_once") is True
        and volume.get("third_persistent_sum_vector") is False,
        "solver volume action split facts mismatch",
        "jit",
    )
    components = volume.get("components")
    _fail(
        isinstance(components, dict)
        and set(components) == {"curl_curl", "complex_material_mass"},
        "solver volume action component keys mismatch",
        "jit",
    )
    for name, slave_identity in (("curl_curl", True), ("complex_material_mass", False)):
        component = components[name]
        _fail(
            isinstance(component, dict)
            and component.get("schema") == "task038.fullspace-mpc-form-action.v1"
            and component.get("operator") == "uncondensed_fullspace_curl_mass_form"
            and component.get("slave_row_identity") is slave_identity
            and all(
                component.get(key) is False
                for key in (
                    "global_matrix_materialized",
                    "global_constraint_matrix_materialized",
                    "global_condensed_schur_materialized",
                    "cell_schur_matrix_materialized",
                    "slab_matrix_materialized",
                )
            ),
            f"solver physical component audit mismatch: {name}",
            "jit",
        )


def _check_cache(record: dict[str, Any], paths: dict[str, Path]) -> tuple[set[str], set[str]]:
    cache_facts = record.get("cache")
    _fail(isinstance(cache_facts, dict) and cache_facts.get("initial_empty") is True, "fresh cache fact is missing", "jit")
    initial_entry = cache_facts.get("initial_manifest")
    _fail(isinstance(initial_entry, dict), "initial cache manifest is missing", "jit")
    initial_path = _absolute(initial_entry.get("path"))
    _fail(initial_path.is_relative_to(paths["cache_manifests_dir"]) and initial_entry.get("sha256") == _sha256(initial_path), "initial manifest path/hash mismatch", "jit")
    previous = _manifest(initial_path, paths["cache_dir"])
    _fail(previous.get("artifacts") == [] and previous.get("artifact_count") == 0, "fresh cache is not empty", "jit")
    groups = cache_facts.get("group_manifests")
    _fail(isinstance(groups, list) and [entry.get("group") for entry in groups] == list(GROUPS), "cache group manifest order mismatch", "jit")
    all_modules: set[str] = set()
    incident_modules: set[str] = set()
    for entry, group, child in zip(groups, GROUPS, record.get("children", [])):
        path = _absolute(entry.get("path"))
        _fail(path.is_relative_to(paths["cache_manifests_dir"]) and entry.get("sha256") == _sha256(path), f"cache manifest path/hash mismatch: {group}", "jit")
        current = _manifest(path, paths["cache_dir"])
        old = {item["relative_path"]: item["sha256"] for item in previous["artifacts"]}
        new = {item["relative_path"]: item["sha256"] for item in current["artifacts"]}
        _fail(all(key in new and new[key] == value for key, value in old.items()), f"cache is not monotonic after {group}", "jit")
        added = sorted(key for key in new if key not in old)
        child_added = sorted(item["relative_path"] for item in child.get("added_artifacts", []))
        _fail(added == child_added and entry.get("artifact_count") == current["artifact_count"], f"cache delta mismatch after {group}", "jit")
        modules = sorted(Path(key).name for key in added if key.endswith(".so"))
        expected_count, _roles = EXPECTED_GROUP_ROLES[group]
        _fail(len(modules) == expected_count and entry.get("new_module_basenames") == modules and child.get("new_module_basenames") == modules, f".so inventory mismatch after {group}", "jit")
        all_modules.update(modules)
        if group == "incident-rhs":
            incident_modules.update(modules)
        previous = current
    _fail(len(all_modules) == 11 and len(incident_modules) == 1, "precompile module inventory is not 11 with one deferred incident module", "jit")
    _fail(cache_facts.get("precompiled_module_basenames") == sorted(all_modules) and cache_facts.get("deferred_incident_module_basenames") == sorted(incident_modules), "precompiled/deferred module inventory mismatch", "jit")
    before = cache_facts.get("before_solver")
    after = cache_facts.get("after_solver")
    _fail(isinstance(before, dict) and isinstance(after, dict), "solver cache manifests are missing", "jit")
    before_path = _absolute(before.get("path"))
    after_path = _absolute(after.get("path"))
    _fail(before_path.is_relative_to(paths["cache_manifests_dir"]) and after_path.is_relative_to(paths["cache_manifests_dir"]), "solver manifest escapes artifact root", "jit")
    before_value = _manifest(before_path, paths["cache_dir"])
    after_value = _manifest(after_path, paths["cache_dir"])
    _fail(before.get("sha256") == _sha256(before_path) and after.get("sha256") == _sha256(after_path) and before_path.read_bytes() == after_path.read_bytes() and before_value == after_value and cache_facts.get("solver_unchanged") is True, "solver changed the formal cache", "jit")
    _fail(before_value == previous and sorted(Path(item["relative_path"]).name for item in previous["artifacts"] if item["relative_path"].endswith(".so")) == sorted(all_modules), "before-solver inventory mismatch", "jit")
    return all_modules, incident_modules


def _check_solver(record: dict[str, Any], paths: dict[str, Path], expected_source_sha: str, all_modules: set[str], incident_modules: set[str], input_path: Path, stage_stats: dict[str, dict[str, Any]]) -> None:
    info = record.get("solver")
    _fail(isinstance(info, dict), "solver facts are missing", "jit")
    solver_path = _absolute(info.get("record_path"))
    _fail(solver_path.is_file() and info.get("record_sha256") == _sha256(solver_path), "solver record/hash missing", "jit")
    payload = _read_json(solver_path)
    _fail(payload.get("schema") == SOLVER_RECORD_SCHEMA and payload.get("stage") == "j3-split-cold-staged-solver" and payload.get("source_sha") == expected_source_sha and payload.get("branch") == BRANCH, "solver record identity mismatch", "jit")
    _fail(payload.get("raw_facts_only") is True and not any(key in payload for key in ("passed", "classification", "status")), "solver record contains checker decision", "jit")
    command = payload.get("command")
    expected_executable = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    _fail(isinstance(command, list) and Path(command[0]) == expected_executable and command[1:3] == ["-m", SOLVER_MODULE], "solver command identity mismatch", "jit")
    _fail(_option(command, "--cache-dir") == str(paths["cache_dir"]) and _option(command, "--marker-dir") == str(paths["marker_dir"]) and _option(command, "--record") == str(solver_path) and _option(command, "--input") == str(input_path) and _option(command, "--expected-source-sha") == expected_source_sha, "solver command arguments mismatch", "jit")
    identity = payload.get("identity")
    _fail(isinstance(identity, dict) and identity.get("input_path") == str(input_path) and identity.get("input_sha256") == INPUT_SHA256 and identity.get("physical_model_sha256") == PHYSICAL_MODEL_SHA256 and identity.get("mode_manifest_sha256") == MODE_MANIFEST_SHA256 and identity.get("profile") == EXPECTED_PROFILE, "solver profile mismatch", "jit")
    _check_runtime(payload.get("runtime"), expected_source_sha, "solver")
    _check_physical_audit(payload.get("physical_audit"))
    architecture = payload.get("architecture")
    expected_architecture = {
        "p6_matrix_free": True, "p6_global_aij": False, "high_order_global_aij": False,
        "global_dense_transfer": False, "numeric_allgather": False,
        "p3_sparse_matrix_built": True, "p1_sparse_matrix_built": True,
        "p1_direct_factor_built": True, "same_mesh_pmg_built": True,
        "streaming_dtn_action_built": True, "dtn_carrier_built": True,
        "dtn_carrier_lifetime": "transient_released", "physical_volume_action_built": True,
        "volume_component_count": 2,
        "volume_components": ["curl_curl", "complex_material_mass"],
        "monolithic_physical_volume": False,
        "rhs_built": False, "outer_ksp_built": False, "solve_run": False,
        "recovery_run": False, "bundle_destroyed_before_record": True,
    }
    _fail(architecture == expected_architecture, "solver architecture facts are not the measured bundle facts", "jit")
    _fail(tuple(payload.get("marker_names", ())) == EXPECTED_MARKERS[:-1], "solver marker prefix mismatch")
    calls = payload.get("ffcx_calls")
    _fail(isinstance(calls, list) and len(calls) == payload.get("expected_ffcx_call_count") == 10, "solver FFCx call count is not ten", "jit")
    module_names: set[str] = set()
    for call in calls:
        _fail(isinstance(call, dict) and call.get("code") == [None, None] and call.get("cache_hit") is True and isinstance(call.get("module_name"), str) and call["module_name"], "solver FFCx call was not an exact cache hit", "jit")
        module_file = _absolute(call.get("module_file"))
        _fail(module_file.is_file() and module_file.suffix == ".so" and module_file.is_relative_to(paths["cache_dir"]), "solver module file is outside formal cache", "jit")
        module_names.add(module_file.name)
    _fail(len(module_names) == 10 and module_names == all_modules - incident_modules, "solver module set is not ten distinct precompiled modules", "jit")
    _fail(payload.get("mode", {}).get("manifest_sha256") == MODE_MANIFEST_SHA256, "solver mode identity mismatch", "jit")
    for path_key in ("stdout_path", "stderr_path"):
        path = _absolute(info.get(path_key))
        _fail(path.is_file() and info.get(path_key.replace("_path", "_sha256")) == _sha256(path), "solver output hash mismatch", "process")
    _check_monitor(info.get("process"), stage_stats["solver"], int(info["process"]["pid"]), "solver")
    _fail(info.get("cache_unchanged") is True, "solver cache unchanged fact is false", "jit")


def check_record(record_path: Path | str, expected_source_sha: str) -> dict[str, Any]:
    record_argument = Path(os.path.abspath(os.fspath(record_path)))
    record = _read_json(record_argument)
    _fail(isinstance(record, dict), "parent record is not an object")
    _check_identity(record, expected_source_sha)
    paths = _check_paths(record, record_argument)
    input_path = _absolute(record["identity"]["input_path"])
    _check_markers(record, paths)
    stage_stats = _check_process(record, paths)
    _fail(isinstance(record.get("children"), list) and [item.get("group") for item in record["children"]] == list(GROUPS), "child order mismatch")
    previous_end = None
    for child, group in zip(record["children"], GROUPS):
        _check_monitor(child.get("process"), stage_stats[f"precompile:{group}"], int(child["pid"]), f"child {group}")
        if previous_end is not None:
            _fail(previous_end < child["process"]["started_ns"], f"child stages overlap: {group}", "process")
        previous_end = child["process"]["ended_ns"]
        _check_child_record(child, group, expected_source_sha, paths["cache_dir"], input_path)
    _fail(stage_stats["precompile:parent-only"]["first_timestamp_ns"] > previous_end, "parent-only sample overlaps final child", "process")
    all_modules, incident_modules = _check_cache(record, paths)
    solver = record["solver"]
    _fail(stage_stats["solver"]["first_timestamp_ns"] > stage_stats["precompile:parent-only"]["last_timestamp_ns"], "solver stage overlaps precompile", "process")
    _check_solver(record, paths, expected_source_sha, all_modules, incident_modules, input_path, stage_stats)
    return {
        "schema": CHECKER_SCHEMA,
        "passed": True,
        "classification": "J3_SPLIT_COLD_STAGED_PASS",
        "contract_errors": [],
        "gate_failures": [],
        "identity": {"source_sha": record["source_sha"], "branch": record["branch"], "input_sha256": record["identity"]["input_sha256"], "physical_model_sha256": record["identity"]["physical_model_sha256"], "mode_manifest_sha256": record["identity"]["mode_manifest_sha256"]},
        "evidence": {"raw_record_path": str(record_argument), "raw_record_sha256": _sha256(record_argument), "process_sample_sha256": record["process"]["sample_sha256"], "marker_manifest_sha256": record["markers"]["manifest_sha256"]},
        "metrics": {"precompile_group_count": len(GROUPS), "solver_ffcx_call_count": 10, "precompiled_module_count": len(all_modules), "solver_module_count": len(all_modules - incident_modules), "process_sample_count": record["process"]["sample_count"], "peak_rss_bytes": record["process"]["peak_rss_bytes"], "max_swap_bytes": record["process"]["max_swap_bytes"]},
    }


def _emit(value: dict[str, Any], output: str | None) -> None:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    if output is None or output == "-":
        sys.stdout.write(encoded)
    else:
        Path(os.path.abspath(output)).write_text(encoded, encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", default="-")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = check_record(args.record, args.expected_source_sha)
    except (CheckError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
        if not isinstance(error, CheckError):
            error = CheckError(str(error))
        result = {"schema": CHECKER_SCHEMA, "passed": False, "classification": {"resource": "J3_RESOURCE_GATE_FAIL", "process": "J3_PROCESS_AUTHORITY_FAIL", "jit": "J3_SPLIT_STAGING_IDENTITY_FAIL"}.get(error.kind, "J3_CONTRACT_INVALID"), "contract_errors": [str(error)] if error.kind == "contract" else [], "gate_failures": [str(error)] if error.kind != "contract" else [], "metrics": {}}
        _emit(result, args.output)
        return 1
    _emit(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ("CHECKER_SCHEMA", "EXPECTED_GROUP_ROLES", "EXPECTED_MARKERS", "GROUPS", "check_record", "main")
