"""Read-only V30 q CSR provider with a narrow, verified V28 q0 donor import."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse


V30_Q_CSR_SELECTOR_SCHEMA = "task40extra.review_v30_qualified_q_csr_selector.v1"
V30_Q_CSR_MANIFEST_SCHEMA = "task40extra.review_v30_q_csr.v1"
V30_Q_CSR_NATIVE_SCHEMA = "task40extra.review_v30_q_csr_native_qualification.v1"
V30_Q0_LEGACY_IMPORT_SCHEMA = "task40extra.review_v30_q0_legacy_donor_import.v1"
_OPERATOR_IDENTITY_KEYS = (
    "scientific_input_sha256",
    "profile_identity_sha256",
    "ordered_mode_sha256",
    "q_map_sha256",
    "original_h_sha256",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path.name}")
    return value


def _require_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _require_source_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in (40, 64)
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{label} must be a lowercase 40- or 64-character source hash")
    return value


def _array_sha256(array: np.ndarray, dtype: np.dtype[Any], label: str) -> str:
    value = np.asarray(array)
    if value.dtype != dtype:
        raise ValueError(f"{label} must use exact dtype {dtype.str}")
    canonical = np.dtype(dtype).newbyteorder("<")
    digest = hashlib.sha256()
    digest.update(b"task40-v30-array-v1\\0")
    digest.update(canonical.str.encode("ascii") + b"\\0")
    digest.update(np.asarray(value.shape, dtype="<i8").tobytes())
    flat = value.reshape(-1)
    chunk = max(1, (4 * 1024 * 1024) // canonical.itemsize)
    for start in range(0, flat.size, chunk):
        part = flat[start : start + chunk]
        if part.dtype != canonical:
            part = part.astype(canonical, copy=True)
        digest.update(np.ascontiguousarray(part).view(np.uint8))
    return digest.hexdigest()


def _require_csr(matrix: Any, label: str) -> sparse.csr_matrix:
    if (
        not sparse.isspmatrix_csr(matrix)
        or matrix.dtype != np.dtype(np.complex128)
        or matrix.indices.dtype != np.dtype(np.int32)
        or matrix.indptr.dtype != np.dtype(np.int32)
        or matrix.shape[0] <= 0
        or matrix.shape[1] <= 0
        or not matrix.has_canonical_format
        or not matrix.has_sorted_indices
        or matrix.shape[0] + 1 > np.iinfo(np.int32).max
        or matrix.nnz > np.iinfo(np.int32).max
        or matrix.indptr.shape != (matrix.shape[0] + 1,)
        or int(matrix.indptr[0]) != 0
        or int(matrix.indptr[-1]) != int(matrix.nnz)
    ):
        raise ValueError(f"{label} is not canonical complex128/int32 CSR")
    chunk = 1 << 20
    for start in range(0, int(matrix.nnz), chunk):
        stop = min(start + chunk, int(matrix.nnz))
        columns = matrix.indices[start:stop]
        if (
            np.any(columns < 0)
            or np.any(columns >= matrix.shape[1])
            or not np.isfinite(matrix.data[start:stop]).all()
        ):
            raise ValueError(f"{label} contains an invalid column or non-finite value")
    for start in range(0, matrix.shape[0], chunk):
        stop = min(start + chunk, matrix.shape[0])
        if np.any(matrix.indptr[start + 1 : stop + 1] < matrix.indptr[start:stop]):
            raise ValueError(f"{label} row pointers are not monotone")
    return matrix


def _csr_sha256(matrix: sparse.csr_matrix) -> str:
    _require_csr(matrix, "runtime q map")
    digest = hashlib.sha256()
    digest.update(b"task40-v30-csr-v1\\0")
    digest.update(np.asarray(matrix.shape, dtype="<i8").tobytes())
    digest.update(b"<i4\\0<c16\\0")
    for value in (matrix.indptr, matrix.indices, matrix.data):
        dtype = np.dtype(value.dtype).newbyteorder("<")
        flat = np.asarray(value).reshape(-1)
        chunk = max(1, (4 * 1024 * 1024) // dtype.itemsize)
        for start in range(0, flat.size, chunk):
            part = flat[start : start + chunk]
            if part.dtype != dtype:
                part = part.astype(dtype, copy=True)
            digest.update(np.ascontiguousarray(part).view(np.uint8))
    return digest.hexdigest()


def _resolve_artifact(
    raw_path: Any,
    *,
    manifest_path: Path,
    resolve_path: Callable[[str | Path], Path],
    approved_root: Path,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("CSR artifact path is missing")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    resolved = resolve_path(candidate).resolve()
    if not resolved.is_relative_to(approved_root.resolve()):
        raise ValueError("CSR artifact escaped the approved root")
    return resolved


class QualifiedQCSRProvider:
    """Open one selected q after independent runtime and saved-evidence checks."""

    def __init__(
        self,
        selector_path: str | Path,
        *,
        selector_sha256: str,
        repo_root: str | Path,
        path_resolver: Callable[[Path], Path],
        allocation_gate: Callable[[str, Mapping[str, Any]], Any],
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._raw_resolver = path_resolver
        self.allocation_gate = allocation_gate
        if not callable(path_resolver) or not callable(allocation_gate):
            raise TypeError("provider needs an approved path resolver and live allocation gate")
        self.path_resolver = lambda path: self._resolve(path)
        selector = self._resolve(selector_path)
        if not selector.is_file() or _sha256_file(selector) != _require_sha(
            selector_sha256, "selector_sha256"
        ):
            raise ValueError("V30 q selector is missing or changed")
        payload = _read_json(selector)
        rows = payload.get("q_csr_entries")
        if payload.get("schema") != V30_Q_CSR_SELECTOR_SCHEMA or not isinstance(rows, list) or not rows:
            raise ValueError("V30 q selector schema or entries are invalid")
        self.selector_path = selector
        self.selector_sha256 = selector_sha256
        self.profile = payload.get("profile")
        self.entries: dict[int, Mapping[str, Any]] = {}
        for row in rows:
            if (
                not isinstance(row, Mapping)
                or type(row.get("q_index")) is not int
                or row["q_index"] < 0
                or row["q_index"] in self.entries
            ):
                raise ValueError("V30 selector q indices must be unique nonnegative integers")
            self.entries[row["q_index"]] = dict(row)

    def _resolve(self, raw_path: str | Path, base: Path | None = None) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (base or self.repo_root) / candidate
        candidate = candidate.resolve(strict=False)
        if candidate.is_relative_to(self.repo_root):
            return candidate
        mapped = Path(self._raw_resolver(candidate)).resolve(strict=False)
        if not mapped.is_relative_to(self.repo_root):
            raise ValueError("q evidence escaped the approved execution root")
        return mapped

    @staticmethod
    def _run_identity(value: Mapping[str, Any], label: str) -> dict[str, str]:
        result = dict(value)
        _require_source_sha(result.get("source_sha"), f"{label}.source_sha")
        _require_sha(result.get("window_sha256"), f"{label}.window_sha256")
        return result

    def load(
        self,
        q_index: int,
        twist_index: int,
        *,
        expected_operator_identity: Mapping[str, Any],
        expected_execution_identity: Mapping[str, Any],
        expected_q_map: sparse.csr_matrix,
        expected_original_h: np.ndarray,
        expected_legacy_q0_identity: Mapping[str, Any] | None = None,
        expected_q0_active_lookup: np.ndarray | None = None,
        q0_identity_mapping: Mapping[str, np.ndarray] | None = None,
    ) -> tuple[sparse.csr_matrix, dict[str, Any]]:
        if type(q_index) is not int or q_index not in self.entries:
            raise ValueError(f"selector has no qualified q={q_index}")
        if type(twist_index) is not int or twist_index < 0:
            raise ValueError("twist index must be an explicit nonnegative integer")
        entry = self.entries[q_index]
        if entry.get("twist_index") != twist_index:
            raise ValueError("selected q is bound to another twist")
        identity = dict(expected_operator_identity)
        if not set(_OPERATOR_IDENTITY_KEYS) <= set(identity):
            raise ValueError("runtime operator identity is incomplete")
        for key in _OPERATOR_IDENTITY_KEYS:
            _require_sha(identity.get(key), f"operator_identity.{key}")
        self.allocation_gate(
            f"task40_v30_q{q_index}_runtime_identity",
            {
                "additional_payload_bytes": 0,
                "runtime_q_map_owner_bytes": int(
                    expected_q_map.data.nbytes + expected_q_map.indices.nbytes + expected_q_map.indptr.nbytes
                ),
                "runtime_original_h_owner_bytes": int(np.asarray(expected_original_h).nbytes),
                "workspace_bytes": 16 * 1024 * 1024,
                "validation_chunk_bytes": 4 * 1024 * 1024,
            },
        )
        runtime_map_sha = _csr_sha256(expected_q_map)
        runtime_h_sha = _array_sha256(
            np.asarray(expected_original_h), np.dtype(np.complex128), "runtime original H"
        )
        if (
            identity["q_map_sha256"] != runtime_map_sha
            or identity["original_h_sha256"] != runtime_h_sha
            or dict(entry.get("operator_identity", {})) != identity
        ):
            raise ValueError("selector identity differs from actual runtime input/operator data")
        execution = self._run_identity(expected_execution_identity, "execution_identity")
        if (
            self._run_identity(entry.get("execution_identity", {}), "selector.execution_identity")
            != execution
        ):
            raise ValueError("selector execution source/window differs from this run")
        matrix_source = self._run_identity(
            entry.get("matrix_source_identity", {}), "matrix_source_identity"
        )
        if entry.get("shape") is None:
            raise ValueError("selector omits the q matrix shape")

        manifest_record = entry.get("csr_manifest")
        qualification_record = entry.get("native_qualification")
        if not isinstance(manifest_record, Mapping) or not isinstance(qualification_record, Mapping):
            raise ValueError("selector must bind a CSR manifest and qualification")
        manifest_path = self._bound_json(manifest_record, "CSR manifest")
        manifest_sha = _require_sha(manifest_record.get("sha256"), "csr_manifest.sha256")
        if _sha256_file(manifest_path) != manifest_sha:
            raise ValueError("CSR manifest hash changed")
        manifest = _read_json(manifest_path)
        legacy_q0 = manifest.get("schema") == "task40extra.review_v28_saved_q0_csr.v1"
        qualification_path = self._bound_json(qualification_record, "native qualification")
        qualification_sha = _require_sha(
            qualification_record.get("sha256"), "native_qualification.sha256"
        )
        if _sha256_file(qualification_path) != qualification_sha:
            raise ValueError("qualification hash changed")
        qualification = _read_json(qualification_path)

        legacy_receipt: dict[str, Any] | None = None
        if legacy_q0:
            legacy_receipt = self._verify_legacy_q0(
                entry=entry,
                manifest=manifest,
                manifest_path=manifest_path,
                manifest_sha=manifest_sha,
                qualification_record=qualification_record,
                qualification_path=qualification_path,
                qualification_sha=qualification_sha,
                qualification=qualification,
                identity=identity,
                execution=execution,
                matrix_source=matrix_source,
                current_q_map=expected_q_map,
                current_h=np.asarray(expected_original_h),
                expected_legacy_identity=expected_legacy_q0_identity,
                current_active_lookup=expected_q0_active_lookup,
                index_mapping=q0_identity_mapping,
            )
            max_error = None
        else:
            max_error = qualification.get("maximum_relative_error")
            if (
                manifest.get("schema") != V30_Q_CSR_MANIFEST_SCHEMA
                or manifest.get("status") != "COMPLETE_CSR"
                or manifest.get("q_index") != q_index
                or manifest.get("twist_index") != twist_index
                or manifest.get("profile") != self.profile
                or dict(manifest.get("operator_identity", {})) != identity
                or dict(manifest.get("matrix_source_identity", {})) != matrix_source
                or qualification.get("schema") != V30_Q_CSR_NATIVE_SCHEMA
                or qualification.get("status") != "PASS"
                or qualification.get("q_index") != q_index
                or qualification.get("twist_index") != twist_index
                or qualification.get("csr_manifest_sha256") != manifest_sha
                or dict(qualification.get("operator_identity", {})) != identity
                or dict(qualification.get("matrix_source_identity", {})) != matrix_source
                or dict(qualification.get("execution_identity", {})) != execution
                or qualification.get("four_complete_csr_actions_passed") is not True
                or qualification.get("paired_sector_leakage_passed") is not True
                or not isinstance(max_error, (int, float))
                or not math.isfinite(float(max_error))
                or not 0 <= float(max_error) <= 1e-11
            ):
                raise ValueError(f"q={q_index} has no matching ≤1e-11 V30 native PASS")

        shape = manifest.get("shape")
        if (
            manifest.get("status") != "COMPLETE_CSR"
            or not isinstance(shape, list)
            or len(shape) != 2
            or any(type(dimension) is not int or dimension <= 0 for dimension in shape)
            or shape[0] != shape[1]
            or shape != entry["shape"]
        ):
            raise ValueError("q CSR shape/status differs from its frozen selector")
        arrays = manifest.get("csr_artifacts")
        if not isinstance(arrays, Mapping):
            raise ValueError("CSR manifest has no artifact inventory")
        paths: dict[str, Path] = {}
        records: dict[str, Mapping[str, Any]] = {}
        for name in ("data", "indices", "indptr"):
            record = arrays.get(name)
            if not isinstance(record, Mapping):
                raise ValueError(f"CSR manifest omits {name}")
            path = _resolve_artifact(
                record.get("path"),
                manifest_path=manifest_path,
                resolve_path=self.path_resolver,
                approved_root=self.repo_root,
            )
            if type(record.get("bytes")) is not int or not path.is_file():
                raise ValueError(f"CSR {name} size/path is invalid")
            if path.stat().st_size != record["bytes"]:
                raise ValueError(f"CSR {name} size changed")
            _require_sha(record.get("sha256"), f"{name}.sha256")
            paths[name], records[name] = path, record
        payload_bytes = sum(record["bytes"] for record in records.values())
        self.allocation_gate(
            f"task40_v30_q{q_index}_csr_open",
            {
                "q_index": q_index,
                "twist_index": twist_index,
                "shape": shape,
                "stored_structural_slots": manifest.get("stored_structural_slots"),
                "additional_payload_bytes": payload_bytes,
                "workspace_bytes": 16 * 1024 * 1024,
                "mmap_file_pages_counted_as_memory": True,
                "all_large_file_hashes_after_gate": True,
                "validation_chunk_bytes": 4 * 1024 * 1024,
            },
        )
        slots = manifest.get("stored_structural_slots")
        if legacy_q0:
            from src.solvers.task40_v27_saved_q0 import open_saved_q0_csr_from_manifest

            def resolve_legacy(raw: str | Path) -> Path:
                return _resolve_artifact(
                    str(raw),
                    manifest_path=manifest_path,
                    resolve_path=self.path_resolver,
                    approved_root=self.repo_root,
                )

            matrix, reopened = open_saved_q0_csr_from_manifest(
                manifest_path, path_resolver=resolve_legacy
            )
            if reopened != manifest:
                raise ValueError("V28 q0 manifest changed during readback")
            _require_csr(matrix, "V28 q0 COMPLETE_CSR")
        else:
            for name, path in paths.items():
                if _sha256_file(path) != records[name]["sha256"]:
                    raise ValueError(f"CSR {name} hash changed")
            if (
                manifest.get("csr_index_dtype") != np.dtype(np.int32).str
                or manifest.get("csr_data_dtype") != np.dtype(np.complex128).str
                or type(slots) is not int
                or not 0 <= slots <= np.iinfo(np.int32).max
                or shape[0] + 1 > np.iinfo(np.int32).max
            ):
                raise ValueError("CSR dtypes or nnz exceed the supported int32 range")
            data = np.load(paths["data"], mmap_mode="r", allow_pickle=False)
            indices = np.load(paths["indices"], mmap_mode="r", allow_pickle=False)
            indptr = np.load(paths["indptr"], mmap_mode="r", allow_pickle=False)
            if (
                data.dtype != np.dtype(np.complex128)
                or indices.dtype != np.dtype(np.int32)
                or indptr.dtype != np.dtype(np.int32)
                or data.ndim != 1
                or indices.shape != data.shape
                or len(indices) != slots
                or indptr.shape != (shape[0] + 1,)
                or int(indptr[0]) != 0
                or int(indptr[-1]) != slots
            ):
                raise ValueError("CSR array dimensions/endpoints differ from its manifest")
            matrix = sparse.csr_matrix((data, indices, indptr), shape=tuple(shape), copy=False)
            if not all(
                np.shares_memory(owner, view)
                for owner, view in ((data, matrix.data), (indices, matrix.indices), (indptr, matrix.indptr))
            ):
                raise ValueError("opened V30 CSR detached from its read-only mmap payloads")
            _require_csr(matrix, f"q={q_index} V30 CSR")

        receipt = {
            "q_index": q_index,
            "twist_index": twist_index,
            "selector_sha256": self.selector_sha256,
            "csr_manifest_path": str(manifest_path),
            "csr_manifest_sha256": manifest_sha,
            "native_qualification_path": str(qualification_path),
            "native_qualification_sha256": qualification_sha,
            "qualification_kind": (
                "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED"
                if legacy_q0
                else "V30_NATIVE_PASS"
            ),
            "qualification_status": qualification.get("status"),
            "maximum_relative_error": None if max_error is None else float(max_error),
            "legacy_q0_import": legacy_receipt,
            "matrix_source_identity": matrix_source,
            "execution_identity": execution,
            "matrix_source_window_differs_from_execution_window": (
                matrix_source["window_sha256"] != execution["window_sha256"]
            ),
            "shape": list(shape),
            "stored_structural_slots": int(slots),
            "payload_bytes": int(payload_bytes),
        }
        return matrix, receipt

    def _verify_legacy_q0(
        self,
        *,
        entry: Mapping[str, Any],
        manifest: Mapping[str, Any],
        manifest_path: Path,
        manifest_sha: str,
        qualification_record: Mapping[str, Any],
        qualification_path: Path,
        qualification_sha: str,
        qualification: Mapping[str, Any],
        identity: Mapping[str, Any],
        execution: Mapping[str, Any],
        matrix_source: Mapping[str, Any],
        current_q_map: sparse.csr_matrix,
        current_h: np.ndarray,
        expected_legacy_identity: Mapping[str, Any] | None,
        current_active_lookup: np.ndarray | None,
        index_mapping: Mapping[str, np.ndarray] | None,
    ) -> dict[str, Any]:
        legacy = entry.get("legacy_q0_import")
        if (
            entry.get("q_index") != 0
            or entry.get("twist_index") != 0
            or manifest.get("q_map_count") != 1
            or manifest.get("q_map_branch") != 0
            or manifest.get("saved_only_no_fe_or_native_rebuild") is not True
            or not isinstance(legacy, Mapping)
            or legacy.get("schema") != V30_Q0_LEGACY_IMPORT_SCHEMA
        ):
            raise ValueError("only the registered V28 q0 donor may use legacy import")
        fill = manifest.get("numeric_fill_identity")
        if not isinstance(fill, Mapping) or self._run_identity(
            {"source_sha": fill.get("source_sha"), "window_sha256": fill.get("campaign_window_sha256")},
            "V28 numeric_fill_identity",
        ) != dict(matrix_source):
            raise ValueError("V28 q0 matrix source/window identity differs from its original fill")

        old = legacy.get("v28_identity")
        pattern = legacy.get("original_pattern_manifest")
        if not isinstance(old, Mapping) or not isinstance(pattern, Mapping):
            raise ValueError("V30 q0 sidecar omits the V28 verifier inputs")
        if expected_legacy_identity is None or current_active_lookup is None:
            raise ValueError("q0 import needs independently computed physical/mode and active-lookup identity")
        legacy_identity = dict(expected_legacy_identity)
        for field in ("input_sha256", "physical_model_sha256", "mode_manifest_sha256"):
            _require_sha(legacy_identity.get(field), f"expected_legacy_q0_identity.{field}")
        if (
            old.get("input_sha256") != identity["scientific_input_sha256"]
            or old.get("input_sha256") != legacy_identity["input_sha256"]
            or old.get("physical_model_sha256") != legacy_identity["physical_model_sha256"]
            or old.get("mode_manifest_sha256") != legacy_identity["mode_manifest_sha256"]
            or old.get("ordered_mode_key_sha256") != identity["ordered_mode_sha256"]
            or old.get("campaign_window_sha256") != matrix_source["window_sha256"]
        ):
            raise ValueError("V28 donor input/profile/modes/window differ from current mathematical identity")
        pattern_path = self._resolve(pattern.get("path", ""))
        pattern_sha = _require_sha(pattern.get("sha256"), "original_pattern_manifest.sha256")
        if not pattern_path.is_file() or _sha256_file(pattern_path) != pattern_sha:
            raise ValueError("V28 original pattern manifest file hash changed")
        old_record = manifest.get("native_qualification")
        if not isinstance(old_record, Mapping) or any(
            old_record.get(key) != qualification_record.get(key)
            for key in ("path", "sha256", "status")
        ):
            raise ValueError("V30 selector does not point to the V28 manifest's original qualification")

        from src.runners.task40_v20_stage_runner import _load_matching_v28_native_qualification

        checked = _load_matching_v28_native_qualification(
            repo_root=self.repo_root,
            manifest_path=manifest_path,
            manifest=manifest,
            expected_pattern_path=pattern_path,
            expected_pattern_sha256=pattern_sha,
            donor_identity_sha256=str(old.get("donor_identity_sha256", "")),
            input_sha256=str(old["input_sha256"]),
            physical_model_sha256=str(legacy_identity["physical_model_sha256"]),
            run_id=str(old["run_id"]),
            campaign_window_sha256=execution["window_sha256"],
            mode_manifest_sha256=str(legacy_identity["mode_manifest_sha256"]),
            ordered_mode_key_sha256=str(old["ordered_mode_key_sha256"]),
            sha256_file=_sha256_file,
            path_resolver=self.path_resolver,
        )
        if (
            checked is None
            or checked[0].resolve() != qualification_path.resolve()
            or _sha256_file(checked[0]) != qualification_sha
            or checked[1].get("status") != "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
            or qualification.get("schema") != "task40extra.review_v28_q0_native_qualification.v1"
        ):
            raise ValueError("existing V28 verifier rejected the immutable q0 native PASS")

        donor = fill.get("donor_identity")
        producer = donor.get("producer_identity") if isinstance(donor, Mapping) else None
        if not isinstance(producer, Mapping):
            raise ValueError("V28 donor manifest omits its producer payload identity")
        payloads = {
            Path(str(row.get("path", ""))).name: row
            for row in producer.get("payloads", [])
            if isinstance(row, Mapping)
        }
        map_record = payloads.get("v25_selected_q0_map.npz")
        h_record = payloads.get("v25_selected_q0_local_H_p.npy")
        lookup_record = payloads.get("v25_selected_q0_original_to_active_int32.npy")
        if not all(isinstance(row, Mapping) for row in (map_record, h_record, lookup_record)):
            raise ValueError("V28 donor omits its original q0 map, original H, or active lookup")
        producer_root = self._resolve(
            producer.get("producer_run_directory", "")
        )
        map_path = self._resolve(map_record.get("path", ""), base=producer_root)
        h_path = self._resolve(h_record.get("path", ""), base=producer_root)
        lookup_path = self._resolve(lookup_record.get("path", ""), base=producer_root)
        for path, record in ((map_path, map_record), (h_path, h_record), (lookup_path, lookup_record)):
            if (
                not path.is_relative_to(producer_root)
                or not path.is_file()
                or type(record.get("bytes")) is not int
                or path.stat().st_size != record["bytes"]
            ):
                raise ValueError("V28 q0 donor map/H path or size changed")
        self.allocation_gate(
            "task40_v30_legacy_q0_map_h_identity",
            {
                "additional_payload_bytes": int(map_record["bytes"] + h_record["bytes"]),
                "workspace_bytes": int(map_record["bytes"] + 16 * 1024 * 1024),
                "map_bytes": int(map_record["bytes"]),
                "original_h_bytes": int(h_record["bytes"]),
                "active_lookup_bytes": int(lookup_record["bytes"]),
                "mapping_owner_bytes": int(
                    sum(np.asarray(value).nbytes for value in index_mapping.values())
                    if isinstance(index_mapping, Mapping)
                    else 0
                ),
                "full_payload_hashes_after_gate": True,
                "comparison": "exact complex128 H and exact mapped CSR values",
            },
        )
        if any(
            _sha256_file(path) != record.get("sha256")
            for path, record in ((map_path, map_record), (h_path, h_record), (lookup_path, lookup_record))
        ):
            raise ValueError("V28 q0 original map/H/active-lookup payload file hash changed")

        from scipy.sparse import load_npz

        donor_map = _require_csr(load_npz(map_path).tocsr(), "V28 donor q0 map")
        donor_h = np.load(h_path, mmap_mode="r", allow_pickle=False)
        donor_lookup = np.load(lookup_path, mmap_mode="r", allow_pickle=False)
        if (
            donor_h.dtype != np.dtype(np.complex128)
            or donor_h.ndim != 1
            or current_h.dtype != np.dtype(np.complex128)
            or current_h.ndim != 1
            or not np.array_equal(donor_h, current_h)
        ):
            raise ValueError("V28 original local-H differs from the runtime complex128 H, without rounding")
        h_sha = _array_sha256(donor_h, np.dtype(np.complex128), "V28 original H")
        if h_sha != identity["original_h_sha256"]:
            raise ValueError("V28 original-H canonical content hash differs from runtime identity")
        if (
            donor_lookup.dtype != np.dtype(np.int32)
            or current_active_lookup.dtype != np.dtype(np.int32)
            or donor_lookup.shape != current_active_lookup.shape
            or not np.array_equal(donor_lookup, current_active_lookup)
        ):
            raise ValueError("V28 original-to-active lookup differs from current FE/MPC numbering")
        donor_q_map_sha = self._compare_q0_map(donor_map, current_q_map, index_mapping)
        return {
            "qualification_kind": "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED",
            "legacy_source_identity": {
                "source_sha": matrix_source["source_sha"],
                "window_sha256": matrix_source["window_sha256"],
            },
            "legacy_qualification_sha256": manifest_sha,
            "legacy_native_qualification_sha256": qualification_sha,
            "current_execution_identity": dict(execution),
            "runtime_q0_map_sha256": identity["q_map_sha256"],
            "donor_q0_map_sha256": donor_q_map_sha,
            "original_h_sha256": h_sha,
        }

    @staticmethod
    def _compare_q0_map(
        donor: sparse.csr_matrix,
        current: sparse.csr_matrix,
        mapping: Mapping[str, np.ndarray] | None,
    ) -> str:
        _require_csr(donor, "V28 donor q0 map")
        _require_csr(current, "runtime q0 map")
        if donor.shape != current.shape:
            raise ValueError("V28/current q0 map shape differs")
        if mapping is None:
            if not (
                np.array_equal(donor.indptr, current.indptr)
                and np.array_equal(donor.indices, current.indices)
                and np.array_equal(donor.data, current.data)
            ):
                raise ValueError("different q0 FE numbering requires explicit row/column identity mapping")
            return _csr_sha256(donor)
        required = {
            "row_keys_current",
            "row_keys_donor",
            "rows_current_to_donor",
            "column_keys_current",
            "column_keys_donor",
            "columns_current_to_donor",
        }
        if set(mapping) != required:
            raise ValueError("explicit q0 index map must contain both axes' keys and bijections")
        rows = np.asarray(mapping["rows_current_to_donor"])
        cols = np.asarray(mapping["columns_current_to_donor"])
        for axis, current_keys, donor_keys, indices, axis_n in (
            ("row", mapping["row_keys_current"], mapping["row_keys_donor"], rows, donor.shape[0]),
            ("column", mapping["column_keys_current"], mapping["column_keys_donor"], cols, donor.shape[1]),
        ):
            current_keys, donor_keys = np.asarray(current_keys), np.asarray(donor_keys)
            if (
                current_keys.dtype.kind not in "iu"
                or donor_keys.dtype.kind not in "iu"
                or indices.dtype.kind not in "iu"
                or current_keys.shape != (axis_n,)
                or donor_keys.shape != (axis_n,)
                or indices.shape != (axis_n,)
                or np.any(indices < 0)
                or np.any(indices >= axis_n)
                or not np.array_equal(current_keys, donor_keys[indices])
                or len(np.unique(indices)) != axis_n
            ):
                raise ValueError(f"q0 {axis} map is not a one-to-one stable identity mapping")
        row_to_donor = rows.astype(np.int64, copy=False)
        col_to_donor = cols.astype(np.int64, copy=False)
        donor_to_current = np.empty(donor.shape[0], dtype=np.int64)
        donor_to_current[row_to_donor] = np.arange(current.shape[0], dtype=np.int64)
        for donor_row, current_row in enumerate(donor_to_current):
            ds, de = int(donor.indptr[donor_row]), int(donor.indptr[donor_row + 1])
            cs, ce = int(current.indptr[current_row]), int(current.indptr[current_row + 1])
            current_columns = col_to_donor[current.indices[cs:ce]]
            order = np.argsort(current_columns, kind="stable")
            if not (
                np.array_equal(current_columns[order], donor.indices[ds:de])
                and np.array_equal(current.data[cs:ce][order], donor.data[ds:de])
            ):
                raise ValueError(f"q0 map differs after explicit index mapping at row {donor_row}")
        return _csr_sha256(donor)

    def _bound_json(self, record: Mapping[str, Any], label: str) -> Path:
        path = self._resolve(record.get("path", ""))
        expected = _require_sha(record.get("sha256"), f"{label}.sha256")
        if not path.is_file() or _sha256_file(path) != expected:
            raise ValueError(f"{label} is missing or its hash changed")
        return path

