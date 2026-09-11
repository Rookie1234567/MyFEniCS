"""V12 O0--O4 orchestration for the existing physical DD4 macro operator.

This module deliberately contains no new numerical operator.  It connects the
qualified DD4 stack to the reviewed outer fixed-restart runner, records the
explicit residual checkpoints, and binds final output comparison to the
already-saved G0/V5 references.  A missing saved reference never changes the
solver result into a reference claim.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from .physical_diagnosis_worker import save_packet
from .workflow_timebase import CONSERVATIVE_REALTIME, ClockBudget, clock_sample


V12_PROFILE = "physical_macro_dd4_v12"
V12_MEMORY_POLICY = "SYMBOLIC_SIZED_LOCAL_MUMPS_V11"
V12_LOCAL_INVENTORY_CAP_BYTES = 2_684_354_560
V12_OLD_LOCAL_INVENTORY_CAP_BYTES = 2_147_483_648
V12_TRUE_RESIDUAL_LIMIT = 1.0e-6
V12_FIELD_LIMIT = 1.0e-4
V12_OUTPUT_LIMIT = 1.0e-5
V12_MODE_POWER_LIMIT = 1.0e-6
V12_MODE_AMPLITUDE_LIMIT = 1.0e-4


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _array_identity(value: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(value))
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
    }


_FORM_ACTION_IDENTITY_KEYS = (
    "schema", "backend", "matrix_type", "operator", "mpc_enabled",
    "slave_row_identity", "global_rows", "local_owned_rows",
    "local_ghost_rows", "local_storage_entries",
    "constraint_row_metadata_entries", "constraint_count",
    "owned_constraint_count", "constraint_nnz", "constraint_nnz_closes",
    "form_rank", "coefficient_count", "ufl_coefficient_count",
    "compiled_coefficient_count", "phase_application", "orientation",
    "owner_local", "numeric_allgather", "replicated_global_numeric_vector",
    "global_matrix_materialized", "global_constraint_matrix_materialized",
    "global_condensed_schur_matrix_materialized", "cell_schur_matrix_materialized",
    "slab_matrix_materialized", "retained_dense_cell_tensor_count",
    "dense_cell_tensor_materialized_per_apply", "cell_schur_matrix_nnz",
    "slab_matrix_nnz", "factor_count", "ksp_created", "dtn_used",
    "ordinary_default_changed", "fresh_packed_arrays_released",
    "jit_options_explicit",
)
_DTN_ACTION_IDENTITY_KEYS = (
    "schema", "profile", "matrix_type", "mode_count", "batch_size",
    "batch_count", "mode_manifest_sha256", "normalization",
    "normalization_nonidentity", "normalization_h_min", "normalization_h_max",
    "owner_local_surface_functionals", "slave_rows_local",
    "slave_functional_rows_local", "slave_functional_rows_global",
    "numeric_allgather", "explicit_c_matrix_count", "explicit_d_matrix_count",
    "global_aij_materialized", "global_schur_materialized",
    "trace_matrix_materialized", "ksp_created", "pde_solved",
    "bounded_work_scales_with",
)


def _allowlisted_audit(audit: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Select only named stable fields from a qualified action audit."""

    return {key: audit[key] for key in keys if key in audit}


def _operator_identity(
    stack: Mapping[str, Any], inventory: Mapping[str, Any], physical_sha256: str,
) -> dict[str, Any]:
    """Build a hash from A6/physics/mode/map identity only.

    In particular, no factor allocation, resident-byte, call-count, or timing
    facts enter this identity; those belong to the resource/cost evidence.
    """

    from src.runners.physical_macro_controls import _mapping_identity_sha256

    maps = inventory.get("maps", {})
    map_identity = {
        str(degree): {
            "packet_sha256": _mapping_identity_sha256(packet),
            "arrays": {
                str(name): _array_identity(value)
                for name, value in sorted(packet.items())
                if isinstance(value, np.ndarray)
            },
        }
        for degree, packet in sorted(maps.items(), key=lambda item: int(item[0]))
    }
    action_audit = getattr(stack["a6"], "audit", {})
    volume_audit = action_audit.get("volume_action", {})
    volume_identity = _allowlisted_audit(
        volume_audit,
        (
            "schema", "operator", "component_count", "slave_row_identity_owner",
            "constraint_identity_rows_exactly_once", "phase_application",
            "sum_output_buffer", "third_persistent_sum_vector",
        ),
    )
    volume_identity["components"] = {
        str(name): _allowlisted_audit(component, _FORM_ACTION_IDENTITY_KEYS)
        for name, component in volume_audit.get("components", {}).items()
    }
    dtn_audit = action_audit.get("dtn_action", {})
    return {
        "schema": "task39extra.review-v12.a6-operator-identity.v1",
        "physical_model_sha256": str(physical_sha256),
        "mode_sha256": str(stack["mode_sha256"]),
        "degree": 6,
        "a6": _allowlisted_audit(
            action_audit,
            (
                "schema", "operator", "owns_dtn", "t4_transmission_included",
                "global_aij_materialized", "global_schur_materialized",
                "ksp_created", "numeric_allgather",
            ),
        ),
        "a6_volume": volume_identity,
        "a6_dtn": _allowlisted_audit(dtn_audit, _DTN_ACTION_IDENTITY_KEYS),
        "quadrature_degree": int(stack["fine"]["dtn_quadrature_degree"]),
        "native_constraint_maps": map_identity,
    }


def _reference_path(value: Any, *, base: Path, name: str | None = None) -> Path:
    # Original G0 uses {relative_path: sha256}; the notch binding uses
    # {label: {path, sha256}}.  Treat these representations separately so a
    # digest can never accidentally be interpreted as a filename.
    raw = value.get("path") if isinstance(value, Mapping) else name
    if raw is None:
        raise ValueError("reference binding has no path")
    path = Path(str(raw))
    return path if path.is_absolute() else (base / path)


def _repo_root(path: Path) -> Path:
    for candidate in (path.parent, *path.parents):
        if (candidate / "src").is_dir() and (candidate / "input").is_dir():
            return candidate
    raise ValueError(f"cannot locate repository root for {path}")


def _load_reference_binding(inventory_path: str | Path, *, notch: bool) -> dict[str, Any]:
    """Verify and load the immutable V5 reference binding without solving."""

    from src.runners.physical_diagnostic_completion import load_packet

    inventory_path = Path(inventory_path).resolve()
    repository_root = _repo_root(inventory_path)
    inventory = json.loads(inventory_path.read_text())
    models = inventory.get("models", ())
    if len(models) < 2:
        raise ValueError("V12 requires both original and nonseparable G0 model bindings")
    model_index = 1 if notch else 0
    model = models[model_index]
    binding_files: dict[str, dict[str, Any]] = {}
    for name, descriptor in model.get("reference_bindings", {}).items():
        path = _reference_path(descriptor, base=repository_root, name=name)
        expected = descriptor.get("sha256") if isinstance(descriptor, Mapping) else descriptor
        if not path.is_file():
            raise FileNotFoundError(f"V12 reference binding is missing: {path}")
        actual = _sha256(path)
        if expected is not None and actual != str(expected):
            raise ValueError(f"V12 reference binding hash mismatch: {path}")
        binding_files[name] = {"path": str(path), "sha256": actual}

    output_file_hashes: dict[str, str] = {}
    if notch:
        matched_path = Path(binding_files["matched_reference.json"]["path"])
        summary_path = Path(binding_files["reference_summary.json"]["path"])
        identity_path = Path(binding_files["reference_identity.json"]["path"])
        matched = json.loads(matched_path.read_text())
        summary = json.loads(summary_path.read_text())
        identity = json.loads(identity_path.read_text())
        reference_output = matched.get("reference_output")
        if not isinstance(reference_output, Mapping):
            reference_output = summary.get("matched_output", {}).get("reference_output")
        residual_path = matched_path.parent / "reference_full_residual.json"
        reference_output_dir = matched_path.parent / "numerical_output"
    else:
        binding_path = Path(binding_files["benchmarks/artifacts/task39extra/v5_balanced/reference_output/binding.json"]["path"])
        binding = json.loads(binding_path.read_text())
        summary = None
        identity = None
        reference_output = binding.get("outputs")
        residual_path = repository_root / Path(
            "benchmarks/artifacts/task39extra/fine_reference_followup/"
            "f09476792d9928d6169cae8cc16b4c008f9bc694/reference_v2/reference_full_residual.json"
        )
        reference_output_dir = repository_root / "benchmarks/artifacts/task39extra/v5_balanced/reference_output"
        output_file_hashes = {
            str(name): str(digest)
            for name, digest in binding.get("files", {}).items()
        }

    if not residual_path.is_file():
        raise FileNotFoundError(f"qualified V12 reference residual is missing: {residual_path}")
    x_ref = None
    residual_binding = None
    residual_binding = {"path": str(residual_path), "sha256": _sha256(residual_path)}
    residual = load_packet(residual_path)
    if residual.get("status") != "REFERENCE_PASS":
        raise ValueError(f"saved reference residual is not qualified: {residual_path}")
    if not np.isfinite(float(residual["relative_residual"])) or float(residual["relative_residual"]) > float(residual["residual_limit"]):
        raise ValueError(f"saved reference residual failed its own gate: {residual_path}")
    x_ref = residual.get("x_ref")
    if identity is None:
        identity = residual.get("identity")
    if not isinstance(reference_output, Mapping):
        raise ValueError("V12 saved reference output is incomplete")
    for name, expected in output_file_hashes.items():
        output_path = reference_output_dir / name
        if not output_path.is_file() or _sha256(output_path) != expected:
            raise ValueError(f"saved original reference output hash mismatch: {output_path}")
    native_map_path = None
    native_map_identity = None
    if notch:
        native_map_path = Path(binding_files["reference_identity.json"]["path"]).parent / "reference_native_map.json"
        if not native_map_path.is_file():
            raise FileNotFoundError(f"saved notch native map is missing: {native_map_path}")
        native_map_identity = json.loads(native_map_path.read_text())
        arrays_descriptor = native_map_identity.get("arrays")
        if not isinstance(arrays_descriptor, Mapping):
            raise ValueError("saved notch native map has no array binding")
        arrays_path = _reference_path(arrays_descriptor, base=native_map_path.parent)
        if not arrays_path.is_file() or _sha256(arrays_path) != arrays_descriptor.get("sha256"):
            raise ValueError("saved notch native map array hash mismatch")
    def compact_identity(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        identity_value = value.get("identity", value)
        if not isinstance(identity_value, Mapping):
            return {}
        keys = (
            "status", "relative_residual", "residual_limit", "mode_sha256",
            "original_physical_sha256", "physical_sha256", "input_sha256",
        )
        return {key: identity_value[key] for key in keys if key in identity_value}

    return {
        "model_index": model_index,
        "model": model,
        "binding_files": binding_files,
        "reference_summary_facts": compact_identity(summary),
        "reference_identity_facts": compact_identity(identity),
        "reference_output": dict(reference_output),
        "reference_output_dir": str(reference_output_dir),
        "residual_binding": residual_binding,
        "x_ref": None if x_ref is None else np.asarray(x_ref, dtype=np.complex128),
        "reference_native_map": None if native_map_path is None else str(native_map_path),
        "reference_native_map_identity": {
            "identity": compact_identity(native_map_identity.get("identity")),
            "arrays": native_map_identity.get("arrays"),
            "ownership": native_map_identity.get("ownership"),
            "independent_indices": native_map_identity.get("independent_indices"),
        } if native_map_identity is not None else None,
        "reference_output_file_hashes": output_file_hashes,
        "authority": "G0_V5_EXISTING_REFERENCE_BINDING",
        "new_reference_solve": False,
    }


def run_macro_v12_precheck(
    inventory_path: str | Path,
    directory: str | Path,
    *,
    source_sha: str | None = None,
    input_path: str | Path | None = None,
    model_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run O0's non-PDE identity and dependency checks."""

    from src.runners.physical_recursive_controls import load_recursive_balanced_inputs

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    inventory = load_recursive_balanced_inputs(inventory_path)
    facts = {
        "schema": "task39extra.review-v12.o0-precheck.v1",
        "status": "O0_PRECHECK_COMPLETED",
        "profile": V12_PROFILE,
        "memory_policy": V12_MEMORY_POLICY,
        "local_inventory_cap_bytes": V12_LOCAL_INVENTORY_CAP_BYTES,
        "old_profile_cap_bytes": V12_OLD_LOCAL_INVENTORY_CAP_BYTES,
        "inventory_path": str(Path(inventory_path).resolve()),
        "inventory_sha256": _sha256(Path(inventory_path)),
        "e1_audit_sha256": inventory["e1_audit_sha256"],
        "source_sha": source_sha,
        "input_path": None if input_path is None else str(Path(input_path).resolve()),
        "model_identity": dict(model_identity or {}),
        "maps": {
            str(degree): {
                "independent_rows": int(packet["independent_indices"].size),
                "packet_sha256": hashlib.sha256(
                    np.ascontiguousarray(packet["independent_indices"]).tobytes()
                ).hexdigest(),
            }
            for degree, packet in inventory["maps"].items()
        },
        "reference_role": "measurement_only; O1 tolerates REFERENCE_UNAVAILABLE",
        "new_reference_factor": False,
    }
    save_packet(directory, "o0_summary", facts)
    return facts


def run_macro_v12_finalize(
    inventory_path: str | Path,
    directory: str | Path,
    *,
    source_sha: str | None = None,
    input_path: str | Path | None = None,
    model_identity: Mapping[str, Any] | None = None,
    budget_path: str | Path | None = None,
) -> dict[str, Any]:
    """Close the V12 evidence chain without rebuilding a numerical operator."""

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    campaign_root = directory.parent.parent
    stage_summaries: dict[str, Any] = {}
    for child in sorted(campaign_root.iterdir() if campaign_root.is_dir() else (), key=str):
        candidate = child / "records"
        for name in ("o0_summary.json", "m1_summary.json", "outer_summary.json"):
            path = candidate / name
            if path.is_file():
                payload = json.loads(path.read_text())
                stage = payload.get("stage") or (
                    "O0_PRECHECK" if name == "o0_summary.json" else
                    "O1_FULL_PHYSICAL_CONTROLS" if name == "m1_summary.json" else
                    payload.get("stage", "OUTER")
                )
                stage_summaries[f"{child.name}:{stage}"] = {
                    "path": str(path),
                    "sha256": _sha256(path),
                    "status": payload.get("status"),
                    "official_status": (payload.get("official_result") or {}).get("status"),
                }
    budget = None
    if budget_path is not None and Path(budget_path).is_file():
        budget = json.loads(Path(budget_path).read_text())
    facts = {
        "schema": "task39extra.review-v12.o4-finalize.v1",
        "status": "O4_FINALIZED",
        "profile": V12_PROFILE,
        "memory_policy": V12_MEMORY_POLICY,
        "local_inventory_cap_bytes": V12_LOCAL_INVENTORY_CAP_BYTES,
        "old_profile_cap_bytes": V12_OLD_LOCAL_INVENTORY_CAP_BYTES,
        "inventory_path": str(Path(inventory_path).resolve()),
        "inventory_sha256": _sha256(Path(inventory_path)),
        "source_sha": source_sha,
        "input_path": None if input_path is None else str(Path(input_path).resolve()),
        "model_identity": dict(model_identity or {}),
        "stage_summaries": stage_summaries,
        "o2_selection": None if budget is None else budget.get("o2_selection"),
        "new_reference_solve": False,
        "new_reference_factor": False,
        "finalization_rule": "summaries and official-result identities are hash-bound; no PDE or reference solve is repeated",
    }
    save_packet(directory, "o4_summary", facts)
    return facts


_SELECTED_FIELD_KEYS = (
    "x_nm", "y_nm", "z_nm", "E_V_per_m", "H_A_per_m",
    "interface_z_nm", "E_t_interface_V_per_m", "H_t_interface_A_per_m",
)
_SELECTED_FIELD_COORDINATE_KEYS = ("x_nm", "y_nm", "z_nm", "interface_z_nm")
_SELECTED_FIELD_VALUE_KEYS = tuple(
    key for key in _SELECTED_FIELD_KEYS if key not in _SELECTED_FIELD_COORDINATE_KEYS
)


def _resolve_field_archive(raw: Any, *, root: Path, repository_root: Path) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "benchmarks":
        return repository_root / path
    return root / path


def _compare_selected_field_archives(
    current: Mapping[str, Any], reference: Mapping[str, Any], *,
    current_dir: Path, reference_dir: Path,
) -> dict[str, Any]:
    current_export = current.get("field_export", {})
    reference_export = reference.get("field_export", {})
    current_raw = current_export.get("full3d_reference_archive")
    reference_raw = reference_export.get("full3d_reference_archive")
    if not current_raw or not reference_raw:
        return {"status": "UNAVAILABLE"}
    repository_root = _repo_root(current_dir)
    current_path = _resolve_field_archive(
        current_raw, root=current_dir, repository_root=repository_root,
    )
    reference_path = _resolve_field_archive(
        reference_raw, root=reference_dir, repository_root=repository_root,
    )
    if not current_path.is_file() or not reference_path.is_file():
        return {
            "status": "MISSING",
            "current_path": str(current_path),
            "reference_path": str(reference_path),
        }
    for path, export, role in (
        (current_path, current_export, "current"),
        (reference_path, reference_export, "reference"),
    ):
        expected = export.get("full3d_reference_archive_sha256")
        if expected is not None and _sha256(path) != str(expected):
            return {"status": "HASH_MISMATCH", "role": role, "path": str(path)}
    try:
        with np.load(current_path, allow_pickle=False) as current_archive, np.load(
            reference_path, allow_pickle=False,
        ) as reference_archive:
            if set(current_archive.files) != set(_SELECTED_FIELD_KEYS):
                return {"status": "ARRAY_INVENTORY_MISMATCH", "role": "current"}
            if set(reference_archive.files) != set(_SELECTED_FIELD_KEYS):
                return {"status": "ARRAY_INVENTORY_MISMATCH", "role": "reference"}
            coordinates: dict[str, Any] = {}
            for name in _SELECTED_FIELD_COORDINATE_KEYS:
                left = np.asarray(current_archive[name])
                right = np.asarray(reference_archive[name])
                exact = bool(left.shape == right.shape and np.array_equal(left, right))
                coordinates[name] = {"shape": list(left.shape), "exact": exact}
                if not exact:
                    return {"status": "COORDINATE_MISMATCH", "coordinates": coordinates}
            differences: dict[str, Any] = {}
            qualified = True
            for name in _SELECTED_FIELD_VALUE_KEYS:
                left = np.asarray(current_archive[name])
                right = np.asarray(reference_archive[name])
                if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
                    return {"status": "VALUE_SHAPE_OR_FINITE_MISMATCH", "field": name}
                absolute = float(np.max(np.abs(left - right), initial=0.0))
                relative = float(
                    np.linalg.norm(left - right)
                    / max(np.linalg.norm(right), np.finfo(float).tiny)
                )
                reference_norm = float(np.linalg.norm(right))
                near_zero = reference_norm <= 1.0e-12 and absolute <= 1.0e-10
                field_pass = bool(relative <= V12_FIELD_LIMIT or near_zero)
                qualified = qualified and field_pass
                differences[name] = {
                    "relative": relative,
                    "max_absolute": absolute,
                    "reference_norm": reference_norm,
                    "near_zero_absolute_gate": near_zero,
                    "pass": field_pass,
                }
            return {
                "status": "AVAILABLE" if qualified else "FIELD_DIFFERENCE_OVER_LIMIT",
                "coordinates": coordinates,
                "differences": differences,
                "max_relative_difference": max(
                    (item["relative"] for item in differences.values()), default=0.0,
                ),
                "max_absolute_difference": max(
                    (item["max_absolute"] for item in differences.values()), default=0.0,
                ),
                "limit": V12_FIELD_LIMIT,
                "current_path": str(current_path),
                "reference_path": str(reference_path),
            }
    except (OSError, ValueError) as exc:
        return {"status": "READ_ERROR", "error": f"{type(exc).__name__}: {exc}"}


def _saved_power(output: Mapping[str, Any]) -> dict[str, float]:
    port = output["port_metrics"]
    volume = output["volume_metrics"]
    return {
        "R": float(port["R_total"]),
        "T": float(port["T_total"]),
        "A": float(port["A_balance"]),
        "A_volume": float(volume["A_volume_total"]),
    }


def _compare_saved_output(
    current: Mapping[str, Any], reference: Mapping[str, Any],
    *, current_dir: Path, reference_dir: Path,
) -> dict[str, Any]:
    from src.runners.physical_balanced_output import compare_modal_files, compare_power_totals

    current_power = _saved_power(current)
    reference_power = _saved_power(reference)
    power_delta = {
        name: abs(current_power[name] - reference_power[name]) for name in current_power
    }
    modal = compare_modal_files(current_dir, reference_dir)
    power = compare_power_totals(current, reference)
    current_port = current["port_metrics"]
    closure = {
        "R_plus_T_minus_modal": abs(
            float(current_port["R_plus_T"]) - current_power["R"] - current_power["T"]
        ),
        "A_minus_A_volume": abs(current_power["A"] - current_power["A_volume"]),
        "R_plus_T_plus_A_volume_minus_one": abs(
            current_power["R"] + current_power["T"] + current_power["A_volume"] - 1.0
        ),
    }
    finite = {
        "electric_finite": bool(current.get("electric_finite")),
        "magnetic_finite": bool(
            np.isfinite(float(current.get("field_export", {}).get("max_abs_H", np.nan)))
        ),
        "auxiliary_finite": bool(current.get("auxiliary_finite")),
        "curl_postprocess_success": bool(current.get("field_export", {}).get("curl_postprocess_success")),
    }
    selected_field = _compare_selected_field_archives(
        current, reference, current_dir=current_dir, reference_dir=reference_dir,
    )
    return {
        "current": current_power,
        "reference": reference_power,
        "absolute_power_differences": power_delta,
        "power_max_absolute_difference": max(power_delta.values()),
        "modal": modal,
        "power": power,
        "closure": closure,
        "finite": finite,
        "selected_field": selected_field,
        "power_limit": V12_OUTPUT_LIMIT,
        "mode_power_limit": V12_MODE_POWER_LIMIT,
        "mode_amplitude_limit": V12_MODE_AMPLITUDE_LIMIT,
    }


def _field_compare(stack: Mapping[str, Any], solution: Any, x_ref: np.ndarray | None) -> dict[str, Any]:
    if x_ref is None:
        return {"status": "REFERENCE_FIELD_UNAVAILABLE"}
    from src.solvers.physical_error_diagnostics import metric_square
    from src.solvers.physical_error_metric import LosslessFEMetric

    from src.solvers.condensed_fine_reference import native_map_arrays

    indices = np.asarray(
        native_map_arrays(stack["levels"]["spaces"][6], stack["levels"]["floquets"][6])["independent_indices"],
        dtype=np.int64,
    )
    if x_ref.shape != solution.array.shape:
        return {"status": "REFERENCE_FIELD_SHAPE_MISMATCH", "reference_shape": list(x_ref.shape)}
    metric = LosslessFEMetric(
        stack["fine"]["setup"], 6, stack["fine"]["cfg"].k0,
        stack.get("recovery_quadrature_metadata"),
    )
    try:
        error = np.asarray(solution.array - x_ref, dtype=np.complex128)[indices]
        reference = np.asarray(x_ref, dtype=np.complex128)[indices]
        result = {}
        for name, action in (("L2", metric.mass), ("scaled_curl", metric.curl)):
            error_norm = float(np.sqrt(metric_square(action, error)))
            reference_norm = float(np.sqrt(metric_square(action, reference)))
            result[name] = {
                "absolute_error_norm": error_norm,
                "reference_norm": reference_norm,
                "relative": error_norm / max(reference_norm, np.finfo(float).tiny),
            }
        result["status"] = "REFERENCE_FIELD_AVAILABLE"
        result["max_relative"] = max(item["relative"] for item in result.values() if isinstance(item, Mapping))
        result["limit"] = V12_FIELD_LIMIT
        return result
    finally:
        metric.destroy()


def _write_checkpoint(
    checkpoint_root: Path,
    solution: Any,
    iteration: int,
    residual: float,
    *,
    input_sha256: str,
    operator_sha256: str,
    physical_sha256: str,
    source_sha: str,
    prefix: str,
) -> dict[str, Any]:
    from src.solvers.fullspace_memory_first_krylov import write_solution_checkpoint

    start, stop = solution.getOwnershipRange()
    prefix_root = checkpoint_root / prefix
    prefix_root.mkdir(parents=True, exist_ok=True)
    path = prefix_root / f"iteration_{int(iteration):08d}"
    return write_solution_checkpoint(
        path,
        solution,
        iteration=int(iteration),
        explicit_true_residual=float(residual),
        input_identity_sha256=input_sha256,
        operator_identity_sha256=operator_sha256,
        physical_model_sha256=physical_sha256,
        source_sha=source_sha,
        ownership={
            "rank": 0,
            "ownership_range": [int(start), int(stop)],
            "local_size": int(solution.getLocalSize()),
            "global_size": int(solution.getSize()),
        },
        comm=solution.getComm(),
    )


def _stage_timeout(stage: str) -> float:
    return {
        "O2_RESTART_PROBE_32": 2400.0,
        "O2_RESTART_PROBE_64": 2400.0,
        "O3_ORIGINAL": 10800.0,
        "O3_NOTCH": 10800.0,
    }.get(stage, 10800.0)


def _run_outer_candidate(
    stack: Mapping[str, Any],
    rhs: Any,
    *,
    framework: str,
    restart: int,
    max_it: int,
    sample: Callable[[], Mapping[str, Any]],
    marker: Callable[[str, Mapping[str, Any]], Any],
    checkpoint_root: Path,
    input_sha256: str,
    operator_sha256: str,
    physical_sha256: str,
    source_sha: str,
    stage: str,
    output_name: str,
    reference_x_ref: np.ndarray | None = None,
) -> dict[str, Any]:
    from src.solvers.fullspace_memory_first_krylov import run_fixed_restart_cycles
    from src.solvers.fullspace_memory_first_krylov import ExternalDeadlineStop
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.physical_macro_dd4 import make_macro_pc

    started = time.perf_counter()
    candidate_clock_start = clock_sample()
    candidate_clock = ClockBudget(candidate_clock_start, policy=CONSERVATIVE_REALTIME)
    node_records: list[dict[str, Any]] = []
    checkpoint_facts: list[dict[str, Any]] = []
    node_checkpoint_facts: list[dict[str, Any]] = []
    deadline_state = {
        "requested": False, "reason": None, "last_residual": None,
        "last_conservative_seconds": 0.0,
    }

    def timebase_snapshot() -> dict[str, Any]:
        interval = candidate_clock.update(clock_sample())
        elapsed = interval["elapsed_seconds"]
        snapshot = {
            "policy": interval["policy"],
            "policy_version": interval["policy_version"],
            "monotonic_seconds": float(elapsed["monotonic"]),
            "boottime_seconds": float(elapsed["boottime"]),
            "utc_seconds": float(elapsed["utc"]),
            "conservative_seconds": float(interval["budget_seconds"]),
            "utc_positive_excess_seconds": float(
                interval["utc_positive_excess_seconds"]
            ),
            "discrepancy_seconds": float(interval["discrepancy_seconds"]),
        }
        deadline_state["last_conservative_seconds"] = snapshot["conservative_seconds"]
        return snapshot

    def deadline_requested() -> bool:
        elapsed = timebase_snapshot()["conservative_seconds"]
        residual = deadline_state["last_residual"]
        requested = elapsed >= _stage_timeout(stage)
        if stage in {"O3_ORIGINAL", "O3_NOTCH"} and residual is not None:
            requested = requested or (
                elapsed >= 1800.0 and float(residual) > 0.10
            ) or (
                elapsed >= 5400.0 and float(residual) > 1.0e-3
            )
        if requested:
            deadline_state["requested"] = True
            deadline_state["reason"] = (
                "O3_EARLY_STOP_RHO_OVER_0P10" if elapsed >= 1800.0
                and residual is not None and float(residual) > 0.10 else
                "O3_EARLY_STOP_RHO_OVER_1E-3" if elapsed >= 5400.0
                and residual is not None and float(residual) > 1.0e-3 else
                "OUTER_STAGE_DEADLINE"
            )
        return requested

    def pc_deadline_requested() -> bool:
        if deadline_requested():
            raise ExternalDeadlineStop(str(deadline_state["reason"]))
        return False
    outer_pc = make_macro_pc(
        stack,
        framework=framework,
        sample=sample,
        save=lambda name, facts: save_packet(Path(checkpoint_root).parent, f"{output_name}_{name}", facts),
        stop_requested=pc_deadline_requested,
    )
    a6 = stack["a6"]
    from src.runners.physical_macro_controls import _stack_cost_snapshot
    cost_start = _stack_cost_snapshot(stack, stack["I4"])

    def apply_action(source: Any) -> Any:
        return apply_owned(a6, source)

    def apply_pc(source: Any) -> Any:
        return outer_pc.apply(source)

    interval = 8 if stage in {"O3_ORIGINAL", "O3_NOTCH"} else 8
    # O2 selection needs hash-bound solution snapshots at every common
    # pre-restart node.  The cycle checkpoint at restart/2*restart is not a
    # substitute: R32 and R64 must be compared at 8,16,24,32 themselves.
    if stage.startswith("O2_"):
        node_set = {8, 16, 24, 32, 40, 48, 56, 64}
    elif stage in {"O3_ORIGINAL", "O3_NOTCH"}:
        node_set = set(range(32, max_it + 1, 32))
    else:
        node_set = set()

    def explicit_node(iteration: int, residual: float, solution: Any) -> None:
        deadline_state["last_residual"] = float(residual)
        resource = dict(sample())
        resource_compact = {
            key: resource.get(key)
            for key in (
                "timestamp_ns", "rss_bytes", "pss_bytes", "swap_bytes",
                "all_status_readable", "launch_cap_bytes",
            )
            if key in resource
        }
        cost_snapshot = _stack_cost_snapshot(stack, stack["I4"])
        timebase = timebase_snapshot()
        row = {
            "iteration": int(iteration),
            "true_residual": float(residual),
            "solution_norm": float(solution.norm()),
            "solution_sha256": hashlib.sha256(
                np.asarray(solution.array, dtype=np.complex128).tobytes()
            ).hexdigest(),
            "input_identity_sha256": input_sha256,
            "operator_identity_sha256": operator_sha256,
            "physical_model_sha256": physical_sha256,
            "true_residual_definition": "||rhs-A6*x||/||rhs|| from a fresh explicit action",
            "elapsed_seconds": float(time.perf_counter() - started),
            "elapsed_seconds_monotonic": timebase["monotonic_seconds"],
            "elapsed_seconds_conservative": timebase["conservative_seconds"],
            "timebase": timebase,
            "resource": resource_compact,
            "outer_pc_calls": int(getattr(outer_pc, "apply_count", 0)),
            "cost": cost_snapshot,
        }
        if stage.startswith("O2_") and iteration in {32, 40, 48, 56, 64}:
            field_started = time.perf_counter()
            row["reference_field"] = _field_compare(stack, solution, reference_x_ref)
            row["reference_field_elapsed_seconds"] = float(
                time.perf_counter() - field_started
            )
            # Field comparison is part of the node's recorded cost.  Refresh
            # all clocks after it so the three timing fields end at one point.
            timebase = timebase_snapshot()
            row["elapsed_seconds"] = float(time.perf_counter() - started)
            row["elapsed_seconds_monotonic"] = timebase["monotonic_seconds"]
            row["elapsed_seconds_conservative"] = timebase["conservative_seconds"]
            row["timebase"] = timebase
        node_records.append(row)
        if iteration in node_set:
            node_checkpoint = _write_checkpoint(
                    checkpoint_root,
                    solution,
                    iteration,
                    residual,
                    input_sha256=input_sha256,
                    operator_sha256=operator_sha256,
                    physical_sha256=physical_sha256,
                    source_sha=source_sha,
                    prefix=f"{output_name}_periodic_nodes",
                )
            checkpoint_facts.append(node_checkpoint)
            node_checkpoint_facts.append(node_checkpoint)

    def checkpoint(iteration: int, solution: Any, residual: float) -> Mapping[str, Any]:
        fact = _write_checkpoint(
            checkpoint_root,
            solution,
            iteration,
            residual,
            input_sha256=input_sha256,
            operator_sha256=operator_sha256,
            physical_sha256=physical_sha256,
            source_sha=source_sha,
            prefix=output_name,
        )
        checkpoint_facts.append(fact)
        return fact

    def stop_after_cycle(cycle: Mapping[str, Any], _cycles: Any) -> bool:
        elapsed = timebase_snapshot()["conservative_seconds"]
        iteration = int(cycle["end_iteration"])
        residual = float(cycle["explicit_true_residual"])
        if stage.startswith("O2_") and elapsed >= 2400.0:
            return True
        if stage in {"O3_ORIGINAL", "O3_NOTCH"}:
            if elapsed >= 1800.0 and residual > 0.10:
                return True
            if elapsed >= 5400.0 and residual > 1.0e-3:
                return True
        marker("outer_cycle_completed", {
            "stage": stage, "framework": framework, "restart": restart,
            "iteration": iteration, "true_residual": residual,
            "elapsed_seconds": elapsed,
            "elapsed_seconds_conservative": elapsed,
        })
        return False

    try:
        result = run_fixed_restart_cycles(
            rhs,
            apply_action,
            apply_pc,
            max_it=max_it,
            residual_limit=V12_TRUE_RESIDUAL_LIMIT,
            resource_sample=sample,
            start_iteration=0,
            checkpoint_writer=checkpoint,
            first_checkpoint_iteration=restart,
            checkpoint_interval=restart,
            stop_after_cycle=stop_after_cycle,
            stop_on_true_residual=True,
            ksp_type="fgmres",
            restart=restart,
            cycle_max_it=restart,
            explicit_residual_interval=interval,
            explicit_residual_observer=explicit_node,
            stop_requested=deadline_requested,
        )
        result["framework"] = framework
        result["restart"] = int(restart)
        result["stage"] = stage
        result["node_records"] = node_records
        result["checkpoint_facts"] = checkpoint_facts
        result["node_checkpoint_facts"] = node_checkpoint_facts
        final_timebase = timebase_snapshot()
        result["elapsed_seconds_wall"] = time.perf_counter() - started
        result["elapsed_seconds_monotonic"] = final_timebase["monotonic_seconds"]
        result["elapsed_seconds_conservative"] = final_timebase["conservative_seconds"]
        result["timebase"] = {
            "start": candidate_clock_start,
            "final": final_timebase,
        }
        result["deadline"] = dict(deadline_state)
        result["outer_pc_calls"] = int(getattr(outer_pc, "apply_count", 0))
        result["outer_pc_total_counts"] = dict(
            getattr(outer_pc, "total_counts", {})
        )
        result["outer_pc_total_operation_seconds"] = dict(
            getattr(outer_pc, "total_operation_seconds", {})
        )
        result["outer_pc_cost_semantics"] = (
            "outer PC totals include the nested I4/coarse calls made by each "
            "outer apply; report separately from the stack I4 counters and "
            "do not add parent and child totals"
        )
        result["cost_start"] = cost_start
        result["cost_end"] = _stack_cost_snapshot(stack, stack["I4"])
        result["cost_delta"] = {
            key: result["cost_end"][key] - value
            for key, value in cost_start.items()
            if isinstance(value, (int, float))
            and isinstance(result["cost_end"].get(key), (int, float))
        }
        result["status"] = (
            "COMPLETED_TRUE_RESIDUAL" if result["final_true_residual"] <= V12_TRUE_RESIDUAL_LIMIT
            else "CONTROLLED_STOP"
        )
        return result
    except BaseException:
        raise


def _release_result(result: Mapping[str, Any]) -> None:
    solution = result.get("final_solution")
    if solution is not None:
        solution.destroy()


def run_macro_v12_outer(
    cfg: Any,
    comm: Any,
    inventory_path: str | Path,
    directory: str | Path,
    *,
    sample: Callable[[], Mapping[str, Any]],
    marker: Callable[[str, Mapping[str, Any]], Any],
    source_sha: str,
    input_path: str | Path,
    model_identity: Mapping[str, Any] | None = None,
    stage: str,
    outer_restart: int,
    framework: str = "BAL_H",
) -> dict[str, Any]:
    """Run O2/O3 with a real physical RHS and the selected DD4 outer PC."""

    from src.io.physical_recursive_profile import MACRO_V12_PROFILE
    from src.runners.physical_recursive_controls import (
        load_recursive_balanced_inputs,
        verify_recursive_map,
    )
    from src.solvers.fullspace_memory_first_krylov import destroy_krylov_result
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        recover_p0_outputs,
    )
    from src.solvers.physical_macro_dd4 import build_macro_stack, destroy_macro_stack

    if comm.size != 1:
        raise ValueError("V12 physical macro outer stages are MPI1-only")
    if stage not in {"O2_RESTART_PROBE_32", "O2_RESTART_PROBE_64", "O3_ORIGINAL", "O3_NOTCH"}:
        raise ValueError(f"unsupported V12 outer stage {stage}")
    if outer_restart not in (32, 64):
        raise ValueError("V12 outer restart must be 32 or 64")
    if framework not in {"BAL_H", "ONE_C"}:
        raise ValueError("V12 framework must be BAL_H or ONE_C")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    input_path = Path(input_path).resolve()
    input_sha256 = _sha256(input_path)
    physical_sha256 = str((model_identity or {}).get("physical_model_sha256", ""))
    if len(physical_sha256) != 64:
        raise ValueError("V12 outer stage requires a hash-bound physical model identity")
    phase_timings: dict[str, dict[str, Any]] = {}
    active_phases: dict[str, dict[str, Any]] = {}

    def phase_start(name: str) -> None:
        start_clock = clock_sample()
        active_phases[name] = start_clock
        marker(f"{name}_started", {"clock": start_clock})

    def phase_finish(name: str) -> None:
        start_clock = active_phases.pop(name, None)
        if start_clock is None:
            return
        end_clock = clock_sample()
        interval = ClockBudget(
            start_clock, policy=CONSERVATIVE_REALTIME,
        ).update(end_clock)
        phase_timings[name] = {
            "start_clock": start_clock,
            "end_clock": end_clock,
            "clock_interval": interval,
            "elapsed_seconds_monotonic": float(
                interval["elapsed_seconds"]["monotonic"]
            ),
            "elapsed_seconds_conservative": float(interval["budget_seconds"]),
        }
        marker(f"{name}_completed", phase_timings[name])

    phase_start("setup")
    inventory = load_recursive_balanced_inputs(inventory_path)
    notch = stage == "O3_NOTCH" or bool(cfg.cell_notch)
    reference_binding = _load_reference_binding(inventory_path, notch=notch)
    phase_finish("setup")
    stack = None
    rhs = None
    candidate_results: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "schema": "task39extra.review-v12.outer-stage.v1",
        "status": "STARTED",
        "profile": MACRO_V12_PROFILE,
        "memory_policy": V12_MEMORY_POLICY,
        "local_inventory_cap_bytes": V12_LOCAL_INVENTORY_CAP_BYTES,
        "stage": stage,
        "framework": framework,
        "outer_restart": int(outer_restart),
        "source_sha": source_sha,
        "input_path": str(input_path),
        "input_sha256": input_sha256,
        "physical_model_sha256": physical_sha256,
        "inventory_sha256": _sha256(Path(inventory_path)),
        "model_identity": dict(model_identity or {}),
        "reference_binding": {
            key: value for key, value in reference_binding.items() if key != "x_ref"
        },
        "new_reference_solve": False,
        "new_reference_factor": False,
        "candidates": [],
        "official_result": None,
        "stage_times": phase_timings,
    }
    try:
        phase_start("build")
        try:
            stack = build_macro_stack(
                cfg, comm, sample=sample, marker=marker,
                save=lambda name, facts: save_packet(directory, name, facts),
                memory_policy=V12_MEMORY_POLICY,
                local_inventory_cap_bytes=V12_LOCAL_INVENTORY_CAP_BYTES,
            )
        finally:
            phase_finish("build")
        expected_model = reference_binding["model"]
        if str(expected_model.get("physical_sha")) != physical_sha256:
            raise ValueError("V12 input physical identity differs from the selected G0 reference model")
        if str(expected_model.get("mode_sha")) != str(stack["mode_sha256"]):
            raise ValueError("V12 rebuilt mode identity differs from the selected G0 reference model")
        for identity_source in (
            reference_binding.get("reference_summary_facts"),
            reference_binding.get("reference_identity_facts"),
            (reference_binding.get("reference_native_map_identity") or {}).get("identity"),
        ):
            if not isinstance(identity_source, Mapping):
                continue
            identity = identity_source.get("identity", identity_source)
            if identity.get("mode_sha256") not in (None, str(stack["mode_sha256"])):
                raise ValueError("saved reference mode identity differs from current V12 mode inventory")
            saved_physical = identity.get("original_physical_sha256") or identity.get("physical_sha256")
            if saved_physical is not None and str(saved_physical) != physical_sha256:
                raise ValueError("saved reference physical identity differs from current V12 model")
        if not notch:
            verify_recursive_map(stack, 6, inventory["maps"][6])
            verify_recursive_map(stack, 4, inventory["maps"][4])
        stack_identity = {
            "profile": MACRO_V12_PROFILE,
            "memory_policy": V12_MEMORY_POLICY,
            "local_inventory_cap_bytes": V12_LOCAL_INVENTORY_CAP_BYTES,
            "mode_sha256": stack["mode_sha256"],
            "p4_bridge": stack["a4_bridge"],
            "p2_matrix": stack["p2_matrix_facts"],
            "coverage": stack["local"].coverage,
            "resident_bytes": stack["local"].resident_bytes,
            "resident_inventory": stack["local"].resident_inventory if hasattr(stack["local"], "resident_inventory") else None,
            "new_reference_factor": False,
            "p4_global_matrix": False,
            "p4_global_factor": False,
            "notch": notch,
        }
        save_packet(directory, "macro_stack_identity", stack_identity)
        summary["macro_stack_identity"] = stack_identity
        operator_identity = _operator_identity(stack, inventory, physical_sha256)
        operator_sha256 = _json_sha256(operator_identity)
        save_packet(directory, "operator_identity", {
            "identity": operator_identity,
            "sha256": operator_sha256,
        })
        summary["operator_identity"] = {
            "sha256": operator_sha256,
            "schema": operator_identity["schema"],
            "mode_sha256": operator_identity["mode_sha256"],
            "native_constraint_maps": operator_identity["native_constraint_maps"],
        }
        phase_start("rhs")
        try:
            rhs, rhs_facts = build_physical_rhs(stack["fine"])
        finally:
            phase_finish("rhs")
        save_packet(directory, "physical_rhs", {"rhs": np.array(rhs.array), "facts": rhs_facts})
        checkpoint_root = directory / "checkpoints"
        max_it = 64 if stage.startswith("O2_") else 2048
        if stage.startswith("O2_"):
            phase_start("outer")
            try:
                result = _run_outer_candidate(
                    stack, rhs, framework=framework, restart=outer_restart, max_it=max_it,
                    sample=sample, marker=marker, checkpoint_root=checkpoint_root,
                    input_sha256=input_sha256, operator_sha256=operator_sha256,
                    physical_sha256=physical_sha256, source_sha=source_sha, stage=stage,
                    output_name=f"restart_{outer_restart}",
                    reference_x_ref=reference_binding.get("x_ref"),
                )
            finally:
                phase_finish("outer")
            candidate_results.append(result)
            summary["candidates"] = [{
                key: value for key, value in result.items() if key != "final_solution"
            }]
        else:
            phase_start("outer")
            try:
                result = _run_outer_candidate(
                    stack, rhs, framework=framework, restart=outer_restart, max_it=max_it,
                    sample=sample, marker=marker, checkpoint_root=checkpoint_root,
                    input_sha256=input_sha256, operator_sha256=operator_sha256,
                    physical_sha256=physical_sha256, source_sha=source_sha, stage=stage,
                    output_name="original" if not notch else "notch",
                    reference_x_ref=reference_binding.get("x_ref"),
                )
            finally:
                phase_finish("outer")
            candidate_results.append(result)
            summary["candidates"] = [{
                key: value for key, value in result.items() if key != "final_solution"
            }]
        # Probe and production stages share the same official-output rule:
        # output recovery is admitted only after the full explicit residual
        # gate.  This also makes a successful O2 probe a valid original solve
        # candidate instead of silently discarding its physical observables.
        if result["status"] == "COMPLETED_TRUE_RESIDUAL":
            from src.solvers.physical_macro_dd4 import release_macro_auxiliary_for_recovery

            solution = result["final_solution"]
            recovery_checkpoint = _write_checkpoint(
                checkpoint_root,
                solution,
                int(result["iterations"]),
                float(result["final_true_residual"]),
                input_sha256=input_sha256,
                operator_sha256=operator_sha256,
                physical_sha256=physical_sha256,
                source_sha=source_sha,
                prefix="recovery",
            )
            summary["recovery_package"] = {
                "status": "DURABLE_BEFORE_AUXILIARY_RELEASE",
                "checkpoint": recovery_checkpoint,
                "true_residual": float(result["final_true_residual"]),
                "iterations": int(result["iterations"]),
                "operator_identity_sha256": operator_sha256,
                "physical_model_sha256": physical_sha256,
                "input_identity_sha256": input_sha256,
                "recovery_rule": "restore the hash-bound solution shard before any new PDE solve",
            }
            save_packet(directory, "recovery_package", summary["recovery_package"])
            marker("recovery_package_durable", summary["recovery_package"])
            release_macro_auxiliary_for_recovery(stack)
            summary["recovery_release_resource"] = dict(sample())
            marker("recovery_auxiliary_released", summary["recovery_release_resource"])
            output = recover_p0_outputs(
                stack["fine"], solution, directory / "numerical_output",
                export_all_port_modes=True,
            )
            field = _field_compare(stack, solution, reference_binding.get("x_ref"))
            output_compare = _compare_saved_output(
                output, reference_binding["reference_output"],
                current_dir=directory / "numerical_output",
                reference_dir=Path(reference_binding["reference_output_dir"]),
            )
            modal = output_compare["modal"]
            total_differences = output_compare["power"]["total_absolute_differences"]
            closure = output_compare["closure"]
            finite = output_compare["finite"]
            selected_field = output_compare["selected_field"]
            official_pass = bool(
                result["final_true_residual"] <= V12_TRUE_RESIDUAL_LIMIT
                and field.get("status") == "REFERENCE_FIELD_AVAILABLE"
                and field.get("max_relative", float("inf")) <= V12_FIELD_LIMIT
                and modal["mode_count"] == 80
                and modal["power_max_absolute_difference"] <= V12_MODE_POWER_LIMIT
                and modal["amplitude_relative_difference"] <= V12_MODE_AMPLITUDE_LIMIT
                and max(total_differences.values()) <= V12_OUTPUT_LIMIT
                and max(closure.values()) <= V12_OUTPUT_LIMIT
                and all(finite.values())
                and selected_field.get("status") == "AVAILABLE"
            )
            official = {
                "status": "OFFICIAL_RESULT_PASS" if official_pass else "OFFICIAL_RESULT_FAIL",
                "true_residual": float(result["final_true_residual"]),
                "field": field,
                "output": output_compare,
                "reference_authority": reference_binding["authority"],
                "new_reference_solve": False,
            }
            summary["official_result"] = official
            save_packet(directory, "official_result", {
                "summary": official,
                "output": output,
            })
        if stage.startswith("O2_"):
            reached48 = int(result["iterations"]) >= 48
            summary["reach_48"] = reached48
            summary["reach_64"] = int(result["iterations"]) >= 64
            summary["status"] = "O2_CANDIDATE_COMPLETED" if reached48 else "O2_CANDIDATE_CONTROLLED_STOP"
        else:
            official = summary.get("official_result")
            summary["status"] = (
                "O3_COMPLETED" if official and official["status"] == "OFFICIAL_RESULT_PASS"
                else "O3_COMPLETED_WITHOUT_OFFICIAL_RESULT" if result["status"] == "COMPLETED_TRUE_RESIDUAL"
                else "O3_CONTROLLED_STOP"
            )
        save_packet(directory, "outer_summary", summary)
        return summary
    except BaseException as exc:
        summary.update(
            status="V12_OUTER_FAILED",
            exception_type=type(exc).__name__,
            exception=str(exc),
        )
        save_packet(directory, "outer_summary", summary)
        raise
    finally:
        if rhs is not None:
            rhs.destroy()
        for result in candidate_results:
            _release_result(result)
        if stack is not None:
            destroy_macro_stack(stack)


__all__ = [
    "V12_LOCAL_INVENTORY_CAP_BYTES",
    "V12_MEMORY_POLICY",
    "V12_PROFILE",
    "run_macro_v12_outer",
    "run_macro_v12_precheck",
]
