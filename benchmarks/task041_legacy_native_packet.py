"""Explicit read-only bridge for the approved native Task039 V4 packet."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmarks.task039_v4_selected_mode_packet import (
    TASK039_V4_SELECTED_MODE_SCOPE,
    _require_task039_identity,
)
from benchmarks.task041_balh_workflow import (
    _physical_contract,
    _valid_sha,
)
from src.io.input_validation import TASK041_BALH_MPI_SIZE, task041_balh_case
from src.io.resolved_config import resolved_config_sha256

TASK041_LEGACY_NATIVE_PACKET_DESCRIPTOR_SCHEMA = (
    "task041.h3.legacy_native_packet_descriptor.v1"
)
TASK041_LEGACY_NATIVE_PACKET_ORIGIN = "task039.v4.h4.legacy_native"
TASK039_V4_H4_IDENTITY_SCHEMA = "task039.v4.h4.mode-identity.v1"
TASK039_V4_H4_MODEL_ID = "task039_5nm_v4_1deg_s5_hybrid_direct_m480"
TASK039_V4_H4_RUN_ID = "task039_v4_hybrid_direct_p6h4_m480_mpi8"
TASK039_V4_H4_SOURCE_SHA = "b01a5932e4dfaf895e81e0424e0dd88c276fb0d3"
TASK039_V4_H4_INPUT_SHA256 = (
    "dd7c945c1696b4f9da3e35c295071a24b796a10d164d2a819b4abe68f72f44ca"
)
TASK039_V4_H4_RESOLVED_SHA256 = (
    "80ce8af49e59df65b462d71a23a29d99e07a4fd77862e57b5efed4b659919b70"
)
TASK039_V4_H4_PHYSICAL_SHA256 = (
    "8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c"
)
TASK039_V4_H4_MANIFEST_SHA256 = (
    "306939dda3b70777204c11fbd65beac2db5dc0637bc9b6803f7794d0d7cbad2f"
)
TASK039_V4_H4_EXTERNAL_SHA256 = (
    "ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a"
)
TASK039_V4_H4_MODE_COUNT = 480
TASK039_V4_H4_GLOBAL_SIZE = 11605


class Task041LegacyNativePacketError(ValueError):
    """The explicitly requested native packet cannot be imported."""


def task041_legacy_native_profile(specification: Any) -> bool:
    """Return whether a current specification may use the explicit bridge."""

    normalized = specification.as_jsonable()
    case = task041_balh_case(str(normalized.get("model_id", "")))
    discretization = normalized.get("discretization")
    execution = normalized.get("execution")
    return bool(
        case is not None
        and case.get("wavelength_nm") == 5.0
        and case.get("mode_count") == TASK039_V4_H4_MODE_COUNT
        and isinstance(discretization, Mapping)
        and discretization.get("nedelec_degree") == 6
        and discretization.get("mesh_target_nm") == 4.0
        and isinstance(execution, Mapping)
        and execution.get("mpi_size") == TASK041_BALH_MPI_SIZE
    )


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task041LegacyNativePacketError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, Mapping):
        raise Task041LegacyNativePacketError(f"{label} is not a JSON object: {path}")
    return dict(value)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Task041LegacyNativePacketError(f"cannot hash artifact: {path}") from exc


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}


def _digest(value: Any, length: int, label: str) -> str:
    if not _valid_sha(value, length):
        raise Task041LegacyNativePacketError(f"{label} is not a valid SHA")
    return str(value)


def _descriptor_paths(
    descriptor: Mapping[str, Any],
    descriptor_path: Path,
    *,
    full_artifacts: bool = True,
) -> dict[str, Path]:
    packet_root_value = descriptor.get("packet_root")
    identity_value = descriptor.get("identity_path")
    producer_root_value = descriptor.get("producer_root")
    if not all(
        isinstance(value, str) and Path(value).is_absolute()
        for value in (packet_root_value, identity_value, producer_root_value)
    ):
        raise Task041LegacyNativePacketError(
            "legacy descriptor requires absolute packet, identity, and producer paths"
        )
    packet_root = Path(packet_root_value).resolve()
    identity_path = Path(identity_value).resolve()
    producer_root = Path(producer_root_value).resolve()
    if not packet_root.is_dir() or not identity_path.is_file() or not producer_root.is_dir():
        raise Task041LegacyNativePacketError("legacy packet, identity, or producer is missing")
    producer_files = {
        "run_manifest": producer_root / "run_manifest.json",
        "run_summary": producer_root / "run_summary.json",
        "numeric_summary": producer_root / "numerical_output" / "run_summary.json",
        "resolved_config": producer_root / "resolved_config.json",
        "input": producer_root / "input_original.dat",
        "source_record": producer_root / "source_sha.txt",
        "input_record": producer_root / "input_sha256.txt",
        "physical_record": producer_root / "physical_model_sha256.txt",
        "process_samples": producer_root / "numerical_output" / "process_tree_samples.jsonl",
    }
    paths = {
        "descriptor": descriptor_path,
        "packet_root": packet_root,
        "manifest": packet_root / "manifest.json",
        "identity": identity_path,
        "producer_root": producer_root,
        **producer_files,
    }
    for name, path in paths.items():
        if not full_artifacts and name not in {
            "descriptor",
            "packet_root",
            "manifest",
            "identity",
            "producer_root",
            "resolved_config",
        }:
            continue
        if name not in {"descriptor", "packet_root", "producer_root"} and not path.is_file():
            raise Task041LegacyNativePacketError(f"legacy artifact is missing: {name}")
    artifact_hashes = descriptor.get("artifact_sha256")
    if not isinstance(artifact_hashes, Mapping):
        raise Task041LegacyNativePacketError("legacy artifact hashes are missing")
    expected_names = {"packet_manifest", "packet_identity", *producer_files}
    if set(artifact_hashes) != expected_names:
        raise Task041LegacyNativePacketError("legacy descriptor artifact hash set is invalid")
    artifact_pairs = (
        ("packet_manifest", "manifest"),
        ("packet_identity", "identity"),
        *((name, name) for name in producer_files),
    )
    for name, path_name in artifact_pairs:
        if not full_artifacts and name not in {
            "packet_manifest",
            "packet_identity",
            "resolved_config",
        }:
            continue
        expected = _digest(artifact_hashes.get(name), 64, f"artifact_sha256.{name}")
        if _sha256(paths[path_name]) != expected:
            raise Task041LegacyNativePacketError(f"legacy artifact hash does not match: {name}")
    return paths


def _physical_binding(
    producer_resolved: Mapping[str, Any], consumer_normalized: Mapping[str, Any]
) -> dict[str, Any]:
    producer_contract = _physical_contract(producer_resolved)
    consumer_contract = _physical_contract(consumer_normalized)
    producer_materials = dict(producer_contract["materials"])
    consumer_materials = dict(consumer_contract["materials"])
    labels = {
        name: {
            "producer": producer_materials[name],
            "consumer": consumer_materials[name],
        }
        for name in ("substrate_name", "grating_name")
    }
    for name in labels:
        producer_materials.pop(name)
        consumer_materials.pop(name)
    checks = {
        section: (
            producer_contract[section] == consumer_contract[section]
            if section != "materials"
            else producer_materials == consumer_materials
        )
        for section in producer_contract
    }
    return {
        "pass": all(checks.values()),
        "sections": checks,
        "ignored_material_labels": labels,
        "producer_physical_contract": producer_contract,
        "consumer_physical_contract": consumer_contract,
    }


def _consumer_identity(
    specification: Any, normalized: Mapping[str, Any], source_sha: str
) -> dict[str, Any]:
    from benchmarks.task041_balh_workflow import build_task041_balh_packet_identity

    return build_task041_balh_packet_identity(
        specification,
        normalized,
        source_sha,
        resolved_config_sha256(specification),
    )


def _resource_evidence(
    run_manifest: Mapping[str, Any], samples_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recompute the historical worker-tree RSS/swap peak from raw samples."""

    count = 0
    peak_rss = 0
    peak_swap = 0
    phase_wall: float | None = None
    try:
        with samples_path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                if not isinstance(row, Mapping):
                    continue
                count += 1
                rss = row.get("rss_bytes")
                swap = row.get("swap_bytes")
                if type(rss) is int and rss >= 0:
                    peak_rss = max(peak_rss, rss)
                if type(swap) is int and swap >= 0:
                    peak_swap = max(peak_swap, swap)
                elapsed = row.get("elapsed_seconds")
                if isinstance(elapsed, (int, float)) and float(elapsed) >= 0.0:
                    phase_wall = float(elapsed)
    except (OSError, json.JSONDecodeError) as exc:
        raise Task041LegacyNativePacketError(
            "legacy producer process samples are unreadable"
        ) from exc
    if count == 0 or phase_wall is None:
        raise Task041LegacyNativePacketError("legacy producer raw resource samples are incomplete")
    derived_interval: float | None = None
    try:
        start = datetime.fromisoformat(str(run_manifest["start_time"]))
        end = datetime.fromisoformat(str(run_manifest["end_time"]))
        derived_interval = (end - start).total_seconds()
    except (KeyError, TypeError, ValueError):
        pass
    phase = {
        "phase": "producer",
        "status": "inherited_legacy_native",
        "phase_invocation": "not_run_in_current_invocation",
        "reused": True,
        "returncode": 0,
        "process_group_gone": None,
        "historical_lifecycle": "finished_exit0; public process-group record unavailable",
        "termination_reason": None,
        "sample_count": count,
        "phase_wall_seconds": phase_wall,
        "whole_job_wall_seconds": derived_interval,
        "whole_job_wall_status": "derived_from_run_manifest_times",
        "worker_tree": {
            "peak_rss_bytes": peak_rss,
            "peak_swap_bytes": peak_swap,
            "sample_count": count,
            "phase_wall_seconds": phase_wall,
            "raw_samples": _artifact(samples_path),
        },
        "peak_memory_authority_bytes": None,
        "peak_process_tree_rss_bytes": None,
        "peak_pss_bytes": None,
        "peak_uss_bytes": None,
        "peak_process_tree_swap_bytes": None,
        "peak_dedicated_cgroup_swap_bytes": None,
        "peak_swap_bytes": None,
        "producer_resource_qualified": False,
        "resource_qualification_status": "unqualified_public_parent_not_measured",
        "resource_source": "legacy_producer_worker_tree_raw_samples",
        "raw_samples_path": str(samples_path),
        "raw_samples_sha256": _sha256(samples_path),
        "public_parent_rss_bytes": None,
        "public_parent_rss_status": "not_measured",
        "cgroup_reserve_status": "not_measured",
        "global_swap_delta_status": "not_measured",
    }
    evidence = {
        "status": "unqualified",
        "resource_qualified": False,
        "worker_tree": {
            "peak_rss_bytes": peak_rss,
            "peak_swap_bytes": peak_swap,
            "sample_count": count,
            "phase_wall_seconds": phase_wall,
            "raw_samples": _artifact(samples_path),
        },
        "whole_job_wall_seconds": derived_interval,
        "whole_job_wall_status": "derived_from_run_manifest_times",
        "public_parent_rss": {"status": "not_measured", "bytes": None},
        "pss_uss": {"status": "not_measured", "pss_bytes": None, "uss_bytes": None},
        "cgroup_and_global_swap": {
            "status": "not_measured",
            "worker_tree_swap_bytes": peak_swap,
        },
        "reason": "historical producer sampled worker tree, not public parent/cgroup",
    }
    return phase, evidence


def _validate_descriptor(
    descriptor_path: Path,
    *,
    full_artifacts: bool = True,
) -> tuple[dict[str, Any], dict[str, Path]]:
    descriptor = _read_json(descriptor_path, "legacy packet descriptor")
    if descriptor.get("schema") != TASK041_LEGACY_NATIVE_PACKET_DESCRIPTOR_SCHEMA:
        raise Task041LegacyNativePacketError("legacy packet descriptor schema is unsupported")
    if descriptor.get("origin") != TASK041_LEGACY_NATIVE_PACKET_ORIGIN:
        raise Task041LegacyNativePacketError("legacy packet descriptor origin is unsupported")
    return descriptor, _descriptor_paths(
        descriptor,
        descriptor_path,
        full_artifacts=full_artifacts,
    )


def _validate_packet_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path, "legacy packet manifest")
    shards = manifest.get("shards")
    if not isinstance(shards, list):
        raise Task041LegacyNativePacketError("legacy packet shards are missing")
    ranges: list[tuple[int, int]] = []
    descriptor_count = 0
    for shard in shards:
        if not isinstance(shard, Mapping):
            raise Task041LegacyNativePacketError("legacy packet shard is invalid")
        ownership = shard.get("ownership_range")
        files = shard.get("files")
        if not isinstance(ownership, list) or len(ownership) != 2 or not isinstance(files, Mapping):
            raise Task041LegacyNativePacketError("legacy packet shard descriptors are missing")
        ranges.append((ownership[0], ownership[1]))
        for array_descriptor in files.values():
            if not isinstance(array_descriptor, Mapping):
                raise Task041LegacyNativePacketError("legacy packet array descriptor is invalid")
            relative = array_descriptor.get("path")
            if not isinstance(relative, str) or not relative:
                raise Task041LegacyNativePacketError("legacy packet array path is missing")
            path = (manifest_path.parent / relative).resolve()
            if _sha256(path) != array_descriptor.get("sha256"):
                raise Task041LegacyNativePacketError("legacy packet array hash/path mismatch")
            descriptor_count += 1
    if descriptor_count != 32:
        raise Task041LegacyNativePacketError("legacy packet does not contain 32 array descriptors")
    return {
        "global_size": manifest.get("global_size"),
        "mode_count": manifest.get("mode_count"),
        "rank_count": manifest.get("rank_count"),
        "owner_ranges": [list(value) for value in ranges],
        "array_descriptor_count": descriptor_count,
    }


def validate_task041_legacy_native_packet(
    descriptor_path: str | Path,
    specification: Any,
    consumer_source_sha: str,
) -> dict[str, Any]:
    """Validate the approved packet and bind it to one current consumer."""

    descriptor_file = Path(descriptor_path).resolve()
    _descriptor, paths = _validate_descriptor(descriptor_file)
    packet_identity = _read_json(paths["identity"], "legacy packet identity")
    if packet_identity.get("schema") != TASK039_V4_H4_IDENTITY_SCHEMA:
        raise Task041LegacyNativePacketError("legacy packet identity schema is unsupported")
    _require_task039_identity(packet_identity)
    expected_identity = {
        "scope": TASK039_V4_SELECTED_MODE_SCOPE,
        "source_sha": TASK039_V4_H4_SOURCE_SHA,
        "input_sha256": TASK039_V4_H4_INPUT_SHA256,
        "resolved_sha256": TASK039_V4_H4_RESOLVED_SHA256,
        "physical_sha256": TASK039_V4_H4_PHYSICAL_SHA256,
        "model_id": TASK039_V4_H4_MODEL_ID,
        "run_id": TASK039_V4_H4_RUN_ID,
        "mode_count": TASK039_V4_H4_MODE_COUNT,
        "mpi_size": TASK041_BALH_MPI_SIZE,
    }
    if any(packet_identity.get(key) != value for key, value in expected_identity.items()):
        raise Task041LegacyNativePacketError("legacy packet is not the approved 5 nm identity")
    if packet_identity.get("external_keys") != {
        "count": 600,
        "sha256": TASK039_V4_H4_EXTERNAL_SHA256,
    }:
        raise Task041LegacyNativePacketError("legacy packet external identity is invalid")
    if _sha256(paths["manifest"]) != TASK039_V4_H4_MANIFEST_SHA256:
        raise Task041LegacyNativePacketError("legacy packet manifest hash is not approved")
    packet_layout = _validate_packet_manifest(paths["manifest"])

    producer_manifest = _read_json(paths["run_manifest"], "legacy producer run_manifest")
    producer_summary = _read_json(paths["run_summary"], "legacy producer run_summary")
    numeric_summary = _read_json(paths["numeric_summary"], "legacy producer numeric summary")
    resolved_config = _read_json(paths["resolved_config"], "legacy producer resolved_config")
    if _sha256(paths["resolved_config"]) != TASK039_V4_H4_RESOLVED_SHA256:
        raise Task041LegacyNativePacketError("legacy producer resolved config hash mismatch")
    if _sha256(paths["input"]) != TASK039_V4_H4_INPUT_SHA256:
        raise Task041LegacyNativePacketError("legacy producer input bytes hash mismatch")
    for path, expected in (
        (paths["source_record"], TASK039_V4_H4_SOURCE_SHA),
        (paths["input_record"], TASK039_V4_H4_INPUT_SHA256),
        (paths["physical_record"], TASK039_V4_H4_PHYSICAL_SHA256),
    ):
        if path.read_text(encoding="utf-8").strip() != expected:
            raise Task041LegacyNativePacketError(f"legacy producer identity record mismatch: {path}")
    producer_fields = (
        ("source_sha", "source_sha"),
        ("input_sha256", "input_sha256"),
        ("resolved_config_sha256", "resolved_sha256"),
        ("physical_model_sha256", "physical_sha256"),
        ("model_id", "model_id"),
        ("run_id", "run_id"),
        ("requested_modes", "mode_count"),
        ("mpi_size", "mpi_size"),
    )
    if any(
        producer_manifest.get(old) != packet_identity.get(new)
        for old, new in producer_fields
    ):
        raise Task041LegacyNativePacketError("legacy producer run manifest identity mismatch")
    if producer_manifest.get("status") != "finished" or producer_manifest.get("exit_status") != 0:
        raise Task041LegacyNativePacketError("legacy producer run did not finish with exit_status=0")
    if producer_summary.get("status") != "finished" or producer_summary.get("exit_status") != 0:
        raise Task041LegacyNativePacketError("legacy producer resource summary is not finished")
    numeric_packet = numeric_summary.get("packet")
    if (
        not isinstance(numeric_packet, Mapping)
        or Path(str(numeric_packet.get("manifest", ""))).resolve() != paths["manifest"]
        or numeric_packet.get("manifest_sha256") != TASK039_V4_H4_MANIFEST_SHA256
        or numeric_summary.get("status") != "controlled_stop_packet_written"
    ):
        raise Task041LegacyNativePacketError("legacy producer packet handoff is not bound")

    normalized = specification.as_jsonable()
    if not task041_legacy_native_profile(specification) or not _valid_sha(consumer_source_sha, 40):
        raise Task041LegacyNativePacketError(
            "legacy native import requires the Task041 5 nm M480 MPI8 profile"
        )
    physical = _physical_binding(resolved_config, normalized)
    consumer_identity = _consumer_identity(specification, normalized, consumer_source_sha)
    external = packet_identity["external_keys"]
    external_match = consumer_identity["external_keys"] == external
    binding = {
        "schema": "task041.side_balh.legacy_native_binding.v1",
        "origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        "pass": bool(physical["pass"] and external_match),
        "producer_identity": dict(packet_identity),
        "consumer_identity": consumer_identity,
        "physical_equivalence": physical,
        "external_keys": {
            "producer": external,
            "consumer": consumer_identity["external_keys"],
            "pass": external_match,
        },
        "descriptor": _artifact(descriptor_file),
    }
    if not binding["pass"]:
        raise Task041LegacyNativePacketError("legacy packet/current Task041 binding failed")
    phase, resource = _resource_evidence(producer_manifest, paths["process_samples"])
    compact_manifest = {
        "schema": "task041.public.selected_mode_manifest.v1",
        "packet_origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        "path": str(paths["manifest"]),
        "sha256": TASK039_V4_H4_MANIFEST_SHA256,
        "identity": dict(packet_identity),
        "legacy_binding": binding,
    }
    return {
        "summary": {
            "status": numeric_summary.get("status"),
            "packet": dict(numeric_packet),
        },
        "identity": dict(packet_identity),
        "identity_path": str(paths["identity"]),
        "manifest": str(paths["manifest"]),
        "manifest_sha256": TASK039_V4_H4_MANIFEST_SHA256,
        "packet_root": str(paths["packet_root"]),
        "producer_root": str(paths["producer_root"]),
        "compact_manifest": compact_manifest,
        "packet_origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        "legacy_native_binding": str(descriptor_file),
        "producer_source_sha": TASK039_V4_H4_SOURCE_SHA,
        "consumer_binding": binding,
        "legacy_binding": binding,
        "producer_phase": phase,
        "producer_resource": resource,
        "producer_resource_qualified": False,
        "producer_supervisor_summary": None,
        "producer_supervisor_summary_sha256": None,
        "packet_layout": packet_layout,
        "descriptor": _artifact(descriptor_file),
    }


def bind_task041_legacy_native_consumer(
    producer_identity: Mapping[str, Any],
    specification: Any,
    consumer_source_sha: str,
    descriptor_path: str | Path,
) -> dict[str, Any]:
    """Recheck worker binding without rehashing the packet's 32 arrays."""

    _descriptor, paths = _validate_descriptor(
        Path(descriptor_path).resolve(), full_artifacts=False
    )
    identity = _read_json(paths["identity"], "legacy packet identity")
    if dict(identity) != dict(producer_identity):
        raise Task041LegacyNativePacketError("worker packet identity differs from descriptor")
    if _sha256(paths["resolved_config"]) != identity.get("resolved_sha256"):
        raise Task041LegacyNativePacketError("worker legacy resolved config hash mismatch")
    normalized = specification.as_jsonable()
    physical = _physical_binding(
        _read_json(paths["resolved_config"], "legacy producer resolved config"), normalized
    )
    consumer_identity = _consumer_identity(specification, normalized, consumer_source_sha)
    if not physical["pass"] or consumer_identity["external_keys"] != identity.get("external_keys"):
        raise Task041LegacyNativePacketError("worker legacy packet binding failed")
    return {
        "schema": "task041.side_balh.legacy_native_binding.v1",
        "origin": TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        "pass": True,
        "producer_identity": dict(identity),
        "consumer_identity": consumer_identity,
        "physical_equivalence": physical,
        "external_keys": {
            "producer": identity["external_keys"],
            "consumer": consumer_identity["external_keys"],
            "pass": True,
        },
        "descriptor": _artifact(Path(descriptor_path).resolve()),
    }


__all__ = [
    "TASK039_V4_H4_EXTERNAL_SHA256",
    "TASK039_V4_H4_IDENTITY_SCHEMA",
    "TASK039_V4_H4_MANIFEST_SHA256",
    "TASK039_V4_H4_MODE_COUNT",
    "TASK039_V4_H4_RUN_ID",
    "TASK041_LEGACY_NATIVE_PACKET_DESCRIPTOR_SCHEMA",
    "TASK041_LEGACY_NATIVE_PACKET_ORIGIN",
    "Task041LegacyNativePacketError",
    "bind_task041_legacy_native_consumer",
    "task041_legacy_native_profile",
    "validate_task041_legacy_native_packet",
]
