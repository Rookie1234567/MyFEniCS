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


def qualification(record, *, joint_ports=False):
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
    if joint_ports:
        value = d.get("zero_carrier_old_rhs_relative")
        if type(value) not in (int,float) or not 0 <= value <= 1e-10:
            reasons.append("zero_carrier_old_rhs")
        plane = d.get("plane",[])
        if len(plane) != 2 or {p.get("z_sign") for p in plane} != {-1,1}:
            reasons.append("bidirectional_air_flux")
        for p in plane:
            f = p.get("physical_flux",{})
            if f.get("channels") != 36 or f.get("physical_E_cross_H") is not True:
                reasons.append("physical_flux_missing_or_proxy")
            for name,limit in (("independent_Poynting_vs_port_max_absolute",1e-12),
                               ("all_mode_vs_analytic_max_absolute",1e-6),
                               ("reflected",1e-5),("energy_closure",1e-5)):
                v = f.get(name)
                if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=limit:
                    reasons.append("air_flux_"+name)
            if abs(f.get("transmitted",0)-1)>1e-5:
                reasons.append("air_flux_transmitted")
            for key in ("per_mode_physical_power","per_mode_analytic_power"):
                values = f.get(key,[])
                if len(values)!=36 or any(type(v) not in (float,int) or not math.isfinite(v)
                                         or v<0 for v in values):
                    reasons.append("air_flux_all_modes")
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


def joint_port_qualification(record):
    """Rebuild V21 admission from measurements, never just a passed flag."""
    base = qualification(record.get("base",{}),joint_ports=True)
    failures = list(base["failed"])
    trace = record.get("trace",{})
    rows = trace.get("rows",[])
    if {(r.get("degree"),r.get("facet")) for r in rows} != {
            (p,f) for p in (3,4,6) for f in range(6)} or len(rows)!=18:
        failures.append("trace_coverage")
    if not any(r.get("actual_cell_permutation",0)!=0 for r in rows):
        failures.append("actual_orientation")
    for r in rows:
        if (len(r.get("nodal_and_integral_relative",[]))!=2
                or any(not isinstance(v,(float,int)) or not math.isfinite(v)
                       or not 0<=v<=1e-10 for v in r.get("nodal_and_integral_relative",[]))
                or r.get("omitted_boundary_dof_difference",0)<=1e-10):
            failures.append("trace_moment_or_negative_control")
    affected = record.get("affected_ports",[])
    if len(affected)!=3 or {r.get("degree") for r in affected}!={3,4,6}:
        failures.append("affected_degree_coverage")
    for r in affected:
        for name,limit in (("quadrature_15_30",1e-8),("physical_rhs",1e-10),
                           ("condensed_action_recovery",1e-10),
                           ("accurate_vs_independent_decimal",1e-10)):
            v = r.get(name)
            if type(v) not in (float,int) or not math.isfinite(v) or not 0<=v<=limit:
                failures.append(name)
        samples = r.get("physical_ports",{}).get("samples",[])
        if len(samples)!=3 or any(len(s)!=3 or any(not 0<=v<=1e-10 for v in s) for s in samples):
            failures.append("physical_ports")
        if (r.get("generic_nonzero_interior_port_rejected") is not True
                or r.get("nonzero_internal_and_port_rhs") is not True
                or r.get("omitted_boundary_dof_negative",0)<=1e-10
                or r.get("native_action",{}).get("status")!="PASS"):
            failures.append("nonzero_and_negative_controls")
    return dict(passed=not failures,failed=failures,base_checker=base,
                complete_physical_air_flux_required=True)


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

    allowed = ("O3", "E3", "E4", "O6")
    if set(observables) != set(algebra) or not set(observables) <= set(allowed):
        raise ValueError("RETAINED_ROLE_COVERAGE_INCONSISTENT")
    roles = tuple(r for r in allowed if r in observables)
    missing = [r for r in allowed if r not in roles]
    physics = {r: physics_from_arrays(observables[r]) for r in roles}
    equations = {r: solved(algebra[r], reference=r == "O6") for r in roles}
    reference = (
        "O6" in roles
        and equations["O6"]["passed"]
        and physics["O6"]["raw_valid"]
        and physics["O6"]["energy_closure"] <= 1e-5
    )
    pairs = [
        (a, b)
        for a, b in [(r, "O6") for r in ("O3", "E3", "E4")]
        + [("E3", "E4"), ("O3", "E3")]
        if a in roles and b in roles
    ]
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
            or not np.isfinite(second).all()
            or np.min(second) < 0
        ):
            raise ValueError("COMMON_INTEGRALS_INVALID")
        threshold = 1e-3 if b == "E4" else 1e-4
        fields = np.sqrt(first[0, :, 0]) / np.maximum(np.sqrt(first[0, :, 1]), 1e-12)
        mode_alignment = align_physical_modes(observables[a], observables[b])
        complex_errors, mode_errors = {}, {}
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
            if name in (
                "total_projection",
                "scattered_projection",
                "outgoing_origin",
                "outgoing_boundary",
            ):
                ref = ref[mode_alignment]
                mode_errors[name] = complex_mode_differences(
                    observables[a][name], ref, observables[a]["mode_keys"]
                )
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
                    - np.asarray(physics[b]["per_level_power"])[mode_alignment]
                )
            )
        )
        drift = float(np.max(abs(second - first) / np.maximum(abs(second), 1e-24)))
        fieldpass = bool(
            np.max(fields) <= threshold
            and max(complex_errors.values()) <= threshold
            and all(v["max_relative"] <= threshold for v in mode_errors.values())
        )
        powerpass = (
            max(powers.values()) <= 1e-5
            and level <= 1e-6
            and physics[a]["energy_closure"] <= 1e-5
        )
        results[key] = dict(
            field_relative=fields.tolist(),
            complex_relative=complex_errors,
            per_mode_complex=mode_errors,
            modes_aligned_by_physical_key=True,
            power_absolute=powers,
            per_level_max_absolute=level,
            quadrature_drift=drift,
            field_passed=fieldpass,
            power_passed=bool(powerpass),
            qualified=bool(
                (
                    reference
                    if b == "O6"
                    else b == "E4"
                    and equations[b]["passed"]
                    and physics[b]["raw_valid"]
                    and physics[b]["energy_closure"] <= 1e-5
                )
                and equations[a]["passed"]
                and physics[a]["raw_valid"]
                and fieldpass
                and powerpass
                and drift <= 1e-8
            ),
        )
    return dict(
        schema="fixed_phase.independent-comparison.v1",
        coverage="COMPLETE" if not missing else "PARTIAL",
        missing_roles=missing,
        physics=physics,
        equations=equations,
        reference_qualified=bool(reference),
        comparisons=results,
        no_solver_calls=True,
        neural_gain="NOT_TESTED",
        target_qualified=False,
    )


def saved_port_recovery(native, state):
    """Independent raw diagonal-port/affine audit; no FE action or solve."""
    import numpy as np

    for key in (
        "H",
        "dp",
        "dr",
        "dv",
        "gp",
        "masters",
        "background",
        "background_alpha",
    ):
        if key not in native:
            raise ValueError("RAW_PORT_NATIVE_INCOMPLETE")
    required = {
        "c_scattered",
        "c_total",
        "alpha_scattered",
        "alpha_total",
        "background",
        "background_alpha",
        "masters",
    }
    if set(state) != required:
        raise ValueError("RAW_PORT_STATE_INCOMPLETE")
    H = native["H"]
    c = state["c_scattered"]
    alpha = state["alpha_scattered"]
    if (
        H.shape != alpha.shape
        or c.shape != (len(native["masters"]),)
        or c.dtype != np.complex128
        or alpha.dtype != np.complex128
        or not np.isfinite(c).all()
        or not np.isfinite(alpha).all()
        or not np.isfinite(H).all()
        or np.any(H <= 0)
    ):
        raise ValueError("RAW_PORT_STATE_LAYOUT")
    if not np.array_equal(state["masters"], native["masters"]):
        raise ValueError("RAW_PORT_MASTER_ORDER")
    if (
        not np.array_equal(state["background"], native["background"])
        or not np.array_equal(state["background_alpha"], native["background_alpha"])
        or not np.array_equal(state["c_total"], c + state["background"])
        or not np.array_equal(state["alpha_total"], alpha + state["background_alpha"])
    ):
        raise ValueError("RAW_PORT_AFFINE_BACKGROUND")
    if (
        native["dp"].shape != native["dr"].shape
        or native["dp"].shape != native["dv"].shape
        or np.any(native["dp"] < 0)
        or np.any(native["dp"] >= len(H))
        or np.any(native["dr"] < 0)
        or np.any(native["dr"] >= len(c))
        or not np.isfinite(native["dv"]).all()
        or not np.isfinite(native["gp"]).all()
    ):
        raise ValueError("RAW_PORT_MAP_INVALID")
    d = np.zeros(len(H), complex)
    np.add.at(d, native["dp"], native["dv"] * c[native["dr"]])
    expected = (d + native["gp"]) / H
    original_relative = float(
        np.linalg.norm(expected - alpha) / max(np.linalg.norm(alpha), 1e-12)
    )
    return dict(
        original_port_recovery_relative=original_relative,
        finite=True,
        master_order_exact=True,
        affine_exact=True,
        no_FE_or_solver_calls=True,
    )


def interior_port_support(arrays):
    """Explain a saved condensation precondition failure without dropping terms."""
    import numpy as np

    masters = arrays["masters"]
    interior = np.unique(arrays["idofs"])
    ids = np.searchsorted(masters, interior)
    if np.any(ids >= len(masters)) or not np.array_equal(masters[ids], interior):
        raise ValueError("INTERIOR_MASTER_IDENTITY")
    result = {}
    for row, value in (("br", "bv"), ("dr", "dv")):
        if (
            arrays[row].shape != arrays[value].shape
            or not np.isfinite(arrays[value]).all()
        ):
            raise ValueError("INTERIOR_PORT_LAYOUT")
        mask = np.isin(arrays[row], ids)
        values = arrays[value][mask]
        whole = float(np.linalg.norm(arrays[value]))
        result[value] = dict(
            stored_interior_entries=len(values),
            exact_nonzeros=int(np.count_nonzero(values)),
            exact_zeros=int(np.sum(values == 0)),
            max_absolute=float(abs(values).max(initial=0)),
            norm=float(np.linalg.norm(values)),
            all_entry_norm=whole,
            norm_fraction=float(np.linalg.norm(values) / max(whole, 1e-300)),
            unique_internal_rows=len(np.unique(arrays[row][mask])),
        )
    return dict(
        internal_independent_dofs=len(ids),
        blocks=result,
        no_terms_removed=True,
        no_FE_or_action_or_factor_or_solve=True,
        accuracy_or_recovery_qualified=False,
    )


def align_physical_modes(left, right):
    """Key/side/polarization/reference-plane alignment, with no phase fitting."""
    import numpy as np

    keys = [tuple(row) for row in right["mode_keys"]]
    lookup = {key: j for j, key in enumerate(keys)}
    if len(lookup) != 340:
        raise ValueError("MODE_ALIGNMENT_DUPLICATE_OR_INCOMPLETE")
    try:
        order = np.asarray([lookup[tuple(row)] for row in left["mode_keys"]])
    except KeyError as error:
        raise ValueError("MODE_ALIGNMENT_PHYSICAL_KEYS") from error
    for name in ("mode_k", "mode_e", "mode_boundary_z"):
        if (
            name not in left
            or name not in right
            or not np.array_equal(left[name], right[name][order])
        ):
            raise ValueError("MODE_ALIGNMENT_PHYSICAL_IDENTITY:" + name)
    return order


def complex_mode_differences(candidate, reference, keys):
    """All 340 complex entries; denominator=max(abs(reference),1e-12)."""
    import numpy as np

    if (
        candidate.shape != (340,)
        or reference.shape != (340,)
        or candidate.dtype != np.complex128
        or reference.dtype != np.complex128
        or not np.isfinite(candidate).all()
        or not np.isfinite(reference).all()
    ):
        raise ValueError("FULL_COMPLEX_MODE_LAYOUT")
    absolute = abs(candidate - reference)
    denominator = np.maximum(abs(reference), 1e-12)
    relative = absolute / denominator
    worst = int(np.argmax(relative))
    return dict(
        count=340,
        max_relative=float(relative[worst]),
        max_absolute=float(absolute.max()),
        near_zero_count=int(np.sum(abs(reference) < 1e-12)),
        natural_floor=1e-12,
        denominator_definition="max(abs(reference_j),1e-12), no phase fit",
        worst_key=keys[worst].tolist(),
        worst_absolute=float(absolute[worst]),
        worst_reference_absolute=float(abs(reference[worst])),
        worst_denominator=float(denominator[worst]),
    )
