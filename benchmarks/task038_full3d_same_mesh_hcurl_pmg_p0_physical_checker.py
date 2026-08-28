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


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)


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


def _check_checkpoints(record: Mapping[str, Any], checkpoint_root: Path, expected_sha: str, errors: list[str], gates: list[str]) -> list[int]:
    krylov = record.get("krylov", {})
    iterations = krylov.get("iterations") if isinstance(krylov, Mapping) else None
    expected = list(range(CHECKPOINT_INTERVAL, int(iterations) + 1, CHECKPOINT_INTERVAL)) if type(iterations) is int and iterations > 0 else []
    facts = krylov.get("checkpoint_facts") if isinstance(krylov, Mapping) else None
    if not isinstance(facts, list) or [item.get("iteration") for item in facts if isinstance(item, Mapping)] != expected:
        _error(errors, "checkpoint schedule is not the fixed solution-only 500-step schedule")
        return expected
    identities = record.get("identities", {})
    for item in facts:
        if not isinstance(item, Mapping):
            _error(errors, "checkpoint fact is not an object")
            continue
        manifest_path = Path(str(item.get("manifest_path", ""))).resolve()
        if not _inside(manifest_path, checkpoint_root) or not manifest_path.is_file():
            _error(errors, "checkpoint manifest is missing or escapes checkpoint_root")
            continue
        if item.get("manifest_sha256") != _sha256_file(manifest_path):
            _error(errors, "checkpoint manifest SHA mismatch")
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _error(errors, f"checkpoint manifest unreadable: {exc}")
            continue
        if manifest.get("schema") != "fixed-memory-krylov.solution-checkpoint.v1" or manifest.get("iteration") != item.get("iteration") or manifest.get("source_sha") != expected_sha or manifest.get("mpi_size") != 1 or manifest.get("solution_only") is not True or manifest.get("numeric_allgather") is not False or manifest.get("vector_roles") != ["solution"]:
            _error(errors, "checkpoint manifest contract is not closed")
        for name in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
            if manifest.get(name) != identities.get(name):
                _error(errors, f"checkpoint identity mismatch: {name}")
        ranks = manifest.get("ranks")
        if not isinstance(ranks, list) or len(ranks) != 1 or not isinstance(ranks[0], Mapping) or not isinstance(ranks[0].get("solution"), Mapping):
            _error(errors, "MPI1 checkpoint shard metadata is incomplete")
            continue
        descriptor = ranks[0]["solution"]
        shard = (manifest_path.parent / str(descriptor.get("relative_path", ""))).resolve()
        if not _inside(shard, manifest_path.parent) or not shard.is_file() or descriptor.get("bytes") != shard.stat().st_size or descriptor.get("sha256") != _sha256_file(shard):
            _error(errors, "checkpoint solution shard bytes/SHA is not closed")
            continue
        try:
            values = np.asarray(np.load(shard, allow_pickle=False))
        except (OSError, ValueError, TypeError) as exc:
            _error(errors, f"checkpoint shard unreadable: {exc}")
            continue
        if values.ndim != 1 or str(values.dtype) != descriptor.get("dtype") or list(values.shape) != descriptor.get("shape") or not np.all(np.isfinite(values)):
            _gate(gates, "checkpoint solution shard dtype/shape/finite Gate failed")
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
        "semantics": dict(semantics),
    }


def _check_scalar_direct_authority(
    port: Mapping[str, Any],
    volume: Mapping[str, Any],
    errors: list[str],
    gates: list[str],
    physics_blockers: list[str],
) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "path": str(DIRECT_AUTHORITY_PATH),
        "sha256": DIRECT_AUTHORITY_SHA256,
        "absolute_total_tolerance": TOTAL_FULL3D_TOL,
    }
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
        physics_blockers.append(
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
) -> dict[str, Any]:
    physical = record.get("physical")
    recovery = physical.get("recovery") if isinstance(physical, Mapping) else None
    final = record.get("krylov", {}).get("final_true_residual") if isinstance(record.get("krylov"), Mapping) else None
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
        field_export = _check_reference_export(recovery, raw_dir, errors, gates)
        inventory = _check_significant_inventory(recovery, raw_dir, errors, gates)
        scalar_direct = _check_scalar_direct_authority(
            port, volume, errors, gates, physics_blockers
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
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_record(args.record.resolve(), args.watchdog_compact.resolve(), args.expected_source_sha)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CHECKER_SCHEMA", "check_record", "main"]
