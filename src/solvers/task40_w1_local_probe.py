"""Bounded original-size single-cell W1 Maxwell/port correction witness.

The module assembles only a one-cell p4 or p6 local tensor with the mainline
Maxwell form, factors only its cell-interior block, and streams mode coupling
in bounded batches. It never builds a global volume operator or a dense Hhat.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

import numpy as np

from .directional_boundary import FacetPolynomial, zvalue
from .common_3d_forms import _build_physical_volume_terms


def _local_tensor(
    degree: int,
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    config: Any,
    material_tag: int,
) -> dict[str, Any]:
    import basix.ufl
    import ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI

    from .hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        _orient_cell_tensor,
        _strict_local_lu,
        _tabulate_raw_tensor_class,
    )

    lo = np.asarray([axis[0] for axis in bounds], dtype=np.float64)
    hi = np.asarray([axis[1] for axis in bounds], dtype=np.float64)
    if np.any(hi <= lo) or not np.isfinite(lo).all() or not np.isfinite(hi).all():
        raise ValueError("local target cell bounds must be finite and increasing")
    msh = mesh.create_box(
        MPI.COMM_SELF,
        np.asarray([lo, hi], dtype=np.float64),
        [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    msh.topology.create_entity_permutations()
    ufl_element = basix.ufl.element("N1curl", "hexahedron", degree)
    V = fem.functionspace(msh, ufl_element)
    basix_element = ufl_element.basix_element
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    if material_tag not in (config.tags.air, config.tags.substrate, config.tags.grating):
        raise ValueError("local representative must use an original physical material tag")
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.asarray([0], dtype=np.int32),
        np.asarray([material_tag], dtype=np.int32),
    )
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    curl_curl, material_mass = _build_physical_volume_terms(config, u, v, dx)
    a = curl_curl + material_mass
    # Match common_3d_case_flow: fem.form(a) with the original DOLFINx/FFCx
    # default degree estimation and no added quadrature override.
    compiled = fem.form(a)
    kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
    geometry_map = np.asarray(msh.geometry.dofmap[0], dtype=np.int32)
    coordinates = np.ascontiguousarray(msh.geometry.x[geometry_map], dtype=np.float64)
    if coordinates.shape != (8, 3):
        raise ValueError("local hexahedron geometry dof map must have eight vertices")
    coordinates_flat = np.ascontiguousarray(coordinates.ravel(), dtype=np.float64)
    tensor = _tabulate_raw_tensor_class(
        compiled,
        kernels,
        coordinates_flat,
        tag=material_tag,
        dimension=int(basix_element.dim),
    )
    cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    if cell_info.shape != (1,):
        raise ValueError("one-cell native orientation inventory changed")
    _orient_cell_tensor(V.element, tensor, cell_info)
    interior = np.asarray(basix_element.entity_dofs[3][0], dtype=np.int64)
    trace = np.setdiff1d(np.arange(int(basix_element.dim), dtype=np.int64), interior)
    expected_interior = 450 if degree == 6 else 108 if degree == 4 else None
    if expected_interior is None or len(interior) != expected_interior:
        raise ValueError("local p4/p6 interior support differs from the native Basix inventory")
    Vii = np.ascontiguousarray(tensor[np.ix_(interior, interior)])
    Vit = np.ascontiguousarray(tensor[np.ix_(interior, trace)])
    Vti = np.ascontiguousarray(tensor[np.ix_(trace, interior)])
    Vtt = np.ascontiguousarray(tensor[np.ix_(trace, trace)])
    factor, identity_defect = _strict_local_lu(Vii)
    if not np.isfinite(identity_defect) or identity_defect > 1e-11:
        raise ValueError("one-cell native interior factor identity exceeds its guard")
    return {
        "degree": int(degree),
        "basix_element": basix_element,
        "dof_element": V.element,
        "function_space": V,
        "mesh": msh,
        "cell_info": cell_info,
        "coordinates": coordinates,
        "coordinates_flat": coordinates_flat,
        "geometry_dofmap": geometry_map,
        "cell_dofs": np.asarray(V.dofmap.cell_dofs(0), dtype=np.int64),
        "bounds": tuple((float(a), float(b)) for a, b in zip(lo, hi, strict=True)),
        "tensor": tensor,
        "interior_positions": interior,
        "trace_positions": trace,
        "Vii": Vii,
        "Vit": Vit,
        "Vti": Vti,
        "Vtt": Vtt,
        "factor": factor,
        "interior_factor_identity_relative": float(identity_defect),
        "form_integral_ids": sorted(int(key) for key in kernels),
        "ufcx_form_signature": compiled.module.ffi.string(
            compiled.ufcx_form.signature
        ).decode("ascii"),
        "local_full_dimension": int(basix_element.dim),
        "local_interior_dimension": int(len(interior)),
        "local_trace_dimension": int(len(trace)),
        "volume_quadrature_policy": "fem.form(a) default; matches common_3d_case_flow; no explicit degree override",
        "material_tag": int(material_tag),
        "epsilon_r": [
            complex(
                config.eps_r
                if material_tag == config.tags.air
                else config.substrate_index**2
                if material_tag == config.tags.substrate
                else config.grating_index**2
            ).real,
            complex(
                config.eps_r
                if material_tag == config.tags.air
                else config.substrate_index**2
                if material_tag == config.tags.substrate
                else config.grating_index**2
            ).imag,
        ],
        "k0_nm_inverse": float(config.k0),
        "tensor_seconds": None,
    }


def _direct_full_basis_integral(
    element: Any,
    side: str,
    k_vector: np.ndarray,
    coordinates: np.ndarray,
    quadrature_degree: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Independent tensor-product-free Basix q rule over every native row."""
    import basix

    if side not in ("top", "bottom"):
        raise ValueError("direct full-basis oracle requires top or bottom")
    coordinates = np.asarray(coordinates, dtype=np.float64)
    if coordinates.shape != (8, 3):
        raise ValueError("direct full-basis oracle requires eight actual cell vertices")
    lo, hi = coordinates.min(axis=0), coordinates.max(axis=0)
    if np.any(hi <= lo):
        raise ValueError("direct full-basis oracle requires positive cell extents")
    rule, weights = basix.make_quadrature(
        basix.CellType.quadrilateral, quadrature_degree
    )
    zref = 1.0 if side == "top" else 0.0
    reference_points = np.column_stack((rule, np.full(len(rule), zref)))
    tabulation = element.tabulate(0, reference_points)[0][:, :, :2]
    physical_points = lo + reference_points * (hi - lo)
    phase = np.exp(1j * (physical_points @ np.asarray(k_vector, dtype=np.complex128)))
    integrated = np.einsum(
        "q,q,qjc->jc", weights, phase, tabulation, optimize=True
    ) * np.asarray([(hi - lo)[1], (hi - lo)[0]])
    return np.ascontiguousarray(integrated), rule, weights


def native_local_face_witness(
    *, local: dict[str, Any], layout: Any, side: str, face_i: int, face_j: int
) -> dict[str, Any]:
    """Build/check the literal one-cell E/Eᴴ map on the selected target face.

    This is an actual one-cell Basix orientation witness. The target's full
    volume MPC master/slave map is deliberately not inferred from it.
    """
    from .native_boundary_adapter import build_literal_adapter

    if side not in ("top", "bottom"):
        raise ValueError("native face witness requires top or bottom")
    bounds = local["bounds"]
    literal = {
        "cell_dofs": local["cell_dofs"][None, :],
        "coordinates": local["coordinates"],
        "geometry_dofmap": np.arange(8, dtype=np.int32)[None, :],
        "permutations": local["cell_info"],
        "slaves": np.empty(0, dtype=np.int64),
    }
    description = {
        "name": f"task40-w1-{side}-degree-{local['degree']}",
        "cells": [{
            "side": side,
            "indices": [int(face_i), int(face_j), 0 if side == "bottom" else 13],
            "bounds_nm": [[float(a), float(b)] for a, b in bounds],
        }],
    }
    adapter, construction = build_literal_adapter(
        local["basix_element"],
        literal,
        description,
        layout,
        int(local["local_full_dimension"]),
        np.empty(0, dtype=np.int64),
    )
    expected_rows = np.asarray(layout.maps[side][face_i, face_j], dtype=np.int64)
    if not np.array_equal(adapter.compact_rows, np.unique(expected_rows)):
        raise ValueError("native literal selected-face row map is incomplete or escaped")
    interior_columns = local["interior_positions"]
    if adapter.E[:, interior_columns].nnz:
        raise ValueError("native face map contains cell-interior rows")
    native = np.asarray(
        np.arange(adapter.native_size, dtype=np.float64)
        + 1j * np.arange(adapter.native_size, dtype=np.float64)[::-1],
        dtype=np.complex128,
    ) / max(adapter.native_size, 1)
    dual = np.asarray(
        np.arange(adapter.boundary_size, dtype=np.float64)[::-1]
        + 0.5j * np.arange(adapter.boundary_size, dtype=np.float64),
        dtype=np.complex128,
    ) / max(adapter.boundary_size, 1)
    primal_image = adapter.extract(native)
    dual_image = adapter.scatter(dual)
    lhs = np.vdot(dual, primal_image)
    rhs = np.vdot(dual_image, native)
    relative = float(abs(lhs - rhs) / max(abs(lhs), abs(rhs), np.finfo(float).tiny))
    if relative > 1e-11:
        raise ValueError("one-cell native E/EH pairing failed")
    return {
        "side": side,
        "degree": int(local["degree"]),
        "native_dofs": int(adapter.native_size),
        "compact_boundary_rows": int(len(adapter.compact_rows)),
        "boundary_row_universe": int(adapter.boundary_size),
        "exact_slave_storage_count": int(len(adapter.slaves)),
        "MPC_full_target_mapping": "NOT_RUN; original-size volume mesh and global MPC IDs are absent",
        "E_EH_pairing_relative": relative,
        "selected_face_row_membership_pass": True,
        "cell_interior_columns_exactly_zero": True,
        "nonzero_native_map_entries": int(adapter.E.nnz),
        "construction": construction,
        "max_abs_native_scatter": float(np.max(np.abs(dual_image), initial=0.0)),
    }


def stream_boundary_correction(
    *,
    modes: list[dict],
    side: str,
    degree: int,
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    config: Any,
    material_tag: int,
    mode_alpha: np.ndarray,
    trace_values: np.ndarray,
    known_interior_solution: np.ndarray,
    boundary_layout: Any,
    face_i: int,
    face_j: int,
    boundary_quadrature_degree: int = 30,
    batch_modes: int = 64,
) -> dict[str, Any]:
    """Apply one real p4/p6 local condensed block over all ordered keys.

    ``Hp`` is the implicit identity. ``Hhat @ alpha`` and the affine internal
    RHS correction are streamed as ``alpha + Di solve(Bi alpha)`` and
    ``g + Di solve(fi)``; no mode-square object is created.
    """
    began = perf_counter()
    if side not in ("top", "bottom") or batch_modes < 1:
        raise ValueError("one physical port side and a positive mode batch are required")
    local = _local_tensor(degree, bounds, config, material_tag)
    native_face = native_local_face_witness(
        local=local,
        layout=boundary_layout,
        side=side,
        face_i=face_i,
        face_j=face_j,
    )
    nmode = len(modes)
    ni = local["local_interior_dimension"]
    nt = local["local_trace_dimension"]
    alpha = np.asarray(mode_alpha, dtype=np.complex128)
    xt = np.asarray(trace_values, dtype=np.complex128)
    xi0 = np.asarray(known_interior_solution, dtype=np.complex128)
    if alpha.shape != (nmode,):
        raise ValueError("full ordered mode alpha shape differs")
    if xt.shape != (nt,) or xi0.shape != (ni,):
        raise ValueError("known local trace/interior solution shapes differ")
    if any(not np.isfinite(a).all() for a in (alpha, xt, xi0)):
        raise ValueError("local witness vectors must be finite")
    if not np.linalg.norm(alpha) or not np.linalg.norm(xi0) or not np.linalg.norm(xt):
        raise ValueError("manufactured alpha/interior/trace solution must be nonzero")

    polynomial = FacetPolynomial(local["basix_element"])
    coordinates = local["coordinates"]
    lower = np.min(coordinates, axis=0)
    upper = np.max(coordinates, axis=0)
    jacobian = np.diag(upper - lower)
    origin = lower.copy()
    interior = local["interior_positions"]
    trace = local["trace_positions"]
    Vii, Vit, Vti, Vtt = local["Vii"], local["Vit"], local["Vti"], local["Vtt"]
    Bi_alpha = np.zeros(ni, dtype=np.complex128)
    Bt_alpha = np.zeros(nt, dtype=np.complex128)
    active_indices = np.asarray([i for i, row in enumerate(modes) if row["side"] == side], dtype=np.int64)
    if not len(active_indices):
        raise ValueError("the frozen full mode inventory has no modes on selected side")
    local_integral_calls = 0
    internal_B_nonzero_entries = 0
    internal_D_nonzero_entries = 0
    max_abs_internal_B = 0.0
    max_abs_internal_D = 0.0

    def native_mode_vectors(index: int) -> tuple[np.ndarray, np.ndarray]:
        row = modes[index]
        kv = np.asarray([zvalue(v) for v in row["k_vector"]], dtype=np.complex128)
        integrated = polynomial.integral_native(
            side,
            kv,
            jacobian,
            origin,
            int(boundary_quadrature_degree),
        )
        e = np.asarray([zvalue(v) for v in row["e_vector"][:2]], dtype=np.complex128)
        traction = np.asarray([zvalue(v) for v in row["traction_vector"][:2]], dtype=np.complex128)
        h = float(row["projection_denominator"])
        if not np.isfinite(h) or h <= 0:
            raise ValueError("original modal projection denominator must be finite and positive")
        # The full native basis integral includes cell-interior positions.
        # Do not project through FacetPolynomial.active or threshold small
        # entries: the mainline local partition is applied only afterwards.
        b_native = integrated @ (-traction)
        d_native = (integrated @ e).conj() / h
        if local["dof_element"].needs_dof_transformations:
            b_native = np.ascontiguousarray(b_native)
            d_native = np.ascontiguousarray(d_native)
            local["dof_element"].T_apply(b_native, local["cell_info"], 1)
            local["dof_element"].T_apply(d_native, local["cell_info"], 1)
        return b_native, d_native

    def port_vectors(index: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        b_native, d_native = native_mode_vectors(index)
        return b_native[interior], b_native[trace], d_native[interior], d_native[trace]

    for start in range(0, len(active_indices), batch_modes):
        for index in active_indices[start : start + batch_modes]:
            bi, bt, _di, _dt = port_vectors(int(index))
            Bi_alpha += bi * alpha[index]
            Bt_alpha += bt * alpha[index]
            internal_B_nonzero_entries += int(np.count_nonzero(bi))
            max_abs_internal_B = max(max_abs_internal_B, float(np.max(np.abs(bi), initial=0.0)))
            local_integral_calls += 1

    from scipy.linalg import lu_solve

    # Manufacture compatible loads from one known nonzero native state.
    # This makes the full interior/trace/port residuals meaningful gates.
    fi = Vii @ xi0 + Vit @ xt + Bi_alpha
    solve_b_alpha = lu_solve(local["factor"], Bi_alpha)
    solve_fi = lu_solve(local["factor"], fi)
    xi = lu_solve(local["factor"], fi - Vit @ xt - Bi_alpha)
    solve_vit_trace = lu_solve(local["factor"], Vit @ xt)
    qhat_alpha = alpha.copy()  # original Hp is the implicit identity
    affine_internal_rhs = np.zeros(nmode, dtype=np.complex128)
    rhs_p = np.zeros(nmode, dtype=np.complex128)
    port_lhs = np.zeros(nmode, dtype=np.complex128)
    correction_trace = np.zeros(nmode, dtype=np.complex128)
    Dt_trace = np.zeros(nmode, dtype=np.complex128)
    Di_solve_b = np.zeros(nmode, dtype=np.complex128)
    Di_solve_f = np.zeros(nmode, dtype=np.complex128)
    Di_xi = np.zeros(nmode, dtype=np.complex128)
    Di_xi0 = np.zeros(nmode, dtype=np.complex128)
    d_i_alpha_norm_sq = 0.0
    d_i_f_norm_sq = 0.0
    d_t_trace_norm_sq = 0.0
    for start in range(0, len(active_indices), batch_modes):
        for index in active_indices[start : start + batch_modes]:
            _bi, _bt, di, dt = port_vectors(int(index))
            qhat_alpha[index] += di @ solve_b_alpha
            affine_internal_rhs[index] += di @ solve_fi
            Di_solve_b[index] = di @ solve_b_alpha
            Di_solve_f[index] = di @ solve_fi
            Di_xi[index] = di @ xi
            Di_xi0[index] = di @ xi0
            correction_trace[index] = di @ solve_vit_trace
            Dt_trace[index] = dt @ xt
            internal_D_nonzero_entries += int(np.count_nonzero(di))
            max_abs_internal_D = max(max_abs_internal_D, float(np.max(np.abs(di), initial=0.0)))
            d_i_alpha_norm_sq += float(abs(di @ solve_b_alpha) ** 2)
            d_i_f_norm_sq += float(abs(di @ solve_fi) ** 2)
            d_t_trace_norm_sq += float(abs(dt @ xt) ** 2)
            local_integral_calls += 1

    rhs_p = alpha - Di_xi0 - Dt_trace
    affine_internal_rhs = rhs_p + Di_solve_f
    port_lhs = alpha - rhs_p - Di_xi - Dt_trace
    ft = Vti @ xi0 + Vtt @ xt + Bt_alpha
    S_V = Vtt - Vti @ lu_solve(local["factor"], Vit)
    Bhat_alpha = Bt_alpha - Vti @ solve_b_alpha
    original_trace_lhs = Vti @ xi + Vtt @ xt + Bt_alpha - ft
    reduced_trace_lhs = S_V @ xt + Bhat_alpha - (ft - Vti @ solve_fi)
    original_port_lhs = port_lhs
    reduced_port_lhs = qhat_alpha - affine_internal_rhs - Dt_trace + correction_trace
    interior_equation = Vii @ xi + Vit @ xt + Bi_alpha - fi
    local_recovery_rel = float(
        np.linalg.norm(interior_equation)
        / max(
            float(np.linalg.norm(Vii @ xi)), float(np.linalg.norm(Vit @ xt)),
            float(np.linalg.norm(Bi_alpha)), float(np.linalg.norm(fi)),
            np.finfo(float).tiny,
        )
    )
    solution_reference_rel = float(
        np.linalg.norm(xi - xi0)
        / max(float(np.linalg.norm(xi0)), np.finfo(float).tiny)
    )
    original_trace_scale = max(
        float(np.linalg.norm(Vti @ xi)), float(np.linalg.norm(Vtt @ xt)),
        float(np.linalg.norm(Bt_alpha)), float(np.linalg.norm(ft)), np.finfo(float).tiny,
    )
    reduced_trace_scale = max(
        float(np.linalg.norm(S_V @ xt)), float(np.linalg.norm(Bhat_alpha)),
        float(np.linalg.norm(ft - Vti @ solve_fi)), np.finfo(float).tiny,
    )
    original_trace_residual_rel = float(
        np.linalg.norm(original_trace_lhs) / original_trace_scale
    )
    reduced_trace_residual_rel = float(
        np.linalg.norm(reduced_trace_lhs) / reduced_trace_scale
    )
    trace_equation_rel = float(
        np.linalg.norm(original_trace_lhs - reduced_trace_lhs)
        / max(original_trace_scale, reduced_trace_scale, np.finfo(float).tiny)
    )
    original_port_scale = max(
        float(np.linalg.norm(alpha)), float(np.linalg.norm(rhs_p)),
        float(np.linalg.norm(Di_xi)), float(np.linalg.norm(Dt_trace)), np.finfo(float).tiny,
    )
    reduced_port_scale = max(
        float(np.linalg.norm(qhat_alpha)), float(np.linalg.norm(affine_internal_rhs)),
        float(np.linalg.norm(Dt_trace)), float(np.linalg.norm(correction_trace)),
        np.finfo(float).tiny,
    )
    original_port_residual_rel = float(
        np.linalg.norm(original_port_lhs) / original_port_scale
    )
    reduced_port_residual_rel = float(
        np.linalg.norm(reduced_port_lhs) / reduced_port_scale
    )
    port_residual_rel = float(
        np.linalg.norm(original_port_lhs - reduced_port_lhs)
        / max(original_port_scale, reduced_port_scale, np.finfo(float).tiny)
    )
    # Independently route one frozen key through the mainline direct-trace
    # carrier constructor. Interior rows remain in Bi/Di; only the trace
    # slices are passed to P6DirectTracePortTerms. This is local identity-MPC
    # wiring only; no full-target MPC numbering is claimed.
    from types import SimpleNamespace
    from .native_boundary_adapter import independent_trace_port_terms

    witness_index = int(active_indices[0])
    witness_b_native, witness_d_native = native_mode_vectors(witness_index)
    witness_mode = modes[witness_index]
    witness_k = np.asarray(
        [zvalue(value) for value in witness_mode["k_vector"]], dtype=np.complex128
    )
    witness_e = np.asarray(
        [zvalue(value) for value in witness_mode["e_vector"][:2]],
        dtype=np.complex128,
    )
    witness_traction = np.asarray(
        [zvalue(value) for value in witness_mode["traction_vector"][:2]],
        dtype=np.complex128,
    )
    witness_h = float(witness_mode["projection_denominator"])
    direct_integral, direct_rule, direct_weights = _direct_full_basis_integral(
        local["basix_element"], side, witness_k, local["coordinates"],
        int(boundary_quadrature_degree),
    )
    direct_b_native = direct_integral @ (-witness_traction)
    direct_d_native = (direct_integral @ witness_e).conj() / witness_h
    if local["dof_element"].needs_dof_transformations:
        direct_b_native = np.ascontiguousarray(direct_b_native)
        direct_d_native = np.ascontiguousarray(direct_d_native)
        local["dof_element"].T_apply(direct_b_native, local["cell_info"], 1)
        local["dof_element"].T_apply(direct_d_native, local["cell_info"], 1)
    oracle_b_relative = float(
        np.linalg.norm(direct_b_native - witness_b_native)
        / max(float(np.linalg.norm(direct_b_native)), np.finfo(float).tiny)
    )
    oracle_d_relative = float(
        np.linalg.norm(direct_d_native - witness_d_native)
        / max(float(np.linalg.norm(direct_d_native)), np.finfo(float).tiny)
    )
    direct_C = np.zeros((local["local_full_dimension"], 1), dtype=np.complex128)
    direct_D = np.zeros((1, local["local_full_dimension"]), dtype=np.complex128)
    direct_C[trace, 0] = witness_b_native[trace]
    direct_D[0, trace] = witness_d_native[trace]
    trace_rows = np.asarray(trace, dtype=np.int64)
    local_system = SimpleNamespace(
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=trace_rows,
            original_to_active={int(row): i for i, row in enumerate(trace_rows)},
        )
    )
    direct_terms = independent_trace_port_terms(local_system, direct_C, direct_D)
    direct_term = direct_terms[0]
    direct_b_relative = float(
        np.linalg.norm(direct_term.B_values - direct_C[direct_term.B_original_rows, 0])
        / max(float(np.linalg.norm(direct_C)), np.finfo(float).tiny)
    )
    direct_d_relative = float(
        np.linalg.norm(direct_term.D_values - direct_D[0, direct_term.D_original_rows])
        / max(float(np.linalg.norm(direct_D)), np.finfo(float).tiny)
    )
    if direct_b_relative > 1e-14 or direct_d_relative > 1e-14:
        raise ValueError("native full-row/trace direct carrier split changed its values")
    return {
        "degree": int(degree),
        "side": side,
        "state_classification": "manufactured consistent nonzero known xi0/xt/alpha; arbitrary retained states are not claimed solved",
        "class_bounds_nm": [[float(a), float(b)] for a, b in bounds],
        "epsilon_r": local["epsilon_r"],
        "volume_quadrature_policy": local["volume_quadrature_policy"],
        "ufcx_form_signature": local["ufcx_form_signature"],
        "boundary_quadrature_degree": int(boundary_quadrature_degree),
        "mode_count_full_ordered": nmode,
        "mode_count_integrated_for_this_port_side": int(len(active_indices)),
        "batch_modes": int(batch_modes),
        "full_local_rows": local["local_full_dimension"],
        "internal_rows": ni,
        "trace_rows": nt,
        "interior_factor_identity_relative": local["interior_factor_identity_relative"],
        "local_Hhat_materialized": False,
        "native_face_mapping": native_face,
        "internal_B_native_nonzero_entries_over_all_modes": internal_B_nonzero_entries,
        "internal_D_native_nonzero_entries_over_all_modes": internal_D_nonzero_entries,
        "max_abs_internal_B_native": max_abs_internal_B,
        "max_abs_internal_D_native": max_abs_internal_D,
        "small_key_native_carrier_witness": {
            "ordered_key_index": witness_index,
            "key": [
                modes[witness_index]["side"], modes[witness_index]["m"],
                modes[witness_index]["n"], modes[witness_index]["polarization"],
            ],
            "internal_B_nonzero_count": int(np.count_nonzero(witness_b_native[interior])),
            "internal_D_nonzero_count": int(np.count_nonzero(witness_d_native[interior])),
            "internal_B_max_abs": float(np.max(np.abs(witness_b_native[interior]), initial=0.0)),
            "internal_D_max_abs": float(np.max(np.abs(witness_d_native[interior]), initial=0.0)),
            "trace_carrier_api": "P6DirectTracePortTerms via independent_trace_port_terms",
            "direct_trace_B_relative": direct_b_relative,
            "direct_trace_D_relative": direct_d_relative,
            "full_dof_direct_q30_B_relative": oracle_b_relative,
            "full_dof_direct_q30_D_relative": oracle_d_relative,
            "full_dof_direct_q30_gate_pass": bool(
                oracle_b_relative <= 1e-10 and oracle_d_relative <= 1e-10
            ),
            "D_constructed_independently_from_B": True,
            "global_target_MPC_mapping": "NOT_RUN",
        },
        "original_Hp_representation": "implicit identity vector action",
        "local_integral_calls": local_integral_calls,
        "nonzero_internal_rhs_norm": float(np.linalg.norm(fi)),
        "nonzero_full_port_rhs_norm": float(np.linalg.norm(rhs_p)),
        "nonzero_trace_rhs_norm": float(np.linalg.norm(ft)),
        "full_mode_Hhat_alpha_norm": float(np.linalg.norm(qhat_alpha)),
        "full_mode_Hhat_minus_Hp_alpha_norm": float(np.linalg.norm(qhat_alpha - alpha)),
        "full_mode_affine_internal_port_rhs_correction_norm": float(np.linalg.norm(affine_internal_rhs - rhs_p)),
        "full_mode_Di_solve_Bi_alpha_norm": float(np.sqrt(d_i_alpha_norm_sq)),
        "full_mode_Di_solve_fi_norm": float(np.sqrt(d_i_f_norm_sq)),
        "full_mode_Dt_trace_norm": float(np.sqrt(d_t_trace_norm_sq)),
        "local_recovery_equation_relative": local_recovery_rel,
        "known_interior_solution_relative": solution_reference_rel,
        "local_original_trace_equation_relative": original_trace_residual_rel,
        "local_reduced_trace_equation_relative": reduced_trace_residual_rel,
        "local_trace_elimination_identity_relative": trace_equation_rel,
        "local_port_equation_relative": original_port_residual_rel,
        "local_reduced_port_equation_relative": reduced_port_residual_rel,
        "local_port_elimination_identity_relative": port_residual_rel,
        "original_Hhat_gate": "matrix-free vector actions only; no 32060-square allocation",
        "seconds": float(perf_counter() - began),
        "arrays": {
            "qhat_alpha": qhat_alpha,
            "affine_internal_rhs": affine_internal_rhs,
            "port_residual": port_lhs,
            "reduced_port_residual": reduced_port_lhs,
            "port_internal_trace_correction": correction_trace,
            "port_trace_action": Dt_trace,
            "recovered_interior": xi,
            "interior_rhs": fi,
            "port_rhs": rhs_p,
            "mode_alpha": alpha,
            "known_interior_solution": xi0,
            "port_manufactured_internal_term": Di_xi0,
            "local_native_tensor": local["tensor"],
            "interior_positions": interior,
            "trace_positions": trace,
            "trace_values": xt,
            "trace_rhs": ft,
            "Bi_alpha": Bi_alpha,
            "Bt_alpha": Bt_alpha,
            "port_internal_B_correction": Di_solve_b,
            "port_internal_rhs_correction": Di_solve_f,
            "port_internal_recovered_correction": Di_xi,
            "local_cell_coordinates": local["coordinates"],
            "local_cell_orientation": local["cell_info"],
            "witness_mode_k": witness_k,
            "witness_mode_e": witness_e,
            "witness_mode_traction": witness_traction,
            "witness_mode_projection_denominator": np.asarray(witness_h),
            "witness_direct_q30_integrated_basis": direct_integral,
            "witness_direct_q30_rule_points": direct_rule,
            "witness_direct_q30_rule_weights": direct_weights,
            "witness_direct_q30_B_native": direct_b_native,
            "witness_direct_q30_D_native": direct_d_native,
            "witness_candidate_B_native": witness_b_native,
            "witness_candidate_D_native": witness_d_native,
            "witness_internal_B_native": witness_b_native[interior],
            "witness_internal_D_native": witness_d_native[interior],
            "witness_trace_B_native": witness_b_native[trace],
            "witness_trace_D_native": witness_d_native[trace],
        },
        "mesh_and_form": {
            "one_cell_mesh_only": True,
            "global_volume_matrix": False,
            "global_factor": False,
            "form_integral_ids": local["form_integral_ids"],
            "volume_quadrature_policy": local["volume_quadrature_policy"],
            "ufcx_form_signature": local["ufcx_form_signature"],
            "native_cell_orientation": local["cell_info"].astype(int).tolist(),
            "tensor_bytes": int(local["tensor"].nbytes),
        },
    }
