"""Independently recompute the Task40 Review V5 Gx784 saved-record gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


FIELD_NAMES = (
    "E_total",
    "E_scattered",
    "H_total",
    "H_scattered",
    "curl_E_total",
    "curl_E_scattered",
    "scaled_curl_E_total",
    "scaled_curl_E_scattered",
)
FIELD_LIMIT = 1.0e-2
MODE_LIMIT = 1.0e-2
POWER_LIMIT = 1.0e-3
ENERGY_LIMIT = 1.0e-5
RESIDUAL_LIMIT = 1.0e-6
NATIVE_IDENTITY_LIMIT = 1.0e-10
PORT_RESIDUAL_LIMIT = 1.0e-8
FROZEN_KEYS_PATH = Path(__file__).resolve().parents[1] / (
    "docs/task40extra_0p7nm_engineering/outcomes/records/channel_study_v2.json"
)
FROZEN_KEYS_SHA256 = "9d04ad61c3e7f5dc16f4606428c8e5721033d33ec96cf53b7e902f5c308d472f"
FROZEN_V4_VOLUME_SHA256 = "5f8004f51cb7d9543730281ace16f296cdc47b0358c66038302bf4f39ac40c17"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite")
    return number


def _complex_pair(value: Any, label: str) -> complex:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} is not a [real, imag] pair")
    result = complex(_finite(value[0], label), _finite(value[1], label))
    return result


def _load_f5_norms(binding: dict[str, Any]) -> tuple[dict[str, dict[str, float]], str]:
    path = Path(binding["path"]).resolve()
    digest = _sha256(path)
    if digest != FROZEN_V4_VOLUME_SHA256 or digest != binding.get("sha256"):
        raise ValueError("frozen V4 volume archive hash differs")
    record = _read_json(path)
    if (
        record.get("schema") != "task40.review-v4.directional-cross-volume.v1"
        or record.get("status") != "completed"
    ):
        raise ValueError("frozen V4 F5 denominator archive has the wrong identity")
    identities = record.get("run_identities", {})
    gx = identities.get("G10", {})
    f5 = identities.get("G11", {})
    if (
        gx.get("run_id") != "task40extra_0p7nm_nonseparable_gx560_manual_m2_v3_v1"
        or f5.get("run_id") != "task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1"
        or gx.get("run_root") != binding.get("Gx_run_root")
        or f5.get("run_root") != binding.get("F5_run_root")
    ):
        raise ValueError("frozen V4 archive is not bound to the saved Gx and F5 runs")
    norms: dict[str, dict[str, float]] = {}
    regions = record["comparison"]["regions"]
    for region, region_record in regions.items():
        norms[region] = {}
        for name, quantity in region_record["quantities"].items():
            value = _finite(quantity["corner_l2_norms"]["G11"], f"F5 {region}/{name}")
            if value <= 0.0:
                raise ValueError(f"archived F5 norm is not positive for {region}/{name}")
            norms[region][name] = value
    expected = {
        ("physical_domain", "E_scattered"): 0.8964588762723267,
        ("physical_domain", "scaled_curl_E_scattered"): 0.8963653695824167,
    }
    for key, value in expected.items():
        if not math.isclose(norms[key[0]][key[1]], value, rel_tol=0.0, abs_tol=1.0e-15):
            raise ValueError(f"frozen F5 norm changed for {key[0]}/{key[1]}")
    return norms, digest


def _record_map(records: list[dict[str, Any]]) -> tuple[list[tuple[str, int, int, str]], dict[tuple[str, int, int, str], dict[str, Any]]]:
    keys = []
    mapped = {}
    for row in records:
        key = (
            str(row["side"]),
            int(row["m"] if "m" in row else row["order_m"]),
            int(row["n"] if "n" in row else row["order_n"]),
            str(row["polarization"]),
        )
        if key in mapped:
            raise ValueError(f"duplicate mode key {key}")
        _complex_pair(row["outgoing_amplitude_at_boundary"], f"mode {key} amplitude")
        _complex_pair(row["gamma"], f"mode {key} gamma")
        _finite(row["power_ratio"], f"mode {key} power ratio")
        if not isinstance(row.get("propagating"), bool):
            raise ValueError(f"mode {key} propagating flag is missing")
        keys.append(key)
        mapped[key] = row
    return keys, mapped


def _recompute_mode_pair(
    first_rows: list[dict[str, Any]],
    second_rows: list[dict[str, Any]],
    f5_rows: list[dict[str, Any]],
    selected_keys: set[tuple[str, int, int, str]],
) -> dict[str, Any]:
    first_keys, first = _record_map(first_rows)
    second_keys, second = _record_map(second_rows)
    f5_keys, f5 = _record_map(f5_rows)
    if len(first_keys) != 340 or first_keys != second_keys or first_keys != f5_keys:
        raise ValueError("the saved mode records are not the same ordered M=8,N=2 inventory")
    if len(selected_keys) != 11 or not selected_keys.issubset(set(first_keys)):
        raise ValueError("the frozen significant key list does not match the 11-mode subset")
    significant_errors = []
    f5_diagnostics = []
    for key in first_keys:
        left = _complex_pair(first[key]["outgoing_amplitude_at_boundary"], str(key))
        right = _complex_pair(second[key]["outgoing_amplitude_at_boundary"], str(key))
        reference = _complex_pair(f5[key]["outgoing_amplitude_at_boundary"], str(key))
        if bool(first[key]["propagating"]) != bool(second[key]["propagating"]):
            raise ValueError(f"saved runs disagree on propagation status for {key}")
        difference = abs(right - left)
        f5_diagnostics.append(difference / max(abs(reference), float.fromhex("0x1.0p-1022")))
        if key in selected_keys:
            if not first[key]["propagating"]:
                raise ValueError(f"frozen significant key is not propagating in the first run: {key}")
            significant_errors.append(
                difference / max(abs(left), float.fromhex("0x1.0p-1022"))
            )
    maximum = max(significant_errors, default=math.inf)
    return {
        "mode_count": len(first_keys),
        "ordered_keys_identical": True,
        "frozen_significant_key_count": len(selected_keys),
        "max_significant_relative_to_first": maximum,
        "max_fixed_F5_normalized_diagnostic": max(f5_diagnostics, default=math.inf),
        "limit": MODE_LIMIT,
        "pass": len(significant_errors) == 11 and maximum <= MODE_LIMIT,
    }


def check_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "task40extra.review-v5.gx784-paired-comparison.v1":
        raise ValueError("V5 paired-comparison schema differs")

    solver_evidence = payload["solver_evidence"]
    solver_path = Path(solver_evidence["path"]).resolve()
    if _sha256(solver_path) != solver_evidence.get("sha256"):
        raise ValueError("Gx784 solver summary hash differs")
    solver_summary = _read_json(solver_path)
    solver_gate = _recompute_solver_gate(solver_summary)
    if not solver_gate["pass"]:
        return {
            "schema": "task40extra.review-v5.gx784-independent-check.v1",
            "status": "failed",
            "classification": "solver_or_recovery_gate_not_passed_comparison_held",
            "comparison_status": "held",
            "independently_recomputed": True,
            "solver_gate": solver_gate,
            "failure_reasons": list(solver_gate["failure_reasons"]),
        }

    field_preflight = payload.get("field_artifact_preflight")
    if isinstance(field_preflight, dict):
        archive_path_value = field_preflight.get("archive_path")
        expected_archive_sha = field_preflight.get("expected_sha256")
        actual_archive_sha = None
        if archive_path_value:
            archive_path = Path(str(archive_path_value)).resolve()
            if archive_path.is_file() and archive_path.stat().st_size > 0:
                actual_archive_sha = _sha256(archive_path)
        if (
            field_preflight.get("complete") is not True
            or not isinstance(expected_archive_sha, str)
            or actual_archive_sha != expected_archive_sha
        ):
            reason = field_preflight.get("failure_reason") or (
                "Gx784 retained-field archive is missing or its SHA differs"
            )
            return {
                "schema": "task40extra.review-v5.gx784-independent-check.v1",
                "status": "failed",
                "classification": "saved_field_archive_missing_or_hash_mismatch_comparison_held",
                "comparison_status": "held",
                "independently_recomputed": True,
                "solver_gate": solver_gate,
                "field_artifact_preflight": {
                    **field_preflight,
                    "actual_sha256": actual_archive_sha,
                },
                "failure_reasons": [str(reason)],
            }

    restoration_failures = []
    for label in ("Gx", "F5", "Gx784"):
        witness = payload.get("runs", {}).get(label, {}).get(
            "field_restoration_sample_witness", {}
        )
        if witness.get("pass") is not True:
            restoration_failures.append(
                f"{label}: saved total-field sample restoration witness did not pass"
            )
    if restoration_failures:
        return {
            "schema": "task40extra.review-v5.gx784-independent-check.v1",
            "status": "failed",
            "classification": "saved_field_restoration_not_passed_comparison_held",
            "comparison_status": "held",
            "independently_recomputed": True,
            "solver_gate": solver_gate,
            "failure_reasons": restoration_failures,
        }

    frozen_order = _load_frozen_significant_keys(
        payload.get("frozen_significant_keys", [])
    )
    f5_norms, f5_hash = _load_f5_norms(payload["fixed_F5_denominator"])
    if payload["fixed_F5_denominator"].get("archive_sha256") != f5_hash:
        raise ValueError("comparison denominator archive binding differs")

    failure_reasons: list[str] = []
    field_pairs = {}
    for pair_name in ("Gx_to_Gx784", "F5_to_Gx784"):
        comparison = payload["field_comparisons"][pair_name]["comparison"]
        if comparison.get("material_tag_mismatch_count") != 0:
            failure_reasons.append(f"{pair_name}: material tags differ")
        quantities = comparison["metrics"]["physical_domain"]["quantities"]
        values = {}
        for name in FIELD_NAMES:
            row = quantities[name]
            difference = _finite(row["difference_l2_norm"], f"{pair_name}/{name} difference")
            denominator = _finite(f5_norms["physical_domain"][name], f"F5/{name} denominator")
            relative = difference / denominator
            archived_relative = _finite(
                row["relative_to_fixed_denominator"],
                f"{pair_name}/{name} fixed-denominator relative",
            )
            if row.get("fixed_denominator_label") != "F5" or not math.isclose(
                archived_relative, relative, rel_tol=1e-12, abs_tol=1e-15
            ):
                raise ValueError(f"{pair_name}/{name}: fixed F5 normalization is inconsistent")
            values[name] = relative
            if relative > FIELD_LIMIT:
                failure_reasons.append(f"{pair_name}: {name}={relative:.9g} > {FIELD_LIMIT:g}")
        field_pairs[pair_name] = {
            "relative_to_archived_F5_norm": values,
            "limit": FIELD_LIMIT,
            "pass": all(value <= FIELD_LIMIT for value in values.values()),
        }

    mode_inventories = payload["mode_inventories"]
    frozen_keys = set(frozen_order)
    mode_pairs = {
        "Gx_to_Gx784": _recompute_mode_pair(
            mode_inventories["Gx"]["records"],
            mode_inventories["Gx784"]["records"],
            mode_inventories["F5"]["records"],
            frozen_keys,
        ),
        "F5_to_Gx784": _recompute_mode_pair(
            mode_inventories["F5"]["records"],
            mode_inventories["Gx784"]["records"],
            mode_inventories["F5"]["records"],
            frozen_keys,
        ),
    }
    for name, gate in mode_pairs.items():
        if not gate["pass"]:
            failure_reasons.append(
                f"{name}: significant mode maximum {gate['max_significant_relative_to_first']:.9g} > {MODE_LIMIT:g}"
            )

    powers = payload["official_power_by_run"]
    power_pairs = {}
    for pair_name, first_label in (("Gx_to_Gx784", "Gx"), ("F5_to_Gx784", "F5")):
        first, second = powers[first_label], powers["Gx784"]
        metric_differences = {}
        for metric in ("R_total", "T_total", "A_balance", "A_volume_total"):
            left = _finite(first[metric], f"{first_label}/{metric}")
            right = _finite(second[metric], f"Gx784/{metric}")
            difference = abs(right - left)
            metric_differences[metric] = difference
            if difference > POWER_LIMIT:
                failure_reasons.append(f"{pair_name}: {metric} absolute difference {difference:.9g} > {POWER_LIMIT:g}")
        power_pairs[pair_name] = {
            "absolute_differences": metric_differences,
            "limit": POWER_LIMIT,
            "pass": all(value <= POWER_LIMIT for value in metric_differences.values()),
        }

    energy = {}
    for label, row in powers.items():
        r = _finite(row["R_total"], f"{label}/R_total")
        t = _finite(row["T_total"], f"{label}/T_total")
        a_balance = _finite(row["A_balance"], f"{label}/A_balance")
        a_volume = _finite(row["A_volume_total"], f"{label}/A_volume_total")
        closure = abs(r + t + a_volume - 1.0)
        absorption = abs(a_balance - a_volume)
        energy[label] = {"port_volume_closure": closure, "absorption_difference": absorption}
        if closure > ENERGY_LIMIT:
            failure_reasons.append(f"{label}: R+T+A_volume closure {closure:.9g} > {ENERGY_LIMIT:g}")
        if absorption > ENERGY_LIMIT:
            failure_reasons.append(f"{label}: A_balance−A_volume {absorption:.9g} > {ENERGY_LIMIT:g}")
        for r00 in ("R00_s", "R00_p", "R00_total"):
            _finite(row[r00], f"{label}/{r00}")

    checks_pass = not failure_reasons
    return {
        "schema": "task40extra.review-v5.gx784-independent-check.v1",
        "status": "pass" if checks_pass else "failed",
        "classification": "tested_x_agreement_pass" if checks_pass else "accuracy_not_closed",
        "independently_recomputed": True,
        "field_pairs": field_pairs,
        "mode_pairs": mode_pairs,
        "power_pairs": power_pairs,
        "energy_gates": energy,
        "solver_gate": solver_gate,
        "failure_reasons": failure_reasons,
    }


def _load_frozen_significant_keys(
    payload_keys: list[Any],
) -> list[tuple[str, int, int, str]]:
    if _sha256(FROZEN_KEYS_PATH) != FROZEN_KEYS_SHA256:
        raise ValueError("tracked frozen M2 significant-key artifact SHA differs")
    frozen = _read_json(FROZEN_KEYS_PATH)
    source_keys = frozen.get("frozen_baseline", {}).get("selected_keys")
    if not isinstance(source_keys, list):
        raise ValueError("tracked frozen M2 significant-key list is missing")
    expected = [
        (str(row[0]), int(row[1]), int(row[2]), str(row[3]))
        for row in source_keys
    ]
    supplied = [
        (str(row[0]), int(row[1]), int(row[2]), str(row[3]))
        for row in payload_keys
    ]
    if len(expected) != 11 or len(set(expected)) != 11:
        raise ValueError("tracked frozen M2 significant-key list is not 11 unique keys")
    if supplied != expected:
        raise ValueError("payload significant keys differ from the frozen channel-study artifact")
    return expected


def _number_or_none(value: Any, label: str, failures: list[str]) -> float | None:
    try:
        return _finite(value, label)
    except (TypeError, ValueError):
        failures.append(f"{label} is missing or nonfinite")
        return None


def _recompute_solver_gate(summary: dict[str, Any]) -> dict[str, Any]:
    """Read native worker residual/recovery fields, not only its aggregate booleans."""

    failures: list[str] = []
    final = _number_or_none(
        summary.get("final_residual", {}).get("explicit_relative_residual"),
        "final_residual.explicit_relative_residual",
        failures,
    )
    post = _number_or_none(
        summary.get("post_release_final_residual", {}).get(
            "explicit_relative_residual"
        ),
        "post_release_final_residual.explicit_relative_residual",
        failures,
    )
    gates = summary.get("gates", {})
    reported_post = _number_or_none(
        gates.get("post_release_final_explicit_relative_residual"),
        "gates.post_release_final_explicit_relative_residual",
        failures,
    )
    reported_final = _number_or_none(
        gates.get("independent_final_explicit_relative_residual"),
        "gates.independent_final_explicit_relative_residual",
        failures,
    )
    for label, value in (
        ("full A6 residual", final),
        ("post-release full A6 residual", post),
    ):
        if value is not None and value > RESIDUAL_LIMIT:
            failures.append(f"{label}={value:.9g} > {RESIDUAL_LIMIT:g}")
    if final is not None and reported_final is not None and not math.isclose(
        final, reported_final, rel_tol=1e-12, abs_tol=1e-15
    ):
        failures.append("native and aggregate final A6 residual values disagree")
    if post is not None and reported_post is not None and not math.isclose(
        post, reported_post, rel_tol=1e-12, abs_tol=1e-15
    ):
        failures.append("native and aggregate post-release A6 residual values disagree")

    retained = summary.get("x2_retained_final", {})
    residuals = retained.get("residuals", {})
    native_identity = _number_or_none(
        residuals.get("native_identity_relative"),
        "x2_retained_final.residuals.native_identity_relative",
        failures,
    )
    internal_residual = _number_or_none(
        residuals.get("internal_residual_relative"),
        "x2_retained_final.residuals.internal_residual_relative",
        failures,
    )
    schur_port_identity = _number_or_none(
        residuals.get("schur_port_identity_relative"),
        "x2_retained_final.residuals.schur_port_identity_relative",
        failures,
    )
    port_residual = _number_or_none(
        residuals.get("port_residual_relative"),
        "x2_retained_final.residuals.port_residual_relative",
        failures,
    )
    for name, value in (
        ("native recovery identity", native_identity),
        ("interior residual", internal_residual),
        ("Schur-port identity", schur_port_identity),
    ):
        if value is not None and value > NATIVE_IDENTITY_LIMIT:
            failures.append(f"{name}={value:.9g} > {NATIVE_IDENTITY_LIMIT:g}")
    if port_residual is not None and port_residual > PORT_RESIDUAL_LIMIT:
        failures.append(f"port residual={port_residual:.9g} > {PORT_RESIDUAL_LIMIT:g}")

    post_packet = summary.get("post_release_final_residual", {})
    release_facts = post_packet.get("release_facts", {})
    p6_release = release_facts.get("p6", {}).get("released_after_final_residual") is True
    p4_release = release_facts.get("p4", {}).get("released_after_final_residual") is True
    booleans = {
        "post_release_residual_gate": gates.get("post_release_residual_gate") is True,
        "release_after_final_residual": summary.get("release_after_final_residual") is True,
        "p6_released_after_final_residual": p6_release,
        "p4_released_after_final_residual": p4_release,
        "authority_limited_checks_pass": gates.get("authority_limited_checks_pass") is True,
        "complete_field_saved": retained.get("complete_field_saved") is True,
        "saved_before_field_evaluation": retained.get("saved_before_field_evaluation") is True,
        "strict_zero_slave_storage": residuals.get("strict_zero_slave_storage") is True,
    }
    failures.extend(f"{name} is not true" for name, value in booleans.items() if not value)
    return {
        "explicit_relative_A6_true_residual": final,
        "post_release_explicit_relative_A6_true_residual": post,
        "limit": RESIDUAL_LIMIT,
        "native_recovery_identity_relative": native_identity,
        "interior_residual_relative": internal_residual,
        "schur_port_identity_relative": schur_port_identity,
        "native_identity_limit": NATIVE_IDENTITY_LIMIT,
        "port_residual_relative": port_residual,
        "port_residual_limit": PORT_RESIDUAL_LIMIT,
        "native_release_recovery_checks": booleans,
        "pass": not failures,
        "failure_reasons": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_path = args.result.resolve()
    payload = _read_json(result_path)
    checked = check_payload(payload)
    checked["source_result_path"] = str(result_path)
    checked["source_result_sha256"] = _sha256(result_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(checked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": checked["status"], "classification": checked["classification"], "failure_reasons": checked["failure_reasons"]}, ensure_ascii=False), flush=True)
    # A completed negative Gate is still a valid checker result. Structural or
    # provenance failures raise above and produce a non-zero process exit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
