"""Thin full-surface provider for the frozen main numerical API.

No new boundary solver: FacetPolynomial, BoundaryLayout and
DirectionalBoundaryAction all come from the c354afa snapshot. This module
selects the qualified input and complete facet range, and saves witnesses.
"""

import hashlib
import json
from pathlib import Path
import shutil
import time

import numpy as np

INSTANCE = "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"
GENERIC_SEED = 4212801
SEAM_SEED = 4212901


def seam_rows(layout):
    rows = []
    for side in ("bottom", "top"):
        maps = layout.maps[side]
        rows.extend(
            [maps[0].ravel(), maps[-1].ravel(), maps[:, 0].ravel(), maps[:, -1].ravel()]
        )
    return np.unique(np.concatenate(rows))


def witnesses(layout):
    result = {}
    for name, seed in (("generic", GENERIC_SEED), ("seam", SEAM_SEED)):
        rng = np.random.default_rng(seed)
        t = rng.normal(size=layout.rows) + 1j * rng.normal(size=layout.rows)
        d = rng.normal(size=layout.rows) + 1j * rng.normal(size=layout.rows)
        a = rng.normal(size=32060) + 1j * rng.normal(size=32060)
        if name == "seam":
            retained = seam_rows(layout)
            mask = np.zeros(layout.rows, bool)
            mask[retained] = True
            t[~mask] = 0
            d[~mask] = 0
        result[name] = dict(
            trace=np.asarray(t, np.complex128),
            dual=np.asarray(d, np.complex128),
            alpha=np.asarray(a, np.complex128),
        )
    return result


class FullSurfaceAdapter:
    """Explicit input provider into actual unchanged main class methods."""

    def __init__(self, layout, modes, *, action_class=None):
        if action_class is None:
            from src.solvers.directional_boundary import DirectionalBoundaryAction

            action_class = DirectionalBoundaryAction
        self.layout = layout
        self.modes = modes
        self.action = action_class(layout, modes, 60, face_inventory=None)
        if self.action.face_inventory is not None or self.action.face_masks is not None:
            raise ValueError("W29_COMPLETE_FACETS_REQUIRED")

    def evaluate(self, state):
        action = self.action
        return dict(
            components=action.project_components(state["trace"]),
            recover=action.recover(state["trace"]),
            apply=action.apply(state["trace"]),
            adjoint=action.apply(state["dual"], adjoint=True),
            modal_rhs=action.modal_rhs(state["alpha"]),
        )


def relative_receipt(path, run, helpers):
    row = helpers.file_receipt(path)
    row["path"] = str(Path(path).relative_to(run))
    return row


def layout_arrays(layout, ledger):
    p = layout.polynomial
    arrays = dict(
        degree=np.array(layout.p),
        x=layout.x,
        y=layout.y,
        ledger_x=ledger.x,
        ledger_y=ledger.y,
        phases=np.array(layout.phases),
        element_geometry=np.asarray(
            __import__("basix").cell.geometry(__import__("basix").CellType.hexahedron)
        ),
        edge_vertices=np.asarray(
            __import__("basix").cell.topology(__import__("basix").CellType.hexahedron)[
                1
            ],
            np.int64,
        ),
    )
    arrays.update(
        edge_dofs=np.asarray(p.element.entity_dofs[1], np.int64),
        face_dofs=np.asarray(p.element.entity_dofs[2], np.int64),
    )
    for side in ("bottom", "top"):
        arrays.update(
            {
                side + "_coeff": p.coefficients[side],
                side + "_active": p.active[side],
                side + "_map": layout.maps[side],
                side + "_weights": layout.weights[side],
            }
        )
    return arrays


def qualify_full_moments(root, modes, layout, ledger, binding, run, helpers):
    """Reuse exact binary64 frequencies; only missing values use existing oracle."""
    from src.solvers.directional_boundary import zvalue
    from numpy.polynomial.legendre import legvander
    import basix

    original = Path(binding["spec"]["v28_reference_root"])
    oldindex = json.loads((original / "chunk_index.json").read_text())
    oldrow = oldindex["oracle"]
    oldpath = original / oldrow["path"]
    if (
        oldpath.stat().st_size != oldrow["bytes"]
        or hashlib.sha256(oldpath.read_bytes()).hexdigest() != oldrow["sha256"]
    ):
        raise ValueError("W29_INHERITED_ORACLE_BYTES_HASH")
    with np.load(oldpath, allow_pickle=False) as f:
        old = {k: f[k] for k in f.files}
    oldlookup = {float(w): i for i, w in enumerate(old["frequencies"])}
    frequencies = {0.0}
    for axes in ((layout.x, layout.y), (ledger.x, ledger.y)):
        for axis, coords in enumerate(axes):
            for k in {zvalue(m["k_vector"][axis]) for m in modes}:
                if k.imag != 0:
                    raise ValueError("W29_FIXED_REAL_TANGENTIAL_FREQUENCY")
                for width in np.diff(coords):
                    frequencies.update((float(-k.real * width), float(k.real * width)))
    frequencies = np.asarray(sorted(frequencies), np.float64)
    if np.any(abs(frequencies) > 56):
        raise ValueError("W29_FREQUENCY_OUTSIDE_QUALIFIED_RANGE")
    prior = binding["spec"]["prerequisite_paths"].get("surface_p4")
    if layout.p == 6 and prior and (Path(prior) / "surface_index.json").is_file():
        index = json.loads((Path(prior) / "surface_index.json").read_text())
        if index.get("complete") is True and index.get("instance_id") == INSTANCE:
            row = index["arrays"]["reference"]
            path = Path(prior) / row["path"]
            if (
                path.stat().st_size != row["bytes"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]
            ):
                raise ValueError("W29_P4_REFERENCE_REUSE_IDENTITY")
            with np.load(path, allow_pickle=False) as raw:
                values = {k: raw[k] for k in raw.files}
            if not np.array_equal(values["frequencies"], frequencies):
                raise ValueError("W29_P4_P6_FREQUENCY_REUSE_MISMATCH")
            helpers.atomic_arrays(run / "moment_reference.npz", values)
            helpers.atomic_json(
                run / "moment_reference_decimal.json",
                dict(
                    complete=True,
                    inherited_p4_reference=dict(root=str(prior), **row),
                    independent_values_not_regenerated=True,
                    exact_binary64_reused=len(frequencies),
                    newly_qualified=0,
                    fixed_precision=[80, 110],
                    maximum_degree=6,
                ),
            )
            return dict(
                count=len(frequencies),
                reused=len(frequencies),
                new=0,
                reused_p4=True,
                maximum_frequency=float(np.max(abs(frequencies))),
            )
    oracle = helpers.oracle_module(root)
    decimal = helpers.load_file(
        "_w29_decimal_oracle", root / "benchmarks/portable_facet_oracle.py"
    )
    rule, weights = basix.make_quadrature(basix.CellType.interval, 60)
    values = legvander(2 * rule[:, 0] - 1, 6)
    saved = dict(
        frequencies=frequencies,
        reference80=[],
        reference110=[],
        analytic=[],
        integration_candidate=[],
    )
    strings, reused = [], 0
    for i, w in enumerate(frequencies):
        helpers.guard(binding)
        if float(w) in oldlookup:
            j = oldlookup[float(w)]
            a, b, c = old["reference80"][j], old["reference110"][j], old["analytic"][j]
            reused += 1
        else:
            a, astrings = decimal.moments(float(w), 6, 80)
            b, bstrings = decimal.moments(float(w), 6, 110, direct_quadrature=True)
            c = oracle.unit_interval_moments(float(w), 6)
            strings.append(
                dict(omega_hex=float(w).hex(), Decimal80=astrings, Decimal110=bstrings)
            )
        candidate = (weights * np.exp(1j * w * rule[:, 0])) @ values
        if max(float(np.max(abs(a - b))), float(np.max(abs(b - c)))) > 1e-12:
            raise ValueError("W29_INDEPENDENT_MOMENT_REFERENCE_UNRESOLVED")
        for key, value in [
            ("reference80", a),
            ("reference110", b),
            ("analytic", c),
            ("integration_candidate", candidate),
        ]:
            saved[key].append(value)
        if i % 250 == 0:
            print(
                json.dumps(
                    dict(
                        phase="full_surface_reference",
                        complete=i + 1,
                        total=len(frequencies),
                    )
                ),
                flush=True,
            )
    helpers.atomic_arrays(
        run / "moment_reference.npz", {k: np.asarray(v) for k, v in saved.items()}
    )
    helpers.atomic_json(
        run / "moment_reference_decimal.json",
        dict(
            complete=True,
            inherited_oracle=oldrow,
            inherited_root=str(original),
            exact_binary64_reused=reused,
            newly_qualified=len(frequencies) - reused,
            fixed_precision=[80, 110],
            maximum_degree=6,
            values=strings,
        ),
    )
    return dict(
        count=len(frequencies),
        reused=reused,
        new=len(frequencies) - reused,
        maximum_frequency=float(np.max(abs(frequencies))),
    )


def affected_native_columns(layout, ledger, modes, binding, run, helpers):
    """Original q60 local integration, every native column at each new width.

    Mode selection is fixed by physical keys and extrema before scoring. The
    saved checker uses independent frozen moments for every selected column;
    no tiny cell-interior trace is discarded or promoted to a volume gate.
    """
    from src.solvers.directional_boundary import zvalue

    arrays = dict(mode_indices=[], sides=[], origins=[], widths=[], integral=[])
    for coordinates in ((layout.x, layout.y), (ledger.x, ledger.y)):
        unique_x = {}
        unique_y = {}
        for i, w in enumerate(np.diff(coordinates[0])):
            unique_x.setdefault(float(w).hex(), i)
        for j, w in enumerate(np.diff(coordinates[1])):
            unique_y.setdefault(float(w).hex(), j)
        for side_number, side in enumerate(("bottom", "top")):
            ids = [i for i, m in enumerate(modes) if m["side"] == side]
            chosen = sorted(
                set(
                    [
                        next(
                            i
                            for i in ids
                            if (modes[i]["m"], modes[i]["n"], modes[i]["polarization"])
                            == (0, 0, "s")
                        ),
                        max(ids, key=lambda i: abs(zvalue(modes[i]["k_vector"][0]))),
                        max(ids, key=lambda i: abs(zvalue(modes[i]["k_vector"][1]))),
                    ]
                )
            )
            for i in unique_x.values():
                for j in unique_y.values():
                    helpers.guard(binding)
                    dx, dy = np.diff(coordinates[0])[i], np.diff(coordinates[1])[j]
                    origin = np.array(
                        [
                            coordinates[0][i],
                            coordinates[1][j],
                            120.0 if side == "top" else -10.0,
                        ]
                    )
                    for mode_index in chosen:
                        k = np.array([zvalue(v) for v in modes[mode_index]["k_vector"]])
                        value = layout.polynomial.integral_native(
                            side, k, np.diag([dx, dy, 10.0]), origin, 60
                        )
                        arrays["mode_indices"].append(mode_index)
                        arrays["sides"].append(side_number)
                        arrays["origins"].append(origin)
                        arrays["widths"].append([dx, dy])
                        arrays["integral"].append(value)
    helpers.atomic_arrays(
        run / "affected_native_columns.npz",
        {k: np.asarray(v) for k, v in arrays.items()},
    )
    return dict(
        cases=len(arrays["mode_indices"]),
        native_columns=layout.polynomial.element.dim,
        both_coordinates_and_sides=True,
        tiny_internal_columns_retained=True,
        predeclared_modes="00s, maximum abs kx, maximum abs ky for each side",
    )


def produce(root, snapshot, binding, run, helpers, component):
    began = time.monotonic()
    modes = json.loads(Path(binding["spec"]["manifest_path"]).read_text())["modes"]
    modes, physical = component.physical_modes(modes)
    layout, floquet = helpers.layout_for(modes, binding["spec"]["degree"])
    ledger = type(layout)(
        layout.x + 25, layout.y + 12.5, layout.polynomial, layout.phases
    )
    helpers.atomic_arrays(run / "layout.npz", layout_arrays(layout, ledger))
    inherited_root = Path(binding["spec"]["v28_reference_root"])
    inherited_index = json.loads((inherited_root / "chunk_index.json").read_text())
    inherited_basis = inherited_index["layouts"][str(layout.p)]
    basis_path = inherited_root / inherited_basis["path"]
    if (
        basis_path.stat().st_size != inherited_basis["bytes"]
        or hashlib.sha256(basis_path.read_bytes()).hexdigest()
        != inherited_basis["sha256"]
    ):
        raise ValueError("W29_QUALIFIED_NATIVE_BASIS_CHANGED")
    shutil.copyfile(basis_path, run / "qualified_v28_basis.npz")
    definition = dict(
        instance_id=INSTANCE,
        mode_count=32060,
        facets=2 * layout.nx * layout.ny,
        rows=layout.rows,
        q=60,
        witnesses=dict(generic_seed=GENERIC_SEED, seam_seed=SEAM_SEED),
        reference_norm="Euclidean norm of independently contracted saved reference; scalar complex modulus",
        zero_rule="max(reference_norm, binary64 tiny); no fitted floor",
        original_relative_limit=1e-10,
        original_moment_absolute_limit=1e-12,
        B="traction contraction",
        D="electric polarization projection divided by original H",
        recover="per-mode projection/amplitude, not returned FE vector",
        apply="complete surface-return vector",
    )
    helpers.atomic_json(run / "reference_definition.json", definition)
    moment_stats = qualify_full_moments(
        root, modes, layout, ledger, binding, run, helpers
    )
    native_stats = affected_native_columns(layout, ledger, modes, binding, run, helpers)
    before = time.monotonic()
    provider = FullSurfaceAdapter(layout, modes)
    absolute = FullSurfaceAdapter(ledger, modes)
    construction_seconds = time.monotonic() - before
    e = np.array(
        [[complex(v["real"], v["imag"]) for v in m["e_vector"][:2]] for m in modes]
    )
    traction = np.array(
        [
            [complex(v["real"], v["imag"]) for v in m["traction_vector"][:2]]
            for m in modes
        ]
    )
    H = np.array([m["projection_denominator"] for m in modes])
    k = np.array(
        [[complex(v["real"], v["imag"]) for v in m["k_vector"]] for m in modes]
    )
    bridge = np.exp(-1j * (k[:, :2] @ np.array([25.0, 12.5])))
    inputs = witnesses(layout)
    arrays = dict(
        e=e, traction=traction, H=H, k=k, bridge=bridge, seam_rows=seam_rows(layout)
    )
    actions_started = time.monotonic()
    for name, state in inputs.items():
        helpers.guard(binding)
        values = provider.evaluate(state)
        shifted_state = dict(state, alpha=state["alpha"] * bridge)
        shifted = absolute.evaluate(shifted_state)
        for key, value in state.items():
            arrays[name + "_" + key] = value
        for key, value in values.items():
            arrays[name + "_" + key] = value
        for key, value in shifted.items():
            arrays[name + "_ledger_" + key] = value
        print(
            json.dumps(
                dict(
                    phase="main_api_complete_surface",
                    degree=layout.p,
                    witness=name,
                    complete_facets=definition["facets"],
                    complete_modes=len(modes),
                )
            ),
            flush=True,
        )
    kin, kout, ein, incoming = component.physical_incidence(modes)
    arrays.update(
        incident_alpha=incoming,
        incident_rhs=provider.action.modal_rhs(incoming),
        incident_ledger_rhs=absolute.action.modal_rhs(incoming * bridge),
        incident_k_in=kin,
        incident_k_out=kout,
        incident_e=ein,
    )
    actions_seconds = time.monotonic() - actions_started
    helpers.atomic_arrays(run / "actions.npz", arrays)
    table_arrays = {}
    for prefix, adapter in [("center", provider), ("ledger", absolute)]:
        for side, values in adapter.action.tables.items():
            for key, value in zip(
                ("fx", "fy", "ix", "iy", "zphase"), values, strict=True
            ):
                table_arrays[prefix + "_" + side + "_" + key] = value
    helpers.atomic_arrays(run / "candidate_tables.npz", table_arrays)
    import inspect

    api = dict(
        provider="Qualified V28 instance through FullSurfaceAdapter",
        instance_id=INSTANCE,
        math_commit=binding["math_source_sha"],
        native_classes=[
            type(layout.polynomial).__name__,
            type(layout).__name__,
            type(provider.action).__name__,
        ],
        numerical_module=str(
            Path(inspect.getsourcefile(type(provider.action))).relative_to(snapshot)
        ),
        face_inventory=None,
        face_masks=None,
        actual_facets=definition["facets"],
        actual_rows=layout.rows,
        actual_modes=len(modes),
        statistics=dict(center=provider.action.stats, ledger=absolute.action.stats),
        cache_bytes=dict(
            center=provider.action.cache_bytes, ledger=absolute.action.cache_bytes
        ),
        mathematical_source_unmodified=True,
        remote_main_ingested=False,
    )
    helpers.atomic_json(run / "main_api_call.json", api)
    receipts = {
        name: relative_receipt(run / filename, run, helpers)
        for name, filename in [
            ("layout", "layout.npz"),
            ("actions", "actions.npz"),
            ("candidate_tables", "candidate_tables.npz"),
            ("reference", "moment_reference.npz"),
            ("reference_decimal", "moment_reference_decimal.json"),
            ("native_columns", "affected_native_columns.npz"),
            ("qualified_basis", "qualified_v28_basis.npz"),
            ("definition", "reference_definition.json"),
            ("main_api", "main_api_call.json"),
        ]
    }
    helpers.atomic_json(
        run / "surface_index.json",
        dict(
            schema="w1-full-surface-index.v29",
            instance_id=INSTANCE,
            degree=layout.p,
            complete=True,
            mode_count=32060,
            facets=definition["facets"],
            rows=layout.rows,
            reference_frozen_before_candidate=True,
            profile=binding["spec"]["integration_profile"],
            arrays=receipts,
        ),
    )
    return dict(
        status="FULL_SURFACE_COMPLETE_PENDING_INDEPENDENT_CHECK",
        degree=layout.p,
        facets=definition["facets"],
        rows=layout.rows,
        mode_count=32060,
        reference_stats=moment_stats,
        affected_native_columns=native_stats,
        raw=helpers.file_receipt(run / "surface_index.json"),
        raw_files=[helpers.file_receipt(run / r["path"]) for r in receipts.values()],
        main_api=api,
        physical=physical,
        floquet=floquet,
        original_q60_only=True,
        cold_seconds=time.monotonic() - began,
        construction_seconds=construction_seconds,
        actual_all_actions_seconds=actions_seconds,
        no_global_dense_trace_mode_matrix=True,
        new_Maxwell_factor_solve_Gram_NN_calls=0,
    )
