"""Independent scalar Maxwell mode qualification for the opt-in W1 instance.

No import of a mode generator, FE stack, ledger builder or serialized PASS tag.
Keys and physical values are derived from the frozen resolved configuration.
"""

import cmath
import hashlib
import json
import math
from decimal import Decimal, localcontext

MODE_FIELDS = frozenset(
    (
        "schema mode_index side m n polarization alpha gamma beta k_vector "
        "e_vector h_vector refractive_index vertical_sign "
        "electric_tangential_norm_sq power_per_unit_amplitude "
        "propagating rayleigh_warning classification rayleigh_tolerance "
        "projection_denominator traction_vector"
    ).split()
)
LIMIT = 1e-10


def canonical_sha(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def zvalue(value):
    if not isinstance(value, dict) or set(value) != {"real", "imag"}:
        raise ValueError("W28_COMPLEX_LAYOUT")
    if any(
        type(value[k]) not in (float, int) or not math.isfinite(value[k])
        for k in ("real", "imag")
    ):
        raise ValueError("W28_NONFINITE_MODE")
    return complex(value["real"], value["imag"])


def cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def norm(a):
    return math.sqrt(math.fsum(abs(z) ** 2 for z in a))


def wave_constants(physical):
    inc, geo = physical["incidence"], physical["geometry"]
    k0 = 2 * math.pi / physical["wavelength_nm"]
    theta, phi = (
        math.radians(inc["theta_from_positive_z_deg"]),
        math.radians(inc["azimuth_deg"]),
    )
    nt = complex(*physical["materials"]["top_external_medium"]["refractive_index"])
    kx, ky = (
        k0 * nt * math.sin(theta) * math.cos(phi),
        k0 * nt * math.sin(theta) * math.sin(phi),
    )
    return k0, kx, ky, geo["period_x_nm"], geo["period_y_nm"]


def mode_values(physical, side, m, n, pol, *, tolerance=1e-6):
    k0, kx, ky, lx, ly = wave_constants(physical)
    medium = physical["materials"][
        ("top" if side == "top" else "bottom") + "_external_medium"
    ]
    ni, mu = (
        complex(*medium["refractive_index"]),
        complex(*medium["relative_permeability"]),
    )
    alpha, gamma = kx + 2 * math.pi * m / lx, ky + 2 * math.pi * n / ly
    dispersion = (k0 * ni) ** 2 - alpha**2 - gamma**2
    beta = cmath.sqrt(dispersion)
    if beta.imag < -1e-14 or (abs(beta.imag) < 1e-14 and beta.real < 0):
        beta = -beta
    sign = 1 if side == "top" else -1
    k = [alpha, gamma, sign * beta]
    kt = math.hypot(abs(alpha), abs(gamma))
    if kt < 1e-12 * max(abs(k0 * ni), 1):
        bases = {"x": [1 + 0j, 0j, 0j], "y": [0j, 1 + 0j, 0j]}
    else:
        s = [-gamma / kt, alpha / kt, 0j]
        p = cross([v / (k0 * ni) for v in k], s)
        pn = norm(p)
        bases = {"s": s, "p": [v / pn for v in p]}
    if pol not in bases:
        raise ValueError("W28_POLARIZATION_GAUGE")
    e = bases[pol]
    h = [v / (k0 * mu) for v in cross(k, e)]
    traction = [v / mu for v in cross([1j * v for v in cross(k, e)], [0, 0, sign])]
    et2 = math.fsum(abs(v) ** 2 for v in e[:2])
    plane = physical["ports"][side]["reference_plane_z_nm"]
    H = lx * ly * et2 * math.exp(-2 * k[2].imag * plane)
    power = max(0.5 * cross(e, [v.conjugate() for v in h])[2].real * sign, 0) * lx * ly
    scale = max(abs(dispersion), abs(beta) ** 2, 1e-30)
    prop = beta.real > 1e-12 and dispersion.real > -1e-10 * scale
    rayleigh = abs(beta) / max(abs(k0 * ni), 1e-30) < tolerance
    return dict(
        alpha=alpha,
        gamma=gamma,
        beta=beta,
        k_vector=k,
        e_vector=e,
        h_vector=h,
        refractive_index=ni,
        vertical_sign=sign,
        electric_tangential_norm_sq=et2,
        power_per_unit_amplitude=power,
        propagating=prop,
        rayleigh_warning=rayleigh,
        classification="near-cutoff"
        if rayleigh
        else ("propagating" if prop else "evanescent"),
        rayleigh_tolerance=tolerance,
        projection_denominator=H,
        traction_vector=traction,
    )


def expected_keys(physical):
    k0, kx, ky, lx, ly = wave_constants(physical)
    if physical["ports"]["order_policy"] != "auto_propagating" or any(
        physical["ports"][k] is not None for k in ("maximum_abs_m", "maximum_abs_n")
    ):
        raise ValueError("W28_FROZEN_AUTO_POLICY")
    nmax = max(
        abs(complex(*v["refractive_index"])) for v in physical["materials"].values()
    )
    mm = math.floor((nmax * k0 + abs(kx)) * lx / (2 * math.pi) + 1e-12)
    nn = math.floor((nmax * k0 + abs(ky)) * ly / (2 * math.pi) + 1e-12)
    keys = []
    for side in ("top", "bottom"):
        for m in range(-mm, mm + 1):
            for n in range(-nn, nn + 1):
                value = mode_values(physical, side, m, n, "s")
                if value["propagating"] or (m, n) == (0, 0):
                    keys.extend([[side, m, n, p] for p in ("s", "p")])
    return keys, {"automatic_abs_m": mm, "automatic_abs_n": nn}


def metric(actual, reference, natural):
    a = actual if isinstance(actual, list) else [actual]
    b = reference if isinstance(reference, list) else [reference]
    if len(a) != len(b) or not all(
        math.isfinite(z.real) and math.isfinite(z.imag) for z in a
    ):
        raise ValueError("W28_FINITE_MATCHED_MODE_FIELDS")
    num = norm([x - y for x, y in zip(a, b, strict=True)])
    ref = norm(b)
    den = max(ref, 1e-12 * natural)
    return dict(
        numerator=num,
        reference_norm=ref,
        denominator=den,
        relative=num / den,
        near_zero=ref < 1e-12 * natural,
    )


def check_row(row, physical, index, key):
    if set(row) != MODE_FIELDS or row["schema"] != "fullspace-dtn.mode.v1":
        raise ValueError("W28_EXACT_MODE_SCHEMA")
    if (
        type(row["mode_index"]) is not int
        or row["mode_index"] != index
        or type(row["m"]) is not int
        or type(row["n"]) is not int
        or [row["side"], row["m"], row["n"], row["polarization"]] != key
    ):
        raise ValueError("W28_ORDERED_KEY_AND_INDEX")
    expect = mode_values(physical, *key)
    k0, *_ = wave_constants(physical)
    metrics = {}
    for field, value in expect.items():
        actual = row[field]
        if field in {"propagating", "rayleigh_warning"}:
            if type(actual) is not bool or actual != value:
                raise ValueError("W28_CLASSIFICATION:" + field)
        elif field == "classification":
            if actual != value:
                raise ValueError("W28_CLASSIFICATION:" + field)
        elif field == "vertical_sign":
            if type(actual) is not int or actual != value:
                raise ValueError("W28_OUTGOING_SIGN")
        else:
            if isinstance(value, list):
                actual = [zvalue(v) for v in actual]
            elif isinstance(value, complex):
                actual = zvalue(actual)
            elif type(actual) not in (float, int) or not math.isfinite(actual):
                raise ValueError("W28_MODE_SCALAR:" + field)
            natural = (
                k0
                if field in {"alpha", "gamma", "beta", "k_vector", "traction_vector"}
                else 1.0
            )
            metrics[field] = metric(actual, value, natural)
    k = [zvalue(v) for v in row["k_vector"]]
    e = [zvalue(v) for v in row["e_vector"]]
    metrics["transversality"] = metric(
        sum(x * y for x, y in zip(k, e, strict=True)), 0j, norm(k) * norm(e)
    )
    # A zero target here uses its physical operation scale, rather than a tiny residual.
    metrics["transversality"]["denominator"] = norm(k) * norm(e)
    metrics["transversality"]["relative"] = (
        metrics["transversality"]["numerator"]
        / metrics["transversality"]["denominator"]
    )
    if row["projection_denominator"] <= 0:
        raise ValueError("W28_POSITIVE_H")
    return metrics


def decimal_beta_witness(row, physical, precision):
    """Independent real-pair Decimal square root on exact stored alpha/gamma.

    This isolates branch/cancellation arithmetic; scalar FP64 configuration
    checks above independently establish alpha/gamma and physical identity.
    """
    with localcontext() as c:
        c.prec = precision
        D = Decimal.from_float
        pi = Decimal(
            "3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798214808651"
        )
        k0 = 2 * pi / D(physical["wavelength_nm"])
        medium = physical["materials"][row["side"] + "_external_medium"][
            "refractive_index"
        ]
        nr, ni = D(medium[0]), D(medium[1])
        a, g = zvalue(row["alpha"]), zvalue(row["gamma"])
        if a.imag or g.imag:
            raise ValueError("W28_REAL_TANGENTIAL_DECIMAL")
        x = k0 * k0 * (nr * nr - ni * ni) - D(a.real) ** 2 - D(g.real) ** 2
        y = 2 * k0 * k0 * nr * ni
        magnitude = (x * x + y * y).sqrt()
        br = ((magnitude + x) / 2).sqrt()
        bi = ((magnitude - x) / 2).sqrt()
        if y < 0:
            bi = -bi
        expected = complex(float(br), float(bi))
        return dict(
            precision=precision,
            beta=[str(br), str(bi)],
            metrics=metric(zvalue(row["beta"]), expected, float(k0)),
        )


def validate_document(document, physical, *, write_row=None):
    if (
        document.get("schema") != "fullspace-dtn.mode-manifest.v1"
        or document.get("profile") != "full3d_scalable_v1"
        or document.get("mode_count") != 32060
    ):
        raise ValueError("W28_MANIFEST_SCHEMA_COUNT_PROFILE")
    keys, bounds = expected_keys(physical)
    keysha = hashlib.sha256(
        json.dumps(keys, separators=(",", ":")).encode()
    ).hexdigest()
    if len(keys) != 32060 or len(document["modes"]) != len(keys):
        raise ValueError("W28_FULL_SCIENTIFIC_KEY_COVERAGE")
    maxima = {}
    failures = []
    categories = {}
    groups = {}
    rows = document["modes"]
    for i, (row, key) in enumerate(zip(rows, keys, strict=True)):
        terms = check_row(row, physical, i, key)
        groups[(key[0], key[3])] = groups.get((key[0], key[3]), 0) + 1
        categories[row["classification"]] = categories.get(row["classification"], 0) + 1
        for field, m in terms.items():
            v = dict(
                mode_index=i, key=key, field=field, **m, passed=m["relative"] <= LIMIT
            )
            if write_row is not None:
                write_row(v)
            if field not in maxima or m["relative"] > maxima[field]["relative"]:
                maxima[field] = v
            if not v["passed"]:
                failures.append(v)
    # Finite fixed witness set: nearest cutoff, extremal H/frequency, n=0 and
    # every scalar ambiguity (none may be silently removed).
    chosen = {}
    for side in ("top", "bottom"):
        ids = [i for i, r in enumerate(rows) if r["side"] == side]
        chosen[f"{side}_nearest_cutoff"] = min(
            ids, key=lambda i: abs(zvalue(rows[i]["beta"]))
        )
        chosen[f"{side}_minimum_H"] = min(
            ids, key=lambda i: rows[i]["projection_denominator"]
        )
        chosen[f"{side}_maximum_frequency"] = max(
            ids,
            key=lambda i: abs(zvalue(rows[i]["alpha"])) + abs(zvalue(rows[i]["gamma"])),
        )
        chosen[f"{side}_n0"] = next(
            i for i in ids if rows[i]["m"] == 0 and rows[i]["n"] == 0
        )
    hp = []
    for role, i in chosen.items():
        witnesses = [decimal_beta_witness(rows[i], physical, p) for p in (80, 110)]
        hp.append(dict(role=role, mode_index=i, key=keys[i], witnesses=witnesses))
        if any(v["metrics"]["relative"] > LIMIT for v in witnesses):
            failures.append(dict(role=role, mode_index=i, high_precision=witnesses))
    return dict(
        status="MODE_SCIENCE_PASS" if not failures else "MODE_SCIENCE_FAIL",
        mode_count=len(rows),
        field_checks=len(rows) * len(maxima),
        coverage_complete=True,
        ordered_key_sha256=keysha,
        groups={f"{s}/{p}": n for (s, p), n in groups.items()},
        classifications=categories,
        automatic_bounds=bounds,
        maximum_by_field=maxima,
        failed_count=len(failures),
        failures=failures,
        high_precision=hp,
        all_ambiguous_classifications_preserved=True,
        independent_generator_calls=0,
        normalization="own instance original whole-cell/reference-plane; no phase fit",
        threshold=LIMIT,
    )
