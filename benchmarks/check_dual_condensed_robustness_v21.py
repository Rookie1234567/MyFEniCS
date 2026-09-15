"""Independent read-only checker for the Review V21 A/B/C worker evidence.

The worker writes raw residual packets and the two complete 80-channel port
files.  This checker recomputes the residual norm, modal sums, passivity and
the stage/reference classification from those files; it never trusts the
worker's final boolean as the decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.check_dual_cell_condensed_v19 import (
    load_arrays as _load_v19_arrays,
    residual_facts as _residual_facts,
)
from benchmarks.check_dual_condensed_memory_v20 import (
    exact_p4_call_facts,
    jit_preparation_facts,
    phase_resource_facts,
    release_timeline_facts,
)
from benchmarks.check_p4_blr_v16 import _hash, _json, _jsonl
from benchmarks.check_p4_blr_tradeoff_v17 import _control_value
from benchmarks.check_p4_cell_condensed_v18 import (
    _array,
    fullspace_balance_facts,
    fullspace_residual_facts,
    matrix_identity_facts,
    resource_facts,
)
from src.runners.physical_macro_v12 import _compare_saved_output
from src.runners.physical_p4_schur_v14 import _v14_physical_checks


CHECKER_SCHEMA = "task039extra.v21.authority-checker.v1"
PASS_CLASSIFICATION = "DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED"
MODE_SHA = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
V20_P6_INVENTORY_LABEL = "v20_p6_local_caches"
V21_P6_INVENTORY_LABEL = "v21_p6_local_caches"
HISTORICAL_V21_Z2_SOURCE_SHA = "863ec3bcd7eead867795284db11fc39e758a6f08"
HISTORICAL_V21_Z2_SUMMARY_SCHEMA = "task039extra.v14.z2_notch_h10.v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _complex(value: Any) -> complex:
    if isinstance(value, Mapping):
        return complex(float(value["real"]), float(value["imag"]))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return complex(float(value[0]), float(value[1]))
    return complex(value)


def _keys(rows: list[Mapping[str, Any]]) -> list[tuple[str, int, int, str, str, int]]:
    return [
        (
            str(row["side"]),
            int(row["m"]),
            int(row["n"]),
            str(row["polarization"]),
            str(row["direction"]),
            int(row["auxiliary_index"]),
        )
        for row in rows
    ]


def _check_channels(
    output_dir: Path, output_facts: Mapping[str, Any]
) -> tuple[dict[str, bool], dict[str, Any]]:
    del output_facts
    checks = {
        "files": False,
        "count": False,
        "unique_order": False,
        "channel_identity": False,
        "finite_amplitudes": False,
        "finite_powers": False,
        "modal_sums": False,
        "normalization": False,
        "passivity": False,
        "energy_closure": False,
        "absorption_consistency": False,
    }
    facts: dict[str, Any] = {"status": "NOT_CHECKED", "failure_keys": []}
    try:
        orders_path = output_dir / "dtn_port_diffraction_orders_3d.json"
        amplitudes_path = output_dir / "dtn_auxiliary_amplitudes_3d.json"
        orders_payload = _read(orders_path)
        orders = list(orders_payload["orders"])
        amplitudes = list(_read(amplitudes_path))
        metrics = orders_payload["metrics"]
        volume_payload = _read(output_dir / "volume_absorption.json")
        checks["files"] = True
        checks["count"] = len(orders) == len(amplitudes) == 80
        order_keys = _keys(orders)
        amplitude_keys = _keys(amplitudes)
        checks["unique_order"] = (
            len(order_keys) == len(set(order_keys))
            and len(amplitude_keys) == len(set(amplitude_keys))
            and order_keys == amplitude_keys
        )
        checks["channel_identity"] = bool(
            [row["auxiliary_index"] for row in orders] == list(range(80))
            and sum(str(row["side"]) == "top" for row in orders) == 40
            and sum(str(row["side"]) == "bottom" for row in orders) == 40
            and int(metrics.get("dtn_port_mode_count", -1)) == 80
        )
        order_map = dict(zip(order_keys, orders))
        amplitude_map = dict(zip(amplitude_keys, amplitudes))
        amplitude_finite = True
        power_finite = True
        passive = True
        modal_r = 0.0
        modal_t = 0.0
        failures: list[list[Any]] = []
        rows: list[dict[str, Any]] = []
        for key in order_keys:
            order = order_map[key]
            amplitude = amplitude_map[key]
            finite_amp = all(
                np.isfinite(_complex(order[field]))
                and np.isfinite(_complex(amplitude[field]))
                for field in (
                    "auxiliary_amplitude_total_projection",
                    "incident_projection",
                    "outgoing_amplitude",
                    "boundary_phase",
                    "outgoing_amplitude_at_boundary",
                )
            )
            finite_power = all(
                np.isfinite(float(order[field]))
                for field in ("modal_power_code_units", "power_ratio", "R", "T")
            )
            same_amplitude = all(
                abs(_complex(order[field]) - _complex(amplitude[field])) <= 1.0e-12
                for field in (
                    "auxiliary_amplitude_total_projection",
                    "incident_projection",
                    "outgoing_amplitude",
                    "boundary_phase",
                    "outgoing_amplitude_at_boundary",
                )
            )
            power_ratio = float(order["power_ratio"])
            r_value = float(order["R"])
            t_value = float(order["T"])
            is_passive = (
                power_ratio >= -1.0e-12
                and r_value >= -1.0e-12
                and t_value >= -1.0e-12
                and np.isclose(
                    power_ratio,
                    r_value if str(order["side"]) == "top" else t_value,
                    rtol=1.0e-10,
                    atol=1.0e-12,
                )
                and np.isclose(
                    t_value if str(order["side"]) == "top" else r_value,
                    0.0,
                    rtol=0.0,
                    atol=1.0e-12,
                )
            )
            amplitude_finite = amplitude_finite and finite_amp and same_amplitude
            power_finite = power_finite and finite_power
            passive = passive and is_passive
            modal_r += r_value
            modal_t += t_value
            if not (finite_amp and finite_power and same_amplitude and is_passive):
                failures.append(list(key))
            rows.append(
                {
                    "key": list(key),
                    "finite_amplitude": bool(finite_amp),
                    "finite_power": bool(finite_power),
                    "outgoing_fields_match": bool(same_amplitude),
                    "power_ratio": power_ratio,
                    "R": r_value,
                    "T": t_value,
                    "passive": bool(is_passive),
                }
            )
        # The normalization and modal totals are read from the raw files.  A
        # copied ``output_facts`` dictionary is not authoritative evidence.
        incident = float(metrics.get("incident_power_code_units", np.nan))
        file_incident = incident
        r_total = float(metrics.get("R_total", np.nan))
        t_total = float(metrics.get("T_total", np.nan))
        r_plus_t = float(metrics.get("R_plus_T", np.nan))
        a_balance = float(metrics.get("A_balance", np.nan))
        a_volume = float(volume_payload.get("A_volume_total", np.nan))
        volume_incident = float(volume_payload.get("incident_power_code_units", np.nan))
        checks["finite_amplitudes"] = bool(
            amplitude_finite and len(rows) == 80
        )
        checks["finite_powers"] = bool(power_finite and len(rows) == 80)
        checks["modal_sums"] = bool(
            abs(modal_r - r_total) <= 1.0e-8
            and abs(modal_t - t_total) <= 1.0e-8
            and abs(modal_r + modal_t - r_plus_t) <= 1.0e-8
        )
        checks["normalization"] = bool(
            np.isfinite(incident)
            and incident > 0.0
            and np.isfinite(file_incident)
            and abs(incident - file_incident) <= 1.0e-12 * max(abs(incident), 1.0)
            and np.isfinite(volume_incident)
            and abs(incident - volume_incident)
            <= 1.0e-12 * max(abs(incident), 1.0)
        )
        checks["passivity"] = bool(
            passive
            and r_total >= -1.0e-12
            and t_total >= -1.0e-12
            and a_volume >= -1.0e-12
            and np.isfinite(r_plus_t)
            and np.isclose(r_total + t_total, r_plus_t, rtol=1.0e-10, atol=1.0e-10)
            and r_plus_t + a_volume <= 1.0 + 1.0e-5
        )
        checks["energy_closure"] = bool(
            np.isfinite(r_total)
            and np.isfinite(t_total)
            and np.isfinite(a_volume)
            and abs(r_total + t_total + a_volume - 1.0) <= 1.0e-5
        )
        checks["absorption_consistency"] = bool(
            np.isfinite(a_balance)
            and np.isfinite(a_volume)
            and abs(a_balance - a_volume) <= 1.0e-5
        )
        facts = {
            "status": "CHECKED",
            "expected_count": 80,
            "checked_count": len(rows),
            "order_keys": [list(key) for key in order_keys],
            "failure_keys": failures,
            "modal_R": modal_r,
            "modal_T": modal_t,
            "metrics": {
                "R_total": r_total,
                "T_total": t_total,
                "R_plus_T": r_plus_t,
                "A_balance": a_balance,
                "A_volume_total": a_volume,
                "energy_closure_error": abs(r_total + t_total + a_volume - 1.0),
                "absorption_consistency_error": abs(a_balance - a_volume),
            },
            "incident_power_code_units": incident,
            "rows": rows,
            "files": {
                "orders": str(orders_path),
                "amplitudes": str(amplitudes_path),
            },
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        facts = {
            "status": "FAILED_TO_READ_OR_VALIDATE",
            "failure_keys": [],
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    return checks, facts


def _field_output_facts_v21(
    output_dir: Path, output_facts: Mapping[str, Any]
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Recheck the required saved E/H/curl outputs independently of stage_pass."""

    checks = {
        "archive_files": False,
        "electric_finite": False,
        "magnetic_finite": False,
        "curl_postprocess": False,
        "field_export_scalars": False,
    }
    facts: dict[str, Any] = {"status": "NOT_CHECKED"}
    try:
        archive_path = output_dir / "full3d_reference_samples.npz"
        metadata_path = output_dir / "full3d_reference_samples.json"
        electric_file = output_dir / "E_3d_numerical.bp"
        magnetic_file = output_dir / "H_3d_A_per_m_from_curl.bp"
        field_export = output_facts.get("field_export", {})
        with np.load(archive_path, allow_pickle=False) as archive:
            required_arrays = {
                name: np.asarray(archive[name])
                for name in (
                    "E_V_per_m",
                    "H_A_per_m",
                    "E_t_interface_V_per_m",
                    "H_t_interface_A_per_m",
                )
            }
        checks["archive_files"] = (
            archive_path.is_file()
            and metadata_path.is_file()
            and electric_file.is_dir()
            and magnetic_file.is_dir()
        )
        checks["electric_finite"] = bool(
            np.isfinite(required_arrays["E_V_per_m"]).all()
            and np.isfinite(required_arrays["E_t_interface_V_per_m"]).all()
        )
        checks["magnetic_finite"] = bool(
            np.isfinite(required_arrays["H_A_per_m"]).all()
            and np.isfinite(required_arrays["H_t_interface_A_per_m"]).all()
        )
        checks["curl_postprocess"] = field_export.get("curl_postprocess_success") is True
        checks["field_export_scalars"] = all(
            np.isfinite(float(field_export[name])) and float(field_export[name]) >= 0.0
            for name in ("max_abs_E", "max_abs_H")
        )
        facts = {
            "status": "CHECKED",
            "array_shapes": {
                name: list(array.shape) for name, array in required_arrays.items()
            },
            "files": {
                "archive": str(archive_path),
                "metadata": str(metadata_path),
                "electric": str(electric_file),
                "magnetic": str(magnetic_file),
            },
            "field_export": {
                "max_abs_E": field_export.get("max_abs_E"),
                "max_abs_H": field_export.get("max_abs_H"),
                "curl_postprocess_success": field_export.get("curl_postprocess_success"),
            },
        }
    except (OSError, KeyError, TypeError, ValueError, FloatingPointError, json.JSONDecodeError) as exc:
        facts = {
            "status": "FAILED_TO_READ_OR_VALIDATE",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    return checks, facts


def _alias_v21_events(
    events: list[Mapping[str, Any]], *, stage: str | None = None
) -> list[dict[str, Any]]:
    """Adapt stage-prefixed V21 labels for the qualified V20 pure helpers.

    The worker preserves the real ``z2``/``z3``/``z4`` event prefix.  The
    reused helpers intentionally know only the historical ``y3`` labels, so
    this adapter adds aliases while retaining every original event row.
    """

    aliases = {
        "v21_independent_final_residual_complete": "y3_independent_final_residual_complete",
        "v21_authority_limited_output_complete": "y3_physical_output_comparison_complete",
        "v21_physical_output_comparison_complete": "y3_physical_output_comparison_complete",
    }
    stage_prefix = {
        "Z2_NOTCH_H10": "z2",
        "Z3_ORIGINAL_H7P5": "z3",
        "Z4_NOTCH_H7P5": "z4",
    }.get(str(stage))
    if stage_prefix is not None:
        aliases.update(
            {
                f"{stage_prefix}_independent_final_residual_complete":
                "y3_independent_final_residual_complete",
                f"{stage_prefix}_authority_limited_output_complete":
                "y3_physical_output_comparison_complete",
                f"{stage_prefix}_physical_output_comparison_complete":
                "y3_physical_output_comparison_complete",
            }
        )
    result = []
    for event in events:
        original = dict(event)
        result.append(original)
        alias = aliases.get(str(event.get("event")))
        if alias is not None:
            copied = dict(event)
            copied["event"] = alias
            copied["aliased_from"] = event.get("event")
            result.append(copied)
        # The V20 lifecycle helper has a deliberately independent, historical
        # label.  Keep the raw V21 inventory event untouched and add only an
        # exact in-memory compatibility row for that helper.
        if (
            stage_prefix is not None
            and event.get("event") == "v14_inventory_released"
            and isinstance(event.get("facts"), Mapping)
            and event["facts"].get("label") == V21_P6_INVENTORY_LABEL
        ):
            copied = dict(event)
            copied["facts"] = dict(event["facts"])
            copied["facts"]["label"] = V20_P6_INVENTORY_LABEL
            copied["aliased_from"] = event.get("event")
            copied["label_aliased_from"] = V21_P6_INVENTORY_LABEL
            result.append(copied)
    return result


def _v21_release_timeline_facts(
    events: list[Mapping[str, Any]], *, stage: str
) -> dict[str, Any]:
    """Run the V20 chronology checks plus raw V21 label/owner/amount checks."""

    aliased_events = _alias_v21_events(events, stage=stage)
    legacy = release_timeline_facts(aliased_events)
    checks = dict(legacy.get("checks", {}))
    reserve_rows = [
        event
        for event in events
        if event.get("event") == "v14_inventory_reserved"
        and isinstance(event.get("facts"), Mapping)
        and event["facts"].get("label") == V21_P6_INVENTORY_LABEL
    ]
    release_rows = [
        event
        for event in events
        if event.get("event") == "v14_inventory_released"
        and isinstance(event.get("facts"), Mapping)
        and event["facts"].get("label") == V21_P6_INVENTORY_LABEL
    ]
    start_rows = [
        event for event in events if event.get("event") == "v20_p6_release_started"
    ]
    complete_rows = [
        event for event in events if event.get("event") == "v20_p6_release_complete"
    ]
    reserve_facts = (
        reserve_rows[0].get("facts", {})
        if len(reserve_rows) == 1
        and isinstance(reserve_rows[0].get("facts"), Mapping)
        else {}
    )
    release_facts = (
        release_rows[0].get("facts", {})
        if len(release_rows) == 1
        and isinstance(release_rows[0].get("facts"), Mapping)
        else {}
    )
    reserve_entry = reserve_facts.get("entry", {})
    reserved_bytes = (
        reserve_entry.get("bytes")
        if isinstance(reserve_entry, Mapping)
        else None
    )
    released_bytes = release_facts.get("bytes")
    complete_facts = (
        complete_rows[0].get("facts", {})
        if len(complete_rows) == 1
        and isinstance(complete_rows[0].get("facts"), Mapping)
        else {}
    )
    checks["v21_p6_raw_inventory_label"] = (
        len(reserve_rows) == 1 and len(release_rows) == 1
    )
    checks["v21_p6_release_owner_refs"] = (
        len(complete_rows) == 1
        and complete_facts.get("owner_refs_cleared") is True
    )
    checks["v21_p6_release_after_final_residual"] = (
        len(complete_rows) == 1
        and complete_facts.get("released_after_final_residual") is True
    )
    checks["v21_p6_release_timing"] = (
        len(start_rows) == 1
        and len(release_rows) == 1
        and len(complete_rows) == 1
        and int(start_rows[0].get("timestamp_ns", -1))
        < int(release_rows[0].get("timestamp_ns", -1))
        < int(complete_rows[0].get("timestamp_ns", -1))
    )
    checks["v21_p6_release_amount"] = (
        type(reserved_bytes) is int
        and reserved_bytes > 0
        and type(released_bytes) is int
        and released_bytes > 0
    )
    checks["v21_p6_release_amount_matches_reservation"] = (
        checks["v21_p6_release_amount"]
        and released_bytes == reserved_bytes
    )
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "legacy_helper": legacy,
        "inventory_amount": {
            "reserve_label": V21_P6_INVENTORY_LABEL,
            "reserved_bytes": reserved_bytes,
            "released_bytes": released_bytes,
            "reserve_count": len(reserve_rows),
            "release_count": len(release_rows),
        },
        "label_adapter": {
            "raw_label": V21_P6_INVENTORY_LABEL,
            "legacy_label": V20_P6_INVENTORY_LABEL,
            "in_memory_only": True,
        },
    }


def _summary_schema_facts(
    summary: Mapping[str, Any], *, source_sha: str, stage: str
) -> dict[str, Any]:
    """Accept only the known historical V21 overwrite, never arbitrary drift."""

    observed = summary.get("schema")
    native = observed == "task039extra.v21.worker-summary.v1"
    historical_compatibility = (
        source_sha == HISTORICAL_V21_Z2_SOURCE_SHA
        and stage == "Z2_NOTCH_H10"
        and summary.get("profile")
        == "physical_p6_trace_p4_condensed_robustness_v21"
        and observed == HISTORICAL_V21_Z2_SUMMARY_SCHEMA
    )
    return {
        "observed": observed,
        "expected": "task039extra.v21.worker-summary.v1",
        "native_pass": native,
        "compatibility_applied": historical_compatibility,
        "compatibility_scope": (
            {
                "source_sha": HISTORICAL_V21_Z2_SOURCE_SHA,
                "stage": "Z2_NOTCH_H10",
                "observed_schema": HISTORICAL_V21_Z2_SUMMARY_SCHEMA,
                "reason": "historical V14 record.update overwrote the V21 adapter schema",
            }
            if historical_compatibility
            else None
        ),
        "passed": native or historical_compatibility,
    }


def _mode_identity_facts_v21(
    summary: Mapping[str, Any], run_directory: Path, output_directory: Path
) -> dict[str, Any]:
    """Validate the fixed 80-mode identity from the saved manifest and raw output."""

    checks = {
        "operator_mode_sha": summary.get("operator_identity", {}).get(
            "ordered_mode_sha256"
        ) == MODE_SHA,
        "retained_mode_sha": summary.get("operator_identity", {})
        .get("retained_p6", {})
        .get("ordered_mode_sha256") == MODE_SHA,
        "manifest_file": False,
        "manifest_hash": False,
        "manifest_schema": False,
        "manifest_count": False,
        "manifest_indices": False,
        "manifest_key_order": False,
        "output_key_order": False,
        "output_auxiliary_order": False,
        "output_directions": False,
    }
    facts: dict[str, Any] = {"status": "NOT_CHECKED"}
    try:
        descriptor = summary["mode_manifest"]
        manifest_path = Path(str(descriptor["path"])).resolve()
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        orders_payload = _read(output_directory / "dtn_port_diffraction_orders_3d.json")
        orders = list(orders_payload["orders"])
        manifest_rows = list(manifest["modes"])
        manifest_keys = [
            (
                str(row["side"]),
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]),
            )
            for row in manifest_rows
        ]
        output_keys = [
            (
                str(row["side"]),
                int(row["m"]),
                int(row["n"]),
                str(row["polarization"]),
            )
            for row in orders
        ]
        checks.update(
            {
                "manifest_file": manifest_path.is_file(),
                "manifest_hash": descriptor.get("sha256")
                == hashlib.sha256(manifest_bytes).hexdigest()
                == descriptor.get("mode_sha256")
                == MODE_SHA,
                "manifest_schema": manifest.get("schema")
                == "fullspace-dtn.mode-manifest.v1",
                "manifest_count": manifest.get("mode_count") == 80
                and descriptor.get("mode_count") == 80
                and len(manifest_rows) == 80,
                "manifest_indices": [row.get("mode_index") for row in manifest_rows]
                == list(range(80)),
                "manifest_key_order": manifest_keys == output_keys,
                "output_key_order": [
                    int(row.get("auxiliary_index", -1)) for row in orders
                ]
                == list(range(80)),
                "output_auxiliary_order": len(output_keys) == 80
                and len(set(output_keys)) == 80,
                "output_directions": all(
                    str(row.get("direction"))
                    == ("outgoing_up" if str(row.get("side")) == "top" else "outgoing_down")
                    for row in orders
                ),
            }
        )
        facts = {
            "status": "CHECKED",
            "path": str(manifest_path),
            "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "mode_sha256": descriptor.get("mode_sha256"),
            "mode_count": len(manifest_rows),
            "manifest_key_order": [list(key) for key in manifest_keys],
            "output_key_order": [list(key) for key in output_keys],
            "checks": checks,
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        facts = {
            "status": "FAILED_TO_READ_OR_VALIDATE",
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "checks": checks,
        }
    return {"checks": checks, "passed": all(checks.values()), **facts}


def _cache_description_facts_v21(
    packet: Mapping[str, Any],
    p6_build_audit: Mapping[str, Any],
    p6_recipe: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the shared identity cache with the live oriented-class count.

    V20's checker intentionally freezes twelve oriented classes.  V21 must
    retain the same 450x450 read-only identity representation while deriving
    the class count from the actual build audit and the saved recipe because
    the h=7.5 mesh has more oriented classes.
    """

    cache = packet["cache"]
    identity = cache["identity_cache"]
    semantic = identity["semantic"]
    representation = identity["representation"]

    def digest(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    inventory = p6_recipe.get("buffer_inventory", {})
    class_counts = {
        "recipe": inventory.get("class_count"),
        "retained_local_schur_sum": p6_build_audit.get(
            "retained_local_schur_class_count_sum"
        ),
        "oriented_schur_sum": p6_build_audit.get("oriented_schur_class_count_sum"),
    }
    positive_ints = all(type(value) is int and value > 0 for value in class_counts.values())
    expected_class_count = (
        int(next(iter(class_counts.values()))) if positive_ints else None
    )
    checks = {
        "saved_descriptor_digest": digest(cache["arrays"])
        == cache["array_content_sha256"],
        "semantic_digest": digest(semantic)
        == identity["semantic_sha256"]
        == cache["identity_cache_semantic_sha256"],
        "representation_digest": digest(representation)
        == identity["representation_sha256"]
        == cache["identity_cache_representation_sha256"],
        "identity_semantics": (
            expected_class_count is not None
            and semantic["operator"] == "identity"
            and semantic["shape"] == [450, 450]
            and semantic["dtype"] == "float64"
            and semantic["logical_class_count"] == expected_class_count
            and representation["logical_class_count"] == expected_class_count
        ),
        "build_descriptor_class_count": positive_ints
        and len(set(class_counts.values())) == 1,
        "one_shared_identity": (
            representation["mode"] == "shared_read_only_per_interior_shape"
            and representation["read_only"] is True
            and representation["unique_storage_count"] == 1
            and representation["unique_storage_bytes"] == 450 * 450 * 8
        ),
        "payload_components": sum(cache["components"].values())
        == cache["unique_numpy_bytes"],
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "semantic": semantic,
        "representation": representation,
        "class_counts": class_counts,
        "expected_class_count": expected_class_count,
        "unique_numpy_bytes": cache["unique_numpy_bytes"],
        "array_content_sha256": cache["array_content_sha256"],
    }


def _jit_preparation_facts_v21(
    events: list[Mapping[str, Any]], samples: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Reuse V20 preparation checks with the V21 cache policy semantics.

    A cold compiler miss is useful observation, but it is not a V21 gate.  The
    gate is that the run-owned cache reused all qualified modules and that the
    actual compiler calls were still observed under the watchdog timeline.
    """

    facts = jit_preparation_facts(events, samples)
    checks = dict(facts.get("checks", {}))
    cache = facts.get("cache", {})
    checks["v21_reuse_all_qualified"] = (
        cache.get("cache_policy") == "v21_reuse_all_qualified"
        and cache.get("excluded_module_family") is None
        and cache.get("excluded_file_count") == 0
        and cache.get("excluded_bytes") == 0
    )
    preparation_events = [
        event
        for event in events
        if event.get("event") == "v20_form_preparation_complete"
    ]
    observed_roles: set[str] = set()
    required_roles = {"p6_condensation", "p4_condensation"}
    for event in preparation_events:
        payload = event.get("facts", {})
        observed_roles.update(
            str(row.get("role"))
            for row in payload.get("compiler_events", [])
            if isinstance(row, Mapping) and row.get("role") is not None
        )
        required_roles.update(
            str(row.get("role"))
            for row in payload.get("official_evaluation_roles", [])
            if isinstance(row, Mapping) and row.get("role") is not None
        )
    checks["actual_compiler_observations"] = bool(
        preparation_events and required_roles <= observed_roles
    )
    facts["observed_roles"] = sorted(observed_roles)
    facts["required_roles"] = sorted(required_roles)
    facts["checks"] = checks
    facts["passed"] = all(checks.values())
    facts["cold_reorder_status"] = "OBSERVATION_ONLY"
    facts["cold_reorder_gate"] = False
    return facts


def _saved_field_facts_v21(
    full: np.ndarray,
    original_rhs: np.ndarray,
    retained_y: np.ndarray,
    retained_alpha: np.ndarray,
    slave_rows: np.ndarray,
    pre_solution: np.ndarray,
    pre_rhs: np.ndarray,
    post_solution: np.ndarray,
    post_rhs: np.ndarray,
    *,
    expected_full_storage_size: int,
    expected_retained_size: int,
    expected_rhs_sha256: str,
) -> dict[str, Any]:
    """Recompute the V20 field-packet contract with live V21 sizes."""

    slaves = np.asarray(slave_rows)
    valid_slaves = bool(
        slaves.ndim == 1
        and np.issubdtype(slaves.dtype, np.integer)
        and len(slaves) > 0
        and len(np.unique(slaves)) == len(slaves)
        and np.all(slaves >= 0)
        and np.all(slaves < full.size)
    )
    checks = {
        "full_storage_size": full.shape == (int(expected_full_storage_size),),
        "retained_size": retained_y.shape == (int(expected_retained_size),)
        and retained_alpha.shape == (80,),
        "same_full_solution": np.array_equal(full, pre_solution)
        and np.array_equal(full, post_solution),
        "same_physical_rhs": np.array_equal(original_rhs, pre_rhs)
        and np.array_equal(original_rhs, post_rhs),
        "case_bound_rhs_identity": _sha256_array(original_rhs) == expected_rhs_sha256,
        "finite_full_solution": bool(np.isfinite(full).all()),
        "retained_ports_saved": np.array_equal(retained_y[-80:], retained_alpha),
        "owned_slave_rows": valid_slaves,
        "strict_slave_zero": bool(valid_slaves and np.all(full[slaves] == 0)),
    }
    return {
        "checks": checks,
        "solution_sha256": _sha256_array(full),
        "rhs_sha256": _sha256_array(original_rhs),
        "slave_count": int(len(slaves)),
        "passed": all(checks.values()),
    }


def _sha256_array(value: Any) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    return hashlib.sha256(array.tobytes()).hexdigest()


def _dimension_identity_facts(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Check that live FE/MPC dimensions close through every saved owner."""

    dimensions = summary.get("actual_dimension_identity", {})
    p6 = dimensions.get("p6", {}) if isinstance(dimensions, Mapping) else {}
    p4 = dimensions.get("p4", {}) if isinstance(dimensions, Mapping) else {}
    p6_counts = p6.get("expected_space_counts")
    p4_counts = p4.get("expected_space_counts")
    solver = summary.get("solver", {})
    retained = solver.get("retained_outer", {})
    identity = summary.get("operator_identity", {})
    p6_identity = identity.get("retained_p6", {})
    p6_audit = p6_identity.get("p6_build_audit", {})
    setup = retained.get("setup_checks", {})
    p4_condensation = (
        summary.get("interface_stack", {}).get("condensation", {})
        if isinstance(summary.get("interface_stack", {}), Mapping)
        else {}
    )
    p4_partition = identity.get("partition", {})
    p4_tuple = (
        [int(value) for value in p4_counts]
        if isinstance(p4_counts, list)
        and len(p4_counts) == 4
        and all(type(value) is int for value in p4_counts)
        else None
    )
    p4_condensed_rows = (
        int(p4_tuple[1] + p4_tuple[3]) if p4_tuple is not None else None
    )
    checks = {
        "p6_counts_shape": isinstance(p6_counts, list)
        and len(p6_counts) == 4
        and all(type(value) is int and value > 0 for value in p6_counts),
        "p4_counts_shape": isinstance(p4_counts, list)
        and len(p4_counts) == 4
        and all(type(value) is int and value > 0 for value in p4_counts),
        "p6_live_facts": all(
            isinstance(p6.get(key), str)
            and len(p6[key]) == 64
            for key in ("cell_interior_dofs_sha256", "slave_rows_sha256")
        ),
        "p4_live_facts": all(
            isinstance(p4.get(key), str)
            and len(p4[key]) == 64
            for key in ("cell_interior_dofs_sha256", "slave_rows_sha256")
        ),
        "p6_setup_closes": setup.get("actual_space_counts") == p6_counts
        and setup.get("expected_space_counts") == p6_counts,
        "p6_audit_closes": [
            p6_audit.get("full_rows"),
            p6_audit.get("active_rows"),
            p6_audit.get("interior_rows"),
            p6_audit.get("appended_rows"),
        ] == p6_counts,
        "p6_operator_storage_closes": identity.get("p6_storage_rows") == p6_counts[0]
        if isinstance(p6_counts, list) and len(p6_counts) == 4
        else False,
        "p4_operator_storage_closes": identity.get("p4_storage_rows") == p4_counts[0]
        if isinstance(p4_counts, list) and len(p4_counts) == 4
        else False,
        "p4_stack_tuple_closes": (
            [
                p4_condensation.get("full_rows"),
                p4_condensation.get("active_rows"),
                p4_condensation.get("interior_rows"),
                p4_condensation.get("appended_rows"),
            ]
            == p4_tuple
            and all(value is not None for value in p4_tuple or ())
        ),
        "p4_stack_condensed_rows": (
            p4_condensation.get("matrix_rows") == p4_condensed_rows
            and identity.get("condensed_rows") == p4_condensed_rows
        ),
        "p4_partition_closes": (
            p4_partition.get("storage_size") == p4_tuple[0]
            and p4_partition.get("active_rows") == p4_tuple[1]
            and p4_partition.get("appended_rows") == p4_tuple[3]
        )
        if p4_tuple is not None
        else False,
        "retained_global_closes": solver.get("retained_global_size")
        == (p6_counts[1] + p6_counts[3])
        if isinstance(p6_counts, list) and len(p6_counts) == 4
        else False,
    }
    return {
        "checks": checks,
        "p6_counts": p6_counts,
        "p4_counts": p4_counts,
        "p4_condensed_rows": p4_condensed_rows,
        "passed": all(checks.values()),
    }


def _reference_facts(
    summary: Mapping[str, Any], run_directory: Path
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Recompute the matched-reference branch without trusting comparison.status."""

    checks: dict[str, bool] = {}
    facts: dict[str, Any] = {"status": "NOT_CHECKED"}
    binding = summary.get("reference_binding")
    output_packet = summary.get("output")
    if not isinstance(binding, Mapping) or not isinstance(output_packet, Mapping):
        checks["reference_binding_present"] = False
        return checks, facts
    try:
        descriptors = list(binding.get("binding_files", {}).values()) + [
            binding["residual_binding"]
        ]
        checks.update(
            {
                f"binding_{index}": _hash(Path(str(descriptor["path"])))
                == descriptor["sha256"]
                for index, descriptor in enumerate(descriptors)
            }
        )
        reference_dir = Path(str(binding["reference_output_dir"])).resolve()
        checks.update(
            {
                f"reference_output_{name}": _hash(reference_dir / name) == digest
                for name, digest in binding["reference_output_file_hashes"].items()
            }
        )
        current_output = output_packet["output"]
        comparison = _compare_saved_output(
            current_output,
            binding["reference_output"],
            current_dir=run_directory / "numerical_output",
            reference_dir=reference_dir,
        )
        physical = _v14_physical_checks(
            summary["solver"], summary.get("field", {}), comparison, time_policy="observe_only"
        )
        checks["recomputed_physical_checks"] = bool(physical) and all(
            value is True for value in physical.values()
        )
        checks["reference_authority"] = (
            summary.get("reference_evaluation", {}).get("authority")
            == "MATCHED_REFERENCE_AVAILABLE"
            and summary.get("reference_evaluation", {}).get("loaded") is True
        )
        facts = {
            "status": "CHECKED",
            "comparison": comparison,
            "physical_checks": physical,
            "reference_output_dir": str(reference_dir),
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        checks["reference_recomputation"] = False
        facts = {
            "status": "FAILED_TO_READ_OR_VALIDATE",
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    return checks, facts


def check_run(run_directory: str | Path, *, expected_source_sha: str | None = None) -> dict[str, Any]:
    run_directory = Path(run_directory).resolve()
    summary_path = run_directory / "physical_dual_condensed_robustness_v21_summary.json"
    summary_bytes = summary_path.read_bytes()
    summary = json.loads(summary_bytes.decode("utf-8"))
    root = Path(__file__).resolve().parents[1]
    stage = str(summary.get("stage", ""))
    source_sha = str(summary.get("source_sha", ""))
    summary_schema_facts = _summary_schema_facts(
        summary, source_sha=source_sha, stage=stage
    )
    checks: dict[str, bool] = {
        "source_identity": bool(
            len(source_sha) == 40
            and source_sha == source_sha.lower()
            and all(character in "0123456789abcdef" for character in source_sha)
            and (expected_source_sha is None or source_sha == str(expected_source_sha))
        ),
        "stage": stage in {"Z2_NOTCH_H10", "Z3_ORIGINAL_H7P5", "Z4_NOTCH_H7P5"},
        "profile": summary.get("profile")
        == "physical_p6_trace_p4_condensed_robustness_v21",
        "summary_schema": summary_schema_facts["passed"],
    }
    solver = summary.get("solver", {})
    retained = solver.get("retained_outer", {})
    identity = summary.get("operator_identity", {})
    stack = summary.get("interface_stack", {})
    setup = retained.get("setup_checks", {})
    manifest_sha256: str | None = None
    geometry_facts: dict[str, Any] = {"status": "NOT_CHECKED"}

    try:
        manifest = _json(run_directory / "run_manifest.json")
        manifest_sha256 = _sha256(run_directory / "run_manifest.json")
        resolved = _json(run_directory / "resolved_config.json")
        checks.update(
            {
                "source_manifest": manifest.get("source_sha") == source_sha
                and manifest.get("source_after", {}).get("source_sha") == source_sha
                and manifest.get("source_after", {}).get(
                    "tracked_and_nonignored_untracked_clean"
                )
                is True,
                "resolved_source": resolved.get("provenance", {}).get("source_sha")
                in (None, source_sha),
                "input_identity": bool(
                    identity.get("input_sha256")
                    == manifest.get("input_sha256")
                    == resolved.get("provenance", {}).get("input_sha256")
                ),
                "physical_identity": identity.get("physical_model_sha256")
                == manifest.get("physical_model_sha256")
                == resolved.get("provenance", {}).get("physical_model_sha256"),
                "resolved_profile_stage": resolved.get("solver", {}).get(
                    "preconditioner"
                )
                == "physical_p6_trace_p4_condensed_robustness_v21"
                and resolved.get("solver", {}).get("stage") == stage,
            }
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        checks["source_manifest"] = False
        checks["resolved_source"] = False
        checks["input_identity"] = False
        checks["physical_identity"] = False
        checks["resolved_profile_stage"] = False
        manifest, resolved = {}, {}

    try:
        geometry_descriptor = summary["geometry_audit"]
        geometry_path = Path(str(geometry_descriptor["path"])).resolve()
        geometry_bytes = geometry_path.read_bytes()
        geometry_audit = json.loads(geometry_bytes.decode("utf-8"))
        expected_variant = (
            "original" if stage == "Z3_ORIGINAL_H7P5" else "frozen_notch"
        )
        expected_identity = {
            "Z2_NOTCH_H10": "v21_frozen_notch_h10",
            "Z3_ORIGINAL_H7P5": "v21_original_h7p5",
            "Z4_NOTCH_H7P5": "v21_frozen_notch_h7p5",
        }[stage]
        expected_axes = resolved.get("discretization", {}).get(
            "mesh_axis_cell_counts"
        )
        geometry_checks = {
            "schema": geometry_audit.get("schema")
            == "task039extra.v21.actual-mesh-material-entity-audit.v1",
            "descriptor_path": geometry_path == Path(str(geometry_descriptor["path"])).resolve(),
            "descriptor_hash": geometry_descriptor.get("sha256")
            == hashlib.sha256(geometry_bytes).hexdigest(),
            "variant": geometry_audit.get("variant") == expected_variant,
            "geometry_identity": geometry_audit.get("geometry_identity") == expected_identity,
            "axis_counts": geometry_audit.get("actual_axis_cell_counts") == expected_axes,
            "descriptor_axis_counts": geometry_descriptor.get("actual_axis_cell_counts")
            == geometry_audit.get("actual_axis_cell_counts"),
            "entity_identity": geometry_audit.get("geometry_entity_sha256")
            == resolved.get("derived", {})
            .get("v21_identity", {})
            .get("geometry_entity_sha256"),
            "material_identity": isinstance(
                geometry_audit.get("material_layout_sha256"), str
            )
            and len(geometry_audit["material_layout_sha256"]) == 64,
            "material_baseline": geometry_audit.get("material_baseline_consistent") is True,
            "owned_cell_rows": len(geometry_audit.get("cell_rows", []))
            == int(geometry_audit.get("owned_cell_count", -1)),
            "union_volume": np.isfinite(
                float(geometry_audit.get("symmetric_difference_volume_nm3", np.nan))
            )
            and float(geometry_audit["symmetric_difference_volume_nm3"]) <= 1.0e-9,
            "union_boundary": geometry_audit.get("boundary_complete") is True,
            "notch_branch": (
                int(geometry_audit.get("notch", {}).get("changed_cells", -1)) > 0
                if expected_variant == "frozen_notch"
                else int(geometry_audit.get("notch", {}).get("changed_cells", -1)) == 0
            ),
        }
        geometry_facts = {
            "status": "CHECKED",
            "path": str(geometry_path),
            "sha256": hashlib.sha256(geometry_bytes).hexdigest(),
            "checks": geometry_checks,
            "audit": geometry_audit,
        }
        checks["geometry_audit"] = all(geometry_checks.values())
    except (OSError, KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError):
        checks["geometry_audit"] = False
        geometry_facts = {"status": "FAILED_TO_READ_OR_VALIDATE"}

    dimension_facts = _dimension_identity_facts(summary)
    checks["dimension_identity"] = dimension_facts["passed"]
    native_map_sha = identity.get("p6_native_map_sha256")
    if not isinstance(native_map_sha, str):
        nested = identity.get("retained_p6", {})
        native_map_sha = nested.get("p6_native_map_sha256") if isinstance(nested, Mapping) else None
    checks["native_map_identity"] = isinstance(native_map_sha, str) and len(native_map_sha) == 64

    residual_before: dict[str, Any] = {"status": "NOT_CHECKED"}
    residual_after: dict[str, Any] = {"status": "NOT_CHECKED"}
    try:
        residual_before = fullspace_residual_facts(summary["final_residual"], root)
        residual_after = fullspace_residual_facts(
            summary["post_release_final_residual"], root
        )
        checks["independent_final_A6"] = residual_before["passed"]
        checks["independent_post_release_A6"] = residual_after["passed"]
    except (OSError, KeyError, TypeError, ValueError, FloatingPointError) as exc:
        residual_before = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        residual_after = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        checks["independent_final_A6"] = False
        checks["independent_post_release_A6"] = False

    final_packet: dict[str, Any] = {}
    terminal_raw: dict[str, Any] = {}
    terminal_trace: dict[str, Any] = {"status": "NOT_CHECKED"}
    trace: list[dict[str, Any]] = []
    try:
        final_packet = _json(run_directory / "x2_retained_final.json")
        terminal_raw = _load_v19_arrays(final_packet, "residuals", root)
        terminal_trace = _residual_facts(
            terminal_raw, final_packet["facts"], terminal=True
        )
        checks["terminal_retained_residuals"] = terminal_trace["passed"]
        monitor_rows = _jsonl(run_directory / "monitor_residuals.jsonl")
        for row in monitor_rows:
            packet = row["packet"]
            raw = _load_v19_arrays(packet, "raw", root)
            facts = _residual_facts(raw, packet["facts"])
            trace.append({"iteration": int(row["iteration"]), "facts": facts})
        iterations = int(solver["iterations"])
        checks["every_eight_saved"] = set(range(0, iterations + 1, 8)) <= {
            row["iteration"] for row in trace
        }
        checks["saved_residuals"] = bool(trace) and all(
            row["facts"]["passed"] for row in trace
        )
        retained_checkpoints = retained.get("retained_checkpoints", {})
        checks["every_32_saved_y"] = set(range(0, iterations + 1, 32)) <= {
            int(key) for key in retained_checkpoints
        }
    except (OSError, KeyError, TypeError, ValueError, FloatingPointError) as exc:
        terminal_trace = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        checks["terminal_retained_residuals"] = False
        checks["every_eight_saved"] = False
        checks["saved_residuals"] = False
        checks["every_32_saved_y"] = False

    saved_fields: dict[str, Any] = {"status": "NOT_CHECKED"}
    try:
        p6_counts = dimension_facts["p6_counts"]
        expected_rhs_sha = str(setup["physical_rhs_sha256"])
        saved_fields = _saved_field_facts_v21(
            _array(final_packet, "full_solution", root),
            _array(final_packet, "original_rhs", root),
            _array(final_packet, "retained_y", root),
            terminal_raw["retained_alpha"],
            _array(final_packet, "owned_slave_rows", root),
            _array(summary["final_residual"], "solution", root),
            _array(summary["final_residual"], "rhs", root),
            _array(summary["post_release_final_residual"], "solution", root),
            _array(summary["post_release_final_residual"], "rhs", root),
            expected_full_storage_size=int(p6_counts[0]),
            expected_retained_size=int(p6_counts[1] + p6_counts[3]),
            expected_rhs_sha256=expected_rhs_sha,
        )
        checks["complete_saved_field"] = saved_fields["passed"]
    except (OSError, KeyError, TypeError, ValueError, IndexError, FloatingPointError) as exc:
        saved_fields = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        checks["complete_saved_field"] = False

    balance: dict[str, Any] = {"status": "NOT_CHECKED"}
    p4_quality: dict[str, Any] = {"status": "NOT_CHECKED"}
    matrix: dict[str, Any] = {"status": "NOT_CHECKED"}
    try:
        boundaries = summary["pc"]["boundary_records"]
        balance = fullspace_balance_facts(boundaries)
        p4_quality = exact_p4_call_facts(boundaries)
        matrix = matrix_identity_facts(
            stack["matrix_identity_before_factor"],
            stack["matrix_identity_after_factor"],
        )
        matrix_checks = matrix["checks"]
        matrix_checks["before_release_matches_factor"] = (
            stack.get("matrix_identity_before_release")
            == stack.get("matrix_identity_after_factor")
        )
        matrix_checks["before_release_consistent"] = (
            stack.get("matrix_identity_before_release")
            == stack.get("matrix_identity_before_factor")
        )
        matrix["passed"] = all(matrix_checks.values())
        checks["unchanged_BAL_H"] = balance["passed"]
        checks["online_native_A4"] = p4_quality["passed"]
        checks["p4_CSR_identity"] = matrix["passed"]
    except (KeyError, TypeError, ValueError, OSError) as exc:
        balance = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        p4_quality = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        matrix = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        checks["unchanged_BAL_H"] = False
        checks["online_native_A4"] = False
        checks["p4_CSR_identity"] = False

    structural = {
        "terminal_state": solver.get("status") == "TRUE_RESIDUAL_PASS"
        and summary.get("stage_pass") is True
        and summary.get("official_result") is True,
        "one_KSP": solver.get("ksp_create_count")
        == solver.get("ksp_solve_count")
        == solver.get("ksp_destroy_count")
        == 1,
        "frozen_KSP": solver.get("restart") == 32
        and solver.get("max_it") == 2048
        and 0 <= int(solver.get("iterations", -1)) <= 2048
        and solver.get("screen_enabled") is False,
        "zero_start": solver.get("zero_start") is True,
        "p6_action_only": identity.get("retained_p6", {})
        .get("p6_build_audit", {})
        .get("matrix_materialized")
        is False,
        "prepared_p6_form": identity.get("retained_p6", {}).get("compiled_form_reused")
        is True,
        "setup_count": setup.get("setup_pc_counts")
        == {"bal_h": 1, "p4_mat_solve": 2, "h6": 1},
        "total_PC_count": balance.get("pc_count")
        == int(solver.get("pc_apply_count", -1)) + 1,
        "complete_PC_counts": solver.get("actual_pc_counts_including_one_setup_call")
        == {
            "bal_h": balance.get("pc_count"),
            "h6": balance.get("pc_count"),
            "p4_mat_solve": balance.get("global_mat_solve_count"),
        }
        and summary.get("pc", {}).get("h6_apply_count") == balance.get("pc_count")
        and summary.get("pc", {}).get("native_A4_action_count")
        == 2 * balance.get("pc_count", -1),
        "cache_unchanged": retained.get("cache", {}).get("array_content_sha256")
        == solver.get("p6_cache_after", {}).get("array_content_sha256")
        and retained.get("cache", {}).get("unique_numpy_bytes")
        == solver.get("p6_cache_after", {}).get("unique_numpy_bytes"),
        "rhs_policy": setup.get("rhs_identity_policy") == "case_bound_physical_rhs"
        and setup.get("physical_rhs_sha256") == saved_fields.get("rhs_sha256"),
        "exact_p4": stack.get("backend") == "exact"
        and _control_value(stack.get("factor", {}).get("controls_before_symbolic", {}), "icntl", 35) == 0
        and _control_value(stack.get("factor", {}).get("controls_before_symbolic", {}), "icntl", 10) == 0,
        "release_contract": stack.get("matrix_lifecycle_policy")
        == "MATRIX_RETAINED_BACKEND_DEPENDENCY"
        and stack.get("matrix_release_before_official_output") is True,
        "time_policy": summary.get("time_policy") == "observe_only"
        and summary.get("time_gate_evaluated") is False,
    }
    checks.update({f"structural_{key}": value for key, value in structural.items()})

    try:
        samples = _jsonl(run_directory / "watchdog/resources.jsonl")
        events = _jsonl(run_directory / "v21_events.jsonl")
        aliased_events = _alias_v21_events(events, stage=stage)
        resources = resource_facts(run_directory, fullspace=True, prefix="v21")
        phases = phase_resource_facts(samples, aliased_events)
        jit = _jit_preparation_facts_v21(aliased_events, samples)
        cache = _cache_description_facts_v21(
            _json(run_directory / "v21_x1_p6_cache_identity.json"),
            identity.get("retained_p6", {}).get("p6_build_audit", {}),
            identity.get("retained_p6", {}).get("p6_recipe", {}),
        )
        lifecycle = _v21_release_timeline_facts(events, stage=stage)
        checks["resource_gate"] = resources["passed"]
        checks["phase_evidence"] = phases.get("status") == "MEASURED"
        checks["jit_preparation"] = jit["passed"]
        checks["cache_descriptor"] = cache["passed"] and cache[
            "array_content_sha256"
        ] == retained.get("cache", {}).get("array_content_sha256")
        checks["release_timeline"] = lifecycle["passed"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        resources = {"passed": False, "error": str(exc)}
        phases = {"status": "FAILED_TO_READ_OR_VALIDATE", "error": str(exc)}
        jit = {"passed": False, "error": str(exc)}
        cache = {"passed": False, "error": str(exc)}
        lifecycle = {"passed": False, "error": str(exc)}
        checks["resource_gate"] = False
        checks["phase_evidence"] = False
        checks["jit_preparation"] = False
        checks["cache_descriptor"] = False
        checks["release_timeline"] = False

    output_dir = run_directory / "numerical_output"
    mode_identity = _mode_identity_facts_v21(summary, run_directory, output_dir)
    checks["mode_identity"] = mode_identity["passed"]
    channel_checks, channel_facts = _check_channels(
        output_dir, summary.get("output_facts", {})
    )
    checks.update({f"channel_{key}": value for key, value in channel_checks.items()})
    field_checks, field_facts = _field_output_facts_v21(
        output_dir, summary.get("output_facts", {})
    )
    checks.update({f"field_{key}": value for key, value in field_checks.items()})

    reference_facts: dict[str, Any] = {"status": "NOT_CHECKED"}
    if stage == "Z2_NOTCH_H10":
        reference_checks, reference_facts = _reference_facts(summary, run_directory)
        checks.update({f"reference_{key}": value for key, value in reference_checks.items()})
        checks["reference_classification"] = bool(reference_checks) and all(
            reference_checks.values()
        )
        classification = "MATCHED_REFERENCE_PASS"
    else:
        checks["reference_classification"] = bool(
            summary.get("reference_evaluation", {}).get("authority")
            == "MATCHED_REFERENCE_NOT_AVAILABLE"
            and summary.get("reference_evaluation", {}).get("mode")
            == "authority_limited"
        )
        classification = PASS_CLASSIFICATION

    errors = [key for key, passed in checks.items() if passed is not True]
    passed = not errors
    return {
        "schema": CHECKER_SCHEMA,
        "status": "PASS" if passed else "FAIL",
        "evidence_valid": passed,
        "stage_pass": passed,
        "classification": classification if passed else "V21_CHECKER_FAIL",
        "stage": stage,
        "run_directory": str(run_directory),
        "source_sha": source_sha,
        "solver_source_sha": source_sha,
        "checker_source_sha256": _sha256(Path(__file__).resolve()),
        "expected_source_sha": expected_source_sha,
        "worker_summary_path": str(summary_path),
        "worker_summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
        "manifest_sha256": manifest_sha256,
        "checks": checks,
        "errors": errors,
        "summary_schema_facts": summary_schema_facts,
        "dimension_facts": dimension_facts,
        "residual_before": residual_before,
        "residual_after": residual_after,
        "terminal_trace": terminal_trace,
        "trace": trace,
        "saved_field": saved_fields,
        "balance": balance,
        "online_p4_quality": p4_quality,
        "matrix": matrix,
        "resources": resources,
        "phase_resources": phases,
        "jit_preparation": jit,
        "cache_descriptor": cache,
        "lifecycle": lifecycle,
        "reference": reference_facts,
        "channel_facts": channel_facts,
        "field_facts": field_facts,
        "geometry_facts": geometry_facts,
        "mode_identity": mode_identity,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = check_run(
            args.run_directory, expected_source_sha=args.expected_source_sha
        )
    except Exception as exc:  # checker boundary must emit a result, not crash
        result = {
            "schema": CHECKER_SCHEMA,
            "status": "FAIL",
            "evidence_valid": False,
            "errors": [{"type": type(exc).__name__, "message": str(exc)}],
        }
    output = args.output or (args.run_directory / "v21_checker_result.json")
    output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHECKER_SCHEMA",
    "MODE_SHA",
    "check_run",
    "main",
    "_alias_v21_events",
    "_cache_description_facts_v21",
    "_check_channels",
    "_dimension_identity_facts",
    "_field_output_facts_v21",
    "_jit_preparation_facts_v21",
    "_mode_identity_facts_v21",
    "_summary_schema_facts",
    "_v21_release_timeline_facts",
]
