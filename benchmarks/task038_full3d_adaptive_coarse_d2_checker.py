"""Independent, read-only checker for the D2 owner-local coarse artifacts.

The checker opens numeric shards with ``mmap`` and recomputes the small
algebra from the raw owner-local arrays.  It does not construct a mesh,
import the worker, or execute a PETSc action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.canonical_matrix_artifacts import (
    compare_canonical_matrices,
    read_canonical_matrix_manifest,
)


CHECKER_SCHEMA = "task038.full3d.adaptive-coarse.d2-check.v1"
RECORD_SCHEMA = "task038.full3d.adaptive-coarse.d2-record.v1"
PROFILE = "full3d_scalable_v1"
DEGREE = 6
MESH_TARGET_NM = 10.0
RANK = 64
PREFIXES = (16, 32, 48, 64)
EXPECTED_GLOBAL_ROWS = 173_802
EXPECTED_CANONICAL_PACKET_COUNT = 173_802
EXPECTED_RANK64_Z_AZ_BYTES = 355_946_496
Z_ORTHOGONALITY_LIMIT = 1.0e-10
E_RELATIVE_LIMIT = 1.0e-11
CANONICAL_LIMIT = 1.0e-12
CONDITION_LIMIT = 1.0e12
RANK64_Z_AZ_LIMIT = 355_946_496
TOTAL_RETAINED_LIMIT = 424_000_000
_ITEMSIZE = np.dtype(np.complex128).itemsize


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _required(value: Any, key: str) -> Any:
    if not isinstance(value, Mapping) or key not in value:
        raise ValueError(f"missing required field: {key}")
    return value[key]


def _sha_field(value: Any, label: str, length: int) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ValueError(f"{label} must be a {length}-character lowercase hex SHA")
    if value != value.lower() or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be lowercase hexadecimal")
    return value


def _path(raw_dir: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} path is missing")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else raw_dir / candidate


def _verify_file_descriptor(
    raw_dir: Path,
    descriptor: Mapping[str, Any],
    label: str,
    path_key: str = "path",
) -> Path:
    path = _path(raw_dir, _required(descriptor, path_key), label)
    if not path.is_file():
        raise ValueError(f"{label} file is missing: {path}")
    expected_sha = _sha_field(_required(descriptor, "sha256"), f"{label}.sha256", 64)
    if _sha256(path) != expected_sha:
        raise ValueError(f"{label} SHA256 does not match")
    expected_bytes = _required(descriptor, "bytes")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int):
        raise ValueError(f"{label}.bytes is invalid")
    if path.stat().st_size != expected_bytes:
        raise ValueError(f"{label}.bytes does not match")
    return path


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} is boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} is non-finite")
    return number


def _stats(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} is missing")
    result: dict[str, int] = {}
    for key in ("local", "global_sum", "global_max"):
        item = _required(value, key)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError(f"{label}.{key} is invalid")
        result[key] = item
    return result


def _mode_descriptor(record: Mapping[str, Any], raw_dir: Path) -> tuple[Path, str, int]:
    top = _required(record, "mode_manifest")
    artifacts = _required(record, "artifacts")
    artifact = _required(artifacts, "mode_manifest")
    if not isinstance(top, Mapping) or not isinstance(artifact, Mapping):
        raise ValueError("mode_manifest descriptors are required")
    if dict(top) != dict(artifact):
        raise ValueError("top-level and artifact mode_manifest descriptors differ")
    path = _verify_file_descriptor(
        raw_dir, top, "mode_manifest", path_key="relative_path"
    )
    if path.suffix != ".json" or not isinstance(_read_json(path), (dict, list)):
        raise ValueError("mode_manifest is not JSON")
    return path, str(top["sha256"]), int(top["bytes"])


def _check_watchdog(record: Mapping[str, Any], raw_dir: Path) -> dict[str, Any]:
    contract = _required(record, "resource_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("resource_contract is missing")
    if contract.get("status") != "measured":
        raise ValueError("successful D2 record resource_contract.status is not measured")
    raw_path = _path(raw_dir, _required(contract, "raw_path"), "watchdog_raw")
    raw_sha = _sha_field(
        _required(contract, "raw_sha256"), "watchdog_raw.sha256", 64
    )
    if not raw_path.is_file() or _sha256(raw_path) != raw_sha:
        raise ValueError("watchdog raw artifact is missing or has wrong SHA256")
    compact_path = _path(raw_dir, _required(contract, "compact_path"), "watchdog_compact")
    compact_sha = _sha_field(
        _required(contract, "compact_sha256"), "watchdog_compact.sha256", 64
    )
    if not compact_path.is_file() or _sha256(compact_path) != compact_sha:
        raise ValueError("watchdog compact artifact is missing or has wrong SHA256")
    raw = _read_json(raw_path)
    compact = _read_json(compact_path)
    if not isinstance(raw, Mapping) or raw.get("schema") != (
        "task038.full3d.adaptive-coarse.d2-watchdog-raw.v1"
    ):
        raise ValueError("watchdog raw schema is invalid")
    if not isinstance(compact, Mapping) or compact.get("schema") != (
        "task038.full3d.adaptive-coarse.d2-watchdog-compact.v1"
    ):
        raise ValueError("watchdog compact schema is invalid")
    if raw.get("worker_returncode") != 0 or compact.get("worker_returncode") != 0:
        raise ValueError("watchdog worker returncode is not zero")
    if raw.get("stop_reason") != "natural_exit" or compact.get("stop_reason") != "natural_exit":
        raise ValueError("watchdog did not end by natural exit")
    termination = _required(raw, "termination")
    if (
        not isinstance(termination, Mapping)
        or termination.get("requested") is not False
        or termination.get("method") != "natural_exit"
    ):
        raise ValueError("watchdog termination is not a natural exit")
    samples = _required(raw, "samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("watchdog has no valid authority samples")
    peak = 0
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or sample.get("authority_error"):
            raise ValueError(f"watchdog sample {index} has authority_error")
        authority = _required(sample, "authority")
        process_tree = _required(authority, "process_tree")
        if not isinstance(authority, Mapping) or not isinstance(process_tree, Mapping):
            raise ValueError(f"watchdog sample {index} authority is invalid")
        if process_tree.get("all_status_readable") is not True:
            raise ValueError(f"watchdog sample {index} is not readable")
        if authority.get("job_no_swap") is not True:
            raise ValueError(f"watchdog sample {index} job swap is not zero")
        swap = _required(process_tree, "swap_bytes")
        if isinstance(swap, bool) or not isinstance(swap, int) or swap != 0:
            raise ValueError(f"watchdog sample {index} process-tree swap is nonzero")
        memory = _finite_number(
            _required(authority, "memory_authority_bytes"),
            f"watchdog sample {index}.memory_authority_bytes",
        )
        if memory < 0:
            raise ValueError(f"watchdog sample {index} memory is negative")
        peak = max(peak, int(memory))
    if compact.get("raw_sha256") != raw_sha:
        raise ValueError("watchdog compact raw SHA256 does not match")
    if compact.get("process_tree_peak_memory_authority_bytes") != peak:
        raise ValueError("watchdog compact peak is not recomputed from raw samples")
    if compact.get("process_tree_swap_gate") is not True:
        raise ValueError("watchdog compact swap gate is not true")
    if contract.get("worker_returncode") != 0 or contract.get("stop_reason") != "natural_exit":
        raise ValueError("record watchdog contract is not a natural exit")
    if contract.get("process_tree_peak_memory_authority_bytes") != peak:
        raise ValueError("record watchdog peak does not match raw samples")
    return {
        "raw_sha256": raw_sha,
        "compact_sha256": compact_sha,
        "sample_count": len(samples),
        "process_tree_peak_memory_authority_bytes": peak,
        "process_tree_swap_gate": True,
    }


def _check_identity(record: Mapping[str, Any], raw_dir: Path, expected_mpi: int) -> dict[str, Any]:
    if record.get("schema") != RECORD_SCHEMA or record.get("stage") != "d2":
        raise ValueError("record schema or stage is invalid")
    if record.get("case") != f"p6-h10-mpi{expected_mpi}":
        raise ValueError("record case does not match its expected MPI size")
    mpi = _required(record, "mpi")
    if not isinstance(mpi, Mapping) or mpi.get("size") != expected_mpi:
        raise ValueError("record MPI size does not match its input")
    if record.get("degree") != DEGREE or record.get("mesh_target_nm") != MESH_TARGET_NM:
        raise ValueError("record degree or mesh target is not frozen p6/h10")
    if record.get("profile") != PROFILE or record.get("rank") != RANK:
        raise ValueError("record profile or rank is invalid")
    if record.get("prefixes") != list(PREFIXES):
        raise ValueError("record prefix ladder is invalid")
    model = _required(record, "model")
    if (
        not isinstance(model, Mapping)
        or model.get("profile") != PROFILE
        or model.get("degree") != DEGREE
        or model.get("mesh_target_nm") != MESH_TARGET_NM
        or model.get("input_resolved_from_file") is not True
    ):
        raise ValueError("record model identity is invalid")
    source = _required(record, "source_identity")
    if not isinstance(source, Mapping):
        raise ValueError("source_identity is missing")
    expected_sha = _sha_field(_required(source, "expected_sha"), "expected_sha", 40)
    source_sha = _sha_field(_required(source, "source_git_sha"), "source_git_sha", 40)
    if source_sha != expected_sha or source.get("tracked_status") != "":
        raise ValueError("record source is not the expected clean SHA")
    runtime = _required(record, "runtime")
    if not isinstance(runtime, Mapping):
        raise ValueError("runtime identity is missing")
    if runtime.get("qualified_activation") != "1":
        raise ValueError("runtime qualified activation is not 1")
    if runtime.get("mpi_size") != expected_mpi:
        raise ValueError("runtime MPI size does not match the record")
    if runtime.get("scalar_dtype") != "complex128" or runtime.get("int_dtype") != "int32":
        raise ValueError("runtime scalar or integer dtype is not the qualified ABI")
    if runtime.get("source_identity") != dict(source):
        raise ValueError("runtime and top-level source identity differ")
    executable = runtime.get("sys_executable")
    if not isinstance(executable, str) or not executable.startswith("/") or "\\" in executable:
        raise ValueError("runtime Python executable is not a Linux path")
    qualified_bin = (Path(__file__).resolve().parents[1] / ".venv" / "bin").resolve()
    if Path(executable).parent.resolve() != qualified_bin:
        raise ValueError("runtime Python executable is outside the qualified .venv/bin")
    for name in ("petsc4py", "slepc4py", "dolfinx", "basix", "mpi4py"):
        module_path = runtime.get(name)
        if (
            not isinstance(module_path, str)
            or not module_path.startswith("/")
            or "\\" in module_path
            or ":" in module_path
        ):
            raise ValueError(f"runtime module path is not a Linux path: {name}")
    input_data = _required(record, "input")
    if not isinstance(input_data, Mapping):
        raise ValueError("input identity is missing")
    input_path = _path(raw_dir, _required(input_data, "path"), "input")
    if not input_path.is_file():
        raise ValueError("input file is missing")
    input_sha = _sha_field(_required(input_data, "file_sha256"), "input.file_sha256", 64)
    if _sha256(input_path) != input_sha:
        raise ValueError("input file SHA256 does not match")
    resolved_sha = _sha_field(
        _required(input_data, "resolved_config_sha256"),
        "input.resolved_config_sha256",
        64,
    )
    resolved_bytes = _required(input_data, "resolved_config_bytes")
    if isinstance(resolved_bytes, bool) or not isinstance(resolved_bytes, int) or resolved_bytes <= 0:
        raise ValueError("resolved configuration byte count is invalid")
    mode_path, mode_sha, mode_bytes = _mode_descriptor(record, raw_dir)
    return {
        "source_git_sha": source_sha,
        "input_sha256": input_sha,
        "resolved_config_sha256": resolved_sha,
        "resolved_config_bytes": resolved_bytes,
        "mode_manifest_path": mode_path,
        "mode_manifest_sha256": mode_sha,
        "mode_manifest_bytes": mode_bytes,
        "mpi_size": expected_mpi,
        "runtime": dict(runtime),
    }


def _check_forbidden(record: Mapping[str, Any]) -> None:
    operator = _required(record, "operator")
    if not isinstance(operator, Mapping):
        raise ValueError("operator audit is missing")
    for key in (
        "global_aij_materialized",
        "global_schur_materialized",
        "factor_materialized",
        "numeric_allgather",
    ):
        if operator.get(key) is not False:
            raise ValueError(f"operator forbidden audit {key} is not false")
    if operator.get("t4_transmission_included") is not False:
        raise ValueError("operator T4 transmission audit is not false")
    operator_audit = _required(operator, "audit")
    if not isinstance(operator_audit, Mapping):
        raise ValueError("physical operator nested audit is missing")
    for key, expected in (
        ("schema", "task038.fullspace-physical-action.v1"),
        ("operator", "A_volume_plus_dynamic_DtN"),
        ("t4_transmission_included", False),
        ("global_aij_materialized", False),
        ("global_schur_materialized", False),
        ("ksp_created", False),
        ("numeric_allgather", False),
    ):
        if operator_audit.get(key) != expected:
            raise ValueError(f"physical operator audit {key} is not closed")
    volume_audit = _required(operator_audit, "volume_action")
    if not isinstance(volume_audit, Mapping):
        raise ValueError("volume action audit is missing")
    for key, expected in (
        ("schema", "task038.fullspace-mpc-form-action.v1"),
        ("numeric_allgather", False),
        ("global_matrix_materialized", False),
        ("global_constraint_matrix_materialized", False),
        ("global_condensed_schur_materialized", False),
        ("cell_schur_matrix_materialized", False),
        ("slab_matrix_materialized", False),
        ("factor_count", 0),
        ("ksp_created", False),
    ):
        if volume_audit.get(key) != expected:
            raise ValueError(f"volume action audit {key} is not closed")
    dtn_audit = _required(operator_audit, "dtn_action")
    if not isinstance(dtn_audit, Mapping):
        raise ValueError("DtN action audit is missing")
    for key, expected in (
        ("schema", "fullspace-dtn.carrier.v1"),
        ("numeric_allgather", False),
        ("global_aij_materialized", False),
        ("global_schur_materialized", False),
        ("trace_matrix_materialized", False),
        ("ksp_created", False),
        ("explicit_c_matrix_count", 0),
        ("explicit_d_matrix_count", 0),
        ("pde_solved", False),
    ):
        if dtn_audit.get(key) != expected:
            raise ValueError(f"DtN action audit {key} is not closed")
    basis = _required(record, "basis")
    basis_audit = _required(basis, "audit") if isinstance(basis, Mapping) else None
    if not isinstance(basis_audit, Mapping):
        raise ValueError("trace basis audit is missing")
    for key, expected in (
        ("construction_workspace_released", True),
        ("physical_action_applied", False),
        ("az_e_not_built", True),
        ("rank_prefix", RANK),
        ("rank_ladder", list(PREFIXES)),
        ("phase_application", "finalized_floquet_mpc_once"),
        ("numeric_allgather", False),
        ("global_aij_materialized", False),
        ("global_schur_materialized", False),
        ("factor_materialized", False),
    ):
        if basis_audit.get(key) != expected:
            raise ValueError(f"trace basis audit {key} is not closed")
    coarse = _required(record, "coarse")
    coarse_audit = _required(coarse, "audit") if isinstance(coarse, Mapping) else None
    if not isinstance(coarse_audit, Mapping):
        raise ValueError("coarse audit is missing")
    for key in (
        "global_aij_materialized",
        "global_schur_materialized",
        "factor_materialized",
        "numeric_allgather",
    ):
        if coarse_audit.get(key) is not False:
            raise ValueError(f"coarse forbidden audit {key} is not false")


def _load_owner_arrays(
    record: Mapping[str, Any], raw_dir: Path, mpi_size: int
) -> tuple[list[np.memmap], list[np.memmap], int, dict[str, dict[str, Any]]]:
    owner = _required(record, "owner_local_arrays")
    if not isinstance(owner, Mapping):
        raise ValueError("owner_local_arrays is missing")
    for name in ("Z", "AZ"):
        descriptor = _required(owner, name)
        if not isinstance(descriptor, Mapping):
            raise ValueError(f"owner_local_arrays.{name} descriptor is missing")
    z_paths = sorted(raw_dir.glob("Z.rank*.npy"))
    az_paths = sorted(raw_dir.glob("AZ.rank*.npy"))
    if len(z_paths) != mpi_size or len(az_paths) != mpi_size:
        raise ValueError("owner-local shard count does not match MPI size")
    z_values: list[np.memmap] = []
    az_values: list[np.memmap] = []
    shard_hashes: dict[str, dict[str, Any]] = {}
    total_rows = 0
    for rank in range(mpi_size):
        z_path = raw_dir / f"Z.rank{rank:04d}.npy"
        az_path = raw_dir / f"AZ.rank{rank:04d}.npy"
        if z_path not in z_paths or az_path not in az_paths:
            raise ValueError("owner-local shard rank names are incomplete")
        try:
            z = np.load(z_path, mmap_mode="r", allow_pickle=False)
            az = np.load(az_path, mmap_mode="r", allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError(f"owner-local shard {rank} is not valid NPY") from exc
        if z.dtype != np.complex128 or az.dtype != np.complex128:
            raise ValueError("owner-local shard dtype is not complex128")
        if z.ndim != 2 or az.shape != z.shape or z.shape[1] != RANK:
            raise ValueError("owner-local shard shape is not (local_rows,64)")
        for start in range(0, z.shape[0], 4096):
            if not np.all(np.isfinite(z[start : start + 4096])) or not np.all(
                np.isfinite(az[start : start + 4096])
            ):
                raise ValueError("owner-local shard contains non-finite data")
        z_values.append(z)
        az_values.append(az)
        shard_hashes[str(rank)] = {
            "Z_sha256": _sha256(z_path),
            "AZ_sha256": _sha256(az_path),
            "Z_bytes": z_path.stat().st_size,
            "AZ_bytes": az_path.stat().st_size,
        }
        total_rows += int(z.shape[0])
    if total_rows != EXPECTED_GLOBAL_ROWS:
        raise ValueError(
            f"owner-local global row count={total_rows}, "
            f"expected={EXPECTED_GLOBAL_ROWS}"
        )
    if total_rows * RANK * _ITEMSIZE * 2 != EXPECTED_RANK64_Z_AZ_BYTES:
        raise ValueError(
            "owner-local rank64 Z+AZ bytes do not equal "
            f"{EXPECTED_RANK64_Z_AZ_BYTES}"
        )
    root_z = _required(owner, "Z")
    root_az = _required(owner, "AZ")
    _verify_file_descriptor(raw_dir, root_z, "owner_local_arrays.Z")
    _verify_file_descriptor(raw_dir, root_az, "owner_local_arrays.AZ")
    if (
        root_z.get("shape") != list(z_values[0].shape)
        or root_az.get("shape") != list(az_values[0].shape)
        or root_z.get("dtype") != "complex128"
        or root_az.get("dtype") != "complex128"
    ):
        raise ValueError("owner-local descriptor shape or dtype does not match")
    return z_values, az_values, total_rows, shard_hashes


def _load_e(record: Mapping[str, Any], raw_dir: Path) -> np.memmap:
    artifacts = _required(record, "artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("artifacts are missing")
    descriptor = _required(artifacts, "E")
    if not isinstance(descriptor, Mapping):
        raise ValueError("E descriptor is missing")
    path = _verify_file_descriptor(raw_dir, descriptor, "E")
    try:
        values = np.load(path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise ValueError("E.npy is not valid NPY") from exc
    if values.dtype != np.complex128 or values.shape != (RANK, RANK):
        raise ValueError("E.npy shape or dtype is invalid")
    if descriptor.get("shape") != list(values.shape) or descriptor.get("dtype") != "complex128":
        raise ValueError("E descriptor shape or dtype does not match")
    if not np.all(np.isfinite(values)):
        raise ValueError("E.npy contains non-finite values")
    return values


def _load_matrix_manifest(
    record: Mapping[str, Any], raw_dir: Path, name: str, role: str, mpi_size: int
) -> Path:
    artifacts = _required(record, "artifacts")
    matrices = _required(artifacts, "canonical_matrices") if isinstance(artifacts, Mapping) else None
    descriptor = _required(matrices, name) if isinstance(matrices, Mapping) else None
    if not isinstance(descriptor, Mapping):
        raise ValueError(f"canonical {name} descriptor is missing")
    if descriptor.get("role") != role or descriptor.get("mpi_size") != mpi_size:
        raise ValueError(f"canonical {name} role or MPI size is invalid")
    manifest_path = _path(
        raw_dir, _required(descriptor, "manifest_relative_path"), f"canonical {name}"
    )
    expected_sha = _sha_field(
        _required(descriptor, "manifest_sha256"), f"canonical {name}.manifest_sha256", 64
    )
    if not manifest_path.is_file() or _sha256(manifest_path) != expected_sha:
        raise ValueError(f"canonical {name} manifest SHA256 does not match")
    manifest = read_canonical_matrix_manifest(manifest_path)
    if (
        manifest.get("role") != role
        or manifest.get("mpi_size") != mpi_size
        or manifest.get("column_count") != RANK
        or manifest.get("global_packet_count") != EXPECTED_CANONICAL_PACKET_COUNT
        or descriptor.get("global_packet_count") != EXPECTED_CANONICAL_PACKET_COUNT
    ):
        raise ValueError(f"canonical {name} manifest identity or packet count is invalid")
    extractor = _required(manifest, "extractor_audit")
    if (
        not isinstance(extractor, Mapping)
        or extractor.get("role") != role
        or extractor.get("numeric_allgather") is not False
        or extractor.get("owner_local_streaming") is not True
    ):
        raise ValueError(f"canonical {name} extractor audit is invalid")
    return manifest_path


def _worker_audits(record: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    coarse = _required(record, "coarse")
    audit = _required(coarse, "audit") if isinstance(coarse, Mapping) else None
    if not isinstance(audit, Mapping) or audit.get("rank") != RANK:
        raise ValueError("coarse rank audit is invalid")
    if audit.get("small_numeric_collective") != "scalars_and_r_by_r_allreduce_only":
        raise ValueError("coarse numeric collective audit is invalid")
    raw_prefixes = _required(audit, "prefix_audits")
    if not isinstance(raw_prefixes, list) or len(raw_prefixes) != len(PREFIXES):
        raise ValueError("coarse prefix audits are incomplete")
    result: dict[int, Mapping[str, Any]] = {}
    for item in raw_prefixes:
        if not isinstance(item, Mapping) or item.get("prefix") in result:
            raise ValueError("coarse prefix audit is malformed")
        prefix = item.get("prefix")
        if prefix not in PREFIXES:
            raise ValueError("coarse prefix audit has an unexpected prefix")
        result[int(prefix)] = item
        for key in (
            "z_orthogonality_defect",
            "az_repeat_relative_frobenius",
            "e_condition_number",
            "physical_consistency_relative",
        ):
            _finite_number(_required(item, key), f"prefix {prefix}.{key}")
        if item.get("finite") is not True or item.get("az_repeat_exact") is not True:
            raise ValueError(f"prefix {prefix} finite/exact repeat audit failed")
        if _finite_number(item["z_orthogonality_defect"], "z defect") > Z_ORTHOGONALITY_LIMIT:
            raise ValueError(f"prefix {prefix} worker z defect exceeds limit")
        if _finite_number(item["az_repeat_relative_frobenius"], "repeat") > E_RELATIVE_LIMIT:
            raise ValueError(f"prefix {prefix} worker repeat exceeds limit")
        if _finite_number(item["e_condition_number"], "condition") > CONDITION_LIMIT:
            raise ValueError(f"prefix {prefix} worker condition exceeds limit")
        if _finite_number(item["physical_consistency_relative"], "consistency") > E_RELATIVE_LIMIT:
            raise ValueError(f"prefix {prefix} worker consistency exceeds limit")
        if item.get("e_prefix_leading_exact") is not True:
            raise ValueError(f"prefix {prefix} stored E leading block is not exact")
        if _finite_number(
            _required(item, "e_prefix_leading_relative"),
            f"prefix {prefix}.e_prefix_leading_relative",
        ) > 1.0e-12:
            raise ValueError(f"prefix {prefix} stored E leading block exceeds 1e-12")
        _finite_number(
            _required(item, "e_hermitian_relative_defect"),
            f"prefix {prefix}.e_hermitian_relative_defect",
        )
        for key in (
            "resident_z_bytes",
            "resident_az_bytes",
            "resident_e_bytes",
            "resident_metadata_bytes",
            "resident_work_vector_bytes",
            "logical_prefix_z_bytes",
            "logical_prefix_az_bytes",
            "logical_prefix_e_bytes",
        ):
            _stats(_required(item, key), f"prefix {prefix}.{key}")
        if _required(item, "rank64_z_az_hard_limit_bytes") != EXPECTED_RANK64_Z_AZ_BYTES:
            raise ValueError("rank64 Z+AZ hard limit is not the frozen contract")
        if _required(item, "total_coarse_retained_hard_limit_bytes") != TOTAL_RETAINED_LIMIT:
            raise ValueError("coarse retained hard limit is not the frozen contract")
        if item.get("logical_prefix_bytes_provenance") != "derived_exact_array_size":
            raise ValueError("logical prefix byte provenance is invalid")
        if item.get("resident_bytes_provenance") != "exact_current_retained_objects":
            raise ValueError("resident byte provenance is invalid")
    if set(result) != set(PREFIXES):
        raise ValueError("coarse prefix audit set is incomplete")
    for key in (
        "global_aij_materialized",
        "global_schur_materialized",
        "factor_materialized",
        "numeric_allgather",
    ):
        if audit.get(key) is not False:
            raise ValueError(f"coarse forbidden audit {key} is not false")
    return result


def _worker_prefix_metrics(
    facts: Mapping[str, Any], prefix: int
) -> dict[str, Any]:
    p = int(prefix)
    z_gram = np.zeros((p, p), dtype=np.complex128)
    e_calculated = np.zeros((p, p), dtype=np.complex128)
    z_arrays = facts["z_arrays"]
    az_arrays = facts["az_arrays"]
    for z, az in zip(z_arrays, az_arrays):
        z_prefix = z[:, :p]
        az_prefix = az[:, :p]
        z_gram += z_prefix.conj().T @ z_prefix
        e_calculated += z_prefix.conj().T @ az_prefix
    stored = np.asarray(facts["e"][:p, :p], dtype=np.complex128)
    e_difference = e_calculated - stored
    e_relative = float(
        np.linalg.norm(e_difference)
        / max(np.linalg.norm(stored), np.finfo(float).tiny)
    )
    z_defect = float(np.linalg.norm(z_gram - np.eye(p, dtype=np.complex128)))
    condition = float(np.linalg.cond(stored))
    hermitian = float(
        np.linalg.norm(stored - stored.conj().T)
        / max(np.linalg.norm(stored), np.finfo(float).tiny)
    )
    rows = sum(int(values.shape[0]) for values in z_arrays)
    z_logical = rows * p * _ITEMSIZE
    az_logical = rows * p * _ITEMSIZE
    e_logical = p * p * _ITEMSIZE * facts["mpi_size"]
    resident_z = rows * RANK * _ITEMSIZE
    resident_az = rows * RANK * _ITEMSIZE
    resident_e = int(facts["e"].nbytes) * facts["mpi_size"]
    audit = facts["audits"][p]
    metadata = _stats(audit["resident_metadata_bytes"], "resident metadata")
    work = _stats(audit["resident_work_vector_bytes"], "resident work")
    resident_total = resident_z + resident_az + resident_e + metadata["global_sum"] + work["global_sum"]
    logical_total = z_logical + az_logical + e_logical + metadata["global_sum"] + work["global_sum"]
    stored_total = _required(audit, "resident_coarse_total_global_sum")
    stored_logical = _required(audit, "logical_prefix_coarse_total_global_sum")
    if stored_total != resident_total or stored_logical != logical_total:
        raise ValueError(f"prefix {p} resident/logical byte closure is invalid")
    if _stats(audit["resident_z_bytes"], "resident Z")["global_sum"] != resident_z:
        raise ValueError(f"prefix {p} resident Z bytes are not recomputed")
    if _stats(audit["resident_az_bytes"], "resident AZ")["global_sum"] != resident_az:
        raise ValueError(f"prefix {p} resident AZ bytes are not recomputed")
    if _stats(audit["resident_e_bytes"], "resident E")["global_sum"] != resident_e:
        raise ValueError(f"prefix {p} resident E bytes are not recomputed")
    if _stats(audit["logical_prefix_z_bytes"], "logical Z")["global_sum"] != z_logical:
        raise ValueError(f"prefix {p} logical Z bytes are not recomputed")
    if _stats(audit["logical_prefix_az_bytes"], "logical AZ")["global_sum"] != az_logical:
        raise ValueError(f"prefix {p} logical AZ bytes are not recomputed")
    if _stats(audit["logical_prefix_e_bytes"], "logical E")["global_sum"] != e_logical:
        raise ValueError(f"prefix {p} logical E bytes are not recomputed")
    if resident_z + resident_az > RANK64_Z_AZ_LIMIT:
        raise ValueError(f"prefix {p} resident Z+AZ exceeds {RANK64_Z_AZ_LIMIT} B")
    if resident_total > TOTAL_RETAINED_LIMIT:
        raise ValueError(f"prefix {p} resident coarse total exceeds {TOTAL_RETAINED_LIMIT} B")
    finite = bool(
        np.all(np.isfinite(z_gram))
        and np.all(np.isfinite(e_calculated))
        and np.isfinite(z_defect)
        and np.isfinite(e_relative)
        and np.isfinite(condition)
        and np.isfinite(hermitian)
    )
    passed = bool(
        finite
        and z_defect <= Z_ORTHOGONALITY_LIMIT
        and e_relative <= E_RELATIVE_LIMIT
        and condition <= CONDITION_LIMIT
    )
    return {
        "prefix": p,
        "finite": finite,
        "z_h_z_defect": z_defect,
        "e_relative_l2": e_relative,
        "e_condition_number": condition,
        "e_hermitian_relative_defect": hermitian,
        "logical_prefix_z_bytes": z_logical,
        "logical_prefix_az_bytes": az_logical,
        "logical_prefix_e_bytes": e_logical,
        "resident_z_bytes": resident_z,
        "resident_az_bytes": resident_az,
        "resident_e_bytes": resident_e,
        "resident_coarse_total_global_sum": resident_total,
        "resident_z_az_limit_bytes": RANK64_Z_AZ_LIMIT,
        "resident_total_limit_bytes": TOTAL_RETAINED_LIMIT,
        "worker_audit": {
            "az_repeat_exact": facts["audits"][p]["az_repeat_exact"],
            "az_repeat_relative_frobenius": facts["audits"][p]["az_repeat_relative_frobenius"],
            "physical_consistency_relative": facts["audits"][p]["physical_consistency_relative"],
        },
        "passed": passed,
    }


def check_worker_record(record_path: Path, raw_dir: Path, expected_mpi_size: int) -> dict[str, Any]:
    """Return independently recomputed worker facts; never trust worker status."""

    try:
        record = _read_json(Path(record_path))
        if not isinstance(record, Mapping):
            raise ValueError("record must be a JSON object")
        identity = _check_identity(record, Path(raw_dir), expected_mpi_size)
        _check_forbidden(record)
        watchdog = _check_watchdog(record, Path(raw_dir))
        z_arrays, az_arrays, total_rows, shard_hashes = _load_owner_arrays(
            record, Path(raw_dir), expected_mpi_size
        )
        e = _load_e(record, Path(raw_dir))
        z_manifest = _load_matrix_manifest(
            record, Path(raw_dir), "Z", "full_fe", expected_mpi_size
        )
        az_manifest = _load_matrix_manifest(
            record, Path(raw_dir), "AZ", "full_fe_dual", expected_mpi_size
        )
        audits = _worker_audits(record)
        facts: dict[str, Any] = {
            "record_path": Path(record_path),
            "record_sha256": _sha256(Path(record_path)),
            "raw_dir": Path(raw_dir),
            "record": record,
            **identity,
            "watchdog": watchdog,
            "z_arrays": z_arrays,
            "az_arrays": az_arrays,
            "e": e,
            "z_manifest_path": z_manifest,
            "az_manifest_path": az_manifest,
            "audits": audits,
            "total_rows": total_rows,
            "owner_local_shard_hashes": shard_hashes,
            "e_sha256": _sha256(
                _path(
                    Path(raw_dir),
                    _required(_required(_required(record, "artifacts"), "E"), "path"),
                    "E",
                )
            ),
        }
        facts["prefixes"] = {
            prefix: _worker_prefix_metrics(facts, prefix) for prefix in PREFIXES
        }
        return {"passed": all(item["passed"] for item in facts["prefixes"].values()), "facts": facts, "errors": []}
    except Exception as exc:
        return {"passed": False, "facts": None, "errors": [f"{type(exc).__name__}: {exc}"]}


def _pair_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> None:
    for key in (
        "source_git_sha",
        "input_sha256",
        "resolved_config_sha256",
        "resolved_config_bytes",
        "mode_manifest_sha256",
        "mode_manifest_bytes",
    ):
        if left[key] != right[key]:
            raise ValueError(f"MPI identity differs for {key}")


def _cross_result(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    z = compare_canonical_matrices(
        left["z_manifest_path"], right["z_manifest_path"],
        relative_tolerance=CANONICAL_LIMIT, prefixes=PREFIXES,
    )
    az = compare_canonical_matrices(
        left["az_manifest_path"], right["az_manifest_path"],
        relative_tolerance=CANONICAL_LIMIT, prefixes=PREFIXES,
    )
    return {"Z_full_fe": z, "AZ_full_fe_dual": az}


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(body)
    return hashlib.sha256(body).hexdigest()


def check_pair(
    mpi1_record: Path,
    mpi1_raw_dir: Path,
    mpi2_record: Path,
    mpi2_raw_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Check both workers and write four prefix compact records plus aggregate."""

    left = check_worker_record(mpi1_record, mpi1_raw_dir, 1)
    right = check_worker_record(mpi2_record, mpi2_raw_dir, 2)
    prefix_results: dict[str, dict[str, Any]] = {}
    cross: dict[str, Any] = {}
    errors: list[str] = []
    if left["facts"] is None:
        errors.extend(f"MPI1: {item}" for item in left["errors"])
    if right["facts"] is None:
        errors.extend(f"MPI2: {item}" for item in right["errors"])
    if not errors:
        try:
            _pair_identity(left["facts"], right["facts"])
            cross = _cross_result(left["facts"], right["facts"])
        except Exception as exc:
            errors.append(f"cross-MPI: {type(exc).__name__}: {exc}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for prefix in PREFIXES:
        item: dict[str, Any] = {
            "schema": CHECKER_SCHEMA,
            "prefix": prefix,
            "mpi1": left["facts"]["prefixes"].get(prefix) if left["facts"] else None,
            "mpi2": right["facts"]["prefixes"].get(prefix) if right["facts"] else None,
            "cross_mpi": {
                "Z_full_fe": cross.get("Z_full_fe", {}).get("prefixes", {}).get(str(prefix)),
                "AZ_full_fe_dual": cross.get("AZ_full_fe_dual", {}).get("prefixes", {}).get(str(prefix)),
            },
            "evidence_hashes": {
                "mpi1_record_sha256": left.get("facts", {}).get("record_sha256") if left["facts"] else None,
                "mpi2_record_sha256": right.get("facts", {}).get("record_sha256") if right["facts"] else None,
                "mpi1_owner_local_shards": left.get("facts", {}).get("owner_local_shard_hashes") if left["facts"] else None,
                "mpi2_owner_local_shards": right.get("facts", {}).get("owner_local_shard_hashes") if right["facts"] else None,
                "mpi1_E_sha256": left.get("facts", {}).get("e_sha256") if left["facts"] else None,
                "mpi2_E_sha256": right.get("facts", {}).get("e_sha256") if right["facts"] else None,
                "mpi1_Z_manifest_sha256": _sha256(left["facts"]["z_manifest_path"]) if left["facts"] else None,
                "mpi2_Z_manifest_sha256": _sha256(right["facts"]["z_manifest_path"]) if right["facts"] else None,
                "mpi1_AZ_manifest_sha256": _sha256(left["facts"]["az_manifest_path"]) if left["facts"] else None,
                "mpi2_AZ_manifest_sha256": _sha256(right["facts"]["az_manifest_path"]) if right["facts"] else None,
            },
            "limits": {
                "z_h_z_defect": Z_ORTHOGONALITY_LIMIT,
                "e_relative_l2": E_RELATIVE_LIMIT,
                "e_condition_number": CONDITION_LIMIT,
                "az_repeat_relative_frobenius": E_RELATIVE_LIMIT,
                "physical_consistency_relative": E_RELATIVE_LIMIT,
                "canonical_relative_l2": CANONICAL_LIMIT,
                "rank64_z_az_bytes": RANK64_Z_AZ_LIMIT,
                "resident_coarse_total_bytes": TOTAL_RETAINED_LIMIT,
            },
        }
        if left["facts"] is None or right["facts"] is None or errors:
            item["errors"] = list(errors) + left["errors"] + right["errors"]
            item["passed"] = False
        else:
            z_cross = item["cross_mpi"]["Z_full_fe"]
            az_cross = item["cross_mpi"]["AZ_full_fe_dual"]
            item["passed"] = bool(
                item["mpi1"]["passed"]
                and item["mpi2"]["passed"]
                and isinstance(z_cross, Mapping) and z_cross.get("passed") is True
                and isinstance(az_cross, Mapping) and az_cross.get("passed") is True
            )
            item["errors"] = [] if item["passed"] else ["prefix Gate failed"]
        target = output_dir / f"d2_adaptive_coarse_prefix_{prefix}.json"
        item["evidence_sha256"] = _write_json_exclusive(target, item)
        prefix_results[str(prefix)] = item
    aggregate = {
        "schema": CHECKER_SCHEMA,
        "mpi1_record": str(Path(mpi1_record).resolve()),
        "mpi2_record": str(Path(mpi2_record).resolve()),
        "prefixes": prefix_results,
        "passed": all(item["passed"] for item in prefix_results.values()),
        "errors": errors,
    }
    aggregate["evidence_sha256"] = _write_json_exclusive(
        output_dir / "d2_adaptive_coarse_aggregate.json", aggregate
    )
    return aggregate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent D2 adaptive coarse checker")
    parser.add_argument("--mpi1-record", type=Path, required=True)
    parser.add_argument("--mpi1-raw-dir", type=Path, required=True)
    parser.add_argument("--mpi2-record", type=Path, required=True)
    parser.add_argument("--mpi2-raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_pair(
        args.mpi1_record,
        args.mpi1_raw_dir,
        args.mpi2_record,
        args.mpi2_raw_dir,
        args.output_dir,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
