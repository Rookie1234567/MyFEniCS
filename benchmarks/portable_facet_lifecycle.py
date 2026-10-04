"""Bounded parameterized local-facet qualification and cold lifecycle.

Numerical kernels live in src; this module supplies fixed fixtures, independent
oracles, timing and hash-bound evidence. It never assembles a PDE operator.
"""

import json
from time import monotonic
from types import MappingProxyType

import numpy as np

from benchmarks.facet_receiver_example import receiver_class, consume
from benchmarks.portable_facet_checks import binding, array_digest
from benchmarks.portable_facet_oracle import moments, relative, local_integral
from src.solvers.local_facet_functionals import local_port_rows, port_direction_actions


def setup(root):
    import basix

    design_path = root / "input/task042extra_feinn_5nm/facet_component_v23.json"
    design = json.loads(design_path.read_text())
    cls = receiver_class(root / "tmp/task42extra/v23/receiver_directional_boundary.py")
    polynomials = {}
    validation = {}
    for degree in design["degrees"]:
        element = basix.create_element(
            basix.ElementFamily.N1E,
            basix.CellType.hexahedron,
            degree,
            basix.LagrangeVariant.legendre,
        )
        polynomial = cls(element)
        transform = np.eye(element.dim)
        element.T_apply(transform.ravel(), element.dim, design["orientation_cell_info"])
        assert np.linalg.norm(transform - np.eye(element.dim)) > 0
        polynomial.coefficients = MappingProxyType(
            {
                side: np.ascontiguousarray(
                    np.einsum("abjc,jk->abkc", value, transform, optimize=True)
                )
                for side, value in polynomial.coefficients.items()
            }
        )
        for value in polynomial.coefficients.values():
            value.flags.writeable = False
        # Native point evaluation is independent of polynomial-coordinate
        # construction and uses a different, fixed grid (no interpolation).
        from numpy.polynomial.legendre import legvander

        u = np.array([0.071, 0.277, 0.623, 0.941])
        v = np.array([0.039, 0.391, 0.747, 0.973])
        x, y = np.meshgrid(u, v, indexing="ij")
        errors = {}
        for side, z in [("bottom", 0.0), ("top", 1.0)]:
            points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, z)))
            native = element.tabulate(0, points)[0, :, :, :2]
            native = np.einsum("njv,jk->nkv", native, transform, optimize=True)
            recovered = np.einsum(
                "na,nb,abjc->njc",
                legvander(2 * points[:, 0] - 1, degree),
                legvander(2 * points[:, 1] - 1, degree),
                polynomial.coefficients[side],
                optimize=True,
            )
            errors[side] = relative(recovered, native)
        assert max(e["relative"] for e in errors.values()) <= 1e-10, (
            "NATIVE_POLYNOMIAL_RECONSTRUCTION"
        )
        validation[str(degree)] = dict(
            native_dimension=element.dim,
            full_columns_retained=True,
            nonidentity_orientation=True,
            cell_info=design["orientation_cell_info"],
            native_points=errors,
            coefficient_hash={
                s: array_digest(c) for s, c in polynomial.coefficients.items()
            },
            edge_columns=len(element.entity_dofs[1][0]),
            face_columns=len(element.entity_dofs[2][0]),
            interior_columns=len(element.entity_dofs[3][0]),
            interior_not_pruned=True,
            bytes=sum(a.nbytes for a in polynomial.coefficients.values()),
        )
        polynomials[degree] = polynomial
    return design, polynomials, validation, design_path


def frequencies(design):
    xs = (
        np.arange(design["x_orders"][0], design["x_orders"][1] + 1)
        * 2
        * np.pi
        / design["period_nm"][0]
        + design["k_inc_x_per_nm"]
    )
    ys = (
        np.arange(design["y_orders"][0], design["y_orders"][1] + 1)
        * 2
        * np.pi
        / design["period_nm"][1]
    )
    return np.r_[
        0.0,
        *[np.r_[width * xs, -width * xs] for width in design["x_widths_nm"]],
        ys * design["y_width_nm"],
        2 * np.pi * 35 / 36,
    ]


def local_cases(design):
    k0 = 2 * np.pi / design["lambda_nm"]
    cases = []
    for width in design["x_widths_nm"]:
        for m, n in design["local_mode_keys"]:
            kx = design["k_inc_x_per_nm"] + 2 * np.pi * m / design["period_nm"][0]
            ky = 2 * np.pi * n / design["period_nm"][1]
            kz = np.sqrt(complex(k0**2 - kx**2 - ky**2))
            for side in design["sides"]:
                k = np.array([kx, ky, kz if side == "top" else -kz], np.complex128)
                s = np.array([-ky, kx, 0.0], np.complex128) / np.hypot(kx, ky)
                for polarization in design["polarizations"]:
                    e = s if polarization == "s" else np.cross(s, k) / k0
                    J = np.diag([width, design["y_width_nm"], 10.0])
                    origin = np.array([16.5, 0.0, 120.0 if side == "top" else -10.0])
                    normal = np.array([0.0, 0.0, 1.0 if side == "top" else -1.0])
                    cases.append(
                        dict(
                            key=[m, n, side, polarization, width],
                            k=k,
                            e=e,
                            J=J,
                            origin=origin,
                            normal=normal,
                            z=130.0 if side == "top" else -10.0,
                        )
                    )
    return cases


def physical_oracle(polynomial, case, precision):
    J, k = case["J"], case["k"]
    mx, _ = moments(float(k[0].real * J[0, 0]), polynomial.p, precision)
    my, _ = moments(float(k[1].real * J[1, 1]), polynomial.p, precision)
    integral = local_integral(
        polynomial.coefficients[case["key"][2]],
        mx,
        my,
        J,
        k,
        case["origin"],
        case["key"][2],
    )
    # Independent scalar formula for normal curl traction, conjugates, and
    # whole-cell H; it does not call the producer row/action kernels.
    ex, ey, ez = case["e"]
    kx, ky, kz = k
    nz = case["normal"][2]
    traction = np.array([1j * (kz * ex - kx * ez) * nz, 1j * (kz * ey - ky * ez) * nz])
    B = -(integral[:, 0] * traction[0] + integral[:, 1] * traction[1])
    D = integral[:, 0].conj() * ex.conjugate() + integral[:, 1].conj() * ey.conjugate()
    H = (
        50.0
        * 25.0
        * (abs(ex) ** 2 + abs(ey) ** 2)
        * abs(np.exp(1j * kz * case["z"])) ** 2
    )
    return B, D, float(H), integral


def qualify(root, artifact, marker, budget):
    from src.runners.fixed_phase_campaign import write

    begin = monotonic()
    design, polys, validation, design_path = setup(root)
    freq = frequencies(design)
    oracle80 = []
    oracle110 = []
    decimal = []
    for i, w in enumerate(freq):
        budget("fixed_mp_moment")
        low, _ = moments(w, 6, 80)
        high, digits = moments(w, 6, 110)
        oracle80.append(low)
        oracle110.append(high)
        decimal.append(digits)
    a80, a110 = np.array(oracle80), np.array(oracle110)
    quad_cross = []
    # Exactly three preselected frequencies, fixed before numerical results.
    for w in (0.0, 2 * np.pi * 35 / 4, -2 * np.pi * 35 / 4):
        low, _ = moments(w, 6, 80, direct_quadrature=True)
        high, _ = moments(w, 6, 110, direct_quadrature=True)
        rec, _ = moments(w, 6, 110)
        quad_cross.append(
            dict(
                omega=w,
                precisions_80_110=relative(low, high),
                quad_recurrence=relative(high, rec),
            )
        )
    rng = np.random.default_rng(design["direction_seed"])
    all_arrays = dict(frequencies=freq, moment_oracle80=a80, moment_oracle110=a110)
    local = {}
    cases = local_cases(design)
    for p, poly in polys.items():
        directions = rng.normal(size=(3, poly.element.dim)) + 1j * rng.normal(
            size=(3, poly.element.dim)
        )
        directions[:, 0] *= np.exp(0.37j)  # fixed nonunit Floquet scalar, once only
        directions /= np.linalg.norm(directions, axis=1)[:, None]
        load = rng.normal(size=len(cases)) + 1j * rng.normal(size=len(cases))
        b80, d80, h80, b110, d110, h110 = [], [], [], [], [], []
        for case in cases:
            budget("local_original_port_oracle")
            b, d, h, _ = physical_oracle(poly, case, 80)
            b80.append(b)
            d80.append(d)
            h80.append(h)
            b, d, h, _ = physical_oracle(poly, case, 110)
            b110.append(b)
            d110.append(d)
            h110.append(h)
        for name, value in [
            ("directions", directions),
            ("load", load),
            ("B80", b80),
            ("D80", d80),
            ("H80", h80),
            ("B", b110),
            ("D", d110),
            ("H", h110),
        ]:
            all_arrays[f"p{p}_{name}"] = np.asarray(value)
        local[str(p)] = dict(
            B=relative(b80, b110),
            D=relative(d80, d110),
            H=relative(h80, h110),
            original_H_min=float(min(h110)),
            original_H_max=float(max(h110)),
            case_keys=[c["key"] for c in cases],
            nonzero_directions=3,
            nonzero_load=True,
        )
        marker(
            "local_facet_oracle",
            dict(degree=p, cases=len(cases), dimension=poly.element.dim),
        )
    raw = artifact / "oracle.npz"
    np.savez(raw, **all_arrays)
    digits_path = artifact / "moment_decimal110.json"
    write(digits_path, decimal)
    passed = (
        np.max(abs(a80 - a110)) <= 1e-12
        and all(
            max(x["precisions_80_110"]["relative"], x["quad_recurrence"]["relative"])
            <= 1e-10
            for x in quad_cross
        )
        and all(
            max(x[k]["relative"] for k in ("B", "D", "H")) <= 1e-10
            for x in local.values()
        )
    )
    report = dict(
        scope=design["scope"],
        design=binding(design_path),
        receiver=binding(root / "tmp/task42extra/v23/receiver_directional_boundary.py"),
        native_validation=validation,
        oracle_precisions=[80, 110],
        Bessel_calls_in_oracle=0,
        moment_80_110_max_absolute=float(np.max(abs(a80 - a110))),
        quadrature_cross_checks=quad_cross,
        local=local,
        stage_qualified=bool(passed),
        component_qualified=bool(passed),
        strict_field_qualified=False,
        all32060_qualified=False,
        Maxwell_factor_solve_Gram_training=0,
        worker_qualification_seconds=monotonic() - begin,
        oracle_arithmetic="independent 80/110 integer-polynomial integrals; local contraction extended accumulator then complex128, fixed native binary64 coefficients",
    )
    write(artifact / "qualification.json", report)
    return report, dict(
        oracle=raw,
        decimal_moments=digits_path,
        qualification=artifact / "qualification.json",
    )


def checked_dependency(stage):
    from src.runners.fixed_phase_campaign import ARTIFACTS

    paths = sorted(ARTIFACTS.glob("index_" + stage + "_attempt*.json"))
    records = [json.loads(p.read_text()) for p in paths]
    records = [r for r in records if r["result"].get("stage_qualified")]
    if len(records) != 1:
        raise ValueError("UNIQUE_LOCAL_COMPONENT_DEPENDENCY_REQUIRED")
    record = records[0]
    for item in record["files"].values():
        if binding(item["path"])["sha256"] != item["sha256"]:
            raise ValueError("LOCAL_COMPONENT_DEPENDENCY_FILE_CHANGED")
    return record


def cold_lifecycle(root, artifact, marker, budget, implementation):
    from src.runners.fixed_phase_campaign import write

    begin = monotonic()
    dependency = checked_dependency("v23_facet_qualification")
    with np.load(dependency["files"]["oracle"]["path"], allow_pickle=False) as z:
        oracle = {k: np.array(z[k]) for k in z.files}
    read_end = monotonic()
    design, polys, validation, design_path = setup(root)
    setup_end = monotonic()
    if validation != dependency["result"]["native_validation"]:
        raise ValueError("COLD_NATIVE_COEFFICIENT_IDENTITY_CHANGED")
    rows = {}
    raw = {}
    cases = local_cases(design)
    # Importing the opt-in analytic provider is fully charged, and never forced
    # into the q60 ordinary process. Caller identities are independently bound.
    if implementation == "analytic":
        from src.solvers.interval_facet_moments import (
            facet_identity,
            unit_interval_moments,
        )

        def provider(w, p):
            return unit_interval_moments(w, p)
    else:
        import basix
        from numpy.polynomial.legendre import legvander

        q, w = basix.make_quadrature(basix.CellType.interval, 60)

        def provider(omega, p):
            return (w * np.exp(1j * omega * q[:, 0])) @ legvander(2 * q[:, 0] - 1, p)

    moment_values = np.array([provider(w, 6) for w in oracle["frequencies"]])
    interval_error = float(np.max(abs(moment_values - oracle["moment_oracle110"])))
    raw["moment_values"] = moment_values
    for p, poly in polys.items():
        b, d, h = [], [], []
        for case in cases:
            budget("bounded_local_cold_action")
            expected = (
                facet_identity(
                    poly, case["key"][2], case["k"], case["J"], case["origin"]
                )
                if implementation == "analytic"
                else None
            )
            integral = consume(
                poly,
                case["key"][2],
                case["k"],
                case["J"],
                case["origin"],
                implementation=implementation,
                expected=expected,
            )
            bb, dd, hh = local_port_rows(
                integral,
                case["k"],
                case["e"],
                case["normal"],
                original_area=1250.0,
                reference_z=case["z"],
            )
            b.append(bb)
            d.append(dd)
            h.append(hh)
        B, D, H = map(np.array, (b, d, h))
        c = oracle[f"p{p}_directions"]
        load = oracle[f"p{p}_load"]
        actual = port_direction_actions(B, D, H, c, load)
        oB, oD, oH = (oracle[f"p{p}_{k}"] for k in ("B", "D", "H"))
        independent = dict(
            forward=oB @ c.T,
            projection=(oD @ c.T + load[:, None]) / oH[:, None],
            adjoint=oB.conj().T @ load,
        )
        metrics = {k: relative(v, independent[k]) for k, v in actual.items()}
        metrics.update(B=relative(B, oB), D=relative(D, oD), H=relative(H, oH))
        lhs = np.vdot(actual["forward"][:, 0], load)
        rhs = np.vdot(c[0], actual["adjoint"])
        metrics["conjugate_adjoint"] = relative(np.array([lhs]), np.array([rhs]))
        # Negative conjugation control is explicitly retained, never clipped.
        wrong = D.conj() @ c.T
        negative = relative(wrong, oD @ c.T)
        rows[str(p)] = dict(
            metrics=metrics,
            wrong_conjugation_negative=negative,
            original_denominators=True,
            passed=all(v["relative"] <= 1e-10 for v in metrics.values()),
        )
        raw.update(
            {
                f"p{p}_B": B,
                f"p{p}_D": D,
                f"p{p}_H": H,
                **{f"p{p}_{k}": v for k, v in actual.items()},
            }
        )
        marker(
            "cold_local_actions_saved",
            dict(
                implementation=implementation,
                degree=p,
                cases=len(cases),
                passed=rows[str(p)]["passed"],
            ),
        )
    action_end = monotonic()
    raw_path = artifact / "cold_arrays.npz"
    np.savez(raw_path, **raw)
    # Independent checker re-reads on-disk arrays after write, so persistence
    # and checking costs belong to this cold lifecycle, not a later warm loop.
    from benchmarks.portable_facet_result_checker import check_arrays

    check = check_arrays(raw_path, dependency["files"]["oracle"]["path"])
    result = dict(
        implementation=implementation,
        interval_max_absolute=interval_error,
        rows=rows,
        checker=check,
        stage_qualified=bool(check["passed"]),
        component_qualified=bool(check["passed"]),
        strict_field_qualified=False,
        dependency_source_sha=dependency["source_sha"],
        design=binding(design_path),
        native_validation=validation,
        new_Maxwell_factor_solve_Gram_training=0,
        one_cold_lifecycle=True,
        repeat_microbenchmarks=0,
        phase_seconds=dict(
            oracle_read=read_end - begin,
            native_first_coefficients=setup_end - read_end,
            import_integral_contraction_adaptation=action_end - setup_end,
            write_independent_check=monotonic() - action_end,
        ),
        worker_cold_seconds=monotonic() - begin,
        cache="receiver polynomials held only within this lifecycle; no prior-process coefficient cache",
        cold_comparison_scope="launcher complete lifecycle including imports/resource window tracked separately",
    )
    write(artifact / "cold_result.json", result)
    return result, dict(cold_arrays=raw_path, cold_result=artifact / "cold_result.json")
