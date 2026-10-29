"""Capture selected V19 native rank-1 cell terms from DOLFINx forms.

This adapter follows the DOLFINx cell-vector kernel order. It never assembles a
rank-2 tensor, factors a matrix, solves a system, or forms a global vector.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
import argparse
import hashlib
import importlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Any

import numpy as np


V19_CAPTURE_SCHEMA = "task41.p0.v19.selected_native_rank1_capture.v1"
V19_SELECTED_CELLS = (7873, 8014)
V19_COLUMNS = (0, 1)
V19_MAX_PACKED_COEFFICIENT_BYTES = 12 * 1024**3
V19_MAX_NEW_EVIDENCE_BYTES = 16 * 1024**2
V19_MAX_CUMULATIVE_RAW_BYTES = 16 * 1024**3
V19_MIN_FREE_BYTES = 2 * 1024**3
V19_MAX_PLANNED_WORKING_BYTES = 16 * 1024**3
V19_ORIGINAL_PRODUCER_SOURCE_SHA = "afbe91e5947ed18fb74d7105097e129c1b8b4cc7"
V19_ORIGINAL_DONOR_RUN = "20261019T053402.514018Z"
V19_ORIGINAL_RECOVERY_MANIFEST_SHA256 = (
    "f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465"
)
SOURCE_BINDINGS: dict[str, tuple[str, str]] = {
    "v17_report": (
        "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/"
        "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54/"
        "selected_incident_replay/attempt04/task41_p0_v17_selected_two_cell_worker.json",
        "4e6fce6680a0bb304ed0370542f8b5c6003d39940d94ff3e54f19322aeb1709b",
    ),
    "v18_compact": (
        "docs/task41extra_phi90_p50x50_g17x20/outcomes/v18_closeout/"
        "v18_saved_jz_compact.json",
        "5934702837f9400a7c6c990e1c157b57783e06cc399e216e502f1be746047794",
    ),
    "v3_donor_closeout": (
        "docs/task41extra_phi90_p50x50_g17x20/outcomes/"
        "b0_v3_full_action_failure_20261019.json",
        "3c3f24db2f9f13f4dde80eb0e58ac2b1655ad98c4790c5e83e111107b919bcc6",
    ),
}
V19_PROGRESS_SCHEMA = "task41.p0.v19.selected_native_rank1_progress.v1"
V19_TERM_ARCHIVE_SCHEMA = "task41.p0.v19.native_rank1_term_archive.v1"
V19_RECEIPT_SCHEMA = "task41.p0.v19.selected_native_rank1_worker_receipt.v1"
_UFCX_INTEGRAL_OFFSET_COUNT = 6
_TERM_ARRAY_FIELDS = (
    "raw_kernel_output",
    "oriented_test_vector",
    "packed_coefficient_row",
    "packed_constants",
    "local_dofs",
    "original_dofs",
    "geometry_dof_indices",
    "geometry_coordinates",
)
_TERM_INPUT_ARRAY_FIELDS = frozenset({
    "packed_coefficient_row",
    "packed_constants",
    "local_dofs",
    "original_dofs",
    "geometry_dof_indices",
    "geometry_coordinates",
})


def _read_ffi_ints(ffi: Any, pointer: Any, count: int, label: str) -> tuple[int, ...]:
    """Read a CFFI int pointer using its caller-known length."""
    count = int(count)
    if count < 0:
        raise ValueError(f"{label} length is negative")
    if count == 0:
        return ()
    if pointer == ffi.NULL:
        raise ValueError(f"{label} pointer is NULL")
    return tuple(int(pointer[index]) for index in range(count))


def _ufcx_cell_integrals(compiled_form: Any) -> tuple[int, tuple[int, ...]]:
    """Return C++ cell-integral start and physical UFCx ids, with explicit reads."""
    ufcx_form = compiled_form.ufcx_form
    module = compiled_form.module
    if isinstance(ufcx_form, list) or isinstance(module, list):
        raise NotImplementedError("V19 capture requires a single cell topology")
    ffi = module.ffi
    offsets = _read_ffi_ints(
        ffi,
        ufcx_form.form_integral_offsets,
        _UFCX_INTEGRAL_OFFSET_COUNT,
        "UFCx form_integral_offsets",
    )
    if offsets[0] != 0 or any(right < left for left, right in zip(offsets, offsets[1:])):
        raise ValueError("UFCx form integral offsets are malformed")
    total = offsets[-1]
    ids = _read_ffi_ints(
        ffi, ufcx_form.form_integral_ids, total, "UFCx form_integral_ids"
    )
    cell_start, cell_stop = offsets[0], offsets[1]
    if not 0 <= cell_start <= cell_stop <= len(ids):
        raise ValueError("UFCx cell-integral range is malformed")
    return cell_start, ids[cell_start:cell_stop]


def _integral_index_domain(
    compiled_form: Any, integral_type_cell: Any, integral_index: int
) -> np.ndarray:
    """Read the exact DOLFINx entity sequence for a C++ integral index."""
    domains = getattr(compiled_form._cpp_object, "domains", None)
    if domains is None:
        raise TypeError("DOLFINx Form.domains(type, integral_index) is unavailable")
    entities = np.asarray(
        domains(integral_type_cell, int(integral_index)), dtype=np.int32
    )
    if entities.ndim != 1 or np.any(entities < 0):
        raise ValueError("V19 native capture requires nonnegative cell entity lists")
    return entities


def _coefficient_stride(
    compiled_form: Any, *, ffi: Any, ufcx_form: Any
) -> tuple[int, tuple[int, ...], tuple[int, ...]]:
    """Derive pack stride from compiled coefficients' original finite elements."""
    count = int(ufcx_form.num_coefficients)
    original_positions = _read_ffi_ints(
        ffi,
        ufcx_form.original_coefficient_positions,
        count,
        "UFCx original_coefficient_positions",
    )
    if any(position < 0 for position in original_positions) or len(
        set(original_positions)
    ) != count:
        raise ValueError("UFCx original coefficient positions are invalid or duplicated")

    coefficients = compiled_form._cpp_object.coefficients
    if callable(coefficients):
        coefficients = coefficients()
    coefficients = tuple(coefficients)
    if len(coefficients) != count:
        raise ValueError("DOLFINx coefficient count differs from UFCx num_coefficients")

    compiled_dimensions: list[int] = []
    for coefficient in coefficients:
        function_space = coefficient.function_space
        function_space = function_space() if callable(function_space) else function_space
        element = function_space.element
        element = element() if callable(element) else element
        dimension = int(element.space_dimension)
        if dimension <= 0:
            raise ValueError("original coefficient finite-element dimension is invalid")
        compiled_dimensions.append(dimension)
    # DOLFINx builds Form.coefficients() in UFCx compiled order using
    # original_coefficient_positions. Positions need not be a dense permutation
    # when UFL removes an unused coefficient; the C++ packer stride is the
    # finite-element dimensions of the compiled coefficient sequence itself.
    compiled_dims = tuple(compiled_dimensions)
    return sum(compiled_dims), original_positions, compiled_dims


def _require_finite_array(values: np.ndarray, label: str) -> np.ndarray:
    array = np.asarray(values)
    if not np.isfinite(array).all():
        raise ValueError(f"V19 {label} contains non-finite values")
    return array


def _array_identity(values: np.ndarray) -> dict[str, Any]:
    """Return a small deterministic identity for one contiguous numerical input."""
    array = np.ascontiguousarray(np.asarray(values))
    header = json.dumps(
        {"dtype": array.dtype.str, "shape": list(array.shape)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    hasher = hashlib.sha256()
    hasher.update(header)
    hasher.update(b"\0")
    hasher.update(memoryview(array).cast("B"))
    digest = hasher.hexdigest()
    return {
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "sha256": digest,
    }


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _compiled_integral_inventory(
    compiled_form: Any,
    integral_type_cell: Any,
    selected_cells: Sequence[int],
) -> dict[str, Any]:
    """Freeze the real C++/UFCx cell-integral and selected-entity mapping."""
    cells = tuple(int(value) for value in selected_cells)
    if not cells or len(set(cells)) != len(cells) or any(value < 0 for value in cells):
        raise ValueError("V19 integral inventory requires unique selected cells")
    cell_start, physical_ids = _ufcx_cell_integrals(compiled_form)
    cpp_form = compiled_form._cpp_object
    cpp_count = int(cpp_form.num_integrals(integral_type_cell, 0))
    if cpp_count <= 0 or cpp_count != len(physical_ids):
        raise ValueError("UFCx physical integral ids and C++ integral-index count differ")
    if set(cpp_form.integral_types) != {integral_type_cell}:
        raise ValueError("V19 native volume form contains non-cell integrals")
    ffi = compiled_form.module.ffi
    selected = set(cells)
    seen: set[int] = set()
    records: list[dict[str, Any]] = []
    invocation_count = 0
    for integral_index in range(cpp_count):
        entities = _integral_index_domain(compiled_form, integral_type_cell, integral_index)
        kernel = compiled_form.ufcx_form.form_integrals[cell_start + integral_index]
        if getattr(kernel, "tabulate_tensor_complex128", ffi.NULL) == ffi.NULL:
            raise TypeError("V19 rank-1 form has no complex128 cell kernel")
        positions = [
            int(position)
            for position, value in enumerate(entities)
            if int(value) in selected
        ]
        entity_order = [int(entities[position]) for position in positions]
        seen.update(entity_order)
        invocation_count += len(positions)
        records.append({
            "cpp_integral_index": integral_index,
            "ufcx_kernel_position": cell_start + integral_index,
            "ufcx_physical_integral_id": int(physical_ids[integral_index]),
            "domain_entity_count": int(entities.size),
            "domain_entity_ids_sha256": _array_identity(entities)["sha256"],
            "selected_entity_positions": positions,
            "selected_entity_cell_order": entity_order,
        })
    if seen != selected:
        raise ValueError("V19 compiled cell-integral domains omit selected cells")
    return {
        "cpp_integral_index_order": list(range(cpp_count)),
        "ufcx_cell_integral_start": int(cell_start),
        "ufcx_physical_integral_ids": [int(value) for value in physical_ids],
        "kernel_inventory_from_compiled_form": records,
        "expected_selected_kernel_invocations": invocation_count,
    }


def _runtime_abi_identity() -> dict[str, Any]:
    """Describe the active Python, FEM, scalar/index and MPI ABI stack."""
    from mpi4py import MPI
    from petsc4py import PETSc

    module_names = (
        "dolfinx",
        "basix",
        "ufl",
        "ffcx",
        "petsc4py",
        "slepc4py",
        "mpi4py",
    )
    modules: dict[str, Any] = {}
    for name in module_names:
        module = importlib.import_module(name)
        modules[name] = {
            "version": str(getattr(module, "__version__", "UNKNOWN")),
            "module_file": str(Path(module.__file__).resolve())
            if getattr(module, "__file__", None)
            else None,
        }
    petsc_identity = {
        "scalar_type": np.dtype(PETSc.ScalarType).str,
        "int_type": np.dtype(PETSc.IntType).str,
        "version": list(PETSc.Sys.getVersion()),
    }
    try:
        slepc_module = importlib.import_module("slepc4py.SLEPc")
        petsc_identity["slepc_version"] = list(slepc_module.Sys.getVersion())
    except (ImportError, AttributeError, TypeError):
        petsc_identity["slepc_version"] = "UNAVAILABLE"
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "platform": platform.platform(),
        "modules": modules,
        "petsc": petsc_identity,
        "mpi_library": str(MPI.Get_library_version()).strip(),
        "mpi_world_size": int(MPI.COMM_WORLD.Get_size()),
    }


def _canonical_form_code(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"encoding": "bytes-hex", "value": value.hex()}
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence):
        return [_canonical_form_code(item) for item in value]
    raise TypeError("V19 compiled Form.code contains an unsupported value")


def _module_artifact_identity(module: Any) -> dict[str, Any]:
    module_name = str(getattr(module, "__name__", type(module).__qualname__))
    raw_path = getattr(module, "__file__", None)
    if not raw_path:
        return {
            "module_name": module_name,
            "module_file": None,
            "module_file_sha256": None,
            "module_file_status": "NOT_EXPOSED",
        }
    try:
        path = Path(str(raw_path)).resolve(strict=True)
        if not path.is_file():
            raise OSError("module path is not a file")
        return {
            "module_name": module_name,
            "module_file": str(path),
            "module_file_sha256": sha256_file(path),
            "module_file_status": "HASHED",
        }
    except OSError:
        return {
            "module_name": module_name,
            "module_file": str(raw_path),
            "module_file_sha256": None,
            "module_file_status": "UNAVAILABLE",
        }


def _native_action_identity(
    action: Any,
    *,
    component: str,
    integral_type_cell: Any,
    selected_cells: Sequence[int],
    abi_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind a real split action's UFL, generated code, module, JIT and ABI."""
    if component not in {"curl", "material_mass"}:
        raise ValueError("V19 native action identity has an unknown component")
    compiled_form = getattr(action, "_action_form", None)
    if compiled_form is None or getattr(action, "_local_kernel", None) is not None:
        raise ValueError("V19 identity requires the production compiled native Form")
    signatures: dict[str, str] = {}
    for name, form in (
        ("bilinear", getattr(action, "_bilinear_form", None)),
        ("rank1_action", getattr(action, "_action_ufl", None)),
    ):
        signature_method = getattr(form, "signature", None)
        signature = signature_method() if callable(signature_method) else None
        if not isinstance(signature, str) or not signature:
            raise ValueError(f"V19 {component} {name} UFL signature is unavailable")
        signatures[name] = signature
    code = getattr(compiled_form, "code", None)
    if code is None:
        raise ValueError(f"V19 {component} compiled Form does not expose generated C code")
    canonical_code = _canonical_form_code(code)
    if canonical_code == [] or canonical_code == "":
        raise ValueError(f"V19 {component} compiled Form generated C code is empty")
    identity = {
        "component": component,
        "ufl_signatures": signatures,
        "ufl_signatures_sha256": _json_sha256(signatures),
        "ffcx_generated_code_sha256": _json_sha256(canonical_code),
        "compiled_module": _module_artifact_identity(compiled_form.module),
        "jit_options": dict(getattr(action, "_jit_options", {}) or {}),
        "abi_identity": dict(abi_identity),
        "integral_inventory": _compiled_integral_inventory(
            compiled_form, integral_type_cell, selected_cells
        ),
    }
    identity["identity_sha256"] = _json_sha256(identity)
    return identity


def _validate_identity_checksum(identity: Mapping[str, Any]) -> None:
    payload = dict(identity)
    claimed = payload.pop("identity_sha256", None)
    if not isinstance(claimed, str) or claimed != _json_sha256(payload):
        raise ValueError("V19 native kernel identity checksum differs")


def _validate_v19_saved_vector_layout(
    columns: Sequence[Mapping[str, Any]],
    known_bindings: Mapping[str, Mapping[str, Any]],
    *,
    trace_rows: int,
    storage_rows: int,
    selected_row: int,
    selected_original_row: int,
) -> np.ndarray:
    """Close the real V16 loader output to the V19 source-column layouts."""
    if len(columns) != 2 or set(known_bindings) != {"0", "1"}:
        raise ValueError("V19 saved-vector loader must provide exactly two pinned columns")
    active_maps: list[np.ndarray] = []
    for column in V19_COLUMNS:
        record = columns[column]
        if record.get("column") != column:
            raise ValueError("V19 saved-vector loader changed the pinned source-column order")
        active_rows = np.asarray(record.get("active_original_rows"))
        if (
            active_rows.shape != (int(trace_rows),)
            or active_rows.dtype != np.dtype(np.int64)
            or not 0 <= int(selected_row) < active_rows.size
            or int(active_rows[int(selected_row)]) != int(selected_original_row)
        ):
            raise ValueError("V19 V3 active/original row map differs from the pinned V16 layout")
        active_maps.append(active_rows)
        values = np.asarray(record.get("known_field"))
        binding = known_bindings[str(column)]
        bound_shape = tuple(int(value) for value in binding.get("shape", ()))
        bound_dtype = np.dtype(binding.get("dtype"))
        expected_bytes = int(binding.get("bytes", -1))
        if (
            values.shape != (int(storage_rows),)
            or values.dtype != np.dtype(np.complex128)
            or bound_shape != values.shape
            or bound_dtype != values.dtype
            or expected_bytes != values.nbytes
        ):
            raise ValueError(f"V19 original known field column {column} layout differs")
    if not np.array_equal(active_maps[0], active_maps[1]):
        raise ValueError("V19 pinned source columns disagree on the active/original row map")
    return active_maps[0]


@contextmanager
def _destroy_split_action_on_exit(action: Any) -> Any:
    """Release both compiled component forms on success and every failure path."""
    try:
        yield action
    finally:
        action.destroy()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError(f"V19 checkpoint cannot replace a symlink: {path}")
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"V19 checkpoint temporary already exists: {temporary}")
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.replace(temporary, path)
        else:
            os.rename(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"V19 evidence already exists; refusing to overwrite: {path}")
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"V19 evidence temporary already exists: {temporary}")
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _term_archive_path(term_directory: Path, term: Mapping[str, Any]) -> Path:
    component = str(term.get("component", ""))
    column = term.get("column")
    cell = term.get("cell_index")
    integral_index = term.get("cpp_integral_index")
    if (
        component not in {"curl", "material_mass"}
        or type(column) is not int or column not in V19_COLUMNS
        or type(cell) is not int or cell not in V19_SELECTED_CELLS
        or type(integral_index) is not int or integral_index < 0
    ):
        raise ValueError("V19 term identity has an invalid bounded name")
    return term_directory / (
        f"{component}_col{column}_cell{cell}_integral{integral_index:03d}.npz"
    )


def _archive_identity_and_refs(
    archive_path: Path,
    *,
    output_directory: Path,
    expected_identity: Mapping[str, Any],
    expected_archive_sha256: str | None = None,
    allow_orphan_atomic_archive: bool = False,
) -> dict[str, Any]:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("V19 saved term archive is missing or a symlink")
    if expected_archive_sha256 is None and not allow_orphan_atomic_archive:
        raise ValueError("V19 archive reopen requires a checkpoint SHA; orphan adoption must be explicit")
    if expected_archive_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", expected_archive_sha256) is None:
        raise ValueError("V19 checkpoint archive SHA-256 is malformed")
    digest = sha256_file(archive_path)
    size = int(archive_path.stat().st_size)
    if expected_archive_sha256 is not None and digest != expected_archive_sha256:
        raise ValueError("V19 term archive SHA-256 differs from its progress checkpoint")
    try:
        with np.load(archive_path, allow_pickle=False) as saved:
            metadata = json.loads(str(saved["term_metadata"].item()))
            if (
                metadata.get("schema") != V19_TERM_ARCHIVE_SCHEMA
                or metadata.get("term_identity") != dict(expected_identity)
                or set(saved.files) != {"term_metadata", *_TERM_ARRAY_FIELDS}
            ):
                raise ValueError("V19 archive identity or field set differs")
            stored_identity = dict(metadata["term_identity"])
            stored_identity_sha256 = stored_identity.pop("identity_sha256", None)
            if stored_identity_sha256 != _json_sha256(stored_identity):
                raise ValueError("V19 archive term identity digest is malformed")
            expected_input_identities = expected_identity.get("array_identities")
            stored_capture_identities = metadata.get("capture_array_identities")
            if (
                not isinstance(expected_input_identities, Mapping)
                or not isinstance(stored_capture_identities, Mapping)
                or set(stored_capture_identities) != set(_TERM_ARRAY_FIELDS)
            ):
                raise ValueError("V19 archive omits its bound input/output array identities")
            if set(expected_input_identities) != _TERM_INPUT_ARRAY_FIELDS:
                raise ValueError("V19 term identity input-array inventory differs")
            references: dict[str, Any] = {}
            actual_identities: dict[str, Any] = {}
            for field in _TERM_ARRAY_FIELDS:
                values = np.asarray(saved[field])
                actual = _array_identity(values)
                if stored_capture_identities.get(field) != actual:
                    raise ValueError(f"V19 archive member {field} differs from its embedded identity")
                if field in expected_input_identities and expected_input_identities[field] != actual:
                    raise ValueError(f"V19 archive member {field} differs from the fresh native inputs")
                actual_identities[field] = actual
                references[field] = {
                    "path": archive_path.relative_to(output_directory).as_posix(),
                    "member": field,
                    "sha256": digest,
                    "bytes": size,
                    "dtype": values.dtype.str,
                    "shape": list(values.shape),
                }
            status = metadata.get("capture_status")
            error = metadata.get("capture_error")
            finite_output = all(
                np.isfinite(np.asarray(saved[field])).all()
                for field in ("raw_kernel_output", "oriented_test_vector")
            )
            if status == "CAPTURED_FINITE":
                if error is not None or not finite_output:
                    raise ValueError("V19 finite archive status contradicts its output arrays")
            elif status == "CAPTURE_FAILED_RETAINED":
                if not isinstance(error, str) or not error or finite_output:
                    raise ValueError("V19 retained-negative archive status lacks a non-finite output/error")
            else:
                raise ValueError("V19 archive has an unknown capture status")
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"V19 term archive cannot be safely reopened: {archive_path.name}: {exc}"
        ) from exc
    return {
        "array_artifacts": references,
        "archive_sha256": digest,
        "archive_bytes": size,
        "capture_status": status,
        "capture_error": error,
        "archive_binding_status": (
            "CHECKPOINT_SHA256_VERIFIED"
            if expected_archive_sha256 is not None
            else "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY"
        ),
    }


def _write_term_archive(
    term: Mapping[str, Any], *, term_directory: Path, output_directory: Path
) -> dict[str, Any]:
    archive_path = _term_archive_path(term_directory, term)
    if archive_path.exists() or archive_path.is_symlink():
        # A completed atomic archive may have been written just before a process
        # died while advancing the JSON checkpoint. It can be adopted only when
        # every embedded identity and array field closes exactly.
        return _archive_identity_and_refs(
            archive_path,
            output_directory=output_directory,
            expected_identity=term["term_identity"],
            allow_orphan_atomic_archive=True,
        )
    temporary = archive_path.with_name(archive_path.name + f".{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"V19 partial archive exists and is retained: {temporary}")
    arrays = {
        field: np.ascontiguousarray(np.asarray(term[field]))
        for field in _TERM_ARRAY_FIELDS
    }
    metadata = {
        "schema": V19_TERM_ARCHIVE_SCHEMA,
        "term_identity": dict(term["term_identity"]),
        "capture_status": term.get("capture_status"),
        "capture_error": term.get("capture_error"),
        "capture_array_identities": {
            field: _array_identity(values) for field, values in arrays.items()
        },
    }
    with temporary.open("xb") as stream:
        np.savez(stream, term_metadata=np.asarray(json.dumps(metadata, sort_keys=True)), **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, archive_path)
        temporary.unlink()
        parent_fd = os.open(term_directory, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return _archive_identity_and_refs(
        archive_path,
        output_directory=output_directory,
        expected_identity=term["term_identity"],
        expected_archive_sha256=sha256_file(archive_path),
    )


def _write_or_reopen_mpc_archive(
    *,
    archive_path: Path,
    output_directory: Path,
    support: Mapping[str, Any],
    maps: Mapping[str, np.ndarray],
    state: dict[str, Any],
    progress_path: Path,
) -> dict[str, Any]:
    """Persist selected support plus hashes for the full in-memory maps."""
    saved_binding = state.get("mpc_restriction_archive")
    created_this_call = False
    if archive_path.is_symlink():
        raise ValueError("V19 MPC archive cannot be a symlink")
    if not archive_path.exists():
        if saved_binding is not None:
            raise ValueError("V19 progress refers to a missing MPC archive")
        payload = {
            "schema": "task41.p0.v19.mpc_restriction_summary.v1",
            "support": dict(support),
        }
        _write_new_json(archive_path, payload)
        created_this_call = True

    digest = sha256_file(archive_path)
    if saved_binding is not None and (
        not isinstance(saved_binding, Mapping)
        or saved_binding.get("sha256") != digest
        or saved_binding.get("array_identities") != support.get("mpc_map_array_identities")
    ):
        raise ValueError("V19 MPC archive differs from its progress checkpoint")
    try:
        stored_payload = json.loads(archive_path.read_text(encoding="utf-8"))
        if stored_payload != {
            "schema": "task41.p0.v19.mpc_restriction_summary.v1",
            "support": dict(support),
        }:
            raise ValueError("V19 MPC archive summary differs from the live split action")
        identities = dict(support["mpc_map_array_identities"])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("V19 MPC archive cannot be safely reopened") from exc
    if saved_binding is None and created_this_call:
        binding_status = "NEW_ATOMIC_ARCHIVE_VERIFIED"
    elif saved_binding is None:
        binding_status = "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY"
    else:
        binding_status = "CHECKPOINT_SHA256_VERIFIED"
    binding = {
        "path": archive_path.relative_to(output_directory).as_posix(),
        "sha256": digest,
        "bytes": int(archive_path.stat().st_size),
        "array_identities": identities,
        "binding_status": binding_status,
    }
    if archive_path.stat().st_size > V19_MAX_NEW_EVIDENCE_BYTES:
        raise OSError("V19 compact MPC support summary exceeds the 16 MiB evidence cap")
    if saved_binding is None:
        state["mpc_restriction_archive"] = binding
        _checkpoint_progress(progress_path, state)
    elif saved_binding.get("binding_status") != binding_status:
        # An adopted orphan is upgraded to checkpoint-bound on its next reopen.
        state["mpc_restriction_archive"] = binding
        _checkpoint_progress(progress_path, state)
    return binding


def _v19_live_preflight(
    *,
    contract: Mapping[str, Any],
    fixed_window: Any,
    output_directory: Path,
    saved_diagnostics_budget_check: Callable[..., Mapping[str, Any]],
    stage: str,
    planned_working_set_bytes: int,
) -> dict[str, Any]:
    """Reuse the campaign's disk/accounting and live resource admission gates."""
    import time

    from src.runners.task40_v20_stage_runner import _resource_snapshot
    from src.solvers.task40_v22_operator_probe import _resource_admission
    from src.runners.workflow_timebase import clock_sample

    if not callable(saved_diagnostics_budget_check):
        raise TypeError("V19 must reuse the service's saved-diagnostics cumulative-byte gate")
    plan = int(planned_working_set_bytes)
    if not 0 <= plan <= V19_MAX_PLANNED_WORKING_BYTES:
        raise MemoryError("V19 planned working set exceeds its 16 GiB fixed ceiling")
    budget = saved_diagnostics_budget_check(final=False)
    if not isinstance(budget, Mapping):
        raise ValueError("V19 saved-diagnostics budget check returned no accounting")
    required_budget_values = {
        "recorded_cumulative_raw_artifact_bytes",
        "bound_raw_artifact_bytes_stat_deduplicated",
        "window_output_tree_bytes",
        "reserved_remaining_new_evidence_bytes",
        "cumulative_raw_artifact_limit_bytes",
        "free_space_bytes",
        "free_space_floor_bytes",
    }
    if (
        budget.get("status") != "PRE_CHECKER_ADMITTED"
        or not required_budget_values.issubset(budget)
        or budget.get("cumulative_raw_artifact_limit_bytes") != V19_MAX_CUMULATIVE_RAW_BYTES
        or budget.get("free_space_floor_bytes") != V19_MIN_FREE_BYTES
        or budget.get("window_wide_new_evidence_limit_bytes") != V19_MAX_NEW_EVIDENCE_BYTES
        or budget.get("free_space_bytes", -1) < V19_MIN_FREE_BYTES
        or budget.get("reserved_remaining_new_evidence_bytes", V19_MAX_NEW_EVIDENCE_BYTES + 1)
        > V19_MAX_NEW_EVIDENCE_BYTES
    ):
        raise OSError(f"V19 existing cumulative evidence gate failed at {stage}")
    actual_new_bytes = _output_tree_bytes(output_directory)
    if (
        budget.get("current_invocation_bytes", actual_new_bytes) < actual_new_bytes
        or budget.get("window_output_tree_bytes", actual_new_bytes) < actual_new_bytes
        or actual_new_bytes > V19_MAX_NEW_EVIDENCE_BYTES
    ):
        raise OSError("V19 saved-diagnostics output byte accounting is stale or over cap")

    resources = contract.get("resources")
    if not isinstance(resources, Mapping):
        raise ValueError("V19 contract omits the exact process resource limits")
    baseline = _resource_admission(
        f"{stage}:baseline",
        0,
        resource_sample=_resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
        host_reserve_bytes=int(resources["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=0,
    )
    cgroup = baseline.get("current_process_cgroup", {})
    if (
        not isinstance(cgroup, Mapping)
        or cgroup.get("dedicated_job_cgroup") is not True
        or cgroup.get("readable") is not True
        or cgroup.get("memory_limit_bytes") != resources["task_memory_max_bytes"]
        or cgroup.get("swap_current_bytes") != 0
    ):
        raise RuntimeError(f"V19 {stage}: dedicated contracted zero-swap task cgroup is unavailable")
    tree_rss = baseline.get("current_process_tree_rss_bytes")
    if type(tree_rss) is not int or tree_rss < 0:
        raise RuntimeError(f"V19 {stage}: process-tree RSS sample is not authoritative")
    additional = max(0, plan - tree_rss)
    admission = _resource_admission(
        stage,
        additional,
        resource_sample=_resource_snapshot,
        require_task_cgroup=True,
        explicit_process_tree_cap_bytes=int(resources["task_memory_max_bytes"]),
        host_reserve_bytes=int(resources["host_reserve_bytes"]),
        task_cgroup_reserve_bytes=0,
    )
    current = clock_sample(include_boot_id=True)
    if current.get("boot_id") != fixed_window.anchor.get("boot_id"):
        raise RuntimeError("V19 fixed-window boot identity changed during worker preparation")
    seconds_remaining = (fixed_window.deadline_utc_ns - int(current["utc_ns"])) / 1e9
    if seconds_remaining <= float(fixed_window.closeout_seconds):
        raise TimeoutError("V19 numerical work would consume the fixed closeout reserve")
    observed_rss = _current_rss_bytes()
    if observed_rss > V19_MAX_PLANNED_WORKING_BYTES or observed_rss > plan:
        raise MemoryError(f"V19 current worker RSS exceeds its planned stage budget at {stage}")
    return {
        "stage": stage,
        "saved_diagnostics_disk_budget": dict(budget),
        "resource_admission": admission,
        "planned_working_set_bytes": plan,
        "fixed_window_seconds_remaining": seconds_remaining,
        "closeout_reserve_seconds": fixed_window.closeout_seconds,
        "checked_at_monotonic": time.monotonic(),
    }


def _read_pinned_json(root: Path, key: str) -> tuple[Path, dict[str, Any]]:
    relative, expected_sha256 = SOURCE_BINDINGS[key]
    raw_path = root / relative
    if raw_path.is_symlink():
        raise ValueError(f"V19 {key} source cannot be a symlink")
    path = raw_path.resolve(strict=True)
    if not path.is_relative_to(root) or path.stat().st_size > V19_MAX_NEW_EVIDENCE_BYTES:
        raise ValueError(f"V19 {key} source escaped its bounded path/size")
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"V19 {key} source SHA-256 differs from its frozen binding")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"V19 {key} source is unreadable JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"V19 {key} source is not a JSON object")
    return path, payload


def _validate_fresh_cell_direction(
    *, fresh_cell: Mapping[str, Any], saved_cell: Mapping[str, Any], cell: int,
) -> None:
    saved_tag = saved_cell.get("cell_tag")
    saved_permutation = saved_cell.get("cell_permutation")
    if (
        type(saved_tag) is not int
        or type(saved_permutation) is not int
        or type(fresh_cell.get("cell_tag")) is not int
        or type(fresh_cell.get("cell_permutation")) is not int
        or fresh_cell.get("cell_tag") != saved_tag
        or fresh_cell.get("cell_permutation") != saved_permutation
    ):
        raise ValueError(
            f"V19 fresh FE cell {cell} tag/permutation differs from its V17 receipt"
        )


def _read_v17_native_sources(root: Path) -> dict[str, Any]:
    v17_path, v17 = _read_pinned_json(root, "v17_report")
    callback = v17.get("selected_two_cell_candidate_callback")
    if (
        v17.get("schema") != "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1"
        or v17.get("status") != "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY"
        or v17.get("official_result") is not False
        or not isinstance(callback, Mapping)
        or callback.get("scope", {}).get("selected_active_row") != 1_622_464
        or callback.get("scope", {}).get("selected_original_row") != 5_218_672
        or callback.get("scope", {}).get("cell_order") != list(V19_SELECTED_CELLS)
        or callback.get("scope", {}).get("columns") != list(V19_COLUMNS)
    ):
        raise ValueError("V19 V17 donor report schema/status or row scope differs")
    cell_rows = callback.get("cells")
    column_rows = callback.get("columns")
    if (
        not isinstance(cell_rows, list)
        or [int(row.get("cell_index", -1)) for row in cell_rows] != list(V19_SELECTED_CELLS)
        or not isinstance(column_rows, list)
        or [int(row.get("column", -1)) for row in column_rows] != list(V19_COLUMNS)
    ):
        raise ValueError("V19 V17 donor report must retain exact two-cell/two-column order")
    for row in cell_rows:
        if (
            len(row.get("columns", [])) != 2
            or not isinstance(row.get("fresh_map_artifacts"), Mapping)
            or not isinstance(row.get("candidate_artifacts"), Mapping)
        ):
            raise ValueError("V19 V17 donor cell omits its saved map/candidate identity")
        for col, local in enumerate(row["columns"]):
            if (
                int(local.get("column", col)) != col
                or not isinstance(local.get("known_interior_local_artifact"), Mapping)
                or not isinstance(local.get("known_trace_local_artifact"), Mapping)
            ):
                raise ValueError("V19 V17 donor cell omits its original known local vectors")
    v18_path, v18 = _read_pinned_json(root, "v18_compact")
    if (
        v18.get("schema") != "task41.p0.v18.saved_jz_closeout.v1"
        or v18.get("scope", {}).get("status") != "COMPLETED_LOCAL_MIXED_NOT_QUALIFIED"
        or v18.get("scope", {}).get("official_result") is not False
        or "native rank-1" not in str(v18.get("missing_evidence", "")).lower()
    ):
        raise ValueError("V19 V18 closeout does not preserve the accepted negative boundary")
    v3_path, v3 = _read_pinned_json(root, "v3_donor_closeout")
    raw = v3.get("raw_evidence")
    identity = v3.get("identity")
    if (
        v3.get("schema") != "task41.p0.b0.v3.saved_evidence_closeout.v1"
        or not isinstance(raw, Mapping)
        or not isinstance(identity, Mapping)
        or identity.get("source_sha") != V19_ORIGINAL_PRODUCER_SOURCE_SHA
        or Path(str(raw.get("remote_directory", ""))).name != V19_ORIGINAL_DONOR_RUN
        or raw.get("recovery_manifest_sha256") != V19_ORIGINAL_RECOVERY_MANIFEST_SHA256
    ):
        raise ValueError("V19 original V3 producer/donor closeout binding differs")
    return {
        "v17_report_path": str(v17_path),
        "v17_report_sha256": SOURCE_BINDINGS["v17_report"][1],
        "v17_callback": callback,
        "v18_compact_path": str(v18_path),
        "v18_compact_sha256": SOURCE_BINDINGS["v18_compact"][1],
        "v18_scope_status": v18["scope"]["status"],
        "v18_missing_evidence": v18["missing_evidence"],
        "v3_closeout_path": str(v3_path),
        "v3_closeout_sha256": SOURCE_BINDINGS["v3_donor_closeout"][1],
        "v3_producer_source_sha": identity["source_sha"],
        "v3_donor_run": V19_ORIGINAL_DONOR_RUN,
        "v3_recovery_manifest_sha256": V19_ORIGINAL_RECOVERY_MANIFEST_SHA256,
    }


def _output_tree_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"V19 output tree contains a symlink: {path}")
        if path.is_file():
            total += int(path.stat().st_size)
    return total


def _disk_gate(output_directory: Path) -> dict[str, int]:
    output_bytes = _output_tree_bytes(output_directory)
    free_bytes = int(shutil.disk_usage(output_directory).free)
    if output_bytes > V19_MAX_NEW_EVIDENCE_BYTES:
        raise OSError("V19 newly written evidence exceeds the fixed 16 MiB cap")
    if free_bytes < V19_MIN_FREE_BYTES:
        raise OSError("V19 output filesystem is below the fixed 2 GiB free-space floor")
    return {
        "new_output_tree_bytes": output_bytes,
        "new_evidence_limit_bytes": V19_MAX_NEW_EVIDENCE_BYTES,
        "free_space_bytes": free_bytes,
        "free_space_floor_bytes": V19_MIN_FREE_BYTES,
        "cumulative_raw_artifact_limit_bytes": V19_MAX_CUMULATIVE_RAW_BYTES,
    }


def saved_diagnostics_budget_check_from_context(
    context: Mapping[str, Any], *, final: bool = False
) -> dict[str, Any]:
    """Recompute the V19 campaign disk gate from a service-hash-bound context."""
    output_root = Path(str(context.get("output_directory", ""))).resolve(strict=True)
    service_root = Path(str(context.get("service_directory", ""))).resolve(strict=True)
    window_root = Path(str(context.get("window_output_root", ""))).resolve(strict=True)
    results_root = Path(str(context.get("results_root", ""))).resolve(strict=True)
    expected_parent = window_root / "selected_incident_replay"
    if (
        output_root.parent != expected_parent
        or re.fullmatch(r"attempt[0-9]{2,}", output_root.name) is None
        or service_root.parent != output_root.parent
        or not service_root.name.startswith(output_root.name + ".service-")
        or results_root not in output_root.parents
        or type(context.get("recorded_cumulative_raw_artifact_bytes")) is not int
        or type(context.get("prior_window_output_bytes")) is not int
    ):
        raise ValueError("V19 disk-budget context paths or prior counters are not registered")

    def tree_bytes(root: Path) -> int:
        total = 0
        if not root.exists():
            return total
        if root.is_symlink() or not root.is_dir():
            raise ValueError("V19 campaign accounting path is not a real directory")
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError("V19 campaign output contains a symlink")
            if path.is_file():
                total += int(path.stat().st_size)
        return total

    inventory = context.get("bound_raw_artifact_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("V19 disk-budget context omits the pinned raw-artifact inventory")
    inode_sizes: dict[tuple[int, int], int] = {}
    for row in inventory:
        if not isinstance(row, Mapping):
            raise ValueError("V19 bound raw-artifact row is malformed")
        raw_path = Path(str(row.get("path", "")))
        if not raw_path.is_absolute() or raw_path.is_symlink():
            raise ValueError("V19 bound raw-artifact path is not a pinned absolute file")
        path = raw_path.resolve(strict=True)
        size = row.get("bytes")
        if (
            not path.is_relative_to(results_root)
            or path.suffix.lower() not in {".npy", ".npz"}
            or not path.is_file()
            or type(size) is not int
            or size <= 0
            or path.stat().st_size != size
        ):
            raise ValueError("V19 bound raw-artifact path/size changed or escaped results")
        stat = path.stat()
        key = (int(stat.st_dev), int(stat.st_ino))
        previous = inode_sizes.setdefault(key, size)
        if previous != size:
            raise ValueError("V19 hard-linked raw evidence has inconsistent sizes")
    bound_bytes = sum(inode_sizes.values())
    window_bytes = tree_bytes(window_root)
    invocation_bytes = tree_bytes(output_root) + tree_bytes(service_root)
    if window_bytes > V19_MAX_NEW_EVIDENCE_BYTES:
        raise OSError("V19 window-wide new evidence exceeds its 16 MiB cap")
    recorded = int(context["recorded_cumulative_raw_artifact_bytes"])
    prior_window = int(context["prior_window_output_bytes"])
    cumulative_before_new = max(recorded, bound_bytes) + prior_window + window_bytes
    reserve = 0 if final else V19_MAX_NEW_EVIDENCE_BYTES - window_bytes
    disk_root = window_root.parent if window_root.parent.exists() else results_root
    free_bytes = int(shutil.disk_usage(disk_root).free)
    if cumulative_before_new + reserve > V19_MAX_CUMULATIVE_RAW_BYTES:
        raise OSError("V19 cumulative raw evidence exceeds its 16 GiB cap")
    if free_bytes < V19_MIN_FREE_BYTES + reserve:
        raise OSError("V19 output would violate the 2 GiB free-space floor")
    return {
        "status": "POST_WRITE_CHECKED" if final else "PRE_CHECKER_ADMITTED",
        "recorded_cumulative_raw_artifact_bytes": recorded,
        "bound_raw_artifact_bytes_stat_deduplicated": bound_bytes,
        "prior_window_output_bytes_conservative": prior_window,
        "window_output_tree_bytes": window_bytes,
        "current_invocation_bytes": invocation_bytes,
        "window_wide_new_evidence_limit_bytes": V19_MAX_NEW_EVIDENCE_BYTES,
        "reserved_remaining_new_evidence_bytes": reserve,
        "cumulative_raw_artifact_limit_bytes": V19_MAX_CUMULATIVE_RAW_BYTES,
        "free_space_bytes": free_bytes,
        "free_space_floor_bytes": V19_MIN_FREE_BYTES,
    }


def _worker_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded V19 rank-1 capture worker")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--budget-context", type=Path, required=True)
    parser.add_argument("--budget-context-sha256", required=True)
    args = parser.parse_args(argv)
    context_path = args.budget_context.resolve(strict=True)
    if context_path.is_symlink() or sha256_file(context_path) != args.budget_context_sha256:
        raise ValueError("V19 worker disk-budget context differs from the service SHA-256")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    if not isinstance(context, Mapping):
        raise ValueError("V19 worker disk-budget context is not a JSON object")

    def progress(event: Mapping[str, Any]) -> None:
        print(json.dumps(dict(event), sort_keys=True, ensure_ascii=False), flush=True)

    receipt = run_v19_native_rank1_worker(
        contract_path=args.contract_path,
        contract_sha256=args.contract_sha256,
        output_directory=args.output_dir,
        repo_root=args.repo_root,
        progress_callback=progress,
        saved_diagnostics_budget_check=lambda *, final=False: (
            saved_diagnostics_budget_check_from_context(context, final=final)
        ),
    )
    print(json.dumps({"phase": "v19_worker", "status": receipt.get("status")}, sort_keys=True), flush=True)
    return 0 if receipt.get("status") == "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE" else 3


def _current_rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("V19 cannot read its current Linux VmRSS for the working-set gate")


def _load_map_array(
    *, root: Path, report_path: Path, record: Mapping[str, Any], label: str
) -> np.ndarray:
    raw_path = Path(str(record.get("path", "")))
    path = raw_path if raw_path.is_absolute() else report_path.parent / raw_path
    if path.is_symlink():
        raise ValueError(f"V19 {label} map artifact cannot be a symlink")
    path = path.resolve(strict=True)
    results_root = (root / "results" / "task41extra_phi90_p50x50_g17x20").resolve(strict=True)
    if (
        not path.is_relative_to(results_root)
        or record.get("sha256") != sha256_file(path)
        or record.get("bytes") != path.stat().st_size
    ):
        raise ValueError(f"V19 {label} map artifact path/size/hash differs")
    array = np.load(path, allow_pickle=False, mmap_mode="r")
    if list(array.shape) != record.get("shape") or array.dtype.str != np.dtype(
        record.get("dtype")
    ).str:
        raise ValueError(f"V19 {label} map artifact shape/dtype differs")
    return array


def _v19_state_path(output_directory: Path) -> Path:
    return output_directory / "task41_p0_v19_native_rank1_progress.json"


def _v19_read_state(path: Path, run_identity: Mapping[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": V19_PROGRESS_SCHEMA,
            "run_identity": dict(run_identity),
            "run_identity_sha256": _json_sha256(run_identity),
            "consumer_execution_bindings": [],
            "terms": {},
        }
    if path.is_symlink() or path.stat().st_size > V19_MAX_NEW_EVIDENCE_BYTES:
        raise ValueError("V19 progress path/size is invalid")
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V19 progress checkpoint is unreadable; retained without overwrite") from exc
    saved_identity = saved.get("run_identity") if isinstance(saved, dict) else None
    if not isinstance(saved_identity, Mapping):
        raise ValueError("V19 existing progress belongs to another numerical input/window")
    saved_base_identity = {
        key: value for key, value in saved_identity.items()
        if key != "native_capture_identity"
    }
    saved_native_identity = saved_identity.get("native_capture_identity")
    if (
        saved.get("schema") != V19_PROGRESS_SCHEMA
        or saved_base_identity != dict(run_identity)
        or saved.get("run_identity_sha256") != _json_sha256(saved_identity)
        or not isinstance(saved.get("consumer_execution_bindings"), list)
        or not isinstance(saved.get("terms"), Mapping)
        or (
            saved_native_identity is not None
            and (
                not isinstance(saved_native_identity, Mapping)
                or saved.get("native_capture_identity_sha256")
                != saved_native_identity.get("identity_sha256")
            )
        )
        or (bool(saved.get("terms")) and saved_native_identity is None)
    ):
        raise ValueError("V19 existing progress belongs to another numerical input/window")
    if isinstance(saved_native_identity, Mapping):
        _validate_identity_checksum({
            "identity_sha256": saved_native_identity.get("identity_sha256"),
            **{
                key: value
                for key, value in saved_native_identity.items()
                if key != "identity_sha256"
            },
        })
    return saved


def _checkpoint_progress(path: Path, state: Mapping[str, Any]) -> None:
    _write_json_atomic(path, state)
    _disk_gate(path.parent)


def _validate_output_location(root: Path, output_directory: Path, window_sha256: str) -> Path:
    if output_directory.is_symlink():
        raise ValueError("V19 output directory cannot be a symlink")
    path = output_directory.resolve(strict=True)
    expected_parent = (
        root / "results" / "task41extra_phi90_p50x50_g17x20"
        / "task41_p0_saved_diagnostics_6h" / window_sha256
        / "selected_incident_replay"
    ).resolve(strict=True)
    if path.parent != expected_parent or re.fullmatch(r"attempt[0-9]{2,}", path.name) is None:
        raise ValueError("V19 output directory is outside its fixed window/attempt location")
    return path


def _read_worker_receipt(path: Path, *, contract_sha256: str, run_identity_sha256: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size > V19_MAX_NEW_EVIDENCE_BYTES:
        raise ValueError("V19 existing worker receipt path/size is invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("V19 existing worker receipt is unreadable; raw files are retained") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != V19_RECEIPT_SCHEMA
        or payload.get("consumer_contract_sha256") != contract_sha256
        or payload.get("run_identity_sha256") != run_identity_sha256
        or payload.get("status") != "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE"
    ):
        raise ValueError("V19 existing receipt is not a complete same-contract capture")
    return payload


_V19_RECEIPT_IDENTITY_FIELDS = (
    "schema",
    "status",
    "classification",
    "consumer_contract_path",
    "consumer_contract_sha256",
    "consumer_source_sha",
    "consumer_window_path",
    "consumer_window_sha256",
    "run_identity",
    "run_identity_sha256",
    "native_capture_identity",
    "source_bindings",
    "original_donor",
    "v16_manifest_path",
    "v16_manifest_sha256",
    "v16_metadata_path",
    "v16_metadata_sha256",
    "v3_donor_manifest_path",
    "v3_donor_manifest_sha256",
    "v3_vector_index_path",
    "v3_vector_index_sha256",
    "known_field_bindings",
    "fresh_v17_map_identity",
    "mpc_restriction_support",
    "mpc_restriction_archive",
    "split_component_order",
    "split_combine_semantics",
    "local_kernel_override",
    "native_action_global_vector_assembly",
    "rank2_kernel_outputs",
    "factorizations",
    "getrs",
    "full_native_action",
    "actual_integral_inventory",
    "expected_selected_native_kernel_invocation_count_from_integral_lists",
    "persisted_selected_kernel_term_count",
    "kernel_invocation_ceiling",
    "new_evidence_limit_bytes",
    "cumulative_raw_artifact_limit_bytes",
    "free_space_floor_bytes",
    "planned_working_set_max_bytes",
    "official_result",
    "scientific_qualified",
    "full_owner_unlocked",
)


def _receipt_component_bindings(payload: Mapping[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    captures = payload.get("component_column_captures")
    if not isinstance(captures, list):
        raise ValueError("V19 existing receipt omits component/column term bindings")
    bindings: dict[tuple[str, int], dict[str, Any]] = {}
    for capture in captures:
        if not isinstance(capture, Mapping):
            raise ValueError("V19 receipt contains a malformed component capture")
        component, column = capture.get("component"), capture.get("column")
        if component not in {"curl", "material_mass"} or type(column) is not int or column not in V19_COLUMNS:
            raise ValueError("V19 receipt component/column identity is outside the approved scope")
        key = (str(component), column)
        if key in bindings:
            raise ValueError("V19 receipt repeats a component/column capture")
        bindings[key] = {
            name: value
            for name, value in capture.items()
            if name not in {"kernel_calls_this_invocation", "hash_bound_terms_reused", "terms"}
        }
    expected = {
        (component, column)
        for component in ("curl", "material_mass")
        for column in V19_COLUMNS
    }
    if set(bindings) != expected:
        raise ValueError("V19 receipt component/column inventory is incomplete")
    return bindings


def _receipt_term_bindings(payload: Mapping[str, Any]) -> dict[tuple[str, int, int, int], dict[str, Any]]:
    captures = payload.get("component_column_captures")
    if not isinstance(captures, list):
        raise ValueError("V19 existing receipt omits component/column term bindings")
    terms: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    capture_keys: set[tuple[str, int]] = set()
    for capture in captures:
        if not isinstance(capture, Mapping):
            raise ValueError("V19 receipt contains a malformed component capture")
        component, column = capture.get("component"), capture.get("column")
        if component not in {"curl", "material_mass"} or type(column) is not int or column not in V19_COLUMNS:
            raise ValueError("V19 receipt component/column identity is outside the approved scope")
        capture_keys.add((str(component), column))
        records = capture.get("terms")
        if not isinstance(records, list):
            raise ValueError("V19 receipt component capture omits its term list")
        for record in records:
            if not isinstance(record, Mapping):
                raise ValueError("V19 receipt contains a malformed term binding")
            cell, integral_index = record.get("cell_index"), record.get("cpp_integral_index")
            identity, artifacts = record.get("term_identity"), record.get("array_artifacts")
            if (
                type(cell) is not int or cell not in V19_SELECTED_CELLS
                or type(integral_index) is not int or integral_index < 0
                or not isinstance(identity, Mapping)
                or identity.get("component") != component
                or identity.get("column") != column
                or identity.get("cell_index") != cell
                or identity.get("cpp_integral_index") != integral_index
                or not isinstance(artifacts, Mapping)
                or set(artifacts) != set(_TERM_ARRAY_FIELDS)
                or not isinstance(record.get("archive_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", record["archive_sha256"]) is None
                or record.get("archive_binding_status") not in {
                    "CHECKPOINT_SHA256_VERIFIED",
                    "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY",
                }
                or record.get("capture_status") not in {
                    "CAPTURED_FINITE",
                    "CAPTURE_FAILED_RETAINED",
                }
            ):
                raise ValueError("V19 receipt term identity/artifact set is invalid")
            if any(
                not isinstance(reference, Mapping)
                or reference.get("sha256") != record["archive_sha256"]
                for reference in artifacts.values()
            ):
                raise ValueError("V19 receipt term archive SHA differs from its member references")
            key = (str(component), column, cell, integral_index)
            if key in terms:
                raise ValueError("V19 receipt repeats a component/column/cell/integral term")
            terms[key] = {
                "term_identity": dict(identity),
                "array_artifacts": dict(artifacts),
                "archive_sha256": record.get("archive_sha256"),
                "archive_binding_status": record.get("archive_binding_status"),
                "capture_status": record.get("capture_status"),
            }
    expected = {
        (component, column)
        for component in ("curl", "material_mass")
        for column in V19_COLUMNS
    }
    if capture_keys != expected:
        raise ValueError("V19 receipt component/column inventory is incomplete")
    return terms


def _verify_existing_receipt_matches_fresh(
    existing: Mapping[str, Any], fresh: Mapping[str, Any]
) -> None:
    for field in _V19_RECEIPT_IDENTITY_FIELDS:
        if field not in existing or field not in fresh or existing[field] != fresh[field]:
            raise ValueError(f"V19 completed receipt binding differs from fresh capture: {field}")
    if _receipt_component_bindings(existing) != _receipt_component_bindings(fresh):
        raise ValueError("V19 completed receipt component inventory differs from fresh capture")
    if _receipt_term_bindings(existing) != _receipt_term_bindings(fresh):
        raise ValueError("V19 completed receipt term/archive bindings differ from reopened capture")


def run_v19_native_rank1_worker(
    *,
    contract_path: str | Path,
    contract_sha256: str,
    output_directory: str | Path,
    repo_root: str | Path | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    saved_diagnostics_budget_check: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Capture/reopen only the two-cell, two-column native rank-1 volume terms.

    The caller must be the authorized saved-diagnostics service. This function
    never creates a window or authorization and never invokes rank-2, LU,
    GETRS, a global native action, or a candidate/full-owner evaluator.
    """
    worker_started = time.perf_counter()
    stage_timings = {
        "mesh_construction_seconds": 0.0,
        "fresh_map_validation_seconds": 0.0,
        "form_jit_action_construction_seconds": 0.0,
        "coefficient_table_packing_seconds": 0.0,
        "selected_coefficient_row_packing_seconds": 0.0,
        "kernel_execution_seconds": 0.0,
        "direction_transform_seconds": 0.0,
        "term_archive_save_seconds": 0.0,
    }
    from dolfinx.cpp.fem import IntegralType
    from mpi4py import MPI
    if MPI.COMM_WORLD.Get_size() != 1:
        raise ValueError("V19 native rank-1 capture requires an MPI-1 service process")

    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.task41_p0_checker import (
        TASK41_P0_B0_V16_TRACE_ROWS,
        TASK41_P0_B0_V16_STORAGE_ROWS,
        TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS,
        TASK41_P0_B0_V16_V3_VECTOR_INDEX_SHA256,
        TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE,
        TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
        TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW,
        TASK41_P0_B0_V17_SELECTED_ROW,
        TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256,
        load_task41_p0_b0_v16_saved_vector_manifest,
        load_task41_p0_b0_v17_selected_cell_metadata,
        load_task41_p0_b0_v17_v3_selected_donor,
    )
    from src.runners.task41_p0_contract import (
        TASK41_B0_RUN_ID,
        TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE,
        TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        TASK41_B0_V19_NATIVE_RANK1_SCOPE,
        TASK41_B0_V19_NATIVE_RANK1_WINDOW_RELATIVE,
        TASK41_MODEL_ID,
        load_task41_p0_fixed_window,
        require_task41_p0_contract,
        sha256_file as contract_sha256_file,
    )
    from src.runners.task41_p0_v4_volume_only_audit import (
        build_selected_volume_trace_star_metadata,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve(strict=True)
    report_path = Path(output_directory)
    if not report_path.is_absolute():
        report_path = root / report_path
    raw_contract_path = Path(contract_path)
    if not raw_contract_path.is_absolute():
        raw_contract_path = root / raw_contract_path
    contract, contract_digest = require_task41_p0_contract(
        raw_contract_path,
        expected_sha256=contract_sha256,
        current_root=root,
        require_clean_source=True,
        check_current_source=True,
        case_id="B0",
    )
    if (
        contract.get("execution_scope") != TASK41_B0_V19_NATIVE_RANK1_SCOPE
        or contract.get("case", {}).get("run_id") != TASK41_B0_RUN_ID
        or contract.get("case", {}).get("model_id") != TASK41_MODEL_ID
    ):
        raise ValueError("V19 worker contract scope/case differs from the exact two-cell review")
    from src.runners.task41_p0_contract import _git

    consumer_source_sha = _git(root, "rev-parse", "HEAD")
    if contract.get("source", {}).get("sha") != consumer_source_sha:
        raise ValueError("V19 worker source SHA differs from the clean canonical HEAD")
    fixed_window = load_task41_p0_fixed_window(contract, current_root=root)
    if (
        Path(str(contract["window"].get("path"))).resolve()
        != (root / TASK41_B0_V19_NATIVE_RANK1_WINDOW_RELATIVE).resolve()
        or contract["window"].get("sha256") != fixed_window.sha256
        or fixed_window.payload.get("scope") != TASK41_B0_V19_NATIVE_RANK1_SCOPE
    ):
        raise ValueError("V19 worker did not receive the new exact-scope fixed window")
    output_root = _validate_output_location(root, report_path, fixed_window.sha256)
    if output_root.resolve(strict=True) != report_path.resolve(strict=True):
        raise ValueError("V19 worker output directory identity changed")
    _disk_gate(output_root)
    _v19_live_preflight(
        contract=contract,
        fixed_window=fixed_window,
        saved_diagnostics_budget_check=saved_diagnostics_budget_check,
        stage="before_saved_input_load",
        output_directory=output_root,
        planned_working_set_bytes=V19_MAX_PLANNED_WORKING_BYTES,
    )

    sources = _read_v17_native_sources(root)
    v16_manifest_path = (root / TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE).resolve(strict=True)
    if v16_manifest_path.is_symlink() or contract_sha256_file(v16_manifest_path) != TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256:
        raise ValueError("V19 V16 saved-vector manifest path/hash differs")
    v16_manifest, saved_vectors, _ = load_task41_p0_b0_v16_saved_vector_manifest(
        v16_manifest_path,
        TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        repo_root=root,
        include_saved_array_replay=False,
        include_row_incidence=False,
    )
    v16_metadata_path = (root / TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE).resolve(strict=True)
    v16_metadata = load_task41_p0_b0_v17_selected_cell_metadata(
        repo_root=root,
        metadata_path=v16_metadata_path,
        expected_sha256=TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
    )
    donor = load_task41_p0_b0_v17_v3_selected_donor(
        repo_root=root,
        results_root=root / "results" / TASK41_MODEL_ID,
    )
    if (
        donor.get("manifest_sha256") != TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256
        or donor.get("source_index_sha256") != TASK41_P0_B0_V16_V3_VECTOR_INDEX_SHA256
        or len(donor.get("columns", [])) != 2
    ):
        raise ValueError("V19 V3 donor manifest/index differs from the pinned V16 loader")
    donor_run_root = Path(donor["manifest_path"]).resolve(strict=True).parent
    results_root = (root / "results" / TASK41_MODEL_ID).resolve(strict=True)
    resolved_config_path = (donor_run_root / "resolved_config.json").resolve(strict=True)
    if (
        not resolved_config_path.is_relative_to(results_root)
        or sha256_file(resolved_config_path) != contract.get("case", {}).get("resolved_config_sha256")
    ):
        raise ValueError("V19 V3 donor resolved configuration differs from the frozen case")
    config_value = json.loads(resolved_config_path.read_text(encoding="utf-8"))
    cfg = simulation_config_3d_from_normalized(config_value)
    known_bindings = {
        str(column): {
            "filename": TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS[column]["known_field"][0],
            "sha256": TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS[column]["known_field"][1],
            "bytes": TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS[column]["known_field"][2],
            "dtype": TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS[column]["known_field"][3],
            "shape": TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS[column]["known_field"][4],
        }
        for column in V19_COLUMNS
    }
    active_rows = _validate_v19_saved_vector_layout(
        donor["columns"],
        known_bindings,
        trace_rows=TASK41_P0_B0_V16_TRACE_ROWS,
        storage_rows=TASK41_P0_B0_V16_STORAGE_ROWS,
        selected_row=TASK41_P0_B0_V17_SELECTED_ROW,
        selected_original_row=TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW,
    )

    base_run_identity = {
        "task_id": TASK41_MODEL_ID,
        "run_id": TASK41_B0_RUN_ID,
        "fixed_window_sha256": fixed_window.sha256,
        "execution_scope": TASK41_B0_V19_NATIVE_RANK1_SCOPE,
        "v17_report_sha256": sources["v17_report_sha256"],
        "v18_compact_sha256": sources["v18_compact_sha256"],
        "v16_saved_vector_manifest_sha256": TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
        "v16_selected_metadata_sha256": TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
        "v3_donor_manifest_sha256": TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256,
        "v3_vector_index_sha256": TASK41_P0_B0_V16_V3_VECTOR_INDEX_SHA256,
        "known_field_bindings": known_bindings,
        "resolved_config_sha256": contract["case"]["resolved_config_sha256"],
        "selected_cells": list(V19_SELECTED_CELLS),
        "columns": list(V19_COLUMNS),
    }
    receipt_path = output_root / f"task41_p0_v19_native_rank1_worker_{contract_digest}.json"
    progress_path = _v19_state_path(output_root)
    state = _v19_read_state(progress_path, base_run_identity)
    current_binding = {
        "contract_path": str(raw_contract_path.resolve(strict=True)),
        "contract_sha256": contract_digest,
        "consumer_source_sha": consumer_source_sha,
        "fixed_window_sha256": fixed_window.sha256,
    }
    if current_binding not in state["consumer_execution_bindings"]:
        state["consumer_execution_bindings"].append(current_binding)
    _checkpoint_progress(progress_path, state)
    terms_directory = output_root / "native_rank1_terms"
    if terms_directory.is_symlink():
        raise ValueError("V19 term archive directory cannot be a symlink")
    terms_directory.mkdir(exist_ok=True)
    if any(path.is_symlink() for path in terms_directory.iterdir()):
        raise ValueError("V19 term archive directory contains a symlink")
    if any(path.name.endswith(".tmp") for path in terms_directory.iterdir()):
        raise ValueError("V19 partial term archive is retained; refusing to repeat or overwrite it")

    def emit(event: Mapping[str, Any]) -> None:
        if progress_callback is not None:
            progress_callback(event)

    emit({"phase": "v19_inputs", "status": "PINNED_SAVED_INPUTS_LOADED"})
    _v19_live_preflight(
        contract=contract,
        fixed_window=fixed_window,
        saved_diagnostics_budget_check=saved_diagnostics_budget_check,
        stage="before_mesh_and_action_construction",
        output_directory=output_root,
        planned_working_set_bytes=V19_MAX_PLANNED_WORKING_BYTES,
    )
    started = time.perf_counter()
    try:
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
        )
    finally:
        stage_timings["mesh_construction_seconds"] += time.perf_counter() - started
    space = levels["spaces"][6]
    floquet = levels["floquets"][6]
    started = time.perf_counter()
    try:
        fresh_metadata = build_selected_volume_trace_star_metadata(
            space,
            floquet.mpc,
            levels["mesh_data"].cell_tags,
            selected_active_row=TASK41_P0_B0_V17_SELECTED_ROW,
            expected_active_original_rows=active_rows,
            selected_cell_indices=V19_SELECTED_CELLS,
            progress_callback=progress_callback,
        )
    finally:
        stage_timings["fresh_map_validation_seconds"] += time.perf_counter() - started
    fresh_cells = fresh_metadata.get("incidents")
    if (
        not isinstance(fresh_cells, list)
        or [int(row.get("cell_index", -1)) for row in fresh_cells] != list(V19_SELECTED_CELLS)
    ):
        raise ValueError("V19 fresh mesh maps did not reproduce both pinned cells in order")
    v17_cells = {int(row["cell_index"]): row for row in sources["v17_callback"]["cells"]}
    fresh_map_refs: dict[str, Any] = {}
    for fresh_cell in fresh_cells:
        cell = int(fresh_cell["cell_index"])
        saved_cell = v17_cells[cell]
        saved_map_refs = saved_cell["fresh_map_artifacts"]
        _validate_fresh_cell_direction(
            fresh_cell=fresh_cell, saved_cell=saved_cell, cell=cell
        )
        for field in (
            "geometry_dofs", "actual_geometry_coordinates", "local_dofs",
            "original_rows", "interior_positions", "trace_positions",
            "interior_original_rows", "trace_original_rows", "active_ids",
        ):
            record = saved_map_refs.get(field)
            if not isinstance(record, Mapping):
                raise ValueError(f"V19 V17 frozen cell {cell} omits map field {field}")
            stored = _load_map_array(
                root=root,
                report_path=Path(sources["v17_report_path"]),
                record=record,
                label=f"cell {cell} {field}",
            )
            current = np.asarray(fresh_cell[field])
            if current.dtype != stored.dtype or not np.array_equal(current, stored):
                raise ValueError(f"V19 fresh FE cell {cell} {field} differs from its V17 map")
        fresh_map_refs[str(cell)] = {
            "cell_index": cell,
            "tag": int(fresh_cell["cell_tag"]),
            "permutation": int(fresh_cell["cell_permutation"]),
            "coordinate_sha256": str(fresh_cell["actual_coordinate_sha256"]),
            "v17_map_artifacts": dict(saved_map_refs),
        }
    for vector_name in ("known_field",):
        for column in V19_COLUMNS:
            if vector_name not in donor["columns"][column]:
                raise ValueError(f"V19 donor omitted {vector_name} column {column}")

    started = time.perf_counter()
    try:
        split_action = _build_split_volume_action(
            levels["mesh_data"], cfg, space, floquet,
            jit_options=dict(SAME_MESH_JIT_OPTIONS),
        )
    finally:
        stage_timings["form_jit_action_construction_seconds"] += (
            time.perf_counter() - started
        )
    with _destroy_split_action_on_exit(split_action):
        component_actions = split_action.component_actions
        if any(action._local_kernel is not None for action in component_actions.values()):
            raise ValueError("V19 actual split volume action unexpectedly uses a local-kernel override")
        owned_rows = int(split_action.component_actions["curl"]._owned_rows)
        ghost_rows = int(split_action.component_actions["curl"]._ghost_rows)
        if owned_rows != TASK41_P0_B0_V16_STORAGE_ROWS or ghost_rows != 0:
            raise ValueError("V19 MPI1 FE vector ownership differs from the full-storage V3 known input")

        abi_identity = _runtime_abi_identity()
        native_action_identities = {
            component: _native_action_identity(
                action,
                component=component,
                integral_type_cell=IntegralType.cell,
                selected_cells=V19_SELECTED_CELLS,
                abi_identity=abi_identity,
            )
            for component, action in component_actions.items()
        }
        native_capture_identity = {
            "schema": "task41.p0.v19.native_capture_identity.v1",
            "abi_identity": abi_identity,
            "component_identities": native_action_identities,
        }
        native_capture_identity["identity_sha256"] = _json_sha256(native_capture_identity)
        _validate_identity_checksum(native_capture_identity)
        saved_native_identity = state["run_identity"].get("native_capture_identity")
        if saved_native_identity is not None and saved_native_identity != native_capture_identity:
            raise ValueError("V19 existing progress native kernel/UFL/ABI identity differs")
        if state["terms"] and saved_native_identity is None:
            raise ValueError("V19 saved terms omit the frozen native kernel identity")
        run_identity = {
            **base_run_identity,
            "native_capture_identity": native_capture_identity,
        }
        run_identity_sha256 = _json_sha256(run_identity)
        state["run_identity"] = run_identity
        state["run_identity_sha256"] = run_identity_sha256
        state["native_capture_identity_sha256"] = native_capture_identity["identity_sha256"]
        _checkpoint_progress(progress_path, state)
        existing_receipt = _read_worker_receipt(
            receipt_path,
            contract_sha256=contract_digest,
            run_identity_sha256=run_identity_sha256,
        )

        target_local_dofs = []
        internal_local_dofs: dict[str, list[int]] = {}
        for cell in fresh_cells:
            cell_index = int(cell["cell_index"])
            local_dofs = np.asarray(cell["local_dofs"], dtype=np.int64)
            original_rows = np.asarray(cell["original_rows"], dtype=np.int64)
            interior_positions = np.asarray(cell["interior_positions"], dtype=np.int64)
            local_position = int(v16_metadata["cells"][V19_SELECTED_CELLS.index(cell_index)]["local_position"])
            if (
                local_dofs.shape != (882,)
                or original_rows.shape != (882,)
                or local_position < 0 or local_position >= 882
                or int(original_rows[local_position]) != TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW
                or int(local_dofs[local_position]) != int(original_rows[local_position])
            ):
                raise ValueError(f"V19 selected cell {cell_index} target local/original row differs")
            target_local_dofs.append(int(local_dofs[local_position]))
            internal_local_dofs[str(cell_index)] = [int(value) for value in local_dofs[interior_positions]]
        if len(set(target_local_dofs)) != 1:
            raise ValueError("V19 selected target local row differs across the two cell maps")
        all_internal = [value for rows in internal_local_dofs.values() for value in rows]
        if len(set(all_internal)) != len(all_internal) or set(all_internal) & set(target_local_dofs):
            raise ValueError("V19 900 interior rows are not unique/disjoint from the target row")

        mpc_maps: dict[str, np.ndarray] = {}
        first_action = component_actions["curl"]
        for field in (
            "_slave_indices", "_flat_slave_indices", "_master_indices",
            "_conjugated_master_coefficients", "_owned_slave_indices",
        ):
            values = np.ascontiguousarray(np.asarray(getattr(first_action, field)))
            mpc_maps[field.removeprefix("_")] = values
        relevant_rows = np.unique(np.asarray(target_local_dofs + all_internal, dtype=np.int64))
        slave_hits = relevant_rows[
            np.isin(relevant_rows, np.asarray(mpc_maps["slave_indices"]))
        ]
        master_hits = relevant_rows[
            np.isin(relevant_rows, np.asarray(mpc_maps["master_indices"]))
        ]
        restricted_hits = np.union1d(slave_hits, master_hits)
        mpc_support = {
            "owned_rows": owned_rows,
            "ghost_rows": ghost_rows,
            "curl_slave_row_identity": bool(first_action._slave_row_identity),
            "material_mass_slave_row_identity": bool(component_actions["material_mass"]._slave_row_identity),
            "selected_target_local_rows": target_local_dofs,
            "selected_internal_local_row_count": len(all_internal),
            "selected_rows_touch_any_mpc_slave_or_master": bool(restricted_hits.size),
            "selected_rows_touch_mpc_indices": [int(value) for value in restricted_hits],
            "mpc_map_array_identities": {name: _array_identity(values) for name, values in mpc_maps.items()},
            "map_scope": "complete finalized local MPC restriction arrays from actual split actions",
        }
        if mpc_support["selected_rows_touch_any_mpc_slave_or_master"]:
            raise ValueError("V19 selected target/interior support intersects MPC rows; two-cell output is incomplete")
        for component, action in component_actions.items():
            if action._slave_row_identity != (component == "curl"):
                raise ValueError("V19 split component MPC slave-row ownership differs from production")
            for name, values in mpc_maps.items():
                actual = np.asarray(getattr(action, f"_{name}"))
                if not np.array_equal(actual, values):
                    raise ValueError("V19 split component restriction maps differ before axpy")
        mpc_archive_path = output_root / "native_rank1_mpc_restriction.json"
        _v19_live_preflight(
            contract=contract,
            fixed_window=fixed_window,
            saved_diagnostics_budget_check=saved_diagnostics_budget_check,
            stage="before_mpc_archive_write",
            output_directory=output_root,
            planned_working_set_bytes=max(_current_rss_bytes(), V19_MAX_PLANNED_WORKING_BYTES),
        )
        mpc_archive_ref = _write_or_reopen_mpc_archive(
            archive_path=mpc_archive_path,
            output_directory=output_root,
            support=mpc_support,
            maps=mpc_maps,
            state=state,
            progress_path=progress_path,
        )
        _disk_gate(output_root)

        saved_term_keys: set[str] = set()
        inventories: dict[str, Any] = {}
        component_summaries: list[dict[str, Any]] = []
        try:
            for column in V19_COLUMNS:
                source_values = np.asarray(donor["columns"][column]["known_field"])
                if source_values.shape != (owned_rows,) or source_values.dtype != np.dtype(np.complex128):
                    raise ValueError(f"V19 original known column {column} does not match the action vector")

                def term_key(term: Mapping[str, Any]) -> str:
                    return _term_archive_path(terms_directory, term).stem

                def reopen_term(term: Mapping[str, Any]) -> Mapping[str, Any] | None:
                    key = term_key(term)
                    archive_path = _term_archive_path(terms_directory, term)
                    stored = state["terms"].get(key)
                    if stored is not None and stored.get("term_identity") != term.get("term_identity"):
                        raise ValueError(f"V19 saved term {key} belongs to different packed inputs or FE maps")
                    if not archive_path.exists():
                        if stored is not None:
                            raise ValueError(f"V19 progress refers to missing native term {key}")
                        return None
                    product = _archive_identity_and_refs(
                        archive_path,
                        output_directory=output_root,
                        expected_identity=term["term_identity"],
                        expected_archive_sha256=(
                            str(stored["archive_sha256"]) if stored is not None else None
                        ),
                        allow_orphan_atomic_archive=stored is None,
                    )
                    if stored is not None:
                        if (
                            stored.get("archive_sha256") != product["archive_sha256"]
                            or stored.get("array_artifacts") != product["array_artifacts"]
                            or stored.get("capture_status") != product["capture_status"]
                        ):
                            raise ValueError(f"V19 saved term {key} differs from its checkpoint binding")
                        if stored.get("archive_binding_status") != product["archive_binding_status"]:
                            state["terms"][key] = {
                                **dict(stored),
                                "archive_binding_status": product["archive_binding_status"],
                            }
                            _checkpoint_progress(progress_path, state)
                    else:
                        state["terms"][key] = {
                            "term_identity": dict(term["term_identity"]),
                            **product,
                        }
                        _checkpoint_progress(progress_path, state)
                    saved_term_keys.add(key)
                    if product["capture_status"] != "CAPTURED_FINITE":
                        raise FloatingPointError(f"V19 saved negative capture {key} is retained")
                    return product

                def persist_term(term: Mapping[str, Any]) -> Mapping[str, Any]:
                    key = term_key(term)
                    product = _write_term_archive(
                        term,
                        term_directory=terms_directory,
                        output_directory=output_root,
                    )
                    state["terms"][key] = {
                        "term_identity": dict(term["term_identity"]),
                        **product,
                    }
                    saved_term_keys.add(key)
                    _checkpoint_progress(progress_path, state)
                    _v19_live_preflight(
                        contract=contract,
                        fixed_window=fixed_window,
                        saved_diagnostics_budget_check=saved_diagnostics_budget_check,
                        stage="after_native_rank1_term_persist",
                        output_directory=output_root,
                        planned_working_set_bytes=min(
                            V19_MAX_PLANNED_WORKING_BYTES,
                            _current_rss_bytes() + 64 * 1024**2,
                        ),
                    )
                    emit({
                        "phase": "v19_native_rank1_term",
                        "status": product["capture_status"],
                        "component": term["component"],
                        "column": term["column"],
                        "cell_index": term["cell_index"],
                        "cpp_integral_index": term["cpp_integral_index"],
                        "term_identity_sha256": term["term_identity"]["identity_sha256"],
                        "archive_sha256": product["archive_sha256"],
                    })
                    return product["array_artifacts"]

                capture = split_action.capture_selected_rank1_cell_terms(
                    source_values,
                    capture_selected_rank1_cell_terms,
                    selected_cells=V19_SELECTED_CELLS,
                    column=column,
                    integral_type_cell=IntegralType.cell,
                    native_action_identities=native_action_identities,
                    on_term=persist_term,
                    reuse_term=reopen_term,
                    pre_pack_gate=lambda detail: _v19_live_preflight(
                        contract=contract,
                        fixed_window=fixed_window,
                        saved_diagnostics_budget_check=saved_diagnostics_budget_check,
                        stage="before_native_coefficient_pack",
                        output_directory=output_root,
                        planned_working_set_bytes=_current_rss_bytes()
                        + int(detail["expected_pack_bytes"])
                        + 64 * 1024**2,
                    ),
                    release_term_arrays_after_callback=True,
                    max_packed_coefficient_bytes=V19_MAX_PACKED_COEFFICIENT_BYTES,
                )
                for component in ("curl", "material_mass"):
                    component_result = capture["components"][component]
                    component_timings = component_result.get("stage_timings_seconds")
                    if not isinstance(component_timings, Mapping):
                        raise ValueError("V19 native capture omitted its measured stage timings")
                    for timing_key in (
                        "coefficient_table_packing_seconds",
                        "selected_coefficient_row_packing_seconds",
                        "kernel_execution_seconds",
                        "direction_transform_seconds",
                        "term_archive_save_seconds",
                    ):
                        timing_value = component_timings.get(timing_key)
                        if (
                            not isinstance(timing_value, (int, float))
                            or isinstance(timing_value, bool)
                            or not np.isfinite(float(timing_value))
                            or float(timing_value) < 0.0
                        ):
                            raise ValueError("V19 native capture stage timing is malformed")
                        stage_timings[timing_key] += float(timing_value)
                    inventory_key = component
                    inventory_value = {
                        "cpp_integral_index_order": component_result["cpp_integral_index_order"],
                        "ufcx_physical_integral_ids": component_result["ufcx_physical_integral_ids"],
                        "kernel_inventory_from_compiled_form": component_result[
                            "kernel_inventory_from_compiled_form"
                        ],
                        "expected_selected_kernel_invocations": component_result[
                            "expected_selected_kernel_invocations"
                        ],
                    }
                    if (
                        component_result.get("native_kernel_identity_sha256")
                        != native_action_identities[component]["identity_sha256"]
                        or component_result.get("integral_inventory_sha256")
                        != _json_sha256(native_action_identities[component]["integral_inventory"])
                    ):
                        raise ValueError(f"V19 {component} capture differs from its frozen kernel identity")
                    previous = inventories.get(inventory_key)
                    if previous is not None and previous != inventory_value:
                        raise ValueError(f"V19 {component} integral/domain inventory changed between columns")
                    inventories[inventory_key] = inventory_value
                    component_summaries.append({
                        "column": column,
                        "component": component,
                        "native_kernel_identity_sha256": component_result[
                            "native_kernel_identity_sha256"
                        ],
                        "integral_inventory_sha256": component_result[
                            "integral_inventory_sha256"
                        ],
                        "expected_selected_kernel_invocations": component_result[
                            "expected_selected_kernel_invocations"
                        ],
                        "kernel_calls_this_invocation": component_result["kernel_calls_this_invocation"],
                        "hash_bound_terms_reused": component_result["hash_bound_terms_reused"],
                        "completed_selected_kernel_terms": component_result[
                            "completed_selected_kernel_terms"
                        ],
                        "packed_coefficient_bytes_preflight": component_result[
                            "packed_coefficient_bytes_preflight"
                        ],
                        "packed_coefficient_bytes_observed": component_result[
                            "packed_coefficient_bytes_observed"
                        ],
                        "packed_coefficient_table_references_released": component_result[
                            "packed_coefficient_table_references_released"
                        ],
                        "compiled_coefficient_space_dimensions": component_result[
                            "compiled_coefficient_space_dimensions"
                        ],
                        "original_coefficient_positions": component_result[
                            "original_coefficient_positions"
                        ],
                        "terms": [
                            {
                                "component": term["component"],
                                "column": term["column"],
                                "cell_index": term["cell_index"],
                                "cpp_integral_index": term["cpp_integral_index"],
                                "ufcx_physical_integral_id": term["ufcx_physical_integral_id"],
                                "entity_position": term["entity_position"],
                                "term_identity": term["term_identity"],
                                "array_artifacts": term["array_artifacts"],
                                "archive_sha256": state["terms"][
                                    _term_archive_path(terms_directory, term).stem
                                ]["archive_sha256"],
                                "archive_binding_status": state["terms"][
                                    _term_archive_path(terms_directory, term).stem
                                ]["archive_binding_status"],
                                "capture_status": term["capture_status"],
                                "source": term["source"],
                                "kernel_executed_this_invocation": term[
                                    "kernel_executed_this_invocation"
                                ],
                            }
                            for term in component_result["terms"]
                        ],
                    })
                emit({"phase": "v19_native_rank1_column", "status": "CAPTURED_OR_REOPENED", "column": column})
        finally:
            split_action.destroy()
        expected_term_count = sum(
            2 * int(inventory["expected_selected_kernel_invocations"])
            for inventory in inventories.values()
        )
        if len(saved_term_keys) != expected_term_count or len(state["terms"]) != expected_term_count:
            raise ValueError("V19 saved native kernel term count differs from the compiled integral inventories")
        known_term_file_names = {
            _term_archive_path(terms_directory, term).name
            for summary in component_summaries
            for term in summary["terms"]
        }
        existing_term_files = {path.name for path in terms_directory.glob("*.npz")}
        if existing_term_files != known_term_file_names:
            raise ValueError("V19 term archive inventory has unbound or missing products")

        aggregate_expected = sum(
            2 * int(inventory["expected_selected_kernel_invocations"])
            for inventory in inventories.values()
        )
        receipt = {
            "schema": V19_RECEIPT_SCHEMA,
            "status": "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE",
            "classification": "RECONSTRUCTED_SELECTED_NATIVE_ACTION_PENDING_INDEPENDENT_CHECK",
            "consumer_contract_path": str(raw_contract_path.resolve(strict=True)),
            "consumer_contract_sha256": contract_digest,
            "consumer_source_sha": consumer_source_sha,
            "consumer_window_path": str(Path(fixed_window.path).resolve(strict=True)),
            "consumer_window_sha256": fixed_window.sha256,
            "run_identity": run_identity,
            "run_identity_sha256": run_identity_sha256,
            "native_capture_identity": native_capture_identity,
            "source_bindings": sources,
            "original_donor": {
                "source_sha": V19_ORIGINAL_PRODUCER_SOURCE_SHA,
                "run_name": V19_ORIGINAL_DONOR_RUN,
                "recovery_manifest_sha256": V19_ORIGINAL_RECOVERY_MANIFEST_SHA256,
                "historical_backend_runtime_audit": "NOT_PRESENT_IN_PINNED_V3_CLOSEOUT",
                "historical_kernel_identity_status": "UNKNOWN_MISSING_FROM_PINNED_V3_CLOSEOUT",
                "historical_jit_binary_sha256": None,
                "current_capture_interpretation": "RECONSTRUCTED_SELECTED_NATIVE_ACTION_NOT_HISTORICAL_BITWISE_REPLAY",
            },
            "v16_manifest_path": str(v16_manifest_path),
            "v16_manifest_sha256": TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
            "v16_metadata_path": str(v16_metadata_path),
            "v16_metadata_sha256": TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
            "v3_donor_manifest_path": donor["manifest_path"],
            "v3_donor_manifest_sha256": donor["manifest_sha256"],
            "v3_vector_index_path": donor["source_index_path"],
            "v3_vector_index_sha256": donor["source_index_sha256"],
            "known_field_bindings": known_bindings,
            "fresh_v17_map_identity": fresh_map_refs,
            "mpc_restriction_support": mpc_support,
            "mpc_restriction_archive": mpc_archive_ref,
            "split_component_order": ["curl", "material_mass"],
            "split_combine_semantics": "curl_result.axpy(1, mass_result)",
            "local_kernel_override": False,
            "native_action_global_vector_assembly": False,
            "rank2_kernel_outputs": 0,
            "factorizations": 0,
            "getrs": 0,
            "full_native_action": False,
            "actual_integral_inventory": inventories,
            "component_column_captures": component_summaries,
            "stage_timings_seconds": dict(stage_timings),
            "worker_function_elapsed_seconds_pre_receipt_write": (
                time.perf_counter() - worker_started
            ),
            "expected_selected_native_kernel_invocation_count_from_integral_lists": aggregate_expected,
            "persisted_selected_kernel_term_count": len(state["terms"]),
            "new_kernel_calls_this_invocation": sum(
                int(summary["kernel_calls_this_invocation"])
                for summary in component_summaries
            ),
            "hash_bound_terms_reused_this_invocation": sum(
                int(summary["hash_bound_terms_reused"])
                for summary in component_summaries
            ),
            "kernel_invocation_ceiling": aggregate_expected,
            "new_evidence_bytes": _disk_gate(output_root)["new_output_tree_bytes"],
            "new_evidence_limit_bytes": V19_MAX_NEW_EVIDENCE_BYTES,
            "cumulative_raw_artifact_limit_bytes": V19_MAX_CUMULATIVE_RAW_BYTES,
            "free_space_floor_bytes": V19_MIN_FREE_BYTES,
            "planned_working_set_max_bytes": V19_MAX_PLANNED_WORKING_BYTES,
            "official_result": False,
            "scientific_qualified": False,
            "full_owner_unlocked": False,
        }
        if receipt["persisted_selected_kernel_term_count"] != aggregate_expected:
            raise ValueError("V19 receipt would not bind the complete dynamic kernel inventory")
        if existing_receipt is not None:
            _verify_existing_receipt_matches_fresh(existing_receipt, receipt)
            return existing_receipt
        _write_new_json(receipt_path, receipt)
        _checkpoint_progress(progress_path, state)
        return receipt


def _ffi_buffer_pointer(ffi: Any, c_type: str, values: np.ndarray) -> tuple[Any, np.ndarray]:
    contiguous = np.ascontiguousarray(values)
    if contiguous.size == 0:
        return ffi.NULL, contiguous
    return ffi.cast(c_type, ffi.from_buffer(contiguous)), contiguous


def _apply_standard_test_transform(element: Any, values: np.ndarray, info: int) -> None:
    """Apply DOLFINx assemble_vector's ``standard`` test transform (Basix T)."""
    cell_info = np.asarray([int(info)], dtype=np.uint32)
    for part in (values.real, values.imag):
        workspace = np.ascontiguousarray(part, dtype=np.float64)
        element.T_apply(workspace, cell_info, 1)
        np.copyto(part, workspace)


def capture_selected_rank1_cell_terms(
    compiled_form: Any,
    function_space: Any,
    *,
    selected_cells: Sequence[int],
    component: str,
    column: int,
    integral_type_cell: Any,
    native_action_identities: Mapping[str, Mapping[str, Any]],
    constants: np.ndarray,
    pack_coefficients: Callable[[Any], Mapping[Any, np.ndarray]],
    max_packed_coefficient_bytes: int = V19_MAX_PACKED_COEFFICIENT_BYTES,
    on_term: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    reuse_term: Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None = None,
    pre_pack_gate: Callable[[Mapping[str, Any]], Any] | None = None,
    release_term_arrays_after_callback: bool = False,
) -> dict[str, Any]:
    """Capture each selected raw cell kernel term in original integration order.

    The caller supplies the same compiled rank-1 action form, packed constants,
    and coefficient packer owned by ``FullspaceMpcFormAction``. Coefficients are
    admitted from the UFCx coefficient count and the original finite-element
    dimensions before the DOLFINx packer allocates its full-domain tables.
    """
    stage_timings = {
        "coefficient_table_packing_seconds": 0.0,
        "selected_coefficient_row_packing_seconds": 0.0,
        "kernel_execution_seconds": 0.0,
        "direction_transform_seconds": 0.0,
        "term_archive_save_seconds": 0.0,
    }
    cells = tuple(int(cell) for cell in selected_cells)
    if not cells or len(set(cells)) != len(cells) or any(cell < 0 for cell in cells):
        raise ValueError("V19 selected cells must be unique nonnegative indices")
    if component not in {"curl", "material_mass"}:
        raise ValueError("V19 component must be curl or material_mass")
    if type(column) is not int or column not in V19_COLUMNS:
        raise ValueError("V19 column must be 0 or 1")
    if int(getattr(compiled_form, "rank", -1)) != 1:
        raise ValueError("V19 native capture requires a rank-1 compiled form")
    if np.dtype(getattr(compiled_form, "dtype", np.complex128)) != np.dtype(np.complex128):
        raise TypeError("V19 native capture requires a complex128 FFCx form")
    if not callable(on_term):
        raise ValueError("V19 native kernels require an atomic persistence callback before execution")

    ufcx_form = compiled_form.ufcx_form
    module = compiled_form.module
    if isinstance(ufcx_form, list) or isinstance(module, list):
        raise NotImplementedError("V19 capture requires one UFCx form/module")
    ffi = module.ffi
    native_identity = native_action_identities.get(component)
    if not isinstance(native_identity, Mapping) or native_identity.get("component") != component:
        raise ValueError("V19 native capture lacks the frozen component kernel identity")
    _validate_identity_checksum(native_identity)
    integral_inventory = native_identity.get("integral_inventory")
    if not isinstance(integral_inventory, Mapping):
        raise ValueError("V19 native kernel identity omits its frozen integral inventory")
    fresh_inventory = _compiled_integral_inventory(
        compiled_form, integral_type_cell, cells
    )
    if dict(integral_inventory) != fresh_inventory:
        raise ValueError("V19 compiled integral/domain inventory differs from its frozen identity")
    cell_start, physical_integral_ids = _ufcx_cell_integrals(compiled_form)
    cpp_form = compiled_form._cpp_object
    cpp_count = int(cpp_form.num_integrals(integral_type_cell, 0))
    cpp_domains = tuple(
        _integral_index_domain(compiled_form, integral_type_cell, index)
        for index in range(cpp_count)
    )

    stride, original_positions, compiled_dimensions = _coefficient_stride(
        compiled_form, ffi=ffi, ufcx_form=ufcx_form
    )
    expected_pack_bytes = sum(domain.size for domain in cpp_domains) * stride * np.dtype(
        np.complex128
    ).itemsize
    budget = int(max_packed_coefficient_bytes)
    if expected_pack_bytes > budget:
        raise MemoryError(
            "V19 DOLFINx full coefficient pack exceeds its one-table budget: "
            f"{expected_pack_bytes} > {budget} bytes"
        )

    if pre_pack_gate is not None:
        gate_result = pre_pack_gate({
            "component": component,
            "column": column,
            "cpp_integral_count": cpp_count,
            "integral_domain_entity_counts": [int(domain.size) for domain in cpp_domains],
            "coefficient_stride_complex128": stride,
            "expected_pack_bytes": expected_pack_bytes,
            "max_packed_coefficient_bytes": budget,
            "selected_kernel_invocations": sum(
                sum(int(value) in set(cells) for value in domain)
                for domain in cpp_domains
            ),
        })
        if gate_result is None:
            raise RuntimeError("V19 coefficient pack gate returned no evidence")

    packed_constants = np.ascontiguousarray(np.asarray(constants, dtype=np.complex128))
    _require_finite_array(packed_constants, "packed constants")
    started = time.perf_counter()
    try:
        packed = pack_coefficients(compiled_form)
    finally:
        stage_timings["coefficient_table_packing_seconds"] += (
            time.perf_counter() - started
        )
    if not isinstance(packed, Mapping):
        raise TypeError("DOLFINx packed coefficients must be keyed by integral type/index")
    expected_keys = {(integral_type_cell, index) for index in range(cpp_count)}
    if set(packed) != expected_keys:
        raise ValueError("packed coefficient keys differ from C++ integral-index keys")
    actual_pack_bytes = 0
    coefficient_tables: dict[int, np.ndarray] = {}
    for index, domain in enumerate(cpp_domains):
        table = np.asarray(packed[(integral_type_cell, index)], dtype=np.complex128)
        if stride:
            if table.ndim != 2 or table.shape != (domain.size, stride):
                raise ValueError("packed coefficient table shape differs from domain and FE stride")
        elif table.size != 0:
            raise ValueError("coefficient-free UFCx form produced a nonempty coefficient table")
        actual_pack_bytes += int(table.nbytes)
        coefficient_tables[index] = table
    if actual_pack_bytes != expected_pack_bytes:
        raise ValueError(
            "V19 packed coefficient bytes differ from the derived full-domain size: "
            f"{actual_pack_bytes} != {expected_pack_bytes}"
        )

    mesh = function_space.mesh
    mesh.topology.create_entity_permutations()
    cell_info = np.asarray(mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap, dtype=np.int32)
    geometry_coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    selected = set(cells)
    if geometry_dofmap.ndim != 2 or geometry_dofmap.shape[0] <= max(cells):
        raise ValueError("V19 selected cells are outside the mesh geometry dofmap")
    if cell_info.ndim != 1 or cell_info.size <= max(cells):
        raise ValueError("V19 cell permutation inventory omits a selected cell")

    element = function_space.element
    local_dimension = int(element.space_dimension)
    kernel_records: list[dict[str, Any]] = []
    selected_seen: set[int] = set()
    kernel_inventory = list(integral_inventory["kernel_inventory_from_compiled_form"])
    expected_selected_kernel_invocations = int(
        integral_inventory["expected_selected_kernel_invocations"]
    )
    integral_inventory_sha256 = _json_sha256(integral_inventory)
    kernel_calls_this_invocation = 0
    hash_bound_terms_reused = 0
    for integral_index in range(cpp_count):
        entities = cpp_domains[integral_index]
        table = coefficient_tables[integral_index]
        physical_integral_id = int(physical_integral_ids[integral_index])
        kernel = ufcx_form.form_integrals[cell_start + integral_index]
        kernel = kernel.tabulate_tensor_complex128
        if kernel == ffi.NULL:
            raise TypeError("V19 rank-1 form has no complex128 cell kernel")
        selected_entity_positions = [
            int(position)
            for position, cell_value in enumerate(entities)
            if int(cell_value) in selected
        ]
        frozen_integral = kernel_inventory[integral_index]
        if (
            frozen_integral["cpp_integral_index"] != integral_index
            or frozen_integral["ufcx_kernel_position"] != cell_start + integral_index
            or frozen_integral["ufcx_physical_integral_id"] != physical_integral_id
            or frozen_integral["domain_entity_count"] != int(entities.size)
            or frozen_integral["domain_entity_ids_sha256"]
            != _array_identity(entities)["sha256"]
            or frozen_integral["selected_entity_positions"] != selected_entity_positions
            or frozen_integral["selected_entity_cell_order"]
            != [int(entities[position]) for position in selected_entity_positions]
        ):
            raise ValueError("V19 integral loop differs from the frozen native inventory")
        for entity_position, cell_value in enumerate(entities):
            cell = int(cell_value)
            if cell not in selected:
                continue
            selected_seen.add(cell)
            permutation = int(cell_info[cell])
            # Force an independent selected-row copy. A C-contiguous row view
            # can otherwise keep the complete packed coefficient table alive.
            started = time.perf_counter()
            try:
                packed_row = (
                    np.array(table[entity_position], dtype=np.complex128, copy=True, order="C")
                    if stride else np.empty(0, dtype=np.complex128)
                )
                _require_finite_array(packed_row, "packed coefficient row")
                coefficient_ptr, packed_row = _ffi_buffer_pointer(
                    ffi, "double _Complex *", packed_row
                )
            finally:
                stage_timings["selected_coefficient_row_packing_seconds"] += (
                    time.perf_counter() - started
                )
            constants_ptr, constants_buffer = _ffi_buffer_pointer(
                ffi, "double _Complex *", packed_constants
            )
            geometry_dofs = np.ascontiguousarray(
                geometry_dofmap[cell], dtype=np.int32
            )
            coordinates = np.ascontiguousarray(
                geometry_coordinates[geometry_dofs].reshape(-1), dtype=np.float64
            )
            coordinate_ptr, coordinate_buffer = _ffi_buffer_pointer(
                ffi, "double *", coordinates
            )
            local_dofs = np.ascontiguousarray(
                function_space.dofmap.cell_dofs(cell), dtype=np.int32
            )
            original_dofs = np.ascontiguousarray(
                function_space.dofmap.index_map.local_to_global(local_dofs),
                dtype=np.int64,
            )
            if local_dofs.shape != (local_dimension,) or original_dofs.shape != (local_dimension,):
                raise ValueError("V19 local/original cell dofmaps do not close")
            term_identity = {
                "component": component,
                "column": column,
                "cell_index": cell,
                "cpp_integral_index": integral_index,
                "ufcx_kernel_position": cell_start + integral_index,
                "ufcx_physical_integral_id": physical_integral_id,
                "entity_position": entity_position,
                "permutation_info": permutation,
                "integral_domain_entity_count": int(entities.size),
                "integral_domain_entity_ids_sha256": _array_identity(entities)["sha256"],
                "native_kernel_identity_sha256": native_identity["identity_sha256"],
                "integral_inventory_sha256": integral_inventory_sha256,
                "array_identities": {
                    "packed_coefficient_row": _array_identity(packed_row),
                    "packed_constants": _array_identity(constants_buffer),
                    "local_dofs": _array_identity(local_dofs),
                    "original_dofs": _array_identity(original_dofs),
                    "geometry_dof_indices": _array_identity(geometry_dofs),
                    "geometry_coordinates": _array_identity(coordinate_buffer),
                },
            }
            term_identity["identity_sha256"] = hashlib.sha256(
                json.dumps(
                    term_identity,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            record = {
                "component": component,
                "column": column,
                "cell_index": cell,
                "cpp_integral_index": integral_index,
                "ufcx_kernel_position": cell_start + integral_index,
                "ufcx_physical_integral_id": physical_integral_id,
                "entity_position": entity_position,
                "permutation_info": permutation,
                "coefficient_key": ["cell", integral_index],
                "coefficient_pointer": "DOLFINx pack_coefficients integral-index row",
                "coefficient_transform": "DOLFINx pack.h coefficient transpose",
                "standard_test_transform": "FiniteElement.T_apply(cell_info, block_size=1)",
                "term_identity": term_identity,
                "packed_coefficient_row": packed_row,
                "packed_constants": constants_buffer.copy(),
                "local_dofs": local_dofs,
                "original_dofs": original_dofs,
                "geometry_dof_indices": geometry_dofs.copy(),
                "geometry_coordinates": coordinate_buffer.copy(),
            }
            reused = reuse_term(record) if reuse_term is not None else None
            if reused is not None:
                if not isinstance(reused, Mapping):
                    raise TypeError("V19 hash-bound term reuse must return an artifact mapping")
                artifact_refs = reused.get("array_artifacts")
                if not isinstance(artifact_refs, Mapping) or set(artifact_refs) != set(_TERM_ARRAY_FIELDS):
                    raise ValueError("V19 resumed term has an incomplete array artifact set")
                record["array_artifacts"] = dict(artifact_refs)
                record["capture_status"] = reused.get("capture_status")
                record["capture_error"] = reused.get("capture_error")
                record["kernel_executed_this_invocation"] = False
                record["source"] = "REOPENED_HASH_BOUND_CAPTURE"
                hash_bound_terms_reused += 1
                if release_term_arrays_after_callback:
                    for field in _TERM_ARRAY_FIELDS:
                        record.pop(field, None)
                kernel_records.append(record)
                if record["capture_status"] != "CAPTURED_FINITE":
                    raise FloatingPointError(
                        "V19 reopened a hash-bound negative kernel product; it is retained, not rerun"
                    )
                continue

            raw = np.zeros(local_dimension, dtype=np.complex128)
            raw_ptr, raw_buffer = _ffi_buffer_pointer(ffi, "double _Complex *", raw)
            # Same seven kernel arguments as DOLFINx assemble_vector_impl.h.
            started = time.perf_counter()
            try:
                kernel(
                    raw_ptr, coefficient_ptr, constants_ptr, coordinate_ptr,
                    ffi.NULL, ffi.NULL, ffi.NULL,
                )
            finally:
                stage_timings["kernel_execution_seconds"] += (
                    time.perf_counter() - started
                )
            kernel_calls_this_invocation += 1
            raw = np.asarray(raw_buffer, dtype=np.complex128).copy()
            oriented = raw.copy()
            capture_errors: list[str] = []
            if not np.isfinite(raw).all():
                capture_errors.append("raw rank-1 kernel output contains non-finite values")
            started = time.perf_counter()
            try:
                _apply_standard_test_transform(element, oriented, permutation)
            except Exception as exc:
                capture_errors.append(
                    f"standard test transformation failed: {type(exc).__name__}: {exc}"
                )
                oriented = np.full(
                    local_dimension, np.nan + 1j * np.nan, dtype=np.complex128
                )
            finally:
                stage_timings["direction_transform_seconds"] += (
                    time.perf_counter() - started
                )
            if not np.isfinite(oriented).all():
                capture_errors.append("oriented rank-1 test output contains non-finite values")
            record.update({
                "raw_kernel_output": raw.copy(),
                "oriented_test_vector": oriented,
                "kernel_executed_this_invocation": True,
                "source": "NEW_NATIVE_RANK1_KERNEL_CAPTURE",
                "capture_status": (
                    "CAPTURED_FINITE" if not capture_errors else "CAPTURE_FAILED_RETAINED"
                ),
                "capture_error": "; ".join(capture_errors) if capture_errors else None,
            })
            if on_term is not None:
                started = time.perf_counter()
                try:
                    artifact_refs = on_term(record)
                finally:
                    stage_timings["term_archive_save_seconds"] += (
                        time.perf_counter() - started
                    )
                if not isinstance(artifact_refs, Mapping):
                    raise TypeError("V19 per-term persistence must return an artifact mapping")
                if set(artifact_refs) != set(_TERM_ARRAY_FIELDS):
                    raise ValueError("V19 per-term persistence returned an incomplete artifact set")
                record["array_artifacts"] = dict(artifact_refs)
                if release_term_arrays_after_callback:
                    for field in _TERM_ARRAY_FIELDS:
                        record.pop(field)
            elif release_term_arrays_after_callback:
                raise ValueError("V19 cannot release term arrays without persisting them")
            kernel_records.append(record)
            # Surface a numerical/transform failure only after the callback has
            # durably stored the raw and transformed evidence with its status.
            if capture_errors:
                raise FloatingPointError(record["capture_error"])
    # Drop every Python reference to the one full-domain coefficient pack. This
    # is an object-lifetime statement; it does not claim that RSS or the OS page
    # cache has already fallen.
    coefficient_tables.clear()
    del coefficient_tables
    if "table" in locals():
        del table
    try:
        del coefficient_ptr, constants_ptr, coordinate_ptr, raw_ptr
        del packed_row, constants_buffer, coordinate_buffer, raw_buffer
        del raw, oriented, record
    except UnboundLocalError:
        # Empty selected domains have no last-row temporary; no full pack is
        # retained because ``packed`` and the coefficient table map are gone.
        pass
    del packed
    if selected_seen != selected:
        missing = sorted(selected - selected_seen)
        raise ValueError(f"V19 selected cells are absent from all cell integrals: {missing}")
    return {
        "schema": V19_CAPTURE_SCHEMA,
        "component": component,
        "column": column,
        "selected_cell_order": list(cells),
        "captured_cell_order": [row["cell_index"] for row in kernel_records],
        "cpp_integral_index_order": list(range(cpp_count)),
        "ufcx_physical_integral_ids": list(physical_integral_ids),
        "kernel_inventory_from_compiled_form": kernel_inventory,
        "native_kernel_identity_sha256": native_identity["identity_sha256"],
        "integral_inventory_sha256": integral_inventory_sha256,
        "expected_selected_kernel_invocations": expected_selected_kernel_invocations,
        "kernel_calls_this_invocation": kernel_calls_this_invocation,
        "hash_bound_terms_reused": hash_bound_terms_reused,
        "completed_selected_kernel_terms": len(kernel_records),
        "original_coefficient_positions": list(original_positions),
        "compiled_coefficient_space_dimensions": list(compiled_dimensions),
        "coefficient_stride_complex128": stride,
        "packed_coefficient_bytes_preflight": expected_pack_bytes,
        "packed_coefficient_bytes_observed": actual_pack_bytes,
        "packed_coefficient_table_references_released": True,
        "stage_timings_seconds": dict(stage_timings),
        "term_count": len(kernel_records),
        "terms": kernel_records,
    }


if __name__ == "__main__":
    raise SystemExit(_worker_cli())
