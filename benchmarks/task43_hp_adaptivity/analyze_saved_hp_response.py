"""Read-only V19 decomposition of already saved Task43 fields.

This module is deliberately NumPy-only.  It never imports a solver, restores a
finite-element field, builds quadrature, samples a field, or runs an operator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_SCHEMA = "task43.v19.saved_hp_response_contract.v1"
CONTRACT_RELATIVE_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/v19_saved_hp_response_contract.json"
)
NPY_RECORD_KEY = "__task43_record_json__"
THREAD_KEYS = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
)
CHANNEL_KEYS = tuple(
    (side, m, n, pol)
    for side in ("top", "bottom")
    for m in range(-4, 5)
    for n in range(-8, 9)
    for pol in ("s", "p")
)
J_POWER_TOLERANCES = {
    "R_total": 1.0e-5,
    "T_total": 1.0e-5,
    "A_volume": 1.0e-5,
    "R00_s": 1.0e-6,
    "R00_p": 1.0e-6,
    "R00_total": 1.0e-5,
}
J_AMPLITUDE_TOLERANCE = 1.0e-4
J_CHANNEL_POWER_TOLERANCE = 1.0e-6
REPLAY_RTOL = 3.0e-11
REPLAY_ATOL = 1.0e-15
G_IDENTITY_TOL = 1.0e-10
VOLUME_NM3 = 350000.0
EXPECTED_SOURCE_ROLES = frozenset({
    "r9_plan", "h8_plan", "p8_plan", "p5_comparison", "p8_comparison",
    "r9_modal", "h8_modal", "p8_modal", "y6_modal", "r9_absorption",
    "h8_absorption", "p8_absorption", "y6_summary",
})
EXPECTED_SOURCES = {
    "r9_plan": ("benchmarks/artifacts/task43/round9_p_only_authority_attempt1/plan_output/plans/round9_p_up.json", "9f8bbc8f90ae609822ac934311986f75d1648eba5b26b6a488647e9b94fd4947"),
    "h8_plan": ("benchmarks/artifacts/task43/v11_science/formal/R9_H8_attempt1/run/candidate_plan.json", "f26dc8a9c4a0c6d4aed7d9767477e142e57dadb69db39a437bb05b9bed701688"),
    "p8_plan": ("benchmarks/artifacts/task43/v16_p8/formal/v18_R9_P8_attempt1/run/candidate_plan.json", "10733af8fc00e29d54fa4d4ee18b2e78bc6ed7c15834db7a0ff6902ba4de9a04"),
    "p5_comparison": ("benchmarks/artifacts/task43/v11_science/support/union_comparison_attempt1/comparison/v11_r9_h8_union_comparison.json", "26c836ba9abab4ec2636c7c3467381a25b087e7b9c6e85cd655508589abe8097"),
    "p8_comparison": ("benchmarks/artifacts/task43/v16_p8/support/v18_paired_comparison_recovery_attempt3/comparison/v16_r9_p8_paired_comparison.json", "1fca6095529c01685717f3db97b8d00302bb90fc1dfb2df9042cff58e9e137af"),
    "r9_modal": ("benchmarks/artifacts/task43/round9_p_up_attempt1/run/solve/dtn_port_diffraction_orders_3d.json", "443bd3683027534b349903fc11c97ef21a69fb3982d1bc70fd47781fed28be0e"),
    "h8_modal": ("benchmarks/artifacts/task43/v11_science/formal/R9_H8_attempt1/run/solve/dtn_port_diffraction_orders_3d.json", "cd035508492b0f65798afc669db4e9f93516608d965612f6650ab327d83d8ed3"),
    "p8_modal": ("benchmarks/artifacts/task43/v16_p8/formal/v18_R9_P8_attempt1/run/solve/dtn_port_diffraction_orders_3d.json", "c7b1ff6033f0a901a6e42f827bd26a9f3e7ab1b046dcf57cd7656548d2e446c8"),
    "y6_modal": ("benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/numerical_output/dtn_port_diffraction_orders_3d.json", "667871dbebed4319e23190173941e1cfd7d647b9bf1e99d2f9fbec4d4d6ae463"),
    "r9_absorption": ("benchmarks/artifacts/task43/round9_p_up_attempt1/run/solve/volume_absorption.json", "4f73d4db2da94f52ff5206942e8953b98d7427691f827da7ca047f171851bdd8"),
    "h8_absorption": ("benchmarks/artifacts/task43/v11_science/formal/R9_H8_attempt1/run/solve/volume_absorption.json", "63fad5942ada7021ce18c4394ec557dc2133c4e19136da2741fb2bcfbe2657cb"),
    "p8_absorption": ("benchmarks/artifacts/task43/v16_p8/formal/v18_R9_P8_attempt1/run/solve/volume_absorption.json", "f718627465f72c0783f02f60c73256232d73de00ca34128e237fc3be7459d080"),
    "y6_summary": ("benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/p6_condensed_direct_summary.json", "1323cb258e65e75ea5ae76bdb4c9d6d6d25c7465f486094dc22b7c7264e4bafc"),
}
EXPECTED_STAGE_ROOTS = {
    "T1": "benchmarks/artifacts/task43/v19_saved_hp_response/support/targeted_attempt1",
    "T2": "benchmarks/artifacts/task43/v19_saved_hp_response/support/targeted_recovery1",
    "D1": "benchmarks/artifacts/task43/v19_saved_hp_response/support/decomposition_attempt1",
    "D2": "benchmarks/artifacts/task43/v19_saved_hp_response/support/decomposition_recovery1",
}
EXPECTED_T1_SELECTORS = [
    "src/test/test_task43_saved_hp_response.py::test_weighted_multicell_terms_close_after_reordering",
    "src/test/test_task43_saved_hp_response.py::test_response_direction_cases[aligned]",
    "src/test/test_task43_saved_hp_response.py::test_response_direction_cases[opposite]",
    "src/test/test_task43_saved_hp_response.py::test_response_direction_cases[orthogonal]",
    "src/test/test_task43_saved_hp_response.py::test_domain_cancellation_and_zero_increment",
    "src/test/test_task43_saved_hp_response.py::test_channel_reference_inventory_is_exact",
    "src/test/test_task43_saved_hp_response.py::test_wrong_owner_map_is_rejected",
    "src/test/test_task43_saved_hp_response.py::test_modal_missing_key_is_rejected",
    "src/test/test_task43_saved_hp_response.py::test_modal_duplicate_key_is_rejected",
    "src/test/test_task43_saved_hp_response.py::test_mixed_sample_package_rebound_hash_is_rejected",
    "src/test/test_task43_saved_hp_response.py::test_amplitude_square_identity_is_not_physical_power",
    "src/test/test_task43_saved_hp_response.py::test_archive_readonly_and_q8_survives_q10_write_failure",
]
EXPECTED_ARCHIVE_BINDINGS = {
    "q8": {
        "sample_count": 565248,
        "p5": ("benchmarks/artifacts/task43/v11_science/support/union_comparison_attempt1/comparison/v11_r9_h8_union_q8.npz", "7286c09d6b3f3bb3a7ece1cd46284a9a5faafd6ebbcb213e2568b6a32ed1119e", "task43.v11.union_comparison_samples.v1", "159e993139e2ee7b7b3ba7c722171f932a98e052cabb74c8ab3febbf3f200476"),
        "p8": ("benchmarks/artifacts/task43/v16_p8/support/v18_paired_comparison_attempt1/comparison/v16_r9_p8_q8_samples.npz", "5475cffe826f45217cebd8df35239f4ba8a4a5813657cf2ca7696ce871af792f", "task43.v16.p8.paired-sample.v1", "51751bdc91ddc266b83bbf9cb4d52284d20c4a3662836749a23133637f6a95a5"),
        "point_sha256": "79133226dbc3a87db3fca45aedc21318b71d81b96e504f7dad3fbd6f617781ca",
        "weight_sha256": "00e92e61b9f4ae1b3ab2cc57cad2f9e678072257b5ae75c5eef3ecebf7ee319d",
    },
    "q10": {
        "sample_count": 1104000,
        "p5": ("benchmarks/artifacts/task43/v11_science/support/union_comparison_attempt1/comparison/v11_r9_h8_union_q10.npz", "82d7bc676e23bea0794caf5e16b3d6c28ee02cb18c57cb59e4bfc08a55759f99", "task43.v11.union_comparison_samples.v1", "a6aeb4265cbf11fc0b10ead3fdafa87855ca809f61d0c0037c89b52f10516886"),
        "p8": ("benchmarks/artifacts/task43/v16_p8/support/v18_paired_comparison_recovery_attempt3/comparison/v16_r9_p8_q10_samples.npz", "a3f3edca3f1f07fca79c37c1823b1616d6c330c36122ebc405d47ef2f8c20a85", "task43.v16.p8.paired-sample.v1", "cf5b88122dd2f202d93277cdc7af74ba12e412a3755b0172dbbb3b355a3b2266"),
        "point_sha256": "679fb3959e3be7f1d0179b65ff2dd21d9d1bf0f3a910a39dbb2fb7224bda3dfd",
        "weight_sha256": "9bdfb7548ed2c7c3a5dabfe6c02883118d3e15684e30ee20115cd2488e17da73",
    },
}
P5_NPZ_MEMBERS = frozenset({
    "R9_E", "R9_H8_E", "R9_H8_cell_global_ids", "R9_H8_curl_E",
    "R9_H8_point_cell_global_ids", "R9_H8_point_cell_local_slots",
    "R9_cell_global_ids", "R9_curl_E", "R9_point_cell_global_ids",
    "R9_point_cell_local_slots", "Y6_1_E", "Y6_1_cell_global_ids",
    "Y6_1_curl_E", "Y6_1_point_cell_global_ids",
    "Y6_1_point_cell_local_slots", "points_nm", "weights_nm3",
})
P8_NPZ_MEMBERS = frozenset({
    "P8_E", "P8_cell_global_ids", "P8_curl_E",
    "P8_point_cell_global_ids", "P8_point_cell_local_slots",
})


class EvidenceError(RuntimeError):
    """An input or identity gate failed; no scientific result is emitted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"expected JSON object at {path}")
    return value


def _source_path(record: dict[str, Any]) -> Path:
    raw = Path(str(record["path"]))
    if raw.is_absolute() or ".." in raw.parts:
        raise EvidenceError(f"source paths must be repo-relative and contained: {raw}")
    return REPO_ROOT / raw


def _checked_source(record: dict[str, Any]) -> Path:
    path = _source_path(record)
    relative = path.relative_to(REPO_ROOT)
    cursor = REPO_ROOT
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise EvidenceError(f"symlink in frozen source path: {cursor}")
    if not path.is_file():
        raise EvidenceError(f"missing or non-file input: {path}")
    actual = sha256_file(path)
    if actual != record.get("sha256"):
        raise EvidenceError(f"source SHA256 mismatch: {path}")
    return path


def _npy_header(stream: BinaryIO) -> tuple[tuple[int, ...], np.dtype[Any], bool]:
    try:
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, fortran_order, dtype = np.lib.format.read_array_header_1_0(stream)
        elif version == (2, 0):
            shape, fortran_order, dtype = np.lib.format.read_array_header_2_0(stream)
        else:
            raise EvidenceError(f"unsupported NPY version {version}")
    except (ValueError, EOFError, OSError) as exc:
        raise EvidenceError(f"invalid NPY member header: {exc}") from exc
    return tuple(int(x) for x in shape), np.dtype(dtype), bool(fortran_order)


def _read_npy_payload(
    archive: zipfile.ZipFile, member: str, *, retain: bool = False
) -> tuple[tuple[int, ...], np.dtype[Any], str, bytes | None]:
    digest = hashlib.sha256()
    kept = bytearray() if retain else None
    with archive.open(member, "r") as stream:
        shape, dtype, fortran_order = _npy_header(stream)
        if fortran_order or dtype.hasobject:
            raise EvidenceError(f"forbidden NPY layout/object dtype: {member}")
        digest.update(dtype.str.encode("ascii"))
        digest.update(json.dumps(list(shape)).encode("ascii"))
        count = math.prod(shape)
        remaining = count * dtype.itemsize
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise EvidenceError(f"truncated NPY payload: {member}")
            digest.update(chunk)
            if kept is not None:
                kept.extend(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            raise EvidenceError(f"trailing bytes after NPY payload: {member}")
    return shape, dtype, digest.hexdigest(), None if kept is None else bytes(kept)


def inspect_npz(
    path: Path,
    *,
    outer_sha256: str,
    expected_members: set[str],
    expected_count: int,
    expected_schema: str,
    expected_identity: dict[str, Any],
    expected_nested_identity: dict[str, Any],
    expected_record_sha256: str,
) -> dict[str, Any]:
    """Validate archive bytes, exact members, inner hashes and fixed identity."""
    actual_outer = sha256_file(path)
    if actual_outer != outer_sha256:
        raise EvidenceError(f"NPZ SHA256 mismatch: {path}")
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceError(f"invalid NPZ/ZIP {path}: {exc}") from exc
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise EvidenceError(f"duplicate ZIP members: {path}")
        expected_zip_names = {f"{name}.npy" for name in expected_members}
        expected_zip_names.add(f"{NPY_RECORD_KEY}.npy")
        if set(names) != expected_zip_names:
            raise EvidenceError(
                f"NPZ member inventory mismatch at {path}: "
                f"missing={sorted(expected_zip_names - set(names))}, "
                f"extra={sorted(set(names) - expected_zip_names)}"
            )
        record_shape, record_dtype, _, record_payload = _read_npy_payload(
            archive, f"{NPY_RECORD_KEY}.npy", retain=True
        )
        if (record_dtype != np.dtype("u1") or record_payload is None
                or record_shape != (len(record_payload),)):
            raise EvidenceError(f"embedded archive record is not uint8: {path}")
        if hashlib.sha256(record_payload).hexdigest() != expected_record_sha256:
            raise EvidenceError(f"embedded record SHA256 mismatch: {path}")
        try:
            record = json.loads(record_payload.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EvidenceError(f"invalid embedded archive JSON: {path}") from exc
        if not isinstance(record, dict) or record.get("schema") != expected_schema:
            raise EvidenceError(f"embedded schema mismatch: {path}")
        arrays = record.get("arrays")
        if not isinstance(arrays, dict) or set(arrays) != expected_members:
            raise EvidenceError(f"embedded array inventory mismatch: {path}")
        for name in sorted(expected_members):
            shape, dtype, payload_sha, _ = _read_npy_payload(archive, f"{name}.npy")
            saved = arrays[name]
            if (
                shape != tuple(saved.get("shape", ()))
                or dtype.str != saved.get("dtype")
                or payload_sha != saved.get("sha256")
            ):
                raise EvidenceError(f"inner array identity mismatch: {path}:{name}")
        identity = record.get("identity")
        if not isinstance(identity, dict):
            raise EvidenceError(f"missing archive identity: {path}")
        for key, expected in expected_identity.items():
            if identity.get(key) != expected:
                raise EvidenceError(f"archive identity mismatch {key}: {path}")
        for dotted_key, expected in expected_nested_identity.items():
            cursor: Any = identity
            for part in dotted_key.split("."):
                if not isinstance(cursor, dict) or part not in cursor:
                    raise EvidenceError(f"archive identity missing {dotted_key}: {path}")
                cursor = cursor[part]
            if cursor != expected:
                raise EvidenceError(f"archive identity mismatch {dotted_key}: {path}")
        if identity.get("sample_count") != expected_count:
            raise EvidenceError(f"sample_count mismatch: {path}")
        return record


def verify_pair_identity(
    p5_record: dict[str, Any], p8_record: dict[str, Any], p5_sha256: str,
    expected_candidate: str, expected_q: int,
) -> None:
    p5_identity = p5_record["identity"]
    p8_identity = p8_record["identity"]
    if p5_identity.get("reference_label") != "Y6_1":
        raise EvidenceError("P5 reference must remain Y6_1")
    if p8_identity.get("P5_sample_sha256") != p5_sha256:
        raise EvidenceError("P8 package is mixed with a different P5 sample archive")
    if p8_identity.get("candidate_identity", {}).get("candidate_id") != expected_candidate:
        raise EvidenceError("P8 candidate identity differs from the fixed V16 candidate")
    if p8_identity.get("P8_sampled_once") is not True:
        raise EvidenceError("P8 archive does not preserve the sampled-once identity")
    if p5_identity.get("quadrature_order") != expected_q or p8_identity.get("quadrature_order") != expected_q:
        raise EvidenceError("P5/P8 package quadrature order differs")
    if p5_identity.get("sample_count") != p8_identity.get("sample_count"):
        raise EvidenceError("P5/P8 package point counts differ")
    for name in ("points_nm", "weights_nm3"):
        expected = p5_record["arrays"][name]["sha256"]
        saved = p8_identity.get("point_identity" if name == "points_nm" else "weight_identity", {})
        if not isinstance(saved, dict) or saved.get("sha256") != expected:
            raise EvidenceError(f"P8 package is mixed with different common {name}")


def validate_owner_map(
    cell_global_ids: np.ndarray,
    point_local_slots: np.ndarray,
    point_global_ids: np.ndarray,
) -> None:
    cells = np.asarray(cell_global_ids)
    slots = np.asarray(point_local_slots)
    owners = np.asarray(point_global_ids)
    if cells.ndim != 1 or slots.ndim != 1 or owners.shape != slots.shape:
        raise EvidenceError("owner map has an invalid rank or layout")
    if cells.size == 0 or len(set(int(x) for x in cells)) != cells.size:
        raise EvidenceError("cell global ids must be nonempty and unique")
    if np.any(slots < 0) or np.any(slots >= cells.size):
        raise EvidenceError("point local slot outside cell id array")
    if not np.array_equal(np.unique(slots), np.arange(cells.size, dtype=slots.dtype)):
        raise EvidenceError("point owner map does not cover every cell exactly at least once")
    if not np.array_equal(cells[slots], owners):
        raise EvidenceError("point owner global ids disagree with local slots")


def response_terms(
    reference_error: np.ndarray,
    action_delta: np.ndarray,
    weights: np.ndarray,
    owner_slots: np.ndarray,
    cell_count: int,
) -> dict[str, np.ndarray]:
    """Return per-cell B,D,X,I and an independently accumulated after norm."""
    e = np.asarray(reference_error, dtype=np.complex128)
    d = np.asarray(action_delta, dtype=np.complex128)
    w = np.asarray(weights, dtype=np.float64)
    slots = np.asarray(owner_slots, dtype=np.int64)
    if e.shape != d.shape or e.shape[0] != w.size or w.shape != slots.shape:
        raise ValueError("response values, weights and owner slots must align")
    if e.ndim not in (1, 2) or np.any(slots < 0) or np.any(slots >= cell_count):
        raise ValueError("invalid response layout or cell owner")
    if not all(np.isfinite(x).all() for x in (e, d, w)) or np.any(w <= 0.0):
        raise ValueError("response input contains nonfinite values or nonpositive weights")
    if e.ndim == 1:
        e = e[:, None]
        d = d[:, None]
    before_density = np.sum(np.abs(e) ** 2, axis=1)
    action_density = np.sum(np.abs(d) ** 2, axis=1)
    cross_density = 2.0 * np.real(np.sum(np.conjugate(e) * d, axis=1))
    after_density = np.sum(np.abs(e - d) ** 2, axis=1)
    b = np.bincount(slots, weights=w * before_density, minlength=cell_count)
    action = np.bincount(slots, weights=w * action_density, minlength=cell_count)
    cross = np.bincount(slots, weights=w * cross_density, minlength=cell_count)
    after = np.bincount(slots, weights=w * after_density, minlength=cell_count)
    return {
        "B": b,
        "D": action,
        "X": cross,
        "I": cross - action,
        "after_error_squared": after,
        "I_independent": b - after,
        "identity_error": (cross - action) - (b - after),
    }


def amplitude_square_delta(reference: complex, delta: complex) -> dict[str, float]:
    """Algebra for |a+da|^2-|a|^2; this is not a physical-power conversion."""
    a = complex(reference)
    da = complex(delta)
    if not all(math.isfinite(v) for v in (a.real, a.imag, da.real, da.imag)):
        raise ValueError("amplitude must be finite")
    interference = 2.0 * (a.conjugate() * da).real
    quadratic = abs(da) ** 2
    return {
        "interference_amplitude_squared": interference,
        "delta_amplitude_squared": quadratic,
        "amplitude_squared_change": interference + quadratic,
        "independent_amplitude_squared_change": abs(a + da) ** 2 - abs(a) ** 2,
        "identity_error": interference + quadratic - (abs(a + da) ** 2 - abs(a) ** 2),
    }


def modal_key(row: dict[str, Any]) -> tuple[str, int, int, str]:
    return (str(row["side"]), int(row["order_m"]), int(row["order_n"]), str(row["polarization"]))


def modal_inventory(rows: list[dict[str, Any]]) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    values: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for row in rows:
        key = modal_key(row)
        if key in values:
            raise EvidenceError(f"duplicate modal key: {key}")
        if key not in CHANNEL_KEYS:
            raise EvidenceError(f"unexpected modal key: {key}")
        for field in ("outgoing_amplitude_at_boundary", "outgoing_amplitude"):
            pair = row.get(field)
            if not isinstance(pair, list) or len(pair) != 2 or not all(
                isinstance(v, (int, float)) and math.isfinite(float(v)) for v in pair
            ):
                raise EvidenceError(f"invalid complex modal field {field} for {key}")
        for field in ("power_ratio", "modal_power_code_units", "R", "T"):
            if not isinstance(row.get(field), (int, float)) or not math.isfinite(float(row[field])):
                raise EvidenceError(f"invalid modal power field {field} for {key}")
        values[key] = row
    if set(values) != set(CHANNEL_KEYS):
        missing = sorted(set(CHANNEL_KEYS) - set(values))
        raise EvidenceError(f"modal inventory is not the exact 612-channel set; missing={missing[:4]}")
    counts: dict[tuple[str, str], int] = {}
    for side, _, _, pol in values:
        counts[(side, pol)] = counts.get((side, pol), 0) + 1
    if counts != {(s, p): 153 for s in ("top", "bottom") for p in ("s", "p")}:
        raise EvidenceError("modal inventory must contain 153 modes per side/polarization")
    return values


def _complex_pair(row: dict[str, Any], field: str) -> complex:
    pair = row[field]
    return complex(float(pair[0]), float(pair[1]))


def _close(actual: float, expected: float, label: str) -> dict[str, float]:
    if not math.isfinite(float(actual)) or not math.isfinite(float(expected)):
        raise EvidenceError(f"nonfinite scalar replay {label}")
    absolute = abs(float(actual) - float(expected))
    relative = absolute / max(abs(float(expected)), 1.0e-300)
    if absolute > max(REPLAY_ATOL, REPLAY_RTOL * abs(float(expected))):
        raise EvidenceError(
            f"saved scalar replay mismatch {label}: actual={actual!r}, expected={expected!r}"
        )
    return {"absolute_error": absolute, "relative_error": relative}


def _read_proc_stat(pid: int) -> tuple[int, int, str]:
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    close = raw.rfind(")")
    if close < 0:
        raise EvidenceError(f"invalid /proc/{pid}/stat")
    fields = raw[close + 2 :].split()
    return int(fields[1]), int(fields[19]), fields[0]


def _proc_record(pid: int) -> dict[str, Any]:
    ppid, start_ticks, state = _read_proc_stat(pid)
    cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    return {"pid": pid, "ppid": ppid, "start_ticks": start_ticks,
            "state": state, "cmdline": cmdline[:500]}


def _proc_chain(pid: int, limit: int = 16) -> list[dict[str, Any]]:
    chain = []
    cursor = pid
    for _ in range(limit):
        if cursor <= 1:
            break
        record = _proc_record(cursor)
        chain.append(record)
        cursor = int(record["ppid"])
    return chain


def runtime_identity() -> dict[str, Any]:
    pid = os.getpid()
    ppid, start_ticks, state = _read_proc_stat(pid)
    status = Path(f"/proc/{pid}/status").read_text(encoding="ascii")
    tracer_line = next((line for line in status.splitlines() if line.startswith("TracerPid:")), None)
    swap_line = next((line for line in status.splitlines() if line.startswith("VmSwap:")), None)
    if tracer_line is None or swap_line is None:
        raise EvidenceError("/proc status lacks TracerPid or VmSwap")
    tracer_pid = int(tracer_line.split()[1])
    task_swap_kib = int(swap_line.split()[1])
    expected_watchdog = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    phase_raw = os.environ.get("PHYSICAL_WATCHDOG_PHASE_PATH", "")
    stage = os.environ.get("TASK43_V19_STAGE", "")
    root_raw = os.environ.get("TASK43_V19_RUN_ROOT", "")
    activation_marker = os.environ.get("_MYFENICS_NATIVE_QUALIFIED_ACTIVATION")
    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    qualified_venv = os.environ.get("TASK40_SHARED_VENV_ROOT", "")
    if expected_watchdog <= 0 or not phase_raw:
        raise EvidenceError("watchdog identity environment is missing")
    if stage not in ("T1", "T2", "D1", "D2") or not root_raw:
        raise EvidenceError("V19 stage or unique run-root environment is missing")
    if activation_marker != "1" or not virtual_env or virtual_env != qualified_venv:
        raise EvidenceError("qualified activation marker/venv identity is missing")
    root = Path(root_raw)
    expected_phase = root / "watchdog" / "workflow_phase.json"
    phase = Path(phase_raw)
    if not phase.is_absolute() or phase.resolve(strict=False) != expected_phase.resolve(strict=False):
        raise EvidenceError("watchdog phase path does not match this unique V19 root")
    ancestors = _proc_chain(ppid)
    watchdog_record = _proc_record(expected_watchdog)
    watchdog_start_ticks = int(watchdog_record["start_ticks"])
    direct_watchdog = (
        ppid == expected_watchdog
        and "benchmarks.subreaper_watchdog" in watchdog_record["cmdline"]
    )
    tracer_record = _proc_record(tracer_pid) if tracer_pid > 0 else None
    tracer_chain = _proc_chain(int(tracer_record["ppid"])) if tracer_record else []
    tracer_owned_by_watchdog = bool(
        tracer_record
        and (
            int(tracer_record["ppid"]) == expected_watchdog
            or any(int(parent["pid"]) == expected_watchdog for parent in tracer_chain)
        )
    )
    task_records = []
    task_dir = Path(f"/proc/{pid}/task")
    for entry in sorted(task_dir.iterdir(), key=lambda item: int(item.name)):
        tid = int(entry.name)
        _, tid_start, tid_state = _read_proc_stat(tid)
        tid_affinity = sorted(os.sched_getaffinity(tid))
        task_records.append({"tid": tid, "start_ticks": tid_start,
                             "state": tid_state, "cpu_affinity": tid_affinity})
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []
    threads = {key: os.environ.get(key) for key in THREAD_KEYS}
    identity = {
        "pid": pid, "ppid": ppid, "start_ticks": start_ticks, "state": state,
        "tracer_pid": tracer_pid, "tracer": tracer_record,
        "tracer_ancestor_chain": tracer_chain,
        "tracer_owned_by_watchdog": tracer_owned_by_watchdog,
        "watchdog_pid": expected_watchdog, "watchdog_start_ticks": watchdog_start_ticks,
        "watchdog": watchdog_record,
        "watchdog_is_direct_parent": direct_watchdog,
        "watchdog_phase_path": phase_raw,
        "ancestors": ancestors, "cpu_affinity": affinity,
        "threads": task_records,
        "thread_environment": threads, "task_vmswap_kib": task_swap_kib,
        "python": sys.executable, "numpy": np.__version__,
        "stage": stage, "run_root": str(root.resolve(strict=True)),
        "activation_marker": activation_marker,
        "virtual_env": virtual_env, "qualified_venv": qualified_venv,
    }
    if not direct_watchdog or not tracer_owned_by_watchdog or tracer_pid <= 0 or affinity != [1]:
        raise EvidenceError("runtime parent, tracer, or CPU affinity gate failed")
    if any(value != "1" for value in threads.values()) or task_swap_kib != 0 or any(
        item["cpu_affinity"] != [1] for item in task_records
    ):
        raise EvidenceError("runtime thread or task-swap gate failed")
    return identity


def write_runtime_identity(stage: str, moment: str) -> Path:
    """Persist the current checker/pytest worker identity under its unique root."""
    if stage not in ("T1", "T2", "D1", "D2") or moment not in ("start", "end"):
        raise EvidenceError("invalid runtime identity stage or moment")
    if os.environ.get("TASK43_V19_STAGE") != stage:
        raise EvidenceError("runtime stage does not match TASK43_V19_STAGE")
    root_raw = os.environ.get("TASK43_V19_RUN_ROOT", "")
    if not root_raw:
        raise EvidenceError("TASK43_V19_RUN_ROOT is missing")
    root = Path(root_raw)
    if root.is_symlink() or not root.is_dir():
        raise EvidenceError("runtime identity root must be an existing nonsymlink directory")
    target = root / f"runtime_{moment}.json"
    if target.exists() or target.is_symlink():
        raise EvidenceError(f"refusing to overwrite runtime identity: {target}")
    identity = runtime_identity()
    if moment == "end":
        start_path = root / "runtime_start.json"
        if start_path.is_symlink() or not start_path.is_file():
            raise EvidenceError("runtime start identity is missing before end record")
        start = _json_file(start_path).get("identity", {})
        for key in ("pid", "start_ticks", "ppid", "watchdog_pid", "watchdog_start_ticks",
                    "tracer_pid"):
            if start.get(key) != identity.get(key):
                raise EvidenceError(f"runtime identity changed during stage: {key}")
        for key in ("pid", "start_ticks", "ppid"):
            if (start.get("tracer") or {}).get(key) != (identity.get("tracer") or {}).get(key):
                raise EvidenceError(f"tracer identity changed during stage: {key}")
        if start.get("watchdog", {}).get("cmdline") != identity.get("watchdog", {}).get("cmdline"):
            raise EvidenceError("watchdog command identity changed during stage")
        if start.get("activation_marker") != identity.get("activation_marker"):
            raise EvidenceError("activation marker changed during stage")
    record = {
        "schema": "task43.v19.runtime_identity.v1", "stage": stage,
        "moment": moment, "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "identity": identity,
    }
    atomic_json(target, record)
    atomic_json(Path(identity["watchdog_phase_path"]), {"stage": stage, "moment": moment, "worker_pid": identity["pid"], "worker_start_ticks": identity["start_ticks"], "status": "WORKER_ACTIVE" if moment == "start" else "WORKER_FINISHED_PENDING_ROOT_AUDIT"})
    return target


def atomic_json(path: Path, value: Any) -> str:
    tmp = path.with_name(path.name + ".tmp")
    try:
        payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
        with tmp.open("x", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return sha256_file(path)


def atomic_csv(path: Path, header: list[str], rows: list[dict[str, Any]]) -> str:
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=header, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    return sha256_file(path)


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"manifest missing or symlinked: {path}")
    expected_path = REPO_ROOT / CONTRACT_RELATIVE_PATH
    if path.resolve(strict=True) != expected_path.resolve(strict=True):
        raise EvidenceError(f"V19 checker accepts only the fixed contract path: {expected_path}")
    manifest = _json_file(path)
    if manifest.get("schema") != CONTRACT_SCHEMA:
        raise EvidenceError("unsupported V19 contract schema")
    _validate_contract(manifest)
    execution = manifest.get("execution")
    if not isinstance(execution, dict) or not isinstance(execution.get("slots"), dict):
        raise EvidenceError("V19 contract lacks execution.slots")
    return manifest, sha256_file(path)


def _validate_contract(manifest: dict[str, Any]) -> None:
    authorization = manifest.get("authorization")
    if not isinstance(authorization, dict) or authorization.get("new_formal_pde") != 0:
        raise EvidenceError("V19 contract cannot authorize a new PDE")
    if any(authorization.get(key) is not False for key in (
        "sample_or_restore", "matrix_assembly", "operator_application", "dual_solve",
        "field_recovery", "new_quadrature_sampling", "future_automatic_runs",
    )):
        raise EvidenceError("V19 contract authorizes an excluded operation")
    if authorization.get("review_section") != "review_report_v18.md#9":
        raise EvidenceError("V19 authorization does not point to the fixed review scope")
    source_records = manifest.get("sources")
    if not isinstance(source_records, dict) or set(source_records) != EXPECTED_SOURCE_ROLES:
        raise EvidenceError("V19 source role inventory is not the exact 13-file set")
    for role, (path, digest) in EXPECTED_SOURCES.items():
        record = source_records[role]
        if not isinstance(record, dict) or (record.get("path"), record.get("sha256")) != (path, digest):
            raise EvidenceError(f"V19 frozen source binding differs for {role}")
    tests = manifest.get("tests")
    if not isinstance(tests, dict) or tests.get("selectors") != EXPECTED_T1_SELECTORS:
        raise EvidenceError("T1 test selector list differs from the fixed 12-node batch")
    if tests.get("recovery_selectors") != []:
        raise EvidenceError("T2 recovery selectors must remain empty until a local bug is diagnosed")
    if tests.get("max_initial_nodes") != 12 or tests.get("max_recovery_nodes") != 6:
        raise EvidenceError("V19 test batch limits differ from the review")
    if tests.get("collection_only") is not False:
        raise EvidenceError("collect-only is not an authorized V19 test mode")
    physics = manifest.get("physics")
    expected_physics = {
        "case": "phi90_periodic_3d_maxwell_grating",
        "geometry_nm": {"period": [50.0, 50.0], "height": 140.0},
        "wavelength_nm": 13.5, "phi_deg": 90.0,
        "parent": "accepted9/R9", "reference": "Y6_1",
        "actions": ["H8", "P8"], "modal_inventory": {"order": 13, "count": 612},
        "quadrature": {"operator": 15, "incident_port": 28, "field_comparison": [8, 10]},
        "normal_corrections": 1, "extra_corrections": 0,
        "k0_per_nm": 0.46542113386515455,
        "magnetic_field_scale_a_per_m": 0.002654418727984993,
        "mu_r": [1.0, 0.0], "volume_nm3": VOLUME_NM3,
        "g_identity_relative_tolerance": G_IDENTITY_TOL,
        "cell_groups": {
            "requested": {"forest_root_id": 4, "global_cell_id": 8,
                          "lower": [16.5, 5.0, -10.0], "upper": [33.5, 10.0, 0.0]},
            "closure": {"forest_root_id": 34, "global_cell_id": None,
                        "lower": [16.5, 5.0, 0.0], "upper": [33.5, 10.0, 30.0]},
        },
    }
    if physics != expected_physics:
        raise EvidenceError("V19 physics/owner/quadrature identity differs from the fixed review scope")
    archives = manifest.get("quadrature_archives")
    if not isinstance(archives, dict) or set(archives) != set(EXPECTED_ARCHIVE_BINDINGS):
        raise EvidenceError("V19 contract must contain exactly the q8 and q10 archive pairs")
    for q, binding in EXPECTED_ARCHIVE_BINDINGS.items():
        rec = archives[q]
        if not isinstance(rec, dict) or int(rec.get("sample_count", -1)) != binding["sample_count"]:
            raise EvidenceError(f"wrong {q} sample count in contract")
        if set(rec.get("p5_members", [])) != P5_NPZ_MEMBERS or set(rec.get("p8_members", [])) != P8_NPZ_MEMBERS:
            raise EvidenceError(f"wrong {q} exact NPZ member inventory in contract")
        for role in ("p5", "p8"):
            expected = binding[role]
            entry = rec.get(role)
            if not isinstance(entry, dict) or (
                entry.get("path"), entry.get("sha256"), entry.get("schema"),
                entry.get("embedded_record_sha256"),
            ) != expected:
                raise EvidenceError(f"{q} {role} archive binding differs from the review")
        p5, p8 = rec["p5"], rec["p8"]
        if p5.get("identity", {}).get("quadrature_order") != int(q.removeprefix("q")):
            raise EvidenceError(f"{q} P5 archive identity has a wrong quadrature order")
        if p8.get("identity", {}).get("quadrature_order") != int(q.removeprefix("q")):
            raise EvidenceError(f"{q} P8 archive identity has a wrong quadrature order")
        if p5.get("identity", {}).get("reference_label") != "Y6_1":
            raise EvidenceError(f"{q} P5 archive identity does not use Y6_1")
        if p8.get("identity", {}).get("P5_sample_sha256") != p5["sha256"]:
            raise EvidenceError(f"{q} P8 archive contract mixes a different P5 archive")
        if p8.get("nested_identity", {}).get("candidate_identity.candidate_id") != "v16_r9_p8":
            raise EvidenceError(f"{q} P8 archive contract candidate identity is missing")
        if p8.get("nested_identity", {}).get("point_identity.sha256") != binding["point_sha256"]:
            raise EvidenceError(f"{q} P8 archive contract point identity is wrong")
        if p8.get("nested_identity", {}).get("weight_identity.sha256") != binding["weight_sha256"]:
            raise EvidenceError(f"{q} P8 archive contract weight identity is wrong")
    slots = manifest["execution"]["slots"]
    if set(slots) != set(EXPECTED_STAGE_ROOTS):
        raise EvidenceError("V19 execution slots are not exactly T1/T2/D1/D2")
    expected_limits = {"T1": (270, 300, True), "T2": (270, 300, False),
                       "D1": (1140, 1200, True), "D2": (1140, 1200, True)}
    for stage, root in EXPECTED_STAGE_ROOTS.items():
        slot = slots[stage]
        work, whole, armed = expected_limits[stage]
        output = "." if stage.startswith("T") else "data"
        if not isinstance(slot, dict) or (
            slot.get("root"), slot.get("output_subdir"), slot.get("work_seconds"),
            slot.get("whole_seconds"), slot.get("rss_limit_bytes"), slot.get("cpu_affinity"),
            slot.get("mpi_processes"), slot.get("threads"), slot.get("armed"),
        ) != (root, output, work, whole, 8589934592, [1], 0, 1, armed):
            raise EvidenceError(f"V19 execution slot differs from its fixed review budget: {stage}")


def _slot_for_stage(manifest: dict[str, Any], stage: str) -> dict[str, Any]:
    slots = manifest.get("execution", {}).get("slots", {})
    slot = slots.get(stage)
    if not isinstance(slot, dict):
        raise EvidenceError(f"V19 contract has no execution slot for {stage}")
    if slot.get("armed") is not True:
        raise EvidenceError(f"V19 stage {stage} has not been armed by its frozen contract")
    rel_root = Path(str(slot.get("root", "")))
    if rel_root.is_absolute() or ".." in rel_root.parts or not rel_root.parts:
        raise EvidenceError(f"invalid repo-relative execution root for {stage}")
    expected_root = REPO_ROOT / rel_root
    run_root = Path(os.environ.get("TASK43_V19_RUN_ROOT", ""))
    if not run_root.is_absolute() or run_root.resolve(strict=False) != expected_root.resolve(strict=False):
        raise EvidenceError(f"runtime root does not match frozen {stage} slot")
    output_subdir = Path(str(slot.get("output_subdir", "")))
    if output_subdir.is_absolute() or ".." in output_subdir.parts:
        raise EvidenceError(f"invalid output subdirectory for {stage}")
    expected_limits = {
        "T1": (270, 300), "T2": (270, 300),
        "D1": (1140, 1200), "D2": (1140, 1200),
    }
    if stage not in expected_limits or (
        int(slot.get("work_seconds", -1)), int(slot.get("whole_seconds", -1))
    ) != expected_limits[stage]:
        raise EvidenceError(f"execution limits differ from the fixed {stage} authorization")
    if int(slot.get("rss_limit_bytes", -1)) != 8589934592:
        raise EvidenceError(f"RSS limit differs from the fixed 8 GiB {stage} authorization")
    if slot.get("cpu_affinity") != [1] or int(slot.get("mpi_processes", -1)) != 0 or int(slot.get("threads", -1)) != 1:
        raise EvidenceError(f"CPU/MPI/thread constraints differ for {stage}")
    return slot


def _input_paths_and_hashes(
    manifest: dict[str, Any], source_paths: dict[str, Path]
) -> tuple[dict[str, Path], dict[str, str]]:
    paths = dict(source_paths)
    for q, record in manifest["quadrature_archives"].items():
        if q not in ("q8", "q10") or not isinstance(record, dict):
            raise EvidenceError("quadrature archive contract must contain only q8 and q10")
        for role in ("p5", "p8"):
            archive_record = record[role]
            key = f"quadrature.{q}.{role}"
            paths[key] = _checked_source(archive_record)
    return paths, {role: sha256_file(path) for role, path in paths.items()}


def _load_json_source(sources: dict[str, Any], role: str) -> tuple[dict[str, Any], Path]:
    record = sources[role]
    path = _checked_source(record)
    return _json_file(path), path


def _verify_sources(manifest: dict[str, Any]) -> dict[str, Path]:
    result = {}
    for role, record in manifest["sources"].items():
        result[role] = _checked_source(record)
    return result


def _load_modal(path: Path) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    modal = _json_file(path)
    rows = modal.get("orders")
    if not isinstance(rows, list):
        raise EvidenceError(f"modal JSON lacks orders: {path}")
    return modal_inventory(rows)


def _load_npz_arrays(path: Path, names: set[str]) -> dict[str, np.ndarray]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != names | {NPY_RECORD_KEY}:
                raise EvidenceError(f"loaded NPZ members changed after validation: {path}")
            arrays = {name: np.asarray(archive[name]) for name in names}
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise EvidenceError(f"cannot load NPZ arrays {path}: {exc}") from exc
    for name, array in arrays.items():
        if array.dtype.kind in "fc" and not np.isfinite(array).all():
            raise EvidenceError(f"nonfinite values in {path}:{name}")
        array.flags.writeable = False
    return arrays


def _plan_boxes(path: Path, expected_sha: str) -> list[dict[str, Any]]:
    if sha256_file(path) != expected_sha:
        raise EvidenceError(f"plan SHA256 mismatch: {path}")
    value = _json_file(path)
    boxes = value.get("cell_interior_degrees")
    if not isinstance(boxes, list):
        raise EvidenceError(f"plan lacks cell_interior_degrees: {path}")
    for row in boxes:
        if not isinstance(row, dict) or len(row.get("lower", [])) != 3 or len(row.get("upper", [])) != 3:
            raise EvidenceError(f"invalid cell box in plan: {path}")
    return boxes


def _boxes_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(
        abs(float(left[side][i]) - float(right[side][i])) <= 1.0e-12
        for side in ("lower", "upper") for i in range(3)
    )


def _cell_groups(
    r9_boxes: list[dict[str, Any]], h8_boxes: list[dict[str, Any]],
    expected_ids: list[int], root_targets: dict[str, dict[str, list[float]]],
) -> dict[int, str]:
    if len(r9_boxes) != 180 or len(expected_ids) != 180:
        raise EvidenceError("R9 base mesh must map exactly 180 cells")
    groups: dict[int, str] = {}
    target_index: dict[str, int] = {}
    if set(root_targets) != {"requested", "closure"}:
        raise EvidenceError("cell group contract must name only requested and closure boxes")
    for name, target in root_targets.items():
        box = {"lower": target["lower"], "upper": target["upper"]}
        matches = [i for i, row in enumerate(r9_boxes)
                   if _boxes_equal(row, box)]
        if len(matches) != 1:
            raise EvidenceError(f"root target {name} does not resolve to one R9 global cell")
        actual_global_id = expected_ids[matches[0]]
        if target.get("global_cell_id") is not None and int(target["global_cell_id"]) != actual_global_id:
            raise EvidenceError(f"root target {name} global cell ID/box mismatch")
        expected_forest_root = {"requested": 4, "closure": 34}[name]
        if int(target.get("forest_root_id", -1)) != expected_forest_root:
            raise EvidenceError(f"root target {name} forest-root identity differs from frozen Task43 mapping")
        if name == "requested" and actual_global_id != 8:
            raise EvidenceError(f"root target {name} is not the frozen global cell")
        target_index[name] = actual_global_id
    for local_index, global_id in enumerate(expected_ids):
        groups[global_id] = (
            "requested_root4_global8" if global_id == target_index["requested"] else
            "H8_required_closure_root34" if global_id == target_index["closure"] else
            "rest_of_domain"
        )
    for name in ("requested", "closure"):
        box = {"lower": root_targets[name]["lower"], "upper": root_targets[name]["upper"]}
        contained = [row for row in h8_boxes if all(
            float(row["lower"][i]) >= float(box["lower"][i]) - 1.0e-12
            and float(row["upper"][i]) <= float(box["upper"][i]) + 1.0e-12
            for i in range(3)
        )]
        if len(contained) != 8:
            raise EvidenceError(f"H8 box {name} must have exactly eight child cells")
    return groups


def order_plan_boxes_from_saved_owners(
    points: np.ndarray, cell_ids: np.ndarray, slots: np.ndarray,
    owners: np.ndarray, plan_boxes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match saved FE owners to geometric plan rows, never equate their indices."""
    validate_owner_map(cell_ids, slots, owners)
    count = len(cell_ids)
    if len(plan_boxes) != count or points.shape != (len(slots), 3):
        raise EvidenceError("saved owner/plan geometry layouts differ")
    low = np.full((count, 3), np.inf)
    high = np.full((count, 3), -np.inf)
    for axis in range(3):
        np.minimum.at(low[:, axis], slots, points[:, axis])
        np.maximum.at(high[:, axis], slots, points[:, axis])
    selected = []
    for cell in range(count):
        matches = [i for i, box in enumerate(plan_boxes)
                   if all(low[cell, a] >= float(box["lower"][a]) - 1e-12
                          and high[cell, a] <= float(box["upper"][a]) + 1e-12
                          for a in range(3))]
        if len(matches) != 1:
            raise EvidenceError("saved owner points do not select a unique frozen plan box")
        selected.append(matches[0])
    if len(set(selected)) != count:
        raise EvidenceError("saved owner to frozen plan mapping is not bijective")
    return [plan_boxes[i] for i in selected]


def validate_points_against_r9_boxes(
    points_nm: np.ndarray, cell_ids: np.ndarray, owner_slots: np.ndarray,
    owner_global_ids: np.ndarray, boxes: list[dict[str, Any]],
) -> None:
    """Check saved owner ids and every saved point against the ordered R9 boxes."""
    ids = np.asarray(cell_ids)
    slots = np.asarray(owner_slots)
    owners = np.asarray(owner_global_ids)
    points = np.asarray(points_nm)
    if len(boxes) != ids.size or points.shape != (slots.size, 3) or owners.shape != slots.shape:
        raise EvidenceError("R9 point/owner/box layouts do not align")
    if not np.array_equal(ids, np.arange(ids.size, dtype=ids.dtype)):
        raise EvidenceError("R9 cell IDs are not in the saved plan row order")
    if not np.array_equal(ids[slots], owners):
        raise EvidenceError("R9 owner global IDs do not match their local slots")
    lower = np.asarray([row["lower"] for row in boxes], dtype=np.float64)
    upper = np.asarray([row["upper"] for row in boxes], dtype=np.float64)
    for start in range(0, points.shape[0], 65536):
        end = min(start + 65536, points.shape[0])
        local = slots[start:end]
        chunk = points[start:end]
        if not np.all(chunk >= lower[local] - 1.0e-12) or not np.all(chunk <= upper[local] + 1.0e-12):
            raise EvidenceError("saved quadrature point lies outside its recorded R9 owner box")


def _accumulate_component(
    reference_error: np.ndarray,
    action_delta: np.ndarray,
    weights: np.ndarray,
    slots: np.ndarray,
    cell_count: int,
    scale: float,
) -> dict[str, np.ndarray]:
    # Chunk the pointwise temporaries; input NPZ arrays remain read-only.
    out = {name: np.zeros(cell_count, dtype=np.float64)
           for name in ("B", "D", "X", "after_error_squared")}
    for start in range(0, len(weights), 32768):
        end = min(start + 32768, len(weights))
        e = np.asarray(reference_error[start:end]) * scale
        d = np.asarray(action_delta[start:end]) * scale
        w = weights[start:end]
        owner = slots[start:end]
        partial = response_terms(e, d, w, owner, cell_count)
        for name in out:
            out[name] += partial[name]
    out["I"] = out["X"] - out["D"]
    out["I_independent"] = out["B"] - out["after_error_squared"]
    out["identity_error"] = out["I"] - out["I_independent"]
    return out


def _g_terms_for_action(
    p5: dict[str, np.ndarray], action_e: np.ndarray, action_curl: np.ndarray,
    k0: float, cell_count: int,
) -> dict[str, Any]:
    slots = p5["R9_point_cell_local_slots"]
    e = p5["Y6_1_E"] - p5["R9_E"]
    d_e = action_e - p5["R9_E"]
    curl_e = (p5["Y6_1_curl_E"] - p5["R9_curl_E"]) / k0
    curl_d = (action_curl - p5["R9_curl_E"]) / k0
    reference_g = _accumulate_component(e, d_e, p5["weights_nm3"], slots, cell_count, 1.0)
    curl_g = _accumulate_component(curl_e, curl_d, p5["weights_nm3"], slots, cell_count, 1.0)
    total = {}
    for key in reference_g:
        total[key] = reference_g[key] + curl_g[key]
    return {"E": reference_g, "curl_over_k0": curl_g, "G": total}


def _norm(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sqrt(np.dot(weights, np.sum(np.abs(values) ** 2, axis=1))))


def _field_replay(
    p5: dict[str, np.ndarray], action_e: np.ndarray, action_curl: np.ndarray,
    comparison_case: dict[str, Any], k0: float, h_scale: float,
    incident_g_floor: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    w = p5["weights_nm3"]
    ref_e = p5["Y6_1_E"]
    ref_curl = p5["Y6_1_curl_E"]
    e_delta = action_e - ref_e
    curl_delta = (action_curl - ref_curl) / k0
    curl_metric = _norm(curl_delta, w)
    g_delta = float(np.sqrt(np.dot(w, np.sum(np.abs(e_delta) ** 2 + np.abs(curl_delta) ** 2, axis=1))))
    g_ref = float(np.sqrt(np.dot(w, np.sum(np.abs(ref_e) ** 2 + np.abs(ref_curl / k0) ** 2, axis=1))))
    h_delta = h_scale * _norm(curl_delta, w)
    e_delta_norm = _norm(e_delta, w)
    raw_norms = {
        "E_total_code": e_delta_norm,
        "E_scattered_code": e_delta_norm,
        "curl_E_over_k0_code": curl_metric,
        "H_total_A_per_m": h_delta,
        "H_scattered_A_per_m": h_delta,
        "G": g_delta,
    }
    replay = {}
    ratios = {}
    for name, metric in raw_norms.items():
        saved = comparison_case["field_metrics"][name]
        key = "difference_g_norm" if name == "G" else "difference_l2"
        saved_value = float(saved[key])
        replay[name] = _close(metric, saved_value, f"{name}.difference")
        if name == "G":
            denominator = max(float(saved["reference_g_norm"]), float(saved["incident_g_norm_floor"]))
        else:
            denominator = max(float(saved["reference_l2"]), float(saved["reference_norm_floor"]))
        ratios[name] = metric / denominator if denominator > 0 else None
        if ratios[name] is None:
            raise EvidenceError(f"zero field normalization denominator for {name}")
        saved_ratio = float(
            saved["relative_with_incident_floor"] if name == "G"
            else saved["relative_to_reference_or_floor"]
        )
        replay[f"{name}.relative"] = _close(ratios[name], saved_ratio, f"{name}.relative")
    replay["G.reference_norm"] = _close(g_ref, float(comparison_case["field_metrics"]["G"]["reference_g_norm"]), "G.reference_norm")
    direct_reference_norms = {
        "E_total_code": _norm(ref_e, w),
        "curl_E_over_k0_code": _norm(ref_curl / k0, w),
        "H_total_A_per_m": h_scale * _norm(ref_curl / k0, w),
    }
    for name, actual in direct_reference_norms.items():
        replay[f"{name}.reference_norm"] = _close(
            actual, float(comparison_case["field_metrics"][name]["reference_l2"]),
            f"{name}.reference_norm",
        )
    return ratios, {"replay_errors": replay, "difference_norms": raw_norms,
                    "reference_norms_recomputed": direct_reference_norms,
                    "scattered_reference_norms": "REUSED_FROM_HASH_BOUND_COMPARISON",
                    "reference_G_norm": g_ref, "H_scale_A_per_m": h_scale}


def _modal_aggregate(
    modal: dict[tuple[str, int, int, str], dict[str, Any]],
    absorption: float,
) -> dict[str, float]:
    top = [row for (side, _, _, _), row in modal.items() if side == "top"]
    bottom = [row for (side, _, _, _), row in modal.items() if side == "bottom"]
    zero_s = modal[("top", 0, 0, "s")]
    zero_p = modal[("top", 0, 0, "p")]
    return {
        "R_total": math.fsum(float(row["R"]) for row in top),
        "T_total": math.fsum(float(row["T"]) for row in bottom),
        "R00_s": float(zero_s["R"]), "R00_p": float(zero_p["R"]),
        "R00_total": float(zero_s["R"]) + float(zero_p["R"]),
        "A_volume": float(absorption),
    }


def _absorption(path: Path, reference: bool = False) -> float:
    record = _json_file(path)
    if reference:
        value = record.get("official_result", {}).get("volume_metrics", {}).get("A_volume_total")
    else:
        value = record.get("A_volume_total")
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise EvidenceError(f"missing finite saved A_volume in {path}")
    return float(value)


def _component_scale(key: str, value: float) -> float:
    if key.startswith("power."):
        tolerance = J_POWER_TOLERANCES[key.removeprefix("power.")]
    elif key.startswith("amplitude."):
        tolerance = J_AMPLITUDE_TOLERANCE
    else:
        tolerance = 1.0e-4
    return abs(float(value)) / tolerance


def _replay_j(
    p5: dict[str, np.ndarray], action_e: np.ndarray, action_curl: np.ndarray,
    action_modal: dict[tuple[str, int, int, str], dict[str, Any]],
    reference_modal: dict[tuple[str, int, int, str], dict[str, Any]],
    action_abs: float, reference_abs: float, comparison_case: dict[str, Any],
    reference_power: dict[str, Any], field_ratios: dict[str, float],
) -> dict[str, Any]:
    action_power = _modal_aggregate(action_modal, action_abs)
    ref_power = _modal_aggregate(reference_modal, reference_abs)
    channel_diffs = {
        key: float(action_modal[key]["power_ratio"]) - float(reference_modal[key]["power_ratio"])
        for key in CHANNEL_KEYS
    }
    saved_power_delta = {
        key: float(value) for key, value in comparison_case["signed_observables"]
        ["aggregate_signed_candidate_minus_reference"].items()
    }
    if set(saved_power_delta) != set(action_power):
        raise EvidenceError("saved aggregate power inventory differs from the fixed J observables")
    direct_power_delta = {key: action_power[key] - ref_power[key] for key in action_power}
    direct_aggregate_replay = {
        key: _close(direct_power_delta[key], saved_power_delta[key], f"modal_sum.{key}")
        for key in direct_power_delta
    }
    power_delta = saved_power_delta
    components = {
        f"power.{key}": _component_scale(f"power.{key}", value)
        for key, value in power_delta.items()
    }
    components["power.max_individual_channel"] = max(abs(v) for v in channel_diffs.values()) / J_CHANNEL_POWER_TOLERANCE
    groups: dict[str, list[float]] = {}
    for key in CHANNEL_KEYS:
        side, _, _, pol = key
        amp_delta = _complex_pair(action_modal[key], "outgoing_amplitude_at_boundary") - _complex_pair(reference_modal[key], "outgoing_amplitude_at_boundary")
        groups.setdefault(f"{side}_{pol}", []).append(abs(amp_delta) ** 2)
    for group, squared in groups.items():
        components[f"amplitude.{group}"] = math.sqrt(math.fsum(squared)) / J_AMPLITUDE_TOLERANCE
    field_to_j = {
        "E_total_code": "field.E_total_code",
        "E_scattered_code": "field.E_scattered_code",
        "H_total_A_per_m": "field.H_total_A_per_m",
        "H_scattered_A_per_m": "field.H_scattered_A_per_m",
        "G": "field.G",
    }
    for metric, output_key in field_to_j.items():
        components[output_key] = float(field_ratios[metric]) / 1.0e-4
    saved_components = comparison_case["J_infinity"]["components"]
    if set(components) != set(saved_components):
        raise EvidenceError("recomputed J component inventory differs from saved comparison")
    replay = {key: _close(components[key], float(saved_components[key]), f"J.{key}") for key in components}
    witness = max(components, key=components.__getitem__)
    saved_j = comparison_case["J_infinity"]
    if witness != saved_j["witness"]:
        raise EvidenceError("recomputed J witness differs from saved comparison")
    _close(components[witness], float(saved_j["value"]), "J.value")
    return {
        "components": components,
        "value": components[witness],
        "witness": witness,
        "replay_errors": replay,
        "power_observables_from_hash_bound_comparison": {
            key: float(reference_power[key]) + saved_power_delta[key]
            for key in saved_power_delta
        },
        "modal_direct_aggregate_sums": action_power,
        "modal_direct_aggregate_replay_errors": direct_aggregate_replay,
        "aggregate_J_power_source": "HASH_BOUND_SAVED_SIGNED_AGGREGATES; PER_MODE_POWER_REPLAYED_SEPARATELY",
        "power_delta_vs_Y6_1": power_delta,
        "max_individual_channel_power_abs_delta": max(abs(v) for v in channel_diffs.values()),
    }


def _cell_csv_rows(
    order: int, boxes: list[dict[str, Any]], ids: list[int], groups: dict[int, str],
    results: dict[str, Any], normalized_g_squared: float, baseline_error_squared: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot, global_id in enumerate(ids):
        row: dict[str, Any] = {
            "quadrature_order": order, "global_cell_id": global_id,
            "lower_nm": json.dumps(boxes[slot]["lower"], separators=(",", ":")),
            "upper_nm": json.dumps(boxes[slot]["upper"], separators=(",", ":")),
            "region": groups[global_id],
        }
        for action, components in results.items():
            for field, component_terms in components.items():
                for name in ("B", "D", "X", "I", "after_error_squared", "I_independent", "identity_error"):
                    value = float(component_terms[name][slot])
                    prefix = f"{action}.{field}.{name}"
                    row[prefix] = value
                    row[f"{prefix}.over_frozen_reference_or_floor_G2"] = (
                        value / normalized_g_squared if normalized_g_squared else None
                    )
                    row[f"{prefix}.over_baseline_error_G2"] = value / baseline_error_squared if baseline_error_squared else None
                b, d, x = (float(component_terms[n][slot]) for n in ("B", "D", "X"))
                row[f"{action}.{field}.direction_correlation"] = (
                    x / (2.0 * math.sqrt(b * d)) if b > 0.0 and d > 0.0 else "N/A"
                )
        rows.append(row)
    return rows


def _block_summaries(
    ids: list[int], groups: dict[int, str], results: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    blocks = ("requested_root4_global8", "H8_required_closure_root34", "rest_of_domain")
    global_terms = {
        (action, component): {
            "B": float(np.sum(values["B"], dtype=np.float64)),
            "D": float(np.sum(values["D"], dtype=np.float64)),
        }
        for action, components in results.items()
        for component, values in components.items()
    }
    for block in blocks:
        selected = np.asarray([i for i, global_id in enumerate(ids) if groups[global_id] == block], dtype=np.int64)
        summary[block] = {}
        for action, components in results.items():
            summary[block][action] = {}
            for component, values in components.items():
                aggregate = {}
                for term in ("B", "D", "X", "I", "after_error_squared", "I_independent"):
                    aggregate[term] = float(np.sum(values[term][selected], dtype=np.float64))
                impacts = values["I"][selected]
                positive = float(np.sum(np.maximum(impacts, 0.0), dtype=np.float64))
                negative = float(np.sum(np.minimum(impacts, 0.0), dtype=np.float64))
                denominator = positive + abs(negative)
                aggregate.update({
                    "positive_I_sum": positive, "negative_I_sum": negative,
                    "B_fraction_of_global": (
                        aggregate["B"] / global_terms[(action, component)]["B"]
                        if global_terms[(action, component)]["B"] > 0.0 else "N/A"
                    ),
                    "D_fraction_of_global": (
                        aggregate["D"] / global_terms[(action, component)]["D"]
                        if global_terms[(action, component)]["D"] > 0.0 else "N/A"
                    ),
                    "cancellation_fraction": (1.0 - abs(aggregate["I"]) / denominator) if denominator > 0 else "N/A",
                    "direction_correlation": (
                        aggregate["X"] / (2.0 * math.sqrt(aggregate["B"] * aggregate["D"]))
                        if aggregate["B"] > 0 and aggregate["D"] > 0 else "N/A"
                    ),
                    "cell_count": int(selected.size),
                })
                summary[block][action][component] = aggregate
    return summary


def _mode_rows(
    modal_by_case: dict[str, dict[tuple[str, int, int, str], dict[str, Any]]],
    power_limit: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    exceed: list[dict[str, Any]] = []
    for key in CHANNEL_KEYS:
        side, m, n, pol = key
        values = {name: modal_by_case[name][key] for name in ("R9", "H8", "P8", "Y6_1")}
        amplitudes = {name: _complex_pair(row, "outgoing_amplitude_at_boundary") for name, row in values.items()}
        out: dict[str, Any] = {
            "side": side, "m": m, "n": n, "polarization": pol,
            "power_threshold": power_limit,
            "physical_power_reassembly": "NOT_PERFORMED",
        }
        for name, row in values.items():
            amp = amplitudes[name]
            out[f"{name}_amplitude_real"] = amp.real
            out[f"{name}_amplitude_imag"] = amp.imag
            out[f"{name}_saved_power_ratio"] = float(row["power_ratio"])
            out[f"{name}_saved_R"] = float(row["R"])
            out[f"{name}_saved_T"] = float(row["T"])
        for action_name in ("R9", "H8", "P8"):
            amp_delta_parent = amplitudes[action_name] - amplitudes["R9"]
            amp_delta_reference = amplitudes[action_name] - amplitudes["Y6_1"]
            square = amplitude_square_delta(amplitudes["R9"], amp_delta_parent)
            power_delta_parent = float(values[action_name]["power_ratio"]) - float(values["R9"]["power_ratio"])
            power_delta_reference = float(values[action_name]["power_ratio"]) - float(values["Y6_1"]["power_ratio"])
            out.update({
                f"{action_name}_minus_R9_amplitude_real": amp_delta_parent.real,
                f"{action_name}_minus_R9_amplitude_imag": amp_delta_parent.imag,
                f"{action_name}_minus_R9_amplitude_absolute": abs(amp_delta_parent),
                f"{action_name}_minus_Y6_1_amplitude_real": amp_delta_reference.real,
                f"{action_name}_minus_Y6_1_amplitude_imag": amp_delta_reference.imag,
                f"{action_name}_minus_Y6_1_amplitude_absolute": abs(amp_delta_reference),
                f"{action_name}_minus_R9_power_ratio_signed": power_delta_parent,
                f"{action_name}_minus_R9_power_ratio_absolute": abs(power_delta_parent),
                f"{action_name}_minus_Y6_1_power_ratio_signed": power_delta_reference,
                f"{action_name}_minus_Y6_1_power_ratio_absolute": abs(power_delta_reference),
                f"{action_name}_minus_R9_power_exceeds_threshold": abs(power_delta_parent) > power_limit,
                f"{action_name}_minus_Y6_1_power_exceeds_threshold": abs(power_delta_reference) > power_limit,
                f"{action_name}_amplitude_squared_interference_vs_R9": square["interference_amplitude_squared"],
                f"{action_name}_amplitude_squared_quadratic_vs_R9": square["delta_amplitude_squared"],
                f"{action_name}_amplitude_squared_change_vs_R9": square["amplitude_squared_change"],
                f"{action_name}_independent_amplitude_squared_change_vs_R9": square["independent_amplitude_squared_change"],
                f"{action_name}_amplitude_squared_identity_error": square["identity_error"],
                f"{action_name}_propagating": bool(values[action_name].get("propagating", False)),
            })
        rows.append(out)
        for action_name in ("R9", "H8", "P8"):
            if out[f"{action_name}_minus_Y6_1_power_exceeds_threshold"]:
                exceed.append({
                    "action": action_name, "side": side, "m": m, "n": n,
                    "polarization": pol,
                    "signed_difference": out[f"{action_name}_minus_Y6_1_power_ratio_signed"],
                    "absolute_difference": out[f"{action_name}_minus_Y6_1_power_ratio_absolute"],
                    "threshold": power_limit,
                })
    return rows, exceed


def _load_source_bundle(manifest: dict[str, Any]) -> dict[str, Any]:
    paths = _verify_sources(manifest)
    comparison = _json_file(paths["p8_comparison"])
    if set(comparison.get("results", {})) != {"q8", "q10"}:
        raise EvidenceError("V18 comparison must contain exactly q8 and q10")
    if comparison.get("shared_physics", {}).get("all_four_cases_match") is not True:
        raise EvidenceError("comparison does not bind shared four-case physics")
    numeric = comparison["shared_physics"]["shared_identity"]["numeric"]
    physics = manifest["physics"]
    k0 = float(numeric["k0_per_nm"][0])
    h_scale = float(numeric["magnetic_field_scale_a_per_m"][0])
    if k0 != float(physics["k0_per_nm"]) or h_scale != float(physics["magnetic_field_scale_a_per_m"]):
        raise EvidenceError("frozen H/G scaling differs from saved comparison shared identity")
    if numeric["mu_r"] != [1.0, 0.0]:
        raise EvidenceError("unexpected frozen mu_r")
    modal = {name: _load_modal(paths[role]) for name, role in {
        "R9": "r9_modal", "H8": "h8_modal", "P8": "p8_modal", "Y6_1": "y6_modal"
    }.items()}
    absorption = {name: _absorption(paths[role], reference=(name == "Y6_1")) for name, role in {
        "R9": "r9_absorption", "H8": "h8_absorption", "P8": "p8_absorption", "Y6_1": "y6_summary"
    }.items()}
    for q in ("q8", "q10"):
        comparison_q = comparison["results"][q]
        for name, key in (("R9", "R9"), ("H8", "R9_H8"), ("P8", "R9_P8")):
            _close(absorption[name], float(comparison_q[key]["signed_observables"]["aggregate_signed_candidate_minus_reference"]["A_volume"]) + float(comparison_q["Y6_1_reference"]["power"]["A_volume"]), f"{q}.{name}.A_volume")
    r9_plan = _plan_boxes(paths["r9_plan"], manifest["sources"]["r9_plan"]["sha256"])
    h8_plan = _plan_boxes(paths["h8_plan"], manifest["sources"]["h8_plan"]["sha256"])
    p8_plan = _plan_boxes(paths["p8_plan"], manifest["sources"]["p8_plan"]["sha256"])
    if len(p8_plan) != len(r9_plan) or any(not _boxes_equal(a, b) for a, b in zip(p8_plan, r9_plan, strict=True)):
        raise EvidenceError("P8 and R9 base-cell boxes differ")
    return {"paths": paths, "comparison": comparison, "modal": modal,
            "absorption": absorption, "plans": {"R9": r9_plan, "H8": h8_plan, "P8": p8_plan},
            "k0": k0, "h_scale": h_scale}


def _expected_npz_members(contract: dict[str, Any], q: str) -> tuple[set[str], set[str]]:
    record = contract["quadrature_archives"][q]
    return set(record["p5_members"]), set(record["p8_members"])


def _load_order_arrays(
    contract: dict[str, Any], q: str, source_paths: dict[str, Path],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any]]:
    rec = contract["quadrature_archives"][q]
    p5rec = rec["p5"]
    p8rec = rec["p8"]
    p5path = _checked_source(p5rec)
    p8path = _checked_source(p8rec)
    p5_members, p8_members = _expected_npz_members(contract, q)
    p5_record = inspect_npz(
        p5path, outer_sha256=p5rec["sha256"], expected_members=p5_members,
        expected_count=int(rec["sample_count"]), expected_schema=p5rec["schema"],
        expected_identity=p5rec["identity"], expected_nested_identity=p5rec["nested_identity"], expected_record_sha256=p5rec["embedded_record_sha256"],
    )
    p8_record = inspect_npz(
        p8path, outer_sha256=p8rec["sha256"], expected_members=p8_members,
        expected_count=int(rec["sample_count"]), expected_schema=p8rec["schema"],
        expected_identity=p8rec["identity"], expected_nested_identity=p8rec["nested_identity"], expected_record_sha256=p8rec["embedded_record_sha256"],
    )
    verify_pair_identity(p5_record, p8_record, p5rec["sha256"], "v16_r9_p8", int(q[1:]))
    p5 = _load_npz_arrays(p5path, p5_members)
    p8 = _load_npz_arrays(p8path, p8_members)
    count = int(rec["sample_count"])
    if p5["points_nm"].shape != (count, 3) or p5["weights_nm3"].shape != (count,):
        raise EvidenceError(f"{q} common point/weight layout mismatch")
    if np.any(p5["weights_nm3"] <= 0.0):
        raise EvidenceError(f"{q} quadrature weights are not strictly positive")
    volume = float(np.sum(p5["weights_nm3"], dtype=np.float64))
    if abs(volume - VOLUME_NM3) > 1.0e-8:
        raise EvidenceError(f"{q} common quadrature volume mismatch: {volume}")
    for prefix in ("R9", "R9_H8", "Y6_1"):
        validate_owner_map(
            p5[f"{prefix}_cell_global_ids"],
            p5[f"{prefix}_point_cell_local_slots"],
            p5[f"{prefix}_point_cell_global_ids"],
        )
        if p5[f"{prefix}_point_cell_local_slots"].shape != (count,):
            raise EvidenceError(f"{q} {prefix} owner map count mismatch")
    validate_owner_map(p8["P8_cell_global_ids"], p8["P8_point_cell_local_slots"], p8["P8_point_cell_global_ids"])
    if not np.array_equal(p8["P8_cell_global_ids"], p5["R9_cell_global_ids"]):
        raise EvidenceError(f"{q} P8 and R9 cell identity differs")
    if not np.array_equal(p8["P8_point_cell_global_ids"], p5["R9_point_cell_global_ids"]):
        raise EvidenceError(f"{q} P8 owner map differs from R9 point map")
    return p5, p8, {"P5_sha256": p5rec["sha256"], "P8_sha256": p8rec["sha256"],
                    "sample_count": count, "volume_nm3": volume,
                    "P5_embedded_record_sha256": p5rec["embedded_record_sha256"],
                    "P8_embedded_record_sha256": p8rec["embedded_record_sha256"]}


def _one_order(
    q: str, contract: dict[str, Any], bundle: dict[str, Any],
    source_paths: dict[str, Path], root_targets: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    order = int(q.removeprefix("q"))
    p5, p8, archive_identity = _load_order_arrays(contract, q, source_paths)
    ids = [int(x) for x in p5["R9_cell_global_ids"]]
    if ids != list(range(180)):
        raise EvidenceError(f"{q} R9 global cell id order is not the frozen 0..179 order")
    ordered_r9_boxes = order_plan_boxes_from_saved_owners(
        p5["points_nm"], p5["R9_cell_global_ids"], p5["R9_point_cell_local_slots"],
        p5["R9_point_cell_global_ids"], bundle["plans"]["R9"],
    )
    groups = _cell_groups(ordered_r9_boxes, bundle["plans"]["H8"], ids, root_targets)
    validate_points_against_r9_boxes(
        p5["points_nm"], p5["R9_cell_global_ids"],
        p5["R9_point_cell_local_slots"], p5["R9_point_cell_global_ids"],
        ordered_r9_boxes,
    )
    reference_g = float(np.sum(np.abs(p5["Y6_1_E"]) ** 2 + np.abs(p5["Y6_1_curl_E"] / bundle["k0"]) ** 2, axis=1) @ p5["weights_nm3"])
    if not math.isfinite(reference_g) or reference_g <= 0:
        raise EvidenceError(f"{q} reference G squared must be finite and positive")
    outputs: dict[str, Any] = {}
    field_ratios: dict[str, Any] = {}
    j_replays: dict[str, Any] = {}
    modal_by_case = bundle["modal"]
    comparison_q = bundle["comparison"]["results"][q]
    reference_abs = bundle["absorption"]["Y6_1"]
    baseline_terms = _accumulate_component(
        p5["Y6_1_E"] - p5["R9_E"], p5["Y6_1_E"] - p5["R9_E"],
        p5["weights_nm3"], p5["R9_point_cell_local_slots"], 180, 1.0,
    )
    baseline_curl = _accumulate_component(
        (p5["Y6_1_curl_E"] - p5["R9_curl_E"]) / bundle["k0"],
        (p5["Y6_1_curl_E"] - p5["R9_curl_E"]) / bundle["k0"],
        p5["weights_nm3"], p5["R9_point_cell_local_slots"], 180, 1.0,
    )
    baseline_error_squared = float(np.sum(baseline_terms["B"] + baseline_curl["B"]))
    if baseline_error_squared <= 0 or not math.isfinite(baseline_error_squared):
        raise EvidenceError("R9-to-reference baseline error must be positive and finite")
    cell_actions = {}
    for action, ekey, ckey, modal_name, comp_name in (
        ("H8", "R9_H8_E", "R9_H8_curl_E", "H8", "R9_H8"),
        ("P8", "P8_E", "P8_curl_E", "P8", "R9_P8"),
    ):
        field_e = p5[ekey] if action == "H8" else p8[ekey]
        field_curl = p5[ckey] if action == "H8" else p8[ckey]
        terms = _g_terms_for_action(p5, field_e, field_curl, bundle["k0"], 180)
        cell_actions[action] = terms
        global_checks = {}
        for component_name, values in terms.items():
            scale = np.maximum.reduce([
                values["B"], values["after_error_squared"], np.abs(values["X"]),
                values["D"], np.full(180, 1.0e-30),
            ])
            ratio = np.abs(values["identity_error"]) / scale
            if np.any(ratio > G_IDENTITY_TOL):
                raise EvidenceError(f"{q} {action} {component_name} per-cell G identity failed")
            global_error = float(np.sum(values["identity_error"], dtype=np.float64))
            global_scale = max(
                float(np.sum(values["B"], dtype=np.float64)),
                float(np.sum(values["after_error_squared"], dtype=np.float64)),
                abs(float(np.sum(values["X"], dtype=np.float64))),
                float(np.sum(values["D"], dtype=np.float64)), 1.0e-30,
            )
            if abs(global_error) > G_IDENTITY_TOL * global_scale:
                raise EvidenceError(f"{q} {action} {component_name} global G identity failed")
            global_checks[component_name] = {
                "sum_B": float(np.sum(values["B"], dtype=np.float64)),
                "sum_D": float(np.sum(values["D"], dtype=np.float64)),
                "sum_X": float(np.sum(values["X"], dtype=np.float64)),
                "sum_I": float(np.sum(values["I"], dtype=np.float64)),
                "sum_after_error_squared": float(np.sum(values["after_error_squared"], dtype=np.float64)),
                "sum_I_independent": float(np.sum(values["I_independent"], dtype=np.float64)),
                "identity_error": global_error,
                "scale": global_scale,
                "relative_error": abs(global_error) / global_scale,
                "tolerance": G_IDENTITY_TOL,
            }
        computed_g2 = float(np.sum(terms["G"]["after_error_squared"]))
        expected_eta = float(comparison_q[comp_name]["eta"])
        diff_g = math.sqrt(computed_g2)
        reference_g_norm = float(comparison_q[comp_name]["field_metrics"]["G"]["reference_g_norm"])
        floor_g = float(comparison_q[comp_name]["field_metrics"]["G"]["incident_g_norm_floor"])
        eta = diff_g / max(reference_g_norm, floor_g)
        _close(eta, expected_eta, f"{q}.{action}.G_eta")
        field_ratio, field_replay = _field_replay(
            p5, field_e, field_curl, comparison_q[comp_name], bundle["k0"],
            bundle["h_scale"], floor_g,
        )
        field_ratios[action] = field_ratio
        action_modal = modal_by_case[modal_name]
        j_replays[action] = _replay_j(
            p5, field_e, field_curl, action_modal, modal_by_case["Y6_1"],
            bundle["absorption"][modal_name], reference_abs,
            comparison_q[comp_name], comparison_q["Y6_1_reference"]["power"], field_ratio,
        )
        outputs[action] = {
            "G_error_norm": diff_g,
            "G_error_squared": computed_g2,
            "G_eta_recomputed": eta,
            "G_eta_saved": expected_eta,
            "field_norm_replay": field_replay,
            "J_replay": j_replays[action],
            "signed_observables_candidate_minus_Y6_1": comparison_q[comp_name]["signed_observables"]["aggregate_signed_candidate_minus_reference"],
            "classification": comparison_q.get("classification", {}).get("classification"),
            "G_identity_checks": global_checks,
        }
        for observable, computed in j_replays[action]["power_delta_vs_Y6_1"].items():
            saved = comparison_q[comp_name]["signed_observables"]["aggregate_signed_candidate_minus_reference"][observable]
            _close(computed, float(saved), f"{q}.{action}.signed.{observable}")
    # Include the frozen R9 parent itself so all three pre-existing J vectors
    # are replayed from the same saved common points and modal sources.
    r9_case = comparison_q["R9"]
    r9_field_ratios, r9_field_replay = _field_replay(
        p5, p5["R9_E"], p5["R9_curl_E"], r9_case,
        bundle["k0"], bundle["h_scale"],
        float(r9_case["field_metrics"]["G"]["incident_g_norm_floor"]),
    )
    r9_j = _replay_j(
        p5, p5["R9_E"], p5["R9_curl_E"], modal_by_case["R9"],
        modal_by_case["Y6_1"], bundle["absorption"]["R9"], reference_abs,
        r9_case, comparison_q["Y6_1_reference"]["power"], r9_field_ratios,
    )
    for observable, computed in r9_j["power_delta_vs_Y6_1"].items():
        saved = r9_case["signed_observables"]["aggregate_signed_candidate_minus_reference"][observable]
        _close(computed, float(saved), f"{q}.R9.signed.{observable}")
    outputs["R9"] = {
        "G_error_norm": float(np.sqrt(baseline_error_squared)),
        "G_error_squared": baseline_error_squared,
        "field_norm_replay": r9_field_replay,
        "J_replay": r9_j,
        "signed_observables_candidate_minus_Y6_1": r9_case["signed_observables"]["aggregate_signed_candidate_minus_reference"],
        "classification": comparison_q.get("classification", {}).get("classification"),
    }
    reference_g_norm = math.sqrt(reference_g)
    reference_g_floor = float(comparison_q["R9"]["field_metrics"]["G"]["incident_g_norm_floor"])
    normalized_g_norm = max(reference_g_norm, reference_g_floor)
    normalized_g_squared = normalized_g_norm ** 2
    cell_rows = _cell_csv_rows(order, ordered_r9_boxes, ids, groups, cell_actions,
                               normalized_g_squared, baseline_error_squared)
    mode_rows, all_exceed = _mode_rows(modal_by_case, J_CHANNEL_POWER_TOLERANCE)
    result = {
        "quadrature": {"order": order, **archive_identity},
        "cell_partition": {
            "cell_count": 180,
            "owner_global_id_to_plan_row": {str(g): bundle["plans"]["R9"].index(ordered_r9_boxes[i]) for i, g in enumerate(ids)},
            "global_reference_G_norm": reference_g_norm,
            "frozen_incident_G_norm_floor": reference_g_floor,
            "frozen_reference_or_floor_G_norm": normalized_g_norm,
            "normalized_G_squared_denominator": normalized_g_squared,
            "baseline_R9_to_Y6_1_error_G_squared": baseline_error_squared,
            "special_cell_bindings": {
                name: {
                    "forest_root_id": int(target["forest_root_id"]),
                    "global_cell_id": next(i for i, group in groups.items() if group == ("requested_root4_global8" if name == "requested" else "H8_required_closure_root34")),
                    "box_nm": {"lower": target["lower"], "upper": target["upper"]},
                    "region": "requested_root4_global8" if name == "requested" else "H8_required_closure_root34",
                }
                for name, target in root_targets.items()
            },
            "H8_closure_global_cell_id": next(i for i, g in groups.items() if g == "H8_required_closure_root34"),
            "block_cell_counts": {name: sum(1 for value in groups.values() if value == name) for name in set(groups.values())},
        },
        "block_response_summaries": _block_summaries(ids, groups, cell_actions),
        "actions": outputs,
        "J_and_G_replay_tolerances": {"relative": REPLAY_RTOL, "absolute": REPLAY_ATOL},
        "modal_power_reassembly": "NOT_PERFORMED; saved physical powers are used directly; amplitude-square algebra is labeled separately",
        "power_channels_over_1e-6": all_exceed,
    }
    return result, cell_rows, mode_rows


def _persist_order_outputs(
    output_root: Path, order: str, result: dict[str, Any],
    cell_rows: list[dict[str, Any]], mode_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Commit a complete order independently; never overwrite an existing order."""
    if order not in ("q8", "q10") or not cell_rows or not mode_rows:
        raise EvidenceError("invalid order or empty output tables")
    qdir = output_root / order
    qdir.mkdir(exist_ok=False)
    paths = {"cells_csv": qdir / "cells.csv", "modes_612_csv": qdir / "modes_612.csv"}
    record: dict[str, Any] = {"status": "COMPLETE"}
    for name, rows in (("cells_csv", cell_rows), ("modes_612_csv", mode_rows)):
        path = paths[name]
        digest = atomic_csv(path, list(rows[0]), rows)
        record[name] = {"path": str(path), "sha256": digest, "rows": len(rows)}
    result = dict(result)
    result["outputs"] = {name: record[name] for name in paths}
    path = qdir / "diagnostic.json"
    record["diagnostic"] = {"path": str(path), "sha256": atomic_json(path, result)}
    return record


def resume_completed_order(
    source_root: Path, contract: dict[str, Any], order: str = "q8",
) -> dict[str, Any]:
    """Read and bind an unchanged completed order; do not copy or alter it."""
    source = _json_file(source_root / "run_manifest.json")
    expected_inputs = {role: rec["sha256"] for role, rec in contract["sources"].items()}
    for q, pair in contract["quadrature_archives"].items():
        for role in ("p5", "p8"):
            expected_inputs[f"quadrature.{q}.{role}"] = pair[role]["sha256"]
    if source.get("source_sha256_start") != expected_inputs:
        raise EvidenceError("completed order input binding differs from this contract")
    if source.get("checker_sha256") != sha256_file(Path(__file__)):
        raise EvidenceError("completed order belongs to different checker bytes; explicit recomputation required")
    # This also covers a partial run that did not reach its final input check.
    for rec in contract["sources"].values():
        _checked_source(rec)
    for pair in contract["quadrature_archives"].values():
        for role in ("p5", "p8"):
            _checked_source(pair[role])
    record = source.get("orders", {}).get(order)
    if not isinstance(record, dict) or record.get("status") != "COMPLETE":
        raise EvidenceError("requested prior order is not complete")
    for name in ("diagnostic", "cells_csv", "modes_612_csv"):
        ref = record[name]
        path = Path(ref["path"])
        if not path.resolve().is_relative_to(source_root.resolve()) or path.is_symlink():
            raise EvidenceError("prior artifact escapes its original root")
        if sha256_file(path) != ref["sha256"]:
            raise EvidenceError("prior completed order artifact hash mismatch")
    result = dict(record)
    result["reused_from"] = {"order": order, "path": str(source_root / "run_manifest.json"),
                             "sha256": sha256_file(source_root / "run_manifest.json")}
    return result


def run_analysis(manifest_path: Path, output_root: Path, stage: str, resume_from: Path | None = None) -> dict[str, Any]:
    manifest, manifest_sha = _load_manifest(manifest_path)
    if stage not in ("D1", "D2"):
        raise EvidenceError("analysis requires a diagnostic slot")
    if resume_from is not None and stage != "D2":
        raise EvidenceError("only D2 may consume an explicitly bound completed D1 order")
    slot = _slot_for_stage(manifest, stage)
    expected_output = REPO_ROOT / Path(str(slot["root"])) / Path(str(slot["output_subdir"]))
    if output_root.resolve(strict=False) != expected_output.resolve(strict=False):
        raise EvidenceError("--output-root does not match the frozen D1 output directory")
    if output_root.exists() or output_root.is_symlink():
        raise FileExistsError(f"refusing existing output root: {output_root}")
    start = time.monotonic()
    run_root = Path(os.environ["TASK43_V19_RUN_ROOT"])
    start_identity_path = run_root / "runtime_start.json"
    if start_identity_path.is_symlink() or not start_identity_path.is_file():
        raise EvidenceError("D1 runtime start identity was not saved by the checked worker")
    identity_record = _json_file(start_identity_path)
    identity = identity_record.get("identity", {})
    if identity_record.get("stage") != stage or identity_record.get("moment") != "start":
        raise EvidenceError("saved runtime start identity is not for D1")
    output_root.mkdir(parents=True, exist_ok=False)
    source_paths = _verify_sources(manifest)
    bundle = _load_source_bundle(manifest)
    input_paths, source_hashes = _input_paths_and_hashes(manifest, source_paths)
    code_sha = sha256_file(Path(__file__))
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                              check=True, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EvidenceError(f"cannot record actual Git HEAD: {exc}") from exc
    run_record: dict[str, Any] = {
        "schema": "task43.v19.saved_hp_response_run.v1",
        "stage": stage, "contract_path": str(manifest_path.resolve()),
        "contract_sha256": manifest_sha, "git_head": head,
        "checker_sha256": code_sha, "python": sys.executable,
        "numpy_version": np.__version__, "runtime_identity": identity,
        "execution_slot": slot,
        "source_sha256_start": source_hashes,
        "runtime_identity_start": {
            "path": str(start_identity_path), "sha256": sha256_file(start_identity_path),
        },
        "started_utc": datetime.now(timezone.utc).isoformat(), "status": "RUNNING",
        "orders": {},
    }
    atomic_json(output_root / "run_manifest.json", run_record)
    root_targets = manifest["physics"]["cell_groups"]
    for q in ("q8", "q10"):
        prior = _json_file(resume_from / "run_manifest.json") if resume_from else {}
        if prior.get("orders", {}).get(q, {}).get("status") == "COMPLETE":
            record = resume_completed_order(resume_from, manifest, q)
        else:
            order_result, cell_rows, mode_rows = _one_order(q, manifest, bundle, source_paths, root_targets)
            record = _persist_order_outputs(output_root, q, order_result, cell_rows, mode_rows)
        run_record["orders"][q] = record
        run_record["last_complete_order"] = q
        atomic_json(output_root / "run_manifest.json", run_record)
    all_result = {
        "schema": "task43.v19.saved_hp_response_result.v1",
        "classification": "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE",
        "official_result": False,
        "selection_eligible": False,
        "new_formal_pde": 0,
        "source_sha256_start": source_hashes,
        "q8": _json_file(Path(run_record["orders"]["q8"]["diagnostic"]["path"])),
        "q10": _json_file(Path(run_record["orders"]["q10"]["diagnostic"]["path"])),
        "comparison": {
            "reference": "Y6_1", "parent": "R9", "actions": ["H8", "P8"],
            "q10_primary_q8_robustness": True,
            "J_and_R00_are_global_observables_not_additive_cell_terms": True,
        },
    }
    final_hashes = {role: sha256_file(path) for role, path in input_paths.items()}
    if final_hashes != source_hashes:
        raise EvidenceError("a frozen input changed while the checker was reading it")
    if sha256_file(manifest_path) != manifest_sha:
        raise EvidenceError("the frozen V19 contract changed while the checker was reading it")
    if sha256_file(Path(__file__)) != code_sha:
        raise EvidenceError("the checker source changed during its own run")
    result_sha = atomic_json(output_root / "diagnostic.json", all_result)
    run_record.update({
        "status": "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE",
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_monotonic_seconds": time.monotonic() - start,
        "source_sha256_end": final_hashes,
        "result": {"path": str(output_root / "diagnostic.json"), "sha256": result_sha},
    })
    atomic_json(output_root / "run_manifest.json", run_record)
    return all_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume-from", type=Path)
    args = parser.parse_args(argv)
    stage = os.environ.get("TASK43_V19_STAGE", "")
    if stage not in ("D1", "D2"):
        print("V19 saved response checker requires D1 or D2 stage identity", file=sys.stderr, flush=True)
        return 2
    started = False
    result: dict[str, Any] | None = None
    failure: BaseException | None = None
    end_path: Path | None = None
    try:
        write_runtime_identity(stage, "start")
        started = True
        if stage == "D2":
            import pytest
            run_root = Path(os.environ["TASK43_V19_RUN_ROOT"])
            selectors = [
                "src/test/test_task43_saved_hp_response.py::test_saved_owner_geometry_reorders_plan_rows",
                "src/test/test_task43_saved_hp_response.py::test_wrong_owner_map_is_rejected",
                "src/test/test_task43_saved_hp_response.py::test_weighted_multicell_terms_close_after_reordering",
            ]
            test_code = pytest.main(["-v", "-rA", "--maxfail=1", "--junitxml", str(run_root / "tests.xml"),
                                     "--basetemp", str(run_root / "fixtures"), *selectors])
            if int(test_code) != 0:
                raise EvidenceError(f"D2 affected fixture batch failed: {test_code}")
        result = run_analysis(args.manifest, args.output_root, stage, args.resume_from)
    except BaseException as exc:
        failure = exc
    finally:
        if started:
            try:
                end_path = write_runtime_identity(stage, "end")
            except BaseException as exc:
                failure = failure or exc
    if failure is not None:
        # Never change a refused pre-existing data root: only this worker's
        # manifest with its own PID may be marked incomplete.
        failure_manifest = args.output_root / "run_manifest.json"
        if failure_manifest.is_file():
            record = _json_file(failure_manifest)
            if record.get("runtime_identity", {}).get("pid") == os.getpid():
                record.update(status="FAILED_INCOMPLETE", official_result=False,
                              selection_eligible=False,
                              failure={"type": type(failure).__name__, "message": str(failure)})
                atomic_json(failure_manifest, record)
        print(f"V19 saved response checker failed: {type(failure).__name__}: {failure}", file=sys.stderr, flush=True)
        return 2
    if result is None:
        print("V19 saved response checker produced no result", file=sys.stderr, flush=True)
        return 2
    run_manifest = args.output_root / "run_manifest.json"
    if stage in ("D1", "D2") and run_manifest.is_file() and end_path is not None:
        record = _json_file(run_manifest)
        record["runtime_identity_end"] = {
            "path": str(end_path), "sha256": sha256_file(end_path),
        }
        atomic_json(run_manifest, record)
    print(json.dumps({"classification": result["classification"], "output_root": str(args.output_root)}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
