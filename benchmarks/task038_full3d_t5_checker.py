"""Pure checker for the T5 authority bridge.

This module deliberately imports only the standard library and NumPy.  It
does not import a worker, solver, PETSc, MPI, or any production action.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np


T5_SCHEMA = "task038.full3d.iterative.t5.authority-record.v1"
T5_CHECK_SCHEMA = "task038.full3d.iterative.t5.authority-check.v1"
T5_PROFILE = "full3d_scalable_v1"
T5_ACTION_LIMIT = 1.0e-11
T5_CANONICAL_LIMIT = 1.0e-12
T5_PROCESS_TREE_CEILING_BYTES = 6 * 1024**3
T5_HARD_STOP_BYTES = 12 * 1024**3
T5_ROW_WITNESS_SCHEMA = "task038.t5.row-layout-manifest.v1"
T5_ROW_SHARD_SCHEMA = "task038.t5.row-layout-shard.v1"
T5_ROW_WITNESS_FIELDS = (
    "block_kind",
    "physical_key",
    "ordered_global_row_ids",
    "active_global_row_ids",
    "slave_global_row_ids",
    "slave_exclusion",
    "orientation_state",
    "orientation_transform_sha256",
    "mpc_relation_digest",
)
T5_MESH_IDENTITY_FIELDS = (
    "cell_type",
    "cells_global",
    "vertices_global",
    "geometry_shape",
    "canonical_connectivity_sha256",
    "canonical_geometry_sha256",
    "axis_counts",
    "digest_algorithm",
)

OLD_SOURCE_SHA = "41cbbd454eb8336d9ea5378ed618447acfc60aac"
OLD_ARRAY_FACTS = {
    "rhs": {
        "file_sha256": "caf87001775247cb6967d6ebb244c8eb646bcd0d71c6e77410cd091488b1b87f",
        "array_sha256": "31384363d498673ab5e30a26d47042581756ecabfc0efe3dba7a956b3600c20f",
    },
    "outer_action": {
        "file_sha256": "f2605312bf172f91ad13d3a9855ed006b87419be9392f6dbef24c17b51b41de2",
        "array_sha256": "8adcfe14349403a5233a18b982e0490721d5ecbb4364757db2b7265c38e56108",
    },
    "solution": {
        "file_sha256": "d2a5a7e7b94a73d5212bc693d43282cace2883aadd0bb66780a3f8ae7b9e535e",
        "array_sha256": "620b5e496536d69c0bc471731b09a15424c29044e6836881ccd85340cbee0c39",
    },
    "residual": {
        "file_sha256": "4166665f2e3c302f0645d9581856ec1bc433de4679540e45f98eb1e161093cc6",
        "array_sha256": "35de8f03a1fdf4c410cff33ceee44a31831df418443c7534650308505114de98",
    },
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _key_from_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        if set(value) != {"tuple"} or not isinstance(value["tuple"], list):
            raise ValueError("canonical key tuple encoding is invalid")
        return tuple(_key_from_jsonable(item) for item in value["tuple"])
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError("canonical key JSON value is invalid")


def _key_jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"tuple": [_key_jsonable(item) for item in value]}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported canonical key value: {type(value).__name__}")


def _canonical_key_json_bytes(key: Any) -> bytes:
    return json.dumps(
        _key_jsonable(key),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("artifact path is not a relative string")
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def _artifact_path(root: Path, value: Any) -> Path:
    if isinstance(value, str) and Path(value).is_absolute():
        return Path(value)
    return _safe_path(root, value)


def _read_packet_shard(path: Path, expected_sha256: str | None = None):
    digest = hashlib.sha256()
    packets: dict[Any, complex] = {}
    duplicate_count = 0
    with path.open("rb") as stream:
        for raw_line in stream:
            digest.update(raw_line)
            row = json.loads(raw_line)
            if row.get("schema_version") != "task037.canonical-vector-shard.v1":
                raise ValueError("canonical packet shard schema mismatch")
            key = _key_from_jsonable(row.get("key"))
            key_bytes = _canonical_key_json_bytes(key)
            if row.get("key_sha256") != hashlib.sha256(key_bytes).hexdigest():
                raise ValueError("canonical key SHA mismatch")
            value = row.get("value")
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("canonical value encoding mismatch")
            coefficient = complex(float(value[0]), float(value[1]))
            if not math.isfinite(coefficient.real) or not math.isfinite(
                coefficient.imag
            ):
                raise ValueError("canonical packet value is non-finite")
            if key in packets:
                duplicate_count += 1
            packets[key] = coefficient
    actual_sha256 = digest.hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError("canonical packet shard SHA mismatch")
    return packets, {
        "file_sha256": actual_sha256,
        "packet_count": len(packets) + duplicate_count,
        "duplicate_count": duplicate_count,
        "finite": True,
    }


def _read_packet_manifest(path: Path) -> tuple[dict[Any, complex], dict[str, Any]]:
    manifest_sha = _sha256_path(path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "task037.canonical-vector-manifest.v1":
        raise ValueError("canonical packet manifest schema mismatch")
    packets: dict[Any, complex] = {}
    shard_facts = []
    duplicate_count = 0
    for shard in manifest.get("per_rank_shards", []):
        shard_path = path.parent / shard["filename"]
        local, facts = _read_packet_shard(shard_path, shard.get("file_sha256"))
        for key, value in local.items():
            if key in packets:
                duplicate_count += 1
            packets[key] = value
        duplicate_count += int(facts["duplicate_count"])
        shard_facts.append(facts)
    if int(manifest.get("global_summed_packet_count", -1)) != sum(
        int(item["packet_count"]) for item in shard_facts
    ):
        raise ValueError("canonical manifest packet count does not close")
    return packets, {
        "manifest_sha256": manifest_sha,
        "packet_count": sum(int(item["packet_count"]) for item in shard_facts),
        "unique_key_count": len(packets),
        "duplicate_count": duplicate_count,
        "finite": all(bool(item["finite"]) for item in shard_facts),
        "role": manifest.get("role"),
        "l2_norm": math.sqrt(sum(abs(value) ** 2 for value in packets.values())),
    }


def _packet_difference(
    left: Mapping[Any, complex], right: Mapping[Any, complex]
) -> dict[str, Any]:
    left_keys = set(left)
    right_keys = set(right)
    missing = left_keys - right_keys
    extra = right_keys - left_keys
    if missing or extra:
        return {
            "key_set_equal": False,
            "missing_key_count": len(missing),
            "extra_key_count": len(extra),
            "relative_l2": math.inf,
            "max_abs": math.inf,
        }
    difference_sq = sum(abs(left[key] - right[key]) ** 2 for key in left)
    reference_sq = sum(abs(right[key]) ** 2 for key in right)
    max_abs = max((abs(left[key] - right[key]) for key in left), default=0.0)
    return {
        "key_set_equal": True,
        "missing_key_count": 0,
        "extra_key_count": 0,
        "relative_l2": math.sqrt(difference_sq)
        / max(math.sqrt(reference_sq), 1.0e-300),
        "max_abs": max_abs,
    }


T5_PHYSICAL_IDENTITY_SCHEMA = "task038.full3d.iterative.t5.physical-identity.v2"
T5_PHYSICAL_IDENTITY_RECORD_SCHEMA = (
    "task038.full3d.iterative.t5.physical-identity-record.v2"
)
T5_PHYSICAL_IDENTITY_FIELDS = (
    "wavelength",
    "geometry",
    "materials",
    "incidence",
    "floquet",
    "finite_element",
    "facet_normal",
    "ordered_modes",
    "incident_amplitudes",
    "rhs_composition",
    "mpc",
    "raw_config",
    "source_provenance",
)


def _valid_hex(value: Any, length: int) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _identity_field_errors(
    role: str, name: str, value: Any
) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{role}.{name} identity field is missing or not an object"]
    status = value.get("status")
    if status == "available":
        if "value" not in value or not isinstance(value.get("source_evidence"), str):
            return [f"{role}.{name} available field lacks value/source evidence"]
        return []
    if status == "unavailable":
        if not isinstance(value.get("reason"), str) or not value["reason"]:
            return [f"{role}.{name} unavailable field lacks a reason"]
        if not isinstance(value.get("source_evidence"), str) or not value["source_evidence"]:
            return [f"{role}.{name} unavailable field lacks source evidence"]
        return []
    return [f"{role}.{name} identity field has invalid status"]


def _identity_file_errors(
    descriptor: Any, base: Path, label: str
) -> tuple[list[str], dict[str, Any]]:
    if not isinstance(descriptor, Mapping):
        return [f"{label} file descriptor is missing"], {}
    raw_path = descriptor.get("path")
    if not isinstance(raw_path, str):
        return [f"{label} file descriptor path is missing"], {}
    path = Path(raw_path)
    if not path.is_absolute():
        path = (base / path).resolve()
    else:
        path = path.resolve()
    if not path.is_file():
        return [f"{label} file is missing: {path}"], {}
    actual_bytes = int(path.stat().st_size)
    actual_sha = _sha256_path(path)
    errors: list[str] = []
    if descriptor.get("bytes") != actual_bytes:
        errors.append(f"{label} byte count does not match raw file")
    if descriptor.get("sha256") != actual_sha:
        errors.append(f"{label} SHA-256 does not match raw file")
    if not _valid_hex(descriptor.get("sha256"), 64):
        errors.append(f"{label} SHA-256 is not lowercase hexadecimal")
    return errors, {
        "path": str(path),
        "bytes": actual_bytes,
        "sha256": actual_sha,
    }


def _check_identity_manifest(
    path: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"identity manifest is unreadable: {exc}"], {}
    if manifest.get("schema") != T5_PHYSICAL_IDENTITY_SCHEMA:
        errors.append("identity manifest schema mismatch")
    role = manifest.get("role")
    if role not in {"historical_w5", "current_task038_extra"}:
        errors.append("identity manifest role is invalid")
    fields = manifest.get("physical_identity")
    if not isinstance(fields, Mapping):
        return errors + ["identity manifest physical_identity is missing"], {}
    for name in T5_PHYSICAL_IDENTITY_FIELDS:
        errors.extend(_identity_field_errors(str(role), name, fields.get(name)))
    if set(fields) != set(T5_PHYSICAL_IDENTITY_FIELDS):
        errors.append("identity manifest mandatory field set is not exact")
    if role == "current_task038_extra":
        geometry = fields.get("geometry", {}).get("value")
        if (
            not isinstance(geometry, Mapping)
            or geometry.get("mesh_witness") != geometry.get("rebuild")
        ):
            errors.append("current generated/rebuild mesh witness is not identical")
        modes = fields.get("ordered_modes", {}).get("value")
        amplitudes = fields.get("incident_amplitudes", {}).get("value")
        mode_keys = {
            "schema", "mode_index", "side", "m", "n", "polarization",
            "alpha", "gamma", "beta", "k_vector", "e_vector", "h_vector",
            "refractive_index", "vertical_sign", "electric_tangential_norm_sq",
            "power_per_unit_amplitude", "propagating", "rayleigh_warning",
            "classification", "rayleigh_tolerance", "projection_denominator",
            "traction_vector",
        }
        if not isinstance(modes, list) or not modes:
            errors.append("current ordered mode inventory is empty")
        elif any(
            not isinstance(mode, Mapping)
            or not mode_keys.issubset(mode)
            or mode.get("schema") != "fullspace-dtn.mode.v1"
            or mode.get("mode_index") != index
            or not isinstance(mode.get("projection_denominator"), (int, float))
            or not math.isfinite(float(mode["projection_denominator"]))
            or float(mode["projection_denominator"]) <= 0.0
            for index, mode in enumerate(modes)
        ):
            errors.append("current ordered mode identity is not closed")
        if not isinstance(amplitudes, list) or len(amplitudes) != len(modes or ()):
            errors.append("current incident amplitude inventory does not match modes")
    source = manifest.get("source")
    if not isinstance(source, Mapping) or not _valid_hex(source.get("commit_sha"), 40):
        errors.append("identity manifest source commit SHA is invalid")
    raw_artifacts = manifest.get("raw_artifacts")
    if not isinstance(raw_artifacts, Mapping) or not raw_artifacts:
        errors.append("identity manifest raw artifact descriptors are missing")
    raw_facts: dict[str, Any] = {}
    for name, descriptor in (raw_artifacts.items() if isinstance(raw_artifacts, Mapping) else ()):
        file_errors, facts = _identity_file_errors(
            descriptor, path.parent, f"{role} raw artifact {name}"
        )
        errors.extend(file_errors)
        raw_facts[str(name)] = facts
    if role == "current_task038_extra":
        provenance = fields.get("source_provenance", {})
        provenance_value = provenance.get("value") if isinstance(provenance, Mapping) else None
        if not isinstance(provenance_value, Mapping):
            errors.append("current source provenance value is missing")
        else:
            mode_facts = raw_facts.get("mode_manifest", {})
            dynamic_sha = provenance_value.get("dynamic_mode_manifest_sha256")
            dynamic_bytes = provenance_value.get("dynamic_mode_manifest_bytes")
            if dynamic_sha != mode_facts.get("sha256"):
                errors.append("current dynamic mode manifest SHA is not bound to raw evidence")
            if dynamic_bytes != mode_facts.get("bytes"):
                errors.append("current dynamic mode manifest byte count is not bound to raw evidence")
            source_files = provenance_value.get("source_files")
            required_files = {
                "input_validation": "src/io/input_validation.py",
                "dtn_port_3d": "src/solvers/dtn_port_3d.py",
                "fullspace_dtn_action": "src/solvers/fullspace_dtn_action.py",
                "fullspace_physical_action": "src/solvers/fullspace_physical_action.py",
            }
            if not isinstance(source_files, Mapping):
                errors.append("current source defining blobs are missing")
            else:
                source_commit = source.get("commit_sha") if isinstance(source, Mapping) else None
                for name, expected_path in required_files.items():
                    blob = source_files.get(name)
                    if (
                        not isinstance(blob, Mapping)
                        or blob.get("commit_sha") != source_commit
                        or blob.get("path") != expected_path
                        or not _valid_hex(blob.get("sha256"), 64)
                    ):
                        errors.append(f"current source defining blob is invalid: {name}")
    return errors, {
        "role": role,
        "fields": fields,
        "raw_artifacts": raw_facts,
        "source": source,
        "path": str(path.resolve()),
        "manifest_sha256": _sha256_path(path),
    }


def check_physical_identity(record_path: Path) -> dict[str, Any]:
    """Recompute R1 completeness and the old/current physical diagnosis."""

    errors: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema": T5_PHYSICAL_IDENTITY_RECORD_SCHEMA,
            "status": "fail",
            "failures": [f"identity record is unreadable: {exc}"],
        }
    if record.get("schema") != T5_PHYSICAL_IDENTITY_RECORD_SCHEMA:
        errors.append("identity record schema mismatch")
    source = record.get("source")
    if not isinstance(source, Mapping):
        errors.append("identity record source is missing")
    else:
        if not _valid_hex(source.get("expected_sha"), 40):
            errors.append("identity expected source SHA is invalid")
        if source.get("expected_sha") != source.get("head_sha"):
            errors.append("identity expected source SHA does not equal HEAD SHA")
        if source.get("tracked_status") != "":
            errors.append("identity source worktree is dirty")
    manifest_descriptors = record.get("manifests")
    if not isinstance(manifest_descriptors, Mapping):
        errors.append("identity manifest descriptors are missing")
        manifest_descriptors = {}
    manifests: dict[str, dict[str, Any]] = {}
    for label in ("old", "current"):
        descriptor = manifest_descriptors.get(label)
        file_errors, file_facts = _identity_file_errors(
            descriptor, record_path.parent, f"{label} identity manifest"
        )
        errors.extend(file_errors)
        if file_facts:
            declared_sha = descriptor.get("sha256") if isinstance(descriptor, Mapping) else None
            if declared_sha != file_facts["sha256"]:
                errors.append(f"{label} identity manifest descriptor SHA mismatch")
            manifest_errors, manifest_facts = _check_identity_manifest(
                Path(file_facts["path"])
            )
            errors.extend(manifest_errors)
            expected_manifest_source = (
                OLD_SOURCE_SHA
                if label == "old"
                else source.get("head_sha") if isinstance(source, Mapping) else None
            )
            if manifest_facts.get("source", {}).get("commit_sha") != expected_manifest_source:
                errors.append(f"{label} identity source SHA is not bound to the record")
            manifests[label] = manifest_facts
    input_block = record.get("input")
    if not isinstance(input_block, Mapping):
        errors.append("R1 T1 input/resolved-config binding is missing")
    else:
        input_errors, input_facts = _identity_file_errors(
            input_block.get("template"), record_path.parent, "T1 input template"
        )
        errors.extend(input_errors)
        if input_facts:
            resolved_facts = manifests.get("current", {}).get("raw_artifacts", {}).get("resolved_config", {})
            resolved_path = resolved_facts.get("path") if isinstance(resolved_facts, Mapping) else None
            if input_block.get("resolved_config_bytes") != resolved_facts.get("bytes"):
                errors.append("R1 resolved-config byte count is not bound to current raw evidence")
            if not isinstance(resolved_path, str) or input_block.get("resolved_config_sha256") != resolved_facts.get("sha256"):
                errors.append("R1 resolved-config SHA is not bound to current raw evidence")
    old_fields = manifests.get("old", {}).get("fields", {})
    current_fields = manifests.get("current", {}).get("fields", {})
    field_mismatches: list[str] = []
    old_unavailable: list[str] = []
    for name in T5_PHYSICAL_IDENTITY_FIELDS:
        old_field = old_fields.get(name)
        current_field = current_fields.get(name)
        if isinstance(old_field, Mapping) and old_field.get("status") == "unavailable":
            old_unavailable.append(name)
        if name == "source_provenance":
            continue
        if (
            isinstance(old_field, Mapping)
            and isinstance(current_field, Mapping)
            and old_field.get("status") == "available"
            and current_field.get("status") == "available"
            and _canonical_json(old_field.get("value"))
            != _canonical_json(current_field.get("value"))
        ):
            field_mismatches.append(name)
    rhs = record.get("rhs_observation")
    rhs_facts: dict[str, Any] = {}
    if not isinstance(rhs, Mapping):
        errors.append("R1 RHS observation descriptors are missing")
    else:
        old_errors, old_file = _identity_file_errors(
            rhs.get("old_manifest"), record_path.parent, "old RHS canonical manifest"
        )
        current_errors, current_file = _identity_file_errors(
            rhs.get("current_manifest"), record_path.parent, "current RHS canonical manifest"
        )
        errors.extend(old_errors + current_errors)
        if old_file and current_file:
            try:
                old_packets, old_packet_facts = _read_packet_manifest(Path(old_file["path"]))
                current_packets, current_packet_facts = _read_packet_manifest(
                    Path(current_file["path"])
                )
                difference = _packet_difference(old_packets, current_packets)
                rhs_facts = {
                    "old": old_packet_facts,
                    "current": current_packet_facts,
                    "comparison": difference,
                    "relative_tolerance": rhs.get("relative_tolerance"),
                }
                if old_packet_facts["duplicate_count"] != 0 or current_packet_facts["duplicate_count"] != 0:
                    errors.append("R1 RHS canonical packets contain duplicates")
                if not old_packet_facts["finite"] or not current_packet_facts["finite"]:
                    errors.append("R1 RHS canonical packets contain non-finite values")
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"R1 RHS canonical comparison is unreadable: {exc}")
    comparison = rhs_facts.get("comparison", {})
    rhs_relative = float(comparison.get("relative_l2", math.inf))
    rhs_key_ok = bool(
        comparison.get("key_set_equal") is True
        and comparison.get("missing_key_count") == 0
        and comparison.get("extra_key_count") == 0
    )
    same_physics = bool(
        not old_unavailable
        and not field_mismatches
        and rhs_key_ok
        and rhs_relative <= T5_CANONICAL_LIMIT
    )
    if same_physics:
        classification = "SAME_PHYSICAL_IDENTITY"
    elif field_mismatches or (rhs_key_ok and rhs_relative > T5_CANONICAL_LIMIT):
        classification = "HISTORICAL_W5_NOT_SAME_PHYSICAL_RHS"
    else:
        classification = "OLD_PHYSICAL_IDENTITY_INCOMPLETE"
    old_field_contract = bool(
        old_fields
        and all(
            not _identity_field_errors("old", name, old_fields.get(name))
            for name in T5_PHYSICAL_IDENTITY_FIELDS
        )
    )
    current_field_contract = bool(
        current_fields
        and all(
            not _identity_field_errors("current", name, current_fields.get(name))
            and current_fields[name].get("status") == "available"
            for name in T5_PHYSICAL_IDENTITY_FIELDS
        )
    )
    gates = {
        "old_manifest_completeness": old_field_contract,
        "current_manifest_completeness": current_field_contract,
        "raw_hashes": bool(
            manifests.get("old")
            and manifests.get("current")
            and not any("raw artifact" in error for error in errors)
        ),
        "rhs_key_structure": rhs_key_ok,
        "same_physics_claim": same_physics,
    }
    return {
        "schema": T5_PHYSICAL_IDENTITY_RECORD_SCHEMA,
        "status": "pass" if not errors else "fail",
        "failures": errors,
        "classification": classification,
        "gates": gates,
        "derived": {
            "old_unavailable_fields": old_unavailable,
            "available_field_mismatches": field_mismatches,
            "rhs": rhs_facts,
            "same_physics_claim": same_physics,
        },
    }


def _manifest_ref(value: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get("manifest_relative_path", value.get("manifest_path"))
    return value


def _read_manifest_ref(
    root: Path, value: Any
) -> tuple[dict[Any, complex], dict[str, Any]]:
    reference = _manifest_ref(value)
    path = _artifact_path(root, reference)
    packets, facts = _read_packet_manifest(path)
    if isinstance(value, Mapping):
        declared_sha = value.get("manifest_sha256")
        if declared_sha is not None and declared_sha != facts["manifest_sha256"]:
            raise ValueError("canonical manifest SHA mismatch")
    return packets, facts


def _manifest_quality_errors(label: str, facts: Mapping[str, Any]) -> list[str]:
    errors = []
    if facts.get("role") != "full_fe_dual":
        errors.append(f"{label} canonical manifest role is not full_fe_dual")
    if facts.get("packet_count", 0) <= 0 or facts.get("unique_key_count", 0) <= 0:
        errors.append(f"{label} canonical manifest is empty")
    if facts.get("duplicate_count") != 0:
        errors.append(f"{label} canonical manifest contains duplicate keys")
    if facts.get("finite") is not True or not math.isfinite(float(facts["l2_norm"])):
        errors.append(f"{label} canonical manifest contains non-finite values")
    return errors


def _check_resource_contract(
    record: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    resource = record.get("resource_contract")
    if not isinstance(resource, Mapping):
        return ["external watchdog resource evidence is missing"], {}
    errors: list[str] = []
    if resource.get("watchdog") != "external_process_tree":
        errors.append("resource watchdog is not external_process_tree")
    if resource.get("status") != "measured_pass":
        errors.append("resource watchdog status is not measured_pass")
    if resource.get("process_tree_memory_ceiling_bytes") != T5_PROCESS_TREE_CEILING_BYTES:
        errors.append("resource process-tree ceiling is not 6 GiB")
    if resource.get("hard_stop_memory_bytes") != T5_HARD_STOP_BYTES:
        errors.append("resource hard stop is not 12 GiB")
    if resource.get("swap_required_bytes") != 0:
        errors.append("resource swap contract is not zero")
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    try:
        raw_path = _safe_path(raw_dir, resource["raw_report_relative_path"])
        compact_path = _safe_path(raw_dir, resource["compact_report_relative_path"])
    except (KeyError, TypeError, ValueError) as exc:
        return errors + [f"resource evidence path is invalid: {exc}"], {}
    try:
        raw_sha = _sha256_path(raw_path)
        compact_sha = _sha256_path(compact_path)
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        compact = json.loads(compact_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"resource evidence is unreadable: {exc}"], {}
    if resource.get("compact_report_sha256") != compact_sha:
        errors.append("compact watchdog report SHA mismatch")
    if resource.get("raw_report_sha256") != raw_sha:
        errors.append("record raw watchdog report SHA mismatch")
    if compact.get("raw_report_sha256") != raw_sha:
        errors.append("raw watchdog report SHA mismatch")
    if compact.get("schema") != "task038.t5.external-process-tree-compact.v1":
        errors.append("compact watchdog report schema mismatch")
    if compact.get("status") != "measured_pass":
        errors.append("compact watchdog report status is not measured_pass")
    if raw.get("schema") != "task038.t5.external-process-tree-raw.v1":
        errors.append("raw watchdog report schema mismatch")
    samples = raw.get("samples")
    if not isinstance(samples, list) or not samples:
        return errors + ["raw watchdog sample list is empty"], {}
    rss_values: list[int] = []
    swap_values: list[int] = []
    cgroup_swap_values: list[int] = []
    authority_values: list[int] = []
    readable = True
    for sample in samples:
        tree = sample.get("process_tree") if isinstance(sample, Mapping) else None
        cgroup = sample.get("job_cgroup") if isinstance(sample, Mapping) else None
        if not isinstance(tree, Mapping) or not isinstance(cgroup, Mapping):
            errors.append("raw watchdog sample lacks process-tree/cgroup fields")
            continue
        values = (tree.get("rss_bytes"), tree.get("swap_bytes"), sample.get("memory_authority_bytes"))
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            errors.append("raw watchdog numeric resource field is invalid")
            continue
        rss_values.append(int(tree["rss_bytes"]))
        swap_values.append(int(tree["swap_bytes"]))
        authority_values.append(int(sample["memory_authority_bytes"]))
        readable = readable and tree.get("all_status_readable") is True and sample.get("job_no_swap") is True
        if cgroup.get("dedicated_job_cgroup") is True:
            cgroup_swap = cgroup.get("swap_current_bytes")
            if cgroup_swap is None:
                errors.append("dedicated cgroup swap field is unreadable")
            elif isinstance(cgroup_swap, bool) or not isinstance(cgroup_swap, int):
                errors.append("raw watchdog dedicated cgroup swap field is invalid")
            else:
                cgroup_swap_values.append(int(cgroup_swap))
    observed = {
        "process_tree_peak_rss_bytes": max(rss_values, default=0),
        "process_tree_peak_swap_bytes": max(swap_values, default=0),
        "dedicated_cgroup_peak_swap_bytes": max(cgroup_swap_values, default=0),
        "memory_authority_peak_bytes": max(authority_values, default=0),
        "sample_count": len(samples),
        "all_status_readable": readable,
    }
    for key, value in observed.items():
        if compact.get(key) != value or resource.get(key) != value:
            errors.append(f"resource field is not recomputed from raw samples: {key}")
    if compact.get("returncode") != raw.get("returncode") or compact.get("returncode") != 0:
        errors.append("watchdog worker return code is not zero")
    if compact.get("stop_reason") is not None or raw.get("stop_reason") is not None:
        errors.append("watchdog recorded a stop reason")
    termination = compact.get("termination")
    if termination != raw.get("termination"):
        errors.append("compact/raw watchdog termination facts differ")
    if not isinstance(termination, Mapping) or termination.get("process_group_exited") is not True:
        errors.append("watchdog process group did not close")
    if isinstance(termination, Mapping) and termination.get("sigkill_required") is True:
        errors.append("watchdog required SIGKILL")
    if not readable or observed["process_tree_peak_rss_bytes"] >= T5_PROCESS_TREE_CEILING_BYTES:
        errors.append("process-tree peak RSS is not below the 6 GiB gate")
    if observed["memory_authority_peak_bytes"] >= T5_HARD_STOP_BYTES:
        errors.append("memory-authority peak reached the 12 GiB hard stop")
    if observed["process_tree_peak_swap_bytes"] != 0 or observed["dedicated_cgroup_peak_swap_bytes"] != 0:
        errors.append("watchdog observed nonzero swap")
    return errors, {
        **observed,
        "raw_report_sha256": raw_sha,
        "compact_report_sha256": compact_sha,
        "status": "pass" if not errors else "fail",
    }


def _compare_manifest_refs(
    left_root: Path,
    left_ref: Any,
    right_root: Path | None = None,
    right_ref: Any = None,
    *,
    tolerance: float = T5_CANONICAL_LIMIT,
    compare_values: bool = True,
) -> tuple[list[str], dict[str, Any]]:
    """Read and compare canonical packets, including independent raw facts."""

    errors: list[str] = []
    try:
        left, left_facts = _read_manifest_ref(left_root, left_ref)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"left canonical manifest is unreadable: {exc}"], {}
    if right_ref is None:
        errors.extend(_manifest_quality_errors("left", left_facts))
        return errors, {"left": left_facts, "pass": not errors}
    try:
        right, right_facts = _read_manifest_ref(
            left_root if right_root is None else right_root, right_ref
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"right canonical manifest is unreadable: {exc}"], {
            "left": left_facts
        }
    facts_to_check = (("left", left_facts), ("right", right_facts))
    for label, facts in facts_to_check:
        errors.extend(_manifest_quality_errors(label, facts))
    comparison = (
        _packet_difference(left, right)
        if compare_values
        else {
            "key_set_equal": set(left) == set(right),
            "missing_key_count": len(set(left) - set(right)),
            "extra_key_count": len(set(right) - set(left)),
            "relative_l2": 0.0 if set(left) == set(right) else math.inf,
            "max_abs": 0.0 if set(left) == set(right) else math.inf,
        }
    )
    comparison.update(
        {
            "left_packet_count": left_facts["packet_count"],
            "right_packet_count": right_facts["packet_count"],
            "left_unique_key_count": left_facts["unique_key_count"],
            "right_unique_key_count": right_facts["unique_key_count"],
            "left_duplicate_count": left_facts["duplicate_count"],
            "right_duplicate_count": right_facts["duplicate_count"],
            "left_role": left_facts["role"],
            "right_role": right_facts["role"],
            "left_finite": left_facts["finite"],
            "right_finite": right_facts["finite"],
            "value_comparison": compare_values,
            "tolerance": tolerance,
        }
    )
    if left_facts["packet_count"] != right_facts["packet_count"]:
        errors.append("canonical packet counts differ")
    if left_facts["unique_key_count"] != right_facts["unique_key_count"]:
        errors.append("canonical unique key counts differ")
    if comparison.get("key_set_equal") is not True:
        errors.append("canonical packet key sets differ")
    if compare_values and float(comparison.get("relative_l2", math.inf)) > tolerance:
        errors.append(f"canonical gate exceeds {tolerance:g}")
    return errors, {
        "left": left_facts,
        "right": right_facts,
        "comparison": comparison,
        "pass": not errors,
    }


def _check_old_arrays(record: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    old = record.get("old_w5")
    if not isinstance(old, Mapping):
        return ["old_w5 facts are missing"], {}
    directory = Path(str(old.get("directory", "")))
    errors: list[str] = []
    arrays: dict[str, np.ndarray] = {}
    facts: dict[str, Any] = {}
    for name, expected in OLD_ARRAY_FACTS.items():
        path = directory / f"m6b_iter200_{name}.npy"
        if not path.is_file():
            errors.append(f"old W5 array is missing: {path}")
            continue
        file_sha = _sha256_path(path)
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        array_sha = hashlib.sha256(
            np.ascontiguousarray(array).view(np.uint8)
        ).hexdigest()
        arrays[name] = np.asarray(array)
        facts[name] = {
            "file_sha256": file_sha,
            "array_sha256": array_sha,
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "bytes": int(path.stat().st_size),
        }
        if file_sha != expected["file_sha256"]:
            errors.append(f"old {name} file SHA mismatch")
        if array_sha != expected["array_sha256"]:
            errors.append(f"old {name} array SHA mismatch")
        if list(array.shape) != [173802] or str(array.dtype) != "complex128":
            errors.append(f"old {name} shape or dtype mismatch")
        if not bool(np.all(np.isfinite(array))):
            errors.append(f"old {name} contains non-finite values")
    if all(name in arrays for name in ("rhs", "outer_action", "residual")):
        delta = arrays["residual"] - (arrays["rhs"] - arrays["outer_action"])
        rhs_norm = float(np.linalg.norm(arrays["rhs"]))
        closure = {
            "max_abs": float(np.max(np.abs(delta))),
            "relative_l2": float(
                np.linalg.norm(delta) / max(rhs_norm, 1.0e-300)
            ),
        }
        facts["residual_closure"] = closure
        if closure["max_abs"] != 0.0 or closure["relative_l2"] != 0.0:
            errors.append("old residual does not equal rhs minus outer_action")
    return errors, facts


def _check_row_witness(
    raw_dir: Path, descriptor: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    try:
        manifest_path = _safe_path(raw_dir, descriptor.get("manifest_relative_path"))
    except (TypeError, ValueError) as exc:
        return [f"row witness path is invalid: {exc}"], {}
    if not manifest_path.is_file():
        return ["row witness manifest is missing"], {}
    manifest_sha = _sha256_path(manifest_path)
    if descriptor.get("manifest_sha256") != manifest_sha:
        errors.append("row witness manifest SHA mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != T5_ROW_WITNESS_SCHEMA:
        errors.append("row witness manifest schema mismatch")
    stream_facts = []
    for shard in manifest.get("shards", []):
        shard_path = manifest_path.parent / shard["filename"]
        if not shard_path.is_file():
            errors.append(f"row witness shard is missing: {shard_path}")
            continue
        digest = hashlib.sha256()
        block_count = 0
        row_id_count = 0
        relation_digests: set[str] = set()
        with shard_path.open("rb") as stream:
            for raw_line in stream:
                digest.update(raw_line)
                row = json.loads(raw_line)
                if row.get("schema") != T5_ROW_SHARD_SCHEMA:
                    errors.append("row witness shard schema mismatch")
                for key in T5_ROW_WITNESS_FIELDS:
                    if key not in row:
                        errors.append(f"row witness field is missing: {key}")
                if row.get("slave_exclusion") is not True:
                    errors.append("row witness slave exclusion is not enabled")
                ordered = row.get("ordered_global_row_ids", [])
                active = row.get("active_global_row_ids", [])
                slaves = row.get("slave_global_row_ids", [])
                if not all(isinstance(item, int) and not isinstance(item, bool) for item in ordered + active + slaves):
                    errors.append("row witness row IDs are not integer metadata")
                if len(ordered) != len(set(ordered)):
                    errors.append("row witness block contains duplicate row IDs")
                if set(active) & set(slaves) or set(active) | set(slaves) != set(ordered):
                    errors.append("row witness slave exclusion does not close")
                transform_sha = row.get("orientation_transform_sha256")
                relation_sha = row.get("mpc_relation_digest")
                if not isinstance(transform_sha, str) or len(transform_sha) != 64:
                    errors.append("row witness orientation transform digest is invalid")
                if not isinstance(relation_sha, str) or len(relation_sha) != 64:
                    errors.append("row witness MPC relation digest is invalid")
                else:
                    relation_digests.add(relation_sha)
                block_count += 1
                row_id_count += len(ordered)
        actual_sha = digest.hexdigest()
        if shard.get("sha256") != actual_sha:
            errors.append("row witness shard SHA mismatch")
        if shard.get("block_count") != block_count:
            errors.append("row witness block count mismatch")
        if shard.get("row_id_count") != row_id_count:
            errors.append("row witness row count mismatch")
        stream_facts.append(
            {
                "rank": shard.get("rank"),
                "sha256": actual_sha,
                "block_count": block_count,
                "row_id_count": row_id_count,
                "relation_digests": sorted(relation_digests),
            }
        )
    identity = _canonical_json(
        [
            {
                "rank": item["rank"],
                "sha256": item["sha256"],
                "block_count": item["block_count"],
                "row_id_count": item["row_id_count"],
            }
            for item in sorted(stream_facts, key=lambda item: int(item["rank"]))
        ]
    )
    global_digest = hashlib.sha256(identity).hexdigest()
    if manifest.get("global_digest") != global_digest:
        errors.append("row witness global digest mismatch")
    relation_union = sorted(
        {digest for item in stream_facts for digest in item["relation_digests"]}
    )
    if manifest.get("relation_digests") != relation_union:
        errors.append("row witness relation digest inventory mismatch")
    derived = {
        "manifest_sha256": manifest_sha,
        "global_digest": global_digest,
        "block_count": sum(item["block_count"] for item in stream_facts),
        "row_id_count": sum(item["row_id_count"] for item in stream_facts),
        "relation_digests": relation_union,
    }
    return errors, derived


def _check_mesh_witnesses(
    record: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    witnesses = record.get("mesh_witnesses")
    names = ("old_exact", "current_generated", "current_rebuild")
    if not isinstance(witnesses, Mapping):
        return ["mesh witness identities are missing"], {}
    errors: list[str] = []
    entries: dict[str, Mapping[str, Any]] = {}
    for name in names:
        entry = witnesses.get(name)
        if not isinstance(entry, Mapping):
            errors.append(f"mesh witness is missing: {name}")
            continue
        entries[name] = entry
        missing = [field for field in T5_MESH_IDENTITY_FIELDS if field not in entry]
        if missing:
            errors.append(f"mesh witness {name} is missing fields: {missing}")
    if len(entries) == len(names):
        reference = tuple(entries["old_exact"][field] for field in T5_MESH_IDENTITY_FIELDS)
        for name in names[1:]:
            observed = tuple(entries[name][field] for field in T5_MESH_IDENTITY_FIELDS)
            if observed != reference:
                errors.append(f"mesh witness identity differs: {name}")
        if entries["old_exact"].get("source") != "old_exact_xdmf":
            errors.append("old mesh witness source is not the exact XDMF artifact")
        for name in names[1:]:
            if entries[name].get("source") != name:
                errors.append(f"mesh witness source is not explicit: {name}")
    declared = witnesses.get("identity_fields")
    if declared != list(T5_MESH_IDENTITY_FIELDS):
        errors.append("mesh witness identity field list is not the checker contract")
    return errors, {
        "identity_fields": list(T5_MESH_IDENTITY_FIELDS),
        "sources": {name: entries[name].get("source") for name in entries},
    }


def _check_residual_mpi_identity(
    raw_dir: Path, bridge: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    left_ref = bridge.get("mpi1_manifest_path", bridge.get("mpi1_manifest_relative_path"))
    right_ref = bridge.get(
        "mpi2_reextract_manifest_path",
        bridge.get("mpi2_reextract_manifest_relative_path"),
    )
    if left_ref is None:
        return ["MPI1 residual manifest is missing"], {}
    errors, facts = _compare_manifest_refs(
        raw_dir,
        left_ref,
        right_ref=right_ref,
        tolerance=T5_CANONICAL_LIMIT,
    )
    if right_ref is None:
        left = facts.get("left", {})
        return errors, {
            "stage": "mpi1",
            "qualified_for_mpi2": not errors,
            "manifest_sha256": left.get("manifest_sha256"),
            "packet_count": left.get("packet_count"),
            "unique_key_count": left.get("unique_key_count"),
            "duplicate_count": left.get("duplicate_count"),
            "finite": left.get("finite"),
            "l2_norm": left.get("l2_norm"),
        }
    comparison = dict(facts.get("comparison", {}))
    comparison.update(
        {
            "stage": "mpi2",
            "mpi1_packet_count": comparison.get("left_packet_count"),
            "mpi2_reextract_packet_count": comparison.get("right_packet_count"),
            "mpi1_unique_key_count": comparison.get("left_unique_key_count"),
            "mpi2_reextract_unique_key_count": comparison.get("right_unique_key_count"),
            "mpi1_duplicate_count": comparison.get("left_duplicate_count"),
            "mpi2_reextract_duplicate_count": comparison.get("right_duplicate_count"),
            "mpi1_role": comparison.get("left_role"),
            "mpi2_role": comparison.get("right_role"),
            "mpi1_finite": comparison.get("left_finite"),
            "mpi2_finite": comparison.get("right_finite"),
            "qualified_for_mpi2": not errors,
        }
    )
    return errors, comparison


def _check_residual_authority(
    raw_dir: Path, artifacts: Mapping[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """Independently close residual source/action/repeat/reference packets."""

    if artifacts.get("status") != "pass":
        return ["residual action evidence is not_run"], {
            "status": "not_run",
            "reason": artifacts.get("reason"),
        }
    names = ("source", "action", "repeat", "reference")
    missing = [name for name in names if not isinstance(artifacts.get(name), Mapping)]
    if missing:
        return [f"residual action manifest is missing: {missing}"], {}
    facts: dict[str, Any] = {}
    errors: list[str] = []
    for name in names:
        own_errors, own = _compare_manifest_refs(raw_dir, artifacts[name])
        errors.extend(f"{name}: {error}" for error in own_errors)
        facts[name] = own
    comparisons = (
        ("source_action_structure", "source", "action", False, T5_CANONICAL_LIMIT),
        ("action_reference", "action", "reference", True, T5_ACTION_LIMIT),
        ("repeat_action", "repeat", "action", True, T5_CANONICAL_LIMIT),
    )
    comparison_facts: dict[str, Any] = {}
    for name, left, right, compare_values, tolerance in comparisons:
        comparison_errors, comparison = _compare_manifest_refs(
            raw_dir,
            artifacts[left],
            right_ref=artifacts[right],
            compare_values=compare_values,
            tolerance=tolerance,
        )
        errors.extend(f"{name}: {error}" for error in comparison_errors)
        comparison_facts[name] = comparison
    source_facts = facts.get("source", {}).get("left", {})
    if float(source_facts.get("l2_norm", 0.0)) <= 0.0:
        errors.append("residual source canonical norm is not positive")
    facts.update(comparison_facts)
    facts["status"] = "pass" if not errors else "fail"
    return errors, facts


def check_t5_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute all available T5 bridge gates from a raw record."""

    errors: list[str] = []
    gates: dict[str, bool] = {}
    if record.get("schema") != T5_SCHEMA:
        errors.append("record schema mismatch")
    if record.get("profile") != T5_PROFILE:
        errors.append("record profile mismatch")
    source = record.get("source")
    source_ok = isinstance(source, Mapping) and all(
        isinstance(source.get(key), str) and len(source.get(key)) == 40
        for key in ("expected_sha", "commit_sha_start", "commit_sha_end")
    )
    source_ok = bool(
        source_ok
        and source["expected_sha"] == source["commit_sha_start"] == source["commit_sha_end"]
        and not source.get("tracked_status_start")
        and not source.get("tracked_status_end")
    )
    gates["source_identity"] = source_ok
    if not source_ok:
        errors.append("source identity is not clean and hash-bound")

    resource_errors, resource_facts = _check_resource_contract(record)
    errors.extend(resource_errors)
    gates["external_watchdog_contract"] = not resource_errors

    provenance = record.get("extractor_provenance")
    runtime = provenance.get("runtime") if isinstance(provenance, Mapping) else None
    runtime_python = runtime.get("python") if isinstance(runtime, Mapping) else None
    repo_venv = (Path(__file__).resolve().parents[1] / ".venv").resolve()
    runtime_python_ok = (
        isinstance(runtime_python, str)
        and Path(runtime_python).is_absolute()
        and Path(runtime_python).is_relative_to(repo_venv)
    )
    provenance_ok = isinstance(provenance, Mapping) and (
        provenance.get("old_source_sha") == OLD_SOURCE_SHA
        and provenance.get("old_api") == "iter_canonical_full_fe_dual_packets"
        and provenance.get("current_api") == "extract_canonical_full_fe_dual_packets"
        and provenance.get("entity_transform") == "transform.conj().T"
        and provenance.get("cell_transform") == "Tt_apply"
        and provenance.get("slave_exclusion") is True
        and isinstance(provenance.get("old_source_blob_sha256"), str)
        and len(provenance["old_source_blob_sha256"]) == 64
        and isinstance(runtime, Mapping)
        and runtime.get("qualified_activation") == "1"
        and runtime.get("petsc_scalar_type") == str(np.dtype(np.complex128))
        and runtime_python_ok
    )
    gates["extractor_provenance"] = bool(provenance_ok)
    if not provenance_ok:
        errors.append("dual extractor provenance is incomplete")

    old_errors, old_facts = _check_old_arrays(record)
    errors.extend(old_errors)
    closure = old_facts.get("residual_closure", {})
    gates["old_residual_closure"] = bool(
        closure.get("max_abs") == 0.0 and closure.get("relative_l2") == 0.0
    )

    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    witness_errors, witness_facts = _check_row_witness(
        raw_dir, record.get("row_layout_witness", {})
    )
    errors.extend(witness_errors)
    gates["row_layout_witness"] = not witness_errors

    mesh_errors, mesh_facts = _check_mesh_witnesses(record)
    errors.extend(mesh_errors)
    gates["mesh_witness_identity"] = not mesh_errors

    bridge = record.get("bridge", {})
    rhs_manifest_relative = (
        bridge.get("current_rhs_manifest_relative_path")
        if isinstance(bridge, Mapping)
        else None
    )
    rhs_difference: dict[str, Any] = {}
    if not isinstance(rhs_manifest_relative, str):
        errors.append("current RHS canonical manifest path is missing")
    else:
        try:
            current_path = _safe_path(raw_dir, rhs_manifest_relative)
            old_manifest_path = Path(str(bridge["old_manifest_path"]))
            old_packets, old_manifest_facts = _read_packet_manifest(old_manifest_path)
            current_packets, current_manifest_facts = _read_packet_manifest(current_path)
            rhs_difference = _packet_difference(old_packets, current_packets)
            rhs_difference.update(
                {
                    "old_packet_count": old_manifest_facts["packet_count"],
                    "current_packet_count": current_manifest_facts["packet_count"],
                    "old_duplicate_count": old_manifest_facts["duplicate_count"],
                    "current_duplicate_count": current_manifest_facts["duplicate_count"],
                }
            )
            if old_manifest_facts["role"] != "candidate_physical_rhs_dual":
                errors.append("old RHS manifest role mismatch")
            if current_manifest_facts["role"] != "full_fe_dual":
                errors.append("current RHS manifest role mismatch")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"RHS canonical bridge is unreadable: {exc}")
    gates["rhs_canonical_bridge"] = bool(
        rhs_difference.get("key_set_equal") is True
        and rhs_difference.get("old_duplicate_count") == 0
        and rhs_difference.get("current_duplicate_count") == 0
        and float(rhs_difference.get("relative_l2", math.inf)) <= T5_CANONICAL_LIMIT
    )
    if not gates["rhs_canonical_bridge"]:
        errors.append("old/current physical RHS canonical identity failed")

    residual_bridge = record.get("residual_bridge")
    if not isinstance(residual_bridge, Mapping):
        residual_errors, residual_facts = ["residual MPI bridge facts are missing"], {}
    else:
        residual_errors, residual_facts = _check_residual_mpi_identity(
            raw_dir, residual_bridge
        )
    errors.extend(residual_errors)
    gates["residual_mpi_identity"] = not residual_errors
    gates["qualified_for_mpi2"] = bool(
        residual_facts.get("qualified_for_mpi2") is True
    )

    artifacts = record.get("artifacts", {})
    residual_artifacts = (
        artifacts.get("residual") if isinstance(artifacts, Mapping) else None
    )
    if not isinstance(residual_artifacts, Mapping):
        residual_action_errors, residual_action_facts = [
            "residual action artifact registry is missing"
        ], {}
    else:
        residual_action_errors, residual_action_facts = _check_residual_authority(
            raw_dir, residual_artifacts
        )
    errors.extend(residual_action_errors)
    gates["residual_physical_action"] = not residual_action_errors

    operator = record.get("operator", {})
    operator_ok = isinstance(operator, Mapping)
    if operator_ok:
        audit = operator.get("physical_action_audit")
        operator_ok = bool(
            operator.get("volume_plus_dynamic_dtn") is True
            and operator.get("t4_transmission_included") is False
            and operator.get("global_aij_materialized") is False
            and operator.get("global_schur_materialized") is False
            and operator.get("ksp_created") is False
            and operator.get("pde_run") is False
            and isinstance(audit, Mapping)
            and audit.get("numeric_allgather") is False
        )
    gates["full_physical_action"] = operator_ok
    if not operator_ok:
        errors.append("full physical action facts failed")

    return {
        "schema": T5_CHECK_SCHEMA,
        "record_schema": record.get("schema"),
        "gates": gates,
        "status": "pass" if not errors and all(gates.values()) else "fail",
        "failures": errors,
        "derived": {
            "old_arrays": old_facts,
            "row_layout_witness": witness_facts,
            "mesh_witness_identity": mesh_facts,
            "rhs_canonical_bridge": rhs_difference,
            "residual_mpi_identity": residual_facts,
            "residual_physical_action": residual_action_facts,
            "external_watchdog": resource_facts,
        },
    }


def check_t5_path(record_path: Path) -> dict[str, Any]:
    return check_t5_record(json.loads(record_path.read_text(encoding="utf-8")))


def check_t5_pair(mpi1_record_path: Path, mpi2_record_path: Path) -> dict[str, Any]:
    mpi1 = check_t5_path(mpi1_record_path)
    mpi2 = check_t5_path(mpi2_record_path)
    failures = list(mpi1.get("failures", [])) + list(mpi2.get("failures", []))
    first = json.loads(mpi1_record_path.read_text(encoding="utf-8"))
    second = json.loads(mpi2_record_path.read_text(encoding="utf-8"))
    first_bridge = first.get("residual_bridge", {})
    second_bridge = second.get("residual_bridge", {})
    if mpi1.get("gates", {}).get("qualified_for_mpi2") is not True:
        failures.append("MPI1 record is not qualified for MPI2 conversion")
    if mpi2.get("gates", {}).get("residual_mpi_identity") is not True:
        failures.append("MPI2 residual re-extraction did not pass")
    if first.get("mpi", {}).get("size") != 1 or second.get("mpi", {}).get("size") != 2:
        failures.append("T5 residual pair is not MPI1 followed by MPI2")
    if first_bridge.get("mpi1_manifest_sha256") != second_bridge.get("mpi1_manifest_sha256"):
        failures.append("MPI2 did not consume the qualified MPI1 residual manifest")
    first_artifacts = first.get("artifacts", {}).get("residual", {})
    second_artifacts = second.get("artifacts", {}).get("residual", {})
    cross_mpi: dict[str, Any] = {}
    for name in ("source", "action", "reference"):
        if not isinstance(first_artifacts, Mapping) or not isinstance(
            second_artifacts, Mapping
        ):
            failures.append("residual MPI action artifact registry is missing")
            break
        left_ref = first_artifacts.get(name)
        right_ref = second_artifacts.get(name)
        if not isinstance(left_ref, Mapping) or not isinstance(right_ref, Mapping):
            failures.append(f"residual MPI {name} manifest is missing")
            continue
        compare_errors, compare_facts = _compare_manifest_refs(
            Path(str(first.get("raw_dir", mpi1_record_path.parent))).resolve(),
            left_ref,
            Path(str(second.get("raw_dir", mpi2_record_path.parent))).resolve(),
            right_ref,
            tolerance=T5_CANONICAL_LIMIT,
        )
        failures.extend(f"MPI1/MPI2 {name}: {error}" for error in compare_errors)
        cross_mpi[name] = compare_facts
    return {
        "schema": T5_CHECK_SCHEMA,
        "kind": "mpi1-mpi2-pair",
        "records": {
            "mpi1": mpi1,
            "mpi2": mpi2,
        },
        "derived": {"residual_cross_mpi": cross_mpi},
        "status": "pass" if not failures else "fail",
        "failures": failures,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check one T5 raw authority record")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--identity-record", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mpi1-record", type=Path)
    parser.add_argument("--mpi2-record", type=Path)
    args = parser.parse_args()
    if args.identity_record is not None:
        result = check_physical_identity(args.identity_record)
    elif args.record is not None:
        result = check_t5_path(args.record)
    elif args.mpi1_record is not None and args.mpi2_record is not None:
        result = check_t5_pair(args.mpi1_record, args.mpi2_record)
    else:
        parser.error("provide --record or both --mpi1-record and --mpi2-record")
    serialized = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        if args.output.exists():
            parser.error(f"checker output already exists: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
