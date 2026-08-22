"""Independent, read-only checker for the N2 setup artifacts.

This module intentionally imports no runner, solver, PETSc, MPI, DOLFINx, or
SLEPc.  It validates the worker facts, watchdog samples, owner-local arrays,
and canonical Z32/AZ32 manifests from files only.  It does not rerun an
action or infer a numerical result from the worker classification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.canonical_matrix_artifacts import compare_canonical_matrices


N2_SCHEMA = "task038.full3d.local-spectral.n2-record.v1"
N2_WATCHDOG_RAW_SCHEMA = "task038.full3d.local-spectral.n2-watchdog-raw.v1"
N2_WATCHDOG_COMPACT_SCHEMA = "task038.full3d.local-spectral.n2-watchdog-compact.v1"
N2_PROFILE = "full3d_scalable_v1"
N2_DEGREE = 6
N2_MESH_TARGET_NM = 10.0
N2_RANK = 32
N2_REGIONAL_RANK = 16
N2_MODE_CAP = 8
N2_MAX_CLASSES = 32
N2_FACTOR_BYTES_LIMIT = 6_230_448
N2_WARN_BYTES = 1_800_000_000
N2_HARD_BYTES = 2_000_000_000
N2_RETAINED_HARD_BYTES = 1_798_919_864
N2_EXPECTED_GLOBAL_ROWS = 173_802
N2_EXPECTED_GLOBAL_CELLS = 252
N2_MAX_LOCAL_ROWS = 882
N2_MODE_SHARD_HARD_BYTES = 252 * 882 * 8 * 16
N2_PREFIXES = (16, 32)
N1_ALGEBRA_LIMIT = 1.0e-11
LOCAL_FACTOR_CERTIFICATION_SCHEMA = "task038.local-factor-certification-v2"
LOCAL_FACTOR_CERTIFICATION_ORDINARY_LIMIT = 1.0e-10
LOCAL_FACTOR_CERTIFICATION_KAPPA_LIMIT = 1.0e8
LOCAL_FACTOR_CERTIFICATION_FACTOR_BYTES_LIMIT = 6_230_448
LOCAL_FACTOR_CERTIFICATION_EPS64 = 2.220446049250313e-16
N1_PO_U_LIMIT = 1.0e-13
N1_RP_LIMIT = 1.0e-13


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _error(errors: list[str], message: str) -> None:
    errors.append(str(message))


def _required_number(
    mapping: Mapping[str, Any], key: str, label: str, errors: list[str]
) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _error(errors, f"{label}.{key} is missing or not numeric")
        return None
    result = float(value)
    if not np.isfinite(result):
        _error(errors, f"{label}.{key} is non-finite")
        return None
    return result


def _required_integer(
    mapping: Mapping[str, Any], key: str, label: str, errors: list[str]
) -> int | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        _error(errors, f"{label}.{key} is missing or not an integer")
        return None
    return int(value)


def _require_bound(
    mapping: Mapping[str, Any], key: str, label: str, limit: float, errors: list[str]
) -> float | None:
    value = _required_number(mapping, key, label, errors)
    if value is not None and value > limit:
        _error(errors, f"{label}.{key}={value:.17g} exceeds {limit:.17g}")
    return value


def _local_factor_certification_thresholds(rows: int) -> dict[str, float]:
    n = int(rows)
    gamma = n * LOCAL_FACTOR_CERTIFICATION_EPS64 / (
        1.0 - n * LOCAL_FACTOR_CERTIFICATION_EPS64
    )
    return {
        "hermitian_defect": max(1.0e-13, 8.0 * gamma),
        "factorization_relative_error": max(1.0e-13, 16.0 * gamma),
        "normalized_backward_error": max(1.0e-14, 16.0 * gamma),
        "ordinary_relative_residual": LOCAL_FACTOR_CERTIFICATION_ORDINARY_LIMIT,
        "kappa2": LOCAL_FACTOR_CERTIFICATION_KAPPA_LIMIT,
        "factor_bytes": LOCAL_FACTOR_CERTIFICATION_FACTOR_BYTES_LIMIT,
    }
def _relative(left: np.ndarray, right: np.ndarray) -> float:
    numerator = float(np.linalg.norm(np.asarray(left, dtype=np.complex128)))
    denominator = max(float(np.linalg.norm(np.asarray(right, dtype=np.complex128))), np.finfo(float).tiny)
    return numerator / denominator


def _array_descriptor(
    descriptor: Mapping[str, Any], raw_dir: Path, expected_shape: tuple[int, ...] | None = None
) -> tuple[np.ndarray | None, list[str]]:
    errors: list[str] = []
    path_value = descriptor.get("path")
    if not isinstance(path_value, str):
        return None, ["array descriptor path is missing"]
    path = Path(path_value)
    if not path.is_absolute():
        path = raw_dir / path
    if not path.is_file():
        return None, [f"array artifact is missing: {path}"]
    expected_hash = descriptor.get("sha256")
    if not isinstance(expected_hash, str) or expected_hash != _sha256(path):
        _error(errors, f"array SHA256 mismatch: {path}")
    try:
        array = np.load(path, mmap_mode="r", allow_pickle=False)
    except (OSError, ValueError) as exc:
        return None, errors + [f"array cannot be mmap-read: {exc}"]
    if array.dtype != np.dtype(np.complex128):
        _error(errors, f"array dtype is {array.dtype}, expected complex128: {path}")
    if expected_shape is not None and tuple(array.shape) != tuple(expected_shape):
        _error(errors, f"array shape {array.shape} != expected {expected_shape}: {path}")
    if descriptor.get("bytes") != path.stat().st_size:
        _error(errors, f"array byte count mismatch: {path}")
    if descriptor.get("shape") != list(array.shape):
        _error(errors, f"array descriptor shape mismatch: {path}")
    if descriptor.get("dtype") != "complex128":
        _error(errors, f"array descriptor dtype mismatch: {path}")
    if not np.all(np.isfinite(array)):
        _error(errors, f"array contains non-finite values: {path}")
    return array, errors


def _watchdog(record_path: Path, record: Mapping[str, Any], errors: list[str]) -> dict[str, Any] | None:
    contract = record.get("resource_contract")
    if not isinstance(contract, Mapping):
        _error(errors, "resource_contract is missing")
        return None
    if contract.get("status") != "measured":
        _error(errors, f"resource_contract.status is {contract.get('status')!r}, expected measured")
    raw_path = Path(str(contract.get("raw_path", "")))
    compact_path = Path(str(contract.get("compact_path", "")))
    if not raw_path.is_file() or not compact_path.is_file():
        _error(errors, "watchdog raw/compact artifact is missing")
        return None
    if contract.get("raw_sha256") != _sha256(raw_path):
        _error(errors, "watchdog raw SHA256 mismatch")
    if contract.get("compact_sha256") != _sha256(compact_path):
        _error(errors, "watchdog compact SHA256 mismatch")
    raw = _load(raw_path)
    compact = _load(compact_path)
    if raw.get("schema") != N2_WATCHDOG_RAW_SCHEMA:
        _error(errors, "watchdog raw schema mismatch")
    if compact.get("schema") != N2_WATCHDOG_COMPACT_SCHEMA:
        _error(errors, "watchdog compact schema mismatch")
    samples = raw.get("samples")
    if not isinstance(samples, list) or not samples:
        _error(errors, "watchdog has no usable samples")
        return compact
    valid = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping) or not isinstance(sample.get("authority"), Mapping):
            _error(errors, f"watchdog sample {index} lacks authority")
            continue
        authority = sample["authority"]
        tree = authority.get("process_tree")
        if not isinstance(tree, Mapping) or tree.get("all_status_readable") is not True:
            _error(errors, f"watchdog sample {index} process tree is unreadable")
            continue
        if tree.get("pss_uss_readable") is not True:
            _error(errors, f"watchdog sample {index} PSS/USS is unreadable")
        if int(tree.get("swap_bytes", -1)) != 0:
            _error(errors, f"watchdog sample {index} process-tree swap is nonzero")
        cgroup = authority.get("job_cgroup")
        if isinstance(cgroup, Mapping) and cgroup.get("dedicated_job_cgroup") and int(cgroup.get("swap_current_bytes", -1)) != 0:
            _error(errors, f"watchdog sample {index} dedicated cgroup swap is nonzero")
        valid.append(sample)
    if len(valid) != len(samples):
        _error(errors, "watchdog authority samples are incomplete")
    peaks: dict[str, int] = {}
    rss_peaks: dict[str, int] = {}
    pss_peaks: dict[str, int] = {}
    uss_peaks: dict[str, int] = {}
    cgroup_swap_peaks: dict[str, int] = {}
    for sample in valid:
        stage = str(sample.get("stage", "unknown"))
        authority = sample["authority"]
        tree = authority["process_tree"]
        value = int(authority.get("memory_authority_bytes", -1))
        if value < 0:
            _error(errors, f"watchdog sample has invalid memory authority: {value}")
        peaks[stage] = max(peaks.get(stage, 0), value)
        rss_peaks[stage] = max(rss_peaks.get(stage, 0), int(tree.get("rss_bytes", -1)))
        pss_peaks[stage] = max(pss_peaks.get(stage, 0), int(tree.get("pss_bytes", -1)))
        uss_peaks[stage] = max(uss_peaks.get(stage, 0), int(tree.get("uss_bytes", -1)))
        cgroup = authority.get("dedicated_cgroup_swap_bytes")
        if cgroup is not None:
            cgroup_swap_peaks[stage] = max(cgroup_swap_peaks.get(stage, 0), int(cgroup))
    peak = max(peaks.values(), default=0)
    if peak >= N2_HARD_BYTES:
        _error(errors, f"process-tree peak {peak} is not below hard limit {N2_HARD_BYTES}")
    post_setup = peaks.get("post_setup_release", 0)
    post_setup_samples = sum(
        1 for sample in valid if sample.get("stage") == "post_setup_release"
    )
    if post_setup_samples < 1:
        _error(errors, "watchdog has no post_setup_release sample")
    if post_setup >= N2_WARN_BYTES:
        _error(errors, f"post-setup peak {post_setup} is not below warning limit {N2_WARN_BYTES}")
    if raw.get("worker_returncode") != 0 or raw.get("stop_reason") != "natural_exit":
        _error(errors, "worker did not have natural returncode-zero watchdog termination")
    termination = raw.get("termination")
    if not isinstance(termination, Mapping) or termination.get("process_group_exited") is not True:
        _error(errors, "watchdog process group did not close")
    if not isinstance(termination, Mapping) or termination.get("method") != "already_exited":
        _error(errors, "natural watchdog termination was not verified as already_exited")
    if compact.get("raw_sha256") != _sha256(raw_path):
        _error(errors, "watchdog compact does not bind raw SHA256")
    if compact.get("process_tree_peak_memory_authority_bytes") != peak:
        _error(errors, "watchdog compact peak does not match raw samples")
    if compact.get("stage_peak_memory_authority_bytes") != peaks:
        _error(errors, "watchdog compact stage peaks do not match raw samples")
    if compact.get("stage_peak_process_tree_rss_bytes") != rss_peaks:
        _error(errors, "watchdog compact RSS stage peaks do not match raw samples")
    if compact.get("stage_peak_process_tree_pss_bytes") != pss_peaks:
        _error(errors, "watchdog compact PSS stage peaks do not match raw samples")
    if compact.get("stage_peak_process_tree_uss_bytes") != uss_peaks:
        _error(errors, "watchdog compact USS stage peaks do not match raw samples")
    if compact.get("stage_peak_dedicated_cgroup_swap_bytes") != cgroup_swap_peaks:
        _error(errors, "watchdog compact cgroup-swap peaks do not match raw samples")
    post_setup = peaks.get("post_setup_release", 0)
    if compact.get("warning_crossed") != bool(peak >= N2_WARN_BYTES):
        _error(errors, "watchdog warning-crossed flag is not recomputed from raw samples")
    if compact.get("post_setup_peak_memory_authority_bytes") != post_setup:
        _error(errors, "watchdog post-setup peak does not match raw samples")
    if compact.get("post_setup_sample_count") != post_setup_samples:
        _error(errors, "watchdog post-setup sample count does not match raw samples")
    if compact.get("post_setup_warning_crossed") != bool(post_setup >= N2_WARN_BYTES):
        _error(errors, "watchdog post-setup warning flag is not recomputed from raw samples")
    if compact.get("process_tree_swap_gate") is not True:
        _error(errors, "watchdog process-tree swap gate is not true")
    if compact.get("no_orphan_claim") is not True:
        _error(errors, "watchdog no-orphan claim is not verified")
    compact_termination = compact.get("termination")
    if not isinstance(compact_termination, Mapping) or compact_termination.get("method") != "already_exited":
        _error(errors, "compact watchdog termination was not verified as already_exited")
    command = " ".join(str(item) for item in compact.get("command", []))
    expected = record.get("source_identity", {}).get("expected_sha")
    for token in (str(record_path.resolve()), str(record.get("case")), str(expected), "--stage n2", "--expected-mpi-size"):
        if token not in command:
            _error(errors, f"watchdog command is not bound to record fact {token!r}")
    return compact


def _check_identity(record: Mapping[str, Any], record_path: Path, expected_sha: str, expected_mpi: int, errors: list[str]) -> None:
    if record.get("schema") != N2_SCHEMA:
        _error(errors, "record schema mismatch")
    if record.get("case") != f"p6-h10-mpi{expected_mpi}":
        _error(errors, "record case is not the expected frozen p6/h10 MPI case")
    if record.get("degree") != N2_DEGREE or record.get("mesh_target_nm") != N2_MESH_TARGET_NM or record.get("profile") != N2_PROFILE:
        _error(errors, "record model identity is not frozen p6/h10/full3d_scalable_v1")
    identity = record.get("source_identity")
    runtime = record.get("runtime")
    if not isinstance(identity, Mapping) or identity.get("expected_sha") != expected_sha or identity.get("source_git_sha") != expected_sha or identity.get("tracked_status") != "":
        _error(errors, "source identity is missing, dirty, or not bound to expected SHA")
    if not isinstance(runtime, Mapping):
        _error(errors, "runtime identity is missing")
        return
    for key, expected in (("qualified_activation", "1"), ("mpi_size", expected_mpi), ("scalar_dtype", "complex128"), ("int_dtype", "int32")):
        if runtime.get(key) != expected:
            _error(errors, f"runtime.{key}={runtime.get(key)!r} does not equal {expected!r}")
    if runtime.get("source_identity") != dict(identity):
        _error(errors, "runtime.source_identity differs from top-level source identity")
    executable = str(runtime.get("sys_executable", ""))
    if "/.venv/" not in executable or "\\" in executable or not executable.endswith("/bin/python"):
        _error(errors, "runtime executable is not the qualified Linux repository venv")
    model = record.get("model")
    if not isinstance(model, Mapping):
        _error(errors, "model identity is missing")
        return
    required = {
        "reuse_class_templates": True,
        "max_exact_classes": N2_MAX_CLASSES,
        "max_patch_rows": 882,
        "factor_bytes_limit": N2_FACTOR_BYTES_LIMIT,
        "gradient_count": 3,
        "positive_mode_count": 5,
        "mode_cap": N2_MODE_CAP,
        "regional_rank": N2_REGIONAL_RANK,
        "top_rank": N2_RANK,
        "levels": 2,
        "source_independent": True,
    }
    for key, value in required.items():
        if model.get(key) != value:
            _error(errors, f"model.{key} is not frozen to {value!r}")
    if model.get("local_factor_certification_v2") is True and model.get(
        "local_factor_certification_schema"
    ) != LOCAL_FACTOR_CERTIFICATION_SCHEMA:
        _error(errors, "model local-factor certification-v2 schema is not frozen")
    if record.get("no_rho") is not True or record.get("not_n3") is not True:
        _error(errors, "record does not explicitly prove setup-only/no-rho mode")


def _check_forbidden(record: Mapping[str, Any], errors: list[str]) -> None:
    basis = record.get("basis", {}).get("audit") if isinstance(record.get("basis"), Mapping) else None
    operator = record.get("operator")
    coarse = record.get("coarse", {}).get("audit") if isinstance(record.get("coarse"), Mapping) else None
    if not isinstance(basis, Mapping) or not isinstance(operator, Mapping) or not isinstance(coarse, Mapping):
        _error(errors, "basis/operator/coarse audit is missing")
        return
    basis_required_false = ("construction_workspace_released",)
    if basis.get("construction_workspace_released") is not True:
        _error(errors, "basis construction workspace was not released")
    for key in ("global_numeric_allgather", "global_aij_materialized", "global_schur_materialized", "global_factor_materialized", "global_direct_coarse_solve"):
        if basis.get(key) is not False:
            _error(errors, f"basis forbidden audit {key} is not false")
    if basis.get("regional_rank") != N2_REGIONAL_RANK or basis.get("top_rank") != N2_RANK:
        _error(errors, "basis rank audit is not regional16/top32")
    if basis.get("row_order") != "physical_dofmap_owned_local_order":
        _error(errors, "basis is not in physical DOLFINx owned-row order")
    template_identity = record.get("basis", {}).get("class_template_identity")
    if not isinstance(template_identity, Mapping):
        _error(errors, "class-template identity is missing")
    else:
        class_digests = template_identity.get("class_digests")
        mode_digests = template_identity.get("class_template_mode_digests")
        if not isinstance(class_digests, list) or not class_digests or len(class_digests) > N2_MAX_CLASSES:
            _error(errors, "class digest inventory is missing or exceeds 32")
        elif len(set(class_digests)) != len(class_digests):
            _error(errors, "class digest inventory contains duplicates")
        if not isinstance(mode_digests, list) or len(mode_digests) != len(class_digests or ()):
            _error(errors, "per-class template mode digest inventory does not close")
        elif any(not isinstance(item, list) or len(item) != 2 or not all(isinstance(value, str) for value in item) for item in mode_digests):
            _error(errors, "per-class template mode digest entry is invalid")
    for key in ("t4_transmission_included", "global_aij_materialized", "global_schur_materialized", "factor_materialized", "numeric_allgather", "outer_contraction_run", "global_direct_coarse_solve"):
        if operator.get(key) is not False:
            _error(errors, f"operator forbidden audit {key} is not false")
    nested = operator.get("audit")
    if not isinstance(nested, Mapping):
        _error(errors, "physical action nested audit is missing")
    else:
        for key in ("global_aij_materialized", "global_schur_materialized", "ksp_created", "numeric_allgather", "t4_transmission_included"):
            if nested.get(key) is not False:
                _error(errors, f"physical action audit {key} is not false")
    for key in ("numeric_allgather", "global_aij_materialized", "global_schur_materialized", "factor_materialized"):
        if coarse.get(key) is not False:
            _error(errors, f"coarse forbidden audit {key} is not false")


def _check_setup_audits(
    record: Mapping[str, Any], coarse_metrics: Mapping[str, Any], errors: list[str]
) -> dict[str, Any]:
    inventory = record.get("inventory")
    patch = inventory.get("patch_audit") if isinstance(inventory, Mapping) else None
    regional = inventory.get("regional_audit") if isinstance(inventory, Mapping) else None
    basis_record = record.get("basis")
    basis = basis_record.get("audit") if isinstance(basis_record, Mapping) else None
    coarse_record = record.get("coarse")
    coarse = coarse_record.get("audit") if isinstance(coarse_record, Mapping) else None
    if not all(isinstance(value, Mapping) for value in (patch, regional, basis, coarse)):
        _error(errors, "N2 setup numeric/inventory audits are missing")
        return {}

    global_cells = _required_integer(regional, "global_cell_count", "regional", errors)
    if global_cells != N2_EXPECTED_GLOBAL_CELLS:
        _error(errors, f"global patch/cell count {global_cells!r} != {N2_EXPECTED_GLOBAL_CELLS}")
    row_count_max = _required_integer(patch, "row_count_max", "patch", errors)
    if row_count_max is not None and (row_count_max <= 0 or row_count_max > N2_MAX_LOCAL_ROWS):
        _error(errors, f"patch.row_count_max={row_count_max} exceeds {N2_MAX_LOCAL_ROWS}")
    class_count = _required_integer(patch, "class_count", "patch", errors)
    if class_count is not None and (class_count <= 0 or class_count > N2_MAX_CLASSES):
        _error(errors, f"patch.class_count={class_count} exceeds {N2_MAX_CLASSES}")
    global_factor_count = _required_integer(
        patch, "global_owner_factor_count", "patch", errors
    )
    if class_count is not None and global_factor_count != class_count:
        _error(errors, "global factor count does not equal exact class count")

    class_digests = patch.get("class_digests")
    factor_audits = patch.get("factor_audits_by_class")
    class_patch_counts = patch.get("class_patch_counts_global")
    certification_v2_enabled = patch.get("certification_v2_enabled") is True
    if certification_v2_enabled:
        if patch.get("certification_v2_schema") != LOCAL_FACTOR_CERTIFICATION_SCHEMA:
            _error(errors, "local-factor certification-v2 schema is missing")
        if patch.get("certification_v2_all_class_pass") is not True:
            _error(errors, "local-factor certification-v2 all-class Gate is not true")
    if not isinstance(class_digests, list) or not isinstance(factor_audits, Mapping):
        _error(errors, "per-class factor audit is missing")
    else:
        if set(factor_audits) != set(class_digests):
            _error(errors, "per-class factor audit keys do not equal class inventory")
        for digest in class_digests:
            factor = factor_audits.get(digest)
            if not isinstance(factor, Mapping):
                _error(errors, f"factor audit is missing for class {digest!r}")
                continue
            factor_bytes = _required_integer(factor, "factor_bytes", f"factor[{digest}]", errors)
            if factor_bytes is not None and (factor_bytes <= 0 or factor_bytes > N2_FACTOR_BYTES_LIMIT):
                _error(errors, f"factor[{digest}].factor_bytes={factor_bytes} exceeds {N2_FACTOR_BYTES_LIMIT}")
            _require_bound(
                factor, "factorization_relative_error", f"factor[{digest}]", N1_ALGEBRA_LIMIT, errors
            )
            if certification_v2_enabled:
                certificate = factor.get("certification_v2")
                if not isinstance(certificate, Mapping):
                    _error(errors, f"factor[{digest}] certification-v2 facts are missing")
                else:
                    rows = _required_integer(certificate, "rows", f"factor[{digest}].certification_v2", errors)
                    if rows is not None:
                        expected_thresholds = _local_factor_certification_thresholds(rows)
                        thresholds = certificate.get("thresholds")
                        if not isinstance(thresholds, Mapping) or set(thresholds) != set(expected_thresholds) or any(
                            thresholds.get(key) != value for key, value in expected_thresholds.items()
                        ):
                            _error(errors, f"factor[{digest}] certification-v2 thresholds do not close")
                    if certificate.get("schema") != LOCAL_FACTOR_CERTIFICATION_SCHEMA:
                        _error(errors, f"factor[{digest}] certification-v2 schema does not close")
                    gates = certificate.get("gates")
                    if (
                        certificate.get("gate_pass") is not True
                        or not isinstance(gates, Mapping)
                        or any(value is not True for value in gates.values())
                    ):
                        _error(errors, f"factor[{digest}] certification-v2 Gate is not true")
                    thresholds = certificate.get("thresholds")
                    backward_limit = (
                        float(thresholds.get("normalized_backward_error", 0.0))
                        if isinstance(thresholds, Mapping)
                        else 0.0
                    )
                    factorization_limit = (
                        float(thresholds.get("factorization_relative_error", 0.0))
                        if isinstance(thresholds, Mapping)
                        else 0.0
                    )
                    _require_bound(
                        certificate,
                        "ordinary_relative_residual",
                        f"factor[{digest}].certification_v2",
                        LOCAL_FACTOR_CERTIFICATION_ORDINARY_LIMIT,
                        errors,
                    )
                    _require_bound(
                        certificate,
                        "normalized_backward_error",
                        f"factor[{digest}].certification_v2",
                        backward_limit,
                        errors,
                    )
                    _require_bound(
                        certificate,
                        "factorization_relative_error",
                        f"factor[{digest}].certification_v2",
                        factorization_limit,
                        errors,
                    )
                    if certificate.get("packed_roundtrip_exact") is not True or certificate.get("triangular_repeat_exact") is not True:
                        _error(errors, f"factor[{digest}] certification-v2 packing/repeat is not exact")
                _require_bound(
                    factor,
                    "fixed_rhs_solve_residual",
                    f"factor[{digest}]",
                    LOCAL_FACTOR_CERTIFICATION_ORDINARY_LIMIT,
                    errors,
                )
            else:
                _require_bound(
                    factor, "fixed_rhs_solve_residual", f"factor[{digest}]", N1_ALGEBRA_LIMIT, errors
                )
    if not isinstance(class_patch_counts, Mapping) or not isinstance(class_digests, list):
        _error(errors, "global class patch-count inventory is missing")
    elif set(class_patch_counts) != set(class_digests):
        _error(errors, "global class patch-count keys do not equal class inventory")
    else:
        patch_total = 0
        for digest in class_digests:
            count = class_patch_counts.get(digest)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                _error(errors, f"global patch count for class {digest!r} is invalid")
            else:
                patch_total += int(count)
        if patch_total != N2_EXPECTED_GLOBAL_CELLS:
            _error(
                errors,
                f"global patch/cell inventory total {patch_total} != {N2_EXPECTED_GLOBAL_CELLS}",
            )

    global_factor_bytes = _required_integer(
        patch, "global_owner_factor_bytes", "patch", errors
    )
    factor_byte_sum = None
    if isinstance(class_digests, list) and isinstance(factor_audits, Mapping):
        values = [
            factor_audits[digest].get("factor_bytes")
            for digest in class_digests
            if isinstance(factor_audits.get(digest), Mapping)
        ]
        if len(values) == len(class_digests) and all(
            isinstance(value, int) and not isinstance(value, bool) for value in values
        ):
            factor_byte_sum = int(sum(values))
            if global_factor_bytes != factor_byte_sum:
                _error(errors, "global factor bytes do not equal per-class factor bytes")

    if patch.get("dense_workspace_released") is not True:
        _error(errors, "dense local B/M workspace was not released")
    mode_template_count = _required_integer(patch, "mode_template_count", "patch", errors)
    if class_count is not None and mode_template_count != class_count:
        _error(errors, "mode template count does not equal exact class count")
    mode_bytes = _required_integer(
        patch, "mode_shard_bytes_retained_global", "patch", errors
    )
    if mode_bytes is not None and (mode_bytes < 0 or mode_bytes > N2_MODE_SHARD_HARD_BYTES):
        _error(errors, f"retained mode shard bytes {mode_bytes} exceeds {N2_MODE_SHARD_HARD_BYTES}")

    for key in (
        "B0_hermitian_relative_defect",
        "M_local_hermitian_relative_defect",
        "gradient_gram_defect_max",
        "projected_eigen_residual_max",
        "fixed_solve_residual_max",
    ):
        _require_bound(
            patch,
            key,
            "patch",
            LOCAL_FACTOR_CERTIFICATION_ORDINARY_LIMIT
            if certification_v2_enabled and key == "fixed_solve_residual_max"
            else N1_ALGEBRA_LIMIT,
            errors,
        )
    if certification_v2_enabled:
        _require_bound(
            patch,
            "certification_v2_ordinary_residual_max",
            "patch",
            LOCAL_FACTOR_CERTIFICATION_ORDINARY_LIMIT,
            errors,
        )
    for key in ("B0_min_eigenvalue", "M_local_min_eigenvalue"):
        value = _required_number(patch, key, "patch", errors)
        if value is not None and value <= 0.0:
            _error(errors, f"patch.{key}={value:.17g} is not positive")
    gradient_rank = _required_integer(patch, "gradient_rank_min", "patch", errors)
    if gradient_rank is not None and gradient_rank < 3:
        _error(errors, f"patch.gradient_rank_min={gradient_rank} is below 3")
    _require_bound(patch, "pou_closure_relative_error", "patch", N1_PO_U_LIMIT, errors)
    _require_bound(
        patch,
        "restriction_prolongation_adjoint_relative_error_max",
        "patch",
        N1_RP_LIMIT,
        errors,
    )

    if record.get("levels") != 2 or regional.get("regional_rank_cap") != N2_REGIONAL_RANK:
        _error(errors, "N2 levels/regional rank cap is not frozen to 2/16")
    regional_ranks = regional.get("regional_ranks")
    if not isinstance(regional_ranks, list) or not regional_ranks:
        _error(errors, "regional rank inventory is missing")
    elif any(isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > N2_REGIONAL_RANK for value in regional_ranks):
        _error(errors, "regional rank inventory exceeds rank16")
    _require_bound(regional, "regional_mass_orthogonality_max", "regional", N1_ALGEBRA_LIMIT, errors)
    _require_bound(regional, "regional_projected_eigen_residual_max", "regional", N1_ALGEBRA_LIMIT, errors)
    for key, limit in (("max_candidate_dimension", 64), ("max_projected_dimension", 64)):
        value = _required_integer(regional, key, "regional", errors)
        if value is not None and value > limit:
            _error(errors, f"regional.{key}={value} exceeds {limit}")
    if regional.get("top_rank_built") is not True or regional.get("multilevel_basis_built") is not True:
        _error(errors, "regional/top multilevel basis is not recorded as built")
    if regional.get("regional_dense_row_operator_materialized") is not False:
        _error(errors, "regional dense row operator audit is not false")

    if basis.get("top_rank") != N2_RANK or basis.get("regional_rank") != N2_REGIONAL_RANK:
        _error(errors, "basis top/regional ranks are not 32/16")
    top_defect = _require_bound(
        basis, "top_orthogonality_relative_defect", "basis", N1_ALGEBRA_LIMIT, errors
    )
    if basis.get("construction_workspace_released") is not True:
        _error(errors, "basis construction workspace is not released")

    coarse_rank = _required_integer(coarse, "rank", "coarse", errors)
    if coarse_rank != N2_RANK:
        _error(errors, f"coarse.rank={coarse_rank!r} != {N2_RANK}")
    _require_bound(coarse, "z_orthogonality_defect", "coarse", 1.0e-10, errors)
    _require_bound(coarse, "az_repeat_relative_frobenius", "coarse", N1_ALGEBRA_LIMIT, errors)
    if coarse.get("az_repeat_exact") is not True:
        _error(errors, "coarse AZ repeat exact gate is not true")
    _require_bound(coarse, "physical_consistency_relative", "coarse", N1_ALGEBRA_LIMIT, errors)
    e_condition = _require_bound(coarse, "e_condition_number", "coarse", 1.0e12, errors)
    prefix_audits = coarse.get("prefix_audits")
    if not isinstance(prefix_audits, list):
        _error(errors, "coarse prefix audits are missing")
    else:
        by_prefix = {
            item.get("prefix"): item
            for item in prefix_audits
            if isinstance(item, Mapping)
        }
        for prefix in N2_PREFIXES:
            item = by_prefix.get(prefix)
            if not isinstance(item, Mapping):
                _error(errors, f"coarse prefix audit {prefix} is missing")
                continue
            _require_bound(item, "z_orthogonality_defect", f"coarse.prefix[{prefix}]", 1.0e-10, errors)
            _require_bound(item, "az_repeat_relative_frobenius", f"coarse.prefix[{prefix}]", N1_ALGEBRA_LIMIT, errors)
            _require_bound(item, "physical_consistency_relative", f"coarse.prefix[{prefix}]", N1_ALGEBRA_LIMIT, errors)
            if item.get("az_repeat_exact") is not True or item.get("e_prefix_leading_exact") is not True:
                _error(errors, f"coarse prefix {prefix} exact repeat/leading-E gate is not true")
            _require_bound(item, "e_prefix_leading_relative", f"coarse.prefix[{prefix}]", 1.0e-12, errors)
            _require_bound(item, "e_condition_number", f"coarse.prefix[{prefix}]", 1.0e12, errors)

    identity = record.get("identity_apply")
    if not isinstance(identity, Mapping):
        _error(errors, "zero identity apply audit is missing")
    else:
        if identity.get("input_norm") != 0.0 or identity.get("output_norm") != 0.0:
            _error(errors, "zero identity apply did not remain zero")
        if identity.get("finite") is not True or identity.get("zero_output") is not True:
            _error(errors, "zero identity apply finite/zero gate is not true")
        if identity.get("rho_run") is not False or identity.get("ksp_created") is not False:
            _error(errors, "zero identity apply is not setup-only")
        _required_number(identity, "wall_seconds_rank_max", "identity_apply", errors)

    return {
        "global_cell_count": global_cells,
        "row_count_max": row_count_max,
        "class_count": class_count,
        "global_factor_count": global_factor_count,
        "mode_shard_bytes": mode_bytes,
        "top_orthogonality_defect": top_defect,
        "e_condition_number": e_condition,
        "coarse_metrics": dict(coarse_metrics),
    }


def _check_markers(record: Mapping[str, Any], errors: list[str]) -> None:
    markers = record.get("markers")
    ledger = markers.get("ledger") if isinstance(markers, Mapping) else None
    if not isinstance(ledger, list):
        _error(errors, "marker ledger is missing")
        return
    names = [item.get("marker") for item in ledger if isinstance(item, Mapping)]
    expected = ["preflight", "mesh_space_mpc", "JIT", "subdomain_inventory", "local_factor_build", "local_mode_build", "regional_coarse_build", "top_level_build", "identity_apply", "post_setup_release", "canonical_evidence", "cleanup"]
    if names != expected:
        _error(errors, f"marker order {names!r} != expected {expected!r}")
    previous = -1
    for item in ledger:
        if not isinstance(item, Mapping) or not isinstance(item.get("monotonic_ns"), int):
            _error(errors, "marker lacks monotonic timestamp")
            continue
        if int(item["monotonic_ns"]) <= previous:
            _error(errors, "marker monotonic timestamps are not increasing")
        previous = int(item["monotonic_ns"])


def _check_matrix_artifacts(record: Mapping[str, Any], raw_dir: Path, errors: list[str]) -> dict[str, Any]:
    artifacts = record.get("artifacts")
    arrays = artifacts.get("arrays") if isinstance(artifacts, Mapping) else None
    if not isinstance(arrays, Mapping):
        _error(errors, "owner-local array descriptors are missing")
        return {}
    shards = arrays.get("owner_shards")
    if not isinstance(shards, list) or not shards:
        _error(errors, "owner_shards is missing or empty")
        return {}
    local_arrays: dict[str, Any] = {"per_rank": {}}
    ranges: list[tuple[int, int]] = []
    total_rows = 0
    for shard in shards:
        if not isinstance(shard, Mapping) or not isinstance(shard.get("rank"), int):
            _error(errors, "owner shard descriptor is invalid")
            continue
        rank = int(shard["rank"])
        rank_arrays: dict[str, np.ndarray] = {}
        for name in ("Z16", "Z32", "AZ32"):
            descriptor = shard.get(name)
            if not isinstance(descriptor, Mapping):
                _error(errors, f"owner shard {rank} lacks {name}")
                continue
            array, array_errors = _array_descriptor(descriptor, raw_dir)
            errors.extend(array_errors)
            if array is not None:
                rank_arrays[name] = array
        z32 = rank_arrays.get("Z32")
        if z32 is None:
            continue
        rows, columns = z32.shape
        if columns != N2_RANK:
            _error(errors, f"owner shard {rank} Z32 does not have rank 32")
        if rank_arrays.get("Z16") is not None and rank_arrays["Z16"].shape != (rows, N2_REGIONAL_RANK):
            _error(errors, f"owner shard {rank} Z16 shape does not match Z32")
        if rank_arrays.get("AZ32") is not None and rank_arrays["AZ32"].shape != (rows, N2_RANK):
            _error(errors, f"owner shard {rank} AZ32 shape does not match Z32")
        ownership = shard.get("ownership_range")
        if not isinstance(ownership, list) or len(ownership) != 2 or any(isinstance(value, bool) or not isinstance(value, int) for value in ownership):
            _error(errors, f"owner shard {rank} ownership_range is invalid")
        else:
            start, stop = map(int, ownership)
            if stop - start != rows or start < 0 or stop < start:
                _error(errors, f"owner shard {rank} ownership range does not close rows")
            ranges.append((start, stop))
        if shard.get("local_owned_rows") != rows:
            _error(errors, f"owner shard {rank} local_owned_rows does not close Z32")
        total_rows += rows
        local_arrays["per_rank"][rank] = rank_arrays
    if total_rows != N2_EXPECTED_GLOBAL_ROWS:
        _error(errors, f"owner shard total rows {total_rows} != {N2_EXPECTED_GLOBAL_ROWS}")
    if arrays.get("global_owned_rows") != total_rows:
        _error(errors, "record global_owned_rows does not close owner shards")
    if ranges:
        ordered = sorted(ranges)
        if ordered[0][0] != 0 or any(left[1] != right[0] for left, right in zip(ordered, ordered[1:])):
            _error(errors, "owner shard ownership ranges are not contiguous")
        if ordered[-1][1] != N2_EXPECTED_GLOBAL_ROWS:
            _error(errors, "owner shard ownership ranges do not end at global row count")
    return local_arrays


def _check_coarse_arrays(record: Mapping[str, Any], local_arrays: Mapping[str, np.ndarray], raw_dir: Path, expected_global_rows: int, errors: list[str]) -> dict[str, Any]:
    shards = local_arrays.get("per_rank")
    if not isinstance(shards, Mapping):
        return {}
    z_gram = np.zeros((N2_RANK, N2_RANK), dtype=np.complex128)
    e_recomputed = np.zeros_like(z_gram)
    for rank, arrays in shards.items():
        if not isinstance(arrays, Mapping) or "Z32" not in arrays or "AZ32" not in arrays:
            _error(errors, f"owner shard {rank} lacks Z32/AZ32 for algebra")
            continue
        z = np.asarray(arrays["Z32"], dtype=np.complex128)
        az = np.asarray(arrays["AZ32"], dtype=np.complex128)
        z_gram += z.conj().T @ z
        e_recomputed += z.conj().T @ az
    gram = z_gram
    z_defect = _relative(gram - np.eye(N2_RANK, dtype=np.complex128), np.eye(N2_RANK, dtype=np.complex128))
    if not np.isfinite(z_defect) or z_defect > 1.0e-10:
        _error(errors, f"Z32 orthogonality {z_defect} exceeds 1e-10")
    e_desc = record.get("artifacts", {}).get("E32") if isinstance(record.get("artifacts"), Mapping) else None
    e = None
    if isinstance(e_desc, Mapping):
        e, array_errors = _array_descriptor(e_desc, raw_dir, expected_shape=(N2_RANK, N2_RANK))
        errors.extend(array_errors)
    else:
        _error(errors, "E32 descriptor is missing")
    if e is None:
        return {"z_orthogonality_relative": z_defect}
    e_relative = _relative(e_recomputed - e, e)
    if not np.isfinite(e_relative) or e_relative > 1.0e-11:
        _error(errors, f"E32 recomputation relative {e_relative} exceeds 1e-11")
    condition = float(np.linalg.cond(e))
    if not np.isfinite(condition) or condition > 1.0e12:
        _error(errors, f"E32 condition {condition} exceeds 1e12")
    return {"z_orthogonality_relative": z_defect, "e_recomputed_relative": e_relative, "e_condition": condition, "e_hermitian_relative_defect": _relative(e - e.conj().T, e)}


def check_worker_record(record_path: Path, *, expected_sha: str, expected_mpi_size: int, raw_dir: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    try:
        record = _load(Path(record_path))
    except ValueError as exc:
        return {"passed": False, "errors": [str(exc)], "record": str(record_path)}
    if not isinstance(record, Mapping):
        return {"passed": False, "errors": ["record must be an object"], "record": str(record_path)}
    _check_identity(record, Path(record_path), expected_sha, expected_mpi_size, errors)
    _check_markers(record, errors)
    _check_forbidden(record, errors)
    actual_raw = Path(raw_dir) if raw_dir is not None else Path(str(record.get("raw_dir", "")))
    if not actual_raw.is_absolute():
        actual_raw = Path(record_path).parent / actual_raw
    local_arrays = _check_matrix_artifacts(record, actual_raw, errors)
    coarse = _check_coarse_arrays(record, local_arrays, actual_raw, N2_EXPECTED_GLOBAL_ROWS, errors)
    setup = _check_setup_audits(record, coarse, errors)
    watchdog = _watchdog(Path(record_path), record, errors)
    retained = record.get("retained_components")
    if not isinstance(retained, Mapping):
        _error(errors, "retained component closure is missing")
    else:
        if retained.get("retained_closure_limit_bytes") != N2_RETAINED_HARD_BYTES:
            _error(errors, "retained closure hard limit is not the N0 contract")
        closure = retained.get("retained_closure_bytes_global")
        if not isinstance(closure, int) or closure > N2_RETAINED_HARD_BYTES:
            _error(errors, f"retained closure {closure!r} exceeds N0 hard limit")
        if retained.get("unbudgeted_unknown") != 0:
            _error(errors, "retained closure has unknown bytes")
    passed = not errors
    return {
        "schema": "task038.full3d.local-spectral.n2-check.v1",
        "record": str(Path(record_path).resolve()),
        "mpi_size": expected_mpi_size,
        "passed": passed,
        "errors": errors,
        "gates": {"identity": not any("identity" in error or "SHA" in error for error in errors), "markers": not any("marker" in error for error in errors), "forbidden": not any("forbidden" in error or "audit" in error for error in errors), "arrays": bool(local_arrays) and not any("array" in error or "Z32" in error or "E32" in error for error in errors), "coarse": bool(coarse) and not any("orthogonality" in error or "E32" in error or "condition" in error for error in errors), "resource": watchdog is not None and not any("watchdog" in error or "process-tree" in error or "peak" in error or "swap" in error for error in errors)},
        "coarse": coarse,
        "setup": setup,
        "watchdog": watchdog,
        "errors_count": len(errors),
    }


def check_pair(mpi1_record: Path, mpi2_record: Path, *, expected_sha: str, output: Path | None = None) -> dict[str, Any]:
    left = check_worker_record(mpi1_record, expected_sha=expected_sha, expected_mpi_size=1)
    right = check_worker_record(mpi2_record, expected_sha=expected_sha, expected_mpi_size=2)
    errors = list(left.get("errors", [])) + list(right.get("errors", []))
    comparisons: dict[str, Any] = {}
    if left.get("passed") and right.get("passed"):
        left_record = _load(mpi1_record)
        right_record = _load(mpi2_record)
        left_basis = left_record.get("basis", {})
        right_basis = right_record.get("basis", {})
        left_templates = left_basis.get("class_template_identity", {})
        right_templates = right_basis.get("class_template_identity", {})
        if left_templates.get("class_digests") != right_templates.get("class_digests"):
            errors.append("MPI1/MPI2 class digest inventories differ")
        if left_templates.get("class_template_mode_digests") != right_templates.get("class_template_mode_digests"):
            errors.append("MPI1/MPI2 class-template mode digest inventories differ")
        left_mixing = left_basis.get("top_mixing_identity")
        right_mixing = right_basis.get("top_mixing_identity")
        if left_mixing != right_mixing:
            errors.append("MPI1/MPI2 fixed top mixing identity differs")
        for label, record in (("MPI1", left_record), ("MPI2", right_record)):
            template = record.get("basis", {}).get("class_template_identity", {})
            digests = template.get("class_digests", [])
            owners = template.get("class_owners")
            if not isinstance(owners, Mapping) or set(owners) != set(digests):
                errors.append(f"{label} class owner map is incomplete")
            elif any(isinstance(owner, bool) or not isinstance(owner, int) or owner < 0 or owner >= record.get("mpi", {}).get("size", 0) for owner in owners.values()):
                errors.append(f"{label} class owner map has an invalid rank")
        for role in ("Z32", "AZ32"):
            left_desc = left_record["artifacts"]["canonical_matrices"][role]
            right_desc = right_record["artifacts"]["canonical_matrices"][role]
            comparison = compare_canonical_matrices(
                Path(left_desc["manifest_path"]),
                Path(right_desc["manifest_path"]),
                relative_tolerance=1.0e-11,
                prefixes=N2_PREFIXES,
            )
            comparisons[role] = comparison
            if not comparison.get("passed"):
                errors.append(f"cross-MPI {role} canonical comparison failed")
    result = {
        "schema": "task038.full3d.local-spectral.n2-pair-check.v1",
        "source_git_sha": expected_sha,
        "passed": not errors,
        "individual": {"mpi1": left, "mpi2": right},
        "canonical_comparisons": comparisons,
        "errors": errors,
    }
    if output is not None:
        if Path(output).exists():
            raise FileExistsError(f"pair check output already exists: {output}")
        Path(output).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independent N2 setup checker")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-mpi-size", type=int, choices=(1, 2))
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--mpi1-record", type=Path)
    parser.add_argument("--mpi2-record", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.record is not None:
        if args.expected_mpi_size is None:
            parser.error("--expected-mpi-size is required with --record")
        result = check_worker_record(args.record, expected_sha=args.expected_source_sha, expected_mpi_size=args.expected_mpi_size, raw_dir=args.raw_dir)
    elif args.mpi1_record is not None and args.mpi2_record is not None:
        result = check_pair(args.mpi1_record, args.mpi2_record, expected_sha=args.expected_source_sha, output=args.output)
    else:
        parser.error("provide --record or both --mpi1-record and --mpi2-record")
    if args.output is not None and args.record is not None:
        if args.output.exists():
            raise FileExistsError(f"checker output already exists: {args.output}")
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
