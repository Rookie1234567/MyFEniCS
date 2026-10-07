"""Independent integrity and full-residual recheck for Task40 V10 packets."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def _registered_v15_profile_inventory(identity: Any) -> dict[str, Any]:
    """Resolve only registered V15 identities; never trust packet row counts."""

    from src.io.physical_intermediate_profile import TASK40_V15_P6_PROFILES
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    if not isinstance(identity, str) or identity not in TASK40_V15_P6_PROFILES:
        raise ValueError(f"unknown registered Task40 V15 profile identity: {identity!r}")
    profile = TASK40_P6_PERIODIC_PROFILES.get(identity)
    if profile is None:
        raise ValueError(f"registered Task40 V15 profile has no periodic inventory: {identity}")
    return {
        "identity": identity,
        "global_interior_rows": int(profile.global_interior_rows),
        "global_independent_rows": int(profile.global_independent_rows),
        "global_storage_rows": int(profile.global_storage_rows),
        "mode_count": int(profile.mode_count),
        "q_count": int(profile.q_count),
        "q_port_counts": tuple(int(value) for value in profile.q_port_counts),
        "sector_port_counts": tuple(int(value) for value in profile.sector_port_counts),
        "local_interior_rows": int(profile.local_interior_rows),
    }


def _close_float(actual: float, expected: float, *, rtol: float = 2.0e-12) -> bool:
    actual = float(actual)
    expected = float(expected)
    return bool(
        np.isfinite(actual)
        and np.isfinite(expected)
        and (actual == expected or np.isclose(actual, expected, rtol=rtol, atol=0.0))
    )


def _vector_defect_relative(
    actual: np.ndarray, expected: np.ndarray, action_scale: float
) -> float:
    from src.solvers.augmented_reference_correction import stable_euclidean_norm

    left = np.asarray(actual)
    right = np.asarray(expected)
    if left.shape != right.shape or left.dtype != np.dtype(np.complex128):
        return float("inf")
    if right.dtype != np.dtype(np.complex128):
        return float("inf")
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        return float("inf")
    scale = float(action_scale)
    defect = stable_euclidean_norm(left - right)
    if not np.isfinite(scale) or scale < 0.0:
        return float("inf")
    if scale == 0.0:
        return 0.0 if defect == 0.0 else float("inf")
    return defect / scale


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
    """Recompute frozen Task40 internal recovery from saved raw arrays."""

    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    profile_identity = record.get("profile_identity")
    v15_inventory = None
    if profile_identity is None:
        # Historical V10 packets predate profile binding and remain frozen at B0.
        registered_interior_rows = 36_000
    elif profile_identity == "task40extra_v10_p6_y_orbit_reference_v1":
        registered_interior_rows = 36_000
    else:
        v15_inventory = _registered_v15_profile_inventory(profile_identity)
        registered_interior_rows = v15_inventory["global_interior_rows"]
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
    if expected_rows != registered_interior_rows:
        raise ValueError(
            "regular witness row count differs from its registered profile inventory"
        )
    row_shape = (expected_rows,)
    if any(
        vector.shape != row_shape
        for vector in (effective_rhs, saved_action, saved_residual, original_rows, twists)
    ):
        raise ValueError("regular internal raw arrays do not share their registered row layout")
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

    if v15_inventory is not None:
        expected_per_twist = v15_inventory["global_interior_rows"] // 2
        twist_counts = {
            twist: int(np.count_nonzero(twists == twist)) for twist in (0, 1)
        }
        if twist_counts != {0: expected_per_twist, 1: expected_per_twist}:
            raise ValueError("V15 regular witness does not cover both complete interior sectors")
        if int(record.get("expected_port_mode_count", -1)) != v15_inventory["mode_count"]:
            raise ValueError("V15 regular witness mode count differs from registered profile")
        sectors = record.get("local_recovery_facts")
        if not isinstance(sectors, Sequence) or isinstance(sectors, (str, bytes)) or len(sectors) != 2:
            raise ValueError("V15 regular witness is missing both sector recovery facts")
        sector_by_twist = {}
        for sector in sectors:
            if not isinstance(sector, Mapping):
                raise ValueError("V15 sector recovery facts must be mappings")
            twist = int(sector.get("twist_index", -1))
            if twist in sector_by_twist or twist not in (0, 1):
                raise ValueError("V15 regular witness sector identities are incomplete or duplicated")
            sector_by_twist[twist] = sector
        expected_q_by_twist = {0: (0, 2), 1: (1, 3)}
        for twist, q_indices in expected_q_by_twist.items():
            sector = sector_by_twist.get(twist)
            expected_sector_modes = sum(
                v15_inventory["q_port_counts"][q] for q in q_indices
            )
            if (
                sector is None
                or tuple(int(value) for value in sector.get("global_q_indices", ()))
                != q_indices
                or int(sector.get("internal_row_count", -1)) != expected_per_twist
                or int(sector.get("port_mode_count", -1)) != expected_sector_modes
            ):
                raise ValueError("V15 regular witness sector rows or modes differ from profile")
        q_rows = record.get("q_true_residuals")
        if (
            not isinstance(q_rows, Sequence)
            or isinstance(q_rows, (str, bytes))
            or len(q_rows) != v15_inventory["q_count"]
            or {int(row.get("q", -1)) for row in q_rows if isinstance(row, Mapping)}
            != set(range(v15_inventory["q_count"]))
            or any(not isinstance(row, Mapping) for row in q_rows)
        ):
            raise ValueError("V15 regular witness does not cover every registered q branch")
        for row in q_rows:
            rhs_norm = float(row.get("rhs_norm", np.nan))
            residual_norm = float(row.get("true_residual_norm", np.nan))
            relative = float(row.get("true_residual_relative", np.nan))
            recomputed_relative = (
                residual_norm / rhs_norm if rhs_norm > 0.0 else (0.0 if residual_norm == 0.0 else float("inf"))
            )
            if not _close_float(relative, recomputed_relative):
                raise ValueError("V15 regular witness q residual rows are inconsistent")

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
        "schema": (
            "task40extra.review_v15_regular_internal_witness_recheck.v1"
            if v15_inventory is not None
            else "task40extra.review_v10_regular_internal_witness_recheck.v1"
        ),
        "packet_json": str(path),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": actual_npz_sha,
        "profile_identity": profile_identity,
        "internal_row_count": expected_rows,
        "expected_port_mode_count": (
            v15_inventory["mode_count"] if v15_inventory is not None else None
        ),
        "twist_row_order": "twist_index ascending; original storage row ascending within twist",
        "recomputed_relative_residual": relative,
        "stored_relative_residual": stored_relative,
        "residual_algebra_defect_relative": algebra_defect,
        "operation_scale": scale,
        "limit": limit,
        "passed": True,
        "operator_reapplied_by_checker": False,
    }


def verify_v15_pc_state_packet(packet_json: str | Path) -> dict[str, Any]:
    """Recompute V15 state identities, native budget terms, and admission."""

    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        V15_DECOMPOSITION_CLOSURE_LIMIT,
        V15_REFERENCE_PC_REJECTED,
        augmented_state_sha256,
        recompute_v15_candidate_facts,
        select_v15_reference_pc_candidate,
        stable_euclidean_norm,
    )

    path = Path(packet_json).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("schema") != "task40extra.review_v15_p6_pc_state_evidence.v1":
        raise ValueError("not a registered V15 PC state evidence packet")
    if record.get("reference_pc_strategy") != NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15:
        raise ValueError("V15 PC packet strategy identity is invalid")
    profile_identity = record.get("profile_identity", record.get("profile"))
    inventory = _registered_v15_profile_inventory(profile_identity)
    array_manifest = record.get("arrays")
    if not isinstance(array_manifest, Mapping):
        raise ValueError("V15 PC packet has no NPZ array manifest")
    npz_path = Path(str(array_manifest["path"])).resolve()
    actual_npz_sha = _file_sha256(npz_path)
    if actual_npz_sha != array_manifest.get("sha256"):
        raise ValueError("V15 PC packet NPZ identity check failed")

    def complex_array(arrays: Any, key: str, shape: tuple[int, ...]) -> np.ndarray:
        value = _raw_array_ref(record, key, arrays)
        if value.dtype != np.dtype(np.complex128) or value.shape != shape:
            raise ValueError(f"V15 PC packet array {key!r} has an invalid dtype or profile shape")
        if not np.isfinite(value).all():
            raise ValueError(f"V15 PC packet array {key!r} contains nonfinite values")
        return value

    def norm_matches(raw_facts: Mapping[str, Any], key: str, value: np.ndarray) -> bool:
        return _close_float(
            float(raw_facts.get(key, np.nan)), stable_euclidean_norm(value)
        )

    if inventory["q_count"] != 4:
        raise ValueError("registered V15 profile does not declare the four-q contract")
    candidates_meta = record.get("candidate_facts")
    if not isinstance(candidates_meta, Sequence) or isinstance(candidates_meta, (str, bytes)):
        raise ValueError("V15 PC packet candidate_facts must be a sequence")
    candidates = []
    with np.load(npz_path, allow_pickle=False) as arrays:
        fe_rhs = complex_array(arrays, "fe_rhs", (inventory["global_independent_rows"],))
        port_rhs = complex_array(arrays, "port_rhs", (inventory["mode_count"],))
        for index, facts in enumerate(candidates_meta):
            if not isinstance(facts, Mapping):
                raise ValueError("V15 PC candidate facts must be mappings")
            fe_state = complex_array(
                arrays,
                f"candidate_{index}_finite_element_state",
                (inventory["global_independent_rows"],),
            )
            alpha = complex_array(
                arrays,
                f"candidate_{index}_port_amplitudes",
                (inventory["mode_count"],),
            )
            if facts.get("evaluation_available") is not True:
                if record.get("status") != "REJECTED":
                    raise ValueError("V15 PASS packet contains an unevaluated candidate")
                continue

            raw_facts = facts.get("raw_facts")
            if not isinstance(raw_facts, Mapping):
                raise ValueError("evaluated V15 candidate has no raw_facts mapping")
            computed_state_sha = augmented_state_sha256(fe_state, alpha)
            if (
                computed_state_sha != facts.get("state_sha256")
                or computed_state_sha != raw_facts.get("state_sha256")
            ):
                raise ValueError("V15 candidate state hash differs from its saved FE/alpha arrays")
            if int(raw_facts.get("retained_mode_count", -1)) != inventory["mode_count"]:
                raise ValueError("V15 candidate retained mode count differs from profile")

            sector_facts = raw_facts.get("native_sector_facts")
            if not isinstance(sector_facts, Sequence) or isinstance(sector_facts, (str, bytes)) or len(sector_facts) != 2:
                raise ValueError("V15 candidate does not record both native sectors")
            sector_by_twist = {}
            for sector in sector_facts:
                if not isinstance(sector, Mapping):
                    raise ValueError("V15 candidate sector identity must be a mapping")
                twist = int(sector.get("twist_index", -1))
                if twist not in (0, 1) or twist in sector_by_twist:
                    raise ValueError("V15 candidate sector identities are incomplete or duplicated")
                sector_by_twist[twist] = sector
            all_mode_ids = []
            for twist, expected_count in enumerate(inventory["sector_port_counts"]):
                ids = sector_by_twist[twist].get("mode_indices")
                if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
                    raise ValueError("V15 candidate sector mode identities are missing")
                ids = [int(value) for value in ids]
                if len(ids) != expected_count:
                    raise ValueError("V15 candidate sector mode count differs from profile")
                all_mode_ids.extend(ids)
            if sorted(all_mode_ids) != list(range(inventory["mode_count"])):
                raise ValueError("V15 candidate does not cover every registered port mode once")

            q_rows = raw_facts.get("q_true_residuals")
            if (
                not isinstance(q_rows, Sequence)
                or isinstance(q_rows, (str, bytes))
                or len(q_rows) != inventory["q_count"]
                or any(not isinstance(row, Mapping) for row in q_rows)
                or {int(row.get("q", -1)) for row in q_rows} != set(range(inventory["q_count"]))
            ):
                raise ValueError("V15 candidate does not cover every registered q phase")

            effective_rhs = complex_array(
                arrays, f"candidate_{index}_effective_rhs", (inventory["global_independent_rows"],)
            )
            port_elimination_action = complex_array(
                arrays,
                f"candidate_{index}_port_elimination_action",
                (inventory["global_independent_rows"],),
            )
            sum_lifted_rhs = complex_array(
                arrays,
                f"candidate_{index}_sum_lifted_effective_rhs",
                (inventory["global_independent_rows"],),
            )
            sum_lifted_actions = complex_array(
                arrays,
                f"candidate_{index}_sum_lifted_native_actions",
                (inventory["global_independent_rows"],),
            )
            global_action = complex_array(
                arrays,
                f"candidate_{index}_global_native_action_independent",
                (inventory["global_independent_rows"],),
            )
            d_b = complex_array(
                arrays, f"candidate_{index}_d_b", (inventory["global_independent_rows"],)
            )
            d_a = complex_array(
                arrays, f"candidate_{index}_d_A", (inventory["global_independent_rows"],)
            )
            b_delta = complex_array(
                arrays,
                f"candidate_{index}_modal_alpha_defect_action",
                (inventory["global_independent_rows"],),
            )
            eliminated_direct = complex_array(
                arrays,
                f"candidate_{index}_eliminated_fe_residual_direct",
                (inventory["global_independent_rows"],),
            )
            eliminated_decomposed = complex_array(
                arrays,
                f"candidate_{index}_eliminated_fe_residual_decomposed",
                (inventory["global_independent_rows"],),
            )
            complete_decomposed = complex_array(
                arrays,
                f"candidate_{index}_complete_fe_residual_decomposed",
                (inventory["global_independent_rows"],),
            )
            complete_fe = complex_array(
                arrays,
                f"candidate_{index}_complete_augmented_fe_residual",
                (inventory["global_independent_rows"],),
            )
            complete_port = complex_array(
                arrays,
                f"candidate_{index}_complete_augmented_port_residual",
                (inventory["mode_count"],),
            )
            alpha_closure = complex_array(
                arrays,
                f"candidate_{index}_alpha_closure_residual",
                (inventory["mode_count"],),
            )
            lifted_errors = [
                complex_array(
                    arrays,
                    f"candidate_{index}_lifted_sector_error_{twist}",
                    (inventory["global_independent_rows"],),
                )
                for twist in (0, 1)
            ]
            lifted_sector_rhs = [
                complex_array(
                    arrays,
                    f"candidate_{index}_lifted_sector_effective_rhs_{twist}",
                    (inventory["global_independent_rows"],),
                )
                for twist in (0, 1)
            ]
            lifted_sector_actions = [
                complex_array(
                    arrays,
                    f"candidate_{index}_lifted_sector_native_action_{twist}",
                    (inventory["global_independent_rows"],),
                )
                for twist in (0, 1)
            ]
            action_identity_defects = [
                (effective_rhs, fe_rhs - port_elimination_action),
                (sum_lifted_rhs, lifted_sector_rhs[0] + lifted_sector_rhs[1]),
                (sum_lifted_actions, lifted_sector_actions[0] + lifted_sector_actions[1]),
                (d_b, effective_rhs - sum_lifted_rhs),
                (d_a, sum_lifted_actions - global_action),
                (lifted_errors[0], lifted_sector_rhs[0] - lifted_sector_actions[0]),
                (lifted_errors[1], lifted_sector_rhs[1] - lifted_sector_actions[1]),
                (
                    eliminated_direct,
                    effective_rhs - global_action,
                ),
                (
                    eliminated_decomposed,
                    d_b + lifted_errors[0] + lifted_errors[1] + d_a,
                ),
                (eliminated_direct, eliminated_decomposed),
                (complete_decomposed, eliminated_decomposed - b_delta),
                (complete_fe, complete_decomposed),
            ]
            def action_norm(value: np.ndarray) -> float:
                return stable_euclidean_norm(value)

            recomputed_closure_scale = (
                action_norm(effective_rhs)
                + action_norm(global_action)
                + sum(action_norm(value) for value in lifted_sector_rhs)
                + sum(action_norm(value) for value in lifted_sector_actions)
                + action_norm(complete_fe)
                + action_norm(b_delta)
                + action_norm(fe_rhs)
                + action_norm(port_elimination_action)
            )
            producer_closure_defects = (
                (eliminated_direct, eliminated_decomposed),
                (complete_fe, complete_decomposed),
                (effective_rhs, fe_rhs - port_elimination_action),
            )
            closure_norm = max(
                (action_norm(left - right) for left, right in producer_closure_defects),
                default=0.0,
            )
            additional_identity_defect_norm = max(
                (action_norm(left - right) for left, right in action_identity_defects),
                default=0.0,
            )
            closure_relative = (
                closure_norm / recomputed_closure_scale
                if recomputed_closure_scale > 0.0
                else (0.0 if closure_norm == 0.0 else float("inf"))
            )
            recorded_closure_scale = float(
                raw_facts.get("decomposition_closure_scale", np.nan)
            )
            recorded_closure_norm = float(
                raw_facts.get("decomposition_closure_norm", np.nan)
            )
            recorded_original_scale = float(raw_facts.get("effective_rhs_scale", np.nan))
            recomputed_original_scale = action_norm(fe_rhs) + action_norm(port_elimination_action)
            if (
                not _close_float(recorded_closure_scale, recomputed_closure_scale)
                or not _close_float(recorded_closure_norm, closure_norm)
                or not _close_float(
                    recorded_original_scale, recomputed_original_scale
                )
                or not np.isfinite(closure_relative)
                or closure_relative > V15_DECOMPOSITION_CLOSURE_LIMIT
                or (
                    additional_identity_defect_norm / recomputed_closure_scale
                    if recomputed_closure_scale > 0.0
                    else (0.0 if additional_identity_defect_norm == 0.0 else float("inf"))
                ) > V15_DECOMPOSITION_CLOSURE_LIMIT
            ):
                raise ValueError("V15 native budget closure or identity fails on its registered action scale")
            budget_terms = raw_facts.get("budget_term_norms")
            if not isinstance(budget_terms, Mapping):
                raise ValueError("V15 candidate is missing native budget term norms")
            lifted_norms = [stable_euclidean_norm(value) for value in lifted_errors]
            for actual, expected in zip(
                budget_terms.get("lifted_sector_errors", ()), lifted_norms, strict=True
            ):
                if not _close_float(float(actual), expected):
                    raise ValueError("V15 lifted-sector budget norm differs from saved array")
            expected_norms = {
                "d_b": stable_euclidean_norm(d_b),
                "d_A": stable_euclidean_norm(d_a),
                "B_delta_alpha": stable_euclidean_norm(b_delta),
            }
            if any(
                not _close_float(float(budget_terms.get(key, np.nan)), value)
                for key, value in expected_norms.items()
            ):
                raise ValueError("V15 native budget term norm differs from saved array")
            if not (
                norm_matches(raw_facts, "eliminated_fe_residual_norm", eliminated_direct)
                and norm_matches(raw_facts, "complete_augmented_fe_residual_norm", complete_fe)
                and norm_matches(raw_facts, "alpha_closure_residual_norm", alpha_closure)
            ):
                raise ValueError("V15 candidate residual norm differs from saved residual array")
            budget_numerator = (
                expected_norms["d_b"]
                + sum(lifted_norms)
                + expected_norms["d_A"]
                + expected_norms["B_delta_alpha"]
            )
            scale = recorded_original_scale
            budget_relative = (
                budget_numerator / scale
                if scale > 0.0
                else (0.0 if budget_numerator == 0.0 else float("inf"))
            )
            if not _close_float(float(facts.get("metrics", {}).get("noncancelling_budget", np.nan)), budget_relative):
                raise ValueError("V15 candidate non-cancelling budget differs from saved arrays")

            candidate = {
                "state_label": facts.get("state_label", f"candidate_{index}"),
                "metrics": facts.get("metrics"),
                "frozen_scale_metrics": facts.get("frozen_scale_metrics"),
                "structural_gates": facts.get("structural_gates"),
                "state_sha256": computed_state_sha,
                "raw_facts": raw_facts,
            }
            rebuilt = recompute_v15_candidate_facts(candidate)
            if not rebuilt["raw_facts_consistent"]:
                raise ValueError("V15 candidate raw metrics do not match independent recomputation")
            candidates.append(candidate)

    status = record.get("status")
    if status not in {"PASS", "REJECTED"}:
        raise ValueError("V15 PC packet status is not a recognized state")
    if not candidates:
        if status != "REJECTED" or not isinstance(record.get("failure"), str):
            raise ValueError("V15 packet has no evaluated candidate and no explicit failure")
        return {
            "schema": "task40extra.review_v15_p6_pc_state_packet_recheck.v1",
            "packet_json": str(path),
            "packet_npz": str(npz_path),
            "packet_npz_sha256": actual_npz_sha,
            "profile_identity": inventory["identity"],
            "candidate_count": 0,
            "admission": V15_REFERENCE_PC_REJECTED,
            "numerically_admitted": False,
            "packet_integrity_passed": True,
            "passed": True,
        }
    recomputed_selection = select_v15_reference_pc_candidate(candidates)
    recorded_selection = record.get("candidate_selection")
    if not isinstance(recorded_selection, Mapping) or (
        recorded_selection.get("admission") != recomputed_selection["admission"]
        or recorded_selection.get("selected_candidate_index")
        != recomputed_selection["selected_candidate_index"]
    ):
        raise ValueError("V15 candidate selector result differs from independently recomputed facts")
    if status == "PASS" and not recomputed_selection["admitted"]:
        raise ValueError("V15 packet claims PASS while its saved candidates are rejected")
    if status == "REJECTED" and recomputed_selection["admitted"]:
        raise ValueError("V15 failure packet contains a candidate that independently passes")
    return {
        "schema": "task40extra.review_v15_p6_pc_state_packet_recheck.v1",
        "packet_json": str(path),
        "packet_npz": str(npz_path),
        "packet_npz_sha256": actual_npz_sha,
        "profile_identity": inventory["identity"],
        "candidate_count": len(candidates),
        "candidate_selection": recomputed_selection,
        "admission": recomputed_selection["admission"],
        "numerically_admitted": recomputed_selection["admitted"],
        "packet_integrity_passed": True,
        "passed": True,
        "operator_reapplied_by_checker": False,
    }


def verify_v10_output_bundle(
    packet_json: str | Path, *, expected_channel_count: int = 532
) -> dict[str, Any]:
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
    port_mode_table_check = verify_v10_dtn_port_mode_table(
        port_table_paths[0], expected_channel_count=expected_channel_count
    )
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
    parser.add_argument("--v15-pc-state-packet", action="store_true")
    parser.add_argument(
        "--receipt-output",
        type=Path,
        help="V15 PC checker receipt path (defaults beside the packet)",
    )
    parser.add_argument(
        "--expected-channel-count",
        type=int,
        choices=(340, 532, 588),
        default=532,
        help="explicit case contract: 532 for B0, 340 for Gx560, 588 for E1",
    )
    args = parser.parse_args(argv)
    selected_checks = sum(
        (bool(args.regular_internal_witness), bool(args.v15_pc_state_packet))
    )
    if selected_checks > 1:
        parser.error("select at most one packet-specific checker mode")
    if args.v15_pc_state_packet:
        packet_path = args.packet_json.resolve()
        receipt_path = args.receipt_output or packet_path.with_name(
            f"{packet_path.stem}.v15_checker_receipt.json"
        )
        receipt_path = receipt_path.resolve()
        try:
            result = verify_v15_pc_state_packet(packet_path)
        except Exception as exc:
            receipt = {
                "schema": "task40extra.review_v15_pc_state_checker_receipt.v1",
                "checker": "verify_v15_pc_state_packet",
                "status": "REJECTED",
                "packet_json": str(packet_path),
                "packet_json_sha256": (
                    _file_sha256(packet_path) if packet_path.is_file() else None
                ),
                "passed": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with receipt_path.open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            print(json.dumps({"receipt_path": str(receipt_path), **receipt}, sort_keys=True, indent=2))
            return 2
        receipt = {
            "schema": "task40extra.review_v15_pc_state_checker_receipt.v1",
            "checker": "verify_v15_pc_state_packet",
            "status": "PASS",
            "packet_json": str(packet_path),
            "packet_json_sha256": _file_sha256(packet_path),
            "packet_npz": result["packet_npz"],
            "packet_npz_sha256": result["packet_npz_sha256"],
            "passed": True,
            "result": result,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({"receipt_path": str(receipt_path), **receipt}, sort_keys=True, indent=2))
        return 0
    elif args.regular_internal_witness:
        result = verify_v10_regular_internal_witness(args.packet_json)
    else:
        if args.receipt_output is not None:
            parser.error("--receipt-output is supported with --v15-pc-state-packet only")
        result = verify_v10_output_bundle(
            args.packet_json, expected_channel_count=args.expected_channel_count
        )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
