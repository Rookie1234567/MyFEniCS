from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
import ufl
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.sparse import linalg as spla

from dolfinx import default_real_type, default_scalar_type, fem
from dolfinx.fem import petsc as fem_petsc

from ..common.config import SimulationConfig
from ..common.materials import relative_permittivity
from ..common.pml import curl_3d
from ..constraints.floquet_constraint import (
    build_floquet_constraints,
    dof_trace_mismatch,
)
from ..geometry.mesh_builder import build_mesh
from ..postprocessing.power_metrics import (
    compute_dtn_auxiliary_power_metrics,
    compute_dtn_port_power_metrics,
    compute_power_metrics,
)
from ..postprocessing.postprocess import save_fields_and_plots
from .solve_vector_maxwell import (
    _json_default,
    _petsc_to_csr,
    _solve_manual,
    _solve_mpc,
)

CompressedTraceVector = dict[str, object]
CompressedTraceBank = dict[str, dict[int, CompressedTraceVector]]


def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1e-14 or (abs(root.imag) < 1e-14 and root.real < 0):
        root = -root
    return root


def port_incident_field_function(V, cfg: SimulationConfig) -> fem.Function:
    E_inc = fem.Function(V, name="E_port_inc")
    px, py = cfg.polarization

    def eval_field(x):
        phase = np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
        values = np.empty((2, x.shape[1]), dtype=np.complex128)
        values[0] = cfg.port_incident_amplitude * px * phase
        values[1] = cfg.port_incident_amplitude * py * phase
        return values

    E_inc.interpolate(eval_field)
    return E_inc


def _subtract_fields(total, incident):
    E_scat = fem.Function(total.function_space, name="E_scat")
    E_scat.x.array[:] = total.x.array[:] - incident.x.array[:]
    E_scat.x.scatter_forward()
    return E_scat


def _fourier_trace_vector(V, mesh_data, tag: int, alpha: float) -> np.ndarray:
    msh = mesh_data.mesh
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(msh)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mesh_data.facet_tags)
    phase = ufl.exp(PETSc.ScalarType(1j * alpha) * x[0])
    form = fem.form(phase * ufl.conj(v[0]) * ds(tag))
    vec = fem_petsc.assemble_vector(form)
    vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    return vec.array.copy()


def _compress_trace_vector(ell: np.ndarray) -> CompressedTraceVector:
    cutoff = max(1e-14, 1e-12 * float(np.max(np.abs(ell)))) if len(ell) else 1e-14
    nz = np.flatnonzero(np.abs(ell) > cutoff)
    return {
        "indices": nz.astype(np.int64, copy=True),
        "values": np.asarray(ell[nz], dtype=np.complex128).copy(),
        "size": int(len(ell)),
        "cutoff": float(cutoff),
    }


def _compressed_outer_trace_triplets(
    trace: CompressedTraceVector, coefficient: complex
):
    nz = np.asarray(trace["indices"], dtype=np.int64)
    values = np.asarray(trace["values"], dtype=np.complex128)
    if len(nz) == 0:
        return (
            np.asarray([], dtype=np.int64),
            np.asarray([], dtype=np.int64),
            np.asarray([], dtype=np.complex128),
        )
    rows = np.repeat(nz, len(nz))
    cols = np.tile(nz, len(nz))
    data = coefficient * np.repeat(values, len(nz)) * np.tile(np.conj(values), len(nz))
    return rows, cols, data


def _add_compressed_trace_to_rhs(
    b_out: np.ndarray, trace: CompressedTraceVector, coefficient: complex
) -> None:
    nz = np.asarray(trace["indices"], dtype=np.int64)
    values = np.asarray(trace["values"], dtype=np.complex128)
    if len(nz):
        b_out[nz] += coefficient * values


def _port_side_specs(
    cfg: SimulationConfig,
) -> tuple[tuple[str, int, complex], tuple[str, int, complex]]:
    return (
        ("top", cfg.tags.outer_top, complex(cfg.n_air)),
        ("bottom", cfg.tags.outer_bottom, complex(cfg.n_substrate)),
    )


def _rayleigh_scale(k_medium: complex) -> float:
    return max(abs(k_medium) ** 2, 1.0)


def _is_near_rayleigh(k_medium: complex, alpha: complex, cfg: SimulationConfig) -> bool:
    beta_squared = complex(k_medium**2 - alpha**2)
    return abs(beta_squared) <= float(cfg.port_rayleigh_tolerance) * _rayleigh_scale(
        k_medium
    )


def _is_clearly_propagating(
    k_medium: complex, alpha: complex, beta: complex, cfg: SimulationConfig
) -> bool:
    if abs(complex(alpha).imag) > 1e-10:
        return False
    dispersion = complex(k_medium**2 - alpha**2)
    if _is_near_rayleigh(k_medium, alpha, cfg):
        return False
    scale = max(abs(dispersion), abs(k_medium) ** 2, 1.0e-30)
    beta_margin = float(cfg.port_rayleigh_tolerance) * max(abs(k_medium), 1.0e-30)
    # A lossy half-space gives a power-carrying outgoing mode a complex beta.
    # Classify it from the real part of beta^2 instead of requiring Im(k)=0.
    return dispersion.real > -1.0e-10 * scale and beta.real > beta_margin


def _candidate_orders_for_side(cfg: SimulationConfig, k_medium: complex) -> list[int]:
    if not cfg.port_use_diffraction_orders:
        return [0]
    reciprocal = 2.0 * np.pi / cfg.period_x
    alpha0 = float(np.real(cfg.kx))
    radius = abs(float(np.real(k_medium)))
    half_width = int(np.ceil((abs(alpha0) + radius) / reciprocal)) + 2
    return list(range(-half_width, half_width + 1))


def _mode_record(
    *,
    cfg: SimulationConfig,
    side: str,
    tag: int,
    refractive_index: complex,
    order: int,
    selected: bool,
) -> dict[str, object]:
    k_medium = complex(cfg.k0 * refractive_index)
    alpha = complex(cfg.kx + 2.0 * np.pi * order / cfg.period_x)
    beta = _positive_sqrt(k_medium**2 - alpha**2)
    near_rayleigh = _is_near_rayleigh(k_medium, alpha, cfg)
    propagating = _is_clearly_propagating(k_medium, alpha, beta, cfg)
    return {
        "side": side,
        "tag": int(tag),
        "order": int(order),
        "refractive_index": refractive_index,
        "k_medium": k_medium,
        "alpha": alpha,
        "beta": beta,
        "is_propagating": bool(propagating),
        "is_near_rayleigh": bool(near_rayleigh),
        "selected": bool(selected),
        "selected_reason": (
            "order0_forced"
            if order == 0 and not propagating
            else "clearly_propagating"
            if selected and cfg.port_use_diffraction_orders
            else "order0_only"
            if selected
            else "not_selected"
        ),
    }


def _select_dtn_port_modes(cfg: SimulationConfig, log) -> dict[str, object]:
    selected_modes: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    rayleigh_warnings: list[dict[str, object]] = []
    orders_by_side: dict[str, list[int]] = {"top": [], "bottom": []}

    for side, tag, refractive_index in _port_side_specs(cfg):
        k_medium = complex(cfg.k0 * refractive_index)
        side_candidates = _candidate_orders_for_side(cfg, k_medium)
        selected_orders: list[int] = []
        for order in side_candidates:
            probe = _mode_record(
                cfg=cfg,
                side=side,
                tag=tag,
                refractive_index=refractive_index,
                order=order,
                selected=False,
            )
            selected = order == 0 or (
                cfg.port_use_diffraction_orders and bool(probe["is_propagating"])
            )
            probe["selected"] = bool(selected)
            probe["selected_reason"] = (
                "order0_always_included"
                if order == 0
                else "clearly_propagating"
                if selected
                else "evanescent_or_rayleigh_near"
            )
            candidates.append(probe)
            if bool(probe["is_near_rayleigh"]):
                warning = {
                    "side": side,
                    "order": int(order),
                    "alpha": probe["alpha"],
                    "beta": probe["beta"],
                    "is_propagating": bool(probe["is_propagating"]),
                    "is_near_rayleigh": True,
                }
                rayleigh_warnings.append(warning)
                log(
                    "warning: Fourier DtN order near Rayleigh anomaly "
                    f"(side={side}, order={order}, beta={probe['beta']})"
                )
            if selected:
                selected_orders.append(order)
                selected_modes.append(
                    _mode_record(
                        cfg=cfg,
                        side=side,
                        tag=tag,
                        refractive_index=refractive_index,
                        order=order,
                        selected=True,
                    )
                )
        orders_by_side[side] = sorted(set(selected_orders))

    log(
        "selected Fourier DtN orders: "
        f"top={orders_by_side['top']}, bottom={orders_by_side['bottom']}"
    )
    return {
        "modes": selected_modes,
        "mode_candidates": candidates,
        "orders_by_side": orders_by_side,
        "rayleigh_warnings": rayleigh_warnings,
    }


def _top_incident_source_amplitude(
    mode: dict[str, object], cfg: SimulationConfig
) -> complex:
    k_medium = complex(mode["k_medium"])
    beta = complex(mode["beta"])
    return (
        2j
        * k_medium**2
        / beta
        * complex(cfg.port_incident_amplitude)
        * cfg.polarization[0]
        * np.exp(1j * cfg.ky * cfg.y_max)
    )


def _build_dtn_trace_data(
    V, mesh_data, cfg: SimulationConfig, log
) -> dict[str, object]:
    if cfg.use_pml:
        raise RuntimeError(
            "Fourier DtN ports require use_pml=False in the current port total-field solver."
        )
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(
            "Fourier DtN ports are currently implemented in the serial manual backend."
        )

    selection = _select_dtn_port_modes(cfg, log)
    modes: list[dict[str, object]] = []
    trace_vectors: CompressedTraceBank = {"top": {}, "bottom": {}}
    for raw_mode in selection["modes"]:
        mode = dict(raw_mode)
        side = str(mode["side"])
        order = int(mode["order"])
        ell = _fourier_trace_vector(
            V, mesh_data, int(mode["tag"]), complex(mode["alpha"])
        )
        trace = _compress_trace_vector(ell)
        trace_vectors[side][order] = trace
        mode.update(
            {
                "q": -1j * complex(mode["k_medium"]) ** 2 / complex(mode["beta"]),
                "num_trace_dofs": int(len(trace["indices"])),
                "trace_vector_storage": "compressed_nonzero_indices_and_values",
                "dense_trace_size": int(trace["size"]),
                "trace_compression_ratio": (
                    float(len(trace["indices"]) / trace["size"])
                    if int(trace["size"])
                    else 0.0
                ),
                "trace_cutoff": float(trace["cutoff"]),
            }
        )
        modes.append(mode)
        del ell

    return {
        **selection,
        "modes": modes,
        "trace_vectors": trace_vectors,
    }


def _add_fourier_port_operators_explicit(
    A_csr, b_np, V, mesh_data, cfg: SimulationConfig, log
):
    metadata = _build_dtn_trace_data(V, mesh_data, cfg, log)
    b_out = np.asarray(b_np, dtype=np.complex128).copy()
    port_rows: list[np.ndarray] = []
    port_cols: list[np.ndarray] = []
    port_data: list[np.ndarray] = []

    for mode in metadata["modes"]:
        side = str(mode["side"])
        order = int(mode["order"])
        trace = metadata["trace_vectors"][side][order]
        q_mode = complex(mode["q"])
        rows, cols, data = _compressed_outer_trace_triplets(
            trace, q_mode / cfg.period_x
        )
        if len(data):
            port_rows.append(rows)
            port_cols.append(cols)
            port_data.append(data)
        mode["assembly_role"] = "explicit_outer_product"
        mode["port_outer_nnz"] = int(len(trace["indices"]) ** 2)

        if side == "top" and order == 0:
            _add_compressed_trace_to_rhs(
                b_out, trace, -_top_incident_source_amplitude(mode, cfg)
            )

    if port_data:
        A_port = sparse.coo_matrix(
            (
                np.concatenate(port_data),
                (np.concatenate(port_rows), np.concatenate(port_cols)),
            ),
            shape=A_csr.shape,
            dtype=np.complex128,
        ).tocsr()
    else:
        A_port = sparse.csr_matrix(A_csr.shape, dtype=np.complex128)

    metadata["port_dtn_assembly"] = "explicit"
    metadata["num_auxiliary_dofs"] = 0
    metadata["explicit_port_matrix_nnz"] = int(A_port.nnz)
    return A_csr + A_port, b_out, metadata


def _add_fourier_port_operators_auxiliary(
    A_csr, b_np, V, mesh_data, cfg: SimulationConfig, log
):
    metadata = _build_dtn_trace_data(V, mesh_data, cfg, log)
    b_out = np.asarray(b_np, dtype=np.complex128).copy()
    n_fem = A_csr.shape[0]
    modes = list(metadata["modes"])
    n_aux = len(modes)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    data: list[np.ndarray] = []

    for aux_index, mode in enumerate(modes):
        side = str(mode["side"])
        order = int(mode["order"])
        trace = metadata["trace_vectors"][side][order]
        nz = np.asarray(trace["indices"], dtype=np.int64)
        values = np.asarray(trace["values"], dtype=np.complex128)
        q_mode = complex(mode["q"])
        aux_dof = n_fem + aux_index

        if len(nz):
            # FEM equation: A u + q ell a = b.
            rows.append(nz)
            cols.append(np.full(len(nz), aux_dof, dtype=np.int64))
            data.append(q_mode * values)

            # Modal equation: a - (1/L) ell^H u = 0.
            rows.append(np.full(len(nz), aux_dof, dtype=np.int64))
            cols.append(nz)
            data.append(-(np.conj(values) / cfg.period_x))

        rows.append(np.asarray([aux_dof], dtype=np.int64))
        cols.append(np.asarray([aux_dof], dtype=np.int64))
        data.append(np.asarray([1.0 + 0.0j], dtype=np.complex128))

        mode["assembly_role"] = "auxiliary_modal_unknown"
        mode["auxiliary_index"] = int(aux_index)
        mode["auxiliary_global_dof"] = int(aux_dof)
        mode["auxiliary_column_nnz"] = int(len(nz))

        if side == "top" and order == 0:
            _add_compressed_trace_to_rhs(
                b_out, trace, -_top_incident_source_amplitude(mode, cfg)
            )

    if n_aux:
        A_aux = sparse.coo_matrix(
            (
                np.concatenate(data),
                (np.concatenate(rows), np.concatenate(cols)),
            ),
            shape=(n_fem + n_aux, n_fem + n_aux),
            dtype=np.complex128,
        ).tocsr()
    else:
        A_aux = sparse.csr_matrix((n_fem, n_fem), dtype=np.complex128)

    A_aug = sparse.block_diag(
        (A_csr, sparse.csr_matrix((n_aux, n_aux), dtype=np.complex128)), format="csr"
    )
    A_aug = A_aug + A_aux
    b_aug = np.concatenate([b_out, np.zeros(n_aux, dtype=np.complex128)])
    metadata["port_dtn_assembly"] = "auxiliary"
    metadata["num_auxiliary_dofs"] = int(n_aux)
    metadata["auxiliary_block_nnz"] = int(A_aux.nnz)
    return A_aug, b_aug, metadata


def _fem_constraint_embedding(n_fem: int, constraints):
    slave = constraints.slave_dofs
    master = constraints.master_dofs
    coefficients = constraints.coefficients
    offsets = constraints.offsets

    is_slave = np.zeros(n_fem, dtype=bool)
    is_slave[slave] = True
    free = np.flatnonzero(~is_slave)
    reduced_index = -np.ones(n_fem, dtype=np.int64)
    reduced_index[free] = np.arange(len(free), dtype=np.int64)
    if np.any(reduced_index[master] < 0):
        raise RuntimeError("Floquet master dofs cannot also be slave dofs.")

    slave_rows = np.repeat(slave, np.diff(offsets))
    rows = np.concatenate([free, slave_rows])
    cols = np.concatenate([reduced_index[free], reduced_index[master]])
    data = np.concatenate([np.ones(len(free), dtype=np.complex128), coefficients])
    C_fem = sparse.coo_matrix(
        (data, (rows, cols)), shape=(n_fem, len(free)), dtype=np.complex128
    ).tocsr()
    return C_fem, len(free)


def _solve_manual_with_auxiliary(A_aug, b_aug, constraints, n_fem: int):
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError(
            "auxiliary DtN manual constraint elimination is serial-only."
        )
    n_total = A_aug.shape[0]
    n_aux = n_total - n_fem
    C_fem, num_fem_reduced = _fem_constraint_embedding(n_fem, constraints)
    C_aug = sparse.block_diag(
        (C_fem, sparse.identity(n_aux, dtype=np.complex128, format="csr")), format="csr"
    )
    A_reduced = (C_aug.conjugate().transpose() @ A_aug @ C_aug).tocsc()
    b_reduced = C_aug.conjugate().transpose() @ b_aug
    x_reduced = spla.spsolve(A_reduced, b_reduced)
    reduced_residual = np.linalg.norm(A_reduced @ x_reduced - b_reduced) / max(
        np.linalg.norm(b_reduced), 1e-30
    )
    x_full = np.asarray(C_aug @ x_reduced, dtype=np.complex128)
    return (
        x_full[:n_fem],
        x_full[n_fem:],
        {
            "solver_backend": "manual_constraint_elimination_with_auxiliary_dtn_modes",
            "reduced_linear_residual": float(reduced_residual),
            "num_reduced_dofs": int(A_reduced.shape[0]),
            "reduced_matrix_nnz": int(A_reduced.nnz),
            "num_fem_reduced_dofs": int(num_fem_reduced),
            "num_auxiliary_dofs": int(n_aux),
            "ksp_converged_reason": None,
            "ksp_iterations": None,
        },
    )


def _auxiliary_coefficients_by_side(
    modes: list[dict[str, object]], aux_values: np.ndarray
) -> dict[str, dict[int, complex]]:
    coefficients: dict[str, dict[int, complex]] = {"top": {}, "bottom": {}}
    for mode in modes:
        side = str(mode["side"])
        order = int(mode["order"])
        aux_index = int(mode["auxiliary_index"])
        coefficients.setdefault(side, {})[order] = complex(aux_values[aux_index])
    return coefficients


def _write_auxiliary_amplitudes(
    out_dir: Path, modes: list[dict[str, object]], aux_values: np.ndarray
) -> None:
    if MPI.COMM_WORLD.rank != 0:
        return
    rows = []
    for mode in modes:
        if "auxiliary_index" not in mode:
            continue
        value = complex(aux_values[int(mode["auxiliary_index"])])
        rows.append(
            {
                "side": mode["side"],
                "order": int(mode["order"]),
                "auxiliary_index": int(mode["auxiliary_index"]),
                "alpha": mode["alpha"],
                "beta": mode["beta"],
                "amplitude_real": value.real,
                "amplitude_imag": value.imag,
                "amplitude_abs": abs(value),
                "is_propagating": bool(mode["is_propagating"]),
                "is_near_rayleigh": bool(mode["is_near_rayleigh"]),
            }
        )
    (out_dir / "dtn_auxiliary_amplitudes.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _add_fourier_port_operators(A_csr, b_np, V, mesh_data, cfg: SimulationConfig, log):
    if cfg.use_pml:
        raise RuntimeError(
            "多衍射级次 Fourier 端口目前要求 use_pml=False；请去掉 --port-use-pml。"
        )
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("多衍射级次 Fourier 端口目前只支持单进程运行。")
    if cfg.port_dtn_order_count < 0:
        raise RuntimeError("port_dtn_order_count must be non-negative.")

    order_count = cfg.port_dtn_order_count
    if order_count < 0:
        return A_csr, b_np, []

    log(f"adding Fourier DtN periodic port orders m=-{order_count}...{order_count}")
    b_out = np.asarray(b_np, dtype=np.complex128).copy()
    modes: list[dict[str, object]] = []
    trace_vectors: CompressedTraceBank = {"top": {}, "bottom": {}}
    port_rows: list[np.ndarray] = []
    port_cols: list[np.ndarray] = []
    port_data: list[np.ndarray] = []

    for side, tag, refractive_index in (
        ("top", cfg.tags.outer_top, cfg.n_air),
        ("bottom", cfg.tags.outer_bottom, cfg.n_substrate),
    ):
        k_medium = cfg.k0 * refractive_index
        for order in range(-order_count, order_count + 1):
            alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
            beta = _positive_sqrt(k_medium**2 - alpha**2)
            q_mode = -1j * k_medium**2 / beta
            ell = _fourier_trace_vector(V, mesh_data, tag, alpha)
            trace = _compress_trace_vector(ell)
            trace_vectors[side][order] = trace
            rows, cols, data = _compressed_outer_trace_triplets(
                trace, q_mode / cfg.period_x
            )
            if len(data):
                port_rows.append(rows)
                port_cols.append(cols)
                port_data.append(data)
            del ell

            if side == "top" and order == 0:
                source_amplitude = (
                    2j
                    * k_medium**2
                    / beta
                    * cfg.port_incident_amplitude
                    * cfg.polarization[0]
                    * np.exp(1j * cfg.ky * cfg.y_max)
                )
                _add_compressed_trace_to_rhs(b_out, trace, -source_amplitude)

            modes.append(
                {
                    "side": side,
                    "order": order,
                    "alpha": alpha,
                    "beta": beta,
                    "q": q_mode,
                    "num_trace_dofs": int(len(trace["indices"])),
                    "port_outer_nnz": int(len(trace["indices"]) ** 2),
                    "trace_vector_storage": "compressed_nonzero_indices_and_values",
                    "dense_trace_size": int(trace["size"]),
                    "trace_compression_ratio": (
                        float(len(trace["indices"]) / trace["size"])
                        if int(trace["size"])
                        else 0.0
                    ),
                    "trace_cutoff": float(trace["cutoff"]),
                }
            )

    if port_data:
        A_port = sparse.coo_matrix(
            (
                np.concatenate(port_data),
                (np.concatenate(port_rows), np.concatenate(port_cols)),
            ),
            shape=A_csr.shape,
            dtype=np.complex128,
        ).tocsr()
    else:
        A_port = sparse.csr_matrix(A_csr.shape, dtype=np.complex128)

    return A_csr + A_port, b_out, modes, trace_vectors


def run_port_case(
    cfg: SimulationConfig,
    out_dir: Path,
    constraint_backend: str = "manual",
    *,
    solution_observer: Callable[[np.ndarray], None] | None = None,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    start = time.perf_counter()

    def log(message: str):
        log_lines.append(message)
        if MPI.COMM_WORLD.rank == 0:
            PETSc.Sys.Print(message)

    if not np.issubdtype(default_scalar_type, np.complexfloating):
        raise RuntimeError("Current DOLFINx/PETSc is not in complex mode.")
    if cfg.polarization_type.upper() != "TM":
        raise RuntimeError(
            "solve_port_maxwell.run_port_case() only supports TM Ex/Ey; use solve_te_maxwell for TE."
        )
    if cfg.use_pml:
        raise RuntimeError(
            "port_use_pml=True is disabled for the TM port total-field solver. "
            "The current port weak form integrates only physical air/substrate/grating cells, so PML cells would "
            "have unconstrained Maxwell degrees of freedom. Use the default port_use_pml=False."
        )

    log(f"case = {cfg.case_name}")
    log("formulation = port_total_field")
    log(f"constraint_backend = {constraint_backend}")
    log(f"use_pml = {cfg.use_pml}")
    log(f"PETSc ScalarType = {PETSc.ScalarType}")
    log(f"k0 = {cfg.k0:.12g}, kx = {cfg.kx}, ky = {cfg.ky}")
    log(f"port_incident_amplitude = {cfg.port_incident_amplitude}")
    log(f"port_boundary_model = {cfg.port_boundary_model}")
    log(f"port_dtn_order_count = {cfg.port_dtn_order_count}")
    log(f"port_dtn_assembly = {cfg.port_dtn_assembly}")
    log(f"port_use_diffraction_orders = {cfg.port_use_diffraction_orders}")
    log(
        f"Floquet phase = {cfg.floquet_phase.real:.12g} + {cfg.floquet_phase.imag:.12g}j"
    )
    if cfg.port_boundary_model not in ("robin", "dtn"):
        raise ValueError(
            "A concrete port case must use port_boundary_model='robin' or 'dtn'."
        )
    if cfg.port_dtn_order_count < 0:
        raise ValueError("port_dtn_order_count must be non-negative.")
    if cfg.port_dtn_assembly not in ("explicit", "auxiliary"):
        raise ValueError("port_dtn_assembly must be 'explicit' or 'auxiliary'.")
    if cfg.port_boundary_model == "dtn" and constraint_backend in (
        "mpc_official",
        "mpc_lowlevel",
    ):
        raise RuntimeError(
            "DtN Fourier 端口目前只支持 manual 后端；官方 MPC 后端请使用 port_boundary_model='robin'。"
        )

    mesh_data = build_mesh(cfg, out_dir)
    msh = mesh_data.mesh
    tdim = msh.topology.dim
    num_cells = msh.topology.index_map(tdim).size_global

    curl_el = element(
        "N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type
    )
    V = fem.functionspace(msh, curl_el)
    num_dofs = V.dofmap.index_map.size_global * V.dofmap.index_map_bs
    log(f"mesh cells = {num_cells}")
    log(f"N1curl dofs = {num_dofs}")

    eps = relative_permittivity(mesh_data, cfg)
    E_inc = port_incident_field_function(V, cfg)
    constraints = build_floquet_constraints(V, mesh_data, cfg)
    log(f"Floquet constrained boundary dofs = {len(constraints.slave_dofs)}")
    log(f"max left/right y-pairing error = {constraints.max_pair_y_error:.3e}")
    log(f"max Floquet probe reconstruction error = {constraints.max_probe_error:.3e}")

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    x = ufl.SpatialCoordinate(msh)
    dx = ufl.Measure("dx", msh, subdomain_data=mesh_data.cell_tags)
    ds = ufl.Measure("ds", domain=msh, subdomain_data=mesh_data.facet_tags)
    d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))

    k_air = cfg.k0 * cfg.n_air
    k_sub = cfg.k0 * cfg.n_substrate
    beta_air = _positive_sqrt(k_air**2 - cfg.kx**2)
    beta_sub = _positive_sqrt(k_sub**2 - cfg.kx**2)
    q_top = -1j * k_air**2 / beta_air
    q_bottom = -1j * k_sub**2 / beta_sub

    a = (
        ufl.inner(curl_3d(u), curl_3d(v)) * d_physical
        - cfg.k0**2 * eps * ufl.inner(u, v) * d_physical
    )
    if cfg.port_boundary_model == "robin":
        incident_x = (
            cfg.port_incident_amplitude
            * cfg.polarization[0]
            * ufl.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
        )
        top_source = 2j * k_air**2 / beta_air * incident_x
        a = (
            a
            + ufl.inner(q_top * u[0], v[0]) * ds(cfg.tags.outer_top)
            + ufl.inner(q_bottom * u[0], v[0]) * ds(cfg.tags.outer_bottom)
        )
        L = -ufl.inner(top_source, v[0]) * ds(cfg.tags.outer_top)
    else:
        L = PETSc.ScalarType(0.0) * ufl.conj(v[0]) * ds(cfg.tags.outer_top)

    if constraint_backend in ("mpc_official", "mpc_lowlevel"):
        log("solving port total-field system with dolfinx_mpc.MultiPointConstraint")
        E_total, solver_info = _solve_mpc(a, L, V, constraints, cfg, log)
        E_inc_output = port_incident_field_function(E_total.function_space, cfg)
    elif constraint_backend == "manual":
        log("assembling PETSc matrix/vector")
        A = fem_petsc.assemble_matrix(fem.form(a), bcs=[])
        A.assemble()

        port_modes = []
        port_trace_vectors: CompressedTraceBank = {"top": {}, "bottom": {}}
        port_metadata: dict[str, object] = {}
        port_auxiliary_values = np.asarray([], dtype=np.complex128)
        port_auxiliary_coefficients: dict[str, dict[int, complex]] = {
            "top": {},
            "bottom": {},
        }
        A_csr = _petsc_to_csr(A)
        linear_matrix_rows = int(A_csr.shape[0])
        linear_matrix_nnz = int(A_csr.nnz)
        if cfg.port_boundary_model == "robin":
            b = fem_petsc.assemble_vector(fem.form(L))
            b.ghostUpdate(
                addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
            )
            b_np = b.array.copy()
        else:
            b_np = np.zeros(A_csr.shape[0], dtype=np.complex128)
        if cfg.port_boundary_model == "dtn":
            if cfg.port_dtn_assembly == "explicit":
                A_csr, b_np, port_metadata = _add_fourier_port_operators_explicit(
                    A_csr, b_np, V, mesh_data, cfg, log
                )
                linear_matrix_rows = int(A_csr.shape[0])
                linear_matrix_nnz = int(A_csr.nnz)
                port_modes = port_metadata["modes"]
                port_trace_vectors = port_metadata["trace_vectors"]
                log(
                    "solving explicit DtN constrained port system with C^H A C reduction + SciPy SuperLU"
                )
                solution, solver_info = _solve_manual(A_csr, b_np, constraints)
            else:
                A_aug, b_aug, port_metadata = _add_fourier_port_operators_auxiliary(
                    A_csr, b_np, V, mesh_data, cfg, log
                )
                linear_matrix_rows = int(A_aug.shape[0])
                linear_matrix_nnz = int(A_aug.nnz)
                port_modes = port_metadata["modes"]
                port_trace_vectors = port_metadata["trace_vectors"]
                log(
                    "solving auxiliary DtN constrained port system with block C^H A C reduction + SciPy SuperLU"
                )
                solution, port_auxiliary_values, solver_info = (
                    _solve_manual_with_auxiliary(
                        A_aug, b_aug, constraints, A_csr.shape[0]
                    )
                )
                port_auxiliary_coefficients = _auxiliary_coefficients_by_side(
                    port_modes, port_auxiliary_values
                )
                _write_auxiliary_amplitudes(out_dir, port_modes, port_auxiliary_values)
        else:
            log(
                "solving constrained port system with C^H A C reduction + SciPy SuperLU"
            )
            solution, solver_info = _solve_manual(A_csr, b_np, constraints)
        E_total = fem.Function(V, name="E_total")
        E_total.x.array[:] = solution
        E_total.x.scatter_forward()
        E_inc_output = E_inc
    else:
        raise ValueError(
            "port total-field solver supports 'mpc_official', 'mpc_lowlevel', or 'manual'."
        )
    if constraint_backend in ("mpc_official", "mpc_lowlevel"):
        port_modes = []
        port_trace_vectors = {"top": {}, "bottom": {}}
        port_metadata = {}
        port_auxiliary_values = np.asarray([], dtype=np.complex128)
        port_auxiliary_coefficients = {"top": {}, "bottom": {}}
        linear_matrix_rows = None
        linear_matrix_nnz = None

    if solution_observer is not None:
        solution_observer(np.asarray(E_total.x.array, dtype=np.complex128).copy())

    E_scat_output = _subtract_fields(E_total, E_inc_output)
    field_metrics = save_fields_and_plots(
        mesh_data, cfg, E_inc_output, E_scat_output, E_total, out_dir
    )
    power_metrics = compute_power_metrics(mesh_data, cfg, E_total, out_dir)
    dtn_port_power_metrics = {}
    dtn_auxiliary_power_metrics = {}
    dtn_port_vs_probe_power_difference = {}
    dtn_auxiliary_vs_trace_power_difference = {}
    if cfg.port_boundary_model == "dtn":
        dtn_port_power_metrics = compute_dtn_port_power_metrics(
            mesh_data, cfg, E_total, out_dir, port_trace_vectors
        )
        if cfg.port_dtn_assembly == "auxiliary":
            dtn_auxiliary_power_metrics = compute_dtn_auxiliary_power_metrics(
                mesh_data,
                cfg,
                E_total,
                out_dir,
                port_auxiliary_coefficients,
                port_metadata,
            )
            if {"R_total", "T_total", "R_plus_T"}.issubset(dtn_port_power_metrics) and {
                "R_total",
                "T_total",
                "R_plus_T",
            }.issubset(dtn_auxiliary_power_metrics):
                dtn_auxiliary_vs_trace_power_difference = {
                    "R_total_aux_minus_trace": (
                        dtn_auxiliary_power_metrics["R_total"]
                        - dtn_port_power_metrics["R_total"]
                    ),
                    "T_total_aux_minus_trace": (
                        dtn_auxiliary_power_metrics["T_total"]
                        - dtn_port_power_metrics["T_total"]
                    ),
                    "R_plus_T_aux_minus_trace": (
                        dtn_auxiliary_power_metrics["R_plus_T"]
                        - dtn_port_power_metrics["R_plus_T"]
                    ),
                }
        if {"R_total", "T_total", "R_plus_T"}.issubset(power_metrics) and {
            "R_total",
            "T_total",
            "R_plus_T",
        }.issubset(dtn_port_power_metrics):
            dtn_port_vs_probe_power_difference = {
                "R_total_port_minus_probe": dtn_port_power_metrics["R_total"]
                - power_metrics["R_total"],
                "T_total_port_minus_probe": dtn_port_power_metrics["T_total"]
                - power_metrics["T_total"],
                "R_plus_T_port_minus_probe": dtn_port_power_metrics["R_plus_T"]
                - power_metrics["R_plus_T"],
            }
    near_field_integrals = (
        dtn_auxiliary_power_metrics.get("near_field_integrals")
        or dtn_port_power_metrics.get("near_field_integrals")
        or power_metrics.get("near_field_integrals")
        or {}
    )
    floquet_mismatch_total = dof_trace_mismatch(E_total.x.array, constraints)
    elapsed = time.perf_counter() - start

    summary = {
        "case_name": cfg.case_name,
        "formulation": "port_total_field",
        "port_model": (
            "single Floquet fundamental mode Robin port"
            if cfg.port_boundary_model == "robin"
            else "multi-order Fourier Floquet DtN port"
        ),
        "config": cfg.as_jsonable(),
        "num_mesh_cells": int(num_cells),
        "num_nedelec_dofs": int(num_dofs),
        "num_reduced_dofs": solver_info["num_reduced_dofs"],
        "linear_matrix_rows": linear_matrix_rows,
        "linear_matrix_nnz": linear_matrix_nnz,
        "reduced_matrix_nnz": solver_info.get("reduced_matrix_nnz"),
        "petsc_scalar_type": str(PETSc.ScalarType),
        "solver": solver_info["solver_backend"],
        "reduced_linear_residual": solver_info["reduced_linear_residual"],
        "ksp_converged_reason": solver_info["ksp_converged_reason"],
        "ksp_iterations": solver_info["ksp_iterations"],
        "dolfinx_mpc_num_local_slaves": solver_info.get("dolfinx_mpc_num_local_slaves"),
        "elapsed_seconds": elapsed,
        "max_abs_E_inc": field_metrics["max_abs_E_inc"],
        "max_abs_E_scat_reference": field_metrics["max_abs_E_scat"],
        "max_abs_E_total": field_metrics["max_abs_E_total"],
        "power_metrics": power_metrics,
        "dtn_port_power_metrics": dtn_port_power_metrics,
        "dtn_auxiliary_power_metrics": dtn_auxiliary_power_metrics,
        "near_field_integrals": near_field_integrals,
        "dtn_port_vs_probe_power_difference": dtn_port_vs_probe_power_difference,
        "dtn_auxiliary_vs_trace_power_difference": dtn_auxiliary_vs_trace_power_difference,
        "floquet_phase": cfg.floquet_phase,
        "floquet_max_probe_error": constraints.max_probe_error,
        "floquet_mismatch_total_dof": floquet_mismatch_total,
        "top_port_q": q_top,
        "bottom_port_q": q_bottom,
        "port_boundary_model": cfg.port_boundary_model,
        "port_dtn_order_count": cfg.port_dtn_order_count,
        "port_dtn_assembly": cfg.port_dtn_assembly,
        "port_use_diffraction_orders": cfg.port_use_diffraction_orders,
        "port_orders_by_side": port_metadata.get("orders_by_side", {}),
        "port_order_candidates": port_metadata.get("mode_candidates", []),
        "port_rayleigh_warnings": port_metadata.get("rayleigh_warnings", []),
        "num_auxiliary_dofs": solver_info.get(
            "num_auxiliary_dofs", port_metadata.get("num_auxiliary_dofs", 0)
        ),
        "dtn_auxiliary_amplitudes_file": (
            "dtn_auxiliary_amplitudes.json"
            if cfg.port_boundary_model == "dtn" and cfg.port_dtn_assembly == "auxiliary"
            else None
        ),
        "port_modes": port_modes,
    }
    if solver_info["reduced_linear_residual"] is not None:
        log(f"reduced residual = {solver_info['reduced_linear_residual']:.3e}")
    log(f"max |E_inc| = {field_metrics['max_abs_E_inc']:.6e}")
    log(f"max |E_total| = {field_metrics['max_abs_E_total']:.6e}")
    if {"R_total", "T_total", "R_plus_T"}.issubset(power_metrics):
        log(
            "power metrics: "
            f"R={power_metrics['R_total']:.6e}, "
            f"T={power_metrics['T_total']:.6e}, "
            f"R+T={power_metrics['R_plus_T']:.6e}"
        )
    if {"R_total", "T_total", "R_plus_T"}.issubset(dtn_port_power_metrics):
        log(
            "DtN boundary-integral port power metrics: "
            f"R={dtn_port_power_metrics['R_total']:.6e}, "
            f"T={dtn_port_power_metrics['T_total']:.6e}, "
            f"R+T={dtn_port_power_metrics['R_plus_T']:.6e}"
        )
    if {"R_total", "T_total", "R_plus_T"}.issubset(dtn_auxiliary_power_metrics):
        log(
            "DtN auxiliary-amplitude port power metrics: "
            f"R={dtn_auxiliary_power_metrics['R_total']:.6e}, "
            f"T={dtn_auxiliary_power_metrics['T_total']:.6e}, "
            f"R+T={dtn_auxiliary_power_metrics['R_plus_T']:.6e}"
        )
    elif power_metrics.get("skipped"):
        log(f"power metrics skipped: {power_metrics['reason']}")
    log(f"Floquet mismatch total dof = {floquet_mismatch_total:.3e}")
    log(f"elapsed seconds = {elapsed:.3f}")

    if MPI.COMM_WORLD.rank == 0:
        (out_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "solver_log.txt").write_text(
            "\n".join(log_lines) + "\n", encoding="utf-8"
        )

    return summary
