"""Independent raw checker for the V6-2 full-interface Schur route.

The legacy identity-only branch reads JSON only.  Executed exact/packet-ready
evidence additionally reopens each persisted NPY with a bounded mmap read and
recomputes its dtype, shape, finite-value, contiguous-value, and file hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "task040.v6_2.full_interface_schur_checker.v1"
EXPECTED_FORMAL_SCHEMA = "task040.v6_2.full_interface_schur.v1"
EXPECTED_RANK_SCHEMA = "task040.v6_2.rank_artifact.v1"
EXPECTED_MPI_SIZE = 8
EXPECTED_LOWER_COUNT = 7560
EXPECTED_UPPER_COUNT = 7560
EXPECTED_JOINT_COUNT = EXPECTED_LOWER_COUNT + EXPECTED_UPPER_COUNT
PACKET_WRITER_IDENTITY = "task040.v6.current_exact_packet_writer.v1"
EXPECTED_HARD_STOP_BYTES = 45 * 2**30
EXPECTED_WALL_BUDGET_SECONDS = 21600.0
EXPECTED_FORMAL_SEQUENCE_START_SCOPE = (
    "run_v6_2_interface_schur_entry_before_preflight_and_artifact_setup"
)
EXPECTED_FROZEN_RHS_SOURCE_SHA = (
    "fd7bea41d7d7b7869dd3ade4407129b00900ef7d"
)
ZERO_TOLERANCE = 1.0e-13
ROUNDTRIP_TOLERANCE = 1.0e-11
ACTION_TOLERANCE = 1.0e-10
HEX_DIGITS = frozenset("0123456789abcdef")
_PROVENANCE_FIELDS = (
    "input_sha256",
    "physical_model_sha256",
    "selected_manifest_sha256",
    "selected_identity_sha256",
    "resolved_config_sha256",
    "source_sha",
)
_PACKET_ROLES = (
    "exact_output_canonical",
    "exact_output_owner_rows",
    "gamma_l_canonical",
    "gamma_u_canonical",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise TypeError(f"JSON root is not an object: {path}")
    return payload, _sha256(path)


def _is_hex(value: Any, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in HEX_DIGITS for character in value)
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _valid_provenance(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return all(
        _is_hex(value.get(field), 40 if field == "source_sha" else 64)
        for field in _PROVENANCE_FIELDS
    )


def _same_finite_number(observed: Any, expected: Any, *, tolerance: float = 1.0e-12) -> bool:
    if expected is None:
        return observed is None
    if not _finite(observed) or not _finite(expected):
        return False
    return bool(math.isclose(float(observed), float(expected), rel_tol=tolerance, abs_tol=tolerance))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _all_true(mapping: Any) -> bool:
    return isinstance(mapping, Mapping) and bool(mapping) and all(
        value is True for value in mapping.values()
    )


def _resolve_artifact_path(root: Path, value: Any, field: str) -> Path:
    """Resolve an artifact path while keeping it inside the formal root."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} is not a path")
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not _inside(resolved, root):
        raise ValueError(f"{field} escapes the formal root")
    return resolved


def _check_watchdog_audit(
    root: Path,
    manifest: Mapping[str, Any],
    read_files: list[dict[str, str]],
) -> dict[str, Any]:
    """Reopen the outer watchdog summary and bind it to this V6 manifest."""

    watchdog_path = root.parent / "watchdog_summary.json"
    run_summary_path = root / "run_summary.json"
    errors: list[str] = []
    watchdog_summary: Mapping[str, Any] = {}
    summary_sha256: str | None = None
    run_summary_sha256: str | None = None
    if watchdog_path.is_file():
        try:
            watchdog_summary, summary_sha256 = _read_json(watchdog_path)
            read_files.append(
                {
                    "path": os.path.relpath(watchdog_path, root),
                    "sha256": summary_sha256,
                }
            )
        except Exception as exc:
            errors.append(f"watchdog summary: {type(exc).__name__}: {exc}")
    else:
        errors.append("watchdog summary is missing")
    if run_summary_path.is_file():
        run_summary_sha256 = _sha256(run_summary_path)
        read_files.append(
            {
                "path": str(run_summary_path.relative_to(root)),
                "sha256": run_summary_sha256,
            }
        )
    else:
        errors.append("run summary is missing")

    elapsed_seconds = watchdog_summary.get("elapsed_seconds")
    peak_rss_bytes = watchdog_summary.get("peak_rss_bytes")
    authoritative_sample_count = watchdog_summary.get("authoritative_sample_count")
    checks = {
        "schema": watchdog_summary.get("schema") == "task040.level_a.watchdog.v1",
        "method_matches_manifest": watchdog_summary.get("method")
        == manifest.get("method"),
        "source_sha_matches_manifest": watchdog_summary.get("source_sha")
        == manifest.get("source_sha"),
        "termination_reason_natural_exit": watchdog_summary.get(
            "termination_reason"
        )
        == "natural_exit",
        "return_code_zero": watchdog_summary.get("return_code") == 0,
        "hard_stop_bytes": watchdog_summary.get("hard_stop_bytes")
        == EXPECTED_HARD_STOP_BYTES,
        "timeout_seconds": watchdog_summary.get("timeout_seconds")
        == EXPECTED_WALL_BUDGET_SECONDS,
        "elapsed_before_timeout": (
            _finite(elapsed_seconds)
            and float(elapsed_seconds) < EXPECTED_WALL_BUDGET_SECONDS
        ),
        "peak_rss_below_hard_stop": (
            _finite(peak_rss_bytes)
            and float(peak_rss_bytes) < EXPECTED_HARD_STOP_BYTES
        ),
        "peak_swap_zero": watchdog_summary.get("peak_swap_bytes") == 0,
        "peak_dedicated_cgroup_swap_zero": watchdog_summary.get(
            "peak_dedicated_cgroup_swap_bytes"
        )
        == 0,
        "all_status_readable": watchdog_summary.get("all_status_readable") is True,
        "swap_authority_readable": watchdog_summary.get("swap_authority_readable")
        is True,
        "authoritative_sample_count_positive": (
            isinstance(authoritative_sample_count, int)
            and not isinstance(authoritative_sample_count, bool)
            and authoritative_sample_count > 0
        ),
        "run_summary_present": watchdog_summary.get("run_summary_present") is True
        and run_summary_path.is_file(),
        "run_summary_hash_matches": (
            run_summary_sha256 is not None
            and watchdog_summary.get("run_summary_sha256") == run_summary_sha256
        ),
    }
    return {
        "valid": not errors and all(checks.values()),
        "watchdog_summary_path": os.path.relpath(watchdog_path, root),
        "summary_sha256": summary_sha256,
        "run_summary_path": str(run_summary_path.relative_to(root)),
        "run_summary_sha256": run_summary_sha256,
        "observations": {
            field: watchdog_summary.get(field)
            for field in (
                "schema",
                "method",
                "source_sha",
                "termination_reason",
                "return_code",
                "hard_stop_bytes",
                "timeout_seconds",
                "elapsed_seconds",
                "peak_rss_bytes",
                "peak_swap_bytes",
                "peak_dedicated_cgroup_swap_bytes",
                "all_status_readable",
                "swap_authority_readable",
                "authoritative_sample_count",
                "run_summary_present",
                "run_summary_sha256",
            )
        },
        "checks": checks,
        "errors": errors,
    }


def _hash_loaded_complex128(values: np.ndarray) -> str:
    """Hash a one-dimensional complex128 array in bounded chunks."""

    digest = hashlib.sha256()
    flat = np.asarray(values)
    for start in range(0, int(flat.size), 1 << 20):
        chunk = np.ascontiguousarray(flat[start : start + (1 << 20)])
        digest.update(chunk.tobytes())
    return digest.hexdigest()


def _read_packet_array(
    root: Path,
    path_value: Any,
    read_files: list[dict[str, str]],
) -> tuple[dict[str, Any], Path]:
    """Read one persisted packet shard without invoking any numerical solver."""

    path = _resolve_artifact_path(root, path_value, "packet array_path")
    if path.suffix != ".npy" or not path.is_file():
        raise ValueError(f"packet array is missing or not NPY: {path}")
    file_sha = _sha256(path)
    values = np.load(path, mmap_mode="r", allow_pickle=False)
    try:
        if not isinstance(values, np.ndarray) or values.ndim != 1:
            raise ValueError(f"packet array is not one-dimensional: {path}")
        if values.dtype != np.dtype(np.complex128):
            raise ValueError(f"packet array is not complex128: {path}")
        finite = True
        for start in range(0, int(values.size), 1 << 20):
            if not bool(
                np.isfinite(values[start : start + (1 << 20)]).all()
            ):
                finite = False
                break
        if not finite:
            raise ValueError(f"packet array contains non-finite values: {path}")
        value_sha = _hash_loaded_complex128(values)
        result = {
            "dtype": str(values.dtype),
            "shape": [int(values.size)],
            "local_size": int(values.size),
            "finite": True,
            "value_sha256": value_sha,
            "file_sha256": file_sha,
        }
    finally:
        del values
    read_files.append(
        {
            "path": str(path.relative_to(root)),
            "sha256": file_sha,
            "kind": "npy",
        }
    )
    return result, path


def _packet_identity_fields_for_checker(role: str) -> tuple[str, ...]:
    common = (
        "label",
        "role",
        "dtype",
        "rank",
        "mpi_size",
        "value_sha256",
        "source_definition_sha256",
        "bare_f_operator_hash",
        "canonical_layout_sha256",
        "canonical_key_set_sha256",
        "source_provenance",
    )
    if role == "exact_output_canonical":
        return common + (
            "canonical_key_count_local",
            "global_active_size",
            "canonical_key_order_sha256",
            "canonical_key_set_local_sha256",
            "canonical_roundtrip_relative",
        )
    if role == "exact_output_owner_rows":
        return common + ("local_size", "global_size", "ownership_range", "owner_row_order")
    return common + (
        "canonical_key_count_local",
        "canonical_global_size",
        "canonical_key_order_sha256",
        "canonical_key_set_local_sha256",
        "gamma_transform_sha256",
    )


def _check_packet_file_chain(
    root: Path,
    label: str,
    role: str,
    packet: Mapping[str, Any],
    read_files: list[dict[str, str]],
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Reopen one role's NPY/metadata/manifest and verify every stored hash."""

    try:
        if packet.get("label") != label or packet.get("role") != role:
            raise ValueError("packet label/role mismatch")
        if packet.get("writer_identity") != PACKET_WRITER_IDENTITY:
            raise ValueError("packet writer identity is not the production writer")
        if packet.get("dtype") != "complex128":
            raise ValueError("packet dtype is not complex128")
        array_info, array_path = _read_packet_array(
            root, packet.get("array_path"), read_files
        )
        if packet.get("array_sha256") != packet.get("value_sha256"):
            raise ValueError("packet array/value hashes are split")
        if (
            array_info["value_sha256"] != packet.get("array_sha256")
            or array_info["value_sha256"] != packet.get("value_sha256")
        ):
            raise ValueError("packet array value hash differs from identity")
        if array_info["file_sha256"] != packet.get("shard_sha256"):
            raise ValueError("packet NPY file hash differs from metadata")
        metadata_path = _resolve_artifact_path(root, packet.get("path"), "packet path")
        manifest_path = _resolve_artifact_path(
            root, packet.get("manifest_path"), "packet manifest_path"
        )
        if not metadata_path.is_file() or not manifest_path.is_file():
            raise ValueError("packet metadata or manifest is missing")
        metadata, metadata_sha = _read_json(metadata_path)
        manifest, manifest_sha = _read_json(manifest_path)
        read_files.extend(
            [
                {
                    "path": str(metadata_path.relative_to(root)),
                    "sha256": metadata_sha,
                    "kind": "packet_metadata",
                },
                {
                    "path": str(manifest_path.relative_to(root)),
                    "sha256": manifest_sha,
                    "kind": "packet_manifest",
                },
            ]
        )
        if metadata_sha != packet.get("metadata_sha256"):
            raise ValueError("packet metadata file hash differs from record")
        if manifest_sha != packet.get("manifest_sha256"):
            raise ValueError("packet manifest file hash differs from record")
        if manifest.get("metadata_sha256") != metadata_sha:
            raise ValueError("packet manifest metadata hash differs")
        if (
            packet.get("writer_identity") != PACKET_WRITER_IDENTITY
            or metadata.get("writer_identity") != PACKET_WRITER_IDENTITY
            or manifest.get("writer_identity") != PACKET_WRITER_IDENTITY
        ):
            raise ValueError("packet writer identity is not the production writer")
        for field in _packet_identity_fields_for_checker(role):
            if metadata.get(field) != packet.get(field) or manifest.get(field) != packet.get(field):
                raise ValueError(f"packet {role} identity field {field} differs")
        for field in ("array_path", "array_sha256", "shard_sha256", "manifest_path"):
            if metadata.get(field) != packet.get(field) or manifest.get(field) != packet.get(field):
                raise ValueError(f"packet {role} artifact field {field} differs")
        if expected_identity is not None:
            for field in _packet_identity_fields_for_checker(role):
                if packet.get(field) != expected_identity.get(field):
                    raise ValueError(
                        f"packet {role} differs from live expected identity for {field}"
                    )
        expected_length = (
            int(packet.get("local_size", -1))
            if role == "exact_output_owner_rows"
            else int(packet.get("canonical_key_count_local", -1))
        )
        if expected_length != int(array_info["local_size"]):
            raise ValueError("packet array length differs from role identity")
        _ = array_path
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def _expected_packet_identities_from_exact_result(
    exact_result: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Extract the consumer's live identity, never a writer-reported hash."""

    expected: dict[str, Mapping[str, Any]] = {}
    family = exact_result.get("family")
    if not isinstance(family, Mapping):
        return expected
    for record in family.get("source_records", ()):
        if not isinstance(record, Mapping):
            continue
        fgmres = record.get("fgmres")
        if not isinstance(fgmres, Mapping):
            continue
        audit = fgmres.get("accepted_solution_packet_audit")
        if not isinstance(audit, Mapping):
            continue
        identities = audit.get("expected_packet_identities")
        if not isinstance(identities, Mapping):
            continue
        label = str(record.get("label"))
        expected[label] = identities
    return expected


def _validate_exact_adapter_audit(
    label: str,
    adapter: Any,
    exact_result: Mapping[str, Any],
    *,
    expected_bare_f_operator_hash: str | None = None,
    expected_rank: int | None = None,
    expected_mpi_size: int = EXPECTED_MPI_SIZE,
) -> None:
    """Validate the raw, post-release RHS adapter audit for one source.

    The exact-detail residual is only meaningful when the persisted source that
    produced it is still identifiable.  This check deliberately consumes the
    compact audit emitted by :class:`LoadedExactQualificationRHS`; it does not
    infer adapter identity from the residual or from a writer-side packet.
    """

    if not isinstance(adapter, Mapping):
        raise ValueError(f"exact detail {label} adapter audit is missing")
    for field in (
        "retained_during_callbacks",
        "released_by_driver",
        "destroyed_after_source",
    ):
        if adapter.get(field) is not True:
            raise ValueError(f"exact detail {label} adapter {field} is not true")
    for field in ("numeric_allgather", "full_numeric_replica"):
        if adapter.get(field) is not False:
            raise ValueError(f"exact detail {label} adapter {field} must be false")
    if adapter.get("condensed_rhs_built") is not True:
        raise ValueError(f"exact detail {label} adapter condensed RHS is not built")
    if adapter.get("interior_rhs_group_count") != 3:
        raise ValueError(f"exact detail {label} adapter group count is not three")

    load = adapter.get("load")
    if not isinstance(load, Mapping):
        raise ValueError(f"exact detail {label} adapter load audit is missing")
    required_identity = {
        "label": label,
        "role": "rhs",
        "schema": "task040.v5.current_bare_f_authority_vector.v1",
        "side": "bottom",
        "dtype": "complex128",
        "owner_row_values_not_row_ids": True,
        "raw_global_row_remap": False,
    }
    for field, expected in required_identity.items():
        if load.get(field) != expected:
            raise ValueError(
                f"exact detail {label} adapter load {field} is not authority-bound"
            )
    frozen_provenance = exact_result.get("frozen_rhs_source_provenance")
    if not _valid_provenance(frozen_provenance):
        raise ValueError(f"exact detail {label} frozen provenance is invalid")
    if load.get("source_provenance") != frozen_provenance:
        raise ValueError(f"exact detail {label} adapter frozen provenance differs")
    if load.get("source_sha") != frozen_provenance.get("source_sha"):
        raise ValueError(f"exact detail {label} adapter source SHA differs")

    bare_hash = (
        expected_bare_f_operator_hash
        if expected_bare_f_operator_hash is not None
        else exact_result.get("bare_f_operator_hash")
    )
    if not _is_hex(bare_hash):
        raise ValueError(f"exact detail {label} adapter bare-F hash is unavailable")
    if load.get("bare_f_operator_hash") != bare_hash:
        raise ValueError(f"exact detail {label} adapter bare-F hash differs from root")
    for field in (
        "source_definition_sha256",
        "array_sha256",
        "array_sha256_observed",
        "owner_row_array_sha256",
        "owner_row_array_sha256_observed",
        "canonical_layout_sha256",
        "canonical_layout_sha256_observed",
        "canonical_key_set_sha256",
        "global_sha256",
        "rank_local_shard_binding_sha256",
    ):
        if not _is_hex(load.get(field)):
            raise ValueError(f"exact detail {label} adapter {field} is not a digest")
    for declared, observed in (
        ("array_sha256", "array_sha256_observed"),
        ("owner_row_array_sha256", "owner_row_array_sha256_observed"),
        ("canonical_layout_sha256", "canonical_layout_sha256_observed"),
    ):
        if load.get(declared) != load.get(observed):
            raise ValueError(
                f"exact detail {label} adapter {declared} differs from observed"
            )
    required_load_flags = {
        "canonical_values_loaded": True,
        "owner_values_loaded": True,
        "numeric_values_loaded": True,
        "owner_row_array_loaded": True,
        "canonical_values_retained": False,
        "owner_values_retained": False,
    }
    for field, expected in required_load_flags.items():
        if load.get(field) is not expected:
            raise ValueError(
                f"exact detail {label} adapter load {field} is not {expected}"
            )
    try:
        local_size = int(load["local_size"])
        global_size = int(load["global_size"])
        ownership = tuple(int(value) for value in load["ownership_range"])
        canonical_count = int(load["canonical_key_count_local"])
        live_roundtrip = float(load["canonical_roundtrip_relative"])
        producer_roundtrip = float(
            load["canonical_to_current_roundtrip_relative"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"exact detail {label} adapter size/roundtrip is invalid") from exc
    if (
        not np.isfinite(producer_roundtrip)
        or producer_roundtrip < 0.0
        or producer_roundtrip > 1.0e-12
    ):
        raise ValueError(
            f"exact detail {label} adapter producer roundtrip is invalid"
        )
    if (
        local_size < 0
        or global_size <= 0
        or len(ownership) != 2
        or ownership[0] < 0
        or ownership[1] < ownership[0]
        or ownership[1] - ownership[0] != local_size
        or canonical_count < 0
        or not np.isfinite(live_roundtrip)
        or live_roundtrip < 0.0
        or live_roundtrip > 1.0e-12
        or (
            expected_rank is not None
            and load.get("canonical_layout_rank") != expected_rank
        )
        or load.get("canonical_layout_mpi_size") != expected_mpi_size
    ):
        raise ValueError(f"exact detail {label} adapter layout/roundtrip is invalid")
    rhs_repeat = load.get("rhs_repeat")
    if not isinstance(rhs_repeat, Mapping):
        raise ValueError(f"exact detail {label} adapter RHS repeat audit is missing")
    repeat_difference = rhs_repeat.get("relative_difference")
    if (
        rhs_repeat.get("pass") is not True
        or not _finite(repeat_difference)
        or float(repeat_difference) < 0.0
        or float(repeat_difference) > 1.0e-12
    ):
        raise ValueError(f"exact detail {label} adapter RHS repeat audit is invalid")

    distributed = load.get("distributed")
    if not isinstance(distributed, Mapping):
        raise ValueError(f"exact detail {label} adapter distributed audit is missing")
    for field in (
        "label",
        "role",
        "global_size",
        "global_sha256",
    ):
        if distributed.get(field) != load.get(field):
            raise ValueError(
                f"exact detail {label} adapter distributed {field} differs"
            )
    for field in (
        "owner_local",
        "ownership_coverage_exact",
    ):
        if distributed.get(field) is not True:
            raise ValueError(f"exact detail {label} adapter distributed {field} is false")
    for field in ("numeric_allgather", "full_numeric_replica"):
        if distributed.get(field) is not False:
            raise ValueError(
                f"exact detail {label} adapter distributed {field} must be false"
            )
    rank_records = distributed.get("rank_records")
    if (
        not isinstance(rank_records, Sequence)
        or isinstance(rank_records, (str, bytes))
        or len(rank_records) != expected_mpi_size
        or not all(isinstance(item, Mapping) for item in rank_records)
    ):
        raise ValueError(f"exact detail {label} adapter rank records are incomplete")
    ordered_rank_records = sorted(rank_records, key=lambda item: item.get("rank", -1))
    if [item.get("rank") for item in ordered_rank_records] != list(
        range(expected_mpi_size)
    ):
        raise ValueError(f"exact detail {label} adapter rank records are not ordered")
    canonical_hashes: list[str] = []
    cursor = 0
    for rank_record in ordered_rank_records:
        if (
            not isinstance(rank_record.get("rank"), int)
            or isinstance(rank_record.get("rank"), bool)
            or rank_record.get("mpi_size") != expected_mpi_size
            or rank_record.get("canonical_layout_rank")
            != rank_record.get("rank")
            or rank_record.get("canonical_layout_mpi_size") != expected_mpi_size
            or rank_record.get("label") != label
            or rank_record.get("role") != "rhs"
            or rank_record.get("global_size") != global_size
            or rank_record.get("global_sha256") != load.get("global_sha256")
            or rank_record.get("source_sha")
            != frozen_provenance.get("source_sha")
            or rank_record.get("source_definition_sha256")
            != load.get("source_definition_sha256")
            or rank_record.get("bare_f_operator_hash") != bare_hash
            or rank_record.get("source_provenance") != frozen_provenance
            or rank_record.get("canonical_key_set_sha256")
            != load.get("canonical_key_set_sha256")
            or rank_record.get("canonical_layout_sha256")
            != load.get("canonical_layout_sha256")
            or not _is_hex(rank_record.get("array_sha256"))
            or not _is_hex(rank_record.get("owner_row_array_sha256"))
            or not _is_hex(rank_record.get("rank_local_shard_binding_sha256"))
        ):
            raise ValueError(f"exact detail {label} adapter rank identity differs")
        try:
            first, last = (int(value) for value in rank_record["ownership_range"])
            record_local_size = int(rank_record["local_size"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"exact detail {label} adapter rank range is invalid") from exc
        if first != cursor or last < first or last - first != record_local_size:
            raise ValueError(f"exact detail {label} adapter owner coverage is not exact")
        canonical_hashes.append(str(rank_record["array_sha256"]))
        cursor = last
    if cursor != global_size:
        raise ValueError(f"exact detail {label} adapter owner coverage has a gap")
    expected_global_sha256 = hashlib.sha256(
        "\n".join(canonical_hashes).encode("ascii")
    ).hexdigest()
    if load.get("global_sha256") != expected_global_sha256:
        raise ValueError(f"exact detail {label} adapter global canonical hash differs")
    if expected_rank is not None:
        local_record = ordered_rank_records[expected_rank]
        if (
            local_record.get("rank") != expected_rank
            or local_record.get("mpi_size") != expected_mpi_size
            or local_record.get("array_sha256") != load.get("array_sha256")
            or local_record.get("owner_row_array_sha256")
            != load.get("owner_row_array_sha256")
            or local_record.get("canonical_layout_sha256")
            != load.get("canonical_layout_sha256")
            or local_record.get("global_sha256") != load.get("global_sha256")
            or local_record.get("rank_local_shard_binding_sha256")
            != load.get("rank_local_shard_binding_sha256")
        ):
            raise ValueError(f"exact detail {label} adapter local hashes differ")


def _validate_exact_checkpoint_recovery(
    label: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    active_local_size: int,
    expected_gamma_local_count: int | None = None,
) -> None:
    """Validate the compact three-group recovery proof on every checkpoint.

    The solver deliberately removes FE-sized row arrays before serializing an
    exact detail.  Their compact count/dtype/hash records are still required:
    without them a residual number could be claimed without proving that the
    three interior recoveries and the local Gamma/interior partition ran.
    """

    for row in rows:
        recovery = row.get("recovery")
        if not isinstance(recovery, Mapping):
            raise ValueError(
                f"exact detail {label} checkpoint recovery is missing"
            )
        if recovery.get("group_interior_solve_count") != 3:
            raise ValueError(
                f"exact detail {label} checkpoint recovery solve count is not three"
            )
        compact_rows: list[Mapping[str, Any]] = []
        for field in ("gamma_rows_local", "interior_rows_local"):
            compact = recovery.get(field)
            if not isinstance(compact, Mapping):
                raise ValueError(
                    f"exact detail {label} checkpoint recovery {field} is missing"
                )
            count = compact.get("count")
            if (
                not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
                or compact.get("dtype") != "int64"
                or not _is_hex(compact.get("sha256"))
            ):
                raise ValueError(
                    f"exact detail {label} checkpoint recovery {field} is invalid"
                )
            compact_rows.append(compact)
        if sum(int(compact["count"]) for compact in compact_rows) != int(
            active_local_size
        ):
            raise ValueError(
                f"exact detail {label} checkpoint recovery rows do not cover active local size"
            )
        if expected_gamma_local_count is not None:
            if (
                not isinstance(expected_gamma_local_count, int)
                or isinstance(expected_gamma_local_count, bool)
                or expected_gamma_local_count < 0
                or expected_gamma_local_count > int(active_local_size)
                or compact_rows[0]["count"] != expected_gamma_local_count
                or compact_rows[1]["count"]
                != int(active_local_size) - expected_gamma_local_count
            ):
                raise ValueError(
                    f"exact detail {label} checkpoint recovery Gamma/interior counts "
                    "do not match the rank mapping"
                )
        norms = recovery.get("interior_rhs_norms")
        if (
            not isinstance(norms, Sequence)
            or isinstance(norms, (str, bytes))
            or len(norms) != 3
            or any(not _finite(value) or float(value) < 0.0 for value in norms)
        ):
            raise ValueError(
                f"exact detail {label} checkpoint recovery RHS norms are invalid"
            )
        nonzero = recovery.get("interior_rhs_nonzero")
        if not isinstance(nonzero, bool) or nonzero is not any(
            float(value) > 0.0 for value in norms
        ):
            raise ValueError(
                f"exact detail {label} checkpoint recovery nonzero flag is inconsistent"
            )


def _conditional_resource_gate(resource: Mapping[str, Any]) -> bool:
    """Recompute the resource part of the 512 authorization from raw fields."""

    hard_limit = resource.get("hard_limit_bytes")
    rss_bytes = resource.get("rss_bytes")
    swap_bytes = resource.get("swap_bytes")
    return bool(
        resource.get("pass") is True
        and _finite(hard_limit)
        and float(hard_limit) == float(EXPECTED_HARD_STOP_BYTES)
        and _finite(rss_bytes)
        and float(rss_bytes) >= 0.0
        and float(rss_bytes) < float(hard_limit)
        and _finite(swap_bytes)
        and float(swap_bytes) == 0.0
        and resource.get("all_status_readable") is True
    )


def _conditional_wall_gate(
    gate_wall: Mapping[str, Any],
    raw_wall: Mapping[str, Any],
) -> bool:
    """Recompute the 512 wall condition and bind it to the raw snapshot."""

    elapsed = gate_wall.get("elapsed_seconds")
    budget = gate_wall.get("budget_seconds")
    raw_elapsed = raw_wall.get("elapsed_seconds")
    raw_budget = raw_wall.get("budget_seconds")
    return bool(
        _same_finite_number(elapsed, raw_elapsed)
        and _same_finite_number(budget, raw_budget)
        and _finite(elapsed)
        and float(elapsed) >= 0.0
        and _finite(budget)
        and float(budget) == EXPECTED_WALL_BUDGET_SECONDS
        and float(elapsed) < EXPECTED_WALL_BUDGET_SECONDS
    )


def _validate_conditional_gate_observation(
    *,
    checkpoint: int,
    history_values: Mapping[int, float],
    observation: Mapping[str, Any],
) -> bool:
    """Validate one serialized conditional decision against checkpoint facts.

    The returned value is the authorization recomputed from the history and
    raw resource/wall snapshot.  Stored ``authorized`` and gate booleans are
    only accepted when they agree with this value.
    """

    if checkpoint == 128:
        target = 256
        r64 = history_values.get(64)
        r128 = history_values.get(128)
        direct_gate = r128 is not None and r128 <= 0.8
        drop: float | None = None
        drop_gate = False
        if r64 is not None and r128 is not None and r64 > 0.0 and r128 > 0.0:
            drop = float(np.log10(r64 / r128))
            drop_gate = bool(np.isfinite(drop) and drop >= 0.10)
        residual_gate = bool(direct_gate or drop_gate)
    elif checkpoint == 256:
        target = 512
        required = (16, 32, 64, 128, 256)
        required_present = all(value in history_values for value in required)
        ordered_values = [history_values[value] for value in required if value in history_values]
        monotone = bool(
            required_present
            and all(
                current <= previous + 1.0e-14
                for previous, current in zip(ordered_values, ordered_values[1:], strict=False)
            )
        )
        r64 = history_values.get(64)
        r128 = history_values.get(128)
        r256 = history_values.get(256)
        direct_gate = False
        drop = None
        drop_gate = False
        residual_gate = bool(
            required_present and r256 is not None and r256 <= 1.0e-2 and monotone
        )
    else:
        raise ValueError(f"unsupported conditional source checkpoint {checkpoint}")

    if not isinstance(observation, Mapping):
        raise ValueError(f"conditional observation at {checkpoint} is not a mapping")
    if observation.get("target_checkpoint") != target:
        raise ValueError(f"conditional observation at {checkpoint} has wrong target")
    for field, expected in (
        ("residual_gate", residual_gate),
        ("authorized", None),
        ("authorization_consensus", True),
    ):
        if field == "authorized":
            if not isinstance(observation.get(field), bool):
                raise ValueError(f"conditional observation at {checkpoint} lacks boolean authorization")
        elif observation.get(field) is not expected:
            raise ValueError(f"conditional observation at {checkpoint} has invalid {field}")

    authorized_by_rank = observation.get("authorized_by_rank")
    if (
        not isinstance(authorized_by_rank, Sequence)
        or isinstance(authorized_by_rank, (str, bytes))
        or len(authorized_by_rank) != EXPECTED_MPI_SIZE
        or any(value is not observation["authorized"] for value in authorized_by_rank)
    ):
        raise ValueError(f"conditional observation at {checkpoint} has invalid rank consensus")

    resource = observation.get("resource_snapshot")
    resource_observation = observation.get("resource_observation")
    gate_wall = observation.get("wall_observation")
    raw_wall = resource.get("wall_observation") if isinstance(resource, Mapping) else None
    if not isinstance(resource, Mapping) or not isinstance(resource_observation, Mapping):
        raise ValueError(f"conditional observation at {checkpoint} lacks resource snapshot")
    if not isinstance(gate_wall, Mapping) or not isinstance(raw_wall, Mapping):
        raise ValueError(f"conditional observation at {checkpoint} lacks wall snapshot")
    for observed_field, raw_field in (
        ("current_rss_bytes", "rss_bytes"),
        ("current_swap_bytes", "swap_bytes"),
        ("all_status_readable", "all_status_readable"),
        ("pass", "pass"),
    ):
        if (
            observed_field not in resource_observation
            or raw_field not in resource
            or resource_observation[observed_field] != resource[raw_field]
        ):
            raise ValueError(
                f"conditional observation at {checkpoint} resource snapshot differs"
            )
    if resource_observation.get("current_sample_only") is not True:
        raise ValueError(f"conditional observation at {checkpoint} resource scope is invalid")

    resource_gate = _conditional_resource_gate(resource)
    wall_gate = _conditional_wall_gate(gate_wall, raw_wall)
    expected_authorized = (
        residual_gate
        if target == 256
        else residual_gate and resource_gate and wall_gate
    )
    if observation.get("authorized") is not expected_authorized:
        raise ValueError(f"conditional observation at {checkpoint} authorization was not recomputed")
    if observation.get("resource_gate") is not resource_gate:
        raise ValueError(f"conditional observation at {checkpoint} resource Gate differs")
    expected_wall_gate: bool | None = wall_gate if target == 512 else None
    if observation.get("wall_gate") is not expected_wall_gate:
        raise ValueError(f"conditional observation at {checkpoint} wall Gate differs")

    residual = observation.get("residual_observation")
    if not isinstance(residual, Mapping):
        raise ValueError(f"conditional observation at {checkpoint} lacks residual observation")
    expected_sequence = sorted(history_values)
    if residual.get("checkpoint") != checkpoint or residual.get(
        "observed_checkpoint_sequence"
    ) != expected_sequence:
        raise ValueError(f"conditional observation at {checkpoint} history sequence differs")
    for field, expected in (
        ("r64", r64),
        ("r128", r128),
        ("r256", history_values.get(256)),
        ("drop_64_to_128_decade", drop),
    ):
        if not _same_finite_number(residual.get(field), expected):
            raise ValueError(f"conditional observation at {checkpoint} residual field {field} differs")
    if residual.get("required_checkpoint_iterations") != [16, 32, 64, 128, 256]:
        raise ValueError(f"conditional observation at {checkpoint} required history differs")
    if checkpoint == 128:
        if residual.get("r128_threshold_gate") is not direct_gate:
            raise ValueError(f"conditional observation at {checkpoint} direct residual Gate differs")
        if residual.get("drop_64_to_128_gate") is not drop_gate:
            raise ValueError(f"conditional observation at {checkpoint} drop Gate differs")
        if residual.get("monotone_history") is not False:
            raise ValueError(f"conditional observation at {checkpoint} monotone field is invalid")
    else:
        if residual.get("required_checkpoint_set_complete") is not required_present:
            raise ValueError(f"conditional observation at {checkpoint} history completeness differs")
        if residual.get("monotone_history") is not monotone:
            raise ValueError(f"conditional observation at {checkpoint} monotone Gate differs")
    return bool(expected_authorized)


def _check_packet_aggregate_chain(
    root: Path,
    label: str,
    aggregate: Mapping[str, Any],
    read_files: list[dict[str, str]],
    *,
    expected_identities: Mapping[str, Mapping[str, Any]] | None = None,
    expected_identities_by_rank: Mapping[
        int, Mapping[str, Mapping[str, Any]]
    ]
    | None = None,
    expected_qualification_provenance: Mapping[str, Any] | None = None,
    expected_frozen_source_provenance: Mapping[str, Any] | None = None,
    expected_frozen_descriptor_hashes_by_rank: Mapping[
        int, Mapping[str, str]
    ]
    | Sequence[Mapping[str, str]]
    | None = None,
    expected_bare_f_operator_hash: str | None = None,
    checked_files: set[str] | None = None,
) -> tuple[bool, str | None]:
    """Validate an all-rank aggregate and each persisted role shard."""

    try:
        aggregate_path = _resolve_artifact_path(root, aggregate.get("path"), "aggregate path")
        if not aggregate_path.is_file() or _sha256(aggregate_path) != aggregate.get("sha256"):
            raise ValueError("packet aggregate file hash differs")
        aggregate_payload, aggregate_sha = _read_json(aggregate_path)
        read_files.append(
            {
                "path": str(aggregate_path.relative_to(root)),
                "sha256": aggregate_sha,
                "kind": "packet_aggregate",
            }
        )
        if aggregate_payload.get("label") != label:
            raise ValueError("packet aggregate label differs")
        aggregate_schema = "task040.v6.current_exact_packet_rank_manifest.v1"
        if aggregate.get("schema") != aggregate_schema:
            raise ValueError("packet aggregate descriptor schema differs")
        if aggregate_payload.get("schema") != aggregate_schema:
            raise ValueError("packet aggregate payload schema differs")
        if aggregate_payload.get("mpi_size") != EXPECTED_MPI_SIZE:
            raise ValueError("packet aggregate MPI size differs")
        descriptor_bare_hash = aggregate.get("bare_f_operator_hash")
        payload_bare_hash = aggregate_payload.get("bare_f_operator_hash")
        if (
            not _is_hex(descriptor_bare_hash)
            or descriptor_bare_hash != payload_bare_hash
        ):
            raise ValueError(
                "packet aggregate descriptor/payload bare operator hash differs"
            )
        if (
            expected_bare_f_operator_hash is not None
            and descriptor_bare_hash != expected_bare_f_operator_hash
        ):
            raise ValueError(
                "packet aggregate bare operator hash differs from root authority"
            )
        for container_name, container in (
            ("descriptor", aggregate),
            ("payload", aggregate_payload),
        ):
            if (
                container.get("numeric_allgather") is not False
                or container.get("full_numeric_replica") is not False
            ):
                raise ValueError(
                    f"packet aggregate {container_name} numeric replication flags are invalid"
                )
        rank_manifests = aggregate_payload.get("rank_manifests")
        if not isinstance(rank_manifests, Sequence) or isinstance(
            rank_manifests, (str, bytes)
        ) or len(rank_manifests) != EXPECTED_MPI_SIZE:
            raise ValueError("packet aggregate rank manifests are incomplete")
        expected_aggregate_counts = {
            "mpi_size": EXPECTED_MPI_SIZE,
            "rank_count": EXPECTED_MPI_SIZE,
            "role_count": len(_PACKET_ROLES),
            "role_count_per_rank": len(_PACKET_ROLES),
        }
        for field, expected_value in expected_aggregate_counts.items():
            if aggregate.get(field) != expected_value:
                raise ValueError(
                    f"packet aggregate descriptor {field} differs from authority"
                )
            if aggregate_payload.get(field) != expected_value:
                raise ValueError(
                    f"packet aggregate payload {field} differs from authority"
                )
            if aggregate.get(field) != aggregate_payload.get(field):
                raise ValueError(
                    f"packet aggregate descriptor/payload {field} differs"
                )
        if aggregate.get("qualification_source_provenance") != aggregate_payload.get(
            "qualification_source_provenance"
        ):
            raise ValueError("packet aggregate qualification provenance differs")
        if (
            expected_qualification_provenance is not None
            and aggregate.get("qualification_source_provenance")
            != expected_qualification_provenance
        ):
            raise ValueError(
                "packet aggregate qualification provenance differs from exact detail"
            )
        descriptor_hashes_by_rank = aggregate.get(
            "frozen_rhs_descriptor_metadata_sha256_by_rank"
        )
        payload_hashes_by_rank = aggregate_payload.get(
            "frozen_rhs_descriptor_metadata_sha256_by_rank"
        )
        if descriptor_hashes_by_rank != payload_hashes_by_rank:
            raise ValueError("packet aggregate descriptor-hash map differs")
        if not isinstance(descriptor_hashes_by_rank, Sequence) or isinstance(
            descriptor_hashes_by_rank, (str, bytes)
        ) or len(descriptor_hashes_by_rank) != EXPECTED_MPI_SIZE:
            raise ValueError("packet aggregate descriptor-hash map is incomplete")
        for rank, rank_hashes in enumerate(descriptor_hashes_by_rank):
            if not isinstance(rank_hashes, Mapping) or set(
                str(source_label) for source_label in rank_hashes
            ) != set(_EXACT_SOURCE_ORDER) or len(rank_hashes) != len(
                _EXACT_SOURCE_ORDER
            ) or any(
                not _is_hex(digest) for digest in rank_hashes.values()
            ):
                raise ValueError(
                    f"packet aggregate descriptor-hash map is invalid for rank {rank}"
                )
        if expected_frozen_descriptor_hashes_by_rank is not None:
            if isinstance(expected_frozen_descriptor_hashes_by_rank, Mapping):
                expected_descriptor_hashes = [
                    expected_frozen_descriptor_hashes_by_rank.get(rank)
                    for rank in range(EXPECTED_MPI_SIZE)
                ]
            else:
                expected_descriptor_hashes = list(
                    expected_frozen_descriptor_hashes_by_rank
                )
            if (
                len(expected_descriptor_hashes) != EXPECTED_MPI_SIZE
                or any(
                    not isinstance(rank_hashes, Mapping)
                    for rank_hashes in expected_descriptor_hashes
                )
                or any(
                    dict(actual) != dict(expected)
                    for actual, expected in zip(
                        descriptor_hashes_by_rank,
                        expected_descriptor_hashes,
                        strict=True,
                    )
                )
            ):
                raise ValueError(
                    "packet aggregate descriptor-hash map differs from exact detail"
                )
        descriptor_binding = aggregate.get(
            "frozen_rhs_descriptor_metadata_binding_sha256"
        )
        payload_binding = aggregate_payload.get(
            "frozen_rhs_descriptor_metadata_binding_sha256"
        )
        computed_binding = hashlib.sha256(
            json.dumps(
                descriptor_hashes_by_rank,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if (
            not _is_hex(descriptor_binding)
            or descriptor_binding != payload_binding
            or descriptor_binding != computed_binding
        ):
            raise ValueError("packet aggregate descriptor binding hash differs")
        if aggregate.get("qualification_source_provenance") is None:
            raise ValueError("packet aggregate qualification provenance is missing")
        if aggregate.get("source_provenance") != aggregate_payload.get(
            "source_provenance"
        ):
            raise ValueError("packet aggregate frozen source provenance differs")
        frozen_source_provenance = aggregate_payload.get("source_provenance")
        if not _valid_provenance(frozen_source_provenance):
            raise ValueError("packet aggregate frozen source provenance is invalid")
        if expected_frozen_source_provenance is not None and frozen_source_provenance != (
            dict(expected_frozen_source_provenance)
        ):
            raise ValueError(
                "packet aggregate frozen source provenance differs from exact detail"
            )
        if expected_bare_f_operator_hash is not None and not _is_hex(
            expected_bare_f_operator_hash
        ):
            raise ValueError("packet aggregate expected bare operator hash is invalid")
        seen_ranks: list[int] = []
        seen_paths: set[str] = set()
        packets_by_role: dict[str, list[Mapping[str, Any]]] = {
            role: [] for role in _PACKET_ROLES
        }
        for expected_rank, rank_manifest in enumerate(rank_manifests):
            if not isinstance(rank_manifest, Mapping) or rank_manifest.get("rank") != expected_rank:
                raise ValueError("packet aggregate rank ordering differs")
            roles = rank_manifest.get("roles")
            if not isinstance(roles, Mapping) or set(roles) != set(_PACKET_ROLES):
                raise ValueError("packet aggregate role set is incomplete")
            seen_ranks.append(expected_rank)
            for role in _PACKET_ROLES:
                packet = roles[role]
                if not isinstance(packet, Mapping):
                    raise ValueError("packet aggregate role is not a mapping")
                if packet.get("rank") != expected_rank:
                    raise ValueError("packet aggregate packet rank differs")
                if packet.get("mpi_size") != EXPECTED_MPI_SIZE:
                    raise ValueError("packet aggregate packet MPI size differs")
                if packet.get("source_provenance") != frozen_source_provenance:
                    raise ValueError(
                        f"packet {role} source provenance differs from frozen authority"
                    )
                if expected_bare_f_operator_hash is not None and packet.get(
                    "bare_f_operator_hash"
                ) != expected_bare_f_operator_hash:
                    raise ValueError(
                        f"packet {role} bare operator hash differs from root authority"
                    )
                for path_field in ("path", "array_path", "manifest_path"):
                    path = _resolve_artifact_path(
                        root, packet.get(path_field), f"packet {role} {path_field}"
                    )
                    path_key = str(path)
                    if path_key in seen_paths:
                        raise ValueError("packet aggregate contains duplicate paths")
                    seen_paths.add(path_key)
                if checked_files is not None:
                    # Aggregates are expected to be distinct per label.  Keep
                    # a diagnostic key only; never skip validation based on a
                    # writer-supplied packet identity.  Otherwise a packet
                    # from one role/label could make a later role appear
                    # checked without reopening its own files.
                    checked_files.add(
                        f"{label}:{expected_rank}:{role}:{packet.get('path')}"
                    )
                packets_by_role[role].append(packet)
                expected = None
                if expected_identities_by_rank is not None:
                    rank_expected = expected_identities_by_rank.get(expected_rank)
                    if isinstance(rank_expected, Mapping):
                        expected = rank_expected.get(role)
                elif expected_identities is not None:
                    expected = expected_identities.get(role)
                valid, error = _check_packet_file_chain(
                    root,
                    label,
                    role,
                    packet,
                    read_files,
                    expected_identity=expected,
                )
                if not valid:
                    raise ValueError(error or f"packet {role} file chain is invalid")
        if seen_ranks != list(range(EXPECTED_MPI_SIZE)):
            raise ValueError("packet aggregate rank set is incomplete")

        # Recompute the distributed contract from every reopened packet
        # record.  These checks deliberately operate on role-specific
        # metadata; canonical shards are not PETSc ownership ranges.
        for role, role_packets in packets_by_role.items():
            if len(role_packets) != EXPECTED_MPI_SIZE:
                raise ValueError(f"packet aggregate {role} rank coverage is incomplete")
            if len(
                {
                    _json_signature(packet["source_provenance"])
                    for packet in role_packets
                }
            ) != 1:
                raise ValueError(f"packet aggregate {role} provenance differs across ranks")
            for field in ("source_definition_sha256", "bare_f_operator_hash"):
                if len({packet[field] for packet in role_packets}) != 1:
                    raise ValueError(
                        f"packet aggregate {role} {field} differs across ranks"
                    )
            if len({packet["canonical_key_set_sha256"] for packet in role_packets}) != 1:
                raise ValueError(
                    f"packet aggregate {role} canonical key-set differs across ranks"
                )

            if role == "exact_output_canonical":
                global_sizes = {
                    int(packet["global_active_size"]) for packet in role_packets
                }
                if len(global_sizes) != 1 or next(iter(global_sizes)) <= 0:
                    raise ValueError(
                        "exact canonical packet global active sizes differ"
                    )
                if sum(
                    int(packet["canonical_key_count_local"])
                    for packet in role_packets
                ) != next(iter(global_sizes)):
                    raise ValueError(
                        "exact canonical local counts do not cover global active size"
                    )
            elif role == "exact_output_owner_rows":
                global_sizes = {int(packet["global_size"]) for packet in role_packets}
                if len(global_sizes) != 1 or next(iter(global_sizes)) <= 0:
                    raise ValueError("owner-row global sizes differ")
                ranges: list[tuple[int, int, int]] = []
                for packet in role_packets:
                    ownership = packet.get("ownership_range")
                    if (
                        not isinstance(ownership, Sequence)
                        or isinstance(ownership, (str, bytes))
                        or len(ownership) != 2
                        or any(
                            not isinstance(value, int) or isinstance(value, bool)
                            for value in ownership
                        )
                    ):
                        raise ValueError("owner-row ownership range is invalid")
                    start, end = int(ownership[0]), int(ownership[1])
                    global_size = next(iter(global_sizes))
                    if (
                        start < 0
                        or end < start
                        or end > global_size
                        or int(packet["local_size"]) != end - start
                    ):
                        raise ValueError("owner-row ownership span is invalid")
                    ranges.append((start, end, int(packet["rank"])))
                cursor = 0
                for start, end, _rank in sorted(ranges):
                    if start != cursor:
                        raise ValueError("owner-row ranges have a gap or overlap")
                    cursor = end
                if cursor != next(iter(global_sizes)):
                    raise ValueError("owner-row ranges do not cover global size")
            else:
                global_sizes = {
                    int(packet["canonical_global_size"]) for packet in role_packets
                }
                expected_global_size = (
                    EXPECTED_LOWER_COUNT
                    if role == "gamma_l_canonical"
                    else EXPECTED_UPPER_COUNT
                )
                if global_sizes != {expected_global_size}:
                    raise ValueError(
                        f"{role} global size differs from Gamma layout authority"
                    )
                if sum(
                    int(packet["canonical_key_count_local"])
                    for packet in role_packets
                ) != expected_global_size:
                    raise ValueError(
                        f"{role} local counts do not cover Gamma layout authority"
                    )

        for expected_rank, rank_manifest in enumerate(rank_manifests):
            base = rank_manifest["roles"]["exact_output_canonical"]
            for role in _PACKET_ROLES[1:]:
                packet = rank_manifest["roles"][role]
                for field in (
                    "source_definition_sha256",
                    "bare_f_operator_hash",
                    "source_provenance",
                ):
                    if packet[field] != base[field]:
                        raise ValueError(
                            "packet roles on one rank do not share "
                            f"{field} (rank {expected_rank})"
                        )

        exact_packets = packets_by_role["exact_output_canonical"]
        owner_packets = packets_by_role["exact_output_owner_rows"]
        for exact_packet, owner_packet in zip(exact_packets, owner_packets, strict=True):
            if (
                exact_packet["canonical_key_set_sha256"]
                != owner_packet["canonical_key_set_sha256"]
                or exact_packet["canonical_layout_sha256"]
                != owner_packet["canonical_layout_sha256"]
                or int(exact_packet["global_active_size"])
                != int(owner_packet["global_size"])
            ):
                raise ValueError(
                    "same-rank exact canonical and owner-row identity differs"
                )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


_EXACT_SOURCE_ORDER = (
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "modal_traction_positive",
    "modal_traction_negative",
    "fixed_random_repeat_1",
)


def _exact_detail_semantic_signature(
    exact_result: Mapping[str, Any],
    *,
    expected_bare_f_operator_hash: str | None = None,
    expected_rank: int | None = None,
    expected_mpi_size: int = EXPECTED_MPI_SIZE,
    expected_gamma_local_count: int | None = None,
    require_adapter: bool = False,
) -> tuple[dict[str, Any], dict[str, Mapping[str, Mapping[str, Any]]]]:
    """Return rank-comparable exact observations and live packet identities.

    Packet value hashes and artifact paths are intentionally kept out of the
    rank-consensus signature: owner shards are expected to differ by rank.
    The returned identity map is retained separately for per-rank packet
    verification.
    """

    family = exact_result.get("family")
    if not isinstance(family, Mapping):
        raise ValueError("exact detail lacks family mapping")
    if exact_result.get("schema") != "task040.v6_2.exact_qualification_packets.v1":
        raise ValueError("exact detail result schema is invalid")
    if family.get("schema") != "task040.v6.exact_qualification_family.v1":
        raise ValueError("exact detail family schema is invalid")
    if tuple(family.get("ordered_labels", ())) != _EXACT_SOURCE_ORDER:
        raise ValueError("exact detail source order is not the V6 authority order")
    records = family.get("source_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("exact detail source_records is not a sequence")
    tolerance = family.get("full_residual_tolerance")
    if not _finite(tolerance) or float(tolerance) != 1.0e-9:
        raise ValueError("exact detail residual tolerance is not the fixed V6 value")
    if family.get("packetization_required") is not True:
        raise ValueError("executed exact detail must require packetization")
    if tuple(family.get("initial_labels", ())) != _EXACT_SOURCE_ORDER[:2]:
        raise ValueError("exact detail initial source labels are not the V6 pair")
    for container_name, container in (("family", family), ("exact result", exact_result)):
        for field in ("numeric_allgather", "full_numeric_replica"):
            if container.get(field) is not False:
                raise ValueError(
                    f"{container_name} {field} must be explicitly false"
                )
    semantic_records: list[dict[str, Any]] = []
    expected_identities: dict[str, Mapping[str, Mapping[str, Any]]] = {}
    seen_labels: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("exact detail contains a non-mapping source record")
        label = record.get("label")
        if label not in _EXACT_SOURCE_ORDER or label in seen_labels:
            raise ValueError("exact detail source labels are duplicated or unknown")
        seen_labels.add(str(label))
        fgmres = record.get("fgmres")
        if not isinstance(fgmres, Mapping):
            raise ValueError(f"exact detail {label} lacks fgmres mapping")
        adapter = record.get("adapter")
        if require_adapter:
            _validate_exact_adapter_audit(
                str(label),
                adapter,
                exact_result,
                expected_bare_f_operator_hash=expected_bare_f_operator_hash,
                expected_rank=expected_rank,
                expected_mpi_size=expected_mpi_size,
            )
        adapter_load = (
            adapter.get("load") if isinstance(adapter, Mapping) else None
        )
        if (
            fgmres.get("schema") != "task040.v6.exact_interface_fgmres.v1"
            or fgmres.get("label") != label
        ):
            raise ValueError(f"exact detail {label} FGMRES identity is invalid")
        if fgmres.get("full_residual_tolerance") != float(tolerance):
            raise ValueError(f"exact detail {label} FGMRES tolerance is inconsistent")
        for field in (
            "identity_preconditioner",
            "active_rhs_unchanged",
            "condensed_rhs_unchanged",
        ):
            if fgmres.get(field) is not True:
                raise ValueError(f"exact detail {label} {field} is not true")
        for field in ("numeric_allgather", "full_numeric_replica"):
            if fgmres.get(field) is not False:
                raise ValueError(
                    f"exact detail {label} {field} must be explicitly false"
                )
        if tuple(fgmres.get("mandatory_checkpoints", ())) != (16, 32, 64, 128):
            raise ValueError(f"exact detail {label} mandatory checkpoints are invalid")
        if tuple(fgmres.get("conditional_checkpoints", ())) != (256, 512):
            raise ValueError(f"exact detail {label} conditional checkpoints are invalid")
        fgmres_restart = fgmres.get("restart")
        if (
            not isinstance(fgmres_restart, int)
            or isinstance(fgmres_restart, bool)
            or fgmres_restart <= 0
        ):
            raise ValueError(f"exact detail {label} FGMRES restart is invalid")
        rhs_norm = fgmres.get("full_rhs_norm")
        interface_rhs_norm = fgmres.get("interface_rhs_norm")
        if any(
            not _finite(value) or float(value) <= 0.0
            for value in (rhs_norm, interface_rhs_norm)
        ):
            raise ValueError(f"exact detail {label} RHS norm denominator is invalid")
        for digest_name in (
            "active_rhs_initial_sha256",
            "active_rhs_final_sha256",
            "condensed_rhs_initial_sha256",
            "condensed_rhs_final_sha256",
        ):
            if not _is_hex(fgmres.get(digest_name)):
                raise ValueError(f"exact detail {label} RHS digest is invalid")
        if (
            fgmres["active_rhs_initial_sha256"]
            != fgmres["active_rhs_final_sha256"]
            or fgmres["condensed_rhs_initial_sha256"]
            != fgmres["condensed_rhs_final_sha256"]
        ):
            raise ValueError(f"exact detail {label} RHS changed during solve")
        history = fgmres.get("checkpoint_history")
        if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
            raise ValueError(f"exact detail {label} lacks checkpoint history")
        checkpoints = fgmres.get("checkpoints")
        if not isinstance(checkpoints, Mapping):
            raise ValueError(f"exact detail {label} lacks checkpoint mapping")
        rows: list[dict[str, Any]] = []
        history_items: dict[int, Mapping[str, Any]] = {}
        early_final_items: list[Mapping[str, Any]] = []
        seen_iterations: set[int] = set()
        for item in history:
            if not isinstance(item, Mapping):
                raise ValueError(f"exact detail {label} has a non-mapping checkpoint")
            try:
                iteration = int(item["iteration"])
                relative = float(item["full_true_residual_relative"])
                item_tolerance = float(item["full_residual_tolerance"])
                interface_norm = float(item["interface_true_residual_norm"])
                interface_relative = float(
                    item["interface_true_residual_relative"]
                )
                full_norm = float(item["full_true_residual_norm"])
                full_denominator = float(item["rhs_norm_denominator"])
                interface_denominator = float(
                    item["interface_rhs_norm_denominator"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"exact detail {label} has an incomplete checkpoint"
                ) from exc
            finite_flag = item.get("finite")
            accepted_flag = item.get("accepted_full_solution")
            checkpoint_kind = item.get("checkpoint_kind")
            if checkpoint_kind not in {"mandatory", "conditional", "early_final"}:
                raise ValueError(f"exact detail {label} checkpoint kind is invalid")
            if not isinstance(finite_flag, bool) or not isinstance(
                accepted_flag, bool
            ):
                raise ValueError(f"exact detail {label} checkpoint flags are invalid")
            if item.get("label") != label or item.get("restart") != fgmres_restart:
                raise ValueError(f"exact detail {label} checkpoint identity is invalid")
            if any(
                not _finite(number) or float(number) < 0.0
                for number in (interface_norm, full_norm)
            ) or any(
                not _finite(number) or float(number) <= 0.0
                for number in (full_denominator, interface_denominator)
            ):
                raise ValueError(f"exact detail {label} checkpoint norms are invalid")
            if not np.isclose(
                full_denominator,
                float(rhs_norm),
                rtol=1.0e-12,
                atol=1.0e-12,
            ) or not np.isclose(
                interface_denominator,
                float(interface_rhs_norm),
                rtol=1.0e-12,
                atol=1.0e-12,
            ):
                raise ValueError(
                    f"exact detail {label} checkpoint denominators differ from RHS norms"
                )
            expected_full_relative = full_norm / full_denominator
            expected_interface_relative = interface_norm / interface_denominator
            if (
                iteration <= 0
                or iteration > 512
                or iteration in seen_iterations
                or not np.isfinite(relative)
                or relative < 0.0
                or not np.isfinite(interface_relative)
                or interface_relative < 0.0
                or not np.isclose(
                    relative,
                    expected_full_relative,
                    rtol=1.0e-12,
                    atol=1.0e-12,
                )
                or not np.isclose(
                    interface_relative,
                    expected_interface_relative,
                    rtol=1.0e-12,
                    atol=1.0e-12,
                )
                or not np.isfinite(item_tolerance)
                or item_tolerance != float(tolerance)
                or not finite_flag
            ):
                raise ValueError(f"exact detail {label} checkpoint is invalid")
            if checkpoint_kind == "early_final":
                if iteration in {16, 32, 64, 128, 256, 512}:
                    raise ValueError(
                        f"exact detail {label} early-final overlaps a requested checkpoint"
                    )
                early_final_items.append(item)
            elif checkpoint_kind == "mandatory" and iteration not in {
                16,
                32,
                64,
                128,
            }:
                raise ValueError(f"exact detail {label} mandatory checkpoint kind is misplaced")
            elif checkpoint_kind == "conditional" and iteration not in {256, 512}:
                raise ValueError(f"exact detail {label} conditional checkpoint kind is misplaced")
            seen_iterations.add(iteration)
            history_items[iteration] = item
            rows.append(
                {
                    "iteration": iteration,
                    "checkpoint_kind": checkpoint_kind,
                    "label": str(item["label"]),
                    "restart": int(item["restart"]),
                    "interface_true_residual_norm": interface_norm,
                    "interface_true_residual_relative": interface_relative,
                    "full_true_residual_norm": full_norm,
                    "full_true_residual_relative": relative,
                    "rhs_norm_denominator": full_denominator,
                    "interface_rhs_norm_denominator": interface_denominator,
                    "full_residual_tolerance": item_tolerance,
                    "finite": finite_flag,
                    "accepted_full_solution": accepted_flag,
                    "recovery": item.get("recovery"),
                }
            )
        if require_adapter:
            if not isinstance(adapter_load, Mapping):
                raise ValueError(f"exact detail {label} adapter load is missing")
            try:
                active_local_size = int(adapter_load["local_size"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"exact detail {label} adapter local size is invalid"
                ) from exc
            _validate_exact_checkpoint_recovery(
                str(label),
                rows,
                active_local_size=active_local_size,
                expected_gamma_local_count=expected_gamma_local_count,
            )
        for row in rows:
            expected_accepted = bool(
                row["finite"]
                and row["full_true_residual_relative"] <= float(tolerance)
            )
            if row["accepted_full_solution"] is not expected_accepted:
                raise ValueError(
                    f"exact detail {label} checkpoint accepted flag is not pointwise"
                )
        if [row["iteration"] for row in rows] != sorted(seen_iterations):
            raise ValueError(f"exact detail {label} checkpoint order is invalid")
        requested_iterations = seen_iterations - {
            int(item["iteration"]) for item in early_final_items
        }
        if set(checkpoints) != {str(iteration) for iteration in requested_iterations}:
            raise ValueError(f"exact detail {label} checkpoint mapping differs")
        mandatory_iterations = {16, 32, 64, 128}
        if len(early_final_items) > 1:
            raise ValueError(f"exact detail {label} has multiple early-final records")
        if early_final_items:
            early_iteration = int(early_final_items[0]["iteration"])
            if early_iteration != max(seen_iterations):
                raise ValueError(f"exact detail {label} early-final record is not final")
            required_before_early = {
                value
                for value in (*sorted(mandatory_iterations), 256, 512)
                if value < early_iteration
            }
            if not required_before_early.issubset(requested_iterations):
                raise ValueError(
                    f"exact detail {label} requested checkpoints before early-final are incomplete"
                )
            early_record = fgmres.get("early_final_record")
            if not isinstance(early_record, Mapping) or _json_signature(
                early_record
            ) != _json_signature(early_final_items[0]):
                raise ValueError(f"exact detail {label} early-final record differs")
        elif fgmres.get("early_final_record") is not None:
            raise ValueError(f"exact detail {label} has an unexpected early-final record")
        for iteration in requested_iterations:
            checkpoint = checkpoints[str(iteration)]
            if not isinstance(checkpoint, Mapping):
                raise ValueError(f"exact detail {label} checkpoint is not a mapping")
            if checkpoint.get("iteration") != iteration or _json_signature(
                checkpoint
            ) != _json_signature(history_items[iteration]):
                raise ValueError(f"exact detail {label} checkpoint index differs")
        final_iteration = fgmres.get("final_iteration")
        if (
            not isinstance(final_iteration, int)
            or isinstance(final_iteration, bool)
            or final_iteration < 0
            or final_iteration > 512
            or final_iteration != max(seen_iterations)
        ):
            raise ValueError(f"exact detail {label} final iteration is inconsistent")
        final_record = fgmres.get("final_record")
        if seen_iterations:
            if not isinstance(final_record, Mapping):
                raise ValueError(f"exact detail {label} final record is missing")
            if _json_signature(final_record) != _json_signature(
                history_items[final_iteration]
            ):
                raise ValueError(f"exact detail {label} final record differs from history")
        elif final_record is not None or final_iteration != 0:
            raise ValueError(f"exact detail {label} empty final record is invalid")
        stopped_at_happy_breakdown = fgmres.get("stopped_at_happy_breakdown")
        if not isinstance(stopped_at_happy_breakdown, bool):
            raise ValueError(f"exact detail {label} happy-breakdown flag is invalid")
        if early_final_items and not stopped_at_happy_breakdown:
            raise ValueError(f"exact detail {label} early-final record lacks happy-breakdown flag")
        if not early_final_items:
            requested_order = (16, 32, 64, 128, 256, 512)
            if stopped_at_happy_breakdown:
                expected_prefix = {
                    iteration
                    for iteration in requested_order
                    if iteration <= final_iteration
                }
                if requested_iterations != expected_prefix:
                    raise ValueError(
                        f"exact detail {label} happy-breakdown checkpoint prefix is incomplete"
                    )
            elif not mandatory_iterations.issubset(requested_iterations):
                raise ValueError(
                    f"exact detail {label} mandatory checkpoints are incomplete"
                )
        best = min(
            (row["full_true_residual_relative"] for row in rows),
            default=float("inf"),
        )
        observed_best = record.get("best_full_true_residual_relative")
        if not _finite(observed_best) or float(observed_best) != best:
            raise ValueError(f"exact detail {label} best residual is not recomputed")
        full_gate = bool(
            np.isfinite(best) and best >= 0.0 and best <= float(tolerance)
        )
        if record.get("full_residual_gate_pass") is not full_gate:
            raise ValueError(f"exact detail {label} full residual Gate is inconsistent")
        packet_error = fgmres.get("packetization_gate_error")
        if packet_error not in (None, ""):
            raise ValueError(f"exact detail {label} has packetization error: {packet_error}")
        packet_gate_value = record.get("packetization_gate_pass")
        consumed_value = fgmres.get("accepted_solution_consumed")
        if not isinstance(packet_gate_value, bool) or not isinstance(
            consumed_value, bool
        ):
            raise ValueError(f"exact detail {label} packet/accepted flags are invalid")
        packet_gate = packet_gate_value
        consumed = consumed_value
        accepted_present = fgmres.get("accepted_solution_present")
        if not isinstance(accepted_present, bool):
            raise ValueError(f"exact detail {label} accepted-solution flag is invalid")
        if accepted_present != consumed:
            raise ValueError(f"exact detail {label} accepted-solution flags disagree")
        released = fgmres.get("accepted_solution_released_by_driver")
        if not isinstance(released, bool) or released != accepted_present:
            raise ValueError(f"exact detail {label} accepted-solution release flag is invalid")
        accepted_observed = any(row["accepted_full_solution"] for row in rows)
        if accepted_observed != full_gate or accepted_present != accepted_observed:
            raise ValueError(f"exact detail {label} accepted-solution observation is inconsistent")
        accepted_iterations = [
            int(row["iteration"]) for row in rows if row["accepted_full_solution"]
        ]
        accepted_solution_iteration = fgmres.get("accepted_solution_iteration")
        expected_accepted_iteration = (
            max(accepted_iterations) if accepted_iterations else None
        )
        if accepted_solution_iteration != expected_accepted_iteration:
            raise ValueError(
                f"exact detail {label} accepted-solution iteration is inconsistent"
            )
        conditional_authorized = fgmres.get("conditional_authorized", {})
        conditional_completed = fgmres.get("conditional_completed", {})
        if not isinstance(conditional_authorized, Mapping) or not isinstance(
            conditional_completed, Mapping
        ):
            raise ValueError(f"exact detail {label} conditional audit is invalid")
        if set(conditional_authorized) != {"256", "512"} or set(
            conditional_completed
        ) != {"256", "512"}:
            raise ValueError(f"exact detail {label} conditional keys are invalid")
        if any(
            not isinstance(conditional_authorized.get(key), bool)
            or not isinstance(conditional_completed.get(key), bool)
            for key in ("256", "512")
        ):
            raise ValueError(f"exact detail {label} conditional flags are invalid")
        conditional_observations = fgmres.get("conditional_gate_observations")
        if not isinstance(conditional_observations, Mapping):
            raise ValueError(f"exact detail {label} conditional observations are missing")
        expected_observation_keys = {
            str(iteration)
            for iteration in (128, 256)
            if iteration in seen_iterations
        }
        if set(conditional_observations) != expected_observation_keys:
            raise ValueError(f"exact detail {label} conditional observation keys are invalid")
        history_values = {
            int(row["iteration"]): float(row["full_true_residual_relative"])
            for row in rows
        }
        recomputed_authorized: dict[str, bool] = {"256": False, "512": False}
        for decision_iteration in (128, 256):
            if decision_iteration not in seen_iterations:
                continue
            # A decision is made at the boundary before any later cycle is
            # entered.  Recompute it from exactly the history available at
            # that point; using the final history would incorrectly make the
            # 128 observation depend on a later 256/512 (or early-final)
            # record.
            decision_history_values = {
                iteration: value
                for iteration, value in history_values.items()
                if iteration <= decision_iteration
            }
            recomputed_authorized[str(256 if decision_iteration == 128 else 512)] = (
                _validate_conditional_gate_observation(
                    checkpoint=decision_iteration,
                    history_values=decision_history_values,
                    observation=conditional_observations[str(decision_iteration)],
                )
            )
        for conditional_iteration in (256, 512):
            authorized_value = conditional_authorized.get(str(conditional_iteration))
            completed_value = conditional_completed.get(str(conditional_iteration))
            if authorized_value is not recomputed_authorized[str(conditional_iteration)]:
                raise ValueError(
                    f"exact detail {label} conditional {conditional_iteration} authorization is not recomputed"
                )
            if completed_value and not authorized_value:
                raise ValueError(
                    f"exact detail {label} completed unauthorized conditional checkpoint"
                )
            if completed_value != (conditional_iteration in seen_iterations):
                raise ValueError(
                    f"exact detail {label} conditional completion flag is inconsistent"
                )
        if conditional_authorized["512"] and not conditional_completed["256"]:
            raise ValueError(
                f"exact detail {label} authorized 512 without completed 256"
            )
        if not conditional_authorized.get("256", False):
            if any(row["iteration"] > 128 for row in rows):
                raise ValueError(
                    f"exact detail {label} crossed unauthorized 256 boundary"
                )
        elif not conditional_authorized.get("512", False) and any(
            row["iteration"] > 256 for row in rows
        ):
            raise ValueError(
                f"exact detail {label} crossed unauthorized 512 boundary"
            )
        packet_audit = fgmres.get("accepted_solution_packet_audit")
        if full_gate:
            if not packet_gate or not consumed or not isinstance(packet_audit, Mapping):
                raise ValueError(
                    f"exact detail {label} accepted source lacks packet audit"
                )
            packet_write = packet_audit.get("packet_write")
            identities = packet_audit.get("expected_packet_identities")
            if not isinstance(packet_write, Mapping) or not isinstance(
                identities, Mapping
            ):
                raise ValueError(f"exact detail {label} lacks packet identities")
            if set(packet_write) != set(_PACKET_ROLES) or set(identities) != set(
                _PACKET_ROLES
            ):
                raise ValueError(f"exact detail {label} packet role set is incomplete")
            expected_identities[str(label)] = identities
        elif packet_gate or consumed or packet_audit is not None:
            raise ValueError(
                f"exact detail {label} has packet evidence without a residual Gate"
            )
        semantic_records.append(
            {
                "label": str(label),
                "full_residual_gate_pass": full_gate,
                "packetization_gate_pass": packet_gate,
                "best_full_true_residual_relative": best,
                "checkpoint_history": rows,
                "accepted_solution_consumed": consumed,
            }
        )

    initial_pair_pass = bool(
        len(semantic_records) >= 2
        and all(
            record["full_residual_gate_pass"]
            and record["packetization_gate_pass"]
            for record in semantic_records[:2]
        )
    )
    skipped = family.get("skipped_labels")
    if not isinstance(skipped, Sequence) or isinstance(skipped, (str, bytes)):
        raise ValueError("exact detail skipped_labels is not a sequence")
    expected_skipped = list(_EXACT_SOURCE_ORDER[2:]) if not initial_pair_pass else []
    if list(skipped) != expected_skipped:
        raise ValueError("exact detail skipped labels do not match the initial pair Gate")
    expected_record_count = 5 if initial_pair_pass else 2
    if len(semantic_records) != expected_record_count:
        raise ValueError("exact detail source count does not match continuation policy")
    all_sources_pass = bool(
        initial_pair_pass
        and len(semantic_records) == len(_EXACT_SOURCE_ORDER)
        and all(
            record["full_residual_gate_pass"]
            and record["packetization_gate_pass"]
            for record in semantic_records
        )
    )
    if family.get("initial_pair_gate_pass") is not initial_pair_pass:
        raise ValueError("exact detail initial pair Gate is inconsistent")
    if family.get("all_sources_gate_pass") is not all_sources_pass:
        raise ValueError("exact detail all-sources Gate is inconsistent")
    expected_family_status = (
        "completed_initial_pair_and_remaining_sources"
        if all_sources_pass
        else "completed_exact_numerical_gate_negative_continuation_allowed"
    )
    expected_family_classification = (
        "V6_EXACT_QUALIFICATION_READY"
        if all_sources_pass
        else "V6_EXACT_QUALIFICATION_GATE_FAIL"
    )
    if family.get("status") != expected_family_status:
        raise ValueError("exact detail family status is inconsistent with residual Gates")
    if family.get("classification") != expected_family_classification:
        raise ValueError(
            "exact detail family classification is inconsistent with residual Gates"
        )
    if family.get("normal_numerical_negative") is not (not all_sources_pass):
        raise ValueError("exact detail numerical-negative flag is inconsistent")
    expected_result_status = (
        "completed_all_sources_and_packet_aggregate"
        if all_sources_pass
        else expected_family_status
    )
    expected_result_classification = (
        "V6_EXACT_QUALIFICATION_READY_WITH_PACKETS"
        if all_sources_pass
        else "V6_EXACT_QUALIFICATION_GATE_FAIL"
    )
    if exact_result.get("status") != expected_result_status:
        raise ValueError("exact detail result status is inconsistent")
    if exact_result.get("classification") != expected_result_classification:
        raise ValueError("exact detail result classification is inconsistent")
    if tuple(exact_result.get("source_order", ())) != _EXACT_SOURCE_ORDER:
        raise ValueError("exact detail result source order is inconsistent")
    exact_summary = {
        "status": exact_result.get("status"),
        "classification": exact_result.get("classification"),
        "ordered_labels": list(_EXACT_SOURCE_ORDER),
        "source_records": semantic_records,
        "skipped_labels": expected_skipped,
        "initial_pair_gate_pass": initial_pair_pass,
        "all_sources_gate_pass": all_sources_pass,
        "full_residual_tolerance": float(tolerance),
        "numerical_negative": not all_sources_pass,
    }
    return exact_summary, expected_identities


def _recomputed_initial_pair_publication(
    exact_result: Mapping[str, Any],
    semantic_summary: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Recompute initial-pair publication from the reopened exact detail."""

    family = exact_result.get("family")
    if not isinstance(family, Mapping):
        raise ValueError("exact detail family is missing for packet publication")
    initial_pair_gate_pass = semantic_summary.get("initial_pair_gate_pass")
    if not isinstance(initial_pair_gate_pass, bool):
        raise ValueError("exact detail initial pair Gate is not boolean")
    if family.get("initial_pair_gate_pass") is not initial_pair_gate_pass:
        raise ValueError("exact detail publication Gate differs from family Gate")
    ledger = exact_result.get("initial_pair_publication")
    if not isinstance(ledger, Mapping):
        raise ValueError("exact detail initial-pair publication ledger is missing")
    if ledger.get("initial_pair_gate_pass") is not initial_pair_gate_pass:
        raise ValueError("exact detail publication ledger Gate differs from family Gate")
    expected_status = (
        "passed_then_published"
        if initial_pair_gate_pass
        else "failed_then_discarded"
    )
    if ledger.get("status") != expected_status:
        raise ValueError("exact detail publication status is inconsistent")
    packet_root_value = exact_result.get("packet_root")
    if not isinstance(packet_root_value, str) or not packet_root_value:
        raise ValueError("exact detail packet root is missing")
    packet_root = (
        _resolve_artifact_path(root, packet_root_value, "exact packet root")
        if root is not None
        else Path(packet_root_value)
    )
    packet_root_exists = packet_root.exists()
    if ledger.get("packet_root_exists_after_gate") is not packet_root_exists:
        raise ValueError("exact detail packet-root existence ledger differs")
    if packet_root_exists is not initial_pair_gate_pass:
        raise ValueError("exact detail packet-root existence differs from family Gate")
    return {
        "initial_pair_gate_pass": initial_pair_gate_pass,
        "status": expected_status,
        "packet_root_exists_after_gate": packet_root_exists,
    }


def _recomputed_exact_compact_summary(
    exact_result: Mapping[str, Any],
    semantic_summary: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Rebuild the compact exact summary from the reopened detail payload."""

    family = exact_result["family"]
    initial_pair_publication = _recomputed_initial_pair_publication(
        exact_result,
        semantic_summary,
        root=root,
    )
    semantic_by_label = {
        str(record["label"]): record
        for record in semantic_summary["source_records"]
    }
    source_residual_ledger: list[dict[str, Any]] = []
    for record in family["source_records"]:
        label = str(record["label"])
        fgmres = record["fgmres"]
        checkpoints: list[dict[str, Any]] = []
        for checkpoint in fgmres["checkpoint_history"]:
            checkpoints.append(
                {
                    field: checkpoint[field]
                    for field in (
                        "iteration",
                        "checkpoint_kind",
                        "interface_true_residual_norm",
                        "interface_true_residual_relative",
                        "full_true_residual_norm",
                        "full_true_residual_relative",
                        "full_residual_tolerance",
                        "finite",
                        "accepted_full_solution",
                    )
                    if field in checkpoint
                }
            )
        semantic_record = semantic_by_label[label]
        source_residual_ledger.append(
            {
                "label": label,
                "full_residual_gate_pass": semantic_record[
                    "full_residual_gate_pass"
                ],
                "best_full_true_residual_relative": semantic_record[
                    "best_full_true_residual_relative"
                ],
                "packetization_gate_pass": semantic_record[
                    "packetization_gate_pass"
                ],
                "packetization_gate_error": fgmres.get(
                    "packetization_gate_error"
                ),
                "accepted_solution_present": fgmres[
                    "accepted_solution_present"
                ],
                "accepted_solution_consumed": semantic_record[
                    "accepted_solution_consumed"
                ],
                "checkpoints": checkpoints,
            }
        )
    packet_aggregate_refs: dict[str, dict[str, Any]] = {}
    packet_aggregate = exact_result.get("packet_aggregate", {})
    if isinstance(packet_aggregate, Mapping):
        for label, aggregate in packet_aggregate.items():
            if isinstance(aggregate, Mapping):
                packet_aggregate_refs[str(label)] = {
                    field: aggregate[field]
                    for field in (
                        "path",
                        "sha256",
                        "mpi_size",
                        "rank_count",
                        "role_count_per_rank",
                        "frozen_rhs_descriptor_metadata_binding_sha256",
                    )
                    if field in aggregate
                }
    identity_chain = exact_result.get("authority_identity_chain", {})
    public_identity_chain = {}
    if isinstance(identity_chain, Mapping):
        for field in (
            "frozen_rhs_source_provenance",
            "qualification_source_provenance",
        ):
            if field in identity_chain:
                public_identity_chain[field] = identity_chain[field]
    return {
        "executed": True,
        "status": exact_result["status"],
        "classification": exact_result["classification"],
        "family_status": family["status"],
        "family_classification": family["classification"],
        "initial_pair_gate_pass": bool(family["initial_pair_gate_pass"]),
        "all_sources_gate_pass": bool(family["all_sources_gate_pass"]),
        "initial_pair_publication": initial_pair_publication,
        "packet_aggregate_gate_pass": bool(
            exact_result.get("packet_aggregate_gate_pass", False)
        ),
        "numerical_negative": not bool(semantic_summary["all_sources_gate_pass"]),
        "source_residual_ledger": source_residual_ledger,
        "packet_aggregate_refs": packet_aggregate_refs,
        "authority_identity_chain": public_identity_chain,
    }


def _exact_output_vectors_loaded_count(exact_result: Mapping[str, Any]) -> int:
    """Count accepted exact outputs from the reopened source records.

    A source contributes only after its full residual Gate and packet consumer
    both report a consumed accepted solution.  The packet files themselves are
    checked separately; this helper is intentionally a compact ledger check.
    """

    family = exact_result.get("family")
    if not isinstance(family, Mapping):
        raise ValueError("exact detail family is missing while counting outputs")
    records = family.get("source_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("exact detail source records are missing while counting outputs")
    count = 0
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("exact detail source record is invalid while counting outputs")
        fgmres = record.get("fgmres")
        if not isinstance(fgmres, Mapping):
            raise ValueError("exact detail FGMRES record is missing while counting outputs")
        consumed = fgmres.get("accepted_solution_consumed")
        if not isinstance(consumed, bool):
            raise ValueError("exact detail accepted-solution flag is invalid while counting outputs")
        if consumed:
            if record.get("full_residual_gate_pass") is not True:
                raise ValueError("exact output was consumed without a residual Gate")
            if record.get("packetization_gate_pass") is not True:
                raise ValueError("exact output was consumed without packetization")
            count += 1
    return count


def _check_exact_detail_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
    rank_artifacts: Sequence[Mapping[str, Any]],
    read_files: list[dict[str, str]],
) -> dict[str, Any]:
    """Reopen and independently validate all rank exact-detail artifacts."""

    details: list[dict[str, Any]] = []
    expected_by_rank: dict[int, dict[str, Mapping[str, Any]]] = {}
    frozen_descriptor_hashes_by_rank: dict[int, Mapping[str, str]] = {}
    exact_output_vectors_loaded_by_rank: dict[int, int] = {}
    aggregate_refs_by_label: dict[str, Mapping[str, Any]] = {}
    qualification_provenance: Mapping[str, Any] | None = None
    frozen_source_provenance: Mapping[str, Any] | None = None
    errors: list[str] = []
    descriptor_refs = manifest.get("exact_qualification_artifacts")
    if not isinstance(descriptor_refs, Sequence) or isinstance(
        descriptor_refs, (str, bytes)
    ) or len(descriptor_refs) != EXPECTED_MPI_SIZE:
        errors.append("root exact_qualification_artifacts is incomplete")
        descriptor_refs = ()
    for expected_rank, artifact_descriptor in enumerate(rank_artifacts):
        reference = artifact_descriptor.get("exact_qualification_artifact")
        if not isinstance(reference, Mapping):
            errors.append(f"rank {expected_rank} lacks exact detail reference")
            continue
        path_value = reference.get("path")
        expected_sha = reference.get("sha256")
        try:
            path = _resolve_artifact_path(root, path_value, "exact detail path")
        except Exception as exc:
            errors.append(f"rank {expected_rank} exact detail path: {exc}")
            continue
        if not _is_hex(expected_sha) or not path.is_file():
            errors.append(f"rank {expected_rank} exact detail file is missing or unhashed")
            continue
        actual_sha = _sha256(path)
        read_files.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": actual_sha,
                "kind": "exact_detail",
            }
        )
        if actual_sha != expected_sha:
            errors.append(f"rank {expected_rank} exact detail hash differs")
            continue
        try:
            payload, _payload_sha = _read_json(path)
            if (
                payload.get("schema")
                != "task040.v6_2.exact_qualification_rank_artifact.v1"
                or payload.get("rank") != expected_rank
                or payload.get("mpi_size") != EXPECTED_MPI_SIZE
                or payload.get("qualification_source_sha")
                != manifest.get("source_sha")
                or payload.get("bare_f_operator_hash")
                != manifest.get("bare_f_operator_hash")
            ):
                raise ValueError("exact detail root identity differs")
            exact_result = payload.get("exact_result")
            if not isinstance(exact_result, Mapping):
                raise ValueError("exact detail exact_result is missing")
            current_provenance = exact_result.get(
                "qualification_source_provenance"
            )
            frozen_provenance = exact_result.get("frozen_rhs_source_provenance")
            if not _valid_provenance(current_provenance) or not _valid_provenance(
                frozen_provenance
            ):
                raise ValueError("exact detail frozen/current provenance is incomplete")
            if any(
                current_provenance[field] != frozen_provenance[field]
                for field in _PROVENANCE_FIELDS
                if field != "source_sha"
            ):
                raise ValueError(
                    "exact detail frozen/current shared provenance differs"
                )
            if frozen_provenance["source_sha"] != EXPECTED_FROZEN_RHS_SOURCE_SHA:
                raise ValueError("exact detail frozen source is not the V5 authority")
            if (
                current_provenance["source_sha"] != manifest.get("source_sha")
                or current_provenance["input_sha256"]
                != manifest.get("input_sha256")
                or current_provenance["physical_model_sha256"]
                != manifest.get("physical_model_sha256")
                or frozen_provenance["input_sha256"]
                != manifest.get("input_sha256")
                or frozen_provenance["physical_model_sha256"]
                != manifest.get("physical_model_sha256")
            ):
                raise ValueError("exact detail provenance does not bind to root")
            identity_chain = exact_result.get("authority_identity_chain")
            if not isinstance(identity_chain, Mapping) or any(
                identity_chain.get(field) != exact_result.get(field)
                for field in (
                    "frozen_rhs_source_provenance",
                    "qualification_source_provenance",
                )
            ):
                raise ValueError("exact detail authority identity chain differs")
            if identity_chain.get("frozen_rhs_descriptor_metadata_sha256") != (
                exact_result.get("frozen_rhs_descriptor_metadata_sha256")
            ):
                raise ValueError("exact detail descriptor chain is not bound")
            if payload.get("frozen_rhs_source_provenance") != frozen_provenance:
                raise ValueError("exact detail payload frozen provenance differs")
            if payload.get("qualification_source_provenance") != current_provenance:
                raise ValueError("exact detail payload qualification provenance differs")
            if payload.get("qualification_source_sha") != current_provenance.get(
                "source_sha"
            ) or payload.get("frozen_rhs_source_sha") != frozen_provenance.get(
                "source_sha"
            ):
                raise ValueError("exact detail payload source chain differs")
            if payload.get("formal_sequence_start_scope") != artifact_descriptor.get(
                "formal_sequence_start_scope"
            ):
                raise ValueError("exact detail formal scope differs")
            if reference.get("formal_sequence_start_scope") != artifact_descriptor.get(
                "formal_sequence_start_scope"
            ):
                raise ValueError("exact detail reference formal scope differs")
            if (
                payload.get("formal_sequence_start_scope")
                != EXPECTED_FORMAL_SEQUENCE_START_SCOPE
                or artifact_descriptor.get("formal_sequence_start_scope")
                != EXPECTED_FORMAL_SEQUENCE_START_SCOPE
                or reference.get("formal_sequence_start_scope")
                != EXPECTED_FORMAL_SEQUENCE_START_SCOPE
            ):
                raise ValueError("exact detail formal scope is not the authority scope")
            if "frozen_rhs_descriptor_metadata_binding_sha256" in payload and not _is_hex(
                payload.get("frozen_rhs_descriptor_metadata_binding_sha256")
            ):
                raise ValueError("exact detail descriptor binding is not a digest")
            expected_gamma_local_count = artifact_descriptor.get(
                "canonical_mapping_count"
            )
            if (
                not isinstance(expected_gamma_local_count, int)
                or isinstance(expected_gamma_local_count, bool)
                or expected_gamma_local_count < 0
            ):
                raise ValueError(
                    f"rank {expected_rank} exact detail Gamma mapping count is invalid"
                )
            semantic, expected_identities = _exact_detail_semantic_signature(
                exact_result,
                expected_bare_f_operator_hash=manifest.get("bare_f_operator_hash"),
                expected_rank=expected_rank,
                expected_mpi_size=EXPECTED_MPI_SIZE,
                expected_gamma_local_count=expected_gamma_local_count,
                require_adapter=True,
            )
            exact_output_vectors_loaded_by_rank[expected_rank] = (
                _exact_output_vectors_loaded_count(exact_result)
            )
            compact = _recomputed_exact_compact_summary(
                exact_result,
                semantic,
                root=root,
            )
            descriptor_hashes = payload.get("frozen_rhs_descriptor_metadata_sha256")
            result_hashes = exact_result.get("frozen_rhs_descriptor_metadata_sha256")
            if descriptor_hashes != result_hashes:
                raise ValueError("exact detail descriptor-hash chain differs")
            if not isinstance(descriptor_hashes, Mapping) or set(
                str(label) for label in descriptor_hashes
            ) != set(_EXACT_SOURCE_ORDER) or len(descriptor_hashes) != len(
                _EXACT_SOURCE_ORDER
            ) or any(
                not _is_hex(value) for value in descriptor_hashes.values()
            ):
                raise ValueError("exact detail descriptor-hash map is invalid")
            frozen_descriptor_hashes_by_rank[expected_rank] = dict(
                descriptor_hashes
            )
            if identity_chain.get("frozen_rhs_descriptor_metadata_sha256") != descriptor_hashes:
                raise ValueError("exact detail descriptor map is not in authority chain")
            if reference.get("frozen_rhs_descriptor_metadata_sha256") != descriptor_hashes:
                raise ValueError("exact detail reference descriptor map differs")
            if payload.get("qualification_source_provenance") != exact_result.get(
                "qualification_source_provenance"
            ):
                raise ValueError("exact detail qualification provenance differs")
            if qualification_provenance is None:
                qualification_provenance = current_provenance
            elif qualification_provenance != current_provenance:
                raise ValueError(
                    "exact detail qualification provenance differs across ranks"
                )
            if frozen_source_provenance is None:
                frozen_source_provenance = frozen_provenance
            elif frozen_source_provenance != frozen_provenance:
                raise ValueError(
                    "exact detail frozen source provenance differs across ranks"
                )
            family = exact_result.get("family")
            if not isinstance(family, Mapping):
                raise ValueError("exact detail family is missing")
            all_sources_pass = bool(family.get("all_sources_gate_pass"))
            aggregate_gate = exact_result.get("packet_aggregate_gate_pass") is True
            aggregates = exact_result.get("packet_aggregate")
            if not isinstance(aggregates, Mapping):
                raise ValueError("exact detail packet aggregate is not a mapping")
            if all_sources_pass:
                if (
                    not aggregate_gate
                    or set(str(source_label) for source_label in aggregates)
                    != set(_EXACT_SOURCE_ORDER)
                    or len(aggregates) != len(_EXACT_SOURCE_ORDER)
                ):
                    raise ValueError(
                        "packet-ready exact detail lacks the five packet aggregates"
                    )
                for source_label in _EXACT_SOURCE_ORDER:
                    aggregate = aggregates.get(source_label)
                    if not isinstance(aggregate, Mapping):
                        raise ValueError(
                            f"exact detail packet aggregate is missing {source_label}"
                        )
                    previous = aggregate_refs_by_label.get(source_label)
                    if previous is None:
                        aggregate_refs_by_label[source_label] = aggregate
                    elif _json_signature(previous) != _json_signature(aggregate):
                        raise ValueError(
                            f"packet aggregate reference differs across ranks for {source_label}"
                        )
            elif aggregate_gate or aggregates:
                raise ValueError(
                    "numerical-negative exact detail contains packet aggregates"
                )
            if artifact_descriptor.get("exact_qualification") != compact:
                errors.append(
                    f"rank {expected_rank} compact exact summary differs from detail"
                )
            details.append(compact)
            expected_by_rank[expected_rank] = expected_identities
        except Exception as exc:
            errors.append(f"rank {expected_rank} exact detail: {type(exc).__name__}: {exc}")

        if expected_rank < len(descriptor_refs):
            if descriptor_refs[expected_rank] != reference:
                errors.append(f"rank {expected_rank} exact detail root reference differs")
        if isinstance(reference, Mapping):
            if reference.get("rank") != expected_rank:
                errors.append(f"rank {expected_rank} exact detail descriptor rank differs")
            if reference.get("mpi_size") != EXPECTED_MPI_SIZE:
                errors.append(f"rank {expected_rank} exact detail descriptor mpi size differs")
            if reference.get("qualification_source_sha") != manifest.get("source_sha"):
                errors.append(f"rank {expected_rank} exact detail current source differs")
            if reference.get("frozen_rhs_source_sha") != EXPECTED_FROZEN_RHS_SOURCE_SHA:
                errors.append(f"rank {expected_rank} exact detail frozen source differs")

    if len(details) == EXPECTED_MPI_SIZE:
        signatures = {_json_signature(item) for item in details}
        if len(signatures) != 1:
            errors.append("exact detail semantic observations differ across ranks")
    root_chain = manifest.get("exact_qualification_artifact_chain_sha256")
    if descriptor_refs:
        computed_chain = hashlib.sha256(
            json.dumps(
                list(descriptor_refs), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if root_chain != computed_chain:
            errors.append("root exact detail artifact chain hash differs")
    summary = details[0] if details and not errors else None
    if summary is not None:
        root_exact = manifest.get("exact_qualification")
        root_summary = root_exact.get("summary") if isinstance(root_exact, Mapping) else None
        if root_summary != summary:
            errors.append("root exact compact summary does not match rank detail")
        if not isinstance(root_exact, Mapping):
            errors.append("root exact rank consensus wrapper is missing")
        elif (
            root_exact.get("rank_consensus") is not True
            or root_exact.get("by_rank") is not None
        ):
            errors.append("root exact rank consensus wrapper is inconsistent")
    return {
        "valid": not errors and len(details) == EXPECTED_MPI_SIZE,
        "errors": errors,
        "summary": summary,
        "expected_identities_by_rank": expected_by_rank,
        "frozen_descriptor_hashes_by_rank": frozen_descriptor_hashes_by_rank,
        "exact_output_vectors_loaded_by_rank": exact_output_vectors_loaded_by_rank,
        "aggregate_refs_by_label": aggregate_refs_by_label,
        "qualification_provenance": qualification_provenance,
        "frozen_source_provenance": frozen_source_provenance,
    }


def _operator_audit_check(
    root: Path,
    manifest: Mapping[str, Any],
    read_files: list[dict[str, str]],
) -> bool:
    descriptor = manifest.get("operator_semantics_audit")
    if not isinstance(descriptor, Mapping):
        return False
    relative = descriptor.get("path")
    expected_sha = descriptor.get("sha256")
    if not isinstance(relative, str) or not _is_hex(expected_sha):
        return False
    path = (root / relative).resolve()
    if not _inside(path, root) or path.suffix != ".json" or not path.is_file():
        return False
    actual_sha = _sha256(path)
    read_files.append({"path": str(path.relative_to(root)), "sha256": actual_sha})
    if actual_sha != expected_sha:
        return False
    try:
        audit, _audit_sha = _read_json(path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    if audit.get("schema") != "task040.v5.operator_semantics_audit.v1":
        return False
    if audit.get("source_sha") != manifest.get("source_sha"):
        return False
    recorded_content_sha = audit.get("record_sha256")
    if not _is_hex(recorded_content_sha):
        return False
    content_record = dict(audit)
    content_record.pop("record_sha256", None)
    computed_content_sha = hashlib.sha256(
        json.dumps(content_record, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    if recorded_content_sha != computed_content_sha:
        return False
    descriptor_content_sha = descriptor.get("content_sha256")
    if not _is_hex(descriptor_content_sha) or descriptor_content_sha != recorded_content_sha:
        return False
    explicit_pass = audit.get("pass")
    if explicit_pass is False:
        return False
    if explicit_pass is not None and explicit_pass is not True:
        return False
    checks = audit.get("checks")
    if checks is not None and not _all_true(checks):
        return False
    modal_identity = audit.get("modal_source_identity")
    if not isinstance(modal_identity, Mapping) or modal_identity.get("pass") is not True:
        return False
    current_authority = audit.get("current_authority")
    if not isinstance(current_authority, Mapping):
        return False
    if current_authority.get("static_path_identity") is not True:
        return False
    if current_authority.get("operator") != "explicit_current_bare_F":
        return False
    if current_authority.get("factor") != "ResearchExactFactorInverse(F)":
        return False
    c_d_h = current_authority.get("C_D_H_constructed")
    if (
        not isinstance(c_d_h, Mapping)
        or set(c_d_h) != {"C", "D", "H"}
        or any(value != 0 for value in c_d_h.values())
    ):
        return False
    if current_authority.get("qep_calls") != 0:
        return False
    for field in (
        "top_system_constructed",
        "full_coupling_constructed",
        "woodbury_inverse",
        "physical_dtn_operator",
    ):
        if current_authority.get(field) is not False:
            return False
    repair = modal_identity.get("repair")
    if not isinstance(repair, Mapping):
        return False
    if (
        repair.get("qep_calls") != 0
        or repair.get("top_system_constructed") is not False
        or repair.get("full_coupling_constructed") is not False
        or repair.get("scalar_cg_substitution") is not False
    ):
        return False
    return True


def _vector_gate_checks(manifest: Mapping[str, Any]) -> dict[str, bool]:
    deterministic = manifest.get("deterministic_vectors")
    if not isinstance(deterministic, Sequence) or isinstance(deterministic, (str, bytes)):
        return {"three_deterministic_vectors": False}
    checks = {"three_deterministic_vectors": len(deterministic) == 3}
    max_repeat = 0.0
    max_roundtrip = 0.0
    max_action = 0.0
    max_interior = 0.0
    solve_counts: list[int] = []
    vector_indexes: list[int] = []
    solve_count_values_valid = True
    for item in deterministic:
        if not isinstance(item, Mapping):
            checks["vector_records_well_formed"] = False
            continue
        required = (
            "vector_index",
            "gamma_action_error",
            "full_interior_residual_error",
            "solve_count",
            "roundtrip_error",
            "repeat_error",
        )
        if not all(key in item for key in required):
            checks["vector_records_well_formed"] = False
            continue
        vector_index = item["vector_index"]
        if not isinstance(vector_index, int) or isinstance(vector_index, bool):
            checks["vector_indexes_well_formed"] = False
        else:
            vector_indexes.append(vector_index)
        solve_count = item["solve_count"]
        if not isinstance(solve_count, int) or isinstance(solve_count, bool):
            solve_count_values_valid = False
        else:
            solve_counts.append(solve_count)
        numeric = [item[key] for key in required if key not in {"solve_count", "vector_index"}]
        if not all(_finite(value) and float(value) >= 0.0 for value in numeric):
            checks["vector_records_finite"] = False
            continue
        max_repeat = max(max_repeat, float(item["repeat_error"]))
        max_roundtrip = max(max_roundtrip, float(item["roundtrip_error"]))
        max_action = max(max_action, float(item["gamma_action_error"]))
        max_interior = max(max_interior, float(item["full_interior_residual_error"]))
    checks.update(
        {
            "vector_records_well_formed": checks.get("vector_records_well_formed", True),
            "vector_records_finite": checks.get("vector_records_finite", True),
            "vector_indexes_0_1_2": sorted(vector_indexes) == [0, 1, 2]
            and len(vector_indexes) == len(set(vector_indexes)),
            "solve_count_values_valid": solve_count_values_valid,
            "solve_count_three_each": solve_count_values_valid
            and solve_counts == [3, 3, 3],
            "repeat_le_1e-11": max_repeat <= ROUNDTRIP_TOLERANCE,
            "roundtrip_le_1e-11": max_roundtrip <= ROUNDTRIP_TOLERANCE,
            "gamma_action_le_1e-10": max_action <= ACTION_TOLERANCE,
            "interior_residual_le_1e-10": max_interior <= ACTION_TOLERANCE,
            "zero_map_le_1e-13": _finite(manifest.get("zero_error"))
            and float(manifest["zero_error"]) <= ZERO_TOLERANCE,
            "linearity_le_1e-11": _finite(manifest.get("linearity_error"))
            and float(manifest["linearity_error"]) <= ROUNDTRIP_TOLERANCE,
        }
    )
    return checks


def _recomputed_identity_gate_fields(value: Mapping[str, Any]) -> dict[str, bool]:
    """Recompute identity flags that have an observable raw counterpart.

    The identity map is an assertion about observations, not an authority
    source by itself.  Some older rank artifacts do not expose every
    component (for example a separate restriction error), so a component is
    returned only when the corresponding raw observation is present.  A
    present identity flag is nevertheless always checked against the value
    returned here.
    """

    computed: dict[str, bool] = {}
    zero_error = value.get("zero_error")
    if _finite(zero_error):
        computed["zero_map"] = float(zero_error) >= 0.0 and float(
            zero_error
        ) <= ZERO_TOLERANCE
    linearity_error = value.get("linearity_error")
    if _finite(linearity_error):
        computed["linearity"] = float(linearity_error) >= 0.0 and float(
            linearity_error
        ) <= ROUNDTRIP_TOLERANCE

    deterministic = value.get("deterministic_vectors")
    if isinstance(deterministic, Sequence) and not isinstance(
        deterministic, (str, bytes)
    ):
        computed["three_deterministic_vectors"] = len(deterministic) == 3
        valid_vectors = [item for item in deterministic if isinstance(item, Mapping)]
        if len(valid_vectors) == len(deterministic):
            finite_vector_values = all(
                _finite(item.get(field)) and float(item[field]) >= 0.0
                for item in valid_vectors
                for field in (
                    "gamma_action_error",
                    "full_interior_residual_error",
                    "roundtrip_error",
                    "repeat_error",
                )
            )
            computed["repeat"] = finite_vector_values and all(
                float(item["repeat_error"]) <= ROUNDTRIP_TOLERANCE
                for item in valid_vectors
            )
            computed["full_elimination_gamma"] = finite_vector_values and all(
                float(item["gamma_action_error"]) <= ACTION_TOLERANCE
                for item in valid_vectors
            )
            computed["full_elimination_interior"] = finite_vector_values and all(
                float(item["full_interior_residual_error"])
                <= ACTION_TOLERANCE
                for item in valid_vectors
            )
            computed["restriction_prolongation"] = finite_vector_values and all(
                float(item["roundtrip_error"]) <= ROUNDTRIP_TOLERANCE
                for item in valid_vectors
            )
            computed["group_solve_count"] = all(
                isinstance(item.get("solve_count"), int)
                and not isinstance(item.get("solve_count"), bool)
                and item["solve_count"] == 3
                for item in valid_vectors
            )

    layout = value.get("canonical_interface_layout")
    if isinstance(layout, Mapping):
        if "global_size" in layout:
            computed["joint_size"] = layout.get("global_size") == EXPECTED_JOINT_COUNT
        for identity_name, raw_name in (
            ("layout_coverage_exact", "coverage_exact"),
            ("layout_owner_distributed", "owner_distributed"),
            ("layout_position_bijection", "canonical_position_bijection"),
        ):
            if raw_name in layout:
                computed[identity_name] = layout.get(raw_name) is True
        if "canonical_order" in layout:
            computed["layout_canonical_l_then_u"] = (
                layout.get("canonical_order")
                == "Gamma_L_then_Gamma_U_by_physical_key"
            )
        if "lower_global_rows" in layout and "upper_global_rows" in layout:
            computed["layout_counts_7560_plus_7560"] = (
                layout.get("lower_global_rows") == EXPECTED_LOWER_COUNT
                and layout.get("upper_global_rows") == EXPECTED_UPPER_COUNT
                and layout.get("global_size") == EXPECTED_JOINT_COUNT
            )

    if value.get("numeric_allgather") is False:
        computed["numeric_allgather"] = True
    elif "numeric_allgather" in value:
        computed["numeric_allgather"] = False
    if value.get("full_interface_numeric_replica") is False:
        computed["full_interface_replica"] = True
    elif "full_interface_numeric_replica" in value:
        computed["full_interface_replica"] = False

    lifecycle = value.get("factor_lifecycle_after")
    if not isinstance(lifecycle, Mapping):
        lifecycle_container = value.get("factor_lifecycle")
        if isinstance(lifecycle_container, Mapping):
            after_by_rank = lifecycle_container.get("after_by_rank")
            if isinstance(after_by_rank, Sequence) and not isinstance(
                after_by_rank, (str, bytes)
            ) and after_by_rank and all(
                isinstance(item, Mapping) for item in after_by_rank
            ):
                lifecycle = after_by_rank[0]
    if isinstance(lifecycle, Mapping):
        if "ready" in lifecycle:
            computed["factor_ready_three_observed"] = lifecycle.get("ready") == 3
        if "simultaneous_max" in lifecycle:
            computed["factor_simultaneous_max_three_observed"] = (
                lifecycle.get("simultaneous_max") == 3
            )
        if "after_cleanup" in lifecycle:
            computed["factor_after_cleanup_zero_observed"] = (
                lifecycle.get("after_cleanup") == 0
            )
        if "action_destroyed" in lifecycle:
            computed["factor_action_destroyed"] = (
                lifecycle.get("action_destroyed") is True
            )

    return computed


def _identity_gate_matches_observations(value: Mapping[str, Any]) -> bool:
    identity_gate = value.get("identity_gate")
    if not isinstance(identity_gate, Mapping):
        return False
    computed = _recomputed_identity_gate_fields(value)
    return bool(computed) and all(
        name in identity_gate and identity_gate.get(name) is observed
        for name, observed in computed.items()
    )


def _json_signature(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _rank_gate_checks(
    rank_artifacts: Sequence[Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    checks: dict[str, bool] = {
        "rank_artifacts_complete": len(rank_artifacts) == EXPECTED_MPI_SIZE,
        "rank_artifacts_are_mappings": all(
            isinstance(artifact, Mapping) for artifact in rank_artifacts
        ),
        "rank_artifact_schema": True,
        "rank_identity_pass": True,
        "rank_resource_pass": True,
        "rank_system_forbidden_zero": True,
        "rank_no_numeric_allgather": True,
        "rank_no_full_replica": True,
        "rank_mapping_matches_layout": True,
        "rank_mapping_count_observed": True,
        "rank_mpi_size": True,
        "rank_factor_lifecycle": True,
        "rank_factor_lifecycle_observed": True,
        "rank_factor_lifecycle_consistent": True,
        "rank_deterministic_scalars_consistent": True,
        "rank_zero_linearity_consistent": True,
        "rank_identity_gate_consistent": True,
        "rank_identity_gate_raw_consistent": True,
        "rank_provenance_consistent": True,
        "rank_formal_sequence_scope_consistent": True,
        "rank_mapping_count_sum": False,
    }
    ranks: list[int] = []
    operator_hashes: list[str] = []
    mapping_hashes: list[str] = []
    mapping_counts: list[int] = []
    deterministic_signatures: list[str] = []
    identity_signatures: list[str] = []
    zero_values: list[float] = []
    linearity_values: list[float] = []
    lifecycle_by_rank: dict[int, Any] = {}
    formal_scopes: list[str] = []
    for artifact in rank_artifacts:
        if not isinstance(artifact, Mapping):
            checks["rank_artifact_schema"] = False
            continue
        ranks.append(int(artifact.get("rank", -1)))
        checks["rank_artifact_schema"] &= artifact.get("schema") == EXPECTED_RANK_SCHEMA
        checks["rank_mpi_size"] = checks.get("rank_mpi_size", True) and (
            artifact.get("mpi_size") == EXPECTED_MPI_SIZE
        )
        checks["rank_identity_pass"] &= artifact.get("identity_preflight", {}).get("pass") is True
        checks["rank_resource_pass"] &= artifact.get("resource_preflight_pass") is True
        checks["rank_system_forbidden_zero"] &= artifact.get("matrix_objects") == {
            "C": 0,
            "D": 0,
            "H": 0,
        }
        checks["rank_system_forbidden_zero"] &= artifact.get("qep_calls") == 0
        checks["rank_no_numeric_allgather"] &= (
            artifact.get("numeric_allgather") is False
            and artifact.get("fe_numeric_allgather") is False
        )
        checks["rank_no_full_replica"] &= artifact.get("full_interface_numeric_replica") is False
        layout = artifact.get("canonical_interface_layout", {})
        checks["rank_mapping_matches_layout"] &= (
            layout.get("owner_local_mapping_count") == artifact.get("canonical_mapping_count")
        )
        mapping_count = artifact.get("canonical_mapping_count")
        if isinstance(mapping_count, int) and not isinstance(mapping_count, bool):
            mapping_counts.append(mapping_count)
        else:
            checks["rank_mapping_count_observed"] = False
            checks["rank_mapping_matches_layout"] = False
        deterministic = artifact.get("deterministic_vectors")
        if isinstance(deterministic, Sequence) and not isinstance(
            deterministic, (str, bytes)
        ):
            deterministic_signatures.append(_json_signature(deterministic))
        else:
            checks["rank_deterministic_scalars_consistent"] = False
        if _finite(artifact.get("zero_error")) and _finite(
            artifact.get("linearity_error")
        ):
            zero_values.append(float(artifact["zero_error"]))
            linearity_values.append(float(artifact["linearity_error"]))
        else:
            checks["rank_zero_linearity_consistent"] = False
        identity_gate = artifact.get("identity_gate")
        if isinstance(identity_gate, Mapping):
            identity_signatures.append(_json_signature(identity_gate))
            checks["rank_identity_gate_raw_consistent"] &= (
                _identity_gate_matches_observations(artifact)
            )
            if "gate_pass" in artifact:
                checks["rank_identity_gate_raw_consistent"] &= (
                    artifact.get("gate_pass") is _all_true(identity_gate)
                )
            if "classification" in artifact:
                expected_classification = (
                    "V6_2_FULL_INTERFACE_SCHUR_PASS"
                    if _all_true(identity_gate)
                    else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
                )
                checks["rank_identity_gate_raw_consistent"] &= (
                    artifact.get("classification") == expected_classification
                )
        else:
            checks["rank_identity_gate_consistent"] = False
            checks["rank_identity_gate_raw_consistent"] = False
        after = artifact.get("factor_lifecycle_after", {})
        lifecycle_observed = isinstance(after, Mapping) and all(
            key in after
            and isinstance(after[key], int)
            and not isinstance(after[key], bool)
            for key in ("ready", "after_cleanup", "simultaneous_max")
        )
        checks["rank_factor_lifecycle_observed"] &= lifecycle_observed
        if lifecycle_observed:
            lifecycle_by_rank[int(artifact["rank"])] = after
        checks["rank_factor_lifecycle"] &= (
            lifecycle_observed
            and after.get("ready") == 3
            and after.get("after_cleanup") == 0
            and after.get("simultaneous_max") == 3
        )
        operator_hash = artifact.get("bare_f_operator_hash")
        if _is_hex(operator_hash):
            operator_hashes.append(operator_hash)
        mapping_hash = artifact.get("canonical_mapping_sha256")
        if _is_hex(mapping_hash):
            mapping_hashes.append(mapping_hash)
        checks["rank_provenance_consistent"] &= (
            artifact.get("source_sha") == manifest.get("source_sha")
            and artifact.get("input_sha256") == manifest.get("input_sha256")
            and artifact.get("physical_model_sha256")
            == manifest.get("physical_model_sha256")
        )
        formal_scope = artifact.get("formal_sequence_start_scope")
        if isinstance(formal_scope, str) and formal_scope:
            formal_scopes.append(formal_scope)
    checks["ranks_exactly_0_to_7"] = sorted(ranks) == list(range(EXPECTED_MPI_SIZE))
    checks["operator_hashes_present_and_equal"] = (
        len(operator_hashes) == EXPECTED_MPI_SIZE
        and len(set(operator_hashes)) == 1
        and operator_hashes[0] == manifest.get("bare_f_operator_hash")
    )
    checks["mapping_hashes_present"] = len(mapping_hashes) == EXPECTED_MPI_SIZE
    checks["rank_mapping_count_sum"] = (
        len(mapping_counts) == EXPECTED_MPI_SIZE
        and sum(mapping_counts) == EXPECTED_JOINT_COUNT
    )
    checks["rank_mapping_count_observed"] &= len(mapping_counts) == EXPECTED_MPI_SIZE
    manifest_after_by_rank = manifest.get("factor_lifecycle", {}).get(
        "after_by_rank"
    )
    checks["rank_factor_lifecycle_consistent"] = (
        isinstance(manifest_after_by_rank, Sequence)
        and not isinstance(manifest_after_by_rank, (str, bytes))
        and len(manifest_after_by_rank) == EXPECTED_MPI_SIZE
        and sorted(lifecycle_by_rank) == list(range(EXPECTED_MPI_SIZE))
        and all(
            _json_signature(manifest_after_by_rank[rank])
            == _json_signature(lifecycle_by_rank[rank])
            for rank in range(EXPECTED_MPI_SIZE)
        )
    )
    checks["rank_deterministic_scalars_consistent"] &= (
        len(deterministic_signatures) == EXPECTED_MPI_SIZE
        and len(set(deterministic_signatures)) == 1
        and deterministic_signatures[0]
        == _json_signature(manifest.get("deterministic_vectors"))
    )
    checks["rank_zero_linearity_consistent"] &= (
        len(zero_values) == EXPECTED_MPI_SIZE
        and len(linearity_values) == EXPECTED_MPI_SIZE
        and len(set(zero_values)) == 1
        and len(set(linearity_values)) == 1
        and zero_values[0] == manifest.get("zero_error")
        and linearity_values[0] == manifest.get("linearity_error")
    )
    checks["rank_identity_gate_consistent"] &= (
        len(identity_signatures) == EXPECTED_MPI_SIZE
        and len(set(identity_signatures)) == 1
        and identity_signatures[0] == _json_signature(manifest.get("identity_gate"))
    )
    exact_refs = manifest.get("exact_qualification_artifacts")
    exact_ref_claims_execution = bool(
        isinstance(exact_refs, Sequence)
        and not isinstance(exact_refs, (str, bytes))
        and any(isinstance(reference, Mapping) for reference in exact_refs)
    )
    execution_requires_scope = bool(
        exact_ref_claims_execution
        or manifest.get("pde_solve")
        == "exact_interface_fgmres_with_full_bare_f_residual_run"
        or (
            isinstance(manifest.get("exact_qualification_plan"), Mapping)
            and manifest["exact_qualification_plan"].get("status")
            == "configured_same_process_exact"
            and manifest["exact_qualification_plan"].get("identity_only") is False
        )
    )
    if execution_requires_scope:
        checks["rank_formal_sequence_scope_consistent"] = (
            len(formal_scopes) == EXPECTED_MPI_SIZE
            and len(set(formal_scopes)) == 1
            and formal_scopes[0] == manifest.get("formal_sequence_start_scope")
        )
    checks["rank_identity_gate_all_true"] = bool(
        rank_artifacts
        and all(
            isinstance(artifact, Mapping)
            and isinstance(artifact.get("identity_gate"), Mapping)
            and _all_true(artifact["identity_gate"])
            for artifact in rank_artifacts
        )
    )
    checks["rank_scalar_records_finite"] = bool(
        len(zero_values) == EXPECTED_MPI_SIZE
        and len(linearity_values) == EXPECTED_MPI_SIZE
    )
    checks["rank_mapping_sum_is_joint_size"] = checks["rank_mapping_count_sum"]
    checks["rank_artifacts_are_mappings"] &= len(
        [artifact for artifact in rank_artifacts if isinstance(artifact, Mapping)]
    ) == EXPECTED_MPI_SIZE
    return checks


def check_v6_2_interface_schur(
    *,
    formal_root: str | Path,
    formal_source_sha: str,
    checker_source_sha: str,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute V6-2 evidence from JSON and bounded mmap packet artifacts."""

    root = Path(formal_root).resolve()
    output_path = None if output is None else Path(output).resolve()
    if output_path is not None and _inside(output_path, root):
        raise ValueError("checker output must be outside the formal root")
    read_files: list[dict[str, str]] = []
    evidence: dict[str, bool] = {}
    gate: dict[str, bool] = {}
    manifest_path = root / "v6_2_manifest.json"
    if not root.is_dir() or not manifest_path.is_file():
        raise FileNotFoundError(f"V6-2 manifest is missing: {manifest_path}")
    manifest, manifest_sha = _read_json(manifest_path)
    read_files.append({"path": str(manifest_path.relative_to(root)), "sha256": manifest_sha})
    watchdog_audit = _check_watchdog_audit(root, manifest, read_files)
    evidence["watchdog_audit"] = bool(watchdog_audit["valid"])

    # Only a real rank-detail reference selects the executed path.  The
    # runner deliberately writes ``[None] * mpi_size`` when identity fails
    # before exact qualification; that is not an executed exact claim.  A
    # non-empty/partial reference list, however, is an executed claim and is
    # checked as malformed if the eight details cannot be reopened.
    exact_artifact_refs = manifest.get("exact_qualification_artifacts")
    exact_refs_malformed = False
    if exact_artifact_refs is not None:
        exact_refs_malformed = not (
            isinstance(exact_artifact_refs, Sequence)
            and not isinstance(exact_artifact_refs, (str, bytes))
            and len(exact_artifact_refs) == EXPECTED_MPI_SIZE
            and all(
                reference is None or isinstance(reference, Mapping)
                for reference in exact_artifact_refs
            )
        )
    exact_refs_have_mapping = (
        isinstance(exact_artifact_refs, Sequence)
        and not isinstance(exact_artifact_refs, (str, bytes))
        and any(isinstance(reference, Mapping) for reference in exact_artifact_refs)
    )
    exact_summary = manifest.get("exact_qualification")
    exact_summary_claims_execution = bool(
        isinstance(exact_summary, Mapping)
        and (
            exact_summary.get("executed") is True
            or (
                isinstance(exact_summary.get("summary"), Mapping)
                and exact_summary["summary"].get("executed") is True
            )
        )
    )
    executed_exact_hint = bool(
        exact_refs_have_mapping
        or exact_refs_malformed
        or exact_summary_claims_execution
        or manifest.get("pde_solve")
        == "exact_interface_fgmres_with_full_bare_f_residual_run"
    )
    exact_refs_all_none = bool(
        isinstance(exact_artifact_refs, Sequence)
        and not isinstance(exact_artifact_refs, (str, bytes))
        and len(exact_artifact_refs) == EXPECTED_MPI_SIZE
        and all(reference is None for reference in exact_artifact_refs)
    )
    identity_stop_pde = bool(
        not executed_exact_hint
        and exact_refs_all_none
        and not exact_summary_claims_execution
        and manifest.get("pde_solve") == "not_run_by_v6_2_identity_gate"
    )
    configured_identity_path = bool(
        isinstance(manifest.get("exact_qualification_plan"), Mapping)
        and manifest["exact_qualification_plan"].get("status")
        == "configured_same_process_exact"
        and manifest["exact_qualification_plan"].get("identity_only") is False
        and not executed_exact_hint
    )

    evidence["formal_schema"] = manifest.get("schema") == EXPECTED_FORMAL_SCHEMA
    evidence["source_sha"] = manifest.get("source_sha") == str(formal_source_sha)
    evidence["checker_source_sha_input"] = _is_hex(checker_source_sha, 40)
    evidence["mpi_size"] = manifest.get("mpi_size") == EXPECTED_MPI_SIZE
    evidence["identity_preflight"] = (
        manifest.get("identity_preflight", {}).get("pass") is True
        and _all_true(manifest.get("identity_preflight", {}).get("checks"))
    )
    evidence["resource_preflight"] = (
        manifest.get("resource_preflight", {}).get("pass") is True
        and _all_true(manifest.get("resource_preflight", {}).get("checks"))
    )
    evidence["operator_semantics_audit"] = _operator_audit_check(
        root, manifest, read_files
    )
    evidence["input_hashes_present"] = _is_hex(manifest.get("input_sha256")) and _is_hex(
        manifest.get("physical_model_sha256")
    )
    evidence["system_created"] = manifest.get("system_created") is True
    evidence["matrix_objects_zero"] = manifest.get("matrix_objects") == {
        "C": 0,
        "D": 0,
        "H": 0,
    }
    evidence["qep_zero"] = manifest.get("qep_calls") == 0
    evidence["no_forbidden_factors"] = (
        manifest.get("full_side_exact_factor_count") == 0
        and manifest.get("global_direct_factor_count") == 0
        and (
            executed_exact_hint
            or manifest.get("exact_output_vectors_loaded") == 0
        )
    )
    evidence["pde_execution_contract"] = (
        (
            executed_exact_hint
            and manifest.get("pde_solve")
            == "exact_interface_fgmres_with_full_bare_f_residual_run"
        )
        or (
            not executed_exact_hint
            and not configured_identity_path
            and manifest.get("pde_solve") == "not_run"
        )
        or identity_stop_pde
    )
    evidence["owner_distributed_contract"] = (
        manifest.get("numeric_allgather") is False
        and manifest.get("fe_numeric_allgather") is False
        and manifest.get("full_interface_numeric_replica") is False
        and manifest.get("root_metadata_gather") is True
        and manifest.get("per_rank_full_interface_replica") is False
        and manifest.get("raw_global_row_remap") is False
    )
    evidence["support_metadata_distinction"] = (
        manifest.get("root_metadata_gather") is True
        and manifest.get("support_metadata_replicated") is True
        and manifest.get("per_rank_full_interface_replica") is False
        and manifest.get("numeric_allgather") is False
    )

    layout = manifest.get("canonical_interface_layout", {})
    canonical_layout_gate = (
        layout.get("global_size") == EXPECTED_JOINT_COUNT
        and layout.get("lower_global_rows") == EXPECTED_LOWER_COUNT
        and layout.get("upper_global_rows") == EXPECTED_UPPER_COUNT
        and layout.get("canonical_order") == "Gamma_L_then_Gamma_U_by_physical_key"
        and layout.get("canonical_position_bijection") is True
        and layout.get("coverage_exact") is True
        and layout.get("owner_distributed") is True
        and layout.get("root_metadata_gather") is True
        and layout.get("per_rank_full_interface_replica") is False
        and layout.get("numeric_allgather") is False
        and layout.get("value_basis") == "current_raw_active_coefficients"
        and layout.get("canonical_block_transforms_applied") is False
    )
    evidence["canonical_layout_recorded"] = isinstance(layout, Mapping) and all(
        key in layout
        for key in (
            "global_size",
            "lower_global_rows",
            "upper_global_rows",
            "canonical_order",
            "canonical_position_bijection",
            "coverage_exact",
            "owner_distributed",
            "root_metadata_gather",
            "per_rank_full_interface_replica",
            "numeric_allgather",
            "value_basis",
            "canonical_block_transforms_applied",
        )
    )
    gamma_counts = manifest.get("gamma_counts", {})
    gamma_counts_gate = gamma_counts == {
        "Gamma_L": EXPECTED_LOWER_COUNT,
        "Gamma_U": EXPECTED_UPPER_COUNT,
        "joint": EXPECTED_JOINT_COUNT,
    }
    evidence["gamma_counts_recorded"] = isinstance(gamma_counts, Mapping) and all(
        isinstance(gamma_counts.get(key), int)
        and not isinstance(gamma_counts.get(key), bool)
        for key in ("Gamma_L", "Gamma_U", "joint")
    )

    rank_descriptors = manifest.get("rank_artifacts")
    if not isinstance(rank_descriptors, Sequence) or isinstance(rank_descriptors, (str, bytes)):
        rank_descriptors = []
    rank_artifacts: list[Mapping[str, Any]] = []
    descriptor_paths: set[str] = set()
    descriptor_hashes: list[str] = []
    for descriptor in rank_descriptors:
        if not isinstance(descriptor, Mapping):
            evidence["rank_descriptor_contract"] = False
            continue
        relative = descriptor.get("path")
        expected_sha = descriptor.get("sha256")
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or not _is_hex(expected_sha)
            or relative in descriptor_paths
        ):
            evidence["rank_descriptor_contract"] = False
            continue
        path = (root / relative).resolve()
        if not _inside(path, root) or path.suffix != ".json" or not path.is_file():
            evidence["rank_descriptor_contract"] = False
            continue
        descriptor_paths.add(relative)
        artifact, actual_sha = _read_json(path)
        read_files.append({"path": relative, "sha256": actual_sha})
        descriptor_hashes.append(actual_sha)
        if (
            actual_sha != expected_sha
            or artifact.get("rank") != descriptor.get("rank")
            or artifact.get("canonical_mapping_count")
            != descriptor.get("canonical_mapping_count")
            or artifact.get("canonical_mapping_sha256")
            != descriptor.get("canonical_mapping_sha256")
            or artifact.get("factor_lifecycle_after")
            != descriptor.get("factor_lifecycle_after")
            or artifact.get("formal_sequence_start_scope")
            != descriptor.get("formal_sequence_start_scope")
            or artifact.get("exact_qualification")
            != descriptor.get("exact_qualification")
        ):
            evidence["rank_descriptor_hashes"] = False
        rank_artifacts.append(artifact)
    evidence["rank_descriptor_contract"] = evidence.get("rank_descriptor_contract", True) and len(rank_descriptors) == EXPECTED_MPI_SIZE
    evidence["rank_descriptor_hashes"] = evidence.get("rank_descriptor_hashes", True) and len(descriptor_hashes) == EXPECTED_MPI_SIZE
    if not executed_exact_hint:
        evidence["exact_output_count_contract"] = (
            manifest.get("exact_output_vectors_loaded") == 0
            and all(
                artifact.get("exact_output_vectors_loaded") == 0
                for artifact in rank_artifacts
            )
        )
    npy_read = any(item.get("kind") == "npy" for item in read_files)
    if not executed_exact_hint:
        evidence["no_npy_read"] = not npy_read
    rank_checks = _rank_gate_checks(rank_artifacts, manifest)
    if manifest.get("pde_solve") == "not_run_by_v6_2_identity_gate":
        # This status is valid only for a complete, pre-exact identity stop;
        # it must not turn a missing/partial exact execution claim into a
        # passing evidence record.
        evidence["pde_execution_contract"] = bool(
            identity_stop_pde
            and rank_checks.get("rank_identity_gate_all_true") is False
        )
    root_identity_consistent = _identity_gate_matches_observations(manifest)
    root_identity_gate = manifest.get("identity_gate")
    if isinstance(root_identity_gate, Mapping):
        if "gate_pass" in manifest:
            root_identity_consistent = root_identity_consistent and (
                manifest.get("gate_pass") is _all_true(root_identity_gate)
            )
        if "classification" in manifest:
            expected_identity_classification = (
                "V6_2_FULL_INTERFACE_SCHUR_PASS"
                if _all_true(root_identity_gate)
                else "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
            )
            root_identity_consistent = root_identity_consistent and (
                manifest.get("classification") == expected_identity_classification
            )
    evidence["identity_gate_raw_consistency"] = root_identity_consistent
    rank_integrity_names = (
        "rank_artifacts_complete",
        "rank_artifacts_are_mappings",
        "rank_artifact_schema",
        "rank_mpi_size",
        "rank_identity_pass",
        "rank_resource_pass",
        "rank_system_forbidden_zero",
        "rank_no_numeric_allgather",
        "rank_no_full_replica",
        "rank_mapping_matches_layout",
        "rank_mapping_count_observed",
        "rank_factor_lifecycle_observed",
        "rank_factor_lifecycle_consistent",
        "rank_deterministic_scalars_consistent",
        "rank_zero_linearity_consistent",
        "rank_identity_gate_consistent",
        "rank_identity_gate_raw_consistent",
        "rank_provenance_consistent",
        "rank_formal_sequence_scope_consistent",
        "ranks_exactly_0_to_7",
        "operator_hashes_present_and_equal",
        "mapping_hashes_present",
        "rank_scalar_records_finite",
    )
    rank_gate_names = (
        "rank_factor_lifecycle",
        "rank_identity_gate_all_true",
        "rank_mapping_count_sum",
    )
    rank_integrity_checks = {
        name: bool(rank_checks.get(name, False)) for name in rank_integrity_names
    }
    rank_gate_checks = {
        name: bool(rank_checks.get(name, False)) for name in rank_gate_names
    }
    evidence.update(
        {f"evidence_{name}": value for name, value in rank_integrity_checks.items()}
    )
    evidence["rank_integrity"] = all(rank_integrity_checks.values())
    evidence["formal_sequence_scope"] = (
        (
            isinstance(manifest.get("formal_sequence_start_scope"), str)
            and bool(manifest.get("formal_sequence_start_scope"))
            and manifest.get("formal_sequence_start_scope")
            == EXPECTED_FORMAL_SEQUENCE_START_SCOPE
            and rank_checks["rank_formal_sequence_scope_consistent"]
        )
        if executed_exact_hint or configured_identity_path
        else True
    )

    lifecycle = manifest.get("factor_lifecycle", {})
    after_by_rank = lifecycle.get("after_by_rank")
    after_is_valid = isinstance(after_by_rank, Sequence) and not isinstance(
        after_by_rank, (str, bytes)
    ) and len(after_by_rank) == EXPECTED_MPI_SIZE and all(
        isinstance(item, Mapping)
        and all(
            key in item
            and isinstance(item[key], int)
            and not isinstance(item[key], bool)
            for key in ("ready", "after_cleanup", "simultaneous_max")
        )
        for item in after_by_rank
    )
    derived_construction = (
        [int(item["ready"]) for item in after_by_rank]
        if after_is_valid
        else []
    )
    derived_destruction = (
        [int(item["ready"]) - int(item["after_cleanup"]) for item in after_by_rank]
        if after_is_valid
        else []
    )
    derived_simultaneous = (
        [int(item["simultaneous_max"]) for item in after_by_rank]
        if after_is_valid
        else []
    )
    evidence["factor_lifecycle_recorded"] = (
        after_is_valid
        and all(
            isinstance(lifecycle.get(name), int)
            and not isinstance(lifecycle.get(name), bool)
            for name in ("construction_count", "destruction_count", "simultaneous_max")
        )
    )
    lifecycle_gate = (
        evidence["factor_lifecycle_recorded"]
        and len(set(derived_construction)) == 1
        and len(set(derived_destruction)) == 1
        and len(set(derived_simultaneous)) == 1
        and derived_construction[0] == 3
        and derived_destruction[0] == 3
        and derived_simultaneous[0] == 3
        and lifecycle.get("construction_count") == derived_construction[0]
        and lifecycle.get("destruction_count") == derived_destruction[0]
        and lifecycle.get("simultaneous_max") == max(derived_simultaneous)
        and lifecycle.get("rank_consensus") is True
    )
    qualification = manifest.get("exact_qualification_plan")
    # A pre-exact identity stop is a configured V6 path, not the legacy
    # identity-only plan.  Keep the old JSON-only plan compatible, but do not
    # force a real V6 identity stop to claim that owner arrays were never
    # loaded.
    legacy_plan = not executed_exact_hint and not identity_stop_pde
    qualification_status_ok = (
        qualification.get("status") in {
            "designed_not_run",
            "configured_same_process_exact",
        }
        if isinstance(qualification, Mapping)
        else False
    )
    frozen_owner_text = (
        qualification.get("frozen_owner_row_arrays")
        if isinstance(qualification, Mapping)
        else None
    )
    if legacy_plan:
        plan_mode_ok = (
            qualification.get("status") == "designed_not_run"
            and qualification.get("identity_only") is True
            and frozen_owner_text
            == "not_loaded; complex PETSc owner-order values, never row ids"
        ) if isinstance(qualification, Mapping) else False
    else:
        plan_mode_ok = (
            isinstance(qualification, Mapping)
            and qualification.get("status") == "configured_same_process_exact"
            and qualification.get("identity_only") is False
            and isinstance(frozen_owner_text, str)
            and frozen_owner_text.startswith("loaded per source only after")
        )
    evidence["exact_qualification_plan"] = (
        isinstance(qualification, Mapping)
        and qualification_status_ok
        and plan_mode_ok
        and qualification.get("source_order") == [
            "external_dtn_coupling",
            "fixed_random_repeat_0",
            "modal_traction_positive",
            "modal_traction_negative",
            "fixed_random_repeat_1",
        ]
        and qualification.get("checkpoints") == [16, 32, 64, 128]
        and qualification.get("conditional_checkpoints") == [256, 512]
        and qualification.get("rhs_layout")
        == "current_canonical_active_keys_owner_local"
        and qualification.get("interface_rhs")
        == "g=b_Gamma-A_GammaI*A_II^-1*b_I"
        and qualification.get("solution_recovery")
        == "x_I=A_II^-1*(b_I-A_I,Gamma*x_Gamma)"
        and qualification.get("full_residual")
        == "independent_current_bare_F_mult"
        and qualification.get("first_two_gate")
        == "each relative true residual <= 1e-9"
        and qualification.get("one_cell_source_factor") == "not_reexecuted"
    )

    exact_audit: dict[str, Any] = {
        "valid": True,
        "errors": [],
        "summary": None,
        "expected_identities_by_rank": {},
        "aggregate_refs_by_label": {},
        "packet_aggregates_valid": True,
    }
    if executed_exact_hint:
        exact_audit = _check_exact_detail_artifacts(
            root,
            manifest,
            rank_artifacts,
            read_files,
        )
        aggregate_errors: list[str] = list(exact_audit.get("errors", []))
        aggregate_refs = exact_audit.get("aggregate_refs_by_label", {})
        expected_by_rank = exact_audit.get("expected_identities_by_rank", {})
        expected_frozen_descriptor_hashes_by_rank = exact_audit.get(
            "frozen_descriptor_hashes_by_rank", {}
        )
        expected_qualification_provenance = exact_audit.get(
            "qualification_provenance"
        )
        expected_frozen_source_provenance = exact_audit.get(
            "frozen_source_provenance"
        )
        summary = exact_audit.get("summary")
        packet_ready = bool(
            isinstance(summary, Mapping)
            and summary.get("all_sources_gate_pass") is True
        )
        if packet_ready:
            if not isinstance(aggregate_refs, Mapping) or tuple(
                aggregate_refs
            ) != _EXACT_SOURCE_ORDER:
                aggregate_errors.append("packet-ready detail aggregate set is incomplete")
            else:
                checked_files: set[str] = set()
                for label in _EXACT_SOURCE_ORDER:
                    expected_for_label: dict[int, Mapping[str, Any]] = {}
                    if isinstance(expected_by_rank, Mapping):
                        for rank, by_label in expected_by_rank.items():
                            if isinstance(by_label, Mapping) and isinstance(
                                by_label.get(label), Mapping
                            ):
                                expected_for_label[int(rank)] = by_label[label]
                    aggregate = aggregate_refs.get(label)
                    valid, error = _check_packet_aggregate_chain(
                        root,
                        label,
                        aggregate,
                        read_files,
                        expected_identities_by_rank=expected_for_label,
                        expected_qualification_provenance=(
                            expected_qualification_provenance
                            if isinstance(expected_qualification_provenance, Mapping)
                            else None
                        ),
                        expected_frozen_source_provenance=(
                            expected_frozen_source_provenance
                            if isinstance(expected_frozen_source_provenance, Mapping)
                            else None
                        ),
                        expected_frozen_descriptor_hashes_by_rank=(
                            expected_frozen_descriptor_hashes_by_rank
                            if isinstance(
                                expected_frozen_descriptor_hashes_by_rank, Mapping
                            )
                            else None
                        ),
                        expected_bare_f_operator_hash=manifest.get(
                            "bare_f_operator_hash"
                        ),
                        checked_files=checked_files,
                    )
                    if not valid:
                        aggregate_errors.append(
                            error or f"packet aggregate is invalid for {label}"
                        )
        elif aggregate_refs:
            aggregate_errors.append(
                "numerical-negative exact detail unexpectedly has packet aggregates"
            )
        exact_audit["errors"] = aggregate_errors
        exact_audit["valid"] = not aggregate_errors
        exact_audit["packet_aggregates_valid"] = not aggregate_errors
        evidence["exact_detail_artifacts"] = bool(exact_audit["valid"])
        evidence["exact_detail_root_chain"] = bool(exact_audit["valid"])
        evidence["packet_artifact_chain"] = bool(
            exact_audit["packet_aggregates_valid"]
        )
        loaded_by_rank = exact_audit.get(
            "exact_output_vectors_loaded_by_rank", {}
        )
        advertised_counts = [
            artifact.get("exact_output_vectors_loaded")
            for artifact in rank_artifacts
        ]
        loaded_counts = [
            loaded_by_rank.get(rank) if isinstance(loaded_by_rank, Mapping) else None
            for rank in range(EXPECTED_MPI_SIZE)
        ]
        evidence["exact_output_count_contract"] = bool(
            len(loaded_counts) == EXPECTED_MPI_SIZE
            and loaded_counts == advertised_counts
            and len(set(loaded_counts)) == 1
            and manifest.get("exact_output_vectors_loaded") == loaded_counts[0]
        )
        evidence.pop("no_npy_read", None)
        exact_summary = exact_audit.get("summary")
        packet_ready = bool(
            isinstance(exact_summary, Mapping)
            and exact_summary.get("all_sources_gate_pass") is True
        )
        # Packet reopening appends NPY entries to read_files.  Recompute the
        # flag after that pass; the pre-reopen value only describes the root
        # and rank JSON reads.
        npy_read = any(item.get("kind") == "npy" for item in read_files)
        evidence["npy_read_contract"] = (
            npy_read if packet_ready else not npy_read
        )
    else:
        evidence["exact_detail_artifacts"] = True
        if exact_refs_all_none:
            root_chain = manifest.get("exact_qualification_artifact_chain_sha256")
            computed_chain = hashlib.sha256(
                json.dumps(
                    [None] * EXPECTED_MPI_SIZE,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            evidence["exact_detail_root_chain"] = (
                _is_hex(root_chain) and root_chain == computed_chain
            )
        else:
            # The legacy schema predates rank exact-detail references and has
            # no chain to verify.
            evidence["exact_detail_root_chain"] = True
        evidence["packet_artifact_chain"] = True

    gate.update(_vector_gate_checks(manifest))
    gate["factor_lifecycle"] = lifecycle_gate
    gate["rank_factor_lifecycle"] = rank_gate_checks["rank_factor_lifecycle"]
    gate["rank_identity_gate"] = rank_gate_checks["rank_identity_gate_all_true"]
    gate["rank_deterministic_scalars"] = rank_checks[
        "rank_deterministic_scalars_consistent"
    ]
    gate["rank_mapping_count_sum"] = rank_gate_checks["rank_mapping_count_sum"]
    gate["rank_owner_mapping"] = (
        rank_checks["rank_artifacts_complete"]
        and rank_checks["ranks_exactly_0_to_7"]
        and rank_checks["rank_mapping_matches_layout"]
    )
    gate["canonical_layout"] = canonical_layout_gate
    gate["gamma_counts"] = gamma_counts_gate
    gate["forbidden_objects_zero"] = (
        evidence["matrix_objects_zero"]
        and evidence["qep_zero"]
        and evidence["no_forbidden_factors"]
    )
    gate["exact_qualification_plan_recorded"] = evidence["exact_qualification_plan"]
    if executed_exact_hint:
        exact_summary = exact_audit.get("summary")
        gate["exact_detail_numerical_gate"] = bool(
            isinstance(exact_summary, Mapping)
            and exact_summary.get("all_sources_gate_pass") is True
        )
        gate["exact_packet_aggregate_gate"] = bool(
            isinstance(exact_summary, Mapping)
            and exact_summary.get("all_sources_gate_pass") is True
            and exact_audit.get("packet_aggregates_valid") is True
        )
    else:
        gate["exact_detail_numerical_gate"] = True
        gate["exact_packet_aggregate_gate"] = True
    non_exact_gate_names = tuple(
        name
        for name in gate
        if name not in {"exact_detail_numerical_gate", "exact_packet_aggregate_gate"}
    )
    gate["non_exact_identity_layout_lifecycle_forbidden"] = all(
        bool(gate[name]) for name in non_exact_gate_names
    )
    gate_pass = bool(all(gate.values()))
    evidence_valid = bool(all(evidence.values()))
    checker_pass = evidence_valid
    if not evidence_valid:
        classification = "IMPLEMENTATION_FAILURE"
    elif executed_exact_hint and not gate_pass:
        exact_summary = exact_audit.get("summary")
        if (
            isinstance(exact_summary, Mapping)
            and exact_summary.get("numerical_negative") is True
            and exact_audit.get("packet_aggregates_valid") is True
            and gate["non_exact_identity_layout_lifecycle_forbidden"] is True
        ):
            classification = "V6_2_FULL_INTERFACE_SCHUR_NUMERICAL_NEGATIVE"
        else:
            classification = "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
    elif gate_pass:
        classification = "V6_2_FULL_INTERFACE_SCHUR_PASS"
    else:
        classification = "V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL"
    return {
        "schema": SCHEMA,
        "formal_root": str(root),
        "formal_root_sha256": manifest_sha,
        "formal_source_sha": str(formal_source_sha),
        "checker_source_sha": str(checker_source_sha),
        "evidence_valid": evidence_valid,
        "checker_pass": checker_pass,
        "gate_pass": gate_pass,
        "classification": classification,
        "evidence_checks": evidence,
        "gate_checks": gate,
        "rank_integrity_checks": rank_integrity_checks,
        "rank_gate_checks": rank_gate_checks,
        "executed_exact": executed_exact_hint,
        "exact_execution": exact_audit,
        "watchdog_audit": watchdog_audit,
        "read_files": read_files,
        "npy_read": any(
            str(item.get("kind")) == "npy"
            for item in read_files
        ),
        "output_disjoint_from_formal_root": (
            None if output_path is None else not _inside(output_path, root)
        ),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(
        json.dumps(payload, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", required=True)
    parser.add_argument("--formal-source-sha", required=True)
    parser.add_argument("--checker-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    root = Path(args.formal_root).resolve()
    output = Path(args.output).resolve()
    if _inside(output, root):
        print("V6-2 checker output must be outside formal root")
        return 2
    try:
        result = check_v6_2_interface_schur(
            formal_root=root,
            formal_source_sha=args.formal_source_sha,
            checker_source_sha=args.checker_source_sha,
            output=output,
        )
    except Exception as exc:  # evidence corruption is a checker failure, not a solver result
        result = {
            "schema": SCHEMA,
            "formal_root": str(root),
            "formal_source_sha": str(args.formal_source_sha),
            "checker_source_sha": str(args.checker_source_sha),
            "evidence_valid": False,
            "checker_pass": False,
            "gate_pass": False,
            "classification": "IMPLEMENTATION_FAILURE",
            "error": f"{type(exc).__name__}: {exc}",
            "read_files": [],
            "npy_read": False,
            "output_disjoint_from_formal_root": True,
        }
    _write_json(output, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["checker_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
