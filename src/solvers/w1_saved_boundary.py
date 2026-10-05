"""Pure saved-array W1 checker: no FE imports, quadrature or generator.

Rebuilds both local component columns and empirical actions from stored
native coefficients and independently qualified one-dimensional moments.
"""

import csv
import hashlib
import json
from pathlib import Path
import numpy as np

LIMIT = 1e-10


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def read_npz(root, row):
    original = Path(row["path"])
    p = (root / original).resolve()
    if (
        original.is_absolute()
        or not p.is_relative_to(root.resolve())
        or p.is_symlink()
        or not p.is_file()
        or p.stat().st_size != row["bytes"]
        or sha(p) != row["sha256"]
    ):
        raise ValueError("W28_RELATIVE_ARRAY_HASH_SCOPE")
    with np.load(p, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def terms(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("W28_MATCHED_FINITE_ARRAYS")
    numerator = float(np.linalg.norm(a - b))
    ref = float(np.linalg.norm(b))
    den = max(ref, np.finfo(float).tiny)
    return dict(
        numerator=numerator,
        reference_norm=ref,
        denominator=den,
        relative=numerator / den,
        near_zero=ref <= np.finfo(float).tiny,
    )


def z(row):
    return np.array([complex(x["real"], x["imag"]) for x in row], np.complex128)


def check_saved(root, modes, physical, metrics_path, *, guard=lambda: None):
    root = Path(root).resolve()
    index = json.loads((root / "chunk_index.json").read_text())
    if (
        index.get("complete") is not True
        or index.get("instance_id") != "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"
    ):
        raise ValueError("W28_PARTIAL_OR_WRONG_INSTANCE")
    if index.get("profile") not in {"q60_native", "q60_phase_subdivision_v28"}:
        raise ValueError("W28_PROFILE")
    table = read_npz(root, index["oracle"])
    freq = table["frequencies"]
    if (
        len(freq) != len(set(freq.tolist()))
        or np.any(abs(freq) > 56)
        or table["reference80"].shape != (len(freq), 7)
    ):
        raise ValueError("W28_FULL_ORACLE_LAYOUT")
    reference = table["reference110"]
    oraclemax = float(np.max(abs(table["reference80"] - reference)))
    analyticmax = float(np.max(abs(table["analytic"] - reference)))
    if not np.isfinite(reference).all() or max(oraclemax, analyticmax) > 1e-12:
        raise ValueError("W28_NUMERIC_ORACLE_UNQUALIFIED")
    integration = table["integration_candidate"]
    if integration.shape != reference.shape or not np.isfinite(integration).all():
        raise ValueError("W28_INTEGRATION_MOMENT_LAYOUT")
    moment_errors = abs(integration - reference)
    moment_max = float(np.max(moment_errors))
    moment_failed = int(np.count_nonzero(moment_errors > 1e-12))
    lookup = {float(w): reference[i] for i, w in enumerate(freq)}
    layouts = {}
    actions = {}
    accum = {}
    all_metrics = {}
    count = failed = 0
    coverage = {4: [], 6: []}
    actual_freq = set()

    def record(field, a, b, p=0, key=(), i=-1):
        nonlocal count, failed
        value = terms(a, b)
        passed = value["relative"] <= LIMIT
        count += 1
        failed += not passed
        item = dict(
            degree=p, key=list(key), mode_index=i, field=field, **value, passed=passed
        )
        if (
            field not in all_metrics
            or value["relative"] > all_metrics[field]["relative"]
        ):
            all_metrics[field] = item
        writer.writerow({**item, "key": json.dumps(list(key), separators=(",", ":"))})
        return value

    path = Path(metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "degree",
                "key",
                "mode_index",
                "field",
                "numerator",
                "reference_norm",
                "denominator",
                "relative",
                "near_zero",
                "passed",
            ],
        )
        writer.writeheader()
        for p in (4, 6):
            layouts[p] = read_npz(root, index["layouts"][str(p)])
            a = read_npz(root, index["actions"][str(p)])
            actions[p] = a
            dim = 3 * p * (p + 1) ** 2
            if int(layouts[p]["degree"]) != p or layouts[p]["top_coeff"].shape != (
                p + 1,
                p + 1,
                dim,
                2,
            ):
                raise ValueError("W28_COMPLETE_NATIVE_COEFFICIENT_LAYOUT")
            accum[p] = {}
            for witness in ("original", "generic"):
                trace = a[witness + "_trace"]
                dual = a[witness + "_dual"]
                alpha = a[witness + "_alpha"]
                if trace.shape != dual.shape or alpha.shape != (32060,):
                    raise ValueError("W28_EMPIRICAL_WITNESS_LAYOUT")
                if witness == "generic":
                    rng = np.random.default_rng(4212801)
                    expected_trace = rng.normal(size=len(trace)) + 1j * rng.normal(
                        size=len(trace)
                    )
                    expected_dual = rng.normal(size=len(trace)) + 1j * rng.normal(
                        size=len(trace)
                    )
                    expected_alpha = (
                        rng.normal(size=32060) + 1j * rng.normal(size=32060)
                    ) / np.sqrt(32060)
                    if not all(
                        np.array_equal(a[witness + "_" + k], v)
                        for k, v in (
                            ("trace", expected_trace),
                            ("dual", expected_dual),
                            ("alpha", expected_alpha),
                        )
                    ):
                        raise ValueError("W28_FIXED_GENERIC_WITNESS")
                accum[p][witness] = {
                    n: np.zeros_like(a[witness + "_" + n])
                    for n in (
                        "components",
                        "recover",
                        "apply",
                        "adjoint",
                        "modal_rhs",
                        "physical_rhs",
                    )
                }
        for receipt in index["chunks"]:
            guard()
            data = read_npz(root, receipt)
            p = receipt["degree"]
            side = receipt["side"]
            lay = layouts[p]
            ids = data["mode_indices"]
            dim = 3 * p * (p + 1) ** 2
            if (
                len(ids) > 64
                or ids.tolist() != receipt["mode_indices"]
                or data["candidate"].shape != (len(ids), dim, 2)
                or int(data["quadrature_degree"]) != 60
                or str(data["profile"]) != index["profile"]
            ):
                raise ValueError("W28_CHUNK_FULL_COLUMN_LAYOUT")
            J = data["J"]
            origin = data["origins"][0]
            # Original 90/46/46/90 partition and actual representative face.
            expected_J = np.diag([8.5 / 46, 6.25, 10.0])
            expected_origin = np.array(
                [-8.5 + 10 * 8.5 / 46, -6.25, 120.0 if side == "top" else -10.0]
            )
            if (
                np.linalg.norm(J - expected_J) > 2e-14
                or np.linalg.norm(origin - expected_origin) > 2e-14
            ):
                raise ValueError("W28_ORIGINAL_FACE_GEOMETRY")
            if not np.array_equal(data["origins"][1] - origin, [25, 12.5, 0]):
                raise ValueError("W28_COORDINATE_BRIDGE")
            for j, i in enumerate(ids):
                i = int(i)
                mode = modes[i]
                key = [mode["side"], mode["m"], mode["n"], mode["polarization"]]
                if mode["side"] != side:
                    raise ValueError("W28_WRONG_SIDE")
                for field, source in [
                    ("k", "k_vector"),
                    ("e", "e_vector"),
                    ("traction", "traction_vector"),
                ]:
                    if not np.array_equal(data[field][j], z(mode[source])):
                        raise ValueError("W28_MANIFEST_ARRAY_PHYSICS")
                H = mode["projection_denominator"]
                if data["H"][j] != H:
                    raise ValueError("W28_ORIGINAL_INSTANCE_H")
                k = data["k"][j]
                omega = (float(k[0].real * J[0, 0]), float(k[1].real * J[1, 1]))
                actual_freq.update(omega)
                actual_freq.update(-w for w in omega)
                if any(w not in lookup for w in omega):
                    raise ValueError("W28_ALL_FREQUENCIES_REQUIRED")
                pos = origin.copy()
                pos[2] += J[2, 2] if side == "top" else 0
                mx, my = lookup[omega[0]][: p + 1], lookup[omega[1]][: p + 1]
                # Pure saved contraction, no analytical integrator or quadrature.
                ref = np.einsum(
                    "a,b,abjc->jc",
                    np.asarray(mx, np.clongdouble),
                    np.asarray(my, np.clongdouble),
                    np.asarray(lay[side + "_coeff"], np.longdouble),
                    optimize=True,
                )
                ref *= np.array([J[1, 1], J[0, 0]], np.longdouble)
                ref *= np.exp(1j * np.dot(k, pos))
                ref = np.asarray(ref, np.complex128)
                c = data["candidate"][j]
                r = data["reference"][j]
                shifted = data["absolute_candidate"][j]
                record("saved_reference", r, ref, p, key, i)
                record("integral", c, ref, p, key, i)
                e, t = data["e"][j, :2], data["traction"][j, :2]
                Bc, Br = c @ -t, ref @ -t
                Dc, Dr = (c @ e).conj() / H, (ref @ e).conj() / H
                record("stored_B", data["B"][j], Br, p, key, i)
                record("stored_D_H", data["D"][j], Dr, p, key, i)
                record("B", Bc, Br, p, key, i)
                record("D_H", Dc, Dr, p, key, i)
                phase = np.exp(1j * np.dot(k, [25, 12.5, 0]))
                record("coordinate_integral", shifted, c * phase, p, key, i)
                record("coordinate_B", shifted @ -t / phase, Bc, p, key, i)
                record("coordinate_D", (shifted @ e).conj() / H, Dc / phase, p, key, i)
                for direction in range(3):
                    v = np.exp(1j * (0.19 + 0.07 * direction) * np.arange(dim))
                    record("B_direction_" + str(direction), Bc @ v, Br @ v, p, key, i)
                    record("D_direction_" + str(direction), Dc @ v, Dr @ v, p, key, i)
                active = lay[side + "_active"]
                rows = lay[side + "_rows"]
                weights = lay[side + "_weights"]
                B, D = Br[active], Dr[active]
                integral = ref[active]
                for witness in ("original", "generic"):
                    a = actions[p]
                    outstate = accum[p][witness]
                    trace = weights * a[witness + "_trace"][rows]
                    dual = weights * a[witness + "_dual"][rows]
                    proj = integral.conj().T @ trace
                    projected = np.vdot(e, proj) / H
                    record(
                        witness + "_components_key",
                        a[witness + "_components"][i],
                        proj,
                        p,
                        key,
                        i,
                    )
                    record(
                        witness + "_recover_key",
                        a[witness + "_recover"][i],
                        np.asarray(projected),
                        p,
                        key,
                        i,
                    )
                    outstate["components"][i] = proj
                    outstate["recover"][i] = projected
                    np.add.at(outstate["apply"], rows, weights.conj() * B * projected)
                    np.add.at(
                        outstate["adjoint"],
                        rows,
                        weights.conj() * D.conj() * np.vdot(B, dual),
                    )
                    np.add.at(
                        outstate["modal_rhs"],
                        rows,
                        weights.conj() * B * a[witness + "_alpha"][i],
                    )
                    np.add.at(
                        outstate["physical_rhs"],
                        rows,
                        weights.conj() * B * a[witness + "_physical_alpha"][i],
                    )
                coverage[p].append(i)
        if any(sorted(ids) != list(range(32060)) for ids in coverage.values()):
            raise ValueError("W28_INCOMPLETE_OR_DUPLICATE_MODE_OUTPUT")
        if not actual_freq <= set(freq.tolist()):
            raise ValueError("W28_REFERENCE_ALL_FREQUENCIES")
        for p in (4, 6):
            a = actions[p]
            for witness, state in accum[p].items():
                for name, value in state.items():
                    record(witness + "_" + name, a[witness + "_" + name], value, p)
                record(
                    witness + "_adjoint",
                    np.vdot(a[witness + "_dual"], a[witness + "_apply"]),
                    np.vdot(a[witness + "_adjoint"], a[witness + "_trace"]),
                    p,
                )
            packet = read_npz(root, index["incident"][str(p)])
            mode = next(
                m
                for m in modes
                if (m["side"], m["m"], m["n"], m["polarization"]) == ("top", 0, 0, "s")
            )
            kout = z(mode["k_vector"])
            kin = kout.copy()
            kin[2] *= -1
            e = z(mode["e_vector"])
            # Locate the stored independently qualified complete outgoing matrix.
            i = mode["mode_index"]
            selected = next(
                c
                for c in index["chunks"]
                if c["degree"] == p and i in c["mode_indices"]
            )
            raw = read_npz(root, selected)
            ro = raw["reference"][selected["mode_indices"].index(i)]
            delta = np.exp(1j * (kin[2] - kout[2]) * 130)
            ti = np.cross(1j * np.cross(kin, e), [0, 0, 1])
            to = np.cross(1j * np.cross(kout, e), [0, 0, 1])
            expected = (ro @ ti[:2] - ro @ to[:2]) * delta
            for name in (
                "rhs_center",
                "rhs_reference",
                "rhs_absolute",
                "rhs_absolute_reference",
                "rhs_modal",
                "background_rhs_center",
                "background_rhs_absolute",
            ):
                record("incident_" + name, packet[name], expected, p)
            if (
                not np.array_equal(packet["k_in"], kin)
                or not np.array_equal(packet["k_out"], kout)
                or not np.array_equal(packet["e_in"], e)
                or float(packet["reference_plane_nm"]) != 130
            ):
                raise ValueError("W28_PHYSICAL_INCOMING_IDENTITY")
            alpha = np.zeros(32060, complex)
            alpha[i] = 2 * delta
            for witness in ("original", "generic"):
                if not np.array_equal(a[witness + "_physical_alpha"], alpha):
                    raise ValueError("W28_PHYSICAL_PORT_RHS")
            bottom = next(
                m
                for m in modes
                if (m["side"], m["m"], m["n"], m["polarization"])
                == ("bottom", 0, 0, "s")
            )
            kb = z(bottom["k_vector"])
            record("background_bottom_k", packet["background_bottom_k"], kb, p)
            R = (kout[2] + kb[2]) / (kout[2] - kb[2])
            T = 1 + R
            record("background_r", packet["background_r"], np.array(R), p)
            record("background_t", packet["background_t"], np.array(T), p)
        out.flush()
    return dict(
        status="W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS"
        if failed == 0 and moment_failed == 0
        else "W1_FULL_MODE_NUMERICAL_FAIL",
        coverage={str(p): len(v) for p, v in coverage.items()},
        coverage_complete=True,
        metric_checks=count,
        failed_metric_count=failed + moment_failed,
        one_dimensional_moment_maximum_absolute=moment_max,
        one_dimensional_moment_failed_count=moment_failed,
        one_dimensional_failed_moments=[
            dict(
                omega=float(freq[i]),
                ell=int(j),
                numerator=float(moment_errors[i, j]),
                absolute_limit=1e-12,
                reference_norm=float(abs(reference[i, j])),
                candidate=[
                    float(integration[i, j].real),
                    float(integration[i, j].imag),
                ],
                reference=[float(reference[i, j].real), float(reference[i, j].imag)],
            )
            for i, j in np.argwhere(moment_errors > 1e-12)
        ],
        maximum_by_field=all_metrics,
        maximum_original_relative=max(m["relative"] for m in all_metrics.values()),
        oracle_maximum_absolute=max(oraclemax, analyticmax),
        oracle_frequency_count=len(freq),
        actual_frequency_count=len(actual_freq),
        physical_incident_rhs_qualified=not any(
            v["relative"] > LIMIT
            for k, v in all_metrics.items()
            if k.startswith(("incident_", "background_"))
        ),
        coordinate_physics_qualified=not any(
            v["relative"] > LIMIT
            for k, v in all_metrics.items()
            if k.startswith("coordinate_")
        ),
        checker_FE_quadrature_generator_factor_solve_calls=0,
        profile=index["profile"],
        full_target_qualified=False,
        official_results=False,
    )


def validate_native_control_saved(run):
    """Independent saved native orientation and literal double-seam MPC check."""
    run = Path(run)
    result = json.loads((run / "component_result.json").read_text())
    if (
        result.get("status") != "CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE"
        or result.get("native_control_complete") is not True
    ):
        raise ValueError("W28_NATIVE_CONTROL_NOT_COMPLETE")
    raw = result["raw"]
    p = Path(raw["path"])
    if (
        p.resolve() != run.resolve() / "control_arrays.npz"
        or p.stat().st_size != raw["bytes"]
        or sha(p) != raw["sha256"]
    ):
        raise ValueError("W28_NATIVE_CONTROL_ARRAY_BINDING")
    checks = {}
    with np.load(p, allow_pickle=False) as data:
        for degree, prefix in ((4, ""), (6, "p6_")):
            T = data[prefix + "orientation"]
            dim = 3 * degree * (degree + 1) ** 2
            if (
                T.shape != (dim, dim)
                or not np.isfinite(T).all()
                or np.array_equal(T, np.eye(dim))
            ):
                raise ValueError("W28_FULL_NATIVE_ORIENTATION")
            orth = float(np.linalg.norm(T.T @ T - np.eye(dim)))
            G = data[prefix + "MPC_expansion"]
            x = data[prefix + "MPC_state"]
            dual = data[prefix + "MPC_dual"]
            phases = np.array(
                [1, np.exp(0.37j), np.exp(-0.23j), np.exp(0.37j) * np.exp(-0.23j)]
            )
            expected = phases * x[0]
            expanded = terms(data[prefix + "MPC_expanded"], expected)
            applied = terms(G @ x, expected)
            adj = abs(np.vdot(dual, G @ x) - np.vdot(G.conj().T @ dual, x))
            if max(orth, expanded["relative"], applied["relative"], adj) > 1e-10:
                raise ValueError("W28_CONTROL_SAVED_NUMERIC_GATE")
            checks[str(degree)] = dict(
                orientation_all_columns=dim,
                orthogonality_absolute=orth,
                mpc_relative=expanded["relative"],
                adjoint_absolute=float(adj),
            )
    return checks
