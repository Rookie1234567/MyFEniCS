"""Independent raw-data checker for the Task040 V1-2/V1-3 Run-B route."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

HARD_STOP_BYTES = 45 * 2**30
COMPLEMENT_ORTHOGONALITY_LIMIT = 1.0e-8
ROOT = Path(__file__).resolve().parents[1]
PROBE_MANIFEST = (
    ROOT
    / "benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/"
    / "task040_v1_2_probe_manifest_v1.json"
)
FROZEN_PROBE_MANIFEST_SHA256 = (
    "7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad"
)
FROZEN_LOWER_RESOLVED_MODE_METADATA_SHA256 = (
    "dde523dc62c73f7bd50953958fde42d42d0cfd5756c16329b16915e13c4742da"
)
EXPECTED_SPAN_SIZES = (296, 776, 480)
__all__ = ["recompute_v1_2_gate", "recompute_v1_2_small_contractions"]


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _pair(value: Any) -> complex:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(_finite(item) for item in value)
    ):
        raise ValueError("Run-B complex values must be finite [real, imag] pairs")
    return complex(float(value[0]), float(value[1]))


def _matrix(value: Any) -> np.ndarray:
    if not isinstance(value, list) or not value:
        raise ValueError("Run-B small matrix is empty")
    try:
        result = np.asarray([[_pair(item) for item in row] for row in value])
    except ValueError as exc:
        raise ValueError("Run-B small matrix is not rectangular") from exc
    if result.ndim != 2 or not result.shape[1] or not np.isfinite(result).all():
        raise ValueError("Run-B small matrix is not finite and rectangular")
    return np.asarray(result, dtype=np.complex128)


def _pair_out(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _norm2(value: Any, name: str) -> float:
    scalar = _pair(value)
    scale = max(abs(scalar.real), 1.0)
    if abs(scalar.imag) > 1.0e-8 * scale:
        raise ValueError(f"{name} self-contraction has a nonzero imaginary part")
    if scalar.real < -1.0e-10 * scale:
        raise ValueError(f"{name} self-contraction is negative")
    return max(float(scalar.real), 0.0)


def _nonnegative(value: float, scale: float, name: str) -> float:
    tolerance = 1.0e-10 * max(abs(scale), 1.0)
    if value < -tolerance:
        raise ValueError(f"{name} contraction is materially negative")
    return max(float(value), 0.0)


def _contraction_metrics(probe: dict[str, Any]) -> dict[str, Any]:
    contractions = probe.get("contractions")
    if not isinstance(contractions, dict):
        raise ValueError("Run-B probe is missing distributed contractions")
    ss = _norm2(contractions["source_h_source"], "source")
    bb = _norm2(contractions["scalar_h_scalar"], "scalar")
    ee = _norm2(contractions["exact_h_exact"], "exact")
    pp = _norm2(contractions["projected_h_projected"], "projected")
    se = _pair(contractions["scalar_h_exact"])
    pe = _pair(contractions["projected_h_exact"])
    if min(ss, bb, ee, pp) <= 0.0:
        raise ValueError("Run-B probe has a zero source/action norm")
    alpha = se / bb
    rho_star_sq = _nonnegative(ee - abs(se) ** 2 / bb, ee, "rho_star")
    original_sq = _nonnegative(ee + bb - 2.0 * se.real, ee + bb, "original")
    projected_sq = _nonnegative(pp + ee - 2.0 * pe.real, pp + ee, "projected")
    correlation = se / math.sqrt(bb * ee)
    before = probe.get("YH_before_projection")
    after = probe.get("YH_after_projection")
    complement_orthogonality = None
    if before is not None or after is not None:
        if not isinstance(before, list) or not isinstance(after, list):
            raise ValueError("Run-B complement YH fields are malformed")
        before_norm = math.sqrt(sum(abs(_pair(item)) ** 2 for item in before))
        after_norm = math.sqrt(sum(abs(_pair(item)) ** 2 for item in after))
        complement_orthogonality = after_norm / max(before_norm, 1.0e-30)
        if not math.isfinite(complement_orthogonality):
            raise ValueError("Run-B complement orthogonality is non-finite")
    return {
        "label": str(probe["label"]),
        "group": probe.get("group"),
        "kind": str(probe.get("kind", "physical")),
        "source_norm_squared": ss,
        "alpha": _pair_out(alpha),
        "alpha_magnitude": float(abs(alpha)),
        "alpha_phase_radians": float(np.angle(alpha)),
        "original_scalar_exact_relative": math.sqrt(original_sq / ee),
        "rho_star": math.sqrt(rho_star_sq / ee),
        "correlation": _pair_out(correlation),
        "correlation_magnitude": float(abs(correlation)),
        "projected_exact_relative": math.sqrt(projected_sq / ee),
        "complement_orthogonality": complement_orthogonality,
    }


def _group_metrics(raw: dict[str, Any]) -> list[dict[str, Any]]:
    groups = raw.get("groups")
    if not isinstance(groups, list) or len(groups) != 3:
        raise ValueError("Run-B raw record must contain exactly three groups")
    result = []
    for group in groups:
        contractions = group.get("projected_contractions")
        if not isinstance(contractions, dict):
            contractions = {
                "gram": group["gram"],
                "scalar": group["scalar_projected"],
                "exact": group["exact_projected"],
            }
        gram = _matrix(contractions["gram"])
        scalar = _matrix(contractions["scalar"])
        exact = _matrix(contractions["exact"])
        if gram.shape[0] != gram.shape[1] or scalar.shape != exact.shape:
            raise ValueError("Run-B projected contractions have inconsistent shapes")
        singular = np.linalg.svd(exact, compute_uv=False)
        result.append(
            {
                "group": int(group["group"]),
                "span_size": int(exact.shape[0]),
                "declared_span_size": int(group.get("span_size", -1)),
                "matrix_shapes": {
                    "gram": list(gram.shape),
                    "scalar": list(scalar.shape),
                    "exact": list(exact.shape),
                },
                "scalar_exact_relative": float(
                    np.linalg.norm(exact - scalar)
                    / max(float(np.linalg.norm(exact)), 1.0e-30)
                ),
                "gram_rank": int(np.linalg.matrix_rank(gram)),
                "projected_rank": int(np.linalg.matrix_rank(exact)),
                "projected_singular_values": [float(item) for item in singular],
                "projected_condition": float(singular[0] / singular[-1])
                if singular.size and singular[-1] > 0.0
                else float("inf"),
            }
        )
    return result


def _probe_metrics(raw: dict[str, Any]) -> list[dict[str, Any]]:
    probes = raw.get("probes")
    if not isinstance(probes, list) or not probes:
        probes = list(raw.get("physical_probes", [])) + list(
            raw.get("interface_probes", [])
        )
    if not probes:
        raise ValueError("Run-B raw record has no probes")
    return [_contraction_metrics(probe) for probe in probes]


def _probe_inventory_check(raw: dict[str, Any]) -> bool:
    probes = raw.get("probes")
    if not isinstance(probes, list) or len(probes) != 23:
        return False
    manifest = json.loads(PROBE_MANIFEST.read_text(encoding="utf-8"))
    labels = tuple(manifest["physical_probes"]["labels"])
    expected_physical = {(label, group) for label in labels for group in range(3)}
    observed_physical = {
        (item.get("label"), item.get("group"))
        for item in probes
        if isinstance(item, dict) and item.get("kind") == "physical"
    }
    if len(observed_physical) != 15 or observed_physical != expected_physical:
        return False
    expected_interface = set()
    seeds = manifest["fixed_probe_seeds"]
    for interface_index, (interface, group) in enumerate((("lower", 0), ("upper", 2))):
        for kind, field in (
            ("modal_combination", "modal_combinations"),
            ("complement", "complements"),
        ):
            for seed in seeds[field][interface]:
                expected_interface.add(
                    (
                        interface_index,
                        f"{interface}_{kind}_{int(seed)}",
                        group,
                        kind,
                        int(seed),
                    )
                )
    observed_interface = {
        (
            item.get("interface"),
            item.get("label"),
            item.get("group"),
            item.get("kind"),
            item.get("seed"),
        )
        for item in probes
        if isinstance(item, dict)
        and item.get("kind") in {"modal_combination", "complement"}
    }
    return len(observed_interface) == 8 and observed_interface == expected_interface


def _middle_cross_interface_check(raw: dict[str, Any]) -> bool:
    """Validate sampled middle-Schur evidence without reading FE vectors."""

    reports = raw.get("middle_cross_interface_sampled_response")
    if not isinstance(reports, list):
        return False
    manifest = json.loads(PROBE_MANIFEST.read_text(encoding="utf-8"))
    seeds = manifest["fixed_probe_seeds"]
    expected: list[tuple[str, str, str, int]] = []
    for interface in ("lower", "upper"):
        for kind, field in (
            ("modal_combination", "modal_combinations"),
            ("complement", "complements"),
        ):
            expected.extend(
                (interface, kind, f"middle_{interface}_{kind}_{int(seed)}", int(seed))
                for seed in seeds[field][interface]
            )
    if len(reports) != len(expected):
        return False
    identity = raw.get("middle_cross_interface_identity")
    groups = raw.get("groups")
    if not isinstance(identity, dict) or not isinstance(groups, list):
        return False
    complement_rows: dict[str, list[dict[str, Any]]] = {
        "lower": [],
        "upper": [],
    }
    for interface, group_index in (("lower", 0), ("upper", 2)):
        entry = identity.get(interface)
        if not isinstance(entry, dict):
            return False
        try:
            rows = [int(row) for row in entry["global_rows"]]
            size = int(entry["size"])
        except (KeyError, TypeError, ValueError):
            return False
        if (
            size != len(rows)
            or len(set(rows)) != size
            or hashlib.sha256(np.asarray(rows, dtype=np.int64).tobytes()).hexdigest()
            != entry.get("sha256")
            or group_index >= len(groups)
        ):
            return False
        layout = groups[group_index].get("gamma_layout", {})
        if layout.get("global_size") != size or layout.get(
            "gamma_rows_global_order_sha256"
        ) != entry.get("sha256"):
            return False
    observed = {
        (
            item.get("interface"),
            item.get("kind"),
            item.get("label"),
            item.get("seed"),
        )
        for item in reports
        if isinstance(item, dict)
    }
    if observed != set(expected):
        return False
    for item in reports:
        if not isinstance(item, dict) or any(
            key in item for key in ("source_values", "target_values", "vector")
        ):
            return False
        if not (
            item.get("group") == 1
            and item.get("source_group") == 1
            and item.get("response") == "middle_group1_schur"
            and item.get("direction") == "apply_group"
            and item.get("finite") is True
            and item.get("partition_disjoint") is True
            and item.get("partition_complete") is True
            and _finite(item.get("source_norm"))
            and _finite(item.get("middle_norm"))
            and _finite(item.get("same_interface_norm"))
            and _finite(item.get("cross_interface_norm"))
            and _finite(item.get("total_norm"))
            and _finite(item.get("cross_to_total"))
            and float(item["source_norm"]) > 0.0
            and float(item["middle_norm"]) > 0.0
        ):
            return False
        same_norm = float(item["same_interface_norm"])
        cross_norm = float(item["cross_interface_norm"])
        total_norm = float(item["total_norm"])
        if min(same_norm, cross_norm, total_norm) < 0.0:
            return False
        if not math.isclose(
            total_norm * total_norm,
            same_norm * same_norm + cross_norm * cross_norm,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        ):
            return False
        try:
            middle_squared = _norm2(
                item["contractions"]["middle_h_middle"],
                "middle response",
            )
        except (KeyError, TypeError, ValueError):
            return False
        if not math.isclose(
            middle_squared,
            total_norm * total_norm,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        ) or not math.isclose(
            float(item["middle_norm"]),
            total_norm,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        ):
            return False
        if not math.isclose(
            float(item["cross_to_total"]),
            cross_norm / total_norm if total_norm > 0.0 else 0.0,
            rel_tol=1.0e-10,
            abs_tol=1.0e-12,
        ):
            return False
        contractions = item.get("contractions")
        if not isinstance(contractions, dict):
            return False
        try:
            source_norm = _norm2(contractions["source_h_source"], "middle source")
            middle_norm = _norm2(contractions["middle_h_middle"], "middle response")
            _pair(contractions["source_h_middle"])
        except (KeyError, TypeError, ValueError):
            return False
        if source_norm <= 0.0 or middle_norm <= 0.0:
            return False
        if item.get("kind") == "complement":
            interface = str(item["interface"])
            entry = identity[interface]
            try:
                row_index = int(item["interface_row_index"])
                interface_size = int(item["interface_size"])
                selected_row = int(item["selected_active_row"])
            except (KeyError, TypeError, ValueError):
                return False
            if (
                interface_size != int(entry["size"])
                or not 0 <= row_index < interface_size
                or selected_row != int(entry["global_rows"][row_index])
                or item.get("interface_rows_global_order_sha256") != entry.get("sha256")
            ):
                return False
            complement_rows[interface].append(item)
    if len(complement_rows["lower"]) != len(complement_rows["upper"]):
        return False
    if any(
        int(lower["selected_active_row"]) == int(upper["selected_active_row"])
        for lower, upper in zip(
            complement_rows["lower"], complement_rows["upper"], strict=True
        )
    ):
        return False
    return True


def _incoming_neighbor_map_check(raw: dict[str, Any]) -> bool:
    incoming = raw.get("incoming_neighbor_map")
    return bool(
        isinstance(incoming, dict)
        and incoming.get("map") == "block_diagonal_neighbor_transmission"
        and incoming.get("response") == "apply_directed_neighbor"
        and incoming.get("probe_count") == 8
    )


def _resource_checks(
    raw: dict[str, Any], hard_limit_bytes: int = HARD_STOP_BYTES
) -> tuple[dict[str, Any], bool]:
    samples = raw.get("resource_samples")
    if not isinstance(samples, list) or not samples:
        return {"sample_count": 0, "readable": False}, False
    rss = [int(sample["rss_bytes"]) for sample in samples]
    swap = [int(sample["swap_bytes"]) for sample in samples]
    dedicated = [
        int(sample.get("dedicated_cgroup_swap_bytes", 0)) for sample in samples
    ]
    readable = all(sample.get("readable") is True for sample in samples)
    return (
        {
            "sample_count": len(samples),
            "peak_rss_bytes": max(rss),
            "peak_rss_gib": max(rss) / 2**30,
            "peak_swap_bytes": max(swap),
            "peak_dedicated_cgroup_swap_bytes": max(dedicated),
            "readable": readable,
            "hard_limit_bytes": hard_limit_bytes,
        },
        bool(
            readable
            and max(rss) < hard_limit_bytes
            and max(swap) == 0
            and max(dedicated) == 0
        ),
    )


def _identity_check(raw: dict[str, Any]) -> bool:
    manifest = json.loads(PROBE_MANIFEST.read_text(encoding="utf-8"))
    observed = raw.get("identity_observed")
    if not isinstance(observed, dict):
        return False
    identity = manifest["identity"]
    required = {
        "probe_manifest_sha256": FROZEN_PROBE_MANIFEST_SHA256,
        "input_sha256": identity["input_sha256"],
        "physical_model_sha256": identity["physical_model_sha256"],
        "selected_manifest_sha256": identity["selected_manifest_sha256"],
        "selected_identity_sha256": identity["selected_identity_sha256"],
        "selected_selection_sha256": identity["selected_selection_sha256"],
        "resolved_config_sha256": identity["exact_spool_resolved_config_sha256"],
        "spool_catalog_sha256": identity["exact_spool_catalog_sha256"],
        "upper_mode_key_sha256": (
            "089d6abfac9f482e7f6001988b9d1c12b1721c09a86749cdefcbfc4f22e82673"
        ),
        "upper_beta_sha256": (
            "aee266f602bf704ffbc3d7551be661b05e1663f84205012bfe26c8fd5983f6c9"
        ),
        "lower_mode_key_sha256": (
            "046afb0b3d3531f728dc958c1b0c8a321ffa51fb8a0e6ecf6834d462d5ab37e5"
        ),
        "lower_resolved_mode_metadata_sha256": (
            FROZEN_LOWER_RESOLVED_MODE_METADATA_SHA256
        ),
    }
    if any(observed.get(key) != value for key, value in required.items()):
        return False
    expected_outputs = manifest["physical_probes"]["exact_output_identity_sha256"]
    return observed.get("exact_output_identity_sha256") == expected_outputs


def _representation_check(raw: dict[str, Any]) -> bool:
    groups = raw.get("groups")
    lower = raw.get("lower", {})
    upper = raw.get("upper", {})
    expected_outputs = json.loads(PROBE_MANIFEST.read_text(encoding="utf-8"))[
        "physical_probes"
    ]["exact_output_identity_sha256"]
    if not isinstance(groups, list) or len(groups) != 3:
        return False
    return bool(
        _sha256(PROBE_MANIFEST) == FROZEN_PROBE_MANIFEST_SHA256
        and raw.get("probe_manifest_sha256") == FROZEN_PROBE_MANIFEST_SHA256
        and lower.get("mode_count") == 296
        and upper.get("mode_count") == 480
        and upper.get("qep_calls") == 0
        and upper.get("branch_authority") == "positive/forward"
        and [item.get("span_size") for item in groups] == list(EXPECTED_SPAN_SIZES)
        and raw.get("basis_global_replicated") is False
        and raw.get("fe_numeric_allgather") is False
        and all(
            item.get("gamma_layout", {}).get("basis_global_replicated") is False
            and item.get("gamma_layout", {}).get("fe_numeric_allgather") is False
            for item in groups
        )
        and set(raw.get("exact_output_identity_sha256", {})) == set(expected_outputs)
    )


def _v1_3_checks(raw: dict[str, Any]) -> dict[str, Any]:
    screen = raw.get("v1_3_screen")
    audit = raw.get("v1_3_one_apply")
    inventory = raw.get("v1_3_factor_inventory")
    if screen is None and audit is None and inventory is None:
        return {"not_run": True, "pass": True}
    inventory_ok = (
        isinstance(inventory, dict)
        and int(inventory.get("factor_count_ready", -1)) == 3
        and int(inventory.get("full_side_exact_factor_count", -1)) == 0
        and int(inventory.get("global_direct_factor_count", -1)) == 0
        and int(inventory.get("nested_ksp_count", -1)) == 0
    )
    if not isinstance(audit, dict) or not isinstance(screen, dict):
        return {
            "not_run": False,
            "inventory": inventory_ok,
            "raw": False,
            "pass": False,
        }

    scalar = audit.get("scalar_contractions")
    scalar_labels = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    )
    scalar_ok = False
    scalar_metrics: list[dict[str, Any]] = []
    if isinstance(scalar, dict) and scalar.get("labels") == list(scalar_labels):
        try:
            bhb = _matrix(scalar["BHB"])
            bhy = _matrix(scalar["BHY"])
            yhy = _matrix(scalar["YHY"])
            scalar_ok = bhb.shape == (5, 5) and bhy.shape == (5, 5)
            scalar_ok = scalar_ok and yhy.shape == (5, 5)
            if scalar_ok:
                for index, label in enumerate(scalar_labels):
                    b2 = float(np.real(bhb[index, index]))
                    y2 = float(np.real(yhy[index, index]))
                    by = complex(bhy[index, index])
                    scalar_ok = scalar_ok and b2 > 0.0 and y2 > 0.0
                    numerator = b2 - abs(by) ** 2 / y2
                    original_numerator = b2 + y2 - 2.0 * by.real
                    if numerator < -1.0e-10 * max(b2, abs(by) ** 2 / y2, 1.0):
                        scalar_ok = False
                    if original_numerator < -1.0e-10 * max(b2, y2, 2.0 * abs(by), 1.0):
                        scalar_ok = False
                    # The producer stores BHY as y^H b; alpha*=BHY/YHY.
                    alpha = by / y2
                    scalar_metrics.append(
                        {
                            "label": label,
                            "alpha": _pair_out(alpha),
                            "alpha_magnitude": float(abs(alpha)),
                            "alpha_phase_radians": float(np.angle(alpha)),
                            "rho_star": math.sqrt(max(numerator, 0.0) / b2),
                            "original_rho": math.sqrt(
                                max(original_numerator, 0.0) / b2
                            ),
                            "correlation": _pair_out(by / math.sqrt(b2 * y2)),
                        }
                    )
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            scalar_ok = False
    reports = audit.get("reports", [])
    frozen_labels = (
        "physical_side_rhs",
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    )
    report_finite = bool(
        [item.get("label") for item in reports if isinstance(item, dict)]
        == list(frozen_labels)
        and reports
        and reports[0].get("finite") is True
        and _finite(reports[0].get("source_norm"))
        and _finite(reports[0].get("output_norm"))
        and float(reports[0].get("source_norm")) <= 1.0e-13
        and float(reports[0].get("output_norm")) <= 1.0e-13
        and all(
            isinstance(item, dict)
            and _finite(item.get("true_residual_relative"))
            and _finite(item.get("repeat_error"))
            and item.get("finite") is True
            for item in reports[1:]
        )
    )
    zero_ok = bool(
        reports
        and reports[0].get("label") == "physical_side_rhs"
        and reports[0].get("physical_zero") is True
        and _finite(reports[0].get("output_norm"))
        and float(reports[0].get("output_norm")) <= 1.0e-13
    )
    repeat_ok = bool(
        reports and all(float(item["repeat_error"]) <= 1.0e-10 for item in reports)
    )
    linearity = audit.get("gate", {}).get("linearity_relative_error")
    linearity_ok = _finite(linearity) and float(linearity) <= 1.0e-10

    labels = tuple(screen.get("labels", ()))
    phase1 = screen.get("phase1", {})
    phase2 = screen.get("phase2", {})

    def phase_contract(phase_records: Any, *, max_it: int, include_32: bool) -> bool:
        expected = {"0", "4", "8", "16"}
        if include_32:
            expected.add("32")
        if not isinstance(phase_records, dict) or set(phase_records) != set(
            scalar_labels
        ):
            return False
        for label in scalar_labels:
            record = phase_records.get(label)
            checkpoints = (
                record.get("checkpoints") if isinstance(record, dict) else None
            )
            if (
                not isinstance(record, dict)
                or not isinstance(checkpoints, dict)
                or set(checkpoints) != expected
                or record.get("restart") != 32
                or record.get("max_it") != max_it
                or record.get("zero_initial_guess") is not True
                or record.get("zero_initial_guess_count") != 1
                or record.get("shared_ksp") is not True
                or record.get("pc_side") != "right"
                or record.get("ksp_breakdown") is not False
                or record.get("true_residual_matvec_count") != len(expected) - 1
            ):
                return False
            initial = checkpoints["0"]
            if (
                not isinstance(initial, dict)
                or initial.get("finite") is not True
                or not math.isclose(
                    float(initial.get("reported_relative_residual")),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
                or not math.isclose(
                    float(initial.get("true_residual_relative")),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ):
                return False
            if not all(
                checkpoints[key].get("finite") is True
                and _finite(checkpoints[key].get("true_residual_relative"))
                for key in expected
                if key != "0"
            ):
                return False
        return True

    screen_contract = bool(
        isinstance(screen, dict)
        and screen.get("schema") == "task040.v1_1.right_fgmres_batch.v1"
        and labels == scalar_labels
    )
    phase1_ok = bool(
        screen_contract and phase_contract(phase1, max_it=16, include_32=False)
    )
    r8 = (
        [
            float(phase1[label]["checkpoints"]["8"]["true_residual_relative"])
            for label in labels
        ]
        if phase1_ok
        else []
    )
    r16 = (
        [
            float(phase1[label]["checkpoints"]["16"]["true_residual_relative"])
            for label in labels
        ]
        if phase1_ok
        else []
    )
    trend_ok = bool(r8 and r16) and all(
        r16_item <= r8_item * 10.0 ** (-0.25)
        for r8_item, r16_item in zip(r8, r16, strict=True)
    )
    all_five_r16_ge_0p9 = bool(r16) and all(item >= 0.9 for item in r16)
    boundary = screen.get("resource_at_phase_boundary", {})
    boundary_ok = bool(
        isinstance(boundary, dict)
        and _finite(boundary.get("rss_bytes"))
        and int(boundary.get("rss_bytes")) < HARD_STOP_BYTES
        and int(boundary.get("swap_bytes", -1)) == 0
        and boundary.get("all_status_readable") is True
    )
    first_pass = None
    for checkpoint in ("4", "8", "16"):
        values = (
            [
                float(
                    phase1[label]["checkpoints"][checkpoint]["true_residual_relative"]
                )
                for label in labels
            ]
            if phase1_ok
            else []
        )
        if (
            values
            and all(value <= 1.0e-2 for value in values)
            and all(values[index] <= 1.0e-3 for index in range(min(3, len(values))))
        ):
            first_pass = int(checkpoint)
            break
    phase1_frozen_gate = first_pass is not None
    authorized = bool(
        phase1_ok
        and trend_ok
        and boundary_ok
        and not all_five_r16_ge_0p9
        and not phase1_frozen_gate
    )
    phase2_ok = (not authorized and not phase2) or (
        authorized and phase_contract(phase2, max_it=32, include_32=True)
    )
    setup_ok = bool(
        screen.get("ksp_setup_count") == 1
        and screen.get("ksp_destroy_count") == 1
        and screen.get("ksp_destroyed") is True
        and screen.get("single_right_pc_setup") is True
        and screen.get("zero_initial_guess_all_rhs") is True
    )
    reported_authorized = screen.get("conditional_32_authorized")
    authorization_ok = bool(
        screen.get("stop_on_frozen_gate") is True
        and screen.get("phase1_frozen_gate") == phase1_frozen_gate
        and isinstance(reported_authorized, bool)
        and reported_authorized == authorized
    )
    factor_owner = (
        raw.get("lifecycle", {}).get("worker_cleanup", {}).get("factor_owner")
    )
    lifecycle_ok = bool(
        isinstance(factor_owner, dict)
        and factor_owner.get("ready", {}).get("factor_count_ready") == 3
        and factor_owner.get("ready", {}).get("auxiliary_owner_count") == 3
        and factor_owner.get("after", {}).get("factor_count_after_cleanup") == 0
        and factor_owner.get("after", {}).get("auxiliary_owner_count") == 0
        and factor_owner.get("after", {}).get("destroyed") is True
    )
    phase2_pass = False
    if authorized and phase2_ok:
        values = [
            float(phase2[label]["checkpoints"]["32"]["true_residual_relative"])
            for label in labels
        ]
        phase2_pass = all(value <= 1.0e-2 for value in values) and all(
            values[index] <= 1.0e-3 for index in range(min(3, len(values)))
        )
    phase1_apply_count = (
        sum(int(phase1[label].get("right_pc_apply_count", -1)) for label in labels)
        if phase1_ok
        else -1
    )
    phase2_apply_count = (
        sum(int(phase2[label].get("right_pc_apply_count", -1)) for label in labels)
        if authorized and phase2_ok
        else 0
    )
    reported_apply_count = audit.get("action_apply_count_delta")
    apply_count_ok = bool(
        audit.get("formal_source_apply_count") == 6
        and audit.get("repeat_audit_apply_count") == 6
        and audit.get("linearity_audit_apply_count") == 1
        and reported_apply_count == 13
        and phase1_apply_count + phase2_apply_count > 0
        and screen.get("right_pc_apply_count")
        == phase1_apply_count + phase2_apply_count
    )
    evidence_valid = bool(
        inventory_ok
        and boundary_ok
        and report_finite
        and zero_ok
        and repeat_ok
        and linearity_ok
        and scalar_ok
        and screen_contract
        and phase1_ok
        and phase2_ok
        and setup_ok
        and authorization_ok
        and lifecycle_ok
        and apply_count_ok
    )
    numerical_pass = bool(first_pass is not None or phase2_pass)
    classification = (
        "PROJECTED_EXACT_TRANSMISSION_PASS"
        if evidence_valid and numerical_pass
        else "THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT"
        if evidence_valid
        else "IMPLEMENTATION_OR_RESOURCE_FAILURE"
    )
    return {
        "not_run": False,
        "inventory": inventory_ok,
        "scalar_contractions": scalar_ok,
        "reports": report_finite,
        "zero_map": zero_ok,
        "repeat": repeat_ok,
        "linearity": linearity_ok,
        "phase1": phase1_ok,
        "screen_contract": screen_contract,
        "phase1_trend": trend_ok,
        "all_five_r16_ge_0p9": all_five_r16_ge_0p9,
        "resource_boundary": boundary_ok,
        "conditional_32_authorized": authorized,
        "authorization_contract": authorization_ok,
        "phase2": phase2_ok,
        "setup_lifecycle": setup_ok,
        "factor_lifecycle": lifecycle_ok,
        "apply_counts": apply_count_ok,
        "phase1_frozen_gate": phase1_frozen_gate,
        "first_pass_checkpoint": first_pass,
        "classification": classification,
        "scalar_metrics": scalar_metrics,
        "evidence_valid": evidence_valid,
        "numerical_pass": numerical_pass,
        "pass": bool(inventory_ok and evidence_valid and numerical_pass),
    }


def recompute_v1_2_small_contractions(raw: dict[str, Any]) -> dict[str, Any]:
    """Recompute V1-2 metrics from contractions, not worker gate fields."""

    groups = _group_metrics(raw)
    probes = _probe_metrics(raw)
    factor = raw.get("factor_inventory", {})
    lifecycle = raw.get("lifecycle", {})
    factor_pass = (
        factor.get("ready") == 3
        and factor.get("after") == 0
        and factor.get("simultaneous_max") == 3
        and factor.get("full_side") == 0
        and factor.get("global_direct") == 0
        and factor.get("nested_ksp") == 0
    )
    resource, resource_pass = _resource_checks(raw)
    lifecycle_pass = bool(
        lifecycle.get("exact_factor_count_ready") == 3
        and lifecycle.get("exact_factor_count_after_cleanup") == 0
        and raw.get("exact_oracle_after_cleanup", {}).get("destroyed") is True
    )
    physical_labels = {item["label"] for item in probes if item["kind"] == "physical"}
    expected_labels = {
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    }
    probe_finite = all(
        all(
            _finite(item[key])
            for key in (
                "alpha_magnitude",
                "alpha_phase_radians",
                "original_scalar_exact_relative",
                "rho_star",
                "correlation_magnitude",
                "projected_exact_relative",
            )
        )
        and (
            item["complement_orthogonality"] is None
            or _finite(item["complement_orthogonality"])
        )
        for item in probes
    )
    complements = [item for item in probes if item["kind"] == "complement"]
    complement_pass = bool(complements) and all(
        item["complement_orthogonality"] <= COMPLEMENT_ORTHOGONALITY_LIMIT
        for item in complements
    )
    v1_3 = _v1_3_checks(raw)
    v1_2_checks = {
        "identity": _identity_check(raw),
        "representation": _representation_check(raw),
        "finite": probe_finite,
        "physical_labels": physical_labels == expected_labels,
        "probe_inventory": _probe_inventory_check(raw),
        "gram_full_rank": all(
            item["gram_rank"] == item["span_size"] for item in groups
        ),
        "complement_projection": complement_pass,
        "factor_inventory": factor_pass,
        "lifecycle": lifecycle_pass,
        "resource": resource_pass,
        "incoming_neighbor_map": _incoming_neighbor_map_check(raw),
        "middle_cross_interface": _middle_cross_interface_check(raw),
        "span_shapes": all(
            item["group"] in range(3)
            and item["span_size"] == EXPECTED_SPAN_SIZES[item["group"]]
            and item["declared_span_size"] == EXPECTED_SPAN_SIZES[item["group"]]
            and item["matrix_shapes"]["gram"]
            == [EXPECTED_SPAN_SIZES[item["group"]]] * 2
            and item["matrix_shapes"]["scalar"]
            == [EXPECTED_SPAN_SIZES[item["group"]]] * 2
            and item["matrix_shapes"]["exact"]
            == [EXPECTED_SPAN_SIZES[item["group"]]] * 2
            for item in groups
        ),
    }
    v1_2_gate_pass = bool(all(v1_2_checks.values()))
    v1_3_present = any(
        raw.get(field) is not None
        for field in ("v1_3_one_apply", "v1_3_screen", "v1_3_factor_inventory")
    )
    decision_tree_contract = bool(v1_2_gate_pass == v1_3_present)
    overall_numerical_gate = bool(
        v1_2_gate_pass
        and v1_3_present
        and decision_tree_contract
        and v1_3.get("pass", False)
    )
    if not decision_tree_contract:
        classification = "IMPLEMENTATION_OR_RESOURCE_FAILURE"
    elif not v1_2_gate_pass:
        classification = "V1_2_INTERFACE_GATE_FAILED_V1_3_NOT_RUN"
    else:
        classification = v1_3.get(
            "classification", "IMPLEMENTATION_OR_RESOURCE_FAILURE"
        )
    checks = {
        **v1_2_checks,
        "v1_2_gate": v1_2_gate_pass,
        "decision_tree_contract": decision_tree_contract,
        "v1_3": bool(v1_3.get("pass", False)) if v1_3_present else True,
    }
    return {
        "schema": "task040.v1_2.interface_schur.recomputed.v2",
        "groups": groups,
        "probes": probes,
        "resource": resource,
        "complement_orthogonality_limit": COMPLEMENT_ORTHOGONALITY_LIMIT,
        "v1_3": v1_3,
        "v1_2_gate_pass": v1_2_gate_pass,
        "v1_3_present": v1_3_present,
        "decision_tree_contract": decision_tree_contract,
        "classification": classification,
        "checks": checks,
        "gate_pass": overall_numerical_gate,
    }


def recompute_v1_2_gate(run_root: str | Path) -> dict[str, Any]:
    """Read worker/watchdog raw fields and independently classify Run B."""

    root = Path(run_root)
    worker_path = root / "worker" / "run_summary.json"
    watchdog_path = root / "watchdog_summary.json"
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    raw = dict(worker.get("interface_schur_raw", {}))
    samples = []
    for line in (
        (root / "process_tree_samples.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        authority = row.get("resource_authority", {})
        process_tree = authority.get("process_tree", {})
        cgroup = authority.get("job_cgroup", {})
        dedicated = cgroup.get("swap_current_bytes")
        samples.append(
            {
                "rss_bytes": int(row["rss_bytes"]),
                "swap_bytes": int(row["swap_bytes"]),
                "dedicated_cgroup_swap_bytes": int(dedicated or 0),
                "readable": bool(process_tree.get("all_status_readable")),
            }
        )
    raw["resource_samples"] = samples
    derived = recompute_v1_2_small_contractions(raw)
    resource = derived["resource"]
    watchdog_pass = (
        watchdog.get("source_sha") == worker.get("source_sha")
        and watchdog.get("return_code") == 0
        and watchdog.get("termination_reason") == "natural_exit"
        and watchdog.get("run_summary_present") is True
        and watchdog.get("all_status_readable") is True
        and watchdog.get("hard_stop_bytes") == HARD_STOP_BYTES
        and watchdog.get("peak_swap_bytes") == 0
        and watchdog.get("peak_dedicated_cgroup_swap_bytes") == 0
        and watchdog.get("run_summary_sha256") == _sha256(worker_path)
        and resource.get("peak_rss_bytes") == watchdog.get("peak_rss_bytes")
        and resource.get("peak_swap_bytes") == watchdog.get("peak_swap_bytes")
        and resource.get("peak_dedicated_cgroup_swap_bytes")
        == watchdog.get("peak_dedicated_cgroup_swap_bytes")
    )
    derived["checks"]["watchdog"] = watchdog_pass
    if not watchdog_pass:
        derived["classification"] = "IMPLEMENTATION_OR_RESOURCE_FAILURE"
        derived["gate_pass"] = False
    else:
        derived["gate_pass"] = all(derived["checks"].values())
    derived["raw_hashes"] = {
        "worker": _sha256(worker_path),
        "watchdog": _sha256(watchdog_path),
        "samples": _sha256(root / "process_tree_samples.jsonl"),
    }
    return derived


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(recompute_v1_2_gate(args.run_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
