"""Pure, independent Gate recomputation from complete original measurements."""

import math

LIMITS = dict.fromkeys(
    (
        "zero_carrier",
        "physical_volume",
        "physical_B_D_H",
        "physical_rhs",
        "native_adjoint_and_port_load",
        "nonzero_port_rhs",
        "manufactured_original_weak",
        "manufactured_port",
        "manufactured_solve_residual",
        "manufactured_solve_field",
        "manufactured_recovery",
        "physical_floquet_x_y_corner",
        "physical_H_manufactured",
        "manufactured_Gauss_weak",
        "physical_background",
        "total_scattered_affine_closure",
        "air_plane_residual",
    ),
    1e-10,
)
LIMITS.update(
    quadrature_15_30=1e-8, air_plane_fields_channels=1e-4, air_plane_power=1e-6
)


def qualification(record):
    reasons = []
    if record.get("schema") != "fixed_phase.qualification.v1":
        reasons.append("schema")
    raw = record.get("gates", {})
    if set(raw) != set(LIMITS):
        reasons.append("incomplete_or_extra_gates")
    for name, limit in LIMITS.items():
        value = raw.get(name)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value < 0
            or value > limit
        ):
            reasons.append(name)
    d = record.get("details", {})
    if not abs(d.get("ky", 0)) > 0:
        reasons.append("nonzero_ky")
    families = d.get("all_dof_families", {})
    if set(families) != {"1", "2", "3"} or any(v <= 0 for v in families.values()):
        reasons.append("complete_edge_face_internal")
    negative = d.get("negative_controls", {})
    for key in (
        "omitted_curl_difference",
        "double_phase_difference",
        "omitted_internal_rhs_difference",
        "incorrect_physical_ports_difference",
        "old_background_difference",
    ):
        value = negative.get(key, 0)
        if not math.isfinite(value) or value <= 1e-10:
            reasons.append(key)
    if d.get("no_producer_F_read_in_physical_audit") is not True:
        reasons.append("independent_physical_kernel")
    modes = d.get("identity", {}).get("modes", [])
    try:
        keys = {(m["side"], m["m"], m["n"], m["polarization"]) for m in modes}
    except (KeyError, TypeError):
        keys = set()
    expected = {
        (side, m, n, pol)
        for side in ("top", "bottom")
        for m in range(-1, 2)
        for n in range(-1, 2)
        for pol in ("s", "p")
    }
    if len(modes) != 36 or keys != expected:
        reasons.append("complete_fixture_mode_keys")
    return dict(
        status="PASS" if not reasons else "QUALIFICATION_FAILED",
        passed=not reasons,
        failed=reasons,
        limits=LIMITS,
        recomputed_from_original_measurements=True,
    )


def solved(record, *, reference=False):
    limits = dict(
        native_relative=1e-10 if reference else 1e-6,
        augmented_relative=1e-10 if reference else 1e-6,
        original_total_augmented_relative=1e-10 if reference else 1e-6,
        independent_physical_weak=1e-10 if reference else 1e-6,
        recovery=1e-10,
    )
    failed = [
        k
        for k, v in limits.items()
        if k not in record
        or type(record[k]) not in (int, float)
        or not math.isfinite(record[k])
        or not 0 <= record[k] <= v
    ]
    if record.get("channels") != 340 or record.get("full_FE_recovered") is not True:
        failed.append("full_field_and_ports")
    return dict(
        passed=not failed,
        failed=failed,
        limits=limits,
        status="ALGEBRA_QUALIFIED" if not failed else "ALGEBRA_FAILED",
    )


def physics_from_arrays(z):
    """Recompute all powers and E/curl/H norms from retained physical arrays."""
    import numpy as np

    required = (
        "quadrature_weights_nm3",
        "total_E",
        "scattered_E",
        "total_curl",
        "scattered_curl",
        "total_H",
        "scattered_H",
        "cell_epsilon",
        "k0",
        "mu_r",
        "incident_power",
        "port_area",
        "mode_keys",
        "mode_k",
        "mode_e",
        "outgoing_boundary",
        "per_level_power",
        "physical_field_norms",
    )
    if any(k not in z for k in required):
        raise ValueError("INCOMPLETE_RAW_PHYSICS")
    if len(z["mode_keys"]) != 340 or len({tuple(k) for k in z["mode_keys"]}) != 340:
        raise ValueError("INCOMPLETE_OR_DUPLICATE_MODE_KEYS")
    expected = {
        (s, str(m), str(n), p)
        for s in ("top", "bottom")
        for m in range(-8, 9)
        for n in range(-2, 3)
        for p in ("s", "p")
    }
    if {tuple(k) for k in z["mode_keys"]} != expected:
        raise ValueError("INCORRECT_PHYSICAL_MODE_KEYS")
    w = z["quadrature_weights_nm3"]
    k0 = float(z["k0"])
    mu = complex(z["mu_r"])
    names = ("total_E", "total_curl", "scattered_E", "scattered_curl")
    norms = np.asarray(
        [
            np.sqrt(np.sum(w * np.sum(abs(z[k]) ** 2, axis=2)))
            / (k0 if "curl" in k else 1)
            for k in names
        ]
    )
    nh = float(
        np.linalg.norm(norms - z["physical_field_norms"])
        / max(np.linalg.norm(norms), 1e-30)
    )
    hpair = max(
        float(
            np.linalg.norm(z[k + "_H"] - z[k + "_curl"] / (1j * k0 * mu))
            / max(np.linalg.norm(z[k + "_H"]), 1e-30)
        )
        for k in ("total", "scattered")
    )
    av = float(
        0.5
        * k0
        * np.sum(
            np.asarray(z["cell_epsilon"]).imag[:, None]
            * w
            * np.sum(abs(z["total_E"]) ** 2, axis=2)
        )
        / float(z["incident_power"])
    )
    e = z["mode_e"] * z["outgoing_boundary"][:, None]
    h = np.cross(z["mode_k"], e) / (k0 * mu)
    normal = np.where(z["mode_keys"][:, 0] == "top", 1, -1)
    power = (
        np.maximum(0.5 * np.real(np.cross(e, h.conj()))[:, 2] * normal, 0)
        * float(z["port_area"])
        / float(z["incident_power"])
    )
    power_pair = float(np.max(abs(power - z["per_level_power"])))
    R = float(np.sum(power[z["mode_keys"][:, 0] == "top"]))
    T = float(np.sum(power[z["mode_keys"][:, 0] == "bottom"]))
    r00 = {
        p: float(
            np.sum(
                power[
                    (z["mode_keys"][:, 0] == "top")
                    & (z["mode_keys"][:, 1] == "0")
                    & (z["mode_keys"][:, 2] == "0")
                    & (z["mode_keys"][:, 3] == p)
                ]
            )
        )
        for p in ("s", "p")
    }
    return dict(
        R_total=R,
        T_total=T,
        A_balance=1 - R - T,
        A_volume=av,
        R00_s=r00["s"],
        R00_p=r00["p"],
        R00_total=sum(r00.values()),
        energy_closure=abs(R + T + av - 1),
        norms=norms.tolist(),
        norm_pair_relative=nh,
        H_identity_relative=hpair,
        per_level_power_pair_absolute=power_pair,
        raw_valid=bool(
            max(nh, hpair) <= 1e-10 and power_pair <= 1e-12 and np.isfinite(norms).all()
        ),
        per_level_power=power.tolist(),
    )


def compare_from_arrays(integrals, observables, algebra):
    """Producer status/relative errors are ignored: Gate is independently rebuilt."""
    import numpy as np

    roles = ("O3", "E3", "E4", "O6")
    if set(observables) != set(roles) or set(algebra) != set(roles):
        raise ValueError("FOUR_ROLES_REQUIRED")
    physics = {r: physics_from_arrays(observables[r]) for r in roles}
    equations = {r: solved(algebra[r], reference=r == "O6") for r in roles}
    reference = (
        equations["O6"]["passed"]
        and physics["O6"]["raw_valid"]
        and physics["O6"]["energy_closure"] <= 1e-5
    )
    pairs = [(r, "O6") for r in ("O3", "E3", "E4")] + [("E3", "E4")]
    expected = {f"{a}_vs_{b}_q{q}" for a, b in pairs for q in (15, 30)}
    if set(integrals) != expected:
        raise ValueError("COMMON_INTEGRAL_COVERAGE_INCOMPLETE")
    results = {}
    for a, b in pairs:
        key = f"{a}_vs_{b}"
        first = integrals[key + "_q15"]
        second = integrals[key + "_q30"]
        if (
            first.shape != (6, 4, 3)
            or second.shape != first.shape
            or not np.isfinite(first).all()
            or np.min(first) < 0
        ):
            raise ValueError("COMMON_INTEGRALS_INVALID")
        threshold = 1e-3 if b == "E4" else 1e-4
        fields = np.sqrt(first[0, :, 0]) / np.maximum(np.sqrt(first[0, :, 1]), 1e-12)
        complex_errors = {}
        for name in (
            "selected_total_E",
            "selected_total_H",
            "selected_scattered_E",
            "selected_scattered_H",
            "total_projection",
            "scattered_projection",
            "outgoing_origin",
            "outgoing_boundary",
        ):
            ref = observables[b][name]
            diff = observables[a][name] - ref
            complex_errors[name] = float(
                np.linalg.norm(diff) / max(np.linalg.norm(ref), 1e-12)
            )
            if name.startswith("selected"):
                for j in range(6):
                    complex_errors[name + "_point_" + str(j)] = float(
                        np.linalg.norm(diff[j]) / max(np.linalg.norm(ref[j]), 1e-12)
                    )
        powers = {
            k: abs(physics[a][k] - physics[b][k])
            for k in (
                "R_total",
                "T_total",
                "A_balance",
                "A_volume",
                "R00_s",
                "R00_p",
                "R00_total",
            )
        }
        level = float(
            np.max(
                abs(
                    np.asarray(physics[a]["per_level_power"])
                    - physics[b]["per_level_power"]
                )
            )
        )
        drift = float(np.max(abs(second - first) / np.maximum(abs(second), 1e-24)))
        fieldpass = bool(
            np.max(fields) <= threshold and max(complex_errors.values()) <= threshold
        )
        powerpass = (
            max(powers.values()) <= 1e-5
            and level <= 1e-6
            and physics[a]["energy_closure"] <= 1e-5
        )
        results[key] = dict(
            field_relative=fields.tolist(),
            complex_relative=complex_errors,
            power_absolute=powers,
            per_level_max_absolute=level,
            quadrature_drift=drift,
            field_passed=fieldpass,
            power_passed=bool(powerpass),
            qualified=bool(
                reference
                and equations[a]["passed"]
                and physics[a]["raw_valid"]
                and fieldpass
                and powerpass
                and drift <= 1e-8
            ),
        )
    return dict(
        schema="fixed_phase.independent-comparison.v1",
        physics=physics,
        equations=equations,
        reference_qualified=bool(reference),
        comparisons=results,
        no_solver_calls=True,
        neural_gain="NOT_TESTED",
        target_qualified=False,
    )
