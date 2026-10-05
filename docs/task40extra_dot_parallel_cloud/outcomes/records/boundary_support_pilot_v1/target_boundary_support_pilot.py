"""External, opt-in all-side x/y support pilot; creates no FE object.

The caller must own the frozen 18-cell p6 fixture, finalized MPC, original
mode objects, durable events and the whole-process 3 GiB watchdog. Full 882-row
anchors are mandatory. The proposed 84-row contraction never qualifies an
excluded numerical value as zero by observation. Its omission error and both
retained reductions' roundoff are bounded on the actual finite tabulated data.
These bounds say nothing about Basix construction error, continuum accuracy,
the unprocessed modal inventory, FE/JIT admission or production readiness.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "task40extra.boundary-support-pilot.v1"
CELL_DOFS = 882
EXPECTED_ROWS = 13224
EXPECTED_MODE_COUNT = 12
EXPECTED_BASIS_HASH = 16913352432823651554
EXPECTED_COEFFICIENT_SHA256 = "c0be730f050c40e2333362ceac4fac0d656eaf029cf7454a1dbbc21253e064da"
PHASE_ORDERS = ((0, 0), (-142, -5), (-85, -35))
OWNED_BUFFER_LIMIT = 128 << 20
RAW_ARTIFACT_LIMIT = 512 << 20
MAX_CHUNK_SIZE = 128
U = 2.0 ** -53
TINY = float(np.nextafter(np.float64(0), np.float64(1)))
PINNED_SOURCES = {
    "native": ("target_chunked_surface_vector_mass_v2.py", "dff5871b767ed25ecd1500e0433cdc914773c013a46521d4c2bc3a4b0a37bef8"),
    "reference": ("target_higher_quadrature_reference_mass_v2.py", "a0af0fc4838f08af3236c926e383ff84a09ee69c0965c19693a2950a6de44094"),
}
_PUBLIC_CACHE = None


def public_helpers():
    """Import only byte-pinned, unchanged mass-v2 public helpers."""
    global _PUBLIC_CACHE
    if _PUBLIC_CACHE is None:
        modules, identities = {}, {}
        for key, (name, expected) in PINNED_SOURCES.items():
            path = Path(__file__).resolve().parent.parent / "chunked_native" / name
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("pinned mass-v2 helper changed: " + str(path))
            spec = importlib.util.spec_from_file_location("_boundary_support_mass_v2_" + key, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            modules[key] = module
            identities[key] = {"path": str(path), "sha256": actual}
        _PUBLIC_CACHE = (modules["native"], modules["reference"], identities)
    return _PUBLIC_CACHE


def gamma(operations):
    if type(operations) is not int or operations < 0 or operations * U >= 1:
        raise ValueError("invalid binary64 roundoff operation count")
    return float(np.nextafter(operations * U / (1 - operations * U), np.inf))


def upper(value, operations=4, underflow_operations=0):
    """Outward pad nonnegative computed arithmetic, including subnormal loss."""
    array = np.asarray(value, dtype=np.float64)
    if not np.isfinite(array).all() or np.any(array < 0):
        raise FloatingPointError("nonfinite/negative bound input")
    with np.errstate(over="raise", invalid="raise"):
        result = np.nextafter(array * (1 + gamma(operations)) + underflow_operations * TINY, np.inf)
    if not np.isfinite(result).all():
        raise FloatingPointError("nonfinite conservative bound")
    return result


def positive_add(left, right):
    return upper(np.asarray(left) + np.asarray(right), 2, 2)


def stable_norm_bounds(value, order=2):
    """Scaled norm bounds that do not erase distributed tiny values by squaring."""
    value = np.asarray(value)
    if value.ndim != 1 or not np.isfinite(value).all():
        raise ValueError("finite vector required for stable norm")
    if value.dtype.kind == "c":
        normal = np.finfo(np.float64).tiny
        if any(np.any((part != 0) & (np.abs(part) < normal)) for part in (value.real, value.imag)):
            raise FloatingPointError("subnormal complex magnitude requires full-kernel fallback")
    magnitude = np.abs(value)
    if not np.isfinite(magnitude).all():
        raise FloatingPointError("unrepresentable vector magnitude")
    maximum = float(np.max(magnitude, initial=0))
    if maximum == 0:
        return 0.0, 0.0
    if order == np.inf:
        estimate = maximum
    elif order == 2:
        scaled = magnitude / maximum
        estimate = maximum * math.sqrt(float(np.sum(scaled * scaled)))
    else:
        raise ValueError("only l2/linf admitted")
    if not math.isfinite(estimate):
        raise FloatingPointError("unrepresentable vector norm")
    # Division/square underflow occurs after scaling, so each lost scaled term
    # is <=TINY; multiplying that uncertainty by maximum covers amplification.
    rounding = gamma(4 * len(value) + 32) * estimate + 8 * len(value) * TINY * maximum
    low = max(0.0, float(np.nextafter(estimate - rounding - 16 * TINY, -np.inf)))
    high = float(upper(estimate + rounding, 8, 16))
    return low, high


def require_safe_first_products(weights, phase):
    """Fail closed if first product underflow could be amplified by basis values."""
    smallest_normal = np.finfo(np.float64).tiny
    for part in (phase.real, phase.imag):
        product = weights * np.abs(part)
        unsafe = (part != 0) & ((product == 0) | (product < smallest_normal))
        if np.any(unsafe):
            raise FloatingPointError("first weight-phase product underflow requires full-kernel fallback")


def weighted_absolute_bounds(weights, phase, values):
    """Rowwise measured absolute integral and conservative L1-complex bound.

    S_j bounds sum_q |w_q| |phi_qj| (|Re p_q|+|Im p_q|). The upper padding
    covers finite binary64 product, complex L1 evaluation and positive-sum
    rounding. It applies to actual computed phase and basis values only.
    """
    weights, phase, values = map(np.asarray, (weights, phase, values))
    q = len(weights)
    if (weights.dtype != np.float64 or phase.dtype != np.complex128
            or values.dtype != np.float64 or weights.shape != (q,)
            or phase.shape != (q,) or values.ndim != 2 or values.shape[0] != q
            or q < 1 or not all(np.isfinite(a).all() for a in (weights, phase, values))
            or np.any(weights <= 0)):
        raise ValueError("actual positive real weights/finite native phase and real values required")
    with np.errstate(over="raise", invalid="raise"):
        require_safe_first_products(weights, phase)
        measured = np.sum(weights[:, None] * np.abs(phase)[:, None] * np.abs(values), axis=0)
        l1 = upper(np.abs(phase.real) + np.abs(phase.imag), 2, 2)
        first = weights * l1
        if np.any(first < np.finfo(np.float64).tiny):
            raise FloatingPointError("first absolute-scale product underflow can amplify downstream")
        terms = first[:, None] * np.abs(values)
        bound = upper(np.sum(terms, axis=0), q + 8, 4 * q)
    return measured, bound


def local_difference_bound(weights, phase, values, closure):
    """Omitted rows get magnitude bound; retained rows get both-kernel errors."""
    measured, absolute = weighted_absolute_bounds(weights, phase, values)
    q = len(weights)
    bound = upper((1 + gamma(4 * q + 32)) * absolute, 4, 8 * q)
    bound[closure] = upper(2 * gamma(4 * q + 32) * absolute[closure], 4, 16 * q)
    return measured, absolute, bound


def mask_margin_certificate(candidate, error):
    """Sufficient unchanged-mask membership and two-norm relative certificates.

    E bounds anchor-candidate entry error. Margin includes |.| evaluation and
    max-relative cutoff evaluation rounding, not only exact-linear transport.
    This certifies membership and relative error; it never claims bit equality.
    """
    native, _, _ = public_helpers()
    candidate, error = np.asarray(candidate), np.asarray(error)
    if (candidate.ndim != 1 or candidate.dtype != np.complex128 or error.shape != candidate.shape
            or error.dtype != np.float64 or not np.isfinite(candidate).all()
            or not np.isfinite(error).all() or np.any(error < 0)):
        raise ValueError("invalid candidate/error certificate vectors")
    _, _, cutoff = native.unchanged_mask(candidate)
    magnitude = np.abs(candidate)
    magnitude_rounding = upper(gamma(8) * (magnitude + error), 4, 16)
    magnitude_uncertainty = positive_add(error, magnitude_rounding)
    cutoff_uncertainty = upper(1e-13 * float(np.max(magnitude_uncertainty, initial=0))
                               + gamma(8) * cutoff, 8, 16)
    required_margin = positive_add(magnitude_uncertainty, cutoff_uncertainty)
    margin = np.abs(magnitude - cutoff)
    # A downward-rounded margin avoids promoting rounding at a strict boundary.
    margin_lower = np.maximum(0, np.nextafter(margin - gamma(8) * (magnitude + cutoff), -np.inf))
    ambiguous = margin_lower <= required_margin
    norms, masked_norms = {}, {}
    kept = magnitude > cutoff
    for target, cand_values, error_values in ((norms, candidate, error),
                                              (masked_norms, candidate[kept], error[kept])):
        for name, order in (("l2", 2), ("linf", np.inf)):
            try:
                _, en = stable_norm_bounds(error_values, order)
                cn_lower, cn_upper = stable_norm_bounds(cand_values, order)
                lower = max(0.0, float(np.nextafter(cn_lower - en, -np.inf)))
                ok = bool(en == 0 if cn_upper == 0 else lower > 0 and en <= 1e-11 * lower)
                target[name] = {"error_norm_upper": en, "anchor_norm_lower": lower,
                                "relative_limit": 1e-11, "passed": ok}
            except FloatingPointError as exc:
                target[name] = {"passed": False, "reason": str(exc), "relative_limit": 1e-11}
    # Dropped rows have error exactly zero only after membership is certified;
    # its truth is checked separately below, not inferred from small values.
    passed = not bool(np.any(ambiguous)) and all(item["passed"] for item in norms.values())
    passed = passed and all(item["passed"] for item in masked_norms.values())
    return {"passed": passed, "mask_membership_passed": not bool(np.any(ambiguous)),
            "ambiguous_count": int(np.count_nonzero(ambiguous)), "cutoff": cutoff,
            "minimum_margin_lower": float(np.min(margin_lower, initial=np.inf)),
            "maximum_required_margin_upper": float(np.max(required_margin, initial=0)),
            "norms": norms, "masked_norms": masked_norms,
            "masked_error_drop_requires_membership_certificate": True,
            "retained_bit_equality_claimed": False}, ambiguous


def validate_mode_inventory(modes, indices):
    if (len(modes) != EXPECTED_MODE_COUNT or len(indices) != len(modes)
            or len(set(indices)) != len(indices)
            or any(type(i) is not int or i < 0 for i in indices)):
        raise ValueError("twelve original modes and distinct inventory indices required")
    expected = {(side, m, n, pol) for side in ("top", "bottom")
                for m, n in PHASE_ORDERS for pol in ("s", "p")}
    actual, phase_groups = set(), {}
    for position, mode in enumerate(modes):
        key = (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization).lower())
        if (key in actual or np.shape(mode.k_vector) != (3,) or np.shape(mode.e_vector) != (3,)
                or not all(np.isfinite(v) for v in (mode.alpha, mode.gamma, *mode.k_vector, *mode.e_vector))
                or complex(mode.alpha).imag != 0 or complex(mode.gamma).imag != 0):
            raise ValueError("distinct finite actual modes with real transverse phases required")
        actual.add(key)
        phase = (mode.side, complex(mode.alpha), complex(mode.gamma), complex(mode.k_vector[2]))
        phase_groups.setdefault(phase, []).append(position)
    if actual != expected or len(phase_groups) != 6:
        raise ValueError("exact three actual phase orders/both polarizations/both sides required")
    for side in ("top", "bottom"):
        for order in PHASE_ORDERS:
            pair = [mode for mode in modes if mode.side == side and (mode.m, mode.n) == order]
            if len({(complex(m.alpha), complex(m.gamma), complex(m.k_vector[2])) for m in pair}) != 1:
                raise ValueError("polarizations must share their actual phase tuple")
    return phase_groups


@dataclass(frozen=True)
class BoundaryRectangle:
    facet: int
    cell: int
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zplane: float
    side: str
    reference_face: int

    @property
    def area(self):
        return (self.xmax - self.xmin) * (self.ymax - self.ymin)


def rectangle_from_geometry(facet, cell, face_xyz, cell_xyz, zplane, side):
    native, _, _ = public_helpers()
    native.affine_geometry(cell_xyz)  # Literal equality; no tolerant J cache.
    if side not in ("top", "bottom") or np.shape(face_xyz) != (4, 3) or not np.isfinite(face_xyz).all():
        raise ValueError("invalid exterior rectangle input")
    plane = float(np.max(cell_xyz[:, 2]) if side == "top" else np.min(cell_xyz[:, 2]))
    if plane != zplane or not np.all(face_xyz[:, 2] == zplane):
        raise ValueError("tagged face is not the exact associated side plane")
    xmin, ymin = face_xyz[:, :2].min(axis=0)
    xmax, ymax = face_xyz[:, :2].max(axis=0)
    wanted = {(float(x), float(y), float(zplane)) for x in (xmin, xmax) for y in (ymin, ymax)}
    if set(map(tuple, face_xyz)) != wanted or len(wanted) != 4 or xmax <= xmin or ymax <= ymin:
        raise ValueError("nonliteral/nondegenerate rectangle required")
    from basix import CellType
    from basix.cell import topology
    matches = [f for f, vertices in enumerate(topology(CellType.hexahedron)[2])
               if set(map(tuple, cell_xyz[vertices])) == wanted]
    if len(matches) != 1:
        raise ValueError("actual reference face not uniquely resolved from exact geometry")
    return BoundaryRectangle(int(facet), int(cell), float(xmin), float(xmax), float(ymin),
                             float(ymax), float(zplane), side, matches[0])


def actual_rectangles(mesh_data, cfg, budget, event):
    from dolfinx import mesh as dx_mesh
    _, reference, _ = public_helpers()
    msh = mesh_data.mesh
    if (msh.topology.dim != 3 or msh.geometry.dim != 3 or msh.topology.cell_type.name != "hexahedron"
            or msh.geometry.cmap.degree != 1 or msh.geometry.cmap.dim != 8
            or msh.geometry.x.dtype != np.float64 or msh.topology.index_map(3).size_local != 18
            or msh.topology.index_map(3).num_ghosts
            or (cfg.x_min, cfg.x_max, cfg.y_min, cfg.y_max, cfg.domain_z_min, cfg.domain_z_max) != (0, 50, 0, 25, -10, 130)):
        raise ValueError("original 18-cell real affine 50x25x140nm fixture required")
    budget.before("all_side_public_geometry_metadata", 2 << 20)
    msh.topology.create_connectivity(2, 3)
    f_to_c = msh.topology.connectivity(2, 3)
    exterior = set(map(int, dx_mesh.exterior_facet_indices(msh.topology)))
    vertices = msh.geometry.x[msh.geometry.dofmap]
    for axis, expected in enumerate(reference.EXPECTED_AXES):
        if not np.array_equal(np.unique(vertices[:, :, axis]), np.asarray(expected)):
            raise ValueError("actual frozen fixture axes differ")
    native, _, _ = public_helpers()
    for xyz in vertices:
        native.affine_geometry(xyz)
    actual = {tuple(xyz.min(axis=0)) + tuple(xyz.max(axis=0)) for xyz in vertices}
    axes = reference.EXPECTED_AXES
    expected = {(x0, y0, z0, x1, y1, z1) for x0, x1 in zip(axes[0][:-1], axes[0][1:])
                for y0, y1 in zip(axes[1][:-1], axes[1][1:]) for z0, z1 in zip(axes[2][:-1], axes[2][1:])}
    if actual != expected or len(actual) != 18:
        raise ValueError("actual full affine boxes differ")
    result = []
    for side, tag, plane in (("top", cfg.tags.z_max, cfg.domain_z_max),
                             ("bottom", cfg.tags.z_min, cfg.domain_z_min)):
        facets = np.asarray(mesh_data.facet_tags.find(int(tag)), dtype=np.int32)
        if len(facets) != 6 or len(np.unique(facets)) != 6 or not set(map(int, facets)).issubset(exterior):
            raise ValueError("each actual side requires six unique exterior facets")
        gdofs = dx_mesh.entities_to_geometry(msh, 2, facets, permute=False)
        if gdofs.shape != (6, 4):
            raise ValueError("actual facet geometry map differs")
        for facet, geometric in zip(facets, gdofs):
            cells = np.asarray(f_to_c.links(int(facet)))
            if cells.shape != (1,) or not 0 <= cells[0] < 18:
                raise ValueError("each exterior facet must have one owned actual cell")
            result.append(rectangle_from_geometry(facet, cells[0], msh.geometry.x[geometric],
                                                   vertices[cells[0]], float(plane), side))
        wanted = {(x0, x1, y0, y1, float(plane)) for x0, x1 in zip(axes[0][:-1], axes[0][1:])
                  for y0, y1 in zip(axes[1][:-1], axes[1][1:])}
        got = {(r.xmin, r.xmax, r.ymin, r.ymax, r.zplane) for r in result if r.side == side}
        if got != wanted or sum(r.area for r in result if r.side == side) != 1250:
            raise ValueError("actual boundary rectangles do not cover exact side once")
    if len({r.facet for r in result}) != 12 or len({r.cell for r in result}) != 12:
        raise ValueError("actual twelve top/bottom cells/facets must be distinct")
    return sorted(result, key=lambda r: (r.side, r.xmin, r.ymin, r.facet))


def validate_closure_and_T(basis, reference_face, cell_info):
    """Validate public closure blocks and complete actual T invariance, no D²."""
    from basix import CellType
    from basix.cell import topology
    topo = topology(CellType.hexahedron)
    if basis.dim != CELL_DOFS or not 0 <= reference_face < 6:
        raise ValueError("actual p6 hex basis/face required")
    face_vertices = set(topo[2][reference_face])
    edges = [e for e, vertices in enumerate(topo[1]) if set(vertices).issubset(face_vertices)]
    entity = basis.entity_dofs
    closure = np.asarray(basis.entity_closure_dofs[2][reference_face], dtype=np.int32)
    union = sorted([j for e in edges for j in entity[1][e]] + list(entity[2][reference_face]))
    if (len(edges) != 4 or any(len(entity[1][e]) != 6 for e in edges)
            or len(entity[2][reference_face]) != 60 or closure.shape != (84,)
            or len(np.unique(closure)) != 84 or not np.array_equal(np.sort(closure), union)
            or len(entity[3][0]) != 450):
        raise ValueError("public actual entity closure is not four complete edge blocks plus face")
    keep = np.zeros(CELL_DOFS, dtype=bool)
    keep[closure] = True
    # Test every input basis direction, but retain only one 882-vector. This
    # proves actual floating T block invariance without an assembled D×D matrix.
    scratch = np.zeros(CELL_DOFS, dtype=np.float64)
    for row in range(CELL_DOFS):
        scratch.fill(0)
        scratch[row] = 1
        basis.T_apply(scratch, 1, int(cell_info))
        if not np.isfinite(scratch).all() or np.any(scratch[~keep if keep[row] else keep] != 0):
            raise ValueError("actual public native T mixes closure/complement")
    native, _, _ = public_helpers()
    return closure, {"reference_face": int(reference_face), "cell_info": int(cell_info),
                     "closure_rows": 84, "excluded_rows": 798, "edge_entities": edges,
                     "closure": native.array_identity(closure), "T_apply_input_directions_checked": CELL_DOFS,
                     "literal_cross_block_zero": True, "dense_T_bytes": 0,
                     "tiny_entity_transform_values_thresholded": False}


def dual_error_bound(candidate_fe, anchor_fe, error_fe, slaves, masters, coefficients, offsets):
    """Actual |K^H| error transport plus both complex scatter arithmetic errors."""
    n = len(candidate_fe)
    out = error_fe.copy()
    scale = upper(np.abs(candidate_fe) + np.abs(anchor_fe), 8, 16)
    updates = np.zeros(n, dtype=np.int32)
    for slave in slaves:
        s = int(slave)
        for p in range(int(offsets[s]), int(offsets[s + 1])):
            master = int(masters[p])
            coefficient_l1 = float(upper(abs(coefficients[p].real) + abs(coefficients[p].imag), 4, 4))
            out[master] = positive_add(out[master], upper(coefficient_l1 * error_fe[s], 4, 4))
            scale[master] = positive_add(scale[master], upper(coefficient_l1 * scale[s], 4, 8))
            updates[master] += 1
    for row in range(n):
        out[row] = positive_add(out[row], upper(gamma(16 * int(updates[row]) + 16) * scale[row], 4,
                                                   32 * int(updates[row]) + 32))
    out[slaves] = 0  # Exact algorithmic slave assignment in both projected vectors.
    return out


def combine_components(components, coefficients):
    """Production component-masked combination before unchanged second mask."""
    native, _, _ = public_helpers()
    if np.shape(components)[0] != 2 or len(coefficients) != 2:
        raise ValueError("two finite masked component vectors required")
    value = np.zeros(components.shape[1], dtype=np.complex128)
    for component, coefficient in zip(components, coefficients):
        if abs(complex(coefficient)) > 0:
            value += complex(coefficient) * component
    rows, values, cutoff = native.unchanged_mask(value)
    masked = np.zeros_like(value)
    masked[rows] = values
    return value, masked, cutoff


def combined_error_bound(candidate, anchor, errors, coefficients):
    out = np.zeros(candidate.shape[1], dtype=np.float64)
    scale = np.zeros_like(out)
    for c, a, e, coefficient in zip(candidate, anchor, errors, coefficients):
        coefficient_l1 = (0.0 if complex(coefficient) == 0 else
                          float(upper(abs(complex(coefficient).real) + abs(complex(coefficient).imag), 4, 4)))
        out = positive_add(out, upper(coefficient_l1 * e, 4, 4))
        scale = positive_add(scale, upper(coefficient_l1 * (np.abs(c) + np.abs(a)), 12, 24))
    return positive_add(out, upper(gamma(64) * scale, 4, 64))


def phase_modulus_record(phase):
    magnitude = np.abs(phase)
    if phase.dtype != np.complex128 or not np.isfinite(phase).all() or not np.isfinite(magnitude).all():
        raise FloatingPointError("nonfinite actual phase")
    if np.max(np.abs(magnitude - 1)) > 64 * U:
        raise FloatingPointError("actual computed centered transverse phase modulus failed")
    return {"computed_values": len(phase), "minimum_abs": float(np.min(magnitude)),
            "maximum_abs": float(np.max(magnitude)),
            "maximum_abs_minus_one": float(np.max(np.abs(magnitude - 1))),
            "l1_modulus_upper": float(np.max(upper(np.abs(phase.real) + np.abs(phase.imag), 4, 4))),
            "ideal_unit_modulus_assumed": False}


def assemble_boundary_support_pilot(*, V: Any, mesh_data: Any, mpc: Any, cfg: Any,
                                    selected_modes: tuple, selected_indices: tuple,
                                    quadrature_degree: int, allocation_gate, event, output_dir,
                                    production_h_diagonal, chunk_size: int = 32, enable_closure: bool = True):
    """Full anchors + proposed closure + per-component/C/D conservative fallback."""
    native, reference, source_identities = public_helpers()
    if (not callable(allocation_gate) or not callable(event) or type(chunk_size) is not int
            or not 1 <= chunk_size <= MAX_CHUNK_SIZE or quadrature_degree not in (27, 160)
            or type(enable_closure) is not bool):
        raise ValueError("invalid bounded pilot admission/configuration")
    budget = native._Budget(allocation_gate, event, persistent=native.BOOKKEEPING_BYTES)
    groups = validate_mode_inventory(selected_modes, selected_indices)
    if not mpc.finalized or V.mesh is not mesh_data.mesh or V.value_size != 3:
        raise ValueError("caller-owned fixture and finalized MPC required")
    msh, n = V.mesh, int(V.dofmap.index_map.size_local)
    if (msh.comm.size != 1 or msh.comm.rank != 0 or n != EXPECTED_ROWS
            or V.dofmap.index_map.num_ghosts or V.dofmap.index_map.size_global != n
            or V.dofmap.index_map_bs != 1 or V.dofmap.bs != 1):
        raise ValueError("unghosted scalar MPI1 native 13224-row fixture required")
    basis = V.element.basix_element
    if (basis.family.name != "N1E" or basis.cell_type.name != "hexahedron" or basis.degree != 6
            or basis.dim != CELL_DOFS or tuple(basis.value_shape) != (3,)
            or np.dtype(basis.dtype) != np.dtype(np.float64) or basis.map_type.name != "covariantPiola"):
        raise ValueError("actual real p6 882-row covariant-Piola N1E required")
    budget.before("actual_public_basis_coefficient_identity", 2 * 882 * 1029 * 8 + (1 << 20))
    coefficient_matrix = np.asarray(basis.coefficient_matrix)
    if (int(basis.hash()) != EXPECTED_BASIS_HASH or coefficient_matrix.shape != (882, 1029)
            or coefficient_matrix.dtype != np.float64 or not coefficient_matrix.flags.c_contiguous
            or hashlib.sha256(memoryview(coefficient_matrix).cast("B")).hexdigest() != EXPECTED_COEFFICIENT_SHA256):
        raise ValueError("actual basis identity does not match public closure support proof")
    del coefficient_matrix
    h = np.asarray(production_h_diagonal)
    if h.shape != (12,) or h.dtype != np.float64 or not np.isfinite(h).all() or np.any(h <= 0):
        raise ValueError("caller must supply actual positive finite production plane-H diagonal")
    budget.before("public_native_metadata", 8 << 20)
    layout = reference._assert_same_native_layout(V, mpc.function_space)
    slaves = np.asarray(mpc.slaves)
    coefficients, offsets = (np.asarray(a) for a in mpc.coefficients())
    masters = np.asarray(mpc.masters.array)
    if not np.array_equal(np.flatnonzero(np.asarray(mpc.is_slave)), np.sort(slaves)):
        raise ValueError("public finalized MPC flags disagree")
    budget.before("actual_MPC_validate", n * 80 + len(coefficients) * 80)
    native.dual_project(np.zeros(n, dtype=np.complex128), slaves, masters, coefficients, offsets)
    for s in slaves:
        if not np.array_equal(masters[offsets[s]:offsets[s + 1]], mpc.masters.links(int(s))):
            raise ValueError("actual finalized MPC master links/offsets disagree")
    rectangles = actual_rectangles(mesh_data, cfg, budget, event)
    msh.topology.create_entity_permutations()
    permutations = msh.topology.get_cell_permutation_info()
    if permutations.dtype != np.uint32 or permutations.shape != (18,):
        raise ValueError("actual native orientation metadata required")
    from basix import CellType, PolysetType, QuadratureType, make_quadrature
    q = ((quadrature_degree + 2) // 2) ** 2
    budget.before("actual_primary_default_and_Gauss_rule", 2 * q * 24, 12 * q * 8)
    points, weights = make_quadrature(CellType.quadrilateral, quadrature_degree,
                                    rule=QuadratureType.default, polyset_type=PolysetType.standard)
    p2, w2 = make_quadrature(CellType.quadrilateral, quadrature_degree,
                           rule=QuadratureType.gauss_jacobi, polyset_type=PolysetType.standard)
    unit_mass = native.unit_mass_metric(weights)
    event({"kind": "boundary_support_unit_mass_before_gate", "degree": quadrature_degree, "metric": unit_mass})
    if (points.shape != (q, 2) or weights.shape != (q,) or points.dtype != np.float64
            or weights.dtype != np.float64 or not unit_mass["passed"] or not np.isfinite(points).all()
            or np.any(points < 0) or np.any(points > 1)
            or native.array_identity(points) != native.array_identity(p2)
            or native.array_identity(weights) != native.array_identity(w2)):
        raise ValueError("actual unmodified primary production rule failed")
    del p2, w2
    # Simultaneous arrays: 6 component complex arrays, 3 component bound/scale
    # arrays, two component masks; six C/D arrays, two C/D bounds and masks;
    # certificate and dual/combine temporary allowance, rule and metadata.
    component_entries, combined_entries = 12 * 2 * n, 12 * n
    outputs = component_entries * (6 * 16 + 3 * 8 + 2) + combined_entries * (6 * 16 + 2 * 8 + 4)
    replay_metadata_bytes = (slaves.nbytes + masters.nbytes + coefficients.nbytes + offsets.nbytes
                             + 18 * CELL_DOFS * 4 + 18 * 8 * 3 * 8 + 18 * 4
                             + 12 * 84 * 4 + 12 * 86 * 4)
    temporary = 12 * n * 8 * 4 + n * 16 * 16 + (6 << 20) + replay_metadata_bytes
    budget.persistent = native.BOOKKEEPING_BYTES + q * 24
    budget.before("complete_anchor_candidate_certificate_outputs", outputs + temporary)
    budget.persistent += outputs + temporary
    shape = (12, 2, n)
    arrays = {key: np.zeros(shape, dtype=np.complex128) for key in
              ("b_FE_anchor", "b_FE_candidate", "raw_MPC_anchor", "raw_MPC_candidate", "masked_anchor", "masked_candidate")}
    error_fe = np.zeros(shape, dtype=np.float64)
    scale_fe = np.zeros_like(error_fe)
    error_raw = np.zeros_like(error_fe)
    masks_anchor, masks_candidate = np.zeros(shape, dtype=bool), np.zeros(shape, dtype=bool)
    facets, phase_metrics, rowwise_records, rowwise_in_memory = [], {}, [], {}
    topology_cache = {}
    root = None if output_dir is None else Path(output_dir)
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
    def fail_chunk(message, stage, chunks, live_bytes=0):
        native._numerical_failure(message, stage,
            {**chunks, "partial_b_FE_anchor": arrays["b_FE_anchor"],
             "partial_b_FE_candidate": arrays["b_FE_candidate"]},
            root, budget, event, extra_live=live_bytes)
    for rectangle in rectangles:
        cell, info = rectangle.cell, int(permutations[rectangle.cell])
        geometry = np.ascontiguousarray(msh.geometry.x[msh.geometry.dofmap[cell]], dtype=np.float64)
        origin, J, determinant, K = native.affine_geometry(geometry)
        dofs = np.asarray(V.dofmap.cell_dofs(cell))
        if (dofs.dtype != np.int32 or dofs.shape != (CELL_DOFS,) or len(np.unique(dofs)) != CELL_DOFS
                or np.any(dofs < 0) or np.any(dofs >= n)):
            raise ValueError("actual cell DoF map invalid")
        cache_key = (rectangle.reference_face, info)
        if cache_key not in topology_cache:
            budget.before("exact_public_closure_T_validation", 2 << 20)
            topology_cache[cache_key] = validate_closure_and_T(basis, *cache_key)
        closure, topology_record = topology_cache[cache_key]
        excluded = np.setdiff1d(np.arange(CELL_DOFS), closure)
        # Complete full-rule diagnostic rows per phase/component, bounded and
        # lossless. No per-chunk million-value JSON stream is emitted.
        side_groups = [(key, positions) for key, positions in groups.items() if key[0] == rectangle.side]
        facet_measured = np.zeros((3, 2, CELL_DOFS), dtype=np.float64)
        facet_omission_bounds = np.zeros_like(facet_measured)
        facet_retained_bounds = np.zeros_like(facet_measured)
        facets.append({**rectangle.__dict__, "cell_info": info, "J": J.tolist(), "K": K.tolist(),
                       "detJ": determinant, "cell_geometry": native.array_identity(geometry),
                       "cell_dofs": native.array_identity(dofs), "support": topology_record})
        for start in range(0, q, chunk_size):
            stop = min(start + chunk_size, q)
            count = stop - start
            table = count * CELL_DOFS * 3 * 8
            named = 10 * table + count * 512 + CELL_DOFS * 8 * 16 + (1 << 20)
            scratch = 4 * count * 7 ** 3 * 3 * 8 + 2 * table
            facts = {"facet": rectangle.facet, "cell": cell, "side": rectangle.side, "start": start, "stop": stop,
                     "full_anchor_rows": CELL_DOFS, "closure_rows": 84, "dense_T_bytes": 0}
            budget.before("full_anchor_and_closure_native_chunk", named, scratch, **facts)
            xyz, physical_weights, cells = reference.map_chunk(rectangle, points[start:stop], weights[start:stop])
            if not np.all(xyz[:, 2] - rectangle.zplane == 0):
                raise ValueError("actual centered normal phase coordinate not literal zero")
            X = msh.geometry.cmap.pull_back(xyz, geometry)
            if (X.shape != (count, 3) or X.dtype != np.float64 or not np.isfinite(X).all()
                    or not np.allclose(X, (xyz - origin) @ K.T, rtol=0, atol=256 * np.finfo(float).eps)):
                fail_chunk("actual public pullback not admitted affine map", "pullback", {"X": X, "xyz": xyz}, named + scratch)
            if not np.allclose(msh.geometry.cmap.push_forward(X, geometry), xyz, rtol=0,
                               atol=256 * np.finfo(float).eps * float(np.max(np.abs(geometry), initial=1))):
                fail_chunk("actual public coordinate roundtrip failed", "roundtrip", {"X": X, "xyz": xyz}, named + scratch)
            tabulation = basis.tabulate(0, X)
            if (tabulation.shape != (1, count, CELL_DOFS, 3) or tabulation.dtype != np.float64
                    or not tabulation.flags.c_contiguous or not np.isfinite(tabulation).all()):
                fail_chunk("actual public tabulation invalid", "tabulation", {"tabulation": tabulation, "X": X}, named + scratch)
            native.apply_native_basis_orientation(basis, tabulation[0], info)
            mapped = basis.push_forward(tabulation[0].reshape(1, count * CELL_DOFS, 3), J[None],
                                        np.asarray([determinant]), K[None]).reshape(count, CELL_DOFS, 3)
            if mapped.dtype != np.float64 or not np.isfinite(mapped).all():
                fail_chunk("actual covariant-Piola values invalid", "Piola", {"mapped": mapped}, named + scratch)
            for phase_position, (phase_key, positions) in enumerate(side_groups):
                try:
                    phase = reference._phase_chunk(xyz, *phase_key[1:], rectangle.zplane)
                    phase_metric = phase_modulus_record(phase)
                except (ValueError, FloatingPointError) as exc:
                    fail_chunk(str(exc), "phase", {"xyz": xyz, "physical_weights": physical_weights}, named + scratch)
                event({"kind": "boundary_support_actual_phase_modulus", **facts,
                       "mode_positions": positions, **phase_metric})
                summary_key = (rectangle.facet, tuple(positions))
                if summary_key not in phase_metrics:
                    phase_metrics[summary_key] = {"facet": rectangle.facet, "cell": cell,
                        "side": rectangle.side, "mode_positions": positions, "batches": 0,
                        "computed_values": 0, "minimum_abs": np.inf, "maximum_abs": 0.0,
                        "maximum_abs_minus_one": 0.0, "l1_modulus_upper": 0.0,
                        "ideal_unit_modulus_assumed": False, "every_batch_durable_event": True}
                summary = phase_metrics[summary_key]
                summary["batches"] += 1
                summary["computed_values"] += count
                summary["minimum_abs"] = min(summary["minimum_abs"], phase_metric["minimum_abs"])
                for name in ("maximum_abs", "maximum_abs_minus_one", "l1_modulus_upper"):
                    summary[name] = max(summary[name], phase_metric[name])
                weighted_phase = physical_weights * phase
                for component in (0, 1):
                    values = mapped[:, :, component]
                    local_anchor = np.einsum("q,qj->j", weighted_phase, values, optimize=False)
                    local_candidate = np.zeros(CELL_DOFS, dtype=np.complex128)
                    retained = np.ascontiguousarray(values[:, closure])
                    local_candidate[closure] = np.einsum("q,qj->j", weighted_phase, retained, optimize=False)
                    try:
                        measured, absolute, local_error = local_difference_bound(physical_weights, phase, values, closure)
                    except (ValueError, FloatingPointError) as exc:
                        fail_chunk(str(exc), "local_certificate", {"weighted_phase": weighted_phase,
                            "mapped_values": values, "local_anchor": local_anchor,
                            "local_candidate": local_candidate}, named + scratch)
                    if not all(np.isfinite(v).all() for v in (local_anchor, local_candidate, measured, local_error)):
                        fail_chunk("nonfinite actual local integration/certificate", "contraction",
                            {"local_anchor": local_anchor, "local_candidate": local_candidate,
                             "local_error": local_error}, named + scratch)
                    facet_measured[phase_position, component] += measured
                    facet_omission_bounds[phase_position, component, excluded] = positive_add(
                        facet_omission_bounds[phase_position, component, excluded], local_error[excluded])
                    facet_retained_bounds[phase_position, component, closure] = positive_add(
                        facet_retained_bounds[phase_position, component, closure], local_error[closure])
                    for position in positions:
                        np.add.at(arrays["b_FE_anchor"][position, component], dofs, local_anchor)
                        np.add.at(arrays["b_FE_candidate"][position, component], dofs, local_candidate)
                        error_fe[position, component, dofs] = positive_add(error_fe[position, component, dofs], local_error)
                        scale_fe[position, component, dofs] = positive_add(scale_fe[position, component, dofs], absolute)
                    del retained, local_anchor, local_candidate, measured, absolute, local_error
                del phase, weighted_phase
            del tabulation, mapped, X, xyz, physical_weights, cells
        row_artifacts = {}
        if root is not None:
            for key, array in (("measured_weighted_absolute", facet_measured),
                               ("excluded_magnitude_upper", facet_omission_bounds),
                               ("retained_difference_upper", facet_retained_bounds)):
                row_artifacts[key] = native._save(root / f"facet_{rectangle.facet}_{key}.npy", array, budget)
        else:
            # Pure API callers can inspect the same lossless arrays without IO.
            rowwise_in_memory[rectangle.facet] = {"measured_weighted_absolute": facet_measured,
                                                 "excluded_magnitude_upper": facet_omission_bounds,
                                                 "retained_difference_upper": facet_retained_bounds}
            row_artifacts = {key: native.array_identity(value)
                             for key, value in rowwise_in_memory[rectangle.facet].items()}
        row_record = {"facet": rectangle.facet, "cell": cell, "side": rectangle.side,
                      "reference_face": rectangle.reference_face, "closure_rows": closure.tolist(),
                      "excluded_rows": excluded.tolist(), "phase_mode_positions": [positions for _, positions in side_groups],
                      "shape": [3, 2, CELL_DOFS], "artifacts": row_artifacts,
                      "measured_integrals_are_upper_bounds": False,
                      "actual_tabulation_arithmetic_only": True, "Basix_construction_error_bounded": False}
        rowwise_records.append(row_record)
        if root is not None:
            event({"kind": "boundary_support_full_rule_rowwise_integrals_saved", **row_record})
        del facet_measured, facet_omission_bounds, facet_retained_bounds
    error_fe[:] = positive_add(error_fe, upper(2 * gamma(4 * math.ceil(q / chunk_size) * 6 + 32) * scale_fe,
                                               4, 64 * math.ceil(q / chunk_size) * 6))
    early_artifacts = {}
    if root is not None:
        for key in ("b_FE_anchor", "b_FE_candidate"):
            early_artifacts[key] = native._save(root / (key + ".npy"), arrays[key], budget)
        event({"kind": "boundary_support_complete_FE_anchors_saved_before_projection", "artifacts": early_artifacts})
    component_records = []
    containment_records = []
    for position in range(12):
        for component in (0, 1):
            for kind in ("anchor", "candidate"):
                arrays["raw_MPC_" + kind][position, component] = native.dual_project(
                    arrays["b_FE_" + kind][position, component], slaves, masters, coefficients, offsets,
                    failure_callback=lambda value: fail_chunk("actual dual projection failed", "MPC_projection",
                        {"failed_projected_vector": value, "partial_raw_anchor": arrays["raw_MPC_anchor"],
                         "partial_raw_candidate": arrays["raw_MPC_candidate"]}))
                raw = arrays["raw_MPC_" + kind][position, component]
                rows, values, _ = native.unchanged_mask(raw)
                arrays["masked_" + kind][position, component, rows] = values
                (masks_anchor if kind == "anchor" else masks_candidate)[position, component, rows] = True
            error_raw[position, component] = dual_error_bound(arrays["b_FE_candidate"][position, component],
                arrays["b_FE_anchor"][position, component], error_fe[position, component],
                slaves, masters, coefficients, offsets)
            for stage, bound in (("b_FE", error_fe[position, component]),
                                 ("raw_MPC", error_raw[position, component])):
                delta = np.abs(arrays[stage + "_anchor"][position, component]
                               - arrays[stage + "_candidate"][position, component])
                contained = bool(np.all(delta <= bound))
                item = {"mode_position": position, "component": component, "stage": stage,
                        "passed": contained, "maximum_measured_abs_difference": float(np.max(delta, initial=0)),
                        "maximum_error_bound": float(np.max(bound, initial=0))}
                containment_records.append(item)
                event({"kind": "boundary_support_actual_bound_containment", **item})
                if not contained:
                    for key, value in (("anchor", arrays[stage + "_anchor"][position, component]),
                                       ("candidate", arrays[stage + "_candidate"][position, component]), ("bound", bound)):
                        if root is not None:
                            native._save(root / f"failure_{stage}_{position}_{component}_{key}.npy", value, budget)
                    if root is not None:
                        for key in ("raw_MPC_anchor", "raw_MPC_candidate"):
                            native._save(root / ("failure_complete_" + key + ".npy"), arrays[key], budget)
                    raise FloatingPointError("actual full-anchor difference exceeds proposed conservative certificate")
            certificate, _ = mask_margin_certificate(arrays["raw_MPC_candidate"][position, component], error_raw[position, component])
            use_candidate = enable_closure and certificate["passed"]
            component_records.append({"mode_position": position, "original_mode_index": selected_indices[position],
                                      "component": component, "certificate": certificate,
                                      "selected": "closure84" if use_candidate else "full882_fallback"})
    if root is not None:
        for key in ("raw_MPC_anchor", "raw_MPC_candidate", "masked_anchor", "masked_candidate"):
            early_artifacts[key] = native._save(root / (key + ".npy"), arrays[key], budget)
        event({"kind": "boundary_support_complete_raw_and_masked_saved_before_combination",
               "artifacts": {key: value for key, value in early_artifacts.items() if key.startswith(("raw", "masked"))}})
    coefficients_c, coefficients_d = [], []
    for mode in selected_modes:
        normal = np.asarray([0., 0., 1. if mode.side == "top" else -1.])
        traction = np.cross(1j * np.cross(mode.k_vector, mode.e_vector), normal)
        coefficients_c.append(tuple(-complex(v) for v in traction[:2]))
        coefficients_d.append(tuple(complex(v) for v in mode.e_vector[:2]))
    for key in ("C_anchor", "D_anchor", "C_candidate", "D_candidate", "C", "D"):
        arrays[key] = np.zeros((12, n), dtype=np.complex128)
    for key in ("C_combination_error_bound", "D_combination_error_bound"):
        arrays[key] = np.zeros((12, n), dtype=np.float64)
    combined_records = []
    for position in range(12):
        chosen = np.empty((2, n), dtype=np.complex128)
        chosen_error = np.zeros((2, n), dtype=np.float64)
        for component in (0, 1):
            use = component_records[position * 2 + component]["selected"] == "closure84"
            chosen[component] = arrays["masked_candidate" if use else "masked_anchor"][position, component]
            if use:
                chosen_error[component] = error_raw[position, component]
                chosen_error[component, ~masks_candidate[position, component]] = 0
        for key, coefficient in (("C", coefficients_c[position]), ("D", coefficients_d[position])):
            raw_anchor, masked_anchor, _ = combine_components(arrays["masked_anchor"][position], coefficient)
            raw_candidate, masked_candidate, _ = combine_components(arrays["masked_candidate"][position], coefficient)
            raw_chosen, masked_chosen, _ = combine_components(chosen, coefficient)
            combined_error = combined_error_bound(chosen, arrays["masked_anchor"][position], chosen_error, coefficient)
            actual_combined_delta = np.abs(raw_chosen - raw_anchor)
            contained = bool(np.all(actual_combined_delta <= combined_error))
            if not contained:
                if root is not None:
                    for name, value in (("anchor", raw_anchor), ("candidate", raw_chosen), ("bound", combined_error)):
                        native._save(root / f"failure_{key}_{position}_{name}.npy", value, budget)
                raise FloatingPointError("actual combined full-anchor difference exceeds certificate")
            certificate, _ = mask_margin_certificate(raw_chosen, combined_error)
            use = enable_closure and certificate["passed"]
            if key == "D":
                masked_anchor, masked_candidate, masked_chosen = (np.conjugate(v) for v in (masked_anchor, masked_candidate, masked_chosen))
            arrays[key + "_anchor"][position] = masked_anchor
            arrays[key + "_candidate"][position] = masked_candidate
            arrays[key][position] = masked_chosen if use else masked_anchor
            arrays[key + "_combination_error_bound"][position] = combined_error
            combined_records.append({"mode_position": position, "kind": key, "certificate": certificate,
                                     "actual_raw_bound_containment_passed": contained,
                                     "selected": "certified_components_then_combination" if use else "full882_fallback"})
    arrays.update(b_FE_error_bound=error_fe, raw_MPC_error_bound=error_raw, masks_anchor=masks_anchor,
                  masks_candidate=masks_candidate, H=h.copy(), rule_points=points, rule_weights=weights)
    # Copy and persist only small public replay metadata. The caller still owns
    # the original metadata; the byte allowance above includes these copies.
    arrays.update(MPC_slaves=np.ascontiguousarray(slaves).copy(), MPC_masters=np.ascontiguousarray(masters).copy(),
                  MPC_coefficients=np.ascontiguousarray(coefficients).copy(), MPC_offsets=np.ascontiguousarray(offsets).copy(),
                  cell_dofs=np.stack([np.asarray(V.dofmap.cell_dofs(c), dtype=np.int32) for c in range(18)]),
                  cell_geometry=np.ascontiguousarray(msh.geometry.x[msh.geometry.dofmap]).copy(),
                  cell_permutations=np.ascontiguousarray(permutations).copy(),
                  closure_inventory=np.stack([np.r_[np.asarray(key, dtype=np.int32), value[0]]
                                              for key, value in sorted(topology_cache.items())]),
                  closure_rows=np.stack([topology_cache[(r.reference_face, int(permutations[r.cell]))][0]
                                         for r in rectangles]))
    own_masks = []
    for position in range(12):
        for component in (0, 1):
            for kind, masks in (("anchor", masks_anchor), ("candidate", masks_candidate)):
                rows, values, _ = native.unchanged_mask(arrays["raw_MPC_" + kind][position, component])
                expected_mask = np.zeros(n, dtype=bool)
                expected_mask[rows] = True
                ok = (np.array_equal(masks[position, component], expected_mask)
                      and np.array_equal(arrays["masked_" + kind][position, component, rows], values)
                      and np.all(arrays["masked_" + kind][position, component, ~expected_mask] == 0))
                own_masks.append({"mode_position": position, "component": component, "kind": kind, "passed": bool(ok)})
    if not all(item["passed"] for item in own_masks):
        raise ValueError("own unchanged component masks failed replay")
    artifacts = dict(early_artifacts)
    if root is not None:
        raw_bytes = sum(a.nbytes for a in arrays.values())
        if raw_bytes > RAW_ARTIFACT_LIMIT:
            raise MemoryError("pilot raw artifact admission exceeds 512 MiB")
        for key, array in arrays.items():
            if key not in artifacts:
                artifacts[key] = native._save(root / (key + ".npy"), array, budget)
    record = {"schema": SCHEMA, "status": "SOURCE_PILOT_ASSEMBLED_PENDING_CONTROLS",
              "source": {"path": str(Path(__file__).resolve()), "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "pinned_public_helpers": source_identities, "native_layout": layout,
              "quadrature_degree": quadrature_degree, "actual_nodes_per_facet": q, "unit_mass_metric": unit_mass,
              "unit_mass_policy": native.UNIT_MASS_POLICY, "default_gauss_points_weights_byte_equal": True,
              "basis_values_unthresholded": True, "FFCx_byte_equivalence_claimed": False,
              "basis_hash": int(basis.hash()), "basis_coefficient_matrix_sha256": EXPECTED_COEFFICIENT_SHA256,
              "selected_indices": list(selected_indices), "phase_orders": list(PHASE_ORDERS),
              "native_rows": n, "local_rows": CELL_DOFS, "actual_facets": facets,
              "cell_permutations": native.array_identity(permutations), "phase_modulus_summaries": list(phase_metrics.values()),
              "phase_batches_individually_durable": True,
              "components": component_records, "combined": combined_records, "rowwise_full_rule": rowwise_records,
              "actual_bound_containment": containment_records, "own_component_masks": own_masks,
              "selected_output_gate_passed": True,
              "selected_output_status": "CERTIFIED_CLOSURE_OR_COMPLETE_FULL882_FALLBACK",
              "C_coefficients": [[[v.real, v.imag] for v in pair] for pair in coefficients_c],
              "D_coefficients": [[[v.real, v.imag] for v in pair] for pair in coefficients_d],
              "C_convention": "combine(component-masked x/y, (-traction_x,-traction_y)), then unchanged combination cutoff",
              "D_convention": "conjugate(combine(component-masked x/y, (e_x,e_y)) after combination cutoff) exactly once",
              "H_convention": "caller-supplied production boundary-plane projection denominator diagonal",
              "full_882_anchors_mandatory": True, "finite_excluded_values_thresholded": False,
              "bounds_scope": "binary64 arithmetic on actual computed finite phase/Piola/T tabulation only",
              "Basix_construction_error_bounded": False, "remaining_modal_inventory_qualified": False,
              "component_and_combination_cutoffs_after_MPC": True, "artifacts": artifacts,
              "owned_workspace_admission_maximum_bytes": budget.maximum, "owned_buffer_limit_bytes": OWNED_BUFFER_LIMIT,
              "raw_artifact_limit_bytes": RAW_ARTIFACT_LIMIT, "whole_process_3gib_watchdog_required": True,
              "admitted_replay_metadata_bytes": replay_metadata_bytes,
              "admitted_python_metadata_and_serialization_allowance_bytes": 6 << 20,
              "estimate_is_measured_RSS": False, "FE_JIT_PDE_creation_calls": 0,
              "full_C_D_qualification": False, "target_PDE_qualification": False}
    event({"kind": "boundary_support_finished", "record": record})
    return {"record": record, "arrays": arrays, "rowwise_in_memory": rowwise_in_memory}
