"""Independent checker for the p6 same-mesh positive-lane raw facts.

Only JSON, JSONL, NumPy arrays, and checkpoint manifests are read here.  The
checker deliberately has no dependency on the worker, the numerical core, or
MPI/PETSc so that its residual, count, checkpoint, and watchdog decisions are
independent of the producer.
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
STAGE = "c1-p6-positive"
CASE = "p6-h10-mpi1"
SOURCES = ("random", "gradient", "curl", "checkerboard")
RECORD_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p6-positive-record.v3"
MARKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p6-positive-marker.v3"
CHECKER_SCHEMA = "task038.full3d.same-mesh-hcurl-pmg.p6-positive-check.v3"
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
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
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
    "boundary_model": "dtn_port",
    "dtn_order_policy": "auto_propagating",
    "dtn_assembly": "auxiliary",
}
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
    "bundle_destroyed",
    "record_written",
)
LEVELS = (6, 3, 1)
PAIRS = ((6, 3), (3, 1))
RESTART = 20
CYCLE_MAX_IT = 20
MAX_IT = 10_000
CHECKPOINT_INTERVAL = 500
RESIDUAL_LIMIT = 1.0e-8
COLD_RSS_LIMIT = 2_000_000_000
RETAINED_WARNING = 1_800_000_000


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


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(float(value))


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    numerator = float(np.linalg.norm(left - right))
    denominator = max(float(np.linalg.norm(right)), np.finfo(float).tiny)
    value = numerator / denominator
    return float(value) if np.isfinite(value) else float(np.finfo(float).max)


def _inside(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _gate(gates: list[str], message: str) -> None:
    gates.append(message)


def _check_provenance(
    record: Mapping[str, Any],
    record_path: Path,
    expected_source_sha: str,
    errors: list[str],
) -> tuple[Path | None, Path | None]:
    if record.get("schema") != RECORD_SCHEMA:
        _error(errors, "record schema mismatch")
    if record.get("stage") != STAGE or record.get("case") != CASE:
        _error(errors, "stage/case mismatch")
    source_name = record.get("source_name")
    if source_name not in SOURCES:
        _error(errors, "source is not one of the four frozen choices")
    if record.get("mpi_size") != 1 or record.get("branch") != BRANCH:
        _error(errors, "positive lane MPI/branch identity mismatch")
    if record.get("raw_facts_only") is not True:
        _error(errors, "worker record is not explicitly raw-facts-only")
    if any(key in record for key in ("status", "passed", "classification", "checks", "gates")):
        _error(errors, "worker record contains checker-owned decision fields")

    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        _error(errors, "provenance is not a mapping")
        return None, None

    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    checkpoint_root = Path(str(record.get("checkpoint_root", ""))).resolve()
    stored_record = Path(str(record.get("record_path", ""))).resolve()
    if not raw_dir.is_absolute() or not raw_dir.is_dir():
        _error(errors, "raw_dir is missing or not absolute")
    if stored_record != record_path.resolve():
        _error(errors, "record_path is not the checked record")
    if not checkpoint_root.is_absolute() or not checkpoint_root.is_dir():
        _error(errors, "checkpoint_root is missing or not absolute")
    jit_cache = Path(str(provenance.get("jit_cache_dir", ""))).resolve()
    if not raw_dir.is_absolute() or jit_cache != (raw_dir.parent / "jit_cache").resolve() or not jit_cache.is_dir():
        _error(errors, "isolated jit cache is not the fresh artifact sibling")
    if provenance.get("isolated_jit_cache") is not True:
        _error(errors, "isolated JIT cache provenance is missing")

    command = record.get("command")
    if not isinstance(provenance, Mapping) or not isinstance(command, list):
        _error(errors, "provenance or command is not a mapping/list")
        return raw_dir, checkpoint_root
    if provenance.get("source_sha") != expected_source_sha or record.get("command") != provenance.get("command"):
        _error(errors, "source SHA or command provenance mismatch")
    if provenance.get("branch") != BRANCH or provenance.get("clean_source_tree") is not True:
        _error(errors, "source branch/clean provenance is not closed")
    if provenance.get("qualified_activation") != "1" or provenance.get("mpi_size") != 1:
        _error(errors, "qualified ABI or MPI provenance is not closed")
    if provenance.get("petsc_scalar_type") != "complex128" or provenance.get("petsc_int_type") != "int32":
        _error(errors, "PETSc scalar/index provenance mismatch")
    threads = provenance.get("threads")
    if not isinstance(threads, Mapping) or set(threads) != {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"} or any(value != "1" for value in threads.values()):
        _error(errors, "thread provenance is not fixed to one")
    if not isinstance(provenance.get("python_executable"), str) or not Path(provenance["python_executable"]).is_absolute():
        _error(errors, "qualified Python executable is not absolute")
    abi = provenance.get("abi_modules")
    if not isinstance(abi, Mapping) or set(abi) != {"mpi4py", "petsc4py", "dolfinx", "basix"} or any(
        not isinstance(value, str) or not Path(value).is_absolute() for value in abi.values()
    ):
        _error(errors, "Linux ABI module paths are incomplete")

    input_path = Path(str(provenance.get("input_path", ""))).resolve()
    if not input_path.is_absolute() or not input_path.is_file() or not str(input_path).endswith("input/templates/full3d_iterative_example.dat"):
        _error(errors, "input path is not the frozen template")
    elif provenance.get("input_sha256") != _sha256_file(input_path):
        _error(errors, "input SHA does not match the frozen template")
    if provenance.get("input_sha256") != INPUT_SHA256:
        _error(errors, "input SHA is not the frozen Task038 input")
    if provenance.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
        _error(errors, "physical-model SHA is not the frozen Task038 model")
    for key, expected in (
        ("stage", STAGE),
        ("case", CASE),
        ("source_name", source_name),
        ("raw_dir", str(raw_dir)),
        ("checkpoint_root", str(checkpoint_root)),
        ("record_path", str(stored_record)),
        ("jit_cache_dir", str(jit_cache)),
    ):
        if provenance.get(key) != expected:
            _error(errors, f"provenance field mismatch: {key}")
    if not command or not isinstance(command[0], str) or not Path(command[0]).is_absolute():
        _error(errors, "worker command executable is not absolute")
    required = {
        "--stage": STAGE,
        "--case": CASE,
        "--source": source_name,
        "--raw-dir": str(raw_dir),
        "--jit-cache-dir": str(jit_cache),
        "--checkpoint-root": str(checkpoint_root),
        "--record": str(stored_record),
        "--expected-source-sha": expected_source_sha,
        "--expected-mpi-size": "1",
        "--input": str(input_path),
    }
    if len(command) < 3 or command[1:3] != ["-m", "benchmarks.run_task038_full3d_same_mesh_hcurl_pmg_p6_positive"]:
        _error(errors, "worker command module identity mismatch")
    else:
        tail = command[3:]
        if len(tail) != 2 * len(required) or any(
            tail[index] not in required or tail[index + 1] != required[tail[index]]
            for index in range(0, len(tail) - 1, 2)
        ) or set(tail[::2]) != set(required):
            _error(errors, "worker command arguments are not the frozen exact argv")
    return raw_dir, checkpoint_root


def _check_identities(record: Mapping[str, Any], errors: list[str]) -> None:
    identities = record.get("identities")
    if not isinstance(identities, Mapping):
        _error(errors, "identity authorities are missing")
        return
    for name in ("input_identity_authority", "operator_identity_authority"):
        authority = identities.get(name)
        digest = identities.get(name.replace("_authority", "_sha256"))
        if not isinstance(authority, Mapping) or not _hex64(digest) or digest != _stable_sha(authority):
            _error(errors, f"identity authority is missing or hash-inconsistent: {name}")
    physical = identities.get("physical_model_authority")
    physical_digest = identities.get("physical_model_authority_sha256")
    if not isinstance(physical, Mapping) or not _hex64(physical_digest) or physical_digest != _stable_sha(physical):
        _error(errors, "identity authority is missing or hash-inconsistent: physical_model_authority")
        return
    input_authority = identities.get("input_identity_authority")
    if (
        not isinstance(input_authority, Mapping)
        or input_authority.get("input_sha256") != INPUT_SHA256
        or input_authority.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256
    ):
        _error(errors, "input identity is not bound to the frozen input SHA")
    if identities.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
        _error(errors, "physical-model identity SHA is not the frozen model")
    for key, expected in EXPECTED_PHYSICAL_FIELDS.items():
        if physical.get(key) != expected:
            _error(errors, f"frozen physical configuration mismatch: {key}")
    if physical.get("input_sha256") != INPUT_SHA256:
        _error(errors, "physical authority input SHA is not frozen")
    if physical.get("physical_model_sha256") != PHYSICAL_MODEL_SHA256:
        _error(errors, "physical authority model SHA is not frozen")
    operator = identities.get("operator_identity_authority")
    if not isinstance(operator, Mapping) or operator.get("frozen_physical_configuration") != EXPECTED_PHYSICAL_FIELDS:
        _error(errors, "operator identity is not bound to the frozen physical configuration")


def _check_architecture(record: Mapping[str, Any], errors: list[str]) -> None:
    architecture = record.get("architecture")
    if not isinstance(architecture, Mapping):
        _error(errors, "architecture facts are missing")
        return
    if architecture.get("levels") != list(LEVELS) or architecture.get("pairs") != [list(pair) for pair in PAIRS]:
        _error(errors, "p6/p3/p1 levels or pairs are not fixed")
    required_true = {
        "same_physical_mesh": True,
        "p6_matrix_free": True,
        "p3_sparse_allowed": True,
        "p1_sparse_allowed": True,
        "outer_ksp_created": True,
    }
    for key, value in required_true.items():
        if architecture.get(key) is not value:
            _error(errors, f"architecture fact is not true: {key}")
    required_false = (
        "p6_global_aij",
        "high_order_global_aij",
        "global_dense_transfer",
        "global_transfer_matrix",
        "numeric_allgather",
        "p6_factor",
        "physical_solve",
        "dtn",
        "recovery",
        "source_is_pde_rhs",
    )
    for key in required_false:
        if architecture.get(key) is not False:
            _error(errors, f"forbidden architecture fact is not explicit false: {key}")
    setup_audit = architecture.get("setup_audit")
    setup_profile = setup_audit.get("profile") if isinstance(setup_audit, Mapping) else None
    setup_architecture = setup_audit.get("architecture") if isinstance(setup_audit, Mapping) else None
    if not isinstance(setup_audit, Mapping) or setup_audit.get("schema") != "task038.same_mesh_hcurl_pmg.setup.v1":
        _error(errors, "setup audit schema is not the measured p6 setup authority")
    if (
        not isinstance(setup_profile, Mapping)
        or setup_profile.get("levels") != list(LEVELS)
        or setup_profile.get("same_physical_mesh") is not True
    ):
        _error(errors, "setup audit profile is not the fixed same-mesh hierarchy")
    if not isinstance(setup_architecture, Mapping):
        _error(errors, "setup audit architecture is missing")
    else:
        setup_required_true = {"p6_matrix_free": True}
        setup_required_false = (
            "p6_global_aij",
            "global_dense_transfer",
            "global_transfer_matrix",
            "numeric_allgather",
            "p6_factor",
            "physical_solve",
            "dtn",
            "recovery",
            "high_order_global_aij",
            "outer_ksp_created",
        )
        for key, value in setup_required_true.items():
            if setup_architecture.get(key) is not value:
                _error(errors, f"setup architecture fact is not true: {key}")
        for key in setup_required_false:
            if setup_architecture.get(key) is not False:
                _error(errors, f"setup architecture fact is not explicit false: {key}")
    source = record.get("source")
    facts = source.get("facts", {}) if isinstance(source, Mapping) else {}
    if not isinstance(facts, Mapping) or facts.get("primal_role") != "full_fe" or facts.get("phase_application") != "algebraic_slave_zero_action_internal_finalized_mpc_once":
        _error(errors, "frozen source phase/provenance facts are not closed")
    if not isinstance(source, Mapping) or source.get("source_generation") != "build_frozen_fullspace_primal_source" or source.get("role") != "full_fe_primal_diagnostic_solution":
        _error(errors, "source generation/role is not closed")


def _check_probe_arrays(record: Mapping[str, Any], raw_dir: Path, errors: list[str], gates: list[str]) -> dict[str, Any]:
    descriptor = record.get("npz")
    if not isinstance(descriptor, Mapping):
        _error(errors, "positive probe NPZ descriptor is missing")
        return {}
    relative = descriptor.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        _error(errors, "positive probe path is not a safe relative artifact path")
        return {}
    path = (raw_dir / relative).resolve()
    if not _inside(path, raw_dir) or not path.is_file():
        _error(errors, "positive probe NPZ is missing or escapes raw_dir")
        return {}
    if descriptor.get("bytes") != path.stat().st_size or descriptor.get("sha256") != _sha256_file(path):
        _error(errors, "positive probe NPZ bytes/SHA mismatch")
    try:
        with np.load(path, allow_pickle=False) as data:
            names = tuple(data.files)
            arrays = {name: np.asarray(data[name], dtype=np.complex128) for name in names}
    except (OSError, ValueError, TypeError) as exc:
        _error(errors, f"positive probe NPZ unreadable: {exc}")
        return {}
    expected = (
        "source_before", "source_after", "input_before", "input_after",
        "rhs_before", "rhs_after", "rhs_repeat", "final_solution",
        "final_action", "final_true_residual",
    )
    if set(names) != set(expected) or tuple(descriptor.get("roles", ())) != expected:
        _error(errors, "positive probe NPZ roles are not exact")
    if not arrays:
        _error(errors, "positive probe NPZ is empty")
        return arrays
    shapes = {array.shape for array in arrays.values()}
    if len(shapes) != 1 or any(array.ndim != 1 for array in arrays.values()):
        _error(errors, "positive probe arrays do not share a one-dimensional layout")
        return arrays
    if any(not np.all(np.isfinite(array)) for array in arrays.values()):
        _gate(gates, "positive probe contains a non-finite value")
    source = record.get("source", {})
    source_before = arrays.get("source_before")
    source_after = arrays.get("source_after")
    input_before = arrays.get("input_before")
    input_after = arrays.get("input_after")
    if source_before is not None and source_after is not None and not np.array_equal(source_before, source_after):
        _gate(gates, "frozen source vector changed during the solve")
    if input_before is not None and input_after is not None and not np.array_equal(input_before, input_after):
        _gate(gates, "algebraic source input changed during the solve")
    if source_before is not None:
        full_facts = source.get("full_vector", {}) if isinstance(source, Mapping) else {}
        if full_facts.get("array_sha256") != _array_sha(source_before) or float(full_facts.get("norm", -1.0)) != float(np.linalg.norm(source_before)):
            _error(errors, "source vector facts do not match the raw array")
        if not np.linalg.norm(source_before) > 0.0:
            _gate(gates, "source vector is zero")
    if input_before is not None:
        algebraic_facts = source.get("algebraic_input", {}) if isinstance(source, Mapping) else {}
        if algebraic_facts.get("array_sha256") != _array_sha(input_before):
            _error(errors, "algebraic input facts do not match the raw array")
    if "rhs_before" in arrays and "rhs_after" in arrays and not np.array_equal(arrays["rhs_before"], arrays["rhs_after"]):
        _gate(gates, "RHS input changed during the solve")
    if "rhs_before" in arrays and "rhs_repeat" in arrays and _relative(arrays["rhs_before"], arrays["rhs_repeat"]) > 1.0e-13:
        _gate(gates, "repeated exact p6 action is not repeatable")
    if {"rhs_before", "final_action", "final_true_residual"} <= arrays.keys():
        recomputed = arrays["rhs_before"] - arrays["final_action"]
        if _relative(recomputed, arrays["final_true_residual"]) > 1.0e-13:
            _error(errors, "final true residual does not equal RHS minus final action")
        rhs_norm = float(np.linalg.norm(arrays["rhs_before"]))
        residual_norm = float(np.linalg.norm(arrays["final_true_residual"]))
        raw_relative = (
            residual_norm / rhs_norm
            if rhs_norm != 0.0
            else (0.0 if residual_norm == 0.0 else float(np.finfo(float).max))
        )
        if not np.isfinite(raw_relative) or raw_relative > RESIDUAL_LIMIT:
            _gate(gates, "raw RHS/final-residual relative Gate failed")
        worker_relative = (
            record.get("krylov", {}).get("final_true_residual")
            if isinstance(record.get("krylov"), Mapping)
            else None
        )
        if not _finite_number(worker_relative) or not np.isfinite(raw_relative) or abs(float(worker_relative) - raw_relative) > 1.0e-13:
            _error(errors, "worker final residual does not match the raw-array recomputation")
    indices = source.get("owned_slave_indices", []) if isinstance(source, Mapping) else []
    if not isinstance(indices, list) or any(type(value) is not int or value < 0 or value >= next(iter(shapes), (0,))[0] for value in indices):
        _error(errors, "owned slave index list is malformed")
        indices = []
    slave = np.asarray(indices, dtype=np.int64)
    for name in ("input_before", "input_after", "rhs_before", "rhs_after", "rhs_repeat", "final_solution", "final_action", "final_true_residual"):
        if name in arrays and slave.size and np.max(np.abs(arrays[name][slave])) != 0.0:
            _gate(gates, f"owned slave rows are nonzero in {name}")
    return arrays


def _check_krylov(record: Mapping[str, Any], errors: list[str], gates: list[str]) -> dict[str, Any]:
    settings = record.get("settings")
    expected_settings = {
        "ksp_type": "gmres", "pc_side": "right", "norm_type": "unpreconditioned",
        "restart": RESTART, "cycle_max_it": CYCLE_MAX_IT, "max_it": MAX_IT,
        "residual_replacement": True, "zero_initial_guess": True,
        "checkpoint_interval": CHECKPOINT_INTERVAL, "first_checkpoint_iteration": None,
        "residual_limit": RESIDUAL_LIMIT,
    }
    if not isinstance(settings, Mapping) or any(settings.get(key) != value for key, value in expected_settings.items()):
        _error(errors, "fixed Krylov settings are not closed")
    krylov = record.get("krylov")
    if not isinstance(krylov, Mapping):
        _error(errors, "Krylov raw facts are missing")
        return {}
    cycles = krylov.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        _gate(gates, "no completed restart-20 cycle is recorded")
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
        if matvec != expected_matvec or pc != iterations + 1:
            _error(errors, f"cycle {index} GMRES matvec/PC ledger is wrong")
        if cycle.get("ksp_destroyed") is not True or not _finite_number(cycle.get("explicit_true_residual")):
            _error(errors, f"cycle {index} lifecycle/residual fact is incomplete")
        if isinstance(cycle.get("resource"), Mapping) and cycle["resource"].get("scope") != "rank-root-diagnostic":
            _error(errors, f"cycle {index} resource scope is not diagnostic-only")
        cursor = end
        matvec_total += matvec
        pc_total += pc
    if type(krylov.get("iterations")) is not int or krylov.get("iterations") != cursor or cursor <= 0 or cursor > MAX_IT:
        _error(errors, "total iteration ledger is not closed")
    if krylov.get("matvec_count") != matvec_total or krylov.get("pc_apply_count") != pc_total:
        _error(errors, "total matvec/PC counts do not equal the cycle ledger")
    if krylov.get("ksp_destroy_count") != len(cycles):
        _error(errors, "KSP destroy count does not equal the cycle count")
    if krylov.get("driver_explicit_action_count") != len(cycles) + 1:
        _error(errors, "driver explicit action count is not initial-plus-cycle")
    action_fields = {
        "driver_explicit_action_count": krylov.get("driver_explicit_action_count"),
        "rhs_action_count": krylov.get("rhs_action_count"),
        "final_action_recheck_count": krylov.get("final_action_recheck_count"),
        "extra_action_count": krylov.get("extra_action_count"),
        "explicit_action_count_total": krylov.get("explicit_action_count_total"),
        "action_calls_total": krylov.get("action_calls_total"),
    }
    if not all(type(value) is int for value in action_fields.values()):
        _error(errors, "action ledger fields are not integers")
    else:
        rhs_action_count = action_fields["rhs_action_count"]
        final_action_recheck_count = action_fields["final_action_recheck_count"]
        extra_action_count = action_fields["extra_action_count"]
        driver_explicit_action_count = action_fields["driver_explicit_action_count"]
        explicit_action_count_total = action_fields["explicit_action_count_total"]
        action_calls_total = action_fields["action_calls_total"]
        if rhs_action_count != 2 or final_action_recheck_count != 1:
            _error(errors, "RHS and final-recheck action roles are not fixed")
        if extra_action_count != rhs_action_count + final_action_recheck_count:
            _error(errors, "extra action count does not close RHS/repeat/final recheck")
        if explicit_action_count_total != driver_explicit_action_count + extra_action_count:
            _error(errors, "explicit action total does not close driver and extra actions")
        if action_calls_total != matvec_total + explicit_action_count_total:
            _error(errors, "total action calls do not close matvec and explicit actions")
    final = krylov.get("final_true_residual")
    if not _finite_number(final):
        _gate(gates, "final explicit true residual is not finite")
    elif float(final) > RESIDUAL_LIMIT:
        _gate(gates, "final explicit true residual exceeds 1e-8")
    if _finite_number(krylov.get("initial_true_residual")) and abs(float(krylov["initial_true_residual"]) - 1.0) > 1.0e-13:
        _gate(gates, "zero-initial residual is not the RHS norm")
    pc_rows = krylov.get("pc_apply_facts")
    if not isinstance(pc_rows, list) or len(pc_rows) != pc_total:
        _error(errors, "per-apply V-cycle facts do not match the PC count")
    else:
        for index, row in enumerate(pc_rows):
            if not isinstance(row, Mapping) or row.get("apply_index") != index:
                _error(errors, f"V-cycle apply {index} index is malformed")
                continue
            fixed = {
                "p6_smoother_apply_count": 2,
                "p63_adjoint_count": 1,
                "p63_primal_count": 1,
                "lower_cycle_count": 1,
                "p1_solve_count": 1,
            }
            for key, expected in fixed.items():
                if row.get(key) != expected:
                    _error(errors, f"V-cycle apply {index} count mismatch: {key}")
            if row.get("output_finite") is not True or row.get("owned_slave_max") != 0.0:
                _gate(gates, f"V-cycle apply {index} output constraint/finite Gate failed")
            if not _finite_number(row.get("p1_relative_residual")) or float(row["p1_relative_residual"]) > 1.0e-11:
                _gate(gates, f"V-cycle apply {index} p1 residual Gate failed")
    return dict(krylov)


def _check_checkpoints(record: Mapping[str, Any], checkpoint_root: Path, expected_source_sha: str, errors: list[str], gates: list[str]) -> list[int]:
    krylov = record.get("krylov", {})
    iterations = krylov.get("iterations") if isinstance(krylov, Mapping) else None
    expected = list(range(CHECKPOINT_INTERVAL, int(iterations) + 1, CHECKPOINT_INTERVAL)) if type(iterations) is int and iterations > 0 else []
    facts = krylov.get("checkpoint_facts") if isinstance(krylov, Mapping) else None
    if not isinstance(facts, list) or [item.get("iteration") for item in facts if isinstance(item, Mapping)] != expected:
        _error(errors, "checkpoint list does not equal the fixed 500-step schedule")
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
        if manifest.get("schema") != "fixed-memory-krylov.solution-checkpoint.v1" or manifest.get("iteration") != item.get("iteration"):
            _error(errors, "checkpoint manifest schema/iteration mismatch")
        if manifest.get("source_sha") != expected_source_sha or manifest.get("mpi_size") != 1 or manifest.get("solution_only") is not True or manifest.get("numeric_allgather") is not False or manifest.get("vector_roles") != ["solution"]:
            _error(errors, "checkpoint solution-only/provenance facts are not closed")
        for identity_name in ("input_identity_sha256", "operator_identity_sha256", "physical_model_sha256"):
            if manifest.get(identity_name) != identities.get(identity_name):
                _error(errors, f"checkpoint identity mismatch: {identity_name}")
        ranks = manifest.get("ranks")
        if not isinstance(ranks, list) or len(ranks) != 1:
            _error(errors, "MPI1 checkpoint does not contain exactly one rank shard")
            continue
        solution = ranks[0].get("solution") if isinstance(ranks[0], Mapping) else None
        if not isinstance(solution, Mapping):
            _error(errors, "checkpoint solution descriptor is missing")
            continue
        shard = (manifest_path.parent / str(solution.get("relative_path", ""))).resolve()
        if not _inside(shard, manifest_path.parent) or not shard.is_file():
            _error(errors, "checkpoint solution shard is missing or escapes manifest")
            continue
        if solution.get("bytes") != shard.stat().st_size or solution.get("sha256") != _sha256_file(shard):
            _error(errors, "checkpoint solution shard bytes/SHA mismatch")
        try:
            values = np.load(shard, allow_pickle=False)
            values = np.asarray(values)
        except (OSError, ValueError, TypeError) as exc:
            _error(errors, f"checkpoint solution shard unreadable: {exc}")
            continue
        if str(values.dtype) != solution.get("dtype") or list(values.shape) != solution.get("shape") or not np.all(np.isfinite(values)):
            _gate(gates, "checkpoint solution shard dtype/shape/finite Gate failed")
    return expected


def _check_watchdog(record: Mapping[str, Any], compact_path: Path, raw_dir: Path, errors: list[str], gates: list[str], warnings: list[str]) -> dict[str, Any]:
    try:
        compact = _read_json(compact_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"watchdog compact unreadable: {exc}")
        return {}
    if compact.get("schema") != WATCHDOG_SCHEMA:
        _error(errors, "watchdog schema mismatch")
    if compact.get("source_sha") != record.get("provenance", {}).get("source_sha") or compact.get("worker_command") != record.get("command"):
        _error(errors, "watchdog source/command binding mismatch")
    if compact.get("worker_raw_dir") != str(raw_dir.resolve()) or compact.get("worker_record") != record.get("record_path"):
        _error(errors, "watchdog worker path binding mismatch")
    if compact.get("watchdog_poll_seconds") != 0.25 or compact.get("watchdog_rss_limit_bytes") != COLD_RSS_LIMIT:
        _error(errors, "watchdog poll or RSS authority is not fixed")
    watchdog_raw = Path(str(compact.get("watchdog_raw", ""))).resolve()
    watchdog_log = Path(str(compact.get("watchdog_log", ""))).resolve()
    if not watchdog_raw.is_file() or not watchdog_log.is_file() or _inside(watchdog_raw, raw_dir) or _inside(watchdog_log, raw_dir):
        _error(errors, "watchdog artifacts are missing or inside worker raw_dir")
        return compact
    if compact.get("raw_sha256") != _sha256_file(watchdog_raw):
        _error(errors, "watchdog raw SHA mismatch")
    rows: list[Mapping[str, Any]] = []
    try:
        for line in watchdog_raw.read_text(encoding="utf-8").splitlines():
            if line:
                item = json.loads(line, parse_constant=_reject_constant)
                if not isinstance(item, Mapping):
                    raise ValueError("watchdog sample is not an object")
                rows.append(item)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _error(errors, f"watchdog raw invalid: {exc}")
        return compact
    rss: list[int] = []
    swap: list[int] = []
    wall: list[int] = []
    readable: list[bool] = []
    for index, row in enumerate(rows):
        try:
            current_wall = int(row["wall_time_ns"])
            tree = row["authority"]["process_tree"]
            current_rss = int(tree["rss_bytes"])
            current_swap = int(tree["swap_bytes"])
            current_readable = tree["all_status_readable"]
            if not isinstance(current_readable, bool) or current_rss < 0 or current_swap < 0:
                raise ValueError("invalid process-tree authority")
            if wall and current_wall <= wall[-1]:
                _error(errors, "watchdog raw samples are not in source order")
            wall.append(current_wall)
            rss.append(current_rss)
            swap.append(current_swap)
            readable.append(current_readable)
        except (KeyError, TypeError, ValueError) as exc:
            _error(errors, f"watchdog sample {index} is malformed: {exc}")
    if not rows or not rss:
        _error(errors, "watchdog has no process-tree samples")
        return compact
    if compact.get("sample_count") != len(rows) or compact.get("all_status_readable") is not all(readable):
        _error(errors, "watchdog sample/readability summary mismatch")
    if not all(readable):
        _gate(gates, "watchdog process-tree authority was unreadable")
    if compact.get("peak_process_tree_rss_bytes") != max(rss) or compact.get("max_process_tree_swap_bytes") != max(swap):
        _error(errors, "watchdog peak/swap summary mismatch")
    if compact.get("natural_exit") is not True or compact.get("no_orphan") is not True or compact.get("returncode") != 0:
        _gate(gates, "external watchdog lifecycle did not end naturally without an orphan")
    peak = max(rss)
    if peak >= COLD_RSS_LIMIT:
        _gate(gates, "external watchdog process-tree RSS reached 2GB")
    elif peak >= RETAINED_WARNING:
        warnings.append("process-tree RSS is in the 1.8-2.0GB warning interval")
    if max(swap) != 0:
        _gate(gates, "external watchdog process-tree swap is nonzero")
    marker_dir = raw_dir / "markers"
    marker_times: dict[str, int] = {}
    for name in MARKERS:
        try:
            item = _read_json(marker_dir / f"{name}.json")
            marker_times[name] = int(item["wall_time_ns"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
    ready = marker_times.get("retained_ready", -1)
    observed = marker_times.get("retained_observed", -1)
    window = [value for stamp, value in zip(wall, rss) if ready <= stamp <= observed]
    window_swap = [value for stamp, value in zip(wall, swap) if ready <= stamp <= observed]
    if not window:
        _error(errors, "watchdog has no retained-window sample")
    elif max(window) >= COLD_RSS_LIMIT or max(window_swap) != 0:
        _gate(gates, "retained-window process-tree resource Gate failed")
    return {
        "compact": compact,
        "sample_count": len(rows),
        "peak_process_tree_rss_bytes": peak,
        "max_process_tree_swap_bytes": max(swap),
        "retained_sample_count": len(window),
        "retained_peak_process_tree_rss_bytes": max(window, default=None),
        "retained_max_process_tree_swap_bytes": max(window_swap, default=None),
    }


def _check_markers(record: Mapping[str, Any], raw_dir: Path, errors: list[str]) -> dict[str, int]:
    lifecycle = record.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or lifecycle.get("marker_relative_dir") != "markers" or lifecycle.get("marker_names") != list(MARKERS) or lifecycle.get("retained_dwell_seconds") != 2.0:
        _error(errors, "marker/lifecycle contract is not fixed")
    marker_dir = raw_dir / "markers"
    times: dict[str, int] = {}
    if not marker_dir.is_dir():
        _error(errors, "marker directory is missing")
        return times
    files = sorted(path.name for path in marker_dir.glob("*.json"))
    if files != sorted(f"{name}.json" for name in MARKERS):
        _error(errors, "marker inventory is not exact")
    for name in MARKERS:
        try:
            item = _read_json(marker_dir / f"{name}.json")
            if item.get("schema") != MARKER_SCHEMA or item.get("marker") != name or item.get("source_sha") != record.get("provenance", {}).get("source_sha"):
                _error(errors, f"marker identity mismatch: {name}")
            times[name] = int(item["wall_time_ns"])
            if name == "record_written" and (
                item.get("facts", {}).get("record_path") != record.get("record_path")
                or item.get("facts", {}).get("record_sha256") != _sha256_file(Path(record["record_path"]))
            ):
                _error(errors, "record_written marker does not close the record")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            _error(errors, f"marker invalid {name}: {exc}")
    values = [times[name] for name in MARKERS if name in times]
    if len(values) != len(MARKERS) or values != sorted(values) or len(set(values)) != len(values):
        _error(errors, "marker wall times are not strictly increasing")
    if record.get("lifecycle", {}).get("release_order") != [
        "source_rhs", "retained_window", "krylov_result", "bundle"
    ]:
        _error(errors, "release order is not the fixed lifecycle")
    return times


def check_record(record_path: Path, watchdog_compact: Path, expected_source_sha: str) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    warnings: list[str] = []
    try:
        record = _read_json(Path(record_path))
        if not isinstance(record, Mapping):
            raise ValueError("record is not an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "checker_schema": CHECKER_SCHEMA,
            "passed": False,
            "classification": "CONTRACT_INVALID",
            "contract_errors": [f"record unreadable: {exc}"],
            "gate_failures": [],
            "warnings": [],
            "metrics": {},
            "resource": {},
        }
    raw_dir, checkpoint_root = _check_provenance(record, Path(record_path), expected_source_sha, errors)
    if raw_dir is None or checkpoint_root is None:
        raw_dir = Path(".")
        checkpoint_root = Path(".")
    _check_identities(record, errors)
    _check_architecture(record, errors)
    marker_times = _check_markers(record, raw_dir, errors)
    arrays = _check_probe_arrays(record, raw_dir, errors, gates)
    krylov = _check_krylov(record, errors, gates)
    expected_checkpoints = _check_checkpoints(record, checkpoint_root, expected_source_sha, errors, gates)
    resource = _check_watchdog(record, watchdog_compact, raw_dir, errors, gates, warnings)
    if marker_times.get("retained_observed", -1) - marker_times.get("retained_ready", -1) < 2_000_000_000:
        _error(errors, "retained dwell is shorter than two seconds")
    passed = not errors and not gates
    classification = (
        "CONTRACT_INVALID" if errors else
        "C1_P6_POSITIVE_GATE_FAIL" if gates else
        "C1_P6_POSITIVE_PASS_MPI1"
    )
    metrics = {
        "source": record.get("source_name"),
        "iterations": krylov.get("iterations") if isinstance(krylov, Mapping) else None,
        "final_true_residual": krylov.get("final_true_residual") if isinstance(krylov, Mapping) else None,
        "matvec_count": krylov.get("matvec_count") if isinstance(krylov, Mapping) else None,
        "pc_apply_count": krylov.get("pc_apply_count") if isinstance(krylov, Mapping) else None,
        "ksp_destroy_count": krylov.get("ksp_destroy_count") if isinstance(krylov, Mapping) else None,
        "checkpoint_iterations": expected_checkpoints,
        "probe_array_roles": sorted(arrays),
    }
    return {
        "checker_schema": CHECKER_SCHEMA,
        "passed": passed,
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "warnings": warnings,
        "metrics": metrics,
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
    args.output.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CHECKER_SCHEMA", "check_record", "main"]
