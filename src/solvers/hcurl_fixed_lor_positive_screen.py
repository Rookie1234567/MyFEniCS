"""Task040 V9-E fixed-LOR positive screen.

This module is the thin numerical entry point for the opt-in L2c route.  It
uses the existing mesh, Floquet, condensation, fixed-LOR bridge, and bounded
trace-service implementations; it does not implement a second runner.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hcurl_fixed_lor_trace_service import (
    build_fixed_lor_trace_service,
)
from src.solvers.static_local_schur_action import create_static_local_schur_action

V9_E_LOR_L2_ONLY_FLAG = "--v9-e-lor-l2-only"
V9_E_LOR_L2_ONLY_METHOD = "task040_v9_e_lor_l2_only"
V9_E_LOR_L2_ROUTE = "V9_E_LOR_L2"
V9_E_LOR_L2_ONLY_SCHEMA = "task040.v9_e.lor_l2_only.v1"
V9_E_LOR_L2_ONLY_PROFILE_ID = "task040.v9_e.lor.l2_only.v1"
V9_E_LOR_L2_ONLY_HARD_STOP_BYTES = 45 * 2**30
V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS = 21600
V9_E_LOR_L2_MPI_SIZE = 8
V9_E_LOR_L2_ALLOWED_INPUTS = (
    "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat",
    "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat",
)
V9_E_LOR_L2_MARKER_SEQUENCE = (
    "v9_e_lor_l2_preflight",
    "v9_e_lor_l2_mesh_ready",
    "v9_e_lor_l2_space_ready",
    "v9_e_lor_l2_floquet_ready",
    "v9_e_lor_l2_positive_form_ready",
    "v9_e_lor_l2_condensed_ready",
    "v9_e_lor_l2_action_ready",
    "v9_e_lor_l2_bridge_begin",
    "v9_e_lor_l2_bridge_ready",
    "v9_e_lor_l2_service_ready",
    "v9_e_lor_l2_rhs_ready",
    "v9_e_lor_l2_solve_begin",
    "v9_e_lor_l2_checkpoint",
    "v9_e_lor_l2_solve_end",
    "v9_e_lor_l2_explicit_residual",
    "v9_e_lor_l2_cleanup_complete",
)
V9_E_LOR_L2_PASS = "V9_E_LOR_L2_ONLY_ACTION_PASS"
V9_E_LOR_L2_FAIL = "V9_E_LOR_L2_ONLY_ACTION_FAIL"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _validate_input(input_path: str | Path, input_sha256: str) -> Path:
    resolved = Path(input_path).resolve()
    allowed = {Path(item).resolve() for item in V9_E_LOR_L2_ALLOWED_INPUTS}
    if resolved not in allowed:
        raise ValueError("L2c accepts only the two official input files")
    if _sha256(resolved) != input_sha256:
        raise RuntimeError("L2c input SHA256 does not match supplied identity")
    return resolved


def _marker(
    stage: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    comm: MPI.Comm,
    started: float,
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    counted_action: Any = None,
    service: Any = None,
    **detail: Any,
) -> None:
    local_wall = time.monotonic() - started
    wall = comm.allreduce(local_wall, op=MPI.MAX)
    resource = resource_callback() if resource_callback is not None else {}
    payload = dict(detail)
    payload["cross_rank_wall_seconds"] = float(wall)
    payload["resource"] = _json_value(resource)
    payload["action_apply_count"] = int(
        getattr(counted_action, "apply_count", 0)
    )
    payload["service_pc_apply_count"] = int(
        getattr(service, "audit", {}).get("apply_count", 0)
    )
    if marker_callback is not None:
        marker_callback(stage, _json_value(payload))


def _research_cell_tags(mesh):
    from dolfinx.mesh import meshtags

    tdim = mesh.topology.dim
    local_cells = mesh.topology.index_map(tdim).size_local
    cells = np.arange(local_cells, dtype=np.int32)
    values = np.ones(local_cells, dtype=np.int32)
    return meshtags(mesh, tdim, cells, values)


def _research_form(mesh, function_space, tags):
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh, subdomain_data=tags)
    return fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(1.0) * ufl.inner(u, v)
        )
        * dx(1)
    )


def _class_keys(condensed: Any) -> list[tuple[Any, ...]]:
    retained = condensed.retained_local_schur_by_class
    keys = list(retained)
    if not keys:
        raise RuntimeError("L2c condensation retained no local Schur classes")
    return keys


def _build_bridges(condensed: Any) -> dict[tuple[Any, ...], Any]:
    from src.solvers.hcurl_fixed_lor_cell_bridge import (
        build_fixed_p6_lor_cell_bridge,
    )

    bridges = {}
    for key in _class_keys(condensed):
        if len(key) != 5:
            raise RuntimeError("L2c class key must be (tag, wx, wy, wz, cell_info)")
        tag, wx, wy, wz, cell_info = key
        if int(tag) != 1:
            raise RuntimeError("L2c research cell tag must be 1")
        bridges[key] = build_fixed_p6_lor_cell_bridge(
            (float(wx), float(wy), float(wz)),
            curl_coefficient=1.0 + 0.0j,
            mass_coefficient=1.0 + 0.0j,
            cell_info=int(cell_info),
        )
    return bridges


def _deterministic_probe(vector: PETSc.Vec) -> PETSc.Vec:
    start, stop = vector.getOwnershipRange()
    indices = np.arange(start, stop, dtype=np.float64)
    values = np.sin(indices + 0.25) + 1j * np.cos(0.5 * indices + 0.75)
    vector.setArray(np.asarray(values, dtype=PETSc.ScalarType))
    return vector


def _explicit_true_residual(
    operator: PETSc.Mat, solution: PETSc.Vec, rhs: PETSc.Vec
) -> float:
    applied = operator.createVecLeft()
    try:
        operator.mult(solution, applied)
        applied.axpy(-1.0, rhs)
        numerator = applied.norm()
        denominator = rhs.norm()
        return float(numerator / max(denominator, np.finfo(float).tiny))
    finally:
        applied.destroy()


class _CountingActionContext:
    def __init__(self, borrowed: PETSc.Mat):
        self.borrowed = borrowed
        self.apply_count = 0
        self.destroyed = False

    def mult(self, _matrix: PETSc.Mat, source: PETSc.Vec, target: PETSc.Vec):
        if self.destroyed:
            raise RuntimeError("counted action has been destroyed")
        self.apply_count += 1
        self.borrowed.mult(source, target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        self.destroyed = True
        self.borrowed = None


def _create_counted_action(
    borrowed: PETSc.Mat,
) -> tuple[PETSc.Mat, _CountingActionContext]:
    context = _CountingActionContext(borrowed)
    counted = PETSc.Mat().createPython(
        borrowed.getSizes(), comm=borrowed.getComm()
    )
    counted.setPythonContext(context)
    counted.setUp()
    return counted, context


class _ServicePCContext:
    def __init__(self, service: Any):
        self.service = service
        self.apply_count = 0
        self.destroyed = False

    def apply(
        self, pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        if self.destroyed:
            raise RuntimeError("service PC context has been destroyed")
        self.apply_count += 1
        self.service.apply(pc, source, target)

    def destroy(self, _pc: PETSc.PC | None = None) -> None:
        self.destroyed = True
        self.service = None


def _run_fixed_right_fgmres(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    service: Any,
    checkpoint_callback: Callable[[int, float], None] | None = None,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    comm = operator.getComm()
    ksp = PETSc.KSP().create(comm)
    ksp_destroyed = False
    pc_context = _ServicePCContext(service)
    checkpoints = {0, 8, 16, 32, 64, 128, 256}
    history: list[float] = []
    checkpoint_values: dict[str, float] = {}
    diagnostics: dict[str, Any] = {
        "ksp_type": "fgmres",
        "pc_side": "right",
        "restart": 64,
        "max_it": 256,
        "rtol": 1.0e-8,
        "atol": 0.0,
        "norm_type": "unpreconditioned",
        "initial_guess_nonzero": False,
        "zero_initial_guess": True,
        "history": history,
        "checkpoints": checkpoint_values,
        "ksp_destroyed": False,
        "pc_context_destroyed_after_ksp_destroy": False,
    }
    solution = operator.createVecRight()
    completed = False

    def monitor(_ksp: PETSc.KSP, iteration: int, residual: float) -> None:
        value = float(residual)
        history.append(value)
        if iteration in checkpoints:
            checkpoint_values[str(iteration)] = value
            if checkpoint_callback is not None:
                checkpoint_callback(iteration, value)

    try:
        solution.set(0.0)
        ksp.setOperators(operator)
        ksp.setType("fgmres")
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(64)
        ksp.setTolerances(rtol=1.0e-8, atol=0.0, max_it=256)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        ksp.setInitialGuessNonzero(False)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(pc_context)
        observed_pc_side = ksp.getPCSide()
        diagnostics["ksp_type"] = str(ksp.getType())
        diagnostics["pc_side"] = (
            "right"
            if observed_pc_side == PETSc.PC.Side.RIGHT
            else str(observed_pc_side)
        )
        ksp.setMonitor(monitor)
        ksp.solve(rhs, solution)
        action_context = operator.getPythonContext()
        diagnostics.update(
            {
                "reason": int(ksp.getConvergedReason()),
                "iterations": int(ksp.getIterationNumber()),
                "service_pc_apply_count": int(pc_context.apply_count),
                "pc_type": str(pc.getType()).lower(),
                "exact_action_apply_count": int(
                    action_context.apply_count
                ),
            }
        )
        completed = True
    finally:
        if not ksp_destroyed:
            ksp.destroy()
            pc_context.destroy()
            ksp_destroyed = True
        diagnostics["ksp_destroyed"] = True
        diagnostics["pc_context_destroyed_after_ksp_destroy"] = bool(
            pc_context.destroyed
        )
        if not completed:
            solution.destroy()
    return solution, diagnostics


def _bridge_bytes(bridge: Any) -> tuple[int, int]:
    lifecycle = bridge.audit["lifecycle"]
    return (
        int(lifecycle.get("retained_trace_bridge_bytes", 0)),
        int(lifecycle.get("selected_transient_array_bytes_not_peak", 0)),
    )


def _service_bytes(audit: Mapping[str, Any]) -> tuple[int, int]:
    return (
        int(audit.get("retained_numpy_factor_map_bytes_not_peak", 0)),
        int(audit.get("retained_work_vector_payload_bytes_not_peak", 0)),
    )


def run_v9_e_lor_l2_only(
    *,
    cfg: Mapping[str, Any],
    comm: MPI.Comm,
    input_path: str | Path,
    run_directory: str | Path,
    source_sha: str,
    input_sha256: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    watchdog_enabled: bool = False,
    bottom_route_only: bool = False,
    watchdog_hard_stop_bytes: int = V9_E_LOR_L2_ONLY_HARD_STOP_BYTES,
    physical_model_sha256: str = "",
) -> dict[str, Any]:
    """Run one fixed-LOR P+ action-only case and return its audit summary."""
    resolved_input = _validate_input(input_path, input_sha256)
    if comm.size != V9_E_LOR_L2_MPI_SIZE:
        raise RuntimeError("L2c requires the fixed MPI8 route")
    if not watchdog_enabled or not bottom_route_only:
        raise RuntimeError("L2c requires watchdog-enabled bottom-route execution")
    if int(watchdog_hard_stop_bytes) != V9_E_LOR_L2_ONLY_HARD_STOP_BYTES:
        raise RuntimeError("L2c hard memory line is fixed at 45 GiB")

    logger = logging.getLogger("task040.v9_e_lor_l2")
    run_path = Path(run_directory)
    run_path.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    lifecycle: dict[str, Any] = {
        "ksp_destroyed": False,
        "pc_context_destroyed_after_ksp_destroy": False,
        "service_destroyed": False,
        "bridges_destroyed": False,
        "counted_action_destroyed": False,
        "static_action_destroyed": False,
        "condensed_destroyed": False,
        "mpc_destroyed": False,
        "cleanup_complete": False,
    }
    result: dict[str, Any] = {
        "schema_version": V9_E_LOR_L2_ONLY_SCHEMA,
        "method": V9_E_LOR_L2_ONLY_METHOD,
        "route": V9_E_LOR_L2_ROUTE,
        "input_path": str(resolved_input),
        "input_sha256": input_sha256,
        "source_sha": source_sha,
        "physical_model_sha256": physical_model_sha256,
        "scalar_type": str(np.dtype(PETSc.ScalarType)),
        "int_type": str(PETSc.IntType),
        "watchdog_enabled": watchdog_enabled,
        "bottom_route_only": bottom_route_only,
        "lifecycle": lifecycle,
        "official_rta": {"status": "not_run"},
    }
    mesh_data = None
    mesh = None
    function_space = None
    floquet_data = None
    mpc = None
    condensed = None
    static_action = None
    static_context = None
    counted_action = None
    counted_context = None
    service = None
    bridges: dict[tuple[Any, ...], Any] = {}
    solution = None
    rhs = None
    probe = None

    try:
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[0],
            marker_callback,
            comm,
            started,
            resource_callback,
            method=V9_E_LOR_L2_ONLY_METHOD,
        )
        mesh_data = build_airbox_mesh_3d(cfg, run_path)
        mesh = mesh_data.mesh
        result["cells"] = int(mesh.topology.index_map(mesh.topology.dim).size_global)
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[1],
            marker_callback,
            comm,
            started,
            resource_callback,
            cells=result["cells"],
        )
        function_space = _create_nedelec_space(mesh, cfg)
        result["fine_global_dofs"] = int(function_space.dofmap.index_map.size_global)
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[2],
            marker_callback,
            comm,
            started,
            resource_callback,
            fine_global_dofs=result["fine_global_dofs"],
        )
        floquet_data = build_double_floquet_mpc(
            function_space, mesh_data, cfg, log=logger.info
        )
        mpc = floquet_data.mpc
        result["floquet_constraints"] = int(floquet_data.num_constraints)
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[3],
            marker_callback,
            comm,
            started,
            resource_callback,
            floquet_constraints=result["floquet_constraints"],
        )
        tags = _research_cell_tags(mesh)
        compiled_form = _research_form(mesh, function_space, tags)
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[4],
            marker_callback,
            comm,
            started,
            resource_callback,
            curl_coefficient=1.0,
            mass_coefficient=1.0,
            additional_absorbing_shift=0.0,
        )
        condensed = build_unconstrained_assembly_time_condensation(
            compiled_form,
            function_space,
            tags,
            mpc=mpc,
            retain_local_schur_for_matrix_free=True,
            materialize_global_matrix=False,
        )
        build_audit = condensed.build_audit
        if (
            condensed.matrix is not None
            or build_audit["matrix_materialized"] is not False
            or build_audit["global_active_F_allocated"] is not False
        ):
            raise RuntimeError("L2c action-only condensation materialized a matrix")
        result["active_rows"] = int(build_audit["active_rows"])
        result["appended_rows"] = int(build_audit["appended_rows"])
        static_action, static_context = create_static_local_schur_action(condensed)
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[5],
            marker_callback,
            comm,
            started,
            resource_callback,
        )
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[6],
            marker_callback,
            comm,
            started,
            resource_callback,
        )
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[7],
            marker_callback,
            comm,
            started,
            resource_callback,
            class_count=len(_class_keys(condensed)),
        )
        bridges = _build_bridges(condensed)
        bridge_metrics = [_bridge_bytes(bridge) for bridge in bridges.values()]
        result["bridge_retained_bytes_rank_sum"] = int(
            comm.allreduce(sum(item[0] for item in bridge_metrics), op=MPI.SUM)
        )
        result["bridge_transient_bytes_rank_sum"] = int(
            comm.allreduce(sum(item[1] for item in bridge_metrics), op=MPI.SUM)
        )
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[8],
            marker_callback,
            comm,
            started,
            resource_callback,
            bridge_count_local=len(bridges),
            bridge_count_global=int(comm.allreduce(len(bridges), op=MPI.SUM)),
        )
        service = build_fixed_lor_trace_service(condensed, bridges)
        service_audit = dict(service.audit)
        factor_bytes, work_bytes = _service_bytes(service_audit)
        result["pc_factor_map_bytes_rank_sum"] = int(
            comm.allreduce(factor_bytes, op=MPI.SUM)
        )
        result["pc_work_vector_payload_bytes_rank_sum"] = int(
            comm.allreduce(work_bytes, op=MPI.SUM)
        )
        result["pc_retained_bytes_rank_sum"] = (
            result["pc_factor_map_bytes_rank_sum"]
            + result["pc_work_vector_payload_bytes_rank_sum"]
        )
        result["service_audit"] = _json_value(service_audit)
        result["max_local_factor_rows_local"] = int(
            service_audit.get("max_local_factor_rows", 0)
        )
        result["max_local_factor_rows_global"] = int(
            comm.allreduce(result["max_local_factor_rows_local"], op=MPI.MAX)
        )
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[9],
            marker_callback,
            comm,
            started,
            resource_callback,
            service_factor_map_bytes_local=factor_bytes,
            service_work_vector_bytes_local=work_bytes,
            service_pc_retained_bytes_rank_sum=result["pc_retained_bytes_rank_sum"],
            service_audit=service_audit,
            service=service,
        )
        for bridge in bridges.values():
            bridge.destroy()
        lifecycle["bridges_destroyed"] = all(
            bridge.destroyed for bridge in bridges.values()
        )
        bridges = {}
        counted_action, counted_context = _create_counted_action(static_action)
        probe = _deterministic_probe(counted_action.createVecRight())
        rhs = counted_action.createVecLeft()
        counted_action.mult(probe, rhs)
        result["rhs_norm"] = float(rhs.norm())
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[10],
            marker_callback,
            comm,
            started,
            resource_callback,
            counted_action=counted_context,
            service=service,
            rhs_norm=result["rhs_norm"],
        )

        def checkpoint(iteration: int, residual: float) -> None:
            _marker(
                V9_E_LOR_L2_MARKER_SEQUENCE[12],
                marker_callback,
                comm,
                started,
                resource_callback,
                counted_action=counted_context,
                service=service,
                iteration=iteration,
                reported_recurrence_residual=residual,
                explicit_true_residual=False,
            )

        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[11],
            marker_callback,
            comm,
            started,
            resource_callback,
            counted_action=counted_context,
            service=service,
        )
        solution, ksp_diagnostics = _run_fixed_right_fgmres(
            counted_action, rhs, service, checkpoint_callback=checkpoint
        )
        result["ksp_diagnostics"] = _json_value(ksp_diagnostics)
        lifecycle["ksp_destroyed"] = bool(ksp_diagnostics["ksp_destroyed"])
        lifecycle["pc_context_destroyed_after_ksp_destroy"] = bool(
            ksp_diagnostics["pc_context_destroyed_after_ksp_destroy"]
        )
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[13],
            marker_callback,
            comm,
            started,
            resource_callback,
            counted_action=counted_context,
            service=service,
            iterations=ksp_diagnostics.get("iterations"),
            reason=ksp_diagnostics.get("reason"),
        )
        residual = _explicit_true_residual(counted_action, solution, rhs)
        result["explicit_true_residual"] = residual
        result["final_action_apply_count"] = int(counted_context.apply_count)
        result["service_pc_apply_count"] = int(service.audit["apply_count"])
        result["service_audit"] = _json_value(dict(service.audit))
        result["status"] = (
            V9_E_LOR_L2_PASS
            if (
                math.isfinite(residual)
                and residual <= 1.0e-8
                and int(ksp_diagnostics.get("reason", 0)) > 0
                and lifecycle["pc_context_destroyed_after_ksp_destroy"]
            )
            else V9_E_LOR_L2_FAIL
        )
        result["classification"] = result["status"]
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[14],
            marker_callback,
            comm,
            started,
            resource_callback,
            counted_action=counted_context,
            service=service,
            explicit_true_residual=residual,
            finite=math.isfinite(residual),
        )
    finally:
        if counted_context is not None:
            result["final_action_apply_count"] = int(
                counted_context.apply_count
            )
        if service is not None:
            result["service_pc_apply_count"] = int(service.audit["apply_count"])
        for vector in (solution, rhs, probe):
            if vector is not None:
                vector.destroy()
        if service is not None:
            service.destroy()
            result["service_audit"] = _json_value(dict(service.audit))
            lifecycle["service_destroyed"] = bool(service.destroyed)
        if bridges:
            for bridge in bridges.values():
                bridge.destroy()
            lifecycle["bridges_destroyed"] = all(
                bridge.destroyed for bridge in bridges.values()
            )
            bridges = {}
        if counted_action is not None:
            counted_action.destroy()
            counted_context.destroy()
            lifecycle["counted_action_destroyed"] = bool(counted_context.destroyed)
        if static_action is not None:
            static_action.destroy()
            static_context.destroy()
            lifecycle["static_action_destroyed"] = bool(static_context._destroyed)
        if condensed is not None:
            condensed.destroy()
            lifecycle["condensed_destroyed"] = bool(condensed._destroyed)
        if mpc is not None:
            destroy = getattr(mpc, "destroy", None)
            if callable(destroy):
                destroy()
                lifecycle["mpc_destroyed"] = True
        lifecycle["cleanup_complete"] = all(
            lifecycle[key]
            for key in (
                "ksp_destroyed",
                "pc_context_destroyed_after_ksp_destroy",
                "service_destroyed",
                "bridges_destroyed",
                "counted_action_destroyed",
                "static_action_destroyed",
                "condensed_destroyed",
                "mpc_destroyed",
            )
        )
        result["lifecycle"] = lifecycle
        result["wall_seconds"] = float(time.monotonic() - started)
        if "status" not in result:
            result["status"] = V9_E_LOR_L2_FAIL
        result["classification"] = result["status"]
        _marker(
            V9_E_LOR_L2_MARKER_SEQUENCE[15],
            marker_callback,
            comm,
            started,
            resource_callback,
            counted_action=counted_context,
            service=service,
            lifecycle=lifecycle,
        )
    return result


__all__ = [
    "V9_E_LOR_L2_ALLOWED_INPUTS",
    "V9_E_LOR_L2_MARKER_SEQUENCE",
    "V9_E_LOR_L2_MPI_SIZE",
    "V9_E_LOR_L2_ONLY_FLAG",
    "V9_E_LOR_L2_ONLY_HARD_STOP_BYTES",
    "V9_E_LOR_L2_ONLY_METHOD",
    "V9_E_LOR_L2_ONLY_PROFILE_ID",
    "V9_E_LOR_L2_ONLY_SCHEMA",
    "V9_E_LOR_L2_ONLY_TIMEOUT_SECONDS",
    "V9_E_LOR_L2_PASS",
    "V9_E_LOR_L2_ROUTE",
    "_deterministic_probe",
    "_explicit_true_residual",
    "_run_fixed_right_fgmres",
    "run_v9_e_lor_l2_only",
]
