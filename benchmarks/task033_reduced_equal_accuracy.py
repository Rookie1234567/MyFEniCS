"""Reduced fixed-p equal-accuracy evidence aggregation for Task033.

This module deliberately does not feed the original 21-role Task033 formal
manifest.  It binds the smaller Review-V5 campaign to raw, ignored PDE
artifacts and answers one scoped question: whether a coarser p3 discretization
is no less accurate than the reused p2/h3 baseline against the best available
p3/h5 discrete reference, while reducing measured resources. Review V6 freezes
that result as a fixed-p clear success with explicit execution semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SIGNIFICANT_ORDER_POWER = 1.0e-8
TRUE_RESIDUAL_MAX = 1.0e-9
M_FUNNEL_RTA_ABSOLUTE_MAX = 1.0e-5
M_FUNNEL_ORDER_AMPLITUDE_RELATIVE_MAX = 1.0e-3


class ReducedEqualAccuracyError(ValueError):
    """Raised when a reduced-campaign evidence binding is incomplete."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReducedEqualAccuracyError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReducedEqualAccuracyError(f"JSON evidence must be an object: {path}")
    return payload


def _repo_path(path: Path | str, *, root: Path) -> tuple[Path, str]:
    requested = Path(path)
    resolved = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    try:
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ReducedEqualAccuracyError(f"evidence path escapes repository: {path}") from exc
    return resolved, relative


def _finite(value: object, *, label: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReducedEqualAccuracyError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise ReducedEqualAccuracyError(f"{label} must be finite{' and positive' if positive else ''}")
    return result


def _integer(value: object, *, label: str) -> int:
    number = _finite(value, label=label, positive=True)
    rounded = round(number)
    if not math.isclose(number, rounded, rel_tol=0.0, abs_tol=1.0e-9):
        raise ReducedEqualAccuracyError(f"{label} must be an integer")
    return int(rounded)


def _factor_inventory_nnz(
    inventory: Mapping[str, Any],
    *,
    label: str,
) -> int:
    """Read a factor count without reviving MUMPS int32 overflow."""

    corrected = inventory.get("factor_nnz_corrected")
    if corrected is not None:
        return _integer(corrected, label=f"{label} corrected NNZ")
    matrix = inventory.get("matrix_stats")
    if not isinstance(matrix, Mapping):
        raise ReducedEqualAccuracyError(f"{label} matrix stats are missing")
    return _integer(matrix.get("matrix_nnz_used"), label=f"{label} NNZ")


def classify_resource_reduction(ratio: float) -> str:
    """Classify baseline/candidate reduction using review-v5 boundaries."""

    value = _finite(ratio, label="resource reduction", positive=True)
    if value < 1.3:
        return "weak"
    if value < 2.0:
        return "useful_positive"
    if value < 3.0:
        return "clear_success"
    return "engineering_target"


def _relative_l2(candidate: np.ndarray, reference: np.ndarray) -> float:
    denominator = float(np.linalg.norm(reference.reshape(-1)))
    if not denominator > 0.0:
        raise ReducedEqualAccuracyError("reference field has zero L2 norm")
    return float(np.linalg.norm((candidate - reference).reshape(-1)) / denominator)


def _complex_pair(value: object, *, label: str) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ReducedEqualAccuracyError(f"{label} must be [real, imaginary]")
    return complex(
        _finite(value[0], label=f"{label}.real"),
        _finite(value[1], label=f"{label}.imag"),
    )


def _order_map(payload: Mapping[str, Any]) -> dict[tuple[str, int, int, str], Mapping[str, Any]]:
    rows = payload.get("orders")
    if not isinstance(rows, list):
        raise ReducedEqualAccuracyError("diffraction record lacks orders")
    result: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ReducedEqualAccuracyError("diffraction order row must be an object")
        key = (
            str(row.get("side")),
            int(row.get("order_m", row.get("m"))),
            int(row.get("order_n", row.get("n"))),
            str(row.get("polarization")),
        )
        if key in result:
            raise ReducedEqualAccuracyError(f"duplicate diffraction order {key}")
        result[key] = row
    return result


def _order_error(
    reference: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    candidate: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
) -> dict[str, Any]:
    if set(reference) != set(candidate):
        raise ReducedEqualAccuracyError("diffraction-order coverage differs")
    rows: list[dict[str, Any]] = []
    for key in sorted(reference):
        ref = reference[key]
        cand = candidate[key]
        ref_power = abs(_finite(ref.get("power_ratio"), label=f"{key}.reference_power"))
        cand_power = abs(_finite(cand.get("power_ratio"), label=f"{key}.candidate_power"))
        if max(ref_power, cand_power) < SIGNIFICANT_ORDER_POWER:
            continue
        ref_amplitude = _complex_pair(
            ref.get("outgoing_amplitude_at_boundary"), label=f"{key}.reference_amplitude"
        )
        cand_amplitude = _complex_pair(
            cand.get("outgoing_amplitude_at_boundary"), label=f"{key}.candidate_amplitude"
        )
        power_relative = abs(cand_power - ref_power) / max(
            ref_power, cand_power, SIGNIFICANT_ORDER_POWER
        )
        amplitude_relative = abs(cand_amplitude - ref_amplitude) / max(
            abs(ref_amplitude), abs(cand_amplitude), 1.0e-15
        )
        rows.append(
            {
                "key": list(key),
                "reference_power": ref_power,
                "candidate_power": cand_power,
                "power_relative_error": power_relative,
                "complex_amplitude_relative_error": amplitude_relative,
            }
        )
    if not rows:
        raise ReducedEqualAccuracyError("no significant diffraction orders")
    power = [float(row["power_relative_error"]) for row in rows]
    amplitude = [float(row["complex_amplitude_relative_error"]) for row in rows]
    return {
        "significant_order_count": len(rows),
        "power_relative_error_max": max(power),
        "power_relative_error_rms": math.sqrt(sum(value**2 for value in power) / len(power)),
        "complex_amplitude_relative_error_max": max(amplitude),
        "complex_amplitude_relative_error_rms": math.sqrt(
            sum(value**2 for value in amplitude) / len(amplitude)
        ),
        "rows": rows,
    }


def _assert_hash(path: Path, expected: object, *, label: str) -> str:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ReducedEqualAccuracyError(f"{label} expected SHA-256 is invalid")
    observed = _sha256(path)
    if observed != expected.lower():
        raise ReducedEqualAccuracyError(f"{label} SHA-256 mismatch")
    return observed


def _load_full3d(path: Path | str, *, root: Path) -> dict[str, Any]:
    descriptor_path, descriptor_repo_path = _repo_path(path, root=root)
    descriptor = _read_json(descriptor_path)
    artifacts = descriptor.get("artifacts")
    results = descriptor.get("results")
    physical = descriptor.get("physical_model")
    metadata = descriptor.get("metadata")
    qualification = descriptor.get("qualification")
    if not all(
        isinstance(value, Mapping)
        for value in (
            artifacts,
            results,
            physical,
            metadata,
            qualification,
        )
    ):
        raise ReducedEqualAccuracyError(f"incomplete full3D descriptor {descriptor_path}")
    run_root, run_root_repo_path = _repo_path(str(artifacts["ignored_run_root"]), root=root)
    run_summary_path = run_root / "run_summary.json"
    npz_path = run_root / "full3d_reference_samples.npz"
    orders_path = run_root / "dtn_port_diffraction_orders_3d.json"
    _assert_hash(run_summary_path, artifacts.get("run_summary_sha256"), label="run summary")
    _assert_hash(npz_path, artifacts.get("reference_npz_sha256"), label="reference NPZ")
    _assert_hash(
        orders_path,
        artifacts.get("dtn_port_diffraction_orders_sha256"),
        label="diffraction orders",
    )
    run_summary = _read_json(run_summary_path)
    if run_summary.get("case_status") != "completed" or run_summary.get("official_result") is not True:
        raise ReducedEqualAccuracyError(f"full3D source run is not complete: {run_summary_path}")
    if int(run_summary.get("num_nedelec_dofs")) != int(results.get("num_nedelec_dofs")):
        raise ReducedEqualAccuracyError("full3D descriptor DoF differs from raw run")
    arrays = np.load(npz_path)
    required_arrays = {
        "x_nm",
        "y_nm",
        "z_nm",
        "E_V_per_m",
        "H_A_per_m",
        "interface_z_nm",
        "E_t_interface_V_per_m",
        "H_t_interface_A_per_m",
    }
    if set(arrays.files) != required_arrays:
        raise ReducedEqualAccuracyError(f"unexpected full3D reference arrays: {arrays.files}")
    return {
        "descriptor": descriptor,
        "descriptor_path": descriptor_repo_path,
        "descriptor_sha256": _sha256(descriptor_path),
        "run_root": run_root_repo_path,
        "run_summary_path": run_summary_path.relative_to(root).as_posix(),
        "run_summary_sha256": _sha256(run_summary_path),
        "run_summary": run_summary,
        "arrays": arrays,
        "orders": _order_map(_read_json(orders_path)),
        "orders_sha256": _sha256(orders_path),
        "degree": int(physical["nedelec_degree"]),
        "h_nm": float(physical["mesh_h_nm"]),
        "execution": {
            "source_commit_sha": metadata.get("commit_sha"),
            "container_image": metadata.get("container_image"),
            "container_digest": metadata.get("container_digest"),
            "mpi_size": int(physical.get("mpi_size")),
            "solver_path": physical.get("linear_solver"),
            "no_swap": qualification.get("no_swap") is True,
            "memory_authority_gib": (
                _finite(
                    results.get("external_memory_authority_gib"),
                    label="full3D memory authority",
                    positive=True,
                )
                if results.get("external_memory_authority_gib") is not None
                else None
            ),
            "wall_time_seconds": (
                _finite(
                    results.get("elapsed_seconds"),
                    label="full3D wall time",
                    positive=True,
                )
                if results.get("elapsed_seconds") is not None
                else None
            ),
        },
    }


def compare_full3d_to_reference(reference: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Compare one full3D candidate against a common discrete reference."""

    ref_arrays = reference["arrays"]
    cand_arrays = candidate["arrays"]
    for coordinate in ("x_nm", "y_nm", "z_nm", "interface_z_nm"):
        if not np.array_equal(ref_arrays[coordinate], cand_arrays[coordinate]):
            raise ReducedEqualAccuracyError(f"sample coordinates differ for {coordinate}")
    plane_rows = []
    for index, z_nm in enumerate(ref_arrays["z_nm"]):
        plane_rows.append(
            {
                "z_nm": float(z_nm),
                "electric_relative_l2": _relative_l2(
                    cand_arrays["E_V_per_m"][index], ref_arrays["E_V_per_m"][index]
                ),
                "magnetic_relative_l2": _relative_l2(
                    cand_arrays["H_A_per_m"][index], ref_arrays["H_A_per_m"][index]
                ),
            }
        )
    interface_rows = []
    for index, z_nm in enumerate(ref_arrays["interface_z_nm"]):
        interface_rows.append(
            {
                "z_nm": float(z_nm),
                "electric_tangential_relative_l2": _relative_l2(
                    cand_arrays["E_t_interface_V_per_m"][index],
                    ref_arrays["E_t_interface_V_per_m"][index],
                ),
                "magnetic_tangential_relative_l2": _relative_l2(
                    cand_arrays["H_t_interface_A_per_m"][index],
                    ref_arrays["H_t_interface_A_per_m"][index],
                ),
            }
        )
    ref_results = reference["descriptor"]["results"]
    cand_results = candidate["descriptor"]["results"]
    scalar_rows = {
        key: {
            "reference": _finite(ref_results.get(key), label=f"reference.{key}"),
            "candidate": _finite(cand_results.get(key), label=f"candidate.{key}"),
            "absolute_error": abs(
                _finite(cand_results.get(key), label=f"candidate.{key}")
                - _finite(ref_results.get(key), label=f"reference.{key}")
            ),
        }
        for key in ("R_total", "T_total", "A_balance", "A_volume_total")
    }
    return {
        "scalar_observables": scalar_rows,
        "selected_planes": {
            "rows": plane_rows,
            "max_electric_relative_l2": max(
                float(row["electric_relative_l2"]) for row in plane_rows
            ),
            "max_magnetic_relative_l2": max(
                float(row["magnetic_relative_l2"]) for row in plane_rows
            ),
        },
        "interfaces": {
            "rows": interface_rows,
            "max_electric_tangential_relative_l2": max(
                float(row["electric_tangential_relative_l2"]) for row in interface_rows
            ),
            "max_magnetic_tangential_relative_l2": max(
                float(row["magnetic_tangential_relative_l2"]) for row in interface_rows
            ),
        },
        "diffraction_orders": _order_error(reference["orders"], candidate["orders"]),
        "full_true_relative_residual": _finite(
            cand_results.get("linear_system_true_relative_residual"),
            label="candidate full true residual",
        ),
    }


def _physical_no_worse(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for key in ("R_total", "T_total", "A_balance", "A_volume_total"):
        checks[f"{key}_absolute_error"] = (
            candidate["scalar_observables"][key]["absolute_error"]
            <= baseline["scalar_observables"][key]["absolute_error"]
        )
    checks.update(
        {
            "max_selected_plane_electric_relative_l2": (
                candidate["selected_planes"]["max_electric_relative_l2"]
                <= baseline["selected_planes"]["max_electric_relative_l2"]
            ),
            "max_selected_plane_magnetic_relative_l2": (
                candidate["selected_planes"]["max_magnetic_relative_l2"]
                <= baseline["selected_planes"]["max_magnetic_relative_l2"]
            ),
            "max_interface_electric_tangential_relative_l2": (
                candidate["interfaces"]["max_electric_tangential_relative_l2"]
                <= baseline["interfaces"]["max_electric_tangential_relative_l2"]
            ),
            "max_interface_magnetic_tangential_relative_l2": (
                candidate["interfaces"]["max_magnetic_tangential_relative_l2"]
                <= baseline["interfaces"]["max_magnetic_tangential_relative_l2"]
            ),
            "diffraction_power_relative_error_max": (
                candidate["diffraction_orders"]["power_relative_error_max"]
                <= baseline["diffraction_orders"]["power_relative_error_max"]
            ),
            "diffraction_power_relative_error_rms": (
                candidate["diffraction_orders"]["power_relative_error_rms"]
                <= baseline["diffraction_orders"]["power_relative_error_rms"]
            ),
            "diffraction_complex_amplitude_relative_error_max": (
                candidate["diffraction_orders"]["complex_amplitude_relative_error_max"]
                <= baseline["diffraction_orders"]["complex_amplitude_relative_error_max"]
            ),
            "diffraction_complex_amplitude_relative_error_rms": (
                candidate["diffraction_orders"]["complex_amplitude_relative_error_rms"]
                <= baseline["diffraction_orders"]["complex_amplitude_relative_error_rms"]
            ),
            "full_true_residual_below_gate": (
                candidate["full_true_relative_residual"] <= TRUE_RESIDUAL_MAX
            ),
        }
    )
    failures = [name for name, passed in checks.items() if not passed]
    return {"pass": not failures, "checks": checks, "failures": failures}


def _hybrid_metrics(summary_path: Path | str, *, root: Path) -> dict[str, Any]:
    path, repo_path = _repo_path(summary_path, root=root)
    payload = _read_json(path)
    if payload.get("schema_version") != "task033.memory-watchdog.v2":
        raise ReducedEqualAccuracyError(f"not a Task033 watchdog record: {path}")
    measurements = payload.get("measurements")
    if not isinstance(measurements, Mapping):
        raise ReducedEqualAccuracyError(f"watchdog lacks measurements: {path}")
    source = payload.get("source")
    worker_source = payload.get("worker_source")
    if (
        not isinstance(source, Mapping)
        or source.get("source_clean_verified") is not True
        or source.get("source_stable_during_run") is not True
        or not isinstance(worker_source, Mapping)
    ):
        raise ReducedEqualAccuracyError(f"watchdog lacks clean stable source: {path}")
    solver_path, _ = _repo_path(str(payload.get("solver_record_ignored_path")), root=root)
    _assert_hash(solver_path, payload.get("solver_record_sha256"), label="Hybrid solver record")
    hybrid = measurements.get("hybrid_system")
    ledger = measurements.get("object_payload_ledger")
    timing = measurements.get("timing_seconds_max_rank")
    resource = payload.get("resource_authority")
    validation = measurements.get("validation")
    reconstruction = measurements.get("physical_field_reconstruction")
    solve = measurements.get("solve")
    if not all(
        isinstance(value, Mapping)
        for value in (hybrid, ledger, timing, resource, validation, reconstruction, solve)
    ):
        raise ReducedEqualAccuracyError(f"Hybrid record is structurally incomplete: {path}")
    inventory = ledger.get("local_or_augmented_factor_inventory")
    if not isinstance(inventory, Mapping):
        raise ReducedEqualAccuracyError("Hybrid factor inventory is missing")
    dimensions = hybrid_dimension_costs(hybrid, validation=validation)
    factor_inventory_nnz = 0
    for side in ("bottom", "top"):
        side_record = inventory.get(side)
        if not isinstance(side_record, Mapping):
            raise ReducedEqualAccuracyError(f"Hybrid {side} factor inventory is missing")
        factor_inventory_nnz += _factor_inventory_nnz(
            side_record,
            label=f"{side} factor-inventory",
        )
    port_power = validation.get("port_power")
    selected = reconstruction.get("selected_plane_full3d_comparison")
    if not isinstance(port_power, Mapping) or not isinstance(selected, Mapping):
        raise ReducedEqualAccuracyError("Hybrid physical comparison is missing")
    return {
        "path": repo_path,
        "sha256": _sha256(path),
        "source_commit_sha": source.get("commit_sha"),
        "execution": {
            "source_commit_sha": source.get("commit_sha"),
            "container_image": worker_source.get("container_image"),
            "container_digest": worker_source.get("container_digest"),
            "mpi_size": int(worker_source.get("mpi_size")),
            "solver_path": worker_source.get("primary_solver_path"),
            "no_swap": payload.get("no_swap") is True,
            "memory_authority_semantics": resource.get(
                "memory_authority_semantics"
            ),
        },
        "requested_modes": int(payload.get("requested_modes")),
        "status": payload.get("status"),
        "formal_pass": payload.get("formal_pass") is True,
        "numeric_pass": payload.get("numeric_pass") is True,
        "no_swap": payload.get("no_swap") is True,
        "gates": measurements.get("gates"),
        "rta": {
            key: _finite(port_power.get(key), label=f"Hybrid {key}")
            for key in ("R_total", "T_total", "A_balance")
        },
        "orders": _order_map({"orders": validation.get("external_diffraction_orders")}),
        "max_selected_plane_electric_relative_l2": _finite(
            selected.get("max_middle_plane_electric_relative_l2"),
            label="Hybrid selected-plane E",
        ),
        "max_selected_plane_magnetic_relative_l2": _finite(
            selected.get("max_middle_plane_magnetic_relative_l2"),
            label="Hybrid selected-plane H",
        ),
        "true_relative_residual": _finite(
            solve.get("true_relative_residual"), label="Hybrid true residual"
        ),
        "costs": {
            **dimensions,
            "factor_inventory_nnz": factor_inventory_nnz,
            "memory_authority_gib": _finite(
                resource.get("memory_authority_gib"), label="Hybrid memory", positive=True
            ),
            "wall_time_seconds": _finite(timing.get("total"), label="Hybrid time", positive=True),
        },
        "full3d_reference_comparison": measurements.get("full3d_reference_comparison"),
    }


def _hybrid_funnel(m120: Mapping[str, Any], m160: Mapping[str, Any]) -> dict[str, Any]:
    if m120["source_commit_sha"] != m160["source_commit_sha"]:
        raise ReducedEqualAccuracyError("M120 and M160 source SHAs differ")
    rta_delta = {
        key: abs(float(m160["rta"][key]) - float(m120["rta"][key]))
        for key in ("R_total", "T_total", "A_balance")
    }
    order_delta = _order_error(m120["orders"], m160["orders"])
    selected_metric_delta = {
        "max_electric_relative_l2_metric_absolute_delta": abs(
            float(m160["max_selected_plane_electric_relative_l2"])
            - float(m120["max_selected_plane_electric_relative_l2"])
        ),
        "max_magnetic_relative_l2_metric_absolute_delta": abs(
            float(m160["max_selected_plane_magnetic_relative_l2"])
            - float(m120["max_selected_plane_magnetic_relative_l2"])
        ),
    }
    checks = {
        "same_clean_source_sha": True,
        "both_no_swap": bool(m120["no_swap"] and m160["no_swap"]),
        "both_formal_pass": bool(m120["formal_pass"] and m160["formal_pass"]),
        "rta_max_absolute_delta_le_1e-5": max(rta_delta.values()) <= M_FUNNEL_RTA_ABSOLUTE_MAX,
        "significant_order_amplitude_relative_delta_le_1e-3": (
            order_delta["complex_amplitude_relative_error_max"]
            <= M_FUNNEL_ORDER_AMPLITUDE_RELATIVE_MAX
        ),
        "both_true_residuals_le_1e-9": max(
            float(m120["true_relative_residual"]), float(m160["true_relative_residual"])
        )
        <= TRUE_RESIDUAL_MAX,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "rta_absolute_delta": rta_delta,
        "diffraction_orders": order_delta,
        "selected_plane_error_metric_delta": selected_metric_delta,
    }


def hybrid_dimension_costs(
    hybrid: Mapping[str, Any], *, validation: Mapping[str, Any]
) -> dict[str, int]:
    """Return FE-only, local-system, and total Hybrid row counts.

    ``bottom_global_size`` and ``top_global_size`` include each end's external
    Fourier-DtN auxiliary rows.  Newer records expose FE-only counts directly;
    legacy Task032 records require subtracting the recorded auxiliary arrays.
    """

    local_system_rows = _integer(
        hybrid.get("bottom_global_size"), label="bottom global size"
    ) + _integer(hybrid.get("top_global_size"), label="top global size")
    explicit_fe = (
        hybrid.get("bottom_local_fe_dofs"),
        hybrid.get("top_local_fe_dofs"),
    )
    if all(value is not None for value in explicit_fe):
        local_fe_dofs = _integer(
            explicit_fe[0], label="bottom local FE DoFs"
        ) + _integer(explicit_fe[1], label="top local FE DoFs")
    elif any(value is not None for value in explicit_fe):
        raise ReducedEqualAccuracyError(
            "Hybrid record exposes only one side's local FE DoFs"
        )
    else:
        amplitudes = validation.get("external_auxiliary_amplitudes")
        if not isinstance(amplitudes, Mapping):
            raise ReducedEqualAccuracyError(
                "legacy Hybrid record lacks external auxiliary amplitudes"
            )
        auxiliary_rows = 0
        for side in ("bottom", "top"):
            side_amplitudes = amplitudes.get(side)
            if not isinstance(side_amplitudes, list) or not side_amplitudes:
                raise ReducedEqualAccuracyError(
                    f"legacy Hybrid record lacks {side} auxiliary amplitudes"
                )
            auxiliary_rows += len(side_amplitudes)
        local_fe_dofs = local_system_rows - auxiliary_rows
        if local_fe_dofs <= 0:
            raise ReducedEqualAccuracyError(
                "external auxiliary rows exceed Hybrid local-system rows"
            )
    internal_rows = _integer(
        hybrid.get("internal_unknown_count"), label="internal unknown count"
    )
    return {
        "local_fe_dofs": local_fe_dofs,
        "local_system_rows": local_system_rows,
        "total_rows": local_system_rows + internal_rows,
    }


def _load_task032_hybrid_baseline(path: Path | str, *, root: Path) -> dict[str, Any]:
    watchdog_path, watchdog_repo_path = _repo_path(path, root=root)
    watchdog = _read_json(watchdog_path)
    solver_path, solver_repo_path = _repo_path(str(watchdog.get("solver_record")), root=root)
    solver = _read_json(solver_path)
    hybrid = solver.get("hybrid_system")
    ledger = watchdog.get("object_payload_ledger")
    timing = solver.get("timing_seconds_max_rank")
    memory = watchdog.get("memory")
    validation = solver.get("validation")
    source = watchdog.get("source")
    if not all(
        isinstance(value, Mapping)
        for value in (hybrid, ledger, timing, memory, validation, source)
    ):
        raise ReducedEqualAccuracyError("Task032 Hybrid baseline is incomplete")
    inventory = ledger.get("local_or_augmented_factor_inventory")
    if not isinstance(inventory, Mapping):
        raise ReducedEqualAccuracyError("Task032 Hybrid factor inventory is missing")
    dimensions = hybrid_dimension_costs(hybrid, validation=validation)
    factor_inventory_nnz = sum(
        _factor_inventory_nnz(
            inventory[side],
            label=f"{side} factor-inventory",
        )
        for side in ("bottom", "top")
    )
    return {
        "path": watchdog_repo_path,
        "sha256": _sha256(watchdog_path),
        "solver_path": solver_repo_path,
        "solver_sha256": _sha256(solver_path),
        "source_commit_sha": source.get("commit_sha"),
        "no_swap": watchdog.get("no_swap") is True,
        "execution": {
            "source_commit_sha": source.get("commit_sha"),
            "container_image": source.get("container_image"),
            "container_digest": source.get("container_digest"),
            "mpi_size": int(source.get("mpi_size")),
            "solver_path": source.get("primary_solver_path"),
            "no_swap": watchdog.get("no_swap") is True,
            "memory_authority_semantics": watchdog.get("semantics"),
        },
        "costs": {
            **dimensions,
            "factor_inventory_nnz": factor_inventory_nnz,
            "memory_authority_gib": _finite(
                memory.get("max_simultaneous_worker_rss_gib"),
                label="Task032 Hybrid memory",
                positive=True,
            ),
            "wall_time_seconds": _finite(
                timing.get("total"), label="Task032 Hybrid time", positive=True
            ),
        },
    }


def _resource_reduction(
    baseline: Mapping[str, float | int], candidate: Mapping[str, float | int]
) -> dict[str, Any]:
    rows = {}
    for key in (
        "local_fe_dofs",
        "local_system_rows",
        "total_rows",
        "factor_inventory_nnz",
        "memory_authority_gib",
        "wall_time_seconds",
    ):
        ratio = float(baseline[key]) / float(candidate[key])
        rows[key] = {
            "baseline": baseline[key],
            "candidate": candidate[key],
            "baseline_over_candidate": ratio,
            "classification": classify_resource_reduction(ratio),
            "reduced": ratio > 1.0,
        }
    return {
        "at_least_one_major_metric_reduced": any(row["reduced"] for row in rows.values()),
        "all_major_metrics_reduced": all(row["reduced"] for row in rows.values()),
        "rows": rows,
    }


def _input_descriptor(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: record[key]
        for key in (
            "descriptor_path",
            "descriptor_sha256",
            "run_root",
            "run_summary_path",
            "run_summary_sha256",
            "orders_sha256",
        )
    }


def _execution_contract(
    *,
    full3d: Mapping[str, Mapping[str, Any]],
    hybrid: Mapping[str, Mapping[str, Any]],
    p2_hybrid: Mapping[str, Any],
) -> dict[str, Any]:
    direct_rows = {
        key: full3d[key]["execution"]
        for key in ("candidate_p3_h10", "candidate_p3_h7p5")
    }
    hybrid_rows = {
        "baseline_p2_h3_m160": p2_hybrid["execution"],
        "candidate_p3_h10_m120": hybrid["p3_h10_m120"]["execution"],
        "candidate_p3_h10_m160": hybrid["p3_h10_m160"]["execution"],
        "candidate_p3_h7p5_m120": hybrid["p3_h7p5_m120"]["execution"],
        "candidate_p3_h7p5_m160": hybrid["p3_h7p5_m160"]["execution"],
    }
    all_rows = [*direct_rows.values(), *hybrid_rows.values()]
    image_values = {row["container_image"] for row in all_rows}
    digest_values = {row["container_digest"] for row in all_rows}
    hybrid_solver_values = {
        row["solver_path"] for row in hybrid_rows.values()
    }
    checks = {
        "single_frozen_container_image": len(image_values) == 1,
        "single_frozen_container_digest": len(digest_values) == 1,
        "all_records_mpi4": all(row["mpi_size"] == 4 for row in all_rows),
        "all_records_zero_swap": all(row["no_swap"] for row in all_rows),
        "single_hybrid_solver_path": len(hybrid_solver_values) == 1,
        "p2_h3_and_p3_h7p5_clean_sources_differ": (
            p2_hybrid["source_commit_sha"]
            != hybrid["p3_h7p5_m160"]["source_commit_sha"]
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ReducedEqualAccuracyError(
            "cross-record execution contract failed: " + ", ".join(failures)
        )
    return {
        "container_image": next(iter(image_values)),
        "container_digest": next(iter(digest_values)),
        "mpi_size": 4,
        "direct_solver_path": "direct_lu_mumps",
        "hybrid_solver_path": next(iter(hybrid_solver_values)),
        "zero_swap_required_and_observed": True,
        "one_heavy_case_at_a_time": True,
        "memory_authority_definition": (
            "max(simultaneous live MPI worker RSS sum, "
            "container cgroup current)"
        ),
        "wall_time_semantics": (
            "indicative measured comparison only; source SHA and run "
            "placement differ, so wall time is not a controlled speedup claim"
        ),
        "clean_source_identity": {
            "baseline_p2_h3": p2_hybrid["source_commit_sha"],
            "candidate_p3_h7p5": hybrid["p3_h7p5_m160"][
                "source_commit_sha"
            ],
            "sources_intentionally_different": True,
        },
        "direct_records": direct_rows,
        "hybrid_records": hybrid_rows,
        "checks": checks,
        "failures": failures,
    }


def build_reduced_equal_accuracy(
    *,
    provisional_reference: Path | str,
    p2_h3_reference: Path | str,
    p3_h10_reference: Path | str,
    p3_h7p5_reference: Path | str,
    p2_h3_hybrid_watchdog: Path | str,
    p3_h10_m120: Path | str,
    p3_h10_m160: Path | str,
    p3_h7p5_m120: Path | str,
    p3_h7p5_m160: Path | str,
    source_compatibility_audit: Path | str,
    d1_source_compatibility_audit: Path | str,
    repo_root: Path | str = ROOT,
) -> dict[str, Any]:
    """Build the complete Review-V6 fixed-p equal-accuracy record."""

    root = Path(repo_root).resolve()
    full3d = {
        "provisional_p3_h5": _load_full3d(provisional_reference, root=root),
        "baseline_p2_h3": _load_full3d(p2_h3_reference, root=root),
        "candidate_p3_h10": _load_full3d(p3_h10_reference, root=root),
        "candidate_p3_h7p5": _load_full3d(p3_h7p5_reference, root=root),
    }
    direct_comparison = {
        key: compare_full3d_to_reference(full3d["provisional_p3_h5"], full3d[key])
        for key in ("baseline_p2_h3", "candidate_p3_h10", "candidate_p3_h7p5")
    }
    physical_decision = {
        key: _physical_no_worse(direct_comparison["baseline_p2_h3"], direct_comparison[key])
        for key in ("candidate_p3_h10", "candidate_p3_h7p5")
    }
    hybrid = {
        "p3_h10_m120": _hybrid_metrics(p3_h10_m120, root=root),
        "p3_h10_m160": _hybrid_metrics(p3_h10_m160, root=root),
        "p3_h7p5_m120": _hybrid_metrics(p3_h7p5_m120, root=root),
        "p3_h7p5_m160": _hybrid_metrics(p3_h7p5_m160, root=root),
    }
    funnels = {
        "p3_h10": _hybrid_funnel(hybrid["p3_h10_m120"], hybrid["p3_h10_m160"]),
        "p3_h7p5": _hybrid_funnel(hybrid["p3_h7p5_m120"], hybrid["p3_h7p5_m160"]),
    }
    p2_hybrid = _load_task032_hybrid_baseline(p2_h3_hybrid_watchdog, root=root)
    resource = _resource_reduction(
        p2_hybrid["costs"], hybrid["p3_h7p5_m160"]["costs"]
    )
    compatibility_path, compatibility_repo_path = _repo_path(
        source_compatibility_audit, root=root
    )
    compatibility = _read_json(compatibility_path)
    if (
        compatibility.get("status") != "full3d_hybrid_numerical_source_compatible"
        or compatibility.get("compatible") is not True
    ):
        raise ReducedEqualAccuracyError("source compatibility audit did not pass")
    d1_compatibility_path, d1_compatibility_repo_path = _repo_path(
        d1_source_compatibility_audit, root=root
    )
    d1_compatibility = _read_json(d1_compatibility_path)
    if (
        d1_compatibility.get("status")
        != "d1_source_splits_numerically_compatible"
        or d1_compatibility.get("compatible") is not True
    ):
        raise ReducedEqualAccuracyError(
            "D1 source compatibility audit did not pass"
        )
    h10_positive = bool(physical_decision["candidate_p3_h10"]["pass"])
    h7p5_positive = bool(
        physical_decision["candidate_p3_h7p5"]["pass"]
        and funnels["p3_h7p5"]["pass"]
        and hybrid["p3_h7p5_m120"]["formal_pass"]
        and hybrid["p3_h7p5_m160"]["formal_pass"]
        and resource["at_least_one_major_metric_reduced"]
    )
    hybrid_output = {
        key: {field: value for field, value in record.items() if field != "orders"}
        for key, record in hybrid.items()
    }
    execution_contract = _execution_contract(
        full3d=full3d,
        hybrid=hybrid,
        p2_hybrid=p2_hybrid,
    )
    record: dict[str, Any] = {
        "schema_version": "task033.case091.reduced-equal-accuracy.v2",
        "record_type": "task033_review_v6_fixed_p_equal_accuracy",
        "case_id": "091_hybrid_hp_adaptivity_feasibility",
        "status": "fixed_p_equal_accuracy_clear_success_with_qualifications"
        if h7p5_positive
        else "not_qualified",
        "identity": {
            "is_pde_run": False,
            "consumes_measured_pde_records": True,
            "ordinary_default_changed": False,
            "proves_continuum_accuracy": False,
            "proves_grid_convergence": False,
            "proves_0p7nm_feasible": False,
        },
        "reference_boundary": {
            "identity": "provisional_best_available_discrete_reference",
            "level": "p3_h5",
            "not_continuum_reference": True,
            "not_grid_converged": True,
        },
        "execution_ladder": {
            "p3_h10_required_first": True,
            "p3_h10_equal_accuracy_pass": h10_positive,
            "p3_h7p5_condition_triggered": not h10_positive,
            "p3_h7p5_executed": True,
            "forbidden_m240_not_run": True,
            "forbidden_p3_h3_not_run": True,
            "forbidden_p4_target_not_run": True,
        },
        "inputs": {
            "full3d": {key: _input_descriptor(value) for key, value in full3d.items()},
            "hybrid": {
                key: {
                    "path": value["path"],
                    "sha256": value["sha256"],
                    "source_commit_sha": value["source_commit_sha"],
                }
                for key, value in hybrid.items()
            },
            "p2_h3_hybrid_baseline": {
                key: p2_hybrid[key]
                for key in (
                    "path",
                    "sha256",
                    "solver_path",
                    "solver_sha256",
                    "source_commit_sha",
                )
            },
            "source_compatibility_audit": {
                "path": compatibility_repo_path,
                "sha256": _sha256(compatibility_path),
                "pass": True,
            },
            "d1_source_compatibility_audit": {
                "path": d1_compatibility_repo_path,
                "sha256": _sha256(d1_compatibility_path),
                "pass": True,
            },
        },
        "cross_record_execution_contract": execution_contract,
        "high_order_memory_prediction_calibration": {
            "p3_h10": {
                "predicted_upper_gib": 1.9472054689389793,
                "full_solve_actual_gib": full3d["candidate_p3_h10"][
                    "execution"
                ]["memory_authority_gib"],
                "actual_over_predicted_upper": (
                    full3d["candidate_p3_h10"]["execution"][
                        "memory_authority_gib"
                    ]
                    / 1.9472054689389793
                ),
            },
            "p3_h7p5": {
                "predicted_upper_gib": 2.4630956334897443,
                "full_solve_actual_gib": full3d["candidate_p3_h7p5"][
                    "execution"
                ]["memory_authority_gib"],
                "actual_over_predicted_upper": (
                    full3d["candidate_p3_h7p5"]["execution"][
                        "memory_authority_gib"
                    ]
                    / 2.4630956334897443
                ),
            },
            "prediction_is_launch_guard_not_measurement": True,
            "old_high_order_model_for_1tib_projection": (
                "not_allowed_without_recalibration"
            ),
        },
        "direct_full3d_comparison_to_p3_h5": direct_comparison,
        "physical_error_no_worse_than_p2_h3": physical_decision,
        "hybrid_records": hybrid_output,
        "m120_to_m160": funnels,
        "resource_comparison_p2_h3_vs_p3_h7p5_m160": {
            "baseline": p2_hybrid,
            "candidate": hybrid["p3_h7p5_m160"]["costs"],
            **resource,
        },
        "decision": {
            "p3_h10": "negative_not_equal_accuracy",
            "p3_h7p5": (
                "fixed_p_equal_accuracy_clear_success"
                if h7p5_positive
                else "not_qualified"
            ),
            "selected_candidate": "p3_h7p5" if h7p5_positive else None,
            "scope": (
                "fixed-p reduced campaign only; provisional discrete-reference "
                "comparison, not continuum or grid-converged accuracy"
            ),
        },
        "limitations": [
            "p3/h5 is the best available discrete reference, not a continuum solution.",
            "The p3/h5 reference is not grid converged.",
            "The reused Task032 p2/h3 Hybrid baseline and new p3 runs have different clean source SHAs; Review V6 accepts the hash-bound compatibility audit and keeps wall time indicative only.",
            "M120-to-M160 selected-plane comparison uses changes in reference-error metrics; raw Hybrid plane arrays are not exported as a separate cross-M NPZ.",
            "No M240, p3/h3, p4 target, adaptivity, or 0.7 nm PDE was run.",
        ],
    }
    canonical = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    record["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return record


__all__ = [
    "ReducedEqualAccuracyError",
    "build_reduced_equal_accuracy",
    "classify_resource_reduction",
    "compare_full3d_to_reference",
]
