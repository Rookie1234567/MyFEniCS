"""Task036 exact Cauchy/port-operator/failing-channel audit.

This is a bounded Review-V5 diagnostic.  It reuses the frozen A004-S
Full3D electric traces and rebuilds only the same one-z-cell operator plus
the two original local end-cap operators.  It never launches a Full3D or
Hybrid forward solve and never forms a dense full-interface square.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Sequence

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _authority_config,
    _mode_basis,
    _one_cell_config,
    _project_negative_traces,
)
from src.adaptivity.dtn_goal_adjoint import (
    DtnChannelGoal,
    build_dtn_unit_channel_gradient,
    solve_hermitian_discrete_adjoint,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import (
    build_high_order_constraint_data,
)
from src.coupling.hybrid_internal_modes import (
    build_hybrid_internal_mode_coupling,
)
from src.coupling.modal_trace_projection import (
    ModalTraceProjection,
    _overlap_matrix,
    build_matched_interface_trace,
    extract_tangential_trace,
)
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.modes.stable_propagation import build_two_sided_propagation
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_local_dtn import (
    HybridLocalDtnSystem,
    assemble_hybrid_local_dtn_system,
)
from src.solvers.one_cell_discrete_bloch import (
    EndpointModeLifter,
    ProjectedTwoPortSchur,
    _factor,
    build_one_cell_two_port_schur_action,
    compose_projected_two_port_schur,
    identify_endpoint_active_rows,
    lifted_endpoint_columns,
)


ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_CHANNELS = (
    ("bottom", -6, -2, "s"),
    ("bottom", -6, -1, "s"),
    ("bottom", -5, 0, "s"),
    ("bottom", -4, 0, "s"),
    ("bottom", -3, 0, "s"),
    ("bottom", 0, -2, "p"),
    ("bottom", 0, -2, "s"),
    ("bottom", 0, -1, "s"),
    ("top", -6, -2, "s"),
    ("top", -6, -1, "s"),
    ("top", -5, 0, "s"),
    ("top", -4, 0, "s"),
    ("top", -3, 0, "s"),
    ("top", 0, -2, "s"),
    ("top", 0, -1, "s"),
    ("top", 0, 0, "p"),
)


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True
    ).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _jsonable(value: Any) -> Any:
    if isinstance(value, (complex, np.complexfloating)):
        return _pair(complex(value))
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        if np.iscomplexobj(value):
            return [_jsonable(item) for item in value.tolist()]
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: dict[str, Any], comm: MPI.Intracomm) -> None:
    error = None
    if comm.rank == 0:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(_jsonable(payload), indent=2, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
        except Exception as caught:  # pragma: no cover - collective failure
            error = f"{type(caught).__name__}: {caught}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"Cauchy audit JSON write failed: {error}")
    comm.Barrier()


def _write_npz(
    path: Path,
    arrays: dict[str, np.ndarray],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    result = None
    error = None
    if comm.rank == 0:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(path, **arrays)
            result = {
                "path": str(path),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
                "arrays": {
                    key: list(np.asarray(value).shape)
                    for key, value in arrays.items()
                },
            }
        except Exception as caught:  # pragma: no cover - collective failure
            error = f"{type(caught).__name__}: {caught}"
    error = comm.bcast(error, root=0)
    if error is not None:
        raise RuntimeError(f"Cauchy audit NPZ write failed: {error}")
    return comm.bcast(result, root=0)


def _progress(comm: MPI.Intracomm, message: str) -> None:
    if comm.rank == 0:
        print(f"Task036 Cauchy audit: {message}", flush=True)


def _replicated_vector(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    first, last = map(int, vector.getOwnershipRange())
    packets = comm.allgather(
        (
            first,
            last,
            np.asarray(
                vector.getArray(readonly=True), dtype=np.complex128
            ).copy(),
        )
    )
    result = np.empty(int(vector.getSize()), dtype=np.complex128)
    seen = np.zeros(len(result), dtype=bool)
    for start, stop, values in packets:
        result[int(start) : int(stop)] = values
        seen[int(start) : int(stop)] = True
    if not np.all(seen):
        raise RuntimeError("Distributed vector ownership did not close.")
    return result


def _matrix_action(matrix: PETSc.Mat, values: Sequence[complex]) -> np.ndarray:
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    try:
        first, last = map(int, source.getOwnershipRange())
        array = np.asarray(values, dtype=np.complex128)
        if array.shape != (int(source.getSize()),):
            raise ValueError("Small modal vector has the wrong size.")
        source.getArray()[:] = np.asarray(
            array[first:last], dtype=PETSc.ScalarType
        )
        source.assemble()
        matrix.mult(source, target)
        return _replicated_vector(target)
    finally:
        target.destroy()
        source.destroy()


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(left) - np.asarray(right))
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-30)
    )


def _stable_unit_and_log10_norm(values: np.ndarray) -> tuple[np.ndarray, float]:
    array = np.asarray(values, dtype=np.complex128)
    scale = float(np.max(np.abs(array), initial=0.0))
    if not np.isfinite(scale) or scale <= 0.0:
        raise RuntimeError("A sensitivity row is zero or non-finite.")
    scaled = array / scale
    scaled_norm = float(np.linalg.norm(scaled))
    if not np.isfinite(scaled_norm) or scaled_norm <= 0.0:
        raise RuntimeError("A scaled sensitivity norm is not finite-positive.")
    return scaled / scaled_norm, float(
        np.log10(scale) + np.log10(scaled_norm)
    )


def _stable_vdot(left: np.ndarray, right: np.ndarray) -> complex:
    x = np.asarray(left, dtype=np.complex128)
    y = np.asarray(right, dtype=np.complex128)
    if x.shape != y.shape:
        raise ValueError("Stable dual pairing shapes differ.")
    x_scale = float(np.max(np.abs(x), initial=0.0))
    y_scale = float(np.max(np.abs(y), initial=0.0))
    if x_scale == 0.0 or y_scale == 0.0:
        return 0.0 + 0.0j
    normalized = np.sum(
        np.conj((x / x_scale).astype(np.clongdouble))
        * (y / y_scale).astype(np.clongdouble),
        dtype=np.clongdouble,
    )
    value = normalized * np.longdouble(x_scale) * np.longdouble(y_scale)
    result = complex(value)
    if not np.isfinite(result.real) or not np.isfinite(result.imag):
        raise RuntimeError("A channel-adjoint dual pairing overflowed.")
    return result


def _trace_function_from_global(space, values: np.ndarray) -> fem.Function:
    field = fem.Function(space)
    index_map = space.dofmap.index_map
    block_size = int(space.dofmap.index_map_bs)
    start, stop = map(int, index_map.local_range)
    begin = start * block_size
    end = stop * block_size
    expected = int(index_map.size_global * block_size)
    array = np.asarray(values, dtype=np.complex128)
    if array.shape != (expected,):
        raise ValueError(
            f"Archived trace has {array.size} values; expected {expected}."
        )
    field.x.array[: end - begin] = np.asarray(
        array[begin:end], dtype=PETSc.ScalarType
    )
    field.x.scatter_forward()
    return field


def _fit_columns(
    basis: np.ndarray,
    targets: np.ndarray,
    *,
    rcond: float = 1.0e-10,
) -> tuple[np.ndarray, dict[str, Any]]:
    coefficients, _residuals, rank, singular = np.linalg.lstsq(
        np.asarray(basis, dtype=np.complex128),
        np.asarray(targets, dtype=np.complex128),
        rcond=rcond,
    )
    recovered = basis @ coefficients
    per_column = [
        _relative(recovered[:, index], targets[:, index])
        for index in range(targets.shape[1])
    ]
    return coefficients, {
        "rank": int(rank),
        "columns": int(basis.shape[1]),
        "rcond": float(rcond),
        "condition_retained": float(singular[0] / singular[rank - 1])
        if rank
        else float("inf"),
        "relative_by_cell": per_column,
        "max_relative": float(np.max(per_column, initial=0.0)),
        "aggregate_relative": _relative(recovered, targets),
    }


def _positive_invsqrt(matrix: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    hermitian = 0.5 * (matrix + matrix.conj().T)
    values, vectors = np.linalg.eigh(hermitian)
    scale = max(float(np.max(values, initial=0.0)), 1.0e-300)
    threshold = 1.0e-12 * scale
    if not len(values) or float(np.min(values)) <= threshold:
        raise RuntimeError("Port self-Gram is not positive definite.")
    inverse = (
        vectors
        @ np.diag(1.0 / np.sqrt(values))
        @ vectors.conj().T
    )
    return inverse, {
        "condition": float(values[-1] / values[0]),
        "minimum_eigenvalue": float(values[0]),
        "maximum_eigenvalue": float(values[-1]),
    }


def _load_projected_schur(path: Path) -> tuple[ProjectedTwoPortSchur, np.ndarray]:
    with np.load(path) as archive:
        blocks = {
            name: np.asarray(archive[name], dtype=np.complex128)
            for name in ("S_LL", "S_LR", "S_RL", "S_RR")
        }
        negative = np.asarray(
            archive["negative_trace_coordinates"], dtype=np.complex128
        )
    return (
        ProjectedTwoPortSchur(
            **blocks,
            port_rows=2400,
            interior_rows=2040,
            interior_matrix_nnz=0,
        ),
        negative,
    )


def _repeat_port(
    one_cell: ProjectedTwoPortSchur,
    cells: int,
) -> tuple[ProjectedTwoPortSchur, list[dict[str, float]]]:
    if cells < 1:
        raise ValueError("Port composition requires at least one cell.")
    current = one_cell
    reports: list[dict[str, float]] = []
    for _index in range(1, cells):
        current, report = compose_projected_two_port_schur(
            current, one_cell
        )
        reports.append(report)
    return current, reports


def _small_port_matrix(port: ProjectedTwoPortSchur) -> np.ndarray:
    return np.block(
        [[port.S_LL, port.S_LR], [port.S_RL, port.S_RR]]
    )


def _modal_port_matrix(
    one_cell: ProjectedTwoPortSchur,
    negative_map: np.ndarray,
    forward_one_cell: np.ndarray,
    backward_one_cell: np.ndarray,
    cells: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build the current scalar-CG two-way port in Petrov coordinates."""

    lam = np.asarray(forward_one_cell, dtype=np.complex128)
    mu = np.asarray(backward_one_cell, dtype=np.complex128)
    mapping = np.asarray(negative_map, dtype=np.complex128)
    count = len(lam)
    identity = np.eye(count, dtype=np.complex128)
    lam_n = lam**cells
    mu_n = mu**cells
    boundary = np.block(
        [
            [identity, mapping * mu_n[np.newaxis, :]],
            [lam_n[:, np.newaxis] * identity, mapping],
        ]
    )
    positive_left = one_cell.S_LL + one_cell.S_LR * lam[np.newaxis, :]
    positive_right = one_cell.S_RL + one_cell.S_RR * lam[np.newaxis, :]
    negative_left = (
        one_cell.S_LL @ (mapping * mu[np.newaxis, :])
        + one_cell.S_LR @ mapping
    )
    negative_right = (
        one_cell.S_RL @ (mapping * mu[np.newaxis, :])
        + one_cell.S_RR @ mapping
    )
    flux = np.block(
        [
            [
                positive_left,
                negative_left * (mu ** (cells - 1))[np.newaxis, :],
            ],
            [
                positive_right * (lam ** (cells - 1))[np.newaxis, :],
                negative_right,
            ],
        ]
    )
    result = np.linalg.solve(boundary.T, flux.T).T
    return result, {
        "boundary_resolver_condition": float(np.linalg.cond(boundary)),
        "boundary_resolver_relative_residual": float(
            np.linalg.norm(result @ boundary - flux, ord="fro")
            / max(np.linalg.norm(flux, ord="fro"), 1.0e-30)
        ),
        "construction": (
            "one-cell exact Petrov traction columns plus frozen p5/h10 "
            "scalar-CG forward/backward factors"
        ),
    }


def _minimum_dual_reconstruction(
    test_columns: np.ndarray,
    coordinates: np.ndarray,
) -> np.ndarray:
    gram = test_columns.conj().T @ test_columns
    return test_columns @ np.linalg.solve(gram, coordinates)


def _port_actual_report(
    *,
    label: str,
    cells: int,
    first_plane: int,
    last_plane: int,
    exact_coefficients: np.ndarray,
    exact_left_flux: np.ndarray,
    exact_right_flux: np.ndarray,
    test_block: np.ndarray,
    exact_projected: ProjectedTwoPortSchur,
    modal_matrix: np.ndarray,
) -> dict[str, Any]:
    endpoint_coefficients = np.concatenate(
        (
            exact_coefficients[first_plane],
            exact_coefficients[last_plane],
        )
    )
    actual_flux = np.concatenate(
        (
            exact_left_flux[:, first_plane],
            exact_right_flux[:, last_plane - 1],
        )
    )
    actual_selected = test_block.conj().T @ actual_flux
    exact_selected = _small_port_matrix(exact_projected) @ endpoint_coefficients
    modal_selected = modal_matrix @ endpoint_coefficients
    modal_full = _minimum_dual_reconstruction(test_block, modal_selected)
    visible_actual = _minimum_dual_reconstruction(
        test_block, actual_selected
    )
    complement = actual_flux - visible_actual
    return {
        "label": label,
        "cells": cells,
        "z_nm": [
            float(10.0 + 10.0 * first_plane),
            float(10.0 + 10.0 * last_plane),
        ],
        "actual_full_to_modal_full_relative": _relative(
            actual_flux, modal_full
        ),
        "actual_selected_to_modal_relative": _relative(
            actual_selected, modal_selected
        ),
        "actual_selected_to_exact_projected_relative": _relative(
            actual_selected, exact_selected
        ),
        "exact_projected_to_modal_relative": _relative(
            exact_selected, modal_selected
        ),
        "actual_test_space_complement_relative": float(
            np.linalg.norm(complement)
            / max(np.linalg.norm(actual_flux), 1.0e-30)
        ),
        "norms": {
            "actual_full": float(np.linalg.norm(actual_flux)),
            "actual_selected": float(np.linalg.norm(actual_selected)),
            "test_space_complement": float(np.linalg.norm(complement)),
            "modal_minimum_norm_full": float(np.linalg.norm(modal_full)),
        },
        "norm_contract": (
            "fixed independent p5 trace-coordinate 2-norm; selected "
            "coordinates are W^H q; full modal dual is the minimum-norm "
            "vector satisfying those Petrov coordinates"
        ),
    }


def _active_trace_test_field(
    system: HybridLocalDtnSystem,
    adjoint: PETSc.Vec,
) -> fem.Function:
    if system.static_condensation is None:
        raise RuntimeError("The adjoint audit requires static condensation.")
    active = _replicated_vector(adjoint)[: system.n_fe]
    condensed = system.static_condensation.condensed
    if active.shape != (condensed.active_rows,):
        raise RuntimeError("Local adjoint active-trace size differs.")
    field = fem.Function(system.V, name=f"{system.side}_interface_adjoint")
    vector = field.x.petsc_vec
    vector.set(PETSc.ScalarType(0.0))
    originals = condensed.trace_constraints.owned_active_original_dofs
    if len(originals):
        active_ids = np.asarray(
            [
                condensed.trace_constraints.original_to_active[int(row)]
                for row in originals
            ],
            dtype=PETSc.IntType,
        )
        vector.setValues(
            originals,
            np.asarray(active[active_ids], dtype=PETSc.ScalarType),
        )
    vector.assemble()
    field.x.scatter_forward()
    system.floquet_data.mpc.homogenize(field)
    system.floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _adjoint_port_trace(
    system: HybridLocalDtnSystem,
    adjoint: PETSc.Vec,
    *,
    authority,
    cross_section,
    spaces,
    lifter: EndpointModeLifter,
    condensed,
    endpoint_rows,
    one_cell_mpc,
    one_cell_constraint_data,
) -> tuple[np.ndarray, dict[str, Any]]:
    field = _active_trace_test_field(system, adjoint)
    if system.side == "bottom":
        interface = build_matched_interface_trace(
            authority,
            cross_section,
            spaces,
            system.local_mesh.mesh,
            "top",
            top_z_nm=10.0,
        )
        endpoint = "left"
    else:
        interface = build_matched_interface_trace(
            authority,
            cross_section,
            spaces,
            system.local_mesh.mesh,
            "bottom",
            bottom_z_nm=110.0,
        )
        endpoint = "right"
    trace, extraction = extract_tangential_trace(field, interface)
    left, right = lifted_endpoint_columns(
        [trace],
        lifter,
        condensed,
        endpoint_rows,
        mpc=one_cell_mpc,
        constraint_data=one_cell_constraint_data,
    )
    values = left[:, 0] if endpoint == "left" else right[:, 0]
    _unit, log10_norm = _stable_unit_and_log10_norm(values)
    return values, {
        "endpoint": endpoint,
        "extraction": extraction.__dict__,
        "port_trace_log10_norm": log10_norm,
        "norm_evaluation": "max-scaled Euclidean norm",
    }


def _orders(path: Path) -> dict[tuple[str, int, int, str], complex]:
    record = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(record, dict) and "validation" in record:
        rows = record["validation"]["external_diffraction_orders"]
    else:
        rows = record["orders"]
    result = {}
    for row in rows:
        key = (
            str(row["side"]),
            int(row.get("m", row.get("order_m"))),
            int(row.get("n", row.get("order_n"))),
            str(row["polarization"]).lower(),
        )
        real, imag = row["outgoing_amplitude"]
        result[key] = complex(float(real), float(imag))
    return result


def _channel_adjoint_audit(
    system: HybridLocalDtnSystem,
    channels: Sequence[tuple[str, int, int, str]],
    *,
    current_load: np.ndarray,
    exact_flux: np.ndarray,
    old_orders: dict[tuple[str, int, int, str], complex],
    full_orders: dict[tuple[str, int, int, str], complex],
    authority,
    cross_section,
    spaces,
    lifter: EndpointModeLifter,
    condensed,
    endpoint_rows,
    one_cell_mpc,
    one_cell_constraint_data,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    solver = _factor(system.A)
    results: list[dict[str, Any]] = []
    port_vectors: list[np.ndarray] = []
    try:
        for side, m, n, polarization in channels:
            goal = DtnChannelGoal(
                side, m, n, polarization, "amplitude_real"
            )
            gradient, gradient_report = build_dtn_unit_channel_gradient(
                system.b,
                {
                    "modes": system.external_modes,
                    "num_fem_dofs_after_mpc": system.n_fe,
                },
                channel=goal,
            )
            adjoint = None
            try:
                adjoint, solve_report = solve_hermitian_discrete_adjoint(
                    system.A,
                    solver,
                    gradient,
                    template=system.b,
                )
                port, trace_report = _adjoint_port_trace(
                    system,
                    adjoint,
                    authority=authority,
                    cross_section=cross_section,
                    spaces=spaces,
                    lifter=lifter,
                    condensed=condensed,
                    endpoint_rows=endpoint_rows,
                    one_cell_mpc=one_cell_mpc,
                    one_cell_constraint_data=one_cell_constraint_data,
                )
                adjoint_values = _replicated_vector(adjoint)
                current_pair = _stable_vdot(adjoint_values, current_load)
                exact_pair = _stable_vdot(port, exact_flux)
                residual_pair = current_pair - exact_pair
                prediction = -residual_pair
                actual = old_orders[(side, m, n, polarization)] - full_orders[
                    (side, m, n, polarization)
                ]
                results.append(
                    {
                        "channel": {
                            "side": side,
                            "m": m,
                            "n": n,
                            "polarization": polarization,
                        },
                        "gradient": gradient_report,
                        "adjoint": solve_report,
                        "interface_trace": trace_report,
                        "current_modal_load_pair": current_pair,
                        "exact_fe_load_pair": exact_pair,
                        "current_minus_exact_load_pair": residual_pair,
                        "local_fixed_trace_prediction_old_minus_full3d": (
                            prediction
                        ),
                        "actual_old_minus_full3d_solver_coordinate": actual,
                        "prediction_to_actual_absolute_error": abs(
                            prediction - actual
                        ),
                        "prediction_to_actual_relative": float(
                            abs(prediction - actual)
                            / max(abs(actual), 1.0e-30)
                        ),
                    }
                )
                combined = np.zeros(2 * len(port), dtype=np.complex128)
                if side == "bottom":
                    combined[: len(port)] = port
                else:
                    combined[len(port) :] = port
                port_vectors.append(combined)
            finally:
                if adjoint is not None:
                    adjoint.destroy()
                gradient.destroy()
    finally:
        solver.destroy()
    return results, port_vectors


def _svd_summary(rows: np.ndarray) -> dict[str, Any]:
    values = np.asarray(rows, dtype=np.complex128)
    normalized_rows = [
        _stable_unit_and_log10_norm(row) for row in values
    ]
    normalized = np.stack([item[0] for item in normalized_rows])
    log10_norms = np.asarray(
        [item[1] for item in normalized_rows], dtype=np.float64
    )
    singular = np.linalg.svd(normalized, compute_uv=False)
    energy = singular**2
    cumulative = np.cumsum(energy) / max(float(np.sum(energy)), 1.0e-300)

    def rank_for(level: float) -> int:
        return int(np.searchsorted(cumulative, level, side="left") + 1)

    return {
        "singular_values": singular.tolist(),
        "first_direction_energy_fraction": float(cumulative[0]),
        "first_two_energy_fraction": float(cumulative[min(1, len(cumulative) - 1)]),
        "rank_for_90_percent": rank_for(0.90),
        "rank_for_95_percent": rank_for(0.95),
        "rank_for_99_percent": rank_for(0.99),
        "row_log10_norm_min": float(np.min(log10_norms)),
        "row_log10_norm_max": float(np.max(log10_norms)),
        "normalization": "each row max-scaled before Euclidean normalization",
    }


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--oracle-json", type=Path, required=True)
    parser.add_argument("--exact-traces", type=Path, required=True)
    parser.add_argument("--exact-coefficients", type=Path, required=True)
    parser.add_argument("--projected-blocks", type=Path, required=True)
    parser.add_argument("--old-hybrid-record", type=Path, required=True)
    parser.add_argument("--i1-hybrid-record", type=Path, required=True)
    parser.add_argument("--i2-hybrid-record", type=Path, required=True)
    parser.add_argument("--full3d-orders", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_arguments()
    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise SystemExit("The formal Cauchy audit requires MPI8.")
    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise SystemExit("The Cauchy audit requires PETSc complex128.")
    source_sha = _git("rev-parse", "HEAD")
    if source_sha != args.verified_clean_sha:
        raise SystemExit(
            f"Source SHA {source_sha} != {args.verified_clean_sha}."
        )
    dirty = _git(
        "status", "--short", "--untracked-files=all", "--", "src", "benchmarks"
    )
    if dirty:
        raise SystemExit("Formal Cauchy audit requires clean source:\n" + dirty)
    inputs = (
        args.oracle_json,
        args.exact_traces,
        args.exact_coefficients,
        args.projected_blocks,
        args.old_hybrid_record,
        args.i1_hybrid_record,
        args.i2_hybrid_record,
        args.full3d_orders,
    )
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise SystemExit("Required frozen artifacts are missing:\n" + "\n".join(missing))

    started = time.perf_counter()
    timings: dict[str, float] = {}
    authority = _authority_config()
    one_cell = _one_cell_config(authority)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    oracle = json.loads(args.oracle_json.read_text(encoding="utf-8"))

    stage = time.perf_counter()
    mesh_data = build_airbox_mesh_3d(one_cell, args.work_dir / "one_cell_mesh")
    V = _create_nedelec_space(mesh_data.mesh, one_cell)
    floquet = build_double_floquet_mpc(V, mesh_data, one_cell, lambda msg: _progress(comm, msg))
    constraint_data = build_high_order_constraint_data(V, mesh_data, one_cell)
    a, _L = _build_variational_forms(
        mesh_data.mesh,
        mesh_data,
        one_cell,
        V,
        field_formulation="total_field_dtn_port",
    )
    condensed = build_unconstrained_assembly_time_condensation(
        fem.form(a), V, mesh_data.cell_tags, mpc=floquet.mpc
    )
    endpoint_rows = identify_endpoint_active_rows(
        V,
        condensed,
        left_facets=mesh_data.facet_tags.find(one_cell.tags.z_min),
        right_facets=mesh_data.facet_tags.find(one_cell.tags.z_max),
    )
    action = build_one_cell_two_port_schur_action(
        condensed.matrix, endpoint_rows
    )
    timings["one_cell_assembly_and_interior_factor"] = time.perf_counter() - stage
    row_record = {
        "full_rows": condensed.full_rows,
        "active_rows": condensed.active_rows,
        **endpoint_rows.to_record(),
        "matrix_nnz": int(
            condensed.matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM).get(
                "nz_used", 0.0
            )
        ),
        "dense_interface_square_formed": action.dense_interface_square_formed,
    }
    expected_rows = oracle["row_identity"]
    row_identity_match = bool(
        condensed.full_rows == int(expected_rows["full_rows"])
        and condensed.active_rows
        == int(expected_rows["floquet_independent_active_rows"])
        and len(endpoint_rows.left_active)
        == int(expected_rows["left_active_rows"])
        and len(endpoint_rows.right_active)
        == int(expected_rows["right_active_rows"])
        and len(endpoint_rows.interior_active)
        == int(expected_rows["axial_internal_active_rows"])
        and endpoint_rows.left_active_sha256
        == expected_rows["left_active_sha256"]
        and endpoint_rows.right_active_sha256
        == expected_rows["right_active_sha256"]
    )
    if not row_identity_match:
        raise RuntimeError("One-cell row identity differs from the frozen oracle.")

    stage = time.perf_counter()
    (
        cross_section,
        spaces,
        operators,
        positive,
        negative,
        qep_record,
    ) = _mode_basis(
        authority,
        requested_modes=120,
        candidate_modes=240,
        comm=comm,
    )
    projection = ModalTraceProjection(spaces, positive, quadrature_degree=14)
    negative_traces, negative_coordinates, negative_record = (
        _project_negative_traces(projection, negative, spaces)
    )
    scalar = build_two_sided_propagation(
        [*positive.modes, *negative.modes],
        10.0,
        propagation_model="full3d_uniform_cg",
        axial_fem_degree=5,
        axial_h_nm=10.0,
    )
    lifter = EndpointModeLifter(
        V, axis_scale_nm=max(one_cell.period_x, one_cell.period_y)
    )
    right_left, right_right = lifted_endpoint_columns(
        projection.right_traces,
        lifter,
        condensed,
        endpoint_rows,
        mpc=floquet.mpc,
        constraint_data=constraint_data,
    )
    raw_left, raw_right = lifted_endpoint_columns(
        projection.left_traces,
        lifter,
        condensed,
        endpoint_rows,
        mpc=floquet.mpc,
        constraint_data=constraint_data,
    )
    negative_left, negative_right = lifted_endpoint_columns(
        negative_traces,
        lifter,
        condensed,
        endpoint_rows,
        mpc=floquet.mpc,
        constraint_data=constraint_data,
    )
    inverse_gram = np.linalg.inv(projection.gram)
    petrov_left = raw_left @ inverse_gram.conj().T
    petrov_right = raw_right @ inverse_gram.conj().T
    timings["qep_projection_and_endpoint_lifts"] = time.perf_counter() - stage
    trial_block = np.zeros((2400, 240), dtype=np.complex128)
    trial_block[:1200, :120] = right_left
    trial_block[1200:, 120:] = right_right
    test_block = np.zeros((2400, 240), dtype=np.complex128)
    test_block[:1200, :120] = petrov_left
    test_block[1200:, 120:] = petrov_right
    stage = time.perf_counter()
    projected_action = test_block.conj().T @ action.apply_columns(trial_block)
    live_port = ProjectedTwoPortSchur(
        S_LL=projected_action[:120, :120].copy(),
        S_LR=projected_action[:120, 120:].copy(),
        S_RL=projected_action[120:, :120].copy(),
        S_RR=projected_action[120:, 120:].copy(),
        port_rows=2400,
        interior_rows=action.interior_rows,
        interior_matrix_nnz=action.interior_matrix_nnz,
    )
    timings["live_basis_projected_port_action"] = time.perf_counter() - stage

    stored_port, stored_negative = _load_projected_schur(args.projected_blocks)
    frozen_port_coordinate_relative = _relative(
        _small_port_matrix(stored_port), _small_port_matrix(live_port)
    )
    frozen_negative_coordinate_relative = _relative(
        stored_negative, negative_coordinates
    )

    with np.load(args.exact_traces) as archive:
        z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
        exact_trace_values = np.asarray(
            archive["Et_canonical_owned_dofs"], dtype=np.complex128
        )
    with np.load(args.exact_coefficients) as archive:
        coefficient_z = np.asarray(archive["z_nm"], dtype=np.float64)
        frozen_coefficients = np.asarray(
            archive["coefficients"], dtype=np.complex128
        )
    expected_z = np.linspace(10.0, 110.0, 11)
    if not np.array_equal(z_nm, expected_z) or not np.array_equal(
        coefficient_z, expected_z
    ):
        raise RuntimeError("Frozen exact planes are not 10:10:110 nm.")
    exact_traces = [
        _trace_function_from_global(spaces.transverse, values)
        for values in exact_trace_values
    ]
    exact_coefficients = np.stack(
        [projection.project(trace) for trace in exact_traces]
    )
    coefficient_replay_relative = _relative(
        exact_coefficients, frozen_coefficients
    )
    electric_plane_residual = [
        projection.relative_residual(trace, coefficient)
        for trace, coefficient in zip(
            exact_traces, exact_coefficients, strict=True
        )
    ]
    exact_left, exact_right = lifted_endpoint_columns(
        exact_traces,
        lifter,
        condensed,
        endpoint_rows,
        mpc=floquet.mpc,
        constraint_data=constraint_data,
    )
    exact_cell_trace = np.vstack(
        (exact_left[:, :-1], exact_right[:, 1:])
    )
    stage = time.perf_counter()
    exact_cell_flux = action.apply_columns(exact_cell_trace)
    timings["exact_cauchy_action_10_cells"] = time.perf_counter() - stage
    left_flux = exact_cell_flux[: len(endpoint_rows.left_active), :]
    right_flux = exact_cell_flux[len(endpoint_rows.left_active) :, :]
    continuity = []
    for plane in range(1, 10):
        residual = right_flux[:, plane - 1] + left_flux[:, plane]
        continuity.append(
            float(
                np.linalg.norm(residual)
                / max(
                    np.linalg.norm(right_flux[:, plane - 1]),
                    np.linalg.norm(left_flux[:, plane]),
                    1.0e-30,
                )
            )
        )

    lam = np.asarray(scalar.forward.factors, dtype=np.complex128)
    mu = np.asarray(scalar.backward.factors, dtype=np.complex128)
    directional_trace = np.column_stack(
        (
            np.vstack((right_left, right_right * lam[np.newaxis, :])),
            np.vstack(
                (
                    negative_left * mu[np.newaxis, :],
                    negative_right,
                )
            ),
        )
    )
    stage = time.perf_counter()
    directional_flux = action.apply_columns(directional_trace)
    timings["directional_cauchy_basis_action"] = time.perf_counter() - stage
    _electric_coefficients, electric_fit = _fit_columns(
        directional_trace, exact_cell_trace
    )
    _traction_coefficients, traction_fit = _fit_columns(
        directional_flux, exact_cell_flux
    )
    electric_scale = max(np.linalg.norm(exact_cell_trace), 1.0e-30)
    traction_scale = max(np.linalg.norm(exact_cell_flux), 1.0e-30)
    joint_basis = np.vstack(
        (
            directional_trace / electric_scale,
            directional_flux / traction_scale,
        )
    )
    joint_target = np.vstack(
        (
            exact_cell_trace / electric_scale,
            exact_cell_flux / traction_scale,
        )
    )
    _joint_coefficients, joint_fit = _fit_columns(joint_basis, joint_target)

    right_self = _overlap_matrix(
        projection.mass, projection.right_traces, projection.right_traces
    )
    left_self = _overlap_matrix(
        projection.mass, projection.left_traces, projection.left_traces
    )
    left_right = projection.gram
    right_whitener, right_gram = _positive_invsqrt(right_self)
    left_whitener, left_gram = _positive_invsqrt(left_self)
    whitened_pair = left_whitener @ left_right @ right_whitener
    port_singular = np.linalg.svd(whitened_pair, compute_uv=False)
    port_pair = {
        "right_self_gram": right_gram,
        "left_self_gram": left_gram,
        "raw_left_right_condition": float(np.linalg.cond(left_right)),
        "basis_invariant_whitened_condition": float(
            port_singular[0] / port_singular[-1]
        ),
        "inf_sup_smallest_singular_value": float(port_singular[-1]),
        "largest_singular_value": float(port_singular[0]),
    }

    port_lengths: dict[str, Any] = {}
    actual_specs = (
        ("40nm_z40_z80", 4, 3, 7),
        ("60nm_z30_z90", 6, 2, 8),
        ("100nm_z10_z110", 10, 0, 10),
    )
    for label, cells, first_plane, last_plane in actual_specs:
        exact_projected, composition = _repeat_port(live_port, cells)
        modal_matrix, modal_build = _modal_port_matrix(
            live_port,
            negative_coordinates,
            lam,
            mu,
            cells,
        )
        exact_matrix = _small_port_matrix(exact_projected)
        port_lengths[label] = {
            "stable_composition": {
                "steps": len(composition),
                "max_pivot_condition": float(
                    max(
                        (item["pivot_condition"] for item in composition),
                        default=0.0,
                    )
                ),
                "max_pivot_solve_relative_residual": float(
                    max(
                        (
                            item["pivot_solve_relative_residual"]
                            for item in composition
                        ),
                        default=0.0,
                    )
                ),
                "dense_full_interface_square_formed": False,
                "only_replicated_square_shape": [240, 240],
            },
            "selected_operator": {
                **modal_build,
                "exact_fe_to_current_modal_frobenius_relative": _relative(
                    exact_matrix, modal_matrix
                ),
            },
            "actual_full3d_trace": _port_actual_report(
                label=label,
                cells=cells,
                first_plane=first_plane,
                last_plane=last_plane,
                exact_coefficients=exact_coefficients,
                exact_left_flux=left_flux,
                exact_right_flux=right_flux,
                test_block=test_block,
                exact_projected=exact_projected,
                modal_matrix=modal_matrix,
            ),
        }

    requested_planes: dict[str, Any] = {}
    for plane in (0, 2, 3, 7, 8, 10):
        entries = []
        if plane > 0:
            entries.append(
                {
                    "side": "lower_cell_right",
                    "norm": float(np.linalg.norm(right_flux[:, plane - 1])),
                    "sha256": hashlib.sha256(
                        np.ascontiguousarray(
                            right_flux[:, plane - 1]
                        ).view(np.uint8)
                    ).hexdigest(),
                }
            )
        if plane < 10:
            entries.append(
                {
                    "side": "upper_cell_left",
                    "norm": float(np.linalg.norm(left_flux[:, plane])),
                    "sha256": hashlib.sha256(
                        np.ascontiguousarray(left_flux[:, plane]).view(
                            np.uint8
                        )
                    ).hexdigest(),
                }
            )
        requested_planes[f"z{int(z_nm[plane])}"] = {
            "z_nm": float(z_nm[plane]),
            "electric_projection_relative": electric_plane_residual[plane],
            "weak_conormal_sides": entries,
            "interior_cancellation_relative": (
                None if plane in (0, 10) else continuity[plane - 1]
            ),
        }

    cauchy_archive = _write_npz(
        args.work_dir / "exact_cauchy_traces.npz",
        {
            "z_nm": z_nm,
            "Et_canonical_owned_dofs": exact_trace_values,
            "middle_weak_conormal_left_by_cell": left_flux.T,
            "middle_weak_conormal_right_by_cell": right_flux.T,
        },
        comm,
    )

    # Build, but do not solve, the original 10/110 Hybrid local operators.
    # Their direct factors are reused only for the sixteen external-channel
    # adjoints below.
    stage = time.perf_counter()
    bottom = assemble_hybrid_local_dtn_system(
        authority,
        "bottom",
        bottom_interface_z_nm=10.0,
        top_interface_z_nm=110.0,
        comm=comm,
        log=None,
    )
    top = assemble_hybrid_local_dtn_system(
        authority,
        "top",
        bottom_interface_z_nm=10.0,
        top_interface_z_nm=110.0,
        comm=comm,
        log=None,
    )
    coupling = build_hybrid_internal_mode_coupling(
        authority,
        spaces,
        positive,
        negative,
        bottom,
        top,
        length_nm=100.0,
        propagation_model="full3d_uniform_cg",
        modal_traction_model="scalar_cg_discrete_derivative",
        log=None,
    )
    timings["local_operator_and_coupling_reassembly"] = time.perf_counter() - stage
    lam_100 = np.asarray(coupling.propagation.forward.factors)
    mu_100 = np.asarray(coupling.propagation.backward.factors)
    mapping = np.asarray(coupling.negative_trace_to_positive)
    resolver = np.block(
        [
            [np.eye(120), mapping * mu_100[np.newaxis, :]],
            [lam_100[:, np.newaxis] * np.eye(120), mapping],
        ]
    )
    endpoints = np.concatenate(
        (exact_coefficients[0], exact_coefficients[-1])
    )
    directional = np.linalg.solve(resolver, endpoints)
    forward_amplitude = directional[:120]
    backward_amplitude = directional[120:]
    bottom_load = _matrix_action(
        coupling.bottom.positive_traction, forward_amplitude
    ) + _matrix_action(
        coupling.bottom.negative_traction, mu_100 * backward_amplitude
    )
    top_load = _matrix_action(
        coupling.top.positive_traction, lam_100 * forward_amplitude
    ) + _matrix_action(
        coupling.top.negative_traction, backward_amplitude
    )
    coupling_record = {
        "endpoint_directional_resolver_condition": float(
            np.linalg.cond(resolver)
        ),
        "bottom_current_modal_load_norm": float(np.linalg.norm(bottom_load)),
        "top_current_modal_load_norm": float(np.linalg.norm(top_load)),
        "dense_interface_square_formed": coupling.dense_interface_square_formed,
        "ordinary_hybrid_forward_solve_run": False,
    }
    coupling.destroy()

    old_orders = _orders(args.old_hybrid_record)
    full_orders = _orders(args.full3d_orders)
    bottom_channels = [
        item for item in PERSISTENT_CHANNELS if item[0] == "bottom"
    ]
    top_channels = [item for item in PERSISTENT_CHANNELS if item[0] == "top"]
    stage = time.perf_counter()
    bottom_results, bottom_vectors = _channel_adjoint_audit(
        bottom,
        bottom_channels,
        current_load=bottom_load,
        exact_flux=left_flux[:, 0],
        old_orders=old_orders,
        full_orders=full_orders,
        authority=authority,
        cross_section=cross_section,
        spaces=spaces,
        lifter=lifter,
        condensed=condensed,
        endpoint_rows=endpoint_rows,
        one_cell_mpc=floquet.mpc,
        one_cell_constraint_data=constraint_data,
    )
    timings["bottom_eight_channel_adjoints"] = time.perf_counter() - stage
    bottom.destroy()
    stage = time.perf_counter()
    top_results, top_vectors = _channel_adjoint_audit(
        top,
        top_channels,
        current_load=top_load,
        exact_flux=right_flux[:, -1],
        old_orders=old_orders,
        full_orders=full_orders,
        authority=authority,
        cross_section=cross_section,
        spaces=spaces,
        lifter=lifter,
        condensed=condensed,
        endpoint_rows=endpoint_rows,
        one_cell_mpc=floquet.mpc,
        one_cell_constraint_data=constraint_data,
    )
    timings["top_eight_channel_adjoints"] = time.perf_counter() - stage
    top.destroy()
    channel_results = bottom_results + top_results
    sensitivity_vectors = np.stack(bottom_vectors + top_vectors)
    predictions = np.asarray(
        [
            item["local_fixed_trace_prediction_old_minus_full3d"]
            for item in channel_results
        ],
        dtype=np.complex128,
    )
    actual = np.asarray(
        [
            item["actual_old_minus_full3d_solver_coordinate"]
            for item in channel_results
        ],
        dtype=np.complex128,
    )
    sensitivity_archive = _write_npz(
        args.work_dir / "persistent_channel_interface_adjoints.npz",
        {
            "interface_adjoint_trace_rows": sensitivity_vectors,
            "local_fixed_trace_predictions": predictions,
            "actual_old_minus_full3d": actual,
        },
        comm,
    )
    sensitivity_svd = _svd_summary(sensitivity_vectors)
    sensitivity_summary = {
        "channels": channel_results,
        "raw_archive": sensitivity_archive,
        "adjoint_trace_svd": sensitivity_svd,
        "prediction_vector_relative_error": _relative(predictions, actual),
        "prediction_actual_absolute_cosine": float(
            abs(np.vdot(predictions, actual))
            / max(
                np.linalg.norm(predictions) * np.linalg.norm(actual),
                1.0e-30,
            )
        ),
        "interpretation_limit": (
            "Each adjoint is the exact static local-endcap Hermitian adjoint "
            "with the Full3D interface trace frozen.  It is an interface "
            "sensitivity diagnostic, not a coupled monolithic Hybrid adjoint."
        ),
    }

    payload = {
        "schema_version": "task036.exact-cauchy-port-audit.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "audit_complete_no_actual_candidate_run",
        "metadata": {
            "source_sha": source_sha,
            "branch": _git("branch", "--show-current"),
            "mpi_size": comm.size,
            "scalar_type": str(np.dtype(PETSc.ScalarType)),
            "int_type": str(np.dtype(PETSc.IntType)),
            "command": "python -m benchmarks.run_task036_exact_cauchy_port_audit "
            + " ".join(shlex.quote(item) for item in sys.argv[1:]),
            "scope": (
                "offline frozen-trace replay plus one-cell/local-operator "
                "reassembly; no Full3D or Hybrid forward PDE"
            ),
        },
        "inputs": {
            str(path): {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in inputs
        },
        "one_cell_identity": {
            **row_record,
            "matches_frozen_oracle": row_identity_match,
        },
        "qep": qep_record,
        "trace_basis": {
            "mode_count_per_direction": 120,
            "electric_trace_dofs": projection.global_trace_dofs,
            "coefficient_replay_relative": coefficient_replay_relative,
            "coordinate_replay_interpretation": (
                "diagnostic only: a rebuilt non-normal near-degenerate QEP "
                "basis may rotate or rephase inside the same physical span"
            ),
            "frozen_to_live_projected_port_coordinate_relative": (
                frozen_port_coordinate_relative
            ),
            "frozen_to_live_negative_map_coordinate_relative": (
                frozen_negative_coordinate_relative
            ),
            "negative_trace": negative_record,
            "port_pair_gram_and_inf_sup": port_pair,
        },
        "exact_cauchy": {
            "definition": (
                "E_t is the archived exact Full3D tangential trace.  The "
                "magnetic member is the exact discrete variational weak "
                "conormal from the same p5/h10 one-cell Schur action; it is "
                "physically proportional to n cross H under the common "
                "Maxwell scaling and is not a sampled pointwise H field."
            ),
            "requested_planes": requested_planes,
            "all_internal_conormal_cancellation_relative": continuity,
            "electric_best_approximation": electric_fit,
            "magnetic_traction_best_approximation": traction_fit,
            "joint_cauchy_best_approximation": joint_fit,
            "joint_norm_contract": (
                "electric and weak-conormal independent-coordinate 2-norms "
                "are separately normalized by their frozen ten-cell "
                "aggregate norm before the joint least-squares fit"
            ),
            "raw_archive": cauchy_archive,
        },
        "port_operator": {
            "lengths": port_lengths,
            "composition_contract": (
                "stable small Petrov star products are replayed from the "
                "frozen one-cell blocks; actual Full3D port action uses the "
                "ten exact one-cell conormals and verifies internal flux "
                "cancellation without forming R D, I-RD, or a dense 2400 "
                "by 2400 interface square"
            ),
            "current_modal_coupling_replay": coupling_record,
        },
        "persistent_failing_channel_sensitivity": sensitivity_summary,
        "frozen_enrichment_decision": {
            "selected_family": "transfer_optimal_port_modes",
            "other_families_not_selected": [
                "cauchy_complete_discrete_bloch_correctors",
                "failing_channel_adjoint_modes",
            ],
            "implementation_status": "not_implemented_waiting_for_review",
            "target": (
                "restore interfaces to 10/110 nm, keep the M120 core across "
                "100 nm, and place any added transfer-optimal correctors only "
                "inside the two short end buffers followed by local Schur "
                "condensation"
            ),
        },
        "timing_seconds": {
            **timings,
            "total": time.perf_counter() - started,
        },
        "forbidden_work": {
            "new_hybrid_forward_pde": False,
            "full3d_rerun": False,
            "m_sweep": False,
            "iterative_solver_development": False,
            "hp_or_wavelength_continuation": False,
            "rcwa_development": False,
            "ordinary_default_changed": False,
        },
    }
    _write_json(args.output, payload, comm)
    action.destroy()
    condensed.destroy()
    projection.destroy()
    negative.destroy()
    positive.destroy()
    operators.destroy()
    _progress(comm, f"complete in {time.perf_counter() - started:.3f} s")


if __name__ == "__main__":
    main()
