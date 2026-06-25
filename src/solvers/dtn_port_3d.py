from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

import dolfinx_mpc
from dolfinx import fem

from ..common.config_3d import SimulationConfig3D
from ..common.modes_3d import PortMode3D, incident_power_3d, outgoing_port_modes_3d
from ..constraints.floquet_3d import DoubleFloquet3DData
from .solve_vector_maxwell import _json_default


def _complex_text(value: complex) -> str:
    number = complex(value)
    return f"{number.real:.16e}{number.imag:+.16e}j"


def _idx(values) -> np.ndarray:
    """PETSc index arrays must match the PETSc build's integer width."""

    return np.asarray(values, dtype=PETSc.IntType)


def _as_ufl_vector(values: np.ndarray, phase):
    return ufl.as_vector(tuple(PETSc.ScalarType(value) * phase for value in values))


def _port_mode_phase(mode: PortMode3D, x):
    exponent = (
        PETSc.ScalarType(1j * mode.alpha) * x[0]
        + PETSc.ScalarType(1j * mode.gamma) * x[1]
        + PETSc.ScalarType(1j * mode.k_vector[2]) * x[2]
    )
    return ufl.exp(exponent)


def _surface_vector_form(V, mesh_data, tag: int, vector: np.ndarray, phase):
    v = ufl.TestFunction(V)
    ds = ufl.Measure("ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)
    return ufl.inner(_as_ufl_vector(vector, phase), v) * ds(tag)


def _assemble_mpc_vector(linear_form, mpc) -> PETSc.Vec:
    vec = dolfinx_mpc.assemble_vector(fem.form(linear_form), mpc)
    vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    vec.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
    return vec


def _vec_nonzero_owned_entries(vec: PETSc.Vec, *, relative_tol: float = 1.0e-13) -> tuple[np.ndarray, np.ndarray]:
    start, end = vec.getOwnershipRange()
    values = np.asarray(vec.getArray(readonly=True), dtype=np.complex128)
    if values.size == 0:
        return _idx([]), np.asarray([], dtype=np.complex128)
    cutoff = max(1.0e-30, relative_tol * float(np.max(np.abs(values))))
    nz = np.flatnonzero(np.abs(values) > cutoff)
    return (_idx(np.arange(start, end, dtype=np.int64)[nz]), values[nz].copy())


def _copy_base_matrix_to_augmented(A_base: PETSc.Mat, n_aux: int, comm: MPI.Intracomm) -> PETSc.Mat:
    n_fe = A_base.getSize()[0]
    local_fe_rows = A_base.getOwnershipRange()[1] - A_base.getOwnershipRange()[0]
    local_aug_rows = local_fe_rows + (n_aux if comm.rank == comm.size - 1 else 0)
    A_aug = PETSc.Mat().createAIJ(
        size=((local_aug_rows, n_fe + n_aux), (local_aug_rows, n_fe + n_aux)),
        comm=comm,
    )
    A_aug.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    row_start, row_end = A_base.getOwnershipRange()
    for row in range(row_start, row_end):
        cols, values = A_base.getRow(row)
        if len(cols):
            A_aug.setValues(_idx([row]), _idx(cols), values)
    return A_aug


def _augmented_vec_from_base(b_base: PETSc.Vec, n_aux: int, comm: MPI.Intracomm) -> PETSc.Vec:
    n_fe = b_base.getSize()
    local_fe_rows = b_base.getOwnershipRange()[1] - b_base.getOwnershipRange()[0]
    local_aug_rows = local_fe_rows + (n_aux if comm.rank == comm.size - 1 else 0)
    b_aug = PETSc.Vec().createMPI((local_aug_rows, n_fe + n_aux), comm=comm)
    row_start, row_end = b_base.getOwnershipRange()
    values = np.asarray(b_base.getArray(readonly=True), dtype=np.complex128)
    if values.size:
        b_aug.setValues(_idx(np.arange(row_start, row_end, dtype=np.int64)), values, addv=PETSc.InsertMode.ADD_VALUES)
    return b_aug


def _outward_normal(side: str) -> np.ndarray:
    if side == "top":
        return np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    if side == "bottom":
        return np.asarray((0.0, 0.0, -1.0), dtype=np.float64)
    raise ValueError("side must be 'top' or 'bottom'.")


def _facet_tag_for_side(cfg: SimulationConfig3D, side: str) -> int:
    return cfg.tags.z_max if side == "top" else cfg.tags.z_min


def _traction_vector(mode: PortMode3D, cfg: SimulationConfig3D) -> np.ndarray:
    del cfg
    curl_vector = 1j * np.cross(mode.k_vector, mode.e_vector)
    return np.cross(_outward_normal(mode.side), curl_vector)


def _incident_projection_onto_top_mode(mode: PortMode3D, cfg: SimulationConfig3D) -> complex:
    if mode.side != "top" or mode.m != 0 or mode.n != 0:
        return 0.0 + 0.0j
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    denominator = area * mode.electric_tangential_norm_sq
    incident_e = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    tangential_overlap = np.vdot(mode.e_vector[:2], incident_e[:2])
    phase = np.exp(1j * (cfg.kz - mode.k_vector[2]) * cfg.physical_z_max)
    return complex(area * tangential_overlap * phase / denominator)


def _incident_top_traction_form(V, mesh_data, cfg: SimulationConfig3D):
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    k_inc = np.asarray(cfg.wavevector, dtype=np.complex128)
    e_inc = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    traction = np.cross(np.asarray((0.0, 0.0, 1.0), dtype=np.float64), 1j * np.cross(k_inc, e_inc))
    phase = ufl.exp(
        PETSc.ScalarType(1j * k_inc[0]) * x[0]
        + PETSc.ScalarType(1j * k_inc[1]) * x[1]
        + PETSc.ScalarType(1j * k_inc[2]) * x[2]
    )
    return _surface_vector_form(V, mesh_data, cfg.tags.z_max, traction, phase)


def _solve_augmented_system(
    A_aug: PETSc.Mat,
    b_aug: PETSc.Vec,
    petsc_options: dict[str, Any],
    prefix: str,
) -> tuple[PETSc.Vec, PETSc.KSP]:
    ksp = PETSc.KSP().create(A_aug.getComm())
    ksp.setOptionsPrefix(prefix)
    ksp.setOperators(A_aug)
    opts = PETSc.Options()
    opts.prefixPush(prefix)
    for key, value in petsc_options.items():
        opts[key] = value
    ksp.setFromOptions()
    for key in petsc_options.keys():
        del opts[key]
    opts.prefixPop()
    x_aug = b_aug.duplicate()
    ksp.solve(b_aug, x_aug)
    return x_aug, ksp


def _assign_fe_solution_from_augmented(
    x_aug: PETSc.Vec,
    floquet_data: DoubleFloquet3DData,
    n_aux: int,
):
    mpc = floquet_data.mpc
    E_total = fem.Function(mpc.function_space, name="E_total")
    index_map = E_total.function_space.dofmap.index_map
    block_size = E_total.function_space.dofmap.index_map_bs
    block_start, block_end = index_map.local_range
    owned_size = index_map.size_local * block_size
    global_dofs = _idx(np.arange(block_start * block_size, block_end * block_size, dtype=np.int64))
    if len(global_dofs):
        E_total.x.array[:owned_size] = x_aug.getValues(global_dofs)
    E_total.x.scatter_forward()
    mpc.homogenize(E_total)
    mpc.backsubstitution(E_total)
    E_total.x.scatter_forward()
    if n_aux == 0:
        return E_total
    return E_total


def _gather_auxiliary_values(x_aug: PETSc.Vec, n_fe: int, n_aux: int, comm: MPI.Intracomm) -> np.ndarray:
    values = np.zeros(n_aux, dtype=np.complex128)
    owner_rank = comm.size - 1
    if comm.rank == owner_rank and n_aux:
        values[:] = x_aug.getValues(_idx(np.arange(n_fe, n_fe + n_aux, dtype=np.int64)))
    values = comm.bcast(values, root=owner_rank)
    return np.asarray(values, dtype=np.complex128)


def _linear_residual(A: PETSc.Mat, b: PETSc.Vec, x: PETSc.Vec) -> dict[str, float | None]:
    try:
        residual = b.duplicate()
        A.mult(x, residual)
        residual.axpy(PETSc.ScalarType(-1.0), b)
        rhs_norm = float(b.norm())
        residual_norm = float(residual.norm())
        return {
            "linear_system_rhs_norm": rhs_norm,
            "linear_system_solution_norm": float(x.norm()),
            "linear_system_residual_norm": residual_norm,
            "linear_system_relative_residual": residual_norm / max(rhs_norm, 1.0e-30),
        }
    except Exception:
        return {
            "linear_system_rhs_norm": None,
            "linear_system_solution_norm": None,
            "linear_system_residual_norm": None,
            "linear_system_relative_residual": None,
        }


def _write_port_outputs(
    out_dir: Path,
    cfg: SimulationConfig3D,
    modes: list[PortMode3D],
    aux_values: np.ndarray,
    incident_projections: list[complex],
    metrics: dict[str, Any],
    comm: MPI.Intracomm,
) -> None:
    rows: list[dict[str, Any]] = []
    for idx, (mode, aux_value, inc_proj) in enumerate(zip(modes, aux_values, incident_projections)):
        outgoing_amplitude = complex(aux_value - inc_proj) if mode.side == "top" else complex(aux_value)
        power = abs(outgoing_amplitude) ** 2 * mode.power_per_unit_amplitude / metrics["incident_power_code_units"]
        rows.append(
            {
                "auxiliary_index": idx,
                "side": mode.side,
                "m": mode.m,
                "n": mode.n,
                "polarization": mode.polarization,
                "alpha": mode.alpha,
                "gamma": mode.gamma,
                "beta": mode.beta,
                "vertical_sign": mode.vertical_sign,
                "propagating": mode.propagating,
                "rayleigh_warning": mode.rayleigh_warning,
                "auxiliary_amplitude_total_projection": complex(aux_value),
                "incident_projection": complex(inc_proj),
                "outgoing_amplitude": outgoing_amplitude,
                "power_ratio": float(power),
                "R": float(power) if mode.side == "top" and mode.propagating else 0.0,
                "T": float(power) if mode.side == "bottom" and mode.propagating else 0.0,
            }
        )
    if comm.rank != 0:
        return
    payload = {"metrics": metrics, "orders": rows}
    (out_dir / "dtn_port_power_metrics_3d.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (out_dir / "dtn_port_diffraction_orders_3d.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    csv_rows = [
        {key: _complex_text(value) if isinstance(value, complex) else value for key, value in row.items()}
        for row in rows
    ]
    with (out_dir / "dtn_port_diffraction_orders_3d.csv").open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["side", "m", "n"])
        writer.writeheader()
        writer.writerows(csv_rows)
    amplitudes = [
        {
            "auxiliary_index": idx,
            "side": mode.side,
            "m": mode.m,
            "n": mode.n,
            "polarization": mode.polarization,
            "auxiliary_amplitude_total_projection": complex(aux_values[idx]),
            "incident_projection": complex(incident_projections[idx]),
            "outgoing_amplitude": complex(aux_values[idx] - incident_projections[idx])
            if mode.side == "top"
            else complex(aux_values[idx]),
        }
        for idx, mode in enumerate(modes)
    ]
    (out_dir / "dtn_auxiliary_amplitudes_3d.json").write_text(
        json.dumps(amplitudes, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _port_power_metrics(
    cfg: SimulationConfig3D,
    modes: list[PortMode3D],
    aux_values: np.ndarray,
    incident_projections: list[complex],
) -> dict[str, Any]:
    incident_power = incident_power_3d(cfg)
    rows_by_side = {"top": 0, "bottom": 0}
    R_total = 0.0
    T_total = 0.0
    for mode, aux_value, inc_proj in zip(modes, aux_values, incident_projections):
        rows_by_side[mode.side] += 1
        outgoing_amplitude = complex(aux_value - inc_proj) if mode.side == "top" else complex(aux_value)
        if not mode.propagating:
            continue
        power = abs(outgoing_amplitude) ** 2 * mode.power_per_unit_amplitude / incident_power
        if mode.side == "top":
            R_total += float(power)
        else:
            T_total += float(power)
    return {
        "R_total": float(R_total),
        "T_total": float(T_total),
        "R_plus_T": float(R_total + T_total),
        "A_balance": float(1.0 - R_total - T_total),
        "diffraction_total_power_source": "dtn_auxiliary_port_amplitudes",
        "dtn_port_power_metric_note": (
            "Stage-4 dtn_port R/T is computed directly from auxiliary outgoing modal amplitudes "
            "on the top and bottom port faces."
        ),
        "incident_power_code_units": float(incident_power),
        "stage4_dtn_order_policy": cfg.stage4_dtn_order_policy,
        "stage4_dtn_assembly": cfg.stage4_dtn_assembly,
        "dtn_port_mode_count": int(len(modes)),
        "dtn_port_top_mode_count": int(rows_by_side["top"]),
        "dtn_port_bottom_mode_count": int(rows_by_side["bottom"]),
        "dtn_port_propagating_mode_count": int(sum(1 for mode in modes if mode.propagating)),
        "dtn_port_rayleigh_warning_count": int(sum(1 for mode in modes if mode.rayleigh_warning)),
        "dtn_port_power_metrics_file": "dtn_port_power_metrics_3d.json",
        "dtn_port_orders_json": "dtn_port_diffraction_orders_3d.json",
        "dtn_port_orders_csv": "dtn_port_diffraction_orders_3d.csv",
        "dtn_auxiliary_amplitudes_file": "dtn_auxiliary_amplitudes_3d.json",
    }


def solve_stage4_dtn_port_total_field(
    *,
    a,
    L,
    V,
    mesh_data,
    cfg: SimulationConfig3D,
    floquet_data: DoubleFloquet3DData,
    petsc_options: dict[str, Any],
    out_dir: Path,
    log,
) -> dict[str, Any]:
    """Solve the Stage-4 total-field problem with 3D Fourier-DtN ports."""

    if cfg.stage4_dtn_assembly.lower() != "auxiliary":
        raise NotImplementedError("Stage-4 3D DtN v1 supports only stage4_dtn_assembly='auxiliary'.")
    if cfg.use_pml:
        raise ValueError("stage4_boundary_model='dtn_port' requires use_pml=False.")
    if floquet_data is None:
        raise ValueError("stage4_boundary_model='dtn_port' requires x/y Floquet constraints.")

    comm = mesh_data.mesh.comm
    stage_start = time.perf_counter()
    A_base = dolfinx_mpc.assemble_matrix(fem.form(a), floquet_data.mpc, bcs=None)
    A_base.assemble()
    b_base = _assemble_mpc_vector(L, floquet_data.mpc)
    n_fe = A_base.getSize()[0]
    modes = outgoing_port_modes_3d(cfg)
    n_aux = len(modes)
    if n_aux == 0:
        raise RuntimeError("Stage-4 DtN selected zero port modes.")
    if log is not None:
        log(f"Stage-4 DtN selected auxiliary port modes = {n_aux}")
        log(f"Stage-4 DtN top/bottom mode count = {sum(m.side == 'top' for m in modes)} / {sum(m.side == 'bottom' for m in modes)}")
        log(f"Stage-4 DtN matrix base rows = {n_fe}")

    A_aug = _copy_base_matrix_to_augmented(A_base, n_aux, comm)
    b_aug = _augmented_vec_from_base(b_base, n_aux, comm)

    incident_traction_vec = _assemble_mpc_vector(_incident_top_traction_form(V, mesh_data, cfg), floquet_data.mpc)
    inc_rows, inc_values = _vec_nonzero_owned_entries(incident_traction_vec)
    if len(inc_rows):
        b_aug.setValues(inc_rows, -inc_values, addv=PETSc.InsertMode.ADD_VALUES)

    incident_projections: list[complex] = []
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    x = ufl.SpatialCoordinate(mesh_data.mesh)
    for aux_index, mode in enumerate(modes):
        tag = _facet_tag_for_side(cfg, mode.side)
        phase = _port_mode_phase(mode, x)
        trace_vector = np.asarray((mode.e_vector[0], mode.e_vector[1], 0.0 + 0.0j), dtype=np.complex128)
        traction_vector = _traction_vector(mode, cfg)
        ell = _assemble_mpc_vector(_surface_vector_form(V, mesh_data, tag, trace_vector, phase), floquet_data.mpc)
        traction = _assemble_mpc_vector(_surface_vector_form(V, mesh_data, tag, traction_vector, phase), floquet_data.mpc)
        aux_global = n_fe + aux_index
        denominator = area * mode.electric_tangential_norm_sq
        incident_projection = _incident_projection_onto_top_mode(mode, cfg)
        incident_projections.append(incident_projection)

        rows, values = _vec_nonzero_owned_entries(traction)
        if len(rows):
            A_aug.setValues(rows, _idx([aux_global]), values.reshape((len(rows), 1)))
            if incident_projection != 0.0:
                b_aug.setValues(rows, values * incident_projection, addv=PETSc.InsertMode.ADD_VALUES)

        cols, ell_values = _vec_nonzero_owned_entries(ell)
        if len(cols):
            A_aug.setValues(
                _idx([aux_global]),
                cols,
                (-np.conj(ell_values) / denominator).reshape((1, len(cols))),
            )
        A_aug.setValue(aux_global, aux_global, PETSc.ScalarType(1.0))

        if log is not None and (aux_index + 1) % 50 == 0:
            elapsed = comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)
            log(f"Stage-4 DtN assembled {aux_index + 1}/{n_aux} auxiliary modes in {elapsed:.3f} seconds")

    A_aug.assemble()
    b_aug.assemble()
    x_aug, ksp = _solve_augmented_system(A_aug, b_aug, petsc_options, f"stage4_3d_dtn_{cfg.case_name}_")
    E_total = _assign_fe_solution_from_augmented(x_aug, floquet_data, n_aux)
    aux_values = _gather_auxiliary_values(x_aug, n_fe, n_aux, comm)
    port_metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
    _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, port_metrics, comm)

    solver_info = {
        "solver_backend": "PETSc augmented auxiliary Fourier-DtN port with dolfinx_mpc Floquet constraints",
        "num_auxiliary_dofs": int(n_aux),
        "num_fem_dofs_after_mpc": int(n_fe),
        "num_total_augmented_dofs": int(n_fe + n_aux),
        "stage4_dtn_assembly_seconds": float(comm.allreduce(time.perf_counter() - stage_start, op=MPI.MAX)),
        "ksp_converged_reason": int(ksp.getConvergedReason()),
        "ksp_iterations": int(ksp.getIterationNumber()),
        "actual_ksp_type": ksp.getType(),
        "actual_pc_type": ksp.getPC().getType(),
        "actual_pc_factor_solver_type": None,
        **_linear_residual(A_aug, b_aug, x_aug),
    }
    try:
        solver_info["actual_pc_factor_solver_type"] = ksp.getPC().getFactorSolverType()
    except Exception:
        solver_info["actual_pc_factor_solver_type"] = None

    return {
        "E_total": E_total,
        "A": A_aug,
        "b": b_aug,
        "x": x_aug,
        "ksp": ksp,
        "solver_info": solver_info,
        "port_metrics": port_metrics,
    }
