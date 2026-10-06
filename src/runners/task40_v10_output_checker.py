"""Independent integrity and full-residual recheck for Task40 V10 packets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

_TASK40_V10_INTERNAL_RECOVERY_LIMIT = 1.0e-11


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_array_ref(record: Mapping[str, Any], key: str, arrays: Any) -> np.ndarray:
    reference = record.get(key)
    if not isinstance(reference, Mapping) or not isinstance(reference.get("array_key"), str):
        raise ValueError(f"saved residual packet is missing array reference {key!r}")
    value = np.asarray(arrays[reference["array_key"]])
    if list(value.shape) != reference.get("shape"):
        raise ValueError(f"saved residual array {key!r} changed shape")
    return value


def _array_ref(record: Mapping[str, Any], key: str, arrays: Any) -> np.ndarray:
    return np.asarray(_raw_array_ref(record, key, arrays), dtype=np.complex128)


def verify_v10_dtn_port_mode_table(
    csv_path: str | Path, *, expected_channel_count: int = 532
) -> dict[str, Any]:
    """Verify complete top and bottom modal rows in the emitted DtN port table.

    ``diffraction_channel_count`` from field postprocessing counts the 266
    spatial/polarization orders once.  The official port table carries one row
    for each of those orders on each side, so its complete channel count is
    532 and both sides must contain the same 266 mode identities.
    """

    path = Path(csv_path).resolve()
    expected = int(expected_channel_count)
    expected_per_side = expected // 2
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"side", "m", "n", "polarization"}
        columns = set(reader.fieldnames or ())
        missing_columns = sorted(required - columns)
        rows = list(reader)

    side_counts = {"top": 0, "bottom": 0}
    mode_sets: dict[str, set[tuple[int, int, str]]] = {"top": set(), "bottom": set()}
    duplicate_modes = {"top": 0, "bottom": 0}
    malformed_rows = 0
    for row in rows:
        side = str(row.get("side", "")).strip().lower()
        if side not in mode_sets:
            malformed_rows += 1
            continue
        side_counts[side] += 1
        try:
            key = (
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]).strip().lower(),
            )
            if not key[2]:
                raise ValueError("empty polarization")
        except (KeyError, TypeError, ValueError):
            malformed_rows += 1
            continue
        if key in mode_sets[side]:
            duplicate_modes[side] += 1
        mode_sets[side].add(key)

    paired_modes = len(mode_sets["top"] & mode_sets["bottom"])
    table_passed = bool(
        expected > 0
        and expected % 2 == 0
        and not missing_columns
        and malformed_rows == 0
        and len(rows) == expected
        and side_counts == {"top": expected_per_side, "bottom": expected_per_side}
        and duplicate_modes == {"top": 0, "bottom": 0}
        and len(mode_sets["top"]) == expected_per_side
        and len(mode_sets["bottom"]) == expected_per_side
        and mode_sets["top"] == mode_sets["bottom"]
    )
    npz_path = path.parent / "dtn_port_modal_amplitudes_3d.npz"
    npz_report = None
    if npz_path.is_file():
        try:
            npz_report = _verify_dtn_port_modal_amplitudes_npz(npz_path, rows)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            npz_report = {"npz_path": str(npz_path), "passed": False, "error": str(exc)}
    elif "dtn_phase_gauge" in columns:
        npz_report = {
            "npz_path": str(npz_path),
            "passed": False,
            "error": "new gauge-aware modal CSV requires its NPZ payload",
        }
    passed = bool(table_passed and (npz_report is None or npz_report.get("passed") is True))
    return {
        "schema": "task40extra.review_v10_dtn_port_mode_table_check.v1",
        "csv_path": str(path),
        "expected_channel_count": expected,
        "actual_channel_count": len(rows),
        "expected_modes_per_side": expected_per_side,
        "channel_count_by_side": side_counts,
        "unique_mode_count_by_side": {
            side: len(mode_sets[side]) for side in ("top", "bottom")
        },
        "paired_top_bottom_mode_count": paired_modes,
        "duplicate_mode_count_by_side": duplicate_modes,
        "malformed_row_count": malformed_rows,
        "missing_columns": missing_columns,
        "modal_amplitudes_npz": npz_report,
        "passed": passed,
    }


def _verify_dtn_port_modal_amplitudes_npz(
    npz_path: Path, csv_rows: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Check required solver/plane arrays and explicitly masked optional conversions."""
    required_arrays = {
        "dtn_phase_gauge",
        "solver_amplitude_coordinate",
        "physical_boundary_amplitude_coordinate",
        "legacy_amplitude_field_coordinate",
        "auxiliary_index",
        "side",
        "m",
        "n",
        "polarization",
        "solver_auxiliary_amplitude_total_projection",
        "solver_incident_projection",
        "solver_outgoing_amplitude",
        "physical_boundary_total_amplitude",
        "physical_boundary_incident_amplitude",
        "physical_boundary_outgoing_amplitude",
        "physical_boundary_total_representable",
        "physical_boundary_incident_representable",
        "physical_boundary_outgoing_representable",
        "boundary_phase",
        "boundary_phase_representable",
        "legacy_global_total_projection",
        "legacy_global_incident_projection",
        "legacy_global_outgoing_amplitude",
        "legacy_global_total_representable",
        "legacy_global_incident_representable",
        "legacy_global_outgoing_representable",
        "global_output_representable",
        "global_output_failure_reason",
    }
    with np.load(npz_path, allow_pickle=False) as arrays:
        missing = sorted(required_arrays - set(arrays.files))
        if missing:
            raise ValueError(f"modal amplitude NPZ is missing fields: {missing}")
        count = len(csv_rows)
        vector_names = required_arrays - {
            "dtn_phase_gauge",
            "solver_amplitude_coordinate",
            "physical_boundary_amplitude_coordinate",
            "legacy_amplitude_field_coordinate",
        }
        wrong_shapes = {
            name: list(np.asarray(arrays[name]).shape)
            for name in vector_names
            if np.asarray(arrays[name]).shape != (count,)
        }
        if wrong_shapes:
            raise ValueError(f"modal amplitude NPZ arrays have wrong shapes: {wrong_shapes}")
        gauge = str(np.asarray(arrays["dtn_phase_gauge"]).item())
        if gauge not in {"global_z", "boundary_plane"}:
            raise ValueError("modal amplitude NPZ has an unknown solver gauge")
        if str(np.asarray(arrays["solver_amplitude_coordinate"]).item()) != gauge:
            raise ValueError("modal amplitude NPZ solver coordinate does not match its gauge")
        if str(np.asarray(arrays["physical_boundary_amplitude_coordinate"]).item()) != "boundary_plane":
            raise ValueError("modal amplitude NPZ physical boundary coordinate is not boundary_plane")
        if str(np.asarray(arrays["legacy_amplitude_field_coordinate"]).item()) != "global_z":
            raise ValueError("modal amplitude NPZ legacy coordinate is not global_z")

        for index, row in enumerate(csv_rows):
            if (
                int(arrays["auxiliary_index"][index]) != index
                or str(arrays["side"][index]) != str(row["side"])
                or int(arrays["m"][index]) != int(row["m"])
                or int(arrays["n"][index]) != int(row["n"])
                or str(arrays["polarization"][index]) != str(row["polarization"])
                or str(row.get("dtn_phase_gauge", gauge)) != gauge
            ):
                raise ValueError(f"modal amplitude NPZ identity differs from CSV row {index}")

        csv_value_map = (
            ("solver_auxiliary_amplitude_total_projection", "solver_auxiliary_amplitude_total_projection", None),
            ("solver_incident_projection", "solver_incident_projection", None),
            ("solver_outgoing_amplitude", "solver_outgoing_amplitude", None),
            ("physical_boundary_total_amplitude", "physical_boundary_total_amplitude", "physical_boundary_total_representable"),
            ("physical_boundary_incident_amplitude", "physical_boundary_incident_amplitude", "physical_boundary_incident_representable"),
            ("physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
            ("outgoing_amplitude_at_boundary", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
            ("auxiliary_amplitude_total_projection", "legacy_global_total_projection", "legacy_global_total_representable"),
            ("incident_projection", "legacy_global_incident_projection", "legacy_global_incident_representable"),
            ("outgoing_amplitude", "legacy_global_outgoing_amplitude", "legacy_global_outgoing_representable"),
            ("boundary_phase", "boundary_phase", "boundary_phase_representable"),
        )
        for csv_name, npz_name, mask_name in csv_value_map:
            values = np.asarray(arrays[npz_name])
            mask = None if mask_name is None else np.asarray(arrays[mask_name], dtype=bool)
            for index, row in enumerate(csv_rows):
                raw = str(row.get(csv_name, "")).strip()
                if not raw:
                    if mask is None or mask[index]:
                        raise ValueError(f"CSV field {csv_name} is missing at row {index}")
                    continue
                parsed = complex(raw)
                if mask is not None and not mask[index]:
                    raise ValueError(f"CSV field {csv_name} is present despite an unrepresentable NPZ mask")
                if parsed != complex(values[index]):
                    raise ValueError(f"CSV field {csv_name} differs from NPZ at row {index}")

        solver_names = (
            "solver_auxiliary_amplitude_total_projection",
            "solver_incident_projection",
            "solver_outgoing_amplitude",
        )
        nonfinite_solver = [name for name in solver_names if not np.isfinite(arrays[name]).all()]
        if nonfinite_solver:
            raise ValueError(f"required solver-coordinate amplitudes are nonfinite: {nonfinite_solver}")
        solver_total = np.asarray(arrays["solver_auxiliary_amplitude_total_projection"])
        solver_incident = np.asarray(arrays["solver_incident_projection"])
        solver_outgoing = np.asarray(arrays["solver_outgoing_amplitude"])
        sides = np.asarray(arrays["side"]).astype(str)
        expected_outgoing = solver_total.copy()
        top_rows = sides == "top"
        bottom_rows = sides == "bottom"
        if not np.all(top_rows | bottom_rows):
            raise ValueError("solver-coordinate amplitude NPZ contains an unknown port side")
        expected_outgoing[top_rows] -= solver_incident[top_rows]
        if not np.array_equal(solver_outgoing, expected_outgoing):
            raise ValueError("top outgoing is not total-minus-incident once or bottom outgoing is not total")

        boundary_fields = (
            ("physical_boundary_total_amplitude", "physical_boundary_total_representable"),
            ("physical_boundary_incident_amplitude", "physical_boundary_incident_representable"),
            ("physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
        )
        boundary_masks = []
        for name, mask_name in boundary_fields:
            values = np.asarray(arrays[name])
            mask = np.asarray(arrays[mask_name], dtype=bool)
            boundary_masks.append(mask)
            if not np.isfinite(values[mask]).all():
                raise ValueError(f"representable physical-plane array {name} is nonfinite")
            invalid = values[~mask]
            if invalid.size and not (np.isnan(invalid.real).all() and np.isnan(invalid.imag).all()):
                raise ValueError(f"unrepresentable physical-plane array {name} lacks an explicit NaN placeholder")
        if gauge == "boundary_plane":
            if not all(mask.all() for mask in boundary_masks):
                raise ValueError("boundary-plane solver amplitudes must retain every finite physical-plane value")
            for solver_name, boundary_name in zip(solver_names, (name for name, _ in boundary_fields), strict=True):
                if not np.array_equal(arrays[solver_name], arrays[boundary_name]):
                    raise ValueError("boundary-plane physical fields differ from their solver-coordinate values")

        optional_fields = (
            ("legacy_global_total_projection", "legacy_global_total_representable"),
            ("legacy_global_incident_projection", "legacy_global_incident_representable"),
            ("legacy_global_outgoing_amplitude", "legacy_global_outgoing_representable"),
        )
        optional_masks = []
        for name, mask_name in optional_fields:
            values = np.asarray(arrays[name])
            mask = np.asarray(arrays[mask_name], dtype=bool)
            optional_masks.append(mask)
            if not np.isfinite(values[mask]).all():
                raise ValueError(f"representable optional global array {name} is nonfinite")
            invalid = values[~mask]
            if invalid.size and not (np.isnan(invalid.real).all() and np.isnan(invalid.imag).all()):
                raise ValueError(f"unrepresentable optional global array {name} lacks an explicit NaN placeholder")

        phase = np.asarray(arrays["boundary_phase"])
        phase_mask = np.asarray(arrays["boundary_phase_representable"], dtype=bool)
        if not np.isfinite(phase[phase_mask]).all():
            raise ValueError("representable boundary phases contain nonfinite values")
        invalid_phase = phase[~phase_mask]
        if invalid_phase.size and not (np.isnan(invalid_phase.real).all() and np.isnan(invalid_phase.imag).all()):
            raise ValueError("unrepresentable boundary phase lacks an explicit NaN placeholder")

        global_mask = np.asarray(arrays["global_output_representable"], dtype=bool)
        reason = np.asarray(arrays["global_output_failure_reason"]).astype(str)
        expected_global_mask = np.logical_and.reduce(optional_masks)
        if gauge == "boundary_plane":
            expected_global_mask &= phase_mask
        if not np.array_equal(global_mask, expected_global_mask):
            raise ValueError("global-output status disagrees with its per-field representability masks")
        if np.any(~global_mask & (reason == "")):
            raise ValueError("an unrepresentable optional global output has no recorded reason")

    json_path = npz_path.parent / "dtn_auxiliary_amplitudes_3d.json"
    if not json_path.is_file():
        raise ValueError("new gauge-aware modal CSV requires dtn_auxiliary_amplitudes_3d.json")
    json_rows = json.loads(json_path.read_text(encoding="utf-8"))
    if len(json_rows) != len(csv_rows):
        raise ValueError("modal JSON and CSV row counts differ")
    json_value_map = (
        ("solver_auxiliary_amplitude_total_projection", "solver_auxiliary_amplitude_total_projection", None),
        ("solver_incident_projection", "solver_incident_projection", None),
        ("solver_outgoing_amplitude", "solver_outgoing_amplitude", None),
        ("physical_boundary_total_amplitude", "physical_boundary_total_amplitude", "physical_boundary_total_representable"),
        ("physical_boundary_incident_amplitude", "physical_boundary_incident_amplitude", "physical_boundary_incident_representable"),
        ("physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
        ("outgoing_amplitude_at_boundary", "physical_boundary_outgoing_amplitude", "physical_boundary_outgoing_representable"),
        ("auxiliary_amplitude_total_projection", "legacy_global_total_projection", "legacy_global_total_representable"),
        ("incident_projection", "legacy_global_incident_projection", "legacy_global_incident_representable"),
        ("outgoing_amplitude", "legacy_global_outgoing_amplitude", "legacy_global_outgoing_representable"),
        ("boundary_phase", "boundary_phase", "boundary_phase_representable"),
    )
    with np.load(npz_path, allow_pickle=False) as arrays:
        for index, (json_row, csv_row) in enumerate(zip(json_rows, csv_rows, strict=True)):
            if (
                int(json_row["auxiliary_index"]) != int(csv_row["auxiliary_index"])
                or str(json_row["dtn_phase_gauge"]) != str(csv_row["dtn_phase_gauge"])
                or str(json_row["side"]) != str(csv_row["side"])
                or int(json_row["m"]) != int(csv_row["m"])
                or int(json_row["n"]) != int(csv_row["n"])
                or str(json_row["polarization"]) != str(csv_row["polarization"])
            ):
                raise ValueError(f"modal JSON identity differs from CSV row {index}")
            for json_name, npz_name, mask_name in json_value_map:
                value = json_row.get(json_name)
                mask = True if mask_name is None else bool(arrays[mask_name][index])
                if value is None:
                    if mask:
                        raise ValueError(f"modal JSON field {json_name} is null despite a true NPZ mask")
                    continue
                if not mask or len(value) != 2:
                    raise ValueError(f"modal JSON field {json_name} conflicts with its NPZ mask")
                parsed = complex(float(value[0]), float(value[1]))
                if parsed != complex(arrays[npz_name][index]):
                    raise ValueError(f"modal JSON field {json_name} differs from NPZ at row {index}")

    return {
        "npz_path": str(npz_path.resolve()),
        "json_path": str(json_path.resolve()),
        "mode_count": count,
        "dtn_phase_gauge": gauge,
        "required_solver_and_plane_fields_finite": True,
        "optional_global_values_masked": True,
        "json_csv_npz_values_agree": True,
        "passed": True,
    }


def verify_v10_regular_internal_witness(packet_json: str | Path) -> dict[str, Any]:
    """Recompute Task40's 36,000-row internal recovery from saved raw arrays."""

    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    array_manifest = record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V10 regular witness packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V10 regular witness NPZ identity check failed")

    with np.load(npz_path, allow_pickle=False) as arrays:
        effective_rhs = _array_ref(record, "full_internal_effective_rhs", arrays)
        saved_action = _array_ref(record, "full_internal_saved_field_action", arrays)
        saved_residual = _array_ref(record, "full_internal_recovery_residuals", arrays)
        original_rows = _raw_array_ref(record, "full_internal_original_rows", arrays)
        twists = _raw_array_ref(record, "full_internal_twist_indices", arrays)

    expected_rows = int(record.get("full_internal_recovery_rows", 0))
    if expected_rows != 36_000:
        raise ValueError("V10 regular witness must cover exactly 36,000 internal rows")
    row_shape = (expected_rows,)
    if any(
        vector.shape != row_shape
        for vector in (effective_rhs, saved_action, saved_residual, original_rows, twists)
    ):
        raise ValueError("V10 regular internal raw arrays do not share the 36,000-row layout")
    if not np.issubdtype(original_rows.dtype, np.integer) or not np.issubdtype(
        twists.dtype, np.integer
    ):
        raise ValueError("V10 regular internal row identity arrays must be integers")
    if not np.isfinite(effective_rhs).all() or not np.isfinite(saved_action).all():
        raise ValueError("V10 regular internal raw action arrays contain non-finite values")
    if not np.array_equal(np.unique(twists), np.array([0, 1], dtype=twists.dtype)):
        raise ValueError("V10 regular internal raw arrays do not identify both twists")
    ordered = np.lexsort((original_rows, twists))
    row_pairs = np.rec.fromarrays((twists, original_rows))
    if not np.array_equal(ordered, np.arange(expected_rows)) or np.unique(row_pairs).size != expected_rows:
        raise ValueError("V10 regular internal twist/row order is not unique and canonical")

    recomputed = effective_rhs - saved_action
    scale = float(record["full_internal_recovery_operation_scale"])
    limits = record.get("limits")
    if not isinstance(limits, Mapping) or "full_internal_recovery" not in limits:
        raise ValueError("V10 regular witness is missing limits.full_internal_recovery")
    recorded_limit = float(limits["full_internal_recovery"])
    if "full_internal_recovery_limit" in record:
        duplicate_limit = float(record["full_internal_recovery_limit"])
        if not np.isfinite(duplicate_limit) or duplicate_limit != recorded_limit:
            raise ValueError("V10 regular internal recovery limit fields conflict")
    stored_relative = float(record["full_internal_recovery_relative"])
    if not np.isfinite(scale) or scale < 0.0:
        raise ValueError("V10 regular internal operation scale is invalid")
    if (
        not np.isfinite(recorded_limit)
        or recorded_limit != _TASK40_V10_INTERNAL_RECOVERY_LIMIT
    ):
        raise ValueError("V10 regular internal witness limit differs from fixed 1e-11 contract")
    limit = _TASK40_V10_INTERNAL_RECOVERY_LIMIT
    denominator = max(scale, np.finfo(float).tiny)
    relative = float(np.linalg.norm(recomputed) / denominator)
    algebra_defect = float(
        np.linalg.norm(recomputed - saved_residual)
        / max(
            float(np.linalg.norm(effective_rhs)) + float(np.linalg.norm(saved_action)),
            np.finfo(float).tiny,
        )
    )
    passed = bool(
        np.isfinite(relative)
        and relative <= limit
        and abs(relative - stored_relative) <= 1.0e-12
        and algebra_defect <= 1.0e-12
    )
    if not passed:
        raise ValueError("V10 regular internal residual failed raw-array recomputation")
    return {
        "schema": "task40extra.review_v10_regular_internal_witness_recheck.v1",
        "packet_json": str(path),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": actual_npz_sha,
        "internal_row_count": expected_rows,
        "twist_row_order": "twist_index ascending; original storage row ascending within twist",
        "recomputed_relative_residual": relative,
        "stored_relative_residual": stored_relative,
        "residual_algebra_defect_relative": algebra_defect,
        "operation_scale": scale,
        "limit": limit,
        "passed": True,
        "operator_reapplied_by_checker": False,
    }


def verify_v10_output_bundle(packet_json: str | Path) -> dict[str, Any]:
    """Reopen output identities and independently recompute saved A6 residuals.

    The checker verifies the saved backend applications and their residual
    algebra.  It does not claim to rerun DOLFINx or independently apply A6.
    The worker's distinct sum-factorized and native applications remain the
    operator evidence.
    """
    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    identity = record.get("scientific_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("V10 output packet has no scientific identity")
    file_checks = []
    for item in identity.get("field_mode_and_diffraction_files", ()):
        file_path = Path(str(item["path"])).resolve()
        actual = _file_sha256(file_path)
        file_checks.append({
            "path": str(file_path),
            "expected_sha256": str(item["sha256"]),
            "actual_sha256": actual,
            "size_bytes": file_path.stat().st_size,
            "passed": actual == item["sha256"],
        })
    if not all(row["passed"] for row in file_checks):
        raise ValueError("V10 scientific field/mode output file identity check failed")

    port_table_paths = [
        Path(str(item["path"])).resolve()
        for item in identity.get("field_mode_and_diffraction_files", ())
        if Path(str(item.get("path", ""))).name == "dtn_port_diffraction_orders_3d.csv"
    ]
    if len(port_table_paths) != 1:
        raise ValueError("V10 output identity must contain exactly one full DtN port table")
    port_mode_table_check = verify_v10_dtn_port_mode_table(port_table_paths[0])
    if not port_mode_table_check["passed"]:
        raise ValueError("V10 full top/bottom DtN port mode table is incomplete")

    residual_path = Path(str(identity["full_solution_packet_json"])).resolve()
    residual_record = json.loads(residual_path.read_text(encoding="utf-8"))
    array_manifest = residual_record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V10 final full-state packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V10 final full-state NPZ identity check failed")

    residual_checks = []
    with np.load(npz_path, allow_pickle=False) as arrays:
        rhs = _array_ref(residual_record, "full_physical_rhs_storage", arrays)
        solution = _array_ref(residual_record, "full_solution_storage", arrays)
        if solution.shape != rhs.shape:
            raise ValueError("V10 full solution and physical RHS layouts differ")
        for label, applied_key, residual_key, stored_relative in (
            (
                "sum_factorized_target_backend",
                "target_backend_applied_storage",
                "target_backend_residual_storage",
                float(residual_record["relative_residual"]),
            ),
            (
                "native_full_A6_witness",
                "native_witness_applied_storage",
                "native_witness_residual_storage",
                float(residual_record["native_witness_relative_residual"]),
            ),
        ):
            applied = _array_ref(residual_record, applied_key, arrays)
            saved_residual = _array_ref(residual_record, residual_key, arrays)
            recomputed = rhs - applied
            scale = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
            relative = float(np.linalg.norm(recomputed) / scale)
            algebra_defect = float(
                np.linalg.norm(recomputed - saved_residual)
                / max(scale + float(np.linalg.norm(saved_residual)), np.finfo(float).tiny)
            )
            residual_checks.append({
                "backend": label,
                "recomputed_relative_residual": relative,
                "stored_relative_residual": stored_relative,
                "residual_algebra_defect_relative": algebra_defect,
                "limit": float(residual_record["limit"]),
                "passed": bool(
                    np.isfinite(relative)
                    and relative <= float(residual_record["limit"])
                    and abs(relative - stored_relative) <= 1.0e-12
                    and algebra_defect <= 1.0e-12
                ),
            })
    if not all(row["passed"] for row in residual_checks):
        raise ValueError("V10 independently recomputed saved residual did not pass")
    return {
        "schema": "task40extra.review_v10_output_packet_recheck.v1",
        "packet_json": str(path),
        "residual_packet_json": str(residual_path),
        "residual_packet_npz": str(npz_path),
        "residual_packet_npz_sha256": actual_npz_sha,
        "full_solution_storage_sha256": str(identity["full_solution_storage_sha256"]),
        "ordered_physical_mode_sha256": str(identity["ordered_physical_mode_sha256"]),
        "field_mode_and_diffraction_file_checks": file_checks,
        "full_dtn_port_mode_table_check": port_mode_table_check,
        "residual_checks": residual_checks,
        "operator_reapplied_by_checker": False,
        "status": "PASS",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_json", type=Path)
    parser.add_argument("--regular-internal-witness", action="store_true")
    args = parser.parse_args(argv)
    result = (
        verify_v10_regular_internal_witness(args.packet_json)
        if args.regular_internal_witness
        else verify_v10_output_bundle(args.packet_json)
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
