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

import time
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
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
    _owned_cells_adjacent_to_facet_tag,
    _ReusableSurfaceComponentAssembler,
    _traction_vector,
)
from .hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from .hybrid_local_dtn_action import HybridLocalDtnActionSystem
from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from .mpc_form_action import MpcFormActionContext
from .p4_cell_condensed_inverse import (
    CellPortTerms,
    P4CellCondensedInverse,
    assemble_port_condensed_terms,
)

__all__ = (
    "FullSpacePhysicalDtnActionSystem",
    "P4CondensedExactFactor",
    "P4ExactFactor",
    "P4PhysicalResidualGateError",
    "build_fullspace_physical_dtn_action",
    "build_p4_condensed_exact_factor",
    "build_p4_condensed_exact_factor_from_action",
    "build_p4_exact_factor",
)


def _idx(values: Iterable[int]) -> np.ndarray:
    return np.fromiter(values, dtype=PETSc.IntType)


class P4PhysicalResidualGateError(RuntimeError):
    """Report one p4 physical residual gate without losing its audit."""

    def __init__(self, audit: Mapping[str, Any]) -> None:
        self.audit = dict(audit)
        relative = self.audit.get(
            "augmented_relative_residual",
            self.audit.get("relative_residual"),
        )
        super().__init__(
            "p4 exact factor physical residual refinement exceeded the fixed "
            f"tolerance: relative={relative!s}, "
            f"tolerance={self.audit.get('residual_tolerance')!s}"
        )


def _timing_add(
    timing: MutableMapping[str, float] | None,
    name: str,
    seconds: float,
) -> None:
    if timing is not None:
        timing[name] = float(timing.get(name, 0.0)) + max(0.0, float(seconds))

def _accumulate_optional_timing(
    target: MutableMapping[str, float] | None,
    source: Mapping[str, Any],
) -> None:
    if target is None:
        return
    for name, value in source.items():
        if value is not None:
            _timing_add(target, name, float(value))


def _diagnostic_correction_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError("diagnostic_correction_steps must be an integer")
    count = int(value)
    if count not in (0, 1, 2):
        raise ValueError("diagnostic_correction_steps must be 0, 1, or 2")
    return count


def _readonly_diagnostic_array(values: np.ndarray) -> np.ndarray:
    result = np.array(values, dtype=np.complex128, copy=True)
    result.setflags(write=False)
    return result


def _emit_p4_diagnostic(
    comm: MPI.Intracomm,
    callback: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None,
    record: Mapping[str, Any],
    borrowed: Mapping[str, Any],
) -> None:
    """Call all-rank observer with read-only, borrowed, short-lived data."""

    if callback is None:
        return
    local_error: BaseException | None = None
    try:
        callback(dict(record), borrowed)
    except BaseException as error:  # noqa: BLE001 - synchronize callback failure
        local_error = error
    all_succeeded = comm.allreduce(local_error is None, op=MPI.LAND)
    if not all_succeeded:
        raise RuntimeError("p4 diagnostic callback failed on at least one rank") from local_error

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


def _payload_vector_inventory(
    vector: PETSc.Vec,
    *,
    label: str,
    ownership: str,
) -> dict[str, Any]:
    dtype = np.dtype(PETSc.ScalarType)
    owned_entries = int(vector.getLocalSize())
    return {
        "label": label,
        "kind": "PETSc.Vec",
        "ownership": ownership,
        "owned_entries": owned_entries,
        "global_size": int(vector.getSize()),
        "itemsize": int(dtype.itemsize),
        "payload_bytes_local": owned_entries * int(dtype.itemsize),
        "payload_bytes_semantics": "owned entries only",
        "ghost_native_bytes": "unknown",
    }


def _payload_array_inventory(
    array: Any,
    *,
    label: str,
    ownership: str,
) -> dict[str, Any]:
    if not isinstance(array, np.ndarray):
        return {
            "label": label,
            "kind": "numpy.ndarray",
            "ownership": ownership,
            "payload_bytes_local": "unknown",
            "payload_bytes_semantics": "exposed NumPy buffer; unavailable",
        }
    return {
        "label": label,
        "kind": "numpy.ndarray",
        "ownership": ownership,
        "shape": [int(value) for value in array.shape],
        "dtype": str(array.dtype),
        "itemsize": int(array.dtype.itemsize),
        "payload_bytes_local": int(array.nbytes),
        "payload_bytes_semantics": "exposed NumPy buffer",
    }


def _full_action_inventory(
    system: FullSpacePhysicalDtnActionSystem,
    *,
    owner: str,
) -> dict[str, Any]:
    context = system.action.context
    mode_payload_bytes = sum(
        int(array.nbytes)
        for entry in system.action.modes
        for array in (
            entry.projection_rows,
            entry.projection_values,
            entry.traction_rows,
            entry.traction_values,
        )
    )
    matrix_local = tuple(int(value) for value in system.matrix.getLocalSize())
    matrix_global = tuple(int(value) for value in system.matrix.getSize())
    p4_owned = owner == "p4.physical_action"
    owned_objects = [
        _payload_vector_inventory(
            context.input_vector,
            label=f"{owner}.context.input_vector",
            ownership=owner,
        ),
        _payload_vector_inventory(
            context.action_vector,
            label=f"{owner}.context.action_vector",
            ownership=owner,
        ),
        _payload_array_inventory(
            context.owned_slaves,
            label=f"{owner}.context.owned_slaves",
            ownership=owner,
        ),
        {
            "label": f"{owner}.mode_projection_traction_arrays",
            "kind": "numpy.ndarray aggregate",
            "ownership": owner,
            "array_count": 4 * len(system.action.modes),
            "payload_bytes_local": mode_payload_bytes,
        },
    ]
    borrowed_objects = [
        {
            "label": f"{owner}.side_mesh",
            "ownership": "borrowed from side system; not destroyed here",
            "payload_bytes_local": "unknown",
        },
        {
            "label": f"{owner}.side_external_modes_and_inputs",
            "ownership": "borrowed from side system; not destroyed here",
            "payload_bytes_local": "unknown",
        },
    ]
    if p4_owned:
        owned_objects.extend(
            [
                {
                    "label": f"{owner}.p4_fe_space",
                    "kind": "dolfinx.FunctionSpace",
                    "ownership": "created by _build_matching_p4_action; released with wrapper",
                    "payload_bytes_local": "unknown",
                },
                {
                    "label": f"{owner}.p4_floquet_mpc",
                    "kind": "Floquet MPC",
                    "ownership": "created by _build_matching_p4_action; released with wrapper",
                    "payload_bytes_local": "unknown",
                },
            ]
        )
    else:
        borrowed_objects.extend(
            [
                {
                    "label": f"{owner}.side_p6_fe_space",
                    "kind": "dolfinx.FunctionSpace",
                    "ownership": "borrowed from side system; not destroyed here",
                    "payload_bytes_local": "unknown",
                },
                {
                    "label": f"{owner}.side_p6_floquet_mpc",
                    "kind": "Floquet MPC",
                    "ownership": "borrowed from side system; not destroyed here",
                    "payload_bytes_local": "unknown",
                },
            ]
        )
    return {
        "stage_scope": "rank_local",
        "owner": owner,
        "owned_objects": owned_objects,
        "borrowed_objects": borrowed_objects,
        "python_matrix": {
            "label": f"{owner}.matrix",
            "local_shape": list(matrix_local),
            "global_shape": list(matrix_global),
            "payload_bytes_local": "unknown",
        },
        "native_workspace_bytes": "unknown",
    }


def _p4_matrix_inventory(matrix: PETSc.Mat) -> dict[str, Any]:
    info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    raw_nnz = info.get("nz_used")
    raw_memory = info.get("memory")
    local_nnz = (
        int(raw_nnz)
        if isinstance(raw_nnz, (int, float))
        and not isinstance(raw_nnz, bool)
        and np.isfinite(float(raw_nnz))
        else None
    )
    local_memory = (
        float(raw_memory)
        if isinstance(raw_memory, (int, float))
        and not isinstance(raw_memory, bool)
        and np.isfinite(float(raw_memory))
        else None
    )
    estimated_payload = None
    if local_nnz is not None:
        estimated_payload = local_nnz * (
            2 * np.dtype(PETSc.IntType).itemsize
            + np.dtype(PETSc.ScalarType).itemsize
        )
    return {
        "label": "p4.source_matrix",
        "kind": "PETSc.Mat",
        "ownership": "retained by P4ExactFactor until destroy",
        "local_shape": [int(value) for value in matrix.getLocalSize()],
        "global_shape": [int(value) for value in matrix.getSize()],
        "local_nnz_from_getInfo_LOCAL": local_nnz,
        "local_memory_bytes_from_getInfo_LOCAL": local_memory,
        "payload_bytes_local": estimated_payload,
        "payload_bytes_semantics": "estimated from local nnz; not RSS",
        "native_workspace_bytes": "unknown",
    }


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


def _prepare_physical_p4_port_terms(
    condensed,
    physical: FullSpacePhysicalDtnActionSystem,
) -> dict[int, CellPortTerms]:
    """Insert physical trace/port rows and build owned interior port blocks."""

    n_ports = len(physical.action.modes)
    if n_ports != int(condensed.appended_rows):
        raise ValueError("physical mode count differs from condensed port rows")
    interior_locations: dict[int, tuple[int, int]] = {}
    cell_b: dict[int, dict[int, dict[int, complex]]] = {}
    cell_d: dict[int, dict[int, dict[int, complex]]] = {}
    for cell_index, cell in enumerate(condensed.cell_recovery_maps):
        rows = np.asarray(cell.interior_original_dofs, dtype=PETSc.IntType)
        for local, original in enumerate(rows):
            original = int(original)
            if original in interior_locations:
                raise RuntimeError(f"interior DoF {original} belongs to multiple cells")
            interior_locations[original] = (cell_index, local)

    owned_start, owned_end = (
        int(value) for value in condensed.matrix.getOwnershipRange()
    )
    local_error = None
    try:
        for port, entry in enumerate(physical.action.modes):
            b_rows = np.asarray(entry.traction_rows, dtype=PETSc.IntType)
            b_values = -np.asarray(entry.traction_values, dtype=np.complex128)
            d_rows = np.asarray(entry.projection_rows, dtype=PETSc.IntType)
            d_values = (
                np.conjugate(np.asarray(entry.projection_values, dtype=np.complex128))
                / complex(entry.denominator)
            )
            active_b: dict[int, complex] = {}
            active_d: dict[int, complex] = {}
            if len(b_rows) != len(b_values) or len(d_rows) != len(d_values):
                raise ValueError("physical mode row/value lengths differ")
            for row, value in zip(b_rows, b_values, strict=True):
                if value == 0.0:
                    continue
                location = interior_locations.get(int(row))
                if location is not None:
                    cell_index, local = location
                    by_port = cell_b.setdefault(cell_index, {}).setdefault(port, {})
                    by_port[local] = by_port.get(local, 0.0 + 0.0j) + value
                    continue
                active = condensed.trace_constraints.original_to_active.get(int(row))
                if active is None:
                    raise ValueError(
                        f"physical B row {int(row)} is not an owned active trace row"
                    )
                if not owned_start <= int(active) < min(owned_end, condensed.active_rows):
                    raise ValueError(
                        f"physical B active row {int(active)} is not locally owned"
                    )
                active_b[int(active)] = active_b.get(int(active), 0.0 + 0.0j) + value
            for row, value in zip(d_rows, d_values, strict=True):
                if value == 0.0:
                    continue
                location = interior_locations.get(int(row))
                if location is not None:
                    cell_index, local = location
                    by_port = cell_d.setdefault(cell_index, {}).setdefault(port, {})
                    by_port[local] = by_port.get(local, 0.0 + 0.0j) + value
                    continue
                active = condensed.trace_constraints.original_to_active.get(int(row))
                if active is None:
                    raise ValueError(
                        f"physical D row {int(row)} is not an owned active trace row"
                    )
                if not owned_start <= int(active) < min(owned_end, condensed.active_rows):
                    raise ValueError(
                        f"physical D active row {int(active)} is not locally owned"
                    )
                active_d[int(active)] = active_d.get(int(active), 0.0 + 0.0j) + value
            if active_b:
                b_ids = np.asarray(sorted(active_b), dtype=PETSc.IntType)
                b_values = np.asarray(
                    [active_b[int(row)] for row in b_ids],
                    dtype=PETSc.ScalarType,
                )
                condensed.matrix.setValues(
                    b_ids,
                    np.asarray([condensed.active_rows + port], dtype=PETSc.IntType),
                    b_values.reshape((-1, 1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
            if active_d:
                d_ids = np.asarray(sorted(active_d), dtype=PETSc.IntType)
                d_values = np.asarray(
                    [active_d[int(row)] for row in d_ids],
                    dtype=PETSc.ScalarType,
                )
                condensed.matrix.setValues(
                    np.asarray([condensed.active_rows + port], dtype=PETSc.IntType),
                    d_ids,
                    (-d_values).reshape((1, -1)),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
        if condensed.comm.rank == condensed.comm.size - 1:
            for port in range(n_ports):
                condensed.matrix.setValue(
                    condensed.active_rows + port,
                    condensed.active_rows + port,
                    PETSc.ScalarType(1.0),
                    addv=PETSc.InsertMode.ADD_VALUES,
                )
    except Exception as error:  # noqa: BLE001
        local_error = f"{type(error).__name__}: {error}"
    errors = condensed.comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise RuntimeError(
            "physical p4 trace/port insertion failed: "
            + "; ".join(
                f"rank {rank}: {error}"
                for rank, error in enumerate(errors)
                if error is not None
            )
        )

    terms: dict[int, CellPortTerms] = {}
    for cell_index in sorted(set(cell_b) | set(cell_d)):
        ports = sorted(
            set(cell_b.get(cell_index, {}))
            | set(cell_d.get(cell_index, {}))
        )
        rows = condensed.cell_recovery_maps[cell_index].interior_original_dofs
        bi = np.zeros((len(rows), len(ports)), dtype=np.complex128)
        di = np.zeros((len(ports), len(rows)), dtype=np.complex128)
        for column, port in enumerate(ports):
            for local, value in cell_b.get(cell_index, {}).get(port, {}).items():
                bi[local, column] = value
            for local, value in cell_d.get(cell_index, {}).get(port, {}).items():
                di[column, local] = value
        terms[cell_index] = CellPortTerms(
            Bi=np.ascontiguousarray(bi),
            Di=np.ascontiguousarray(di),
            port_indices=np.asarray(ports, dtype=PETSc.IntType),
        )
    return terms


def _add_physical_mode_values(
    target: PETSc.Vec,
    modes: Sequence[_PhysicalModeEntries],
    values: np.ndarray,
    *,
    scale: complex,
) -> None:
    for amplitude, entry in zip(values, modes, strict=True):
        if len(entry.traction_rows):
            target.setValues(
                entry.traction_rows,
                np.asarray(
                    scale * amplitude * entry.traction_values,
                    dtype=PETSc.ScalarType,
                ),
                addv=PETSc.InsertMode.ADD_VALUES,
            )


def _physical_mode_projection(
    source: PETSc.Vec,
    modes: Sequence[_PhysicalModeEntries],
) -> np.ndarray:
    first, _last = (int(value) for value in source.getOwnershipRange())
    source_values = np.asarray(source.getArray(readonly=True), dtype=np.complex128)
    local = np.asarray(
        [
            np.dot(
                np.conjugate(entry.projection_values),
                source_values[entry.projection_rows - first],
            )
            if len(entry.projection_rows)
            else 0.0 + 0.0j
            for entry in modes
        ],
        dtype=np.complex128,
    )
    global_values = np.empty_like(local)
    source.getComm().tompi4py().Allreduce(local, global_values, op=MPI.SUM)
    return global_values / np.asarray(
        [entry.denominator for entry in modes],
        dtype=np.complex128,
    )


@dataclass
class P4CondensedExactFactor:
    """Physical p4 condensed factor with full FE/port solve semantics."""

    physical_action: FullSpacePhysicalDtnActionSystem
    inverse: P4CellCondensedInverse
    factor_events: list[str]
    residual_tolerance: float = 1.0e-10
    owns_physical_action: bool = True
    _destroyed: bool = field(default=False, init=False, repr=False)
    _last_solve_audit: dict[str, Any] = field(default_factory=dict, init=False)
    _final_metadata: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    @property
    def full_rows(self) -> int:
        return self.physical_action.full_rows

    @property
    def n_aux(self) -> int:
        return len(self.physical_action.action.modes)

    @property
    def condensed(self):
        return self.inverse.condensed

    @property
    def factor(self):
        return self.inverse.factor

    @property
    def last_port_solution(self) -> np.ndarray:
        return np.array(self.inverse.last_port_solution, copy=True)

    def create_fe_vector(self) -> PETSc.Vec:
        vector = self.physical_action.action.context.input_vector.duplicate()
        vector.set(PETSc.ScalarType(0.0))
        return vector

    def _residual_state(
        self,
        rhs: PETSc.Vec,
        solution: PETSc.Vec,
        port_rhs: np.ndarray,
        port_solution: np.ndarray,
        timing: MutableMapping[str, float] | None = None,
        capture_port_values: bool = False,
    ) -> tuple[dict[str, Any], PETSc.Vec, np.ndarray]:
        _require_vector_layout(rhs, self.full_rows, "p4 physical FE RHS")
        _require_vector_layout(solution, self.full_rows, "p4 physical solution")
        effective_rhs = rhs.duplicate()
        action_output = rhs.duplicate()
        residual = None
        augmented_residual = None
        matrix_mult_seconds = None
        try:
            rhs.copy(effective_rhs)
            _add_physical_mode_values(
                effective_rhs,
                self.physical_action.action.modes,
                port_rhs,
                scale=1.0,
            )
            effective_rhs.assemble()
            effective_rhs_norm = float(effective_rhs.norm())
            matrix_mult_started = time.perf_counter()
            try:
                self.physical_action.matrix.mult(solution, action_output)
            finally:
                matrix_mult_seconds = time.perf_counter() - matrix_mult_started
                _timing_add(
                    timing,
                    "native_action_matrix_mult_seconds",
                    matrix_mult_seconds,
                )
            residual = effective_rhs.duplicate()
            effective_rhs.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), action_output)
            residual_norm = float(residual.norm())
            d_solution = _physical_mode_projection(
                solution,
                self.physical_action.action.modes,
            )
            port_residual = np.asarray(
                port_rhs + d_solution - port_solution,
                dtype=np.complex128,
            )
            augmented_residual = residual.duplicate()
            residual.copy(augmented_residual)
            _add_physical_mode_values(
                augmented_residual,
                self.physical_action.action.modes,
                port_residual,
                scale=-1.0,
            )
            augmented_residual.assemble()
            augmented_fe_norm = float(augmented_residual.norm())
            port_norm = float(np.linalg.norm(port_residual))
            augmented_norm = float(np.hypot(augmented_fe_norm, port_norm))
            augmented_rhs_norm = float(
                np.hypot(float(rhs.norm()), float(np.linalg.norm(port_rhs)))
            )
            physical_relative = (
                residual_norm / effective_rhs_norm
                if effective_rhs_norm > 0.0
                else residual_norm
            )
            relative = (
                augmented_norm / augmented_rhs_norm
                if augmented_rhs_norm > 0.0
                else augmented_norm
            )
            physical_passed = bool(
                np.isfinite(physical_relative)
                and physical_relative <= self.residual_tolerance
            )
            augmented_passed = bool(
                np.isfinite(relative) and relative <= self.residual_tolerance
            )
            audit = {
                "status": "passed" if physical_passed and augmented_passed else "gate_failed",
                "physical_rhs_norm": effective_rhs_norm,
                "physical_residual_norm": residual_norm,
                "physical_relative_residual": physical_relative,
                "physical_gate_passed": physical_passed,
                "augmented_fe_residual_norm": augmented_fe_norm,
                "port_residual_norm": port_norm,
                "residual_norm": augmented_norm,
                "relative_residual": relative,
                "augmented_gate_passed": augmented_passed,
                "augmented_rhs_norm": augmented_rhs_norm,
                "residual_tolerance": self.residual_tolerance,
                "native_action_matrix_mult_seconds": float(matrix_mult_seconds),
            }
            if capture_port_values:
                audit.update(
                    {
                        "port_solution_complex": [
                            [float(value.real), float(value.imag)]
                            for value in port_solution
                        ],
                        "port_rhs_complex": [
                            [float(value.real), float(value.imag)]
                            for value in port_rhs
                        ],
                        "port_projection_complex": [
                            [float(value.real), float(value.imag)]
                            for value in d_solution
                        ],
                    }
                )
            return audit, augmented_residual, port_residual
        except BaseException:
            if augmented_residual is not None:
                augmented_residual.destroy()
            raise
        finally:
            effective_rhs.destroy()
            action_output.destroy()
            if residual is not None:
                residual.destroy()

    def audit_solution(
        self,
        rhs: PETSc.Vec,
        solution: PETSc.Vec,
        *,
        port_rhs: np.ndarray | None = None,
        port_solution: np.ndarray | None = None,
    ) -> dict[str, Any]:
        values = self.inverse._prepare_port_rhs(port_rhs)
        solution_ports = (
            self.last_port_solution
            if port_solution is None
            else np.asarray(port_solution, dtype=np.complex128)
        )
        audit, augmented_residual, _port_residual = self._residual_state(
            rhs,
            solution,
            values,
            solution_ports,
        )
        augmented_residual.destroy()
        return audit

    def apply(
        self,
        rhs: PETSc.Vec,
        *,
        port_rhs: np.ndarray | None = None,
        timing: MutableMapping[str, float] | None = None,
        capture_port_values: bool = False,
        diagnostic_correction_steps: int = 0,
        diagnostic_callback: Callable[
            [Mapping[str, Any], Mapping[str, Any]], None
        ]
        | None = None,
    ) -> PETSc.Vec:
        """Solve full FE and port RHS, optionally auditing fixed corrections.

        The observer runs synchronously on every rank. PETSc vectors in its
        mapping are borrowed and must not be retained, modified, or destroyed.
        """

        diagnostic_correction_steps = _diagnostic_correction_count(
            diagnostic_correction_steps
        )
        diagnostic_mode = (
            diagnostic_correction_steps > 0 or diagnostic_callback is not None
        )
        self._last_solve_audit = {}
        values = self.inverse._prepare_port_rhs(port_rhs)
        solve_count_start = int(self.inverse.solve_count)
        total_started = time.perf_counter()
        solution = None
        keep_solution = False
        history: list[dict[str, Any]] = []
        correction_history: list[dict[str, Any]] = []
        correction: PETSc.Vec | None = None
        correction_seconds: float | None = None
        correction_norm: float | None = None
        port_correction: np.ndarray | None = None
        try:
            try:
                solution = self.inverse.apply(rhs, port_rhs=values)
            finally:
                _accumulate_optional_timing(timing, self.inverse.last_timing)
            initial_inverse_seconds = self.inverse.last_timing[
                "inner_apply_seconds"
            ]
            port_solution = self.last_port_solution
            for refinement in range(3):
                augmented_residual = None
                try:
                    residual_started = time.perf_counter()
                    try:
                        audit, augmented_residual, port_residual = self._residual_state(
                            rhs,
                            solution,
                            values,
                            port_solution,
                            timing=timing,
                            capture_port_values=capture_port_values,
                        )
                    finally:
                        residual_elapsed = time.perf_counter() - residual_started
                        _timing_add(
                            timing,
                            "native_action_and_residual_seconds",
                            residual_elapsed,
                        )
                    audit["native_action_and_residual_seconds"] = float(
                        residual_elapsed
                    )
                    audit["inverse_apply_seconds"] = (
                        float(initial_inverse_seconds)
                    )
                    audit.update(
                        {
                            "backsolve_count": int(self.inverse.solve_count)
                            - solve_count_start,
                            "total_factor_solve_count": int(self.inverse.solve_count),
                            "refinement_count": refinement,
                            "same_factor_refinement": refinement > 0,
                            "factor_backsolve_seconds": self.inverse.last_timing[
                                "factor_backsolve_seconds"
                            ],
                            "storage_rhs_reduction_seconds": self.inverse.last_timing[
                                "storage_rhs_reduction_seconds"
                            ],
                            "solution_recovery_seconds": self.inverse.last_timing[
                                "solution_recovery_seconds"
                            ],
                        }
                    )
                    nonfinite_residual = False
                    if diagnostic_mode:
                        nonfinite_residual = not np.isfinite(
                            audit["physical_relative_residual"]
                        ) or not np.isfinite(audit["relative_residual"])
                        if nonfinite_residual:
                            audit["status"] = "failed_nonfinite_residual"
                        audit.update(
                            {
                                "diagnostic_step_index": int(refinement),
                                "diagnostic_correction_count": int(refinement),
                                "diagnostic_correction_limit": int(
                                    diagnostic_correction_steps
                                ),
                                "correction_from_previous_seconds": correction_seconds,
                                "correction_from_previous_norm": correction_norm,
                                "factor_solve_seconds_for_state": audit[
                                    "factor_backsolve_seconds"
                                ],
                                "physical_gate_passed": bool(
                                    audit["physical_gate_passed"]
                                ),
                                "augmented_gate_passed": bool(
                                    audit["augmented_gate_passed"]
                                ),
                            }
                        )
                        correction_history.append(
                            {
                                key: value
                                for key, value in audit.items()
                                if isinstance(
                                    value,
                                    (bool, int, float, str, type(None)),
                                )
                            }
                        )
                        audit["diagnostic_correction_history"] = tuple(
                            correction_history
                        )
                    history.append(dict(audit))
                    self._last_solve_audit = dict(audit)
                    if diagnostic_callback is not None:
                        _emit_p4_diagnostic(
                            self.physical_action.matrix.getComm().tompi4py(),
                            diagnostic_callback,
                            audit,
                            {
                                "solution": solution,
                                "fe_residual": augmented_residual,
                                "port_residual": _readonly_diagnostic_array(
                                    port_residual
                                ),
                                "port_solution": _readonly_diagnostic_array(
                                    port_solution
                                ),
                                "port_rhs": _readonly_diagnostic_array(values),
                                "correction": correction,
                                "port_correction": (
                                    None
                                    if port_correction is None
                                    else _readonly_diagnostic_array(port_correction)
                                ),
                            },
                        )
                    if diagnostic_mode:
                        if nonfinite_residual:
                            raise P4PhysicalResidualGateError(dict(audit))
                        if refinement >= diagnostic_correction_steps:
                            if audit["status"] != "passed":
                                raise P4PhysicalResidualGateError(dict(audit))
                            keep_solution = True
                            return solution
                    elif audit["status"] == "passed":
                        keep_solution = True
                        return solution
                    elif refinement == 2:
                        raise P4PhysicalResidualGateError(dict(audit))
                    if correction is not None:
                        correction.destroy()
                        correction = None
                    try:
                        correction_started = (
                            time.perf_counter() if diagnostic_mode else 0.0
                        )
                        correction = self.inverse.apply(
                            augmented_residual,
                            port_rhs=port_residual,
                        )
                        solution.axpy(PETSc.ScalarType(1.0), correction)
                        if diagnostic_mode:
                            port_correction = self.last_port_solution
                            correction_norm = float(correction.norm())
                            correction_seconds = (
                                time.perf_counter() - correction_started
                            )
                    finally:
                        _accumulate_optional_timing(
                            timing, self.inverse.last_timing
                        )
                        if correction is not None and not diagnostic_mode:
                            correction.destroy()
                            correction = None
                    port_solution = port_solution + self.last_port_solution
                    self.inverse.last_port_solution = np.array(
                        port_solution,
                        copy=True,
                    )
                    initial_inverse_seconds = self.inverse.last_timing[
                        "inner_apply_seconds"
                    ]
                finally:
                    if augmented_residual is not None:
                        augmented_residual.destroy()
            raise AssertionError("unreachable p4 refinement state")
        except BaseException as error:
            if solution is not None and not keep_solution:
                solution.destroy()
            if not self._last_solve_audit:
                self._last_solve_audit = {
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            else:
                self._last_solve_audit["error_type"] = type(error).__name__
                self._last_solve_audit["error"] = str(error)
            raise
        finally:
            if self._last_solve_audit:
                self._last_solve_audit["history"] = tuple(history)
                if timing is not None:
                    self._last_solve_audit["timing"] = dict(timing)
                self._last_solve_audit["total_apply_seconds"] = float(
                    time.perf_counter() - total_started
                )
            if correction is not None:
                correction.destroy()

    def solve(self, rhs: PETSc.Vec, *, port_rhs: np.ndarray | None = None):
        solution = self.apply(rhs, port_rhs=port_rhs)
        return solution, self.last_port_solution

    @property
    def diagnostics(self) -> dict[str, Any]:
        condensed = self.condensed
        if condensed is None:
            return {
                **self._final_metadata,
                "destroyed": True,
                "last_solve": dict(self._last_solve_audit),
                "factor_solve_count": int(self.inverse.solve_count),
            }
        metadata = {
            "schema": "task041.h1c.p4_condensed_exact_factor.v1",
            "full_storage_rows": int(self.full_rows),
            "active_trace_rows": int(condensed.active_rows),
            "interior_rows": int(condensed.interior_rows),
            "port_rows": int(condensed.appended_rows),
            "retained_matrix_rows": int(condensed.active_rows + condensed.appended_rows),
            "factor_creation_count": 1,
            "factor_solve_count": int(self.inverse.solve_count),
            "last_solve": dict(self._last_solve_audit),
            "physical_action": self.physical_action.audit,
            "condensed_build": dict(condensed.build_audit),
            "factor_events": tuple(self.factor_events),
        }
        self._final_metadata = dict(metadata)
        return metadata

    def destroy(self) -> None:
        if self._destroyed:
            return
        cleanup_error: BaseException | None = None
        self._final_metadata = self.diagnostics
        try:
            self.inverse.destroy()
        except BaseException as error:  # noqa: BLE001 - preserve cleanup failure
            cleanup_error = error
        finally:
            if self.owns_physical_action:
                try:
                    self.physical_action.destroy()
                except BaseException as error:  # noqa: BLE001 - preserve cleanup failure
                    if cleanup_error is None:
                        cleanup_error = error
            self._destroyed = True
        if cleanup_error is not None:
            raise cleanup_error


@dataclass
class P4ExactFactor:
    """One collective exact p4 augmented factor and its physical action."""

    physical_action: FullSpacePhysicalDtnActionSystem
    matrix: PETSc.Mat
    factor: ResearchExactFactorInverse
    factor_events: list[str]
    owns_physical_action: bool = True
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

    def _create_augmented_residual_rhs(
        self,
        fe_residual: PETSc.Vec,
        port_residual: np.ndarray,
    ) -> PETSc.Vec:
        rhs = self.create_rhs(fe_residual)
        try:
            first, last = (int(value) for value in rhs.getOwnershipRange())
            for index, value in enumerate(port_residual):
                row = self.full_rows + index
                if first <= row < last:
                    rhs.setValue(
                        row,
                        PETSc.ScalarType(value),
                        addv=PETSc.InsertMode.INSERT_VALUES,
                    )
            rhs.assemble()
            return rhs
        except BaseException:
            rhs.destroy()
            raise

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
        timing: MutableMapping[str, float] | None = None,
        diagnostic_audit: bool = False,
        capture_port_values: bool = False,
        diagnostic_correction_steps: int = 0,
        diagnostic_callback: Callable[
            [Mapping[str, Any], Mapping[str, Any]], None
        ]
        | None = None,
    ) -> dict[str, Any]:
        """Solve the augmented system, with opt-in same-factor corrections.

        Observer PETSc vectors are borrowed for the synchronous call only; the
        callback must not retain, modify, or destroy them.
        """
        diagnostic_correction_steps = _diagnostic_correction_count(
            diagnostic_correction_steps
        )
        diagnostic_mode = (
            diagnostic_correction_steps > 0 or diagnostic_callback is not None
        )
        audit_requested = diagnostic_audit or diagnostic_mode
        _require_vector_layout(rhs, self.augmented_rows, "p4 augmented RHS")
        _require_vector_layout(solution, self.augmented_rows, "p4 augmented solution")
        fe_rhs = self.extract_fe_solution(rhs)
        physical_rhs_norm = float(fe_rhs.norm())
        self._last_solve_audit = {
            "status": "started",
            "rhs_norm": physical_rhs_norm,
            "residual_norm": "not_measured",
            "relative_residual": "not_measured",
            "physical_residual_norm": "not_measured",
            "physical_relative_residual": "not_measured",
            "residual_tolerance": float(residual_tolerance),
            "backsolve_count": 0,
            "refinement_count": 0,
            "same_factor_refinement": False,
        }
        if not np.isfinite(physical_rhs_norm):
            fe_rhs.destroy()
            self._last_solve_audit["status"] = "failed_nonfinite_rhs"
            raise P4PhysicalResidualGateError(dict(self._last_solve_audit))
        backsolves = 0
        correction = None
        fe_solution = None
        physical_output = None
        physical_residual = None
        augmented_fe_residual = None
        effective_physical_residual = None
        port_residual: np.ndarray | None = None
        physical_relative = np.inf
        physical_residual_norm = np.inf
        augmented_relative = np.inf
        correction_history: list[dict[str, Any]] = []
        correction_seconds: float | None = None
        correction_norm: float | None = None
        last_factor_solve_seconds: float | None = None
        try:
            factor_started = time.perf_counter()
            try:
                self.factor.solve(rhs, solution)
            finally:
                last_factor_solve_seconds = time.perf_counter() - factor_started
                _timing_add(
                    timing,
                    "factor_solve_seconds",
                    last_factor_solve_seconds,
                )
            backsolves += 1
            for refinement in range(3):
                if fe_solution is not None:
                    fe_solution.destroy()
                if physical_output is not None:
                    physical_output.destroy()
                if physical_residual is not None:
                    physical_residual.destroy()
                if augmented_fe_residual is not None:
                    augmented_fe_residual.destroy()
                    augmented_fe_residual = None
                if effective_physical_residual is not None:
                    effective_physical_residual.destroy()
                    effective_physical_residual = None
                residual_started = time.perf_counter()
                try:
                    fe_solution = self.extract_fe_solution(solution)
                    physical_output = fe_solution.duplicate()
                    matrix_mult_started = time.perf_counter()
                    try:
                        self.physical_action.matrix.mult(fe_solution, physical_output)
                    finally:
                        _timing_add(
                            timing,
                            "physical_action_matrix_mult_seconds",
                            time.perf_counter() - matrix_mult_started,
                        )
                    physical_residual = fe_rhs.duplicate()
                    fe_rhs.copy(physical_residual)
                    physical_residual.axpy(
                        PETSc.ScalarType(-1.0),
                        physical_output,
                    )
                    physical_residual_norm = float(physical_residual.norm())
                    physical_relative = (
                        physical_residual_norm / physical_rhs_norm
                        if physical_rhs_norm > 0.0
                        else physical_residual_norm
                    )
                    physical_passed = bool(
                        np.isfinite(physical_relative)
                        and physical_relative <= float(residual_tolerance)
                    )

                    self._last_solve_audit = {
                        "status": (
                            "passed"
                            if physical_passed
                            else (
                                "failed_nonfinite_residual"
                                if not np.isfinite(physical_relative)
                                else "gate_failed"
                            )
                        ),
                        "rhs_norm": physical_rhs_norm,
                        "residual_norm": physical_residual_norm,
                        "relative_residual": physical_relative,
                        "physical_residual_norm": physical_residual_norm,
                        "physical_relative_residual": physical_relative,
                        "residual_tolerance": float(residual_tolerance),
                        "backsolve_count": backsolves,
                        "refinement_count": max(backsolves - 1, 0),
                        "same_factor_refinement": backsolves > 1,
                    }
                    if audit_requested:
                        row_start, row_end = (
                            int(value)
                            for value in solution.getOwnershipRange()
                        )
                        local_solution = None
                        local_rhs = None
                        try:
                            local_solution = np.asarray(
                                solution.getArray(readonly=True),
                                dtype=np.complex128,
                            )
                            local_rhs = np.asarray(
                                rhs.getArray(readonly=True),
                                dtype=np.complex128,
                            )
                            local_tail = np.zeros(
                                (2, self.n_aux), dtype=np.complex128
                            )
                            for index in range(self.n_aux):
                                row = self.full_rows + index
                                if row_start <= row < row_end:
                                    local_tail[0, index] = local_solution[
                                        row - row_start
                                    ]
                                    local_tail[1, index] = local_rhs[
                                        row - row_start
                                    ]
                        finally:
                            # These are PETSc-backed NumPy views. Release them
                            # before collectives and the diagnostic observer.
                            if local_solution is not None:
                                del local_solution
                            if local_rhs is not None:
                                del local_rhs
                        port_values = np.empty_like(local_tail)
                        self.matrix.getComm().tompi4py().Allreduce(
                            local_tail,
                            port_values,
                            op=MPI.SUM,
                        )
                        port_solution = port_values[0]
                        port_rhs = port_values[1]
                        d_solution = _physical_mode_projection(
                            fe_solution,
                            self.physical_action.action.modes,
                        )
                        port_residual = (
                            port_rhs
                            + d_solution
                            - port_solution
                        )
                        augmented_fe_residual = physical_residual.duplicate()
                        physical_residual.copy(augmented_fe_residual)
                        # physical_residual starts from bare b - A_phys u;
                        # the full block's effective RHS contributes T g_p,
                        # and its bottom-row residual subtracts T r_p.
                        _add_physical_mode_values(
                            augmented_fe_residual,
                            self.physical_action.action.modes,
                            port_rhs - port_residual,
                            scale=1.0,
                        )
                        augmented_fe_residual.assemble()
                        augmented_fe_norm = float(
                            augmented_fe_residual.norm()
                        )
                        port_residual_norm = float(
                            np.linalg.norm(port_residual)
                        )
                        augmented_residual_norm = float(
                            np.hypot(augmented_fe_norm, port_residual_norm)
                        )
                        augmented_rhs_norm = float(rhs.norm())
                        augmented_relative = (
                            augmented_residual_norm / augmented_rhs_norm
                            if augmented_rhs_norm > 0.0
                            else augmented_residual_norm
                        )
                        self._last_solve_audit.update(
                            {
                                "augmented_residual_source": (
                                    "existing_A4_residual_effective_rhs_minus_traction_port_residual"
                                ),
                                "augmented_fe_residual_norm": augmented_fe_norm,
                                "port_residual_norm": port_residual_norm,
                                "augmented_residual_norm": augmented_residual_norm,
                                "augmented_rhs_norm": augmented_rhs_norm,
                                "augmented_relative_residual": augmented_relative,
                                "augmented_residual_finite": bool(
                                    np.isfinite(augmented_relative)
                                ),
                                "augmented_gate_passed": bool(
                                    np.isfinite(augmented_relative)
                                    and augmented_relative
                                    <= float(residual_tolerance)
                                ),
                            }
                        )
                        if diagnostic_mode:
                            effective_rhs = fe_rhs.duplicate()
                            try:
                                fe_rhs.copy(effective_rhs)
                                _add_physical_mode_values(
                                    effective_rhs,
                                    self.physical_action.action.modes,
                                    port_rhs,
                                    scale=1.0,
                                )
                                effective_rhs.assemble()
                                effective_rhs_norm = float(effective_rhs.norm())
                            finally:
                                effective_rhs.destroy()
                            effective_physical_residual = (
                                augmented_fe_residual.duplicate()
                            )
                            augmented_fe_residual.copy(
                                effective_physical_residual
                            )
                            _add_physical_mode_values(
                                effective_physical_residual,
                                self.physical_action.action.modes,
                                port_residual,
                                scale=1.0,
                            )
                            effective_physical_residual.assemble()
                            bare_residual_norm = physical_residual_norm
                            bare_relative = physical_relative
                            physical_residual_norm = float(
                                effective_physical_residual.norm()
                            )
                            physical_relative = (
                                physical_residual_norm / effective_rhs_norm
                                if effective_rhs_norm > 0.0
                                else physical_residual_norm
                            )
                            physical_passed = bool(
                                np.isfinite(physical_relative)
                                and physical_relative
                                <= float(residual_tolerance)
                            )
                            self._last_solve_audit.update(
                                {
                                    "bare_physical_residual_norm": bare_residual_norm,
                                    "bare_physical_relative_residual": bare_relative,
                                    "rhs_norm": effective_rhs_norm,
                                    "residual_norm": physical_residual_norm,
                                    "relative_residual": physical_relative,
                                    "physical_rhs_norm": effective_rhs_norm,
                                    "effective_physical_residual_norm": physical_residual_norm,
                                    "physical_residual_norm": physical_residual_norm,
                                    "physical_relative_residual": physical_relative,
                                    "physical_gate_passed": physical_passed,
                                }
                            )
                        if capture_port_values:
                            self._last_solve_audit.update(
                                {
                                    "port_solution_complex": [
                                        [float(value.real), float(value.imag)]
                                        for value in port_solution
                                    ],
                                    "port_rhs_complex": [
                                        [float(value.real), float(value.imag)]
                                        for value in port_rhs
                                    ],
                                    "port_projection_complex": [
                                        [float(value.real), float(value.imag)]
                                        for value in d_solution
                                    ],
                                }
                            )
                    else:
                        port_solution = np.empty(0, dtype=np.complex128)
                        port_rhs = np.empty(0, dtype=np.complex128)
                        port_residual = None
                finally:
                    _timing_add(
                        timing,
                        "A4_residual_refinement_seconds",
                        time.perf_counter() - residual_started,
                    )

                augmented_passed = bool(
                    self._last_solve_audit.get("augmented_gate_passed", False)
                )
                if diagnostic_mode:
                    nonfinite_residual = not np.isfinite(
                        physical_relative
                    ) or not np.isfinite(augmented_relative)
                    self._last_solve_audit.update(
                        {
                            "status": (
                                "failed_nonfinite_residual"
                                if nonfinite_residual
                                else (
                                    "passed"
                                    if physical_passed and augmented_passed
                                    else "gate_failed"
                                )
                            ),
                            "physical_gate_passed": bool(physical_passed),
                        }
                    )
                    diagnostic_record = dict(self._last_solve_audit)
                    diagnostic_record.update(
                        {
                            "diagnostic_step_index": int(refinement),
                            "diagnostic_correction_count": int(refinement),
                            "diagnostic_correction_limit": int(
                                diagnostic_correction_steps
                            ),
                            "correction_from_previous_seconds": correction_seconds,
                            "correction_from_previous_norm": correction_norm,
                            "factor_solve_seconds_for_state": last_factor_solve_seconds,
                            "backsolve_count": int(backsolves),
                            "refinement_count": int(backsolves - 1),
                        }
                    )
                    correction_history.append(
                        {
                            key: value
                            for key, value in diagnostic_record.items()
                            if isinstance(
                                value,
                                (bool, int, float, str, type(None)),
                            )
                        }
                    )
                    self._last_solve_audit[
                        "diagnostic_correction_history"
                    ] = tuple(correction_history)
                    diagnostic_record[
                        "diagnostic_correction_history"
                    ] = tuple(correction_history)
                    if diagnostic_callback is not None:
                        _emit_p4_diagnostic(
                            self.matrix.getComm().tompi4py(),
                            diagnostic_callback,
                            diagnostic_record,
                            {
                                "solution": solution,
                                "fe_residual": augmented_fe_residual,
                                "physical_residual": physical_residual,
                                "effective_physical_residual": effective_physical_residual,
                                "port_residual": _readonly_diagnostic_array(
                                    port_residual
                                ),
                                "port_solution": _readonly_diagnostic_array(
                                    port_solution
                                ),
                                "port_rhs": _readonly_diagnostic_array(port_rhs),
                                "correction": correction,
                            },
                        )
                    if nonfinite_residual:
                        raise P4PhysicalResidualGateError(
                            dict(self._last_solve_audit)
                        )
                    if refinement >= diagnostic_correction_steps:
                        if not (physical_passed and augmented_passed):
                            self._last_solve_audit["status"] = "failed_gate"
                            raise P4PhysicalResidualGateError(
                                dict(self._last_solve_audit)
                            )
                        break
                else:
                    if not np.isfinite(physical_relative):
                        raise P4PhysicalResidualGateError(
                            dict(self._last_solve_audit)
                        )
                    if physical_passed:
                        break
                    if refinement == 2:
                        break
                if correction is not None:
                    correction.destroy()
                    correction = None
                correction = solution.duplicate()
                if diagnostic_mode:
                    if augmented_fe_residual is None or port_residual is None:
                        raise AssertionError(
                            "diagnostic augmented residual was not created"
                        )
                    correction_rhs = self._create_augmented_residual_rhs(
                        augmented_fe_residual,
                        port_residual,
                    )
                else:
                    correction_rhs = self.create_rhs(physical_residual)
                correction_started = (
                    time.perf_counter() if diagnostic_mode else 0.0
                )
                try:
                    factor_started = time.perf_counter()
                    try:
                        self.factor.solve(correction_rhs, correction)
                    finally:
                        last_factor_solve_seconds = (
                            time.perf_counter() - factor_started
                        )
                        _timing_add(
                            timing,
                            "factor_solve_seconds",
                            last_factor_solve_seconds,
                        )
                finally:
                    correction_rhs.destroy()
                backsolves += 1
                solution.axpy(PETSc.ScalarType(1.0), correction)
                if diagnostic_mode:
                    correction_norm = float(correction.norm())
                    correction_seconds = time.perf_counter() - correction_started
            gate_failed = (
                not np.isfinite(physical_relative)
                or physical_relative > float(residual_tolerance)
            )
            if diagnostic_mode:
                gate_failed = gate_failed or (
                    not np.isfinite(augmented_relative)
                    or augmented_relative > float(residual_tolerance)
                )
            if gate_failed:
                self._last_solve_audit["status"] = "failed_gate"
                raise P4PhysicalResidualGateError(dict(self._last_solve_audit))
            return dict(self._last_solve_audit)
        except BaseException as error:
            if diagnostic_mode and self._last_solve_audit:
                self._last_solve_audit["error_type"] = type(error).__name__
                self._last_solve_audit["error"] = str(error)
            raise
        finally:
            fe_rhs.destroy()
            if fe_solution is not None:
                fe_solution.destroy()
            if physical_output is not None:
                physical_output.destroy()
            if physical_residual is not None:
                physical_residual.destroy()
            if augmented_fe_residual is not None:
                augmented_fe_residual.destroy()
            if effective_physical_residual is not None:
                effective_physical_residual.destroy()
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
        if self.owns_physical_action:
            self.physical_action.destroy()
        self._destroyed = True


def build_p4_exact_factor(
    side_system: HybridLocalDtnActionSystem,
    *,
    factor_solver_type: str = "mumps",
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> P4ExactFactor:
    """Build one distributed p4 augmented matrix and its single exact factor."""

    if not isinstance(side_system, HybridLocalDtnActionSystem):
        raise TypeError("p4 exact factor requires HybridLocalDtnActionSystem")
    if int(side_system.cfg.nedelec_degree) != 6:
        raise ValueError("p4 exact factor requires a p6 side system")

    physical = None
    matrix = None
    factor = None
    events: list[str] = []

    def lifecycle(event: str, _details: Mapping[str, Any]) -> None:
        events.append(str(event))

    try:
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_form_assembly_begin",
                {"scope": "side_local", "degree": 4},
            )
        physical = _build_matching_p4_action(side_system)
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_form_assembly_ready",
                {
                    "scope": "side_local",
                    "degree": 4,
                    "object_inventory": _full_action_inventory(
                        physical,
                        owner="p4.physical_action",
                    ),
                },
            )
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_matrix_assembly_begin",
                {"scope": "side_local", "degree": 4},
            )
        matrix = _assemble_augmented_matrix(physical)
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_matrix_assembly_ready",
                {
                    "scope": "side_local",
                    "degree": 4,
                    "object_inventory": {
                        "owned_objects": [_p4_matrix_inventory(matrix)],
                        "native_workspace_bytes": "unknown",
                    },
                },
            )
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_factor_begin",
                {
                    "scope": "side_local",
                    "factor_solver_type": factor_solver_type,
                    "backend_lifecycle": "combined",
                },
            )
        factor = ResearchExactFactorInverse(
            matrix,
            factor_solver_type=factor_solver_type,
            factor_only_storage=True,
            lifecycle_callback=lifecycle,
        )
        if lifecycle_callback is not None:
            factor_inventory = _p4_matrix_inventory(matrix)
            factor_inventory["ownership"] = (
                "retained by P4ExactFactor until destroy"
            )
            lifecycle_callback(
                "p4_factor_ready",
                {
                    "scope": "side_local",
                    "factor_solver_type": factor_solver_type,
                    "backend_lifecycle": "combined",
                    "backend_events": tuple(events),
                    "object_inventory": {
                        "owned_objects": [
                            factor_inventory,
                            {
                                "label": "p4.factor",
                                "kind": "ResearchExactFactorInverse",
                                "ownership": (
                                    "retained by P4ExactFactor until destroy"
                                ),
                                "payload_bytes_local": "unknown",
                            },
                        ],
                        "native_workspace_bytes": "unknown",
                    },
                },
            )
        return P4ExactFactor(
            physical_action=physical,
            matrix=matrix,
            factor=factor,
            factor_events=events,
        )
    except Exception:
        if factor is not None:
            factor.destroy()
        if matrix is not None:
            matrix.destroy()
        if physical is not None:
            physical.destroy()
        raise


def _build_p4_condensed_from_physical(
    physical_action: FullSpacePhysicalDtnActionSystem,
    *,
    factor_solver_type: str = "mumps",
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    owns_physical_action: bool,
) -> P4CondensedExactFactor:
    """Build the opt-in p4 factor around an explicit physical action."""

    if not isinstance(physical_action, FullSpacePhysicalDtnActionSystem):
        raise TypeError("condensed p4 factor requires a physical p4 action")
    if int(physical_action.cfg.nedelec_degree) != 4:
        raise ValueError("condensed p4 factor requires a p4 physical action")

    physical = physical_action
    condensed = None
    factor = None
    inverse = None
    events: list[str] = []

    def lifecycle(event: str, _details: Mapping[str, Any]) -> None:
        events.append(str(event))

    try:
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_condensed_form_assembly_begin",
                {"scope": "side_local", "degree": 4},
            )
        support_cells = _owned_cells_adjacent_to_facet_tag(
            physical.local_mesh.mesh_data,
            physical.local_mesh.external_facet_tag,
        )
        n_ports = len(physical.action.modes)
        condensed = build_unconstrained_assembly_time_condensation(
            fem.form(physical.bilinear_form),
            physical.V,
            physical.local_mesh.mesh_data.cell_tags,
            mpc=physical.floquet_data.mpc,
            appended_global_rows=n_ports,
            appended_support_owned_cell_groups=(support_cells,),
            appended_support_group_by_row=tuple(0 for _ in range(n_ports)),
            appended_support_include_group_rows=True,
            defer_final_assembly=True,
            materialize_global_matrix=True,
        )
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_condensed_trace_ready",
                {
                    "scope": "side_local",
                    "degree": 4,
                    "ports": n_ports,
                    "support_cells_local": tuple(map(int, support_cells)),
                    "object_inventory": dict(condensed.build_audit),
                },
            )
        port_terms = _prepare_physical_p4_port_terms(condensed, physical)
        port_audit = assemble_port_condensed_terms(condensed, port_terms)
        if lifecycle_callback is not None:
            lifecycle_callback(
                "p4_condensed_port_ready",
                {
                    "scope": "side_local",
                    "ports": n_ports,
                    "port_audit": port_audit,
                },
            )
        factor = ResearchExactFactorInverse(
            condensed.matrix,
            factor_solver_type=factor_solver_type,
            factor_only_storage=True,
            lifecycle_callback=lifecycle,
        )
        inverse = P4CellCondensedInverse(
            condensed,
            factor,
            port_terms=port_terms,
            owns_condensed=True,
            owns_factor=True,
        )
        return P4CondensedExactFactor(
            physical_action=physical,
            inverse=inverse,
            factor_events=events,
            owns_physical_action=owns_physical_action,
        )
    except Exception:
        if inverse is not None:
            inverse.destroy()
        elif factor is not None:
            factor.destroy()
            if condensed is not None:
                condensed.destroy()
        elif condensed is not None:
            condensed.destroy()
        if owns_physical_action:
            physical.destroy()
        raise


def build_p4_condensed_exact_factor_from_action(
    physical_action: FullSpacePhysicalDtnActionSystem,
    *,
    factor_solver_type: str = "mumps",
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    owns_physical_action: bool = False,
) -> P4CondensedExactFactor:
    """Build a condensed factor while explicitly borrowing or owning action."""

    return _build_p4_condensed_from_physical(
        physical_action,
        factor_solver_type=factor_solver_type,
        lifecycle_callback=lifecycle_callback,
        owns_physical_action=owns_physical_action,
    )


def build_p4_condensed_exact_factor(
    side_system: HybridLocalDtnActionSystem,
    *,
    factor_solver_type: str = "mumps",
    lifecycle_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> P4CondensedExactFactor:
    """Build the opt-in p4 factor without materializing a full FE matrix."""

    if not isinstance(side_system, HybridLocalDtnActionSystem):
        raise TypeError("condensed p4 factor requires a p6 side system")
    if int(side_system.cfg.nedelec_degree) != 6:
        raise ValueError("condensed p4 factor requires a p6 side system")
    physical = _build_matching_p4_action(side_system)
    return _build_p4_condensed_from_physical(
        physical,
        factor_solver_type=factor_solver_type,
        lifecycle_callback=lifecycle_callback,
        owns_physical_action=True,
    )
