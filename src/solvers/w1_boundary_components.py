"""Small opt-in W1 adapter around frozen native mathematical modules.

The caller selects the frozen module root before loading this file. No
global Maxwell matrix/factor, owner mesh, AUTO inventory or NN is built.
"""

import numpy as np


def consumers(q):
    if type(q) is not int or q != 60:
        raise ValueError("W1_ONLY_FIXED_Q60")
    return {
        name: q
        for name in (
            "facet_integral",
            "boundary_action",
            "B",
            "D",
            "modal_rhs",
            "internal_recovery",
            "direct_witness",
            "saved_checker",
        )
    }


def relative_terms(candidate, reference):
    """Original reference norm; no fitted floor or evanescent-mode deletion."""
    candidate, reference = np.asarray(candidate), np.asarray(reference)
    if candidate.shape != reference.shape or not all(
        np.isfinite(a).all() for a in (candidate, reference)
    ):
        raise ValueError("W1_FINITE_MATCHED_ARRAYS_REQUIRED")
    numerator, norm = (
        float(np.linalg.norm(candidate - reference)),
        float(np.linalg.norm(reference)),
    )
    denominator = max(norm, np.finfo(np.float64).tiny)
    return {
        "numerator": numerator,
        "reference_norm": norm,
        "denominator": denominator,
        "relative": numerator / denominator,
        "near_zero": bool(norm <= np.finfo(float).tiny),
    }


def physical_modes(rows):
    """Retain the original H and original origin convention of every mode."""
    from src.solvers.directional_boundary import zvalue

    out = []
    errors = {"H": 0.0, "traction": 0.0, "transversality": 0.0, "dispersion": 0.0}
    k0 = 2 * np.pi / 0.7
    silicon = 0.9998851703688496 + 4.3236152269189515e-6j
    for row in rows:
        k, e, t = [
            np.asarray([zvalue(x) for x in row[name]], np.complex128)
            for name in ("k_vector", "e_vector", "traction_vector")
        ]
        side = row["side"]
        z = 130.0 if side == "top" else -10.0
        normal = np.array([0.0, 0.0, 1.0 if side == "top" else -1.0])
        h = float(row["projection_denominator"])
        reconstructed = (
            50 * 25 * np.vdot(e[:2], e[:2]).real * abs(np.exp(1j * k[2] * z)) ** 2
        )
        errors["H"] = max(errors["H"], abs(reconstructed - h) / h)
        errors["traction"] = max(
            errors["traction"],
            relative_terms(t, np.cross(1j * np.cross(k, e), normal))["relative"],
        )
        errors["transversality"] = max(
            errors["transversality"],
            float(
                abs(k @ e)
                / max(np.linalg.norm(k) * np.linalg.norm(e), np.finfo(float).tiny)
            ),
        )
        expected = k0**2 * (1 if side == "top" else silicon**2)
        errors["dispersion"] = max(
            errors["dispersion"], float(abs(k @ k - expected) / abs(expected))
        )
        out.append({**row, "reference_plane_nm": z})
    if max(errors.values()) > 1e-10:
        raise ValueError("W1_ORIGINAL_PHYSICS_MISMATCH:" + str(errors))
    return out, errors


def centered_phase_pair(k, shift):
    """Centered→ledger x_ledger=x_centered+shift; H unchanged if dz=0."""
    k, shift = np.asarray(k, np.complex128), np.asarray(shift, float)
    phase = np.exp(1j * (k @ shift))
    if not np.isfinite(phase).all() or np.any(abs(phase) == 0):
        raise ValueError("W1_COORDINATE_PHASE_NOT_REVERSIBLE")
    return phase, 1 / phase


def physical_incidence(modes):
    """Original 1-degree grazing/phi0/s incoming wave, no manufactured load."""
    from src.solvers.directional_boundary import zvalue

    selected = [
        i
        for i, m in enumerate(modes)
        if [m["side"], m["m"], m["n"], m["polarization"]] == ["top", 0, 0, "s"]
    ]
    if len(selected) != 1:
        raise ValueError("W1_UNIQUE_ORIGINAL_INCIDENT_MODE_REQUIRED")
    index = selected[0]
    kout = np.array([zvalue(z) for z in modes[index]["k_vector"]])
    expected = (
        2 * np.pi / 0.7 * np.array([np.cos(np.deg2rad(1)), 0, np.sin(np.deg2rad(1))])
    )
    e = np.array([zvalue(z) for z in modes[index]["e_vector"]])
    if (
        relative_terms(kout, expected)["relative"] > 1e-10
        or relative_terms(e, [0, 1, 0])["relative"] > 1e-10
    ):
        raise ValueError("W1_ORIGINAL_INCIDENT_IDENTITY")
    kin = kout.copy()
    kin[2] = -kin[2]
    alpha = np.zeros(len(modes), np.complex128)
    # Natural weak load: t_in - DtN(E_in) = 2*B_out*phase_ratio for TE.
    alpha[index] = 2 * np.exp(1j * (kin[2] - kout[2]) * 130)
    return kin, kout, e, alpha


def incident_boundary_packet(polynomial, side, modes, J, origin, oracle, q=60):
    """Independent incoming/background natural-load witnesses on actual face."""
    kin, kout, e, alpha = physical_incidence(modes)
    if side != "top":
        raise ValueError("W1_TOP_INCOMING_REFERENCE_PLANE")
    normal = np.array([0, 0, 1])
    shift = np.array([25, 12.5, 0])

    def integrals(k, pos):
        identity = oracle.facet_identity(polynomial, side, k, J, pos)
        return (
            polynomial.integral_native(side, k, J, pos, q),
            oracle.integrate_receiver_facet(
                polynomial, side, k, J, pos, expected=identity
            ),
        )

    ci, ri = integrals(kin, origin)
    co, ro = integrals(kout, origin)
    ai, ar = integrals(kin, origin + shift)
    ao, aor = integrals(kout, origin + shift)
    t_in, t_out = (
        np.cross(1j * np.cross(kin, e), normal),
        np.cross(1j * np.cross(kout, e), normal),
    )
    z = float(origin[2] + (J[2, 2] if side == "top" else 0))
    delta = np.exp(1j * (kin[2] - kout[2]) * z)
    rev = np.exp(-1j * (kin @ shift))
    center = ci @ t_in[:2] - (co @ t_out[:2]) * delta
    reference = ri @ t_in[:2] - (ro @ t_out[:2]) * delta
    absolute = (ai @ t_in[:2] - (ao @ t_out[:2]) * delta) * rev
    bottom = [
        m
        for m in modes
        if (m["side"], m["m"], m["n"], m["polarization"]) == ("bottom", 0, 0, "s")
    ]
    if len(bottom) != 1:
        raise ValueError("W1_BACKGROUND_BOTTOM_INCIDENT_KEY")
    from src.solvers.directional_boundary import zvalue

    kb = np.array([zvalue(z) for z in bottom[0]["k_vector"]])
    eb = np.array([zvalue(z) for z in bottom[0]["e_vector"]])
    if (
        relative_terms(kb[:2], kin[:2])["relative"] > 1e-10
        or relative_terms(eb, e)["relative"] > 1e-10
    ):
        raise ValueError("W1_BACKGROUND_TRANSVERSE_IDENTITY")
    # Flat air/Si interface at z=0: a background boundary witness, not a
    # new reference for the 3-D grating or its volume contrast source.
    r = (kout[2] + kb[2]) / (kout[2] - kb[2])
    transmission = 1 + r
    bg_traction = ci @ t_in[:2] + (co @ t_out[:2]) * r
    bg_dtn = (co @ t_out[:2]) * (delta + r)
    bg_absolute = (
        (ai @ t_in[:2] + (ao @ t_out[:2]) * r) - (ao @ t_out[:2]) * (delta + r)
    ) * rev
    # These are the physical incoming boundary source, not the grating's
    # volume contrast source nor a solved 3-D scattered field.
    return {
        "rhs_center": center,
        "rhs_reference": reference,
        "rhs_absolute": absolute,
        "rhs_absolute_reference": (ar @ t_in[:2] - (aor @ t_out[:2]) * delta) * rev,
        "rhs_modal": -co @ t_out[:2] * (2 * delta),
        "k_in": kin,
        "k_out": kout,
        "e_in": e,
        "origin_center": origin,
        "origin_absolute": origin + shift,
        "reference_plane_nm": np.array(z),
        "physical_alpha": alpha,
        "background_rhs_center": bg_traction - bg_dtn,
        "background_rhs_absolute": bg_absolute,
        "background_r": np.array(r),
        "background_t": np.array(transmission),
        "background_bottom_k": kb,
        "background_interface_E_jump": np.array(1 + r - transmission),
        "background_interface_curl_jump": np.array(
            kin[2] + kout[2] * r - kb[2] * transmission
        ),
        "scope": np.array("PHYSICAL_TOP_INCIDENT_BOUNDARY_RHS_NO_VOLUME_SOURCE"),
    }


def probe_actions(layout, modes, q, *, action_factory=None):
    """Real frozen action, adjoint and modal-load API with explicit q60."""
    consumers(q)
    if action_factory is None:
        from src.solvers.directional_boundary import DirectionalBoundaryAction

        action_factory = DirectionalBoundaryAction
    action = action_factory(
        layout, modes, q, face_inventory=(("top", 100, 1), ("bottom", 100, 1))
    )
    trace = np.asarray(np.exp(0.137j * np.arange(layout.rows)), np.complex128)
    dual = np.asarray(np.exp(-0.211j * np.arange(layout.rows)), np.complex128)
    alpha = np.asarray(
        np.exp(0.07j * np.arange(len(modes))) / np.sqrt(len(modes)), np.complex128
    )
    result = {
        "trace": trace,
        "dual": dual,
        "alpha": alpha,
        "components": action.project_components(trace),
        "recover": action.recover(trace),
        "apply": action.apply(trace),
        "adjoint": action.apply(dual, adjoint=True),
        "modal_rhs": action.modal_rhs(alpha),
    }
    if modes and isinstance(modes[0], dict):
        _, _, _, physical_alpha = physical_incidence(modes)
        result.update(
            physical_alpha=physical_alpha, physical_rhs=action.modal_rhs(physical_alpha)
        )
    return result


def reference_actions(layout, modes, integrals, indices, state, accumulators):
    """Independent saved local integral contractions, retaining original H."""
    from src.solvers.directional_boundary import zvalue

    for integral, index in zip(integrals, indices, strict=True):
        mode = modes[index]
        side = mode["side"]
        rows = layout.maps[side][100, 1]
        phase = layout.weights[side][100, 1]
        face_integral = integral[layout.polynomial.active[side]]
        e = np.array([zvalue(v) for v in mode["e_vector"][:2]])
        t = np.array([zvalue(v) for v in mode["traction_vector"][:2]])
        h = mode["projection_denominator"]
        local_trace, local_dual = (
            phase * state["trace"][rows],
            phase * state["dual"][rows],
        )
        projected = face_integral.conj().T @ local_trace
        recovered = np.vdot(e, projected) / h
        B, D = face_integral @ -t, (face_integral @ e).conj() / h
        accumulators["components"][index] = projected
        accumulators["recover"][index] = recovered
        np.add.at(accumulators["apply"], rows, phase.conj() * B * recovered)
        np.add.at(
            accumulators["modal_rhs"], rows, phase.conj() * B * state["alpha"][index]
        )
        if "physical_rhs" in accumulators:
            np.add.at(
                accumulators["physical_rhs"],
                rows,
                phase.conj() * B * state["physical_alpha"][index],
            )
        np.add.at(
            accumulators["adjoint"],
            rows,
            phase.conj() * D.conj() * np.vdot(B, local_dual),
        )


def run_local(spec, modes, layout, *, config, stream=None):
    """Every numerical consumer receives q explicitly; no old runner.run()."""
    if stream is None:
        from src.solvers.task40_w1_local_probe import stream_boundary_correction

        stream = stream_boundary_correction
    consumers(spec["quadrature_degree"])
    degree, side = int(spec["stage"][1]), spec["stage"].split("_")[1]
    ni = 108 if degree == 4 else 450
    dim = 3 * degree * (degree + 1) ** 2
    nt = dim - ni
    # Deterministic manufactured loads test complete recovery, not incidence.
    alpha = np.asarray(
        np.exp(0.17j * np.arange(len(modes))) / np.sqrt(len(modes)), np.complex128
    )
    trace = np.asarray((1 + 0.2j) * np.exp(0.11j * np.arange(nt)), np.complex128)
    interior = np.asarray((0.7 - 0.3j) * np.exp(0.13j * np.arange(ni)), np.complex128)
    i, j = 100, 1
    bounds = (
        (float(layout.x[i]), float(layout.x[i + 1])),
        (float(layout.y[j]), float(layout.y[j + 1])),
        (120.0, 130.0) if side == "top" else (-10.0, 0.0),
    )
    result = stream(
        degree=degree,
        side=side,
        bounds=bounds,
        config=config,
        material_tag=config.tags.air if side == "top" else config.tags.substrate,
        modes=modes,
        mode_alpha=alpha,
        trace_values=trace,
        known_interior_solution=interior,
        boundary_layout=layout,
        face_i=i,
        face_j=j,
        boundary_quadrature_degree=spec["quadrature_degree"],
        batch_modes=64,
    )
    # Historical raw names in the frozen API are labels, not the quadrature.
    arrays = result["arrays"]
    if "small_key_native_carrier_witness" in result:
        arrays["witness_mode_index"] = np.array(
            result["small_key_native_carrier_witness"]["ordered_key_index"]
        )
    arrays.update(
        degree=np.array(degree),
        side=np.array(side),
        quadrature_degree=np.array(60),
        original_H=np.array([m["projection_denominator"] for m in modes])
        if modes and isinstance(modes[0], dict)
        else np.array([]),
        mode_keys=np.array(
            [
                [
                    m["m"],
                    m["n"],
                    0 if m["side"] == "top" else 1,
                    0 if m["polarization"] == "s" else 1,
                ]
                for m in modes
            ],
            dtype=np.int64,
        )
        if modes and isinstance(modes[0], dict)
        else np.array([]),
    )
    for key in list(arrays):
        if "direct_q30" in key:
            arrays[key.replace("direct_q30", "direct_q60")] = arrays.pop(key)
    witness = result.get("small_key_native_carrier_witness", {})
    for key in list(witness):
        if "direct_q30" in key:
            witness[key.replace("direct_q30", "direct_q60")] = witness.pop(key)
    result["consumer_quadrature"] = consumers(spec["quadrature_degree"])
    result["physical_incident_rhs_qualified"] = False
    result["state_purpose"] = "MANUFACTURED_NONZERO_INTERNAL_TRACE_PORT_LOADS"
    return result


def control_layout(*, degree=4):
    """Actual Basix orientation and two non-unit periodic seams, no FE solve."""
    import basix
    from src.solvers.directional_boundary import BoundaryLayout, FacetPolynomial
    from src.solvers.native_boundary_adapter import literal_expansion

    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        degree,
        basix.LagrangeVariant.legendre,
    )
    poly = FacetPolynomial(element)
    phases = (np.exp(0.37j), np.exp(-0.23j))
    layout = BoundaryLayout([-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], poly, phases)
    # Independent topology-based seam check, including the upper-right cell.
    ref, topo = (
        basix.cell.geometry(basix.CellType.hexahedron),
        basix.cell.topology(basix.CellType.hexahedron),
    )
    seam_count = {"x": 0, "y": 0, "corner_cell": 0}
    for side in ("bottom", "top"):
        lookup = {int(d): a for a, d in enumerate(poly.active[side])}
        for i in range(2):
            for j in range(2):
                for edge in topo[1]:
                    edge_index = topo[1].index(edge)
                    ids = element.entity_dofs[1][edge_index]
                    if not ids or ids[0] not in lookup:
                        continue
                    pts = ref[edge]
                    x_edge = pts[0, 0] != pts[1, 0]
                    axis = "y" if x_edge else "x"
                    boundary = (
                        (j + int(pts[0, 1]) == 2)
                        if x_edge
                        else (i + int(pts[0, 0]) == 2)
                    )
                    expected = phases[1 if x_edge else 0] if boundary else 1
                    if not np.all(
                        layout.weights[side][i, j, [lookup[d] for d in ids]] == expected
                    ):
                        raise ValueError("W1_PERIODIC_SEAM_PHASE")
                    if boundary:
                        seam_count[axis] += len(ids)
                        if (i, j) == (1, 1):
                            seam_count["corner_cell"] += len(ids)
    # A literal MPC corner expands once with px*py, and scatters conjugately.
    literal = {
        "master_offsets": np.arange(5),
        "master_rows": np.array([0, 0, 0, 0]),
        "master_dual_coefficients": np.conj(np.array([1, *phases, np.prod(phases)])),
    }
    G = literal_expansion(literal, 4)
    x = np.array([0.7 + 0.9j, 0, 0, 0], np.complex128)
    expected = np.array([1, *phases, np.prod(phases)]) * x[0]
    if relative_terms(G @ x, expected)["relative"] > 1e-14:
        raise ValueError("W1_MPC_EXPANSION_ONCE")
    dual = np.array([0.1 + 0.3j, -0.8j, 0.9 - 0.2j, -0.4 + 0.7j])
    adjoint = abs(np.vdot(dual, G @ x) - np.vdot(G.conj().T @ dual, x))
    # All native column families are included in this orientation test.
    T = np.eye(element.dim)
    element.T_apply(T.ravel(), element.dim, 2097151)
    if (
        np.all(T == np.eye(element.dim))
        or np.linalg.norm(T.T @ T - np.eye(element.dim)) > 1e-12
    ):
        raise ValueError("W1_NATIVE_ORIENTATION_PAIR")
    k = np.array([0.2, -0.3, 0.4j])
    forward, reverse = centered_phase_pair(k, [25, 12.5, 0])
    return {
        "status": "CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE",
        "degree": degree,
        "seams": seam_count,
        "corner_product_phase": True,
        "mpc_adjoint_absolute": float(adjoint),
        "orientation_all_columns": element.dim,
        "coordinate_roundtrip": float(abs(forward * reverse - 1)),
        "bounded_MPC_only": True,
        "full_target_MPC_qualified": False,
        "physical_incident_rhs_qualified": False,
        "PDE_solved": False,
        "arrays": {
            "orientation": T,
            "MPC_expansion": G.toarray(),
            "MPC_state": x,
            "MPC_expanded": G @ x,
            "MPC_expected": expected,
            "MPC_dual": dual,
        },
    }
