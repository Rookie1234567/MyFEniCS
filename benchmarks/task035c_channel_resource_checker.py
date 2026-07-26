from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ORDER_COUNT = 80
EXPECTED_SIGNIFICANT_CHANNEL_COUNT = 12
SIGNIFICANT_POWER_FLOOR = 1.0e-8
P2_RELATIVE_TOLERANCE = 1.0e-3
AMPLITUDE_DENOMINATOR_FLOOR = 1.0e-15
VALID_MODE_COUNTS = (120, 160)


class Task035cEvidenceError(ValueError):
    """Raised when a supposedly hash-bound authority fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Task035cEvidenceError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{context} must be an object")
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
        f"{context} must be an array",
    )
    return value


def _finite(value: Any, context: str) -> float:
    _require(
        isinstance(value, (int, float)) and math.isfinite(float(value)),
        f"{context} must be finite",
    )
    return float(value)


def _integer(value: Any, context: str) -> int:
    number = _finite(value, context)
    _require(number.is_integer(), f"{context} must be an integer")
    return int(number)


def _complex_pair(value: Any, context: str) -> complex:
    pair = _sequence(value, context)
    _require(len(pair) == 2, f"{context} must have two components")
    return complex(
        _finite(pair[0], f"{context}[0]"),
        _finite(pair[1], f"{context}[1]"),
    )


def _hash_is_valid(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _source_sha_is_valid(value: str) -> bool:
    return len(value) == 40 and all(char in "0123456789abcdef" for char in value)


def _resolve_path(value: Any, anchor: Path, context: str) -> Path:
    _require(isinstance(value, str) and value, f"{context} must be a path")
    candidate = Path(value)
    candidates = (
        (candidate,)
        if candidate.is_absolute()
        else (ROOT / candidate, anchor.parent / candidate)
    )
    for item in candidates:
        if item.is_file():
            return item.resolve()
    raise Task035cEvidenceError(f"{context} does not exist: {value}")


def _load_json(
    path: Path | str,
    expected_sha256: str,
    context: str,
) -> tuple[Path, Mapping[str, Any], str]:
    path = Path(path).resolve()
    _require(path.is_file(), f"{context} does not exist: {path}")
    _require(
        isinstance(expected_sha256, str) and _hash_is_valid(expected_sha256),
        f"{context} expected SHA-256 is invalid",
    )
    observed = _sha256(path)
    _require(
        observed == expected_sha256,
        f"{context} SHA-256 mismatch: expected {expected_sha256}, got {observed}",
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise Task035cEvidenceError(f"{context} is not valid JSON: {error}") from error
    return path, _mapping(payload, context), observed


def _record_source(
    record: Mapping[str, Any],
    context: str,
    expected_source_sha: str | None,
) -> str:
    source = _mapping(record.get("source"), f"{context}.source")
    sha_fields = (
        "commit_sha",
        "verified_clean_sha",
        "head_before_sha",
        "head_after_sha",
    )
    observed = {
        str(source[name])
        for name in sha_fields
        if isinstance(source.get(name), str)
    }
    _require(len(observed) == 1, f"{context} source SHA fields disagree")
    sha = next(iter(observed))
    _require(_source_sha_is_valid(sha), f"{context} source SHA is invalid")
    if expected_source_sha is not None:
        _require(
            sha == expected_source_sha,
            f"{context} source SHA {sha} != expected {expected_source_sha}",
        )
    for name in (
        "source_clean_verified",
        "source_stable_during_run",
        "stable_and_clean_after",
    ):
        if name in source:
            _require(source[name] is True, f"{context}.source.{name} is not true")
    if "tracked_source_dirty" in source:
        _require(
            source["tracked_source_dirty"] is False,
            f"{context}.source.tracked_source_dirty is not false",
        )
    return sha


def _order_key(row: Mapping[str, Any], context: str) -> tuple[str, int, int, str]:
    side = row.get("side")
    polarization = row.get("polarization")
    _require(side in {"top", "bottom"}, f"{context}.side is invalid")
    _require(
        polarization in {"s", "p"},
        f"{context}.polarization is invalid",
    )
    return (
        str(side),
        _integer(row.get("m"), f"{context}.m"),
        _integer(row.get("n"), f"{context}.n"),
        str(polarization),
    )


def _order_map(
    rows_value: Any,
    context: str,
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    rows = _sequence(rows_value, context)
    _require(
        len(rows) == EXPECTED_ORDER_COUNT,
        f"{context} must contain exactly {EXPECTED_ORDER_COUNT} rows",
    )
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for index, value in enumerate(rows):
        row = _mapping(value, f"{context}[{index}]")
        key = _order_key(row, f"{context}[{index}]")
        _require(key not in result, f"{context} contains duplicate channel {key}")
        _finite(row.get("power_ratio"), f"{context}[{index}].power_ratio")
        _complex_pair(
            row.get("outgoing_amplitude"),
            f"{context}[{index}].outgoing_amplitude",
        )
        result[key] = row
    return result


def _same_number(first: Any, second: Any, context: str) -> None:
    left = _finite(first, f"{context}.left")
    right = _finite(second, f"{context}.right")
    _require(
        math.isclose(left, right, rel_tol=0.0, abs_tol=1.0e-12),
        f"{context} mismatch: {left} != {right}",
    )


def _source_metadata_sha(raw: Mapping[str, Any], context: str) -> str:
    metadata = _mapping(raw.get("metadata"), f"{context}.metadata")
    values = {
        str(metadata[name])
        for name in (
            "commit_sha",
            "verified_clean_sha",
            "source_commit_at_end_full_sha",
        )
        if isinstance(metadata.get(name), str)
    }
    _require(len(values) == 1, f"{context} raw metadata SHA fields disagree")
    sha = next(iter(values))
    _require(_source_sha_is_valid(sha), f"{context} raw metadata SHA is invalid")
    for name in ("source_clean_and_stable",):
        _require(metadata.get(name) is True, f"{context}.metadata.{name} is not true")
    if "tracked_source_dirty" in metadata:
        _require(
            metadata["tracked_source_dirty"] is False,
            f"{context}.metadata.tracked_source_dirty is not false",
        )
    return sha


def _load_full3d(
    path: Path | str,
    expected_sha256: str,
    expected_source_sha: str,
) -> dict[str, Any]:
    path, record, observed_sha = _load_json(
        path,
        expected_sha256,
        "Full3D watchdog",
    )
    _require(
        record.get("schema_version") == "task033.full3d-watchdog.v1",
        "Full3D watchdog schema is not task033.full3d-watchdog.v1",
    )
    source_sha = _record_source(record, "Full3D watchdog", expected_source_sha)
    raw_evidence = _mapping(
        record.get("raw_evidence"),
        "Full3D watchdog.raw_evidence",
    )
    raw_summary_path = _resolve_path(
        raw_evidence.get("solver_summary"),
        path,
        "Full3D raw summary",
    )
    raw_expected_sha = record.get("solver_summary_sha256")
    _require(
        isinstance(raw_expected_sha, str),
        "Full3D solver_summary_sha256 is missing",
    )
    _, raw_summary, raw_summary_sha = _load_json(
        raw_summary_path,
        raw_expected_sha,
        "Full3D raw summary",
    )
    embedded_summary = _mapping(
        record.get("solver_summary"),
        "Full3D embedded solver summary",
    )
    _require(
        raw_summary == embedded_summary,
        "Full3D embedded solver summary differs from raw summary",
    )
    config = _mapping(raw_summary.get("config"), "Full3D raw summary.config")

    _require(
        raw_summary.get("stage_case") == "stage4_block_grating",
        "Full3D stage_case is not stage4_block_grating",
    )
    _require(
        raw_summary.get("geometry_kind") == "rectangular_block_grating",
        "Full3D geometry is not the fixed rectangular block grating",
    )
    _require(
        config.get("stage4_boundary_model") == "dtn_port",
        "Full3D boundary model is not dtn_port",
    )
    _require(
        config.get("stage4_dtn_order_policy") == "auto_propagating",
        "Full3D DtN order policy is not auto_propagating",
    )
    _require(
        config.get("scattering_background") == "layered",
        "Full3D scattering background is not layered",
    )
    _require(config.get("use_floquet_xy") is True, "Full3D Floquet XY is not enabled")
    _require(
        config.get("polarization_kind") == "s",
        "Full3D polarization is not s",
    )

    degree = _integer(record.get("degree"), "Full3D degree")
    h_nm = _finite(record.get("h_nm"), "Full3D h_nm")
    mpi_size = _integer(record.get("mpi_size"), "Full3D mpi_size")
    _require(mpi_size == 8, "Full3D evidence is not MPI8")
    _require(
        degree == _integer(config.get("nedelec_degree"), "Full3D config degree"),
        "Full3D top-level and raw degree disagree",
    )
    _same_number(h_nm, config.get("mesh_target_size"), "Full3D h identity")
    _require(
        mpi_size
        == _integer(raw_summary.get("mpi_size"), "Full3D raw summary mpi_size"),
        "Full3D top-level and raw MPI size disagree",
    )

    # The hash-bound raw summary is the authoritative run-directory anchor.
    run_directory = raw_summary_path.parent
    order_name = raw_summary.get("dtn_port_orders_json")
    _require(
        isinstance(order_name, str) and order_name,
        "Full3D raw summary does not name the DtN order JSON",
    )
    order_path = (run_directory / order_name).resolve()
    _require(order_path.is_file(), f"Full3D raw order file does not exist: {order_path}")
    order_payload = _mapping(
        json.loads(order_path.read_text(encoding="utf-8")),
        "Full3D raw order payload",
    )
    orders = _order_map(order_payload.get("orders"), "Full3D raw orders")

    requested_backend = record.get("stage4_full3d_assembly_backend_requested")
    actual_backend = record.get("stage4_full3d_assembly_backend_actual")
    _require(
        requested_backend == config.get("stage4_full3d_assembly_backend"),
        "Full3D requested backend differs between watchdog and raw summary",
    )
    _require(
        actual_backend == raw_summary.get("stage4_full3d_assembly_backend_actual"),
        "Full3D actual backend differs between watchdog and raw summary",
    )

    return {
        "path": path,
        "record": record,
        "record_sha256": observed_sha,
        "source_sha": source_sha,
        "raw_summary_path": raw_summary_path,
        "raw_summary_sha256": raw_summary_sha,
        "order_path": order_path,
        "order_sha256": _sha256(order_path),
        "orders": orders,
        "degree": degree,
        "h_nm": h_nm,
        "mpi_size": mpi_size,
        "config": config,
        "requested_backend": requested_backend,
        "actual_backend": actual_backend,
    }


def _hybrid_resource_metrics(
    record: Mapping[str, Any],
    raw: Mapping[str, Any],
    context: str,
) -> dict[str, Any]:
    authority = _mapping(record.get("resource_authority"), f"{context}.resource_authority")
    worker_bytes = _integer(
        authority.get("simultaneous_live_worker_rss_sum_bytes"),
        f"{context} simultaneous worker RSS",
    )
    cgroup_bytes = _integer(
        authority.get("container_cgroup_current_bytes"),
        f"{context} cgroup current",
    )
    recomputed_peak = max(worker_bytes, cgroup_bytes)
    recorded_peak = _integer(
        authority.get("memory_authority_bytes"),
        f"{context} memory authority",
    )
    _require(
        recorded_peak == recomputed_peak,
        f"{context} memory authority is not the recomputed max",
    )
    recorded_gib = _finite(
        authority.get("memory_authority_gib"),
        f"{context} memory authority GiB",
    )
    _require(
        math.isclose(
            recorded_gib,
            recomputed_peak / 1024**3,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        f"{context} memory authority GiB is inconsistent",
    )

    raw_timings = _mapping(
        raw.get("timing_seconds_max_rank"),
        f"{context}.raw.timing_seconds_max_rank",
    )
    measurements = _mapping(record.get("measurements"), f"{context}.measurements")
    copied_timings = _mapping(
        measurements.get("timing_seconds_max_rank"),
        f"{context}.measurements.timing_seconds_max_rank",
    )
    _require(
        raw_timings == copied_timings,
        f"{context} copied timings differ from raw solver timings",
    )
    total_seconds = _finite(raw_timings.get("total"), f"{context} total time")
    modal_seconds = _finite(
        raw_timings.get("internal_modal_coupling"),
        f"{context} modal coupling time",
    )
    system = _mapping(raw.get("hybrid_system"), f"{context}.raw.hybrid_system")
    bottom_stats = _mapping(
        system.get("bottom_matrix_stats"),
        f"{context}.raw.hybrid_system.bottom_matrix_stats",
    )
    top_stats = _mapping(
        system.get("top_matrix_stats"),
        f"{context}.raw.hybrid_system.top_matrix_stats",
    )
    bottom_rows = _integer(
        system.get("bottom_global_size"),
        f"{context} bottom global size",
    )
    top_rows = _integer(
        system.get("top_global_size"),
        f"{context} top global size",
    )
    internal_rows = _integer(
        system.get("internal_unknown_count"),
        f"{context} internal unknown count",
    )
    bottom_nnz = _integer(
        bottom_stats.get("matrix_nnz_used"),
        f"{context} bottom NNZ",
    )
    top_nnz = _integer(
        top_stats.get("matrix_nnz_used"),
        f"{context} top NNZ",
    )
    return {
        "peak_memory_bytes": recomputed_peak,
        "peak_memory_gib": recomputed_peak / 1024**3,
        "worker_rss_bytes": worker_bytes,
        "cgroup_current_bytes": cgroup_bytes,
        "job_cgroup_dedicated": authority.get("job_cgroup_dedicated") is True,
        "total_seconds_max_rank": total_seconds,
        "modal_coupling_seconds_max_rank": modal_seconds,
        "active_rows": bottom_rows + top_rows + internal_rows,
        "assembled_local_fem_nnz": bottom_nnz + top_nnz,
    }


def _load_hybrid(
    path: Path | str,
    expected_sha256: str,
    expected_source_sha: str | None,
    expected_modes: int | None,
    context: str = "Hybrid watchdog",
) -> dict[str, Any]:
    path, record, observed_sha = _load_json(path, expected_sha256, context)
    _require(
        record.get("schema_version") == "task033.memory-watchdog.v2",
        f"{context} schema is not task033.memory-watchdog.v2",
    )
    source_sha = _record_source(record, context, expected_source_sha)
    raw_path = _resolve_path(
        record.get("solver_record_ignored_path"),
        path,
        f"{context} raw solver record",
    )
    raw_expected_sha = record.get("solver_record_sha256")
    _require(isinstance(raw_expected_sha, str), f"{context} raw SHA is missing")
    _, raw, raw_sha = _load_json(
        raw_path,
        raw_expected_sha,
        f"{context} raw solver record",
    )
    raw_source_sha = _source_metadata_sha(raw, context)
    _require(raw_source_sha == source_sha, f"{context} raw and watchdog source differ")

    measurements = _mapping(record.get("measurements"), f"{context}.measurements")
    raw_case = _mapping(raw.get("case"), f"{context}.raw.case")
    copied_case = _mapping(measurements.get("case"), f"{context}.measurements.case")
    _require(raw_case == copied_case, f"{context} copied case differs from raw case")
    raw_validation = _mapping(
        raw.get("validation"),
        f"{context}.raw.validation",
    )
    copied_validation = _mapping(
        measurements.get("validation"),
        f"{context}.measurements.validation",
    )
    raw_order_values = raw_validation.get("external_diffraction_orders")
    _require(
        raw_order_values == copied_validation.get("external_diffraction_orders"),
        f"{context} copied diffraction orders differ from raw solver orders",
    )
    orders = _order_map(raw_order_values, f"{context} raw external orders")

    mpi_size = _integer(
        _mapping(raw.get("metadata"), f"{context}.raw.metadata").get("mpi_size"),
        f"{context} MPI size",
    )
    _require(mpi_size == 8, f"{context} evidence is not MPI8")
    modes = _integer(
        raw_case.get("requested_modes_per_direction"),
        f"{context} requested modes",
    )
    _require(
        modes in VALID_MODE_COUNTS,
        f"{context} requested modes must be M120 or M160",
    )
    if expected_modes is not None:
        _require(modes == expected_modes, f"{context} is not M{expected_modes}")

    degree = _integer(raw_case.get("degree"), f"{context} degree")
    h_nm = _finite(raw_case.get("h_nm"), f"{context} h_nm")
    modal_degree = _integer(raw_case.get("modal_degree"), f"{context} modal degree")
    modal_h_nm = _finite(raw_case.get("modal_h_nm"), f"{context} modal h_nm")
    _require(raw_case.get("material_kind") == "stage4_xy", f"{context} material is wrong")
    _require(
        raw_case.get("polarization_kind") == "s",
        f"{context} polarization is not s",
    )

    system = _mapping(raw.get("hybrid_system"), f"{context}.raw.hybrid_system")
    requested_backend = system.get("assembly_backend_requested")
    bottom_backend = system.get("bottom_assembly_backend_actual")
    top_backend = system.get("top_assembly_backend_actual")
    metadata = _mapping(raw.get("metadata"), f"{context}.raw.metadata")
    _require(
        requested_backend == metadata.get("stage4_full3d_assembly_backend_requested"),
        f"{context} backend request differs between metadata and system",
    )
    _require(
        bottom_backend == top_backend,
        f"{context} bottom and top actual backends differ",
    )

    resource = _hybrid_resource_metrics(record, raw, context)
    return {
        "path": path,
        "record": record,
        "record_sha256": observed_sha,
        "source_sha": source_sha,
        "raw_path": raw_path,
        "raw_sha256": raw_sha,
        "raw": raw,
        "orders": orders,
        "degree": degree,
        "h_nm": h_nm,
        "modal_degree": modal_degree,
        "modal_h_nm": modal_h_nm,
        "mpi_size": mpi_size,
        "modes": modes,
        "case": raw_case,
        "requested_backend": requested_backend,
        "actual_backend": bottom_backend,
        "resource": resource,
    }


def _check_full_hybrid_identity(
    full: Mapping[str, Any],
    hybrid: Mapping[str, Any],
) -> dict[str, Any]:
    _require(full["source_sha"] == hybrid["source_sha"], "Full3D and Hybrid source differ")
    _require(full["degree"] == hybrid["degree"], "Full3D and Hybrid p differ")
    _same_number(full["h_nm"], hybrid["h_nm"], "Full3D and Hybrid h")
    _require(
        hybrid["degree"] == hybrid["modal_degree"],
        "Hybrid local and modal p differ",
    )
    _same_number(hybrid["h_nm"], hybrid["modal_h_nm"], "Hybrid local and modal h")
    full_config = _mapping(full["config"], "Full3D config")
    hybrid_case = _mapping(hybrid["case"], "Hybrid case")
    _same_number(
        full_config.get("lambda0"),
        hybrid_case.get("wavelength_nm"),
        "Full3D and Hybrid wavelength",
    )
    theta = _finite(
        full_config.get("incident_theta_deg"),
        "Full3D incident theta",
    )
    grazing = _finite(
        hybrid_case.get("incident_grazing_deg"),
        "Hybrid incident grazing",
    )
    _require(
        math.isclose(theta + grazing, 90.0, rel_tol=0.0, abs_tol=1.0e-12),
        "Full3D and Hybrid incidence angles differ",
    )
    _require(
        full_config.get("polarization_kind") == hybrid_case.get("polarization_kind"),
        "Full3D and Hybrid polarization differ",
    )

    raw = _mapping(hybrid["raw"], "Hybrid raw")
    comparison = _mapping(
        raw.get("full3d_reference_comparison"),
        "Hybrid raw full3d_reference_comparison",
    )
    reference_path = _resolve_path(
        comparison.get("reference_file"),
        Path(hybrid["path"]),
        "Hybrid raw Full3D reference",
    )
    _require(reference_path == full["path"], "Hybrid raw Full3D reference path differs")
    _require(
        comparison.get("reference_commit_sha") == full["source_sha"],
        "Hybrid raw Full3D reference source SHA differs",
    )
    launch_gate = _mapping(
        _mapping(hybrid["record"], "Hybrid record").get("launch_gate"),
        "Hybrid launch_gate",
    )
    _require(
        launch_gate.get("full3d_reference_expected_sha256")
        == full["record_sha256"],
        "Hybrid launch gate expected Full3D hash differs",
    )
    _require(
        launch_gate.get("full3d_reference_observed_sha256")
        == full["record_sha256"],
        "Hybrid launch gate observed Full3D hash differs",
    )
    _require(
        set(full["orders"]) == set(hybrid["orders"]),
        "Full3D and Hybrid 80-order coverage differs",
    )
    return {
        "pass": True,
        "source_sha": full["source_sha"],
        "degree": full["degree"],
        "h_nm": full["h_nm"],
        "mpi_size": full["mpi_size"],
        "modes": hybrid["modes"],
        "geometry": "Task034 fixed rectangular block grating",
        "boundary_model": "dtn_port",
        "floquet_xy": True,
        "polarization": "s",
        "full3d_reference_hash_bound": True,
        "order_coverage": EXPECTED_ORDER_COUNT,
    }


def _channel_label(key: tuple[str, int, int, str]) -> str:
    side, m, n, polarization = key
    prefix = "R" if side == "top" else "T"
    return f"{prefix}({m},{n})_{polarization}"


def _compare_full_hybrid(
    full_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    hybrid_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
) -> dict[str, Any]:
    significant = [
        key
        for key in sorted(full_orders)
        if max(
            _finite(full_orders[key].get("power_ratio"), "Full3D power"),
            _finite(hybrid_orders[key].get("power_ratio"), "Hybrid power"),
        )
        >= SIGNIFICANT_POWER_FLOOR
    ]
    rows: list[dict[str, Any]] = []
    power_pass_count = 0
    amplitude_pass_count = 0
    for key in significant:
        full_power = _finite(full_orders[key].get("power_ratio"), "Full3D power")
        hybrid_power = _finite(hybrid_orders[key].get("power_ratio"), "Hybrid power")
        power_relative = abs(hybrid_power - full_power) / max(
            abs(full_power),
            abs(hybrid_power),
            SIGNIFICANT_POWER_FLOOR,
        )
        full_amplitude = _complex_pair(
            full_orders[key].get("outgoing_amplitude"),
            "Full3D amplitude",
        )
        hybrid_amplitude = _complex_pair(
            hybrid_orders[key].get("outgoing_amplitude"),
            "Hybrid amplitude",
        )
        amplitude_relative = abs(hybrid_amplitude - full_amplitude) / max(
            abs(full_amplitude),
            abs(hybrid_amplitude),
            AMPLITUDE_DENOMINATOR_FLOOR,
        )
        power_pass = power_relative <= P2_RELATIVE_TOLERANCE
        amplitude_pass = amplitude_relative <= P2_RELATIVE_TOLERANCE
        power_pass_count += int(power_pass)
        amplitude_pass_count += int(amplitude_pass)
        rows.append(
            {
                "channel": _channel_label(key),
                "key": list(key),
                "full3d_power": full_power,
                "hybrid_power": hybrid_power,
                "power_relative_error": power_relative,
                "power_pass": power_pass,
                "full3d_complex_amplitude": [
                    full_amplitude.real,
                    full_amplitude.imag,
                ],
                "hybrid_complex_amplitude": [
                    hybrid_amplitude.real,
                    hybrid_amplitude.imag,
                ],
                "complex_amplitude_relative_error": amplitude_relative,
                "complex_amplitude_pass": amplitude_pass,
            }
        )
    count_pass = len(significant) == EXPECTED_SIGNIFICANT_CHANNEL_COUNT
    return {
        "selection": "max(full3d_power, hybrid_power) >= 1e-8",
        "significant_power_floor": SIGNIFICANT_POWER_FLOOR,
        "relative_tolerance": P2_RELATIVE_TOLERANCE,
        "significant_channel_count": len(significant),
        "significant_channel_count_pass": count_pass,
        "power_pass_count": power_pass_count,
        "complex_amplitude_pass_count": amplitude_pass_count,
        "pass": (
            count_pass
            and power_pass_count == EXPECTED_SIGNIFICANT_CHANNEL_COUNT
            and amplitude_pass_count == EXPECTED_SIGNIFICANT_CHANNEL_COUNT
        ),
        "channels": rows,
    }


def _values_match(reference: Any, observed: Any) -> bool:
    if isinstance(reference, bool) or reference is None:
        return observed is reference
    if isinstance(reference, (int, float)):
        return isinstance(observed, (int, float)) and math.isclose(
            float(reference),
            float(observed),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    if isinstance(reference, str):
        return observed == reference
    if isinstance(reference, Sequence) and not isinstance(reference, (str, bytes)):
        return (
            isinstance(observed, Sequence)
            and not isinstance(observed, (str, bytes))
            and len(reference) == len(observed)
            and all(_values_match(left, right) for left, right in zip(reference, observed))
        )
    if isinstance(reference, Mapping):
        return isinstance(observed, Mapping) and all(
            key in observed and _values_match(value, observed[key])
            for key, value in reference.items()
        )
    return reference == observed


def _load_significant_reference(
    path: Path | str,
    expected_sha256: str,
) -> dict[str, Any]:
    path, record, observed_sha = _load_json(
        path,
        expected_sha256,
        "significant channel reference v1",
    )
    _require(
        record.get("schema_version") == "task035b.significant-channel-reference.v1",
        "significant channel reference schema is not v1",
    )
    _require(
        record.get("status") == "significant_channel_reference_v1_frozen",
        "significant channel reference v1 is not frozen",
    )
    _require(record.get("pass") is True, "significant channel reference pass is not true")
    _require(
        record.get("mechanical_validation_pass") is True,
        "significant channel reference mechanical validation is not true",
    )
    manifest = _mapping(
        record.get("authority_manifest"),
        "significant channel reference authority_manifest",
    )
    _require(
        manifest.get("mechanically_validated") is True,
        "significant channel authority manifest is not mechanically validated",
    )
    selection = _mapping(
        record.get("significant_channel_selection"),
        "significant channel reference selection",
    )
    _require(selection.get("channel_count") == 12, "reference channel count is not 12")
    _require(
        selection.get("significant_power_floor") == SIGNIFICANT_POWER_FLOOR,
        "reference significant power floor differs",
    )
    channels = _sequence(record.get("channels"), "significant reference channels")
    _require(len(channels) == 12, "significant reference must contain 12 channels")
    channel_map: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for index, value in enumerate(channels):
        row = _mapping(value, f"significant reference channels[{index}]")
        channel = _mapping(
            row.get("channel"),
            f"significant reference channels[{index}].channel",
        )
        key = _order_key(channel, f"significant reference channels[{index}].channel")
        _require(key not in channel_map, f"duplicate significant reference channel {key}")
        _require(
            channel.get("label") == _channel_label(key),
            f"significant reference channel label differs for {key}",
        )
        gate = _mapping(
            row.get("unchanged_v0_acceptance_gate"),
            f"significant reference channels[{index}].unchanged_v0_acceptance_gate",
        )
        _require(
            gate.get("unchanged_v0_formula_verified") is True,
            f"significant reference channel {key} v0 formula is not verified",
        )
        _require(
            gate.get("uses_numerical_convergence_band") is False,
            f"significant reference channel {key} uses the numerical band",
        )
        _require(
            gate.get("uses_h15_or_fixed_diagnostics") is False,
            f"significant reference channel {key} uses diagnostic samples",
        )
        _finite(gate.get("power_absolute_tolerance"), f"{key} power tolerance")
        _finite(
            gate.get("complex_amplitude_absolute_tolerance"),
            f"{key} amplitude tolerance",
        )
        center = _mapping(row.get("reference_center"), f"{key} reference center")
        _finite(center.get("power"), f"{key} reference power")
        _complex_pair(center.get("complex_amplitude"), f"{key} reference amplitude")
        _mapping(row.get("analytic_identity"), f"{key} analytic identity")
        channel_map[key] = row
    return {
        "path": path,
        "record_sha256": observed_sha,
        "record": record,
        "channels": channel_map,
    }


def _compare_to_significant_reference(
    full_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    hybrid_orders: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    reference_orders = _mapping(reference["channels"], "reference channel map")
    _require(
        set(reference_orders).issubset(full_orders),
        "Full3D evidence does not cover every v1 channel",
    )
    _require(
        set(reference_orders).issubset(hybrid_orders),
        "Hybrid evidence does not cover every v1 channel",
    )
    rows: list[dict[str, Any]] = []
    full_power_count = 0
    full_amplitude_count = 0
    hybrid_power_count = 0
    hybrid_amplitude_count = 0
    analytic_identity_count = 0
    for key in sorted(reference_orders):
        reference_row = _mapping(reference_orders[key], f"reference {key}")
        analytic = _mapping(reference_row.get("analytic_identity"), f"reference {key} analytic")
        analytic_pass = _values_match(analytic, full_orders[key])
        analytic_identity_count += int(analytic_pass)
        center = _mapping(reference_row.get("reference_center"), f"reference {key} center")
        gate = _mapping(
            reference_row.get("unchanged_v0_acceptance_gate"),
            f"reference {key} gate",
        )
        reference_power = _finite(center.get("power"), f"reference {key} power")
        reference_amplitude = _complex_pair(
            center.get("complex_amplitude"),
            f"reference {key} amplitude",
        )
        power_tolerance = _finite(
            gate.get("power_absolute_tolerance"),
            f"reference {key} power tolerance",
        )
        amplitude_tolerance = _finite(
            gate.get("complex_amplitude_absolute_tolerance"),
            f"reference {key} amplitude tolerance",
        )
        full_power = _finite(full_orders[key].get("power_ratio"), f"Full3D {key} power")
        hybrid_power = _finite(
            hybrid_orders[key].get("power_ratio"),
            f"Hybrid {key} power",
        )
        full_amplitude = _complex_pair(
            full_orders[key].get("outgoing_amplitude"),
            f"Full3D {key} amplitude",
        )
        hybrid_amplitude = _complex_pair(
            hybrid_orders[key].get("outgoing_amplitude"),
            f"Hybrid {key} amplitude",
        )
        full_power_error = abs(full_power - reference_power)
        hybrid_power_error = abs(hybrid_power - reference_power)
        full_amplitude_error = abs(full_amplitude - reference_amplitude)
        hybrid_amplitude_error = abs(hybrid_amplitude - reference_amplitude)
        full_power_pass = full_power_error <= power_tolerance
        hybrid_power_pass = hybrid_power_error <= power_tolerance
        full_amplitude_pass = full_amplitude_error <= amplitude_tolerance
        hybrid_amplitude_pass = hybrid_amplitude_error <= amplitude_tolerance
        full_power_count += int(full_power_pass)
        hybrid_power_count += int(hybrid_power_pass)
        full_amplitude_count += int(full_amplitude_pass)
        hybrid_amplitude_count += int(hybrid_amplitude_pass)
        rows.append(
            {
                "channel": _channel_label(key),
                "analytic_identity_pass": analytic_pass,
                "reference_power": reference_power,
                "power_absolute_tolerance": power_tolerance,
                "full3d_power_absolute_error": full_power_error,
                "full3d_power_pass": full_power_pass,
                "hybrid_power_absolute_error": hybrid_power_error,
                "hybrid_power_pass": hybrid_power_pass,
                "reference_complex_amplitude": [
                    reference_amplitude.real,
                    reference_amplitude.imag,
                ],
                "complex_amplitude_absolute_tolerance": amplitude_tolerance,
                "full3d_complex_amplitude_absolute_error": full_amplitude_error,
                "full3d_complex_amplitude_pass": full_amplitude_pass,
                "hybrid_complex_amplitude_absolute_error": hybrid_amplitude_error,
                "hybrid_complex_amplitude_pass": hybrid_amplitude_pass,
            }
        )
    return {
        "semantics": (
            "independent absolute comparison to frozen v1 center and unchanged-v0 "
            "per-channel tolerances; relative 1e-3 does not replace this gate"
        ),
        "channel_count": len(rows),
        "analytic_identity_pass_count": analytic_identity_count,
        "full3d_power_pass_count": full_power_count,
        "full3d_complex_amplitude_pass_count": full_amplitude_count,
        "hybrid_power_pass_count": hybrid_power_count,
        "hybrid_complex_amplitude_pass_count": hybrid_amplitude_count,
        "pass": all(
            count == EXPECTED_SIGNIFICANT_CHANNEL_COUNT
            for count in (
                len(rows),
                analytic_identity_count,
                full_power_count,
                full_amplitude_count,
                hybrid_power_count,
                hybrid_amplitude_count,
            )
        ),
        "channels": rows,
    }


def _same_m_resource_pair(
    primary: Mapping[str, Any],
    paired: Mapping[str, Any],
) -> dict[str, Any]:
    by_backend = {
        str(primary["actual_backend"]): primary,
        str(paired["actual_backend"]): paired,
    }
    required_backends = {"standard_full", "assembly_time_static_condensed"}
    identity_checks = {
        "same_source_sha": primary["source_sha"] == paired["source_sha"],
        "same_degree": primary["degree"] == paired["degree"],
        "same_h_nm": math.isclose(
            float(primary["h_nm"]),
            float(paired["h_nm"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "same_modal_degree": primary["modal_degree"] == paired["modal_degree"],
        "same_modal_h_nm": math.isclose(
            float(primary["modal_h_nm"]),
            float(paired["modal_h_nm"]),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ),
        "same_mpi_size": primary["mpi_size"] == paired["mpi_size"],
        "same_modes": primary["modes"] == paired["modes"],
        "same_case": primary["case"] == paired["case"],
        "standard_and_static_backends": set(by_backend) == required_backends,
    }
    authoritative = all(identity_checks.values())
    output: dict[str, Any] = {
        "evaluated": True,
        "authoritative_same_source_same_case_pair": authoritative,
        "identity_checks": identity_checks,
        "reason": (
            "same-source same-case standard/static pair"
            if authoritative
            else "diagnostic only because one or more pair identity checks failed"
        ),
    }
    if set(by_backend) == required_backends:
        standard = by_backend["standard_full"]["resource"]
        static = by_backend["assembly_time_static_condensed"]["resource"]
        standard_peak = _finite(standard["peak_memory_bytes"], "standard peak")
        static_peak = _finite(static["peak_memory_bytes"], "static peak")
        standard_total = _finite(standard["total_seconds_max_rank"], "standard total")
        static_total = _finite(static["total_seconds_max_rank"], "static total")
        standard_modal = _finite(
            standard["modal_coupling_seconds_max_rank"],
            "standard modal coupling",
        )
        static_modal = _finite(
            static["modal_coupling_seconds_max_rank"],
            "static modal coupling",
        )
        _require(standard_peak > 0.0, "standard peak memory must be positive")
        _require(standard_total > 0.0, "standard total time must be positive")
        _require(standard_modal > 0.0, "standard modal time must be positive")
        output["recomputed_deltas"] = {
            "memory_saving_fraction": (standard_peak - static_peak) / standard_peak,
            "memory_saving_percent": 100.0
            * (standard_peak - static_peak)
            / standard_peak,
            "static_to_standard_total_time_ratio": static_total / standard_total,
            "static_to_standard_modal_coupling_time_ratio": (
                static_modal / standard_modal
            ),
            "active_row_saving_fraction": (
                _finite(standard["active_rows"], "standard rows")
                - _finite(static["active_rows"], "static rows")
            )
            / _finite(standard["active_rows"], "standard rows"),
            "local_fem_nnz_saving_fraction": (
                _finite(standard["assembled_local_fem_nnz"], "standard NNZ")
                - _finite(static["assembled_local_fem_nnz"], "static NNZ")
            )
            / _finite(standard["assembled_local_fem_nnz"], "standard NNZ"),
        }
    return output


def build_task035c_channel_resource_check(
    *,
    full3d_record: Path | str,
    full3d_sha256: str,
    hybrid_record: Path | str,
    hybrid_sha256: str,
    expected_source_sha: str,
    expected_modes: int,
    gate_kind: str,
    significant_channel_reference: Path | str | None = None,
    significant_channel_reference_sha256: str | None = None,
    paired_hybrid_record: Path | str | None = None,
    paired_hybrid_sha256: str | None = None,
) -> dict[str, Any]:
    _require(
        _source_sha_is_valid(expected_source_sha),
        "expected source SHA is invalid",
    )
    _require(expected_modes in VALID_MODE_COUNTS, "expected modes must be 120 or 160")
    _require(
        gate_kind in {"p2-diagnosis", "p6-formal"},
        "gate kind must be p2-diagnosis or p6-formal",
    )
    full = _load_full3d(full3d_record, full3d_sha256, expected_source_sha)
    hybrid = _load_hybrid(
        hybrid_record,
        hybrid_sha256,
        expected_source_sha,
        expected_modes,
    )
    identity = _check_full_hybrid_identity(full, hybrid)
    relative = _compare_full_hybrid(full["orders"], hybrid["orders"])

    p2_gate = {
        "evaluated": gate_kind == "p2-diagnosis",
        "semantics": "Full3D-to-Hybrid relative 1e-3 diagnosis only",
        "pass": relative["pass"] if gate_kind == "p2-diagnosis" else None,
    }
    p6_reference_result: dict[str, Any] | None = None
    p6_gate_pass: bool | None = None
    reference_authority: dict[str, Any] | None = None
    if gate_kind == "p6-formal":
        _require(
            significant_channel_reference is not None,
            "p6-formal requires significant channel reference v1",
        )
        _require(
            significant_channel_reference_sha256 is not None,
            "p6-formal requires significant channel reference v1 SHA-256",
        )
        reference = _load_significant_reference(
            significant_channel_reference,
            significant_channel_reference_sha256,
        )
        p6_reference_result = _compare_to_significant_reference(
            full["orders"],
            hybrid["orders"],
            reference,
        )
        p6_gate_pass = bool(relative["pass"] and p6_reference_result["pass"])
        reference_authority = {
            "path": str(reference["path"]),
            "sha256": reference["record_sha256"],
        }
    p6_gate = {
        "evaluated": gate_kind == "p6-formal",
        "semantics": (
            "requires Full3D-to-Hybrid relative 12/12 plus independent Full3D "
            "and Hybrid absolute 12/12 against frozen v1 unchanged-v0 tolerances"
        ),
        "pass": p6_gate_pass,
        "reference_authority": reference_authority,
        "absolute_comparison": p6_reference_result,
    }

    pair_result: dict[str, Any] = {"evaluated": False}
    if paired_hybrid_record is not None or paired_hybrid_sha256 is not None:
        _require(
            paired_hybrid_record is not None and paired_hybrid_sha256 is not None,
            "paired Hybrid record and SHA-256 must be provided together",
        )
        paired = _load_hybrid(
            paired_hybrid_record,
            paired_hybrid_sha256,
            None,
            expected_modes,
            context="paired Hybrid watchdog",
        )
        pair_result = _same_m_resource_pair(hybrid, paired)

    selected_gate_pass = (
        bool(p2_gate["pass"]) if gate_kind == "p2-diagnosis" else bool(p6_gate["pass"])
    )
    return {
        "schema_version": "task035c.channel-resource-check.v1",
        "status": "recomputed_pass" if selected_gate_pass else "recomputed_failed",
        "pass": selected_gate_pass,
        "scope": (
            "independent channel/resource evidence checker; not a replacement for "
            "R00/R/T/Aclosure/field/full-explicit-residual qualification"
        ),
        "gate_kind": gate_kind,
        "authorities": {
            "full3d_watchdog": {
                "path": str(full["path"]),
                "sha256": full["record_sha256"],
                "raw_summary_path": str(full["raw_summary_path"]),
                "raw_summary_sha256": full["raw_summary_sha256"],
                "raw_orders_path": str(full["order_path"]),
                "raw_orders_sha256": full["order_sha256"],
            },
            "hybrid_watchdog": {
                "path": str(hybrid["path"]),
                "sha256": hybrid["record_sha256"],
                "raw_solver_path": str(hybrid["raw_path"]),
                "raw_solver_sha256": hybrid["raw_sha256"],
            },
        },
        "identity": identity,
        "full3d_vs_hybrid": relative,
        "p2_diagnosis_gate": p2_gate,
        "p6_formal_gate": p6_gate,
        "resource_recomputed": {
            "hybrid": hybrid["resource"],
            "assembly_backend_requested": hybrid["requested_backend"],
            "assembly_backend_actual": hybrid["actual_backend"],
            "modes": hybrid["modes"],
        },
        "same_m_backend_pair": pair_result,
        "input_status_advisory_only": {
            "full3d_watchdog_status": full["record"].get("status"),
            "hybrid_watchdog_status": hybrid["record"].get("status"),
            "hybrid_watchdog_numeric_pass": hybrid["record"].get("numeric_pass"),
            "hybrid_watchdog_formal_pass": hybrid["record"].get("formal_pass"),
            "hybrid_raw_status": hybrid["raw"].get("status"),
            "semantics": "not used to decide this checker's recomputed pass",
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recompute Task035c channel and Hybrid resource evidence.",
    )
    parser.add_argument("--full3d-record", type=Path, required=True)
    parser.add_argument("--full3d-sha256", required=True)
    parser.add_argument("--hybrid-record", type=Path, required=True)
    parser.add_argument("--hybrid-sha256", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-modes", type=int, choices=VALID_MODE_COUNTS, required=True)
    parser.add_argument(
        "--gate-kind",
        choices=("p2-diagnosis", "p6-formal"),
        required=True,
    )
    parser.add_argument("--significant-channel-reference", type=Path)
    parser.add_argument("--significant-channel-reference-sha256")
    parser.add_argument("--paired-hybrid-record", type=Path)
    parser.add_argument("--paired-hybrid-sha256")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = build_task035c_channel_resource_check(
        full3d_record=args.full3d_record,
        full3d_sha256=args.full3d_sha256,
        hybrid_record=args.hybrid_record,
        hybrid_sha256=args.hybrid_sha256,
        expected_source_sha=args.expected_source_sha,
        expected_modes=args.expected_modes,
        gate_kind=args.gate_kind,
        significant_channel_reference=args.significant_channel_reference,
        significant_channel_reference_sha256=(
            args.significant_channel_reference_sha256
        ),
        paired_hybrid_record=args.paired_hybrid_record,
        paired_hybrid_sha256=args.paired_hybrid_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
