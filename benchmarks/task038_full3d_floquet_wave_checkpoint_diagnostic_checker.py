"""Independent checker for the V15 checkpoint wave-subspace diagnostic.

Only JSON, JSONL and the small diagnostic NPZ are read here.  The checker does
not import the parent, worker, solver, PETSc, MPI, or DOLFINx code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np


CHECKER_SCHEMA = "task038.v15.f2-f3.floquet-wave.checker.v1"
PARENT_SCHEMA = "task038.v15.f2-f3.floquet-wave.parent-record.v1"
WORKER_SCHEMA = "task038.v15.f2-f3.floquet-wave.worker-record.v1"
MARKER_SCHEMA = "task038.v15.f2-f3.floquet-wave.marker.v1"
SAMPLE_SCHEMA = "task038.v14.j3.process-sample.v1"
BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PARENT_MODULE = "benchmarks.run_task038_full3d_jit_staged_parent"
WORKER_MODULE = "benchmarks.run_task038_full3d_floquet_wave_checkpoint_diagnostic"
WORKER_PROFILE = "p6/h10/13.5nm/s/grazing1/phi0"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
SELECTOR_SCHEMA = "task038.v15.floquet-selection.v1"
SELECTOR_SHA256 = "7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3"
SELECTED_MODE_INDICES = (
    38, 39, 72, 73, 76, 77, 32, 33, 36, 37, 40, 41, 0, 1, 42, 43,
    46, 47, 2, 3, 6, 7, 74, 75, 34, 35, 66, 67, 70, 71, 26, 27,
)
PROFILE = {
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
CHECKPOINT = {
    "source_sha": "ee5920b9fa977a39fea7bc09cfbe155303acdb2d",
    "input_identity_sha256": "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f",
    "operator_identity_sha256": "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3",
    "manifest_sha256": "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139",
    "shard_sha256": "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b",
    "iteration": 1000,
    "stored_explicit_true_residual": 0.4837947981092168,
}
CHECKPOINT_SCHEMA = "fixed-memory-krylov.solution-checkpoint.v1"
CHECKPOINT_GLOBAL_SIZE = 173802
CHECKPOINT_LOCAL_SIZE = 173802
CHECKPOINT_VECTOR_BYTES = 2780960
CHECKPOINT_VECTOR_DTYPE = "complex128"
CHECKPOINT_VECTOR_SHAPE = [173802]
GROUPS = (
    "positive-p6", "positive-p3", "positive-p1", "dtn-surface", "incident-rhs",
    "physical-volume-curl", "physical-volume-mass",
)
GROUP_ROLES = {
    "positive-p6": (2, ("positive_p6_action", "positive_p6_bilinear")),
    "positive-p3": (1, ("positive_p3_bilinear",)),
    "positive-p1": (1, ("positive_p1_bilinear",)),
    "dtn-surface": (4, ("dtn_surface_top_0", "dtn_surface_top_1", "dtn_surface_bottom_0", "dtn_surface_bottom_1")),
    "incident-rhs": (1, ("incident_top_traction",)),
    "physical-volume-curl": (1, ("physical_volume_curl_action",)),
    "physical-volume-mass": (1, ("physical_volume_mass_action",)),
}
F2_MARKER_ORDER = (
    "parent_started", "fresh_cache_created",
    "precompile_positive_p6_started", "precompile_positive_p6_complete",
    "precompile_positive_p3_started", "precompile_positive_p3_complete",
    "precompile_positive_p1_started", "precompile_positive_p1_complete",
    "precompile_dtn_surface_started", "precompile_dtn_surface_complete",
    "precompile_incident_rhs_started", "precompile_incident_rhs_complete",
    "precompile_physical_volume_started",
    "precompile_physical_volume_curl_started", "precompile_physical_volume_curl_complete",
    "precompile_physical_volume_mass_started", "precompile_physical_volume_mass_complete",
    "precompile_physical_volume_complete", "all_precompile_children_gone",
    "diagnostic_child_started", "bundle_built", "source_built",
    "checkpoint_restore_started", "checkpoint_restore_complete",
    "residual_action_started", "residual_action_complete", "basis_started",
    "basis_complete", "projection_started", "projection_complete",
    "release_started", "release_complete", "parent_complete",
)
PROCESS_STAGES = tuple(f"precompile:{group}" for group in GROUPS) + (
    "precompile:parent-only", "diagnostic",
)
COMPILER_NAMES = frozenset({"gcc", "g++", "cc1", "cc1plus", "clang", "clang++", "ld", "collect2"})
RSS_LIMIT = 2_000_000_000
RSS_WARNING = 1_800_000_000
RSS_WATCHDOG = 1_950_000_000
RANK = 32
F2_LIMIT = 1.0e-11
ORTH_LIMIT = 1.0e-10
REPEAT_LIMIT = 1.0e-12
CAPTURE_LIMIT = 0.90
RHO_LIMIT = 0.31622776601683794
IDEAL_LIMIT = 0.153
EXPECTED_ARCHITECTURE = {
    "checkpoint_read": True, "residual_action_count": 1,
    "basis_pc_count": 32, "basis_action_count": 32,
    "retains_q": True, "retains_r": True, "retains_z": False,
    "retains_az": False, "ksp": False, "recovery": False,
    "global_aij": False, "numeric_allgather": False,
    "predicted_central_rss": 1_555_934_144,
    "q32_bytes": 88_986_624, "six_vector_bytes": 16_684_992,
    "max_simultaneous_high_vector_count": 6,
    "watchdog_stop_bytes": 1_950_000_000, "hard_gate_bytes": RSS_LIMIT,
}
EXPECTED_PARENT_ARCHITECTURE = {
    "workflow": "f2-f3-floquet-wave", "precompile_group_count": 7,
    "diagnostic_worker": WORKER_MODULE, "checkpoint_read": True,
    "residual_action_count": 1, "ksp": False, "recovery": False,
    "global_aij": False, "numeric_allgather": False,
    "retains_z": False, "retains_az": False,
    "predicted_central_rss": 1_555_934_144,
    "q32_bytes": 88_986_624, "six_vector_bytes": 16_684_992,
    "max_simultaneous_high_vector_count": 6,
    "watchdog_stop_bytes": RSS_WATCHDOG, "hard_gate_bytes": RSS_LIMIT,
    "raw_facts_only": True,
}


class CheckError(Exception):
    def __init__(
        self, message: str, kind: str = "contract", metrics: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.metrics = {} if metrics is None else metrics


def _require(value: Any, key: str, label: str, kind: str = "contract") -> Any:
    if not isinstance(value, dict) or key not in value:
        raise CheckError(f"{label} is missing {key}", kind)
    return value[key]


def _need_dict(value: Any, label: str, kind: str = "contract") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CheckError(f"{label} is not an object", kind)
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_sha(values: Any) -> str:
    array = np.ascontiguousarray(values, dtype=np.complex128)
    return hashlib.sha256(memoryview(array).cast("B")).hexdigest()


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as error:
        raise CheckError(f"cannot read JSON {path}: {error}") from error


def _absolute(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not os.path.isabs(value):
        raise CheckError(f"{label} is not an absolute path")
    return Path(os.path.abspath(value))


def _option(command: Any, name: str) -> str:
    if not isinstance(command, list) or name not in command:
        raise CheckError(f"command lacks {name}")
    index = command.index(name)
    if index + 1 >= len(command) or not isinstance(command[index + 1], str):
        raise CheckError(f"command lacks value for {name}")
    return command[index + 1]


def _compiler(fact: dict[str, Any], root_pid: int) -> bool:
    if int(fact["pid"]) == root_pid:
        return False
    names = {str(fact["comm"])}
    names.update(Path(token).name for token in str(fact["cmdline"]).split())
    return bool(names & COMPILER_NAMES)


def _check_parent_runtime(runtime: Any, source: str) -> None:
    runtime = _need_dict(runtime, "parent identity.runtime")
    repo = Path(__file__).resolve().parents[1]
    if runtime.get("source_sha") != source or runtime.get("branch") != BRANCH:
        raise CheckError("parent runtime source identity mismatch")
    if runtime.get("clean_source_tree") is not True or runtime.get("qualified_activation") != "1":
        raise CheckError("parent runtime qualification mismatch")
    if runtime.get("python_executable") != str(repo / ".venv/bin/python"):
        raise CheckError("parent runtime executable is not lexical .venv")
    if runtime.get("python_prefix") != str(repo / ".venv"):
        raise CheckError("parent runtime prefix is not lexical .venv")


def _check_worker_runtime(runtime: Any, source: str) -> None:
    runtime = _need_dict(runtime, "worker provenance")
    repo = Path(__file__).resolve().parents[1]
    if runtime.get("source_sha") != source or runtime.get("branch") != BRANCH:
        raise CheckError("worker runtime source identity mismatch")
    if runtime.get("qualified_activation") != "1" or runtime.get("mpi_size") != 1:
        raise CheckError("worker runtime qualification mismatch")
    if runtime.get("petsc_scalar_type") != "complex128" or runtime.get("petsc_int_type") != "int32":
        raise CheckError("worker PETSc ABI mismatch")
    if runtime.get("threads") != {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}:
        raise CheckError("worker thread facts mismatch")
    if runtime.get("python_executable") != str(repo / ".venv/bin/python") or runtime.get("python_prefix") != str(repo / ".venv"):
        raise CheckError("worker interpreter is not lexical .venv")
    modules = runtime.get("abi_modules")
    if not isinstance(modules, dict) or set(modules) != {"mpi4py", "petsc4py", "dolfinx", "basix"}:
        raise CheckError("worker ABI module facts are incomplete")
    if any(not isinstance(value, str) or not Path(value).is_absolute() for value in modules.values()):
        raise CheckError("worker ABI module path is invalid")


def _check_identity(record: dict[str, Any], source: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise CheckError("expected source SHA is invalid")
    if record.get("schema") != PARENT_SCHEMA or record.get("workflow") != "f2-f3-floquet-wave":
        raise CheckError("parent schema/workflow mismatch")
    if record.get("stage") != "f2-f3-floquet-wave-parent" or record.get("source_sha") != source or record.get("branch") != BRANCH:
        raise CheckError("parent identity mismatch")
    if record.get("raw_facts_only") is not True or record.get("partial") is True:
        raise CheckError("parent is not a complete raw record")
    if any(key in record for key in ("passed", "classification", "status")):
        raise CheckError("parent contains checker decision")
    identity = _need_dict(record.get("identity"), "parent identity")
    if identity.get("input_sha256") != INPUT_SHA256 or identity.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256 or identity.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256 or identity.get("profile") != PROFILE:
        raise CheckError("parent frozen identity mismatch")
    input_path = _absolute(_require(identity, "input_path", "parent identity"), "parent input_path")
    if not input_path.is_file() or _sha(input_path) != INPUT_SHA256:
        raise CheckError("frozen input file/hash mismatch")
    _check_parent_runtime(_require(identity, "runtime", "parent identity"), source)
    architecture = _need_dict(record.get("architecture"), "parent architecture")
    f3_status = architecture.get("f3_status")
    if f3_status not in {"observed", "span_gate_failed", "not_run_by_f2_residual_gate", "not_run_by_f2_identity_gate", "not_run_by_f2_checkpoint_gate"}:
        raise CheckError("parent F3 status is invalid", "jit")
    expected_parent_architecture = dict(EXPECTED_PARENT_ARCHITECTURE)
    no_f2_action = {"not_run_by_f2_identity_gate", "not_run_by_f2_checkpoint_gate"}
    expected_parent_architecture["residual_action_count"] = 0 if f3_status in no_f2_action else 1
    expected_parent_architecture["checkpoint_read"] = f3_status not in no_f2_action
    expected_keys = set(EXPECTED_PARENT_ARCHITECTURE) | {
        "f3_status", "basis_pc_count", "basis_action_count", "retains_q", "retains_r"
    }
    if set(architecture) != expected_keys or any(architecture.get(key) != value for key, value in expected_parent_architecture.items()):
        raise CheckError("parent architecture facts mismatch", "jit")
    expected_basis = 32 if f3_status == "observed" else int(architecture.get("basis_pc_count", 0))
    if f3_status in {"not_run_by_f2_residual_gate", "not_run_by_f2_identity_gate", "not_run_by_f2_checkpoint_gate"}:
        expected_basis = 0
    if architecture.get("basis_pc_count") != expected_basis or architecture.get("basis_action_count") != expected_basis or architecture.get("retains_q") is not (f3_status in {"observed", "span_gate_failed"}) or architecture.get("retains_r") is not (f3_status in {"observed", "span_gate_failed"}):
        raise CheckError("parent F3 architecture does not close", "jit")
    command = _require(record, "command", "parent")
    repo = Path(__file__).resolve().parents[1]
    if not isinstance(command, list) or len(command) < 3 or Path(command[0]) != repo / ".venv/bin/python" or command[1:3] != ["-m", PARENT_MODULE]:
        raise CheckError("parent command identity mismatch")
    if _option(command, "--workflow") != "f2-f3-floquet-wave" or _option(command, "--source-sha") != source or _option(command, "--input") != str(input_path):
        raise CheckError("parent command provenance mismatch")


def _check_paths(record: dict[str, Any], record_argument: Path) -> dict[str, Path]:
    paths_value = _need_dict(record.get("paths"), "parent paths")
    names = (
        "artifact_root", "cache_dir", "marker_dir", "record", "process_samples",
        "marker_manifest", "children_dir", "solver_dir", "cache_manifests_dir",
        "diagnostic_record", "diagnostic_raw_dir", "checkpoint_dir",
    )
    paths = {name: _absolute(_require(paths_value, name, "parent paths"), f"paths.{name}") for name in names}
    root = paths["artifact_root"]
    if not root.is_dir() or paths["cache_dir"] != root / "jit_cache" or paths["marker_dir"] != root / "markers":
        raise CheckError("fresh parent layout mismatch")
    if paths["record"] != record_argument or paths["record"] != root / "parent_record.json":
        raise CheckError("parent record path is not artifact_root/parent_record.json")
    for name, path in paths.items():
        if name == "record":
            continue
        if name == "checkpoint_dir":
            if not path.is_dir():
                raise CheckError("checkpoint path is not an existing directory")
            continue
        if not path.is_relative_to(root) or not path.exists():
            raise CheckError(f"parent path is invalid: {name}")
    return paths


def _check_checkpoint_authority(checkpoint_dir: Path) -> None:
    manifest_path = checkpoint_dir / "manifest.json"
    if not manifest_path.is_file():
        raise CheckError("checkpoint manifest is missing", "checkpoint_authority")
    if _sha(manifest_path) != CHECKPOINT["manifest_sha256"]:
        raise CheckError("checkpoint manifest authority does not match", "checkpoint_authority")
    try:
        manifest_value = _read_json(manifest_path)
    except CheckError as error:
        raise CheckError("checkpoint manifest cannot be read", "checkpoint_authority") from error
    manifest = _need_dict(manifest_value, "checkpoint manifest", "checkpoint_authority")
    expected = {
        "schema": CHECKPOINT_SCHEMA,
        "iteration": CHECKPOINT["iteration"],
        "explicit_true_residual": CHECKPOINT["stored_explicit_true_residual"],
        "input_identity_sha256": CHECKPOINT["input_identity_sha256"],
        "operator_identity_sha256": CHECKPOINT["operator_identity_sha256"],
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT["source_sha"],
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise CheckError("checkpoint manifest identity does not match", "checkpoint_authority")
    ranks = manifest.get("ranks")
    if not isinstance(ranks, list) or len(ranks) != 1 or not isinstance(ranks[0], dict):
        raise CheckError("checkpoint rank authority is incomplete", "checkpoint_authority")
    rank = ranks[0]
    if rank.get("rank") != 0 or rank.get("ownership") != {
        "rank": 0,
        "ownership_range": [0, CHECKPOINT_GLOBAL_SIZE],
        "local_size": CHECKPOINT_LOCAL_SIZE,
        "global_size": CHECKPOINT_GLOBAL_SIZE,
    }:
        raise CheckError("checkpoint ownership authority does not match", "checkpoint_authority")
    descriptor = _need_dict(rank.get("solution"), "checkpoint solution descriptor", "checkpoint_authority")
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise CheckError("checkpoint solution path is invalid", "checkpoint_authority")
    shard_path = (checkpoint_dir / relative).resolve()
    if not shard_path.is_relative_to(checkpoint_dir) or not shard_path.is_file():
        raise CheckError("checkpoint solution shard is missing", "checkpoint_authority")
    if (
        descriptor.get("sha256") != CHECKPOINT["shard_sha256"]
        or descriptor.get("bytes") != CHECKPOINT_VECTOR_BYTES
        or descriptor.get("dtype") != CHECKPOINT_VECTOR_DTYPE
        or descriptor.get("shape") != CHECKPOINT_VECTOR_SHAPE
        or _sha(shard_path) != CHECKPOINT["shard_sha256"]
        or shard_path.stat().st_size != CHECKPOINT_VECTOR_BYTES
    ):
        raise CheckError("checkpoint solution descriptor does not match", "checkpoint_authority")
    try:
        values = np.load(shard_path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as error:
        raise CheckError(f"checkpoint solution cannot be read: {error}", "jit") from error
    try:
        if values.dtype != np.dtype(CHECKPOINT_VECTOR_DTYPE) or list(values.shape) != CHECKPOINT_VECTOR_SHAPE or values.ndim != 1:
            raise CheckError("checkpoint solution shape or dtype does not match", "checkpoint_authority")
    finally:
        mmap = getattr(values, "_mmap", None)
        if mmap is not None:
            mmap.close()


def _marker_name(path: Path) -> tuple[int, str]:
    match = re.fullmatch(r"(\d+)_([^/]+)\.json", path.name)
    if match is None:
        raise CheckError(f"invalid marker filename: {path.name}")
    return int(match.group(1)), match.group(2)


def _check_markers(record: dict[str, Any], paths: dict[str, Path]) -> list[str]:
    files = sorted(paths["marker_dir"].glob("*.json"), key=lambda path: _marker_name(path)[0])
    names = [_marker_name(path)[1] for path in files]
    residual_end = F2_MARKER_ORDER.index("residual_action_complete")
    complete_names = list(F2_MARKER_ORDER)
    short_names = list(F2_MARKER_ORDER[: residual_end + 1]) + ["release_started", "release_complete", "parent_complete"]
    identity_names = list(F2_MARKER_ORDER[: F2_MARKER_ORDER.index("source_built") + 1]) + ["release_started", "release_complete", "parent_complete"]
    checkpoint_names = list(F2_MARKER_ORDER[: F2_MARKER_ORDER.index("checkpoint_restore_started") + 1]) + ["release_started", "release_complete", "parent_complete"]
    span_names = list(F2_MARKER_ORDER[: F2_MARKER_ORDER.index("basis_complete") + 1]) + ["release_started", "release_complete", "parent_complete"]
    if names not in (complete_names, short_names, identity_names, checkpoint_names, span_names):
        raise CheckError("F2 marker sequence is not an allowed strict lifecycle", "process")
    root = str(paths["artifact_root"])
    cache = str(paths["cache_dir"])
    source = record["source_sha"]
    calculated: list[dict[str, Any]] = []
    previous_time = 0
    for path, name in zip(files, names):
        index, parsed_name = _marker_name(path)
        payload = _need_dict(_read_json(path), f"marker {name}")
        if index != F2_MARKER_ORDER.index(name) or parsed_name != name or payload.get("schema") != MARKER_SCHEMA or payload.get("name") != name or payload.get("marker_index") != index:
            raise CheckError(f"marker identity mismatch: {name}")
        timestamp = payload.get("timestamp_ns")
        if type(timestamp) is not int or timestamp <= previous_time:
            raise CheckError(f"marker timestamp mismatch: {name}")
        previous_time = timestamp
        facts = _need_dict(payload.get("facts"), f"marker {name}")
        if facts.get("artifact_root") != root or facts.get("cache_dir") != cache or facts.get("source_sha") != source:
            raise CheckError(f"marker common facts mismatch: {name}")
        if facts.get("watchdog_stop_bytes") != RSS_WATCHDOG:
            raise CheckError(f"marker watchdog limit mismatch: {name}", "resource")
        expected_stage = "f2-f3-floquet-wave-parent" if name in {"parent_started", "fresh_cache_created", "all_precompile_children_gone", "diagnostic_child_started", "parent_complete"} or F2_MARKER_ORDER.index(name) < F2_MARKER_ORDER.index("bundle_built") else "f2-f3-floquet-wave-diagnostic"
        if facts.get("stage") != expected_stage:
            raise CheckError(f"marker stage mismatch: {name}", "process")
        if expected_stage.endswith("diagnostic") and facts.get("mpi_size") != 1:
            raise CheckError(f"diagnostic marker MPI fact mismatch: {name}")
        if name == "parent_complete" and facts.get("compiler_descendant_count") != 0:
            raise CheckError("parent complete compiler fact is not zero", "resource")
        calculated.append({"name": name, "path": str(path), "sha256": _sha(path)})
    if _read_json(paths["marker_manifest"]) != calculated:
        raise CheckError("marker manifest does not close marker hashes")
    markers = _need_dict(record.get("markers"), "parent markers")
    if markers.get("names") != names or markers.get("manifest_path") != str(paths["marker_manifest"]) or markers.get("manifest_sha256") != _sha(paths["marker_manifest"]):
        raise CheckError("parent marker facts do not close")
    return names


def _check_sample(sample: Any, parent_pid: int) -> int:
    sample = _need_dict(sample, "process sample", "process")
    if sample.get("schema") != SAMPLE_SCHEMA or sample.get("root_pid") != parent_pid:
        raise CheckError("process sample identity mismatch", "process")
    if not isinstance(sample.get("stage"), str) or type(sample.get("timestamp_ns")) is not int:
        raise CheckError("process sample timestamp/stage invalid", "process")
    if sample.get("unreadable_pids") != [] or sample.get("all_status_readable") is not True:
        raise CheckError("process sample is unreadable", "resource")
    vanished = sample.get("vanished_pids")
    if not isinstance(vanished, list) or any(type(pid) is not int or pid <= 0 for pid in vanished) or len(vanished) != len(set(vanished)):
        raise CheckError("process vanished PID facts are invalid", "process")
    members = sample.get("members")
    if not isinstance(members, list) or not members:
        raise CheckError("process sample members are missing", "process")
    pids: list[int] = []
    for member in members:
        member = _need_dict(member, "process member", "process")
        required = ("pid", "ppid", "comm", "state", "cmdline", "stage", "rss_bytes", "pss_bytes", "swap_bytes", "timestamp_ns", "exit_code")
        if any(key not in member for key in required):
            raise CheckError("process member fields are incomplete", "process")
        if type(member["pid"]) is not int or member["pid"] <= 0 or type(member["ppid"]) is not int or member["ppid"] < 0:
            raise CheckError("process member PID facts are invalid", "process")
        if any(not isinstance(member[key], str) for key in ("comm", "state", "cmdline", "stage")):
            raise CheckError("process member text facts are invalid", "process")
        if type(member["rss_bytes"]) is not int or member["rss_bytes"] < 0 or type(member["swap_bytes"]) is not int or member["swap_bytes"] < 0 or (member["pss_bytes"] is not None and (type(member["pss_bytes"]) is not int or member["pss_bytes"] < 0)):
            raise CheckError("process member memory facts are invalid", "process")
        if type(member["timestamp_ns"]) is not int or member["timestamp_ns"] <= 0 or member["exit_code"] is not None:
            raise CheckError("process member lifecycle facts are invalid", "process")
        pids.append(member["pid"])
    if len(pids) != len(set(pids)) or parent_pid not in pids or set(vanished).intersection(pids):
        raise CheckError("process member PID set is invalid", "process")
    pss_ready = all(member["pss_bytes"] is not None for member in members)
    if sample.get("pss_all_readable") is not pss_ready:
        raise CheckError("process PSS readability mismatch", "process")
    rss = sample.get("rss_bytes")
    swap = sample.get("swap_bytes")
    if type(rss) is not int or type(swap) is not int or rss != sum(member["rss_bytes"] for member in members) or swap != sum(member["swap_bytes"] for member in members):
        raise CheckError("process RSS/swap aggregate mismatch", "process")
    pss = sample.get("pss_bytes")
    if pss != (sum(member["pss_bytes"] for member in members) if pss_ready else None):
        raise CheckError("process PSS aggregate mismatch", "process")
    compiler_count = sum(_compiler(member, parent_pid) for member in members)
    if sample.get("compiler_descendant_count") != compiler_count:
        raise CheckError("process compiler count mismatch", "process")
    if rss >= RSS_LIMIT or swap != 0:
        raise CheckError("process resource limit failed", "resource")
    return compiler_count


def _stage_update(stats: dict[str, dict[str, Any]], sample: dict[str, Any], compiler_count: int, parent_pid: int) -> None:
    stage = str(sample["stage"])
    timestamp = int(sample["timestamp_ns"])
    current = stats.setdefault(stage, {
        "sample_count": 0, "first_timestamp_ns": timestamp, "last_timestamp_ns": timestamp,
        "peak_rss_bytes": None, "max_swap_bytes": None, "all_status_readable": True,
        "compiler_descendant_peak": 0, "observed_descendant_pids": set(), "last_sample": None,
        "warning_crossed": False, "warning_sample_index": None, "warning_timestamp_ns": None,
    })
    current["sample_count"] += 1
    current["last_timestamp_ns"] = timestamp
    current["peak_rss_bytes"] = sample["rss_bytes"] if current["peak_rss_bytes"] is None else max(current["peak_rss_bytes"], sample["rss_bytes"])
    current["max_swap_bytes"] = sample["swap_bytes"] if current["max_swap_bytes"] is None else max(current["max_swap_bytes"], sample["swap_bytes"])
    current["all_status_readable"] = current["all_status_readable"] and sample["all_status_readable"] is True
    current["compiler_descendant_peak"] = max(current["compiler_descendant_peak"], compiler_count)
    current["observed_descendant_pids"].update(int(member["pid"]) for member in sample["members"] if int(member["pid"]) != parent_pid)
    current["last_sample"] = sample
    if not current["warning_crossed"] and sample.get("rss_bytes") >= RSS_WARNING:
        current["warning_crossed"] = True
        current["warning_sample_index"] = current["sample_count"]
        current["warning_timestamp_ns"] = timestamp


def _check_process(record: dict[str, Any], paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    process = _need_dict(record.get("process"), "parent process", "process")
    if process.get("stop_limit_bytes") != RSS_WATCHDOG:
        raise CheckError("F2/F3 process stop limit is not 1.95GB", "resource")
    if process.get("warning_limit_bytes") != RSS_WARNING:
        raise CheckError("F2/F3 process warning fact does not close", "resource")
    sample_path = _absolute(_require(process, "sample_path", "parent process"), "process.sample_path")
    if sample_path != paths["process_samples"] or not sample_path.is_file() or process.get("sample_sha256") != _sha(sample_path):
        raise CheckError("parent process sample path/hash mismatch", "process")
    parent_pid = _require(process, "parent_pid", "parent process", "process")
    if type(parent_pid) is not int or parent_pid <= 0:
        raise CheckError("parent PID is invalid", "process")
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
    warning_crossed = False
    warning_sample_index: int | None = None
    warning_timestamp_ns: int | None = None
    with sample_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            sample = _need_dict(json.loads(line), "process sample", "process")
            compiler_count = _check_sample(sample, parent_pid)
            timestamp = int(sample["timestamp_ns"])
            if last is not None and timestamp <= last:
                raise CheckError("process sample timestamps are not increasing", "process")
            count += 1
            first = timestamp if first is None else first
            last = timestamp
            peak = sample["rss_bytes"] if peak is None else max(peak, sample["rss_bytes"])
            max_swap = sample["swap_bytes"] if max_swap is None else max(max_swap, sample["swap_bytes"])
            if not warning_crossed and sample["rss_bytes"] >= RSS_WARNING:
                warning_crossed = True
                warning_sample_index = count
                warning_timestamp_ns = timestamp
            compiler_peak = max(compiler_peak, compiler_count)
            all_readable = all_readable and sample["all_status_readable"] is True
            observed.update(int(member["pid"]) for member in sample["members"] if int(member["pid"]) != parent_pid)
            _stage_update(stats, sample, compiler_count, parent_pid)
            last_sample = sample
    if count == 0 or process.get("sample_count") != count or process.get("first_timestamp_ns") != first or process.get("last_timestamp_ns") != last or process.get("all_status_readable") is not all_readable or process.get("peak_rss_bytes") != peak or process.get("max_swap_bytes") != max_swap or process.get("compiler_descendant_peak") != compiler_peak or process.get("observed_descendant_pids") != sorted(observed) or process.get("last_sample") != last_sample or process.get("warning_crossed") is not warning_crossed or process.get("warning_sample_index") != warning_sample_index or process.get("warning_timestamp_ns") != warning_timestamp_ns or process.get("resource_warning") is not warning_crossed:
        raise CheckError("parent process global summary does not close", "process")
    if peak is not None and peak >= RSS_WATCHDOG:
        raise CheckError("F2/F3 process reached watchdog limit", "resource")
    if set(stats) != set(PROCESS_STAGES):
        raise CheckError("parent process stage inventory mismatch", "process")
    reported = _need_dict(process.get("stage_summaries"), "parent stage summaries", "process")
    if set(reported) != set(stats):
        raise CheckError("parent stage summary inventory mismatch", "process")
    for stage, current in stats.items():
        current["observed_descendant_pids"] = sorted(current["observed_descendant_pids"])
        reported_stage = _need_dict(reported.get(stage), f"stage {stage}", "process")
        for key in ("sample_count", "first_timestamp_ns", "last_timestamp_ns", "peak_rss_bytes", "max_swap_bytes", "all_status_readable", "compiler_descendant_peak", "observed_descendant_pids", "last_sample", "warning_crossed", "warning_sample_index", "warning_timestamp_ns"):
            if reported_stage.get(key) != current[key]:
                raise CheckError(f"stage summary mismatch: {stage}:{key}", "process")
        if stage in {"precompile:parent-only", "diagnostic"} and current["compiler_descendant_peak"] != 0:
            raise CheckError(f"compiler descendant seen in {stage}", "resource")
        if stage == "precompile:parent-only" and current["observed_descendant_pids"]:
            raise CheckError("parent-only stage observed descendants", "process")
    return stats


def _check_monitor(monitor: Any, stage: dict[str, Any], expected_pid: int, label: str) -> None:
    monitor = _need_dict(monitor, f"{label} monitor", "process")
    if monitor.get("pid") != expected_pid:
        raise CheckError(f"{label} monitor PID mismatch", "process")
    if monitor.get("stop_limit_bytes") != RSS_WATCHDOG:
        raise CheckError(f"{label} monitor stop limit mismatch", "resource")
    if monitor.get("warning_limit_bytes") != RSS_WARNING:
        raise CheckError(f"{label} monitor warning fact mismatch", "resource")
    for key, stage_key in (("sample_count", "sample_count"), ("started_ns", "first_timestamp_ns"), ("ended_ns", "last_timestamp_ns"), ("peak_rss_bytes", "peak_rss_bytes"), ("max_swap_bytes", "max_swap_bytes"), ("all_status_readable", "all_status_readable"), ("compiler_descendant_peak", "compiler_descendant_peak"), ("observed_descendant_pids", "observed_descendant_pids"), ("warning_crossed", "warning_crossed"), ("warning_sample_index", "warning_sample_index"), ("warning_timestamp_ns", "warning_timestamp_ns")):
        if monitor.get(key) != stage.get(stage_key):
            raise CheckError(f"{label} monitor/{stage_key} mismatch", "process")
    if monitor.get("resource_warning") is not (monitor.get("peak_rss_bytes") is not None and monitor.get("peak_rss_bytes") >= RSS_WARNING) or monitor.get("process_group_gone") is not True or monitor.get("required_sigkill") is not False or monitor.get("natural_exit") is not True or monitor.get("returncode") != 0 or expected_pid not in monitor["observed_descendant_pids"]:
        raise CheckError(f"{label} process did not close naturally", "process")
    if monitor["max_swap_bytes"] != 0 or monitor["peak_rss_bytes"] >= RSS_WATCHDOG:
        raise CheckError(f"{label} resource gate failed", "resource")


def _manifest(path: Path, cache_dir: Path) -> dict[str, Any]:
    value = _need_dict(_read_json(path), f"cache manifest {path}", "jit")
    if value.get("cache_dir") != str(cache_dir):
        raise CheckError(f"cache manifest directory mismatch: {path}", "jit")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or value.get("artifact_count") != len(artifacts):
        raise CheckError(f"cache manifest count mismatch: {path}", "jit")
    for item in artifacts:
        item = _need_dict(item, "cache artifact", "jit")
        if set(item) != {"relative_path", "bytes", "sha256"}:
            raise CheckError(f"cache artifact fields mismatch: {path}", "jit")
        relative = item["relative_path"]
        relative_path = Path(relative) if isinstance(relative, str) else Path("/")
        if not isinstance(relative, str) or relative_path.is_absolute() or ".." in relative_path.parts or relative_path.suffix not in {".c", ".o", ".so"}:
            raise CheckError(f"cache artifact path invalid: {relative}", "jit")
        target = cache_dir / relative
        if not target.is_file() or type(item["bytes"]) is not int or target.stat().st_size != item["bytes"] or _sha(target) != item["sha256"]:
            raise CheckError(f"cache artifact hash mismatch: {relative}", "jit")
    return value


def _manifest_body(entry: Any, label: str, cache_dir: Path, manifests_dir: Path) -> tuple[Path, dict[str, Any]]:
    entry = _need_dict(entry, label, "jit")
    path = _absolute(_require(entry, "path", label, "jit"), f"{label}.path")
    if not path.is_relative_to(manifests_dir) or not path.is_file() or entry.get("sha256") != _sha(path):
        raise CheckError(f"{label} path/hash mismatch", "jit")
    body = _manifest(path, cache_dir)
    if entry.get("artifact_count") != body["artifact_count"]:
        raise CheckError(f"{label} artifact count mismatch", "jit")
    return path, body


def _check_cache(record: dict[str, Any], paths: dict[str, Path]) -> tuple[set[str], set[str]]:
    cache = _need_dict(record.get("cache"), "parent cache", "jit")
    if cache.get("initial_empty") is not True:
        raise CheckError("fresh cache is not marked empty", "jit")
    _initial_path, previous = _manifest_body(_require(cache, "initial_manifest", "parent cache", "jit"), "initial manifest", paths["cache_dir"], paths["cache_manifests_dir"])
    if previous["artifacts"] or previous["artifact_count"] != 0:
        raise CheckError("initial cache is not empty", "jit")
    group_entries = _require(cache, "group_manifests", "parent cache", "jit")
    if not isinstance(group_entries, list) or len(group_entries) != len(GROUPS):
        raise CheckError("cache group manifest count mismatch", "jit")
    children = _require(record, "children", "parent", "jit")
    if not isinstance(children, list) or len(children) != len(GROUPS):
        raise CheckError("cache child count mismatch", "jit")
    all_modules: set[str] = set()
    incident_modules: set[str] = set()
    for entry, child, group in zip(group_entries, children, GROUPS):
        entry = _need_dict(entry, f"cache group {group}", "jit")
        if entry.get("group") != group:
            raise CheckError(f"cache group order mismatch: {group}", "jit")
        _path, current = _manifest_body(entry, f"cache manifest {group}", paths["cache_dir"], paths["cache_manifests_dir"])
        old_by_path = {item["relative_path"]: item for item in previous["artifacts"]}
        new_by_path = {item["relative_path"]: item for item in current["artifacts"]}
        if any(path not in new_by_path or new_by_path[path]["sha256"] != item["sha256"] or new_by_path[path]["bytes"] != item["bytes"] for path, item in old_by_path.items()):
            raise CheckError(f"cache is not monotonic after {group}", "jit")
        added = [item for item in current["artifacts"] if item["relative_path"] not in old_by_path]
        if added != child.get("added_artifacts") or entry.get("artifact_count") != current["artifact_count"]:
            raise CheckError(f"cache delta mismatch after {group}", "jit")
        modules = sorted(Path(item["relative_path"]).name for item in added if item["relative_path"].endswith(".so"))
        expected_count, _roles = GROUP_ROLES[group]
        if len(modules) != expected_count or entry.get("new_module_basenames") != modules or child.get("new_module_basenames") != modules:
            raise CheckError(f"cache module count mismatch after {group}", "jit")
        all_modules.update(modules)
        if group == "incident-rhs":
            incident_modules.update(modules)
        previous = current
    if len(all_modules) != 11 or len(incident_modules) != 1:
        raise CheckError("precompile cache does not contain exact 11 modules", "jit")
    if cache.get("precompiled_module_basenames") != sorted(all_modules) or cache.get("deferred_incident_module_basenames") != []:
        raise CheckError("precompile module inventory mismatch", "jit")
    before_path, before = _manifest_body(_require(cache, "before_solver", "parent cache", "jit"), "before-solver manifest", paths["cache_dir"], paths["cache_manifests_dir"])
    after_path, after = _manifest_body(_require(cache, "after_diagnostic", "parent cache", "jit"), "after-diagnostic manifest", paths["cache_dir"], paths["cache_manifests_dir"])
    if before != previous or after != before or before_path.read_bytes() != after_path.read_bytes() or cache.get("solver_unchanged") is not True:
        raise CheckError("diagnostic changed the cache", "jit")
    return all_modules, incident_modules


def _check_child_record(child: dict[str, Any], group: str, source: str, cache_dir: Path, input_path: Path) -> None:
    path = _absolute(_require(child, "record_path", f"child {group}"), f"child {group}.record_path")
    if not path.is_file() or child.get("record_sha256") != _sha(path):
        raise CheckError(f"child record/hash missing: {group}", "jit")
    payload = _need_dict(_read_json(path), f"child {group} record", "jit")
    if payload.get("schema") != "task038.full3d.jit-split.child-record.v1" or payload.get("stage") != "j3-split-precompile-child" or payload.get("group") != group or payload.get("source_sha") != source or payload.get("branch") != BRANCH or payload.get("raw_facts_only") is not True:
        raise CheckError(f"child identity mismatch: {group}")
    if any(key in payload for key in ("passed", "classification")):
        raise CheckError(f"child contains checker decision: {group}")
    command = _require(payload, "command", f"child {group}")
    repo = Path(__file__).resolve().parents[1]
    if not isinstance(command, list) or len(command) < 3 or Path(command[0]) != repo / ".venv/bin/python" or command[1:3] != ["-m", "benchmarks.run_task038_full3d_jit_precompile"]:
        raise CheckError(f"child command mismatch: {group}")
    if _option(command, "--group") != group or _option(command, "--cache-dir") != str(cache_dir) or _option(command, "--record") != str(path) or _option(command, "--input") != str(input_path) or _option(command, "--expected-source-sha") != source:
        raise CheckError(f"child command provenance mismatch: {group}")
    identity = _need_dict(payload.get("input"), f"child {group} input")
    if identity.get("path") != str(input_path) or identity.get("input_sha256") != INPUT_SHA256 or identity.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256 or identity.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256 or identity.get("profile") != PROFILE:
        raise CheckError(f"child profile mismatch: {group}")
    _check_worker_runtime(payload.get("runtime"), source)
    facts = _need_dict(payload.get("facts"), f"child {group} facts")
    group_facts = _need_dict(facts.get("group_facts"), f"child {group} group facts")
    count, roles = GROUP_ROLES[group]
    if group_facts.get("compiled_form_count") != count or tuple(group_facts.get("form_roles", ())) != roles:
        raise CheckError(f"child form inventory mismatch: {group}", "jit")
    architecture = _need_dict(payload.get("architecture"), f"child {group} architecture")
    for key in ("matrix", "factor", "pc", "rhs_vector", "surface_carrier", "dtn_carrier", "solve", "recovery", "pde"):
        if architecture.get(key) is not False:
            raise CheckError(f"child forbidden object fact is true: {group}:{key}", "jit")
    if architecture.get("compile") is not True or architecture.get("mesh") is not True or architecture.get("jit") is not True:
        raise CheckError(f"child compile facts mismatch: {group}", "jit")
    for key in ("stdout_path", "stderr_path"):
        output_path = _absolute(_require(child, key, f"child {group}"), f"child {group}.{key}")
        digest_key = key.replace("_path", "_sha256")
        if not output_path.is_file() or child.get(digest_key) != _sha(output_path):
            raise CheckError(f"child output hash mismatch: {group}", "process")


def _field_facts(value: Any, label: str, *, observed: bool = True) -> dict[str, Any]:
    facts = _need_dict(value, label, "numerical")
    required = ("array_sha256", "finite", "norm", "owned_slave_max")
    if any(key not in facts for key in required):
        raise CheckError(f"{label} facts are incomplete", "numerical")
    if observed:
        if not isinstance(facts["array_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", facts["array_sha256"]):
            raise CheckError(f"{label} array hash is invalid", "numerical")
        if type(facts["finite"]) is not bool:
            raise CheckError(f"{label} finite fact is invalid", "numerical")
        for key in ("norm", "owned_slave_max"):
            item = facts[key]
            if facts["finite"]:
                if type(item) not in (int, float) or not np.isfinite(float(item)) or float(item) < 0.0:
                    raise CheckError(f"{label} {key} is invalid", "numerical")
            elif item is not None:
                raise CheckError(f"{label} non-finite {key} is not null", "numerical")
    elif facts != {"observed": False, "array_sha256": None, "finite": None, "norm": None, "owned_slave_max": None}:
        raise CheckError(f"{label} unobserved facts are not explicit", "numerical")
    return facts


def _check_worker(record: dict[str, Any], paths: dict[str, Path], source: str, modules: set[str], stage_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    info = _need_dict(record.get("diagnostic"), "parent diagnostic", "jit")
    worker_path = _absolute(_require(info, "record_path", "parent diagnostic"), "diagnostic.record_path")
    if not worker_path.is_file() or info.get("record_sha256") != _sha(worker_path):
        raise CheckError("diagnostic worker record/hash is missing", "jit")
    payload = _need_dict(_read_json(worker_path), "diagnostic worker record", "jit")
    if payload.get("schema") != WORKER_SCHEMA or payload.get("stage") != "f2-f3-floquet-wave-diagnostic" or payload.get("workflow") != "f2-f3-floquet-wave" or payload.get("source_sha") != source or payload.get("branch") != BRANCH or payload.get("raw_facts_only") is not True:
        raise CheckError("diagnostic worker identity mismatch")
    if any(key in payload for key in ("passed", "classification")):
        raise CheckError("diagnostic worker contains checker decision")
    command = _require(payload, "command", "diagnostic worker")
    repo = Path(__file__).resolve().parents[1]
    if not isinstance(command, list) or len(command) < 3 or Path(command[0]) != repo / ".venv/bin/python" or command[1:3] != ["-m", WORKER_MODULE]:
        raise CheckError("diagnostic worker command mismatch")
    input_path = _absolute(_require(record["identity"], "input_path", "parent identity"), "input_path")
    for name, expected in (("--artifact-root", paths["artifact_root"]), ("--cache-dir", paths["cache_dir"]), ("--marker-dir", paths["marker_dir"]), ("--record", worker_path), ("--input", input_path)):
        if _option(command, name) != str(expected):
            raise CheckError(f"diagnostic worker command mismatch: {name}")
    if _option(command, "--checkpoint-dir") != str(paths["checkpoint_dir"]) or _option(command, "--expected-source-sha") != source or _option(command, "--expected-mpi-size") != "1":
        raise CheckError("diagnostic worker command identity mismatch")
    worker_paths = _need_dict(payload.get("paths"), "diagnostic worker paths")
    exact_paths = {"artifact_root": paths["artifact_root"], "cache_dir": paths["cache_dir"], "marker_dir": paths["marker_dir"], "raw_dir": paths["diagnostic_raw_dir"], "record": worker_path, "checkpoint_dir": paths["checkpoint_dir"]}
    for key, expected in exact_paths.items():
        if _absolute(_require(worker_paths, key, "diagnostic worker paths"), f"worker paths.{key}") != expected:
            raise CheckError(f"diagnostic worker path mismatch: {key}")
    _check_worker_runtime(payload.get("provenance"), source)
    identity = _need_dict(payload.get("identity"), "diagnostic identity")
    if identity.get("input_file_sha256") != INPUT_SHA256 or identity.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256 or identity.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256 or identity.get("profile") != WORKER_PROFILE or identity.get("checkpoint_input_identity_sha256") != CHECKPOINT["input_identity_sha256"] or identity.get("checkpoint_operator_identity_sha256") != CHECKPOINT["operator_identity_sha256"]:
        raise CheckError("diagnostic identity mismatch")
    observed_identity_failures = []
    for key in ("input_identity_sha256", "operator_identity_sha256"):
        value = _require(identity, key, "diagnostic identity", "numerical")
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise CheckError(f"diagnostic identity {key} is invalid", "numerical")
        if value != CHECKPOINT[key]:
            observed_identity_failures.append(f"{key} does not match checkpoint authority")
    _check_checkpoint_authority(paths["checkpoint_dir"])
    checkpoint = _need_dict(payload.get("checkpoint"), "diagnostic checkpoint")
    if checkpoint != {**CHECKPOINT, "solution_only": True}:
        raise CheckError("checkpoint authority mismatch", "jit")
    mode = _need_dict(payload.get("mode"), "diagnostic mode")
    if mode.get("count") != 80 or mode.get("manifest_sha256") != MODE_MANIFEST_SHA256 or mode.get("selector_schema") != SELECTOR_SCHEMA or mode.get("selector_payload_sha256") != SELECTOR_SHA256 or mode.get("selected_mode_indices") != list(SELECTED_MODE_INDICES):
        raise CheckError("dynamic mode/selector identity mismatch", "jit")
    ffcx_calls = _require(payload, "ffcx_calls", "diagnostic worker")
    if not isinstance(ffcx_calls, list) or len(ffcx_calls) != 11 or payload.get("expected_ffcx_call_count") != 11:
        raise CheckError("diagnostic FFCx call count mismatch", "jit")
    observed_modules: set[str] = set()
    for call in ffcx_calls:
        call = _need_dict(call, "FFCx call", "jit")
        if call.get("code") != [None, None] or call.get("cache_hit") is not True or not isinstance(call.get("module_name"), str) or not call["module_name"]:
            raise CheckError("diagnostic FFCx call is not an exact cache hit", "jit")
        module_file = _absolute(_require(call, "module_file", "FFCx call"), "FFCx module_file")
        if module_file.suffix != ".so" or not module_file.is_file() or not module_file.is_relative_to(paths["cache_dir"]):
            raise CheckError("diagnostic FFCx module is outside cache", "jit")
        observed_modules.add(module_file.name)
    if observed_modules != modules:
        raise CheckError("diagnostic FFCx module set does not match precompile cache", "jit")
    source = _need_dict(payload.get("source"), "diagnostic source")
    source_before = _field_facts(_require(source, "before", "diagnostic source"), "diagnostic source before")
    source_norm = source_before["norm"]
    if source_norm is None or float(source_norm) <= 0.0 or source_before["finite"] is not True or source_before["owned_slave_max"] != 0.0:
        source_failures = ["source finite/slave/norm Gate failed"]
    else:
        source_failures = []
    f2 = _need_dict(payload.get("f2"), "F2 facts")
    f2_status = _require(f2, "status", "F2 facts")
    if f2_status not in {"observed", "identity_gate_failed", "checkpoint_restore_failed"}:
        raise CheckError("F2 status is invalid")
    for key in ("stored_true_residual", "recomputed_true_residual", "relative_difference", "owned_slave_max"):
        if key not in f2:
            raise CheckError(f"F2 fact is missing: {key}")
        if f2[key] is not None and (type(f2[key]) not in (int, float) or not np.isfinite(float(f2[key]))):
            raise CheckError(f"F2 fact is invalid: {key}")
    for key in ("identity_gate_passed", "finite", "rhs_input_unchanged", "solution_input_unchanged", "solution_finite", "residual_action_finite"):
        if key not in f2 or f2[key] is not None and type(f2[key]) is not bool:
            raise CheckError(f"F2 boolean fact is invalid: {key}")
    residual_action_count = _require(f2, "residual_action_count", "F2 facts")
    if type(residual_action_count) is not int or residual_action_count not in {0, 1}:
        raise CheckError("F2 action count is invalid")
    if residual_action_count != (0 if f2_status in {"identity_gate_failed", "checkpoint_restore_failed"} else 1):
        raise CheckError("F2 action count does not match lifecycle status", "process")
    if f2_status == "checkpoint_restore_failed":
        if (
            f2.get("identity_gate_passed") is not True
            or f2.get("identity_failures") != []
            or residual_action_count != 0
        ):
            raise CheckError("checkpoint reader failure facts are not closed")
        f3 = _need_dict(payload.get("f3"), "F3 facts")
        if f3.get("status") != "not_run_by_f2_checkpoint_gate":
            raise CheckError("checkpoint reader failure did not stop F3")
        if worker_paths.get("vectors") is not None:
            raise CheckError("checkpoint reader failure unexpectedly wrote vectors")
        raise CheckError("checkpoint reader failed after matching checkpoint authority")
    if f2_status == "identity_gate_failed":
        if not observed_identity_failures or f2.get("identity_gate_passed") is not False or f2.get("identity_failures") != observed_identity_failures:
            raise CheckError("F2 identity hard stop facts are incomplete", "numerical")
        for key in ("checkpoint_solution_before", "checkpoint_solution_after", "exact_action_output", "residual"):
            _field_facts(_require(f2, key, "F2 facts"), f"F2 {key}", observed=False)
        _field_facts(_require(f2, "rhs_before", "F2 facts"), "F2 RHS before")
        _field_facts(_require(f2, "rhs_after", "F2 facts"), "F2 RHS after")
        if worker_paths.get("vectors") is not None:
            raise CheckError("identity hard stop unexpectedly wrote vectors", "process")
        f3 = _need_dict(payload.get("f3"), "F3 facts")
        if f3.get("status") != "not_run_by_f2_identity_gate":
            raise CheckError("F3 identity hard stop status mismatch", "process")
        return {"f2_passed": False, "f2_failures": list(f2["identity_failures"]), "f3_status": f3["status"], "identity_gate": True, "residual_norm": None}
    if f2.get("identity_gate_passed") is not True or observed_identity_failures or f2.get("identity_failures") != []:
        raise CheckError("observed F2 identity gate does not close", "numerical")
    checkpoint_result = _need_dict(_require(f2, "checkpoint", "F2 facts"), "F2 checkpoint", "numerical")
    expected_checkpoint_result = {
        "manifest_sha256": CHECKPOINT["manifest_sha256"],
        "iteration": CHECKPOINT["iteration"],
        "explicit_true_residual": CHECKPOINT["stored_explicit_true_residual"],
        "rank": 0,
        "restored_shard_sha256": CHECKPOINT["shard_sha256"],
    }
    if set(checkpoint_result) != set(expected_checkpoint_result) or any(checkpoint_result.get(key) != value for key, value in expected_checkpoint_result.items()):
        raise CheckError("F2 checkpoint reader result does not close", "numerical")
    source_after = _field_facts(_require(source, "after", "diagnostic source"), "diagnostic source after")
    for key in ("rhs_before", "rhs_after", "checkpoint_solution_before", "checkpoint_solution_after", "exact_action_output", "residual"):
        _field_facts(_require(f2, key, "F2 facts"), f"F2 {key}")
    rhs_before = f2["rhs_before"]
    rhs_after = f2["rhs_after"]
    solution_before = f2["checkpoint_solution_before"]
    solution_after = f2["checkpoint_solution_after"]
    action_output = f2["exact_action_output"]
    residual_facts = f2["residual"]
    source_unchanged = _require(source, "input_unchanged", "diagnostic source", "numerical")
    if type(source_unchanged) is not bool:
        raise CheckError("diagnostic source input fact is invalid", "numerical")
    if rhs_before != source_before or source_after != rhs_after or source_unchanged is not (rhs_before["array_sha256"] == rhs_after["array_sha256"]):
        raise CheckError("source/RHS facts do not close", "numerical")
    f3 = _need_dict(payload.get("f3"), "F3 facts")
    f3_status = _require(f3, "status", "F3 facts")
    if f3_status not in {"observed", "not_run_by_f2_residual_gate", "span_gate_failed"}:
        raise CheckError("F3 status is invalid")
    architecture = _need_dict(payload.get("architecture"), "diagnostic architecture")
    expected_worker_architecture = dict(EXPECTED_ARCHITECTURE)
    expected_worker_architecture["checkpoint_read"] = True
    expected_worker_architecture["residual_action_count"] = f2["residual_action_count"]
    expected_worker_architecture.update({"basis_pc_count": int(f3.get("pc_apply_count", 0)), "basis_action_count": int(f3.get("exact_action_count", 0)), "retains_q": f3_status in {"observed", "span_gate_failed"}, "retains_r": f3_status in {"observed", "span_gate_failed"}})
    if f3_status == "not_run_by_f2_residual_gate":
        expected_worker_architecture.update({"basis_pc_count": 0, "basis_action_count": 0, "retains_q": False, "retains_r": False})
    if architecture != expected_worker_architecture:
        raise CheckError("diagnostic architecture facts mismatch", "jit")
    lifecycle = _need_dict(payload.get("lifecycle"), "diagnostic lifecycle")
    lifecycle_names = list(F2_MARKER_ORDER[20:26])
    if f3_status == "span_gate_failed":
        lifecycle_names += ["basis_started", "basis_complete"]
    elif f3_status == "observed":
        lifecycle_names += list(F2_MARKER_ORDER[26:30])
    lifecycle_names += list(F2_MARKER_ORDER[30:32])
    if lifecycle.get("marker_schema") != MARKER_SCHEMA or lifecycle.get("marker_names") != lifecycle_names:
        raise CheckError("diagnostic lifecycle marker facts mismatch", "process")
    vectors = worker_paths.get("vectors")
    if not isinstance(vectors, dict):
        raise CheckError("diagnostic vector artifact is missing", "contract")
    vector_path = _absolute(_require(vectors, "path", "diagnostic vectors"), "diagnostic vector path")
    if not vector_path.is_file() or not vector_path.is_relative_to(paths["diagnostic_raw_dir"]) or vectors.get("sha256") != _sha(vector_path) or vectors.get("bytes") != vector_path.stat().st_size:
        raise CheckError("diagnostic vector artifact path/hash mismatch")
    try:
        with np.load(vector_path, allow_pickle=False) as arrays:
            role_order = ("residual",) if f3_status == "not_run_by_f2_residual_gate" else ("q", "r_factor", "residual") if f3_status == "span_gate_failed" else ("q", "r_factor", "residual", "coefficients", "projected", "perpendicular")
            if arrays.files != list(role_order) or vectors.get("roles") != list(role_order):
                raise CheckError("diagnostic vector roles are invalid")
            if any(arrays[name].dtype != np.dtype("complex128") for name in arrays.files):
                raise CheckError("diagnostic vector dtype is not complex128")
            values = {name: np.array(arrays[name], dtype=np.complex128, copy=True) for name in arrays.files}
    except (OSError, ValueError) as error:
        if isinstance(error, CheckError):
            raise
        raise CheckError(f"cannot read diagnostic vector artifact: {error}") from error
    residual = values["residual"]
    residual_finite = residual.ndim == 1 and bool(np.all(np.isfinite(residual)))
    if residual.ndim != 1:
        raise CheckError("F2 residual vector shape is invalid", "numerical")
    residual_hash_matches = residual_facts["array_sha256"] == _array_sha(residual)
    source_norm_valid = source_before["finite"] is True and isinstance(source_norm, (int, float)) and np.isfinite(float(source_norm)) and float(source_norm) > 0.0
    recomputed_true_residual = float(np.linalg.norm(residual) / float(source_norm)) if residual_finite and source_norm_valid else None
    stored_true_residual = f2["stored_true_residual"]
    expected_difference = abs(recomputed_true_residual - stored_true_residual) / max(abs(stored_true_residual), np.finfo(float).tiny) if recomputed_true_residual is not None and stored_true_residual is not None else None
    f2_failures = list(source_failures)
    if not residual_hash_matches:
        f2_failures.append("F2 residual hash does not close against NPZ")
    for label, facts in (
        ("source before", source_before),
        ("source after", source_after),
        ("RHS before", rhs_before),
        ("RHS after", rhs_after),
        ("checkpoint solution before", solution_before),
        ("checkpoint solution after", solution_after),
        ("exact action output", action_output),
        ("residual", residual_facts),
    ):
        if facts["finite"] is not True:
            f2_failures.append(f"{label} is non-finite")
        if facts["owned_slave_max"] != 0.0:
            f2_failures.append(f"{label} owned slave is nonzero")
    if stored_true_residual != CHECKPOINT["stored_explicit_true_residual"]:
        f2_failures.append("stored residual does not match checkpoint")
    if f2["recomputed_true_residual"] != recomputed_true_residual and (f2["recomputed_true_residual"] is None or recomputed_true_residual is None or abs(float(f2["recomputed_true_residual"]) - recomputed_true_residual) > F2_LIMIT):
        f2_failures.append("recomputed residual does not close against residual vector")
    if f2["relative_difference"] != expected_difference and (f2["relative_difference"] is None or expected_difference is None or abs(float(f2["relative_difference"]) - expected_difference) > F2_LIMIT):
        f2_failures.append("relative residual difference does not close")
    if expected_difference is None or expected_difference > F2_LIMIT:
        f2_failures.append("relative residual difference exceeds gate")
    if f2["finite"] is not residual_finite or residual_facts["finite"] is not residual_finite:
        f2_failures.append("residual finite fact does not close")
    if f2["rhs_input_unchanged"] is not (rhs_before["array_sha256"] == rhs_after["array_sha256"]):
        f2_failures.append("RHS input fact does not close")
    if f2["solution_input_unchanged"] is not (solution_before["array_sha256"] == solution_after["array_sha256"]):
        f2_failures.append("solution input fact does not close")
    if f2["solution_finite"] is not solution_after["finite"] or f2["residual_action_finite"] is not action_output["finite"]:
        f2_failures.append("F2 finite facts do not close")
    if f2["owned_slave_max"] != solution_before["owned_slave_max"] or solution_before["owned_slave_max"] != 0.0:
        f2_failures.append("F2 owned-slave facts failed")
    if f2["residual_action_count"] != 1:
        f2_failures.append("residual action count is not one")
    if f3_status == "not_run_by_f2_residual_gate":
        if not f2_failures:
            raise CheckError("F3 was skipped despite a passing F2", "process")
        return {"f2_passed": False, "f2_failures": f2_failures, "f3_status": f3_status, "residual_norm": float(np.linalg.norm(residual)) if residual_finite else None}
    if f2_failures:
        raise CheckError("F2 failed but F3 was observed", "process")
    base_metrics = {"f2_passed": True, "f2_failures": [], "f3_status": f3_status, "pc_apply_count": f3.get("pc_apply_count"), "exact_action_count": f3.get("exact_action_count"), "rank": f3.get("rank")}
    selector = _need_dict(_require(f3, "selector", "F3 facts"), "F3 selector", "jit")
    if selector.get("schema") != SELECTOR_SCHEMA or selector.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256 or selector.get("selected_mode_indices") != list(SELECTED_MODE_INDICES) or selector.get("selected_rank") != RANK or selector.get("selector_payload_sha256") != SELECTOR_SHA256:
        raise CheckError("F3 selector mismatch", "jit")
    if f3_status == "span_gate_failed":
        rank = _require(f3, "rank", "F3 facts", "span")
        if type(rank) is not int or not 0 <= rank < RANK or f3.get("accepted_rank") != rank:
            raise CheckError("F3 partial rank is invalid", "span", base_metrics)
        failed = _need_dict(_require(f3, "failed_column", "F3 facts", "span"), "F3 failed column", "span")
        counts = {
            key: _require(f3, key, "F3 facts", "span")
            for key in ("pc_apply_count", "exact_action_count", "modal_rhs_apply_count")
        }
        failed_counts = {
            key: _require(failed, key, "F3 failed column", "span")
            for key in counts
        }
        if (
            type(counts["modal_rhs_apply_count"]) is not int
            or counts["modal_rhs_apply_count"] != rank + 1
            or failed_counts["modal_rhs_apply_count"] != rank + 1
            or type(counts["pc_apply_count"]) is not int
            or type(counts["exact_action_count"]) is not int
            or counts["pc_apply_count"] != counts["exact_action_count"]
            or counts["pc_apply_count"] not in {rank, rank + 1}
            or failed_counts["pc_apply_count"] != counts["pc_apply_count"]
            or failed_counts["exact_action_count"] != counts["exact_action_count"]
        ):
            raise CheckError("F3 partial count mismatch", "span", base_metrics)
        columns = _require(f3, "column_facts", "F3 facts", "span")
        if not isinstance(columns, list) or len(columns) != rank:
            raise CheckError("F3 partial column facts mismatch", "span", base_metrics)
        if failed.get("column_index") != rank or failed.get("mode_index") != SELECTED_MODE_INDICES[rank]:
            raise CheckError("F3 failed column identity mismatch", "span", base_metrics)
        q = values["q"]
        r_factor = values["r_factor"]
        if q.ndim != 2 or q.shape[1] != rank or r_factor.shape != (rank, rank) or not np.all(np.isfinite(q)) or not np.all(np.isfinite(r_factor)):
            raise CheckError("F3 partial Q/R artifact is invalid", "span", base_metrics)
        reconstruction_max = None
        for column_index, (expected_mode, column) in enumerate(zip(SELECTED_MODE_INDICES, columns)):
            column = _need_dict(column, "F3 partial column", "span")
            if column.get("mode_index") != expected_mode or column.get("modal_input_unchanged") is not True or column.get("pc_input_unchanged") is not True or column.get("action_input_unchanged") is not True:
                raise CheckError("F3 partial column input facts failed", "span", base_metrics)
            for role in ("modal_rhs", "pc_output", "action_output"):
                output = _field_facts(column.get(role), f"F3 partial {role}", observed=True)
                if output["finite"] is not True or output["owned_slave_max"] != 0.0:
                    raise CheckError(f"F3 partial {role} slave/finite fact failed", "span", base_metrics)
                if role == "modal_rhs" and (output["norm"] is None or abs(float(output["norm"]) - 1.0) > REPEAT_LIMIT):
                    raise CheckError("F3 partial modal RHS normalization failed", "span", base_metrics)
            for key in ("r_diagonal_abs", "qr_reconstruction_numerator", "qr_reconstruction_denominator", "qr_reconstruction_relative"):
                value = _require(column, key, "F3 partial column", "span")
                if type(value) not in (int, float) or not np.isfinite(float(value)):
                    raise CheckError(f"F3 partial scalar is invalid: {key}", "span", base_metrics)
            denominator = float(column["qr_reconstruction_denominator"])
            numerator = float(column["qr_reconstruction_numerator"])
            relative = float(column["qr_reconstruction_relative"])
            expected_relative = numerator / max(denominator, np.finfo(float).tiny)
            if denominator <= 0.0 or abs(float(column["r_diagonal_abs"]) - abs(r_factor[column_index, column_index])) > ORTH_LIMIT or abs(relative - expected_relative) > ORTH_LIMIT or relative > ORTH_LIMIT:
                raise CheckError("F3 partial QR reconstruction Gate failed", "span", base_metrics)
            reconstruction_max = relative if reconstruction_max is None else max(reconstruction_max, relative)
        if rank:
            singular = np.linalg.svd(r_factor, compute_uv=False)
            singular_finite = bool(np.all(np.isfinite(singular)))
            sigma_max = float(singular[0]) if singular_finite else 0.0
            condition = float(singular[-1] / sigma_max) if singular_finite and sigma_max > 0.0 else 0.0
            condition_finite = bool(singular_finite and np.isfinite(condition))
            gram = np.empty((rank, rank), dtype=np.complex128)
            for row_index in range(rank):
                for column_index in range(rank):
                    gram[row_index, column_index] = np.vdot(q[:, row_index], q[:, column_index])
            orthogonality = float(np.linalg.norm(gram - np.eye(rank), ord=2))
        else:
            condition = None
            condition_finite = None
            orthogonality = None
        return {
            **base_metrics,
            "rank": rank,
            "failed_column": failed,
            "condition_ratio": condition,
            "condition_finite": condition_finite,
            "orthogonality": orthogonality,
            "qr_reconstruction_relative": reconstruction_max,
            "projection_repeat_relative": f3.get("projection_repeat_relative"),
            "captured_energy": f3.get("captured_energy"),
            "rho": f3.get("rho"),
            "ideal_projected_true_residual_relative": f3.get(
                "ideal_projected_true_residual_relative"
            ),
            "residual_norm": float(np.linalg.norm(residual)),
        }
    if set(values) != {"q", "r_factor", "residual", "coefficients", "projected", "perpendicular"}:
        raise CheckError("F3 vector roles are incomplete", "contract")
    q = values["q"]
    r_factor = values["r_factor"]
    coefficients = values["coefficients"]
    projected = values["projected"]
    perpendicular = values["perpendicular"]
    if q.ndim != 2 or q.shape[1] != RANK or r_factor.shape != (RANK, RANK) or coefficients.shape != (RANK,) or projected.shape != residual.shape or perpendicular.shape != residual.shape:
        raise CheckError("F3 vector shapes are invalid", "span", base_metrics)
    if any(not np.all(np.isfinite(value)) for value in (q, r_factor, coefficients, projected, perpendicular)):
        raise CheckError("F3 vector contains non-finite values", "span", base_metrics)
    for key in ("rank", "pc_apply_count", "exact_action_count", "modal_rhs_apply_count"):
        if _require(f3, key, "F3 facts", "span") != RANK:
            raise CheckError(f"F3 fixed count mismatch: {key}", "span", base_metrics)
    columns = _require(f3, "column_facts", "F3 facts", "span")
    if not isinstance(columns, list) or len(columns) != RANK:
        raise CheckError("F3 column facts do not have rank 32", "span", base_metrics)
    reconstruction_max = 0.0
    for column_index, (expected_mode, column) in enumerate(zip(SELECTED_MODE_INDICES, columns)):
        column = _need_dict(column, "F3 column", "span")
        if column.get("mode_index") != expected_mode or column.get("modal_input_unchanged") is not True or column.get("pc_input_unchanged") is not True or column.get("action_input_unchanged") is not True:
            raise CheckError("F3 column input facts failed", "span", base_metrics)
        for role in ("modal_rhs", "pc_output", "action_output"):
            output = _field_facts(column.get(role), f"F3 {role}", observed=True)
            if output["finite"] is not True or output["owned_slave_max"] != 0.0:
                raise CheckError(f"F3 {role} slave/finite fact failed", "span", base_metrics)
            if role == "modal_rhs" and (output["norm"] is None or abs(float(output["norm"]) - 1.0) > REPEAT_LIMIT):
                raise CheckError("F3 modal RHS normalization failed", "span", base_metrics)
        for key in ("r_diagonal_abs", "qr_reconstruction_numerator", "qr_reconstruction_denominator", "qr_reconstruction_relative"):
            value = _require(column, key, "F3 column", "span")
            if type(value) not in (int, float) or not np.isfinite(float(value)):
                raise CheckError(f"F3 column scalar is invalid: {key}", "span", base_metrics)
        denominator = float(column["qr_reconstruction_denominator"])
        numerator = float(column["qr_reconstruction_numerator"])
        relative = float(column["qr_reconstruction_relative"])
        expected_relative = numerator / max(denominator, np.finfo(float).tiny)
        if denominator <= 0.0 or abs(float(column["r_diagonal_abs"]) - abs(r_factor[column_index, column_index])) > ORTH_LIMIT or abs(relative - expected_relative) > ORTH_LIMIT or relative > ORTH_LIMIT:
            raise CheckError("F3 QR reconstruction Gate failed", "span", base_metrics)
        reconstruction_max = max(reconstruction_max, relative)
    scalar_keys = ("condition_ratio", "orthogonality", "qr_reconstruction_relative", "projection_repeat_relative", "captured_energy", "rho", "ideal_projected_true_residual_relative")
    for key in scalar_keys:
        value = _require(f3, key, "F3 facts", "span")
        if type(value) not in (int, float) or not np.isfinite(float(value)):
            raise CheckError(f"F3 scalar is invalid: {key}", "span", base_metrics)
    singular = np.linalg.svd(r_factor, compute_uv=False)
    condition = float(singular[-1] / singular[0]) if singular.size and singular[0] > 0.0 else 0.0
    condition_finite = bool(np.all(np.isfinite(singular)) and np.isfinite(condition))
    gram = np.empty((RANK, RANK), dtype=np.complex128)
    for row_index in range(RANK):
        for column_index in range(RANK):
            gram[row_index, column_index] = np.vdot(q[:, row_index], q[:, column_index])
    gram_error = float(np.linalg.norm(gram - np.eye(RANK), ord=2))
    if f3.get("condition_finite") is not True or not condition_finite or gram_error > ORTH_LIMIT or condition < 1.0e-10 or abs(float(f3["qr_reconstruction_relative"]) - reconstruction_max) > ORTH_LIMIT:
        raise CheckError("F3 Q/R quality or reconstruction Gate failed", "span", {**base_metrics, "condition_ratio": condition, "orthogonality": gram_error, "qr_reconstruction_relative": reconstruction_max})
    recomputed_coefficients = np.empty(RANK, dtype=np.complex128)
    for column_index in range(RANK):
        recomputed_coefficients[column_index] = np.vdot(q[:, column_index], residual)
    recomputed_projected = q @ recomputed_coefficients
    recomputed_perpendicular = residual - recomputed_projected
    if not np.allclose(coefficients, recomputed_coefficients, rtol=0.0, atol=REPEAT_LIMIT) or not np.allclose(projected, recomputed_projected, rtol=0.0, atol=REPEAT_LIMIT) or not np.allclose(perpendicular, recomputed_perpendicular, rtol=0.0, atol=REPEAT_LIMIT):
        raise CheckError("F3 projection does not independently close", "span", base_metrics)
    residual_norm = float(np.linalg.norm(residual))
    perpendicular_norm = float(np.linalg.norm(recomputed_perpendicular))
    rho = perpendicular_norm / residual_norm if residual_norm else perpendicular_norm
    captured = 1.0 - rho * rho
    ideal = perpendicular_norm / float(source_norm) if source_norm else perpendicular_norm
    repeat_perpendicular = residual.copy()
    repeat_workspace = np.empty_like(residual)
    for column_index in range(RANK):
        repeat_coefficient = np.vdot(q[:, column_index], residual)
        np.multiply(q[:, column_index], repeat_coefficient, out=repeat_workspace)
        repeat_perpendicular -= repeat_workspace
    repeat_difference = repeat_perpendicular - recomputed_perpendicular
    repeat = float(np.linalg.norm(repeat_difference) / max(perpendicular_norm, np.finfo(float).tiny))
    metrics = {**base_metrics, "rank": RANK, "orthogonality": gram_error, "condition_ratio": condition, "qr_reconstruction_relative": reconstruction_max, "captured_energy": captured, "rho": rho, "ideal_projected_true_residual_relative": ideal, "residual_norm": residual_norm, "projection_repeat_relative": repeat}
    if abs(float(f2["recomputed_true_residual"]) - recomputed_true_residual) > F2_LIMIT or abs(float(f2["relative_difference"]) - expected_difference) > F2_LIMIT or abs(float(f3["orthogonality"]) - gram_error) > ORTH_LIMIT or abs(float(f3["condition_ratio"]) - condition) > ORTH_LIMIT or abs(float(f3["rho"]) - rho) > REPEAT_LIMIT or abs(float(f3["captured_energy"]) - captured) > REPEAT_LIMIT or abs(float(f3["ideal_projected_true_residual_relative"]) - ideal) > REPEAT_LIMIT or repeat > REPEAT_LIMIT or float(f3["projection_repeat_relative"]) > REPEAT_LIMIT:
        raise CheckError("F3 scalar or projection Gate failed", "span", metrics)
    if captured < CAPTURE_LIMIT or rho > RHO_LIMIT or ideal > IDEAL_LIMIT:
        raise CheckError("F3 projection span Gate failed", "span", metrics)
    return metrics


def _check_partial(record: dict[str, Any], record_path: Path, expected_source_sha: str) -> dict[str, Any]:
    if record.get("schema") != PARENT_SCHEMA or record.get("workflow") != "f2-f3-floquet-wave" or record.get("partial") is not True:
        raise CheckError("partial record identity is invalid")
    if record.get("source_sha") != expected_source_sha or record.get("branch") != BRANCH:
        raise CheckError("partial source identity is invalid")
    paths = _need_dict(record.get("paths"), "partial paths", "process")
    root = _absolute(_require(paths, "artifact_root", "partial paths", "process"), "partial artifact_root")
    if record_path != root / "parent_record.json":
        raise CheckError("partial record path is not artifact_root/parent_record.json")
    process = record.get("process")
    raw_resource = False
    if isinstance(process, dict):
        if process.get("stop_limit_bytes") != RSS_WATCHDOG:
            raise CheckError("partial F2/F3 stop limit is not 1.95GB")
        if process.get("warning_limit_bytes") != RSS_WARNING or process.get("resource_warning") is not (
            process.get("peak_rss_bytes") is not None
            and process.get("peak_rss_bytes") >= RSS_WARNING
        ):
            raise CheckError("partial F2/F3 warning fact does not close", "resource")
        sample_path_value = process.get("sample_path")
        if isinstance(sample_path_value, str) and os.path.isabs(sample_path_value) and Path(sample_path_value).is_file():
            sample_path = Path(sample_path_value)
            if not sample_path.is_relative_to(root) or process.get("sample_sha256") != _sha(sample_path):
                raise CheckError("partial process sample path/hash does not close")
            count = 0
            peak = None
            max_swap = None
            readable = True
            warning_crossed = False
            warning_sample_index = None
            warning_timestamp_ns = None
            with sample_path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    sample = _need_dict(json.loads(line), "partial process sample", "process")
                    _check_sample(sample, int(sample["root_pid"]))
                    count += 1
                    peak = sample["rss_bytes"] if peak is None else max(peak, sample["rss_bytes"])
                    max_swap = sample["swap_bytes"] if max_swap is None else max(max_swap, sample["swap_bytes"])
                    readable = readable and sample["all_status_readable"] is True
                    if not warning_crossed and sample["rss_bytes"] >= RSS_WARNING:
                        warning_crossed = True
                        warning_sample_index = count
                        warning_timestamp_ns = sample["timestamp_ns"]
            if process.get("sample_count") != count or process.get("peak_rss_bytes") != peak or process.get("max_swap_bytes") != max_swap or process.get("all_status_readable") is not readable or process.get("warning_crossed") is not warning_crossed or process.get("warning_sample_index") != warning_sample_index or process.get("warning_timestamp_ns") != warning_timestamp_ns or process.get("resource_warning") is not warning_crossed:
                raise CheckError("partial process summary does not close")
            raw_resource = (peak is not None and peak >= RSS_WATCHDOG) or (max_swap is not None and max_swap > 0)
    if not raw_resource:
        raise CheckError("partial record lacks independent resource-stop evidence")
    return {
        "schema": CHECKER_SCHEMA, "passed": False,
        "classification": "F2_F3_RESOURCE_GATE_FAIL",
        "contract_errors": [], "gate_failures": ["raw process resource stop"],
        "metrics": {"raw_record_path": str(record_path)},
    }


def check_record(record_path: Path | str, expected_source_sha: str) -> dict[str, Any]:
    record_argument = Path(os.path.abspath(os.fspath(record_path)))
    record = _read_json(record_argument)
    if not isinstance(record, dict):
        raise CheckError("parent record is not an object")
    if record.get("partial") is True:
        return _check_partial(record, record_argument, expected_source_sha)
    _check_identity(record, expected_source_sha)
    paths = _check_paths(record, record_argument)
    marker_names = _check_markers(record, paths)
    stage_stats = _check_process(record, paths)
    children = _require(record, "children", "parent", "process")
    if not isinstance(children, list) or [child.get("group") for child in children] != list(GROUPS):
        raise CheckError("precompile child order mismatch", "process")
    input_path = _absolute(_require(record["identity"], "input_path", "parent identity"), "input_path")
    previous_end: int | None = None
    for child, group in zip(children, GROUPS):
        child = _need_dict(child, f"child {group}", "process")
        monitor = _need_dict(child.get("process"), f"child {group} process", "process")
        _check_monitor(monitor, stage_stats[f"precompile:{group}"], int(_require(child, "pid", f"child {group}", "process")), f"child {group}")
        if previous_end is not None and monitor["started_ns"] <= previous_end:
            raise CheckError(f"child stages overlap: {group}", "process")
        previous_end = monitor["ended_ns"]
        _check_child_record(child, group, expected_source_sha, paths["cache_dir"], input_path)
    if previous_end is None or stage_stats["precompile:parent-only"]["first_timestamp_ns"] <= previous_end:
        raise CheckError("parent-only stage overlaps final child", "process")
    modules, incident_modules = _check_cache(record, paths)
    diagnostic = _need_dict(record.get("diagnostic"), "parent diagnostic", "process")
    monitor = _need_dict(diagnostic.get("process"), "diagnostic process", "process")
    _check_monitor(monitor, stage_stats["diagnostic"], int(monitor["pid"]), "diagnostic")
    if stage_stats["diagnostic"]["first_timestamp_ns"] <= stage_stats["precompile:parent-only"]["last_timestamp_ns"]:
        raise CheckError("diagnostic stage overlaps precompile", "process")
    try:
        metrics = _check_worker(record, paths, expected_source_sha, modules, stage_stats)
    except CheckError as error:
        if error.kind == "checkpoint_authority":
            return {
                "schema": CHECKER_SCHEMA,
                "passed": False,
                "classification": "F2_IDENTITY_OR_ALGEBRA_GATE_FAIL",
                "contract_errors": [],
                "gate_failures": [str(error)],
                "metrics": {
                    "f2_passed": False,
                    "f2_failures": [str(error)],
                    "f3_status": "not_run_by_checkpoint_authority_gate",
                },
            }
        raise
    if not metrics["f2_passed"]:
        identity_stop = (
            "checkpoint_restore_started"
            if "checkpoint_restore_started" in marker_names
            else "source_built"
        )
        expected_short = (
            list(F2_MARKER_ORDER[: F2_MARKER_ORDER.index(identity_stop) + 1])
            + ["release_started", "release_complete", "parent_complete"]
            if metrics.get("identity_gate")
            else list(F2_MARKER_ORDER[:26]) + ["release_started", "release_complete", "parent_complete"]
        )
        if marker_names != expected_short:
            raise CheckError("F2 failure does not have the short lifecycle", "process")
        return {
            "schema": CHECKER_SCHEMA, "passed": False,
            "classification": "F2_IDENTITY_OR_ALGEBRA_GATE_FAIL",
            "contract_errors": [], "gate_failures": metrics["f2_failures"],
            "metrics": metrics,
        }
    if metrics["f3_status"] == "span_gate_failed":
        if marker_names != list(F2_MARKER_ORDER[: F2_MARKER_ORDER.index("basis_complete") + 1]) + ["release_started", "release_complete", "parent_complete"]:
            raise CheckError("F3 span failure does not have the partial lifecycle", "process")
        return {
            "schema": CHECKER_SCHEMA,
            "passed": False,
            "classification": "FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE",
            "contract_errors": [],
            "gate_failures": ["F3 span gate"],
            "metrics": metrics,
        }
    if marker_names != list(F2_MARKER_ORDER):
        raise CheckError("complete F3 evidence lacks its marker stages", "process")
    return {
        "schema": CHECKER_SCHEMA, "passed": True,
        "classification": "F2_F3_COLD_STAGED_PASS",
        "contract_errors": [], "gate_failures": [],
        "identity": {
            "source_sha": record["source_sha"], "branch": record["branch"],
            "input_sha256": record["identity"]["input_sha256"],
            "physical_model_sha256": record["identity"]["physical_model_sha256"],
            "mode_manifest_sha256": record["identity"]["mode_manifest_sha256"],
        },
        "evidence": {
            "raw_record_path": str(record_argument), "raw_record_sha256": _sha(record_argument),
            "process_sample_sha256": record["process"]["sample_sha256"],
            "marker_manifest_sha256": record["markers"]["manifest_sha256"],
            "diagnostic_record_sha256": record["diagnostic"]["record_sha256"],
        },
        "metrics": {
            **metrics, "precompile_group_count": 7, "precompiled_module_count": len(modules),
            "solver_ffcx_call_count": 11, "process_sample_count": record["process"]["sample_count"],
            "peak_rss_bytes": record["process"]["peak_rss_bytes"], "max_swap_bytes": record["process"]["max_swap_bytes"],
            "incident_deferred": len(incident_modules) == 0,
        },
    }


def _emit(value: dict[str, Any], output: str) -> None:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    if output == "-":
        sys.stdout.write(payload)
    else:
        Path(os.path.abspath(output)).write_text(payload, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", default="-")
    args = parser.parse_args(argv)
    try:
        result = check_record(args.record, args.expected_source_sha)
    except CheckError as error:
        result = {
            "schema": CHECKER_SCHEMA, "passed": False,
            "classification": {
                "resource": "F2_F3_RESOURCE_GATE_FAIL",
                "numerical": "F2_F3_NUMERICAL_GATE_FAIL",
                "span": "FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE",
                "jit": "F2_F3_CONTRACT_INVALID",
                "process": "F2_F3_CONTRACT_INVALID",
            }.get(error.kind, "F2_F3_CONTRACT_INVALID"),
            "contract_errors": [str(error)] if error.kind == "contract" else [],
            "gate_failures": [str(error)] if error.kind != "contract" else [],
            "metrics": error.metrics,
        }
        _emit(result, args.output)
        return 1
    except (OSError, KeyError, TypeError, ValueError, IndexError) as error:
        result = {
            "schema": CHECKER_SCHEMA, "passed": False,
            "classification": "F2_F3_CONTRACT_INVALID",
            "contract_errors": [f"checker boundary error: {error}"],
            "gate_failures": [], "metrics": {},
        }
        _emit(result, args.output)
        return 1
    _emit(result, args.output)
    return 0


__all__ = ("CHECKER_SCHEMA", "F2_MARKER_ORDER", "check_record", "main")


if __name__ == "__main__":
    raise SystemExit(main())
