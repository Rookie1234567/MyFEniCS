"""Independent compact conclusions from retained raw diagnostic vectors/scalars.

No solver/factor/network imports; only NumPy and immutable artifact reads.
"""

import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "benchmarks/artifacts/task42extra").exists() is False:
    ROOT = Path.cwd()
ART = ROOT / "benchmarks/artifacts/task42extra"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(x, y, tol=1e-8, scale=None):
    scale = max(abs(x), abs(y), np.finfo(float).tiny) if scale is None else scale
    require(abs(x - y) <= tol * scale, "RAW_NUMERICAL_RECORD_MISMATCH")


def quadratic(x, wx):
    value = np.vdot(x, wx)
    require(np.isfinite(value), "NONFINITE_RAW_QUADRATIC")
    return float(value.real)


def load(stage):
    index = json.loads((ART / ("index_" + stage + ".json")).read_text())
    for entry in index["files"].values():
        path = Path(entry["path"])
        require(path.resolve().is_relative_to(ART.resolve()), "ARTIFACT_PATH")
        require(
            hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"],
            "ARTIFACT_HASH",
        )
    return index


def verify_B(result, raw):
    dref = quadratic(raw["c_ref"], raw["Gref"])
    dG = quadratic(raw["f"], raw["qf"])
    same(result["d_ref"], dref)
    same(result["d_G"], dG)
    worst = 0.0
    for name, row in result["rows"].items():
        e, Ge, r, qr = [raw[name + "_" + k] for k in ("e", "Ge", "r", "qr")]
        defect = np.linalg.norm(raw[name + "_Ae"] - (r - raw["r_ref"])) / (
            np.linalg.norm(raw[name + "_Ae"])
            + np.linalg.norm(r)
            + np.linalg.norm(raw["r_ref"])
        )
        require(defect <= 1e-10, "RAW_ERROR_RESIDUAL_IDENTITY")
        same(row["E_G"], np.sqrt(quadratic(e, Ge) / dref))
        same(row["dual_loss"], quadratic(r, qr) / (2 * dG))
        same(row["native_relative"], np.linalg.norm(r) / np.linalg.norm(raw["f"]))
        worst = max(worst, defect)
    step_checks = []
    for step in result["steps"]:
        before, nxt = step["start"], step["end"]
        e, Ge, r, qr = [raw[before + "_" + k] for k in ("e", "Ge", "r", "qr")]
        d, Gd, Ad, qd = [
            raw[nxt + "_" + k] for k in ("delta", "Gdelta", "Adelta", "qdelta")
        ]
        for key, a, wa, b, wb in [("field", e, Ge, d, Gd), ("residual", r, qr, Ad, qd)]:
            cross = 2 * np.vdot(a, wb).real
            update = quadratic(b, wb)
            actual = quadratic(a + b, wa + wb) - quadratic(a, wa)
            s = step[key]["operation_scale"]
            same(step[key]["cross"], cross, scale=s)
            same(step[key]["update_energy"], update, scale=s)
            same(step[key]["change"], actual, scale=s)
            same(actual, cross + update, scale=s)
        same(
            step["ared"],
            -step["residual"]["change"] / (2 * dG),
            scale=max(abs(step["ared"]), result["rows"][before]["dual_loss"]),
        )
        require(
            step["pred"] > 0 and step["ared"] > 0 and step["eta"] > 0,
            "HISTORICAL_ACCEPTANCE_NOT_RETAINED",
        )
        step_checks.append(
            dict(
                start=before,
                end=nxt,
                field_change=step["field"]["change"],
                loss_change=step["residual"]["change"] / (2 * dG),
                eta=step["eta"],
            )
        )
    H = raw["direction_AX"] @ raw["small_T"]
    WH = raw["direction_qAX"] @ raw["small_T"]
    small = H.conj().T @ WH
    small = (small + small.conj().T) / 2
    same(
        float(np.linalg.norm(small - raw["small_image_H"])),
        0,
        scale=max(np.linalg.norm(small), 1e-14),
    )
    ev = np.linalg.eigvalsh(small)
    require(
        np.allclose(
            ev,
            result["finite_field_subspace"]["image_energy_eigenvalues"],
            rtol=1e-8,
            atol=1e-12,
        ),
        "SMALL_OBSERVED_SPECTRUM",
    )
    require(
        all(
            result["actions"][k] <= cap
            for k, cap in dict(A=64, AH=64, Gsolve=128, G_matvec=256).items()
        ),
        "B_OPERATION_CAP",
    )
    return dict(
        identity_worst=worst,
        steps=step_checks,
        effective_rank=len(ev),
        no_global_condition_claim=True,
    )


def raw_change(old, delta, weighted_old, weighted_delta):
    """Recompute every signed term; never use producer values as a scale."""
    before = quadratic(old, weighted_old)
    after = quadratic(old + delta, weighted_old + weighted_delta)
    cross = float(2 * np.vdot(old, weighted_delta).real)
    update = quadratic(delta, weighted_delta)
    require(min(before, after, update) >= 0, "NEGATIVE_SAVED_ENERGY")
    scale = max(before, after, abs(cross) + update, np.finfo(float).tiny)
    change = after - before
    same(change, cross + update, scale=scale)
    return dict(
        before=before,
        after=after,
        cross=cross,
        update_energy=update,
        change=change,
        reconstructed_change=cross + update,
        operation_scale=scale,
        defect=abs(change - cross - update) / scale,
        # No epsilon/ridge or clipping of signed energy removal.
        removed_energy_fraction=(before - after) / before if before > 0 else None,
        near_zero_before=before <= 1e-24 * scale,
        absolute_energy_removed=before - after,
    )


def paired_change(record, actual):
    for key in (
        "before",
        "after",
        "cross",
        "update_energy",
        "change",
        "reconstructed_change",
        "operation_scale",
    ):
        same(record[key], actual[key], scale=actual["operation_scale"])
    same(record["defect"], actual["defect"], scale=1.0)


def verify_C(result, raw):
    require(
        result["d_ref"] > 0
        and np.isfinite(result["d_ref"])
        and result["d_G"] > 0
        and np.isfinite(result["d_G"]),
        "NONZERO_FINITE_SAVED_DENOMINATORS",
    )
    verdicts = {}
    for name, state in result["states"].items():
        e, Ge, r, qr, X, GX, Y, WY = [
            raw[name + "_" + k] for k in ("e", "Ge", "r", "qr", "X", "GX", "Y", "WY")
        ]
        require(
            all(np.isfinite(v).all() for v in (e, Ge, r, qr, X, GX, Y, WY)),
            "NONFINITE_LOCAL_SAVED_VECTORS",
        )
        projections = {}
        for kind, pr in state["projections"].items():
            a = raw[name + "_" + kind + "_alpha"]
            step = raw[name + "_" + kind + "_step"]
            require(np.isrealobj(a) and np.isrealobj(step), "REAL_PARAMETER_REQUIRED")
            require(
                np.isfinite(a).all() and np.isfinite(step).all(),
                "NONFINITE_PARAMETER_PROJECTION",
            )
            require(
                np.allclose(raw[name + "_P"] @ a, step, rtol=1e-10, atol=1e-12),
                "PARAMETER_PROJECTION",
            )
            dx, dgx, dy, dwy = X @ a, GX @ a, Y @ a, WY @ a
            field = raw_change(e, dx, Ge, dgx)
            residual = raw_change(r, dy, qr, dwy)
            paired_change(pr["field_cross_effect"], field)
            paired_change(pr["residual_cross_effect"], residual)
            objective = field if kind == "field" else residual
            same(
                pr["before_energy"],
                objective["before"],
                scale=objective["operation_scale"],
            )
            same(
                pr["after_energy"],
                objective["after"],
                scale=objective["operation_scale"],
            )
            fraction = objective["removed_energy_fraction"]
            if fraction is None:
                require(pr["removed_energy_fraction"] is None, "ZERO_ENERGY_FRACTION")
            else:
                same(
                    pr["removed_energy_fraction"],
                    fraction,
                    scale=objective["operation_scale"] / objective["before"],
                )
            projections[kind] = dict(field=field, residual=residual)
            field_after, res_after = field["after"], residual["after"]
            same(pr["E_G_after_linear"], np.sqrt(field_after / result["d_ref"]))
            same(pr["dual_loss_after_linear"], res_after / (2 * result["d_G"]))
            require(
                pr["rank"] <= 16 and pr["real_coefficients"], "LOCAL_PROJECTION_LAYOUT"
            )
        for w in state["witnesses"]:
            stem = f"{name}_{w['projection']}_{w['cap']}"
            ca = raw[stem + "_actual"]
            Gea = raw[stem + "_Ge"]
            ra = raw[stem + "_r"]
            qra = raw[stem + "_qr"]
            same(
                w["E_G"],
                np.sqrt(quadratic(ca - (raw[name + "_c"] - e), Gea) / result["d_ref"]),
            )
            same(w["dual_loss"], quadratic(ra, qra) / (2 * result["d_G"]))
            require(
                w["parameter_restored"]
                and w["parameter_step_norm"]
                <= w["cap"] * max(state["parameter_norm"], 1) * (1 + 1e-12),
                "DIAGNOSTIC_WITNESS_BOUNDARY",
            )
        require(
            state["parameter_buffers_unchanged"], "DIAGNOSTIC_PARAMETER_PRESERVATION"
        )
        F, R = projections["field"], projections["residual"]
        fraction_field = F["field"]["removed_energy_fraction"]
        fraction_residual_field = R["field"]["removed_energy_fraction"]
        if F["field"]["near_zero_before"] or R["field"]["near_zero_before"]:
            classification = "LOCAL_CLASSIFICATION_UNDEFINED_NEAR_ZERO"
        elif fraction_field >= 0.5 and fraction_residual_field < 0.5:
            classification = "LOCAL_OBJECTIVE_DIRECTION_MISMATCH"
        elif fraction_field >= 0.5 and fraction_residual_field >= 0.5:
            classification = (
                "BOTH_LOCAL_DIRECTIONS_PROMISING_NOT_NONLINEAR_REACHABILITY_PROOF"
            )
        else:
            classification = "TESTED_LOCAL_DIRECTIONS_LIMITED_NOT_GLOBAL_CLASS_BOUND"
        verdicts[name] = dict(
            field_energy_removed=fraction_field,
            residual_projection_field_energy_removed=fraction_residual_field,
            residual_energy_removed=R["residual"]["removed_energy_fraction"],
            classification=classification,
            raw_projections=projections,
        )
    require(
        result["counts"]["JVP"] <= 64
        and result["counts"]["VJP"] <= 16
        and result["counts"]["forward_witnesses"] <= 8,
        "C1_WORK_CAP",
    )
    require(
        all(
            result["actions"][k] <= cap
            for k, cap in dict(A=64, AH=64, Gsolve=80, G_matvec=128).items()
        ),
        "C1_OPERATOR_CAP",
    )
    return verdicts


def auxiliary_state_mapping(cost):
    """Correct new evidence only; the published V12 JSON stays immutable."""
    threshold = 0.8 * cost["baseline_complete_seconds"]
    same(cost["time_gain_threshold_seconds"], threshold)
    require(
        np.isfinite(threshold)
        and threshold > 0
        and cost["nn_prefix_lower_bound_seconds"] > threshold
        and cost["memory_lower_bound_from_historical_NN_workflow_bytes"]
        > 0.8 * cost["baseline_peak_tree_RSS_bytes"],
        "D0_COST_VETO_EVIDENCE",
    )
    require(cost["D1_status"] == "NOT_RUN_COST_VETO", "D1_NOT_RUN_EVIDENCE")
    return dict(D0="COST_VETO_CONFIRMED", D1="NOT_RUN_COST_VETO")


def verify_background(result, raw):
    """Arithmetic-only affine check; the original FE operator is not imported."""
    require(
        all(np.isfinite(raw[k]).all() for k in raw.files)
        if hasattr(raw, "files")
        else all(np.isfinite(v).all() for v in raw.values()),
        "NONFINITE_BACKGROUND_VECTORS",
    )
    db = raw["P34b3"] - raw["b4"]
    scale = np.linalg.norm(raw["P34b3"]) + np.linalg.norm(raw["b4"])
    same(float(np.linalg.norm(db - raw["d_b"])), 0.0, tol=1e-10, scale=scale)
    df, dt = np.linalg.norm(raw["f4"]), np.linalg.norm(raw["total_rhs4"])
    require(min(df, dt) > 0, "ORIGINAL_BACKGROUND_RHS_DENOMINATOR")
    shift = raw["A4_d_b"]
    energy_shift = quadratic(shift, shift)
    rows = {}
    for name, row in result["rows"].items():
        old, new = raw["original_" + name], raw["corrected_" + name]
        natural = np.linalg.norm(old) + np.linalg.norm(shift)
        same(float(np.linalg.norm(new - old - shift)), 0.0, tol=1e-10, scale=natural)
        before, after = quadratic(old, old), quadratic(new, new)
        cross = 2 * np.vdot(old, shift).real
        es = max(before, after, abs(cross) + energy_shift, np.finfo(float).tiny)
        for key, value in dict(
            energy_before=before,
            energy_after=after,
            signed_cross=cross,
            correction_energy=energy_shift,
            energy_change=after - before,
            energy_operation_scale=es,
        ).items():
            same(row[key], value, scale=es)
        same(after - before, cross + energy_shift, scale=es)
        for key, value in dict(
            original_absolute=np.sqrt(before),
            correction_absolute=np.sqrt(energy_shift),
            corrected_absolute=np.sqrt(after),
            original_f4_denominator=df,
            total_rhs_diagnostic_denominator=dt,
            original_relative=np.sqrt(before) / df,
            corrected_relative=np.sqrt(after) / df,
            corrected_total_rhs_diagnostic_relative=np.sqrt(after) / dt,
        ).items():
            same(row[key], value)
        phase = np.vdot(old, shift)
        ps = np.linalg.norm(old) * np.linalg.norm(shift)
        if ps:
            require(
                np.allclose(
                    row["normalized_cross_complex"],
                    [phase.real / ps, phase.imag / ps],
                    rtol=1e-8,
                    atol=1e-8,
                ),
                "BACKGROUND_CROSS_PHASE",
            )
        else:
            require(
                row["normalized_cross_complex"] is None, "BACKGROUND_ZERO_CROSS_PHASE"
            )
        rows[name] = dict(
            original_absolute=np.sqrt(before),
            corrected_absolute=np.sqrt(after),
            corrected_relative=np.sqrt(after) / df,
            original_f4_denominator=float(df),
        )
        if name != "p3reference":
            old_image = old - raw["original_p3reference"]
            new_image = new - raw["corrected_p3reference"]
            s = (
                natural
                + np.linalg.norm(raw["original_p3reference"])
                + np.linalg.norm(new)
                + np.linalg.norm(raw["corrected_p3reference"])
            )
            defect = np.linalg.norm(old_image - new_image) / s
            require(defect <= 1e-10, "BACKGROUND_ERROR_IMAGE_INVARIANCE")
            same(row["error_image_absolute"], np.linalg.norm(old_image))
            rows[name]["error_image_invariance"] = float(defect)
    direct = raw["direct_same_total_reference"]
    s = (
        np.linalg.norm(direct)
        + np.linalg.norm(raw["original_p3reference"])
        + np.linalg.norm(shift)
        + df
    )
    require(
        np.linalg.norm(direct - raw["corrected_p3reference"]) / s <= 1e-10,
        "BACKGROUND_DIRECT_ADDITION_PAIRING",
    )
    require(
        result["cumulative_A4_reserved"] <= 4
        and result["A4"] <= 4
        and all(
            result[k] == 0
            for k in (
                "AH4",
                "G_actions",
                "Gsolve",
                "new_reference_solves",
                "network_forwards",
            )
        )
        and not any(
            result[k]
            for k in ("G4_created", "Gram_factor_created", "Maxwell_factor_created")
        ),
        "BACKGROUND_FORBIDDEN_ACTION_OR_CAP",
    )
    require(
        max(
            result["background_embedding"]["common_E_scaled_curl_relative"]
            + [
                result["background_embedding"]["MPC_operation_relative"],
                result["p3_background_MPC_relative"],
            ]
        )
        <= 1e-10,
        "BACKGROUND_FE_EMBEDDING",
    )
    return dict(
        rows=rows, same_p3_NN_failure_unchanged=True, no_new_solver_qualification=True
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--closure-v13", action="store_true")
    args = parser.parse_args()
    answer = dict(
        schema="task42extra.independent-attribution-checker.v12",
        training_performed=False,
        official_candidate_results=False,
    )
    for stage, verify, key in [
        ("v12_saved_field_attribution", verify_B, "B"),
        ("v12_local_parameter_diagnostic", verify_C, "C1"),
    ]:
        path = ART / ("index_" + stage + ".json")
        if not path.exists():
            answer[key] = dict(status="NOT_RUN")
            continue
        index = load(stage)
        with np.load(index["files"]["vectors"]["path"], allow_pickle=False) as raw:
            answer[key] = verify(index["result"], raw)
    integral = ART / "index_v12_saved_field_integrals.json"
    if integral.exists():
        index = load("v12_saved_field_integrals")
        r = index["result"]
        out = {}
        for name, t in r["energy_terms"].items():
            i = 0 if name == "E_L2" else 1
            e = r["energies"]
            cross = (e["after"][i] - e["minus"][i]) / 2
            change = e["after"][i] - e["before"][i]
            same(t["cross"], cross, scale=t["operation_scale"])
            same(change, cross + e["delta"][i], scale=t["operation_scale"])
            out[name] = dict(change=change, cross=cross, update_energy=e["delta"][i])
        require(max(r["MPC"].values()) <= 1e-10, "ACTUAL_FE_MPC")
        answer["independent_FE_integrals"] = out
    else:
        answer["independent_FE_integrals"] = dict(
            status="NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE", passed=False
        )
    if (ART / "index_v12_test_space_witness.json").exists():
        index = load("v12_test_space_witness")
        r = index["result"]
        with np.load(index["files"]["vectors"]["path"], allow_pickle=False) as raw:
            f = raw["f4"]
            base = raw["r4_p3reference"]
            for name, row in r["rows"].items():
                same(row["native_absolute"], np.linalg.norm(raw["r4_" + name]))
                same(
                    row["native_relative"],
                    np.linalg.norm(raw["r4_" + name]) / np.linalg.norm(f),
                )
                if name != "p3reference":
                    same(
                        row["relative_to_p3_baseline_absolute"],
                        np.linalg.norm(raw["r4_" + name] - base),
                    )
            same(
                r["p4_reference_native"],
                np.linalg.norm(raw["reference4_residual"]) / np.linalg.norm(f),
            )
        require(
            r["A4"] <= 8 and r["p4_reference_native"] <= 1e-10 and not r["G4_created"],
            "P4_WITNESS_GATES",
        )
        require(max(x["MPC"] for x in r["embedding"].values()) <= 1e-10, "P34_MPC")
        answer["C2"] = dict(
            status="RAW_SCALARS_RECOMPUTED",
            p3_baseline_relative=r["rows"]["p3reference"]["native_relative"],
            candidate_rows=r["rows"],
            not_qualified_dual_norm=True,
        )
    else:
        answer["C2"] = dict(status="NOT_RUN")
    answer["decision"] = "FEINN_MAIN_SOLVER_ON_HOLD"
    answer["neural_increment"] = "NO_VERIFIED_NN_INCREMENT"
    if args.closure_v13:
        records = ROOT / "docs/task042extra_feinn_5nm/outcomes/records"
        audit_path = records / "review_v12_evidence_audit.json"
        audit = json.loads(audit_path.read_text())
        for stage, source in audit["source_files"].items():
            index = load(stage)
            require(
                index["source_sha"] == source["source_sha"], "REVIEW_SOURCE_CHANGED"
            )
            for key, entry in source["files"].items():
                require(index["files"][key] == entry, "REVIEW_SAVED_INPUT_CHANGED")
        answer.update(
            schema="task42extra.independent-attribution-checker.v13",
            reused_witness_norms=audit["C1_additional_raw_arithmetic"],
            witness_norm_audit_sha256=hashlib.sha256(
                audit_path.read_bytes()
            ).hexdigest(),
            D=auxiliary_state_mapping(
                json.loads((records / "auxiliary_cost_v12.json").read_text())
            ),
            new_actions=dict(A=0, AH=0, G=0, Gsolve=0, JVP=0, VJP=0, network_forward=0),
            missing_historical_optimizer_RNG="NOT_RETAINED_V2_V6",
            conclusion_boundaries=dict(
                same_p3_NN_solve="FAIL",
                tested_local_objective_direction_mismatch="SUPPORTED_FINITE_DIRECTIONS",
                global_network_expressivity="UNKNOWN",
            ),
        )
        if (ART / "index_v13_background_transfer.json").exists():
            index = load("v13_background_transfer")
            with np.load(index["files"]["vectors"]["path"], allow_pickle=False) as raw:
                answer["background_transfer"] = verify_background(index["result"], raw)
        else:
            answer["background_transfer"] = dict(
                status="NOT_RUN_INPUT_OR_RESOURCE_UNAVAILABLE"
            )
    Path(args.output).write_text(json.dumps(answer, indent=2) + "\n")
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()
