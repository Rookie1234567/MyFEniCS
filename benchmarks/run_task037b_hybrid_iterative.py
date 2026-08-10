"""Dedicated positive frozen Task037b M10 runner.

This module owns the frozen setup, solve, recovery, physics, canonical export,
source-authority, lifecycle, and online-record contracts without importing the
historical Task032/Task033 runners.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import argparse
import gc
import hashlib
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from benchmarks.canonical_vector_artifacts import (
    MANIFEST_SCHEMA,
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.coupling.hybrid_internal_modes import build_hybrid_internal_mode_coupling
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    hybrid_volume_absorption,
    interface_field_continuity,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    evaluate_hybrid_augmented_solution,
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_fem_modal_iterative import create_hybrid_assembled_block_action
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduIterativeConfig,
    create_action_block_ldu_preconditioner,
    solve_hybrid_block_ldu_iterative,
)
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
    create_hybrid_local_dtn_action_components,
)
from src.solvers.condensed_dtn import recover_petsc_auxiliary
from src.solvers.hybrid_local_dtn_woodbury import HybridLocalDtnWoodburyFixedAction
from src.solvers.hybrid_static_field_recovery import recover_hybrid_static_local_field
from src.solvers.hybrid_whole_endcap_fixed_smoother import (
    build_hybrid_whole_endcap_fixed_smoother_action,
)
from benchmarks.task035c_p6_h10_gates import (
    task035c_p6_h10_preflight_authority_gate,
    task037b_h1_pinned_full3d_reference_gate,
    valid_hex_digest,
)
from src.solvers.common_3d_utils import _trim_process_heap


ROOT = Path(__file__).resolve().parents[1]
M10_RECORD_SCHEMA = "task037b.v6-traction-aligned-full-block-pc.v1"
M10_QUALIFICATION_SCHEMA = "task037b.m10-frozen-positive-qualification.v1"
M10_PROFILE_ID = "task037b.m10.frozen.p6-h10.v1"
M10_MODAL_COUNT = 40
M10_REQUESTED_MODES = 120
M10_CANDIDATE_MODES = 240
M10_MPI_SIZE = 8
M10_THRESHOLD = 5.0e-9
M10_TRACTION_THRESHOLD = 1.0e-8
M10_BETA_H_CUTOFF = 1.0e4
M10_NEAR_DEGENERATE_TOLERANCE = 1.0e-6
M10_BLOCK_ROTATION_TOLERANCE = 1.0e-6

M10_LIFECYCLE_ORDER = (
    "setup",
    "solve",
    "retained_solution_postsolve",
    "bottom_recovery",
    "inter_side_cleanup",
    "top_recovery",
    "recovery_cleanup",
    "own_physics_grid",
    "precanonical_cleanup",
    "bottom_active_full_stream_cleanup",
    "top_active_full_stream_cleanup",
    "record",
)


@dataclass(frozen=True)
class FrozenM10Profile:
    """The only numerical profile accepted by this runner."""

    target: str = "hybrid"
    degree: int = 6
    h_nm: float = 10.0
    modal_degree: int = 6
    modal_h_nm: float = 10.0
    wavelength_nm: float = 13.5
    polarization_kind: str = "s"
    incident_grazing_deg: float = 10.0
    bottom_interface_nm: float = 10.0
    top_interface_nm: float = 110.0
    requested_modes: int = M10_REQUESTED_MODES
    candidate_modes: int = M10_CANDIDATE_MODES
    dtN_modes_per_endcap: int = M10_MODAL_COUNT
    internal_propagation_model: str = "full3d_uniform_cg"
    internal_traction_model: str = "scalar_cg_discrete_derivative"
    operator_identity: str = "exact_monolithic_hybrid_operator"
    solver_path: str = "block-ldu-action-full-solve"
    preconditioner_identity: str = "fixed_whole_endcap_ilu0_plus_40_mode_dtn_woodbury"
    subdomain_count: int = 1
    overlap: float = 0.0
    ilu_level: int = 0
    shift: float = 0.1
    near_degenerate_tolerance: float = M10_NEAR_DEGENERATE_TOLERANCE
    block_rotation_tolerance: float = M10_BLOCK_ROTATION_TOLERANCE
    restart: int = 90
    max_it: int = 1000
    rtol: float = M10_THRESHOLD
    initial_guess: str = "zero"
    mpi_size: int = M10_MPI_SIZE
    assembly_backend: str = "assembly_time_static_condensed"


FROZEN_M10 = FrozenM10Profile()


@dataclass
class FrozenM10Setup:
    """Owned physical/QEP/endcap state handed to the later solve stage."""

    cfg: Any
    modal_cfg: Any
    cross_section: Any
    spaces: Any
    positive: Any
    negative: Any
    bottom: Any
    top: Any
    coupling: Any
    reciprocal_pairs: tuple[Any, ...]
    mode_selection: dict[str, dict[str, int]]
    timings: dict[str, float]
    qep_release: dict[str, Any]
    _final_release_done: bool = field(default=False, init=False, repr=False)
    _final_release_state: dict[str, bool] = field(
        default_factory=dict, init=False, repr=False
    )


@dataclass
class FrozenM10LinearSolve:
    """Retained positive linear result and the vectors handed to recovery."""

    result: Any
    layout: HybridAugmentedLayout
    bottom_solution: PETSc.Vec | None
    top_solution: PETSc.Vec | None
    modal_solution: np.ndarray | None
    linear_pass: bool
    inventory: dict[str, Any]
    timings: dict[str, Any]
    release: dict[str, Any]


@dataclass
class FrozenM10Recovery:
    """Retained two-side recovery state handed to later physical stages."""

    linear: FrozenM10LinearSolve
    bottom_solution: PETSc.Vec
    top_solution: PETSc.Vec
    modal_solution: np.ndarray
    bottom_q: np.ndarray
    top_q: np.ndarray
    bottom_recovered: Any
    top_recovered: Any
    reports: dict[str, Any]
    timings: dict[str, Any]
    recovery_pass: bool
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def bottom_physical(self) -> Any:
        return self.bottom_recovered.electric_field

    @property
    def top_physical(self) -> Any:
        return self.top_recovered.electric_field

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.bottom_solution.destroy()
        self.top_solution.destroy()
        self.linear.result.destroy()
        self.modal_solution = None
        self.bottom_q = None
        self.top_q = None
        self.bottom_recovered = None
        self.top_recovered = None
        self._destroyed = True


@dataclass
class FrozenM10Physics:
    """Small own-physics and canonical evidence carrier."""

    port_power: dict[str, Any]
    traction: dict[str, Any]
    interface_continuity: dict[str, Any]
    absorption: dict[str, Any]
    external_orders: list[dict[str, Any]]
    order_audit: dict[str, Any]
    energy: dict[str, float]
    own_grid: dict[str, Any] | None
    canonical: dict[str, Any]
    cleanup: dict[str, Any]
    timings: dict[str, Any]
    own_physics_pass: bool
    canonical_pass: bool
    physics_pass: bool


def _release_frozen_m10_linear_stack(
    *,
    rhs: PETSc.Vec | None,
    operator: PETSc.Mat | None,
    operator_context: Any | None,
    block_context: Any | None,
    result: Any | None,
    components: Mapping[str, Any],
    fixed: Mapping[str, Any],
    woodbury: Mapping[str, Any],
    release_modal_schur: bool,
    exception_cleanup: bool = False,
) -> dict[str, Any]:
    """Release only the temporary solve stack in the reviewed order."""

    order: list[str] = []
    if fixed.get("bottom") is not None:
        fixed["bottom"].destroy()
        order.append("bottom_fixed_smoother")
    if fixed.get("top") is not None:
        fixed["top"].destroy()
        order.append("top_fixed_smoother")
    if woodbury.get("bottom") is not None:
        woodbury["bottom"].destroy()
        order.append("bottom_woodbury")
    if woodbury.get("top") is not None:
        woodbury["top"].destroy()
        order.append("top_woodbury")
    if release_modal_schur and result is not None:
        result.release_deferred_action_modal_schur()
        order.append("action_modal_schur")
    block_context_already_destroyed = bool(
        block_context is None or block_context._destroyed
    )
    block_context_exception_destroyed = False
    if (
        block_context is not None
        and exception_cleanup
        and not block_context_already_destroyed
    ):
        block_context.defer_action_modal_schur_release = False
        block_context.destroy()
        block_context_exception_destroyed = True
    if components.get("bottom") is not None:
        components["bottom"].destroy()
        order.append("bottom_components")
    if components.get("top") is not None:
        components["top"].destroy()
        order.append("top_components")
    if rhs is not None:
        rhs.destroy()
        order.append("outer_rhs")
    if operator is not None:
        operator.destroy()
        order.append("outer_action_matrix")
    if operator_context is not None:
        operator_context.destroy(operator)
        order.append("outer_action_context")
    checks = {
        "block_ldu_context_already_destroyed": block_context_already_destroyed,
        "block_ldu_context_destroyed": bool(
            block_context is None or block_context._destroyed
        ),
        "block_ldu_context_contract": bool(
            block_context is None
            or (
                bool(block_context._destroyed)
                if exception_cleanup
                else block_context_already_destroyed
            )
        ),
        "bottom_fixed_destroyed": fixed.get("bottom") is None
        or bool(fixed["bottom"].diagnostics["destroyed"])
        and bool(fixed["bottom"].diagnostics["lifecycle"]["factors_released"]),
        "top_fixed_destroyed": fixed.get("top") is None
        or bool(fixed["top"].diagnostics["destroyed"])
        and bool(fixed["top"].diagnostics["lifecycle"]["factors_released"]),
        "bottom_woodbury_destroyed": woodbury.get("bottom") is None
        or bool(woodbury["bottom"].diagnostics["destroyed"])
        and bool(woodbury["bottom"].diagnostics["owned_action_data_released"]),
        "top_woodbury_destroyed": woodbury.get("top") is None
        or bool(woodbury["top"].diagnostics["destroyed"])
        and bool(woodbury["top"].diagnostics["owned_action_data_released"]),
        "bottom_components_destroyed": components.get("bottom") is None
        or bool(components["bottom"]._destroyed),
        "top_components_destroyed": components.get("top") is None
        or bool(components["top"]._destroyed),
        "outer_action_matrix_destroyed": operator is None or int(operator.handle) == 0,
        "outer_action_context_destroyed": operator_context is None
        or bool(operator_context._destroyed),
    }
    if release_modal_schur:
        checks["action_modal_schur_destroyed"] = bool(
            block_context is not None
            and block_context.action_modal_schur_system.diagnostics["destroyed"]
        )
    return {
        "order": order,
        "checks": checks,
        "pass": bool(all(checks.values())),
        "action_modal_schur_released": bool(release_modal_schur and result is not None),
        "block_ldu_context_exception_cleanup": block_context_exception_destroyed,
    }


def solve_frozen_m10_linear(
    setup: FrozenM10Setup,
    *,
    log=None,
) -> FrozenM10LinearSolve:
    """Run the frozen action-only outer solve and retain only recovery inputs."""

    started = time.perf_counter()
    modal_count = int(setup.coupling.internal_unknown_count)
    layout = HybridAugmentedLayout.build(setup.bottom, setup.top, modal_count)
    operator: PETSc.Mat | None = None
    operator_context = None
    rhs: PETSc.Vec | None = None
    block_context = None
    result = None
    components: dict[str, Any] = {"bottom": None, "top": None}
    fixed: dict[str, Any] = {"bottom": None, "top": None}
    woodbury: dict[str, Any] = {"bottom": None, "top": None}
    released = False

    try:
        operator, operator_context = create_hybrid_assembled_block_action(
            setup.bottom,
            setup.top,
            setup.coupling,
        )
        exact_inventory = dict(operator_context.inventory)
        if (
            exact_inventory["matrix_free"] is not True
            or exact_inventory["global_A_materialized"] is not False
            or exact_inventory["bottom_global_F_materialized"] is not False
            or exact_inventory["top_global_F_materialized"] is not False
            or int(exact_inventory["bottom_direct_factor_count"]) != 0
            or int(exact_inventory["top_direct_factor_count"]) != 0
        ):
            raise RuntimeError("Frozen M10 exact action inventory is not qualified.")

        rhs = layout.pack(
            setup.bottom.b,
            setup.top.b,
            internal_modal_rhs_correction(setup.coupling),
        )
        components["bottom"] = create_hybrid_local_dtn_action_components(setup.bottom)
        components["top"] = create_hybrid_local_dtn_action_components(setup.top)
        fixed["bottom"] = build_hybrid_whole_endcap_fixed_smoother_action(setup.bottom)
        fixed["top"] = build_hybrid_whole_endcap_fixed_smoother_action(setup.top)
        woodbury["bottom"] = HybridLocalDtnWoodburyFixedAction(
            fixed["bottom"], components["bottom"]
        )
        woodbury["top"] = HybridLocalDtnWoodburyFixedAction(
            fixed["top"], components["top"]
        )
        side_inventory: dict[str, Any] = {}
        for side in ("bottom", "top"):
            fixed_diagnostics = fixed[side].diagnostics
            woodbury_diagnostics = woodbury[side].diagnostics
            woodbury_matrix = woodbury_diagnostics["woodbury"]
            if (
                int(fixed_diagnostics["base_factor_count"]) != 1
                or int(woodbury_diagnostics["base_factor_count"]) != 1
                or int(woodbury_diagnostics["local_direct_factor_count"]) != 0
                or woodbury_diagnostics["nested_ksp_created"] is not False
                or int(woodbury_matrix["K_rank"]) != M10_MODAL_COUNT
                or not np.isfinite(float(woodbury_matrix["K_condition_number"]))
                or float(woodbury_matrix["K_condition_number"]) > 1.0e6
                or woodbury_matrix["arrays_finite"] is not True
            ):
                raise RuntimeError(
                    f"Frozen M10 {side} action inventory is not qualified."
                )
            side_inventory[side] = {
                "fixed": fixed_diagnostics,
                "woodbury": woodbury_diagnostics,
            }

        block_context = create_action_block_ldu_preconditioner(
            layout,
            setup.bottom,
            setup.top,
            setup.coupling,
            woodbury["bottom"],
            woodbury["top"],
        )
        block_inventory = dict(block_context.inventory)
        modal_inventory = block_inventory["modal_schur"]
        if (
            tuple(modal_inventory["shape"]) != (modal_count, modal_count)
            or modal_inventory["dtype"] != "complex128"
            or int(modal_inventory["rank"]) != modal_count
            or modal_inventory["finite"] is not True
            or not np.isfinite(float(modal_inventory["condition"]))
            or float(modal_inventory["condition"]) > 1.0e8
            or modal_inventory["normal_equations"] is not False
            or int(block_inventory["bottom_direct_factor_count"]) != 0
            or int(block_inventory["top_direct_factor_count"]) != 0
            or int(block_inventory["bottom_ilu_factor_count"]) != 1
            or int(block_inventory["top_ilu_factor_count"]) != 1
        ):
            raise RuntimeError("Frozen M10 block-LDU inventory is not qualified.")

        config = HybridBlockLduIterativeConfig(
            restart=FROZEN_M10.restart,
            max_it=FROZEN_M10.max_it,
            threshold=FROZEN_M10.rtol,
            initial_guess=FROZEN_M10.initial_guess,
        )
        result = solve_hybrid_block_ldu_iterative(
            operator,
            rhs,
            block_context,
            config=config,
        )
        postsolve = result.postsolve_audit
        residual_keys = (
            "reported_relative_residual",
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
        )
        linear_pass = bool(
            int(result.converged_reason) > 0
            and 0 < int(result.iterations) <= FROZEN_M10.max_it
            and postsolve["pass"] is True
            and all(
                np.isfinite(float(postsolve[key]))
                and 0.0 <= float(postsolve[key]) <= FROZEN_M10.rtol
                for key in residual_keys
            )
        )
        bottom_solution = top_solution = None
        modal_solution = None
        if linear_pass:
            bottom_solution, top_solution, modal_solution = layout.split(
                result.solution,
                setup.bottom.b,
                setup.top.b,
            )
            modal_solution = np.asarray(modal_solution, dtype=np.complex128).copy()
        release = _release_frozen_m10_linear_stack(
            rhs=rhs,
            operator=operator,
            operator_context=operator_context,
            block_context=block_context,
            result=result,
            components=components,
            fixed=fixed,
            woodbury=woodbury,
            release_modal_schur=linear_pass,
        )
        released = True
        return FrozenM10LinearSolve(
            result=result,
            layout=layout,
            bottom_solution=bottom_solution,
            top_solution=top_solution,
            modal_solution=modal_solution,
            linear_pass=linear_pass,
            inventory={
                "exact_operator": exact_inventory,
                "sides": side_inventory,
                "block_ldu": block_inventory,
                "solver": dict(result.inventory),
            },
            timings={
                "linear_solve_seconds": float(time.perf_counter() - started),
                "solver": dict(result.timing),
            },
            release=release,
        )
    finally:
        if not released:
            _release_frozen_m10_linear_stack(
                rhs=rhs,
                operator=operator,
                operator_context=operator_context,
                block_context=block_context,
                result=result,
                components=components,
                fixed=fixed,
                woodbury=woodbury,
                release_modal_schur=bool(
                    result is not None
                    and result.release.get(
                        "action_modal_schur_retained_after_pc_destroyed", False
                    )
                    and not result.release.get("action_modal_schur_released", False)
                ),
                exception_cleanup=True,
            )


def _copy_replicated_complex_vec(
    vector: PETSc.Vec,
    comm: MPI.Intracomm,
) -> np.ndarray:
    first, last = (int(value) for value in vector.getOwnershipRange())
    local = np.asarray(vector.getArray(readonly=True), dtype=np.complex128).copy()
    replicated = np.empty(int(vector.getSize()), dtype=np.complex128)
    for owned_first, owned_last, values in comm.allgather((first, last, local)):
        replicated[int(owned_first) : int(owned_last)] = np.asarray(
            values, dtype=np.complex128
        )
    return replicated


def _recover_frozen_m10_side(
    side: str,
    setup: FrozenM10Setup,
    linear: FrozenM10LinearSolve,
) -> tuple[np.ndarray, Any, dict[str, Any]]:
    system = setup.bottom if side == "bottom" else setup.top
    active_solution = (
        linear.bottom_solution if side == "bottom" else linear.top_solution
    )
    if active_solution is None:
        raise RuntimeError(f"Frozen M10 {side} recovery lacks an active solution.")

    auxiliary_vec = recover_petsc_auxiliary(system.blocks, active_solution)
    try:
        rhs = system.blocks.b_aux.copy()
        d_u = system.blocks.D.createVecLeft()
        h_q = system.blocks.H.createVecLeft()
        try:
            system.blocks.D.mult(active_solution, d_u)
            rhs.axpy(PETSc.ScalarType(-1.0), d_u)
            rhs_norm = float(rhs.norm())
            system.blocks.H.mult(auxiliary_vec, h_q)
            h_q_norm = float(h_q.norm())
            h_q.axpy(PETSc.ScalarType(-1.0), rhs)
            auxiliary_relative = float(h_q.norm() / max(h_q_norm, rhs_norm, 1.0e-30))
        finally:
            h_q.destroy()
            d_u.destroy()
            rhs.destroy()
        auxiliary = _copy_replicated_complex_vec(
            auxiliary_vec,
            system.local_mesh.mesh.comm,
        )
    finally:
        auxiliary_vec.destroy()

    mode_keys = [
        (int(mode.m), int(mode.n), str(mode.polarization))
        for mode in system.external_modes
    ]
    beta_finite = all(
        np.isfinite(complex(mode.beta).real) and np.isfinite(complex(mode.beta).imag)
        for mode in system.external_modes
    )
    polarizations = {str(mode.polarization) for mode in system.external_modes}
    mode_identity = {
        "count": len(mode_keys),
        "expected_count": M10_MODAL_COUNT,
        "unique": len(set(mode_keys)) == len(mode_keys),
        "polarizations": sorted(polarizations),
        "polarization_sp": polarizations <= {"s", "p"},
        "beta_finite": beta_finite,
        "keys": mode_keys,
    }
    q_values_finite = bool(np.all(np.isfinite(auxiliary)))
    q_report = {
        "shape": list(auxiliary.shape),
        "dtype": str(auxiliary.dtype),
        "auxiliary_relative_residual": auxiliary_relative,
        "auxiliary_finite": q_values_finite,
        "mode_identity": mode_identity,
        "pass": bool(
            auxiliary.shape == (M10_MODAL_COUNT,)
            and q_values_finite
            and np.isfinite(auxiliary_relative)
            and auxiliary_relative >= 0.0
            and auxiliary_relative <= 1.0e-10
            and mode_identity["count"] == M10_MODAL_COUNT
            and mode_identity["unique"]
            and mode_identity["polarization_sp"]
            and mode_identity["beta_finite"]
        ),
    }
    if not q_report["pass"]:
        raise RuntimeError(f"Frozen M10 {side} external-q gate failed: {q_report}")

    recovered = recover_hybrid_static_local_field(
        system,
        setup.coupling,
        active_solution,
        linear.modal_solution,
        auxiliary_override=auxiliary,
    )
    residual = recovered.full_operator_residual
    residual_keys = (
        "linear_system_rhs_norm",
        "linear_system_solution_norm",
        "linear_system_residual_norm",
        "linear_system_relative_residual",
        "reduced_trace_dtn_residual_norm",
        "eliminated_cell_interior_residual_norm",
        "eliminated_cell_interior_max_abs_residual",
    )
    residual_values = {key: float(residual[key]) for key in residual_keys}
    residual_finite_nonnegative = bool(
        all(np.isfinite(value) and value >= 0.0 for value in residual_values.values())
    )
    interior_relative = residual_values["eliminated_cell_interior_residual_norm"] / max(
        residual_values["linear_system_rhs_norm"], 1.0e-30
    )
    condensed = system.static_condensation.condensed
    build = condensed.build_audit
    trace = build["trace_constraints"]
    metadata = system.static_condensation.metadata.to_dict()
    trace_contract = bool(
        trace["status"] == "exact_mpc_trace_expansion_built"
        and trace["constraint_applied_before_global_matrix_insertion"] is True
        and trace["embedded_identity_slave_rows_allocated"] is False
        and build["embedded_mpc_slave_identity_rows_allocated"] is False
        and int(trace["full_trace_rows"])
        == int(trace["active_rows"]) + int(trace["slave_rows"])
        and int(trace["full_trace_rows"]) == int(build["trace_rows"])
        and int(trace["active_rows"]) == int(build["active_rows"])
        and int(trace["full_trace_rows"]) == int(condensed.trace_rows)
        and int(trace["active_rows"]) == int(condensed.active_rows)
        and int(build["full_rows"])
        == int(build["trace_rows"]) + int(build["interior_rows"])
        and int(build["trace_rows"])
        == int(build["active_rows"]) + int(trace["slave_rows"])
        and int(metadata["full_fe_rows"]) == int(build["full_rows"])
        and int(metadata["active_trace_rows"]) == int(build["active_rows"])
        and int(metadata["floquet_slave_rows"]) == int(trace["slave_rows"])
        and int(metadata["cell_interior_rows"]) == int(build["interior_rows"])
    )
    recovery_audit = recovered.recovery_audit
    recovery_contract = bool(
        recovery_audit["full_global_matrix_allocated"] is False
        and recovery_audit["full_trace_matrix_allocated"] is False
        and int(recovery_audit["recovered_interior_rows"])
        == int(metadata["cell_interior_rows"])
        and recovery_audit["ordinary_default_changed"] is False
    )
    streaming = recovered.streaming_audit
    streaming_contract = bool(
        streaming["full_surface_mode_matrix_retained"] is False
        and streaming["full_global_matrix_allocated"] is False
        and streaming["full_effective_rhs_reassembled_once"] is True
    )
    full_report = {
        "residuals": residual_values,
        "linear_system_relative_threshold": 1.0e-8,
        "eliminated_interior_relative_residual": interior_relative,
        "eliminated_interior_relative_threshold": 1.0e-10,
        "eliminated_interior_max_abs_threshold": 1.0e-10,
        "finite_nonnegative": residual_finite_nonnegative,
        "trace_contract": trace_contract,
        "recovery_contract": recovery_contract,
        "streaming_contract": streaming_contract,
        "pass": bool(
            residual_finite_nonnegative
            and residual_values["linear_system_relative_residual"] <= 1.0e-8
            and interior_relative <= 1.0e-10
            and residual_values["eliminated_cell_interior_max_abs_residual"] <= 1.0e-10
            and trace_contract
            and recovery_contract
            and streaming_contract
        ),
    }
    side_report = {
        "side": side,
        "external_q": q_report,
        "full_fe": full_report,
    }
    if not full_report["pass"]:
        raise RuntimeError(f"Frozen M10 {side} full-FE gate failed: {side_report}")
    return auxiliary, recovered, side_report


def recover_frozen_m10(
    setup: FrozenM10Setup,
    linear: FrozenM10LinearSolve,
    *,
    stage_callback: Callable[[str], None] | None = None,
) -> FrozenM10Recovery:
    """Recover bottom then top fields while retaining only later-stage inputs."""

    if (
        not linear.linear_pass
        or linear.release.get("pass") is not True
        or linear.bottom_solution is None
        or linear.top_solution is None
        or linear.modal_solution is None
    ):
        raise RuntimeError("Frozen M10 recovery requires a passed linear stage.")
    comm = setup.bottom.local_mesh.mesh.comm
    started = time.perf_counter()
    pre_cleanup = collective_heap_cleanup(comm)
    if not pre_cleanup["collective_call_completed"]:
        raise RuntimeError("Frozen M10 recovery pre-cleanup did not complete.")
    if stage_callback is not None:
        stage_callback("bottom_recovery")
    bottom_q, bottom_recovered, bottom_report = _recover_frozen_m10_side(
        "bottom", setup, linear
    )
    bottom_cleanup = collective_heap_cleanup(comm)
    if not bottom_cleanup["collective_call_completed"]:
        raise RuntimeError("Frozen M10 bottom recovery cleanup did not complete.")
    if stage_callback is not None:
        stage_callback("inter_side_cleanup")
    if stage_callback is not None:
        stage_callback("top_recovery")
    top_q, top_recovered, top_report = _recover_frozen_m10_side("top", setup, linear)
    top_cleanup = collective_heap_cleanup(comm)
    if not top_cleanup["collective_call_completed"]:
        raise RuntimeError("Frozen M10 top recovery cleanup did not complete.")
    if stage_callback is not None:
        stage_callback("recovery_cleanup")
    reports = {
        "bottom": bottom_report,
        "top": top_report,
        "recovery_pass": bool(
            bottom_report["external_q"]["pass"]
            and top_report["external_q"]["pass"]
            and bottom_report["full_fe"]["pass"]
            and top_report["full_fe"]["pass"]
        ),
    }
    if not reports["recovery_pass"]:
        raise RuntimeError(f"Frozen M10 recovery gate failed: {reports}")
    return FrozenM10Recovery(
        linear=linear,
        bottom_solution=linear.bottom_solution,
        top_solution=linear.top_solution,
        modal_solution=linear.modal_solution,
        bottom_q=bottom_q,
        top_q=top_q,
        bottom_recovered=bottom_recovered,
        top_recovered=top_recovered,
        reports={
            **reports,
            "cleanup": {
                "pre": pre_cleanup,
                "bottom": bottom_cleanup,
                "top": top_cleanup,
            },
        },
        timings={
            "pre_recovery_cleanup_seconds": float(
                pre_cleanup["elapsed_seconds_max_rank"]
            ),
            "bottom_recovery_cleanup_seconds": float(
                bottom_cleanup["elapsed_seconds_max_rank"]
            ),
            "top_recovery_cleanup_seconds": float(
                top_cleanup["elapsed_seconds_max_rank"]
            ),
            "recovery_total_seconds": _max_elapsed(comm, started),
        },
        recovery_pass=True,
    )


def _record_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _array_descriptor(value: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(value))
    return {
        "shape": [int(item) for item in array.shape],
        "dtype": str(array.dtype),
        "bytes": int(array.nbytes),
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }


def _write_frozen_m10_grid_payload(
    run_dir: Path,
    arrays: Mapping[str, np.ndarray],
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    expected_keys = (
        "x_nm",
        "y_nm",
        "z_nm",
        "E_V_per_m",
        "H_A_per_m",
        "modal_amplitudes",
        "bottom_q",
        "top_q",
    )
    expected_shapes = {
        "x_nm": (40,),
        "y_nm": (20,),
        "z_nm": (5,),
        "E_V_per_m": (5, 20, 40, 3),
        "H_A_per_m": (5, 20, 40, 3),
        "modal_amplitudes": (240,),
        "bottom_q": (40,),
        "top_q": (40,),
    }
    if tuple(arrays) != expected_keys:
        raise ValueError("Frozen M10 own-grid NPZ keys are not exact.")
    for name, shape in expected_shapes.items():
        value = np.asarray(arrays[name])
        if value.shape != shape or not np.all(np.isfinite(value)):
            raise ValueError(f"Frozen M10 own-grid array {name} failed its contract.")
    path = run_dir / "m10_own_grid_EH_modal_q.npz"
    payload = None
    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
        np.savez(path, **arrays)
        payload = {
            "schema_version": "task037b.m10-own-grid-EH-modal-q.v1",
            "path": _record_path(path),
            "bytes": int(path.stat().st_size),
            "sha256": _sha256(path),
            "keys": list(arrays),
            "arrays": {
                name: _array_descriptor(value) for name, value in arrays.items()
            },
        }
    return dict(comm.bcast(payload, root=0))


def _audit_frozen_m10_external_orders(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = []
    finite = True
    identity_valid = True
    for row in rows:
        m = row["m"]
        n = row["n"]
        polarization = row["polarization"]
        identity_valid = identity_valid and (
            row["side"] in {"bottom", "top"}
            and isinstance(m, int)
            and not isinstance(m, bool)
            and isinstance(n, int)
            and not isinstance(n, bool)
            and polarization in {"s", "p"}
        )
        keys.append((row["side"], int(m), int(n), polarization))
        for name in (
            "beta_per_nm",
            "total_projection",
            "incident_projection",
            "outgoing_amplitude",
            "outgoing_amplitude_at_boundary",
        ):
            value = complex(row[name])
            finite = finite and np.isfinite(value.real) and np.isfinite(value.imag)
        for name in ("power_ratio", "R", "T"):
            finite = finite and np.isfinite(float(row[name]))
    return {
        "count": len(rows),
        "unique_key_count": len(set(keys)),
        "keys_unique": len(set(keys)) == len(keys),
        "identity_valid": identity_valid,
        "all_finite": finite,
        "pass": bool(
            len(rows) == 80
            and len(set(keys)) == len(keys)
            and identity_valid
            and finite
        ),
    }


def run_frozen_m10_physics(
    setup: FrozenM10Setup,
    recovery: FrozenM10Recovery,
    run_dir: Path,
    comm: MPI.Intracomm,
    *,
    stage_callback: Callable[[str], None] | None = None,
) -> FrozenM10Physics:
    """Run own physics and audited canonical export without final qualification."""

    if (
        not recovery.recovery_pass
        or recovery.bottom_q is None
        or recovery.top_q is None
        or recovery.bottom_recovered is None
        or recovery.top_recovered is None
    ):
        raise RuntimeError("Frozen M10 physics requires passed two-side recovery.")

    solution = SimpleNamespace(
        bottom=recovery.bottom_solution,
        top=recovery.top_solution,
        modal_amplitudes=recovery.modal_solution,
    )
    started = time.perf_counter()
    if stage_callback is not None:
        stage_callback("own_physics_grid")
    validation = evaluate_hybrid_augmented_solution(
        setup.cfg,
        setup.bottom,
        setup.top,
        setup.coupling,
        solution,
        auxiliary_override=(recovery.bottom_q, recovery.top_q),
    )
    port_power = dict(validation["port_power"])
    traction_raw = validation["fe_modal_traction_equilibrium"]
    traction = {
        "role": "exact_variational_conormal_dual",
        "bottom": dict(traction_raw["bottom_dual"]),
        "top": dict(traction_raw["top_dual"]),
    }
    x_nm = (
        setup.cfg.x_min
        + (np.arange(40, dtype=np.float64) + 0.5) * setup.cfg.period_x / 40.0
    )
    y_nm = (
        setup.cfg.y_min
        + (np.arange(20, dtype=np.float64) + 0.5) * setup.cfg.period_y / 20.0
    )
    z_nm = np.asarray(
        [10.0, 30.0, 60.0, 90.0, 110.0],
        dtype=np.float64,
    )
    reconstructor = ModalFieldReconstructor(
        setup.cfg,
        setup.cross_section,
        setup.spaces,
        setup.positive,
        setup.negative,
        bottom_z_nm=FROZEN_M10.bottom_interface_nm,
        top_z_nm=FROZEN_M10.top_interface_nm,
        propagation=setup.coupling.propagation,
        positive_traction_beta_per_nm=setup.coupling.positive_traction_beta_per_nm,
        negative_traction_beta_per_nm=setup.coupling.negative_traction_beta_per_nm,
    )
    selected_planes = reconstructor.selected_planes(
        recovery.modal_solution, x_nm, y_nm, z_nm
    )
    interface_samples = reconstructor.selected_planes(
        recovery.modal_solution,
        x_nm,
        y_nm,
        np.asarray([10.0, 110.0], dtype=np.float64),
    )
    interface_continuity = interface_field_continuity(
        setup.cfg,
        setup.bottom,
        setup.top,
        recovery.bottom_solution,
        recovery.top_solution,
        interface_samples,
    )
    absorption = hybrid_volume_absorption(
        setup.cfg,
        setup.bottom,
        setup.top,
        recovery.bottom_solution,
        recovery.top_solution,
        reconstructor,
        recovery.modal_solution,
        incident_power=float(port_power["incident_power_code_units"]),
    )
    external_orders = list(validation["external_diffraction_orders"])
    order_audit = _audit_frozen_m10_external_orders(external_orders)
    energy = {
        "R": float(port_power["R_total"]),
        "T": float(port_power["T_total"]),
        "A": float(port_power["A_balance"]),
        "A_volume": float(absorption["A_volume_total"]),
    }
    energy["closure"] = energy["R"] + energy["T"] + energy["A_volume"] - 1.0
    energy["A_minus_A_volume"] = energy["A"] - energy["A_volume"]
    energy_finite = all(np.isfinite(float(value)) for value in energy.values())
    energy_pass = bool(energy_finite and abs(energy["closure"]) <= 1.0e-5)
    selected_shape = (5, 20, 40, 3)
    selected_finite = bool(
        selected_planes.electric_V_per_m.shape == selected_shape
        and selected_planes.magnetic_A_per_m.shape == selected_shape
        and np.all(np.isfinite(selected_planes.electric_V_per_m))
        and np.all(np.isfinite(selected_planes.magnetic_A_per_m))
    )
    interface_pass = bool(
        all(
            np.isfinite(
                float(interface_continuity[side]["electric_tangential"]["relative_l2"])
            )
            and float(interface_continuity[side]["electric_tangential"]["relative_l2"])
            <= 5.0e-3
            for side in ("bottom", "top")
        )
    )
    traction_pass = bool(
        all(
            np.isfinite(float(traction[side]["relative_dual"]))
            and abs(float(traction[side]["relative_dual"])) <= 1.0e-8
            for side in ("bottom", "top")
        )
    )
    own_physics_pass = bool(
        selected_finite
        and interface_pass
        and traction_pass
        and order_audit["pass"]
        and energy_pass
    )
    own_grid = None
    canonical: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    canonical_pass = False
    if own_physics_pass:
        arrays = {
            "x_nm": x_nm,
            "y_nm": y_nm,
            "z_nm": z_nm,
            "E_V_per_m": selected_planes.electric_V_per_m,
            "H_A_per_m": selected_planes.magnetic_A_per_m,
            "modal_amplitudes": recovery.modal_solution,
            "bottom_q": recovery.bottom_q,
            "top_q": recovery.top_q,
        }
        own_grid = _write_frozen_m10_grid_payload(run_dir, arrays, comm)
        del arrays
    del reconstructor
    del interface_samples
    del selected_planes
    del validation
    del solution
    if own_physics_pass:
        pre_canonical_cleanup = collective_heap_cleanup(comm)
        if not pre_canonical_cleanup["collective_call_completed"]:
            raise RuntimeError("Frozen M10 pre-canonical cleanup did not complete.")
        cleanup["pre_canonical"] = pre_canonical_cleanup
        if stage_callback is not None:
            stage_callback("precanonical_cleanup")
        canonical_solution = SimpleNamespace(
            bottom=recovery.bottom_solution,
            top=recovery.top_solution,
            bottom_recovered=recovery.bottom_recovered,
            top_recovered=recovery.top_recovered,
        )
        bottom_export = _write_canonical_manifest_exports(
            side="bottom",
            systems={"bottom": setup.bottom, "top": setup.top},
            physical_solution=canonical_solution,
            run_dir=run_dir,
            comm=comm,
        )
        canonical["bottom"] = bottom_export
        del bottom_export
        bottom_cleanup = collective_heap_cleanup(comm)
        if not bottom_cleanup["collective_call_completed"]:
            raise RuntimeError("Frozen M10 bottom canonical cleanup failed.")
        cleanup["bottom_canonical"] = bottom_cleanup
        if stage_callback is not None:
            stage_callback("bottom_active_full_stream_cleanup")
        top_export = _write_canonical_manifest_exports(
            side="top",
            systems={"bottom": setup.bottom, "top": setup.top},
            physical_solution=canonical_solution,
            run_dir=run_dir,
            comm=comm,
        )
        canonical["top"] = top_export
        del top_export
        del canonical_solution
        top_cleanup = collective_heap_cleanup(comm)
        if not top_cleanup["collective_call_completed"]:
            raise RuntimeError("Frozen M10 top canonical cleanup failed.")
        cleanup["top_canonical"] = top_cleanup
        if stage_callback is not None:
            stage_callback("top_active_full_stream_cleanup")
        canonical_pass = bool(
            all(
                len(export["roles"]) == 2
                and all(role["pass"] is True for role in export["roles"].values())
                for export in canonical.values()
            )
        )
    return FrozenM10Physics(
        port_power=port_power,
        traction=traction,
        interface_continuity=interface_continuity,
        absorption=absorption,
        external_orders=external_orders,
        energy=energy,
        own_grid=own_grid,
        order_audit=order_audit,
        canonical=canonical,
        cleanup=cleanup,
        timings={
            "physics_total_seconds": _max_elapsed(comm, started),
        },
        own_physics_pass=own_physics_pass,
        canonical_pass=canonical_pass,
        physics_pass=bool(own_physics_pass and canonical_pass),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _complex_json(value: complex) -> list[float]:
    coefficient = complex(value)
    return [float(coefficient.real), float(coefficient.imag)]


def _json_default(value: Any) -> Any:
    if isinstance(value, complex):
        return _complex_json(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _json_safe(value: Any) -> Any:
    """Convert compact carrier data without retaining PETSc or field objects."""

    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, complex):
        return _complex_json(value)
    if isinstance(value, Path):
        return _record_path(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported compact record value: {type(value).__name__}")


def build_frozen_m10_online_record(
    *,
    case_label: str,
    source_before: Mapping[str, Any],
    source_after: Mapping[str, Any],
    authority_bindings: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    linear: FrozenM10LinearSolve | None = None,
    recovery: FrozenM10Recovery | None = None,
    physics: FrozenM10Physics | None = None,
    final_release: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build bounded online evidence from compact carrier snapshots."""

    result = None if linear is None else linear.result
    postsolve = {} if result is None else dict(result.postsolve_audit)
    residual_keys = (
        "reported_relative_residual",
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    residuals = {key: postsolve.get(key, "not_recorded") for key in residual_keys}
    iterations = None if result is None else int(result.iterations)
    reason = None if result is None else int(result.converged_reason)
    numerical_pass = bool(
        result is not None
        and reason is not None
        and reason > 0
        and iterations is not None
        and 0 < iterations <= FROZEN_M10.max_it
        and postsolve.get("pass") is True
        and all(
            np.isfinite(float(residuals[key]))
            and 0.0 <= float(residuals[key]) <= FROZEN_M10.rtol
            for key in residual_keys
        )
    )
    integration_performance_pass = bool(iterations is not None and iterations <= 900)
    release_pass = bool(linear is not None and linear.release.get("pass") is True)
    recovery_pass = bool(recovery is not None and recovery.recovery_pass is True)
    physics_pass = bool(physics is not None and physics.physics_pass is True)
    lifecycle_pass = bool(lifecycle.get("pass") is True)
    source_after_pass = bool(
        source_after.get("clean") is True
        and source_after.get("matches_verified_clean_sha") is True
    )
    final_release_pass = bool(
        final_release is not None and final_release.get("pass") is True
    )
    error_free = error is None
    qualification = {
        "numerical_pass": numerical_pass,
        "release_pass": release_pass,
        "recovery_pass": recovery_pass,
        "physics_pass": physics_pass,
        "lifecycle_pass": lifecycle_pass,
        "source_after_pass": source_after_pass,
        "final_release_pass": final_release_pass,
        "integration_performance_pass": integration_performance_pass,
        "error_free": error_free,
    }
    online_pass = bool(
        numerical_pass
        and release_pass
        and recovery_pass
        and physics_pass
        and lifecycle_pass
        and source_after_pass
        and final_release_pass
        and integration_performance_pass
        and error_free
    )
    linear_record = {
        "reason": reason,
        "iterations": iterations,
        "linear_pass": bool(linear is not None and linear.linear_pass),
        "postsolve_residuals": residuals,
        "history": [] if result is None else result.history,
        "history_evaluation_count": (
            None if result is None else result.history_evaluation_count
        ),
        "postsolve_evaluation_count": (
            None if result is None else result.postsolve_evaluation_count
        ),
        "postsolve_audit": postsolve,
        "inventory": {} if linear is None else linear.inventory,
        "timing": {} if linear is None else linear.timings,
        "release": {} if linear is None else linear.release,
    }
    recovery_record = (
        {
            "reports": recovery.reports,
            "timing": recovery.timings,
            "recovery_pass": recovery.recovery_pass,
        }
        if recovery is not None
        else {"reports": {}, "timing": {}, "recovery_pass": False}
    )
    physics_record = (
        {
            "port_power": physics.port_power,
            "traction": physics.traction,
            "interface_continuity": physics.interface_continuity,
            "absorption": physics.absorption,
            "external_orders": physics.external_orders,
            "order_audit": physics.order_audit,
            "energy": physics.energy,
            "own_grid": physics.own_grid,
            "canonical": physics.canonical,
            "cleanup": physics.cleanup,
            "timing": physics.timings,
            "own_physics_pass": physics.own_physics_pass,
            "canonical_pass": physics.canonical_pass,
            "physics_pass": physics.physics_pass,
        }
        if physics is not None
        else {}
    )
    record = {
        "record_schema": M10_RECORD_SCHEMA,
        "qualification_schema": M10_QUALIFICATION_SCHEMA,
        "case_label": case_label,
        "profile": asdict(FROZEN_M10),
        "ordinary_default_changed": False,
        "explicit_opt_in": True,
        "source": {
            "before": source_before,
            "after": source_after,
        },
        "authority_bindings": authority_bindings,
        "linear": linear_record,
        "recovery": recovery_record,
        "physics": physics_record,
        "lifecycle": lifecycle,
        "final_release": final_release or {},
        "offline_comparisons": {
            "twelve_plus_twelve": "not_run_offline_checker",
            "Full3D": "not_run_offline_checker",
            "direct_Hybrid": "not_run_offline_checker",
        },
        "qualification": qualification,
        "integration_performance_pass": integration_performance_pass,
        "online_pass": online_pass,
        "status": (
            "online_candidate_pass_awaiting_offline_checker"
            if online_pass
            else "failed"
        ),
    }
    if error is not None:
        record["error"] = str(error)
    return _json_safe(record)


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def release_frozen_m10_qep_operators(
    operators: Any,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Release the complete QEP operator owner once, then clean up collectively."""

    operators.destroy()
    cleanup = collective_heap_cleanup(comm)
    return {
        "status": "measured",
        "destroy_call_completed": True,
        "destroy_state": getattr(operators, "_destroyed", "not_exposed"),
        "cleanup": cleanup,
        "release_pass": bool(cleanup["collective_call_completed"]),
    }


def build_frozen_m10_setup(
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    *,
    log=None,
) -> FrozenM10Setup:
    """Build the frozen physical/QEP/endcap/coupling bundle only.

    The returned objects remain owned by the caller for the next solve and
    recovery stages.  QEP coefficient matrices are released only after both
    local action systems and the internal coupling are complete.
    """

    cfg = target_stage4_config(
        degree=FROZEN_M10.degree,
        h_nm=FROZEN_M10.h_nm,
    )
    modal_cfg = target_stage4_config(
        degree=FROZEN_M10.modal_degree,
        h_nm=FROZEN_M10.modal_h_nm,
    )
    for current_cfg in (cfg, modal_cfg):
        current_cfg.stage4_full3d_assembly_backend = (
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
        )
        current_cfg.matrix_diagnostics_assemble_unconstrained = False
        current_cfg.matrix_diagnostics_assemble_only = False
        current_cfg.matrix_diagnostics_factorization_only = False
        current_cfg.incident_theta_deg = 90.0 - FROZEN_M10.incident_grazing_deg
        current_cfg.polarization_kind = FROZEN_M10.polarization_kind

    timings: dict[str, float] = {}
    started = time.perf_counter()
    cross_section = build_matching_cross_section(modal_cfg, "stage4_xy")
    spaces = build_cross_section_spaces(
        cross_section,
        transverse_degree=FROZEN_M10.modal_degree,
    )
    operators = assemble_quadratic_beta_operators(
        modal_cfg,
        cross_section,
        spaces,
        log=log,
    )
    poynting_evaluator = PoyntingFluxEvaluator(
        modal_cfg,
        cross_section,
        spaces,
    )
    target = analytic_homogeneous_beta(modal_cfg, modal_cfg.n_air)
    timings["cross_section_qep_assembly"] = _max_elapsed(comm, started)

    started = time.perf_counter()
    positive_right, positive_report = solve_quadratic_beta_modes(
        operators,
        target=target,
        requested_modes=FROZEN_M10.candidate_modes,
    )
    positive_right, positive_selection = select_passive_direction_modes(
        positive_right,
        desired_direction="forward",
        requested_modes=FROZEN_M10.requested_modes,
        poynting_evaluator=poynting_evaluator,
        maximum_abs_beta=M10_BETA_H_CUTOFF / FROZEN_M10.modal_h_nm,
    )
    if len(positive_right) != FROZEN_M10.requested_modes:
        for mode in positive_right:
            mode.destroy()
        raise RuntimeError(
            "Frozen M10 forward QEP selection did not deliver 120 modes."
        )
    positive = build_biorthogonal_mode_basis(
        modal_cfg,
        cross_section,
        spaces,
        operators,
        positive_right,
        adjoint_target=np.conj(target),
        requested_left_modes=FROZEN_M10.candidate_modes,
        near_degenerate_tolerance=FROZEN_M10.near_degenerate_tolerance,
        block_rotation_tolerance=FROZEN_M10.block_rotation_tolerance,
        poynting_evaluator=poynting_evaluator,
        log=log,
    )
    negative_right, negative_report = solve_quadratic_beta_modes(
        operators,
        target=-target,
        requested_modes=FROZEN_M10.candidate_modes,
    )
    negative_right, negative_selection = select_passive_direction_modes(
        negative_right,
        desired_direction="backward",
        requested_modes=FROZEN_M10.requested_modes,
        poynting_evaluator=poynting_evaluator,
        maximum_abs_beta=M10_BETA_H_CUTOFF / FROZEN_M10.modal_h_nm,
    )
    if len(negative_right) != FROZEN_M10.requested_modes:
        for mode in negative_right:
            mode.destroy()
        raise RuntimeError(
            "Frozen M10 backward QEP selection did not deliver 120 modes."
        )
    negative = build_biorthogonal_mode_basis(
        modal_cfg,
        cross_section,
        spaces,
        operators,
        negative_right,
        adjoint_target=-np.conj(target),
        requested_left_modes=FROZEN_M10.candidate_modes,
        near_degenerate_tolerance=FROZEN_M10.near_degenerate_tolerance,
        block_rotation_tolerance=FROZEN_M10.block_rotation_tolerance,
        poynting_evaluator=poynting_evaluator,
        log=log,
    )
    reciprocal_pairs = pair_reciprocal_mode_bases(operators, positive, negative)
    if len(reciprocal_pairs) != FROZEN_M10.requested_modes:
        raise RuntimeError("Frozen M10 reciprocal QEP pairing is incomplete.")
    timings["qep_solve_and_biorthogonal_bases"] = _max_elapsed(comm, started)

    started = time.perf_counter()
    bottom = assemble_hybrid_local_dtn_action_system(
        cfg,
        "bottom",
        bottom_interface_z_nm=FROZEN_M10.bottom_interface_nm,
        top_interface_z_nm=FROZEN_M10.top_interface_nm,
        comm=comm,
        log=log,
    )
    top = assemble_hybrid_local_dtn_action_system(
        cfg,
        "top",
        bottom_interface_z_nm=FROZEN_M10.bottom_interface_nm,
        top_interface_z_nm=FROZEN_M10.top_interface_nm,
        comm=comm,
        log=log,
    )
    timings["bottom_top_action_dtn_systems"] = _max_elapsed(comm, started)

    started = time.perf_counter()
    coupling = build_hybrid_internal_mode_coupling(
        cfg,
        spaces,
        positive,
        negative,
        bottom,
        top,
        length_nm=FROZEN_M10.top_interface_nm - FROZEN_M10.bottom_interface_nm,
        propagation_model=FROZEN_M10.internal_propagation_model,
        modal_traction_model=FROZEN_M10.internal_traction_model,
        log=log,
    )
    timings["internal_modal_coupling"] = _max_elapsed(comm, started)

    qep_release = release_frozen_m10_qep_operators(operators, comm)
    operators = None
    if not qep_release["release_pass"]:
        raise RuntimeError(
            "Frozen M10 early QEP release did not complete collectively."
        )
    timings["early_qep_release"] = float(
        qep_release["cleanup"]["elapsed_seconds_max_rank"]
    )

    return FrozenM10Setup(
        cfg=cfg,
        modal_cfg=modal_cfg,
        cross_section=cross_section,
        spaces=spaces,
        positive=positive,
        negative=negative,
        bottom=bottom,
        top=top,
        coupling=coupling,
        reciprocal_pairs=tuple(reciprocal_pairs),
        mode_selection={
            "forward": {
                "candidate_modes": int(positive_selection.candidate_modes),
                "selected_modes": int(positive_selection.selected_modes),
            },
            "backward": {
                "candidate_modes": int(negative_selection.candidate_modes),
                "selected_modes": int(negative_selection.selected_modes),
            },
        },
        timings=timings,
        qep_release=qep_release,
    )


def _source_provenance(comm: MPI.Intracomm, verified_clean_sha: str) -> dict[str, Any]:
    """Bind every rank to the same clean source commit before any solve."""

    if comm.rank == 0:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        payload = {
            "commit_sha": head,
            "branch": branch,
            "verified_clean_sha": verified_clean_sha,
            "tracked_source_dirty": bool(status),
            "stable_and_clean_before": not bool(status),
        }
    else:
        payload = None
    payload = comm.bcast(payload, root=0)
    if payload["commit_sha"] != verified_clean_sha:
        raise RuntimeError("verified-clean-sha does not match the current HEAD.")
    if payload["tracked_source_dirty"]:
        raise RuntimeError("frozen M10 runner requires a clean source tree.")
    return dict(payload)


def _source_after_provenance(
    comm: MPI.Intracomm,
    verified_clean_sha: str,
) -> dict[str, Any]:
    """Verify that the source stayed at the verified clean commit after release."""

    if comm.rank == 0:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        payload = {
            "head": head,
            "branch": branch,
            "verified_clean_sha": verified_clean_sha,
            "clean": not bool(status),
            "matches_verified_clean_sha": head == verified_clean_sha,
        }
    else:
        payload = None
    return dict(comm.bcast(payload, root=0))


def _authority_is_tracked(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def load_authority_bindings(
    args: argparse.Namespace,
    *,
    current_source_sha: str,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Read and hash-bind the H1, p6, and pinned Full3D authorities."""

    h1_path = args.h1_authority.resolve()
    p6_path = args.task035c_p6_preflight_authority.resolve()
    full3d_path = args.full3d_reference.resolve()
    for path in (h1_path, p6_path, full3d_path):
        if not path.is_file():
            raise FileNotFoundError(f"authority record is unreadable: {path}")
    h1_sha = _sha256(h1_path)
    p6_sha = _sha256(p6_path)
    full3d_sha = _sha256(full3d_path)
    if h1_sha != args.h1_authority_sha256:
        raise RuntimeError("H1 authority SHA256 does not match its CLI binding.")
    if p6_sha != args.task035c_p6_preflight_sha256:
        raise RuntimeError("p6 authority SHA256 does not match its CLI binding.")
    if full3d_sha != args.full3d_reference_sha256:
        raise RuntimeError("Full3D authority SHA256 does not match its CLI binding.")
    h1_record = json.loads(h1_path.read_text(encoding="utf-8"))
    if not isinstance(h1_record, Mapping):
        raise RuntimeError("H1 authority record root must be a JSON object.")
    p6_record = json.loads(p6_path.read_text(encoding="utf-8"))
    full3d_record = json.loads(full3d_path.read_text(encoding="utf-8"))
    p6_gate = task035c_p6_h10_preflight_authority_gate(
        p6_record,
        expected_sha256=args.task035c_p6_preflight_sha256,
        observed_sha256=p6_sha,
        authority_is_tracked=_authority_is_tracked(p6_path),
    )
    full3d_gate = task037b_h1_pinned_full3d_reference_gate(
        full3d_record,
        expected_sha256=args.full3d_reference_sha256,
        observed_sha256=full3d_sha,
        current_source_sha=current_source_sha,
        assembly_backend=FROZEN_M10.assembly_backend,
        mpi_size=FROZEN_M10.mpi_size,
    )
    result = {
        "h1_direct_hybrid": {
            "path": str(h1_path),
            "sha256": h1_sha,
        },
        "p6_preflight": p6_gate,
        "pinned_full3d": full3d_gate,
        "p6": {"path": str(p6_path), "sha256": p6_sha},
        "full3d": {"path": str(full3d_path), "sha256": full3d_sha},
        "current_hybrid_source_sha": current_source_sha,
        "candidate_mpi_size": int(comm.size),
        "reference_mpi_size": M10_MPI_SIZE,
    }
    if not p6_gate["pass"] or not full3d_gate["pass"]:
        raise RuntimeError(f"M10 authority gate failed: {result}")
    return result


def _ensure_output_paths(args: argparse.Namespace, comm: MPI.Intracomm) -> None:
    paths = (args.output, args.run_dir, args.memory_stages)
    if comm.rank == 0:
        for path in paths:
            if path is not None and path.exists():
                raise FileExistsError(f"M10 output collision: {path}")
    comm.barrier()


@dataclass
class LifecycleTrace:
    """Low-frequency lifecycle evidence with an explicit reviewed order."""

    stages: list[str] = field(default_factory=list)
    timestamps: list[dict[str, Any]] = field(default_factory=list)
    memory_stages: Path | None = None
    comm: MPI.Intracomm | None = None

    def record(self, stage: str) -> None:
        if stage not in M10_LIFECYCLE_ORDER:
            raise ValueError(f"unknown frozen M10 lifecycle stage: {stage}")
        expected_index = len(self.stages)
        if (
            expected_index >= len(M10_LIFECYCLE_ORDER)
            or stage != M10_LIFECYCLE_ORDER[expected_index]
        ):
            expected = (
                M10_LIFECYCLE_ORDER[expected_index]
                if expected_index < len(M10_LIFECYCLE_ORDER)
                else "<complete>"
            )
            raise RuntimeError(
                f"M10 lifecycle stage {stage!r} is not the expected {expected!r}"
            )
        self.stages.append(stage)
        self.timestamps.append(
            {
                "stage": stage,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        if self.memory_stages is not None and (
            self.comm is None or self.comm.rank == 0
        ):
            self.memory_stages.parent.mkdir(parents=True, exist_ok=True)
            with self.memory_stages.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(self.timestamps[-1]) + "\n")
                stream.flush()
            print(f"M10 heartbeat stage={stage}", flush=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "task037b.m10-lifecycle.v1",
            "order": list(M10_LIFECYCLE_ORDER),
            "observed": list(self.stages),
            "timestamps": list(self.timestamps),
            "memory_stages": (
                None if self.memory_stages is None else _record_path(self.memory_stages)
            ),
            "pass": self.stages == list(M10_LIFECYCLE_ORDER),
        }


def collective_heap_cleanup(comm: MPI.Intracomm) -> dict[str, Any]:
    """Release Python/PETSc garbage once collectively and retain rank evidence."""

    started = time.perf_counter()
    gc.collect()
    PETSc.garbage_cleanup(comm)
    gc.collect()
    local = dict(_trim_process_heap())
    local["rank"] = int(comm.rank)
    audits = comm.allgather(local)
    return {
        "petsc_garbage_cleanup_called": True,
        "collective_call_completed": bool(
            all(item.get("call_completed") is True for item in audits)
        ),
        "rank_audits": audits,
        "max_rss_before_mb": max(float(item["rss_before_mb"]) for item in audits),
        "max_rss_after_mb": max(float(item["rss_after_mb"]) for item in audits),
        "max_rss_released_mb": max(float(item["rss_released_mb"]) for item in audits),
        "elapsed_seconds_max_rank": _max_elapsed(comm, started),
    }


def release_frozen_m10_objects(
    setup: FrozenM10Setup | None,
    recovery: FrozenM10Recovery | None,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Release the retained positive M10 state once, after record snapshots."""

    if setup is None:
        cleanup = collective_heap_cleanup(comm)
        return {
            "order": [],
            "checks": {
                "cleanup_collective_call_completed": cleanup[
                    "collective_call_completed"
                ]
            },
            "cleanup": cleanup,
            "pass": bool(cleanup["collective_call_completed"]),
        }
    if setup._final_release_done:
        checks = {
            "recovery_destroyed": recovery is None or recovery._destroyed,
            "coupling_destroy_call_completed": setup._final_release_state.get(
                "coupling", False
            ),
            "bottom_destroyed": bool(setup.bottom._destroyed),
            "top_destroyed": bool(setup.top._destroyed),
            "positive_destroy_call_completed": setup._final_release_state.get(
                "positive", False
            ),
            "negative_destroy_call_completed": setup._final_release_state.get(
                "negative", False
            ),
            "cleanup_collective_call_completed": setup._final_release_state.get(
                "cleanup", False
            ),
        }
        return {
            "order": [],
            "checks": checks,
            "cleanup": {"already_released": True},
            "pass": bool(all(checks.values())),
            "already_released": True,
        }

    order: list[str] = []
    if recovery is not None and not recovery._destroyed:
        recovery.destroy()
        order.append("recovery")
    if not setup._final_release_state.get("coupling", False):
        setup.coupling.destroy()
        setup._final_release_state["coupling"] = True
        order.append("coupling")
    if not setup.bottom._destroyed:
        setup.bottom.destroy()
        order.append("bottom")
    if not setup.top._destroyed:
        setup.top.destroy()
        order.append("top")
    if not setup._final_release_state.get("positive", False):
        setup.positive.destroy()
        setup._final_release_state["positive"] = True
        order.append("positive")
    if not setup._final_release_state.get("negative", False):
        setup.negative.destroy()
        setup._final_release_state["negative"] = True
        order.append("negative")
    cleanup = collective_heap_cleanup(comm)
    checks = {
        "recovery_destroyed": recovery is None or recovery._destroyed,
        "coupling_destroy_call_completed": setup._final_release_state["coupling"],
        "bottom_destroyed": bool(setup.bottom._destroyed),
        "top_destroyed": bool(setup.top._destroyed),
        "positive_destroy_call_completed": setup._final_release_state["positive"],
        "negative_destroy_call_completed": setup._final_release_state["negative"],
        "cleanup_collective_call_completed": bool(cleanup["collective_call_completed"]),
    }
    setup._final_release_state["cleanup"] = checks["cleanup_collective_call_completed"]
    passed = bool(all(checks.values()))
    setup._final_release_done = True
    return {
        "order": order,
        "checks": checks,
        "cleanup": cleanup,
        "pass": passed,
    }


@contextmanager
def canonical_active_trace_view(source: PETSc.Vec, condensed: Any):
    """Expose active rows without copying an appended full-field tail."""

    active_rows = int(condensed.active_rows)
    source_size = int(source.getSize())
    if source_size == active_rows:
        yield source
        return
    appended_rows = int(condensed.appended_rows)
    if appended_rows <= 0 or source_size != active_rows + appended_rows:
        raise RuntimeError("canonical active source ownership is inconsistent")
    start, end = map(int, source.getOwnershipRange())
    local_n = max(0, min(end, active_rows) - start)
    active_is = PETSc.IS().createStride(
        local_n, first=start, step=1, comm=source.getComm()
    )
    active_vec = source.getSubVector(active_is)
    try:
        yield active_vec
    finally:
        source.restoreSubVector(active_is, active_vec)
        active_is.destroy()


def _write_canonical_manifest_exports(
    *,
    side: str,
    systems: Mapping[str, Any],
    physical_solution: Any,
    run_dir: Path,
    comm: MPI.Intracomm,
    prefix: str = "task037b_m10",
) -> dict[str, Any]:
    """Write one side's two M10 role shards in audited iterator passes."""

    from src.solvers.hcurl_canonical_vector_dolfinx import (
        iter_canonical_active_trace_packets,
        iter_canonical_full_fe_packets,
    )

    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    if side not in ("bottom", "top"):
        raise ValueError(f"unsupported canonical side: {side}")

    def record_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            return str(path.resolve())

    run_directory = record_path(run_dir)
    system = systems[side]
    active_solution = (
        physical_solution.bottom if side == "bottom" else physical_solution.top
    )
    recovered = (
        physical_solution.bottom_recovered
        if side == "bottom"
        else physical_solution.top_recovered
    )
    side_exports: dict[str, Any] = {}
    for role in ("active_trace", "full_fe"):
        context = (
            canonical_active_trace_view(
                active_solution, system.static_condensation.condensed
            )
            if role == "active_trace"
            else nullcontext(recovered.electric_field.x.petsc_vec)
        )
        with context as packet_source:
            if role == "active_trace":
                packets = iter_canonical_active_trace_packets(
                    system.static_condensation.condensed,
                    system.V,
                    system.floquet_data,
                    packet_source,
                )
            else:
                packets = iter_canonical_full_fe_packets(
                    system.V, packet_source, system.floquet_data
                )
            path = run_dir / (
                f"{prefix}_{side}_{role}_canonical_rank{comm.rank:04d}.jsonl"
            )
            shard = write_canonical_packet_shard(path, packets, audit_packets=True)
        local_count = int(shard["packet_count"])
        local_duplicate = int(shard.pop("local_duplicate_count"))
        finite = bool(shard.pop("packet_finite"))
        if not finite or local_duplicate:
            raise RuntimeError(f"canonical {side}/{role} audit failed")
        audit = {
            "role": role,
            "local_packet_count": local_count,
            "local_duplicate_count": local_duplicate,
            "global_packet_count": int(comm.allreduce(local_count, op=MPI.SUM)),
            "summed_local_duplicate_count": int(
                comm.allreduce(local_duplicate, op=MPI.SUM)
            ),
            "trace_mass_norm": "not_qualified",
            "hcurl_norm": "not_qualified",
        }
        shard.update(
            {
                "rank": int(comm.rank),
                "local_duplicate_count": local_duplicate,
                "packet_finite": finite,
                "extractor_audit": audit,
            }
        )
        by_rank = comm.gather(shard, root=0)
        manifest_result = None
        if comm.rank == 0:
            by_rank = sorted(by_rank, key=lambda item: int(item["rank"]))
            manifest = canonical_shard_manifest(
                role=f"{side}_{role}",
                mpi_size=comm.size,
                shard_metadata=by_rank,
                extractor_audit={
                    "by_rank": [item["extractor_audit"] for item in by_rank]
                },
            )
            manifest_path = run_dir / (
                f"{prefix}_{side}_{role}_canonical_manifest.json"
            )
            manifest_sha = write_canonical_manifest(manifest_path, manifest)
            extractor_global_packet_count = int(audit["global_packet_count"])
            manifest_audit_local_count_sum = int(
                sum(
                    int(item["local_packet_count"])
                    for item in manifest["extractor_audit"]["by_rank"]
                )
            )
            manifest_global_summed_packet_count = int(
                manifest["global_summed_packet_count"]
            )
            manifest_audit_count_matches = (
                manifest_global_summed_packet_count
                == extractor_global_packet_count
                == manifest_audit_local_count_sum
            )
            role_pass = (
                all(
                    item["packet_finite"] and item["local_duplicate_count"] == 0
                    for item in by_rank
                )
                and manifest_audit_count_matches
            )
            manifest_result = {
                "run_directory": run_directory,
                "manifest": record_path(manifest_path),
                "manifest_sha256": manifest_sha,
                "schema_version": MANIFEST_SCHEMA,
                "global_summed_packet_count": manifest_global_summed_packet_count,
                "extractor_global_packet_count": extractor_global_packet_count,
                "manifest_audit_local_count_sum": manifest_audit_local_count_sum,
                "manifest_audit_count_matches": manifest_audit_count_matches,
                "packet_finite": all(item["packet_finite"] for item in by_rank),
                "local_duplicates_zero": all(
                    item["local_duplicate_count"] == 0 for item in by_rank
                ),
                "pass": role_pass,
            }
        side_exports[role] = comm.bcast(manifest_result, root=0)
        del packets
    return {"run_directory": run_directory, "roles": side_exports}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run only the frozen Task037b M10 positive profile."
    )
    parser.add_argument("--frozen-m10", action="store_true")
    parser.add_argument("--case-label", required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--memory-stages", type=Path)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument("--h1-authority", type=Path, required=True)
    parser.add_argument("--h1-authority-sha256", required=True)
    parser.add_argument("--full3d-reference", type=Path, required=True)
    parser.add_argument("--full3d-reference-sha256", required=True)
    parser.add_argument("--task035c-p6-preflight-authority", type=Path, required=True)
    parser.add_argument("--task035c-p6-preflight-sha256", required=True)
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.frozen_m10:
        parser.error("--frozen-m10 is required; no ordinary profile exists here")
    if not valid_hex_digest(args.verified_clean_sha, 40):
        parser.error("--verified-clean-sha must be a 40-character hex digest")
    if not valid_hex_digest(args.h1_authority_sha256, 64):
        parser.error("--h1-authority-sha256 must be a 64-character hex digest")
    if not valid_hex_digest(args.full3d_reference_sha256, 64):
        parser.error("--full3d-reference-sha256 must be a 64-character hex digest")
    if not valid_hex_digest(args.task035c_p6_preflight_sha256, 64):
        parser.error("--task035c-p6-preflight-sha256 must be a 64-character hex digest")
    return args


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def run_frozen_m10(args: argparse.Namespace) -> int:
    """Run the single frozen positive M10 chain and write its online record."""

    comm = MPI.COMM_WORLD
    if comm.size != FROZEN_M10.mpi_size:
        raise RuntimeError("frozen M10 formal identity requires MPI8")
    _ensure_output_paths(args, comm)
    lifecycle = LifecycleTrace(memory_stages=args.memory_stages, comm=comm)
    source_before: dict[str, Any] = {"status": "not_recorded"}
    source_after: dict[str, Any] = {"status": "not_recorded"}
    authority_bindings: dict[str, Any] = {}
    setup: FrozenM10Setup | None = None
    linear: FrozenM10LinearSolve | None = None
    recovery: FrozenM10Recovery | None = None
    physics: FrozenM10Physics | None = None
    final_release: dict[str, Any] | None = None
    error: str | None = None
    chain_pass = False
    rank0_log = print if comm.rank == 0 else None

    try:
        source_before = _source_provenance(comm, args.verified_clean_sha)
        authority_bindings = load_authority_bindings(
            args, current_source_sha=source_before["commit_sha"], comm=comm
        )
        lifecycle.record("setup")
        setup = build_frozen_m10_setup(comm, log=rank0_log)
        lifecycle.record("solve")
        linear = solve_frozen_m10_linear(setup, log=rank0_log)
        if not linear.linear_pass or linear.release.get("pass") is not True:
            raise RuntimeError("Frozen M10 linear qualification failed.")
        lifecycle.record("retained_solution_postsolve")
        recovery = recover_frozen_m10(
            setup,
            linear,
            stage_callback=lifecycle.record,
        )
        physics = run_frozen_m10_physics(
            setup,
            recovery,
            args.run_dir,
            comm,
            stage_callback=lifecycle.record,
        )
        if not physics.physics_pass:
            raise RuntimeError("Frozen M10 physics/canonical qualification failed.")
        chain_pass = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    try:
        if setup is not None:
            final_release = release_frozen_m10_objects(setup, recovery, comm)
            if not final_release["pass"]:
                chain_pass = False
                error = error or "Frozen M10 final release failed."
    except Exception as exc:
        chain_pass = False
        error = error or f"{type(exc).__name__}: {exc}"

    try:
        source_after = _source_after_provenance(comm, args.verified_clean_sha)
        if not (
            source_after.get("clean") is True
            and source_after.get("matches_verified_clean_sha") is True
        ):
            chain_pass = False
            error = error or "Frozen M10 source changed or became dirty after release."
    except Exception as exc:
        chain_pass = False
        error = error or f"{type(exc).__name__}: {exc}"

    if chain_pass and final_release is not None:
        lifecycle.record("record")
    record = build_frozen_m10_online_record(
        case_label=args.case_label,
        source_before=source_before,
        source_after=source_after,
        authority_bindings=authority_bindings,
        lifecycle=lifecycle.as_dict(),
        linear=linear,
        recovery=recovery,
        physics=physics,
        final_release=final_release,
        error=error,
    )
    return_code = 0 if bool(record["online_pass"]) else 1
    if comm.rank == 0:
        _write_json(args.output, record)
    comm.barrier()
    return int(comm.bcast(return_code, root=0))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_frozen_m10(args)


if __name__ == "__main__":
    raise SystemExit(main())
