"""Target p6 boundary witnesses only: no volume form, factor or PDE solve.

Small native meshes are independent oracles. Production tile creation uses
one cell's geometry, full native facet tabulation and canonical dual map; it
never allocates an all-target vector and then slices it.
"""

import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.boundary_witness_scope import PLAN, read_stage
from src.solvers.bounded_port_provider import json_bytes
from src.solvers.port_component_study import array_file, environment, relative
from src.solvers.tiled_port_action import PortTile, TiledPortAction


def complex_value(v):
    return complex(v["real"], v["imag"]) if isinstance(v, dict) else complex(v)


def parent_inventory():
    plan = json.loads(PLAN.read_text())
    pointer = plan["inventory_parent"]
    path = Path(pointer["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer["sha256"]:
        raise ValueError("frozen V36 inventory hash")
    record = json.loads(path.read_text())
    mode = record["ordered_modes"]
    mp = Path(mode["path"])
    if hashlib.sha256(mp.read_bytes()).hexdigest() != mode["sha256"]:
        raise ValueError("frozen complete ordered mode hash")
    return record, json.loads(mp.read_text())


def choose_modes(rows):
    selected = {}
    for side in ("top", "bottom"):
        for pol in ("s", "p"):
            group = [r for r in rows if r["side"] == side and r["polarization"] == pol]
            picks = [
                min(
                    (r for r in group if r["m"] == r["n"] == 0),
                    key=lambda r: r["mode_index"],
                ),
                min(
                    group,
                    key=lambda r: (-abs(complex_value(r["alpha"])), r["mode_index"]),
                ),
                min(
                    group,
                    key=lambda r: (-abs(complex_value(r["gamma"])), r["mode_index"]),
                ),
                min(
                    (
                        r
                        for r in group
                        if r["propagating"] and abs(complex_value(r["beta"])) > 0
                    ),
                    key=lambda r: (abs(complex_value(r["beta"])), r["mode_index"]),
                ),
                min((r for r in group if r["n"] != 0), key=lambda r: r["mode_index"]),
                min(
                    (
                        r
                        for r in group
                        if complex_value(r["alpha"]) != 0
                        and complex_value(r["gamma"]) != 0
                    ),
                    key=lambda r: r["mode_index"],
                ),
            ]
            for r in picks:
                selected[r["mode_index"]] = r
    return [selected[i] for i in sorted(selected)]


def patch_plan(axes):
    x, y, z = [np.array(axes[k]) for k in ("x", "y", "z")]

    def pick(a, maximum=False):
        d = np.diff(a)
        choices = np.arange(1, len(d) - 1)
        return int(choices[np.argmax(d[choices]) if maximum else np.argmin(d[choices])])

    ix, iy = pick(x), pick(y)
    jx, jy = pick(x, True), pick(y, True)
    classes = [
        ("min_ordinary", [(ix, iy), (ix + 1, iy)]),
        ("max_ordinary", [(jx, jy), (jx + 1, jy)]),
        ("x_seam", [(0, iy), (len(x) - 2, iy)]),
        ("xy_corner", [(i, j) for i in (0, len(x) - 2) for j in (0, len(y) - 2)]),
    ]
    result = []
    for name, faces in classes:
        cells = []
        for side, k in [("bottom", 0), ("top", len(z) - 2)]:
            for i, j in faces:
                cells.append(
                    {
                        "indices": [i, j, k],
                        "side": side,
                        "bounds_nm": [
                            [float(x[i]), float(x[i + 1])],
                            [float(y[j]), float(y[j + 1])],
                            [float(z[k]), float(z[k + 1])],
                        ],
                    }
                )
        result.append({"name": name, "cells": cells})
    if sum(len(c["cells"]) for c in result) > 32:
        raise ValueError("native hex witness cap")
    return result


def identity(folder):
    from src.solvers.solver_consumer_contract import compare_fields, complex_distance

    parent, rows = parent_inventory()
    chosen = choose_modes(rows)
    patches = patch_plan(parent["capacity"]["axes_nm"])
    if len(chosen) > 24 or len(rows) != 32060:
        raise ValueError("fixed target mode witness cap/inventory")
    contract = parent["contract"]
    plan = json.loads(PLAN.read_text())
    # Published data have a different scaled geometry/p/material/mode inventory.
    # Runtime/scientific qualification is absent for the restored p6 source.
    required = {
        "geometry": {
            "bounds_nm": contract["regular_geometry"]["bounds_nm"],
            "block_dimensions_nm": [17.0, 25.0, 120.0],
            "void_box_nm": None,
        },
        "material": contract["n_si"],
        "wavelength": 0.7,
        "incidence": contract["incidence"],
        "background": "layered",
        "modes": {
            "count": 32060,
            "sha256": parent["inventory"]["original_mode_manifest_sha256"],
        },
        "reference_planes": contract["regular_geometry"]["reference_planes_nm"],
        "complex_floquet": rows[0]["floquet_phases"],
        "degree": 6,
        "canonical_rows": parent["capacity"]["counts"]["independent_trace_rows"],
        "internal_recovery": "full original 3D affine recovery required",
    }
    offered = plan["dot_offered_fields"]
    consumer = compare_fields(required, offered, scientific_qualified=False)
    consumer["material_difference_norm"] = complex_distance(
        required["material"], offered["material"]
    )
    witness = {
        "schema": "target-p6-boundary.witness-plan.v1",
        "selected_modes": chosen,
        "patches": patches,
        "ordered_inventory_sha256": parent["ordered_modes"]["sha256"],
        "global_period_nm": [50, 25],
        "native_hex_count": sum(len(p["cells"]) for p in patches),
        "degree": 6,
        "quadrature_degrees": [15, 30, 60],
        "mode_selection_rule": plan["mode_selection_rule"],
        "pre_numerical_selection": True,
    }
    write_json(folder / "witness_plan.json", witness)
    write_json(folder / "consumer.json", consumer)
    return {
        "status": "BOUNDARY_WITNESS_PREREGISTERED",
        "consumer": consumer,
        "dot_readonly": plan["dot_readonly"],
        "witness_plan": {
            "path": str(folder / "witness_plan.json"),
            "sha256": hashlib.sha256(
                (folder / "witness_plan.json").read_bytes()
            ).hexdigest(),
        },
        "parent_inventory": plan["inventory_parent"],
        "environment": environment(),
        "native_hex_count": witness["native_hex_count"],
        "selected_mode_count": len(chosen),
        "legacy_v36_scope": "LEGACY_CLIPPED_SURFACE_EQUIVALENCE",
        "volume_action_count": 0,
        "new_LU": 0,
        "target_solve": False,
    }


def build_patch(description, cfg):
    import basix.ufl
    import ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI

    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        AirBox3DMesh,
        _mark_boundary_facets,
        _mark_cells,
    )

    points = []
    lookup = {}
    cells = []
    for cell in description["cells"]:
        bounds = cell["bounds_nm"]
        ids = []
        for zz in bounds[2]:
            for yy in bounds[1]:
                for xx in bounds[0]:
                    key = (xx, yy, zz)
                    if key not in lookup:
                        lookup[key] = len(points)
                        points.append(key)
                    ids.append(lookup[key])
        cells.append(ids)
    domain = ufl.Mesh(basix.ufl.element("Lagrange", "hexahedron", 1, shape=(3,)))
    msh = mesh.create_mesh(
        MPI.COMM_WORLD,
        np.asarray(cells, np.int64),
        domain,
        np.asarray(points, np.float64),
        partitioner=mesh.create_cell_partitioner(mesh.GhostMode.shared_facet),
    )
    tags, facets = _mark_boundary_facets(msh, cfg)
    data = AirBox3DMesh(
        msh,
        _mark_cells(msh, cfg),
        tags,
        facets,
        "hexahedron",
        (len(cells), 1, 1),
        [],
        "target_axes_fragment",
        {},
        {},
        {},
    )
    V = fem.functionspace(msh, basix.ufl.element("N1curl", "hexahedron", 6))
    if np.isin(
        tags.values, [cfg.tags.x_min, cfg.tags.x_max, cfg.tags.y_min, cfg.tags.y_max]
    ).any():
        floquet = build_double_floquet_mpc(V, data, cfg)
    else:
        # Interior fragments contain no periodic entities. Their restriction
        # of the full-target MPC is the identity, not a new small period.
        from types import SimpleNamespace

        import dolfinx_mpc

        mpc = dolfinx_mpc.MultiPointConstraint(V)
        mpc.finalize()
        floquet = SimpleNamespace(mpc=mpc)
    return data, V, floquet


def dual_maps(V, mpc):
    """Explicit G^H pullback on the small witness, preserving tiny entries."""
    n = V.dofmap.index_map.size_local
    coeff, offsets = mpc.coefficients()
    slaves = set(map(int, mpc.slaves))
    maps = []
    for row in range(n):
        if row in slaves:
            masters = np.asarray(mpc.masters.links(row), dtype=np.int64)
            values = np.asarray(
                coeff[offsets[row] : offsets[row + 1]], dtype=np.complex128
            ).conj()
            if any(int(m) in slaves for m in masters):
                raise ValueError("unresolved chained MPC master")
            maps.append((masters, values))
        else:
            maps.append((np.array([row], np.int64), np.ones(1, np.complex128)))
    return maps


def mode_object(row):
    from src.common.modes_3d import PortMode3D

    return PortMode3D(
        side=row["side"],
        m=row["m"],
        n=row["n"],
        polarization=row["polarization"],
        alpha=complex_value(row["alpha"]),
        gamma=complex_value(row["gamma"]),
        beta=complex_value(row["beta"]),
        refractive_index=complex_value(row["refractive_index"]),
        vertical_sign=row["vertical_sign"],
        e_vector=np.array([complex_value(v) for v in row["e_vector"]]),
        k_vector=np.array([complex_value(v) for v in row["k_vector"]]),
        h_vector=np.array([complex_value(v) for v in row["h_vector"]]),
        electric_tangential_norm_sq=row["electric_tangential_norm_sq"],
        power_per_unit_amplitude=row["power_per_unit_amplitude"],
        propagating=row["propagating"],
        rayleigh_warning=row["rayleigh_warning"],
    )


class NativeFacetTiles:
    """One physical face per tile, no global-target numeric creator."""

    def __init__(self, V, mpc, cfg, identities, q, source_identity):
        import basix

        self.V, self.mpc, self.cfg, self.q = V, mpc, cfg, q
        self.identities = identities
        self.source_identity = source_identity
        self.element = V.element.basix_element
        self.dim = self.element.dim
        self.maps = dual_maps(V, mpc)
        msh = V.mesh
        msh.topology.create_entity_permutations()
        self.permutations = msh.topology.get_cell_permutation_info()
        self.rule, self.weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
        self.costs = {
            "tabulation": 0.0,
            "phase_integral": 0.0,
            "orientation": 0.0,
            "canonical_pullback": 0.0,
            "calls": 0,
            "creator_workspace_upper_bytes": int(
                len(self.rule) * self.dim * 3 * 8 * 4 + 512 * self.dim
            ),
            "persistent_geometry_map_bytes": 0,
        }
        self.faces = {}
        ref = basix.cell.geometry(basix.CellType.hexahedron)
        fit = np.column_stack((ref, np.ones(8)))
        for c in range(msh.topology.index_map(3).size_local):
            coords = msh.geometry.x[msh.geometry.dofmap[c]]
            affine = np.linalg.lstsq(fit, coords, rcond=None)[0]
            J = affine[:3].T
            origin = affine[3]
            if np.linalg.norm(fit @ affine - coords) > 1e-11 or np.linalg.det(J) <= 0:
                raise ValueError("affine Piola geometry")
            for side, z in [("bottom", cfg.z_min), ("top", cfg.z_max)]:
                if np.isclose(
                    coords[:, 2].min() if side == "bottom" else coords[:, 2].max(), z
                ):
                    self.faces[f"{side}:cell-{c}"] = (
                        c,
                        J,
                        origin,
                        0.0 if side == "bottom" else 1.0,
                    )
        self.costs["persistent_geometry_map_bytes"] = sum(
            a.nbytes + v.nbytes for a, v in self.maps
        ) + sum(J.nbytes + o.nbytes for _, J, o, _ in self.faces.values())
        self.tabulation = {}

    def tile_ids(self, i):
        return tuple(
            t for t in self.faces if t.startswith(self.identities[i]["side"] + ":")
        )

    def upper_bytes(self, i, t):
        # Complete cell support plus MPC redirects. Each original local row has
        # at most the explicit bounded number of canonical masters in maps.
        c = self.faces[t][0]
        return 48 * sum(
            len(self.maps[int(row)][0]) for row in self.V.dofmap.cell_dofs(c)
        )

    def components(self, i, t):
        c, J, origin, z = self.faces[t]
        began = perf_counter()
        if z not in self.tabulation:
            points = np.column_stack((self.rule, np.full(len(self.rule), z)))
            self.tabulation[z] = self.element.tabulate(0, points)[0]
        tab = self.tabulation[z]
        self.costs["tabulation"] += perf_counter() - began
        began = perf_counter()
        points = np.column_stack((self.rule, np.full(len(self.rule), z)))
        physical = points @ J.T + origin
        k = np.array([complex_value(v) for v in self.identities[i]["k_vector"]])
        phase = np.exp(1j * (physical @ k))
        # covariant Piola: row vectors multiply J^-1, full 882 basis retained.
        basis = tab @ np.linalg.inv(J)
        area = np.linalg.norm(np.cross(J[:, 0], J[:, 1]))
        local = np.einsum("q,qjc->jc", self.weights * phase * area, basis)[
            :, :2
        ].astype(np.complex128)
        self.costs["phase_integral"] += perf_counter() - began
        began = perf_counter()
        local = np.ascontiguousarray(local)
        self.V.element.T_apply(local.view(np.float64).ravel(), self.permutations[c : c + 1], 4)
        self.costs["orientation"] += perf_counter() - began
        began = perf_counter()
        rows = []
        values = []
        for j, row in enumerate(self.V.dofmap.cell_dofs(c)):
            masters, coeff = self.maps[int(row)]
            rows.extend(masters)
            values.extend(coeff[:, None] * local[j])
        rows = np.asarray(rows, np.int64)
        values = np.asarray(values, np.complex128)
        unique, inverse = np.unique(rows, return_inverse=True)
        out = np.zeros((len(unique), 2), np.complex128)
        np.add.at(out, inverse, values)
        self.costs["canonical_pullback"] += perf_counter() - began
        self.costs["calls"] += 1
        return unique, out

    def load_tile(self, i, t, source_identity):
        if source_identity != self.source_identity:
            raise ValueError("facet source identity")
        rows, components = self.components(i, t)
        row = self.identities[i]
        e = np.array([complex_value(v) for v in row["e_vector"]])
        traction = np.array([complex_value(v) for v in row["traction_vector"]])
        C = np.asarray(components @ (-traction[:2]), np.complex128)
        D = np.asarray((components @ e[:2]).conj(), np.complex128)
        for a in (rows, C, D):
            a.flags.writeable = False
        return PortTile(t, rows, C, rows, D)


def dense_tiles(source, i, n):
    C = np.zeros(n, np.complex128)
    D = np.zeros(n, np.complex128)
    raw_components = np.zeros((n, 2), np.complex128)
    for t in source.tile_ids(i):
        rows, values = source.components(i, t)
        np.add.at(raw_components, rows, values)
        tile = source.load_tile(i, t, source.source_identity)
        np.add.at(C, tile.coupling_rows, tile.coupling_values)
        np.add.at(D, tile.projection_rows, tile.projection_values)
    return C, D, raw_components


def clip_audit(components, e, traction):
    first = components.copy()
    stages = []
    for j in range(2):
        threshold = max(1e-30, 1e-13 * float(np.max(abs(first[:, j]))))
        removed = (abs(first[:, j]) <= threshold) & (first[:, j] != 0)
        stages.append(
            {
                "component": j,
                "threshold": threshold,
                "count": int(removed.sum()),
                "norm": float(np.linalg.norm(first[removed, j])),
                "max_absolute": float(np.max(abs(first[removed, j])))
                if removed.any()
                else 0.0,
                "rows": np.flatnonzero(removed).tolist(),
            }
        )
        first[abs(first[:, j]) <= threshold, j] = 0
    original = [components @ (-traction[:2]), (components @ e[:2]).conj()]
    clipped = [first @ (-traction[:2]), (first @ e[:2]).conj()]
    second = []
    for k in range(2):
        value = clipped[k]
        threshold = max(1e-30, 1e-13 * float(np.max(abs(value))))
        removed = (abs(value) <= threshold) & (value != 0)
        second.append(
            {
                "kind": "C" if k == 0 else "D",
                "threshold": threshold,
                "count": int(removed.sum()),
                "norm": float(np.linalg.norm(value[removed])),
                "max_absolute": float(np.max(abs(value[removed])))
                if removed.any()
                else 0.0,
                "rows": np.flatnonzero(removed).tolist(),
            }
        )
        value[abs(value) <= threshold] = 0
    return {
        "first": stages,
        "second": second,
        "C_difference": relative(clipped[0], original[0]),
        "D_difference": relative(clipped[1], original[1]),
        "deleted_empty_C": bool(np.any(original[0]) and not np.any(clipped[0])),
        "deleted_empty_D": bool(np.any(original[1]) and not np.any(clipped[1])),
    }, clipped


def patch(folder):
    from src.solvers.dtn_port_3d import (
        _assemble_mpc_form_vector,
        _ReusableSurfaceComponentAssembler,
        _set_scalar_constant,
    )
    from src.solvers.target_port_preparation import target_config

    env = environment(fe=True)
    cfg, _ = target_config()
    prereg, _ = read_stage("IDENTITY")
    wp = prereg["witness_plan"]
    path = Path(wp["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != wp["sha256"]:
        raise ValueError("pre-registered witness identity")
    plan = json.loads(path.read_text())
    all_records = []
    patch_records = []
    setup_cost = {}
    for description in plan["patches"]:
        began = perf_counter()
        data, V, floquet = build_patch(description, cfg)
        setup_cost[description["name"]] = perf_counter() - began
        n = int(V.dofmap.index_map.size_global)
        rows = []
        for i, r in enumerate(plan["selected_modes"]):
            row = dict(r, original_mode_index=r["mode_index"], mode_index=i)
            rows.append(row)
        previous = {}
        q_records = []
        sources = {}
        for q in (15, 30, 60):
            srcid = hashlib.sha256(
                json_bytes([wp, description, q, os.environ["TASK042_RUN_SOURCE"]])
            ).hexdigest()
            source = NativeFacetTiles(V, floquet.mpc, cfg, rows, q, srcid)
            for i, row in enumerate(rows):
                row["tile_ids"] = list(source.tile_ids(i))
            begun = perf_counter()
            assemblers = {
                (side, j): _ReusableSurfaceComponentAssembler(
                    V,
                    data,
                    cfg.tags.z_max if side == "top" else cfg.tags.z_min,
                    j,
                    quadrature_degree=q,
                )
                for side in ("top", "bottom")
                for j in (0, 1)
            }
            jit = perf_counter() - begun
            records = []
            numeric = {}
            clips = []
            begun = perf_counter()
            for i, row in enumerate(rows):
                mode = mode_object(row)
                native = np.zeros((n, 2), np.complex128)
                for j in range(2):
                    asm = assemblers[(mode.side, j)]
                    _set_scalar_constant(asm.alpha, mode.alpha)
                    _set_scalar_constant(asm.gamma, mode.gamma)
                    _set_scalar_constant(asm.kz, mode.k_vector[2])
                    vec = _assemble_mpc_form_vector(asm.form, floquet.mpc)
                    try:
                        native[:, j] = vec.array.copy()
                    finally:
                        vec.destroy()
                C, D, manual = dense_tiles(source, i, n)
                e = mode.e_vector
                traction = np.array([complex_value(v) for v in row["traction_vector"]])
                native_C = native @ (-traction[:2])
                native_D = (native @ e[:2]).conj()
                checks = {
                    "components": relative(manual, native),
                    "C": relative(C, native_C),
                    "D": relative(D, native_D),
                }
                if q > 15:
                    checks["previous_q_C"] = relative(native_C, previous[i][0])
                    checks["previous_q_D"] = relative(native_D, previous[i][1])
                previous[i] = (native_C.copy(), native_D.copy())
                clipping, clipped = clip_audit(native, e, traction)
                records.append(
                    {
                        "index": i,
                        "original_index": row["original_mode_index"],
                        "mode": [row["side"], row["m"], row["n"], row["polarization"]],
                        "checks": checks,
                        "clipping": clipping,
                    }
                )
                numeric.update(
                    {
                        f"C_{i}": native_C,
                        f"D_{i}": native_D,
                        f"tileC_{i}": C,
                        f"tileD_{i}": D,
                        f"native_components_{i}": native,
                        f"tile_components_{i}": manual,
                    }
                )
                clips.extend([clipped[0], clipped[1]])
                write_json(
                    folder / "pending.json",
                    {"patch": description["name"], "q": q, "records": records},
                )
            native_cost = perf_counter() - begun
            file = array_file(folder / f"{description['name']}_q{q}.npz", **numeric)
            write_json(folder / f"{description['name']}_q{q}.json", records)
            q_records.append(
                {
                    "q": q,
                    "points": len(source.rule),
                    "weights_sum": float(sum(source.weights)),
                    "jit_seconds": jit,
                    "native_and_manual_seconds": native_cost,
                    "source_costs": dict(source.costs),
                    "numeric_file": file,
                    "records": records,
                }
            )
            sources[q] = source
            all_records.extend(records)
            del assemblers, numeric, clips
        q30q60 = all(
            c["checks"]["previous_q_C"]["pass_gate"]
            and c["checks"]["previous_q_D"]["pass_gate"]
            for c in q_records[-1]["records"]
        )
        same_q = all(
            c["checks"][k]["pass_gate"]
            for qr in q_records
            for c in qr["records"]
            for k in ("components", "C", "D")
        )
        selected_q = 30 if q30q60 else None
        component_result = {
            "status": "NOT_RUN_QUADRATURE_OR_MAPPING_GATE",
            "same_q_pass": same_q,
            "q30_vs_q60_pass": q30q60,
        }
        if same_q and q30q60:
            source = sources[30]
            identity = [dict(r) for r in rows]
            action = TiledPortAction(
                identity,
                source,
                source_identity=source.source_identity,
                global_rows=n,
                ownership_range=(0, n),
                tile_bytes=128 * 2**10,
            )
            file = q_records[1]["numeric_file"]
            native_saved = np.load(file["path"])
            rng = np.random.default_rng(423701)
            x = rng.normal(size=n) + 1j * rng.normal(size=n)
            y = rng.normal(size=n) + 1j * rng.normal(size=n)
            x[np.asarray(floquet.mpc.slaves, dtype=int)] = 0
            y[np.asarray(floquet.mpc.slaves, dtype=int)] = 0
            C = np.column_stack([native_saved[f"C_{i}"] for i in range(len(rows))])
            D = np.row_stack([native_saved[f"D_{i}"] for i in range(len(rows))])
            H = np.array([r["projection_denominator"] for r in rows])
            began = perf_counter()
            nf = action.apply(x)
            nh = action.apply(y, adjoint=True)
            na = action.recover(x)
            modal = action.modal_rhs(np.ones(len(rows), complex))
            linear = action.apply((0.37 - 0.91j) * x)
            measured = perf_counter() - began
            of = C @ ((D @ x) / H)
            oh = D.conj().T @ ((C.conj().T @ y) / H)
            oa = D @ x / H
            om = C @ np.ones(len(rows))
            checks = {
                k: relative(a, b)
                for k, a, b in [
                    ("forward", nf, of),
                    ("adjoint", nh, oh),
                    ("port", na, oa),
                    ("modal_rhs", modal, om),
                    ("linearity", linear, (0.37 - 0.91j) * nf),
                ]
            }
            dual_num = float(abs(np.vdot(y, nf) - np.vdot(nh, x)))
            dual_den = float(
                np.linalg.norm(y) * np.linalg.norm(nf)
                + np.linalg.norm(nh) * np.linalg.norm(x)
            )
            checks["dual"] = {
                "numerator": dual_num,
                "denominator": dual_den,
                "relative": dual_num / dual_den,
                "pass_gate": dual_num <= 1e-10 * dual_den,
            }
            h_errors = []
            powers = []
            for r in rows:
                k = np.array([complex_value(v) for v in r["k_vector"]])
                e = np.array([complex_value(v) for v in r["e_vector"]])
                hh = np.cross(k, e) / (cfg.k0 * cfg.mu_r)
                z = r["reference_plane_nm"]
                phase = np.exp(1j * k[2] * z)
                actual_h = (
                    cfg.period_x
                    * cfg.period_y
                    * float(np.vdot(e[:2], e[:2]).real)
                    * abs(phase) ** 2
                )
                h_errors.append(
                    abs(actual_h - r["projection_denominator"])
                    / r["projection_denominator"]
                )
                flux = (
                    0.5
                    * float(np.cross(e, np.conj(hh))[2].real)
                    * abs(phase) ** 2
                    * cfg.period_x
                    * cfg.period_y
                    * (1 if r["side"] == "top" else -1)
                )
                powers.append(abs(flux - r["power_at_reference_unit_amplitude"]))
            checks["H"] = {
                "max_relative": max(h_errors),
                "pass_gate": max(h_errors) <= 1e-10,
            }
            checks["unit_power"] = {
                "max_absolute": max(powers),
                "pass_gate": max(powers) <= 1e-10,
            }
            witness = array_file(
                folder / f"{description['name']}_actions.npz",
                x=x,
                y=y,
                forward=nf,
                old_forward=of,
                adjoint=nh,
                old_adjoint=oh,
                amplitudes=na,
                old_amplitudes=oa,
                modal=modal,
                old_modal=om,
                linear=linear,
            )
            component_result = {
                "status": "TILED_P6_PATCH_QUALIFIED"
                if all(c["pass_gate"] for c in checks.values())
                else "NUMERICAL_GATE_FAILED",
                "checks": checks,
                "action_wall_seconds": measured,
                "action_stats": action.stats,
                "mode_receipts": list(action.receipts.values()),
                "witness": witness,
                "q": 30,
                "tile_byte_cap": 128 * 2**10,
                "H": h_errors,
                "unit_power_absolute_errors": powers,
            }
            native_saved.close()
        patch_records.append(
            {
                "description": description,
                "storage_rows": n,
                "canonical_non_slave_rows": n - len(floquet.mpc.slaves),
                "slave_rows": list(map(int, floquet.mpc.slaves)),
                "q_records": q_records,
                "selected_q": selected_q,
                "component": component_result,
                "setup_seconds": setup_cost[description["name"]],
            }
        )
        write_json(folder / "patch_records_pending.json", patch_records)
        del sources, source, V, data, floquet, previous
    qualified = all(
        r["component"]["status"] == "TILED_P6_PATCH_QUALIFIED" for r in patch_records
    )
    return {
        "status": "TARGET_P6_BOUNDARY_WITNESS_QUALIFIED"
        if qualified
        else "TARGET_P6_BOUNDARY_WITNESS_NOT_QUALIFIED",
        "environment": env,
        "patches": patch_records,
        "native_hex_count": plan["native_hex_count"],
        "selected_mode_count": len(rows),
        "coverage": "finite target p6 surface fragments and selected modes; real FE MPI1 only",
        "complete_target_modes_run": False,
        "full_target_DoF_graph": False,
        "volume_forms": False,
        "target_mesh_created": False,
        "volume_action_count": 0,
        "LU": 0,
        "QR": 0,
        "solve": 0,
        "training": 0,
        "official_RTA": False,
        "reference_read": False,
        "legacy_clipping_qualified": all(
            r["clipping"]["C_difference"]["pass_gate"]
            and r["clipping"]["D_difference"]["pass_gate"]
            for r in all_records
        ),
    }


def execute(role, folder, state):
    if role == "IDENTITY":
        return identity(folder)
    if role == "PATCH":
        return patch(folder)
    from benchmarks.check_boundary_witness import check_saved

    result = check_saved()
    if role == "DEPLOY":
        result.update(
            status="TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED",
            provider="src/solvers/tiled_port_action.py",
            consumer="src/solvers/solver_consumer_contract.py",
            readonly=True,
            source_sha=state["source_sha"],
        )
    return result
