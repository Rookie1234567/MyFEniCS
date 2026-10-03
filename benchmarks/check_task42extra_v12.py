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


def verify_C(result, raw):
    verdicts = {}
    for name, state in result["states"].items():
        e, Ge, r, qr, X, GX, Y, WY = [
            raw[name + "_" + k] for k in ("e", "Ge", "r", "qr", "X", "GX", "Y", "WY")
        ]
        for kind, pr in state["projections"].items():
            a = raw[name + "_" + kind + "_alpha"]
            step = raw[name + "_" + kind + "_step"]
            require(np.isrealobj(a) and np.isrealobj(step), "REAL_PARAMETER_REQUIRED")
            require(
                np.allclose(raw[name + "_P"] @ a, step, rtol=1e-10, atol=1e-12),
                "PARAMETER_PROJECTION",
            )
            dx, dgx, dy, dwy = X @ a, GX @ a, Y @ a, WY @ a
            field_after = quadratic(e + dx, Ge + dgx)
            res_after = quadratic(r + dy, qr + dwy)
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
        F = state["projections"]["field"]
        R = state["projections"]["residual"]
        fraction_residual_field = (
            1 - R["field_cross_effect"]["after"] / R["field_cross_effect"]["before"]
        )
        if F["removed_energy_fraction"] >= 0.5 and fraction_residual_field < 0.5:
            classification = "LOCAL_OBJECTIVE_DIRECTION_MISMATCH"
        elif F["removed_energy_fraction"] >= 0.5 and fraction_residual_field >= 0.5:
            classification = (
                "BOTH_LOCAL_DIRECTIONS_PROMISING_NOT_NONLINEAR_REACHABILITY_PROOF"
            )
        else:
            classification = "TESTED_LOCAL_DIRECTIONS_LIMITED_NOT_GLOBAL_CLASS_BOUND"
        verdicts[name] = dict(
            field_energy_removed=F["removed_energy_fraction"],
            residual_projection_field_energy_removed=fraction_residual_field,
            residual_energy_removed=R["removed_energy_fraction"],
            classification=classification,
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
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
    Path(args.output).write_text(json.dumps(answer, indent=2) + "\n")
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()
