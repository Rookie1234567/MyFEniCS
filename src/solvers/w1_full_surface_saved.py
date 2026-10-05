"""Independent saved full-surface contractions, never the candidate action API.

Reference moments are frozen before the candidate. The checker decodes physical
edge/face keys separately, contracts y before x in extended arithmetic, and
checks every selected mode and complete trace vector. No FE imports or solve.
"""

import csv
import hashlib
import json
from pathlib import Path
import numpy as np

LIMIT = 1e-10


def read_array(root, row):
    root = Path(root).resolve()
    relative = Path(row["path"])
    path = (root / relative).resolve()
    if (
        relative.is_absolute()
        or not path.is_relative_to(root)
        or path.is_symlink()
        or path.stat().st_size != row["bytes"]
        or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
    ):
        raise ValueError("W29_SAVED_ARRAY_BYTES_HASH_SCOPE")
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def terms(candidate, reference):
    a, b = np.asarray(candidate), np.asarray(reference)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("W29_MATCHED_FINITE_SAVED_OUTPUTS")
    numerator = float(np.sqrt(np.sum(abs(a.astype(np.clongdouble) - b) ** 2)))
    norm = float(np.sqrt(np.sum(abs(b) ** 2)))
    denominator = max(norm, np.finfo(np.float64).tiny)
    return dict(
        numerator=numerator,
        reference_norm=norm,
        denominator=denominator,
        relative=numerator / denominator,
        near_zero=norm <= np.finfo(np.float64).tiny,
    )


def expected_maps(data):
    """Enumerate periodic physical entities, rather than trust saved row IDs."""
    x, y, p = data["x"], data["y"], int(data["degree"])
    nx, ny = len(x) - 1, len(y) - 1
    per_side = 2 * p * p * nx * ny
    edge_dofs, face_dofs = data["edge_dofs"], data["face_dofs"]
    geometry, edges = data["element_geometry"], data["edge_vertices"]
    result = {}
    for side_number, side in enumerate(("bottom", "top")):
        active = data[side + "_active"]
        position = {int(d): i for i, d in enumerate(active)}
        native_face = 0 if side == "bottom" else 5
        keys = {}
        serial = side_number * per_side
        for direction in (0, 1):
            for i in range(nx):
                for j in range(ny):
                    for ell in range(p):
                        keys[("edge", direction, i, j, ell)] = serial
                        serial += 1
        for i in range(nx):
            for j in range(ny):
                for ell in range(len(face_dofs[native_face])):
                    keys[("face", i, j, ell)] = serial
                    serial += 1
        if serial != (side_number + 1) * per_side:
            raise ValueError("W29_COMPLETE_PHYSICAL_ENTITY_COUNT")
        maps = np.full((nx, ny, len(active)), -1, np.int64)
        weights = np.ones(maps.shape, np.complex128)
        for i in range(nx):
            for j in range(ny):
                for number, vertices in enumerate(edges):
                    ids = edge_dofs[number]
                    if not len(ids) or int(ids[0]) not in position:
                        continue
                    points = geometry[vertices]
                    direction = int(points[0, 1] != points[1, 1])
                    if direction == 0:
                        raw_i, raw_j = i, j + int(points[0, 1])
                        phase = data["phases"][1] if raw_j == ny else 1
                    else:
                        raw_i, raw_j = i + int(points[0, 0]), j
                        phase = data["phases"][0] if raw_i == nx else 1
                    for ell, d in enumerate(ids):
                        local = position[int(d)]
                        maps[i, j, local] = keys[
                            ("edge", direction, raw_i % nx, raw_j % ny, ell)
                        ]
                        weights[i, j, local] = phase
                for ell, d in enumerate(face_dofs[native_face]):
                    maps[i, j, position[int(d)]] = keys[("face", i, j, ell)]
        if np.any(maps < 0):
            raise ValueError("W29_MISSING_OR_DUPLICATED_NATIVE_ENTITY")
        result[side] = (maps, weights)
    return result


def check_geometry_and_basis(data, inherited):
    # Original partition counts are fixed independently of the producer's
    # proportional allocation. Exact binary64 axes are retained, not merged.
    x = np.concatenate(
        [
            np.linspace(a, b, n + 1)[:-1]
            for a, b, n in [
                (-25.0, -8.5, 90),
                (-8.5, 0.0, 46),
                (0.0, 8.5, 46),
                (8.5, 25.0, 90),
            ]
        ]
        + [np.array([25.0])]
    )
    y = np.linspace(-12.5, 12.5, 5)
    if not all(
        np.array_equal(data[k], v)
        for k, v in [("x", x), ("y", y), ("ledger_x", x + 25), ("ledger_y", y + 12.5)]
    ):
        raise ValueError("W29_PHYSICAL_AXES_OR_COORDINATE_BRIDGE")
    vertices = np.array(
        [[i, j, k] for k in (0, 1) for j in (0, 1) for i in (0, 1)], float
    )
    if not np.array_equal(data["element_geometry"], vertices):
        raise ValueError("W29_REFERENCE_CELL_GEOMETRY")
    for edge in data["edge_vertices"]:
        difference = vertices[edge[1]] - vertices[edge[0]]
        if np.count_nonzero(difference) != 1 or np.sum(difference) != 1:
            raise ValueError("W29_NATIVE_EDGE_ORIENTATION")
    for side in ("bottom", "top"):
        if not all(
            np.array_equal(data[side + suffix], inherited[side + suffix])
            for suffix in ("_coeff", "_active")
        ):
            raise ValueError("W29_QUALIFIED_FULL_NATIVE_BASIS_IDENTITY")
    phase = np.array([np.exp(1j * (2 * np.pi / 0.7) * np.cos(np.deg2rad(1)) * 50), 1.0])
    if terms(data["phases"], phase)["relative"] > LIMIT:
        raise ValueError("W29_PHYSICAL_FLOQUET_PHASE")


def native_column_reference(data, modes, reference, packet):
    """Saved full native columns via y-first Decimal moments, not q60 API."""
    p = int(data["degree"])
    lookup = {
        float(w): reference["reference110"][i, : p + 1].astype(np.clongdouble)
        for i, w in enumerate(reference["frequencies"])
    }
    values = []
    for mode_index, side_number, origin, width in zip(
        packet["mode_indices"],
        packet["sides"],
        packet["origins"],
        packet["widths"],
        strict=True,
    ):
        k = mode_vectors([modes[int(mode_index)]], "k_vector")[0]
        dx, dy = width
        ix, iy = lookup[float(k[0].real * dx)], lookup[float(k[1].real * dy)]
        side = "bottom" if side_number == 0 else "top"
        coeff = data[side + "_coeff"].astype(np.clongdouble)
        local = np.einsum("b,abjc->ajc", iy, coeff, optimize=True)
        local = np.einsum("a,ajc->jc", ix, local, optimize=True)
        local *= np.array([dy, dx])
        position = origin.astype(np.longdouble).copy()
        if side == "top":
            position[2] += 10
        local *= np.exp(1j * np.dot(k.astype(np.clongdouble), position))
        values.append(local)
    return values


def native_D_columns(integral, electric, denominator):
    """D projects onto the conjugate electric mode; it is not B Hermitian."""
    return (np.asarray(integral) @ np.asarray(electric)).conj() / denominator


def mode_vectors(modes, field):
    return np.array(
        [[complex(v["real"], v["imag"]) for v in m[field]] for m in modes],
        np.complex128,
    )


def physical_reference_planes(modes):
    """Original manifest has no derived reference_plane_nm field."""
    planes = []
    for mode in modes:
        if mode["side"] not in ("top", "bottom"):
            raise ValueError("W29_PHYSICAL_REFERENCE_SIDE")
        plane = 130.0 if mode["side"] == "top" else -10.0
        if "reference_plane_nm" in mode and mode["reference_plane_nm"] != plane:
            raise ValueError("W29_PHYSICAL_REFERENCE_PLANE_MISMATCH")
        planes.append(plane)
    return np.array(planes)


def reference_tables(data, modes, reference, *, ledger=False):
    p = int(data["degree"])
    k = mode_vectors(modes, "k_vector")
    lookup = {
        float(w): reference["reference110"][i, : p + 1]
        for i, w in enumerate(reference["frequencies"])
    }
    tables = {}
    for side in ("bottom", "top"):
        ids = np.array([i for i, m in enumerate(modes) if m["side"] == side], np.int64)
        values = []
        indices = []
        for axis, coords in enumerate(
            (data["ledger_x"], data["ledger_y"]) if ledger else (data["x"], data["y"])
        ):
            frequencies = sorted(set(k[ids, axis]), key=lambda v: (v.real, v.imag))
            rank = {v: i for i, v in enumerate(frequencies)}
            matrix = np.empty(
                (len(frequencies), len(coords) - 1, p + 1), np.clongdouble
            )
            for i, wave in enumerate(frequencies):
                for j, (origin, width) in enumerate(
                    zip(coords[:-1], np.diff(coords), strict=True)
                ):
                    omega = float(-wave.real * width)
                    if omega not in lookup or wave.imag != 0:
                        raise ValueError(
                            "W29_REFERENCE_EXACT_BINARY64_FREQUENCY_MISSING"
                        )
                    phase = np.exp(
                        -1j * np.clongdouble(wave.conjugate()) * np.longdouble(origin)
                    )
                    matrix[i, j] = lookup[omega].astype(np.clongdouble) * phase
            values.append(matrix)
            indices.append(np.array([rank[v] for v in k[ids, axis]], np.int64))
        zphase = np.exp(
            -1j
            * k[ids, 2].conj()
            * physical_reference_planes([modes[i] for i in ids])
        )
        tables[side] = (ids, *values, *indices, zphase)
    return tables


def reference_project(trace, data, tables, *, ledger=False):
    x, y = (data["ledger_x"], data["ledger_y"]) if ledger else (data["x"], data["y"])
    out = np.zeros((sum(len(v[0]) for v in tables.values()), 2), np.clongdouble)
    for side, (ids, fx, fy, ix, iy, phase) in tables.items():
        local = (
            trace[data[side + "_map"]].astype(np.clongdouble) * data[side + "_weights"]
        )
        coefficients = data[side + "_coeff"][:, :, data[side + "_active"], :].astype(
            np.clongdouble
        )
        field = np.tensordot(local, coefficients, axes=(2, 2))
        field[:, :, :, :, 0] *= np.diff(y)[None, :, None, None]
        field[:, :, :, :, 1] *= np.diff(x)[:, None, None, None]
        # Independent association: all y cells first, then all x cells.
        intermediate = np.einsum("bjv,ijuvc->biuc", fy, field, optimize=True)
        spectral = np.einsum("aiu,biuc->abc", fx, intermediate, optimize=True)
        for start in range(0, len(ids), 64):
            selected = ids[start : start + 64]
            out[selected] = (
                spectral[ix[start : start + 64], iy[start : start + 64]]
                * phase[start : start + 64, None]
            )
    return out


def reference_scatter(amplitude, data, tables, *, ledger=False):
    p = int(data["degree"])
    x, y = (data["ledger_x"], data["ledger_y"]) if ledger else (data["x"], data["y"])
    out = np.zeros(4 * p * p * (len(x) - 1) * (len(y) - 1), np.clongdouble)
    for side, (ids, fx, fy, ix, iy, phase) in tables.items():
        spectrum = np.zeros((len(fx), len(fy), 2), np.clongdouble)
        for start in range(0, len(ids), 64):
            np.add.at(
                spectrum,
                (ix[start : start + 64], iy[start : start + 64]),
                amplitude[ids[start : start + 64]]
                * phase[start : start + 64, None].conj(),
            )
        intermediate = np.einsum("abc,bjv->ajvc", spectrum, fy.conj(), optimize=True)
        field = np.einsum("aiu,ajvc->ijuvc", fx.conj(), intermediate, optimize=True)
        field[:, :, :, :, 0] *= np.diff(y)[None, :, None, None]
        field[:, :, :, :, 1] *= np.diff(x)[:, None, None, None]
        coefficients = data[side + "_coeff"][:, :, data[side + "_active"], :].astype(
            np.clongdouble
        )
        local = np.tensordot(field, coefficients, axes=((2, 3, 4), (0, 1, 3)))
        local *= data[side + "_weights"].conj()
        np.add.at(out, data[side + "_map"].ravel(), local.ravel())
    return out


def reference_action(state, data, tables, e, traction, H, *, ledger=False):
    projected = reference_project(state["trace"], data, tables, ledger=ledger)
    recovered = np.sum(e.conj() * projected, axis=1) / H
    dual_projection = reference_project(state["dual"], data, tables, ledger=ledger)
    adjoint_alpha = np.sum(-traction.conj() * dual_projection, axis=1) / H
    return dict(
        components=projected,
        recover=recovered,
        apply=reference_scatter(
            -traction * recovered[:, None], data, tables, ledger=ledger
        ),
        adjoint=reference_scatter(
            e * adjoint_alpha[:, None], data, tables, ledger=ledger
        ),
        modal_rhs=reference_scatter(
            -traction * state["alpha"][:, None], data, tables, ledger=ledger
        ),
    )


def check_surface(producer, modes, metrics_path, save_reference, *, guard=lambda: None):
    producer = Path(producer).resolve()
    index = json.loads((producer / "surface_index.json").read_text())
    if (
        index.get("complete") is not True
        or index.get("mode_count") != 32060
        or index.get("facets") != 2176
        or index.get("instance_id") != "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"
        or index.get("reference_frozen_before_candidate") is not True
    ):
        raise ValueError("W29_PARTIAL_WRONG_INSTANCE_OR_SCOPE")
    data = read_array(producer, index["arrays"]["layout"])
    a = read_array(producer, index["arrays"]["actions"])
    reference = read_array(producer, index["arrays"]["reference"])
    candidate_tables = read_array(producer, index["arrays"]["candidate_tables"])
    inherited = read_array(producer, index["arrays"]["qualified_basis"])
    native = read_array(producer, index["arrays"]["native_columns"])
    check_geometry_and_basis(data, inherited)
    p = int(data["degree"])
    if p not in (4, 6) or index["rows"] != 4 * p * p * 272 * 4 or index["degree"] != p:
        raise ValueError("W29_FULL_TRACE_ROWS_NOT_VOLUME_DOFS")
    mapping = expected_maps(data)
    maximum = {}
    count = failed = 0
    reference_outputs = {}
    with Path(metrics_path).open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "degree",
                "field",
                "mode_index",
                "native_column",
                "case_index",
                "key",
                "numerator",
                "reference_norm",
                "denominator",
                "relative",
                "near_zero",
                "passed",
            ],
        )
        writer.writeheader()

        def record(field, value, ref, mode_index=-1, native_column=-1, case_index=-1):
            nonlocal count, failed
            term = terms(value, ref)
            passed = term["relative"] <= LIMIT
            row = dict(
                degree=p,
                field=field,
                mode_index=mode_index,
                native_column=native_column,
                case_index=case_index,
                key=[]
                if mode_index < 0
                else [modes[mode_index][k] for k in ("side", "m", "n", "polarization")],
                **term,
                passed=passed,
            )
            count += 1
            failed += not passed
            if field not in maximum or term["relative"] > maximum[field]["relative"]:
                maximum[field] = row
            writer.writerow(
                {**row, "key": json.dumps(row["key"], separators=(",", ":"))}
            )

        for side, (maps, weights) in mapping.items():
            if not np.array_equal(maps, data[side + "_map"]):
                raise ValueError("W29_PHYSICAL_ROW_MAP_MISMATCH")
            record(side + "_Floquet_weights", data[side + "_weights"], weights)
        oracle_error = max(
            float(np.max(abs(reference["reference80"] - reference["reference110"]))),
            float(np.max(abs(reference["analytic"] - reference["reference110"]))),
        )
        moment_error = float(
            np.max(abs(reference["integration_candidate"] - reference["reference110"]))
        )
        if oracle_error > 1e-12:
            raise ValueError("W29_INDEPENDENT_MOMENT_REFERENCE_UNRESOLVED")
        if moment_error > 1e-12:
            failed += 1
        for i, value in enumerate(
            native_column_reference(data, modes, reference, native)
        ):
            m = modes[int(native["mode_indices"][i])]
            t = mode_vectors([m], "traction_vector")[0, :2]
            electric = mode_vectors([m], "e_vector")[0, :2]
            h = m["projection_denominator"]
            cb, rb = -native["integral"][i] @ t, -value @ t
            cd = native_D_columns(native["integral"][i], electric, h)
            rd = native_D_columns(value, electric, h)
            for column in range(len(value)):
                mode_index = int(native["mode_indices"][i])
                record(
                    "affected_native_integral",
                    native["integral"][i, column],
                    value[column],
                    mode_index,
                    column,
                    i,
                )
                record(
                    "affected_native_B", cb[column], rb[column], mode_index, column, i
                )
                record(
                    "affected_native_D", cd[column], rd[column], mode_index, column, i
                )
        e = mode_vectors(modes, "e_vector")[:, :2]
        traction = mode_vectors(modes, "traction_vector")[:, :2]
        H = np.array([m["projection_denominator"] for m in modes])
        record("saved_e", a["e"], e)
        record("saved_traction", a["traction"], traction)
        record("saved_H", a["H"], H)
        k = mode_vectors(modes, "k_vector")
        original_H = (
            1250
            * np.sum(abs(e) ** 2, axis=1)
            * abs(
                np.exp(
                1j * k[:, 2] * physical_reference_planes(modes)
                )
            )
            ** 2
        )
        record("physical_H", a["H"], original_H)
        bridge = np.exp(-1j * (k[:, :2] @ np.array([25.0, 12.5])))
        record("coordinate_bridge", a["bridge"], bridge)
        for ledger in (False, True):
            prefix = "ledger" if ledger else "center"
            tables = reference_tables(data, modes, reference, ledger=ledger)
            for side, (ids, fx, fy, ix, iy, phase) in tables.items():
                for field, value in [
                    ("fx", fx.reshape(len(fx), -1)),
                    ("fy", fy.reshape(len(fy), -1)),
                    ("zphase", phase),
                ]:
                    record(
                        prefix + "_" + side + "_" + field,
                        candidate_tables[prefix + "_" + side + "_" + field],
                        value,
                    )
                for field, value in [("ix", ix), ("iy", iy)]:
                    if not np.array_equal(
                        candidate_tables[prefix + "_" + side + "_" + field], value
                    ):
                        raise ValueError("W29_MODE_LOOKUP_LAYOUT_MISMATCH")
            for name, seed in [("generic", 4212801), ("seam", 4212901)]:
                guard()
                rng = np.random.default_rng(seed)
                trace = rng.normal(size=index["rows"]) + 1j * rng.normal(
                    size=index["rows"]
                )
                dual = rng.normal(size=index["rows"]) + 1j * rng.normal(
                    size=index["rows"]
                )
                alpha = rng.normal(size=32060) + 1j * rng.normal(size=32060)
                if name == "seam":
                    supported = np.unique(
                        np.concatenate(
                            [v[0][0].ravel() for v in mapping.values()]
                            + [v[0][-1].ravel() for v in mapping.values()]
                            + [v[0][:, 0].ravel() for v in mapping.values()]
                            + [v[0][:, -1].ravel() for v in mapping.values()]
                        )
                    )
                    mask = np.zeros(index["rows"], bool)
                    mask[supported] = True
                    trace[~mask] = 0
                    dual[~mask] = 0
                    if not np.array_equal(supported, a["seam_rows"]):
                        raise ValueError("W29_SEAM_CORNER_SUPPORT")
                if not all(
                    np.array_equal(a[name + "_" + key], value)
                    for key, value in [
                        ("trace", trace),
                        ("dual", dual),
                        ("alpha", alpha),
                    ]
                ):
                    raise ValueError("W29_FROZEN_WITNESS_SEED_OR_INPUT_CHANGED")
                state = dict(
                    trace=trace, dual=dual, alpha=alpha * bridge if ledger else alpha
                )
                outputs = reference_action(
                    state, data, tables, e, traction, H, ledger=ledger
                )
                stored_prefix = name + ("_ledger" if ledger else "")
                for field, value in outputs.items():
                    reference_outputs[stored_prefix + "_" + field] = np.asarray(
                        value, np.complex128
                    )
                    record(
                        stored_prefix + "_" + field,
                        a[stored_prefix + "_" + field],
                        value,
                    )
                    if field in ("components", "recover"):
                        for start in range(0, 32060, 64):
                            guard()
                            for i in range(start, min(start + 64, 32060)):
                                record(
                                    stored_prefix + "_" + field + "_key",
                                    a[stored_prefix + "_" + field][i],
                                    value[i],
                                    i,
                                )
                                if field == "components":
                                    for component in range(2):
                                        record(
                                            stored_prefix
                                            + "_"
                                            + field
                                            + "_"
                                            + str(component)
                                            + "_key",
                                            a[stored_prefix + "_" + field][
                                                i, component
                                            ],
                                            value[i, component],
                                            i,
                                        )
                record(
                    stored_prefix + "_adjoint_inner_product",
                    np.vdot(a[name + "_dual"], a[stored_prefix + "_apply"]),
                    np.vdot(a[stored_prefix + "_adjoint"], a[name + "_trace"]),
                )
            selected = [
                i
                for i, m in enumerate(modes)
                if (m["side"], m["m"], m["n"], m["polarization"]) == ("top", 0, 0, "s")
            ]
            if len(selected) != 1:
                raise ValueError("W29_PHYSICAL_INCOMING_KEY")
            incoming = np.zeros(32060, np.complex128)
            incoming[selected[0]] = 2 * np.exp(-2j * k[selected[0], 2] * 130)
            record("physical_incident_alpha", a["incident_alpha"], incoming)
            value = reference_scatter(
                -traction * (incoming * bridge if ledger else incoming)[:, None],
                data,
                tables,
                ledger=ledger,
            )
            field = "incident_ledger_rhs" if ledger else "incident_rhs"
            record(field, a[field], value)
            reference_outputs[field] = np.asarray(value, np.complex128)
        for name in ("generic", "seam"):
            for field in ("components", "recover"):
                factor = bridge[:, None] if field == "components" else bridge
                record(
                    name + "_bridge_" + field,
                    a[name + "_ledger_" + field],
                    a[name + "_" + field] * factor,
                )
            for field in ("apply", "adjoint", "modal_rhs"):
                record(
                    name + "_bridge_" + field,
                    a[name + "_ledger_" + field],
                    a[name + "_" + field],
                )
        record(
            "incident_coordinate_bridge", a["incident_ledger_rhs"], a["incident_rhs"]
        )
    save_reference(reference_outputs)
    return dict(
        degree=p,
        rows=index["rows"],
        facets=2176,
        mode_count=32060,
        checked_metrics=count,
        failed_metrics=failed,
        maximum_original_relative=max(v["relative"] for v in maximum.values()),
        maximum_by_field=maximum,
        moment_maximum_absolute=moment_error,
        oracle_maximum_absolute=oracle_error,
        reference_arithmetic="saved Decimal110 moments; independent y-before-x extended contractions",
        complete_mode_and_trace_coverage=True,
        source_action_API_called_by_checker=False,
        passed=failed == 0,
    )
