"""Pure T2 record checker; no solver, PETSc, MPI, or worker imports."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


T2_SCHEMA = "task038.full3d.iterative.t2.action-record.v1"
T2_CHECK_SCHEMA = "task038.full3d.iterative.t2.action-check.v1"
T2_PROFILE = "full3d_scalable_v1"
T2_WAVELENGTH_NM = 13.5
T2_REPEATS = 12
T2_CASES = {
    "p2-h50": {"degree": 2, "h_nm": 50.0, "reference": "assembled"},
    "p3-h50": {"degree": 3, "h_nm": 50.0, "reference": "assembled"},
    "p6-h10": {"degree": 6, "h_nm": 10.0, "reference": "independent"},
    "p6-h5": {"degree": 6, "h_nm": 5.0, "reference": "scaling_only"},
}
T2_ACTION_RELATIVE_LIMIT = 1.0e-11
T2_MPI_CANONICAL_LIMIT = 1.0e-12
T2_SMALL_ORACLE_LIMIT = 1.0e-12
T2_REPEAT_LIMIT = 1.0e-13
T2_RETAINED_EXPONENT_LIMIT = 1.10
T2_RSS_STABILITY_START = 4
T2_RSS_STABILITY_LIMIT_BYTES = 64 * 1024 * 1024


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_manifest_path(raw_dir: Path, descriptor: Mapping[str, Any]) -> Path:
    relative = descriptor.get("canonical_manifest_relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("canonical manifest path is invalid")
    path = (raw_dir / relative).resolve()
    path.relative_to(raw_dir.resolve())
    return path


def _validate_canonical_manifest(
    raw_dir: Path, descriptor: Mapping[str, Any]
) -> list[str]:
    from benchmarks.canonical_vector_artifacts import read_canonical_manifest

    try:
        path = _canonical_manifest_path(raw_dir, descriptor)
        if not path.is_file():
            return ["canonical manifest is missing"]
        digest = _sha256_path(path)
        errors = [
            message
            for ok, message in (
                (
                    descriptor.get("canonical_manifest_bytes") == path.stat().st_size,
                    "canonical manifest byte-size mismatch",
                ),
                (
                    descriptor.get("canonical_manifest_sha256") == digest,
                    "canonical manifest SHA mismatch",
                ),
            )
            if not ok
        ]
        manifest = read_canonical_manifest(path, digest)
        if descriptor.get("canonical_packet_count") != manifest.get(
            "global_summed_packet_count"
        ):
            errors.append("canonical packet count mismatch")
        return errors
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"canonical manifest is invalid: {exc}"]


def _validate_binary_artifact(raw_dir: Path, descriptor: Mapping[str, Any]) -> list[str]:
    import numpy as np

    relative = descriptor.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        return ["artifact relative_path is invalid"]
    path = (raw_dir / relative).resolve()
    try:
        path.relative_to(raw_dir.resolve())
    except ValueError:
        return [f"artifact escapes raw directory: {relative}"]
    if not path.is_file():
        return [f"artifact is missing: {relative}"]
    errors: list[str] = []
    shape = descriptor.get("shape")
    if descriptor.get("dtype") != "complex128":
        errors.append(f"{relative}: dtype mismatch")
    if (
        not isinstance(shape, list)
        or len(shape) != 1
        or not isinstance(shape[0], int)
        or isinstance(shape[0], bool)
        or shape[0] <= 0
    ):
        return errors + [f"{relative}: shape descriptor is invalid"]
    expected_bytes = int(shape[0]) * 16
    if descriptor.get("bytes") != expected_bytes or path.stat().st_size != expected_bytes:
        errors.append(f"{relative}: byte-size mismatch")
    digest = _sha256_path(path)
    if descriptor.get("file_sha256") != digest:
        errors.append(f"{relative}: file SHA mismatch")
    if descriptor.get("array_sha256") != digest:
        errors.append(f"{relative}: array SHA mismatch")
    values = np.memmap(path, dtype=np.complex128, mode="r", shape=(shape[0],))
    try:
        if descriptor.get("finite") is not True or not bool(np.all(np.isfinite(values))):
            errors.append(f"{relative}: non-finite values")
    finally:
        del values
    if "canonical_manifest_relative_path" in descriptor:
        errors.extend(_validate_canonical_manifest(raw_dir, descriptor))
    return errors


def _check_record_payload(
    record: Mapping[str, Any],
    *,
    h10: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    numeric_failures: list[str] = []

    def require(ok: bool, message: str, numeric: bool = False) -> None:
        if not ok:
            errors.append(message)
            if numeric:
                numeric_failures.append(message)

    def finite(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and float(value) >= 0
        )

    def nint(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    def list12(value: Any) -> bool:
        return isinstance(value, list) and len(value) == T2_REPEATS

    for key in (
        "schema case profile raw_dir source mpi model artifacts reference repeats "
        "candidate_audit resource"
    ).split():
        require(key in record, f"missing required field: {key}")

    case = record.get("case")
    for value, expected, message in (
        (record.get("schema"), T2_SCHEMA, "record schema mismatch"),
        (record.get("profile"), T2_PROFILE, "profile mismatch"),
    ):
        require(value == expected, message)
    require(isinstance(case, str) and case in T2_CASES, "unknown T2 case")

    source = record.get("source")
    if not isinstance(source, Mapping):
        require(False, "source audit is missing")
    else:
        for ok, message in (
            (
                source.get("commit_sha_start") == source.get("commit_sha_end"),
                "source SHA changed",
            ),
            (
                not source.get("tracked_status_start")
                and not source.get("tracked_status_end"),
                "source worktree was dirty",
            ),
            (
                source.get("expected_sha") == source.get("commit_sha_start"),
                "source SHA does not match expected SHA",
            ),
        ):
            require(ok, message)

    model = record.get("model")
    if not isinstance(model, Mapping):
        require(False, "model identity is missing")
    else:
        phases = model.get("floquet_phases")
        require(
            model.get("wavelength_nm") == T2_WAVELENGTH_NM,
            "wavelength is not the frozen 13.5 nm model",
        )
        require(
            isinstance(phases, Mapping)
            and all(phases.get(axis) for axis in ("x_nontrivial", "y_nontrivial")),
            "nontrivial x/y Floquet phases are not evidenced",
        )
        require(
            all(nint(value) and value > 0 for value in (
                model.get("edge_constraints"),
                model.get("face_constraints"),
            )),
            "edge and face constraints are not both evidenced",
        )

    mpi = record.get("mpi")
    require(
        isinstance(mpi, Mapping) and mpi.get("size") in {1, 2},
        "MPI size must be 1 or 2",
    )

    raw_dir = record.get("raw_dir")
    artifacts = record.get("artifacts")
    raw_path = Path(raw_dir) if isinstance(raw_dir, str) else None
    source_descriptor = source_after_descriptor = action_descriptor = None
    if raw_path is None or not isinstance(artifacts, Mapping):
        require(False, "raw artifact inventory is missing")
    else:
        names = ("source", "source_after", "action")
        if case in {"p2-h50", "p3-h50", "p6-h10"}:
            names += ("reference_action",)
        for name in names:
            descriptor = artifacts.get(name)
            require(isinstance(descriptor, Mapping), f"missing artifact descriptor: {name}")
            if isinstance(descriptor, Mapping):
                errors.extend(_validate_binary_artifact(raw_path, descriptor))
        source_descriptor = artifacts.get("source")
        source_after_descriptor = artifacts.get("source_after")
        action_descriptor = artifacts.get("action")
        complete = isinstance(source_descriptor, Mapping) and isinstance(
            source_after_descriptor, Mapping
        )
        require(complete, "source before/after descriptors are incomplete")
        if complete:
            require(
                source_descriptor.get("file_sha256")
                == source_after_descriptor.get("file_sha256"),
                "source raw values changed",
            )

    repeats = record.get("repeats")
    warm_rss_span = None
    measured_owner_layout = False
    if not isinstance(repeats, Mapping):
        require(False, "repeat audit is missing")
    else:
        require(repeats.get("count") == T2_REPEATS, "repeat count is not exactly 12")
        fields = tuple(
            repeats.get(name)
            for name in (
                "elapsed_seconds",
                "rss_bytes",
                "swap_used_bytes",
                "output_sha256",
                "relative_differences",
            )
        )
        if not all(list12(value) for value in fields):
            require(False, "repeat telemetry is incomplete")
        else:
            times, rss, swaps, hashes, differences = fields
            require(all(finite(value) for value in times), "repeat timing is not finite")
            rss_ok = all(nint(value) for value in rss)
            require(rss_ok, "repeat RSS samples are invalid")
            if rss_ok:
                warm = rss[T2_RSS_STABILITY_START:]
                warm_rss_span = max(warm) - min(warm)
            require(all(value == 0 for value in swaps), "swap usage is nonzero")
            action_sha = (
                action_descriptor.get("file_sha256")
                if isinstance(action_descriptor, Mapping)
                else None
            )
            hashes_ok = all(
                isinstance(value, str) and len(value) == 64 for value in hashes
            )
            require(bool(action_sha) and hashes_ok, "repeat output hashes are invalid")
            if action_sha and hashes_ok:
                require(hashes[0] == action_sha, "first repeat hash does not bind action artifact")
            for value in differences:
                require(finite(value), "repeat relative identity is invalid")
                if finite(value) and value > T2_REPEAT_LIMIT:
                    require(False, "repeat relative identity exceeds the Gate", True)
            if hashes_ok and any(value != hashes[0] for value in hashes):
                require(False, "repeat canonical hash identity exceeds the Gate", True)
            measured_owner_layout = bool(
                source_descriptor
                and source_after_descriptor
                and source_descriptor.get("file_sha256")
                == source_after_descriptor.get("file_sha256")
                and hashes_ok
                and hashes[0] == action_sha
                and all(finite(value) and value <= T2_REPEAT_LIMIT for value in differences)
            )

    reference = record.get("reference")
    if not isinstance(reference, Mapping):
        require(False, "reference audit is missing")
    else:
        require(finite(reference.get("setup_seconds")), "reference setup time is invalid")
        require(nint(reference.get("setup_self_rss_bytes")), "reference setup RSS is missing")
        require(
            reference.get("setup_rss_semantics") == "mpi_rank_max_current_self_rss",
            "reference setup RSS semantics are not rank-max current RSS",
        )
        reference_error = reference.get("relative_error")
        if case in {"p2-h50", "p3-h50", "p6-h10"}:
            limit = (
                T2_SMALL_ORACLE_LIMIT
                if case in {"p2-h50", "p3-h50"}
                else T2_ACTION_RELATIVE_LIMIT
            )
            valid = finite(reference_error)
            require(valid, "reference relative error is invalid")
            if valid and reference_error > limit:
                message = (
                    "assembled oracle identity exceeds the Gate"
                    if case in {"p2-h50", "p3-h50"}
                    else "independent reference identity exceeds the Gate"
                )
                require(False, message, True)
            if case in {"p2-h50", "p3-h50"}:
                require(
                    reference.get("matrix_destroyed_before_repeats") is True,
                    "assembled oracle lifetime was not closed",
                )
        elif case == "p6-h5":
            require(
                reference.get("kind") == "scaling_only",
                "p6-h5 reference must be scaling_only",
            )

    candidate = record.get("candidate_audit")
    if not isinstance(candidate, Mapping):
        require(False, "candidate audit is missing")
    else:
        require(
            str(candidate.get("matrix_type", "")).lower() == "python",
            "candidate is not a PETSc Python shell",
        )
        for key, expected, message in (
            (
                "apply_count",
                T2_REPEATS,
                "candidate apply count is not exactly 12",
            ),
            (
                "phase_application",
                "finalized_floquet_mpc_once",
                "Floquet/MPC phase application is not finalized exactly once",
            ),
            (
                "orientation",
                "dolfinx_n1curl_form_kernel",
                "N1curl orientation identity is missing",
            ),
        ):
            require(candidate.get(key) == expected, message)
        for key in (
            "mpc_enabled",
            "owner_local",
            "constraint_nnz_closes",
            "fresh_packed_arrays_released",
        ):
            require(candidate.get(key) is True, f"candidate audit failed: {key}")
        for key in (
            "numeric_allgather",
            "replicated_global_numeric_vector",
            "ordinary_default_changed",
        ):
            require(
                candidate.get(key) is False,
                f"candidate communication/default audit failed: {key}",
            )
        for key in (
            "factor_count",
            "retained_dense_cell_tensor_count",
            "cell_schur_matrix_nnz",
            "slab_matrix_nnz",
        ):
            require(candidate.get(key) == 0, f"candidate retains forbidden storage: {key}")
        for key in (
            "global_matrix_materialized",
            "global_constraint_matrix_materialized",
            "global_condensed_schur_materialized",
            "cell_schur_matrix_materialized",
            "slab_matrix_materialized",
            "dense_cell_tensor_materialized_per_apply",
            "ksp_created",
            "dtn_used",
        ):
            require(
                candidate.get(key) in {False, 0},
                f"candidate materialization Gate failed: {key}",
            )
        components = candidate.get("retained_numeric_payload_components")
        local_bytes = candidate.get("retained_numeric_payload_local_bytes")
        global_bytes = candidate.get("retained_numeric_payload_global_max_bytes")
        valid_components = isinstance(components, Mapping) and nint(local_bytes)
        require(valid_components, "retained candidate payload is incomplete")
        if valid_components:
            values_ok = all(nint(value) for value in components.values())
            require(values_ok, "retained candidate payload does not close")
            if values_ok:
                require(
                    local_bytes == sum(components.values()),
                    "retained candidate payload does not close",
                )
        require(
            isinstance(global_bytes, int)
            and not isinstance(global_bytes, bool)
            and global_bytes > 0,
            "retained candidate payload is missing",
        )

    warm_stable = warm_rss_span is not None and warm_rss_span <= T2_RSS_STABILITY_LIMIT_BYTES
    resource = record.get("resource")
    if not isinstance(resource, Mapping):
        require(False, "resource telemetry is missing")
    else:
        require(
            resource.get("rss_semantics") == "mpi_rank_max_current_self_rss",
            "RSS semantics are not explicit",
        )
        require(
            resource.get("process_tree_evidence") == "not_measured_t2",
            "T2 process-tree peak must remain explicitly not measured",
        )
        require(warm_rss_span is not None, "warm RSS stability span is missing")
        if warm_rss_span is not None and warm_rss_span > T2_RSS_STABILITY_LIMIT_BYTES:
            require(False, "warm RSS stability span exceeds the Gate", True)

    scaling: dict[str, Any] = {}
    if h10 is not None and case == "p6-h5":
        try:
            rows_now = int(model["global_rows"])
            rows_h10 = int(h10["model"]["global_rows"])
            bytes_now = int(candidate["retained_numeric_payload_global_max_bytes"])
            bytes_h10 = int(h10["candidate_audit"]["retained_numeric_payload_global_max_bytes"])
            if min(rows_now, rows_h10, bytes_now, bytes_h10) <= 0 or rows_now <= rows_h10:
                raise ValueError("scaling inputs are invalid")
            exponent = math.log(bytes_now / bytes_h10) / math.log(rows_now / rows_h10)
            require(math.isfinite(exponent), "h10-to-h5 scaling inputs are invalid")
            scaling["retained_exponent_h10_to_h5"] = exponent
            if exponent > T2_RETAINED_EXPONENT_LIMIT:
                require(False, "h10-to-h5 retained exponent exceeds the Gate", True)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            require(False, "h10-to-h5 scaling inputs are invalid")

    source_stable = bool(
        source_descriptor
        and source_after_descriptor
        and source_descriptor.get("file_sha256")
        == source_after_descriptor.get("file_sha256")
    )
    evidence_failures = [item for item in errors if item not in numeric_failures]
    return {
        "schema": T2_CHECK_SCHEMA,
        "passed": not errors,
        "classification": (
            "T2_ACTION_PASS"
            if not errors
            else "T2_NUMERIC_FAIL"
            if numeric_failures and not evidence_failures
            else "T2_EXECUTION_OR_EVIDENCE_FAIL"
        ),
        "checks": {
            "evidence": not bool(evidence_failures),
            "numeric_only_failure": bool(numeric_failures and not evidence_failures),
            "source_stable": source_stable,
            "owner_layout_identity": measured_owner_layout,
            "rss_stable": warm_stable,
        },
        "problems": errors,
        "scaling": scaling,
    }

def _canonical_peer_problems(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> list[str]:
    left_model, right_model = left.get("model"), right.get("model")
    left_mpi, right_mpi = left.get("mpi"), right.get("mpi")
    if not all((
        isinstance(left_model, Mapping),
        isinstance(right_model, Mapping),
        left_model.get("config_sha256") == right_model.get("config_sha256")
        if isinstance(left_model, Mapping) and isinstance(right_model, Mapping)
        else False,
        left.get("case") == right.get("case"),
        isinstance(left_mpi, Mapping),
        isinstance(right_mpi, Mapping),
        left_mpi.get("size") != right_mpi.get("size")
        if isinstance(left_mpi, Mapping) and isinstance(right_mpi, Mapping)
        else False,
    )):
        return ["MPI peer model identity differs"]
    left_artifacts, right_artifacts = left.get("artifacts"), right.get("artifacts")
    left_raw, right_raw = left.get("raw_dir"), right.get("raw_dir")
    if not all((
        isinstance(left_artifacts, Mapping),
        isinstance(right_artifacts, Mapping),
        isinstance(left_raw, str),
        isinstance(right_raw, str),
    )):
        return ["MPI peer artifact identity is incomplete"]

    from benchmarks.canonical_vector_artifacts import compare_canonical_manifests

    problems: list[str] = []
    for name in ("source", "action"):
        left_descriptor = left_artifacts.get(name)
        right_descriptor = right_artifacts.get(name)
        if not isinstance(left_descriptor, Mapping) or not isinstance(
            right_descriptor, Mapping
        ):
            problems.append(f"MPI canonical descriptor missing: {name}")
            continue
        try:
            comparison = compare_canonical_manifests(
                _canonical_manifest_path(Path(left_raw), left_descriptor),
                _canonical_manifest_path(Path(right_raw), right_descriptor),
                left_sha256=left_descriptor["canonical_manifest_sha256"],
                right_sha256=right_descriptor["canonical_manifest_sha256"],
                relative_tolerance=T2_MPI_CANONICAL_LIMIT,
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            problems.append(f"MPI canonical packet check failed: {name}: {exc}")
        else:
            if not comparison["pass"]:
                problems.append(f"MPI canonical packet mismatch: {name}")
    return problems


def _load_record(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"record is unreadable: {exc}"
    if not isinstance(value, dict):
        return None, "record root must be an object"
    return value, None


def _failed_result(message: str) -> dict[str, Any]:
    return {
        "schema": T2_CHECK_SCHEMA,
        "passed": False,
        "classification": "T2_EXECUTION_OR_EVIDENCE_FAIL",
        "checks": {"evidence": False},
        "problems": [message],
    }


def check_t2_record(record_path: str | Path) -> dict[str, Any]:
    path = Path(record_path)
    record, message = _load_record(path)
    if message is not None:
        return _failed_result(message)
    result = _check_record_payload(record)
    result["record"] = str(path)
    return result


def check_t2_aggregate(
    *,
    p2_record_path: str | Path,
    p3_record_path: str | Path,
    p6_h10_mpi1_record_path: str | Path,
    p6_h10_mpi2_record_path: str | Path,
    p6_h5_record_path: str | Path,
) -> dict[str, Any]:
    specs = {
        "p2_mpi1": (Path(p2_record_path), "p2-h50", 1),
        "p3_mpi1": (Path(p3_record_path), "p3-h50", 1),
        "p6_h10_mpi1": (Path(p6_h10_mpi1_record_path), "p6-h10", 1),
        "p6_h10_mpi2": (Path(p6_h10_mpi2_record_path), "p6-h10", 2),
        "p6_h5_mpi1": (Path(p6_h5_record_path), "p6-h5", 1),
    }
    records: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    numeric_failures: list[str] = []
    identity_problems: list[str] = []
    for label, (path, expected_case, expected_mpi) in specs.items():
        value, message = _load_record(path)
        if message is not None:
            message = f"{label}: {message}"
            errors.append(message)
            identity_problems.append(message)
            continue
        records[label] = value
        mpi = value.get("mpi")
        identity_ok = (
            value.get("case") == expected_case
            and isinstance(mpi, Mapping)
            and mpi.get("size") == expected_mpi
            and mpi.get("expected_size") == expected_mpi
        )
        if not identity_ok:
            message = f"{label}: case/MPI identity is wrong"
            errors.append(message)
            identity_problems.append(message)

    scaling: dict[str, Any] = {}

    def validate(label: str, h10: Mapping[str, Any] | None = None) -> None:
        value = records.get(label)
        if value is None:
            return
        result = _check_record_payload(value, h10=h10)
        if label == "p6_h5_mpi1":
            scaling.update(result.get("scaling", {}))
        target = (
            numeric_failures
            if result["classification"] == "T2_NUMERIC_FAIL"
            else errors
        )
        target.extend(f"{label}: {item}" for item in result["problems"])

    for label in ("p2_mpi1", "p3_mpi1", "p6_h10_mpi1"):
        validate(label)
    if "p6_h10_mpi1" not in records:
        errors.append("p6_h10_mpi1: required MPI peer record is missing")
    validate("p6_h10_mpi2")
    if "p6_h10_mpi1" not in records:
        errors.append("p6_h5_mpi1: required h10 scaling record is missing")
    validate("p6_h5_mpi1", records.get("p6_h10_mpi1"))

    peer_problems = []
    if "p6_h10_mpi1" in records and "p6_h10_mpi2" in records:
        peer_problems = _canonical_peer_problems(
            records["p6_h10_mpi1"], records["p6_h10_mpi2"]
        )
        errors.extend(f"p6_h10 MPI peer: {item}" for item in peer_problems)
    problems = errors + numeric_failures
    return {
        "schema": T2_CHECK_SCHEMA,
        "passed": not problems,
        "classification": (
            "T2_ACTION_PASS"
            if not problems
            else "T2_NUMERIC_FAIL"
            if numeric_failures and not errors
            else "T2_EXECUTION_OR_EVIDENCE_FAIL"
        ),
        "checks": {
            "exact_five_record_set": not identity_problems,
            "mpi_canonical_identity": not peer_problems,
            "mandatory_h10_to_h5_scaling": not any(
                "h10-to-h5" in item for item in errors + numeric_failures
            ),
            "evidence": not bool(errors),
            "numeric_only_failure": bool(numeric_failures and not errors),
        },
        "records": {label: str(path) for label, (path, _, _) in specs.items()},
        "scaling": scaling,
        "problems": problems,
    }
