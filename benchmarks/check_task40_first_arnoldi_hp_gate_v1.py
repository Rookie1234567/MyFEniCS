"""Independent offline checker for the Task40 first-Arnoldi H_p comparison."""

import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path

import numpy as np


SCHEMA = "task40extra.first-arnoldi-hp-gate-check.v1"
LIMIT = 1.0e-10


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_sha256(value):
    payload = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _complex_value(value):
    if isinstance(value, dict):
        return complex(float(value["real"]), float(value["imag"]))
    return complex(value)


def _verify_mode_orthogonality(modes, period_x, period_y):
    """Verify reciprocal-lattice spacing and same-order E_t orthogonality."""

    maximum_overlap = 0.0
    seen = set()
    for index, mode in enumerate(modes):
        if mode.get("mode_index") != index:
            raise ValueError("mode order identity mismatch")
        key = (mode.get("side"), mode.get("m"), mode.get("n"), mode.get("polarization"))
        if key in seen:
            raise ValueError("duplicate mode identity in ordered manifest")
        seen.add(key)
    for first_index, first in enumerate(modes):
        for second in modes[first_index + 1 :]:
            if first["side"] != second["side"]:
                continue
            delta_m = int(second["m"]) - int(first["m"])
            delta_n = int(second["n"]) - int(first["n"])
            delta_alpha = (
                _complex_value(second["alpha"]) - _complex_value(first["alpha"])
            ) * period_x / (2.0 * math.pi)
            delta_gamma = (
                _complex_value(second["gamma"]) - _complex_value(first["gamma"])
            ) * period_y / (2.0 * math.pi)
            if (
                abs(delta_alpha - delta_m) > 1.0e-10
                or abs(delta_gamma - delta_n) > 1.0e-10
            ):
                raise ValueError("mode order is inconsistent with the Floquet lattice")
            if delta_m != 0 or delta_n != 0:
                continue
            first_e = np.asarray(
                [_complex_value(value) for value in first["e_vector"][:2]],
                dtype=np.complex128,
            )
            second_e = np.asarray(
                [_complex_value(value) for value in second["e_vector"][:2]],
                dtype=np.complex128,
            )
            denominator = float(np.linalg.norm(first_e) * np.linalg.norm(second_e))
            overlap = abs(np.vdot(first_e, second_e)) / max(
                denominator, np.finfo(float).tiny
            )
            maximum_overlap = max(maximum_overlap, float(overlap))
            if not np.isfinite(overlap) or overlap > 1.0e-12:
                raise ValueError("same-order tangential polarizations are not orthogonal")
    return maximum_overlap


def check_saved_pair(packet_path, mode_manifest_path, resolved_config_path):
    """Read saved vectors and identities, then independently recompute the gate."""

    packet_path = Path(packet_path)
    manifest_path = Path(mode_manifest_path)
    config_path = Path(resolved_config_path)
    packet = json.loads(packet_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    config = json.loads(config_path.read_text())
    modes = manifest.get("modes")
    if not isinstance(modes, list) or manifest.get("mode_count") != len(modes):
        raise ValueError("ordered mode manifest count is invalid")

    mode_sha = _canonical_sha256(manifest)
    expected_mode_sha = packet.get("identity", {}).get("ordered_mode_sha256")
    if mode_sha != expected_mode_sha:
        raise ValueError("packet and ordered mode manifest hash mismatch")

    arrays_facts = packet.get("arrays", {})
    arrays_path = Path(arrays_facts.get("path", ""))
    if not arrays_path.is_file() or _sha256(arrays_path) != arrays_facts.get("sha256"):
        raise ValueError("saved first-Arnoldi array file is missing or hash-mismatched")

    derived = config["derived"]
    bounds = derived["physical_bounds"]
    period_x = float(bounds["x_max"] - bounds["x_min"])
    period_y = float(bounds["y_max"] - bounds["y_min"])
    area = period_x * period_y
    if not np.isfinite(area) or area <= 0.0:
        raise ValueError("resolved port area is invalid")

    normalization_h = np.empty(len(modes), dtype=np.float64)
    maximum_h_relative_disagreement = 0.0
    for index, mode in enumerate(modes):
        if mode.get("mode_index") != index:
            raise ValueError("mode order identity mismatch")
        side = mode.get("side")
        if side not in {"top", "bottom"}:
            raise ValueError("mode side identity is invalid")
        z_boundary = float(
            derived["domain_z_max" if side == "top" else "domain_z_min"]
        )
        kz = _complex_value(mode["k_vector"][2])
        phase = cmath.exp(1j * kz * z_boundary)
        e_t = np.asarray(
            [_complex_value(value) for value in mode["e_vector"][:2]],
            dtype=np.complex128,
        )
        computed_e_t_norm_sq = float(np.vdot(e_t, e_t).real)
        recorded_e_t_norm_sq = float(mode["electric_tangential_norm_sq"])
        if (
            not np.isfinite(computed_e_t_norm_sq)
            or computed_e_t_norm_sq <= 0.0
            or not math.isclose(
                computed_e_t_norm_sq,
                recorded_e_t_norm_sq,
                rel_tol=5.0e-14,
                abs_tol=0.0,
            )
        ):
            raise ValueError("mode tangential norm does not match its saved E_t vector")
        recomputed_h = area * computed_e_t_norm_sq * abs(phase) ** 2
        recorded_h = float(mode["projection_denominator"])
        if (
            not np.isfinite(recomputed_h)
            or recomputed_h <= 0.0
            or not math.isclose(recomputed_h, recorded_h, rel_tol=5.0e-14, abs_tol=0.0)
        ):
            raise ValueError("mode H does not match the recomputed tangential surface norm")
        normalization_h[index] = recomputed_h
        maximum_h_relative_disagreement = max(
            maximum_h_relative_disagreement,
            abs(recomputed_h - recorded_h) / recorded_h,
        )

    maximum_polarization_overlap = _verify_mode_orthogonality(
        modes, period_x, period_y
    )
    identity = packet.get("identity", {})
    space_facts = identity.get("expected_space_facts", {})
    active_rows = int(space_facts.get("active_rows", 0))
    appended_rows = int(space_facts.get("appended_rows", -1))
    if appended_rows != len(modes) or active_rows <= 0:
        raise ValueError("saved FE/port partition identity is invalid")

    pair = packet.get("pair", {})
    expected_pair_names = {
        "candidate_a6_candidate_h6",
        "candidate_a6_native_h6",
        "native_a6_candidate_h6",
        "native_a6_native_h6",
    }
    if set(pair) != expected_pair_names:
        raise ValueError("saved first-Arnoldi pair does not contain all four required variants")
    reference_record = pair.get("candidate_a6_candidate_h6")
    if not isinstance(reference_record, dict):
        raise ValueError("saved candidate/candidate reference vector is missing")
    tiny = np.finfo(float).tiny
    h_sqrt = np.sqrt(normalization_h)
    comparisons = {}
    with np.load(arrays_path, allow_pickle=False) as arrays:
        reference = np.asarray(arrays[reference_record["array_key"]])
        expected_size = active_rows + appended_rows
        if reference.shape != (expected_size,) or not np.isfinite(reference).all():
            raise ValueError("saved candidate/candidate vector has an invalid shape or value")
        for name, record in pair.items():
            candidate = np.asarray(arrays[record["array_key"]])
            if (
                candidate.shape != (expected_size,)
                or record.get("shape") != [expected_size]
                or record.get("dtype") != str(candidate.dtype)
                or not np.isfinite(candidate).all()
            ):
                raise ValueError(f"saved first-Arnoldi vector identity is invalid: {name}")
            difference = candidate - reference
            fe_delta = difference[:active_rows]
            port_delta = difference[active_rows:]
            fe_reference = reference[:active_rows]
            port_reference = reference[active_rows:]
            weighted_port_delta = h_sqrt * port_delta
            weighted_port_reference = h_sqrt * port_reference
            raw_relative = float(np.linalg.norm(difference)) / max(
                float(np.linalg.norm(reference)), tiny
            )
            fe_relative = float(np.linalg.norm(fe_delta)) / max(
                float(np.linalg.norm(fe_reference)), tiny
            )
            port_gram_relative = float(np.linalg.norm(weighted_port_delta)) / max(
                float(np.linalg.norm(weighted_port_reference)), tiny
            )
            joint_relative = float(
                np.hypot(
                    np.linalg.norm(fe_delta), np.linalg.norm(weighted_port_delta)
                )
            ) / max(
                float(
                    np.hypot(
                        np.linalg.norm(fe_reference),
                        np.linalg.norm(weighted_port_reference),
                    )
                ),
                tiny,
            )
            raw_passed = bool(np.isfinite(raw_relative) and raw_relative <= LIMIT)
            raw_record = packet.get("pair_summary", {}).get(
                "comparisons_to_candidate_combination", {}
            ).get(name)
            if not isinstance(raw_record, dict):
                raise ValueError(f"saved raw comparison record is missing: {name}")
            if "raw_passed" in raw_record or "raw_limit" in raw_record:
                if not {
                    "raw_passed",
                    "raw_limit",
                    "raw_relative_to_combination",
                }.issubset(raw_record):
                    raise ValueError(
                        f"saved explicit raw comparison fields are incomplete: {name}"
                    )
                recorded_relative = float(raw_record["raw_relative_to_combination"])
                recorded_limit = float(raw_record["raw_limit"])
                recorded_passed = bool(raw_record["raw_passed"])
                raw_record_contract = "explicit_raw_fields"
            else:
                if not {
                    "relative_to_combination",
                    "limit",
                    "passed",
                }.issubset(raw_record):
                    raise ValueError(f"saved raw comparison fields are missing: {name}")
                recorded_relative = float(raw_record["relative_to_combination"])
                recorded_limit = float(raw_record["limit"])
                recorded_passed = bool(raw_record["passed"])
                raw_record_contract = "legacy_unweighted_euclidean_fields"
            raw_record_consistent = bool(
                math.isclose(
                    recorded_relative,
                    raw_relative,
                    rel_tol=5.0e-14,
                    abs_tol=0.0,
                )
                and recorded_limit == LIMIT
                and recorded_passed == raw_passed
            )
            if not raw_record_consistent:
                raise ValueError(f"saved raw comparison record disagrees with vectors: {name}")
            fe_passed = bool(np.isfinite(fe_relative) and fe_relative <= LIMIT)
            port_passed = bool(
                np.isfinite(port_gram_relative) and port_gram_relative <= LIMIT
            )
            comparisons[name] = {
                "raw_relative_to_combination": raw_relative,
                "raw_abs_norm_diagnostic": float(np.linalg.norm(difference)),
                "raw_limit": LIMIT,
                "raw_passed": raw_passed,
                "raw_record_consistent": raw_record_consistent,
                "raw_record_contract": raw_record_contract,
                "fixed_basis_trace_coefficient_relative": fe_relative,
                "fixed_basis_trace_coefficient_abs_norm": float(
                    np.linalg.norm(fe_delta)
                ),
                "port_modal_gram_relative": port_gram_relative,
                "port_modal_gram_abs_norm": float(
                    np.linalg.norm(weighted_port_delta)
                ),
                "port_unweighted_relative_diagnostic": (
                    float(np.linalg.norm(port_delta))
                    / max(float(np.linalg.norm(port_reference)), tiny)
                ),
                "port_unweighted_abs_norm_diagnostic": float(
                    np.linalg.norm(port_delta)
                ),
                "joint_mixed_metric_relative_diagnostic": joint_relative,
                "fe_passed": fe_passed,
                "port_passed": port_passed,
                "passed": bool(fe_passed and port_passed),
            }

    packed_h = np.ascontiguousarray(normalization_h, dtype="<f8").tobytes()
    passed = bool(comparisons) and all(v["passed"] for v in comparisons.values())
    raw_passed = bool(comparisons) and all(
        v["raw_passed"] for v in comparisons.values()
    )
    if passed and not raw_passed:
        classification = "TASK40_COMPONENT_METRIC_PASS_WITH_RAW_EUCLIDEAN_NEGATIVE"
    elif passed:
        classification = "TASK40_COMPONENT_METRIC_PASS"
    else:
        classification = "TASK40_COMPONENT_METRIC_NEGATIVE"
    return {
        "schema": SCHEMA,
        "classification": classification,
        "passed": passed,
        "raw_euclidean_all_passed": raw_passed,
        "identity": {
            "packet_sha256": _sha256(packet_path),
            "mode_manifest_file_sha256": _sha256(manifest_path),
            "ordered_mode_sha256": mode_sha,
            "normalization_h_sha256": hashlib.sha256(packed_h).hexdigest(),
            "npz_sha256": _sha256(arrays_path),
            "resolved_config_sha256": _sha256(config_path),
            "source_sha": identity.get("source_sha"),
        },
        "partition": {
            "active_rows": active_rows,
            "appended_rows": appended_rows,
        },
        "port_metric_definition": (
            "H_i=area*|E_t,i|^2*|exp(i*kz_i*z_boundary)|^2; diagonal modal "
            "Gram for full-period Floquet orders and orthogonal same-order E_t; "
            "top and bottom port supports are disjoint"
        ),
        "basis_rescaling_invariance": (
            "Phi_i'=s_i*Phi_i, alpha_i'=alpha_i/s_i, H_i'=|s_i|^2*H_i "
            "leaves sqrt(H_i)*|alpha_i| unchanged"
        ),
        "fe_metric_definition": (
            "Euclidean norm of independent FE trace coefficients in the fixed "
            "native basis; this is not a full-field error"
        ),
        "source_basis": [
            "src/solvers/dtn_port_3d.py::_mode_boundary_phase and _mode_projection_denominator",
            "src/solvers/fullspace_dtn_action.py::build_ordered_mode_manifest",
            "src/solvers/p6_cell_condensed_action.py::build_p6_cell_condensed_action_from_carrier",
            "src/common/modes_3d.py::polarization_basis_3d and outgoing_port_modes_3d",
        ],
        "orthogonality": {
            "different_floquet_orders": "verified_reciprocal_lattice_spacing",
            "same_order_max_normalized_tangential_overlap": (
                maximum_polarization_overlap
            ),
            "different_port_sides": "disjoint_support",
        },
        "max_h_relative_disagreement": maximum_h_relative_disagreement,
        "limit": LIMIT,
        "comparisons": comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("mode_manifest", type=Path)
    parser.add_argument("resolved_config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_saved_pair(args.packet, args.mode_manifest, args.resolved_config)
    rendered = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
