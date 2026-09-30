"""Independent arithmetic of saved restricted action and actual network field.

No QR/SVD solve or reference solve is repeated. All additional action columns
are explicitly charged, including those verifying the saved restricted action.
"""

import csv
import json
from pathlib import Path
import sys

import numpy as np
from scipy import sparse

from benchmarks.check_task42extra_v2 import (
    RECORDS,
    RESULTS,
    index,
    read,
    write,
    sha,
    close,
    channel_error,
    complex_array,
)
from benchmarks.check_task42extra_v5 import resources
from src.solvers.feinn_gqr import GramColumns, squared_norm
from src.solvers.feinn_native import load_native
from src.solvers.feinn_restricted_residual import POLICY, ROUTE, load_basis

STAGES = (
    "v6_operator_readout_checks",
    ROUTE,
    "v6_residual_readout_reconstruct",
    "v6_residual_readout_compare_only",
)


def policy(item):
    if any(bool(item[k]) != value for k, value in POLICY.items()):
        raise ValueError("V6_REFERENCE_ROLE_POLICY_LOST")


def resource_update(indices):
    return resources(
        indices,
        version=6,
        old_seconds=44815.22461795143,
        batch_limit=3600,
        main_limit=1800,
        main_route=ROUTE,
    )


def main():
    indices = {s: index(s)[0] for s in STAGES}
    if "--resources-only" in sys.argv:
        resource_update(indices)
        return
    fit = indices[ROUTE]
    r = fit["result"]
    core = index("e1_fe")[0]
    previous = index("FEINN-FROZEN-HIDDEN-READOUT-G")[0]
    if len(list(RESULTS.glob("task42extra_v6_frozen_feature_residual_*"))) != 1:
        raise ValueError("V6_MAIN_START_COUNT")
    for item in indices.values():
        policy(item["result"])
        policy(read(Path(item["run_directory"]) / "run_manifest.json"))
    if r["target_reference_loaded"] or any(
        r[k]
        for k in (
            "optimizer_steps",
            "Gsolve_count",
            "Gram_factor_count",
            "Maxwell_factor_count",
        )
    ):
        raise ValueError("READOUT_MAIN_SCOPE")
    basis = load_basis(previous["files"]["projection_arrays"]["path"])
    with np.load(fit["files"]["projection_arrays"]["path"], allow_pickle=False) as data:
        B, Z, R = (np.array(data[k]) for k in ("B", "Z", "R_B"))
        y, residual = (np.array(data[k]) for k in ("y", "residual_hat"))
        L, s, vh, pi = (
            np.array(data[k]) for k in ("left_B", "singular_B", "vh_B", "permutation_B")
        )
    with np.load(fit["files"]["checkpoint"]["path"], allow_pickle=False) as data:
        policy(data)
        c, p, a = (np.array(data[k]) for k in ("c", "parameters", "a1"))
    packet = load_native(core["files"]["native"]["path"])
    Bh, fh = B / packet.bnorm, packet.f / packet.bnorm
    rr = Bh @ y - fh
    keep = s > s[0] * 1e-12
    qr = np.linalg.norm(Bh[:, pi] - Z @ R) / np.linalg.norm(Bh)
    orth = np.linalg.norm(Z.conj().T @ Z - np.eye(195))
    svd_pair = np.linalg.norm(R - (L * s) @ vh) / np.linalg.norm(R)
    opt = np.linalg.norm((Z @ L[:, keep]).conj().T @ rr)
    rho = np.linalg.norm(rr)
    projection_defect = abs(1 - rho**2 - np.linalg.norm(Bh @ y) ** 2)
    old_pi = basis["permutation"]
    y_from_a = basis["singular_values"] * (
        basis["vh"] @ (basis["scales"][old_pi] * a[old_pi])
    )
    map_inverse = np.linalg.norm(y - y_from_a) / np.linalg.norm(y)
    G = GramColumns(sparse.load_npz(core["files"]["gram"]["path"]), limit=32)
    ideal = basis["Q_eff"] @ y
    diff = c - ideal
    map_E = np.linalg.norm(diff) / np.linalg.norm(ideal)
    map_G = np.sqrt(
        squared_norm(diff, G(diff, "checker_writeback"))
        / squared_norm(ideal, G(ideal, "checker_field_norm"))
    )
    rng = np.random.default_rng(421601)
    combinations = []
    for _ in range(3):
        u = rng.normal(size=195) + 1j * rng.normal(size=195)
        b, ac = B @ u, packet.apply(basis["Q_eff"] @ u)
        combinations.append(
            float(np.linalg.norm(b - ac) / (np.linalg.norm(b) + np.linalg.norm(ac)))
        )
    r_actual = packet.apply(c) - packet.f
    A_pair = np.linalg.norm(r_actual - packet.bnorm * rr) / packet.bnorm
    audit = packet.audit(c)
    from src.solvers.optimization_checkpoint import load_checkpoint

    current = load_checkpoint(
        fit["files"]["parameter_only_model"]["path"],
        fit["files"]["parameter_only_model"]["sha256"],
    )
    old = load_checkpoint(
        previous["files"]["parameter_only_model"]["path"],
        previous["files"]["parameter_only_model"]["sha256"],
    )
    policy(current["metadata"])
    if "optimizer" in current or current["metadata"]["optimizer_state_saved"]:
        raise ValueError("OPTIMIZER_HISTORY_CONTAMINATION")
    hidden_exact = all(
        np.array_equal(v.numpy(), old["model"][k].numpy())
        for k, v in current["model"].items()
        if not k.startswith("envelopes.6.")
    )
    pp = np.concatenate(
        [
            current["model"][o["name"]].numpy().ravel()
            for o in current["parameter_order"]
        ]
    )
    if not np.array_equal(p, pp) or not hidden_exact:
        raise ValueError("FROZEN_NETWORK_IDENTITY")
    stable = bool(
        sum(keep) == 195
        and qr <= 1e-10
        and orth <= 1e-10
        and svd_pair <= 1e-10
        and opt <= 1e-9
        and max(combinations) <= 1e-10
        and map_inverse <= 1e-10
        and map_E <= 1e-10
        and map_G <= 1e-9
        and A_pair <= 1e-9
        and projection_defect <= 1e-8
        and rho <= 1 + 1e-9
        and np.linalg.norm(rr - residual) <= 1e-12
    )
    physical = indices["v6_residual_readout_compare_only"]["result"]
    candidate = physical["physics"]["records"][ROUTE]
    reference = physical["physics"]["records"]["REFERENCE"]
    comp = physical["comparisons"][ROUTE]
    errors = comp["errors"]
    channels = {
        k: channel_error(candidate, reference, v, errors[k])
        for k, v in {
            "ordered_total_channels": "ordered_complex_total_channels",
            "ordered_outgoing_channels": "ordered_complex_outgoing_channels",
            "ordered_boundary_outgoing_channels": "ordered_complex_boundary_outgoing_channels",
            "ordered_scattered_channels": "ordered_complex_scattered_channels",
        }.items()
    }
    for e in errors.values():
        if not close(e["absolute"] / e["denominator"], e["relative"]):
            raise ValueError("FIELD_ERROR_DENOMINATOR")
    for key, field in dict(
        selected_total_E="selected_total_E",
        selected_total_H="selected_total_H_code",
        selected_scattered_E="selected_scattered_E",
        selected_scattered_H="selected_scattered_H_code",
    ).items():
        aa, bb = (
            np.asarray(complex_array(x[field])).reshape(6, 3)
            for x in (candidate, reference)
        )
        for suffix, x, z in [("", aa, bb)] + [
            (f"_point_{j}", aa[j], bb[j]) for j in range(6)
        ]:
            if not close(
                np.linalg.norm(x - z) / max(np.linalg.norm(z), 1e-12),
                errors[key + suffix]["relative"],
            ):
                raise ValueError("COMPLEX_FIELD_ERROR")
    power = candidate["port"]
    Av = candidate["volume"]["A_volume_total"]
    energy = abs(power["R_total"] + power["T_total"] + Av - 1)
    absorption = abs(power["A_balance"] - Av)
    powers = np.max(
        abs(
            np.asarray(candidate["ordered_per_channel_power"])
            - reference["ordered_per_channel_power"]
        )
    )
    if not close(energy, comp["energy_closure_absolute"]) or not close(
        powers, comp["max_channel_power_absolute"]
    ):
        raise ValueError("POWER_ENERGY_ARITHMETIC")
    audit = candidate["audit"]
    equation = (
        all(
            audit[k] <= 1e-6
            for k in [
                "native_relative",
                "augmented_relative",
                "original_total_augmented_relative",
                "independent_DOLFINx_total_native_relative",
                "port_full_rhs_relative",
                "port_operation_relative",
            ]
        )
        and audit["slave_storage_max"] == 0
    )
    field_pass = all(e["relative"] <= 1e-4 for e in errors.values())
    power_pass = (
        max(comp["power_absolute_differences"].values()) <= 1e-5
        and max(energy, absorption) <= 1e-5
        and powers <= 1e-6
    )
    old_gates = {v: read(RECORDS / f"gate_decisions_v{v}.json") for v in (4, 5)}
    identities = {}
    NE, NC = np.square(physical["physics"]["reference_scattered_norms"])
    for name, eg, ee in [
        ("V4", old_gates[4]["G_field_error"]["relative"], old_gates[4]["errors"]),
        ("V5", old_gates[5]["G_field_error"]["relative"], old_gates[5]["errors"]),
        ("V6", physical["G_field_error"], errors),
    ]:
        weighted = (
            NE * ee["scattered_L2"]["relative"] ** 2
            + (2 * np.pi) ** 2 * NC * ee["scattered_scaled_curl"]["relative"] ** 2
        ) / (NE + (2 * np.pi) ** 2 * NC)
        identities[name] = dict(
            E_G_squared=eg**2,
            weighted_L2_curl_squared=float(weighted),
            absolute_defect=abs(eg**2 - weighted),
        )
    norm_ok = (
        max(v["absolute_defect"] for v in identities.values()) <= 1e-8
        and physical["norm_identity"]["relative_reference_energy_defect"] <= 1e-10
    )
    py = physical["V5_G_pythagorean"]
    norm_ok &= (
        py["normalized_absolute_defect"] <= 1e-8
        and py["new_error_squared"] >= py["V5_error_squared"] - 1e-8
    )
    if not norm_ok or not stable:
        raise ValueError("RESIDUAL_FLOOR_OR_NORM_IDENTITY_NOT_REPRODUCED")
    for name, region in physical["region_field_errors"].items():
        if (
            region["cell_ids_sha256"]
            != old_gates[5]["region_field_errors"][name]["cell_ids_sha256"]
        ):
            raise ValueError("REGION_IDENTITY")
    counts = dict(
        A=indices[STAGES[0]]["result"]["native_action_counts"]["A"]
        + r["native_action_counts"]["A"]
        + packet.counts["A"],
        AH=indices[STAGES[0]]["result"]["native_action_counts"]["AH"]
        + r["native_action_counts"]["AH"]
        + packet.counts["AH"],
        audit=r["native_action_counts"]["audit"]
        + physical["full_native_audits"]
        + packet.counts["audit"],
        G=indices[STAGES[0]]["result"]["G_action_columns"]
        + r["G_action_columns"]
        + physical["G_action_columns"]
        + G.count,
    )
    if (
        counts["A"] > 256
        or counts["AH"] > 8
        or counts["audit"] > 12
        or counts["G"] > 512
    ):
        raise ValueError("COLUMN_BUDGET")
    category = "FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED"
    gate = dict(
        schema="task42extra.gate-decisions.v6",
        category=category,
        frozen_feature_residual_gate=bool(rho <= 1e-6),
        scope="this discrete full 195D frozen feature space; not entire network class",
        representation_positive=max(physical["G_field_error"], errors["scattered_L2"]["relative"], errors["scattered_scaled_curl"]["relative"])<=1e-3,
        representation_partial=max(physical["G_field_error"], errors["scattered_L2"]["relative"], errors["scattered_scaled_curl"]["relative"])<=1e-2,
        representation_thresholds=[1e-3, 1e-2],
        frozen_feature_residual_excess_over_1e_6=audit["native_relative"]-1e-6,
        projection_stability_pass=stable,
        numerical_equation_pass=bool(equation),
        field_reconstruction_pass=bool(field_pass),
        power_check_pass=bool(power_pass),
        G_field_error=dict(
            relative=physical["G_field_error"], denominator=physical["d_ref"]
        ),
        audit=audit,
        errors=errors,
        channels=channels,
        raw_physics=physical["physics"],
        region_field_errors=physical["region_field_errors"],
        norm_identity=physical["norm_identity"],
        norm_identities_three_fields=identities,
        V5_G_pythagorean=py,
        q30_to_q15_relative=physical["q30_to_q15_relative"],
        energy_closure_absolute=energy,
        absorption_balance_volume_absolute=absorption,
        max_channel_power_absolute=float(powers),
        power_differences=comp["power_absolute_differences"],
        total_operator_counts=counts,
        unique_main_starts=1,
        neural_increment="NOT_DEMONSTRATED_REFERENCE_EXPOSED_FEATURES",
        **POLICY,
    )
    write("gate_decisions_v6.json", gate)
    metrics = dict(
        retained_rank=int(sum(keep)),
        QR_reconstruction_relative=float(qr),
        QR_orthogonality_F=float(orth),
        small_R_SVD_pair=float(svd_pair),
        retained_optimality=float(opt),
        rho=float(rho),
        residual_projection_defect=float(projection_defect),
        old_G_inverse_relative=float(map_inverse),
        actual_network_Euclidean=float(map_E),
        actual_network_G=float(map_G),
        original_native_pair=float(A_pair),
        By_AQy_relative=combinations,
        independent_action_counts=packet.counts,
        independent_G_columns=G.count,
    )
    write(
        "residual_readout_projection_v6.json",
        dict(
            schema="task42extra.residual-readout-projection.v6",
            source_sha=fit["source_sha"],
            raw=fit["files"]["projection"],
            main=r["projection"],
            independent=metrics,
            hidden_buffers_exactly_unchanged=hidden_exact,
            **POLICY,
        ),
    )
    write(
        "residual_readout_checks_v6.json",
        dict(
            schema="task42extra.residual-readout-checks.v6",
            targeted=read(RECORDS / "targeted_tests_v6.json"),
            real_T0=indices[STAGES[0]]["result"],
            actual_source_sha=indices[STAGES[0]]["source_sha"],
            **POLICY,
        ),
    )
    write(
        "run_index_v6.json",
        dict(
            schema="task42extra.run-index.v6",
            stages={
                s: dict(
                    source_sha=x["source_sha"],
                    run_directory=x["run_directory"],
                    files=x["files"],
                    index_sha256=sha(index(s)[1]),
                )
                for s, x in indices.items()
            },
            main_start_count=1,
            source_is_documentation_HEAD=False,
            **POLICY,
        ),
    )
    rows = []
    for name, g, cr in [
        (
            "V4_FINAL",
            old_gates[4],
            index("v4_fit_compare_only")[0]["result"]["physics"]["records"][
                "FEINN-REFERENCE-FIT-G-ADAM500-REPLAY"
            ],
        ),
        (
            "V5_G_OPTIMAL",
            old_gates[5],
            index("v5_readout_compare_only")[0]["result"]["physics"]["records"][
                "FEINN-FROZEN-HIDDEN-READOUT-G"
            ],
        ),
        (ROUTE, gate, candidate),
    ]:
        e = g["errors"]
        rows.append(
            dict(
                route=name,
                G_field_error=g["G_field_error"]["relative"],
                scattered_E_L2=e["scattered_L2"]["relative"],
                scattered_scaled_curl=e["scattered_scaled_curl"]["relative"],
                total_E_L2=e["total_L2"]["relative"],
                total_scaled_curl=e["total_scaled_curl"]["relative"],
                native=g["audit"]["native_relative"],
                augmented=g["audit"]["augmented_relative"],
                R=cr["port"]["R_total"],
                T=cr["port"]["T_total"],
                A_balance=cr["port"]["A_balance"],
                A_volume=cr["volume"]["A_volume_total"],
                energy_closure=g["energy_closure_absolute"],
                max_channel_power=g["max_channel_power_absolute"],
            )
        )
    with (RECORDS / "residual_readout_comparison_v6.csv").open(
        "w", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    resource = resource_update(indices)
    print(
        json.dumps(
            dict(
                status="INDEPENDENT_V6_AUDIT_COMPLETE",
                category=category,
                rho=float(rho),
                G_error=physical["G_field_error"],
                counts=counts,
                batch_seconds=resource["V6_batch_seconds"],
            )
        )
    )


if __name__ == "__main__":
    main()
