"""Independent raw-evidence checker for the Task040 V4-1 controlled stop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.task040_level_a import (
    TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
    TASK040_V1_2_INPUT_SHA256,
    TASK040_V1_2_PHYSICAL_MODEL_SHA256,
    TASK040_V1_2_PROBE_MANIFEST,
    TASK040_V1_2_PROBE_MANIFEST_SHA256,
    TASK040_V1_2_SELECTED_MANIFEST_SHA256,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID,
    TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA,
    TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA,
    TASK040_V4_FROZEN_BRANCH,
)
from src.solvers.hybrid_exact_authority_compat import V4_EXACT_AUTHORITY_LABELS


EXPECTED_CLASSIFICATION = "EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F"
IMPLEMENTATION_FAILURE = "IMPLEMENTATION_FAILURE"
EXPECTED_FAILURE_CODE = "CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE"
EXPECTED_FAILURE_REASON = "canonical source-row binding unavailable/incompatible"
EXPECTED_DOWNSTREAM = (
    "projection",
    "lift",
    "trace",
    "dual",
    "response",
    "fgmres",
    "coarse",
    "level_b",
    "full_hybrid",
    "h3",
)
EXPECTED_MARKERS = ("construction_begin", "v4_identity_stop")
EXPECTED_FORMAL_RAW_PATHS = (
    Path("memory_stage_markers.raw.jsonl"),
    Path("memory_stages.jsonl"),
    Path("process_tree_samples.jsonl"),
    Path("watchdog_summary.json"),
    Path("worker/run_summary.json"),
    Path("worker_stdout.txt"),
)
EXPECTED_IDENTITY_CHECKS = (
    "input_sha256",
    "physical_model_sha256",
    "frozen_branch",
    "freeze_source",
    "selected_manifest",
    "resolved_config",
    "packet_manifest",
    "spool_catalog",
    "spool_producer_source",
    "exact_output_metadata",
    "canonical_source_binding",
)
EXPECTED_ROLES = ("rhs", "exact_output")
SPOOL_EXTRA_LABEL = "physical_side_rhs"

__all__ = ["check_v4_exact_authority", "main"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(char in "0123456789abcdef" for char in value)
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object: {path}")
            rows.append(value)
    return rows


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_probe_manifest() -> tuple[Path, dict[str, Any], str]:
    path = _repo_root() / TASK040_V1_2_PROBE_MANIFEST
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TASK040_V1_2_PROBE_MANIFEST_SHA256:
        raise ValueError("Task040 V1-2 probe manifest hash mismatch")
    manifest = json.loads(payload)
    if not isinstance(manifest, Mapping):
        raise ValueError("Task040 V1-2 probe manifest is not an object")
    return path, dict(manifest), digest


def _metadata_payload_hash(record: Mapping[str, Any]) -> str:
    payload = dict(record)
    payload.pop("metadata_payload_sha256_excluding_self", None)
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _record(
    checks: dict[str, bool],
    details: dict[str, Any],
    name: str,
    passed: Any,
    **info: Any,
) -> None:
    checks[name] = bool(passed)
    if info:
        details[name] = info


def _command_value(command: Any, flag: str) -> str | None:
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        return None
    values = list(command)
    try:
        index = values.index(flag)
    except ValueError:
        return None
    if index + 1 >= len(values):
        return None
    return str(values[index + 1])


def _formal_paths(root: Path) -> list[Path]:
    """Return only the six immutable formal raw paths, never checker output."""

    return [root / relative_path for relative_path in EXPECTED_FORMAL_RAW_PATHS]


def _spool_path(exact_spool_root: Path) -> Path:
    nested = exact_spool_root / "v5_blr_reference_spool"
    return nested if nested.is_dir() else exact_spool_root


def _resolved_config_path(exact_spool_root: Path, spool_root: Path) -> Path:
    candidates = [
        exact_spool_root / "resolved_config.json",
        spool_root.parent / "resolved_config.json",
        spool_root.parent.parent / "resolved_config.json",
    ]
    existing = []
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate.is_file() and candidate not in existing:
            existing.append(candidate)
    if len(existing) != 1:
        raise ValueError(
            "expected exactly one frozen resolved_config.json near the exact spool; "
            f"found {len(existing)}: {existing}"
        )
    return existing[0]


def _spool_records(
    spool_root: Path,
    labels: Sequence[str],
    checks: dict[str, bool],
    details: dict[str, Any],
) -> tuple[dict[tuple[str, str], list[tuple[int, Path, dict[str, Any]]]], list[str]]:
    all_labels = tuple(labels) + (SPOOL_EXTRA_LABEL,)
    json_paths = [
        spool_root / f"rank{rank:04d}" / f"bottom_{label}_{role}.json"
        for rank in range(8)
        for label in all_labels
        for role in EXPECTED_ROLES
    ]
    records: dict[tuple[str, str], list[tuple[int, Path, dict[str, Any]]]] = {}
    for label in labels:
        for role in EXPECTED_ROLES:
            pair = (label, role)
            pair_records: list[tuple[int, Path, dict[str, Any]]] = []
            for rank in range(8):
                path = spool_root / f"rank{rank:04d}" / f"bottom_{label}_{role}.json"
                if path.is_file():
                    value = _read_json(path)
                    if not isinstance(value, dict):
                        raise ValueError(f"spool metadata is not an object: {path}")
                    pair_records.append((rank, path, value))
            records[pair] = pair_records
    expected_json_paths = {path.resolve() for path in json_paths}
    actual_json_paths = {
        path.resolve() for path in spool_root.rglob("*.json") if path.is_file()
    }
    _record(
        checks,
        details,
        "spool_json_count",
        actual_json_paths == expected_json_paths,
        observed=len(actual_json_paths),
        expected=96,
        missing=sorted(str(path) for path in expected_json_paths - actual_json_paths),
        unexpected=sorted(
            str(path) for path in actual_json_paths - expected_json_paths
        ),
    )
    _record(
        checks,
        details,
        "spool_expected_pairs",
        all(
            len(records[(label, role)]) == 8
            for label in labels
            for role in EXPECTED_ROLES
        ),
        observed={
            f"{label}:{role}": len(records[(label, role)])
            for label in labels
            for role in ("rhs", "exact_output")
        },
        expected=8,
    )
    return records, [
        str(path) for path in sorted(expected_json_paths & actual_json_paths)
    ]


def _check_spool_identity(
    records: Mapping[tuple[str, str], Sequence[tuple[int, Path, Mapping[str, Any]]]],
    labels: Sequence[str],
    spool_root: Path,
    identity: Mapping[str, Any],
    source_canonical_authority: Mapping[str, Any],
    manifest: Mapping[str, Any],
    selected_manifest_sha256: str,
    selected_identity_sha256: str,
    checks: dict[str, bool],
    details: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    manifest_identity = manifest["identity"]
    physical_probes = manifest["physical_probes"]
    probe_identities = physical_probes["probe_identities"]
    exact_output_identities = physical_probes["exact_output_identity_sha256"]
    global_size = int(physical_probes["global_size"])
    producer_source_sha = str(manifest_identity["exact_spool_source_sha"])
    expected_packet_identity = identity.get("packet_identity")
    source_ownership = identity.get("source_ownership")
    authority_entries = source_canonical_authority.get("entries")
    producer: dict[str, Any] = {}
    rhs_identity: dict[str, Any] = {}
    exact_output: dict[str, Any] = {}
    canonical_missing: list[str] = []
    metadata_hash_pass = True
    descriptor_pass = True
    packet_wrapper_pass = True
    ownership_pass = True
    all_wrapper_tokens: list[str] = []
    for label in labels:
        for role in EXPECTED_ROLES:
            pair = f"{label}:{role}"
            shards = records[(label, role)]
            source_shas: list[Any] = []
            global_ids: list[Any] = []
            ranges: list[list[int]] = []
            wrappers: list[str] = []
            pair_descriptor_pass = True
            pair_packet_pass = True
            for rank, metadata_path, record in shards:
                metadata_hash = record.get("metadata_payload_sha256_excluding_self")
                self_hash_pass = (
                    _is_hex(metadata_hash, 64)
                    and _metadata_payload_hash(record) == metadata_hash
                )
                metadata_hash_pass = metadata_hash_pass and self_hash_pass
                expected_json_path = (
                    spool_root / f"rank{rank:04d}" / f"bottom_{label}_{role}.json"
                ).resolve()
                expected_array_path = expected_json_path.with_suffix(".npy")
                path_pass = record.get("metadata_path") == str(
                    expected_json_path
                ) and record.get("array_path") == str(expected_array_path)
                ownership = record.get("ownership_range")
                try:
                    normalized_ownership = [int(ownership[0]), int(ownership[1])]
                except (IndexError, TypeError, ValueError):
                    normalized_ownership = []
                ranges.append(normalized_ownership)
                source_identity = record.get("source_identity")
                packet_wrapper = (
                    source_identity.get("packet_identity")
                    if isinstance(source_identity, Mapping)
                    else None
                )
                nested_packet_identity = (
                    packet_wrapper.get("packet_identity")
                    if isinstance(packet_wrapper, Mapping)
                    else None
                )
                wrapper_token = json.dumps(
                    packet_wrapper, sort_keys=True, separators=(",", ":")
                )
                wrappers.append(wrapper_token)
                all_wrapper_tokens.append(wrapper_token)
                source_sha = (
                    packet_wrapper.get("source_sha")
                    if isinstance(packet_wrapper, Mapping)
                    else None
                )
                source_shas.append(source_sha)
                vector_identity = (
                    source_identity.get("vector_identity")
                    if isinstance(source_identity, Mapping)
                    else None
                )
                probe_metadata = (
                    source_identity.get("probe_metadata")
                    if isinstance(source_identity, Mapping)
                    else None
                )
                global_id = (
                    vector_identity.get("global_sha256")
                    if isinstance(vector_identity, Mapping)
                    else None
                )
                global_ids.append(global_id)
                expected_global_id = (
                    probe_identities[label]["rhs_identity_sha256"]
                    if role == "rhs"
                    else exact_output_identities[label]
                )
                vector_pass = (
                    isinstance(vector_identity, Mapping)
                    and vector_identity.get("local_sha256")
                    == record.get("array_sha256")
                    and vector_identity.get("dtype") == record.get("dtype")
                    and vector_identity.get("global_size") == record.get("global_size")
                    and vector_identity.get("ownership_range")
                    == record.get("ownership_range")
                    and global_id == expected_global_id
                )
                probe_pass = (
                    isinstance(probe_metadata, Mapping)
                    and probe_metadata.get("label") == label
                )
                if role == "exact_output":
                    probe_pass = probe_pass and dict(probe_metadata) == {"label": label}
                else:
                    expected_probe = probe_identities[label]
                    probe_identity = (
                        probe_metadata.get("identity")
                        if isinstance(probe_metadata, Mapping)
                        else None
                    )
                    probe_pass = probe_pass and (
                        isinstance(probe_identity, Mapping)
                        and probe_identity.get("global_sha256") == expected_global_id
                        and probe_identity.get("local_sha256")
                        == record.get("array_sha256")
                        and probe_identity.get("dtype") == record.get("dtype")
                        and probe_identity.get("global_size")
                        == record.get("global_size")
                        and probe_identity.get("ownership_range")
                        == record.get("ownership_range")
                        and probe_metadata.get("seed") == expected_probe.get("seed")
                        and probe_metadata.get("source") == expected_probe.get("source")
                        and (
                            probe_metadata.get("resolved_column")
                            == expected_probe.get("resolved_column")
                            if "resolved_column" in expected_probe
                            else "resolved_column" not in probe_metadata
                        )
                    )
                descriptor_ok = (
                    record.get("side") == "bottom"
                    and record.get("label") == label
                    and record.get("role") == role
                    and record.get("dtype") == "complex128"
                    and record.get("global_size") == global_size
                    and _is_hex(record.get("array_sha256"), 64)
                    and record.get("local_size")
                    == (normalized_ownership[1] - normalized_ownership[0])
                    if len(normalized_ownership) == 2
                    else False
                )
                identity_ok = (
                    isinstance(source_identity, Mapping)
                    and source_identity.get("artifact_role") == role
                    and isinstance(packet_wrapper, Mapping)
                    and packet_wrapper.get("manifest_sha256")
                    == selected_manifest_sha256
                    and isinstance(nested_packet_identity, Mapping)
                    and nested_packet_identity == expected_packet_identity
                    and _canonical_json_sha256(nested_packet_identity)
                    == selected_identity_sha256
                )
                pair_descriptor_pass = (
                    pair_descriptor_pass and path_pass and vector_pass and probe_pass
                )
                pair_packet_pass = pair_packet_pass and identity_ok
                if not descriptor_ok:
                    pair_descriptor_pass = False
                if not identity_ok:
                    pair_packet_pass = False
            expected_ranges = (
                source_ownership.get(label, {}).get(role)
                if isinstance(source_ownership, Mapping)
                else None
            )
            canonical_range = (
                authority_entries.get(label, {}).get(role, {}).get("ownership_ranges")
                if isinstance(authority_entries, Mapping)
                else None
            )
            contiguous = (
                len(ranges) == 8
                and ranges[0] == [0, ranges[0][1]]
                and all(
                    len(current) == 2 and current[0] == ranges[index - 1][1]
                    for index, current in enumerate(ranges)
                    if index > 0
                )
                and bool(ranges)
                and ranges[-1][1] == global_size
            )
            pair_ownership_pass = (
                contiguous and ranges == expected_ranges and ranges == canonical_range
            )
            ownership_pass = ownership_pass and pair_ownership_pass
            descriptor_pass = descriptor_pass and pair_descriptor_pass
            packet_wrapper_pass = packet_wrapper_pass and pair_packet_pass
            if len(set(wrappers)) != 1:
                pair_packet_pass = False
                packet_wrapper_pass = False
            expected_global_id = (
                probe_identities[label]["rhs_identity_sha256"]
                if role == "rhs"
                else exact_output_identities[label]
            )
            identity_summary = {
                "shard_count": len(global_ids),
                "shard_counts": len(global_ids),
                "observed": sorted({value for value in global_ids if value}),
                "expected": expected_global_id,
                "checks": all(value == expected_global_id for value in global_ids),
                "pass": bool(
                    len(global_ids) == 8
                    and len(set(global_ids)) == 1
                    and global_ids[0] == expected_global_id
                    and pair_descriptor_pass
                    and pair_ownership_pass
                    and pair_packet_pass
                )
                if global_ids
                else False,
            }
            if role == "rhs":
                rhs_identity[label] = identity_summary
            else:
                exact_output[label] = identity_summary
            producer[pair] = {
                "shard_count": len(source_shas),
                "valid_source_sha_count": sum(
                    _is_hex(value, 40) for value in source_shas
                ),
                "expected_match_count": sum(
                    value == producer_source_sha for value in source_shas
                ),
                "observed_source_shas": sorted(
                    {value for value in source_shas if isinstance(value, str)}
                ),
                "pass": bool(
                    len(source_shas) == 8
                    and all(value == producer_source_sha for value in source_shas)
                    and pair_packet_pass
                ),
            }
            if (
                all(
                    "canonical_source_authority" not in record
                    for _rank, _path, record in shards
                )
                and len(shards) == 8
            ):
                canonical_missing.append(pair)
    expected_missing = [
        f"{label}:{role}" for label in labels for role in EXPECTED_ROLES
    ]
    producer_pass = all(item["pass"] for item in producer.values()) and len(
        producer
    ) == 2 * len(labels)
    rhs_pass = all(item["pass"] for item in rhs_identity.values()) and len(
        rhs_identity
    ) == len(labels)
    exact_pass = all(item["pass"] for item in exact_output.values()) and len(
        exact_output
    ) == len(labels)
    expected_wrapper = json.dumps(
        {
            "manifest_sha256": selected_manifest_sha256,
            "packet_identity": expected_packet_identity,
            "source_sha": producer_source_sha,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    packet_wrapper_global_pass = (
        len(all_wrapper_tokens) == 8 * len(labels) * len(EXPECTED_ROLES)
        and len(set(all_wrapper_tokens)) == 1
        and all(token == expected_wrapper for token in all_wrapper_tokens)
    )
    packet_wrapper_pass = packet_wrapper_pass and packet_wrapper_global_pass
    canonical_pass = canonical_missing == expected_missing
    _record(
        checks, details, "producer_source_identity", producer_pass, entries=producer
    )
    _record(
        checks,
        details,
        "metadata_self_hash",
        metadata_hash_pass,
    )
    _record(
        checks,
        details,
        "array_descriptor_contract",
        descriptor_pass,
    )
    _record(
        checks,
        details,
        "ownership_contract",
        ownership_pass,
    )
    _record(
        checks,
        details,
        "packet_wrapper_identity",
        packet_wrapper_pass,
    )
    _record(checks, details, "rhs_probe_identity", rhs_pass, entries=rhs_identity)
    _record(checks, details, "exact_output_identity", exact_pass, entries=exact_output)
    _record(
        checks,
        details,
        "canonical_source_binding_contract",
        canonical_pass,
        missing_entries=canonical_missing,
        expected_missing_entries=expected_missing,
        descriptor_complete=False,
        bridge_qualified=False,
        **{"pass": False},
    )
    return canonical_missing, {
        "producer": producer,
        "rhs": rhs_identity,
        "exact_output": exact_output,
        "expected_producer_source_sha": producer_source_sha,
        "global_size": global_size,
        "packet_wrapper_count": len(all_wrapper_tokens),
        "packet_wrapper_global_pass": packet_wrapper_global_pass,
    }


def _check_source_canonical_authority(
    authority: Any,
    labels: Sequence[str],
    checks: dict[str, bool],
    details: dict[str, Any],
) -> list[str]:
    expected_missing = [
        f"{label}:{role}" for label in labels for role in ("rhs", "exact_output")
    ]
    entries = authority.get("entries") if isinstance(authority, Mapping) else None
    entry_contract = isinstance(entries, Mapping) and set(entries) == set(labels)
    if entry_contract:
        for label in labels:
            label_entries = entries.get(label)
            entry_contract = entry_contract and isinstance(label_entries, Mapping)
            if not isinstance(label_entries, Mapping):
                continue
            entry_contract = entry_contract and set(label_entries) == {
                "rhs",
                "exact_output",
            }
            for role in ("rhs", "exact_output"):
                entry = label_entries.get(role)
                entry_contract = (
                    entry_contract
                    and isinstance(entry, Mapping)
                    and entry.get("descriptor_available") is False
                    and entry.get("reason") == EXPECTED_FAILURE_CODE
                )
    observed_missing = (
        authority.get("missing_entries") if isinstance(authority, Mapping) else None
    )
    passed = (
        isinstance(authority, Mapping)
        and authority.get("array_hash_validation_only") is True
        and authority.get("canonical_map_content_hash_verified") is False
        and authority.get("canonical_map_opened") is False
        and authority.get("canonical_reconstruction_verified") is False
        and authority.get("descriptor_available") is False
        and authority.get("descriptor_complete") is False
        and authority.get("bridge_qualified") is False
        and authority.get("pass") is False
        and authority.get("failure_code") == EXPECTED_FAILURE_CODE
        and authority.get("reason") == EXPECTED_FAILURE_REASON
        and authority.get("labels") == list(labels)
        and authority.get("required_roles") == ["rhs", "exact_output"]
        and observed_missing == expected_missing
        and authority.get("inconsistent_fields") == []
        and authority.get("malformed_entries") == []
        and authority.get("numeric_vectors_constructed") is False
        and authority.get("values_retained") is False
        and authority.get("raw_global_row_remap_forbidden") is True
        and authority.get("raw_npy_mmap_hash_read") is True
        and authority.get("source_current_key_equality_verified") is False
        and entry_contract
    )
    _record(
        checks,
        details,
        "source_canonical_authority_contract",
        passed,
        missing_entries=observed_missing,
        expected_missing_entries=expected_missing,
        descriptor_available=(
            authority.get("descriptor_available")
            if isinstance(authority, Mapping)
            else None
        ),
        descriptor_complete=(
            authority.get("descriptor_complete")
            if isinstance(authority, Mapping)
            else None
        ),
        bridge_qualified=(
            authority.get("bridge_qualified")
            if isinstance(authority, Mapping)
            else None
        ),
        pass_value=(authority.get("pass") if isinstance(authority, Mapping) else None),
    )
    return list(observed_missing) if isinstance(observed_missing, list) else []


def _producer_identity_summary(
    producer: Mapping[str, Mapping[str, Any]], expected_source_sha: str
) -> dict[str, Any]:
    per_label_role = {
        pair: {
            "check": item.get("pass") is True,
            "expected_match_count": item.get("expected_match_count"),
            "expected_mpi_size": 8,
            "observed_source_shas": item.get("observed_source_shas"),
            "shard_count": item.get("shard_count"),
            "valid_source_sha_count": item.get("valid_source_sha_count"),
        }
        for pair, item in sorted(producer.items())
    }
    observed_source_shas = sorted(
        {
            value
            for item in producer.values()
            for value in item.get("observed_source_shas", [])
        }
    )
    return {
        "expected_mpi_size": 8,
        "expected_source_sha": expected_source_sha,
        "observed_source_sha": (
            observed_source_shas[0] if len(observed_source_shas) == 1 else None
        ),
        "observed_source_shas": observed_source_shas,
        "per_label_role": per_label_role,
        "pass": (
            len(per_label_role) == 10
            and len(observed_source_shas) == 1
            and observed_source_shas[0] == expected_source_sha
            and all(
                item["check"]
                and item["expected_mpi_size"] == 8
                and item["shard_count"] == 8
                and item["valid_source_sha_count"] == 8
                and item["expected_match_count"] == 8
                for item in per_label_role.values()
            )
        ),
    }


def _check_watchdog(
    formal_root: Path,
    watchdog: Mapping[str, Any],
    run_summary_path: Path,
    process_rows: Sequence[Mapping[str, Any]],
    checks: dict[str, bool],
    details: dict[str, Any],
) -> None:
    process_path = formal_root / "process_tree_samples.jsonl"
    summary_hash = _sha256(run_summary_path)
    computed_peak = max(
        (int(row.get("rss_bytes", -1)) for row in process_rows), default=-1
    )
    computed_authority_peak = max(
        (
            int(row.get("resource_authority", {}).get("memory_authority_bytes", -1))
            for row in process_rows
        ),
        default=-1,
    )
    timeline_rows_valid = all(
        row.get("authoritative_sample") is True
        and row.get("rss_bytes")
        == row.get("resource_authority", {}).get("memory_authority_bytes")
        and row.get("swap_bytes") == 0
        and row.get("terminal_teardown_excluded") is False
        and row.get("resource_authority", {})
        .get("process_tree", {})
        .get("all_status_readable")
        is True
        and row.get("resource_authority", {}).get("process_tree", {}).get("swap_bytes")
        == 0
        and row.get("resource_authority", {}).get("job_cgroup", {}).get("readable")
        is True
        and row.get("resource_authority", {})
        .get("job_cgroup", {})
        .get("swap_current_bytes")
        == 0
        for row in process_rows
    )
    _record(
        checks,
        details,
        "watchdog_exit",
        watchdog.get("schema") == "task040.level_a.watchdog.v1"
        and watchdog.get("return_code") == 0
        and watchdog.get("termination_reason") == "natural_exit"
        and watchdog.get("run_summary_present") is True,
        return_code=watchdog.get("return_code"),
        termination_reason=watchdog.get("termination_reason"),
    )
    _record(
        checks,
        details,
        "watchdog_samples",
        len(process_rows) == 20
        and watchdog.get("sample_count") == 20
        and watchdog.get("authoritative_sample_count") == 20
        and timeline_rows_valid,
        observed=len(process_rows),
        sample_count=watchdog.get("sample_count"),
        authoritative_sample_count=watchdog.get("authoritative_sample_count"),
    )
    _record(
        checks,
        details,
        "watchdog_resource",
        watchdog.get("all_status_readable") is True
        and watchdog.get("swap_authority_readable") is True
        and watchdog.get("peak_swap_bytes") == 0
        and watchdog.get("peak_dedicated_cgroup_swap_bytes") == 0
        and (
            (
                watchdog.get("dedicated_cgroup_present") is False
                and watchdog.get("dedicated_cgroup_swap_readable") is None
            )
            or (
                watchdog.get("dedicated_cgroup_present") is True
                and watchdog.get("dedicated_cgroup_swap_readable") is True
            )
        )
        and watchdog.get("terminal_teardown_excluded_count") == 0
        and computed_peak == 1_764_352_000
        and computed_authority_peak == 1_764_352_000
        and watchdog.get("peak_rss_bytes") == computed_peak,
        computed_peak_rss_bytes=computed_peak,
        computed_peak_authority_bytes=computed_authority_peak,
        watchdog_peak_rss_bytes=watchdog.get("peak_rss_bytes"),
    )
    process_control = watchdog.get("process_control")
    _record(
        checks,
        details,
        "watchdog_process_control",
        isinstance(process_control, Mapping)
        and process_control.get("requested") is True
        and process_control.get("process_group_exited") is True
        and process_control.get("worker_exited") is True
        and process_control.get("sigkill_required") is False,
        process_control=process_control,
    )
    artifact_hashes = watchdog.get("artifact_hashes", {})
    expected_artifacts = {
        "memory_stage_markers.raw.jsonl": formal_root
        / "memory_stage_markers.raw.jsonl",
        "memory_stages.jsonl": formal_root / "memory_stages.jsonl",
        "process_tree_samples.jsonl": process_path,
        "worker_stdout.txt": formal_root / "worker_stdout.txt",
    }
    _record(
        checks,
        details,
        "watchdog_artifact_hashes",
        all(
            artifact_hashes.get(name) == _sha256(path)
            for name, path in expected_artifacts.items()
        )
        and watchdog.get("run_summary_sha256") == summary_hash,
        observed={name: _sha256(path) for name, path in expected_artifacts.items()},
        watchdog_artifacts=artifact_hashes,
        run_summary_sha256=summary_hash,
    )


def check_v4_exact_authority(
    formal_root: str | Path,
    formal_source_sha: str,
    checker_source_sha: str,
    *,
    exact_spool_root: str | Path | None = None,
) -> dict[str, Any]:
    """Recompute V4-1 evidence from raw JSON/JSONL/stdout and spool metadata."""

    formal_root = Path(formal_root).resolve()
    formal_paths = _formal_paths(formal_root)
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    if not _is_hex(formal_source_sha, 40) or not _is_hex(checker_source_sha, 40):
        raise ValueError(
            "source SHAs must be lowercase 40-character hexadecimal strings"
        )
    _record(
        checks,
        details,
        "formal_raw_file_set",
        all(path.is_file() for path in formal_paths),
        observed={
            str(path.relative_to(formal_root)): path.is_file() for path in formal_paths
        },
        expected=[str(path) for path in EXPECTED_FORMAL_RAW_PATHS],
    )
    watchdog_path = formal_root / "watchdog_summary.json"
    run_summary_path = formal_root / "worker" / "run_summary.json"
    process_path = formal_root / "process_tree_samples.jsonl"
    marker_path = formal_root / "memory_stage_markers.raw.jsonl"
    stages_path = formal_root / "memory_stages.jsonl"
    stdout_path = formal_root / "worker_stdout.txt"
    watchdog = _read_json(watchdog_path)
    run_summary = _read_json(run_summary_path)
    process_rows = _read_jsonl(process_path)
    marker_rows = _read_jsonl(marker_path)
    stage_rows = _read_jsonl(stages_path)
    stdout = stdout_path.read_text(encoding="utf-8")
    if not isinstance(watchdog, Mapping) or not isinstance(run_summary, Mapping):
        raise ValueError("formal summaries must be JSON objects")
    identity = run_summary.get("identity_observed", {})
    exact_authority = run_summary.get("exact_authority", {})
    source_loading = run_summary.get("source_loading", {})
    construction = run_summary.get("construction", {})
    if not isinstance(identity, Mapping):
        raise ValueError("identity_observed must be an object")
    probe_manifest_path, probe_manifest, probe_manifest_sha256 = _load_probe_manifest()
    manifest_identity = probe_manifest.get("identity", {})
    physical_probes = probe_manifest.get("physical_probes", {})
    if not isinstance(manifest_identity, Mapping) or not isinstance(
        physical_probes, Mapping
    ):
        raise ValueError("probe manifest identity sections are missing")
    probe_labels = physical_probes.get("labels")
    input_arg = _command_value(watchdog.get("command"), "--input")
    if input_arg is None:
        raise ValueError("watchdog command is missing --input")
    input_path = Path(input_arg)
    if not input_path.is_absolute():
        input_path = _repo_root() / input_path
    input_path = input_path.resolve()
    input_sha256 = _sha256(input_path)
    selected_manifest_sha256 = TASK040_V1_2_SELECTED_MANIFEST_SHA256
    selected_identity_sha256 = manifest_identity.get("selected_identity_sha256")
    _record(
        checks,
        details,
        "probe_manifest_identity",
        probe_manifest_sha256 == TASK040_V1_2_PROBE_MANIFEST_SHA256
        and probe_manifest.get("schema")
        == "task040.v1_2.interface_schur_probe_manifest.v1"
        and probe_labels == list(V4_EXACT_AUTHORITY_LABELS)
        and manifest_identity.get("input_sha256") == TASK040_V1_2_INPUT_SHA256
        and manifest_identity.get("physical_model_sha256")
        == TASK040_V1_2_PHYSICAL_MODEL_SHA256
        and manifest_identity.get("selected_manifest_sha256")
        == TASK040_V1_2_SELECTED_MANIFEST_SHA256
        and _is_hex(selected_identity_sha256, 64)
        and manifest_identity.get("exact_spool_catalog_sha256")
        == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
        observed_sha256=probe_manifest_sha256,
        expected_sha256=TASK040_V1_2_PROBE_MANIFEST_SHA256,
    )
    _record(
        checks,
        details,
        "input_hash",
        input_sha256 == TASK040_V1_2_INPUT_SHA256
        and run_summary.get("input_sha256") == input_sha256
        and identity.get("input_sha256") == input_sha256
        and manifest_identity.get("input_sha256") == input_sha256,
        path=str(input_path),
        observed_sha256=input_sha256,
        expected_sha256=TASK040_V1_2_INPUT_SHA256,
    )
    _record(
        checks,
        details,
        "selected_manifest_identity",
        manifest_identity.get("selected_manifest_sha256") == selected_manifest_sha256
        and identity.get("selected_manifest_sha256") == selected_manifest_sha256
        and identity.get("spool_packet_manifest_sha256") == selected_manifest_sha256
        and _is_hex(selected_identity_sha256, 64),
        observed_sha256=selected_manifest_sha256,
        selected_identity_sha256=selected_identity_sha256,
        expected_sha256=TASK040_V1_2_SELECTED_MANIFEST_SHA256,
    )
    _record(
        checks,
        details,
        "formal_identity",
        run_summary.get("schema") == TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_SCHEMA
        and run_summary.get("method") == TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD
        and run_summary.get("profile")
        == TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_PROFILE_ID
        and run_summary.get("source_sha") == formal_source_sha
        and watchdog.get("source_sha") == formal_source_sha
        and watchdog.get("method") == TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD,
        source_sha=identity.get("source_sha"),
        current_source_sha=identity.get("current_source_sha"),
        labels=identity.get("labels"),
    )
    _record(
        checks,
        details,
        "frozen_identity",
        run_summary.get("input_sha256") == TASK040_V1_2_INPUT_SHA256
        and run_summary.get("physical_model_sha256")
        == TASK040_V1_2_PHYSICAL_MODEL_SHA256
        and identity.get("input_sha256") == TASK040_V1_2_INPUT_SHA256
        and identity.get("physical_model_sha256") == TASK040_V1_2_PHYSICAL_MODEL_SHA256
        and identity.get("frozen_branch") == TASK040_V4_FROZEN_BRANCH
        and identity.get("task040_manifest_freeze_source_sha")
        == TASK040_V4_FROZEN_AUTHORITY_SOURCE_SHA
        and identity.get("probe_manifest_sha256") == TASK040_V1_2_PROBE_MANIFEST_SHA256
        and identity.get("selected_manifest_sha256")
        == TASK040_V1_2_SELECTED_MANIFEST_SHA256
        and identity.get("spool_packet_manifest_sha256")
        == TASK040_V1_2_SELECTED_MANIFEST_SHA256
        and identity.get("spool_catalog_sha256")
        == TASK040_V1_2_EXACT_SPOOL_CATALOG_SHA256,
    )
    packet_identity = identity.get("packet_identity")
    system_inventory = identity.get("system_inventory")
    _record(
        checks,
        details,
        "formal_identity_observed_contract",
        identity.get("source_sha") == formal_source_sha
        and identity.get("current_source_sha") == formal_source_sha
        and identity.get("labels") == list(V4_EXACT_AUTHORITY_LABELS)
        and identity.get("probe_authority") == physical_probes.get("probe_identities")
        and isinstance(packet_identity, Mapping)
        and _canonical_json_sha256(packet_identity) == selected_identity_sha256
        and isinstance(system_inventory, Mapping)
        and system_inventory.get("system_created") is False
        and system_inventory.get("explicit_bare_f_created") is False,
        packet_identity_sha256=(
            _canonical_json_sha256(packet_identity)
            if isinstance(packet_identity, Mapping)
            else None
        ),
        selected_identity_sha256=selected_identity_sha256,
    )
    command = watchdog.get("command")
    supplied_spool = exact_spool_root
    command_spool = _command_value(command, "--exact-spool-root")
    if supplied_spool is None:
        supplied_spool = command_spool
    if supplied_spool is None:
        raise ValueError("exact spool root is missing from CLI and watchdog command")
    supplied_spool_path = Path(supplied_spool).resolve()
    command_spool_path = Path(command_spool).resolve() if command_spool else None
    command_input_path = Path(input_arg).resolve()
    command_run_directory = _command_value(command, "--run-directory")
    command_memory_stages = _command_value(command, "--memory-stages")
    command_memory_markers = _command_value(command, "--memory-markers")
    command_values = (
        list(command)
        if isinstance(command, Sequence) and not isinstance(command, (str, bytes))
        else []
    )
    _record(
        checks,
        details,
        "formal_command_identity",
        _command_value(command, "-n") == "8"
        and _command_value(command, "--source-sha") == formal_source_sha
        and command_input_path == input_path
        and command_run_directory is not None
        and Path(command_run_directory).resolve() == (formal_root / "worker").resolve()
        and command_memory_stages is not None
        and Path(command_memory_stages).resolve() == stages_path.resolve()
        and command_memory_markers is not None
        and Path(command_memory_markers).resolve() == marker_path.resolve()
        and "--v4-exact-authority-compatibility" in command_values
        and command_spool_path == supplied_spool_path,
        command=command,
    )
    spool_root = _spool_path(supplied_spool_path)
    resolved_config_path = _resolved_config_path(supplied_spool_path, spool_root)
    resolved_config_sha256 = _sha256(resolved_config_path)
    _record(
        checks,
        details,
        "resolved_config_content_hash",
        identity.get("resolved_config_sha256") == resolved_config_sha256
        and manifest_identity.get("exact_spool_resolved_config_sha256")
        == resolved_config_sha256,
        observed=resolved_config_sha256,
        recorded=identity.get("resolved_config_sha256"),
    )
    records, spool_files = _spool_records(
        spool_root, V4_EXACT_AUTHORITY_LABELS, checks, details
    )
    canonical_missing, spool_summary = _check_spool_identity(
        records,
        V4_EXACT_AUTHORITY_LABELS,
        spool_root,
        identity,
        identity.get("source_canonical_authority", {}),
        probe_manifest,
        selected_manifest_sha256,
        selected_identity_sha256,
        checks,
        details,
    )
    source_canonical_missing = _check_source_canonical_authority(
        identity.get("source_canonical_authority"),
        V4_EXACT_AUTHORITY_LABELS,
        checks,
        details,
    )
    _record(
        checks,
        details,
        "canonical_source_binding_cross_reference",
        canonical_missing
        == source_canonical_missing
        == [
            f"{label}:{role}"
            for label in V4_EXACT_AUTHORITY_LABELS
            for role in ("rhs", "exact_output")
        ],
        spool_missing_entries=canonical_missing,
        source_missing_entries=source_canonical_missing,
    )
    expected_producer_identity = _producer_identity_summary(
        spool_summary["producer"], spool_summary["expected_producer_source_sha"]
    )
    _record(
        checks,
        details,
        "spool_producer_identity_cross_reference",
        identity.get("spool_producer_source_sha")
        == spool_summary["expected_producer_source_sha"]
        and identity.get("spool_producer_source_identity")
        == expected_producer_identity,
        observed=identity.get("spool_producer_source_identity"),
        expected=expected_producer_identity,
    )
    expected_identity_failures = ["canonical_source_binding"]
    raw_identity_checks = identity.get("identity_checks", {})
    expected_raw_checks = {
        "input_sha256": True,
        "physical_model_sha256": True,
        "frozen_branch": True,
        "freeze_source": True,
        "selected_manifest": True,
        "resolved_config": True,
        "packet_manifest": True,
        "spool_catalog": True,
        "spool_producer_source": True,
        "exact_output_metadata": True,
        "canonical_source_binding": False,
    }
    _record(
        checks,
        details,
        "raw_identity_failure_contract",
        isinstance(raw_identity_checks, Mapping)
        and set(raw_identity_checks) == set(EXPECTED_IDENTITY_CHECKS)
        and identity.get("identity_failures") == expected_identity_failures
        and identity.get("identity_checks_pass") is False
        and all(
            isinstance(raw_identity_checks.get(name), Mapping)
            and raw_identity_checks[name].get("pass") is expected
            for name, expected in expected_raw_checks.items()
        ),
        observed_failures=identity.get("identity_failures"),
        expected_failures=expected_identity_failures,
    )
    factor_inventory = run_summary.get("factor_inventory", {})
    exact_factor_inventory = exact_authority.get("factor_inventory", {})
    factor_keys = (
        "exact_output_vectors_loaded",
        "full_side_exact_factor_count",
        "global_direct_factor_count",
        "cross_section_group_factor_count",
        "reduced_dense_factor_count",
        "factor_objects_created",
    )
    exact_output_summary = spool_summary["exact_output"]
    exact_output_expected = {
        label: exact_output_summary[label]["expected"]
        for label in V4_EXACT_AUTHORITY_LABELS
    }
    exact_output_observed = {
        label: (
            exact_output_summary[label]["observed"][0]
            if len(exact_output_summary[label]["observed"]) == 1
            else None
        )
        for label in V4_EXACT_AUTHORITY_LABELS
    }
    exact_output_checks = {
        label: exact_output_summary[label]["checks"]
        for label in V4_EXACT_AUTHORITY_LABELS
    }
    exact_output_shard_counts = {
        label: exact_output_summary[label]["shard_counts"]
        for label in V4_EXACT_AUTHORITY_LABELS
    }
    expected_exact_output_metadata_identity = {
        "array_hash_validation_only": True,
        "checks": exact_output_checks,
        "expected": exact_output_expected,
        "expected_mpi_size": 8,
        "numeric_vectors_constructed": False,
        "observed": exact_output_observed,
        "pass": all(exact_output_checks.values())
        and all(value == 8 for value in exact_output_shard_counts.values()),
        "shard_counts": exact_output_shard_counts,
        "values_retained": False,
    }
    _record(
        checks,
        details,
        "exact_output_metadata_identity_contract",
        identity.get("exact_output_metadata_identity")
        == expected_exact_output_metadata_identity,
        observed=identity.get("exact_output_metadata_identity"),
        expected=expected_exact_output_metadata_identity,
    )
    resource_authority = run_summary.get("resource_authority")
    _record(
        checks,
        details,
        "run_summary_resource_authority_contract",
        isinstance(resource_authority, Mapping)
        and set(resource_authority)
        == {
            "status",
            "sample_count",
            "all_status_readable",
            "swap_authority_readable",
            "swap_zero_authoritative",
        }
        and resource_authority.get("status") == "not_run_by_identity_gate"
        and resource_authority.get("sample_count") == 0
        and resource_authority.get("all_status_readable") is None
        and resource_authority.get("swap_authority_readable") is None
        and resource_authority.get("swap_zero_authoritative") is None
        and run_summary.get("resource_samples") == {},
        resource_authority=resource_authority,
        resource_samples=run_summary.get("resource_samples"),
    )
    source_loading_keys = {
        "array_hash_validation_only",
        "canonical_reconstruction",
        "exact_output_metadata_hash_validation_only",
        "exact_output_vectors_loaded",
        "labels",
        "numeric_vectors_constructed",
        "raw_global_row_remap_used",
        "rhs_vectors_loaded",
        "values_retained",
    }
    _record(
        checks,
        details,
        "source_loading_contract",
        isinstance(source_loading, Mapping)
        and set(source_loading) == source_loading_keys
        and source_loading.get("labels") == list(V4_EXACT_AUTHORITY_LABELS)
        and source_loading.get("array_hash_validation_only") is True
        and source_loading.get("exact_output_metadata_hash_validation_only") is True
        and source_loading.get("rhs_vectors_loaded") == 0
        and source_loading.get("exact_output_vectors_loaded") == 0
        and source_loading.get("numeric_vectors_constructed") is False
        and source_loading.get("values_retained") is False
        and source_loading.get("raw_global_row_remap_used") is False
        and source_loading.get("canonical_reconstruction")
        == "not_run_by_identity_gate",
    )
    construction_keys = {
        "explicit_bare_f_created",
        "interface_masses_built",
        "pde_solved",
        "qep_called",
        "system_created",
    }
    _record(
        checks,
        details,
        "construction_contract",
        isinstance(construction, Mapping)
        and set(construction) == construction_keys
        and all(construction.get(key) is False for key in construction_keys),
    )
    exact_cleanup = exact_authority.get("cleanup", {})
    exact_factor_inventory = exact_authority.get("factor_inventory", {})
    _record(
        checks,
        details,
        "exact_authority_lifecycle_contract",
        exact_authority.get("classification") == EXPECTED_CLASSIFICATION
        and exact_authority.get("failure_code") == EXPECTED_FAILURE_CODE
        and exact_authority.get("failure_reason") == EXPECTED_FAILURE_REASON
        and exact_authority.get("identity_pass") is False
        and exact_authority.get("gate_pass") is False
        and exact_authority.get("labels") == list(V4_EXACT_AUTHORITY_LABELS)
        and exact_authority.get("qep_calls") == 0
        and exact_authority.get("pde_solve") == "not_run"
        and exact_authority.get("exact_output_vectors_loaded") == 0
        and exact_authority.get("reports") == []
        and exact_authority.get("residual_status") == "not_run_by_identity_gate"
        and exact_authority.get("bare_f_residual") == "not_run_by_identity_gate"
        and exact_authority.get("a_side_explanatory_residual")
        == "not_run_by_identity_gate"
        and exact_authority.get("finite_pass") is None
        and exact_authority.get("repeat_pass") is None
        and exact_authority.get("bare_f_residual_pass") is None
        and exact_authority.get("bare_f_hash_unchanged_pass") is None
        and all(exact_factor_inventory.get(key) == 0 for key in factor_keys)
        and exact_cleanup.get("factor_objects_created") == 0
        and exact_cleanup.get("interface_masses_built") is False
        and exact_cleanup.get("packet_built") is False,
    )
    _record(
        checks,
        details,
        "factor_inventory_contract",
        isinstance(factor_inventory, Mapping)
        and set(factor_inventory) == set(factor_keys)
        and all(factor_inventory.get(key) == 0 for key in factor_keys)
        and isinstance(exact_factor_inventory, Mapping)
        and set(exact_factor_inventory) == set(factor_keys)
        and all(exact_factor_inventory.get(key) == 0 for key in factor_keys),
        root_keys=sorted(factor_inventory)
        if isinstance(factor_inventory, Mapping)
        else None,
        exact_keys=(
            sorted(exact_factor_inventory)
            if isinstance(exact_factor_inventory, Mapping)
            else None
        ),
    )
    _record(
        checks,
        details,
        "identity_stop_contract",
        run_summary.get("classification") == EXPECTED_CLASSIFICATION
        and run_summary.get("identity_failure_code") == EXPECTED_FAILURE_CODE
        and run_summary.get("identity_failure_reason") == EXPECTED_FAILURE_REASON
        and run_summary.get("identity_pass") is False
        and run_summary.get("gate_pass") is False
        and run_summary.get("residual_status") == "not_run_by_identity_gate"
        and run_summary.get("numerical_gate_pass") is None
        and exact_authority.get("reports") == []
        and exact_authority.get("residual_status") == "not_run_by_identity_gate"
        and exact_authority.get("bare_f_residual") == "not_run_by_identity_gate"
        and exact_authority.get("a_side_explanatory_residual")
        == "not_run_by_identity_gate"
        and exact_authority.get("numerical_gate_pass") is None
        and source_loading.get("rhs_vectors_loaded") == 0
        and source_loading.get("exact_output_vectors_loaded") == 0
        and source_loading.get("numeric_vectors_constructed") is False
        and source_loading.get("values_retained") is False
        and source_loading.get("raw_global_row_remap_used") is False
        and construction.get("system_created") is False
        and construction.get("explicit_bare_f_created") is False
        and construction.get("interface_masses_built") is False
        and set(factor_inventory) == set(factor_keys)
        and set(exact_factor_inventory) == set(factor_keys)
        and all(factor_inventory.get(key) == 0 for key in factor_keys)
        and all(exact_factor_inventory.get(key) == 0 for key in factor_keys)
        and run_summary.get("qep_calls") == 0
        and run_summary.get("pde_solve") == "not_run"
        and identity.get("spool_producer_source_sha")
        == spool_summary["expected_producer_source_sha"]
        and identity.get("labels") == list(V4_EXACT_AUTHORITY_LABELS)
        and set(run_summary.get("not_run_by_gate", {})) == set(EXPECTED_DOWNSTREAM)
        and set(exact_authority.get("downstream", {})) == set(EXPECTED_DOWNSTREAM)
        and all(
            run_summary.get("not_run_by_gate", {}).get(key) == "not_run_by_gate"
            for key in EXPECTED_DOWNSTREAM
        )
        and all(
            exact_authority.get("downstream", {}).get(key) == "not_run_by_gate"
            for key in EXPECTED_DOWNSTREAM
        ),
    )
    marker_contract = (
        [row.get("stage") for row in marker_rows] == list(EXPECTED_MARKERS)
        and [row.get("stage") for row in stage_rows] == list(EXPECTED_MARKERS)
        and marker_rows[0].get("detail")
        == {"method": TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD}
        and marker_rows[1].get("detail")
        == {
            "array_hash_validation_only": True,
            "failure_code": EXPECTED_FAILURE_CODE,
            "numeric_vectors_constructed": False,
            "residual_status": "not_run_by_identity_gate",
            "system_created": False,
            "values_retained": False,
        }
        and stage_rows[0].get("status") == "running"
        and stage_rows[0].get("method")
        == TASK040_V4_EXACT_AUTHORITY_COMPATIBILITY_METHOD
        and stage_rows[1].get("status") == "complete"
        and stage_rows[1].get("array_hash_validation_only") is True
        and stage_rows[1].get("failure_code") == EXPECTED_FAILURE_CODE
        and stage_rows[1].get("numeric_vectors_constructed") is False
        and stage_rows[1].get("residual_status") == "not_run_by_identity_gate"
        and stage_rows[1].get("system_created") is False
        and stage_rows[1].get("values_retained") is False
    )
    _record(
        checks,
        details,
        "marker_contract",
        marker_contract,
        marker_stages=[row.get("stage") for row in marker_rows],
        stage_stages=[row.get("stage") for row in stage_rows],
    )
    _record(checks, details, "worker_stdout_contract", stdout == "")
    _check_watchdog(
        formal_root, watchdog, run_summary_path, process_rows, checks, details
    )
    formal_hashes = {str(path.resolve()): _sha256(path) for path in formal_paths}
    all_hashes = formal_hashes | {path: _sha256(Path(path)) for path in spool_files}
    all_hashes[str(resolved_config_path.resolve())] = resolved_config_sha256
    all_hashes[str(input_path)] = input_sha256
    all_hashes[str(probe_manifest_path.resolve())] = probe_manifest_sha256
    evidence_valid = all(checks.values())
    classification = (
        EXPECTED_CLASSIFICATION if evidence_valid else IMPLEMENTATION_FAILURE
    )
    return {
        "schema": "task040.v4.exact_authority.raw_checker.v1",
        "checker_source_sha": checker_source_sha,
        "formal_source_sha": formal_source_sha,
        "formal_root": str(formal_root),
        "exact_spool_root": str(spool_root),
        "evidence_valid": evidence_valid,
        "gate_pass": False,
        "classification": classification,
        "checker_pass": evidence_valid,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "details": {
            **details,
            "canonical_missing_entries": canonical_missing,
            "formal_file_count": len(formal_paths),
            "spool_json_file_count": len(spool_files),
        },
        "read_files": [
            {"path": path, "sha256": digest}
            for path, digest in sorted(all_hashes.items())
        ],
    }


def _write_json_atomically(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, sort_keys=True, indent=2)
        stream.write("\n")
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-root", required=True, type=Path)
    parser.add_argument("--exact-spool-root", type=Path)
    parser.add_argument("--formal-source-sha", required=True)
    parser.add_argument("--checker-source-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = check_v4_exact_authority(
            args.formal_root,
            args.formal_source_sha,
            args.checker_source_sha,
            exact_spool_root=args.exact_spool_root,
        )
    except (
        AttributeError,
        LookupError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        report = {
            "schema": "task040.v4.exact_authority.raw_checker.v1",
            "checker_source_sha": args.checker_source_sha,
            "formal_source_sha": args.formal_source_sha,
            "evidence_valid": False,
            "gate_pass": False,
            "classification": IMPLEMENTATION_FAILURE,
            "checker_pass": False,
            "checks": {},
            "failures": ["checker_exception"],
            "error": f"{type(exc).__name__}: {exc}",
            "read_files": [],
        }
    _write_json_atomically(args.output, report)
    return 0 if report["checker_pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
