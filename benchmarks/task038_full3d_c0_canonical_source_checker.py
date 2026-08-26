"""Independent checker for the V13 C0 physical-canonical-source audit.

Only JSON, canonical packet shards, and the shared external-watchdog ledger are
read here.  The worker and solver are deliberately not imported; this module
recomputes the source hash, canonical packet relations, and owner-adjoint work
from the recorded physical keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.task038_full3d_interlevel_spectral_checker import (
    _check_watchdog,
)


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
MODULE = "benchmarks.run_task038_full3d_c0_canonical_source"
SCHEMA = "task038.full3d.canonical-source.c0-record.v3"
CHECK_SCHEMA = "task038.full3d.canonical-source.c0-check.v4"
MARKER_SCHEMA = "task038.full3d.canonical-source.c0-marker.v3"
WATCHDOG_SCHEMA = "task038.lor-native-complex-hx.foundation-e-watchdog.v1"
SHARD_SCHEMA = "task037.canonical-vector-shard.v1"
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
KEY_DIGEST_ALGORITHM = "sha256(canonical-key-json-v1)"
C0_FIXED_SEED = "task038-c0-physical-canonical-source-v1"
C0_CASES = ("p3-h50-mpi1", "p3-h50-mpi2")
C0_MARKERS = (
    "startup",
    "preflight",
    "mesh",
    "sources",
    "transfer",
    "packets",
    "release",
)
PACKET_ROLES = {
    "source_primal": "full_fe",
    "source_dual": "full_fe_dual",
    "projected_primal": "full_fe",
    "projected_repeat_primal": "full_fe",
    "projected_scaled_primal": "full_fe",
    "projected_combo_primal": "full_fe",
    "adjoint_dual": "full_fe_dual",
    "adjoint_repeat_dual": "full_fe_dual",
    "explicit_adjoint_dual": "full_fe_dual",
}
SOURCE_LABELS = ("source_primal", "source_dual")
OUTPUT_LABELS = tuple(label for label in PACKET_ROLES if label not in SOURCE_LABELS)
ALPHA = 0.37 + 0.19j
BETA = -0.23 + 0.41j
SOURCE2_SCALE = 0.5 - 0.75j
SOURCE_RELATIVE_LIMIT = 1.0e-13
SOURCE_MAX_ABS_LIMIT = 1.0e-12
OUTPUT_RELATIVE_LIMIT = 1.0e-11
ADJOINT_LIMIT = 1.0e-11
LINEARITY_LIMIT = 1.0e-11
REPEAT_LIMIT = 1.0e-13
WATCHDOG_RSS_LIMIT = 2_000_000_000
EXPECTED_INPUT_BYTES = 2119
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_RESOLVED_BYTES = 4076
EXPECTED_RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"), parse_constant=_reject_constant
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and bool(np.isfinite(float(value)))


def _complex_pair(value: Any) -> complex | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if any(type(item) not in (int, float) for item in value):
        return None
    result = complex(float(value[0]), float(value[1]))
    return result if np.isfinite(result.real) and np.isfinite(result.imag) else None


def _key_jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"tuple": [_key_jsonable(item) for item in value]}
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("canonical key contains a non-finite float")
        return value
    raise TypeError(f"unsupported canonical key value: {type(value).__name__}")


def _key_from_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) != {"tuple"} or not isinstance(value["tuple"], list):
            raise ValueError("canonical key tuple encoding is invalid")
        return tuple(_key_from_jsonable(item) for item in value["tuple"])
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("canonical key contains a non-finite float")
        return value
    raise ValueError("canonical key JSON value is invalid")


def _canonical_key_json_bytes(key: tuple[Any, ...]) -> bytes:
    return json.dumps(
        _key_jsonable(key),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _source_jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return {"tuple": [_source_jsonable(item) for item in value]}
    if isinstance(value, list):
        return [_source_jsonable(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("source identity contains a non-finite float")
        return {"float_hex": value.hex()}
    raise TypeError(f"unsupported source identity value: {type(value).__name__}")


def _source_coefficient(key: tuple[Any, ...], fixed_seed: str) -> tuple[np.complex128, str]:
    if len(key) != 7:
        raise ValueError("canonical source key must have seven fields")
    role, dimension, entity, basis, orientation, master, phase = key
    if role not in {"full_fe", "full_fe_dual"}:
        raise ValueError("canonical source key role is invalid")
    payload = {
        "schema": "task038.v13.c0.physical-canonical-source.v1",
        "role": str(role),
        "physical_entity_geometry_key": _source_jsonable(
            tuple(sorted(tuple(int(component) for component in point) for point in entity))
        ),
        "entity_dimension": int(dimension),
        "entity_local_basis_index": int(basis),
        "canonical_orientation_state": _source_jsonable(orientation),
        "floquet_master_phase_state": {
            "master": _source_jsonable(master),
            "phase": _source_jsonable(phase),
        },
        "fixed_seed": fixed_seed,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    raw = bytes.fromhex(digest)
    value = np.complex128(
        0.5 + int.from_bytes(raw[:8], "big") / float(1 << 64)
        + 1j * (-0.5 + int.from_bytes(raw[8:16], "big") / float(1 << 64))
    )
    return value, digest


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _relative_values(left: dict[tuple[Any, ...], complex], right: dict[tuple[Any, ...], complex]) -> tuple[float, float, int, int]:
    left_keys = set(left)
    right_keys = set(right)
    common = left_keys & right_keys
    missing = len(right_keys - left_keys)
    extra = len(left_keys - right_keys)
    ordered = sorted(common, key=_canonical_key_json_bytes)
    difference = [left[key] - right[key] for key in ordered]
    reference = [right[key] for key in ordered]
    difference_norm = math.sqrt(
        max(math.fsum(float(abs(value) ** 2) for value in difference), 0.0)
    )
    reference_norm = math.sqrt(
        max(math.fsum(float(abs(value) ** 2) for value in reference), 0.0)
    )
    relative = difference_norm / max(reference_norm, np.finfo(float).tiny)
    maximum = max((abs(value) for value in difference), default=0.0)
    return float(relative), float(maximum), missing, extra


def _work(primal: dict[tuple[Any, ...], complex], dual: dict[tuple[Any, ...], complex]) -> complex | None:
    if not set(dual).issubset(primal):
        return None
    ordered = sorted(dual, key=_canonical_key_json_bytes)
    products = [np.conjugate(dual[key]) * primal[key] for key in ordered]
    return complex(
        math.fsum(float(value.real) for value in products),
        math.fsum(float(value.imag) for value in products),
    )


def _base_packets(packets: dict[tuple[Any, ...], complex]) -> dict[tuple[Any, ...], complex]:
    return {tuple(key[1:]): value for key, value in packets.items()}


def _packet_file(path: Path, expected_sha: str, errors: list[str]) -> tuple[tuple[tuple[Any, ...], complex], ...]:
    digest = _sha256(path) if path.is_file() else None
    if digest != expected_sha:
        errors.append(f"canonical shard SHA mismatch: {path.name}")
        return ()
    packets: list[tuple[tuple[Any, ...], complex]] = []
    try:
        with path.open("rb") as stream:
            for line_number, raw_line in enumerate(stream, 1):
                row = json.loads(raw_line, parse_constant=_reject_constant)
                if not isinstance(row, dict) or set(row) != {"key", "key_sha256", "schema_version", "value"}:
                    errors.append(f"canonical shard row malformed: {path.name}:{line_number}")
                    continue
                if row["schema_version"] != SHARD_SCHEMA:
                    errors.append(f"canonical shard schema mismatch: {path.name}:{line_number}")
                    continue
                key = _key_from_jsonable(row["key"])
                if not isinstance(key, tuple) or hashlib.sha256(_canonical_key_json_bytes(key)).hexdigest() != row["key_sha256"]:
                    errors.append(f"canonical key digest mismatch: {path.name}:{line_number}")
                    continue
                pair = row["value"]
                value = _complex_pair(pair)
                if value is None:
                    errors.append(f"canonical coefficient is nonfinite/malformed: {path.name}:{line_number}")
                    continue
                packets.append((key, value))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"canonical shard unreadable: {path.name}: {exc}")
    return tuple(packets)


def _load_packet_artifact(
    raw_dir: Path,
    label: str,
    descriptor: Any,
    mpi_size: int,
    errors: list[str],
) -> dict[tuple[Any, ...], complex]:
    if not isinstance(descriptor, dict) or set(descriptor) != {
        "role", "manifest_relative_path", "manifest_sha256", "packet_count",
        "duplicate_count", "finite",
    }:
        errors.append(f"packet descriptor key set mismatch: {label}")
        return {}
    expected_role = PACKET_ROLES[label]
    if descriptor["role"] != expected_role:
        errors.append(f"packet descriptor role mismatch: {label}")
    relative = descriptor["manifest_relative_path"]
    manifest_path = raw_dir / relative if isinstance(relative, str) else raw_dir / "__missing__"
    if not isinstance(relative, str) or Path(relative).is_absolute() or not _inside(manifest_path, raw_dir) or not manifest_path.is_file():
        errors.append(f"packet manifest path invalid: {label}")
        return {}
    if _sha256(manifest_path) != descriptor["manifest_sha256"]:
        errors.append(f"packet manifest SHA mismatch: {label}")
        return {}
    try:
        manifest = _read_json(manifest_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"packet manifest unreadable: {label}: {exc}")
        return {}
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("role") != expected_role or manifest.get("mpi_size") != mpi_size or manifest.get("dtype") != "complex128" or manifest.get("key_digest_algorithm") != KEY_DIGEST_ALGORITHM:
        errors.append(f"packet manifest identity mismatch: {label}")
        return {}
    shards = manifest.get("per_rank_shards")
    if not isinstance(shards, list) or len(shards) != mpi_size:
        errors.append(f"packet shard count mismatch: {label}")
        return {}
    packets: list[tuple[tuple[Any, ...], complex]] = []
    local_duplicates = 0
    for shard in shards:
        if not isinstance(shard, dict) or set(shard) != {
            "filename", "packet_count", "file_sha256", "key_digest_algorithm",
            "dtype", "schema_version", "packet_finite", "local_duplicate_count",
        }:
            errors.append(f"packet shard descriptor malformed: {label}")
            continue
        filename = shard["filename"]
        path = manifest_path.parent / filename if isinstance(filename, str) else manifest_path.parent / "__missing__"
        if not isinstance(filename, str) or Path(filename).is_absolute() or not _inside(path, raw_dir):
            errors.append(f"packet shard path invalid: {label}")
            continue
        rows = _packet_file(path, shard["file_sha256"], errors)
        valid_rows = []
        for row_number, (key, value) in enumerate(rows, 1):
            if not isinstance(key, tuple) or len(key) != 7 or key[0] != expected_role:
                errors.append(
                    f"canonical packet key identity mismatch: {label}:{row_number}"
                )
                continue
            valid_rows.append((key, value))
        rows = tuple(valid_rows)
        if shard["schema_version"] != SHARD_SCHEMA or shard["dtype"] != "complex128" or shard["key_digest_algorithm"] != KEY_DIGEST_ALGORITHM or shard["packet_count"] != len(rows):
            errors.append(f"packet shard facts mismatch: {label}")
        actual_duplicate = len(rows) - len({key for key, _value in rows})
        if shard["local_duplicate_count"] != actual_duplicate:
            errors.append(f"packet local duplicate fact mismatch: {label}")
        if shard["packet_finite"] is not True:
            errors.append(f"packet shard finite fact is false: {label}")
        local_duplicates += actual_duplicate
        packets.extend(rows)
    if manifest.get("global_summed_packet_count") != len(packets) or manifest.get("summed_local_duplicate_count") != local_duplicates:
        errors.append(f"packet manifest counts mismatch: {label}")
    if descriptor["packet_count"] != len(packets) or descriptor["duplicate_count"] != local_duplicates or descriptor["finite"] is not True:
        errors.append(f"packet descriptor facts mismatch: {label}")
    result: dict[tuple[Any, ...], complex] = {}
    for key, value in packets:
        if key in result:
            errors.append(f"canonical packet duplicate across ranks: {label}")
        result[key] = value
    return result


def _check_source_packets(
    label: str,
    packets: dict[tuple[Any, ...], complex],
    facts: Any,
    fixed_seed: str,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    if not isinstance(facts, dict):
        errors.append(f"source facts missing: {label}")
        return {
            "global_packet_count": 0,
            "global_independent_packet_count": 0,
            "global_dependent_packet_count": 0,
            "dependent_relation_relative": 0.0,
            "dependent_relation_max_abs": 0.0,
        }
    required = {
        "schema", "role", "fixed_seed", "global_packet_count",
        "global_independent_packet_count", "global_dependent_packet_count",
        "dependent_placeholder_non_authoritative",
        "dependent_value_authority", "source_finite", "source_nonzero",
        "source_generation", "phase_application",
    }
    expected_phase = (
        "finalized_floquet_mpc_once"
        if label == "source_primal"
        else "dual_source_slave_zero_no_phase_reapplication"
    )
    if set(facts) != required or facts["schema"] != "task038.v13.c0.physical-canonical-source.v1" or facts["role"] != PACKET_ROLES[label] or facts["fixed_seed"] != fixed_seed or facts["global_packet_count"] != len(packets) or facts["source_finite"] is not True or facts["source_nonzero"] is not True or facts["source_generation"] != "physical_canonical_key_sha256_v1" or facts["phase_application"] != expected_phase:
        errors.append(f"source facts identity mismatch: {label}")
    dependent = 0
    independent = 0
    relation_relative = 0.0
    relation_max_abs = 0.0
    independent_difference_sq = 0.0
    independent_expected_sq = 0.0
    independent_max_abs = 0.0
    independent_exact_mismatch_count = 0
    for key, value in packets.items():
        if not isinstance(key, tuple) or len(key) != 7 or key[0] != PACKET_ROLES[label]:
            errors.append(f"source packet key/role mismatch: {label}")
            continue
        if label == "source_dual":
            if key[5] is not None:
                errors.append("dual source contains a dependent key")
            expected, _digest = _source_coefficient(key, fixed_seed)
            observed = complex(value)
            expected_value = complex(expected)
            difference = abs(observed - expected_value)
            independent_difference_sq += float(difference) ** 2
            independent_expected_sq += abs(expected_value) ** 2
            independent_max_abs = max(independent_max_abs, float(difference))
            if np.asarray(value, dtype=np.complex128).tobytes() != expected.tobytes():
                independent_exact_mismatch_count += 1
            independent += 1
            continue
        if key[5] is None:
            expected, _digest = _source_coefficient(key, fixed_seed)
            if np.asarray(value, dtype=np.complex128).tobytes() != expected.tobytes():
                errors.append(f"primal source hash coefficient mismatch: {label}")
            independent += 1
        else:
            dependent += 1
            master_candidates = [
                master_value
                for master_key, master_value in packets.items()
                if master_key[0] == key[0]
                and master_key[1] == key[1]
                and master_key[2] == key[5]
                and master_key[3] == key[3]
                and master_key[5] is None
            ]
            if len(master_candidates) != 1:
                errors.append("primal dependent value is not the finalized master relation")
                continue
            master_value = master_candidates[0]
            difference = abs(value - master_value)
            relation_max_abs = max(relation_max_abs, float(difference))
            relative = float(
                difference
                / max(abs(value), abs(master_value), np.finfo(float).tiny)
            )
            relation_relative = max(relation_relative, relative)
            if relative > 1.0e-13 or difference > 1.0e-12:
                gates.append("C0 primal dependent/master relation exceeds source limits")
    if facts.get("global_independent_packet_count") != independent or facts.get("global_dependent_packet_count") != dependent:
        errors.append(f"source independent/dependent counts mismatch: {label}")
    if label == "source_primal" and (facts.get("dependent_placeholder_non_authoritative") is not True or facts.get("dependent_value_authority") != "finalized_mpc_master_phase_relation"):
        errors.append("primal dependent source authority is not explicit")
    if label == "source_dual" and (facts.get("dependent_placeholder_non_authoritative") is not False or facts.get("dependent_value_authority") != "slave_zero_dual_storage"):
        errors.append("dual source authority is not explicit")
    independent_relative = float(
        math.sqrt(independent_difference_sq)
        / max(math.sqrt(independent_expected_sq), np.finfo(float).tiny)
    ) if independent else 0.0
    if label == "source_dual" and (
        independent_relative > SOURCE_RELATIVE_LIMIT
        or independent_max_abs > SOURCE_MAX_ABS_LIMIT
    ):
        gates.append("C0 dual independent source coefficient limits exceeded")
    return {
        "global_packet_count": len(packets),
        "global_independent_packet_count": independent,
        "global_dependent_packet_count": dependent,
        "dependent_relation_relative": relation_relative,
        "dependent_relation_max_abs": relation_max_abs,
        "independent_source_relative": independent_relative,
        "independent_source_max_abs": independent_max_abs,
        "independent_source_exact_mismatch_count": independent_exact_mismatch_count,
    }


def _check_packet_relations(
    packets: dict[str, dict[tuple[Any, ...], complex]],
    facts: Any,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    if not isinstance(facts, dict):
        errors.append("transfer facts are missing")
        return {}
    required = {
        "pair_fine_to_coarse", "primal_output_finite", "dual_output_finite",
        "primal_repeat_relative", "adjoint_repeat_relative", "linearity_relative",
        "input_unchanged", "global_work_lhs", "global_work_rhs", "explicit_work_rhs",
        "global_adjoint_work_relative", "explicit_adjoint_work_relative",
        "implemented_vs_explicit_vector_relative", "phase_application_primal",
        "phase_application_adjoint", "coarse_dual_reduction", "source_finite", "source_nonzero",
    }
    if set(facts) != required:
        errors.append("transfer facts key set is not exact")
    for label, value in packets.items():
        if not value or not all(np.isfinite(complex(item)) for item in value.values()):
            gates.append(f"C0 packet {label} is empty or nonfinite")
    base = {label: _base_packets(value) for label, value in packets.items()}
    scaled_expected = {
        key: SOURCE2_SCALE * value
        for key, value in base["projected_primal"].items()
    }
    combo_keys = set(base["projected_primal"]) & set(base["projected_scaled_primal"])
    combo_expected = {
        key: ALPHA * base["projected_primal"][key]
        + BETA * base["projected_scaled_primal"][key]
        for key in combo_keys
    }
    checks: list[tuple[str, dict[tuple[Any, ...], complex], dict[tuple[Any, ...], complex], float, str]] = [
        ("primal repeat", base["projected_repeat_primal"], base["projected_primal"], REPEAT_LIMIT, "primal_repeat_relative"),
        ("scaled primal", base["projected_scaled_primal"], scaled_expected, OUTPUT_RELATIVE_LIMIT, "scaled_relative"),
        ("combo primal", base["projected_combo_primal"], combo_expected, LINEARITY_LIMIT, "linearity_relative"),
        ("adjoint repeat", base["adjoint_repeat_dual"], base["adjoint_dual"], REPEAT_LIMIT, "adjoint_repeat_relative"),
    ]
    relation_metrics: dict[str, Any] = {}
    for name, actual, expected, limit, stored_key in checks:
        relative, maximum, missing, extra = _relative_values(actual, expected)
        relation_metrics[name] = {"relative": relative, "max_abs": maximum, "missing": missing, "extra": extra}
        if missing or extra or relative > limit:
            gates.append(f"C0 {name} relation failed")
        if stored_key in facts and not _close(facts[stored_key], relative):
            errors.append(f"transfer stored fact mismatch: {stored_key}")
    lhs = _work(base["projected_primal"], base["source_dual"])
    rhs = _work(base["source_primal"], base["adjoint_dual"])
    explicit = _work(base["source_primal"], base["explicit_adjoint_dual"])
    if lhs is None or rhs is None or explicit is None:
        errors.append("canonical work key closure is not exact")
        return {"relations": relation_metrics}
    canonical_relative = _scalar_relative(lhs, rhs)
    explicit_relative = _scalar_relative(lhs, explicit)
    vector_relative, vector_max, missing, extra = _relative_values(
        packets["adjoint_dual"], packets["explicit_adjoint_dual"]
    )
    if missing or extra or vector_relative > ADJOINT_LIMIT:
        gates.append("C0 implemented versus independent P^H vector failed")
    if canonical_relative > ADJOINT_LIMIT or explicit_relative > ADJOINT_LIMIT:
        gates.append("C0 canonical adjoint work failed")
    stored_lhs = _complex_pair(facts.get("global_work_lhs"))
    stored_rhs = _complex_pair(facts.get("global_work_rhs"))
    stored_explicit = _complex_pair(facts.get("explicit_work_rhs"))
    if stored_lhs is None or stored_rhs is None or stored_explicit is None:
        errors.append("global work facts are missing or malformed")
    else:
        global_relative = _scalar_relative(stored_lhs, stored_rhs)
        explicit_global_relative = _scalar_relative(stored_lhs, stored_explicit)
        if global_relative > ADJOINT_LIMIT or explicit_global_relative > ADJOINT_LIMIT:
            gates.append("C0 global adjoint work failed")
        if not _close(facts.get("global_adjoint_work_relative"), global_relative):
            errors.append("transfer stored fact mismatch: global_adjoint_work_relative")
        if not _close(facts.get("explicit_adjoint_work_relative"), explicit_global_relative):
            errors.append("transfer stored fact mismatch: explicit_adjoint_work_relative")
        for actual, stored, name in (
            (lhs, stored_lhs, "lhs"),
            (rhs, stored_rhs, "rhs"),
            (explicit, stored_explicit, "explicit_rhs"),
        ):
            if _scalar_relative(actual, stored) > ADJOINT_LIMIT:
                gates.append(f"C0 global/canonical work mismatch: {name}")
    global_relative = _scalar_relative(stored_lhs, stored_rhs) if stored_lhs is not None and stored_rhs is not None else None
    explicit_global_relative = _scalar_relative(stored_lhs, stored_explicit) if stored_lhs is not None and stored_explicit is not None else None
    for value, key in ((vector_relative, "implemented_vs_explicit_vector_relative"),):
        if not _close(facts.get(key), value):
            errors.append(f"transfer stored fact mismatch: {key}")
    if facts.get("pair_fine_to_coarse") != [3, 1] or facts.get("primal_output_finite") is not True or facts.get("dual_output_finite") is not True or facts.get("input_unchanged") is not True or facts.get("phase_application_primal") != "finalized_floquet_mpc_once" or facts.get("phase_application_adjoint") != "fine_dual_homogenize_then_coarse_C^H_once" or facts.get("coarse_dual_reduction") != "C^H_once" or facts.get("source_finite") is not True or facts.get("source_nonzero") is not True:
        errors.append("transfer fixed identity facts are not closed")
    return {
        "canonical_work_lhs": [float(lhs.real), float(lhs.imag)],
        "canonical_work_rhs": [float(rhs.real), float(rhs.imag)],
        "canonical_adjoint_work_relative": canonical_relative,
        "canonical_explicit_adjoint_work_relative": explicit_relative,
        "implemented_vs_explicit_vector_relative": vector_relative,
        "implemented_vs_explicit_vector_max_abs": vector_max,
        "global_work_lhs": None if stored_lhs is None else [float(stored_lhs.real), float(stored_lhs.imag)],
        "global_work_rhs": None if stored_rhs is None else [float(stored_rhs.real), float(stored_rhs.imag)],
        "explicit_global_work_rhs": None if stored_explicit is None else [float(stored_explicit.real), float(stored_explicit.imag)],
        "global_adjoint_work_relative": global_relative,
        "global_explicit_adjoint_work_relative": explicit_global_relative,
        "relations": relation_metrics,
    }


def _scalar_relative(left: complex, right: complex) -> float:
    return float(abs(left - right) / max(abs(left), abs(right), np.finfo(float).tiny))


def _close(reported: Any, actual: float, tolerance: float = 1.0e-10) -> bool:
    return _finite(reported) and bool(np.isclose(float(reported), float(actual), rtol=tolerance, atol=1.0e-12))


def _check_provenance(record: dict[str, Any], record_path: Path, expected_sha: str, errors: list[str]) -> bool:
    failed = False
    case = record.get("case")
    mpi_size = int(case.rsplit("mpi", 1)[-1]) if case in C0_CASES else -1
    if record.get("schema") != SCHEMA or record.get("stage") != "c0" or record.get("case") not in C0_CASES or record.get("mpi_size") != mpi_size or record.get("degree") != 3 or record.get("h_nm") != 50.0 or record.get("branch") != BRANCH:
        errors.append("C0 fixed stage/case identity mismatch")
        failed = True
    source = record.get("source")
    for name in ("start", "end"):
        item = source.get(name) if isinstance(source, dict) else None
        if not isinstance(item, dict) or item.get("commit_sha") != expected_sha or item.get("branch") != BRANCH or item.get("clean") is not True:
            errors.append(f"C0 source {name} identity mismatch")
            failed = True
    runtime = record.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("qualified_activation") != "1" or runtime.get("mpi_size") != mpi_size or runtime.get("scalar_dtype") != "complex128" or runtime.get("int_dtype") != "int32" or not Path(str(runtime.get("sys_executable", ""))).is_absolute():
        errors.append("C0 runtime ABI identity mismatch")
        failed = True
    threads = runtime.get("threads") if isinstance(runtime, dict) else None
    if not isinstance(threads, dict) or any(threads.get(name) != "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")):
        errors.append("C0 thread identity mismatch")
        failed = True
    raw_dir = record.get("raw_dir")
    raw_path = Path(raw_dir).resolve() if isinstance(raw_dir, str) else None
    record_resolved = record_path.resolve()
    if not isinstance(raw_dir, str) or not Path(raw_dir).is_absolute() or record.get("record_path") != str(record_resolved) or raw_path == record_resolved or raw_path.parent != record_resolved.parent:
        errors.append("C0 record/raw path identity mismatch")
        failed = True
    command = record.get("command")
    expected_input = str((Path(__file__).resolve().parents[1] / "input/templates/full3d_iterative_example.dat").resolve())
    expected_command = [
        str(runtime.get("sys_executable")) if isinstance(runtime, dict) else "",
        "-m", MODULE, "--stage", "c0", "--case", str(case),
        "--raw-dir", str(raw_dir), "--record", str(record.get("record_path")),
        "--expected-source-sha", expected_sha, "--expected-mpi-size", str(mpi_size),
        "--input", expected_input, "--fixed-seed", C0_FIXED_SEED,
    ]
    if command != expected_command:
        errors.append("C0 worker command identity mismatch")
        failed = True
    identity = record.get("input_identity")
    if not isinstance(identity, dict) or identity.get("path_relative") != "input/templates/full3d_iterative_example.dat" or identity.get("raw_bytes") != EXPECTED_INPUT_BYTES or identity.get("raw_sha256") != EXPECTED_INPUT_SHA256 or identity.get("resolved_bytes") != EXPECTED_RESOLVED_BYTES or identity.get("resolved_sha256") != EXPECTED_RESOLVED_SHA256 or identity.get("physical_model_sha256") != EXPECTED_PHYSICAL_MODEL_SHA256:
        errors.append("C0 fixed input identity mismatch")
        failed = True
    provenance = record.get("provenance")
    expected_provenance = {
        "canonical_source_schema": "task038.v13.c0.physical-canonical-source.v1",
        "fixed_seed": C0_FIXED_SEED,
        "hash_fields": [
            "role", "physical_entity_geometry_key", "entity_dimension",
            "entity_local_basis_index", "canonical_orientation_state",
            "floquet_master_phase_state", "fixed_seed",
        ],
        "forbidden_source_fields": [
            "PETSc global row id", "rank id", "local row id", "ownership range",
            "iteration order", "Python object hash",
        ],
        "source_generation": "physical_canonical_key_sha256_v1",
    }
    if provenance != expected_provenance:
        errors.append("C0 source provenance identity mismatch")
        failed = True
    settings = record.get("settings")
    expected_settings = {
        "levels": [3, 1], "transfer_pair": [3, 1],
        "input_relative_limit": SOURCE_RELATIVE_LIMIT,
        "input_max_abs_limit": SOURCE_MAX_ABS_LIMIT,
        "output_relative_limit": OUTPUT_RELATIVE_LIMIT,
        "adjoint_limit": ADJOINT_LIMIT,
        "phase_once": "finalized_floquet_mpc_once",
        "canonical_order": "structured physical-key JSON after rank-shard merge",
    }
    if settings != expected_settings:
        errors.append("C0 settings identity mismatch")
        failed = True
    return failed


def _check_architecture(record: dict[str, Any], errors: list[str]) -> None:
    architecture = record.get("architecture")
    if not isinstance(architecture, dict) or set(architecture) != {"forbidden", "owner", "levels"}:
        errors.append("C0 architecture key set is not exact")
        return
    forbidden = architecture["forbidden"]
    expected = {
        "global_transfer_matrix", "numeric_allgather", "global_high_order_aij",
        "global_direct_coarse", "p1_factor", "smoother", "ksp",
        "physical_solve", "recovery", "static_condensation",
    }
    if not isinstance(forbidden, dict) or set(forbidden) != expected or any(value is not False for value in forbidden.values()):
        errors.append("C0 forbidden architecture is not closed")
    owner = architecture["owner"]
    for key in ("global_transfer_matrix", "numeric_allgather", "static_condensation", "physical", "pde", "ksp_created", "vcycle_created"):
        if not isinstance(owner, dict) or owner.get(key) is not False:
            errors.append(f"C0 owner forbidden fact is not false: {key}")
    levels = architecture["levels"]
    if not isinstance(levels, dict) or set(levels) != {"level3", "level1"}:
        errors.append("C0 level architecture is not exact")
        return
    for name, degree in (("level3", 3), ("level1", 1)):
        item = levels[name]
        if not isinstance(item, dict) or item.get("degree") != degree or type(item.get("global_rows")) is not int or item["global_rows"] <= 0 or type(item.get("local_owned_rows")) is not int or item["local_owned_rows"] <= 0:
            errors.append(f"C0 level facts invalid: {name}")


def _check_markers(record: dict[str, Any], raw_dir: Path, record_path: Path, expected_sha: str, errors: list[str]) -> None:
    info = record.get("markers")
    if not isinstance(info, dict) or set(info) != {"relative_dir", "names", "wall_time_ns"} or info.get("relative_dir") != "markers" or tuple(info.get("names", ())) != C0_MARKERS:
        errors.append("C0 marker record is not exact")
        return
    wall = info["wall_time_ns"]
    if not isinstance(wall, dict) or set(wall) != set(C0_MARKERS):
        errors.append("C0 marker wall-time map is not exact")
    marker_dir = raw_dir / info["relative_dir"] if isinstance(info["relative_dir"], str) else raw_dir / "__missing__"
    times: list[int] = []
    for name in C0_MARKERS:
        path = marker_dir / f"{name}.json"
        try:
            item = _read_json(path)
            stamp = item["wall_time_ns"]
            if item.get("schema") != MARKER_SCHEMA or item.get("marker") != name or item.get("source_sha") != expected_sha or type(stamp) is not int or wall.get(name) != stamp:
                errors.append(f"C0 marker identity mismatch: {name}")
            else:
                times.append(stamp)
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"C0 marker unreadable: {name}: {exc}")
    closeout = marker_dir / "record_closeout.json"
    try:
        item = _read_json(closeout)
        facts = item.get("facts")
        stamp = item.get("wall_time_ns")
        if item.get("schema") != MARKER_SCHEMA or item.get("marker") != "record_closeout" or item.get("source_sha") != expected_sha or type(stamp) is not int or not isinstance(facts, dict) or facts.get("record_path") != str(record_path.resolve()) or facts.get("record_sha256") != _sha256(record_path) or not isinstance(wall.get("release"), int) or stamp <= wall["release"]:
            errors.append("C0 record_closeout is not bound to record")
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"C0 record_closeout unreadable: {exc}")
    if marker_dir.is_dir() and {path.name for path in marker_dir.glob("*.json")} != {f"{name}.json" for name in C0_MARKERS} | {"record_closeout.json"}:
        errors.append("C0 marker directory has unauthorized files")
    if len(times) == len(C0_MARKERS) and times != sorted(times):
        errors.append("C0 marker sequence is not monotonic")


def _cross_mpi(
    record: dict[str, Any],
    current: dict[str, dict[tuple[Any, ...], complex]],
    reference_path: Path | None,
    expected_sha: str,
    errors: list[str],
    gates: list[str],
) -> dict[str, Any]:
    mpi_size = record.get("mpi_size")
    if mpi_size == 1:
        if reference_path is not None:
            errors.append("C0 MPI1 must not receive an MPI1 reference")
        return {"status": "mpi1_only_pending_mpi2"}
    if mpi_size != 2 or reference_path is None:
        errors.append("C0 MPI2 requires --mpi1-reference")
        return {"status": "missing_mpi1_reference"}
    reference_path = reference_path.resolve()
    if not reference_path.is_file() or reference_path == Path(str(record.get("record_path"))).resolve():
        errors.append("C0 MPI1 reference is missing or self-referential")
        return {"status": "invalid_mpi1_reference"}
    try:
        reference = _read_json(reference_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"C0 MPI1 reference unreadable: {exc}")
        return {"status": "invalid_mpi1_reference"}
    reference_errors: list[str] = []
    reference_dir = Path(str(reference.get("raw_dir", ""))).resolve()
    if reference.get("schema") != SCHEMA or reference.get("case") != "p3-h50-mpi1" or reference.get("mpi_size") != 1 or reference.get("branch") != BRANCH:
        reference_errors.append("C0 MPI1 reference identity mismatch")
    _check_provenance(reference, reference_path, expected_sha, reference_errors)
    reference_packets: dict[str, dict[tuple[Any, ...], complex]] = {}
    descriptors = reference.get("packet_artifacts") if isinstance(reference, dict) else None
    if not isinstance(descriptors, dict) or set(descriptors) != set(PACKET_ROLES):
        reference_errors.append("C0 MPI1 reference packet labels are not exact")
    else:
        for label in PACKET_ROLES:
            reference_packets[label] = _load_packet_artifact(reference_dir, label, descriptors[label], 1, reference_errors)
    if reference_errors:
        errors.extend(f"C0 MPI1 reference: {item}" for item in reference_errors)
        return {"status": "invalid_mpi1_reference", "path": str(reference_path), "sha256": _sha256(reference_path)}
    comparisons: list[dict[str, Any]] = []
    for label in PACKET_ROLES:
        relative, maximum, missing, extra = _relative_values(current[label], reference_packets[label])
        limit = SOURCE_RELATIVE_LIMIT if label in SOURCE_LABELS else OUTPUT_RELATIVE_LIMIT
        if missing or extra or relative > limit or (label in SOURCE_LABELS and maximum > SOURCE_MAX_ABS_LIMIT):
            gates.append(f"C0 MPI1/MPI2 canonical identity failed: {label}")
        comparisons.append({"label": label, "relative": relative, "max_abs": maximum, "missing": missing, "extra": extra, "limit": limit})
    return {"status": "compared", "path": str(reference_path), "sha256": _sha256(reference_path), "packet_comparisons": comparisons, "relative_limit": OUTPUT_RELATIVE_LIMIT, "source_relative_limit": SOURCE_RELATIVE_LIMIT, "source_max_abs_limit": SOURCE_MAX_ABS_LIMIT}


def check_record(record_path: Path, watchdog_compact: Path, expected_sha: str, mpi1_reference: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    gates: list[str] = []
    lifecycle_failures: list[str] = []
    try:
        record = _read_json(record_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"schema": CHECK_SCHEMA, "passed": False, "classification": "CONTRACT_INVALID", "contract_errors": [str(exc)], "gate_failures": []}
    if not isinstance(record, dict):
        return {"schema": CHECK_SCHEMA, "passed": False, "classification": "CONTRACT_INVALID", "contract_errors": ["record is not an object"], "gate_failures": []}
    for forbidden in ("status", "passed", "classification"):
        if forbidden in record:
            errors.append(f"worker record must not contain {forbidden}")
    provenance_error = _check_provenance(record, record_path, expected_sha, errors)
    raw_dir = Path(str(record.get("raw_dir", ""))).resolve()
    if not raw_dir.is_dir():
        errors.append("C0 raw_dir is missing")
    _check_architecture(record, errors)
    _check_markers(record, raw_dir, record_path, expected_sha, errors)
    resource = _check_watchdog(
        watchdog_compact, record, record_path, expected_sha,
        errors, gates, lifecycle_failures,
        mpi_size=record.get("mpi_size"), allow_mpiexec_n2=True,
    )
    if resource.get("watchdog_raw") is not None and Path(str(resource["watchdog_raw"])).parent != raw_dir.parent:
        errors.append("C0 watchdog raw is not sibling to worker raw_dir")
    descriptors = record.get("packet_artifacts")
    packet_sets: dict[str, dict[tuple[Any, ...], complex]] = {}
    if not isinstance(descriptors, dict) or set(descriptors) != set(PACKET_ROLES):
        errors.append("C0 packet label set is not exact")
    else:
        for label in PACKET_ROLES:
            packet_sets[label] = _load_packet_artifact(raw_dir, label, descriptors[label], int(record.get("mpi_size", -1)), errors)
    source_facts = record.get("source_facts")
    source_metrics: dict[str, Any] = {}
    if isinstance(source_facts, dict):
        source_metrics["primal"] = _check_source_packets(
            "source_primal", packet_sets.get("source_primal", {}),
            source_facts.get("primal"), C0_FIXED_SEED, errors, gates
        )
        source_metrics["dual"] = _check_source_packets(
            "source_dual", packet_sets.get("source_dual", {}),
            source_facts.get("dual"), C0_FIXED_SEED, errors, gates
        )
    else:
        errors.append("C0 source facts are missing")
    transfer_metrics = _check_packet_relations(packet_sets, record.get("transfer_facts"), errors, gates) if len(packet_sets) == len(PACKET_ROLES) else {}
    cross = _cross_mpi(record, packet_sets, mpi1_reference, expected_sha, errors, gates) if len(packet_sets) == len(PACKET_ROLES) else {"status": "not_available"}
    if not isinstance(record.get("record_authority"), str) or record["record_authority"] != "raw canonical packet shards; checker derives C0 classification":
        errors.append("C0 record authority is not raw-only")
    if provenance_error:
        classification = "INPUT_PROVENANCE_INVALID"
    elif lifecycle_failures:
        classification = "EXECUTION_LIFECYCLE_FAILED"
    elif resource.get("resource_gate_failed") is True:
        classification = "RESOURCE_GATE_FAILED"
    elif errors:
        classification = "CONTRACT_INVALID"
    elif gates:
        classification = "CLOSED_BY_C0_CANONICAL_IDENTITY_GATE"
    elif record.get("mpi_size") == 1:
        classification = "C0_CANONICAL_SOURCE_PASS_MPI1_ONLY"
    else:
        classification = "C0_CANONICAL_SOURCE_PASS_MPI1_MPI2"
    return {
        "schema": CHECK_SCHEMA,
        "passed": classification in {"C0_CANONICAL_SOURCE_PASS_MPI1_ONLY", "C0_CANONICAL_SOURCE_PASS_MPI1_MPI2"},
        "classification": classification,
        "contract_errors": errors,
        "gate_failures": gates,
        "execution_lifecycle_failures": lifecycle_failures,
        "metrics": {"transfer": transfer_metrics, "source": source_metrics, "cross_mpi_identity": cross, "resource": resource, "packet_labels": list(PACKET_ROLES)},
        "record": {"path": str(record_path.resolve()), "sha256": _sha256(record_path)},
        "expected_source_sha": expected_sha,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--watchdog-compact", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--mpi1-reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f"checker output already exists: {args.output}")
    result = check_record(
        args.record.resolve(), args.watchdog_compact.resolve(), args.expected_source_sha,
        args.mpi1_reference.resolve() if args.mpi1_reference is not None else None,
    )
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
