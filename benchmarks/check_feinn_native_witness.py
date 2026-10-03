"""Independent frozen-vector witness audit, with exactly two A and four G actions."""

import argparse
import json
from pathlib import Path

import numpy as np

from src.solvers.neural_fe_action_packet import array_hash


def require(value, reason):
    if not value:
        raise ValueError(reason)


def relative(a, b):
    a, b = np.asarray(a), np.asarray(b)
    require(
        a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(),
        "FINITE_VECTOR_LAYOUT",
    )
    return float(
        np.linalg.norm(a - b) / max(np.linalg.norm(a) + np.linalg.norm(b), 1e-30)
    )


def replay_operation_account(actions, result):
    prior = result["prior_failed_attempt"]["operation_upper_bound"]
    combined = {
        key: actions[key] + prior[key] for key in ("A", "AH", "Gsolve", "G_matvec")
    }
    combined.update(
        network_forward=result["complete_network_forwards"] + prior["network_forward"],
        Gram_factor=result["Gram_factor_lifecycles"] + prior["Gram_factor"],
        JVP=result["JVP"] + prior["JVP"],
        VJP=result["VJP"] + prior["VJP"],
    )
    require(
        combined["A"] <= 16
        and combined["Gsolve"] <= 8
        and combined["G_matvec"] <= 24
        and combined["network_forward"] <= 8
        and combined["Gram_factor"] <= 2
        and combined["AH"] == combined["JVP"] == combined["VJP"] == 0,
        "INCLUDING_FAILED_ATTEMPT_OPERATION_CAPS",
    )
    return combined


def evaluate(arrays, state, predicted, metadata):
    data = {
        key: np.asarray(arrays[state + "_" + key])
        for key in (
            "c_zero",
            "c_linear",
            "c_actual",
            "r_zero",
            "r_linear",
            "r_actual",
            "qr_zero",
            "qr_linear",
            "qr_actual",
            "e_zero",
            "e_linear",
            "e_actual",
            "Ge_zero",
            "Ge_linear",
            "Ge_actual",
            "theta_zero",
            "theta_trial",
            "theta_restored",
            "delta_theta",
        )
    }
    require(
        all(np.isfinite(value).all() for value in data.values()),
        "FINITE_WITNESS_ARRAYS",
    )
    require(
        np.array_equal(data["theta_zero"], data["theta_restored"]),
        "RESTORED_PARAMETERS",
    )
    require(
        relative(data["theta_trial"] - data["theta_zero"], data["delta_theta"])
        <= 1e-10,
        "PARAMETER_STEP_IDENTITY",
    )
    n0 = float(np.vdot(data["r_zero"], data["r_zero"]).real)
    d0 = float(np.vdot(data["r_zero"], data["qr_zero"]).real)
    f0 = float(np.vdot(data["e_zero"], data["Ge_zero"]).real)
    require(
        min(n0, d0, f0) > 0 and np.isfinite([n0, d0, f0]).all(),
        "POSITIVE_WITNESS_DENOMINATORS",
    )
    points = {}
    for kind in ("zero", "linear", "actual"):
        r, q, e, Ge = [data[key + "_" + kind] for key in ("r", "qr", "e", "Ge")]
        N = float(np.vdot(r, r).real / n0)
        R = float(np.vdot(r, q).real / d0)
        F = float(np.vdot(e, Ge).real / f0)
        require(np.isfinite([N, R, F]).all() and min(N, R, F) >= 0, "WITNESS_ENERGY")
        points[kind] = dict(
            N=N,
            R=R,
            F=F,
            native=float(np.linalg.norm(r) / metadata["native_denominator"]),
            dual_loss=float(np.vdot(r, q).real / (2 * metadata["d_G"])),
            G_error_energy=float(np.vdot(e, Ge).real),
        )
    for key in ("N", "R", "F"):
        require(
            abs(
                points["linear"][key]
                - predicted["raw_points"]["native_constrained"][key]
            )
            <= 1e-10,
            "FROZEN_LINEAR_SCORING",
        )
    defect = float(
        np.linalg.norm(data["c_actual"] - data["c_linear"])
        / np.linalg.norm(data["c_linear"] - data["c_zero"])
    )
    require(
        relative(data["e_actual"] - data["e_zero"], data["c_actual"] - data["c_zero"])
        <= 1e-10,
        "SAME_REFERENCE_ERROR_DIFFERENCE",
    )
    proof = metadata["rows"][state]
    require(
        proof["theta_restored"] is True and proof["buffers_restored"] is True,
        "RESTORATION_PROOF",
    )
    require(
        proof["theta_zero_sha256"] == array_hash(data["theta_zero"])
        and proof["theta_trial_sha256"] == array_hash(data["theta_trial"]),
        "THETA_HASH",
    )
    require(
        proof["c_zero_sha256"] == array_hash(data["c_zero"])
        and proof["c_actual_sha256"] == array_hash(data["c_actual"]),
        "C_HASH",
    )
    checks = dict(
        retains_half_native_drop=points["actual"]["N"]
        <= 1 - 0.5 * (1 - points["linear"]["N"]),
        field_energy=points["actual"]["F"] <= 0.999,
        dual_nonincrease=points["actual"]["R"] <= 1 + 1e-8,
        nonlinear_model=defect <= 0.05,
        original_identity=proof["original_c_identity_relative"] <= 1e-10,
        operator_pairings=max(proof["operator_pairings"].values()) <= 1e-10,
    )
    return dict(
        points=points,
        nonlinear_defect=defect,
        checks=checks,
        local_pre_FE_support=all(checks.values()),
        failure_quantities=[key for key, value in checks.items() if not value],
    )


def main():
    from scipy import sparse
    from src.runners.feinn_workflow import load_index, write_json, sha
    from src.runners.feinn_native_constraint_arrays import source
    from src.runners.feinn_common_descent_arrays import extract, read_checked
    from src.solvers.feinn_native import load_native
    from src.solvers.feinn_native_network_witness import (
        witness_gate,
        prior_failed_attempt,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    head = source()
    pre, gate = witness_gate()
    witness = load_index("v18_native_network_witness", file_keys=("vectors", "result"))
    native = load_index("e1_fe", file_keys=("native", "gram"))
    packet = load_native(native["files"]["native"]["path"])
    G = sparse.load_npz(native["files"]["gram"]["path"])
    result = witness["result"]
    require(
        result["prior_failed_attempt"] == prior_failed_attempt(),
        "FAILED_ATTEMPT_CHARGE_BINDING",
    )
    require(
        result["status"] == "NETWORK_WITNESS_FROZEN"
        and result["A_checker"] == pre["A_checker"],
        "FROZEN_WITNESS_BOUNDARY",
    )
    require(
        result["complete_network_forwards"] == 4
        and result["Gram_factor_lifecycles"] == 1
        and result["JVP"] == result["VJP"] == 0,
        "FIXED_FORWARD_FACTOR_COUNTS",
    )
    require(
        result["Gram_factor"]["max_solve_true_relative"] <= 1e-11, "GRAM_TRUE_RESIDUAL"
    )
    rows = {}
    with (
        np.load(witness["files"]["vectors"]["path"], allow_pickle=False) as arrays,
        np.load(read_checked(pre["vectors"]), allow_pickle=False) as raw_arrays,
    ):
        for state in pre["states"]:
            candidate = json.loads(read_checked(pre["candidates"][state]).read_text())
            raw = extract(
                raw_arrays,
                state,
                ("P", "X", "Y", "WY", "theta", "e", "Ge", "qr"),
                pre["array_layout"],
                candidate["columns"],
            )
            alpha = np.asarray(candidate["alpha"])
            require(
                np.array_equal(arrays[state + "_theta_zero"], raw["theta"]),
                "ORIGINAL_PARAMETER_VECTOR",
            )
            for key, value in dict(
                delta_theta=raw["P"] @ alpha,
                c_linear=arrays[state + "_c_zero"] + raw["X"] @ alpha,
                r_linear=arrays[state + "_r_zero"] + raw["Y"] @ alpha,
                qr_linear=raw["qr"] + raw["WY"] @ alpha,
                e_zero=raw["e"],
                Ge_zero=raw["Ge"],
                qr_zero=raw["qr"],
            ).items():
                require(
                    relative(arrays[state + "_" + key], value) <= 1e-10,
                    "FROZEN_DIRECTION_OR_SCORING_IDENTITY",
                )
            rows[state] = evaluate(
                arrays, state, gate["configurations"][state + "_1e-10"], result
            )
            c, r, q, e, Ge = [
                arrays[state + "_" + key]
                for key in (
                    "c_actual",
                    "r_actual",
                    "qr_actual",
                    "e_actual",
                    "Ge_actual",
                )
            ]
            pairing = relative(packet.apply(c) - packet.f, r)
            # Exactly two counted sparse Gram actions per state. Original qr/Ge
            # already have independent C1 pairing plus fresh solve truth tests.
            qpair = float(np.linalg.norm(G @ q - r) / np.linalg.norm(r))
            epair = relative(G @ e, Ge)
            require(
                pairing <= 1e-10 and qpair <= 1e-11 and epair <= 1e-10,
                "INDEPENDENT_NATIVE_GRAM_PAIRING",
            )
            rows[state]["independent_pairings"] = dict(
                A=pairing, Gsolve_true=qpair, Ge=epair
            )
    actions = dict(result["actions"])
    actions["A"] += packet.counts["A"]
    actions["G_matvec"] += 4
    require(
        actions["A"] <= 8
        and actions["AH"] == 0
        and actions["Gsolve"] <= 4
        and actions["G_matvec"] <= 12,
        "WHOLE_C_OPERATION_CAPS",
    )
    combined = replay_operation_account(actions, result)
    output = dict(
        status="INDEPENDENT_VECTOR_AUDIT_COMPLETE",
        source_sha=head,
        rows=rows,
        actions=actions,
        actions_including_failed_attempt_conservative_upper=combined,
        prior_failed_attempt=result["prior_failed_attempt"],
        FE_restore_required=True,
        local_mechanism="PENDING_INDEPENDENT_FE",
        vectors=witness["files"]["vectors"],
        original_result=witness["files"]["result"],
        A_checker=pre["A_checker"],
        checker_source_sha256=sha(__file__),
        new_network_forward=0,
        new_Gsolve=0,
        new_Gram_factor=0,
        reference_used_for_training=False,
        pde_only_solve=False,
        official_candidate_results=False,
        production_initialization_allowed=False,
    )
    require(not Path(args.output).exists(), "IMMUTABLE_WITNESS_CHECKER_OUTPUT")
    write_json(args.output, output)
    print(
        json.dumps(
            dict(
                status=output["status"],
                rows={key: row["failure_quantities"] for key, row in rows.items()},
                actions=actions,
            )
        )
    )


if __name__ == "__main__":
    main()
