"""Independent checker for the P0 physical Maxwell raw evidence.

The checker reads only JSON, JSONL, NumPy arrays, and checkpoint artifacts.
It does not import the worker, numerical core, PETSc, MPI, or DOLFINx.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p0_physical"
STAGE = "p0-physical"
CASE = "p6-h10-mpi1"
SOURCE = "physical_rhs"
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p0-physical-record.v2"
MARKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p0-physical-marker.v2"
V14_MARKER_SCHEMA = "task038.v14.j3.marker.v1"
SAMPLE_SCHEMA = "task038.v14.j3.process-sample.v1"
CHECKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p0-physical-check.v2"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
MARKERS = (
    "paths_ready",
    "bundle_built",
    "source_built",
    "solve_started",
    "solve_complete",
    "retained_ready",
    "retained_observed",
    "krylov_destroyed",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "release_observation",
    "recovery_started",
    "recovery_built",
    "official_outputs_written",
    "bundle_destroyed",
    "record_written",
)
LEVELS = (6, 3, 1)
PAIRS = ((6, 3), (3, 1))
RESTART = 20
CYCLE_MAX_IT = 20
MAX_IT = 20_000
CHECKPOINT_INTERVAL = 500
RESIDUAL_LIMIT = 1.0e-6
COLD_RSS_LIMIT = 2_000_000_000
RETAINED_WARNING = 1_800_000_000
RETAINED_DWELL_NS = 2_000_000_000
RELEASE_OBSERVATION_NS = 1_000_000_000
DIRECT_AUTHORITY_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/cases/102_hybrid_iterative_robustness/records/"
    "task037c_mpi8_three_way_qualification_v1.json"
)
DIRECT_AUTHORITY_SHA256 = (
    "eec638b833679937252982ae394012e88e679c058cccc0c4f6c091d33754fbd8"
)
# This is the frozen task037c_comparator.TOTAL_FULL3D_TOL absolute-total rule.
TOTAL_FULL3D_TOL = 1.0e-5
SIGNIFICANT_GATE_DEFINITION = (
    "one set of 12 significant diffraction identities: 12 power gates and 12 "
    "complex boundary-amplitude gates"
)
EXPECTED_PHYSICAL_FIELDS = {
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
    "boundary_model": "dtn_port",
    "dtn_order_policy": "auto_propagating",
    "dtn_assembly": "auxiliary",
}
J4_EXPECTED_PROFILE = {
    **EXPECTED_PHYSICAL_FIELDS,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
}

J4_PARENT_SCHEMA = "task038.v14.j4.p0r.parent-record.v1"
J4_WORKER_SCHEMA = "task038.v14.j4.p0r.worker-record.v1"
J4_CHECKER_SCHEMA = "task038.v14.j4.p0r.check.v1"
J4_WORKFLOW = "j4-p0r"
J4_WORKER_MARKER_SCHEMA = "task038.v14.j4.p0r.worker-marker.v1"
J4_WORKER_MARKERS = (
    "paths_ready",
    "bundle_built",
    "source_built",
    "one_action_complete",
    "one_pc_complete",
    "solve_started",
    "solve_complete",
    "retained_ready",
    "retained_observed",
    "krylov_destroyed",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "release_observation",
    "bundle_destroyed",
    "record_written",
)
J5_WORKFLOW = "j5-full"
J5_PARENT_SCHEMA = "task038.v14.j5.full.parent-record.v1"
J5_WORKER_SCHEMA = "task038.v14.j5.full.worker-record.v1"
J5_CHECKER_SCHEMA = "task038.v14.j5.full.check.v1"
J5_WORKER_MARKER_SCHEMA = "task038.v14.j5.full.worker-marker.v1"
J5_WORKER_MARKERS = (
    "paths_ready",
    "bundle_built",
    "source_built",
    "one_action_complete",
    "one_pc_complete",
    "solve_started",
    "solve_complete",
    "retained_ready",
    "retained_observed",
    "krylov_destroyed",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "release_observation",
    "recovery_started",
    "recovery_built",
    "official_outputs_written",
    "recovery_complete",
    "bundle_destroyed",
    "record_written",
)
J5_PARENT_STAGE = "j5-full-parent"
J5_SOLVER_STAGE = "j5-full-solver"
J5_MILESTONES = (20, 100, 200, 500, 1000, 2000, 5000, 10000, 15000, 20000)
J5_NUMERICAL_FIXED_CAP = "J5_PHYSICAL_NUMERICAL_FAIL_AT_FIXED_CAP"
J5_NUMERICAL_BEFORE_CAP = "J5_PHYSICAL_NUMERICAL_FAIL_BEFORE_FIXED_CAP"
J5_NUMERICAL_GATE_FAIL = "J5_PHYSICAL_NUMERICAL_GATE_FAIL"
J5_CHECKPOINT_GATE_FAIL = "J5_CHECKPOINT_GATE_FAIL"
J5_AUTHORITY_ARRAYS_MISSING = "J5_NUMERICAL_RECOVERY_PASS_AUTHORITY_ARRAYS_MISSING"
J4_GROUP_ROLES = {
    "positive-p6": ("positive_p6_action", "positive_p6_bilinear"),
    "positive-p3": ("positive_p3_bilinear",),
    "positive-p1": ("positive_p1_bilinear",),
    "dtn-surface": (
        "dtn_surface_top_0",
        "dtn_surface_top_1",
        "dtn_surface_bottom_0",
        "dtn_surface_bottom_1",
    ),
    "incident-rhs": ("incident_top_traction",),
    "physical-volume-curl": ("physical_volume_curl_action",),
    "physical-volume-mass": ("physical_volume_mass_action",),
}
J4_GROUP_COUNTS = {group: len(roles) for group, roles in J4_GROUP_ROLES.items()}
J4_MARKER_ORDER = (
    "parent_started",
    "fresh_cache_created",
    "precompile_positive_p6_started",
    "precompile_positive_p6_complete",
    "precompile_positive_p3_started",
    "precompile_positive_p3_complete",
    "precompile_positive_p1_started",
    "precompile_positive_p1_complete",
    "precompile_dtn_surface_started",
    "precompile_dtn_surface_complete",
    "precompile_incident_rhs_started",
    "precompile_incident_rhs_complete",
    "precompile_physical_volume_started",
    "precompile_physical_volume_curl_started",
    "precompile_physical_volume_curl_complete",
    "precompile_physical_volume_mass_started",
    "precompile_physical_volume_mass_complete",
    "precompile_physical_volume_complete",
    "all_precompile_children_gone",
    "solver_child_started",
    "positive_setup_started",
    "positive_setup_complete",
    "mode_inventory_started",
    "mode_inventory_complete",
    "surface_assemblers_started",
    "surface_assemblers_complete",
    "dtn_carrier_started",
    "dtn_carrier_complete",
    "dtn_action_complete",
    "physical_volume_action_started",
    "physical_volume_action_complete",
    "bundle_built",
    "source_built",
    "one_action_complete",
    "one_pc_complete",
    "solve_started",
    "solve_complete",
    "solver_stack_release_started",
    "solver_stack_release_complete",
    "parent_complete",
)
J4_PARENT_MARKER_INDEX = {
    name: index
    for index, name in enumerate(
        (
            "parent_started",
            "fresh_cache_created",
            "precompile_positive_p6_started",
            "precompile_positive_p6_complete",
            "precompile_positive_p3_started",
            "precompile_positive_p3_complete",
            "precompile_positive_p1_started",
            "precompile_positive_p1_complete",
            "precompile_dtn_surface_started",
            "precompile_dtn_surface_complete",
            "precompile_incident_rhs_started",
            "precompile_incident_rhs_complete",
            "precompile_physical_volume_started",
            "precompile_physical_volume_curl_started",
            "precompile_physical_volume_curl_complete",
            "precompile_physical_volume_mass_started",
            "precompile_physical_volume_mass_complete",
            "precompile_physical_volume_complete",
            "all_precompile_children_gone",
            "solver_child_started",
            "positive_setup_started",
            "positive_setup_complete",
            "mode_inventory_started",
            "mode_inventory_complete",
            "surface_assemblers_started",
            "surface_assemblers_complete",
            "dtn_carrier_started",
            "dtn_carrier_complete",
            "dtn_action_complete",
            "physical_volume_action_started",
            "physical_volume_action_complete",
            "bundle_built",
            "source_built",
            "one_action_complete",
            "one_pc_complete",
            "solve_started",
            "solve_complete",
            "solver_stack_release_started",
            "solver_stack_release_complete",
            "recovery_started",
            "recovery_complete",
            "parent_complete",
        )
    )
}
J4_PROCESS_STAGES = tuple(f"precompile:{group}" for group in J4_GROUP_COUNTS) + (
    "precompile:parent-only",
    "solver",
)
J4_COMPILER_NAMES = frozenset(
    {"gcc", "g++", "cc1", "cc1plus", "clang", "clang++", "ld", "collect2"}
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


def _option(argv: list[str], name: str) -> str:
    try:
        index = argv.index(name)
        return argv[index + 1]
    except (ValueError, IndexError):
        return ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Path):
        return str(value)
    return value


def _stable_sha(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _array_sha(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values, dtype=np.complex128).tobytes(order="C")
    ).hexdigest()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    numerator = float(np.linalg.norm(np.asarray(left) - np.asarray(right)))
    denominator = max(float(np.linalg.norm(np.asarray(right))), np.finfo(float).tiny)
    value = numerator / denominator
    return float(value) if np.isfinite(value) else float(np.finfo(float).max)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(float(value))


def _complex_json_value(value: Any) -> complex:
    if isinstance(value, Mapping):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    if isinstance(value, str):
        return complex(value)
    if _finite_number(value):
        return complex(float(value))
    raise ValueError("complex JSON value is not parseable")


def _inside(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _gate(gates: list[str], message: str) -> None:
    gates.append(message)


def _check_provenance(
    record: Mapping[str, Any], record_path: Path, expected_sha: str, errors: list[str]
) -> tuple[Path, Path, dict[str, Any]]:
    if record.get("schema") != RECORD_SCHEMA:
        _error(errors, "record schema mismatch")
    if record.get("stage") != STAGE or record.get("case") != CASE:
        _error(errors, "stage/case mismatch")
    if record.get("source_name") != SOURCE or record.get("mpi_size") != 1:
        _error(errors, "P0 source or MPI identity mismatch")
    if record.get("branch") != BRANCH or record.get("raw_facts_only") is not True:
        _error(errors, "branch/raw-facts provenance is not closed")
    if any(key in record for key in ("status", "passed", "classification", "checks", "gates")):
        _error(errors, "worker record contains checker-owned decision fields")
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        _error(errors, "provenance is missing")
        return Path("."), Path("."), {}
    raw_text = record.get("raw_dir")
    checkpoint_text = record.get("checkpoint_root")
    stored_record_text = record.get("record_path")
    raw_dir = Path(str(raw_text)).resolve()
    checkpoint_root = Path(str(checkpoint_text)).resolve()
    stored_record = Path(str(stored_record_text)).resolve()
    if not raw_dir.is_absolute() or not raw_dir.is_dir():
        _error(errors, "raw_dir is missing or not absolute")
    if not checkpoint_root.is_absolute() or not checkpoint_root.is_dir():
        _error(errors, "checkpoint_root is missing or not absolute")
    if stored_record != record_path.resolve() or not stored_record.is_file():
        _error(errors, "record_path is not the checked record")
    jit_cache = Path(str(provenance.get("jit_cache_dir", ""))).resolve()
    if jit_cache != raw_dir.parent / "jit_cache" or not jit_cache.is_dir():
        _error(errors, "isolated JIT cache is not the artifact sibling")
    if checkpoint_root.parent != raw_dir.parent:
        _error(errors, "checkpoint root is not the artifact sibling")
    if provenance.get("isolated_jit_cache") is not True:
        _error(errors, "isolated JIT cache fact is not true")
    if provenance.get("source_sha") != expected_sha:
        _error(errors, "source SHA provenance mismatch")
    if provenance.get("branch") != BRANCH or provenance.get("clean_source_tree") is not True:
        _error(errors, "source branch/clean provenance is not closed")
    if provenance.get("qualified_activation") != "1" or provenance.get("mpi_size") != 1:
        _error(errors, "qualified activation or MPI provenance is not closed")
    if provenance.get("petsc_scalar_type") != "complex128" or provenance.get("petsc_int_type") != "int32":
        _error(errors, "PETSc ABI provenance mismatch")
    threads = provenance.get("threads")
    if not isinstance(threads, Mapping) or set(threads) != {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"} or any(value != "1" for value in threads.values()):
        _error(errors, "thread provenance is not fixed to one")
    executable = provenance.get("python_executable")
    prefix = provenance.get("python_prefix")
    command = record.get("command")
    expected_prefix = Path(__file__).absolute().parents[1] / ".venv"
    expected_executable = expected_prefix / "bin" / "python"
    if (
        executable != str(expected_executable)
        or prefix != str(expected_prefix)
        or not expected_executable.is_file()
        or not expected_prefix.is_dir()
        or not isinstance(command, list)
        or not command
        or not isinstance(command[0], str)
        or command[0] != executable
    ):
        _error(errors, "worker executable/prefix is not bound to the lexical checkout .venv")
    abi = provenance.get("abi_modules")
    if not isinstance(abi, Mapping) or set(abi) != {"mpi4py", "petsc4py", "dolfinx", "basix"} or any(not isinstance(value, str) or not Path(value).is_absolute() for value in abi.values()):
        _error(errors, "qualified ABI module paths are incomplete")
    input_path = Path(str(provenance.get("input_path", ""))).resolve()
    if not input_path.is_file() or not str(input_path).endswith("input/templates/full3d_iterative_example.dat"):
        _error(errors, "input template provenance is not closed")
    elif provenance.get("input_sha256") != _sha256_file(input_path):
        _error(errors, "input template SHA mismatch")
    if provenance.get("input_sha256") != INPUT_SHA256:
        _error(errors, "input template is not the frozen 1-degree input")
    if provenance.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
        _error(errors, "physical-model SHA is not the frozen 1-degree identity")
    if provenance.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
        _error(errors, "mode manifest SHA is not the frozen ordered identity")
    for key, expected in (
        ("stage", STAGE),
        ("case", CASE),
        ("source_name", SOURCE),
        ("raw_dir", str(raw_dir)),
        ("checkpoint_root", str(checkpoint_root)),
        ("record_path", str(stored_record)),
        ("jit_cache_dir", str(jit_cache)),
    ):
        if provenance.get(key) != expected:
            _error(errors, f"provenance field mismatch: {key}")
    if not isinstance(command, list) or provenance.get("command") != command:
        _error(errors, "worker command is not bound in provenance")
        return raw_dir, checkpoint_root, dict(provenance)
    required = [
        "--stage", STAGE, "--case", CASE, "--source", SOURCE,
        "--raw-dir", str(raw_dir), "--jit-cache-dir", str(jit_cache),
        "--checkpoint-root", str(checkpoint_root), "--record", str(stored_record),
        "--expected-source-sha", expected_sha, "--expected-mpi-size", "1",
        "--input", str(input_path),
    ]
    if len(command) < 3 or command[1:3] != ["-m", MODULE] or command[3:] != required:
        _error(errors, "worker command argv is not the frozen P0 command")
    return raw_dir, checkpoint_root, dict(provenance)


def _check_identities(record: Mapping[str, Any], errors: list[str]) -> None:
    identities = record.get("identities")
    if not isinstance(identities, Mapping):
        _error(errors, "identity authorities are missing")
        return
    for name in ("input_identity_authority", "operator_identity_authority"):
        authority = identities.get(name)
        digest = identities.get(name.replace("_authority", "_sha256"))
        if not isinstance(authority, Mapping) or not isinstance(digest, str) or digest != _stable_sha(authority):
            _error(errors, f"identity hash is not closed: {name}")
    input_authority = identities.get("input_identity_authority")
    if not isinstance(input_authority, Mapping) or input_authority.get("input_sha256") != INPUT_SHA256:
        _error(errors, "input identity is not the frozen 1-degree input")
    physical = identities.get("physical_model_authority")
    if not isinstance(physical, Mapping):
        _error(errors, "physical-model authority is missing")
        return
    if identities.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
        _error(errors, "physical-model identity SHA is not frozen")
    if identities.get("physical_model_authority_sha256") != _stable_sha(physical):
        _error(errors, "physical-model authority hash is not closed")
    for key, expected in EXPECTED_PHYSICAL_FIELDS.items():
        if physical.get(key) != expected:
            _error(errors, f"frozen physical configuration mismatch: {key}")
    for authority in (input_authority, physical):
        if not isinstance(authority, Mapping) or authority.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
            _error(errors, "ordered mode manifest identity is not frozen")
    operator = identities.get("operator_identity_authority")
    if not isinstance(operator, Mapping) or operator.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256:
        _error(errors, "operator mode manifest identity is not frozen")


def _check_architecture(record: Mapping[str, Any], errors: list[str]) -> None:
    architecture = record.get("architecture")
    if not isinstance(architecture, Mapping):
        _error(errors, "physical architecture is missing")
        return
    if architecture.get("levels") != list(LEVELS) or architecture.get("same_physical_mesh") is not True:
        _error(errors, "same-mesh hierarchy is not the fixed p6/p3/p1 profile")
    for key in ("p6_matrix_free", "p3_sparse_allowed", "p1_sparse_allowed", "outer_ksp_created", "physical_solve", "dtn", "recovery"):
        if architecture.get(key) is not True:
            _error(errors, f"physical architecture fact is not true: {key}")
    for key in ("p6_global_aij", "high_order_global_aij", "global_dense_transfer", "global_transfer_matrix", "numeric_allgather", "p6_factor"):
        if architecture.get(key) is not False:
            _error(errors, f"forbidden architecture fact is not explicit false: {key}")
    if architecture.get("source_is_pde_rhs") is not True:
        _error(errors, "physical architecture source_is_pde_rhs is not true")
    setup = architecture.get("setup_audit")
    if not isinstance(setup, Mapping) or setup.get("schema") != "task038.same_mesh_hcurl_pmg.setup.v1":
        _error(errors, "measured setup audit is missing")
        return
    profile = setup.get("profile")
    if not isinstance(profile, Mapping) or profile.get("levels") != list(LEVELS) or profile.get("same_physical_mesh") is not True:
        _error(errors, "setup audit profile is not same-mesh p6/p3/p1")
    setup_arch = setup.get("architecture")
    if not isinstance(setup_arch, Mapping):
        _error(errors, "setup audit architecture is missing")
    else:
        for key in ("p6_matrix_free",):
            if setup_arch.get(key) is not True:
                _error(errors, f"setup audit fact is not true: {key}")
        for key in ("p6_global_aij", "global_dense_transfer", "global_transfer_matrix", "numeric_allgather", "p6_factor", "physical_solve", "dtn", "recovery", "high_order_global_aij", "outer_ksp_created"):
            if setup_arch.get(key) is not False:
                _error(errors, f"setup forbidden fact is not false: {key}")
    physical = record.get("physical")
    audit = physical.get("audit") if isinstance(physical, Mapping) else None
    if not isinstance(audit, Mapping) or audit.get("schema") != "task038.fullspace-physical-action.v1" or audit.get("global_aij_materialized") is not False or audit.get("numeric_allgather") is not False or audit.get("t4_transmission_included") is not False:
        _error(errors, "physical action audit is not closed")


def _check_source(record: Mapping[str, Any], expected_sha: str, errors: list[str]) -> list[int]:
    source = record.get("source")
    if not isinstance(source, Mapping) or source.get("generation") != "dtn_port_modal_physical_rhs" or source.get("role") != "physical_maxwell_rhs" or source.get("phase_application") != "finalized_floquet_mpc_once":
        _error(errors, "physical RHS generation/phase facts are not closed")
        return []
    facts = source.get("facts")
    if not isinstance(facts, Mapping) or facts.get("source_sha") != expected_sha:
        _error(errors, "physical RHS source facts are not bound to source SHA")
    indices = source.get("owned_slave_indices")
    if not isinstance(indices, list) or any(type(value) is not int or value < 0 for value in indices):
        _error(errors, "owned slave index facts are malformed")
        return []
    return indices


def _check_probe(
    record: Mapping[str, Any], raw_dir: Path, slave_indices: list[int], errors: list[str], gates: list[str]
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    descriptor = record.get("npz")
    if not isinstance(descriptor, Mapping) or descriptor.get("relative_path") != "physical_probe.npz":
        _error(errors, "physical probe descriptor is missing")
        return {}, {}
    path = (raw_dir / str(descriptor.get("relative_path"))).resolve()
    if not _inside(path, raw_dir) or not path.is_file():
        _error(errors, "physical probe is missing or escapes raw_dir")
        return {}, {}
    if descriptor.get("bytes") != path.stat().st_size or descriptor.get("sha256") != _sha256_file(path):
        _error(errors, "physical probe bytes/SHA mismatch")
    roles = ("rhs_before", "rhs_after", "final_solution", "final_action", "final_residual")
    if tuple(descriptor.get("roles", ())) != roles:
        _error(errors, "physical probe roles are not exact")
    try:
        with np.load(path, allow_pickle=False) as data:
            if set(data.files) != set(roles):
                _error(errors, "physical probe array inventory is not exact")
            arrays = {name: np.asarray(data[name]) for name in data.files}
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"physical probe unreadable: {exc}")
        return {}, dict(descriptor)
    if set(arrays) != set(roles) or any(array.ndim != 1 or array.dtype != np.dtype(np.complex128) for array in arrays.values()):
        _error(errors, "physical probe dtype/shape is not complex128 one-dimensional")
        return arrays, dict(descriptor)
    if any(not np.all(np.isfinite(array)) for array in arrays.values()):
        _gate(gates, "physical probe contains a non-finite value")
    if not np.array_equal(arrays["rhs_before"], arrays["rhs_after"]):
        _gate(gates, "physical RHS input changed during the solve")
    residual = arrays["final_residual"]
    rhs = arrays["rhs_before"]
    action = arrays["final_action"]
    if _relative(rhs, action + residual) > 1.0e-13:
        _error(errors, "final residual does not close rhs - final action")
    rhs_norm = float(np.linalg.norm(rhs))
    residual_norm = float(np.linalg.norm(residual))
    raw_relative = residual_norm / max(rhs_norm, np.finfo(float).tiny)
    if not np.isfinite(raw_relative) or raw_relative > RESIDUAL_LIMIT:
        _gate(gates, "raw explicit true residual exceeds 1e-6")
    krylov = record.get("krylov", {})
    worker_relative = krylov.get("final_true_residual") if isinstance(krylov, Mapping) else None
    if not _finite_number(worker_relative) or abs(float(worker_relative) - raw_relative) > 1.0e-12:
        _error(errors, "worker final residual does not match raw recomputation")
    source = record.get("source", {})
    before = source.get("before") if isinstance(source, Mapping) else None
    after = source.get("after") if isinstance(source, Mapping) else None
    if not isinstance(before, Mapping) or before.get("array_sha256") != _array_sha(rhs) or not isinstance(after, Mapping) or after.get("array_sha256") != _array_sha(arrays["rhs_after"]):
        _error(errors, "RHS vector facts do not match the raw probe")
    if not rhs_norm > 0.0:
        _gate(gates, "physical RHS is zero")
    for name in roles:
        if any(index >= arrays[name].size for index in slave_indices):
            _error(errors, "owned slave index exceeds raw vector shape")
            break
        if slave_indices and np.max(np.abs(arrays[name][slave_indices])) != 0.0:
            _gate(gates, f"owned slave rows are nonzero in {name}")
    result = krylov.get("final_output") if isinstance(krylov, Mapping) else None
    if isinstance(result, Mapping) and result.get("array_sha256") != _array_sha(arrays["final_solution"]):
        _error(errors, "final solution facts do not match raw probe")
    return arrays, {"raw_relative": float(raw_relative), "rhs_norm": rhs_norm, "residual_norm": residual_norm}


def _check_krylov(record: Mapping[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    expected_settings = {
        "ksp_type": "gmres", "pc_side": "right", "norm_type": "unpreconditioned",
        "restart": RESTART, "cycle_max_it": CYCLE_MAX_IT, "max_it": MAX_IT,
        "residual_replacement": True, "zero_initial_guess": True,
        "checkpoint_interval": CHECKPOINT_INTERVAL, "first_checkpoint_iteration": None,
        "residual_limit": RESIDUAL_LIMIT,
    }
    settings = record.get("settings")
    if not isinstance(settings, Mapping) or any(settings.get(key) != value for key, value in expected_settings.items()):
        _error(errors, "fixed physical GMRES settings are not closed")
    krylov = record.get("krylov")
    if not isinstance(krylov, Mapping):
        _error(errors, "Krylov raw facts are missing")
        return {}
    cycles = krylov.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        _gate(gates, "no physical GMRES cycle is recorded")
        return dict(krylov)
    cursor = 0
    matvec_total = pc_total = 0
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, Mapping):
            _error(errors, f"cycle {index} is not an object")
            continue
        values = [cycle.get(key) for key in ("start_iteration", "end_iteration", "iterations", "matvec_count", "pc_apply_count")]
        if any(type(value) is not int for value in values):
            _error(errors, f"cycle {index} integer ledger is malformed")
            continue
        start, end, iterations, matvec, pc = values
        if cycle.get("cycle_index") != index or start != cursor or end != start + iterations or iterations <= 0 or iterations > CYCLE_MAX_IT:
            _error(errors, f"cycle {index} interval is not continuous")
        if cycle.get("initial_guess_nonzero") is not (index != 0):
            _error(errors, f"cycle {index} initial-guess flag is wrong")
        expected_matvec = iterations if index == 0 else iterations + 1
        if matvec != expected_matvec:
            _error(errors, f"cycle {index} matvec ledger is wrong")
        if pc != iterations + 1 or cycle.get("ksp_destroyed") is not True:
            _error(errors, f"cycle {index} PC/KSP ledger is wrong")
        if not _finite_number(cycle.get("explicit_true_residual")):
            _gate(gates, f"cycle {index} explicit residual is non-finite")
        cursor = end
        matvec_total += matvec
        pc_total += pc
    if type(krylov.get("iterations")) is not int or krylov.get("iterations") != cursor or cursor <= 0 or cursor > MAX_IT:
        _error(errors, "total physical iteration ledger is not closed")
    if krylov.get("matvec_count") != matvec_total or krylov.get("pc_apply_count") != pc_total:
        _error(errors, "physical matvec/PC totals do not equal cycle ledger")
    if krylov.get("ksp_destroy_count") != len(cycles):
        _error(errors, "KSP destroy total does not equal cycle count")
    if krylov.get("driver_explicit_action_count") != len(cycles) + 1 or krylov.get("rhs_action_count") != 0 or krylov.get("final_action_recheck_count") != 1 or krylov.get("extra_action_count") != 1:
        _error(errors, "physical explicit-action roles are not closed")
    driver = krylov.get("driver_explicit_action_count")
    if all(type(value) is int for value in (driver, krylov.get("explicit_action_count_total"), krylov.get("action_calls_total"))):
        if krylov["explicit_action_count_total"] != driver + 1 or krylov["action_calls_total"] != matvec_total + krylov["explicit_action_count_total"]:
            _error(errors, "physical action ledger does not close")
    final = krylov.get("final_true_residual")
    if not _finite_number(final) or float(final) > RESIDUAL_LIMIT:
        _gate(gates, "worker final explicit true residual exceeds 1e-6")
    pc_rows = krylov.get("pc_apply_facts")
    if not isinstance(pc_rows, list) or len(pc_rows) != pc_total:
        _error(errors, "physical V-cycle facts do not match PC count")
    else:
        fixed = {"p6_smoother_apply_count": 2, "p63_adjoint_count": 1, "p63_primal_count": 1, "lower_cycle_count": 1, "p1_solve_count": 1}
        for index, row in enumerate(pc_rows):
            if not isinstance(row, Mapping) or row.get("apply_index") != index:
                _error(errors, f"physical V-cycle apply {index} index is malformed")
                continue
            for key, value in fixed.items():
                if row.get(key) != value:
                    _error(errors, f"physical V-cycle apply {index} count mismatch: {key}")
            if row.get("output_finite") is not True or row.get("owned_slave_max") != 0.0:
                _gate(gates, f"physical V-cycle apply {index} constraint/finite Gate failed")
            if not _finite_number(row.get("p1_relative_residual")) or float(row["p1_relative_residual"]) > 1.0e-11:
                _gate(gates, f"physical V-cycle apply {index} p1 residual Gate failed")
    return dict(krylov)


def _check_checkpoints(
    record: Mapping[str, Any],
    checkpoint_root: Path,
    expected_sha: str,
    errors: list[str],
    gates: list[str],
    checkpoint_failures: list[str] | None = None,
    expected_iterations: int | None = None,
) -> list[int]:
    checkpoint_errors = checkpoint_failures if checkpoint_failures is not None else errors
    checkpoint_gates = checkpoint_failures if checkpoint_failures is not None else gates

    def report_error(message: str) -> None:
        checkpoint_errors.append(message)

    def report_gate(message: str) -> None:
        checkpoint_gates.append(message)

    krylov = record.get("krylov")
    if not isinstance(krylov, Mapping):
        report_error("checkpoint Krylov facts are missing")
        return []
    iterations = expected_iterations if expected_iterations is not None else krylov.get("iterations")
    if type(iterations) is not int or iterations <= 0:
        report_error("checkpoint iteration total is missing or invalid")
        return []
    expected = list(range(CHECKPOINT_INTERVAL, iterations + 1, CHECKPOINT_INTERVAL))
    facts = krylov.get("checkpoint_facts")
    if not isinstance(facts, list) or [item.get("iteration") for item in facts if isinstance(item, Mapping)] != expected:
        report_error("checkpoint schedule is not the fixed solution-only 500-step schedule")
        return expected
    identities = record.get("identities")
    if expected and not isinstance(identities, Mapping):
        report_error("checkpoint identity facts are missing")
        return expected
    for item in facts:
        if not isinstance(item, Mapping):
            report_error("checkpoint fact is not an object")
            continue
        manifest_path = Path(str(item.get("manifest_path", ""))).resolve()
        if not _inside(manifest_path, checkpoint_root) or not manifest_path.is_file():
            report_error("checkpoint manifest is missing or escapes checkpoint_root")
            continue
        if item.get("manifest_sha256") != _sha256_file(manifest_path):
            report_error("checkpoint manifest SHA mismatch")
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report_error(f"checkpoint manifest unreadable: {exc}")
            continue
        if manifest.get("schema") != "fixed-memory-krylov.solution-checkpoint.v1" or manifest.get("iteration") != item.get("iteration") or manifest.get("source_sha") != expected_sha or manifest.get("mpi_size") != 1 or manifest.get("solution_only") is not True or manifest.get("numeric_allgather") is not False or manifest.get("vector_roles") != ["solution"]:
            report_error("checkpoint manifest contract is not closed")
        for name in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
            if manifest.get(name) != identities.get(name):
                report_error(f"checkpoint identity mismatch: {name}")
        ranks = manifest.get("ranks")
        if not isinstance(ranks, list) or len(ranks) != 1 or not isinstance(ranks[0], Mapping) or not isinstance(ranks[0].get("solution"), Mapping):
            report_error("MPI1 checkpoint shard metadata is incomplete")
            continue
        descriptor = ranks[0]["solution"]
        shard = (manifest_path.parent / str(descriptor.get("relative_path", ""))).resolve()
        if not _inside(shard, manifest_path.parent) or not shard.is_file() or descriptor.get("bytes") != shard.stat().st_size or descriptor.get("sha256") != _sha256_file(shard):
            report_error("checkpoint solution shard bytes/SHA is not closed")
            continue
        try:
            values = np.asarray(np.load(shard, allow_pickle=False))
        except (OSError, ValueError, TypeError) as exc:
            report_error(f"checkpoint shard unreadable: {exc}")
            continue
        if values.ndim != 1 or str(values.dtype) != descriptor.get("dtype") or list(values.shape) != descriptor.get("shape") or not np.all(np.isfinite(values)):
            report_gate("checkpoint solution shard dtype/shape/finite Gate failed")
    return expected


def _check_markers(record: Mapping[str, Any], raw_dir: Path, errors: list[str]) -> dict[str, int]:
    lifecycle = record.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        _error(errors, "marker lifecycle facts are not closed")
        lifecycle = {}
    elif lifecycle.get("marker_relative_dir") != "markers" or lifecycle.get("marker_names") != list(MARKERS) or lifecycle.get("retained_dwell_seconds") != 2.0:
        _error(errors, "marker lifecycle facts are not closed")
    marker_dir = raw_dir / "markers"
    if not marker_dir.is_dir():
        _error(errors, "marker directory is missing")
        return {}
    if sorted(path.name for path in marker_dir.glob("*.json")) != sorted(f"{name}.json" for name in MARKERS):
        _error(errors, "marker inventory is not exact")
    times: dict[str, int] = {}
    source_sha = record.get("provenance", {}).get("source_sha") if isinstance(record.get("provenance"), Mapping) else None
    for name in MARKERS:
        try:
            item = _read_json(marker_dir / f"{name}.json")
            if item.get("schema") != MARKER_SCHEMA or item.get("marker") != name or item.get("source_sha") != source_sha:
                _error(errors, f"marker identity mismatch: {name}")
            times[name] = int(item["wall_time_ns"])
            if name == "record_written" and (item.get("facts", {}).get("record_path") != record.get("record_path") or item.get("facts", {}).get("record_sha256") != _sha256_file(Path(str(record.get("record_path"))))):
                _error(errors, "record_written marker does not close the record")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            _error(errors, f"marker invalid {name}: {exc}")
    values = [times[name] for name in MARKERS if name in times]
    if len(values) != len(MARKERS) or values != sorted(values) or len(set(values)) != len(values):
        _error(errors, "marker times are not strictly increasing")
    if lifecycle.get("release_order") != [
        "source_rhs",
        "retained_window",
        "krylov_result",
        "solver_stack",
        "recovery",
        "bundle",
    ]:
        _error(errors, "release order is not the recorded P0 order")
    return times


def _check_watchdog(
    record: Mapping[str, Any], compact_path: Path, raw_dir: Path, marker_times: Mapping[str, int], errors: list[str], gates: list[str], warnings: list[str]
) -> dict[str, Any]:
    try:
        compact = _read_json(compact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"watchdog compact unreadable: {exc}")
        return {}
    if not isinstance(compact, Mapping):
        _error(errors, "watchdog compact is not an object")
        return {}
    if compact.get("schema") != WATCHDOG_SCHEMA:
        _error(errors, "watchdog schema mismatch")
    if compact.get("source_sha") != record.get("provenance", {}).get("source_sha") or compact.get("worker_command") != record.get("command"):
        _error(errors, "watchdog source/command binding mismatch")
    if compact.get("worker_raw_dir") != str(raw_dir) or compact.get("worker_record") != record.get("record_path"):
        _error(errors, "watchdog worker path binding mismatch")
    if compact.get("watchdog_poll_seconds") != 0.25 or compact.get("watchdog_rss_limit_bytes") != COLD_RSS_LIMIT:
        _error(errors, "watchdog poll/RSS authority is not fixed")
    raw_path = Path(str(compact.get("watchdog_raw", ""))).resolve()
    log_path = Path(str(compact.get("watchdog_log", ""))).resolve()
    if not raw_path.is_file() or not log_path.is_file() or _inside(raw_path, raw_dir) or _inside(log_path, raw_dir):
        _error(errors, "watchdog raw/log paths are missing or inside worker raw_dir")
        return compact
    if compact.get("raw_sha256") != _sha256_file(raw_path):
        _error(errors, "watchdog raw SHA mismatch")
    rows: list[Mapping[str, Any]] = []
    try:
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line:
                item = json.loads(line, parse_constant=_reject_constant)
                if not isinstance(item, Mapping):
                    raise ValueError("watchdog row is not an object")
                rows.append(item)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"watchdog raw invalid: {exc}")
        return compact
    rss: list[int] = []
    swaps: list[int] = []
    walls: list[int] = []
    readable: list[bool] = []
    timeline: list[dict[str, int]] = []
    for index, row in enumerate(rows):
        try:
            tree = row["authority"]["process_tree"]
            wall = int(row["wall_time_ns"])
            value = int(tree["rss_bytes"])
            swap = int(tree["swap_bytes"])
            status = tree["all_status_readable"]
            if not isinstance(status, bool) or value < 0 or swap < 0:
                raise ValueError("invalid process tree authority")
            if walls and wall <= walls[-1]:
                _error(errors, "watchdog raw wall times are not source-ordered")
            walls.append(wall)
            rss.append(value)
            swaps.append(swap)
            readable.append(status)
            timeline.append(
                {
                    "wall_time_ns": wall,
                    "rss_bytes": value,
                    "swap_bytes": swap,
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            _error(errors, f"watchdog sample {index} malformed: {exc}")
    if not rss:
        _error(errors, "watchdog has no valid process-tree samples")
        return compact
    if compact.get("sample_count") != len(rows) or compact.get("all_status_readable") is not all(readable):
        _error(errors, "watchdog sample/readability summary mismatch")
    if not all(readable):
        _gate(gates, "watchdog process-tree authority was unreadable")
    if compact.get("peak_process_tree_rss_bytes") != max(rss) or compact.get("max_process_tree_swap_bytes") != max(swaps):
        _error(errors, "watchdog RSS/swap summary mismatch")
    if compact.get("natural_exit") is not True or compact.get("no_orphan") is not True or compact.get("returncode") != 0:
        _gate(gates, "watchdog lifecycle did not close naturally")
    peak = max(rss)
    if peak >= COLD_RSS_LIMIT:
        _gate(gates, "process-tree RSS reached the 2GB hard line")
    elif peak >= RETAINED_WARNING:
        warnings.append("process-tree RSS is in the 1.8-2.0GB warning interval")
    if max(swaps) != 0:
        _gate(gates, "process-tree swap is nonzero")
    ready = marker_times.get("retained_ready", -1)
    observed = marker_times.get("retained_observed", -1)
    window = [value for wall, value in zip(walls, rss) if ready <= wall <= observed]
    window_swap = [value for wall, value in zip(walls, swaps) if ready <= wall <= observed]
    if not window:
        _error(errors, "watchdog has no retained-window sample")
    elif max(window) >= COLD_RSS_LIMIT or max(window_swap) != 0:
        _gate(gates, "retained-window process-tree resource Gate failed")
    return {
        "compact": compact,
        "sample_count": len(rows),
        "peak_process_tree_rss_bytes": peak,
        "max_process_tree_swap_bytes": max(swaps),
        "retained_sample_count": len(window),
        "retained_peak_process_tree_rss_bytes": max(window, default=None),
        "retained_max_process_tree_swap_bytes": max(window_swap, default=None),
        "_timeline": timeline,
    }


def _check_release_observation(
    marker_times: Mapping[str, int],
    timeline: list[Mapping[str, int]],
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    names = (
        "krylov_destroyed",
        "solver_stack_release_started",
        "solver_stack_release_complete",
        "release_observation",
        "recovery_started",
        "recovery_built",
    )
    if any(name not in marker_times for name in names):
        _error(errors, "solver-stack release markers are incomplete")
        return {}
    destroyed, started, complete, observed, recovery_started, recovery = (
        marker_times[name] for name in names
    )
    if not destroyed < started < complete < observed < recovery_started <= recovery:
        _error(errors, "recovery did not follow the solver-stack release observation")
        return {}
    if recovery_started - observed < RELEASE_OBSERVATION_NS:
        _error(errors, "release observation window is shorter than one second")
    before = [sample for sample in timeline if sample["wall_time_ns"] <= started]
    after = [
        sample
        for sample in timeline
        if observed <= sample["wall_time_ns"] < recovery_started
    ]
    if not before or not after:
        _error(errors, "watchdog lacks release-before/release-after samples")
        return {}
    before_sample = before[-1]
    after_sample = after[0]
    if before_sample["swap_bytes"] != 0 or after_sample["swap_bytes"] != 0:
        _gate(gates, "release-before/release-after process-tree swap is nonzero")
    if after_sample["rss_bytes"] >= before_sample["rss_bytes"]:
        _gate(gates, "process-tree RSS did not decrease after solver-stack release")
    return {
        "release_before": dict(before_sample),
        "release_after": dict(after_sample),
        "rss_delta_bytes": int(after_sample["rss_bytes"] - before_sample["rss_bytes"]),
        "rss_delta_relative": float(
            (after_sample["rss_bytes"] - before_sample["rss_bytes"])
            / max(float(before_sample["rss_bytes"]), np.finfo(float).tiny)
        ),
    }


def _check_reference_export(
    recovery: Mapping[str, Any],
    raw_dir: Path,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    export = recovery.get("field_export")
    if not isinstance(export, Mapping) or export.get("full3d_reference_exported") is not True:
        _gate(gates, "official complex E/H reference export is missing")
        return {}
    official_dir = raw_dir / "official"
    archive = Path(str(export.get("full3d_reference_archive", ""))).resolve()
    metadata_path = Path(str(export.get("full3d_reference_metadata", ""))).resolve()
    expected_archive = (official_dir / "full3d_reference_samples.npz").resolve()
    expected_metadata = (official_dir / "full3d_reference_samples.json").resolve()
    if archive != expected_archive or metadata_path != expected_metadata:
        _error(errors, "reference E/H artifact paths are not the official worker paths")
        return {}
    if not archive.is_file() or not metadata_path.is_file():
        _gate(gates, "official complex E/H reference artifacts are missing")
        return {}
    archive_sha = _sha256_file(archive)
    if export.get("full3d_reference_archive_sha256") != archive_sha:
        _error(errors, "reference E/H archive SHA is not closed")
    if export.get("full3d_reference_archive_bytes") != archive.stat().st_size:
        _error(errors, "reference E/H archive size is not closed")
    try:
        metadata = _read_json(metadata_path)
        with np.load(archive, allow_pickle=False) as payload:
            array_keys = sorted(payload.files)
            required_keys = {"x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m"}
            if not required_keys.issubset(payload.files):
                raise KeyError(f"missing reference arrays: {sorted(required_keys - set(payload.files))}")
            x_nm = np.asarray(payload["x_nm"])
            y_nm = np.asarray(payload["y_nm"])
            z_nm = np.asarray(payload["z_nm"])
            electric = np.asarray(payload["E_V_per_m"])
            magnetic = np.asarray(payload["H_A_per_m"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _gate(gates, f"official complex E/H reference artifacts are unreadable: {exc}")
        return {}
    expected_shape = (5, 20, 40, 3)
    expected_x = (np.arange(40, dtype=np.float64) + 0.5) * 50.0 / 40.0
    expected_y = (np.arange(20, dtype=np.float64) + 0.5) * 25.0 / 20.0
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("schema_version") != 1
        or metadata.get("archive") != archive.name
        or metadata.get("archive_sha256") != archive_sha
        or metadata.get("archive_bytes") != archive.stat().st_size
        or list(metadata.get("array_shape_z_y_x_component", ())) != list(expected_shape)
        or metadata.get("point_count") != 4000
        or export.get("full3d_reference_array_shape") != list(expected_shape)
        or export.get("full3d_reference_point_count") != 4000
        or export.get("full3d_reference_plane_z_nm") != [10.0, 30.0, 60.0, 90.0, 110.0]
        or x_nm.ndim != 1
        or y_nm.ndim != 1
        or z_nm.ndim != 1
        or x_nm.dtype != np.dtype(np.float64)
        or y_nm.dtype != np.dtype(np.float64)
        or x_nm.size != 40
        or y_nm.size != 20
        or not np.array_equal(x_nm, expected_x)
        or not np.array_equal(y_nm, expected_y)
        or not np.array_equal(z_nm, np.asarray([10.0, 30.0, 60.0, 90.0, 110.0]))
        or not np.all(np.isfinite(x_nm))
        or not np.all(np.isfinite(y_nm))
        or not np.all(np.isfinite(z_nm))
        or electric.dtype != np.dtype(np.complex128)
        or magnetic.dtype != np.dtype(np.complex128)
        or electric.shape != expected_shape
        or magnetic.shape != expected_shape
        or not np.all(np.isfinite(electric))
        or not np.all(np.isfinite(magnetic))
    ):
        _gate(gates, "official complex E/H reference facts are not closed")
    return {
        "archive_sha256": archive_sha,
        "archive_bytes": int(archive.stat().st_size),
        "array_keys": array_keys,
        "coordinate_sizes": {"x_nm": int(x_nm.size), "y_nm": int(y_nm.size), "z_nm": int(z_nm.size)},
        "plane_z_nm": z_nm.tolist(),
        "array_shape": list(electric.shape),
        "point_count": 4000,
    }


def _check_significant_inventory(
    recovery: Mapping[str, Any],
    raw_dir: Path,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    semantics = recovery.get("significant_gate_semantics")
    expected = {
        "identity_set_count": 12,
        "power_gate_count": 12,
        "complex_boundary_amplitude_gate_count": 12,
        "same_identity_set": True,
        "definition": SIGNIFICANT_GATE_DEFINITION,
        "authority": "benchmarks/task035d_case097_checker.py::significant_12_power_and_12_amplitude",
    }
    if not isinstance(semantics, Mapping) or any(semantics.get(key) != value for key, value in expected.items()):
        _error(errors, "significant diffraction gate semantics are not frozen")
    path = raw_dir / "official" / "diffraction_orders_3d.json"
    try:
        payload = _read_json(path)
        orders = payload["orders"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        _gate(gates, f"diffraction mode/order inventory is unreadable: {exc}")
        return {}
    required = {
        "m", "n", "polarization", "alpha", "gamma", "beta_top", "beta_bottom",
        "reflected_amplitude", "transmitted_amplitude", "R", "T",
    }
    if not isinstance(orders, list) or not orders or any(
        not isinstance(row, Mapping) or not required.issubset(row) for row in orders
    ):
        _gate(gates, "diffraction mode/order identity inventory is incomplete")
        return {}
    keys: list[list[Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    complex_fields = (
        "beta_top",
        "beta_bottom",
        "reflected_amplitude",
        "transmitted_amplitude",
    )
    for index, row in enumerate(orders):
        m, n, polarization = row["m"], row["n"], row["polarization"]
        key = (m, n, polarization)
        valid_key = type(m) is int and type(n) is int and isinstance(polarization, str)
        if not valid_key or key in seen:
            _gate(gates, f"diffraction canonical order key is invalid or duplicated at row {index}")
        if valid_key:
            seen.add(key)
        keys.append([m, n, polarization])
        if any(not _finite_number(row[name]) for name in ("alpha", "gamma", "R", "T")):
            _gate(gates, f"diffraction scalar inventory is non-finite at row {index}")
        try:
            values = [_complex_json_value(row[name]) for name in complex_fields]
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            _gate(gates, f"diffraction complex inventory is invalid at row {index}: {exc}")
        else:
            if any(not np.isfinite(value.real) or not np.isfinite(value.imag) for value in values):
                _gate(gates, f"diffraction complex inventory is non-finite at row {index}")
    count = recovery.get("diffraction_channel_count")
    metrics = recovery.get("diffraction_metrics")
    if type(count) is not int or count != len(orders):
        _gate(gates, "diffraction channel count does not equal the raw order inventory")
    payload_metrics = payload.get("metrics") if isinstance(payload, Mapping) else None
    if isinstance(payload_metrics, Mapping) and "diffraction_channel_count" in payload_metrics:
        if type(payload_metrics["diffraction_channel_count"]) is not int or payload_metrics["diffraction_channel_count"] != len(orders):
            _gate(gates, "diffraction JSON metrics channel count does not equal the raw order inventory")
    if isinstance(metrics, Mapping) and "diffraction_channel_count" in metrics:
        if type(metrics["diffraction_channel_count"]) is not int or metrics["diffraction_channel_count"] != len(orders):
            _gate(gates, "diffraction metrics channel count does not equal the raw order inventory")
    return {
        "order_count": len(orders),
        "identity_sha256": _stable_sha(keys),
        "first_keys": keys[:3],
        "semantics": dict(semantics) if isinstance(semantics, Mapping) else {},
    }


def _check_scalar_direct_authority(
    port: Mapping[str, Any] | None,
    volume: Mapping[str, Any] | None,
    errors: list[str],
    gates: list[str],
    physics_blockers: list[str],
    authority_blockers: list[str] | None = None,
) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "path": str(DIRECT_AUTHORITY_PATH),
        "sha256": DIRECT_AUTHORITY_SHA256,
        "absolute_total_tolerance": TOTAL_FULL3D_TOL,
    }
    if not isinstance(port, Mapping) or not isinstance(volume, Mapping):
        return facts
    try:
        authority = _read_json(DIRECT_AUTHORITY_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        physics_blockers.append(f"exact 1-degree scalar direct authority is unreadable: {exc}")
        return facts
    if _sha256_file(DIRECT_AUTHORITY_PATH) != DIRECT_AUTHORITY_SHA256:
        _error(errors, "tracked 1-degree scalar direct authority SHA mismatch")
        return facts
    profile = authority.get("profile") if isinstance(authority, Mapping) else None
    expected_profile = {
        "degree": 6, "h_nm": 10.0, "wavelength_nm": 13.5, "polarization": "s",
        "grazing_deg": 1.0, "requested_modes": 120, "mpi_size": 8,
    }
    if not isinstance(profile, Mapping) or any(profile.get(key) != value for key, value in expected_profile.items()):
        _error(errors, "tracked direct authority profile is not the exact 1-degree p6/h10 identity")
        return facts
    raw_evidence = authority.get("raw_evidence")
    if not isinstance(raw_evidence, Mapping):
        _error(errors, "tracked direct authority raw evidence facts are missing")
        raw_evidence = {}
    cases = authority.get("cases") if isinstance(authority, Mapping) else None
    case = next((item for item in cases or () if isinstance(item, Mapping) and item.get("phi_deg") == 0.0), None)
    if not isinstance(case, Mapping):
        _error(errors, "tracked direct authority has no phi=0 case")
        return facts
    values: dict[str, Mapping[str, float]] = {}
    for name in ("direct_M120", "direct_M160"):
        item = case.get(name)
        gate = item.get("gate") if isinstance(item, Mapping) else None
        rta = item.get("rta") if isinstance(item, Mapping) else None
        if (
            not isinstance(gate, Mapping)
            or gate.get("status") != "task037c_direct_robustness_pass"
            or gate.get("return_code") != 0
            or gate.get("pass") is not True
            or not isinstance(rta, Mapping)
            or any(not _finite_number(rta.get(key)) for key in ("R", "T", "A", "A_volume"))
        ):
            _gate(gates, f"{name} scalar direct authority is not a pass")
            continue
        values[name] = rta
    if set(values) != {"direct_M120", "direct_M160"}:
        return facts
    totals = ("R", "T", "A", "A_volume")
    pair = {
        key: {
            "abs_delta": abs(float(values["direct_M120"][key]) - float(values["direct_M160"][key])),
            "pass": abs(float(values["direct_M120"][key]) - float(values["direct_M160"][key])) <= TOTAL_FULL3D_TOL,
        }
        for key in totals
    }
    current = {
        "R": port.get("R_total"),
        "T": port.get("T_total"),
        "A": port.get("A_balance"),
        "A_volume": volume.get("A_volume_total"),
    }
    comparisons = {}
    for name, direct in values.items():
        comparisons[name] = {}
        for key in totals:
            delta = (
                abs(float(current[key]) - float(direct[key]))
                if _finite_number(current[key])
                else float(np.finfo(float).max)
            )
            comparisons[name][key] = {"abs_delta": delta, "pass": delta <= TOTAL_FULL3D_TOL}
    scalar_pass = all(item["pass"] for item in pair.values()) and all(
        item["pass"] for row in comparisons.values() for item in row.values()
    )
    if not scalar_pass:
        _gate(gates, "physical R/T/A/A_volume totals exceed frozen 1e-5 direct tolerance")
    facts.update({
        "profile": dict(profile),
        "direct_M120_vs_M160": pair,
        "current_vs_direct": comparisons,
        "scalar_pass": scalar_pass,
    })
    if raw_evidence.get("arrays_included") is not True:
        (authority_blockers if authority_blockers is not None else physics_blockers).append(
            "tracked 1-degree authority has scalar R/T/A/A_volume only; selected E/H, near-field, "
            "and same-identity 12 power plus 12 complex boundary-amplitude arrays are unavailable"
        )
    return facts


def _check_recovery(
    record: Mapping[str, Any],
    raw_dir: Path,
    gates: list[str],
    errors: list[str],
    physics_blockers: list[str],
    physics_output_failures: list[str] | None = None,
    final_override: float | None = None,
    authority_blockers: list[str] | None = None,
) -> dict[str, Any]:
    physical = record.get("physical")
    recovery = physical.get("recovery") if isinstance(physical, Mapping) else None
    final = (
        final_override
        if final_override is not None
        else record.get("krylov", {}).get("final_true_residual")
        if isinstance(record.get("krylov"), Mapping)
        else None
    )
    if not isinstance(recovery, Mapping) or not _finite_number(final):
        _error(errors, "physical recovery facts are missing")
        return {}
    if float(final) <= RESIDUAL_LIMIT:
        if recovery.get("status") != "complete" or recovery.get("field_model") != "total_field" or recovery.get("electric_finite") is not True or recovery.get("auxiliary_finite") is not True:
            _gate(gates, "P0 recovery was not completed after residual convergence")
        port = recovery.get("port_metrics")
        volume = recovery.get("volume_metrics")
        diffraction = recovery.get("diffraction_metrics")
        if not isinstance(port, Mapping) or not isinstance(volume, Mapping) or not isinstance(diffraction, Mapping):
            _gate(gates, "official physical output metrics are incomplete")
        else:
            for key in ("R_total", "T_total", "R_plus_T", "A_balance", "R00_s", "R00_p"):
                if not _finite_number(port.get(key)):
                    _gate(gates, f"official port metric is non-finite: {key}")
            if not _finite_number(volume.get("A_volume_total")) or not isinstance(recovery.get("diffraction_channel_count"), int) or recovery["diffraction_channel_count"] <= 0:
                _gate(gates, "official volume/diffraction metrics are incomplete")
            closure = volume.get("energy_closure_error_port_volume")
            if not _finite_number(closure) or abs(float(closure)) > 1.0e-6:
                _gate(gates, "port/volume energy closure is not within the frozen tolerance")
            if (
                _finite_number(port.get("R_plus_T"))
                and abs(float(port["R_plus_T"]) - float(port["R_total"]) - float(port["T_total"])) > 1.0e-12
            ):
                _gate(gates, "R_plus_T does not close R_total and T_total")
            if (
                _finite_number(port.get("A_balance"))
                and abs(float(port["A_balance"]) - 1.0 + float(port["R_total"]) + float(port["T_total"])) > 1.0e-12
            ):
                _gate(gates, "A_balance does not close the port powers")
            for key in ("dtn_port_top_mode_count", "dtn_port_bottom_mode_count"):
                if not isinstance(port.get(key), int) or port[key] <= 0:
                    _gate(gates, f"official DtN mode inventory is incomplete: {key}")
        output_failures = physics_output_failures if physics_output_failures is not None else gates
        field_export = _check_reference_export(recovery, raw_dir, errors, output_failures)
        inventory = _check_significant_inventory(recovery, raw_dir, errors, output_failures)
        scalar_direct = _check_scalar_direct_authority(
            port, volume, errors, gates, physics_blockers, authority_blockers
        )
        official_dir = raw_dir / "official"
        artifacts = recovery.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            _error(errors, "official output artifact facts are missing")
        else:
            for item in artifacts:
                if not isinstance(item, Mapping):
                    _error(errors, "official artifact fact is malformed")
                    continue
                path = (official_dir / str(item.get("relative_path", ""))).resolve()
                if not _inside(path, official_dir) or not path.is_file() or item.get("bytes") != path.stat().st_size or item.get("sha256") != _sha256_file(path):
                    _error(errors, "official artifact bytes/SHA is not closed")
    else:
        if recovery.get("status") != "not_run":
            _error(errors, "recovery status is inconsistent with the residual")
    checked = dict(recovery)
    if float(final) <= RESIDUAL_LIMIT:
        checked["field_export_check"] = field_export
        checked["significant_inventory_check"] = inventory
        checked["scalar_direct_authority"] = scalar_direct
    return checked


def _j4_hex_sha(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        char in "0123456789abcdef" for char in value
    )


def _j4_compiler(fact: Mapping[str, Any], root_pid: int) -> bool:
    if int(fact.get("pid", -1)) == int(root_pid):
        return False
    names = {str(fact.get("comm", ""))}
    names.update(Path(token).name for token in str(fact.get("cmdline", "")).split())
    return bool(names & J4_COMPILER_NAMES)


def _j4_markers(record: Mapping[str, Any], errors: list[str]) -> dict[str, int]:
    paths = record.get("paths")
    if not isinstance(paths, Mapping):
        _error(errors, "J4 parent paths are missing")
        return {}
    root = Path(str(paths.get("artifact_root", ""))).resolve()
    marker_dir = Path(str(paths.get("marker_dir", ""))).resolve()
    if marker_dir != root / "markers" or not marker_dir.is_dir():
        _error(errors, "J4 marker directory is not the parent-owned directory")
        return {}
    manifest_path = Path(str(paths.get("marker_manifest", ""))).resolve()
    if not manifest_path.is_file():
        _error(errors, "J4 marker manifest is missing")
    elif not isinstance(record.get("markers"), Mapping) or record["markers"].get("manifest_sha256") != _sha256_file(manifest_path):
        _error(errors, "J4 marker manifest SHA mismatch")
    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"J4 marker manifest is unreadable: {exc}")
        return {}
    if not isinstance(manifest, list):
        _error(errors, "J4 marker manifest is not a list")
    times: dict[str, int] = {}
    actual_paths = sorted(marker_dir.glob("*.json"), key=lambda path: path.name)
    if len(actual_paths) != len(J4_MARKER_ORDER):
        _error(errors, "J4 marker inventory is not exact")
    for name in J4_MARKER_ORDER:
        marker_path = marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json"
        try:
            marker = _read_json(marker_path)
            facts = marker.get("facts")
            expected_stage = (
                "j4-p0r-solver"
                if 20 <= J4_PARENT_MARKER_INDEX[name] <= 38
                else "j4-p0r-parent"
            )
            if (
                marker.get("schema") != V14_MARKER_SCHEMA
                or marker.get("name") != name
                or marker.get("marker_index") != J4_PARENT_MARKER_INDEX[name]
                or not isinstance(facts, Mapping)
                or facts.get("stage") != expected_stage
                or facts.get("artifact_root") != str(root)
                or facts.get("cache_dir") != str(root / "jit_cache")
                or facts.get("source_sha") != record.get("source_sha")
            ):
                _error(errors, f"J4 marker identity mismatch: {name}")
            times[name] = int(marker["timestamp_ns"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            _error(errors, f"J4 marker invalid {name}: {exc}")
    values = [times[name] for name in J4_MARKER_ORDER if name in times]
    if values != sorted(values) or len(set(values)) != len(values):
        _error(errors, "J4 marker timestamps are not strictly increasing")
    if isinstance(manifest, list):
        expected_manifest = [
            {"name": name, "path": str(marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json"), "sha256": _sha256_file(marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json")}
            for name in J4_MARKER_ORDER
            if (marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json").is_file()
        ]
        if manifest != expected_manifest:
            _error(errors, "J4 marker manifest entries do not close marker files")
    return times


def _j4_worker_markers(worker: Mapping[str, Any], root: Path, errors: list[str]) -> dict[str, int]:
    raw_dir = Path(str(worker.get("raw_dir", ""))).resolve()
    marker_dir = raw_dir / "markers"
    if raw_dir != root / "worker_raw":
        _error(errors, "J4 worker raw marker directory is not parent-bound")
    lifecycle = worker.get("lifecycle")
    if (
        not isinstance(lifecycle, Mapping)
        or lifecycle.get("marker_relative_dir") != "markers"
        or lifecycle.get("marker_schema") != J4_WORKER_MARKER_SCHEMA
        or lifecycle.get("marker_names") != list(J4_WORKER_MARKERS)
        or lifecycle.get("retained_dwell_seconds") != 2.0
        or lifecycle.get("release_observation_seconds") != 1.0
    ):
        _error(errors, "J4 worker raw marker inventory is not exact")
    expected_paths = [marker_dir / f"{name}.json" for name in J4_WORKER_MARKERS]
    actual_paths = sorted(marker_dir.glob("*.json"), key=lambda path: path.name) if marker_dir.is_dir() else []
    if [path.name for path in actual_paths] != sorted(path.name for path in expected_paths):
        _error(errors, "J4 worker raw marker files are not the exact inventory")
    times: dict[str, int] = {}
    for name, marker_path in zip(J4_WORKER_MARKERS, expected_paths):
        try:
            marker = _read_json(marker_path)
            if (
                marker.get("schema") != J4_WORKER_MARKER_SCHEMA
                or marker.get("marker") != name
                or marker.get("source_sha") != worker.get("source_sha")
                or not isinstance(marker.get("facts"), Mapping)
            ):
                raise ValueError("worker marker identity is not exact")
            timestamp = marker.get("wall_time_ns")
            if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp <= 0:
                raise ValueError("worker marker timestamp is invalid")
            if name == "solve_started" and marker["facts"].get("max_it") != 20:
                raise ValueError("J4 solve_started marker max_it is not 20")
            times[name] = timestamp
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            _error(errors, f"J4 worker marker invalid {name}: {exc}")
    values = [times[name] for name in J4_WORKER_MARKERS if name in times]
    if values != sorted(values) or len(values) != len(set(values)):
        _error(errors, "J4 worker raw marker timestamps are not strictly increasing")
    if times.get("retained_observed", -1) - times.get("retained_ready", -1) < RETAINED_DWELL_NS:
        _error(errors, "J4 worker retained dwell is shorter than two seconds")
    if times.get("release_observation", -1) - times.get("solver_stack_release_complete", -1) < RELEASE_OBSERVATION_NS:
        _error(errors, "J4 worker release observation is shorter than one second")
    return times


def _j4_process_summary(
    path: Path,
    marker_times: Mapping[str, int],
    solver_pid: int,
    worker_marker_times: Mapping[str, int],
    errors: list[str],
    gates: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {}
    sample_count = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    parent_pid: int | None = None
    all_readable = True
    peak_rss: int | None = None
    max_swap: int | None = None
    compiler_peak = 0
    observed: set[int] = set()
    solve_count = 0
    solve_peak: int | None = None
    teardown_count = 0
    teardown_last: int | None = None
    retained_window_count = 0
    retained_window_solver_count = 0
    release_window_count = 0
    release_window_solver_count = 0
    stage_order: list[str] = []
    try:
        stream = path.open(encoding="utf-8")
    except OSError as exc:
        _error(errors, f"J4 process JSONL is unreadable: {exc}")
        return {}, {}
    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line, parse_constant=_reject_constant)
                if not isinstance(row, Mapping):
                    raise ValueError("sample is not an object")
                stage = str(row["stage"])
                timestamp = int(row["timestamp_ns"])
                root_pid = int(row["root_pid"])
                rss = row.get("rss_bytes")
                swap = row.get("swap_bytes")
                members = row.get("members")
                if (
                    row.get("schema") != SAMPLE_SCHEMA
                    or stage not in J4_PROCESS_STAGES
                    or not isinstance(row.get("all_status_readable"), bool)
                    or not isinstance(rss, int)
                    or isinstance(rss, bool)
                    or rss < 0
                    or not isinstance(swap, int)
                    or isinstance(swap, bool)
                    or swap < 0
                    or not isinstance(members, list)
                ):
                    raise ValueError("sample facts are incomplete")
                pids = {int(fact["pid"]) for fact in members}
                compiler_count = sum(_j4_compiler(fact, root_pid) for fact in members)
                if int(row.get("compiler_descendant_count", -1)) != compiler_count:
                    raise ValueError("compiler descendant count does not match members")
                if int(row.get("rss_bytes", -1)) != sum(int(fact["rss_bytes"]) for fact in members):
                    raise ValueError("RSS aggregate does not match members")
                if int(row.get("swap_bytes", -1)) != sum(int(fact["swap_bytes"]) for fact in members):
                    raise ValueError("swap aggregate does not match members")
                if stage == "precompile:parent-only" and pids != {root_pid}:
                    raise ValueError("parent-only sample contains a descendant")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                _error(errors, f"J4 process sample {line_number} invalid: {exc}")
                continue
            sample_count += 1
            parent_pid = root_pid if parent_pid is None else parent_pid
            if root_pid != parent_pid:
                _error(errors, "J4 process sample root PID changed")
            if first_timestamp_ns is None:
                first_timestamp_ns = timestamp
            last_timestamp_ns = timestamp
            if row["all_status_readable"] is not True:
                all_readable = False
            peak_rss = rss if peak_rss is None else max(peak_rss, rss)
            max_swap = swap if max_swap is None else max(max_swap, swap)
            compiler_peak = max(compiler_peak, compiler_count)
            if not stage_order or stage_order[-1] != stage:
                stage_order.append(stage)
            if stage in {"precompile:parent-only", "solver"} and compiler_count != 0:
                _gate(gates, f"J4 {stage} sample observed a compiler descendant")
            descendants = pids - {root_pid}
            observed.update(descendants)
            fact = stages.setdefault(
                stage,
                {
                    "sample_count": 0,
                    "first_timestamp_ns": None,
                    "last_timestamp_ns": None,
                    "peak_rss_bytes": None,
                    "max_swap_bytes": None,
                    "all_status_readable": True,
                    "compiler_descendant_peak": 0,
                    "observed_descendant_pids": set(),
                    "last_sample": None,
                },
            )
            fact["sample_count"] += 1
            fact["first_timestamp_ns"] = timestamp if fact["first_timestamp_ns"] is None else fact["first_timestamp_ns"]
            fact["last_timestamp_ns"] = timestamp
            fact["peak_rss_bytes"] = rss if fact["peak_rss_bytes"] is None else max(fact["peak_rss_bytes"], rss)
            fact["max_swap_bytes"] = swap if fact["max_swap_bytes"] is None else max(fact["max_swap_bytes"], swap)
            fact["all_status_readable"] = fact["all_status_readable"] and row["all_status_readable"] is True
            fact["compiler_descendant_peak"] = max(fact["compiler_descendant_peak"], compiler_count)
            fact["observed_descendant_pids"].update(descendants)
            fact["last_sample"] = row
            if marker_times.get("solve_started", 0) <= timestamp <= marker_times.get("solve_complete", -1):
                solve_count += 1
                solve_peak = rss if solve_peak is None else max(solve_peak, rss)
            if timestamp >= marker_times.get("solve_complete", 1 << 63):
                teardown_count += 1
                teardown_last = rss
            retained_ready = worker_marker_times.get("retained_ready")
            retained_observed = worker_marker_times.get("retained_observed")
            if retained_ready is not None and retained_observed is not None and retained_ready <= timestamp <= retained_observed:
                retained_window_count += 1
                if solver_pid in pids:
                    retained_window_solver_count += 1
            release_complete = worker_marker_times.get("solver_stack_release_complete")
            release_observation = worker_marker_times.get("release_observation")
            if release_complete is not None and release_observation is not None and release_complete <= timestamp <= release_observation:
                release_window_count += 1
                if solver_pid in pids:
                    release_window_solver_count += 1
    if not all_readable:
        _gate(gates, "J4 process-tree authority was unreadable")
    if max_swap not in (None, 0):
        _gate(gates, "J4 process-tree swap is nonzero")
    if peak_rss is None or peak_rss >= COLD_RSS_LIMIT:
        _gate(gates, "J4 process-tree RSS reached the 2GB hard line")
    if stage_order != list(J4_PROCESS_STAGES):
        _error(errors, "J4 process stages are not strictly serial")
    for stage in J4_PROCESS_STAGES:
        if stage not in stages:
            _error(errors, f"J4 process stage is missing: {stage}")
        else:
            stages[stage]["observed_descendant_pids"] = sorted(stages[stage]["observed_descendant_pids"])
    if "solver" in stages and solver_pid not in stages["solver"]["observed_descendant_pids"]:
        _error(errors, "solver PID was not observed in the solver stage")
    if "solver" in stages and stages["solver"]["compiler_descendant_peak"] != 0:
        _gate(gates, "solver stage observed a compiler descendant")
    if solve_count == 0:
        _error(errors, "J4 process timeline has no solve window sample")
    if teardown_count == 0 or teardown_last is None:
        _error(errors, "J4 process timeline has no post-solve teardown sample")
    summary = {
        "sample_path": str(path),
        "sample_sha256": _sha256_file(path),
        "sample_count": sample_count,
        "parent_pid": parent_pid,
        "first_timestamp_ns": first_timestamp_ns,
        "last_timestamp_ns": last_timestamp_ns,
        "all_status_readable": all_readable,
        "peak_rss_bytes": peak_rss,
        "max_swap_bytes": max_swap,
        "compiler_descendant_peak": compiler_peak,
        "observed_descendant_pids": sorted(observed),
        "last_sample": stages.get(J4_PROCESS_STAGES[-1], {}).get("last_sample"),
        "stage_summaries": stages,
    }
    metrics = {
        "solve_sample_count": solve_count,
        "solve_window_peak_rss_bytes": solve_peak,
        "teardown_sample_count": teardown_count,
        "teardown_last_rss_bytes": teardown_last,
        "retained_window_sample_count": retained_window_count,
        "retained_window_solver_sample_count": retained_window_solver_count,
        "release_window_sample_count": release_window_count,
        "release_window_solver_sample_count": release_window_solver_count,
    }
    return summary, metrics


def _j4_compare_summary(
    recorded: Mapping[str, Any], actual: Mapping[str, Any], errors: list[str]
) -> None:
    for key in (
        "sample_count",
        "parent_pid",
        "first_timestamp_ns",
        "last_timestamp_ns",
        "all_status_readable",
        "peak_rss_bytes",
        "max_swap_bytes",
        "compiler_descendant_peak",
        "observed_descendant_pids",
    ):
        if recorded.get(key) != actual.get(key):
            _error(errors, f"J4 process summary mismatch: {key}")
    recorded_stages = recorded.get("stage_summaries")
    actual_stages = actual.get("stage_summaries")
    if not isinstance(recorded_stages, Mapping) or not isinstance(actual_stages, Mapping):
        _error(errors, "J4 stage summaries are missing")
        return
    for stage in J4_PROCESS_STAGES:
        left = recorded_stages.get(stage)
        right = actual_stages.get(stage)
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            _error(errors, f"J4 stage summary is missing: {stage}")
            continue
        for key in (
            "sample_count",
            "first_timestamp_ns",
            "last_timestamp_ns",
            "peak_rss_bytes",
            "max_swap_bytes",
            "all_status_readable",
            "compiler_descendant_peak",
            "observed_descendant_pids",
        ):
            if left.get(key) != right.get(key):
                _error(errors, f"J4 stage summary mismatch: {stage}/{key}")


def _j4_compare_monitor(
    monitor: Mapping[str, Any], stage: Mapping[str, Any], label: str, errors: list[str]
) -> None:
    for monitor_key, stage_key in (
        ("sample_count", "sample_count"),
        ("peak_rss_bytes", "peak_rss_bytes"),
        ("max_swap_bytes", "max_swap_bytes"),
        ("all_status_readable", "all_status_readable"),
        ("compiler_descendant_peak", "compiler_descendant_peak"),
        ("observed_descendant_pids", "observed_descendant_pids"),
    ):
        if monitor.get(monitor_key) != stage.get(stage_key):
            _error(errors, f"J4 {label} monitor/stage mismatch: {monitor_key}")
    if (
        not isinstance(monitor.get("started_ns"), int)
        or not isinstance(monitor.get("ended_ns"), int)
        or not isinstance(stage.get("first_timestamp_ns"), int)
        or not isinstance(stage.get("last_timestamp_ns"), int)
        or not (
            monitor["started_ns"]
            <= stage["first_timestamp_ns"]
            <= stage["last_timestamp_ns"]
            <= monitor["ended_ns"]
        )
    ):
        _error(errors, f"J4 {label} monitor bounds do not contain its samples")
    pid = monitor.get("pid")
    observed = stage.get("observed_descendant_pids")
    if not isinstance(pid, int) or not isinstance(observed, list) or pid not in observed:
        _error(errors, f"J4 {label} PID was not observed in its parent stage")


def _j4_path(value: Any, root: Path, errors: list[str], label: str) -> Path | None:
    if not isinstance(value, str):
        _error(errors, f"J4 {label} path is missing")
        return None
    path = Path(value).resolve()
    if not _inside(path, root) or not path.is_file():
        _error(errors, f"J4 {label} path is missing or escapes artifact root")
        return None
    return path


def _j4_check_children(
    record: Mapping[str, Any], root: Path, cache_dir: Path, errors: list[str], gates: list[str]
) -> tuple[list[str], dict[str, Any]]:
    children = record.get("children")
    if not isinstance(children, list) or [child.get("group") for child in children if isinstance(child, Mapping)] != list(J4_GROUP_COUNTS):
        _error(errors, "J4 precompile children are not the fixed serial groups")
        return [], {}
    cache = record.get("cache")
    initial = cache.get("initial_manifest") if isinstance(cache, Mapping) else None
    initial_path = (
        _j4_path(initial.get("path"), root, errors, "initial cache manifest")
        if isinstance(initial, Mapping)
        else None
    )
    try:
        initial_manifest = initial.get("manifest") if isinstance(initial, Mapping) else None
        actual_initial = _read_json(initial_path) if initial_path is not None else {}
        if (
            not isinstance(initial_manifest, Mapping)
            or actual_initial != initial_manifest
            or initial_manifest.get("cache_dir") != str(cache_dir)
            or initial_manifest.get("artifacts") != []
            or initial_manifest.get("artifact_count") != 0
            or initial.get("sha256") != _sha256_file(initial_path)
        ):
            raise ValueError("initial cache manifest is not empty or closed")
        previous = initial_manifest
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        _error(errors, f"J4 initial cache manifest invalid: {exc}")
        previous = {"artifacts": []}
    modules: list[str] = []
    stage_monitor_data: dict[str, Any] = {}
    for child in children:
        if not isinstance(child, Mapping):
            _error(errors, "J4 child entry is not an object")
            continue
        group = str(child.get("group"))
        expected_count = J4_GROUP_COUNTS.get(group)
        if expected_count is None:
            _error(errors, f"J4 unknown child group: {group}")
            continue
        record_path = _j4_path(child.get("record_path"), root, errors, f"{group} record")
        if record_path is None:
            continue
        if child.get("record_sha256") != _sha256_file(record_path):
            _error(errors, f"J4 child record SHA mismatch: {group}")
        try:
            child_record = _read_json(record_path)
            facts = child_record["facts"]["group_facts"]
            if (
                child_record.get("schema") != "task038.full3d.jit-split.child-record.v1"
                or child_record.get("source_sha") != record.get("source_sha")
                or facts.get("compiled_form_count") != expected_count
                or facts.get("form_roles") != list(J4_GROUP_ROLES[group])
            ):
                raise ValueError("child group facts are not exact")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            _error(errors, f"J4 child record invalid: {group}: {exc}")
        manifest_path = _j4_path(child.get("cache_manifest_path"), root, errors, f"{group} cache manifest")
        if manifest_path is None:
            continue
        if child.get("cache_manifest_sha256") != _sha256_file(manifest_path):
            _error(errors, f"J4 child manifest SHA mismatch: {group}")
        try:
            current = _read_json(manifest_path)
            artifacts = current["artifacts"]
            if current.get("cache_dir") != str(cache_dir) or current.get("artifact_count") != len(artifacts):
                raise ValueError("cache manifest count or identity is not closed")
            if len({item["relative_path"] for item in artifacts}) != len(artifacts):
                raise ValueError("cache manifest contains duplicate artifact paths")
            for item in artifacts:
                relative = Path(str(item["relative_path"]))
                target = (cache_dir / relative).resolve()
                if (
                    not relative.parts
                    or relative.is_absolute()
                    or not _inside(target, cache_dir)
                    or not target.is_file()
                    or item.get("bytes") != target.stat().st_size
                    or item.get("sha256") != _sha256_file(target)
                ):
                    raise ValueError("cache manifest artifact is not closed against the cache")
            current_map = {item["relative_path"]: item for item in artifacts}
            previous_map = {
                item["relative_path"]: item for item in previous.get("artifacts", [])
            }
            added = [item for name, item in current_map.items() if name not in previous_map]
            if any(previous_map[name] != current_map.get(name) for name in previous_map):
                raise ValueError("cache is not monotonic")
            expected_added = child.get("added_artifacts")
            if expected_added != added:
                raise ValueError("cache delta artifacts are not closed")
            names = [str(item["relative_path"]) for item in added]
            added_modules = sorted(Path(name).name for name in names if name.endswith(".so"))
            if len(added_modules) != expected_count or len(set(added_modules)) != expected_count:
                raise ValueError("cache delta has the wrong distinct module count")
            if child.get("new_module_basenames") != added_modules:
                raise ValueError("new module basename list is not closed")
            modules.extend(added_modules)
            previous = current
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            _error(errors, f"J4 cache manifest invalid: {group}: {exc}")
        process = child.get("process")
        if not isinstance(process, Mapping):
            _error(errors, f"J4 child process monitor is missing: {group}")
        else:
            if (
                process.get("natural_exit") is not True
                or process.get("returncode") != 0
                or process.get("process_group_gone") is not True
                or process.get("required_sigkill") is not False
                or process.get("max_swap_bytes") != 0
                or process.get("peak_rss_bytes") is None
                or int(process["peak_rss_bytes"]) >= COLD_RSS_LIMIT
                or process.get("all_status_readable") is not True
            ):
                _gate(gates, f"J4 child process/resource Gate failed: {group}")
            stage_monitor_data[f"precompile:{group}"] = process
    if len(modules) != 11 or len(set(modules)) != 11:
        _error(errors, "J4 precompile inventory is not exactly 11 distinct modules")
    return sorted(modules), {"monitors": stage_monitor_data}


def _j4_check_worker(
    record: Mapping[str, Any],
    root: Path,
    cache_dir: Path,
    precompiled_modules: list[str],
    errors: list[str],
    gates: list[str],
    numerical: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    solver = record.get("solver")
    if not isinstance(solver, Mapping):
        _error(errors, "J4 worker entry is missing")
        return {}, {}
    worker_path = _j4_path(solver.get("record_path"), root, errors, "worker record")
    if worker_path is None:
        return {}, {}
    parent_paths = record.get("paths")
    if not isinstance(parent_paths, Mapping) or parent_paths.get("worker_record") != str(worker_path):
        _error(errors, "J4 worker record path is not parent-bound")
    try:
        worker = _read_json(worker_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"J4 worker record is unreadable: {exc}")
        return {}, {}
    if (
        worker.get("schema") != J4_WORKER_SCHEMA
        or worker.get("workflow") != J4_WORKFLOW
        or worker.get("source_sha") != record.get("source_sha")
        or worker.get("branch") != BRANCH
        or "passed" in worker
        or "classification" in worker
    ):
        _error(errors, "J4 worker identity/schema is not raw-facts-only")
    expected_python = str(Path(__file__).resolve().parents[1] / ".venv/bin/python")
    provenance = worker.get("provenance")
    command = worker.get("command")
    raw_dir = Path(str(worker.get("raw_dir", ""))).resolve()
    if (
        worker.get("record_path") != str(worker_path)
        or raw_dir != root / "worker_raw"
        or worker.get("checkpoint_root") != str(root / "checkpoints")
    ):
        _error(errors, "J4 worker paths are not parent-bound")
    if (
        worker.get("stage") != "j4-p0r-solver"
        or not isinstance(command, list)
        or command[:3] != [expected_python, "-m", MODULE]
        or _option(command, "--workflow") != J4_WORKFLOW
        or _option(command, "--raw-dir") != str(raw_dir)
        or _option(command, "--jit-cache-dir") != str(cache_dir)
        or _option(command, "--v14-marker-dir") != str(root / "markers")
    ):
        _error(errors, "J4 worker command is not the physical P0 worker")
    worker_marker_times = _j4_worker_markers(worker, root, errors)
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("python_executable") != expected_python
        or provenance.get("python_prefix") != str(Path(expected_python).parent.parent)
        or provenance.get("parent_owned_cache") is not True
        or provenance.get("jit_cache_dir") != str(cache_dir)
        or provenance.get("command") != worker.get("command")
    ):
        _error(errors, "J4 worker interpreter/cache ownership provenance is not exact")
    ffcx_calls = worker.get("ffcx_calls")
    call_files: list[str] = []
    if not isinstance(ffcx_calls, list) or len(ffcx_calls) != 11:
        _error(errors, "J4 worker did not observe exactly 11 FFCx calls")
    else:
        for index, call in enumerate(ffcx_calls):
            if not isinstance(call, Mapping):
                _error(errors, f"J4 FFCx cache-hit call is invalid: {index}")
                continue
            module_file = Path(str(call.get("module_file", ""))).resolve()
            if (
                not isinstance(call.get("module_name"), str)
                or not call.get("module_name")
                or call.get("index") != index
                or call.get("code") != [None, None]
                or call.get("cache_hit") is not True
                or not _inside(module_file, cache_dir)
                or module_file.suffix != ".so"
                or not module_file.is_file()
            ):
                _error(errors, f"J4 FFCx cache-hit call is invalid: {index}")
            call_files.append(module_file.name)
    if len(set(call_files)) != 11 or set(call_files) != set(precompiled_modules):
        _error(errors, "J4 solver cache-hit module set does not equal precompiled inventory")
    settings = worker.get("settings")
    krylov = worker.get("krylov")
    if (
        not isinstance(settings, Mapping)
        or any(
            settings.get(key) != value
            for key, value in {
                "max_it": 20,
                "restart": 20,
                "cycle_max_it": 20,
                "residual_replacement": True,
                "zero_initial_guess": True,
                "checkpoint_writer": False,
                "checkpoint_interval": None,
                "first_checkpoint_iteration": None,
                "stop_on_true_residual": False,
                "official_recovery": False,
            }.items()
        )
    ):
        _error(errors, "J4 qualification settings are not exact")
    if not isinstance(krylov, Mapping):
        _error(errors, "J4 Krylov facts are missing")
        return worker, {}
    cycles = krylov.get("cycles")
    if (
        not isinstance(cycles, list)
        or len(cycles) != 1
        or not isinstance(cycles[0], Mapping)
        or cycles[0].get("start_iteration") != 0
        or cycles[0].get("end_iteration") != 20
        or cycles[0].get("iterations") != 20
        or cycles[0].get("ksp_destroyed") is not True
        or krylov.get("iterations") != 20
        or krylov.get("ksp_destroy_count") != 1
        or krylov.get("checkpoint_facts") != []
    ):
        _gate(gates, "J4 did not complete exactly one 20-step restart-20 cycle")
    else:
        cycle = cycles[0]
        count_names = (
            "matvec_count",
            "pc_apply_count",
            "explicit_action_count",
            "driver_explicit_action_count",
            "rhs_action_count",
            "final_action_recheck_count",
            "extra_action_count",
            "explicit_action_count_total",
            "action_calls_total",
        )
        counts: dict[str, int] = {}
        for name in count_names:
            value = krylov.get(name) if name != "matvec_count" and name != "pc_apply_count" else cycle.get(name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                _error(errors, f"J4 counter is not a non-negative integer: {name}")
            else:
                counts[name] = value
        if len(counts) == len(count_names):
            if counts["matvec_count"] != krylov.get("matvec_count"):
                _error(errors, "J4 matvec total does not equal the cycle ledger")
            if counts["pc_apply_count"] != krylov.get("pc_apply_count"):
                _error(errors, "J4 PC total does not equal the cycle ledger")
            pc_facts = krylov.get("pc_apply_facts")
            if not isinstance(pc_facts, list) or counts["pc_apply_count"] != len(pc_facts):
                _error(errors, "J4 PC total does not equal pc_apply_facts")
            if counts["explicit_action_count"] != counts["driver_explicit_action_count"]:
                _error(errors, "J4 driver explicit count is not internally closed")
            if counts["extra_action_count"] != counts["rhs_action_count"] + counts["final_action_recheck_count"]:
                _error(errors, "J4 extra action count is not internally closed")
            if counts["explicit_action_count_total"] != counts["driver_explicit_action_count"] + counts["extra_action_count"]:
                _error(errors, "J4 explicit action total is not internally closed")
            if counts["action_calls_total"] != counts["matvec_count"] + counts["explicit_action_count_total"]:
                _error(errors, "J4 action call total is not internally closed")
    npz_facts = worker.get("npz")
    npz_path = raw_dir / "physical_probe.npz"
    expected_probe_roles = [
        "rhs_before",
        "rhs_after",
        "final_solution",
        "final_action",
        "final_residual",
        "one_action_output",
        "one_pc_output",
    ]
    if (
        not npz_path.is_file()
        or not isinstance(npz_facts, Mapping)
        or npz_facts.get("relative_path") != "physical_probe.npz"
        or npz_facts.get("bytes") != npz_path.stat().st_size
        or npz_facts.get("sha256") != _sha256_file(npz_path)
        or npz_facts.get("roles") != expected_probe_roles
    ):
        _error(errors, "J4 worker probe archive is missing or SHA-invalid")
        return worker, {}
    try:
        with np.load(npz_path, allow_pickle=False) as archive:
            expected_keys = set(expected_probe_roles)
            if set(archive.files) != expected_keys:
                raise ValueError("J4 probe archive keys are not exact")
            arrays = {name: np.asarray(archive[name]) for name in archive.files}
            if any(array.dtype != np.dtype(np.complex128) for array in arrays.values()):
                raise ValueError("J4 probe archive dtype is not complex128")
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"J4 probe archive is invalid: {exc}")
        return worker, {}
    rhs_before = arrays["rhs_before"]
    rhs_after = arrays["rhs_after"]
    final_residual = arrays["final_residual"]
    final_action = arrays["final_action"]
    if not all(array.ndim == 1 and np.all(np.isfinite(array)) for array in arrays.values()):
        numerical.append("J4 probe arrays are non-finite or not vectors")
    if not np.array_equal(rhs_before, rhs_after):
        numerical.append("J4 physical RHS changed during the cycle")
    if not np.allclose(final_residual, rhs_before - final_action, rtol=1e-12, atol=1e-14):
        numerical.append("J4 final residual is not b-Ax")
    rhs_norm = float(np.linalg.norm(rhs_before))
    raw_relative = float(np.linalg.norm(final_residual) / max(rhs_norm, np.finfo(float).tiny))
    initial_relative = float(krylov.get("initial_true_residual", 0.0))
    if not np.isclose(initial_relative, 1.0, rtol=1.0e-12, atol=1.0e-14):
        _error(errors, "J4 zero-start initial residual is not the RHS norm")
    rho20 = raw_relative
    if not np.isfinite(rho20) or rho20 > 1.0 + 1.0e-12:
        numerical.append(f"J4 rho20 exceeds 1+1e-12: {rho20}")
    for name, values in arrays.items():
        if name != "rhs_before" and values.size != rhs_before.size:
            _error(errors, f"J4 probe vector size mismatch: {name}")
    source = worker.get("source")
    source_facts = source.get("facts") if isinstance(source, Mapping) else None
    if (
        not isinstance(source_facts, Mapping)
        or source_facts.get("source_sha") != record.get("source_sha")
        or source.get("generation") != "dtn_port_modal_physical_rhs"
        or source.get("role") != "physical_maxwell_rhs"
        or source.get("phase_application") != "finalized_floquet_mpc_once"
    ):
        _error(errors, "J4 physical RHS/source identity is not closed")
    slaves = source.get("owned_slave_indices", []) if isinstance(source, Mapping) else []
    if not isinstance(slaves, list) or any(not isinstance(item, int) or item < 0 or item >= rhs_before.size for item in slaves):
        _error(errors, "J4 owned slave index facts are invalid")
    else:
        for name, values in arrays.items():
            if slaves and float(np.max(np.abs(values[slaves]))) > 1.0e-12:
                numerical.append(f"J4 owned slave identity rows are nonzero: {name}")
    j4 = worker.get("j4")
    if not isinstance(j4, Mapping) or j4.get("one_action_probe_count") != 1 or j4.get("one_pc_probe_count") != 1:
        _error(errors, "J4 one-action/one-PC probe count is not exactly one")
    else:
        for name, array_name in (("one_action_output", "one_action_output"), ("one_pc_output", "one_pc_output")):
            facts = j4.get(name)
            if not isinstance(facts, Mapping) or facts.get("array_sha256") != _array_sha(arrays[array_name]):
                _error(errors, f"J4 probe fact is not closed: {name}")
        if not _finite_number(j4.get("final_explicit_true_residual")) or not np.isclose(float(j4["final_explicit_true_residual"]), raw_relative, rtol=1.0e-12, atol=1.0e-14):
            _error(errors, "J4 final explicit residual fact does not match the raw arrays")
        if not _finite_number(j4.get("rho20")) or not np.isclose(float(j4["rho20"]), rho20, rtol=1e-12, atol=1e-14):
            _error(errors, "J4 rho20 fact does not match the raw arrays")
    recovery = worker.get("physical", {}).get("recovery") if isinstance(worker.get("physical"), Mapping) else None
    if not isinstance(recovery, Mapping) or recovery.get("status") != "not_run" or recovery.get("official_outputs_written") is not False:
        _error(errors, "J4 official recovery was not explicitly skipped")
    architecture = worker.get("architecture")
    expected_true = {"p3_sparse_matrix_built", "p1_sparse_matrix_built", "p1_direct_factor_built", "same_mesh_pmg_built", "streaming_dtn_action_built", "dtn_carrier_built", "physical_volume_action_built", "p6_matrix_free", "rhs_built", "outer_ksp_built", "solve_run", "bundle_destroyed_before_record"}
    expected_false = {"p6_global_aij", "high_order_global_aij", "global_dense_transfer", "numeric_allgather", "recovery_run"}
    if not isinstance(architecture, Mapping) or any(architecture.get(key) is not True for key in expected_true) or any(architecture.get(key) is not False for key in expected_false):
        _error(errors, "J4 physical architecture facts are not closed")
    physical = worker.get("physical", {}).get("audit") if isinstance(worker.get("physical"), Mapping) else None
    if not isinstance(physical, Mapping) or physical.get("volume_component_count") != 2 or physical.get("volume_components") != ["curl_curl", "complex_material_mass"] or physical.get("physical_form") != "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn":
        _error(errors, "J4 physical split audit is not exact")
    metrics = {
        "raw_relative_residual": raw_relative,
        "rho20": rho20,
        "ffcx_call_count": len(ffcx_calls) if isinstance(ffcx_calls, list) else 0,
        "worker_marker_times": worker_marker_times,
    }
    return worker, metrics


def _j5_parent_markers(record: Mapping[str, Any], errors: list[str]) -> dict[str, int]:
    paths = record.get("paths")
    if not isinstance(paths, Mapping):
        _error(errors, "J5 parent paths are missing")
        return {}
    root = Path(str(paths.get("artifact_root", ""))).resolve()
    marker_dir = Path(str(paths.get("marker_dir", ""))).resolve()
    manifest_path = Path(str(paths.get("marker_manifest", ""))).resolve()
    if marker_dir != root / "markers" or not marker_dir.is_dir():
        _error(errors, "J5 marker directory is not parent-bound")
        return {}
    if record.get("marker_schema") != V14_MARKER_SCHEMA:
        _error(errors, "J5 parent marker schema is not the shared V14 schema")
    marker_facts = record.get("markers")
    if not isinstance(marker_facts, Mapping) or marker_facts.get("names") != list(J4_MARKER_ORDER):
        _error(errors, "J5 parent marker inventory is not the complete V14 order")
        marker_facts = {}
    try:
        manifest = _read_json(manifest_path)
        if not isinstance(manifest, list):
            raise ValueError("marker manifest is not a list")
        if marker_facts.get("manifest_sha256") != _sha256_file(manifest_path):
            raise ValueError("marker manifest SHA mismatch")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        _error(errors, f"J5 marker manifest is invalid: {exc}")
        return {}
    actual_paths = sorted(marker_dir.glob("*.json"), key=lambda path: path.name)
    expected_paths = [
        marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json"
        for name in J4_MARKER_ORDER
    ]
    if [path.name for path in actual_paths] != [path.name for path in expected_paths]:
        _error(errors, "J5 parent marker files are not the exact V14 inventory")
    times: dict[str, int] = {}
    solver_start = J4_PARENT_MARKER_INDEX["positive_setup_started"]
    solver_end = J4_PARENT_MARKER_INDEX["recovery_complete"]
    for name, marker_path in zip(J4_MARKER_ORDER, expected_paths):
        try:
            marker = _read_json(marker_path)
            facts = marker.get("facts")
            index = J4_PARENT_MARKER_INDEX[name]
            expected_stage = J5_SOLVER_STAGE if solver_start <= index <= solver_end else J5_PARENT_STAGE
            if (
                marker.get("schema") != V14_MARKER_SCHEMA
                or marker.get("name") != name
                or marker.get("marker_index") != index
                or not isinstance(facts, Mapping)
                or facts.get("stage") != expected_stage
                or facts.get("artifact_root") != str(root)
                or facts.get("cache_dir") != str(root / "jit_cache")
                or facts.get("source_sha") != record.get("source_sha")
            ):
                raise ValueError("marker identity/stage is not closed")
            timestamp = marker.get("timestamp_ns")
            if type(timestamp) is not int or timestamp <= 0:
                raise ValueError("marker timestamp is invalid")
            times[name] = timestamp
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            _error(errors, f"J5 parent marker invalid {name}: {exc}")
    values = [times[name] for name in J4_MARKER_ORDER if name in times]
    if len(values) != len(J4_MARKER_ORDER) or values != sorted(values) or len(set(values)) != len(values):
        _error(errors, "J5 parent marker timestamps are not strictly increasing")
    expected_manifest = [
        {
            "name": name,
            "path": str(marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json"),
            "sha256": _sha256_file(marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json"),
        }
        for name in J4_MARKER_ORDER
        if (marker_dir / f"{J4_PARENT_MARKER_INDEX[name]:03d}_{name}.json").is_file()
    ]
    if manifest != expected_manifest:
        _error(errors, "J5 parent marker manifest does not close marker files")
    return times


def _j5_worker_markers(worker: Mapping[str, Any], root: Path, errors: list[str]) -> dict[str, int]:
    raw_dir = Path(str(worker.get("raw_dir", ""))).resolve()
    marker_dir = raw_dir / "markers"
    if raw_dir != root / "worker_raw" or not marker_dir.is_dir():
        _error(errors, "J5 worker marker directory is not parent-bound")
    lifecycle = worker.get("lifecycle")
    if (
        not isinstance(lifecycle, Mapping)
        or lifecycle.get("marker_relative_dir") != "markers"
        or lifecycle.get("marker_schema") != J5_WORKER_MARKER_SCHEMA
        or lifecycle.get("marker_names") != list(J5_WORKER_MARKERS)
        or lifecycle.get("retained_dwell_seconds") != 2.0
        or lifecycle.get("release_observation_seconds") != 1.0
        or lifecycle.get("release_order")
        != ["source_rhs", "retained_window", "krylov_result", "solver_stack", "recovery", "bundle"]
    ):
        _error(errors, "J5 worker marker lifecycle is not exact")
    expected_paths = [marker_dir / f"{name}.json" for name in J5_WORKER_MARKERS]
    actual_paths = sorted(marker_dir.glob("*.json"), key=lambda path: path.name) if marker_dir.is_dir() else []
    if [path.name for path in actual_paths] != sorted(path.name for path in expected_paths):
        _error(errors, "J5 worker marker files are not the exact inventory")
    times: dict[str, int] = {}
    for name, path in zip(J5_WORKER_MARKERS, expected_paths):
        try:
            marker = _read_json(path)
            facts = marker.get("facts")
            if (
                marker.get("schema") != J5_WORKER_MARKER_SCHEMA
                or marker.get("marker") != name
                or marker.get("source_sha") != worker.get("source_sha")
                or not isinstance(facts, Mapping)
            ):
                raise ValueError("worker marker identity is not closed")
            timestamp = marker.get("wall_time_ns")
            if type(timestamp) is not int or timestamp <= 0:
                raise ValueError("worker marker timestamp is invalid")
            if name == "solve_started" and facts.get("max_it") != MAX_IT:
                raise ValueError("J5 solve cap is not 20000")
            if name == "solve_complete" and facts.get("final_explicit_recheck") is not True:
                raise ValueError("J5 final explicit recheck is not recorded")
            if name == "record_written" and (
                facts.get("record_path") != worker.get("record_path")
                or facts.get("record_sha256") != _sha256_file(Path(str(worker.get("record_path"))))
            ):
                raise ValueError("J5 record_written marker does not close worker record")
            times[name] = timestamp
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            _error(errors, f"J5 worker marker invalid {name}: {exc}")
    values = [times[name] for name in J5_WORKER_MARKERS if name in times]
    if len(values) != len(J5_WORKER_MARKERS) or values != sorted(values) or len(set(values)) != len(values):
        _error(errors, "J5 worker marker timestamps are not strictly increasing")
    if times.get("retained_observed", -1) - times.get("retained_ready", -1) < RETAINED_DWELL_NS:
        _error(errors, "J5 retained dwell is shorter than two seconds")
    if times.get("release_observation", -1) - times.get("solver_stack_release_complete", -1) < RELEASE_OBSERVATION_NS:
        _error(errors, "J5 release observation is shorter than one second")
    if not times.get("solver_stack_release_complete", 0) < times.get("release_observation", -1) < times.get("recovery_started", -1):
        _error(errors, "J5 recovery started before release observation closed")
    return times


def _j5_check_worker(
    record: Mapping[str, Any],
    root: Path,
    cache_dir: Path,
    precompiled_modules: list[str],
    expected_source_sha: str,
    errors: list[str],
    gates: list[str],
    numerical: list[str],
    checkpoint_failures: list[str],
    recovery_failures: list[str],
    physics_blockers: list[str],
    authority_blockers: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    solver = record.get("solver")
    if not isinstance(solver, Mapping):
        _error(errors, "J5 worker entry is missing")
        return {}, {}
    worker_path = _j4_path(solver.get("record_path"), root, errors, "J5 worker record")
    if worker_path is None:
        return {}, {}
    paths = record.get("paths")
    if not isinstance(paths, Mapping) or paths.get("worker_record") != str(worker_path):
        _error(errors, "J5 worker record path is not parent-bound")
    try:
        worker = _read_json(worker_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"J5 worker record is unreadable: {exc}")
        return {}, {}
    if (
        worker.get("schema") != J5_WORKER_SCHEMA
        or worker.get("workflow") != J5_WORKFLOW
        or worker.get("stage") != J5_SOLVER_STAGE
        or worker.get("source_sha") != record.get("source_sha")
        or worker.get("branch") != BRANCH
        or "passed" in worker
        or "classification" in worker
    ):
        _error(errors, "J5 worker identity/schema is not raw-facts-only")
    raw_dir = Path(str(worker.get("raw_dir", ""))).resolve()
    checkpoint_root = Path(str(worker.get("checkpoint_root", ""))).resolve()
    expected_python = str(Path(__file__).resolve().parents[1] / ".venv/bin/python")
    command = worker.get("command")
    if (
        worker.get("record_path") != str(worker_path)
        or raw_dir != root / "worker_raw"
        or checkpoint_root != root / "checkpoints"
        or not isinstance(command, list)
        or command[:3] != [expected_python, "-m", MODULE]
        or _option(command, "--workflow") != J5_WORKFLOW
        or _option(command, "--stage") != STAGE
        or _option(command, "--case") != CASE
        or _option(command, "--source") != SOURCE
        or _option(command, "--raw-dir") != str(raw_dir)
        or _option(command, "--jit-cache-dir") != str(cache_dir)
        or _option(command, "--checkpoint-root") != str(checkpoint_root)
        or _option(command, "--record") != str(worker_path)
        or _option(command, "--expected-source-sha") != record.get("source_sha")
        or _option(command, "--expected-mpi-size") != "1"
        or _option(command, "--v14-marker-dir") != str(root / "markers")
    ):
        _error(errors, "J5 worker command/path contract is not exact")
    worker_marker_times = _j5_worker_markers(worker, root, errors)
    provenance = worker.get("provenance")
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("source_sha") != record.get("source_sha")
        or provenance.get("branch") != BRANCH
        or provenance.get("stage") != J5_SOLVER_STAGE
        or provenance.get("python_executable") != expected_python
        or provenance.get("python_prefix") != str(Path(expected_python).parent.parent)
        or provenance.get("parent_owned_cache") is not True
        or provenance.get("jit_cache_dir") != str(cache_dir)
        or provenance.get("command") != worker.get("command")
    ):
        _error(errors, "J5 worker interpreter/cache provenance is not exact")
    ffcx_calls = worker.get("ffcx_calls")
    call_files: list[str] = []
    if not isinstance(ffcx_calls, list) or len(ffcx_calls) != 11:
        _error(errors, "J5 worker did not observe exactly 11 FFCx calls")
    else:
        for index, call in enumerate(ffcx_calls):
            if not isinstance(call, Mapping):
                _error(errors, f"J5 FFCx call is invalid: {index}")
                continue
            module_file = Path(str(call.get("module_file", ""))).resolve()
            if (
                call.get("index") != index
                or not isinstance(call.get("module_name"), str)
                or not call.get("module_name")
                or call.get("code") != [None, None]
                or call.get("cache_hit") is not True
                or module_file.suffix != ".so"
                or not _inside(module_file, cache_dir)
                or not module_file.is_file()
            ):
                _error(errors, f"J5 FFCx cache-hit call is invalid: {index}")
            call_files.append(module_file.name)
    if len(call_files) != 11 or len(set(call_files)) != 11 or set(call_files) != set(precompiled_modules):
        _error(errors, "J5 solver cache-hit modules do not equal the 11 precompiled modules")
    settings = worker.get("settings")
    expected_settings = {
        "max_it": MAX_IT,
        "restart": RESTART,
        "cycle_max_it": CYCLE_MAX_IT,
        "residual_replacement": True,
        "zero_initial_guess": True,
        "checkpoint_writer": True,
        "checkpoint_interval": CHECKPOINT_INTERVAL,
        "first_checkpoint_iteration": None,
        "stop_on_true_residual": True,
        "qualification_only": False,
        "official_recovery": True,
    }
    if not isinstance(settings, Mapping) or any(settings.get(key) != value for key, value in expected_settings.items()):
        _error(errors, "J5 full-workflow settings are not exact")
    krylov = worker.get("krylov")
    if not isinstance(krylov, Mapping):
        _error(errors, "J5 Krylov facts are missing")
        return worker, {"worker_marker_times": worker_marker_times}
    cycles = krylov.get("cycles")
    ledger_valid = isinstance(cycles, list) and bool(cycles)
    cursor = 0
    matvec_total = 0
    pc_total = 0
    cycle_boundaries: list[dict[str, Any]] = []
    cycle_memory: list[int] = []
    for index, cycle in enumerate(cycles if isinstance(cycles, list) else []):
        if not isinstance(cycle, Mapping):
            ledger_valid = False
            _error(errors, f"J5 cycle is not an object: {index}")
            continue
        start = cycle.get("start_iteration")
        end = cycle.get("end_iteration")
        iterations = cycle.get("iterations")
        if (
            cycle.get("cycle_index") != index
            or type(start) is not int
            or type(end) is not int
            or type(iterations) is not int
            or start != cursor
            or end - start != iterations
            or iterations <= 0
            or iterations > CYCLE_MAX_IT
            or cycle.get("ksp_destroyed") is not True
            or (index == 0 and cycle.get("initial_guess_nonzero") is not False)
            or (index > 0 and cycle.get("initial_guess_nonzero") is not True)
        ):
            ledger_valid = False
            _error(errors, f"J5 restart-20 cycle ledger is malformed: {index}")
        if type(end) is int:
            cursor = end
        residual = cycle.get("explicit_true_residual")
        if not _finite_number(residual) or float(residual) < 0.0:
            numerical.append(f"J5 cycle explicit true residual is non-finite: {index}")
        matvec_count = cycle.get("matvec_count")
        if type(matvec_count) is not int or matvec_count < 0:
            ledger_valid = False
            _error(errors, f"J5 cycle matvec count is invalid: {index}")
        else:
            matvec_total += matvec_count
        pc_apply_count = cycle.get("pc_apply_count")
        if type(pc_apply_count) is not int or pc_apply_count < 0:
            ledger_valid = False
            _error(errors, f"J5 cycle PC count is invalid: {index}")
        else:
            pc_total += pc_apply_count
        wall_seconds = cycle.get("wall_seconds")
        if not _finite_number(wall_seconds) or float(wall_seconds) < 0.0:
            ledger_valid = False
            _error(errors, f"J5 cycle wall time is invalid: {index}")
        resource = cycle.get("resource")
        process_tree = resource.get("process_tree") if isinstance(resource, Mapping) else None
        memory = resource.get("memory_authority_bytes") if isinstance(resource, Mapping) else None
        no_swap = resource.get("job_no_swap") if isinstance(resource, Mapping) else None
        if (
            not isinstance(resource, Mapping)
            or not isinstance(process_tree, Mapping)
            or type(memory) is not int
            or memory < 0
            or type(no_swap) is not bool
            or type(process_tree.get("rss_bytes")) is not int
            or process_tree.get("rss_bytes") < 0
            or type(process_tree.get("swap_bytes")) is not int
            or process_tree.get("swap_bytes") < 0
            or process_tree.get("all_status_readable") is not True
        ):
            _error(errors, f"J5 cycle resource authority is incomplete: {index}")
        else:
            if process_tree["swap_bytes"] > 0 or no_swap is False:
                _gate(gates, f"J5 cycle process-tree swap Gate failed: {index}")
            if process_tree["rss_bytes"] >= COLD_RSS_LIMIT:
                _gate(gates, f"J5 cycle process-tree RSS Gate failed: {index}")
            cycle_memory.append(memory)
            cycle_boundaries.append(
                {
                    "cycle_index": index,
                    "iteration": end,
                    "explicit_true_residual": float(residual) if _finite_number(residual) else None,
                    "wall_seconds": float(wall_seconds) if _finite_number(wall_seconds) else None,
                    "memory_authority_bytes": memory,
                }
            )
    if (
        not ledger_valid
        or type(krylov.get("iterations")) is not int
        or krylov.get("iterations") != cursor
        or cursor > MAX_IT
    ):
        _error(errors, "J5 did not close the restart-20 iteration ledger")
    if krylov.get("matvec_count") != matvec_total or krylov.get("pc_apply_count") != pc_total:
        _error(errors, "J5 matvec/PC totals do not equal cycle sums")
    if not isinstance(cycles, list) or type(krylov.get("ksp_destroy_count")) is not int or krylov.get("ksp_destroy_count") != len(cycles):
        _error(errors, "J5 KSP destroy total does not equal cycle count")
    memory_accumulation = (
        len(cycle_memory) >= 2
        and all(left <= right for left, right in zip(cycle_memory, cycle_memory[1:]))
        and cycle_memory[-1] > cycle_memory[0]
    )
    if memory_accumulation:
        _gate(gates, "J5 cycle memory authority is monotonically accumulating")
    count_names = (
        "explicit_action_count",
        "driver_explicit_action_count",
        "rhs_action_count",
        "final_action_recheck_count",
        "extra_action_count",
        "explicit_action_count_total",
        "action_calls_total",
    )
    counts: dict[str, int] = {}
    for name in count_names:
        value = krylov.get(name)
        if type(value) is not int or value < 0:
            _error(errors, f"J5 action counter is invalid: {name}")
        else:
            counts[name] = value
    if len(counts) == len(count_names):
        if counts["explicit_action_count"] != counts["driver_explicit_action_count"]:
            _error(errors, "J5 driver explicit action count is not closed")
        if counts["extra_action_count"] != counts["rhs_action_count"] + counts["final_action_recheck_count"]:
            _error(errors, "J5 extra action count is not closed")
        if counts["explicit_action_count_total"] != counts["driver_explicit_action_count"] + counts["extra_action_count"]:
            _error(errors, "J5 explicit action total is not closed")
        if counts["action_calls_total"] != matvec_total + counts["explicit_action_count_total"]:
            _error(errors, "J5 total action calls are not closed")
    pc_facts = krylov.get("pc_apply_facts")
    if not isinstance(pc_facts, list) or len(pc_facts) != pc_total:
        _error(errors, "J5 PC apply facts do not match the cycle sum")
    else:
        for index, fact in enumerate(pc_facts):
            if not isinstance(fact, Mapping) or fact.get("apply_index") != index:
                _error(errors, f"J5 PC apply fact is malformed: {index}")
            elif fact.get("output_finite") is not True or not _finite_number(fact.get("owned_slave_max")) or float(fact["owned_slave_max"]) > 1.0e-12:
                numerical.append(f"J5 PC apply finite/owned-slave Gate failed: {index}")
    npz_facts = worker.get("npz")
    npz_path = raw_dir / "physical_probe.npz"
    expected_roles = ["rhs_before", "rhs_after", "final_solution", "final_action", "final_residual", "one_action_output", "one_pc_output"]
    if (
        not npz_path.is_file()
        or not isinstance(npz_facts, Mapping)
        or npz_facts.get("relative_path") != "physical_probe.npz"
        or npz_facts.get("bytes") != npz_path.stat().st_size
        or npz_facts.get("sha256") != _sha256_file(npz_path)
        or npz_facts.get("roles") != expected_roles
    ):
        _error(errors, "J5 physical probe archive is missing or SHA-invalid")
        return worker, {"worker_marker_times": worker_marker_times}
    try:
        with np.load(npz_path, allow_pickle=False) as archive:
            if set(archive.files) != set(expected_roles):
                raise ValueError("physical probe keys are not exact")
            arrays = {name: np.asarray(archive[name]) for name in archive.files}
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"J5 physical probe archive is unreadable: {exc}")
        return worker, {"worker_marker_times": worker_marker_times}
    if any(array.dtype != np.dtype(np.complex128) or array.ndim != 1 or not np.all(np.isfinite(array)) for array in arrays.values()):
        numerical.append("J5 physical probe arrays are not finite complex128 vectors")
    rhs_before = arrays["rhs_before"]
    rhs_after = arrays["rhs_after"]
    final_action = arrays["final_action"]
    final_residual = arrays["final_residual"]
    if not np.array_equal(rhs_before, rhs_after):
        numerical.append("J5 physical RHS changed during the full workflow")
    if not np.allclose(final_residual, rhs_before - final_action, rtol=1.0e-12, atol=1.0e-14):
        numerical.append("J5 final residual is not b-Ax")
    rhs_norm = float(np.linalg.norm(rhs_before))
    raw_relative = float(np.linalg.norm(final_residual) / max(rhs_norm, np.finfo(float).tiny))
    if not _finite_number(krylov.get("initial_true_residual")) or not np.isclose(float(krylov["initial_true_residual"]), 1.0, rtol=1.0e-12, atol=1.0e-14):
        _error(errors, "J5 zero-start initial residual is not one")
    j5 = worker.get("j5")
    if not isinstance(j5, Mapping) or j5.get("one_action_probe_count") != 1 or j5.get("one_pc_probe_count") != 1:
        _error(errors, "J5 action/PC probe facts are not exactly one each")
    elif any(
        not isinstance(j5.get(name), Mapping)
        or j5[name].get("array_sha256") != _array_sha(arrays[name])
        or j5[name].get("finite") is not True
        or not _finite_number(j5[name].get("owned_slave_max"))
        or float(j5[name]["owned_slave_max"]) > 1.0e-12
        for name in ("one_action_output", "one_pc_output")
    ):
        _error(errors, "J5 action/PC probe arrays are not closed")
    if isinstance(j5, Mapping) and set(j5).intersection(
        {
            "final_explicit_true_residual",
            "rho20",
            "actual_iterations",
            "cycle_count",
            "checkpoint_count",
            "milestone_iterations",
        }
    ):
        _error(errors, "J5 record contains derived solver facts that must be recomputed")
    if not _finite_number(raw_relative):
        numerical.append("J5 final explicit residual is non-finite")
    if isinstance(cycles, list) and cycles:
        last_residual = cycles[-1].get("explicit_true_residual") if isinstance(cycles[-1], Mapping) else None
        if _finite_number(last_residual) and not np.isclose(float(last_residual), raw_relative, rtol=1.0e-12, atol=1.0e-14):
            numerical.append("J5 final cycle residual does not match the raw arrays")
    if not _finite_number(krylov.get("final_true_residual")) or not np.isclose(float(krylov["final_true_residual"]), raw_relative, rtol=1.0e-12, atol=1.0e-14):
        numerical.append("J5 Krylov final residual does not match the raw arrays")
    if raw_relative > RESIDUAL_LIMIT:
        numerical.append(f"J5 final explicit true residual exceeds 1e-6: {raw_relative}")
    cycle_count = len(cycles) if isinstance(cycles, list) else -1
    recovery = worker.get("physical", {}).get("recovery") if isinstance(worker.get("physical"), Mapping) else None
    if raw_relative > RESIDUAL_LIMIT:
        if not isinstance(recovery, Mapping) or recovery.get("status") != "not_run":
            _error(errors, "J5 recovery was not marked not_run at the fixed cap")
    physical = worker.get("physical", {}).get("audit") if isinstance(worker.get("physical"), Mapping) else None
    if (
        not isinstance(physical, Mapping)
        or physical.get("physical_form") != "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn"
        or physical.get("volume_component_count") != 2
        or physical.get("volume_components") != ["curl_curl", "complex_material_mass"]
    ):
        _error(errors, "J5 physical split audit is not exact")
    architecture = worker.get("architecture")
    required_true = {
        "p6_matrix_free", "p3_sparse_matrix_built", "p1_sparse_matrix_built", "p1_direct_factor_built",
        "same_mesh_pmg_built", "streaming_dtn_action_built", "dtn_carrier_built", "physical_volume_action_built",
        "rhs_built", "outer_ksp_built", "solve_run", "bundle_destroyed_before_record",
    }
    required_false = {"p6_global_aij", "high_order_global_aij", "global_dense_transfer", "numeric_allgather", "qualification_only"}
    if not isinstance(architecture, Mapping) or any(architecture.get(key) is not True for key in required_true) or any(architecture.get(key) is not False for key in required_false) or architecture.get("official_recovery") is not True or architecture.get("workflow") != J5_WORKFLOW:
        _error(errors, "J5 physical architecture facts are not closed")
    source = worker.get("source")
    source_facts = source.get("facts") if isinstance(source, Mapping) else None
    if (
        not isinstance(source_facts, Mapping)
        or source_facts.get("source_sha") != expected_source_sha
        or not isinstance(source, Mapping)
        or source.get("generation") != "dtn_port_modal_physical_rhs"
        or source.get("role") != "physical_maxwell_rhs"
        or source.get("phase_application") != "finalized_floquet_mpc_once"
    ):
        _error(errors, "J5 physical RHS/source identity is not closed")
    if not isinstance(source, Mapping):
        _error(errors, "J5 physical RHS facts are missing")
    else:
        owned_slaves = source.get("owned_slave_indices")
        before = source.get("before")
        after = source.get("after")
        if (
            not isinstance(owned_slaves, list)
            or any(type(index) is not int or index < 0 or index >= rhs_before.size for index in owned_slaves)
            or not isinstance(before, Mapping)
            or before.get("array_sha256") != _array_sha(rhs_before)
            or not isinstance(after, Mapping)
            or after.get("array_sha256") != _array_sha(rhs_after)
        ):
            _error(errors, "J5 RHS before/after or owned-slave facts are not closed")
        elif owned_slaves:
            for name, values in arrays.items():
                if float(np.max(np.abs(values[owned_slaves]))) > 1.0e-12:
                    numerical.append(f"J5 owned slave identity rows are nonzero: {name}")
    checkpoints = _check_checkpoints(
        worker,
        checkpoint_root,
        expected_source_sha,
        errors,
        gates,
        checkpoint_failures,
        expected_iterations=cursor,
    )
    if raw_relative <= RESIDUAL_LIMIT:
        checked_recovery = _check_recovery(
            worker,
            raw_dir,
            recovery_failures,
            errors,
            physics_blockers,
            physics_output_failures=recovery_failures,
            final_override=raw_relative,
            authority_blockers=authority_blockers,
        )
    else:
        checked_recovery = dict(recovery) if isinstance(recovery, Mapping) else {}
        for name in ("recovery_built", "official_outputs_written"):
            marker_path = raw_dir / "markers" / f"{name}.json"
            try:
                facts = _read_json(marker_path).get("facts")
                if not isinstance(facts, Mapping) or facts.get("status") != "not_run":
                    raise ValueError("not_run marker is not explicit")
                if name == "official_outputs_written" and facts.get("artifact_count") != 0:
                    raise ValueError("not_run artifact count is not zero")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                _error(errors, f"J5 {name} not_run marker is invalid: {exc}")
    iterations = cursor
    milestone_residuals = {
        str(milestone): next(
            boundary["explicit_true_residual"]
            for boundary in cycle_boundaries
            if boundary["iteration"] == milestone
        )
        for milestone in J5_MILESTONES
        if any(boundary["iteration"] == milestone for boundary in cycle_boundaries)
    }
    metrics = {
        "raw_relative_residual": raw_relative,
        "iterations": iterations,
        "cycle_count": cycle_count,
        "cycle_boundaries": cycle_boundaries,
        "milestone_residuals": milestone_residuals,
        "memory_authority_bytes": cycle_memory,
        "memory_accumulation": memory_accumulation,
        "checkpoint_iterations": checkpoints,
        "ffcx_call_count": len(ffcx_calls) if isinstance(ffcx_calls, list) else 0,
        "worker_marker_times": worker_marker_times,
        "recovery_status": checked_recovery.get("status") if isinstance(checked_recovery, Mapping) else None,
    }
    return worker, metrics


def _j5_partial_process_summary(path: Path) -> dict[str, Any]:
    count = 0
    peak_rss: int | None = None
    max_swap: int | None = None
    all_readable = True
    try:
        stream = path.open(encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}
    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line, parse_constant=_reject_constant)
                rss = sample["rss_bytes"]
                swap = sample["swap_bytes"]
                readable = sample["all_status_readable"]
                if (
                    not isinstance(sample, Mapping)
                    or sample.get("schema") != SAMPLE_SCHEMA
                    or type(rss) is not int
                    or rss < 0
                    or type(swap) is not int
                    or swap < 0
                    or not isinstance(readable, bool)
                ):
                    raise ValueError("partial process sample facts are incomplete")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return {"error": f"line {line_number}: {exc}"}
            count += 1
            peak_rss = rss if peak_rss is None else max(peak_rss, rss)
            max_swap = swap if max_swap is None else max(max_swap, swap)
            all_readable = all_readable and readable
    if count == 0 or peak_rss is None or max_swap is None:
        return {"error": "partial process JSONL is empty"}
    return {
        "sample_count": count,
        "peak_rss_bytes": peak_rss,
        "max_swap_bytes": max_swap,
        "all_status_readable": all_readable,
    }


def _check_j5_partial(
    record: Mapping[str, Any], record_path: Path, expected_source_sha: str
) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    paths = record.get("paths")
    root = Path(str(paths.get("artifact_root", ""))).resolve() if isinstance(paths, Mapping) else Path("/")
    process = record.get("process")
    process_valid = isinstance(process, Mapping)
    if (
        record.get("partial") is not True
        or record.get("schema") != J5_PARENT_SCHEMA
        or record.get("workflow") != J5_WORKFLOW
        or record.get("stage") != J5_PARENT_STAGE
        or record.get("source_sha") != expected_source_sha
        or not _j4_hex_sha(expected_source_sha, 40)
        or record.get("branch") != BRANCH
        or not isinstance(paths, Mapping)
        or Path(str(record_path)).resolve() != root / "parent_record.json"
        or paths.get("record") != str(record_path.resolve())
        or paths.get("artifact_root") != str(root)
        or not root.is_dir()
    ):
        errors.append("J5 partial source/root contract is not closed")
    sample_path = Path(str(process.get("sample_path", ""))).resolve() if process_valid else Path("")
    raw_summary: dict[str, Any] | None = None
    if (
        not process_valid
        or sample_path != root / "parent_process.jsonl"
        or not isinstance(paths, Mapping)
        or paths.get("process_samples") != str(sample_path)
        or not sample_path.is_file()
        or process.get("sample_sha256") != _sha256_file(sample_path)
        or type(process.get("sample_count")) is not int
        or process.get("sample_count") <= 0
        or type(process.get("peak_rss_bytes")) is not int
        or process.get("peak_rss_bytes") < 0
        or type(process.get("max_swap_bytes")) is not int
        or process.get("max_swap_bytes") < 0
        or not isinstance(process.get("all_status_readable"), bool)
    ):
        errors.append("J5 partial process/raw sample facts are not closed")
    if sample_path.is_file():
        raw_summary = _j5_partial_process_summary(sample_path)
        if "error" in raw_summary:
            errors.append(f"J5 partial raw process summary is invalid: {raw_summary['error']}")
        else:
            for key in ("sample_count", "peak_rss_bytes", "max_swap_bytes", "all_status_readable"):
                if process.get(key) != raw_summary.get(key):
                    errors.append(f"J5 partial process summary does not match raw JSONL: {key}")
    error_text = record.get("error")
    if not isinstance(error_text, str) or not error_text:
        errors.append("J5 partial stop reason is missing")
    peak_rss = raw_summary.get("peak_rss_bytes") if raw_summary and "error" not in raw_summary else None
    max_swap = raw_summary.get("max_swap_bytes") if raw_summary and "error" not in raw_summary else None
    resource_stop = (
        raw_summary is not None
        and "error" not in raw_summary
        and type(peak_rss) is int
        and type(max_swap) is int
        and (
            peak_rss >= COLD_RSS_LIMIT
            or max_swap > 0
            or isinstance(error_text, str)
            and any(
                token in error_text
                for token in ("process_tree_rss_limit", "process_tree_swap")
            )
        )
    )
    if resource_stop and not errors:
        gates.append("J5 partial record contains an explicit resource hard-stop fact")
    classification = "J5_RESOURCE_GATE_FAIL" if gates else "J5_CONTRACT_INVALID"
    return {
        "checker_schema": J5_CHECKER_SCHEMA,
        "passed": False,
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "numerical_failures": [],
        "checkpoint_failures": [],
        "recovery_failures": [],
        "physics_blockers": [],
        "authority_blockers": [],
        "warnings": [],
        "identity": {"source_sha": expected_source_sha, "branch": BRANCH, "workflow": J5_WORKFLOW},
        "metrics": {"partial": True, "process_sample_sha256": process.get("sample_sha256") if process_valid else None, "raw_process": raw_summary},
        "resource": {
            "parent_peak_rss_bytes": peak_rss,
            "parent_max_swap_bytes": max_swap,
        },
    }


def check_j5_record(record_path: Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    numerical: list[str] = []
    checkpoint_failures: list[str] = []
    recovery_failures: list[str] = []
    physics_blockers: list[str] = []
    authority_blockers: list[str] = []
    warnings: list[str] = []
    try:
        record = _read_json(record_path)
        if not isinstance(record, Mapping):
            raise ValueError("parent record is not an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "checker_schema": J5_CHECKER_SCHEMA,
            "passed": False,
            "classification": "J5_CONTRACT_INVALID",
            "contract_errors": [f"J5 parent record unreadable: {exc}"],
            "gate_failures": [],
            "numerical_failures": [],
            "checkpoint_failures": [],
            "recovery_failures": [],
            "physics_blockers": [],
            "warnings": [],
            "metrics": {},
            "resource": {},
        }
    if record.get("partial") is True:
        return _check_j5_partial(record, record_path, expected_source_sha)
    paths = record.get("paths")
    root = Path(str(paths.get("artifact_root", ""))).resolve() if isinstance(paths, Mapping) else Path("/")
    cache_dir = root / "jit_cache"
    if (
        record.get("schema") != J5_PARENT_SCHEMA
        or record.get("workflow") != J5_WORKFLOW
        or record.get("stage") != J5_PARENT_STAGE
        or record.get("source_sha") != expected_source_sha
        or not _j4_hex_sha(expected_source_sha, 40)
        or record.get("branch") != BRANCH
        or not isinstance(paths, Mapping)
        or Path(str(record_path)).resolve() != root / "parent_record.json"
        or paths.get("record") != str(record_path.resolve())
        or paths.get("artifact_root") != str(root)
        or paths.get("cache_dir") != str(cache_dir)
        or paths.get("worker_record") != str(root / "worker_record.json")
        or record.get("marker_schema") != V14_MARKER_SCHEMA
        or record.get("sample_schema") != SAMPLE_SCHEMA
        or not root.is_dir()
    ):
        _error(errors, "J5 parent identity/root contract is not closed")
    identity = record.get("identity")
    if (
        not isinstance(identity, Mapping)
        or identity.get("input_sha256") != INPUT_SHA256
        or identity.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256
        or identity.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256
        or identity.get("profile") != J4_EXPECTED_PROFILE
    ):
        _error(errors, "J5 frozen identity is not exact")
    input_path = Path(str(identity.get("input_path", ""))).resolve() if isinstance(identity, Mapping) else Path("")
    if not input_path.is_file() or _sha256_file(input_path) != INPUT_SHA256:
        _error(errors, "J5 frozen input path/SHA is not closed")
    runtime = identity.get("runtime") if isinstance(identity, Mapping) else None
    expected_prefix = Path(__file__).resolve().parents[1] / ".venv"
    expected_python = expected_prefix / "bin/python"
    if (
        not isinstance(runtime, Mapping)
        or runtime.get("source_sha") != expected_source_sha
        or runtime.get("branch") != BRANCH
        or runtime.get("qualified_activation") != "1"
        or runtime.get("mpi_size") != 1
        or runtime.get("petsc_scalar_type") != "complex128"
        or runtime.get("petsc_int_type") != "int32"
        or runtime.get("python_executable") != str(expected_python)
        or runtime.get("python_prefix") != str(expected_prefix)
        or runtime.get("threads") != {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    ):
        _error(errors, "J5 parent runtime provenance is not exact")
    command = record.get("command")
    if (
        not isinstance(command, list)
        or command[:3] != [str(expected_python), "-m", "benchmarks.run_task038_full3d_jit_staged_parent"]
        or _option(command, "--workflow") != J5_WORKFLOW
        or _option(command, "--artifact-root") != str(root)
        or _option(command, "--record") != str(record_path.resolve())
        or _option(command, "--source-sha") != expected_source_sha
        or _option(command, "--input") != str(input_path)
        or _option(command, "--expected-mpi-size") != "1"
    ):
        _error(errors, "J5 parent command is not the exact full-workflow command")
    marker_times = _j5_parent_markers(record, errors)
    modules, child_metrics = _j4_check_children(record, root, cache_dir, errors, gates)
    if isinstance(record.get("cache"), Mapping) and record["cache"].get("deferred_incident_module_basenames") != []:
        _error(errors, "J5 incident RHS must be loaded by the worker, not deferred")
    worker, worker_metrics = _j5_check_worker(record, root, cache_dir, modules, expected_source_sha, errors, gates, numerical, checkpoint_failures, recovery_failures, physics_blockers, authority_blockers)
    solver = record.get("solver")
    solver_process = solver.get("process") if isinstance(solver, Mapping) else None
    solver_pid = int(solver_process.get("pid")) if isinstance(solver_process, Mapping) and type(solver_process.get("pid")) is int else -1
    process_path = Path(str(paths.get("process_samples", ""))).resolve() if isinstance(paths, Mapping) else Path("")
    worker_marker_times = worker_metrics.get("worker_marker_times", {})
    actual_process, process_metrics = _j4_process_summary(process_path, marker_times, solver_pid, worker_marker_times, errors, gates)
    if isinstance(record.get("process"), Mapping):
        _j4_compare_summary(record["process"], actual_process, errors)
    else:
        _error(errors, "J5 parent process summary is missing")
    actual_stages = actual_process.get("stage_summaries", {})
    if isinstance(actual_stages, Mapping):
        for stage_name, monitor in child_metrics.get("monitors", {}).items():
            stage = actual_stages.get(stage_name)
            if isinstance(monitor, Mapping) and isinstance(stage, Mapping):
                _j4_compare_monitor(monitor, stage, stage_name, errors)
            else:
                _error(errors, f"J5 child stage summary is missing: {stage_name}")
    if not isinstance(solver, Mapping) or not isinstance(solver_process, Mapping):
        _error(errors, "J5 solver process facts are missing")
    else:
        if (
            solver.get("workflow") != J5_WORKFLOW
            or solver.get("record_path") != str(root / "worker_record.json")
            or solver.get("record_sha256") != _sha256_file(root / "worker_record.json")
            or solver.get("cache_unchanged") is not True
            or solver_process.get("natural_exit") is not True
            or solver_process.get("returncode") != 0
            or solver_process.get("process_group_gone") is not True
            or solver_process.get("required_sigkill") is not False
            or solver_process.get("all_status_readable") is not True
            or solver_process.get("max_swap_bytes") != 0
            or solver_process.get("peak_rss_bytes") is None
            or int(solver_process["peak_rss_bytes"]) >= COLD_RSS_LIMIT
        ):
            _gate(gates, "J5 solver process/resource lifecycle Gate failed")
        stage = actual_stages.get("solver") if isinstance(actual_stages, Mapping) else None
        if isinstance(stage, Mapping):
            _j4_compare_monitor(solver_process, stage, "solver", errors)
        else:
            _error(errors, "J5 solver stage summary is missing")
    cache = record.get("cache")
    before = cache.get("before_solver") if isinstance(cache, Mapping) else None
    after = cache.get("after_solver") if isinstance(cache, Mapping) else None
    if not isinstance(cache, Mapping) or not isinstance(before, Mapping) or not isinstance(after, Mapping) or cache.get("solver_unchanged") is not True:
        _error(errors, "J5 cache before/after facts are missing or not unchanged")
    else:
        before_path = _j4_path(before.get("path"), root, errors, "J5 before-solver manifest")
        after_path = _j4_path(after.get("path"), root, errors, "J5 after-solver manifest")
        if before_path is not None and after_path is not None and (
            before.get("sha256") != _sha256_file(before_path)
            or after.get("sha256") != _sha256_file(after_path)
            or before_path.read_bytes() != after_path.read_bytes()
        ):
            _error(errors, "J5 solver changed the cache manifest")
    if process_metrics.get("retained_window_sample_count", 0) == 0 or process_metrics.get("retained_window_solver_sample_count", 0) == 0:
        _error(errors, "J5 parent JSONL has no retained-window worker sample")
    if process_metrics.get("release_window_sample_count", 0) == 0 or process_metrics.get("release_window_solver_sample_count", 0) == 0:
        _error(errors, "J5 parent JSONL has no release-observation worker sample")
    solve_peak = process_metrics.get("solve_window_peak_rss_bytes")
    if solve_peak is None or solve_peak > 1_700_000_000:
        _gate(gates, "J5 solve-ready retained RSS exceeded 1.7GB")
    elif solve_peak > 1_600_000_000:
        warnings.append(f"J5 solve-ready retained RSS is in the 1.6-1.7GB warning interval: {solve_peak}")
    teardown_last = process_metrics.get("teardown_last_rss_bytes")
    if teardown_last is not None and solve_peak is not None and teardown_last > solve_peak:
        _gate(gates, "J5 teardown RSS exceeds solve-window peak")
    passed = not errors and not gates and not numerical and not checkpoint_failures and not recovery_failures and not physics_blockers and not authority_blockers
    iterations = worker_metrics.get("iterations")
    final_residual = worker_metrics.get("raw_relative_residual")
    fixed_cap_failure = (
        type(iterations) is int
        and iterations == MAX_IT
        and _finite_number(final_residual)
        and float(final_residual) > RESIDUAL_LIMIT
    )
    classification = (
        "J5_CONTRACT_INVALID"
        if errors
        else "J5_RESOURCE_GATE_FAIL"
        if gates
        else J5_NUMERICAL_FIXED_CAP
        if numerical and fixed_cap_failure
        else J5_NUMERICAL_BEFORE_CAP
        if numerical and type(iterations) is int and iterations < MAX_IT
        else J5_NUMERICAL_GATE_FAIL
        if numerical
        else J5_CHECKPOINT_GATE_FAIL
        if checkpoint_failures
        else "J5_RECOVERY_PHYSICS_FAIL"
        if recovery_failures
        else J5_AUTHORITY_ARRAYS_MISSING
        if authority_blockers and not physics_blockers
        else "J5_RECOVERY_PHYSICS_FAIL"
        if physics_blockers
        else "J5_PASS"
    )
    return {
        "checker_schema": J5_CHECKER_SCHEMA,
        "passed": passed,
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "numerical_failures": numerical,
        "checkpoint_failures": checkpoint_failures,
        "recovery_failures": recovery_failures,
        "physics_blockers": physics_blockers,
        "authority_blockers": authority_blockers,
        "warnings": warnings,
        "identity": {"source_sha": expected_source_sha, "branch": BRANCH, "workflow": J5_WORKFLOW},
        "metrics": {"precompiled_module_count": len(modules), **worker_metrics, **process_metrics},
        "resource": {
            "parent_peak_rss_bytes": actual_process.get("peak_rss_bytes"),
            "parent_max_swap_bytes": actual_process.get("max_swap_bytes"),
            "solve_window_peak_rss_bytes": solve_peak,
            "child_metrics": child_metrics,
        },
    }


def check_j4_record(record_path: Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    numerical: list[str] = []
    warnings: list[str] = []
    try:
        record = _read_json(record_path)
        if not isinstance(record, Mapping):
            raise ValueError("parent record is not an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"checker_schema": J4_CHECKER_SCHEMA, "passed": False, "classification": "J4_CONTRACT_INVALID", "contract_errors": [f"J4 parent record unreadable: {exc}"], "gate_failures": [], "warnings": [], "metrics": {}, "resource": {}}
    paths = record.get("paths")
    root = Path(str(paths.get("artifact_root", ""))).resolve() if isinstance(paths, Mapping) else Path("/")
    cache_dir = root / "jit_cache"
    if (
        record.get("schema") != J4_PARENT_SCHEMA
        or record.get("workflow") != J4_WORKFLOW
        or record.get("stage") != "j4-p0r-parent"
        or record.get("source_sha") != expected_source_sha
        or not _j4_hex_sha(expected_source_sha, 40)
        or record.get("branch") != BRANCH
        or not isinstance(paths, Mapping)
        or paths.get("record") != str(record_path.resolve())
        or paths.get("artifact_root") != str(root)
        or paths.get("cache_dir") != str(cache_dir)
        or Path(str(record_path)).resolve() != root / "parent_record.json"
        or record.get("marker_schema") != V14_MARKER_SCHEMA
        or record.get("sample_schema") != "task038.v14.j3.process-sample.v1"
        or not root.is_dir()
    ):
        _error(errors, "J4 parent identity/root contract is not closed")
    identity = record.get("identity")
    if not isinstance(identity, Mapping) or identity.get("input_sha256") != INPUT_SHA256 or identity.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256 or identity.get("mode_manifest_sha256") != MODE_MANIFEST_SHA256 or identity.get("profile") != J4_EXPECTED_PROFILE:
        _error(errors, "J4 parent frozen identity is not exact")
    runtime = identity.get("runtime") if isinstance(identity, Mapping) else None
    expected_prefix = Path(__file__).resolve().parents[1] / ".venv"
    expected_python = expected_prefix / "bin/python"
    if (
        not isinstance(runtime, Mapping)
        or runtime.get("source_sha") != expected_source_sha
        or runtime.get("branch") != BRANCH
        or runtime.get("qualified_activation") != "1"
        or runtime.get("mpi_size") != 1
        or runtime.get("petsc_scalar_type") != "complex128"
        or runtime.get("petsc_int_type") != "int32"
        or runtime.get("python_executable") != str(expected_python)
        or runtime.get("python_prefix") != str(expected_prefix)
        or runtime.get("threads") != {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    ):
        _error(errors, "J4 parent runtime provenance is not exact")
    command = record.get("command")
    expected_python_text = str(expected_python)
    if (
        not isinstance(command, list)
        or command[:3] != [expected_python_text, "-m", "benchmarks.run_task038_full3d_jit_staged_parent"]
        or "--workflow" not in command
        or J4_WORKFLOW not in command
        or _option(command, "--artifact-root") != str(root)
        or _option(command, "--record") != str(record_path.resolve())
        or _option(command, "--source-sha") != expected_source_sha
        or _option(command, "--input") != str(Path(str(identity.get("input_path", ""))).resolve())
        or _option(command, "--expected-mpi-size") != "1"
    ):
        _error(errors, "J4 parent command is not the lexical checkout interpreter/workflow")
    marker_times = _j4_markers(record, errors)
    if marker_times and [name for name in J4_MARKER_ORDER if name in marker_times] != list(J4_MARKER_ORDER):
        _error(errors, "J4 marker sequence is not the fixed qualification sequence")
    modules, child_metrics = _j4_check_children(record, root, cache_dir, errors, gates)
    worker, worker_metrics = _j4_check_worker(record, root, cache_dir, modules, errors, gates, numerical)
    solver = record.get("solver")
    solver_process = solver.get("process") if isinstance(solver, Mapping) else None
    solver_pid = int(solver_process.get("pid")) if isinstance(solver_process, Mapping) and isinstance(solver_process.get("pid"), int) else -1
    process_path = Path(str(paths.get("process_samples", ""))).resolve() if isinstance(paths, Mapping) else Path("")
    worker_marker_times = worker_metrics.get("worker_marker_times", {})
    actual_process, process_metrics = _j4_process_summary(process_path, marker_times, solver_pid, worker_marker_times, errors, gates)
    if isinstance(record.get("process"), Mapping):
        _j4_compare_summary(record["process"], actual_process, errors)
    else:
        _error(errors, "J4 parent process summary is missing")
    actual_stages = actual_process.get("stage_summaries", {})
    if isinstance(actual_stages, Mapping):
        for stage_name, monitor in child_metrics.get("monitors", {}).items():
            stage = actual_stages.get(stage_name)
            if isinstance(monitor, Mapping) and isinstance(stage, Mapping):
                _j4_compare_monitor(monitor, stage, stage_name, errors)
            else:
                _error(errors, f"J4 child stage summary is missing: {stage_name}")
    if isinstance(solver_process, Mapping):
        if (
            solver_process.get("natural_exit") is not True
            or solver_process.get("returncode") != 0
            or solver_process.get("process_group_gone") is not True
            or solver_process.get("required_sigkill") is not False
            or solver_process.get("all_status_readable") is not True
            or solver_process.get("max_swap_bytes") != 0
            or solver_process.get("peak_rss_bytes") is None
            or int(solver_process["peak_rss_bytes"]) >= COLD_RSS_LIMIT
        ):
            _gate(gates, "J4 solver worker resource/lifecycle Gate failed")
        stage = actual_stages.get("solver") if isinstance(actual_stages, Mapping) else None
        if isinstance(stage, Mapping):
            _j4_compare_monitor(solver_process, stage, "solver", errors)
        else:
            _error(errors, "J4 solver stage summary is missing")
    before = record.get("cache", {}).get("before_solver") if isinstance(record.get("cache"), Mapping) else None
    after = record.get("cache", {}).get("after_solver") if isinstance(record.get("cache"), Mapping) else None
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        _error(errors, "J4 before/after cache manifests are missing")
    else:
        before_path = _j4_path(before.get("path"), root, errors, "before-solver manifest")
        after_path = _j4_path(after.get("path"), root, errors, "after-solver manifest")
        if before_path is not None and after_path is not None:
            if before.get("sha256") != _sha256_file(before_path) or after.get("sha256") != _sha256_file(after_path) or before_path.read_bytes() != after_path.read_bytes():
                _error(errors, "J4 solver changed the formal cache manifest")
    if process_metrics.get("retained_window_sample_count", 0) == 0 or process_metrics.get("retained_window_solver_sample_count", 0) == 0:
        _error(errors, "J4 parent JSONL has no complete retained-window sample")
    if process_metrics.get("release_window_sample_count", 0) == 0 or process_metrics.get("release_window_solver_sample_count", 0) == 0:
        _error(errors, "J4 parent JSONL has no complete release-observation sample")
    solve_peak = process_metrics.get("solve_window_peak_rss_bytes")
    if solve_peak is None or solve_peak > 1_700_000_000:
        _gate(gates, "J4 solve-ready retained RSS exceeded 1.7GB")
    elif 1_600_000_000 < solve_peak <= 1_700_000_000:
        warnings.append(
            f"J4 solve-ready retained RSS is in the 1.6-1.7GB warning interval: {solve_peak}"
        )
    teardown_last = process_metrics.get("teardown_last_rss_bytes")
    if teardown_last is not None and solve_peak is not None and teardown_last > solve_peak:
        _gate(gates, "J4 teardown RSS exceeds solve-window peak")
    if numerical:
        gates.extend(f"numerical: {item}" for item in numerical)
    passed = not errors and not gates
    classification = (
        "J4_CONTRACT_INVALID"
        if errors
        else "J4_NUMERICAL_GATE_FAIL"
        if numerical
        else "J4_RESOURCE_GATE_FAIL"
        if gates
        else "J4_P0R_PASS"
    )
    return {
        "checker_schema": J4_CHECKER_SCHEMA,
        "passed": passed,
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "warnings": warnings,
        "identity": {"source_sha": expected_source_sha, "branch": BRANCH, "workflow": J4_WORKFLOW},
        "metrics": {"precompiled_module_count": len(modules), **worker_metrics, **process_metrics},
        "resource": {"parent_peak_rss_bytes": actual_process.get("peak_rss_bytes"), "parent_max_swap_bytes": actual_process.get("max_swap_bytes"), "child_metrics": child_metrics},
    }


def check_record(record_path: Path, watchdog_compact: Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    warnings: list[str] = []
    try:
        record = _read_json(record_path)
        if not isinstance(record, Mapping):
            raise ValueError("record is not an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"checker_schema": CHECKER_SCHEMA, "passed": False, "classification": "CONTRACT_INVALID", "contract_errors": [f"record unreadable: {exc}"], "gate_failures": [], "warnings": [], "metrics": {}, "resource": {}}
    raw_dir, checkpoint_root, _provenance = _check_provenance(record, record_path, expected_source_sha, errors)
    _check_identities(record, errors)
    _check_architecture(record, errors)
    slave_indices = _check_source(record, expected_source_sha, errors)
    marker_times = _check_markers(record, raw_dir, errors)
    arrays, probe_metrics = _check_probe(record, raw_dir, slave_indices, errors, gates)
    krylov = _check_krylov(record, errors, gates)
    checkpoints = _check_checkpoints(record, checkpoint_root, expected_source_sha, errors, gates)
    resource = _check_watchdog(record, watchdog_compact, raw_dir, marker_times, errors, gates, warnings)
    physics_blockers: list[str] = []
    recovery = _check_recovery(record, raw_dir, gates, errors, physics_blockers)
    watchdog_timeline = resource.pop("_timeline", []) if isinstance(resource, dict) else []
    release = _check_release_observation(marker_times, watchdog_timeline, errors, gates)
    if marker_times.get("retained_observed", -1) - marker_times.get("retained_ready", -1) < RETAINED_DWELL_NS:
        _error(errors, "retained dwell is shorter than two seconds")
    passed = not errors and not gates and not physics_blockers
    classification = (
        "CONTRACT_INVALID"
        if errors
        else "P0_PHYSICAL_GATE_FAIL"
        if gates
        else "P0_NUMERICAL_PASS_PHYSICS_QUALIFICATION_BLOCKED"
        if physics_blockers
        else "P0_PHYSICAL_PASS_MPI1"
    )
    return {
        "checker_schema": CHECKER_SCHEMA,
        "passed": passed,
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "physics_blockers": physics_blockers,
        "warnings": warnings,
        "metrics": {
            "source": record.get("source_name"),
            "iterations": krylov.get("iterations") if isinstance(krylov, Mapping) else None,
            "final_true_residual": krylov.get("final_true_residual") if isinstance(krylov, Mapping) else None,
            "raw_relative_residual": probe_metrics.get("raw_relative"),
            "matvec_count": krylov.get("matvec_count") if isinstance(krylov, Mapping) else None,
            "pc_apply_count": krylov.get("pc_apply_count") if isinstance(krylov, Mapping) else None,
            "ksp_destroy_count": krylov.get("ksp_destroy_count") if isinstance(krylov, Mapping) else None,
            "checkpoint_iterations": checkpoints,
            "probe_array_roles": sorted(arrays),
            "release_observation": release,
            "recovery_status": recovery.get("status") if isinstance(recovery, Mapping) else None,
            "field_export_check": recovery.get("field_export_check") if isinstance(recovery, Mapping) else None,
            "significant_inventory_check": recovery.get("significant_inventory_check") if isinstance(recovery, Mapping) else None,
            "scalar_direct_authority": recovery.get("scalar_direct_authority") if isinstance(recovery, Mapping) else None,
        },
        "resource": resource,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", choices=("full", J4_WORKFLOW, J5_WORKFLOW), default="full")
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, default=None)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.workflow == J4_WORKFLOW:
        result = check_j4_record(args.record.resolve(), args.expected_source_sha)
    elif args.workflow == J5_WORKFLOW:
        result = check_j5_record(args.record.resolve(), args.expected_source_sha)
    else:
        if args.watchdog_compact is None:
            raise ValueError("--watchdog-compact is required for the full P0 workflow")
        result = check_record(args.record.resolve(), args.watchdog_compact.resolve(), args.expected_source_sha)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHECKER_SCHEMA",
    "J4_CHECKER_SCHEMA",
    "J5_CHECKER_SCHEMA",
    "check_j4_record",
    "check_j5_record",
    "check_record",
    "main",
]
