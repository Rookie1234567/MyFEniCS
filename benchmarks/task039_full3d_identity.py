"""Offline A2 identity checks for Task39 Full3D direct and iterative runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    compare_canonical_manifests,
    read_canonical_manifest,
)
from src.io.resolved_config import canonical_json_bytes

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_PLANES = (10.0, 30.0, 60.0, 90.0, 110.0)
_CANONICAL_TOLERANCE = 1.0e-5


class IdentityCheckError(ValueError):
    """A missing, malformed, or contradictory authority artifact."""


def _fail(message: str) -> None:
    raise IdentityCheckError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityCheckError(f"cannot read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        _fail(f"JSON artifact is not an object: {path}")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise IdentityCheckError(f"cannot hash artifact: {path}") from exc


def _artifact(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        _fail(f"missing {label}: {path}")
    return {"label": label, "path": str(path), "sha256": _sha256(path)}


def _resolve(base: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        _fail(f"artifact path is not a non-empty string: {value!r}")
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if (base / candidate).exists():
        return base / candidate
    return (
        _REPO_ROOT / candidate
        if (_REPO_ROOT / candidate).exists()
        else base / candidate
    )


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{label} is not a finite scalar: {value!r}")
    result = float(value)
    if not math.isfinite(result):
        _fail(f"{label} is not finite: {value!r}")
    return result


def _exact(value: Any, expected: Any, label: str) -> None:
    if value != expected:
        _fail(f"{label}={value!r}, expected {expected!r}")


def _complex_pair(value: Any, label: str) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        _fail(f"{label} is not a JSON complex pair")
    return complex(
        _finite(value[0], f"{label}.real"), _finite(value[1], f"{label}.imag")
    )


def _mode_key(value: Any, label: str) -> tuple[str, int, int, str]:
    if isinstance(value, Mapping):
        side, m, n, polarization = (
            value.get(k) for k in ("side", "m", "n", "polarization")
        )
    elif isinstance(value, list) and len(value) == 4:
        side, m, n, polarization = value
    else:
        _fail(f"{label} is not a mode-key object or four-item list")
    if not isinstance(side, str) or not isinstance(polarization, str):
        _fail(f"{label} has invalid side or polarization")
    if (
        isinstance(m, bool)
        or not isinstance(m, int)
        or isinstance(n, bool)
        or not isinstance(n, int)
    ):
        _fail(f"{label} has non-integer m/n")
    return side, m, n, polarization


def _key_sha(keys: Sequence[tuple[str, int, int, str]]) -> str:
    return hashlib.sha256(canonical_json_bytes([list(key) for key in keys])).hexdigest()


def _parse_inventory(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label} external_mode_inventory is missing")
    inventory = dict(value)
    raw_keys = inventory.get("keys")
    if not isinstance(raw_keys, list):
        _fail(f"{label} external_mode_inventory.keys is missing")
    keys = tuple(
        _mode_key(item, f"{label}.keys[{i}]") for i, item in enumerate(raw_keys)
    )
    if len(keys) != 604 or len(set(keys)) != 604:
        _fail("external mode inventory must contain 604 unique keys")
    return {
        "value": inventory,
        "keys": keys,
        "count": len(keys),
        "sha256": hashlib.sha256(canonical_json_bytes(inventory)).hexdigest(),
        "key_sha256": _key_sha(keys),
        "counts": inventory.get("counts"),
    }


def _inventory(
    manifest: Mapping[str, Any], numeric: Mapping[str, Any]
) -> dict[str, Any]:
    manifest_inventory = _parse_inventory(
        manifest.get("external_mode_inventory"), "manifest"
    )
    numeric_value = numeric.get("external_mode_inventory")
    numeric_inventory = (
        None if numeric_value is None else _parse_inventory(numeric_value, "numeric")
    )
    exact: bool | str = (
        "not_applicable"
        if numeric_inventory is None
        else manifest_inventory["value"] == numeric_inventory["value"]
    )
    return {
        **manifest_inventory,
        "manifest_sha256": manifest_inventory["sha256"],
        "numeric_sha256": None
        if numeric_inventory is None
        else numeric_inventory["sha256"],
        "numeric_inventory_available": numeric_inventory is not None,
        "numeric_inventory_exact": exact,
    }


def _load_reference(numeric_dir: Path) -> dict[str, Any]:
    json_path = numeric_dir / "full3d_reference_samples.json"
    reference = _json(json_path)
    _exact(
        reference.get("array_shape_z_y_x_component"), [5, 20, 40, 3], "reference shape"
    )
    archive_path = _resolve(numeric_dir, reference.get("archive"))
    archive_sha = _sha256(archive_path)
    _exact(archive_sha, reference.get("archive_sha256"), "reference archive SHA256")
    _exact(
        archive_path.stat().st_size,
        reference.get("archive_bytes"),
        "reference archive bytes",
    )
    try:
        with np.load(archive_path, allow_pickle=False) as archive:
            arrays = {name: np.asarray(archive[name]).copy() for name in archive.files}
    except (OSError, ValueError) as exc:
        raise IdentityCheckError(
            f"cannot read reference archive: {archive_path}"
        ) from exc
    expected_shapes = {"x_nm": (40,), "y_nm": (20,), "z_nm": (5,)}
    for name, shape in expected_shapes.items():
        array = arrays.get(name)
        if (
            array is None
            or array.shape != shape
            or array.dtype != np.float64
            or not np.isfinite(array).all()
        ):
            _fail(f"reference coordinate array {name} has invalid shape/dtype/values")
    for name in ("E_V_per_m", "H_A_per_m"):
        array = arrays.get(name)
        if (
            array is None
            or array.shape != (5, 20, 40, 3)
            or array.dtype != np.complex128
            or not np.isfinite(array).all()
        ):
            _fail(f"reference array {name} has invalid shape/dtype/values")
    if tuple(arrays["z_nm"]) != _PLANES:
        _fail("reference z coordinates are not the five frozen planes")
    metrics = reference.get("plane_metrics")
    if (
        not isinstance(metrics, list)
        or tuple(item.get("z_nm") for item in metrics) != _PLANES
    ):
        _fail("reference plane_metrics coordinates are invalid")
    return {
        "json": reference,
        "json_artifact": _artifact(json_path, "full3d_reference_samples.json"),
        "archive_artifact": {
            "label": "full3d_reference_samples.npz",
            "path": str(archive_path),
            "sha256": archive_sha,
            "bytes": archive_path.stat().st_size,
        },
        "arrays": arrays,
        "coordinates": {name: arrays[name] for name in expected_shapes},
        "planes_nm": list(_PLANES),
        "array_shapes": {
            name: list(arrays[name].shape) for name in ("E_V_per_m", "H_A_per_m")
        },
        "array_dtypes": {
            name: str(arrays[name].dtype) for name in ("E_V_per_m", "H_A_per_m")
        },
        "array_sha256": {
            name: hashlib.sha256(
                np.ascontiguousarray(arrays[name]).tobytes()
            ).hexdigest()
            for name in ("E_V_per_m", "H_A_per_m")
        },
        "coordinate_sha256": {
            name: hashlib.sha256(
                np.ascontiguousarray(arrays[name]).tobytes()
            ).hexdigest()
            for name in expected_shapes
        },
    }


def _load_orders(
    numeric_dir: Path, expected_keys: set[tuple[str, int, int, str]]
) -> dict[str, Any]:
    path = numeric_dir / "dtn_port_diffraction_orders_3d.json"
    payload = _json(path)
    rows = payload.get("orders")
    if not isinstance(rows, list) or len(rows) != 604:
        _fail("diffraction order artifact does not contain 604 rows")
    by_key: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(f"diffraction order row {index} is not an object")
        key = _mode_key(
            [row.get("side"), row.get("m"), row.get("n"), row.get("polarization")],
            f"order[{index}]",
        )
        if key in by_key:
            _fail(f"duplicate diffraction order key: {key!r}")
        power = _finite(row.get("power_ratio"), f"order {key}.power_ratio")
        if power < 0.0:
            _fail(f"negative diffraction order power: {key!r}")
        by_key[key] = {
            "power_ratio": power,
            "outgoing_amplitude": _complex_pair(
                row.get("outgoing_amplitude"), f"order {key}.outgoing_amplitude"
            ),
        }
    if set(by_key) != expected_keys:
        _fail("diffraction order keys do not exactly match dynamic inventory")
    return {
        "artifact": _artifact(path, "dtn_port_diffraction_orders_3d.json"),
        "rows": by_key,
        "count": len(by_key),
        "key_sha256": _key_sha(tuple(sorted(by_key))),
    }


def _load_canonical(
    numeric_dir: Path, numeric: Mapping[str, Any], role: str
) -> dict[str, Any]:
    key = (
        "full3d_direct_canonical_export"
        if role == "direct"
        else "task037_m3a_canonical_export"
    )
    descriptor = numeric.get(key)
    if not isinstance(descriptor, Mapping) or descriptor.get("status") != "completed":
        _fail(f"{key} is missing or incomplete")
    roles = descriptor.get("roles")
    if not isinstance(roles, Mapping) or set(roles) != {"active_trace", "full_fe"}:
        _fail(f"{key} must contain active_trace and full_fe only")
    result: dict[str, Any] = {}
    for canonical_role in ("active_trace", "full_fe"):
        item = roles.get(canonical_role)
        if not isinstance(item, Mapping):
            _fail(f"{key}.{canonical_role} is missing")
        manifest_path = _resolve(numeric_dir, item.get("manifest"))
        manifest_sha = item.get("manifest_sha256")
        if not isinstance(manifest_sha, str) or not _SHA256.fullmatch(manifest_sha):
            _fail(f"{key}.{canonical_role} manifest SHA is invalid")
        try:
            manifest = read_canonical_manifest(manifest_path, manifest_sha)
        except (OSError, ValueError, KeyError) as exc:
            raise IdentityCheckError(
                f"cannot validate {key}.{canonical_role} manifest"
            ) from exc
        _exact(manifest.get("role"), canonical_role, f"{key}.{canonical_role}.role")
        _exact(manifest.get("mpi_size"), 8, f"{key}.{canonical_role}.mpi_size")
        shards = manifest.get("per_rank_shards")
        if (
            not isinstance(shards, list)
            or len(shards) != 8
            or sorted(item.get("rank") for item in shards) != list(range(8))
        ):
            _fail(f"{key}.{canonical_role} must contain eight rank shards")
        if manifest.get("summed_local_duplicate_count") != 0:
            _fail(f"{key}.{canonical_role} contains duplicate keys")
        packet_count = manifest.get("global_summed_packet_count")
        if (
            not isinstance(packet_count, int)
            or packet_count <= 0
            or item.get("global_summed_packet_count") != packet_count
        ):
            _fail(f"{key}.{canonical_role} packet count is invalid")
        result[canonical_role] = {
            "manifest": _artifact(manifest_path, f"{key}.{canonical_role}.manifest"),
            "path": manifest_path,
            "sha256": manifest_sha,
            "packet_count": packet_count,
            "shards": len(shards),
        }
    return {"summary_key": key, "roles": result}


def _load_run(run_dir: str | Path, role: str) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    numeric_dir = root / "numerical_output"
    manifest_path, outer_path, numeric_path = (
        root / "run_manifest.json",
        root / "run_summary.json",
        numeric_dir / "run_summary.json",
    )
    manifest, outer, numeric = (
        _json(manifest_path),
        _json(outer_path),
        _json(numeric_path),
    )
    manifest_artifact = _artifact(manifest_path, "run_manifest.json")
    outer_artifact = _artifact(outer_path, "run_summary.json")
    numeric_artifact = _artifact(numeric_path, "numerical_output/run_summary.json")
    for source in (manifest, outer):
        _exact(source.get("status"), "finished", "run status")
        _exact(source.get("exit_status"), 0, "run exit_status")
    _exact(numeric.get("case_status"), "completed", "numerical case_status")
    _exact(numeric.get("official_result"), True, "numerical official_result")
    method = "full3d_direct" if role == "direct" else "full3d_iterative"
    _exact(manifest.get("method"), method, "manifest.method")
    _exact(manifest.get("model_id"), f"task039_5nm_{method}", "manifest.model_id")
    _exact(
        manifest.get("resolved_method_adapter"),
        "task038.full3d_direct" if role == "direct" else "task039.full3d_iterative",
        "manifest.resolved_method_adapter",
    )
    for key, pattern in (
        ("source_sha", _SOURCE_SHA),
        ("input_sha256", _SHA256),
        ("resolved_config_sha256", _SHA256),
        ("physical_model_sha256", _SHA256),
    ):
        if not isinstance(manifest.get(key), str) or not pattern.fullmatch(
            manifest[key]
        ):
            _fail(f"manifest.{key} is not a valid identity SHA")
    _exact(manifest.get("mpi_size"), 8, "manifest.mpi_size")
    _exact(numeric.get("mpi_size"), 8, "numerical.mpi_size")
    for key, expected in {
        "lambda0_nm": 5.0,
        "nedelec_degree": 6,
        "mesh_target_size": 10.0,
        "polarization_kind": "s",
        "incident_theta_deg": 80.0,
        "incident_phi_deg": 0.0,
        "stage4_full3d_assembly_backend_actual": "assembly_time_static_condensed",
        "stage4_dtn_order_policy": "auto_propagating",
        "dtn_port_mode_count": 604,
    }.items():
        _exact(numeric.get(key), expected, f"numerical.{key}")
    inventory = _inventory(manifest, numeric)
    orders = _load_orders(numeric_dir, set(inventory["keys"]))
    reference = _load_reference(numeric_dir)
    canonical = _load_canonical(numeric_dir, numeric, role)
    resource = outer.get("resource_authority")
    if not isinstance(resource, Mapping):
        _fail("run_summary.resource_authority is missing")
    artifacts = {
        "run_manifest": manifest_artifact,
        "outer_run_summary": outer_artifact,
        "numerical_run_summary": numeric_artifact,
        "diffraction_orders": orders["artifact"],
        "reference_json": reference["json_artifact"],
        "reference_archive": reference["archive_artifact"],
        "active_trace_canonical_manifest": canonical["roles"]["active_trace"][
            "manifest"
        ],
        "full_fe_canonical_manifest": canonical["roles"]["full_fe"]["manifest"],
    }
    return {
        "root": root,
        "manifest": manifest,
        "numeric": numeric,
        "inventory": inventory,
        "orders": orders,
        "reference": reference,
        "canonical": canonical,
        "resource": dict(resource),
        "artifacts": artifacts,
    }


def _relative(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-30)


def _complex_relative(left: complex, right: complex) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-30)


def _iterative_gate(run: Mapping[str, Any]) -> dict[str, Any]:
    numeric, resource = run["numeric"], run["resource"]
    errors: list[str] = []
    swap = _finite(resource.get("process_tree_peak_swap_mb"), "iterative swap")
    if swap != 0.0:
        errors.append(f"iterative swap is {swap}, expected 0")
    audit = numeric.get("task039_m3a_core_audit")
    profile = numeric.get("task039_solver_profile")
    if not isinstance(audit, Mapping) or not isinstance(profile, Mapping):
        _fail("iterative profile/audit is missing")
    required_profile = {
        "screen_iterations": 4000,
        "restart": 90,
        "relative_tolerance": 1.0e-6,
        "initial_guess": "zero",
        "preconditioner": "full3d_m3a_physical_slab_two_level",
    }
    required_candidate = {
        "outer_ksp": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": 90,
        "rtol": 1.0e-6,
        "atol": 0.0,
        "max_it": 4000,
        "num_slabs": 16,
        "overlap_fraction": 0.125,
        "interpolation": "partition",
        "absorption_shift": 0.1,
    }
    candidate, no_global = (
        audit.get("candidate"),
        audit.get("no_global_factor_inventory"),
    )
    if not isinstance(candidate, Mapping) or not isinstance(no_global, Mapping):
        _fail("iterative candidate/no-global audit is missing")
    checks = {
        f"profile.{key}": profile.get(key) == value
        for key, value in required_profile.items()
    }
    checks.update(
        {
            f"candidate.{key}": candidate.get(key) == value
            for key, value in required_candidate.items()
        }
    )
    checks.update(
        {
            "external_linear_solver_port": numeric.get("external_linear_solver_port")
            is True,
            "ksp_converged": numeric.get("ksp_converged") is True,
            "stage4_energy_balance_pass": numeric.get("stage4_energy_balance_pass")
            is True,
            "matrix_type": audit.get("matrix_type") == "python_action_only",
            "audit_global_A_materialized": audit.get("global_A_materialized") is False,
            "audit_global_F_materialized": audit.get("global_F_materialized") is False,
            "global_A_materialized": numeric.get("global_A_materialized") is False,
            "global_F_materialized": numeric.get("global_F_materialized") is False,
            "global_direct_factor_count": no_global.get("global_direct_factor_count")
            == 0,
            "global_schur_matrix_materialized": no_global.get(
                "global_schur_matrix_materialized"
            )
            is False,
            "no_global_A_materialized": no_global.get("global_A_materialized") is False,
            "no_global_F_materialized": no_global.get("global_F_materialized") is False,
            "external_solver_profile": numeric.get("external_solver_profile")
            == "never_materialized_owner_local_overlap0125_partition",
            "audit_solver_profile": audit.get("solver_profile")
            == "never_materialized_owner_local_overlap0125_partition",
        }
    )
    checks["iterations"] = (
        isinstance(numeric.get("ksp_iterations"), int)
        and 0 <= numeric["ksp_iterations"] <= 4000
    )
    checks["reason"] = (
        isinstance(numeric.get("ksp_converged_reason"), int)
        and numeric["ksp_converged_reason"] > 0
    )
    residuals = {}
    for name in (
        "linear_system_relative_residual",
        "reported_relative_residual",
        "condensed_true_residual",
        "full_augmented_true_residual",
    ):
        value = (
            numeric.get(name)
            if name == "linear_system_relative_residual"
            else audit.get(f"external_{name}")
        )
        residuals[name] = _finite(value, f"iterative {name}")
        checks[f"residual.{name}"] = residuals[name] <= 1.0e-6
    errors.extend(
        f"iterative gate failed: {name}"
        for name, passed in checks.items()
        if not passed
    )
    return {
        "pass": not errors,
        "errors": errors,
        "checks": checks,
        "residuals": residuals,
        "threshold": 1.0e-6,
        "swap_mb": swap,
    }


def _public_run(run: Mapping[str, Any]) -> dict[str, Any]:
    manifest, inventory, reference, canonical = (
        run["manifest"],
        run["inventory"],
        run["reference"],
        run["canonical"],
    )
    return {
        "run_directory": str(run["root"]),
        "source_sha": manifest["source_sha"],
        "input_sha256": manifest["input_sha256"],
        "resolved_config_sha256": manifest["resolved_config_sha256"],
        "physical_model_sha256": manifest["physical_model_sha256"],
        "model_id": manifest["model_id"],
        "run_id": manifest.get("run_id"),
        "mpi_size": manifest["mpi_size"],
        "inventory": {
            "count": inventory["count"],
            "manifest_canonical_sha256": inventory["manifest_sha256"],
            "numeric_canonical_sha256": inventory["numeric_sha256"],
            "numeric_inventory_available": inventory["numeric_inventory_available"],
            "numeric_inventory_exact": inventory["numeric_inventory_exact"],
            "key_sha256": inventory["key_sha256"],
            "counts": inventory["counts"],
        },
        "reference": {
            "planes_nm": reference["planes_nm"],
            "array_shapes": reference["array_shapes"],
            "array_dtypes": reference["array_dtypes"],
            "array_sha256": reference["array_sha256"],
            "coordinate_sha256": reference["coordinate_sha256"],
            "archive": reference["archive_artifact"],
        },
        "canonical": {
            role: {
                "manifest": value["manifest"],
                "packet_count": value["packet_count"],
                "shard_count": value["shards"],
            }
            for role, value in canonical["roles"].items()
        },
        "resource_authority": run["resource"],
        "artifacts": run["artifacts"],
    }


def _compare_full3d_identity(
    direct_run_dir: str | Path, iterative_run_dir: str | Path
) -> dict[str, Any]:
    direct, iterative = (
        _load_run(direct_run_dir, "direct"),
        _load_run(iterative_run_dir, "iterative"),
    )
    errors: list[str] = []
    di, ii = direct["inventory"], iterative["inventory"]
    inventory_pass = (
        di["sha256"] == ii["sha256"]
        and di["keys"] == ii["keys"]
        and di["count"] == ii["count"] == 604
        and all(
            item["numeric_inventory_exact"] in (True, "not_applicable")
            for item in (di, ii)
        )
    )
    if not inventory_pass:
        errors.append("direct and iterative dynamic inventories are not exact matches")
    physical_pass = (
        direct["manifest"]["physical_model_sha256"]
        == iterative["manifest"]["physical_model_sha256"]
    )
    if not physical_pass:
        errors.append("physical_model_sha256 differs between runs")
    observables = {}
    for name in ("R_total", "T_total", "A_balance", "A_volume_total"):
        left, right = (
            _finite(direct["numeric"].get(name), f"direct {name}"),
            _finite(iterative["numeric"].get(name), f"iterative {name}"),
        )
        delta = abs(left - right)
        observables[name] = {
            "direct": left,
            "iterative": right,
            "abs_delta": delta,
            "threshold": 1.0e-6,
            "pass": delta <= 1.0e-6,
        }
        if delta > 1.0e-6:
            errors.append(f"{name} absolute delta exceeds 1e-6")
    closure = {}
    for label, run in (("direct", direct), ("iterative", iterative)):
        value = _finite(
            run["numeric"].get("energy_closure_error_port_volume"), f"{label} closure"
        )
        closure[label] = {
            "value": value,
            "threshold": 1.0e-5,
            "pass": abs(value) <= 1.0e-5,
        }
        if abs(value) > 1.0e-5:
            errors.append(f"{label} energy closure exceeds 1e-5")
    do, io = direct["orders"]["rows"], iterative["orders"]["rows"]
    significant = tuple(
        sorted(
            key
            for key in do
            if max(do[key]["power_ratio"], io[key]["power_ratio"]) >= 1.0e-8
        )
    )
    order_failures, max_power, max_amplitude = [], 0.0, 0.0
    for key in significant:
        power_delta = _relative(do[key]["power_ratio"], io[key]["power_ratio"])
        amplitude_delta = _complex_relative(
            do[key]["outgoing_amplitude"], io[key]["outgoing_amplitude"]
        )
        max_power, max_amplitude = (
            max(max_power, power_delta),
            max(max_amplitude, amplitude_delta),
        )
        if power_delta > 1.0e-4 or amplitude_delta > 1.0e-4:
            order_failures.append(
                {
                    "key": list(key),
                    "power_relative_delta": power_delta,
                    "amplitude_relative_delta": amplitude_delta,
                }
            )
    if order_failures:
        errors.append("significant diffraction order comparison failed")
    coordinates_exact = all(
        np.array_equal(
            direct["reference"]["coordinates"][name],
            iterative["reference"]["coordinates"][name],
        )
        for name in ("x_nm", "y_nm", "z_nm")
    )
    reference_result = {
        "coordinates_exact": coordinates_exact,
        "coordinate_sha256": {
            "direct": direct["reference"]["coordinate_sha256"],
            "iterative": iterative["reference"]["coordinate_sha256"],
        },
    }
    if not coordinates_exact:
        errors.append("selected reference coordinate arrays differ")
    for name in ("E_V_per_m", "H_A_per_m"):
        left, right = (
            direct["reference"]["arrays"][name],
            iterative["reference"]["arrays"][name],
        )
        delta = float(
            np.linalg.norm(left - right)
            / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-30)
        )
        reference_result[name] = {
            "relative_l2": delta,
            "threshold": 1.0e-5,
            "pass": delta <= 1.0e-5,
        }
        if delta > 1.0e-5:
            errors.append(f"selected {name} relative L2 exceeds 1e-5")
    canonical_result = {}
    for role in ("active_trace", "full_fe"):
        left, right = (
            direct["canonical"]["roles"][role],
            iterative["canonical"]["roles"][role],
        )
        try:
            comparison = compare_canonical_manifests(
                left["path"],
                right["path"],
                left_sha256=left["sha256"],
                right_sha256=right["sha256"],
                relative_tolerance=_CANONICAL_TOLERANCE,
            )
        except (OSError, ValueError, KeyError) as exc:
            raise IdentityCheckError(f"canonical {role} comparison failed") from exc
        canonical_result[role] = comparison
        if not comparison.get("pass"):
            errors.append(f"canonical {role} comparison failed")
    iterative_gate = _iterative_gate(iterative)
    errors.extend(iterative_gate["errors"])
    return {
        "schema_version": "task039.full3d-identity.v1",
        "pass": not errors,
        "classification": "A2_FULL3D_IDENTITY_PASS"
        if not errors
        else "A2_FULL3D_IDENTITY_FAIL",
        "errors": errors,
        "thresholds": {
            "observable_abs_delta": 1.0e-6,
            "energy_closure_abs": 1.0e-5,
            "significant_power_relative_delta": 1.0e-4,
            "significant_amplitude_relative_delta": 1.0e-4,
            "selected_reference_relative_l2": 1.0e-5,
            "canonical_relative_l2": _CANONICAL_TOLERANCE,
        },
        "physical_model_sha256": direct["manifest"]["physical_model_sha256"],
        "inventory": {
            "count": di["count"],
            "manifest_canonical_sha256": di["manifest_sha256"],
            "numeric_canonical_sha256": di["numeric_sha256"],
            "numeric_inventory_available": di["numeric_inventory_available"],
            "numeric_inventory_exact": di["numeric_inventory_exact"],
            "key_sha256": di["key_sha256"],
            "exact_match": inventory_pass,
        },
        "runs": {"direct": _public_run(direct), "iterative": _public_run(iterative)},
        "comparisons": {
            "observables": observables,
            "energy_closure": closure,
            "significant_orders": {
                "count": len(significant),
                "threshold": 1.0e-8,
                "normalization": "incident_power",
                "max_power_relative_delta": max_power,
                "max_amplitude_relative_delta": max_amplitude,
                "failures": order_failures,
                "pass": not order_failures,
            },
            "selected_reference": reference_result,
            "canonical": canonical_result,
            "iterative_gate": iterative_gate,
        },
    }


def check_full3d_identity(
    direct_run_dir: str | Path, iterative_run_dir: str | Path
) -> dict[str, Any]:
    """Return a JSON-safe fail-closed A2 comparison."""
    try:
        return _compare_full3d_identity(direct_run_dir, iterative_run_dir)
    except IdentityCheckError as exc:
        return {
            "schema_version": "task039.full3d-identity.v1",
            "pass": False,
            "classification": "A2_FULL3D_IDENTITY_FAIL",
            "errors": [str(exc)],
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct-run", required=True, type=Path)
    parser.add_argument("--iterative-run", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = check_full3d_identity(args.direct_run, args.iterative_run)
    except Exception as exc:
        print(
            json.dumps(
                {"pass": False, "classification": "CHECKER_ERROR", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0 if result["pass"] else 1


__all__ = ["check_full3d_identity", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
