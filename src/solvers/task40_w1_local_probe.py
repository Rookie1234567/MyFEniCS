"""Bounded original-size single-cell W1 Maxwell/port correction witness.

The module assembles only a one-cell p4 or p6 local tensor with the mainline
Maxwell form, factors only its cell-interior block, and streams mode coupling
in bounded batches. It never builds a global volume operator or a dense Hhat.
"""

from __future__ import annotations

import hashlib
from time import perf_counter
from typing import Any

import numpy as np

from .directional_boundary import FacetPolynomial, zvalue
from .common_3d_forms import _build_physical_volume_terms
from .task40_w1_moment_reference import legendre_exponential_moments


def _local_norm(values: np.ndarray) -> float:
    magnitude = np.abs(np.asarray(values))
    return float(np.sqrt(np.sum(magnitude * magnitude, dtype=np.longdouble)))


def _local_residual(
    matrix: np.ndarray, solution: np.ndarray, rhs: np.ndarray
) -> tuple[np.ndarray, float, str]:
    if np.finfo(np.longdouble).eps < np.finfo(np.float64).eps:
        wide = np.clongdouble
        matrix_wide = np.asarray(matrix, dtype=wide)
        solution_wide = np.asarray(solution, dtype=wide)
        rhs_wide = np.asarray(rhs, dtype=wide)
        product = matrix_wide @ solution_wide
        residual = rhs_wide - product
        method = "numpy.clongdouble raw-matrix product"
    else:
        product = matrix @ solution
        residual = rhs - product
        method = "complex128 raw-matrix product"
    scale = max(_local_norm(product), _local_norm(rhs), np.finfo(float).tiny)
    residual_rel = _local_norm(residual) / scale
    if not np.isfinite(residual).all() or not np.isfinite(residual_rel):
        raise FloatingPointError("local raw-matrix residual became non-finite")
    return residual, residual_rel, method


def solve_local_rhs(
    raw_matrix: np.ndarray,
    factor: Any,
    rhs: np.ndarray,
    *,
    max_corrections: int = 3,
    reference_solution: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Solve a bounded local block with its existing LU and residual corrections.

    The raw complex128 matrix is retained for residual evaluation.  The supplied
    factor is reused for the initial solve and every correction; this helper
    never factors or overwrites the matrix.
    """
    from scipy.linalg import lu_solve

    matrix = np.asarray(raw_matrix, dtype=np.complex128)
    right_hand_side = np.asarray(rhs, dtype=np.complex128)
    if (
        matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or right_hand_side.ndim not in (1, 2)
        or right_hand_side.shape[0] != matrix.shape[0]
    ):
        raise ValueError("local solve requires a square matrix and a vector or block RHS")
    if not 0 <= max_corrections <= 3:
        raise ValueError("local solve correction budget must be between zero and three")
    if not np.isfinite(matrix).all() or not np.isfinite(right_hand_side).all():
        raise ValueError("local solve matrix and RHS must be finite")
    reference = None if reference_solution is None else np.asarray(
        reference_solution, dtype=np.complex128
    )
    if reference is not None and reference.shape != right_hand_side.shape:
        raise ValueError("local solve reference solution shape differs from RHS")
    if reference is not None and not np.isfinite(reference).all():
        raise ValueError("local solve reference solution must be finite")

    solution = np.asarray(lu_solve(factor, right_hand_side), dtype=np.complex128)
    initial_solution = solution.copy()
    lu_solve_call_count = 1
    if not np.isfinite(solution).all():
        raise FloatingPointError("initial local LU solution became non-finite")
    residual, residual_rel, residual_method = _local_residual(
        matrix, solution, right_hand_side
    )
    history = [residual_rel]
    attempts: list[dict[str, Any]] = []
    stop_reason = "zero_residual" if not np.any(residual) else "max_corrections"
    for iteration in range(1, max_corrections + 1):
        if not np.any(residual):
            stop_reason = "zero_residual"
            break
        correction = np.asarray(
            lu_solve(factor, np.asarray(residual, dtype=np.complex128)),
            dtype=np.complex128,
        )
        lu_solve_call_count += 1
        if not np.isfinite(correction).all():
            raise FloatingPointError("local residual correction became non-finite")
        candidate = solution + correction
        if not np.isfinite(candidate).all():
            raise FloatingPointError("corrected local solution became non-finite")
        candidate_residual, candidate_rel, _ = _local_residual(
            matrix, candidate, right_hand_side
        )
        accepted = bool(np.isfinite(candidate_rel) and candidate_rel < residual_rel)
        attempt: dict[str, Any] = {
            "iteration": iteration,
            "relative_residual_before": float(residual_rel),
            "relative_residual_after": float(candidate_rel),
            "relative_solution_update": float(
                _local_norm(correction)
                / max(_local_norm(candidate), np.finfo(float).tiny)
            ),
            "accepted": accepted,
        }
        if reference is not None:
            attempt["forward_relative_after"] = float(
                _local_norm(candidate - reference)
                / max(_local_norm(reference), np.finfo(float).tiny)
            )
        attempts.append(attempt)
        if not accepted:
            stop_reason = "residual_stagnation"
            break
        solution = candidate
        residual = candidate_residual
        residual_rel = candidate_rel
        history.append(float(residual_rel))
    final_forward_rel = None
    initial_forward_rel = None
    if reference is not None:
        initial_forward_rel = float(
            _local_norm(initial_solution - reference)
            / max(_local_norm(reference), np.finfo(float).tiny)
        )
        final_forward_rel = float(
            _local_norm(solution - reference)
            / max(_local_norm(reference), np.finfo(float).tiny)
        )
    wide_accumulator = residual_method.startswith("numpy.clongdouble")
    real_precision = np.finfo(np.longdouble if wide_accumulator else np.float64)
    return solution, {
        "factor_reused": True,
        "refactor_count": 0,
        "lu_solve_call_count": lu_solve_call_count,
        "residual_accumulator": residual_method,
        "residual_accumulator_receipt": {
            "dtype": np.dtype(
                np.clongdouble if wide_accumulator else np.complex128
            ).name,
            "itemsize_bytes": int(
                np.dtype(np.clongdouble if wide_accumulator else np.complex128).itemsize
            ),
            "real_epsilon": float(real_precision.eps),
            "real_mantissa_bits": int(real_precision.nmant),
        },
        "initial_relative_residual": float(history[0]),
        "relative_residual_history": history,
        "correction_attempts": attempts,
        "accepted_corrections": int(sum(item["accepted"] for item in attempts)),
        "final_relative_residual": float(residual_rel),
        "stop_reason": stop_reason,
        "initial_forward_relative": initial_forward_rel,
        "final_forward_relative": final_forward_rel,
    }


def _local_rhs_roundoff_facts(
    Vii: np.ndarray,
    Vit: np.ndarray,
    xi0: np.ndarray,
    xt: np.ndarray,
    Bi_alpha: np.ndarray,
    fi: np.ndarray,
    recovery_rhs: np.ndarray,
) -> dict[str, Any]:
    if np.finfo(np.longdouble).eps >= np.finfo(np.float64).eps:
        return {
            "status": "NOT_AVAILABLE_NO_WIDER_ACCUMULATOR",
            "residual_accumulator": "complex128",
        }
    wide = np.clongdouble
    Vii_wide = np.asarray(Vii, dtype=wide)
    Vit_wide = np.asarray(Vit, dtype=wide)
    xi0_wide = np.asarray(xi0, dtype=wide)
    xt_wide = np.asarray(xt, dtype=wide)
    Bi_wide = np.asarray(Bi_alpha, dtype=wide)
    fi_wide = np.asarray(fi, dtype=wide)
    recovery_rhs_wide = np.asarray(recovery_rhs, dtype=wide)
    Axi0_wide = Vii_wide @ xi0_wide
    Vitxt_wide = Vit_wide @ xt_wide
    manufactured_wide = Axi0_wide + Vitxt_wide + Bi_wide
    subtract_wide = fi_wide - Vitxt_wide - Bi_wide
    manufacture_scale = max(
        _local_norm(Axi0_wide), _local_norm(Vitxt_wide), _local_norm(Bi_wide),
        _local_norm(fi_wide), np.finfo(float).tiny,
    )
    subtract_scale = max(
        _local_norm(subtract_wide), _local_norm(Axi0_wide), np.finfo(float).tiny
    )
    ideal_scale = max(_local_norm(Axi0_wide), np.finfo(float).tiny)
    return {
        "status": "MEASURED",
        "residual_accumulator": "numpy.clongdouble raw products; complex128 inputs",
        "residual_accumulator_receipt": {
            "dtype": np.dtype(np.clongdouble).name,
            "itemsize_bytes": int(np.dtype(np.clongdouble).itemsize),
            "real_epsilon": float(np.finfo(np.longdouble).eps),
            "real_mantissa_bits": int(np.finfo(np.longdouble).nmant),
        },
        "manufacture_roundoff_relative": float(
            _local_norm(fi_wide - manufactured_wide) / manufacture_scale
        ),
        "recovery_rhs_subtraction_roundoff_relative": float(
            _local_norm(recovery_rhs_wide - subtract_wide) / subtract_scale
        ),
        "recovery_rhs_vs_Vii_xi0_relative": float(
            _local_norm(recovery_rhs_wide - Axi0_wide) / ideal_scale
        ),
    }


def _local_condition_1_estimate(
    raw_matrix: np.ndarray, factor: Any
) -> float | None:
    from scipy.linalg.lapack import get_lapack_funcs

    lu = factor[0] if isinstance(factor, tuple) else factor
    gecon = get_lapack_funcs("gecon", (raw_matrix,))
    reciprocal_condition, info = gecon(
        lu, float(np.linalg.norm(raw_matrix, ord=1)), norm="1"
    )
    if info != 0 or reciprocal_condition <= 0 or not np.isfinite(reciprocal_condition):
        return None
    return float(1.0 / reciprocal_condition)


def _local_entry_scale_spread(matrix: np.ndarray, axis: int) -> float | None:
    maxima = np.max(np.abs(matrix), axis=axis)
    nonzero = maxima[maxima > 0]
    if not len(nonzero):
        return None
    return float(np.max(nonzero) / np.min(nonzero))


def _local_tensor(
    degree: int,
    bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    config: Any,
    material_tag: int,
    *,
    saved_volume: dict[str, Any] | None = None,
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
    geometry_map = np.asarray(msh.geometry.dofmap[0], dtype=np.int32)
    coordinates = np.ascontiguousarray(msh.geometry.x[geometry_map], dtype=np.float64)
    if coordinates.shape != (8, 3):
        raise ValueError("local hexahedron geometry dof map must have eight vertices")
    coordinates_flat = np.ascontiguousarray(coordinates.ravel(), dtype=np.float64)
    cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    if cell_info.shape != (1,):
        raise ValueError("one-cell native orientation inventory changed")
    if saved_volume is None:
        dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
        curl_curl, material_mass = _build_physical_volume_terms(config, u, v, dx)
        a = curl_curl + material_mass
        # Match common_3d_case_flow: fem.form(a) with the original DOLFINx/FFCx
        # default degree estimation and no added quadrature override.
        compiled = fem.form(a)
        kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
        tensor = _tabulate_raw_tensor_class(
            compiled,
            kernels,
            coordinates_flat,
            tag=material_tag,
            dimension=int(basix_element.dim),
        )
        _orient_cell_tensor(V.element, tensor, cell_info)
        form_integral_ids = sorted(int(key) for key in kernels)
        form_signature = compiled.module.ffi.string(
            compiled.ufcx_form.signature
        ).decode("ascii")
        volume_policy = (
            "fem.form(a) default; matches common_3d_case_flow; "
            "no explicit degree override"
        )
    else:
        required = {
            "tensor", "coordinates", "cell_info", "interior_positions", "trace_positions"
        }
        if required - saved_volume.keys():
            raise ValueError("saved local volume record is missing required arrays")
        saved_coordinates = np.asarray(saved_volume["coordinates"], dtype=np.float64)
        saved_cell_info = np.asarray(saved_volume["cell_info"], dtype=np.uint32)
        if (
            saved_coordinates.shape != (8, 3)
            or not np.allclose(saved_coordinates, coordinates, rtol=0, atol=2e-14)
            or saved_cell_info.shape != (1,)
            or not np.array_equal(saved_cell_info, cell_info)
        ):
            raise ValueError("saved local volume geometry/orientation identity differs")
        tensor = np.ascontiguousarray(saved_volume["tensor"], dtype=np.complex128)
        if tensor.shape != (int(basix_element.dim), int(basix_element.dim)):
            raise ValueError("saved local volume tensor has a different Basix dimension")
        form_integral_ids = []
        form_signature = "REUSED_SAVED_RAW_W1_NATIVE_VOLUME_TENSOR"
        volume_policy = "reused hash-bound W1 raw local tensor; volume form not reassembled"
    interior = np.asarray(basix_element.entity_dofs[3][0], dtype=np.int64)
    trace = np.setdiff1d(np.arange(int(basix_element.dim), dtype=np.int64), interior)
    expected_interior = 450 if degree == 6 else 108 if degree == 4 else None
    if expected_interior is None or len(interior) != expected_interior:
        raise ValueError("local p4/p6 interior support differs from the native Basix inventory")
    if saved_volume is not None and (
        not np.array_equal(
            np.asarray(saved_volume["interior_positions"], dtype=np.int64), interior
        )
        or not np.array_equal(
            np.asarray(saved_volume["trace_positions"], dtype=np.int64), trace
        )
    ):
        raise ValueError("saved local volume row partition differs from the native Basix inventory")
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
        "form_integral_ids": form_integral_ids,
        "ufcx_form_signature": form_signature,
        "local_full_dimension": int(basix_element.dim),
        "local_interior_dimension": int(len(interior)),
        "local_trace_dimension": int(len(trace)),
        "volume_quadrature_policy": volume_policy,
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


def direct_single_face_projection(
    layout: Any,
    mode: dict[str, Any],
    trace: np.ndarray,
    quadrature_degree: int,
    face_i: int,
    face_j: int,
) -> np.ndarray:
    """Independent Basix quadrature for one physical panel and one mode."""
    import basix

    if (
        isinstance(quadrature_degree, bool)
        or not isinstance(quadrature_degree, int)
        or quadrature_degree < 1
    ):
        raise ValueError("direct panel quadrature degree must be positive")
    if not 0 <= face_i < layout.nx or not 0 <= face_j < layout.ny:
        raise ValueError("direct panel index is outside the boundary layout")
    side = mode.get("side")
    if side not in ("top", "bottom"):
        raise ValueError("direct panel mode must name top or bottom")
    values = np.asarray(trace)
    if (
        values.shape != (layout.rows,)
        or values.dtype != np.complex128
        or not np.isfinite(values).all()
    ):
        raise ValueError("direct panel trace must be finite complex128 on the full layout")
    rule, weights = basix.make_quadrature(
        basix.CellType.quadrilateral, quadrature_degree
    )
    zref = 0.0 if side == "bottom" else 1.0
    tab = layout.polynomial.element.tabulate(
        0, np.column_stack((rule, np.full(len(rule), zref)))
    )[0][:, layout.polynomial.active[side], :2]
    dx = float(layout.x[face_i + 1] - layout.x[face_i])
    dy = float(layout.y[face_j + 1] - layout.y[face_j])
    reference_plane = float(mode["reference_plane_nm"])
    points = np.column_stack((
        layout.x[face_i] + dx * rule[:, 0],
        layout.y[face_j] + dy * rule[:, 1],
        np.full(len(rule), reference_plane),
    ))
    k_vector = np.asarray(
        [zvalue(value) for value in mode["k_vector"]], dtype=np.complex128
    )
    basis_integral = np.einsum(
        "q,qjc->jc",
        weights * np.exp(-1j * np.conj(points @ k_vector)),
        tab,
        optimize=True,
    ) * np.asarray([dy, dx])
    local = (
        values[layout.maps[side][face_i, face_j]]
        * layout.weights[side][face_i, face_j]
    )
    return np.asarray(local @ basis_integral, dtype=np.complex128)


def analytic_full_basis_integral(
    polynomial: FacetPolynomial,
    side: str,
    wave_vector: np.ndarray,
    jacobian: np.ndarray,
    origin: np.ndarray,
    *,
    moment_cache: dict[tuple[int, complex, float, float, int, int], np.ndarray] | None = None,
    dps: int = 60,
) -> np.ndarray:
    """Closed-form full native-row integral; x/y origin phase is included once."""
    if side not in ("top", "bottom"):
        raise ValueError("analytic native integral requires top or bottom")
    k = np.asarray(wave_vector, dtype=np.complex128)
    J = np.asarray(jacobian, dtype=np.float64)
    x0 = np.asarray(origin, dtype=np.float64)
    if (
        k.shape != (3,) or J.shape != (3, 3) or x0.shape != (3,)
        or not np.isfinite(k).all() or not np.isfinite(J).all()
        or not np.isfinite(x0).all()
    ):
        raise ValueError("analytic native integral requires finite 3D wave/geometry vectors")
    if np.any(np.diag(J) <= 0) or np.linalg.norm(J - np.diag(np.diag(J))) > 1e-12:
        raise ValueError("analytic native integral requires positive axis-aligned geometry")
    cache = {} if moment_cache is None else moment_cache
    moments = []
    for axis in (0, 1):
        key = (
            axis, complex(k[axis]), float(x0[axis]), float(J[axis, axis]),
            int(polynomial.p), int(dps),
        )
        if key not in cache:
            cache[key] = np.asarray([
                complex(value)
                for value in legendre_exponential_moments(
                    k[axis], float(x0[axis]), float(J[axis, axis]),
                    polynomial.p, dps=dps,
                )
            ], dtype=np.complex128)
        moments.append(cache[key])
    integrated = np.einsum(
        "a,b,abjc->jc", moments[0], moments[1],
        polynomial.coefficients[side], optimize=True,
    ) * np.asarray([J[1, 1], J[0, 0]])
    z_origin = x0[2] + (J[2, 2] if side == "top" else 0.0)
    integrated *= np.exp(1j * k[2] * z_origin)
    return np.ascontiguousarray(integrated, dtype=np.complex128)


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
    saved_local_volume: dict[str, Any] | None = None,
    verify_analytic_full_rows: bool = False,
) -> dict[str, Any]:
    """Apply one real p4/p6 local condensed block over all ordered keys.

    ``Hp`` is the implicit identity. ``Hhat @ alpha`` and the affine internal
    RHS correction are streamed as ``alpha + Di solve(Bi alpha)`` and
    ``g + Di solve(fi)``; no mode-square object is created.
    """
    began = perf_counter()
    if side not in ("top", "bottom") or batch_modes < 1:
        raise ValueError("one physical port side and a positive mode batch are required")
    local = _local_tensor(
        degree, bounds, config, material_tag, saved_volume=saved_local_volume
    )
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
    analytic_moment_cache: dict[
        tuple[int, complex, float, float, int, int], np.ndarray
    ] = {}
    analytic_verified: set[int] = set()
    analytic_B_max_relative = 0.0
    analytic_D_max_relative = 0.0
    analytic_B_internal_max_abs_error = 0.0
    analytic_D_internal_max_abs_error = 0.0
    analytic_B_internal_max_over_full_scale = 0.0
    analytic_D_internal_max_over_full_scale = 0.0
    analytic_B_tiny_interior_nonzero = 0
    analytic_D_tiny_interior_nonzero = 0
    analytic_rows_digest = hashlib.sha256()

    def relative_without_new_floor(candidate: np.ndarray, reference: np.ndarray) -> float:
        error_norm = float(np.linalg.norm(candidate - reference))
        reference_norm = float(np.linalg.norm(reference))
        if reference_norm == 0.0:
            return 0.0 if error_norm == 0.0 else float("inf")
        return error_norm / reference_norm

    def native_mode_vectors(index: int) -> tuple[np.ndarray, np.ndarray]:
        nonlocal analytic_B_max_relative, analytic_D_max_relative
        nonlocal analytic_B_internal_max_abs_error, analytic_D_internal_max_abs_error
        nonlocal analytic_B_internal_max_over_full_scale, analytic_D_internal_max_over_full_scale
        nonlocal analytic_B_tiny_interior_nonzero, analytic_D_tiny_interior_nonzero
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
        if verify_analytic_full_rows and index not in analytic_verified:
            direct = analytic_full_basis_integral(
                polynomial, side, kv, jacobian, origin,
                moment_cache=analytic_moment_cache, dps=60,
            )
            direct_B = np.ascontiguousarray(direct @ (-traction))
            direct_D = np.ascontiguousarray((direct @ e).conj() / h)
            if local["dof_element"].needs_dof_transformations:
                local["dof_element"].T_apply(direct_B, local["cell_info"], 1)
                local["dof_element"].T_apply(direct_D, local["cell_info"], 1)
            analytic_B_max_relative = max(
                analytic_B_max_relative,
                relative_without_new_floor(b_native, direct_B),
            )
            analytic_D_max_relative = max(
                analytic_D_max_relative,
                relative_without_new_floor(d_native, direct_D),
            )
            b_full_norm = float(np.linalg.norm(direct_B))
            d_full_norm = float(np.linalg.norm(direct_D))
            analytic_B_internal_max_abs_error = max(
                analytic_B_internal_max_abs_error,
                float(np.max(np.abs(b_native[interior] - direct_B[interior]), initial=0.0)),
            )
            analytic_D_internal_max_abs_error = max(
                analytic_D_internal_max_abs_error,
                float(np.max(np.abs(d_native[interior] - direct_D[interior]), initial=0.0)),
            )
            if b_full_norm > 0:
                analytic_B_internal_max_over_full_scale = max(
                    analytic_B_internal_max_over_full_scale,
                    float(np.max(np.abs(b_native[interior] - direct_B[interior]), initial=0.0))
                    / b_full_norm,
                )
            if d_full_norm > 0:
                analytic_D_internal_max_over_full_scale = max(
                    analytic_D_internal_max_over_full_scale,
                    float(np.max(np.abs(d_native[interior] - direct_D[interior]), initial=0.0))
                    / d_full_norm,
                )
            analytic_B_tiny_interior_nonzero += int(
                np.count_nonzero((np.abs(direct_B[interior]) > 0)
                                 & (np.abs(direct_B[interior]) < 1e-12))
            )
            analytic_D_tiny_interior_nonzero += int(
                np.count_nonzero((np.abs(direct_D[interior]) > 0)
                                 & (np.abs(direct_D[interior]) < 1e-12))
            )
            analytic_rows_digest.update(np.asarray([index], dtype=np.int64).tobytes())
            for values in (b_native, direct_B, d_native, direct_D):
                analytic_rows_digest.update(np.ascontiguousarray(values).tobytes())
            analytic_verified.add(index)
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

    analytic_full_row_gate = bool(
        not verify_analytic_full_rows
        or (
            len(analytic_verified) == len(active_indices)
            and max(analytic_B_max_relative, analytic_D_max_relative) <= 1e-10
        )
    )
    if verify_analytic_full_rows and not analytic_full_row_gate:
        raise ValueError(
            "q60 B/D full native-row analytic reference gate failed: "
            f"mode_count={len(analytic_verified)}/{len(active_indices)}, "
            f"B_full_rel={analytic_B_max_relative:.17g}, "
            f"D_full_rel={analytic_D_max_relative:.17g}, "
            f"B_internal_max_abs={analytic_B_internal_max_abs_error:.17g}, "
            f"D_internal_max_abs={analytic_D_internal_max_abs_error:.17g}, "
            f"tiny_nonzero_B={analytic_B_tiny_interior_nonzero}, "
            f"tiny_nonzero_D={analytic_D_tiny_interior_nonzero}"
        )

    # Manufacture compatible loads from one known nonzero native state.
    # This makes the full interior/trace/port residuals meaningful gates.
    fi = Vii @ xi0 + Vit @ xt + Bi_alpha
    vit_trace_rhs = Vit @ xt
    recovery_rhs = fi - vit_trace_rhs - Bi_alpha
    solve_b_alpha, solve_b_alpha_facts = solve_local_rhs(
        Vii, local["factor"], Bi_alpha
    )
    solve_fi, solve_fi_facts = solve_local_rhs(Vii, local["factor"], fi)
    xi, solve_recovery_facts = solve_local_rhs(
        Vii,
        local["factor"],
        recovery_rhs,
        reference_solution=xi0,
    )
    solve_vit_trace, solve_vit_trace_facts = solve_local_rhs(
        Vii, local["factor"], vit_trace_rhs
    )
    solve_vit, solve_vit_facts = solve_local_rhs(Vii, local["factor"], Vit)
    recovery_rhs_facts = _local_rhs_roundoff_facts(
        Vii, Vit, xi0, xt, Bi_alpha, fi, recovery_rhs
    )
    condition_1_estimate = _local_condition_1_estimate(Vii, local["factor"])
    local_scale_facts = {
        "row_abs_max_spread": _local_entry_scale_spread(Vii, axis=1),
        "column_abs_max_spread": _local_entry_scale_spread(Vii, axis=0),
        "row_column_scaling_applied": False,
    }
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
    S_V = Vtt - Vti @ solve_vit
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
        "local_vii_factorization_count": int(local["factor"] is not None),
        "local_vii_factorization_scope": (
            "factor object created for this stream_boundary_correction call and reused by its local solves"
        ),
        "interior_factor_identity_relative": local["interior_factor_identity_relative"],
        "local_Hhat_materialized": False,
        "native_face_mapping": native_face,
        "internal_B_native_nonzero_entries_over_all_modes": internal_B_nonzero_entries,
        "internal_D_native_nonzero_entries_over_all_modes": internal_D_nonzero_entries,
        "max_abs_internal_B_native": max_abs_internal_B,
        "max_abs_internal_D_native": max_abs_internal_D,
        "analytic_full_row_crosscheck": {
            "status": (
                "PASS" if verify_analytic_full_rows and analytic_full_row_gate
                else "NOT_REQUESTED"
            ),
            "reference": "closed-form one-dimensional Legendre/exponential moments; deduplicated by frequency",
            "verified_mode_count": int(len(analytic_verified)),
            "expected_mode_count": int(len(active_indices)),
            "candidate_limit": 1e-10,
            "B_full_native_rows_max_relative": analytic_B_max_relative,
            "D_full_native_rows_max_relative": analytic_D_max_relative,
            "B_internal_rows_max_absolute_error": analytic_B_internal_max_abs_error,
            "D_internal_rows_max_absolute_error": analytic_D_internal_max_abs_error,
            "B_internal_max_absolute_error_over_full_reference_norm": analytic_B_internal_max_over_full_scale,
            "D_internal_max_absolute_error_over_full_reference_norm": analytic_D_internal_max_over_full_scale,
            "B_tiny_nonzero_internal_entries_below_1e-12": analytic_B_tiny_interior_nonzero,
            "D_tiny_nonzero_internal_entries_below_1e-12": analytic_D_tiny_interior_nonzero,
            "ordered_full_row_pair_digest_sha256": analytic_rows_digest.hexdigest(),
            "small_nonzero_rows_clipped": False,
        },
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
        "local_recovery_numerics": {
            "factor_scope": "existing one-cell Vii LU reused; no refactor in solve helper",
            "factor_condition_1_estimate": condition_1_estimate,
            "local_scale": local_scale_facts,
            "rhs_roundoff": recovery_rhs_facts,
            "same_factor_solve_facts": {
                "Bi_alpha": solve_b_alpha_facts,
                "fi": solve_fi_facts,
                "recovery_rhs": solve_recovery_facts,
                "Vit_xt": solve_vit_trace_facts,
                "Vit_block": solve_vit_facts,
            },
        },
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
            "recovery_solve_rhs": recovery_rhs,
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
