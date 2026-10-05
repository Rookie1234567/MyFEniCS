"""Independent public Function.eval side/component action reference.

Receives three caller-owned, already backsubstituted/scattered Functions.
Creates no mesh, space, form, mode, factor, carrier or PDE. This route never
uses the candidate's tabulation, selected closure rows or local contractions.
Unchanged byte-pinned mass-v2 state, phase, unit-mass and operation helpers
remain the independent implementation's source of those public contracts.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from target_boundary_support_pilot import public_helpers

SCHEMA = "task40extra.boundary-support-function-eval-reference.v1"
OPERATION_RTOL = 1e-10
MAX_CHUNK_SIZE = 128


def reference_rectangle(facet, cell, face_xyz, cell_xyz, zplane, side, reference):
    """Independent literal affine rectangle check, allowing signed axis maps."""
    if (face_xyz.shape != (4, 3) or cell_xyz.shape != (8, 3)
            or face_xyz.dtype != np.float64 or cell_xyz.dtype != np.float64
            or not np.isfinite(face_xyz).all() or not np.isfinite(cell_xyz).all()
            or side not in ("top", "bottom")):
        raise ValueError("invalid actual side geometry")
    origin = cell_xyz[0]
    J = np.column_stack((cell_xyz[1] - origin, cell_xyz[2] - origin, cell_xyz[4] - origin))
    if (not np.all(np.count_nonzero(J, axis=0) == 1) or not np.all(np.count_nonzero(J, axis=1) == 1)
            or not np.array_equal(origin + reference._REFERENCE_VERTICES @ J.T, cell_xyz)):
        raise ValueError("independent literal affine map validation failed")
    plane = float(np.max(cell_xyz[:, 2]) if side == "top" else np.min(cell_xyz[:, 2]))
    if plane != zplane or not np.all(face_xyz[:, 2] == zplane):
        raise ValueError("actual facet not exact associated boundary plane")
    xmin, ymin = face_xyz[:, :2].min(axis=0)
    xmax, ymax = face_xyz[:, :2].max(axis=0)
    wanted = {(float(x), float(y), float(zplane)) for x in (xmin, xmax) for y in (ymin, ymax)}
    if (set(map(tuple, face_xyz)) != wanted or len(wanted) != 4 or not (xmax > xmin and ymax > ymin)
            or not all(any(np.array_equal(point, vertex) for vertex in cell_xyz) for point in face_xyz)):
        raise ValueError("independent exact physical rectangle validation failed")
    return reference.FacetRectangle(int(facet), int(cell), float(xmin), float(xmax), float(ymin),
                                    float(ymax), float(zplane))


def reference_rectangles(mesh_data, cfg, budget, reference):
    from dolfinx import mesh as dx_mesh
    msh = mesh_data.mesh
    if (msh.topology.dim != 3 or msh.geometry.dim != 3 or msh.topology.cell_type.name != "hexahedron"
            or msh.geometry.cmap.degree != 1 or msh.geometry.cmap.dim != 8
            or msh.geometry.x.dtype != np.float64 or msh.topology.index_map(3).size_local != 18
            or msh.topology.index_map(3).num_ghosts
            or (cfg.x_min, cfg.x_max, cfg.y_min, cfg.y_max, cfg.domain_z_min, cfg.domain_z_max) != (0, 50, 0, 25, -10, 130)):
        raise ValueError("independent reference requires original 18-cell fixture")
    budget.before("reference_all_side_geometry", 2 << 20)
    msh.topology.create_connectivity(2, 3)
    links = msh.topology.connectivity(2, 3)
    exterior = set(map(int, dx_mesh.exterior_facet_indices(msh.topology)))
    vertices = msh.geometry.x[msh.geometry.dofmap]
    for axis, expected in enumerate(reference.EXPECTED_AXES):
        if not np.array_equal(np.unique(vertices[:, :, axis]), expected):
            raise ValueError("independent actual fixture axes differ")
    for cell, xyz in enumerate(vertices):
        top = xyz[xyz[:, 2] == xyz[:, 2].max()]
        reference_rectangle(-1, cell, top, xyz, float(xyz[:, 2].max()), "top", reference)
    axes = reference.EXPECTED_AXES
    expected_boxes = {(x0, y0, z0, x1, y1, z1) for x0, x1 in zip(axes[0][:-1], axes[0][1:])
                      for y0, y1 in zip(axes[1][:-1], axes[1][1:]) for z0, z1 in zip(axes[2][:-1], axes[2][1:])}
    actual_boxes = {tuple(xyz.min(axis=0)) + tuple(xyz.max(axis=0)) for xyz in vertices}
    if actual_boxes != expected_boxes or len(actual_boxes) != 18:
        raise ValueError("independent all-cell boxes differ")
    result = []
    for side, tag, plane in (("top", cfg.tags.z_max, cfg.domain_z_max), ("bottom", cfg.tags.z_min, cfg.domain_z_min)):
        facets = np.asarray(mesh_data.facet_tags.find(int(tag)), dtype=np.int32)
        if len(facets) != 6 or len(np.unique(facets)) != 6 or not set(map(int, facets)).issubset(exterior):
            raise ValueError("independent side requires six actual exterior facets")
        geometry = dx_mesh.entities_to_geometry(msh, 2, facets, permute=False)
        if geometry.shape != (6, 4):
            raise ValueError("independent exterior facet geometry invalid")
        rectangles = []
        for facet, gdofs in zip(facets, geometry):
            cells = np.asarray(links.links(int(facet)))
            if cells.shape != (1,) or not 0 <= cells[0] < 18:
                raise ValueError("independent exterior association invalid")
            rectangles.append(reference_rectangle(facet, cells[0], msh.geometry.x[gdofs], vertices[cells[0]],
                                                    float(plane), side, reference))
        wanted = {(x0, x1, y0, y1, float(plane)) for x0, x1 in zip(axes[0][:-1], axes[0][1:])
                  for y0, y1 in zip(axes[1][:-1], axes[1][1:])}
        if ({(r.xmin, r.xmax, r.ymin, r.ymax, r.zplane) for r in rectangles} != wanted
                or sum(r.area for r in rectangles) != 1250):
            raise ValueError("independent rectangles do not cover actual side once")
        result.extend((side, r) for r in sorted(rectangles, key=lambda r: (r.xmin, r.ymin, r.facet)))
    if len({r.facet for _, r in result}) != 12:
        raise ValueError("independent actual boundary facets repeat")
    return result


def run_reference(*, V, mesh_data, mpc, cfg, selected_modes, selected_indices, native_fields,
                  independent_states, quadrature_degree, allocation_gate, event, output_dir=None,
                  chunk_size=32):
    """Degree160 → independent public Function.eval degrees168/176."""
    native, reference, pinned = public_helpers()
    if (not callable(allocation_gate) or not callable(event) or type(chunk_size) is not int
            or not 1 <= chunk_size <= MAX_CHUNK_SIZE or quadrature_degree not in (27, 160)
            or len(selected_modes) != 12 or len(selected_indices) != 12 or len(set(selected_indices)) != 12
            or V.mesh is not mesh_data.mesh or V.value_size != 3):
        raise ValueError("invalid independent bounded-reference scope")
    wanted = {(side, m, n, p) for side in ("top", "bottom")
              for m, n in ((0, 0), (-142, -5), (-85, -35)) for p in ("s", "p")}
    if {(m.side, int(m.m), int(m.n), str(m.polarization).lower()) for m in selected_modes} != wanted:
        raise ValueError("independent reference exact twelve actual modes required")
    element = V.element.basix_element
    if (element.family.name != "N1E" or element.cell_type.name != "hexahedron" or element.degree != 6
            or element.dim != 882 or tuple(element.value_shape) != (3,)):
        raise ValueError("independent p6 882-row N1E required")
    groups = {}
    for position, mode in enumerate(selected_modes):
        if (np.shape(mode.k_vector) != (3,) or np.shape(mode.e_vector) != (3,)
                or not all(np.isfinite(v) for v in (mode.alpha, mode.gamma, *mode.k_vector, *mode.e_vector))
                or complex(mode.alpha).imag != 0 or complex(mode.gamma).imag != 0):
            raise ValueError("independent finite actual real transverse phase required")
        groups.setdefault((mode.side, complex(mode.alpha), complex(mode.gamma), complex(mode.k_vector[2])), []).append(position)
    if len(groups) != 6:
        raise ValueError("independent actual six side-phase tuples required")
    budget = native._Budget(allocation_gate, event, persistent=(1 << 20))
    n = int(V.dofmap.index_map.size_local)
    if n != 13224:
        raise ValueError("independent native target row count differs")
    budget.before("reference_public_MPC_state_validation", n * 5 * 16 + (1 << 20))
    states = reference._validate_states(V, mpc, native_fields, independent_states)
    rectangles = reference_rectangles(mesh_data, cfg, budget, reference)
    from basix import CellType, PolysetType, QuadratureType, make_quadrature
    arrays, rules = {}, []
    for increment in (8, 16):
        degree = quadrature_degree + increment
        node_count = ((degree + 2) // 2) ** 2
        budget.before("reference_actual_rule", node_count * 24 + (1 << 20), 12 * node_count * 8)
        points, weights = make_quadrature(CellType.quadrilateral, degree, rule=QuadratureType.gauss_jacobi,
                                        polyset_type=PolysetType.standard)
        mass = reference.unit_mass_metric(weights)
        event({"kind": "boundary_reference_unit_mass_before_gate", "degree": degree, "metric": mass})
        if (points.shape != (node_count, 2) or weights.shape != (node_count,) or points.dtype != np.float64
                or weights.dtype != np.float64 or not mass["passed"] or not np.isfinite(points).all()
                or np.any(points < 0) or np.any(points > 1)):
            raise ValueError("independent actual unmodified Gauss rule invalid")
        budget.persistent = (1 << 20) + node_count * 24 + sum(a.nbytes for a in arrays.values()) + (1 << 20)
        contractions = np.zeros((12, 2, 3), dtype=np.complex128)
        scales = np.zeros((12, 2, 3), dtype=np.float64)
        nonzero = np.zeros((2, 2, 3), dtype=bool)
        phase_records = {}
        for side, rectangle in rectangles:
            for start in range(0, node_count, chunk_size):
                stop = min(start + chunk_size, node_count)
                count = stop - start
                items = reference.reference_workspace_items(count, rule_points=node_count)
                # Existing items include a three-state x cache; add equally
                # bounded y cache, retained outputs and contraction scratch.
                request = sum(item["bytes"] for item in items) + count * 3 * 16 + (1 << 20)
                budget.before("reference_public_Function_eval_xy_chunk", request,
                              degree=degree, facet=rectangle.facet, cell=rectangle.cell, side=side,
                              start=start, stop=stop, public_eval_workspace_items=items)
                xyz, physical_weights, cells = reference.map_chunk(rectangle, points[start:stop], weights[start:stop])
                if not np.all(xyz[:, 2] - rectangle.zplane == 0):
                    raise ValueError("independent normal phase coordinate not literal zero")
                output = np.empty((count, 3), dtype=np.complex128)
                cache = np.empty((count, 2, 3), dtype=np.complex128)
                for state_index, field in enumerate(native_fields):
                    field.eval(xyz, cells, u=output)
                    if output.shape != (count, 3) or output.dtype != np.complex128 or not np.isfinite(output).all():
                        raise ValueError("independent public Function.eval returned invalid field")
                    cache[:, :, state_index] = output[:, :2]
                    nonzero[0 if side == "bottom" else 1, :, state_index] |= np.any(output[:, :2] != 0, axis=0)
                for key, positions in groups.items():
                    if key[0] != side:
                        continue
                    phase = reference._phase_chunk(xyz, *key[1:], rectangle.zplane)
                    magnitude = np.abs(phase)
                    if not np.isfinite(magnitude).all() or np.max(np.abs(magnitude - 1)) > 64 * 2.0 ** -53:
                        raise FloatingPointError("independent actual centered phase modulus failed")
                    actual_phase = {"side": side, "facet": rectangle.facet, "start": start, "stop": stop,
                                    "positions": positions, "minimum_abs": float(np.min(magnitude)),
                                    "maximum_abs": float(np.max(magnitude)),
                                    "maximum_abs_minus_one": float(np.max(np.abs(magnitude - 1))),
                                    "ideal_unit_modulus_assumed": False}
                    event({"kind": "boundary_reference_actual_phase_modulus", "degree": degree, **actual_phase})
                    summary_key = (rectangle.facet, tuple(positions))
                    if summary_key not in phase_records:
                        phase_records[summary_key] = {"side": side, "facet": rectangle.facet,
                            "positions": positions, "batches": 0, "computed_values": 0,
                            "minimum_abs": np.inf, "maximum_abs": 0.0, "maximum_abs_minus_one": 0.0,
                            "ideal_unit_modulus_assumed": False, "every_batch_durable_event": True}
                    summary = phase_records[summary_key]
                    summary["batches"] += 1
                    summary["computed_values"] += count
                    summary["minimum_abs"] = min(summary["minimum_abs"], actual_phase["minimum_abs"])
                    summary["maximum_abs"] = max(summary["maximum_abs"], actual_phase["maximum_abs"])
                    summary["maximum_abs_minus_one"] = max(summary["maximum_abs_minus_one"], actual_phase["maximum_abs_minus_one"])
                    for component in (0, 1):
                        for state_index in range(3):
                            value, scale = reference._contract_phased(physical_weights, cache[:, component, state_index], phase)
                            for position in positions:
                                contractions[position, component, state_index] += value
                                scales[position, component, state_index] += scale
                    del phase
                del output, cache, xyz, physical_weights, cells
        if not np.isfinite(contractions).all() or not np.isfinite(scales).all() or not nonzero.all():
            raise ValueError("independent actions invalid or a state has zero actual side/component trace")
        suffix = "degree_plus" + str(increment)
        arrays["component_" + suffix] = contractions
        arrays["component_operation_scales_" + suffix] = scales
        cdual, dfunctional = np.zeros((12, 3), dtype=np.complex128), np.zeros((12, 3), dtype=np.complex128)
        cscale, dscale = np.zeros((12, 3), dtype=np.float64), np.zeros((12, 3), dtype=np.float64)
        for position, mode in enumerate(selected_modes):
            normal = np.asarray([0., 0., 1. if mode.side == "top" else -1.])
            traction = np.cross(1j * np.cross(mode.k_vector, mode.e_vector), normal)
            ccoeff, dcoeff = -traction[:2], np.asarray(mode.e_vector[:2])
            cdual[position] = np.sum(ccoeff[:, None] * contractions[position], axis=0)
            dfunctional[position] = np.conjugate(np.sum(dcoeff[:, None] * contractions[position], axis=0))
            cscale[position] = np.sum(np.abs(ccoeff)[:, None] * scales[position], axis=0)
            dscale[position] = np.sum(np.abs(dcoeff)[:, None] * scales[position], axis=0)
        arrays["Cdual_" + suffix], arrays["Dfunctional_" + suffix] = cdual, dfunctional
        arrays["Cdual_operation_scales_" + suffix], arrays["Dfunctional_operation_scales_" + suffix] = cscale, dscale
        rules.append({"degree": degree, "increment": increment, "actual_nodes_per_facet": node_count,
                      "points": native.array_identity(points), "weights": native.array_identity(weights),
                      "unit_mass_metric": mass, "unit_mass_policy": reference.UNIT_MASS_POLICY,
                      "public_Function_eval_calls": 3 * 12 * math.ceil(node_count / chunk_size),
                      "actual_geometric_points": 12 * node_count, "state_side_component_nonzero": nonzero.tolist(),
                      "phase_modulus_summaries": list(phase_records.values()), "phase_batches_individually_durable": True})
        del points, weights
    metrics = []
    for kind in ("component", "Cdual", "Dfunctional"):
        scale_key = kind + "_operation_scales_degree_plus16"
        for index in np.ndindex(arrays[kind + "_degree_plus16"].shape):
            metric = reference.operation_scaled_difference(arrays[kind + "_degree_plus8"][index],
                arrays[kind + "_degree_plus16"][index], arrays[scale_key][index])
            metrics.append({"kind": kind, "index": list(index), **metric})
    passed = all(m["passed"] for m in metrics)
    record = {"schema": SCHEMA, "status": "REFERENCE_CONVERGENCE_PASS" if passed else "REFERENCE_CONVERGENCE_FAILED",
              "reference_convergence_pass": passed, "operation_rtol": OPERATION_RTOL,
              "primary_degree": quadrature_degree, "rules": rules, "state_identity": states,
              "unit_mass_policy": reference.UNIT_MASS_POLICY, "actual_facet_count": 12,
              "distinct_side_phase_groups": len(groups),
              "pinned_public_helpers": pinned, "selected_indices": list(selected_indices),
              "actual_facets": [{"side": side, **r.__dict__} for side, r in rectangles],
              "convergence_metrics": metrics, "source": {"path": str(Path(__file__).resolve()),
              "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "operation_scale": "sum(w*abs(actual_phase)*abs(Function.eval_xy)); C/D sum coefficient magnitudes times scales",
              "Cdual_convention": "vdot(u,C_raw)=sum((-traction_xy)*component_actions)",
              "Dfunctional_convention": "D_raw@u=conjugate(sum(e_xy*component_actions)) once",
              "no_numerical_denominator_floor": True, "candidate_tabulation_or_support_used": False,
              "full_C_D_qualification": False, "target_PDE_qualification": False,
              "owned_workspace_admission_maximum_bytes": budget.maximum, "FE_JIT_PDE_creation_calls": 0}
    event({"kind": "boundary_reference_finished", "record": record})
    return {"record": record, "arrays": arrays}
