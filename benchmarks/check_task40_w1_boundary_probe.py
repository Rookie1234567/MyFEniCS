"""Independent saved-array checker for the bounded Task40 W1 probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODE_PATH = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json"
EXPECTED_MODE_SHA256 = "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d"
EXPECTED_KEYS_SHA256 = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"
EXPECTED_PHYSICAL_IDENTITY_SHA256 = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"
EXPECTED_INVENTORY_IDENTITY_SHA256 = "39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _numeric_hashes(arrays: dict[str, np.ndarray]) -> dict[str, str]:
    return {
        key: hashlib.sha256(np.ascontiguousarray(value).tobytes(order="C")).hexdigest()
        for key, value in sorted(arrays.items())
    }


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _load_frozen_modes() -> tuple[list[dict], dict]:
    digest = _file_sha256(MODE_PATH)
    if digest != EXPECTED_MODE_SHA256:
        raise ValueError("frozen mode manifest file hash changed")
    document = json.loads(MODE_PATH.read_text(encoding="utf-8"))
    rows = document.get("modes")
    if not isinstance(rows, list) or len(rows) != 32060:
        raise ValueError("frozen full ordered key count changed")
    keys = [[row["side"], row["m"], row["n"], row["polarization"]] for row in rows]
    key_hash = hashlib.sha256(
        json.dumps(keys, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if key_hash != EXPECTED_KEYS_SHA256:
        raise ValueError("frozen full ordered key digest changed")
    ledger_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/target_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    identity = {
        "target_physical_inventory_identity_sha256": ledger.get(
            "target_mode_physical_identity_sha256"
        ),
        "inventory_identity_sha256": ledger.get(
            "original_size_ordered_mode_inventory_identity_sha256"
        ),
    }
    if identity != {
        "target_physical_inventory_identity_sha256": EXPECTED_PHYSICAL_IDENTITY_SHA256,
        "inventory_identity_sha256": EXPECTED_INVENTORY_IDENTITY_SHA256,
    }:
        raise ValueError("target physical or inventory identity changed")
    return rows, {
        "mode_manifest_path": str(MODE_PATH.relative_to(ROOT)),
        "mode_manifest_bytes": MODE_PATH.stat().st_size,
        "mode_manifest_sha256": digest,
        "ordered_key_count": len(keys),
        "ordered_key_sha256": key_hash,
        "target_physical_inventory_identity_sha256": identity[
            "target_physical_inventory_identity_sha256"
        ],
        "side_counts": {side: sum(row["side"] == side for row in rows)
                        for side in ("top", "bottom")},
        "polarization_counts": {pol: sum(row["polarization"] == pol for row in rows)
                                for pol in ("s", "p")},
    }


def _need(arrays: dict[str, np.ndarray], name: str) -> np.ndarray:
    if name not in arrays:
        raise ValueError(f"raw arrays are missing {name}")
    value = np.asarray(arrays[name])
    if value.dtype.kind in "fc" and not np.isfinite(value).all():
        raise ValueError(f"raw array {name} contains nonfinite values")
    return value


def _relative(error: np.ndarray | float, *scales: np.ndarray | float) -> float:
    numerator = float(np.linalg.norm(error))
    denominator = max(
        *(float(np.linalg.norm(value)) for value in scales),
        np.finfo(float).tiny,
    )
    return numerator / denominator


def _direct_witness_check(arrays: dict[str, np.ndarray], prefix: str) -> dict:
    import basix
    import basix.ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI

    degree = int(prefix.split("_")[0][1:])
    side = prefix.split("_")[1]
    coordinates = _need(arrays, prefix + "local_cell_coordinates").astype(np.float64)
    if coordinates.shape != (8, 3):
        raise ValueError("saved direct witness coordinates must be the actual hexahedron vertices")
    lo, hi = coordinates.min(axis=0), coordinates.max(axis=0)
    msh = mesh.create_box(
        MPI.COMM_SELF,
        np.asarray([lo, hi], dtype=np.float64),
        [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    msh.topology.create_entity_permutations()
    ufl_element = basix.ufl.element("N1curl", "hexahedron", degree)
    V = fem.functionspace(msh, ufl_element)
    actual_cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    saved_cell_info = _need(arrays, prefix + "local_cell_orientation").astype(np.uint32)
    if not np.array_equal(actual_cell_info, saved_cell_info):
        raise ValueError("recreated one-cell orientation differs from saved native orientation")

    q = 30
    rule, weights = basix.make_quadrature(basix.CellType.quadrilateral, q)
    saved_rule = _need(arrays, prefix + "witness_direct_q30_rule_points")
    saved_weights = _need(arrays, prefix + "witness_direct_q30_rule_weights")
    if not np.array_equal(rule, saved_rule) or not np.array_equal(weights, saved_weights):
        raise ValueError("saved direct q30 quadrature rule differs from Basix")
    zref = 1.0 if side == "top" else 0.0
    reference_points = np.column_stack((rule, np.full(len(rule), zref)))
    full_basis = ufl_element.basix_element.tabulate(0, reference_points)[0][:, :, :2]
    physical_points = lo + reference_points * (hi - lo)
    k = _need(arrays, prefix + "witness_mode_k").astype(np.complex128)
    phase = np.exp(1j * (physical_points @ k))
    integrated = np.einsum(
        "q,q,qjc->jc", weights, phase, full_basis, optimize=True
    ) * np.asarray([(hi - lo)[1], (hi - lo)[0]])
    stored_integrated = _need(
        arrays, prefix + "witness_direct_q30_integrated_basis"
    )
    integral_rel = _relative(integrated - stored_integrated, integrated)
    e = _need(arrays, prefix + "witness_mode_e").astype(np.complex128)
    traction = _need(arrays, prefix + "witness_mode_traction").astype(np.complex128)
    h = float(_need(arrays, prefix + "witness_mode_projection_denominator"))
    B = np.ascontiguousarray(integrated @ (-traction))
    D = np.ascontiguousarray((integrated @ e).conj() / h)
    if V.element.needs_dof_transformations:
        V.element.T_apply(B, saved_cell_info, 1)
        V.element.T_apply(D, saved_cell_info, 1)
    b_rel = _relative(B - _need(arrays, prefix + "witness_candidate_B_native"), B)
    d_rel = _relative(D - _need(arrays, prefix + "witness_candidate_D_native"), D)
    direct_raw_b_rel = _relative(B - _need(arrays, prefix + "witness_direct_q30_B_native"), B)
    direct_raw_d_rel = _relative(D - _need(arrays, prefix + "witness_direct_q30_D_native"), D)
    return {
        "integrated_basis_relative_to_saved_direct_raw": integral_rel,
        "full_dof_B_candidate_relative": b_rel,
        "full_dof_D_candidate_relative": d_rel,
        "full_dof_B_saved_oracle_relative": direct_raw_b_rel,
        "full_dof_D_saved_oracle_relative": direct_raw_d_rel,
        "pass": max(integral_rel, b_rel, d_rel, direct_raw_b_rel, direct_raw_d_rel) <= 1e-10,
    }


def _v10_local_algebra_check(
    arrays: dict[str, np.ndarray], prefix: str, case: dict, expected_modes: int
) -> dict:
    """Recompute the compact local equations and verify streamed B/D row coverage."""
    A = _need(arrays, prefix + "local_native_tensor")
    ii = _need(arrays, prefix + "interior_positions").astype(np.int64)
    tt = _need(arrays, prefix + "trace_positions").astype(np.int64)
    if (
        len(np.unique(np.r_[ii, tt])) != A.shape[0]
        or not np.array_equal(np.sort(np.r_[ii, tt]), np.arange(A.shape[0]))
    ):
        raise ValueError(f"{prefix}: local interior/trace rows do not partition the native tensor")
    Vii, Vit = A[np.ix_(ii, ii)], A[np.ix_(ii, tt)]
    Vti, Vtt = A[np.ix_(tt, ii)], A[np.ix_(tt, tt)]
    xi = _need(arrays, prefix + "recovered_interior")
    fi = _need(arrays, prefix + "interior_rhs")
    xt = _need(arrays, prefix + "trace_values")
    ft = _need(arrays, prefix + "trace_rhs")
    xi0 = _need(arrays, prefix + "known_interior_solution")
    bi = _need(arrays, prefix + "Bi_alpha")
    bt = _need(arrays, prefix + "Bt_alpha")
    interior_rhs = Vii @ xi0 + Vit @ xt + bi
    rhs_relative = _relative(fi - interior_rhs, Vii @ xi0, Vit @ xt, bi, fi)
    direct_xi = np.linalg.solve(Vii, fi - Vit @ xt - bi)
    interior_relative = _relative(
        Vii @ xi + Vit @ xt + bi - fi, Vii @ xi, Vit @ xt, bi, fi
    )
    recovery_relative = _relative(xi - direct_xi, direct_xi)
    state_relative = _relative(xi - xi0, xi0)
    solve_b = np.linalg.solve(Vii, bi)
    solve_f = np.linalg.solve(Vii, fi)
    schur = Vtt - Vti @ np.linalg.solve(Vii, Vit)
    original_trace = Vti @ xi + Vtt @ xt + bt - ft
    reduced_trace = schur @ xt + (bt - Vti @ solve_b) - (ft - Vti @ solve_f)
    trace_relative = _relative(original_trace - reduced_trace,
                               Vti @ xi, Vtt @ xt, bt, ft,
                               schur @ xt, bt - Vti @ solve_b, ft - Vti @ solve_f)
    alpha = _need(arrays, prefix + "mode_alpha")
    port_rhs = _need(arrays, prefix + "port_rhs")
    internal_b = _need(arrays, prefix + "port_internal_B_correction")
    internal_f = _need(arrays, prefix + "port_internal_rhs_correction")
    internal_x = _need(arrays, prefix + "port_internal_recovered_correction")
    internal_trace = _need(arrays, prefix + "port_internal_trace_correction")
    trace_action = _need(arrays, prefix + "port_trace_action")
    qhat = alpha + internal_b
    affine = port_rhs + internal_f
    original_port = alpha - port_rhs - internal_x - trace_action
    reduced_port = qhat - affine - trace_action + internal_trace
    port_relative = _relative(original_port - reduced_port,
                              alpha, port_rhs, internal_x, trace_action,
                              qhat, affine, internal_trace)
    row_check = case.get("analytic_full_row_crosscheck", {})
    row_gate = bool(
        row_check.get("status") == "PASS"
        and row_check.get("verified_mode_count") == expected_modes
        and row_check.get("expected_mode_count") == expected_modes
        and max(
            float(row_check.get("B_full_native_rows_max_relative", float("inf"))),
            float(row_check.get("D_full_native_rows_max_relative", float("inf"))),
        ) <= 1e-10
        and row_check.get("small_nonzero_rows_clipped") is False
        and np.isfinite(float(row_check.get("B_internal_rows_max_absolute_error", float("nan"))))
        and np.isfinite(float(row_check.get("D_internal_rows_max_absolute_error", float("nan"))))
        and len(str(row_check.get("ordered_full_row_pair_digest_sha256", ""))) == 64
    )
    limits_pass = bool(
        rhs_relative <= 1e-12
        and interior_relative <= 1e-11
        and recovery_relative <= 1e-11
        and state_relative <= 1e-11
        and trace_relative <= 1e-10
        and port_relative <= 1e-10
        and len(alpha) == expected_modes
        and np.linalg.norm(fi) > 0
        and np.linalg.norm(ft) > 0
        and np.linalg.norm(port_rhs) > 0
        and np.linalg.norm(alpha) > 0
        and row_gate
    )
    return {
        "interior_rhs_recomputed_relative": rhs_relative,
        "interior_equation_recomputed_relative": interior_relative,
        "direct_recovery_recomputed_relative": recovery_relative,
        "known_state_recomputed_relative": state_relative,
        "trace_elimination_recomputed_relative": trace_relative,
        "port_elimination_recomputed_relative": port_relative,
        "full_native_B_D_row_check": row_check,
        "pass": limits_pass,
    }


def _recompute_v10_full_BD_rows(
    arrays: dict[str, np.ndarray],
    prefix: str,
    modes: list[dict],
    *,
    degree: int,
    side: str,
) -> dict:
    """Chunk-recompute q60 and analytic B/D over every native row and mode key."""
    import basix
    import basix.ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI
    from src.solvers.directional_boundary import FacetPolynomial
    from src.solvers.task40_w1_moment_reference import (
        legendre_exponential_moment_table,
        quadrature_legendre_exponential_moments,
    )

    coordinates = _need(arrays, prefix + "local_cell_coordinates").astype(np.float64)
    saved_cell_info = _need(arrays, prefix + "local_cell_orientation").astype(np.uint32)
    lo, hi = coordinates.min(axis=0), coordinates.max(axis=0)
    msh = mesh.create_box(
        MPI.COMM_SELF, np.asarray([lo, hi]), [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    msh.topology.create_entity_permutations()
    element = basix.ufl.element("N1curl", "hexahedron", degree)
    V = fem.functionspace(msh, element)
    cell_info = np.asarray(msh.topology.get_cell_permutation_info(), dtype=np.uint32)
    if not np.array_equal(cell_info, saved_cell_info):
        raise ValueError("V10 full B/D checker native orientation changed")
    polynomial = FacetPolynomial(element.basix_element)
    J = np.diag(hi - lo)
    origin = lo.copy()
    interior = np.asarray(element.basix_element.entity_dofs[3][0], dtype=np.int64)
    x_q_cache: dict[complex, np.ndarray] = {}
    y_q_cache: dict[complex, np.ndarray] = {}
    x_a_cache: dict[complex, np.ndarray] = {}
    y_a_cache: dict[complex, np.ndarray] = {}
    max_B_relative = max_D_relative = 0.0
    max_B_internal_abs = max_D_internal_abs = 0.0
    max_B_internal_over_full = max_D_internal_over_full = 0.0
    tiny_B = tiny_D = 0
    checked = 0
    digest = hashlib.sha256()

    def moments(cache_q, cache_a, axis, wave):
        key = complex(wave)
        if key not in cache_q:
            origin_axis = float(origin[axis])
            length_axis = float(J[axis, axis])
            cache_q[key] = np.asarray(
                quadrature_legendre_exponential_moments(
                    key, origin_axis, length_axis, degree, quadrature_degree=60
                ), dtype=np.complex128,
            )
            cache_a[key] = legendre_exponential_moment_table(
                key, np.asarray([origin_axis]), np.asarray([length_axis]), degree
            )[0]
        return cache_q[key], cache_a[key]

    for index, mode in enumerate(modes):
        if mode["side"] != side:
            continue
        k = np.asarray([complex(v["real"], v["imag"]) if isinstance(v, dict) else complex(v)
                        for v in mode["k_vector"]], dtype=np.complex128)
        qx, ax = moments(x_q_cache, x_a_cache, 0, k[0])
        qy, ay = moments(y_q_cache, y_a_cache, 1, k[1])
        z = origin[2] + (J[2, 2] if side == "top" else 0.0)
        phase = np.exp(1j * k[2] * z)
        factor = np.asarray([J[1, 1], J[0, 0]])
        candidate_integral = np.einsum(
            "a,b,abjc->jc", qx, qy, polynomial.coefficients[side], optimize=True
        ) * factor * phase
        reference_integral = np.einsum(
            "a,b,abjc->jc", ax, ay, polynomial.coefficients[side], optimize=True
        ) * factor * phase
        e = np.asarray([complex(v["real"], v["imag"]) if isinstance(v, dict) else complex(v)
                        for v in mode["e_vector"][:2]], dtype=np.complex128)
        traction = np.asarray([
            complex(v["real"], v["imag"]) if isinstance(v, dict) else complex(v)
            for v in mode["traction_vector"][:2]
        ], dtype=np.complex128)
        h = float(mode["projection_denominator"])
        candidate_B = np.ascontiguousarray(candidate_integral @ (-traction))
        candidate_D = np.ascontiguousarray((candidate_integral @ e).conj() / h)
        reference_B = np.ascontiguousarray(reference_integral @ (-traction))
        reference_D = np.ascontiguousarray((reference_integral @ e).conj() / h)
        if V.element.needs_dof_transformations:
            for vector in (candidate_B, candidate_D, reference_B, reference_D):
                V.element.T_apply(vector, cell_info, 1)
        for candidate, reference_vector, kind in (
            (candidate_B, reference_B, "B"), (candidate_D, reference_D, "D")
        ):
            delta = candidate - reference_vector
            denominator = float(np.linalg.norm(reference_vector))
            error = float(np.linalg.norm(delta))
            relative = (error / denominator) if denominator > 0 else (0.0 if error == 0 else float("inf"))
            internal_abs = float(np.max(np.abs(delta[interior]), initial=0.0))
            internal_full = internal_abs / denominator if denominator > 0 else (0.0 if internal_abs == 0 else float("inf"))
            if kind == "B":
                max_B_relative = max(max_B_relative, relative)
                max_B_internal_abs = max(max_B_internal_abs, internal_abs)
                max_B_internal_over_full = max(max_B_internal_over_full, internal_full)
                tiny_B += int(np.count_nonzero((np.abs(reference_vector[interior]) > 0)
                                               & (np.abs(reference_vector[interior]) < 1e-12)))
            else:
                max_D_relative = max(max_D_relative, relative)
                max_D_internal_abs = max(max_D_internal_abs, internal_abs)
                max_D_internal_over_full = max(max_D_internal_over_full, internal_full)
                tiny_D += int(np.count_nonzero((np.abs(reference_vector[interior]) > 0)
                                               & (np.abs(reference_vector[interior]) < 1e-12)))
        digest.update(np.asarray([index], dtype=np.int64).tobytes())
        for vector in (candidate_B, reference_B, candidate_D, reference_D):
            digest.update(np.ascontiguousarray(vector).tobytes())
        checked += 1
    return {
        "mode_count": checked,
        "expected_mode_count": sum(mode["side"] == side for mode in modes),
        "q60_vs_analytic_B_full_rows_max_relative": max_B_relative,
        "q60_vs_analytic_D_full_rows_max_relative": max_D_relative,
        "tiny_B_internal_rows_max_absolute_error": max_B_internal_abs,
        "tiny_D_internal_rows_max_absolute_error": max_D_internal_abs,
        "tiny_B_internal_max_absolute_over_full_row_norm": max_B_internal_over_full,
        "tiny_D_internal_max_absolute_over_full_row_norm": max_D_internal_over_full,
        "tiny_nonzero_B_entries_below_1e-12": tiny_B,
        "tiny_nonzero_D_entries_below_1e-12": tiny_D,
        "all_native_rows_including_tiny_nonzero_checked": True,
        "clipped_or_dropped_rows": False,
        "checker_ordered_row_digest_sha256": digest.hexdigest(),
        "pass": bool(checked == sum(mode["side"] == side for mode in modes)
                     and max(max_B_relative, max_D_relative) <= 1e-10),
    }


def check_v10_saved_array_extension(output: Path, report_path: Path | None = None) -> dict:
    """Independent V10 checker for the saved-array q60 and local-object extension."""
    from src.solvers.directional_boundary import (
        BoundaryLayout, DirectionalBoundaryAction, FacetPolynomial,
    )
    from src.solvers.task40_w1_local_probe import direct_single_face_projection
    from src.solvers.task40_w1_moment_reference import (
        AnalyticMomentBoundaryReference,
        legendre_exponential_moments,
        legendre_exponential_moment_table,
        quadrature_legendre_exponential_moments,
        segmented_legendre_exponential_moments,
    )
    import basix.ufl

    output = Path(output).resolve()
    report_path = report_path or output / "w1_v10_a_extension_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "task40extra.review_v10_w1_a_saved_array_extension.v1":
        raise ValueError("unsupported V10 W1 extension report schema")
    arrays_meta = report.get("arrays", {})
    arrays_path = (ROOT / arrays_meta.get("path", "")).resolve()
    if (
        not arrays_path.is_file()
        or _file_sha256(arrays_path) != arrays_meta.get("file_sha256")
        or arrays_path.stat().st_size != arrays_meta.get("file_bytes")
    ):
        raise ValueError("V10 W1 extension raw archive identity mismatch")
    with np.load(arrays_path, allow_pickle=False) as stream:
        arrays = {key: stream[key] for key in stream.files}
    if _numeric_hashes(arrays) != arrays_meta.get("member_numeric_sha256"):
        raise ValueError("V10 W1 extension raw member hashes mismatch")
    raw_path = ROOT / report["saved_w1_raw"]["path"]
    reference_path = ROOT / report["saved_v9_reference"]["path"]
    if (
        _file_sha256(raw_path) != report["saved_w1_raw"]["sha256"]
        or _file_sha256(reference_path) != report["saved_v9_reference"]["sha256"]
    ):
        raise ValueError("V10 W1 saved source arrays no longer match the report identity")
    with np.load(raw_path, allow_pickle=False) as stream:
        frozen = {key: stream[key] for key in stream.files}
    with np.load(reference_path, allow_pickle=False) as stream:
        reference_arrays = {key: stream[key] for key in stream.files}
    modes_raw, identity = _load_frozen_modes()
    if identity != report.get("input_inventory"):
        raise ValueError("V10 extension ordered mode identity differs")
    reference_planes = {"bottom": -10.0, "top": 130.0}
    modes = [{
        "side": row["side"], "k_vector": row["k_vector"],
        "e_vector": row["e_vector"], "traction_vector": row["traction_vector"],
        "reference_plane_nm": reference_planes[row["side"]],
        "projection_denominator": row["projection_denominator"],
        "mode_index": row["mode_index"], "m": row["m"], "n": row["n"],
        "polarization": row["polarization"],
    } for row in modes_raw]
    x = np.asarray(frozen["surface_x_axis_nm"], dtype=np.float64)
    y = np.asarray(frozen["surface_y_axis_nm"], dtype=np.float64)
    phases = tuple(complex(v) for v in frozen["floquet_phases"])
    representative_face = tuple(int(v) for v in frozen["representative_face_indices"][0])
    faces = [("top", *representative_face), ("bottom", *representative_face)]
    layout = BoundaryLayout(x, y, FacetPolynomial(
        basix.ufl.element("N1curl", "hexahedron", 6).basix_element
    ), phases)
    trace = _need(arrays, "generic_trace").astype(np.complex128)
    alpha = _need(arrays, "generic_alpha").astype(np.complex128)
    action = DirectionalBoundaryAction(layout, modes, 60, face_inventory=faces)
    analytic = AnalyticMomentBoundaryReference(layout, modes, face_inventory=faces)
    candidate_components = action.project_components(trace)
    reference_components = analytic.project_components(trace)
    candidate_apply = action.apply(trace)
    reference_apply = analytic.apply(trace)
    candidate_port = action.modal_rhs(alpha)
    reference_port = analytic.modal_rhs(alpha)
    candidate_scatter = action.scatter_components(candidate_components)
    reference_scatter = analytic.scatter_components(candidate_components)
    frozen_mode_scale = np.linalg.norm(frozen["q60_components"], axis=1) / np.abs(frozen["denominators"])
    mode_error = (
        np.linalg.norm(candidate_components - reference_components, axis=1)
        / np.abs(frozen["denominators"])
        / frozen_mode_scale
    )
    frozen_action_norm = float(np.linalg.norm(frozen["q60_apply"]))
    full_error = float(np.linalg.norm(candidate_apply - reference_apply) / frozen_action_norm)
    port_error = float(np.linalg.norm(candidate_port - reference_port) / np.linalg.norm(reference_port))
    scatter_error = float(np.linalg.norm(candidate_scatter - reference_scatter) / np.linalg.norm(reference_scatter))
    stored_errors = {
        "generic_components": _relative(candidate_components - _need(arrays, "generic_q60_components"), candidate_components),
        "generic_apply": _relative(candidate_apply - _need(arrays, "generic_q60_apply"), candidate_apply),
        "generic_port_rhs": _relative(candidate_port - _need(arrays, "generic_q60_port_rhs"), candidate_port),
        "generic_scatter": _relative(candidate_scatter - _need(arrays, "generic_q60_scatter"), candidate_scatter),
        "analytic_components": _relative(reference_components - _need(arrays, "generic_analytic_reference_components"), reference_components),
        "analytic_apply": _relative(reference_apply - _need(arrays, "generic_analytic_reference_apply"), reference_apply),
        "analytic_port_rhs": _relative(reference_port - _need(arrays, "generic_analytic_reference_port_rhs"), reference_port),
        "analytic_scatter": _relative(reference_scatter - _need(arrays, "generic_analytic_reference_scatter"), reference_scatter),
    }
    frozen_e = np.asarray([[complex(v["real"], v["imag"]) if isinstance(v, dict) else complex(v)
                            for v in row["e_vector"][:2]] for row in modes])
    frozen_h = np.asarray(frozen["denominators"], dtype=np.float64)
    saved_reference_recover = np.sum(
        frozen_e.conj() * reference_arrays["reference_components_80"], axis=1
    ) / frozen_h
    frozen_per_mode = np.abs(frozen["q60_recover"] - saved_reference_recover) / frozen_mode_scale
    frozen_full_error = float(
        np.linalg.norm(frozen["q60_apply"] - reference_arrays["reference_action_80"])
        / frozen_action_norm
    )
    witness = report.get("q60_finite_witness", {})
    q60_metrics = {
        "generic_max_per_mode_over_frozen_scale": float(np.max(mode_error)),
        "generic_full_action_over_saved_q60_apply_norm": full_error,
        "generic_port_rhs_relative": port_error,
        "generic_scatter_relative": scatter_error,
        "frozen_q60_max_per_mode_relative": float(np.max(frozen_per_mode)),
        "frozen_q60_full_action_relative": frozen_full_error,
        "stored_array_reconstruction": stored_errors,
        "pass": bool(
            np.max(mode_error) <= 1e-10 and full_error <= 1e-10
            and port_error <= 1e-10 and scatter_error <= 1e-10
            and np.max(frozen_per_mode) <= 1e-10 and frozen_full_error <= 1e-10
            and max(stored_errors.values()) <= 1e-12
        ),
    }
    moment_checks = []
    for item in witness.get("moment_witnesses", []):
        index = int(item["mode_index"])
        mode = modes[index]
        for axis_index, axis_label, coords, cell_index in (
            (0, "x", x, representative_face[0]),
            (1, "y", y, representative_face[1]),
        ):
            raw_k = mode["k_vector"][axis_index]
            mode_k = (
                complex(raw_k["real"], raw_k["imag"])
                if isinstance(raw_k, dict) else complex(raw_k)
            )
            k = -np.conj(mode_k)
            origin, length = float(coords[cell_index]), float(np.diff(coords)[cell_index])
            q60 = np.asarray(quadrature_legendre_exponential_moments(
                k, origin, length, 6, quadrature_degree=60
            ), dtype=np.complex128)
            analytic_mp = np.asarray([complex(v) for v in legendre_exponential_moments(
                k, origin, length, 6, dps=80
            )], dtype=np.complex128)
            scipy_table = legendre_exponential_moment_table(
                k, np.asarray([origin]), np.asarray([length]), 6
            )[0]
            direct_mp = np.asarray([complex(v) for v in segmented_legendre_exponential_moments(
                k, origin, length, 6, dps=100, segments=5
            )], dtype=np.complex128)
            scale = float(np.linalg.norm(direct_mp))
            q_error = float(np.linalg.norm(q60 - direct_mp) / scale)
            scipy_error = float(np.linalg.norm(scipy_table - direct_mp) / scale)
            mp_error = float(np.linalg.norm(analytic_mp - direct_mp) / scale)
            moment_checks.append({"mode_index": index, "axis": axis_label,
                                  "candidate_relative": q_error,
                                  "scipy_analytic_relative": scipy_error,
                                  "mpmath_closed_form_relative": mp_error})
    direct_panel_checks = []
    for item in witness.get("direct_panel_witnesses", []):
        index = int(item["mode_index"])
        direct = direct_single_face_projection(
            layout, modes[index], trace, 60, *representative_face
        )
        scale = float(np.linalg.norm(direct))
        error = float(np.linalg.norm(candidate_components[index] - direct) / scale)
        direct_panel_checks.append({"mode_index": index, "relative": error})

    local_results = []
    for case in report.get("local_cases", []):
        degree, side = int(case["degree"]), str(case["side"])
        if case.get("case_status") != "PASS":
            local_results.append({
                "degree": degree, "side": side,
                "recomputed": {"pass": False, "classification": case.get("case_status")},
            })
            continue
        prefix = f"p{degree}_q60_{side}_"
        expected = 16030
        recomputed = _v10_local_algebra_check(arrays, prefix, case, expected)
        full_rows = _recompute_v10_full_BD_rows(
            arrays, prefix, modes, degree=degree, side=side
        )
        recomputed["full_native_row_recomputation"] = full_rows
        recomputed["pass"] = bool(recomputed["pass"] and full_rows["pass"])
        local_results.append({"degree": degree, "side": side, "recomputed": recomputed})
    source_hash_check = {
        relative: _file_sha256(ROOT / relative) == expected
        for relative, expected in report.get("source_files_sha256", {}).items()
    }
    complete = len(local_results) == 4
    independent_reference_max = max(
        (item["scipy_analytic_relative"] for item in moment_checks),
        default=float("inf"),
    )
    high_precision_reference_max = max(
        (item["mpmath_closed_form_relative"] for item in moment_checks),
        default=float("inf"),
    )
    candidate_moment_max = max(
        (item["candidate_relative"] for item in moment_checks), default=float("inf")
    )
    panel_max = max((item["relative"] for item in direct_panel_checks), default=float("inf"))
    pass_all = bool(
        q60_metrics["pass"]
        and independent_reference_max <= 1e-12
        and high_precision_reference_max <= 1e-12
        and candidate_moment_max <= 1e-10
        and panel_max <= 1e-10
        and all(row["recomputed"]["pass"] for row in local_results)
        and all(source_hash_check.values())
        and report.get("status") == "PASS_FINITE_A_COMPONENTS"
        and complete
    )
    result = {
        "schema": "task40extra.review_v10_w1_a_saved_array_checker.v1",
        "status": "SAVED_ARRAYS_CHECK_PASS" if pass_all else "SAVED_ARRAYS_PARTIAL_OR_CONTROLLED_NEGATIVE",
        "pass": pass_all,
        "report_sha256": _file_sha256(report_path),
        "arrays_file_sha256": arrays_meta["file_sha256"],
        "input_identity_recomputed": identity,
        "q60_full_generic_recomputation": q60_metrics,
        "q60_moment_witnesses_recomputed": moment_checks,
        "q60_direct_panel_witnesses_recomputed": direct_panel_checks,
        "independent_reference_cross_error_max": independent_reference_max,
        "candidate_cross_error_max": max(candidate_moment_max, panel_max),
        "local_case_recomputations": local_results,
        "source_hash_check": source_hash_check,
        "p4_volume_reused": report.get("p4_volume_reused") is True,
        "global_target_mpc_mapping": "NOT_RUN",
    }
    _atomic_json(output / "w1_v10_a_extension_checker.json", result)
    return result


def check(output: Path, report_path: Path | None = None) -> dict:
    output = Path(output).resolve()
    if report_path is None and (output / "w1_v10_a_extension_report.json").is_file():
        report_path = output / "w1_v10_a_extension_report.json"
    report_path = report_path or output / "w1_boundary_probe_report.json"
    if not report_path.is_file():
        report_path = output / "w1_boundary_probe_progress.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") == "task40extra.review_v10_w1_a_saved_array_extension.v1":
        return check_v10_saved_array_extension(output, report_path)
    raw_meta = report.get("raw")
    if not isinstance(raw_meta, dict) or raw_meta.get("reopened_after_fsync") is not True:
        raise ValueError("saved raw array fsync/readback evidence is absent")
    arrays_path = (ROOT / raw_meta["path"]).resolve()
    if _file_sha256(arrays_path) != raw_meta.get("file_sha256"):
        raise ValueError("saved NPZ file SHA256 mismatch")
    if arrays_path.stat().st_size != raw_meta.get("file_bytes"):
        raise ValueError("saved NPZ byte size mismatch")
    with np.load(arrays_path, allow_pickle=False) as stream:
        arrays = {key: stream[key] for key in stream.files}
    member_hashes = _numeric_hashes(arrays)
    if member_hashes != raw_meta.get("member_numeric_sha256"):
        raise ValueError("saved NPZ numeric member hashes mismatch")

    modes, input_identity = _load_frozen_modes()
    if input_identity != report.get("input_inventory"):
        raise ValueError("report does not bind the current frozen ordered mode inventory")
    keys_match = (
        np.array_equal(_need(arrays, "mode_index"), np.asarray([row["mode_index"] for row in modes]))
        and np.array_equal(_need(arrays, "m"), np.asarray([row["m"] for row in modes]))
        and np.array_equal(_need(arrays, "n"), np.asarray([row["n"] for row in modes]))
        and np.array_equal(_need(arrays, "side"), np.asarray([row["side"] for row in modes], dtype="U6"))
        and np.array_equal(_need(arrays, "polarization"), np.asarray([row["polarization"] for row in modes], dtype="U1"))
    )
    if not keys_match:
        raise ValueError("saved mode vectors are not in the frozen ordered key sequence")

    e = np.asarray([[complex(v["real"], v["imag"]) if isinstance(v, dict) else complex(v)
                     for v in row["e_vector"][:2]] for row in modes])
    h = np.asarray([row["projection_denominator"] for row in modes], dtype=np.float64)
    q30_recover = np.sum(e.conj() * _need(arrays, "q30_components"), axis=1) / h
    q60_recover = np.sum(e.conj() * _need(arrays, "q60_components"), axis=1) / h
    recover30_rel = _relative(q30_recover - _need(arrays, "q30_recover"), q30_recover)
    recover60_rel = _relative(q60_recover - _need(arrays, "q60_recover"), q60_recover)
    q60_components = _need(arrays, "q60_components")
    scale = np.maximum(np.linalg.norm(q60_components, axis=1) / h, np.finfo(float).tiny)
    per_mode = np.abs(q30_recover - q60_recover) / scale
    component_delta = np.linalg.norm(
        _need(arrays, "q30_components") - q60_components, axis=1
    ) / h
    worst = int(np.argmax(per_mode))
    action_rel = _relative(
        _need(arrays, "q30_apply") - _need(arrays, "q60_apply"),
        _need(arrays, "q60_apply"),
    )
    dual, trace = _need(arrays, "dual"), _need(arrays, "trace")
    dot_left = np.vdot(dual, _need(arrays, "q30_apply"))
    dot_right = np.vdot(_need(arrays, "q30_adjoint"), trace)
    adjoint_rel = abs(dot_left - dot_right) / max(abs(dot_left), abs(dot_right), np.finfo(float).tiny)
    q30_rhs_norm = float(np.linalg.norm(_need(arrays, "q30_modal_rhs")))
    boundary_pass = bool(
        max(recover30_rel, recover60_rel) <= 1e-12
        and float(np.max(per_mode)) <= 1e-10
        and adjoint_rel <= 1e-10
        and q30_rhs_norm > 0
    )
    worker_boundary = report.get("q30_q60", {})
    boundary = {
        "q30_recover_reconstruction_relative": recover30_rel,
        "q60_recover_reconstruction_relative": recover60_rel,
        "maximum_relative_q30_q60_difference": float(per_mode[worst]),
        "maximum_component_delta_over_original_denominator": float(np.max(component_delta)),
        "worst_mode_index": worst,
        "worst_key": [modes[worst]["side"], modes[worst]["m"], modes[worst]["n"], modes[worst]["polarization"]],
        "full_action_relative_difference": action_rel,
        "adjoint_bilinear_relative": float(adjoint_rel),
        "q30_modal_rhs_norm": q30_rhs_norm,
        "pass": boundary_pass,
        "worker_claim_agrees": bool(
            worker_boundary.get("boundary_gate_pass") == boundary_pass
            and abs(float(worker_boundary.get("maximum_relative_error", float("inf"))) - float(per_mode[worst]))
            <= 1e-12 * max(1.0, float(per_mode[worst]))
            and abs(float(worker_boundary.get(
                "maximum_component_delta_over_original_denominator", float("inf")
            )) - float(np.max(component_delta)))
            <= 1e-12 * max(1.0, float(np.max(component_delta)))
        ),
    }

    cases = report.get("original_size_local_internal_correction", {}).get(
        "cases", report.get("completed_local_cases", [])
    )
    if not cases:
        cases = report.get("completed_local_cases", [])
    local_results = []
    for case in cases:
        degree, side = int(case["degree"]), str(case["side"])
        prefix = f"p{degree}_{side}_"
        if case.get("case_status") == "FAILED_LOCAL_PROBE":
            local_results.append({"degree": degree, "side": side, "pass": False,
                                  "classification": "FAILED_LOCAL_PROBE",
                                  "error": case.get("error")})
            continue
        A = _need(arrays, prefix + "local_native_tensor")
        ii = _need(arrays, prefix + "interior_positions").astype(np.int64)
        tt = _need(arrays, prefix + "trace_positions").astype(np.int64)
        if len(np.unique(np.r_[ii, tt])) != A.shape[0] or not np.array_equal(np.sort(np.r_[ii, tt]), np.arange(A.shape[0])):
            raise ValueError(f"p{degree}_{side}: local interior/trace rows do not partition the native tensor")
        Vii, Vit = A[np.ix_(ii, ii)], A[np.ix_(ii, tt)]
        Vti, Vtt = A[np.ix_(tt, ii)], A[np.ix_(tt, tt)]
        xi = _need(arrays, prefix + "recovered_interior")
        fi = _need(arrays, prefix + "interior_rhs")
        xt = _need(arrays, prefix + "trace_values")
        ft = _need(arrays, prefix + "trace_rhs")
        xi0 = _need(arrays, prefix + "known_interior_solution")
        bi = _need(arrays, prefix + "Bi_alpha")
        bt = _need(arrays, prefix + "Bt_alpha")
        fi_from_state = Vii @ xi0 + Vit @ xt + bi
        fi_manufacture_rel = _relative(fi - fi_from_state, Vii @ xi0, Vit @ xt, bi, fi)
        direct_xi = np.linalg.solve(Vii, fi - Vit @ xt - bi)
        interior_rel = _relative(Vii @ xi + Vit @ xt + bi - fi, Vii @ xi, Vit @ xt, bi, fi)
        xi_rel = _relative(xi - direct_xi, direct_xi)
        known_state_rel = _relative(xi - xi0, xi0)
        solve_b = np.linalg.solve(Vii, bi)
        solve_f = np.linalg.solve(Vii, fi)
        schur = Vtt - Vti @ np.linalg.solve(Vii, Vit)
        original_trace = Vti @ xi + Vtt @ xt + bt - ft
        ft_from_state = Vti @ xi0 + Vtt @ xt + bt
        ft_manufacture_rel = _relative(ft - ft_from_state, Vti @ xi0, Vtt @ xt, bt, ft)
        reduced_trace = schur @ xt + (bt - Vti @ solve_b) - (ft - Vti @ solve_f)
        original_trace_rel = _relative(original_trace, Vti @ xi, Vtt @ xt, bt, ft)
        reduced_trace_rel = _relative(
            reduced_trace, schur @ xt, bt - Vti @ solve_b, ft - Vti @ solve_f
        )
        trace_identity_rel = _relative(
            original_trace - reduced_trace,
            Vti @ xi, Vtt @ xt, bt, ft, schur @ xt,
            bt - Vti @ solve_b, ft - Vti @ solve_f,
        )

        alpha = _need(arrays, prefix + "mode_alpha")
        port_rhs = _need(arrays, prefix + "port_rhs")
        internal_b = _need(arrays, prefix + "port_internal_B_correction")
        internal_f = _need(arrays, prefix + "port_internal_rhs_correction")
        internal_x = _need(arrays, prefix + "port_internal_recovered_correction")
        manufactured_internal = _need(arrays, prefix + "port_manufactured_internal_term")
        trace_action = _need(arrays, prefix + "port_trace_action")
        internal_trace = _need(arrays, prefix + "port_internal_trace_correction")
        qhat = alpha + internal_b
        affine = port_rhs + internal_f
        port_rhs_from_state = alpha - manufactured_internal - trace_action
        port_rhs_manufacture_rel = _relative(
            port_rhs - port_rhs_from_state, alpha, manufactured_internal, trace_action
        )
        original_port = alpha - port_rhs - internal_x - trace_action
        reduced_port = qhat - affine - trace_action + internal_trace
        original_port_scale = (alpha, port_rhs, internal_x, trace_action)
        reduced_port_scale = (qhat, affine, trace_action, internal_trace)
        original_port_equation_rel = _relative(original_port, *original_port_scale)
        reduced_port_equation_rel = _relative(reduced_port, *reduced_port_scale)
        original_port_reconstruction_rel = _relative(
            original_port - _need(arrays, prefix + "port_residual"), *original_port_scale
        )
        reduced_port_reconstruction_rel = _relative(
            reduced_port - _need(arrays, prefix + "reduced_port_residual"), *reduced_port_scale
        )
        port_identity_rel = _relative(
            original_port - reduced_port, *original_port_scale, *reduced_port_scale
        )
        nonzero_rhs = bool(
            np.linalg.norm(fi) > 0 and np.linalg.norm(ft) > 0
            and np.linalg.norm(port_rhs) > 0 and np.linalg.norm(alpha) > 0
        )
        direct_witness = _direct_witness_check(arrays, prefix)
        worker_oracle = case.get("small_key_native_carrier_witness", {})
        worker_oracle_agrees = bool(
            abs(float(worker_oracle.get("full_dof_direct_q30_B_relative", float("inf")))
                - direct_witness["full_dof_B_candidate_relative"]) <= 1e-12
            and abs(float(worker_oracle.get("full_dof_direct_q30_D_relative", float("inf")))
                    - direct_witness["full_dof_D_candidate_relative"]) <= 1e-12
        )
        internal_b_witness = _need(arrays, prefix + "witness_internal_B_native")
        internal_d_witness = _need(arrays, prefix + "witness_internal_D_native")
        internal_witness_nonzero = bool(
            np.linalg.norm(internal_b_witness) > 0 and np.linalg.norm(internal_d_witness) > 0
        )
        local_pass = bool(
            fi_manufacture_rel <= 1e-12 and ft_manufacture_rel <= 1e-12
            and port_rhs_manufacture_rel <= 1e-12
            and interior_rel <= 1e-11 and xi_rel <= 1e-11 and known_state_rel <= 1e-11
            and original_trace_rel <= 1e-10 and reduced_trace_rel <= 1e-10
            and trace_identity_rel <= 1e-10
            and original_port_equation_rel <= 1e-10 and reduced_port_equation_rel <= 1e-10
            and original_port_reconstruction_rel <= 1e-12
            and reduced_port_reconstruction_rel <= 1e-12
            and port_identity_rel <= 1e-10 and nonzero_rhs and direct_witness["pass"]
            and worker_oracle_agrees and internal_witness_nonzero
            and len(alpha) == len(modes)
            and int(np.count_nonzero(np.asarray([row["side"] for row in modes]) == side)) == 16030
        )
        local_results.append({
            "degree": degree,
            "side": side,
            "local_recovery_equation_relative": interior_rel,
            "recovered_interior_direct_solve_relative": xi_rel,
            "known_interior_solution_relative": known_state_rel,
            "manufactured_interior_rhs_relative": fi_manufacture_rel,
            "manufactured_trace_rhs_relative": ft_manufacture_rel,
            "manufactured_port_rhs_relative": port_rhs_manufacture_rel,
            "original_trace_equation_relative": original_trace_rel,
            "reduced_trace_equation_relative": reduced_trace_rel,
            "trace_elimination_identity_relative": trace_identity_rel,
            "full_key_original_port_equation_relative": original_port_equation_rel,
            "full_key_reduced_port_equation_relative": reduced_port_equation_rel,
            "full_key_original_port_reconstruction_relative": original_port_reconstruction_rel,
            "full_key_reduced_port_reconstruction_relative": reduced_port_reconstruction_rel,
            "full_key_port_identity_relative": port_identity_rel,
            "nonzero_internal_trace_port_rhs": nonzero_rhs,
            "direct_full_dof_q30_witness": direct_witness,
            "worker_full_dof_oracle_claim_agrees": worker_oracle_agrees,
            "internal_B_and_D_witness_nonzero": internal_witness_nonzero,
            "full_mode_count": len(alpha),
            "pass": local_pass,
        })

    source_hash_check = {}
    for relative_path, expected in report.get("source_files_sha256", {}).items():
        source_path = ROOT / relative_path
        source_hash_check[relative_path] = {
            "expected": expected,
            "actual": _file_sha256(source_path) if source_path.is_file() else None,
            "pass": source_path.is_file() and _file_sha256(source_path) == expected,
        }
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    local_complete = len(local_results) == 4 and all(row["pass"] for row in local_results)
    source_head_matches = head == report.get("source_head_at_probe")
    pass_all = bool(
        boundary_pass and boundary["worker_claim_agrees"] and local_complete
        and all(v["pass"] for v in source_hash_check.values()) and source_head_matches
    )
    result = {
        "schema": "task40extra.review_v8_w1_boundary_probe_saved_checker.v1",
        "status": "SAVED_ARRAYS_CHECK_PASS" if pass_all else (
            "SAVED_ARRAYS_PARTIAL_OR_CONTROLLED_NEGATIVE"
        ),
        "source_head_current": head,
        "source_head_at_probe": report.get("source_head_at_probe"),
        "source_head_matches": source_head_matches,
        "report_path": str(report_path),
        "report_sha256": _file_sha256(report_path),
        "raw_npz_sha256": raw_meta["file_sha256"],
        "raw_member_hashes_recomputed": True,
        "input_identity_recomputed": input_identity,
        "mode_key_order_matches": keys_match,
        "boundary_recomputation": boundary,
        "local_case_recomputations": local_results,
        "source_file_hashes": source_hash_check,
        "global_target_mpc_mapping": "NOT_RUN; local one-cell witness does not invent target-volume row IDs",
        "pass": pass_all,
    }
    _atomic_json(output / "w1_boundary_probe_checker.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = check(args.output, args.report)
    print(json.dumps({
        "status": result["status"],
        "pass": result["pass"],
        "report": str(args.output / "w1_boundary_probe_checker.json"),
    }, indent=2))
    # A controlled numerical negative is still a successfully completed
    # checker. Its scientific classification is carried in the saved JSON.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
