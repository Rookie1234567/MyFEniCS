#!/usr/bin/env python3
"""Bounded one-cell V1 N1E Bloch-symbol check; no mesh, MPC, or solve."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import basix
import basix.ufl
import numpy as np
import scipy.linalg as la
import ufl
from ffcx.analysis import analyze_ufl_objects

REPO = next(
    parent for parent in Path(__file__).resolve().parents
    if (parent / "src").is_dir() and (parent / ".git").exists()
)
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
RUN = REPO / "results/euv_grazing1_phi0/v7_interleave_0p7nm_aniso_p6_direct_q160_n0_full__full3d_direct__mpi1__Mna/20261014T062635.999684Z"
OUT = REPO / "docs/task39extra_para_workstation_capacity/outcomes/dispersion_directional_validation_20261015/v1_actual_n1e_ey_dispersion_symbol_archived_execution.json"
V0 = REPO / "docs/task39extra_para_workstation_capacity/outcomes/dispersion_directional_validation_20261015/v0_source_identity_reconciliation.json"
RELEVANT = (
    "src/solvers/common_3d_forms.py",
    "src/solvers/fullspace_physical_intermediate_runtime.py",
    "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
    "src/constraints/floquet_3d.py",
    "src/solvers/fullspace_n1e_sum_factor.py",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_sha(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def shifted_legendre(degree: int, x: np.ndarray) -> np.ndarray:
    """Orthonormal shifted Legendre basis on [0, 1]."""
    x = np.asarray(x, dtype=np.float64)
    return np.column_stack(
        [np.sqrt(2 * j + 1) * np.polynomial.legendre.Legendre.basis(j)(2 * x - 1)
         for j in range(degree + 1)]
    )


def production_ffcx_rules(degree: int, values: dict) -> tuple[list[dict], basix.CellType]:
    """Run FFCx analysis on the production volume-form builder, without C/JIT."""
    from src.common.config_3d import Tags3D
    from src.solvers.common_3d_forms import _build_physical_volume_terms

    coord = basix.ufl.element("Lagrange", "hexahedron", 1, shape=(3,))
    domain = ufl.Mesh(coord)
    element = basix.ufl.element(
        "N1E", "hexahedron", degree, lagrange_variant=basix.LagrangeVariant.legendre
    )
    space = ufl.FunctionSpace(domain, element)
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain)
    cfg = SimpleNamespace(
        tags=Tags3D(),
        mu_r=complex(values["mu_r"]),
        eps_r=complex(values["eps_air"]),
        substrate_index=complex(values["n_substrate"]),
        grating_index=complex(values["n_grating"]),
        k0=float(values["k0_nm_inv"]),
    )
    forms = _build_physical_volume_terms(cfg, u, v, dx)
    coefficient = ufl.Coefficient(space)
    records: list[dict] = []
    for name, form in zip(("curl_curl", "material_mass"), forms, strict=True):
        analysis = analyze_ufl_objects([ufl.action(form, coefficient)], np.dtype(np.complex128))
        for group in analysis.form_data[0].integral_data:
            for integral in group.integrals:
                metadata = integral.metadata()
                records.append({
                    "component": name,
                    "integral_type": integral.integral_type(),
                    "subdomain_id": list(integral.subdomain_id()),
                    "quadrature_degree": int(metadata["quadrature_degree"]),
                    "quadrature_rule": str(metadata["quadrature_rule"]),
                    "estimated_polynomial_degree": int(metadata["estimated_polynomial_degree"]),
                })
    return records, basix.CellType.hexahedron


def build_dof_polynomial_matrix(element, degree: int, hy: float) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(element.points, dtype=np.float64)
    values = np.zeros((3, points.shape[0], degree + 1), dtype=np.float64)
    values[1, :, :] = hy * shifted_legendre(degree, points[:, 0])
    # Basix's interpolation matrix consumes component-major point values.
    packed = np.ascontiguousarray(values.reshape(3 * points.shape[0], degree + 1))
    dofs = np.asarray(element.interpolation_matrix, dtype=np.float64) @ packed
    return dofs, points


def tabulate_physical_fields(element, dofs: np.ndarray, points: np.ndarray,
                             h: tuple[float, float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    hx, hy, hz = h
    tab = np.asarray(element.tabulate(1, points), dtype=np.float64)
    vref = np.einsum("pdi,da->pai", tab[basix.index(0, 0, 0)], dofs, optimize=True)
    dref = np.stack([
        np.einsum("pdi,da->pai", tab[basix.index(1, 0, 0)], dofs, optimize=True),
        np.einsum("pdi,da->pai", tab[basix.index(0, 1, 0)], dofs, optimize=True),
        np.einsum("pdi,da->pai", tab[basix.index(0, 0, 1)], dofs, optimize=True),
    ], axis=0)
    # Covariant Piola: v_phys = J^{-T} v_ref, J=diag(hx,hy,hz).
    scale = np.asarray((hx, hy, hz), dtype=np.float64)
    vphys = vref / scale[None, None, :]
    dphys = dref / (scale[None, None, None, :] * scale[:, None, None, None])
    curl_ref = np.stack((dref[1, ..., 2] - dref[2, ..., 1],
                         dref[2, ..., 0] - dref[0, ..., 2],
                         dref[0, ..., 1] - dref[1, ..., 0]), axis=-1)
    # Covariant-Piola curl: curl_phys = J curl_ref / det(J).
    curlphys = curl_ref * scale[None, None, :] / math.prod(h)
    return vphys, dphys, curlphys


def matrices(element, dofs: np.ndarray, degree: int,
             h: tuple[float, float, float], qdegree: int) -> dict:
    points, weights = basix.make_quadrature(basix.CellType.hexahedron, qdegree,
                                            rule=basix.QuadratureType.default)
    points = np.asarray(points, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    v, dv, curl = tabulate_physical_fields(element, dofs, points, h)
    expected_ey = shifted_legendre(degree, points[:, 0])
    reconstruction_relative = float(
        np.linalg.norm(v[:, :, 1] - expected_ey)
        / max(np.linalg.norm(expected_ey), np.finfo(float).tiny)
    )
    detj = math.prod(h)
    K = detj * np.einsum("qia,qja,q->ij", np.conjugate(curl), curl, weights, optimize=True)
    M = detj * np.einsum("qia,qja,q->ij", np.conjugate(v), v, weights, optimize=True)
    expected_matrix_shape = (degree + 1, degree + 1)
    if K.shape != expected_matrix_shape or M.shape != expected_matrix_shape:
        raise AssertionError(
            f"symbol shape mismatch: K={K.shape}, M={M.shape}, expected={expected_matrix_shape}"
        )
    volume = float(np.sum(weights) * detj)
    value_total = math.sqrt(float(np.sum(weights[:, None, None] * np.abs(v) ** 2) * detj))
    non_ey = v.copy()
    non_ey[..., 1] = 0
    non_ey_l2 = math.sqrt(float(np.sum(weights[:, None, None] * np.abs(non_ey) ** 2) * detj))
    d_yz = dv[1:, :, :, :]
    d_yz_l2 = math.sqrt(float(np.sum(weights[None, :, None, None] * np.abs(d_yz) ** 2) * detj))
    d_x = dv[0]
    d_x_l2 = math.sqrt(float(np.sum(weights[:, None, None] * np.abs(d_x) ** 2) * detj))
    return {
        "K": K, "M": M, "qpoint_count": int(points.shape[0]),
        "quadrature_weight_sum_reference": float(np.sum(weights)),
        "cell_volume": volume,
        "non_ey_value_leakage_relative": non_ey_l2 / max(value_total, np.finfo(float).tiny),
        "yz_derivative_leakage_relative_to_x": d_yz_l2 / max(d_x_l2, np.finfo(float).tiny),
        "ey_polynomial_subspace_reconstruction_relative_l2": reconstruction_relative,
        "dof_condition_2": float(np.linalg.cond(dofs)),
        "max_abs_basis_dof": float(np.max(np.abs(dofs))),
    }


def solve_symbol(degree: int, hx: float, hy: float, hz: float, kx: float,
                 qdegree: int, previous: dict | None) -> tuple[dict, dict]:
    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        degree,
        lagrange_variant=basix.LagrangeVariant.legendre,
        dtype=np.float64,
    )
    dofs, _ = build_dof_polynomial_matrix(element, degree, hy)
    base = matrices(element, dofs, degree, (hx, hy, hz), qdegree)
    # Bloch constraint is E_y(x=1)=exp(+i*kx*hx) E_y(x=0), matching the
    # production high-x slave -> low-x target phase convention.
    phase = np.exp(1j * kx * hx)
    trace = shifted_legendre(degree, np.asarray([1.0]))[0] - phase * shifted_legendre(degree, np.asarray([0.0]))[0]
    Q = la.null_space(trace[None, :])
    Kr = Q.conj().T @ base["K"] @ Q
    Mr = Q.conj().T @ base["M"] @ Q
    Kh = float(np.linalg.norm(Kr - Kr.conj().T) / max(np.linalg.norm(Kr), 1.0e-300))
    Mh = float(np.linalg.norm(Mr - Mr.conj().T) / max(np.linalg.norm(Mr), 1.0e-300))
    evals, evecs = la.eigh(Kr, Mr)

    # Build the exact plane-wave DOF-functional witness, then express the
    # reconstructed polynomial in the shifted-Legendre coefficient basis.
    ref_points = np.asarray(element.points, dtype=np.float64)
    pw = np.zeros((3, ref_points.shape[0]), dtype=np.complex128)
    pw[1] = hy * np.exp(1j * kx * hx * ref_points[:, 0])
    pw_dofs = np.asarray(element.interpolation_matrix, dtype=np.float64) @ np.ascontiguousarray(pw.reshape(-1))
    qpts, qweights = basix.make_quadrature(basix.CellType.hexahedron, qdegree,
                                            rule=basix.QuadratureType.default)
    qpts = np.asarray(qpts, dtype=np.float64)
    vbasis, _, _ = tabulate_physical_fields(element, dofs, qpts, (hx, hy, hz))
    vtarget, _, _ = tabulate_physical_fields(element, pw_dofs[:, None], qpts, (hx, hy, hz))
    alpha_pw, *_ = np.linalg.lstsq(vbasis[:, :, 1], vtarget[:, 0, 1], rcond=None)
    constraint_resid = float(abs(trace @ alpha_pw) / max(np.linalg.norm(alpha_pw), 1.0e-300))
    projected = Q @ la.solve(Mr, Q.conj().T @ base["M"] @ alpha_pw)
    pnorm = math.sqrt(float(np.real(np.vdot(projected, base["M"] @ projected))))
    pvec = projected / pnorm

    exact_scores = []
    prev_scores = []
    normalized_vectors = []
    for j in range(len(evals)):
        full = Q @ evecs[:, j]
        nrm = math.sqrt(float(np.real(np.vdot(full, base["M"] @ full))))
        full = full / nrm
        normalized_vectors.append(full)
        exact_scores.append(float(abs(np.vdot(full, base["M"] @ pvec))))
        if previous is None:
            prev_scores.append(None)
        else:
            prev = previous["vector"]
            numerator = abs(np.vdot(full, base["M"] @ prev))
            denominator = math.sqrt(
                float(np.real(np.vdot(full, base["M"] @ full)))
                * float(np.real(np.vdot(prev, base["M"] @ prev)))
            )
            prev_scores.append(float(numerator / max(denominator, 1.0e-300)))
    selected = int(np.argmax(exact_scores))
    eigvec = normalized_vectors[selected]
    eig = float(evals[selected].real)
    residual = float(np.linalg.norm(Kr @ evecs[:, selected] - evals[selected] * (Mr @ evecs[:, selected])) /
                     max(np.linalg.norm(Kr @ evecs[:, selected]), 1.0e-300))
    target = kx * kx
    rel_kx2 = eig / target - 1.0
    k0 = float(_ACTIVE_VALUES["k0_nm_inv"])
    delta = (eig - target) / (k0 * k0)
    eps = complex(_ACTIVE_VALUES["eps_grating"])
    eps_effective_lambda = eig / eps
    result = {
        "degree": degree, "hx_nm": hx, "hy_nm": hy, "hz_nm": hz,
        "J_diagonal_nm": [hx, hy, hz], "detJ_nm3": math.prod((hx, hy, hz)),
        "bloch_phase_argument_rad": kx * hx,
        "bloch_phase_re": float(phase.real), "bloch_phase_im": float(phase.imag),
        "bloch_trace_relation": "E_y(x=1)=exp(+i*kx*hx)*E_y(x=0)",
        "phase_trace_relative_residual": constraint_resid,
        "constrained_polynomial_dimension": int(Q.shape[1]),
        "eigenvalue_index_selected_by_plane_wave_overlap": selected,
        "lambda_nm_minus2": eig,
        "target_kx2_nm_minus2": target,
        "relative_lambda_over_kx2_minus_1": rel_kx2,
        "plan_delta_lambda_minus_kx2_over_k0_2": delta,
        "material_weighted_diagnostic_lambda_over_eps_nm_minus2": [
            float(eps_effective_lambda.real), float(eps_effective_lambda.imag)],
        "plane_wave_mass_overlap": exact_scores[selected],
        "continuation_overlap_with_previous_h": prev_scores[selected],
        "all_physical_branch_overlaps": exact_scores,
        "all_eigenvalues_nm_minus2": [float(x.real) for x in evals],
        "generalized_eigenpair_relative_residual": residual,
        "K_hermitian_relative_defect": Kh,
        "M_hermitian_relative_defect": Mh,
        "M_min_eigenvalue": float(np.min(la.eigvalsh(Mr)).real),
        "reduced_M_condition_2": float(np.linalg.cond(Mr)),
        "reduced_K_condition_2": float(np.linalg.cond(Kr)),
        "coefficient_basis_condition_2": base["dof_condition_2"],
        "non_ey_value_leakage_relative": base["non_ey_value_leakage_relative"],
        "yz_derivative_leakage_relative_to_x": base["yz_derivative_leakage_relative_to_x"],
        "roundoff_scale_eps_times_max_condition": float(np.finfo(float).eps * max(
            base["dof_condition_2"], np.linalg.cond(Mr), np.linalg.cond(Kr))),
        "longdouble_nmant": int(np.finfo(np.longdouble).nmant),
        "basix_element": {
            "family": "N1E",
            "cell": "hexahedron",
            "degree": degree,
            "lagrange_variant": str(basix.LagrangeVariant.legendre),
            "map_type": str(element.map_type),
            "dimension": int(element.dim),
            "points_shape": list(np.asarray(element.points).shape),
            "dof_transformations_are_identity": bool(element.dof_transformations_are_identity),
        },
        "quadrature_point_count": base["qpoint_count"],
        "reduced_symbol_matrix_shape": list(Kr.shape),
        "quadrature_weight_sum_reference": base["quadrature_weight_sum_reference"],
        "cell_volume_nm3": base["cell_volume"],
        "orientation_scope": "canonical Basix reference-cell orientation only; production mesh cell_info transformations NOT_RUN",
    }
    return result, {"vector": eigvec}


def main() -> None:
    global _ACTIVE_VALUES
    resolved = json.loads((RUN / "resolved_config.json").read_text())
    manifest = json.loads((RUN / "run_manifest.json").read_text())
    direct = json.loads((RUN / "p6_condensed_direct_summary.json").read_text())
    v0 = json.loads(V0.read_text())
    incidence = resolved["incidence"]
    derived = resolved["derived"]
    mats = resolved["materials"]
    values = {
        "k0_nm_inv": float(derived["k0"]),
        "direction_vector": [float(x) for x in derived["direction_vector"]],
        "kx_nm_inv": float(derived["wavevector"][0][0]),
        "kz_nm_inv": float(derived["wavevector"][2][0]),
        "eps_air": complex(*mats["n_air"]) ** 2,
        "eps_substrate": complex(*mats["n_substrate"]) ** 2,
        "eps_grating": complex(*mats["n_grating"]) ** 2,
        "n_substrate": complex(*mats["n_substrate"]),
        "n_grating": complex(*mats["n_grating"]),
        "mu_r": complex(*mats["mu_r"]),
        "grazing_angle_deg": float(incidence["grazing_angle_deg"]),
        "azimuth_deg": float(incidence["azimuth_deg"]),
        "wavelength_nm": float(incidence["wavelength_nm"]),
        "parent_mode_count": int(direct["mode_inventory"]["parent_mode_count"]),
        "active_mode_count": int(direct["mode_inventory"]["active_mode_count"]),
        "active_mode_sha256": direct["mode_inventory"]["active_mode_sha256"],
        "parent_mode_sha256": direct["mode_inventory"]["parent_mode_sha256"],
        "parent_quadrature_degree": int(direct["operator_identity"]["parent_quadrature_degree"]),
        "production_floquet_phase_x": [float(x) for x in derived["floquet_phase_x"]],
    }
    _ACTIVE_VALUES = values
    rule_records: list[dict] = []
    q_by_degree: dict[int, int] = {}
    pairs_by_degree: dict[str, list[list[object]]] = {}
    for p in (6, 7, 8):
        records, _ = production_ffcx_rules(p, values)
        rule_records.extend(records)
        pairs = sorted({(r["quadrature_degree"], r["quadrature_rule"]) for r in records})
        if len(pairs) != 1 or pairs[0][1] != "default":
            raise RuntimeError(f"production FFCx volume rule changed for p{p}: {pairs}")
        pairs_by_degree[str(p)] = [list(x) for x in pairs]
        q_by_degree[p] = int(pairs[0][0])
    if pairs_by_degree["6"] != [[15, "default"]]:
        raise RuntimeError(f"p6 production FFCx volume rule changed unexpectedly: {pairs_by_degree['6']}")
    qpoints, qweights = basix.make_quadrature(
        basix.CellType.hexahedron, q_by_degree[6], rule=basix.QuadratureType.default
    )
    expected_global_phase = np.exp(1j * values["kx_nm_inv"] * resolved["geometry"]["period_x_nm"])
    saved_global_phase = complex(*values["production_floquet_phase_x"])
    phase_identity_error = float(abs(expected_global_phase - saved_global_phase))
    if phase_identity_error > 5e-13:
        raise RuntimeError(f"global x Floquet phase differs from kx: {phase_identity_error}")

    mesh = direct["mesh_evidence"]
    # The historical live grid has hx=0.5 nm. V1 is a one-variable bounded
    # reference-cell study at 0.5/0.25/0.125 nm; only the former is its mesh.
    hy = float(mesh["axes"]["y"]["max_width_nm"])
    hx_values = [0.5, 0.25, 0.125]
    hz_values = [0.6, 10.0 / 17.0]
    rows: list[dict] = []
    for p in (6, 7, 8):
        p_hx = hx_values if p == 6 else [0.5]
        p_hz = hz_values if p == 6 else [0.6]
        previous_by_hz: dict[float, dict] = {hz: None for hz in p_hz}
        for hz in p_hz:
            for hx in p_hx:
                row, state = solve_symbol(
                    p, hx, hy, hz, values["kx_nm_inv"], q_by_degree[p], previous_by_hz[hz]
                )
                previous_by_hz[hz] = state
                rows.append(row)

    source_files = {rel: sha(REPO / rel) for rel in RELEVANT}
    input_path = RUN / "input_original.dat"
    resolved_path = RUN / "resolved_config.json"
    direct_path = RUN / "p6_condensed_direct_summary.json"
    manifest_path = RUN / "run_manifest.json"
    source_from_manifest = str(manifest["source_sha"])
    result = {
        "schema": "task39extra.dispersion-v1-actual-basix-n1e-ey-symbol.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "BOUNDED_REFERENCE_CELL_SYMBOL_COMPLETE_ACTUAL_PRODUCTION_MPC_PORT_NOT_RUN",
        "scope": {
            "description": "one-cell Basix N1E polynomial subspace and Bloch-symbol component; no DOLFINx mesh, global matrix, production MPC, DtN carrier, factor, or PDE solve",
            "no_production_claim": True,
            "not_a_full_model_accuracy_gate": True,
            "no_npz_or_resources_read": True,
        },
        "identity": {
            "analysis_script_sha256": sha(Path(__file__).resolve()),
            "historical_run_id": manifest["run_id"],
            "historical_run_source_sha": source_from_manifest,
            "current_head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "input_sha256": sha(input_path),
            "resolved_config_sha256": sha(resolved_path),
            "physical_model_sha256": (RUN / "physical_model_sha256.txt").read_text().strip(),
            "direct_summary_sha256": sha(direct_path),
            "run_manifest_sha256": sha(manifest_path),
            "v0_reconciliation_sha256": sha(V0),
            "production_source_files_sha256": source_files,
        },
        "model": {
            "wavelength_nm": values["wavelength_nm"],
            "k0_nm_inv": values["k0_nm_inv"],
            "kx_nm_inv": values["kx_nm_inv"],
            "kz_nm_inv": values["kz_nm_inv"],
            "direction_vector": values["direction_vector"],
            "grazing_angle_deg": values["grazing_angle_deg"],
            "azimuth_deg": values["azimuth_deg"],
            "period_x_nm": resolved["geometry"]["period_x_nm"],
            "period_y_nm": resolved["geometry"]["period_y_nm"],
            "epsilon_air": [values["eps_air"].real, values["eps_air"].imag],
            "epsilon_Si": [values["eps_grating"].real, values["eps_grating"].imag],
            "mu_r": [values["mu_r"].real, values["mu_r"].imag],
            "degree_scope": [6, 7, 8],
            "hx_nm_p6": hx_values,
            "hz_nm_p6": hz_values,
            "hy_nm": hy,
            "production_mesh_counts": mesh["actual_axis_cell_counts"],
            "production_cell_info_values": "NOT_RECORDED_IN_BOUND_DIRECT_SUMMARY; canonical reference-cell orientation used here",
            "mode_parent_count_sha_q": [values["parent_mode_count"], values["parent_mode_sha256"], values["parent_quadrature_degree"]],
            "active_mode_count_sha": [values["active_mode_count"], values["active_mode_sha256"]],
        },
        "quadrature": {
            "source": "FFCx analyze_ufl_objects on common_3d_forms._build_physical_volume_terms, actual production curl-curl and material-mass UFL forms; no code generation or compilation",
            "integral_records": rule_records,
            "unique_degree_rule_pairs_by_polynomial_degree": pairs_by_degree,
            "quadrature_degree_by_polynomial_degree": {str(k): int(v) for k, v in q_by_degree.items()},
            "basix_reference_quadrature_points": int(np.asarray(qpoints).shape[0]),
            "basix_default_points_per_axis": int(round(np.asarray(qpoints).shape[0] ** (1 / 3))),
            "reference_weight_sum": float(np.sum(qweights)),
            "surface_dtn_quadrature_degree_from_run": values["parent_quadrature_degree"],
            "surface_and_volume_rules_are_distinct": True,
        },
        "bloch_direction": {
            "production_constraint_convention_source": "constraints/floquet_3d.py::_target_for_kind; x_max slave maps to x_min with cfg.floquet_phase_x",
            "one_cell_relation": "E_y(x=1)=exp(+i*kx*hx)E_y(x=0)",
            "global_phase_expected_from_kx": [float(expected_global_phase.real), float(expected_global_phase.imag)],
            "global_phase_saved_in_resolved": values["production_floquet_phase_x"],
            "global_phase_absolute_difference": phase_identity_error,
            "physical_branch_selection": "maximum mass-metric overlap with Basix DOF-interpolated exp(i*kx*x); adjacent-h continuation overlap also recorded",
            "not_smallest_eigenvalue": True,
            "production_MPC_pairing": "NOT_RUN",
            "production_cell_orientation_transformations": "NOT_RUN; reference-cell canonical orientation only",
        },
        "numerical_results": rows,
        "port_and_rhs": {
            "existing_production_run": {
                "fact": "the bound full 0.7-nm direct run used the production p6 action with the n=0 active DtN inventory and real build_physical_rhs route",
                "active_modes": values["active_mode_count"],
                "parent_modes": values["parent_mode_count"],
                "parent_q": values["parent_quadrature_degree"],
                "operator_scope": direct["operator_scope"],
                "full_dtn_status": direct["full_dtn_status"],
                "input_and_mode_identity_bound": True,
            },
            "this_v1_component_actual_incident_top_traction_projection_action": "NOT_RUN",
            "this_v1_component_actual_DtN_surface_action": "NOT_RUN",
            "next_v2_route": "fullspace_same_mesh_hcurl_pmg_physical.build_physical_rhs = _incident_top_traction_form -> _assemble_mpc_vector -> physical_action.compose_physical_rhs; flat case must use this nonzero boundary-driven RHS and an actual solve, not common_3d_forms.layered_scattered zero-contrast path",
        },
        "limitations": [
            "This reference-cell Bloch component does not instantiate production DOLFINx MPC, real 100x2x234 mesh, or port boundary integrals.",
            "The existing direct run had a real 572-mode N0 port solve, but its full 32060-mode DtN operator remains FULL_DTN_NOT_VERIFIED; this component does not close that limitation.",
            "The one-cell symbol isolates in-plane p6/p7/p8 dispersion; it is not a full grating R/T or RCWA qualification.",
            "Production mesh orientation and actual traction projection require the bounded V2 flat solve and remain not run here.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"result": str(OUT), "result_sha256": sha(OUT), "rows": len(rows),
                      "q_points": int(np.asarray(qpoints).shape[0]), "phase_error": phase_identity_error}, indent=2))


if __name__ == "__main__":
    _ACTIVE_VALUES: dict = {}
    main()
