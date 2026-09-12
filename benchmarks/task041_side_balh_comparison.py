"""Offline Task041 exact-versus-BAL_H comparison checker.

The checker consumes only the hash-bound Task041 exact and candidate consumer
outputs.  It does not start a solver, load a legacy Task39 result, or fit a
phase between the two fields.  The numerical gates are recomputed from the
raw authority, payload, canonical owner shards, and raw supervisor samples.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    KEY_DIGEST_ALGORITHM,
    MANIFEST_SCHEMA,
    SHARD_SCHEMA,
    compare_canonical_manifests,
    read_canonical_manifest,
    read_canonical_packet_shards,
)
from benchmarks.task039_hybrid_direct_identity import (
    _parse_inventory as _task039_parse_inventory,
)
from benchmarks.task039_hybrid_direct_identity import (
    _parse_orders as _task039_parse_orders,
)
from benchmarks.task039_v4_selected_mode_packet import (
    TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
)
from src.io.input_validation import TASK041_BALH_MODEL_IDS, task041_balh_case
from src.modes.selected_mode_packet import _json_bytes as _selected_mode_json_bytes
from src.solvers.hybrid_interface_basis import canonical_mode_keys_sha256

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTRACT_PATH = (
    _REPO_ROOT
    / "docs"
    / "task041_mpi1_shortwave_hybrid_capacity"
    / "outcomes"
    / "records"
    / "task041_side_balh_comparison_contract_v1.json"
)
_AUTHORITY_SCHEMA = "task039.v3-7-hybrid-authority.v1"
_PACKET_IDENTITY_SCHEMA = TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA
_GRID_SCHEMA = "task037b.m10-own-grid-EH-modal-q.v1"
_PAYLOAD_KEYS = (
    "x_nm",
    "y_nm",
    "z_nm",
    "E_V_per_m",
    "H_A_per_m",
    "modal_amplitudes",
    "bottom_q",
    "top_q",
)
_COMPLEX_PAYLOAD_KEYS = frozenset(
    {"E_V_per_m", "H_A_per_m", "modal_amplitudes", "bottom_q", "top_q"}
)
_CANONICAL_ROLES = (
    "bottom.active_trace",
    "bottom.full_fe",
    "top.active_trace",
    "top.full_fe",
)
_RESOURCE_PEAK_FIELDS = (
    "memory_authority_bytes",
    "process_tree_rss_bytes",
    "pss_bytes",
    "uss_bytes",
    "process_tree_swap_bytes",
    "dedicated_cgroup_swap_bytes",
    "swap_bytes",
)
_WORKFLOW_MEMORY_FIELDS = (
    "process_tree_rss_bytes",
    "pss_bytes",
    "uss_bytes",
)
_SIDE_ORDER = {"bottom": 0, "top": 1}
_POLARIZATION_ORDER = {"p": 0, "s": 1}
_CONTRACT = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


class Task041ComparisonError(ValueError):
    """A Task041 comparison artifact does not satisfy its frozen contract."""

    def __init__(
        self,
        message: str,
        *,
        category: str = "evidence",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.context = dict(context or {})


@dataclass(frozen=True)
class Task041Result:
    method: str
    root: Path
    public_root: Path
    summary: Mapping[str, Any]
    run_manifest: Mapping[str, Any]
    authority: Mapping[str, Any]
    authority_path: Path
    identity: Mapping[str, Any]
    producer_identity: Mapping[str, Any]
    packet: Mapping[str, Any]
    external_keys: tuple[tuple[str, int, int, str], ...]
    external_rows: Mapping[tuple[str, int, int, str], Mapping[str, Any]]
    arrays: Mapping[str, np.ndarray]
    array_descriptors: Mapping[str, Mapping[str, Any]]
    canonical: Mapping[str, Mapping[str, Any]]
    own_gates: Mapping[str, Any]
    resources: Mapping[str, Any]


def _fail(message: str, *, category: str = "evidence") -> None:
    raise Task041ComparisonError(message, category=category)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Task041ComparisonError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, Mapping):
        _fail(f"{label} must be a JSON object: {path}")
    return dict(value)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Task041ComparisonError(f"cannot hash artifact: {path}") from exc


def _digest(value: Any, length: int, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not a lowercase {length}-hex digest")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} is not a finite scalar")
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{label} is not finite")
    return result


def _absolute_writer_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        _fail(f"{label} path is missing")
    path = Path(value)
    if not path.is_absolute():
        _fail(f"{label} path must be absolute as written by Task041: {value}")
    path = path.resolve()
    if not path.is_file():
        _fail(f"{label} artifact is missing: {path}")
    return path


def _repo_writer_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        _fail(f"{label} path is missing")
    path = Path(value)
    path = path if path.is_absolute() else _REPO_ROOT / path
    path = path.resolve()
    if not path.is_file():
        _fail(f"{label} artifact is missing: {path}")
    return path


def _result_roots(path_value: str | Path) -> tuple[Path, Path, Path]:
    path = Path(path_value).resolve()
    if path.is_file():
        if path.name != "consumer_summary.json" or path.parent.name != "consumer":
            _fail("result input must be a public Task041 run or its consumer summary")
        consumer_root = path.parent
        public_root = consumer_root.parent
        return public_root, consumer_root, path
    if not path.is_dir():
        _fail(f"Task041 result directory is missing: {path}")
    consumer_root = path / "consumer"
    summary_path = consumer_root / "consumer_summary.json"
    if not summary_path.is_file():
        _fail(f"Task041 consumer summary is missing: {summary_path}")
    return path, consumer_root, summary_path


def _mode_key(raw: Any, label: str) -> tuple[str, int, int, str]:
    if not isinstance(raw, Mapping):
        _fail(f"{label} must be a mapping")
    side = raw.get("side")
    m = raw.get("m")
    n = raw.get("n")
    polarization = raw.get("polarization")
    if side not in _SIDE_ORDER or polarization not in _POLARIZATION_ORDER:
        _fail(f"{label} has an invalid side or polarization")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (m, n)):
        _fail(f"{label} has a non-integer Fourier index")
    if set(raw) != {"side", "m", "n", "polarization"}:
        _fail(f"{label} has fields outside the Task041 physical key")
    return str(side), int(m), int(n), str(polarization)


def _key_order(key: tuple[str, int, int, str]) -> tuple[int, int, int, int]:
    return (_SIDE_ORDER[key[0]], key[1], key[2], _POLARIZATION_ORDER[key[3]])


def _parse_identity_external(
    raw: Mapping[str, Any], label: str
) -> tuple[int, str]:
    value = raw.get("external_keys")
    if not isinstance(value, Mapping) or set(value) != {"count", "sha256"}:
        _fail(f"{label}.external_keys must contain count and sha256")
    count = value.get("count")
    if type(count) is not int or count <= 0:
        _fail(f"{label}.external_keys.count is invalid")
    return count, _digest(value.get("sha256"), 64, f"{label}.external_keys.sha256")


def _authority_inventory(
    raw: Any, label: str
) -> tuple[tuple[str, int, int, str], ...]:
    try:
        parsed = _task039_parse_inventory(raw, label, expected_count=None)
    except (KeyError, TypeError, ValueError) as exc:
        raise Task041ComparisonError(f"{label} external inventory is invalid") from exc
    raw_keys = parsed["value"].get("keys")
    if not isinstance(raw_keys, list):
        _fail(f"{label}.keys is missing")
    keys = tuple(
        _mode_key(value, f"{label}.keys[{index}]")
        for index, value in enumerate(raw_keys)
    )
    if not keys or len(set(keys)) != len(keys):
        _fail(f"{label} external keys are not unique and non-empty")
    return keys


def _identity_key_digest(keys: Sequence[tuple[str, int, int, str]]) -> str:
    canonical = [
        {
            "side": side,
            "m": m,
            "n": n,
            "polarization": polarization,
        }
        for side, m, n, polarization in sorted(keys, key=_key_order)
    ]
    return canonical_mode_keys_sha256(canonical)


def _normal_identity(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        _fail(f"{label} must be a mapping")
    result = dict(raw)
    if result.get("schema") != _PACKET_IDENTITY_SCHEMA:
        _fail(f"{label}.schema is not the Task041 BAL_H selected-packet schema")
    model_id = result.get("model_id")
    if model_id not in TASK041_BALH_MODEL_IDS or task041_balh_case(str(model_id)) is None:
        _fail(f"{label}.model_id is outside the four Task041 BAL_H profiles")
    case = task041_balh_case(str(model_id))
    for field, length in (
        ("source_sha", 40),
        ("input_sha256", 64),
        ("resolved_sha256", 64),
        ("physical_sha256", 64),
    ):
        result[field] = _digest(result.get(field), length, f"{label}.{field}")
    for field in ("run_id", "scope", "comparison_group", "dtn_order_policy"):
        if not isinstance(result.get(field), str) or not result[field]:
            _fail(f"{label}.{field} is missing")
    wavelength = _finite(result.get("wavelength_nm"), f"{label}.wavelength_nm")
    mode_count = result.get("mode_count")
    requested = result.get("requested_modes_per_direction")
    mpi_size = result.get("mpi_size")
    if any(
        type(value) is not int or value <= 0
        for value in (mode_count, requested, mpi_size)
    ):
        _fail(f"{label} mode_count/requested_modes_per_direction/mpi_size is invalid")
    if mode_count != requested:
        _fail(f"{label} mode counts disagree")
    if mpi_size != 8:
        _fail(f"{label} must be MPI8")
    if not isinstance(result.get("mesh"), Mapping):
        _fail(f"{label}.mesh must be a mapping")
    if not isinstance(result.get("physical_contract"), Mapping):
        _fail(f"{label}.physical_contract is missing")
    if case is None:
        _fail(f"{label}.model_id is not a registered case")
    for field in ("run_id", "scope", "mode_count"):
        expected = case[field]
        if result[field] != expected:
            _fail(f"{label}.{field} does not match its registered case")
    if wavelength != case["wavelength_nm"]:
        _fail(f"{label}.wavelength_nm does not match its registered case")
    _parse_identity_external(result, label)
    return result


def _normal_legacy_identity(raw: Any, label: str) -> dict[str, Any]:
    """Validate the one explicitly approved native Task039 packet identity."""

    from benchmarks.task041_legacy_native_packet import (
        TASK039_V4_H4_EXTERNAL_SHA256,
        TASK039_V4_H4_IDENTITY_SCHEMA,
        TASK039_V4_H4_INPUT_SHA256,
        TASK039_V4_H4_MODE_COUNT,
        TASK039_V4_H4_MODEL_ID,
        TASK039_V4_H4_PHYSICAL_SHA256,
        TASK039_V4_H4_RESOLVED_SHA256,
        TASK039_V4_H4_RUN_ID,
        TASK039_V4_H4_SOURCE_SHA,
    )

    if not isinstance(raw, Mapping):
        _fail(f"{label} must be a mapping", category="identity")
    result = dict(raw)
    if result.get("schema") != TASK039_V4_H4_IDENTITY_SCHEMA:
        _fail(f"{label}.schema is not the approved native Task039 schema", category="identity")
    expected = {
        "scope": "task039_v4_h4_m480",
        "source_sha": TASK039_V4_H4_SOURCE_SHA,
        "input_sha256": TASK039_V4_H4_INPUT_SHA256,
        "resolved_sha256": TASK039_V4_H4_RESOLVED_SHA256,
        "physical_sha256": TASK039_V4_H4_PHYSICAL_SHA256,
        "model_id": TASK039_V4_H4_MODEL_ID,
        "run_id": TASK039_V4_H4_RUN_ID,
        "mode_count": TASK039_V4_H4_MODE_COUNT,
        "mpi_size": 8,
        "external_keys": {
            "count": 600,
            "sha256": TASK039_V4_H4_EXTERNAL_SHA256,
        },
    }
    if any(result.get(field) != value for field, value in expected.items()):
        _fail(f"{label} is not the approved native 5 nm identity", category="identity")
    _parse_identity_external(result, label)
    return result


def _validate_legacy_consumer_binding(
    summary: Mapping[str, Any],
    identity: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
    public_root: Path,
) -> None:
    from benchmarks.task041_balh_workflow import _physical_contract
    from benchmarks.task041_legacy_native_packet import (
        TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
        _physical_binding,
        _validate_descriptor,
    )

    if summary.get("packet_origin") != TASK041_LEGACY_NATIVE_PACKET_ORIGIN:
        _fail("legacy packet origin is missing from the consumer summary", category="identity")
    binding = summary.get("consumer_binding")
    if not isinstance(binding, Mapping):
        _fail("legacy consumer binding evidence is missing", category="identity")
    if binding.get("origin") != TASK041_LEGACY_NATIVE_PACKET_ORIGIN:
        _fail("legacy consumer binding origin is invalid", category="identity")
    if binding.get("producer_identity") != dict(producer_identity):
        _fail("legacy consumer binding producer identity differs", category="identity")
    if binding.get("consumer_identity") != dict(identity):
        _fail("legacy consumer binding consumer identity differs", category="identity")
    descriptor = binding.get("descriptor")
    if not isinstance(descriptor, Mapping):
        _fail("legacy descriptor evidence is missing", category="identity")
    descriptor_path = _absolute_writer_path(descriptor.get("path"), "legacy descriptor")
    descriptor_sha = _digest(descriptor.get("sha256"), 64, "legacy descriptor.sha256")
    if _sha256(descriptor_path) != descriptor_sha:
        _fail("legacy descriptor SHA mismatch", category="identity")
    _descriptor, paths = _validate_descriptor(descriptor_path, full_artifacts=False)
    disk_identity = _read_json(paths["identity"], "legacy packet identity")
    if disk_identity != dict(producer_identity):
        _fail("legacy descriptor packet identity differs", category="identity")
    producer_resolved_sha = _digest(
        producer_identity.get("resolved_sha256"), 64, "producer_identity.resolved_sha256"
    )
    if _sha256(paths["resolved_config"]) != producer_resolved_sha:
        _fail("legacy descriptor resolved config SHA mismatch", category="identity")
    producer_resolved = _read_json(
        paths["resolved_config"], "legacy producer resolved config"
    )
    producer_provenance = producer_resolved.get("provenance")
    if not isinstance(producer_provenance, Mapping):
        _fail("legacy producer resolved provenance is missing", category="identity")
    if any(
        producer_provenance.get(field) != producer_identity.get(identity_field)
        for field, identity_field in (
            ("input_sha256", "input_sha256"),
            ("physical_model_sha256", "physical_sha256"),
        )
    ):
        _fail("legacy producer resolved provenance differs from identity", category="identity")
    public_resolved_path = public_root / "resolved_config.json"
    if not public_resolved_path.is_file():
        _fail("Task041 public resolved_config.json is missing", category="identity")
    if _sha256(public_resolved_path) != _digest(
        identity.get("resolved_sha256"), 64, "consumer_identity.resolved_sha256"
    ):
        _fail("Task041 public resolved config SHA differs from consumer identity", category="identity")
    public_resolved = _read_json(
        public_resolved_path, "Task041 public resolved config"
    )
    public_provenance = public_resolved.get("provenance")
    if not isinstance(public_provenance, Mapping):
        _fail("Task041 public resolved provenance is missing", category="identity")
    if any(
        public_provenance.get(field) != identity.get(identity_field)
        for field, identity_field in (
            ("input_sha256", "input_sha256"),
            ("physical_model_sha256", "physical_sha256"),
        )
    ):
        _fail("Task041 public resolved provenance differs from identity", category="identity")
    public_contract = _physical_contract(public_resolved)
    if identity.get("physical_contract") != public_contract:
        _fail(
            "consumer identity physical contract differs from public resolved config",
            category="identity",
        )
    physical = binding.get("physical_equivalence")
    recomputed_physical = _physical_binding(producer_resolved, public_resolved)
    if physical != recomputed_physical:
        _fail(
            "legacy physical equivalence differs from raw resolved contracts",
            category="identity",
        )
    if recomputed_physical["pass"] is not True:
        _fail("legacy raw physical contracts are not equivalent", category="identity")
    expected_external = {
        "producer": producer_identity.get("external_keys"),
        "consumer": identity.get("external_keys"),
        "pass": producer_identity.get("external_keys")
        == identity.get("external_keys"),
    }
    if binding.get("external_keys") != expected_external:
        _fail("legacy external identity binding differs", category="identity")
    if binding.get("pass") is not recomputed_physical["pass"]:
        _fail("legacy consumer binding status differs from raw contracts", category="identity")


def _canonical_identity_bytes(raw: Mapping[str, Any]) -> bytes:
    return _selected_mode_json_bytes(raw)


def _packet_binding(
    summary: Mapping[str, Any],
    producer_identity: Mapping[str, Any],
    consumer_root: Path,
    public_root: Path,
) -> dict[str, Any]:
    packet = summary.get("packet")
    if not isinstance(packet, Mapping):
        _fail("consumer packet binding is missing")
    manifest_path = _absolute_writer_path(
        packet.get("manifest"), "selected packet manifest"
    )
    manifest_sha = _digest(packet.get("manifest_sha256"), 64, "packet.manifest_sha256")
    if _sha256(manifest_path) != manifest_sha:
        _fail("selected packet manifest SHA mismatch")
    identity_path = _absolute_writer_path(
        packet.get("identity"), "selected packet identity"
    )
    disk_identity = _read_json(identity_path, "selected packet identity")
    if dict(disk_identity) != dict(producer_identity):
        _fail("consumer producer_identity differs from selected packet identity")
    packet_manifest = _read_json(manifest_path, "selected packet manifest")
    if packet_manifest.get("identity") != disk_identity:
        _fail("selected packet manifest identity differs from identity artifact")
    identity_sha = hashlib.sha256(_canonical_identity_bytes(disk_identity)).hexdigest()
    if packet_manifest.get("identity_sha256") != identity_sha:
        _fail("selected packet identity SHA mismatch")
    packet_identity_sha = packet.get("identity_sha256")
    if packet_identity_sha is not None and packet_identity_sha != identity_sha:
        _fail("consumer packet identity_sha256 mismatch")
    return {
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha,
        "identity_path": identity_path,
        "identity_sha256": identity_sha,
        "manifest": packet_manifest,
        "producer_source_sha": producer_identity["source_sha"],
    }


def _validate_manifest_identity(
    manifest: Mapping[str, Any], identity: Mapping[str, Any], label: str
) -> None:
    pairs = (
        ("source_sha", "source_sha"),
        ("input_sha256", "input_sha256"),
        ("resolved_config_sha256", "resolved_sha256"),
        ("physical_model_sha256", "physical_sha256"),
        ("model_id", "model_id"),
        ("run_id", "run_id"),
        ("mpi_size", "mpi_size"),
        ("requested_modes", "mode_count"),
    )
    for manifest_name, identity_name in pairs:
        if manifest_name not in manifest:
            _fail(f"{label}.{manifest_name} is missing")
        if manifest[manifest_name] != identity[identity_name]:
            _fail(f"{label}.{manifest_name} does not match consumer identity")


def _validate_public_input_artifacts(
    public_root: Path, manifest: Mapping[str, Any], identity: Mapping[str, Any]
) -> None:
    input_path = public_root / "input_original.dat"
    resolved_path = public_root / "resolved_config.json"
    for path, manifest_field, identity_field, label in (
        (input_path, "input_sha256", "input_sha256", "input_original.dat"),
        (
            resolved_path,
            "resolved_config_sha256",
            "resolved_sha256",
            "resolved_config.json",
        ),
    ):
        if not path.is_file():
            _fail(f"Task041 public {label} is missing")
        actual = _sha256(path)
        expected_manifest = _digest(
            manifest.get(manifest_field), 64, f"run_manifest.{manifest_field}"
        )
        expected_identity = _digest(
            identity.get(identity_field), 64, f"consumer_identity.{identity_field}"
        )
        if actual != expected_manifest or actual != expected_identity:
            _fail(f"Task041 public {label} bytes do not match its identities")


def _authority_and_manifest(
    summary: Mapping[str, Any], consumer_root: Path, public_root: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    authority_value = summary.get("authority_path")
    authority_path = _absolute_writer_path(authority_value, "Task041 authority")
    authority = _read_json(authority_path, "Task041 authority")
    if authority.get("schema") != _AUTHORITY_SCHEMA:
        _fail("Task041 authority schema is unsupported")
    manifest_path = public_root / "run_manifest.json"
    if not manifest_path.is_file():
        _fail("Task041 public run_manifest.json is missing")
    return authority_path, authority, _read_json(manifest_path, "Task041 run manifest")


def _parse_external_orders(
    authority: Mapping[str, Any],
    inventory: tuple[tuple[str, int, int, str], ...],
) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    rows = authority.get("external_orders")
    try:
        parsed = _task039_parse_orders(
            rows, "Task041 external_orders", expected_count=len(inventory)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise Task041ComparisonError("Task041 external_orders is invalid") from exc
    if not all(
        key[0] in _SIDE_ORDER
        and key[3] in _POLARIZATION_ORDER
        and type(key[1]) is int
        and type(key[2]) is int
        for key in parsed
    ):
        _fail("Task041 external_orders contains an invalid physical key")
    if set(parsed) != set(inventory):
        _fail("Task041 external order keys differ from external inventory")
    return parsed


def _load_grid_payload(
    authority: Mapping[str, Any],
    authority_path: Path,
    public_root: Path,
    consumer_root: Path,
    inventory: tuple[tuple[str, int, int, str], ...],
    identity: Mapping[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, Mapping[str, Any]]]:
    descriptor = authority.get("grid_payload")
    if not isinstance(descriptor, Mapping):
        _fail("Task041 grid_payload is missing; field output is diagnostic-only")
    if descriptor.get("schema_version") != _GRID_SCHEMA:
        _fail("Task041 grid_payload schema is unsupported")
    path = _repo_writer_path(descriptor.get("path"), "Task041 grid payload")
    expected_sha = _digest(descriptor.get("sha256"), 64, "grid_payload.sha256")
    if _sha256(path) != expected_sha:
        _fail("Task041 grid payload SHA mismatch")
    if type(descriptor.get("bytes")) is not int or descriptor["bytes"] != path.stat().st_size:
        _fail("Task041 grid payload byte count mismatch")
    if descriptor.get("keys") != list(_PAYLOAD_KEYS):
        _fail("Task041 grid payload key descriptor is incomplete")
    raw_descriptors = descriptor.get("arrays")
    if not isinstance(raw_descriptors, Mapping) or set(raw_descriptors) != set(_PAYLOAD_KEYS):
        _fail("Task041 grid payload array descriptors are incomplete")
    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != set(_PAYLOAD_KEYS):
                _fail("Task041 grid payload archive keys are not exact")
            arrays = {name: np.asarray(archive[name]).copy() for name in _PAYLOAD_KEYS}
    except (OSError, ValueError) as exc:
        raise Task041ComparisonError("cannot read Task041 grid payload") from exc
    descriptors: dict[str, Mapping[str, Any]] = {}
    expected_dtypes = {
        name: "complex128" if name in _COMPLEX_PAYLOAD_KEYS else "float64"
        for name in _PAYLOAD_KEYS
    }
    for name, array in arrays.items():
        item = raw_descriptors.get(name)
        if not isinstance(item, Mapping):
            _fail(f"Task041 grid descriptor is missing {name}")
        descriptors[name] = dict(item)
        if list(array.shape) != item.get("shape"):
            _fail(f"Task041 grid descriptor shape mismatch for {name}")
        if str(array.dtype) != expected_dtypes[name] or str(array.dtype) != item.get("dtype"):
            _fail(f"Task041 grid descriptor dtype mismatch for {name}")
        if type(item.get("bytes")) is not int or item["bytes"] != int(array.nbytes):
            _fail(f"Task041 grid descriptor byte mismatch for {name}")
        observed = hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
        if item.get("sha256") != observed:
            _fail(f"Task041 grid descriptor SHA mismatch for {name}")
        if item.get("finite") is False or not np.isfinite(array).all():
            _fail(f"Task041 grid array {name} is not finite")
    if arrays["x_nm"].shape != (40,) or arrays["y_nm"].shape != (20,):
        _fail("Task041 x/y grid shapes are not (40,)/(20,)")
    if arrays["E_V_per_m"].shape != (5, 20, 40, 3) or arrays["H_A_per_m"].shape != (
        5,
        20,
        40,
        3,
    ):
        _fail("Task041 E/H grid shape is not (5,20,40,3)")
    if arrays["z_nm"].shape != (5,) or not np.array_equal(
        arrays["z_nm"], np.asarray(_CONTRACT["payload"]["z_nm"], dtype=np.float64)
    ):
        _fail("Task041 z planes are not the frozen selected planes")
    for name in ("x_nm", "y_nm", "modal_amplitudes", "bottom_q", "top_q"):
        if arrays[name].ndim != 1:
            _fail(f"Task041 {name} must be one-dimensional")
    expected_q = {
        "bottom_q": sum(key[0] == "bottom" for key in inventory),
        "top_q": sum(key[0] == "top" for key in inventory),
    }
    for name, size in expected_q.items():
        if arrays[name].size != size:
            _fail(f"Task041 {name} size does not match its external side")
    expected_modal_count = 2 * int(identity["mode_count"])
    if arrays["modal_amplitudes"].size != expected_modal_count:
        _fail("Task041 modal_amplitudes size differs from 2*mode_count")
    return arrays, descriptors


def _canonical_manifest_descriptor(
    value: Mapping[str, Any],
    label: str,
    manifest_role: str,
    mpi_size: int,
) -> dict[str, Any]:
    manifest_path_value = value.get("manifest")
    expected_sha = value.get("manifest_sha256")
    if value.get("schema_version") != MANIFEST_SCHEMA:
        _fail(f"{label} canonical descriptor schema is invalid")
    path = _repo_writer_path(manifest_path_value, f"{label} manifest")
    expected_sha = _digest(expected_sha, 64, f"{label}.manifest_sha256")
    try:
        manifest = read_canonical_manifest(path, expected_sha)
    except (OSError, KeyError, ValueError) as exc:
        raise Task041ComparisonError(f"cannot read {label} canonical manifest") from exc
    if manifest.get("role") != manifest_role or manifest.get("mpi_size") != mpi_size:
        _fail(f"{label} canonical manifest identity is invalid")
    if manifest.get("dtype") != "complex128":
        _fail(f"{label} canonical manifest dtype is invalid")
    if manifest.get("key_digest_algorithm") != KEY_DIGEST_ALGORITHM:
        _fail(f"{label} canonical key digest algorithm is invalid")
    shards = manifest.get("per_rank_shards")
    if not isinstance(shards, list) or len(shards) != mpi_size:
        _fail(f"{label} canonical owner shard count is invalid")
    shard_paths: list[Path] = []
    shard_hashes: list[str] = []
    shard_counts: list[int] = []
    for index, item in enumerate(shards):
        if not isinstance(item, Mapping) or item.get("rank") != index:
            _fail(f"{label} canonical owner ranks are not rank-major")
        if item.get("schema_version") != SHARD_SCHEMA:
            _fail(f"{label} canonical shard schema is invalid")
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            _fail(f"{label} canonical shard filename is invalid")
        packet_count = item.get("packet_count")
        if type(packet_count) is not int or packet_count < 0:
            _fail(f"{label} canonical shard packet count is invalid")
        shard_path = path.parent / filename
        if not shard_path.is_file():
            _fail(f"{label} canonical shard is missing: {shard_path}")
        shard_paths.append(shard_path)
        shard_hashes.append(
            _digest(item.get("file_sha256"), 64, f"{label}.shards[{index}].file_sha256")
        )
        shard_counts.append(packet_count)
    try:
        packets = read_canonical_packet_shards(shard_paths, shard_hashes)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise Task041ComparisonError(f"cannot read {label} canonical shards") from exc
    global_count = manifest.get("global_summed_packet_count")
    if type(global_count) is not int or global_count <= 0:
        _fail(f"{label} canonical packet count is empty or invalid")
    if sum(shard_counts) != global_count or len(packets) != global_count:
        _fail(f"{label} canonical packet count disagrees with its manifest")
    unique_count = len({key for key, _value in packets})
    if unique_count != global_count:
        _fail(f"{label} canonical owner shards contain duplicate keys")
    nonempty_count = sum(count > 0 for count in shard_counts)
    if nonempty_count == 0:
        _fail(f"{label} canonical owner shards are all empty")
    return {
        "path": path,
        "sha256": expected_sha,
        "role": manifest["role"],
        "mpi_size": mpi_size,
        "global_summed_packet_count": global_count,
        "shards": [dict(item) for item in shards],
        "packets": packets,
        "nonempty_shard_count": nonempty_count,
        "unique_packet_count": unique_count,
    }


def _load_canonical(
    authority: Mapping[str, Any],
    authority_path: Path,
    public_root: Path,
    consumer_root: Path,
    mpi_size: int,
) -> dict[str, Mapping[str, Any]]:
    raw = authority.get("canonical")
    if not isinstance(raw, Mapping) or set(raw) != {"bottom", "top"}:
        _fail("Task041 canonical bottom/top exports are missing")
    result: dict[str, Mapping[str, Any]] = {}
    for side in ("bottom", "top"):
        side_value = raw.get(side)
        if not isinstance(side_value, Mapping):
            _fail(f"Task041 canonical {side} is invalid")
        roles = side_value.get("roles")
        if not isinstance(roles, Mapping) or set(roles) != {"active_trace", "full_fe"}:
            _fail(f"Task041 canonical {side} roles are incomplete")
        for role in ("active_trace", "full_fe"):
            label = f"{side}.{role}"
            result[label] = _canonical_manifest_descriptor(
                roles[role],
                label,
                f"{side}_{role}",
                mpi_size,
            )
    return result


def _path_value(raw: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = raw
    for name in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(name)
    return value


def _optional_finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _finite_gate_status(value: Any) -> str:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not_measured"
    return "measured" if math.isfinite(float(value)) else "numeric_gate_fail"


def _bounded_gate_status(
    value: Any, limit: float, *, nonnegative: bool = False
) -> str:
    status = _finite_gate_status(value)
    if status != "measured":
        return status
    number = float(value)
    return (
        "numeric_gate_fail"
        if (nonnegative and number < 0.0) or number > limit
        else "measured"
    )


def _own_gates(summary: Mapping[str, Any], authority: Mapping[str, Any]) -> dict[str, Any]:
    thresholds = _CONTRACT["thresholds"]
    solve = _path_value(summary, ("formal", "solve"))
    postsolve = solve.get("postsolve") if isinstance(solve, Mapping) else None
    residual_names = tuple(_CONTRACT["own_gate"]["residual_fields"])
    raw_residuals = {
        name: postsolve.get(name) if isinstance(postsolve, Mapping) else None
        for name in residual_names
    }
    residuals = {
        name: _optional_finite(value) for name, value in raw_residuals.items()
    }
    residual_status = {
        name: _bounded_gate_status(
            raw_residuals[name], thresholds["own_residual"], nonnegative=True
        )
        for name in residual_names
    }
    residual_pass = all(
        status == "measured" for status in residual_status.values()
    )
    reason_value = solve.get("converged_reason") if isinstance(solve, Mapping) else None
    reason = reason_value if type(reason_value) is int else None
    reason_pass = reason is not None and reason > 0
    reason_status = (
        "measured"
        if type(reason_value) is int and reason_value > 0
        else "numeric_gate_fail"
        if type(reason_value) is int
        else "not_measured"
    )
    reports = _path_value(summary, ("formal", "recovery", "reports"))
    raw_external_q = {
        side: _path_value(
            reports, (side, "external_q", "auxiliary_relative_residual")
        )
        for side in ("bottom", "top")
    }
    external_q = {
        side: _optional_finite(value) for side, value in raw_external_q.items()
    }
    external_q_status = {
        side: _bounded_gate_status(
            raw_external_q[side], thresholds["own_external_q"], nonnegative=True
        )
        for side in ("bottom", "top")
    }
    external_q_pass = all(
        status == "measured" for status in external_q_status.values()
    )
    observables = authority.get("observables")
    observables = observables if isinstance(observables, Mapping) else {}
    raw_rta = {
        name: observables.get(name)
        for name in _CONTRACT["own_gate"]["rta_fields"]
    }
    rta = {
        name: _optional_finite(value) for name, value in raw_rta.items()
    }
    rta_status = {name: _finite_gate_status(value) for name, value in raw_rta.items()}
    rta_finite = all(status == "measured" for status in rta_status.values())
    balance_delta = (
        abs(rta["A_balance"] - rta["A_volume"]) if rta_finite else None
    )
    closure = (
        rta["R_total"] + rta["T_total"] + rta["A_volume"] - 1.0
        if rta_finite
        else None
    )
    balance_from_rt = (
        rta["A_balance"] - (1.0 - rta["R_total"] - rta["T_total"])
        if rta_finite
        else None
    )
    balance_status = (
        _bounded_gate_status(balance_delta, thresholds["own_balance_volume"])
        if balance_delta is not None
        else "not_measured"
    )
    # Keep the signed conservation residual for reporting; only its magnitude
    # is the frozen energy-closure gate.
    closure_status = (
        _bounded_gate_status(abs(closure), thresholds["own_energy_closure"])
        if closure is not None
        else "not_measured"
    )
    balance_pass = (
        balance_delta is not None
        and balance_status == "measured"
    )
    closure_pass = (
        closure is not None
        and closure_status == "measured"
    )
    raw_projection = authority.get("interface_projection")
    projection = _optional_finite(raw_projection)
    projection_status = _bounded_gate_status(
        raw_projection, thresholds["own_projection"], nonnegative=True
    )
    projection_pass = (
        projection_status == "measured" and projection is not None
    )
    traction_raw = authority.get("traction")
    negative_authority = authority.get("status") == "measured_candidate_physics_negative"
    traction_field = "relative_dual" if negative_authority else "relative_residual"
    raw_traction = {
        side: (
            traction_raw.get(side, {}).get(traction_field)
            if isinstance(traction_raw, Mapping)
            and isinstance(traction_raw.get(side), Mapping)
            else None
        )
        for side in ("bottom", "top")
    }
    traction = {
        side: _optional_finite(value) for side, value in raw_traction.items()
    }
    traction_status = {
        side: _bounded_gate_status(
            raw_traction[side], thresholds["own_traction"], nonnegative=True
        )
        for side in ("bottom", "top")
    }
    traction_pass = all(
        status == "measured" for status in traction_status.values()
    )
    gate_statuses = {
        "residual": residual_status,
        "outer_reason": reason_status,
        "external_q": external_q_status,
        "observables": rta_status,
        "balance_volume": balance_status,
        "energy_closure": closure_status,
        "projection": projection_status,
        "traction": traction_status,
    }
    statuses = []
    for value in gate_statuses.values():
        statuses.extend(value.values() if isinstance(value, Mapping) else [value])
    if "numeric_gate_fail" in statuses:
        failure_classification = "numeric_gate_fail"
    elif "not_measured" in statuses:
        failure_classification = "evidence_incomplete"
    else:
        failure_classification = None
    result = {
        "limits": {
            "residual": thresholds["own_residual"],
            "external_q": thresholds["own_external_q"],
            "projection": thresholds["own_projection"],
            "traction": thresholds["own_traction"],
            "balance_volume": thresholds["own_balance_volume"],
            "energy_closure": thresholds["own_energy_closure"],
        },
        "raw_residuals": raw_residuals,
        "residuals": residuals,
        "residual_status": residual_status,
        "residual_pass": residual_pass,
        "outer_reason": reason,
        "raw_outer_reason": reason_value,
        "outer_reason_status": reason_status,
        "outer_reason_pass": reason_pass,
        "raw_external_q": raw_external_q,
        "external_q": external_q,
        "external_q_status": external_q_status,
        "external_q_pass": external_q_pass,
        "raw_projection": raw_projection,
        "projection": projection,
        "projection_status": projection_status,
        "projection_pass": projection_pass,
        "traction_field": traction_field,
        "raw_traction": raw_traction,
        "traction": traction,
        "traction_status": traction_status,
        "traction_pass": traction_pass,
        "raw_observables": raw_rta,
        "observables": rta,
        "observables_status": rta_status,
        "balance_delta": balance_delta,
        "balance_volume_status": balance_status,
        "balance_volume_pass": balance_pass,
        "balance_from_rt": balance_from_rt,
        "closure": closure,
        "energy_closure_status": closure_status,
        "energy_closure_pass": closure_pass,
        "gate_statuses": gate_statuses,
        "failure_classification": failure_classification,
    }
    result["pass"] = bool(
        residual_pass
        and reason_pass
        and external_q_pass
        and projection_pass
        and traction_pass
        and rta_finite
        and balance_pass
        and closure_pass
    )
    result["official_field_status"] = (
        "qualified" if result["pass"] else "diagnostic_only"
    )
    return result


def _load_samples(path: Path, phase: str) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise Task041ComparisonError(
                        f"invalid resource sample line {line_number}: {path}"
                    ) from exc
                if isinstance(value, Mapping) and value.get("phase") == phase:
                    samples.append(dict(value))
    except OSError as exc:
        raise Task041ComparisonError(f"cannot read raw resource samples: {path}") from exc
    return samples


def _resource_phase(
    phase_name: str,
    phase: Any,
    samples: list[dict[str, Any]],
    raw_sha: str | None,
    expected_limits: Mapping[str, Any],
    *,
    time_stop_overridden: bool = False,
) -> dict[str, Any]:
    if not isinstance(phase, Mapping):
        return {"status": "not_measured", "pass": False, "reason": "phase_missing"}
    if phase.get("reused") is True:
        peak_names = {
            "memory_authority_bytes": "peak_memory_authority_bytes",
            "process_tree_rss_bytes": "peak_process_tree_rss_bytes",
            "pss_bytes": "peak_pss_bytes",
            "uss_bytes": "peak_uss_bytes",
            "process_tree_swap_bytes": "peak_process_tree_swap_bytes",
            "dedicated_cgroup_swap_bytes": "peak_dedicated_cgroup_swap_bytes",
            "swap_bytes": "peak_swap_bytes",
        }
        return {
            "status": "inherited",
            "pass": False,
            "reused": True,
            "resource_source": phase.get("resource_source", "inherited"),
            "supervisor_summary_sha256": phase.get("supervisor_summary_sha256"),
            "peak": {
                name: phase.get(source) for name, source in peak_names.items()
            },
            "phase_wall_seconds": _optional_finite(
                phase.get("phase_wall_seconds")
            ),
            "worker_tree": phase.get("worker_tree"),
            "reason": "producer was not run in this public invocation",
        }
    if not samples:
        return {
            "status": "not_measured",
            "pass": False,
            "reused": False,
            "reason": "raw_phase_samples_missing",
            "raw_samples_sha256": raw_sha,
        }

    required_fields = (
        "memory_authority_bytes",
        "process_tree_rss_bytes",
        "swap_bytes",
        "job_no_swap",
        "global_swap_used_bytes",
        "global_swap_used_bytes_delta",
        "global_pswpin_pages",
        "global_pswpin_pages_delta",
        "global_pswpout_pages",
        "global_pswpout_pages_delta",
    )
    required_samples_pass = all(
        type(row.get(field)) is int
        and row[field] >= 0
        for row in samples
        for field in required_fields
        if field != "job_no_swap"
    ) and all(row.get("job_no_swap") is True for row in samples)
    peaks = {
        field: max(
            (
                int(row[field])
                for row in samples
                if type(row.get(field)) is int and row[field] >= 0
            ),
            default=None,
        )
        for field in _RESOURCE_PEAK_FIELDS
    }
    post_role = _CONTRACT["resource"]["post_phase_sample_role"]
    post = [row for row in samples if row.get("sample_role") == post_role]
    phase_end = phase.get("phase_end_sample")
    phase_end_pass = (
        isinstance(phase_end, Mapping)
        and phase_end.get("sample_role") == post_role
        and type(phase_end.get("process_tree_rss_bytes")) is int
        and phase_end["process_tree_rss_bytes"] >= 0
    )
    timestamps = [
        float(row["sample_elapsed_seconds"])
        for row in samples
        if _optional_finite(row.get("sample_elapsed_seconds")) is not None
    ]
    gaps = [
        later - earlier
        for earlier, later in pairwise(timestamps)
        if later >= earlier
    ]
    sample_scope = phase.get("sample_root_scope")
    phase_limits = phase.get("limits")
    phase_limits = phase_limits if isinstance(phase_limits, Mapping) else {}
    expected_record_limits = {
        "warning_memory_bytes": expected_limits["warning_memory_bytes"],
        "hard_memory_bytes": expected_limits["hard_memory_bytes"],
        "swap_limit_bytes": expected_limits["swap_limit_bytes"],
        "timeout_seconds": expected_limits["timeout_seconds"],
        "min_memavailable_bytes": expected_limits["min_memavailable_bytes"],
        "min_cgroup_ancestor_headroom_bytes": expected_limits[
            "min_memavailable_bytes"
        ],
        "cumulative_compute_limit_seconds": _CONTRACT["resource"][
            "batch_wall_limit_seconds"
        ],
    }
    limits_match = all(
        phase_limits.get(name) == value
        for name, value in expected_record_limits.items()
    )
    min_memavailable = [
        int(row["host_memavailable_bytes"])
        for row in samples
        if type(row.get("host_memavailable_bytes")) is int
    ]
    reserve = int(expected_limits["min_memavailable_bytes"])
    reserve_pass = bool(
        len(min_memavailable) == len(samples)
        and min(min_memavailable, default=-1) >= reserve
    )

    cgroup_states = set()
    finite_ancestor_rows: list[Mapping[str, Any]] = []
    current_finite_missing = False
    for row in samples:
        state = row.get("cgroup_ancestor_hard_limit_state")
        if isinstance(state, str):
            cgroup_states.add(state)
        elif state is not None:
            cgroup_states.add("invalid")
        current_state = row.get("cgroup_memory_limit_state")
        if isinstance(current_state, str):
            root_without_memory_files = (
                current_state == "unreadable"
                and row.get("cgroup_ancestor_hard_limit_state")
                == "not_applicable_root"
                and row.get("cgroup_memory_current_bytes") is None
                and row.get("cgroup_memory_headroom_bytes") is None
            )
            if not root_without_memory_files:
                cgroup_states.add(current_state)
        elif current_state is not None:
            cgroup_states.add("invalid")
        if current_state == "finite" and (
            type(row.get("cgroup_memory_current_bytes")) is not int
            or type(row.get("cgroup_memory_headroom_bytes")) is not int
        ):
            current_finite_missing = True
        ancestor_rows = row.get("cgroup_ancestor_memory")
        if isinstance(ancestor_rows, list):
            finite_ancestor_rows.extend(
                item
                for item in ancestor_rows
                if isinstance(item, Mapping)
                and item.get("memory_limit_state") == "finite"
            )
    finite_missing = current_finite_missing or any(
        type(row.get("memory_current_bytes")) is not int
        or type(row.get("memory_headroom_bytes")) is not int
        for row in finite_ancestor_rows
    )
    ancestor_headroom = [
        int(row["cgroup_ancestor_memory_headroom_bytes"])
        for row in samples
        if type(row.get("cgroup_ancestor_memory_headroom_bytes")) is int
    ]
    finite_visible = "finite" in cgroup_states or bool(finite_ancestor_rows)
    unlimited_or_root = cgroup_states and cgroup_states <= {
        "max_or_unlimited",
        "not_applicable_root",
    }
    if finite_visible:
        cgroup_pass = bool(
            not finite_missing
            and len(ancestor_headroom) == len(samples)
            and min(ancestor_headroom, default=-1) >= reserve
        )
    else:
        cgroup_pass = bool(unlimited_or_root and not finite_missing)
    cgroup_state_pass = bool(
        cgroup_states
        and not cgroup_states.intersection(
            {"unreadable", "partially_unreadable", "invalid"}
        )
    )
    cgroup_pass = cgroup_pass and cgroup_state_pass

    global_deltas = [
        int(row["global_swap_used_bytes_delta"])
        for row in samples
        if type(row.get("global_swap_used_bytes_delta")) is int
    ]
    global_pswpin_deltas = [
        int(row["global_pswpin_pages_delta"])
        for row in samples
        if type(row.get("global_pswpin_pages_delta")) is int
    ]
    global_pswpout_deltas = [
        int(row["global_pswpout_pages_delta"])
        for row in samples
        if type(row.get("global_pswpout_pages_delta")) is int
    ]
    global_swap_pass = bool(
        len(global_deltas) == len(samples)
        and min(global_deltas, default=-1) >= 0
        and max(global_deltas, default=1) == 0
        and len(global_pswpin_deltas) == len(samples)
        and min(global_pswpin_deltas, default=-1) >= 0
        and max(global_pswpin_deltas, default=1) == 0
        and len(global_pswpout_deltas) == len(samples)
        and min(global_pswpout_deltas, default=-1) >= 0
        and max(global_pswpout_deltas, default=1) == 0
        and all(row.get("global_swap_readable") is True for row in samples)
    )
    hard_cap_pass = bool(
        peaks["memory_authority_bytes"] is not None
        and peaks["memory_authority_bytes"]
        < int(expected_limits["hard_memory_bytes"])
    )
    swap_pass = bool(
        peaks["swap_bytes"] is not None
        and peaks["swap_bytes"] <= int(expected_limits["swap_limit_bytes"])
    )
    wall = _optional_finite(phase.get("phase_wall_seconds"))
    wall_pass = bool(
        wall is not None
        and (
            time_stop_overridden
            or wall < float(expected_limits["timeout_seconds"])
        )
    )
    parent_rss = (
        int(phase_end["process_tree_rss_bytes"])
        if phase_end_pass
        else None
    )
    pass_value = bool(
        phase.get("returncode") == 0
        and phase.get("termination_reason") is None
        and phase.get("process_group_gone") is True
        and sample_scope == _CONTRACT["resource"]["sample_scope"]
        and required_samples_pass
        and len(post) > 0
        and phase_end_pass
        and limits_match
        and hard_cap_pass
        and reserve_pass
        and cgroup_pass
        and swap_pass
        and global_swap_pass
        and wall_pass
    )
    return {
        "status": "measured",
        "pass": pass_value,
        "reused": False,
        "raw_samples_sha256": raw_sha,
        "sample_count": len(samples),
        "post_phase_sample_count": len(post),
        "sample_root_scope": sample_scope,
        "parent_rss_bytes": parent_rss,
        "peak": peaks,
        "pss_uss": {
            "pss_bytes": peaks["pss_bytes"],
            "uss_bytes": peaks["uss_bytes"],
            "missing_allowed": True,
        },
        "limits": dict(expected_record_limits),
        "limits_match_frozen_contract": limits_match,
        "swap_limit_bytes": int(expected_limits["swap_limit_bytes"]),
        "reserve_bytes": reserve,
        "ancestor_reserve_bytes": reserve,
        "min_memavailable_bytes": min(min_memavailable)
        if min_memavailable
        else None,
        "min_ancestor_headroom_bytes": min(ancestor_headroom)
        if ancestor_headroom
        else None,
        "hard_cap_pass": hard_cap_pass,
        "reserve_pass": reserve_pass,
        "cgroup_states": sorted(cgroup_states),
        "cgroup_pass": cgroup_pass,
        "swap_pass": swap_pass,
        "global_swap": {
            "baseline_used_bytes": samples[0].get("global_swap_used_bytes"),
            "new_used_bytes": max(global_deltas, default=None),
            "baseline_pswpin_pages": samples[0].get("global_pswpin_pages"),
            "baseline_pswpout_pages": samples[0].get("global_pswpout_pages"),
            "pswpin_delta_pages": max(global_pswpin_deltas, default=None),
            "pswpout_delta_pages": max(global_pswpout_deltas, default=None),
            "pass": global_swap_pass,
            "semantics": (
                "raw global used, pswpin, and pswpout deltas; "
                "pre-existing baselines are separate"
            ),
        },
        "phase_wall_seconds": wall,
        "phase_wall_pass": wall_pass,
        "time_stop_overridden": time_stop_overridden,
        "sample_timestamp_gap_seconds": {
            "count": len(gaps),
            "min": min(gaps) if gaps else None,
            "max": max(gaps) if gaps else None,
            "mean": sum(gaps) / len(gaps) if gaps else None,
        },
        "configured_poll_interval_seconds": (
            phase.get("sampling", {}).get("configured_poll_interval_seconds")
            if isinstance(phase.get("sampling"), Mapping)
            else None
        ),
    }


def _resources(
    public_root: Path, method: str, model_id: str
) -> dict[str, Any]:
    supervisor_path = public_root / "supervisor_summary.json"
    if not supervisor_path.is_file():
        return {
            "status": "evidence_incomplete",
            "pass": False,
            "reason": "public supervisor summary is missing",
        }
    supervisor = _read_json(supervisor_path, "public supervisor summary")
    time_stop_override: dict[str, Any] = {
        "status": "not_present",
        "enabled": False,
        "applies": False,
    }
    if method == "candidate" and model_id == (
        "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8"
    ):
        record = supervisor.get("time_stop_override")
        manifest_path = public_root / "run_manifest.json"
        manifest = (
            _read_json(manifest_path, "Task041 run manifest")
            if manifest_path.is_file()
            else {}
        )
        consumer_summary_path = public_root / "consumer" / "consumer_summary.json"
        consumer_summary = (
            _read_json(consumer_summary_path, "Task041 consumer summary")
            if consumer_summary_path.is_file()
            else {}
        )
        worker_record = consumer_summary.get("time_stop_override")
        identity = supervisor.get("identity")
        valid = (
            isinstance(record, Mapping)
            and isinstance(manifest.get("time_stop_override"), Mapping)
            and dict(record) == dict(manifest["time_stop_override"])
            and record.get("enabled") is True
            and record.get("enforced") is False
            and record.get("scope")
            == "task041_5nm_balh_candidate_single_invocation"
            and record.get("reason")
            == "user_authorized_single_candidate_time_override"
            and record.get("producer_time_stop_unchanged") is True
            and isinstance(identity, Mapping)
            and record.get("model_id") == model_id
            and record.get("run_id") == identity.get("run_id")
            and record.get("source_sha") == supervisor.get("source_sha")
            and record.get("source_sha") == manifest.get("source_sha")
            and isinstance(worker_record, Mapping)
            and worker_record.get("enabled") is True
            and worker_record.get("enforced") is False
            and worker_record.get("scope") == record.get("scope")
            and worker_record.get("reason") == record.get("reason")
            and worker_record.get("model_id") == record.get("model_id")
            and worker_record.get("run_id") == record.get("run_id")
            and worker_record.get("source_sha") == record.get("source_sha")
            and consumer_summary.get("source_sha") == record.get("source_sha")
        )
        time_stop_override = {
            "status": "valid" if valid else "invalid",
            "enabled": bool(record.get("enabled") is True)
            if isinstance(record, Mapping)
            else False,
            "applies": bool(valid),
            "record": dict(record) if isinstance(record, Mapping) else None,
            "evidence": {
                "run_manifest": {
                    "path": str(manifest_path),
                    "sha256": _sha256(manifest_path)
                    if manifest_path.is_file()
                    else None,
                },
                "supervisor_summary": {
                    "path": str(supervisor_path),
                    "sha256": _sha256(supervisor_path),
                },
                "consumer_summary": {
                    "path": str(consumer_summary_path),
                    "sha256": _sha256(consumer_summary_path)
                    if consumer_summary_path.is_file()
                    else None,
                },
            },
        }
    time_stop_overridden = time_stop_override["applies"] is True
    supervisor_wall_seconds = _optional_finite(supervisor.get("wall_seconds"))
    phase_results = supervisor.get("phase_results")
    if not isinstance(phase_results, Mapping):
        return {
            "status": "evidence_incomplete",
            "pass": False,
            "reason": "public phase_results are missing",
        }
    try:
        from src.io.input_validation import task041_balh_phase_limits_for_model

        frozen_limits = {
            phase: dict(task041_balh_phase_limits_for_model(model_id, phase))
            for phase in ("producer", "consumer")
        }
    except (KeyError, ValueError) as exc:
        raise Task041ComparisonError(
            f"Task041 frozen resource limits are unavailable for {model_id}"
        ) from exc
    sample_path = public_root / "numerical_output" / "log" / "memory_stages.jsonl"
    if not sample_path.is_file():
        return {
            "status": "evidence_incomplete",
            "pass": False,
            "reason": (
                "public numerical_output/log/memory_stages.jsonl is missing"
            ),
        }
    raw_sha = _sha256(sample_path)
    phase_views: dict[str, Any] = {}
    for phase_name in ("producer", "consumer"):
        phase = phase_results.get(phase_name)
        samples = _load_samples(sample_path, phase_name)
        phase_views[phase_name] = _resource_phase(
            phase_name,
            phase,
            samples,
            raw_sha,
            frozen_limits[phase_name],
            time_stop_overridden=time_stop_overridden,
        )
    current = [
        view
        for view in phase_views.values()
        if view.get("reused") is not True and view.get("status") == "measured"
    ]
    current_wall_values = [
        view["phase_wall_seconds"]
        for view in current
        if isinstance(view.get("phase_wall_seconds"), (int, float))
    ]
    current_wall = sum(current_wall_values) if current_wall_values else None
    budget = supervisor.get("compute_wall_budget")
    batch_limit = float(_CONTRACT["resource"]["batch_wall_limit_seconds"])
    if not isinstance(budget, Mapping):
        batch = {
            "status": "not_measured",
            "pass": False,
            "reason": "compute_wall_budget is missing",
        }
    else:
        used_before = _optional_finite(budget.get("used_before_seconds"))
        used_after = _optional_finite(budget.get("used_after_seconds"))
        recorded_limit = _optional_finite(budget.get("limit_seconds"))
        expected_after = (
            None if used_before is None or current_wall is None else used_before + current_wall
        )
        used_before_status = budget.get("used_before_status")
        used_after_status = budget.get("used_after_status")
        current_status = budget.get("current_invocation_status")
        batch = {
            "status": (
                "measured_current_with_derived_baseline"
                if isinstance(used_before_status, str)
                and used_before_status.startswith("derived")
                else "measured_current"
            ),
            "basis": budget.get("basis"),
            "used_before_status": used_before_status,
            "current_invocation_status": current_status,
            "used_after_status": used_after_status,
            "initial_batch_allowance": budget.get("initial_batch_allowance"),
            "derived_allowance_margin_seconds": budget.get(
                "derived_allowance_margin_seconds"
            ),
            "used_before_seconds": used_before,
            "remaining_before_seconds": _optional_finite(
                budget.get("remaining_seconds")
            ),
            "current_invocation_seconds": current_wall,
            "used_after_seconds": used_after,
            "remaining_after_seconds": _optional_finite(
                budget.get("remaining_after_seconds")
            ),
            "limit_seconds": batch_limit,
            "recorded_limit_seconds": recorded_limit,
            "pass": bool(
                used_before is not None
                and current_wall is not None
                and used_after is not None
                and recorded_limit == batch_limit
                and expected_after is not None
                and math.isclose(used_after, expected_after, rel_tol=0.0, abs_tol=1.0e-6)
                and (
                    time_stop_overridden
                    or used_after <= batch_limit
                )
            ),
        }
    producer = phase_views["producer"]
    consumer = phase_views["consumer"]
    if producer.get("reused") is True:
        derived = {
            "status": "inherited_producer_deferred_to_pair",
            "peak": None,
            "wall_seconds": None,
            "producer": producer,
            "consumer": consumer,
        }
    elif producer.get("status") == "measured" and consumer.get("status") == "measured":
        derived_peak = {}
        for field in _RESOURCE_PEAK_FIELDS:
            values = [
                view["peak"].get(field)
                for view in (producer, consumer)
                if isinstance(view.get("peak"), Mapping)
                and type(view["peak"].get(field)) is int
            ]
            derived_peak[field] = max(values) if len(values) == 2 else None
        derived = {
            "status": "derived",
            "semantics": "max(producer,consumer) per quantity; wall is phase sum",
            "peak": derived_peak,
            "wall_seconds": sum(
                view["phase_wall_seconds"] for view in (producer, consumer)
            ),
            "producer": producer,
            "consumer": consumer,
        }
    else:
        derived = {
            "status": "unqualified",
            "peak": None,
            "wall_seconds": None,
            "producer": producer,
            "consumer": consumer,
        }
    return {
        "status": "measured" if current else "evidence_incomplete",
        "method": method,
        "pass": bool(
            current
            and all(view.get("pass") is True for view in current)
            and batch.get("pass") is True
        ),
        "public_supervisor_summary_sha256": _sha256(supervisor_path),
        "supervisor_wall_seconds": supervisor_wall_seconds,
        "phase_sum_wall_seconds": current_wall,
        "raw_samples": {
            "path": str(sample_path),
            "sha256": raw_sha,
            "includes_post_phase": all(
                view.get("post_phase_sample_count", 0) > 0 for view in current
            ),
        },
        "phases": phase_views,
        "batch_compute_wall": batch,
        "current_invocation_compute_wall_seconds": current_wall,
        "time_stop_override": time_stop_override,
        "derived_common_producer_workflow": derived,
        "shared_cgroup_history_not_used_as_peak": True,
        "pss_uss_semantics": "optional; unreadable values remain None",
    }


def _load_task041_side_balh_result(
    run_directory: str | Path, *, method: str
) -> Task041Result:
    """Load one strict Task041 exact or candidate consumer result."""

    if method not in {"candidate", "exact"}:
        _fail("method must be candidate or exact")
    public_root, consumer_root, summary_path = _result_roots(run_directory)
    summary = _read_json(summary_path, "Task041 consumer summary")
    expected_profile = (
        "task041.side_balh.candidate_consumer.v1"
        if method == "candidate"
        else "task041.side_balh.exact_consumer.v1"
    )
    expected_route = (
        "task041_balh_candidate" if method == "candidate" else "task041_balh_exact"
    )
    expected_status = (
        "research_only_approximate_candidate" if method == "candidate" else "exact_side"
    )
    expected_method = (
        "task041_balh_side_inverse_response_fgmres32"
        if method == "candidate"
        else "task041_exact_side_full_formal"
    )
    if summary.get("schema") != expected_profile or summary.get("profile") != expected_profile:
        _fail(f"Task041 {method} consumer profile is not the registered new profile")
    if summary.get("consumer_route") != expected_route or summary.get("qualification_status") != expected_status:
        _fail(f"Task041 {method} provenance is not explicit")
    # The solve report is written before the authority/grid artifacts.  Keep
    # its raw gate evidence available when a failed solve prevents the later
    # authority artifact from being emitted.
    own_gates = _own_gates(summary, {})
    try:
        authority_path, authority, run_manifest = _authority_and_manifest(
            summary, consumer_root, public_root
        )
    except Task041ComparisonError as exc:
        exc.context["own_gates"] = own_gates
        raise
    own_gates = _own_gates(summary, authority)
    try:
        identity = _normal_identity(summary.get("identity"), "consumer_identity")
    except Task041ComparisonError as exc:
        exc.category = "identity"
        raise
    from benchmarks.task041_legacy_native_packet import (
        TASK041_LEGACY_NATIVE_PACKET_ORIGIN,
    )

    packet_origin = summary.get("packet_origin")
    legacy_native = packet_origin == TASK041_LEGACY_NATIVE_PACKET_ORIGIN
    if packet_origin is not None and not legacy_native:
        _fail("Task041 consumer packet origin is unsupported", category="identity")
    producer_raw = summary.get("producer_identity")
    if not isinstance(producer_raw, Mapping):
        binding = summary.get("consumer_binding")
        producer_raw = binding.get("producer_identity") if isinstance(binding, Mapping) else None
    try:
        producer_identity = (
            _normal_legacy_identity(producer_raw, "producer_identity")
            if legacy_native
            else _normal_identity(producer_raw, "producer_identity")
        )
    except Task041ComparisonError as exc:
        exc.category = "identity"
        raise
    if identity["source_sha"] != summary.get("source_sha"):
        _fail("consumer summary source SHA differs from consumer identity")
    _validate_manifest_identity(run_manifest, identity, "run_manifest")
    _validate_public_input_artifacts(public_root, run_manifest, identity)
    if legacy_native:
        _validate_legacy_consumer_binding(
            summary, identity, producer_identity, public_root
        )
    authority_identity = {
        "source_sha": authority.get("source_sha"),
        "physical_model_sha256": authority.get("physical_model_sha256"),
        "model_id": authority.get("model_id"),
        "mpi_size": authority.get("mpi_size"),
        "requested_modes": authority.get("requested_modes"),
    }
    if authority_identity != {
        "source_sha": identity["source_sha"],
        "physical_model_sha256": identity["physical_sha256"],
        "model_id": identity["model_id"],
        "mpi_size": identity["mpi_size"],
        "requested_modes": identity["mode_count"],
    }:
        _fail("Task041 authority identity differs from consumer identity")
    if authority.get("qualification_method") != expected_method:
        _fail("Task041 authority qualification method is not the registered route")
    packet = _packet_binding(summary, producer_identity, consumer_root, public_root)
    consumer_count, consumer_sha = _parse_identity_external(
        identity, "consumer_identity"
    )
    producer_count, producer_sha = _parse_identity_external(
        producer_identity, "producer_identity"
    )
    authority_keys = _authority_inventory(
        authority.get("external_mode_inventory"), "authority"
    )
    authority_count = authority.get("inventory_count")
    if type(authority_count) is not int or authority_count != len(authority_keys):
        _fail("Task041 authority inventory_count does not match its keys")
    authority_sha = _identity_key_digest(authority_keys)
    if not (
        consumer_count == producer_count == authority_count
        and consumer_sha == producer_sha == authority_sha
    ):
        _fail("Task041 consumer, producer, and authority external key identities differ")
    external_rows = _parse_external_orders(authority, authority_keys)
    try:
        arrays, array_descriptors = _load_grid_payload(
            authority,
            authority_path,
            public_root,
            consumer_root,
            authority_keys,
            identity,
        )
    except Task041ComparisonError as exc:
        exc.context["own_gates"] = own_gates
        raise
    try:
        canonical = _load_canonical(
            authority, authority_path, public_root, consumer_root, identity["mpi_size"]
        )
    except Task041ComparisonError as exc:
        exc.context["own_gates"] = own_gates
        raise
    try:
        resources = _resources(public_root, method, identity["model_id"])
    except Task041ComparisonError as exc:
        exc.context["own_gates"] = own_gates
        raise
    return Task041Result(
        method=method,
        root=consumer_root,
        public_root=public_root,
        summary=summary,
        run_manifest=run_manifest,
        authority=authority,
        authority_path=authority_path,
        identity=identity,
        producer_identity=producer_identity,
        packet=packet,
        external_keys=authority_keys,
        external_rows=external_rows,
        arrays=arrays,
        array_descriptors=array_descriptors,
        canonical=canonical,
        own_gates=own_gates,
        resources=resources,
    )


def load_task041_side_balh_result(
    run_directory: str | Path, *, method: str
) -> Task041Result:
    """Load one result while preserving raw own-gate evidence on load failure."""

    try:
        return _load_task041_side_balh_result(run_directory, method=method)
    except Task041ComparisonError as exc:
        exc.context.setdefault("method", method)
        raise


def _scalar_delta(candidate: Any, exact: Any, limit: float) -> dict[str, Any]:
    candidate_value = _optional_finite(candidate)
    exact_value = _optional_finite(exact)
    if candidate_value is None or exact_value is None:
        return {
            "candidate": candidate,
            "exact": exact,
            "absolute_delta": None,
            "limit": limit,
            "pass": False,
            "status": "not_measured",
        }
    delta = abs(candidate_value - exact_value)
    return {
        "candidate": candidate_value,
        "exact": exact_value,
        "absolute_delta": delta,
        "limit": limit,
        "pass": bool(delta <= limit),
        "status": "measured",
    }


def _compare_observables(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    left = candidate.own_gates["observables"]
    right = exact.own_gates["observables"]
    values = {
        name: _scalar_delta(
            left[name], right[name], _CONTRACT["thresholds"]["observable_absolute"]
        )
        for name in ("R_total", "T_total", "A_balance", "A_volume")
    }
    return {"values": values, "pass": all(item["pass"] for item in values.values())}


def _compare_coordinates(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    values = {}
    for name in ("x_nm", "y_nm", "z_nm"):
        left = candidate.arrays[name]
        right = exact.arrays[name]
        values[name] = {
            "candidate_shape": list(left.shape),
            "exact_shape": list(right.shape),
            "candidate_dtype": str(left.dtype),
            "exact_dtype": str(right.dtype),
            "exact": bool(
                left.shape == right.shape
                and left.dtype == right.dtype
                and np.array_equal(left, right)
            ),
        }
    return {"fields": values, "pass": all(item["exact"] for item in values.values())}


def _compare_selected_fields(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    limit = _CONTRACT["thresholds"]["selected_field_relative_l2"]
    floor = _CONTRACT["thresholds"]["selected_field_denominator_floor"]
    for name, unit in (("E_V_per_m", "V/m"), ("H_A_per_m", "A/m")):
        left = candidate.arrays[name]
        right = exact.arrays[name]
        absolute = float(np.linalg.norm(left - right))
        denominator = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), floor)
        planes = []
        for index, z_nm in enumerate(_CONTRACT["payload"]["z_nm"]):
            left_plane = left[index]
            right_plane = right[index]
            plane_absolute = float(np.linalg.norm(left_plane - right_plane))
            plane_denominator = max(
                float(np.linalg.norm(left_plane)), float(np.linalg.norm(right_plane)), floor
            )
            planes.append(
                {
                    "z_nm": z_nm,
                    "absolute_l2": plane_absolute,
                    "max_abs": float(np.max(np.abs(left_plane - right_plane))),
                    "denominator": plane_denominator,
                    "relative_l2": plane_absolute / plane_denominator,
                    "gate": "diagnostic_only",
                }
            )
        relative = absolute / denominator
        result[name] = {
            "unit": unit,
            "absolute_l2": absolute,
            "max_abs": float(np.max(np.abs(left - right))),
            "denominator": denominator,
            "relative_l2": relative,
            "limit": limit,
            "planes": planes,
            "pass": bool(relative <= limit),
        }
    return {"fields": result, "pass": all(item["pass"] for item in result.values())}


def _compare_canonical(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    limit = _CONTRACT["thresholds"]["canonical_relative_l2"]
    denominator_floor = np.finfo(float).tiny
    for role in _CANONICAL_ROLES:
        left = candidate.canonical[role]
        right = exact.canonical[role]
        try:
            comparison = compare_canonical_manifests(
                left["path"],
                right["path"],
                left_sha256=left["sha256"],
                right_sha256=right["sha256"],
                relative_tolerance=limit,
            )
        except (OSError, KeyError, ValueError) as exc:
            comparisons[role] = {
                "status": "checker_error",
                "error": f"{type(exc).__name__}: {exc}",
                "pass": False,
            }
        else:
            left_by_key = {key: value for key, value in left["packets"]}
            right_by_key = {key: value for key, value in right["packets"]}
            common = tuple(sorted(set(left_by_key) & set(right_by_key), key=repr))
            left_values = np.asarray(
                [left_by_key[key] for key in common], dtype=np.complex128
            )
            right_values = np.asarray(
                [right_by_key[key] for key in common], dtype=np.complex128
            )
            absolute_l2 = float(np.linalg.norm(left_values - right_values))
            denominator = max(float(np.linalg.norm(right_values)), denominator_floor)
            relative_l2 = absolute_l2 / denominator
            max_abs = float(
                np.max(np.abs(left_values - right_values), initial=0.0)
            )
            comparisons[role] = {
                "relative_limit": limit,
                **comparison,
                "absolute_l2": absolute_l2,
                "denominator": denominator,
                "relative_coefficient_l2": relative_l2,
                "max_abs_coefficient_error": max_abs,
                "denominator_definition": "max(norm(exact same-key coefficients), numpy.finfo(float).tiny)",
                "left_nonempty_shard_count": left["nonempty_shard_count"],
                "right_nonempty_shard_count": right["nonempty_shard_count"],
                "left_unique_packet_count": left["unique_packet_count"],
                "right_unique_packet_count": right["unique_packet_count"],
                "pass": bool(
                    comparison.get("pass") is True
                    and relative_l2 <= limit
                    and left["nonempty_shard_count"] > 0
                    and right["nonempty_shard_count"] > 0
                    and left["unique_packet_count"]
                    == left["global_summed_packet_count"]
                    and right["unique_packet_count"]
                    == right["global_summed_packet_count"]
                ),
            }
    return {
        "roles": comparisons,
        "pass": all(item.get("pass") is True for item in comparisons.values()),
    }


def _complex_json(value: complex | None) -> list[float] | None:
    if value is None:
        return None
    return [float(value.real), float(value.imag)]


def _compare_external(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    keys = sorted(
        set(candidate.external_rows) | set(exact.external_rows), key=_key_order
    )
    significant_floor = _CONTRACT["thresholds"]["external_significant_power_floor"]
    relative_limit = _CONTRACT["thresholds"]["external_significant_relative"]
    rows = []
    for key in keys:
        left = candidate.external_rows.get(key)
        right = exact.external_rows.get(key)
        left_power = left.get("power_ratio") if left is not None else None
        right_power = right.get("power_ratio") if right is not None else None
        left_amplitude = left.get("outgoing_amplitude") if left is not None else None
        right_amplitude = right.get("outgoing_amplitude") if right is not None else None
        present = left is not None and right is not None
        significant = bool(
            present and max(float(left_power), float(right_power)) >= significant_floor
        )
        if present:
            power_absolute = abs(float(left_power) - float(right_power))
            power_denominator = max(float(left_power), float(right_power), 1.0e-30)
            amplitude_absolute = abs(left_amplitude - right_amplitude)
            amplitude_denominator = max(
                abs(left_amplitude), abs(right_amplitude), 1.0e-30
            )
            power_relative = power_absolute / power_denominator
            amplitude_relative = amplitude_absolute / amplitude_denominator
        else:
            power_absolute = power_denominator = power_relative = None
            amplitude_absolute = amplitude_denominator = amplitude_relative = None
        rows.append(
            {
                "key": list(key),
                "candidate_power": left_power,
                "exact_power": right_power,
                "candidate_amplitude": _complex_json(left_amplitude),
                "exact_amplitude": _complex_json(right_amplitude),
                "power_absolute_delta": power_absolute,
                "power_denominator": power_denominator,
                "power_relative_delta": power_relative,
                "amplitude_absolute_delta": amplitude_absolute,
                "amplitude_denominator": amplitude_denominator,
                "amplitude_relative_delta": amplitude_relative,
                "significant": significant,
                "pass": bool(
                    present
                    and (
                        not significant
                        or (
                            power_relative <= relative_limit
                            and amplitude_relative <= relative_limit
                        )
                    )
                ),
            }
        )
    keys_exact = set(candidate.external_rows) == set(exact.external_rows)
    return {
        "keys_exact": keys_exact,
        "significant_power_floor": significant_floor,
        "relative_limit": relative_limit,
        "rows": rows,
        "pass": bool(keys_exact and all(row["pass"] for row in rows)),
    }


def _normal_flux(arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    return np.asarray(
        0.5
        * np.real(
            np.cross(
                arrays["E_V_per_m"], np.conjugate(arrays["H_A_per_m"]), axis=-1
            )[..., 2]
        ).mean(axis=(1, 2)),
        dtype=np.float64,
    )


def _compare_normal_flux(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    left = _normal_flux(candidate.arrays)
    right = _normal_flux(exact.arrays)
    absolute = float(np.linalg.norm(left - right))
    denominator = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-30)
    return {
        "formula": "0.5 Re((E cross conj(H))_z)",
        "candidate_per_plane": left.tolist(),
        "exact_per_plane": right.tolist(),
        "absolute_l2": absolute,
        "max_abs": float(np.max(np.abs(left - right))),
        "denominator": denominator,
        "relative_l2": absolute / denominator,
        "limit": _CONTRACT["thresholds"]["normal_flux_relative_l2"],
        "pass": bool(
            absolute / denominator
            <= _CONTRACT["thresholds"]["normal_flux_relative_l2"]
        ),
    }


def _pair_identity(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    checks = {
        "physical_sha256": candidate.identity["physical_sha256"]
        == exact.identity["physical_sha256"],
        "wavelength_nm": candidate.identity["wavelength_nm"]
        == exact.identity["wavelength_nm"],
        "mesh": candidate.identity["mesh"] == exact.identity["mesh"],
        "mode_count": candidate.identity["mode_count"] == exact.identity["mode_count"],
        "mpi_size": candidate.identity["mpi_size"] == exact.identity["mpi_size"],
        "comparison_group": candidate.identity["comparison_group"]
        == exact.identity["comparison_group"],
        "scope": candidate.identity["scope"] == exact.identity["scope"],
        "dtn_order_policy": candidate.identity["dtn_order_policy"]
        == exact.identity["dtn_order_policy"],
        "physical_contract": candidate.identity["physical_contract"]
        == exact.identity["physical_contract"],
        "cross_section_partition": candidate.identity["cross_section_partition"]
        == exact.identity["cross_section_partition"],
        "external_keys": candidate.external_keys == exact.external_keys,
        "selected_packet_manifest_sha256": candidate.packet["manifest_sha256"]
        == exact.packet["manifest_sha256"],
        "selected_packet_identity_sha256": candidate.packet["identity_sha256"]
        == exact.packet["identity_sha256"],
        "producer_source_sha": candidate.producer_identity["source_sha"]
        == exact.producer_identity["source_sha"],
        "producer_identity": candidate.producer_identity == exact.producer_identity,
    }
    return {
        "checks": checks,
        "consumer_sources": {
            "candidate": candidate.identity["source_sha"],
            "exact": exact.identity["source_sha"],
            "may_differ": True,
        },
        "consumer_inputs": {
            "candidate": {
                "input_sha256": candidate.identity["input_sha256"],
                "resolved_sha256": candidate.identity["resolved_sha256"],
                "model_id": candidate.identity["model_id"],
            },
            "exact": {
                "input_sha256": exact.identity["input_sha256"],
                "resolved_sha256": exact.identity["resolved_sha256"],
                "model_id": exact.identity["model_id"],
            },
        },
        "pass": all(checks.values()),
    }


def _side_error(
    method: str, run_directory: str | Path, error: Task041ComparisonError
) -> dict[str, Any]:
    context = dict(error.context)
    own_gates = context.get("own_gates")
    if error.category == "identity":
        classification = "TASK041_SIDE_BALH_IDENTITY_FAIL"
    elif (
        isinstance(own_gates, Mapping)
        and own_gates.get("failure_classification") == "numeric_gate_fail"
    ):
        classification = "TASK041_SIDE_BALH_NUMERICAL_GATE_FAIL"
    else:
        classification = "REFERENCE_EVIDENCE_INCOMPLETE"
    return {
        "method": method,
        "root": context.get("root", str(Path(run_directory).resolve())),
        "source_sha": context.get("source_sha"),
        "own_gates": own_gates,
        "pass": False,
        "classification": classification,
        "error_category": error.category,
        "errors": [f"{type(error).__name__}: {error}"],
    }


def _side_success(result: Task041Result) -> dict[str, Any]:
    return {
        "method": result.method,
        "root": str(result.root),
        "source_sha": result.identity["source_sha"],
        "identity": dict(result.identity),
        "producer_identity": dict(result.producer_identity),
        "packet_origin": result.summary.get("packet_origin"),
        "consumer_binding": result.summary.get("consumer_binding"),
        "own_gates": result.own_gates,
        "resource": result.resources,
        "load_pass": True,
    }


def _resource_value(view: Mapping[str, Any], field: str) -> int | None:
    peak = view.get("peak")
    value = peak.get(field) if isinstance(peak, Mapping) else None
    return value if type(value) is int and value >= 0 else None


def _common_workflow_resources(
    candidate: Task041Result, exact: Task041Result
) -> dict[str, Any]:
    candidate_phases = candidate.resources.get("phases", {})
    exact_phases = exact.resources.get("phases", {})
    candidate_producer = candidate_phases.get("producer", {})
    exact_producer = exact_phases.get("producer", {})
    candidate_consumer = candidate_phases.get("consumer", {})
    exact_consumer = exact_phases.get("consumer", {})
    candidate_reused = candidate_producer.get("reused") is True
    producer_binding = {
        "same_packet": candidate.packet["manifest_sha256"]
        == exact.packet["manifest_sha256"]
        and candidate.packet["identity_sha256"]
        == exact.packet["identity_sha256"],
        "same_producer_identity": candidate.producer_identity
        == exact.producer_identity,
        "exact_raw_phase_measured": exact_producer.get("status") == "measured",
        "candidate_reuses_producer": candidate_reused,
        "inherited_source": candidate_producer.get("resource_source"),
        "inherited_supervisor_summary_sha256": candidate_producer.get(
            "supervisor_summary_sha256"
        ),
        "exact_supervisor_summary_sha256": exact.resources.get(
            "public_supervisor_summary_sha256"
        ),
    }
    producer_binding["pass"] = bool(
        producer_binding["same_packet"]
        and producer_binding["same_producer_identity"]
        and producer_binding["exact_raw_phase_measured"]
        and (
            candidate_reused
            or candidate_producer.get("status") == "measured"
        )
    )
    producer_qualified = bool(
        producer_binding["pass"] and exact_producer.get("pass") is True
    )
    producer_values = {
        field: _resource_value(exact_producer, field)
        if producer_qualified
        else None
        for field in _RESOURCE_PEAK_FIELDS
    }
    producer_wall = _optional_finite(exact_producer.get("phase_wall_seconds"))
    producer = {
        "status": "derived" if producer_binding["pass"] else "unqualified",
        "source": "exact consumer raw producer phase",
        "supervisor_summary_sha256": exact.resources.get(
            "public_supervisor_summary_sha256"
        ),
        "raw_samples_sha256": exact_producer.get("raw_samples_sha256"),
        "peak": producer_values,
        "phase_wall_seconds": producer_wall,
        "qualified": producer_qualified,
        "worker_tree": exact_producer.get("worker_tree"),
    }

    def _difference(
        candidate_value: int | None, exact_value: int | None
    ) -> dict[str, Any]:
        if candidate_value is None or exact_value is None:
            return {
                "candidate": candidate_value,
                "exact": exact_value,
                "absolute_delta_bytes": None,
                "absolute_delta_gib": None,
                "relative_delta": None,
                "percent_delta": None,
                "status": "RESOURCE_COMPARISON_INCONCLUSIVE",
                "credibility": "insufficient_measurement",
                "credible_saving": False,
            }
        delta = exact_value - candidate_value
        relative = delta / max(exact_value, np.finfo(float).tiny)
        return {
            "candidate": candidate_value,
            "exact": exact_value,
            "absolute_delta_bytes": delta,
            "absolute_delta_gib": delta / float(2**30),
            "relative_delta": relative,
            "percent_delta": 100.0 * relative,
            "direction": (
                "candidate_lower"
                if delta > 0
                else "candidate_equal"
                if delta == 0
                else "candidate_higher"
            ),
            "status": "measured_difference",
            "credibility": "not_adjudicated",
            "credible_saving": None,
        }

    consumer_peak_savings = {
        field: _difference(
            _resource_value(candidate_consumer, field),
            _resource_value(exact_consumer, field),
        )
        for field in _WORKFLOW_MEMORY_FIELDS
    }
    common_producer_peak = {
        field: producer_values[field]
        for field in _WORKFLOW_MEMORY_FIELDS
    }
    candidate_workflow_peak = {
        field: (
            max(common_producer_peak[field], consumer_value)
            if common_producer_peak[field] is not None
            and (consumer_value := _resource_value(candidate_consumer, field))
            is not None
            else None
        )
        for field in _WORKFLOW_MEMORY_FIELDS
    }
    exact_workflow_peak = {
        field: (
            max(common_producer_peak[field], consumer_value)
            if common_producer_peak[field] is not None
            and (consumer_value := _resource_value(exact_consumer, field)) is not None
            else None
        )
        for field in _WORKFLOW_MEMORY_FIELDS
    }
    workflow_peak_savings = {
        field: _difference(
            candidate_workflow_peak[field], exact_workflow_peak[field]
        )
        for field in _WORKFLOW_MEMORY_FIELDS
    }

    candidate_consumer_wall = _optional_finite(
        candidate_consumer.get("phase_wall_seconds")
    )
    exact_consumer_wall = _optional_finite(exact_consumer.get("phase_wall_seconds"))
    if candidate_consumer_wall is not None and exact_consumer_wall is not None:
        time_ratio = candidate_consumer_wall / max(exact_consumer_wall, np.finfo(float).tiny)
        time_data = {
            "candidate_consumer_seconds": candidate_consumer_wall,
            "exact_consumer_seconds": exact_consumer_wall,
            "candidate_over_exact": time_ratio,
            "status": "derived_from_two_measured_consumer_phases",
        }
    else:
        time_data = {
            "candidate_consumer_seconds": candidate_consumer_wall,
            "exact_consumer_seconds": exact_consumer_wall,
            "candidate_over_exact": None,
            "status": "not_measured",
        }
    if producer_wall is not None and candidate_consumer_wall is not None:
        candidate_workflow_wall = producer_wall + candidate_consumer_wall
    else:
        candidate_workflow_wall = None
    if producer_wall is not None and exact_consumer_wall is not None:
        exact_workflow_wall = producer_wall + exact_consumer_wall
    else:
        exact_workflow_wall = None
    candidate_supervisor_wall = _optional_finite(
        candidate.resources.get("supervisor_wall_seconds")
    )
    exact_supervisor_wall = _optional_finite(
        exact.resources.get("supervisor_wall_seconds")
    )
    candidate_phase_sum = _optional_finite(
        candidate.resources.get("phase_sum_wall_seconds")
    )
    exact_phase_sum = _optional_finite(exact.resources.get("phase_sum_wall_seconds"))
    workflow_time_ratio = (
        candidate_workflow_wall / max(exact_workflow_wall, np.finfo(float).tiny)
        if candidate_workflow_wall is not None and exact_workflow_wall is not None
        else None
    )
    return {
        "producer_binding": producer_binding,
        "common_producer": producer,
        "consumer": {
            "candidate": {
                "status": candidate_consumer.get("status"),
                "raw_samples_sha256": candidate_consumer.get("raw_samples_sha256"),
                "sample_count": candidate_consumer.get("sample_count"),
                "post_phase_sample_count": candidate_consumer.get(
                    "post_phase_sample_count"
                ),
            },
            "exact": {
                "status": exact_consumer.get("status"),
                "raw_samples_sha256": exact_consumer.get("raw_samples_sha256"),
                "sample_count": exact_consumer.get("sample_count"),
                "post_phase_sample_count": exact_consumer.get(
                    "post_phase_sample_count"
                ),
            },
        },
        "memory_savings": {
            "status": (
                "measured_difference"
                if all(
                    item["status"] == "measured_difference"
                    for item in consumer_peak_savings.values()
                )
                else "RESOURCE_COMPARISON_INCONCLUSIVE"
            ),
            "semantics": (
                "descriptive measured consumer peak difference; no H2 credibility gate"
            ),
            "per_quantity": consumer_peak_savings,
        },
        "workflow_peak": {
            "primary_quantity": "process_tree_rss_bytes",
            "semantics": (
                "max(common producer peak, consumer peak) per quantity; "
                "PSS/USS are optional appended diagnostics"
            ),
            "common_producer_peak": common_producer_peak,
            "candidate": candidate_workflow_peak,
            "exact": exact_workflow_peak,
            "savings": workflow_peak_savings,
        },
        "observable_diagnostics": {
            "A_balance_minus_(1-R-T)": {
                "candidate": candidate.own_gates.get("balance_from_rt"),
                "exact": exact.own_gates.get("balance_from_rt"),
                "status": "diagnostic_only",
            }
        },
        "time": time_data,
        "workflow_wall": {
            "candidate_seconds": candidate_workflow_wall,
            "exact_seconds": exact_workflow_wall,
            "candidate_supervisor_wall_seconds": candidate_supervisor_wall,
            "exact_supervisor_wall_seconds": exact_supervisor_wall,
            "candidate_phase_sum_seconds": candidate_phase_sum,
            "exact_phase_sum_seconds": exact_phase_sum,
            "candidate_over_exact": workflow_time_ratio,
            "semantics": "derived common producer phase plus measured consumer phase",
            "status": (
                "derived"
                if candidate_workflow_wall is not None
                and exact_workflow_wall is not None
                else "not_measured"
            ),
        },
        "pass": bool(
            producer_binding["pass"]
            and exact_producer.get("pass") is True
            and candidate_consumer.get("pass") is True
            and exact_consumer.get("pass") is True
        ),
    }


def compare_task041_side_balh_pair(
    candidate_run: str | Path, exact_run: str | Path
) -> dict[str, Any]:
    """Compare one Task041 BAL_H candidate (left) to one exact result (right)."""

    candidate: Task041Result | None = None
    exact: Task041Result | None = None
    candidate_error: dict[str, Any] | None = None
    exact_error: dict[str, Any] | None = None
    try:
        candidate = load_task041_side_balh_result(candidate_run, method="candidate")
    except Task041ComparisonError as exc:
        candidate_error = _side_error("candidate", candidate_run, exc)
    try:
        exact = load_task041_side_balh_result(exact_run, method="exact")
    except Task041ComparisonError as exc:
        exact_error = _side_error("exact", exact_run, exc)

    if candidate is None or exact is None:
        candidate_view = _side_success(candidate) if candidate is not None else candidate_error
        exact_view = _side_success(exact) if exact is not None else exact_error
        return {
            "schema": _CONTRACT["schema"],
            "candidate": candidate_view,
            "exact": exact_view,
            "numerical_pass": False,
            "consumer_resource_contract_pass": False,
            "resource_contract_pass": False,
            "comparison_contract_pass": False,
            "pass": False,
            "classification": (
                candidate_error or exact_error or {}
            ).get("classification", "REFERENCE_EVIDENCE_INCOMPLETE"),
        }

    identity = _pair_identity(candidate, exact)
    coordinates = _compare_coordinates(candidate, exact)
    fields = _compare_selected_fields(candidate, exact)
    observables = _compare_observables(candidate, exact)
    canonical = _compare_canonical(candidate, exact)
    external = _compare_external(candidate, exact)
    normal_flux = _compare_normal_flux(candidate, exact)
    common_workflow = _common_workflow_resources(candidate, exact)
    numerical_pass = bool(
        candidate.own_gates["pass"]
        and exact.own_gates["pass"]
        and coordinates["pass"]
        and fields["pass"]
        and observables["pass"]
        and canonical["pass"]
        and external["pass"]
        and normal_flux["pass"]
    )
    resource_contract_pass = bool(
        candidate.resources["pass"]
        and exact.resources["pass"]
        and common_workflow["pass"]
    )
    consumer_resource_contract_pass = bool(
        candidate.resources["pass"] and exact.resources["pass"]
    )
    comparison_contract_pass = bool(identity["pass"])
    result = {
        "schema": _CONTRACT["schema"],
        "candidate": _side_success(candidate),
        "exact": _side_success(exact),
        "identity": identity,
        "coordinates": coordinates,
        "selected_fields": fields,
        "observables": observables,
        "canonical": canonical,
        "external_channels": external,
        "normal_flux": normal_flux,
        "common_workflow": common_workflow,
        "numerical_pass": numerical_pass,
        "consumer_resource_contract_pass": consumer_resource_contract_pass,
        "resource_contract_pass": resource_contract_pass,
        "comparison_contract_pass": comparison_contract_pass,
    }
    result["pass"] = bool(
        numerical_pass and resource_contract_pass and comparison_contract_pass
    )
    result["classification"] = (
        "TASK041_SIDE_BALH_COMPARISON_PASS"
        if result["pass"]
        else "TASK041_SIDE_BALH_NUMERICAL_OR_RESOURCE_FAIL"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--exact", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = compare_task041_side_balh_pair(args.candidate, args.exact)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if result["pass"] else 1


__all__ = [
    "Task041ComparisonError",
    "Task041Result",
    "compare_task041_side_balh_pair",
    "load_task041_side_balh_result",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
