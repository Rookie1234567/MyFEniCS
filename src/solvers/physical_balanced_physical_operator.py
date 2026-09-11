"""Focused H1c physical-side operators for the reviewed BAL_H path.

The p6 object in this module is a matrix-free full-FE physical Schur action.
Its volume part uses :class:`MpcFormActionContext`; the external modal
unknowns are eliminated with the same uncondensed surface functionals used by
the ordinary one-sided auxiliary DtN assembly.  No p6 matrix is materialized.

The p4 object is the small, explicit augmented FE/mode system needed by the
approved exact coarse factor.  It uses the same distributed full-FE/MPC
numbering and the same external modes as the p6 action.  The factor is
research-only and owns only its retained factor storage; the source matrix is
kept until the residual audit and then destroyed by the wrapper.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import dolfinx_mpc
import ffcx.analysis
import numpy as np
import ufl
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config_3d import SimulationConfig3D
from ..common.modes_3d import PortMode3D
from ..constraints.floquet_3d import build_double_floquet_mpc
from ..geometry.hybrid_local_mesh import HybridLocalMesh, HybridLocalSide
from .common_3d_forms import _build_variational_forms
from .common_3d_solve import _create_nedelec_space
from .dtn_port_3d import (
    _augmented_vec_from_base,
    _combine_owned_entries,
    _copy_base_matrix_to_augmented,
    _mode_projection_denominator,
    _ReusableSurfaceComponentAssembler,
    _traction_vector,
)
from .hybrid_local_dtn_action import HybridLocalDtnActionSystem
from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from .mpc_form_action import MpcFormActionContext

__all__ = (
    "FullSpacePhysicalDtnActionSystem",
    "P4ExactFactor",
    "build_fullspace_physical_dtn_action",
    "build_p4_exact_factor",
)


def _idx(values: Iterable[int]) -> np.ndarray:
    return np.fromiter(values, dtype=PETSc.IntType)


@dataclass(frozen=True)
class _QuadratureSpec:
    integral_type: str
    subdomain_id: tuple[object, ...]
    quadrature_rule: str
    quadrature_degree: int


def _actual_volume_quadrature_contract(
    bilinear_form: Any,
) -> tuple[_QuadratureSpec, ...]:
    """Read every actual same-ABI FFCx volume rule and degree."""

    analysis = ffcx.analysis.analyze_ufl_objects(
        [bilinear_form],
        np.dtype(PETSc.ScalarType),
    )
    specs = [
        _QuadratureSpec(
            integral_type=str(integral.integral_type()),
            subdomain_id=tuple(
                integral.subdomain_id()
                if isinstance(integral.subdomain_id(), tuple)
                else (integral.subdomain_id(),)
            ),
            quadrature_rule=str(integral.metadata()["quadrature_rule"]),
            quadrature_degree=int(integral.metadata()["quadrature_degree"]),
        )
        for form_data in analysis.form_data
        for integral_data in form_data.integral_data
        for integral in integral_data.integrals
    ]
    if not specs:
        raise RuntimeError("FFCx did not expose a volume quadrature contract")
    return tuple(specs)


def _apply_quadrature_contract(
    bilinear_form: Any,
    contract: tuple[_QuadratureSpec, ...],
) -> Any:
    """Apply a fine-form integral rule/degree contract to a matching form."""

    integrals = tuple(bilinear_form.integrals())
    cell_contract = tuple(spec for spec in contract if spec.integral_type == "cell")
    cell_rules = {
        (spec.quadrature_rule, spec.quadrature_degree) for spec in cell_contract
    }
    unique_cell_rule = next(iter(cell_rules)) if len(cell_rules) == 1 else None
    rebuilt = []
    for integral in integrals:
        integral_type = str(integral.integral_type())
        if integral_type == "cell" and unique_cell_rule is not None:
            quadrature_rule, quadrature_degree = unique_cell_rule
        else:
            raw_subdomain = integral.subdomain_id()
            raw_subdomains = (
                raw_subdomain
                if isinstance(raw_subdomain, tuple)
                else (raw_subdomain,)
            )
            matches = [
                spec
                for spec in contract
                if spec.integral_type == integral_type
                and any(
                    value in spec.subdomain_id for value in raw_subdomains
                )
            ]
            if len(matches) != 1:
                raise ValueError(
                    "p4 volume integral has no unique fine quadrature identity"
                )
            quadrature_rule = matches[0].quadrature_rule
            quadrature_degree = matches[0].quadrature_degree
        rebuilt.append(
            integral.reconstruct(
                metadata={
                    **integral.metadata(),
                    "quadrature_rule": quadrature_rule,
                    "quadrature_degree": quadrature_degree,
                }
            )
        )
    return ufl.Form(tuple(rebuilt))


def _require_vector_layout(vector: PETSc.Vec, global_size: int, label: str) -> None:
    if int(vector.getSize()) != int(global_size):
        raise ValueError(f"{label} has the wrong global size")
    first, last = (int(value) for value in vector.getOwnershipRange())
    if int(vector.getLocalSize()) != last - first:
        raise ValueError(f"{label} has an unsupported local ownership layout")


@dataclass
class _PhysicalModeEntries:
    """One full-FE modal projection/load pair in MPC algebraic storage."""

    mode: PortMode3D
    projection_rows: np.ndarray
    projection_values: np.ndarray
    traction_rows: np.ndarray
    traction_values: np.ndarray
    denominator: float

def _build_mode_vectors(
    *,
    V: Any,
    local_mesh: HybridLocalMesh,
    mpc: Any,
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    modes: Sequence[PortMode3D],
    quadrature_degree: int,
) -> tuple[_PhysicalModeEntries, ...]:
    assemblers = (
        _ReusableSurfaceComponentAssembler(
            V,
            local_mesh.mesh_data,
            local_mesh.external_facet_tag,
            0,
            quadrature_degree=quadrature_degree,
        ),
        _ReusableSurfaceComponentAssembler(
            V,
            local_mesh.mesh_data,
            local_mesh.external_facet_tag,
            1,
            quadrature_degree=quadrature_degree,
        ),
    )
    current_key: tuple[int, int, complex] | None = None
    current_components: tuple[
        tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]
    ] | None = None
    entries: list[_PhysicalModeEntries] = []
    for mode in modes:
        if mode.side != side:
            raise ValueError("physical-side modes must belong to the requested side")
        key = (int(mode.m), int(mode.n), complex(mode.k_vector[2]))
        if key != current_key:
            current_components = (
                assemblers[0].assemble_entries(mode, mpc),
                assemblers[1].assemble_entries(mode, mpc),
            )
            current_key = key
        if current_components is None:
            raise RuntimeError("physical modal component stream is empty")
        projection_rows, projection_values = _combine_owned_entries(
            current_components,
            (mode.e_vector[0], mode.e_vector[1]),
            comm=local_mesh.mesh.comm,
        )
        traction_rows, traction_values = _combine_owned_entries(
            current_components,
            tuple(_traction_vector(mode, cfg)[:2]),
            comm=local_mesh.mesh.comm,
        )
        entries.append(
            _PhysicalModeEntries(
                mode=mode,
                projection_rows=projection_rows,
                projection_values=projection_values,
                traction_rows=traction_rows,
                traction_values=traction_values,
                denominator=_mode_projection_denominator(mode, cfg),
            )
        )
    return tuple(entries)


class _FullSpacePhysicalAction:
    """PETSc Python-Mat context for ``F - C H^-1 D`` on full FE storage."""

    def __init__(
        self,
        *,
        context: MpcFormActionContext,
        modes: tuple[_PhysicalModeEntries, ...],
        full_rows: int,
        comm: MPI.Intracomm,
    ) -> None:
        self.context = context
        self.modes = modes
        self.full_rows = int(full_rows)
        self.comm = comm
        self.apply_count = 0
        self.destroyed = False

    def _check_vectors(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        _require_vector_layout(source, self.full_rows, "full physical action source")
        _require_vector_layout(target, self.full_rows, "full physical action target")

    def mult(
        self,
        _matrix: PETSc.Mat | None,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self.destroyed:
            raise RuntimeError("full physical action has been destroyed")
        self._check_vectors(source, target)
        self.context.mult(None, source, target)
        first, _last = (int(value) for value in source.getOwnershipRange())
        source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
        local_projection = np.asarray(
            [
                np.dot(
                    np.conjugate(entry.projection_values),
                    source_values[entry.projection_rows - first],
                )
                if len(entry.projection_rows)
                else 0.0 + 0.0j
                for entry in self.modes
            ],
            dtype=np.complex128,
        )
        projection = np.empty_like(local_projection)
        self.comm.Allreduce(local_projection, projection, op=MPI.SUM)
        target_values = target.getArray()
        for amplitude, entry in zip(
            projection / np.asarray(
                [entry.denominator for entry in self.modes],
                dtype=np.float64,
            ),
            self.modes,
            strict=True,
        ):
            if len(entry.traction_rows):
                target_values[entry.traction_rows - first] -= (
                    PETSc.ScalarType(amplitude) * entry.traction_values
                )
        self.apply_count += 1

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self.destroyed:
            return
        self.context.destroy()
        self.destroyed = True


@dataclass
class FullSpacePhysicalDtnActionSystem:
    """Owned full p6/p4 physical Schur action and its FE/MPC metadata."""

    side: HybridLocalSide
    cfg: SimulationConfig3D
    local_mesh: HybridLocalMesh
    V: Any
    floquet_data: Any
    bilinear_form: Any
    linear_form: Any
    modes: tuple[PortMode3D, ...]
    dtn_quadrature_degree: int
    volume_quadrature_contract: tuple[_QuadratureSpec, ...]
    action: _FullSpacePhysicalAction
    matrix: PETSc.Mat
    _destroyed: bool = field(default=False, init=False, repr=False)

    @property
    def full_rows(self) -> int:
        return int(self.action.full_rows)

    @property
    def volume_quadrature_degree(self) -> int | None:
        degrees = {spec.quadrature_degree for spec in self.volume_quadrature_contract}
        return next(iter(degrees)) if len(degrees) == 1 else None

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": "task041.h1c.fullspace_physical_dtn_action.v1",
            "side": self.side,
            "full_space": "uncondensed_FE_with_MPC_algebraic_slave_identity",
            "external_surface_space": "uncondensed_FE_before_MPC_restriction",
            "global_p6_matrix_materialized": False,
            "external_mode_count": len(self.modes),
            "surface_quadrature_degree": int(self.dtn_quadrature_degree),
            "volume_quadrature": tuple(
                {
                    "integral_type": spec.integral_type,
                    "subdomain_id": spec.subdomain_id,
                    "quadrature_rule": spec.quadrature_rule,
                    "quadrature_degree": int(spec.quadrature_degree),
                }
                for spec in self.volume_quadrature_contract
            ),
            "apply_count": int(self.action.apply_count),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.matrix.destroy()
        self.action.destroy()
        self._destroyed = True


def _wrap_fullspace_action(
    *,
    cfg: SimulationConfig3D,
    side: HybridLocalSide,
    local_mesh: HybridLocalMesh,
    V: Any,
    floquet_data: Any,
    bilinear_form: Any,
    linear_form: Any,
    modes: tuple[PortMode3D, ...],
    dtn_quadrature_degree: int,
    volume_quadrature_contract: tuple[_QuadratureSpec, ...],
) -> FullSpacePhysicalDtnActionSystem:
    if cfg.use_pml:
        raise ValueError("H1c full physical DtN requires use_pml=False")
    if local_mesh.side != side:
        raise ValueError("local mesh side does not match physical action side")
    if not modes:
        raise RuntimeError(f"H1c {side} physical action selected zero external modes")
    if int(dtn_quadrature_degree) <= 0:
        raise ValueError("H1c DtN quadrature degree must be positive")
    context = MpcFormActionContext(bilinear_form, floquet_data.mpc, reference=None)
    full_rows = int(context.input_vector.getSize())
    action = None
    try:
        mode_vectors = _build_mode_vectors(
            V=V,
            local_mesh=local_mesh,
            mpc=floquet_data.mpc,
            cfg=cfg,
            side=side,
            modes=modes,
            quadrature_degree=int(dtn_quadrature_degree),
        )
        action = _FullSpacePhysicalAction(
            context=context,
            modes=mode_vectors,
            full_rows=full_rows,
            comm=local_mesh.mesh.comm,
        )
        local_rows = int(context.input_vector.getLocalSize())
        matrix = PETSc.Mat().createPython(
            ((local_rows, full_rows), (local_rows, full_rows)),
            context=action,
            comm=local_mesh.mesh.comm,
        )
        matrix.setUp()
        return FullSpacePhysicalDtnActionSystem(
            side=side,
            cfg=cfg,
            local_mesh=local_mesh,
            V=V,
            floquet_data=floquet_data,
            bilinear_form=bilinear_form,
            linear_form=linear_form,
            modes=modes,
            dtn_quadrature_degree=int(dtn_quadrature_degree),
            volume_quadrature_contract=volume_quadrature_contract,
            action=action,
            matrix=matrix,
        )
    except Exception:
        if action is not None:
            action.destroy()
        else:
            context.destroy()
        raise


def build_fullspace_physical_dtn_action(
    side_system: HybridLocalDtnActionSystem,
) -> FullSpacePhysicalDtnActionSystem:
    """Wrap one existing action system in a full-space physical p6 action."""

    if not isinstance(side_system, HybridLocalDtnActionSystem):
        raise TypeError("H1c full physical action requires HybridLocalDtnActionSystem")
    if int(side_system.cfg.nedelec_degree) != 6:
        raise ValueError("full-space physical p6 action requires nedelec_degree=6")
    modes = tuple(side_system.external_modes)
    return _wrap_fullspace_action(
        cfg=side_system.cfg,
        side=side_system.side,
        local_mesh=side_system.local_mesh,
        V=side_system.V,
        floquet_data=side_system.floquet_data,
        bilinear_form=side_system.bilinear_form,
        linear_form=side_system.linear_form,
        modes=modes,
        dtn_quadrature_degree=side_system.dtn_quadrature_degree,
        volume_quadrature_contract=_actual_volume_quadrature_contract(
            side_system.bilinear_form
        ),
    )


def _matching_p4_config(cfg: SimulationConfig3D) -> SimulationConfig3D:
    return replace(
        cfg,
        nedelec_degree=4,
        nedelec_trace_degree=None,
        nedelec_interior_degree=None,
        floquet_constraint_mode="topological_trace_p4",
    )


def _build_matching_p4_action(
    side_system: HybridLocalDtnActionSystem,
) -> FullSpacePhysicalDtnActionSystem:
    cfg = _matching_p4_config(side_system.cfg)
    V = _create_nedelec_space(side_system.local_mesh.mesh, cfg)
    floquet_data = build_double_floquet_mpc(
        V,
        side_system.local_mesh.mesh_data,
        cfg,
    )
    raw_bilinear_form, linear_form = _build_variational_forms(
        side_system.local_mesh.mesh,
        side_system.local_mesh.mesh_data,
        cfg,
        V,
        field_formulation="total_field_dtn_port",
        incident_field=None,
    )
    volume_contract = _actual_volume_quadrature_contract(side_system.bilinear_form)
    bilinear_form = _apply_quadrature_contract(raw_bilinear_form, volume_contract)
    return _wrap_fullspace_action(
        cfg=cfg,
        side=side_system.side,
        local_mesh=side_system.local_mesh,
        V=V,
        floquet_data=floquet_data,
        bilinear_form=bilinear_form,
        linear_form=linear_form,
        modes=tuple(side_system.external_modes),
        dtn_quadrature_degree=side_system.dtn_quadrature_degree,
        volume_quadrature_contract=volume_contract,
    )


def _assemble_augmented_matrix(
    system: FullSpacePhysicalDtnActionSystem,
) -> PETSc.Mat:
    """Materialize only the approved p4 augmented matrix."""

    comm = system.local_mesh.mesh.comm
    mpc = system.floquet_data.mpc
    A_base = dolfinx_mpc.assemble_matrix(
        fem.form(system.bilinear_form),
        mpc,
        bcs=None,
    )
    A_base.assemble()
    A_aug = _copy_base_matrix_to_augmented(A_base, len(system.modes), comm)
    n_fe = system.full_rows
    try:
        row_start, row_end = (int(value) for value in A_aug.getOwnershipRange())
        for aux_index, entry in enumerate(system.action.modes):
            if len(entry.traction_rows):
                A_aug.setValues(
                    entry.traction_rows,
                    _idx((n_fe + aux_index,)),
                    (-entry.traction_values).reshape((len(entry.traction_rows), 1)),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
            aux_global = n_fe + aux_index
            if len(entry.projection_rows):
                A_aug.setValues(
                    _idx((aux_global,)),
                    entry.projection_rows,
                    (-np.conj(entry.projection_values) / entry.denominator).reshape(
                        (1, len(entry.projection_rows))
                    ),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
            if row_start <= aux_global < row_end:
                A_aug.setValue(
                    aux_global,
                    aux_global,
                    PETSc.ScalarType(1.0),
                    addv=PETSc.InsertMode.INSERT_VALUES,
                )
        A_aug.assemble()
        return A_aug
    except Exception:
        A_aug.destroy()
        raise
    finally:
        A_base.destroy()


@dataclass
class P4ExactFactor:
    """One collective exact p4 augmented factor and its physical action."""

    physical_action: FullSpacePhysicalDtnActionSystem
    matrix: PETSc.Mat
    factor: ResearchExactFactorInverse
    factor_events: list[str]
    _destroyed: bool = field(default=False, init=False, repr=False)
    _last_solve_audit: dict[str, Any] = field(default_factory=dict, init=False)

    @property
    def full_rows(self) -> int:
        return self.physical_action.full_rows

    @property
    def n_aux(self) -> int:
        return len(self.physical_action.modes)

    @property
    def augmented_rows(self) -> int:
        return self.full_rows + self.n_aux

    def create_rhs(self, fe_rhs: PETSc.Vec) -> PETSc.Vec:
        _require_vector_layout(fe_rhs, self.full_rows, "p4 FE RHS")
        rhs = _augmented_vec_from_base(
            fe_rhs,
            self.n_aux,
            self.matrix.getComm().tompi4py(),
        )
        rhs.assemble()
        return rhs

    def create_fe_vector(self) -> PETSc.Vec:
        start, end = self.matrix.getOwnershipRange()
        fe_local = max(0, min(int(end), self.full_rows) - int(start))
        return PETSc.Vec().createMPI(
            (fe_local, self.full_rows),
            comm=self.matrix.getComm(),
        )

    def extract_fe_solution(self, augmented_solution: PETSc.Vec) -> PETSc.Vec:
        _require_vector_layout(
            augmented_solution,
            self.augmented_rows,
            "p4 augmented solution",
        )
        result = self.create_fe_vector()
        start, end = (int(value) for value in result.getOwnershipRange())
        if end > start:
            result.getArray()[:] = augmented_solution.getValues(
                _idx(range(start, end))
            )
        result.assemble()
        return result

    def solve_with_refinement(
        self,
        rhs: PETSc.Vec,
        solution: PETSc.Vec,
        *,
        residual_tolerance: float = 1.0e-10,
    ) -> dict[str, Any]:
        _require_vector_layout(rhs, self.augmented_rows, "p4 augmented RHS")
        _require_vector_layout(solution, self.augmented_rows, "p4 augmented solution")
        fe_rhs = self.extract_fe_solution(rhs)
        physical_rhs_norm = float(fe_rhs.norm())
        if not np.isfinite(physical_rhs_norm):
            fe_rhs.destroy()
            raise RuntimeError("p4 physical RHS norm is non-finite")
        backsolves = 0
        correction = None
        fe_solution = None
        physical_output = None
        physical_residual = None
        physical_relative = np.inf
        physical_residual_norm = np.inf
        try:
            self.factor.solve(rhs, solution)
            backsolves += 1
            for refinement in range(3):
                if fe_solution is not None:
                    fe_solution.destroy()
                if physical_output is not None:
                    physical_output.destroy()
                if physical_residual is not None:
                    physical_residual.destroy()
                fe_solution = self.extract_fe_solution(solution)
                physical_output = fe_solution.duplicate()
                self.physical_action.matrix.mult(fe_solution, physical_output)
                physical_residual = fe_rhs.duplicate()
                fe_rhs.copy(physical_residual)
                physical_residual.axpy(
                    PETSc.ScalarType(-1.0),
                    physical_output,
                )
                physical_residual_norm = float(physical_residual.norm())
                if physical_rhs_norm > 0.0:
                    physical_relative = physical_residual_norm / physical_rhs_norm
                    if not np.isfinite(physical_relative):
                        raise RuntimeError("p4 physical residual ratio is non-finite")
                    physical_passed = physical_relative <= float(
                        residual_tolerance
                    )
                else:
                    if not np.isfinite(physical_residual_norm):
                        raise RuntimeError(
                            "p4 zero-RHS physical residual is non-finite"
                        )
                    physical_relative = physical_residual_norm
                    physical_passed = physical_residual_norm <= float(
                        residual_tolerance
                    )

                if physical_passed:
                    break
                if refinement == 2:
                    break
                if correction is not None:
                    correction.destroy()
                correction = solution.duplicate()
                correction_rhs = self.create_rhs(physical_residual)
                try:
                    self.factor.solve(correction_rhs, correction)
                finally:
                    correction_rhs.destroy()
                backsolves += 1
                solution.axpy(PETSc.ScalarType(1.0), correction)
            if not np.isfinite(physical_relative) or physical_relative > float(
                residual_tolerance
            ):
                raise RuntimeError(
                    "p4 exact factor physical residual refinement exceeded the fixed "
                    f"tolerance: relative={physical_relative:.6e}, "
                    f"tolerance={residual_tolerance:.6e}"
                )
            self._last_solve_audit = {
                "rhs_norm": physical_rhs_norm,
                "residual_norm": physical_residual_norm,
                "relative_residual": physical_relative,
                "physical_residual_norm": physical_residual_norm,
                "physical_relative_residual": physical_relative,
                "backsolve_count": backsolves,
                "refinement_count": backsolves - 1,
                "same_factor_refinement": backsolves > 1,
            }
            return dict(self._last_solve_audit)
        finally:
            fe_rhs.destroy()
            if fe_solution is not None:
                fe_solution.destroy()
            if physical_output is not None:
                physical_output.destroy()
            if physical_residual is not None:
                physical_residual.destroy()
            if correction is not None:
                correction.destroy()

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "schema": "task041.h1c.p4_exact_factor.v1",
            "augmented_rows": int(self.augmented_rows),
            "factor_creation_count": int(bool(self.factor_events)),
            "factor_destroy_count": int(self._destroyed),
            "factor_events": tuple(self.factor_events),
            "last_solve": dict(self._last_solve_audit),
            "research_factor": self.factor.diagnostics,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.factor.destroy()
        self.matrix.destroy()
        self.physical_action.destroy()
        self._destroyed = True


def build_p4_exact_factor(
    side_system: HybridLocalDtnActionSystem,
    *,
    factor_solver_type: str = "mumps",
) -> P4ExactFactor:
    """Build one distributed p4 augmented matrix and its single exact factor."""

    if not isinstance(side_system, HybridLocalDtnActionSystem):
        raise TypeError("p4 exact factor requires HybridLocalDtnActionSystem")
    if int(side_system.cfg.nedelec_degree) != 6:
        raise ValueError("p4 exact factor requires a p6 side system")

    physical = _build_matching_p4_action(side_system)
    matrix = None
    events: list[str] = []

    def lifecycle(event: str, _details: dict[str, Any]) -> None:
        events.append(str(event))

    try:
        matrix = _assemble_augmented_matrix(physical)
        factor = ResearchExactFactorInverse(
            matrix,
            factor_solver_type=factor_solver_type,
            factor_only_storage=True,
            lifecycle_callback=lifecycle,
        )
        return P4ExactFactor(
            physical_action=physical,
            matrix=matrix,
            factor=factor,
            factor_events=events,
        )
    except Exception:
        if matrix is not None:
            matrix.destroy()
        physical.destroy()
        raise
