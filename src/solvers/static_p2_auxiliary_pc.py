"""Small never-materialized p2 auxiliary preconditioner composition.

The fine operator remains a borrowed p6 action.  The coarse operator is the
already projected M4b ``F2-C2 H2^-1 D2`` composition.  This module only owns
the shifted p2 factor, the modal correction, and temporary vectors; it never
builds a p6 factor or a global transfer matrix.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from basix.ufl import element
import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from dolfinx import default_real_type, fem

from ..constraints.floquet_3d import build_double_floquet_mpc
from .condensed_dtn import project_condensed_blocks_to_coarse
from .hcurl_assembly_time_condensation import (
    _owned_trace_numbering,
    _trace_constraint_map,
)
from .hcurl_multilevel import ModalWoodburyPc, build_absorption_shifted_matrix
from .physical_slab_two_level import build_owner_local_slab_diagonal
from .static_factor_free_slab_pc import FactorFreeLocalSlabKrylovPc
from .static_trace_auxiliary import (
    build_p2_galerkin_fine_matrix,
    build_p2_to_p6_active_trace_transfer,
)

__all__ = (
    "P2AuxiliaryDiagonalModalPc",
    "build_p2_auxiliary_setup",
)


class _PreonlyMumpsLu:
    """Owner of one p2 shifted matrix and its PREONLY/MUMPS solve."""

    def __init__(self, shifted_matrix: PETSc.Mat) -> None:
        self.matrix = shifted_matrix
        self.ksp = PETSc.KSP().create(shifted_matrix.getComm())
        self.ksp.setOperators(shifted_matrix)
        self.ksp.setType("preonly")
        pc = self.ksp.getPC()
        pc.setType("lu")
        pc.setFactorSolverType("mumps")
        self.ksp.setUp()
        self.factor_solver_type = pc.getFactorSolverType()
        self._destroyed = False

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("p2 LU has already been destroyed")
        self.ksp.solve(source, target)

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.ksp.destroy()
        self._destroyed = True


class _ProvidedDiagonalPatch:
    """Apply the fixed omega inverse of one supplied fine diagonal."""

    def __init__(
        self,
        diagonal: PETSc.Vec,
        *,
        absorption_shift: float,
        omega: float,
    ) -> None:
        self.comm = diagonal.getComm().tompi4py()
        self.omega = float(omega)
        self.absorption_shift = float(absorption_shift)
        values = np.asarray(
            diagonal.getArray(readonly=True), dtype=PETSc.ScalarType
        ).copy()
        local_scale = float(np.max(np.abs(values), initial=0.0))
        self.global_scale = float(self.comm.allreduce(local_scale, op=MPI.MAX))
        shifted = values - 1j * self.absorption_shift * np.maximum(
            np.abs(values), 1.0e-12 * self.global_scale
        )
        self._inverse = self.omega / shifted
        self.local_bytes = int(self._inverse.nbytes)
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("fine diagonal patch has already been destroyed")
        if source.getOwnershipRange() != target.getOwnershipRange():
            raise ValueError("fine diagonal patch vector ownership mismatch")
        target.getArray()[:] = self._inverse * source.getArray(readonly=True)
        target.assemble()

    def destroy(self) -> None:
        if not self._destroyed:
            self._inverse = np.empty(0, dtype=PETSc.ScalarType)
            self._destroyed = True


class P2AuxiliaryDiagonalModalPc:
    """Compose a fine pre/post patch with the true p2 auxiliary PC.

    ``fine_operator``, ``transfer`` and ``fine_diagonal`` are borrowed.  The
    projected ``coarse_blocks`` are transferred to this object and destroyed
    with it.  The p2 matrix is shifted through the existing absorption helper,
    factorized once with PREONLY/MUMPS, and corrected with the existing
    all-mode Woodbury algebra.  With no ``fine_patch``, the supplied diagonal
    provides the pre/post patch.  With a ``fine_patch``, that factor-free
    patch provides both applications and is owned and destroyed by this PC.
    """

    def __init__(
        self,
        *,
        fine_operator: PETSc.Mat,
        transfer: Any,
        coarse_blocks: Any,
        fine_diagonal: PETSc.Vec,
        absorption_shift: float = 0.1,
        omega: float = 0.6,
        fine_patch: FactorFreeLocalSlabKrylovPc | None = None,
    ) -> None:
        if coarse_blocks.F is None:
            raise ValueError("p2 auxiliary PC requires the projected F2 matrix")
        if not np.isfinite(float(omega)) or float(omega) <= 0.0:
            raise ValueError("diagonal patch omega must be finite and positive")
        if fine_operator.getSize()[0] != transfer.fine_constraints.active_rows:
            raise ValueError("fine action size does not match the p2-to-p6 transfer")
        if int(fine_diagonal.getSize()) != int(fine_operator.getSize()[0]):
            raise ValueError("fine diagonal size does not match the fine action")
        if tuple(map(int, fine_diagonal.getOwnershipRange())) != tuple(
            map(int, fine_operator.getOwnershipRange())
        ):
            raise ValueError("fine diagonal ownership does not match the fine action")

        self.fine_operator = fine_operator
        self.transfer = transfer
        self.coarse_blocks = coarse_blocks
        self._fine_patch = fine_patch
        self._destroyed = False
        self._absorption_shift = float(absorption_shift)
        self._patch = (
            None
            if fine_patch is not None
            else _ProvidedDiagonalPatch(
                fine_diagonal,
                absorption_shift=absorption_shift,
                omega=omega,
            )
        )
        self.p2_shifted_matrix, p2_scale = build_absorption_shifted_matrix(
            coarse_blocks.F,
            absorption_shift,
        )
        coarse_blocks.release_f()
        self._p2_lu = _PreonlyMumpsLu(self.p2_shifted_matrix)
        self._modal = ModalWoodburyPc(
            base_solver=self._p2_lu,
            C=coarse_blocks.C,
            D=coarse_blocks.D,
            H=coarse_blocks.H,
        )
        self._fine_pre = fine_operator.createVecRight()
        self._fine_work = fine_operator.createVecLeft()
        self._fine_residual = fine_operator.createVecLeft()
        self._fine_correction = fine_operator.createVecRight()
        self._fine_post = fine_operator.createVecRight()
        self._coarse_rhs = coarse_blocks.C.createVecLeft()
        self._coarse_solution = coarse_blocks.C.createVecLeft()
        self._p2_scale = float(p2_scale)
        self.apply_count = 0

    def _check_layout(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        expected = tuple(map(int, self.fine_operator.getOwnershipRange()))
        if tuple(map(int, source.getOwnershipRange())) != expected:
            raise ValueError("fine PC source ownership does not match fine action")
        if tuple(map(int, target.getOwnershipRange())) != expected:
            raise ValueError("fine PC target ownership does not match fine action")

    def apply(
        self,
        _pc: PETSc.PC | None,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        """Apply diagonal-pre, p2 auxiliary, and diagonal-post corrections."""

        if self._destroyed:
            raise RuntimeError("p2 auxiliary PC has already been destroyed")
        self._check_layout(source, target)
        if self._fine_patch is None:
            self._patch.apply(source, self._fine_pre)
        else:
            self._fine_patch.apply(source, self._fine_pre)
        self.fine_operator.mult(self._fine_pre, self._fine_work)
        self._fine_residual.getArray()[:] = source.getArray(readonly=True)
        self._fine_residual.axpy(-1.0, self._fine_work)
        self.transfer.apply_adjoint(self._fine_residual, self._coarse_rhs)
        self._modal.solve(self._coarse_rhs, self._coarse_solution)
        self.transfer.apply(self._coarse_solution, self._fine_correction)
        target.getArray()[:] = self._fine_pre.getArray(readonly=True)
        target.axpy(1.0, self._fine_correction)
        self.fine_operator.mult(target, self._fine_work)
        self._fine_residual.getArray()[:] = source.getArray(readonly=True)
        self._fine_residual.axpy(-1.0, self._fine_work)
        if self._fine_patch is None:
            self._patch.apply(self._fine_residual, self._fine_post)
        else:
            self._fine_patch.apply(self._fine_residual, self._fine_post)
        target.axpy(1.0, self._fine_post)
        target.assemble()
        self.apply_count += 1

    def solve(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self.apply(None, source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        info = self.p2_shifted_matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        comm = self.fine_operator.getComm().tompi4py()
        p2_factor = self._p2_lu.ksp.getPC().getFactorSolverType()
        factor_matrix = self._p2_lu.ksp.getPC().getFactorMatrix()
        factor_info = (
            factor_matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
            if factor_matrix is not None
            else {}
        )
        factor_nnz = int(factor_info.get("nz_used", 0.0))
        factor_memory_petsc = int(factor_info.get("memory", 0.0))
        factor_payload_lower_bound = int(
            factor_nnz
            * (np.dtype(PETSc.ScalarType).itemsize + np.dtype(PETSc.IntType).itemsize)
            + (self.p2_shifted_matrix.getSize()[0] + 1)
            * np.dtype(PETSc.IntType).itemsize
        )
        transfer_audit = self.transfer.audit
        transfer_bytes = {
            "owner_local_stencil_nbytes": int(
                transfer_audit["owner_local_stencil_nbytes"]
            ),
            "source_staging_nbytes": int(transfer_audit["source_staging_nbytes"]),
            "communication_index_nbytes": int(
                transfer_audit["communication_index_nbytes"]
            ),
        }
        work_vector_bytes_local = int(
            sum(
                vector.getLocalSize() * np.dtype(PETSc.ScalarType).itemsize
                for vector in (
                    self._fine_pre,
                    self._fine_work,
                    self._fine_residual,
                    self._fine_correction,
                    self._fine_post,
                    self._coarse_rhs,
                    self._coarse_solution,
                )
            )
        )
        info_dict = {
            "profile": (
                "never_materialized_p2_auxiliary"
                if self._fine_patch is None
                else "never_materialized_p2_factor_free_slab_auxiliary"
            ),
            "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
            "global_p6_matrix_materialized": False,
            "global_p6_transfer_materialized": False,
            "global_p6_factor_count": 0,
            "p6_slab_matrix_count": 0,
            "p6_factor_only_storage": False,
            "p2_matrix_materialized": True,
            "p2_factor_count": 1,
            "p2_factor_solver_type": p2_factor,
            "p2_factor_nnz_used": (factor_nnz if factor_matrix is not None else None),
            "p2_factor_petsc_memory_bytes": factor_memory_petsc,
            "p2_factor_petsc_memory_available": factor_memory_petsc > 0,
            "p2_factor_payload_lower_bound_bytes": (
                factor_payload_lower_bound if factor_matrix is not None else None
            ),
            "p2_rows": int(self.p2_shifted_matrix.getSize()[0]),
            "p2_matrix_nnz_used": int(info.get("nz_used", 0.0)),
            "p2_matrix_memory_bytes": int(info.get("memory", 0.0)),
            "p2_unshifted_matrix_retained": self.coarse_blocks.F is not None,
            "p2_absorption_shift": self._absorption_shift,
            "p2_diagonal_scale": self._p2_scale,
            "modal": self._modal.diagnostics,
            "work_vectors_owned": 7,
            "work_vector_bytes_local": work_vector_bytes_local,
            "work_vector_bytes_global": int(
                comm.allreduce(work_vector_bytes_local, op=MPI.SUM)
            ),
            "transfer_owner_local_stencil_nbytes_local": transfer_bytes[
                "owner_local_stencil_nbytes"
            ],
            "transfer_owner_local_stencil_nbytes_global": int(
                comm.allreduce(
                    transfer_bytes["owner_local_stencil_nbytes"],
                    op=MPI.SUM,
                )
            ),
            "transfer_source_staging_nbytes_local": transfer_bytes[
                "source_staging_nbytes"
            ],
            "transfer_source_staging_nbytes_global": int(
                comm.allreduce(
                    transfer_bytes["source_staging_nbytes"],
                    op=MPI.SUM,
                )
            ),
            "transfer_communication_index_nbytes_local": transfer_bytes[
                "communication_index_nbytes"
            ],
            "transfer_communication_index_nbytes_global": int(
                comm.allreduce(
                    transfer_bytes["communication_index_nbytes"],
                    op=MPI.SUM,
                )
            ),
            "apply_count": int(self.apply_count),
        }
        if self._fine_patch is None:
            info_dict["diagonal_patch"] = {
                "omega": self._patch.omega,
                "absorption_shift": self._patch.absorption_shift,
                "global_scale": self._patch.global_scale,
                "inverse_bytes_local": self._patch.local_bytes,
                "inverse_bytes_global": int(
                    comm.allreduce(self._patch.local_bytes, op=MPI.SUM)
                ),
                "pre_post": True,
            }
        else:
            info_dict["factor_free_slab_patch"] = self._fine_patch.diagnostics
            info_dict["outer_requires_fgmres"] = True
            info_dict["high_order_patch_kind"] = "factor_free_local_slab_krylov"
        return info_dict

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._modal.destroy()
        self._p2_lu.destroy()
        self.p2_shifted_matrix.destroy()
        if self._fine_patch is None:
            self._patch.destroy()
        else:
            self._fine_patch.destroy()
        for vector in (
            self._fine_pre,
            self._fine_work,
            self._fine_residual,
            self._fine_correction,
            self._fine_post,
            self._coarse_rhs,
            self._coarse_solution,
        ):
            vector.destroy()
        self.coarse_blocks.destroy()
        self._destroyed = True


def _constraint_map_for_space(space, mpc) -> Any:
    interior_positions = np.asarray(
        space.element.basix_element.entity_dofs[3][0], dtype=np.int32
    )
    topology = space.mesh.topology
    owned_cells = int(topology.index_map(topology.dim).size_local)
    local_interiors = tuple(
        np.asarray(
            space.dofmap.index_map.local_to_global(
                np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
            ),
            dtype=PETSc.IntType,
        )[interior_positions]
        for cell in range(owned_cells)
    )
    owned_trace, mapping, trace_rows, _full_rows = _owned_trace_numbering(
        space, local_interiors
    )
    return _trace_constraint_map(
        space,
        owned_trace,
        mapping,
        trace_rows,
        mpc,
    )


def build_p2_auxiliary_setup(
    *,
    fine_space: Any,
    fine_condensed: Any,
    fine_operator: PETSc.Mat,
    fine_blocks: Any,
    mesh_data: Any,
    config: Any,
) -> tuple[P2AuxiliaryDiagonalModalPc, Any, PETSc.Vec, dict[str, Any]]:
    """Build the same-mesh p2 auxiliary PC without a p6 global matrix."""

    p2_config = replace(
        config,
        nedelec_degree=2,
        nedelec_trace_degree=None,
        nedelec_interior_degree=None,
    )
    p2_space = fem.functionspace(
        fine_space.mesh,
        element(
            "N1curl",
            fine_space.mesh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    p2_floquet_data = build_double_floquet_mpc(p2_space, mesh_data, p2_config)
    p2_constraints = _constraint_map_for_space(p2_space, p2_floquet_data.mpc)
    del p2_floquet_data
    transfer = build_p2_to_p6_active_trace_transfer(
        p2_space,
        fine_space,
        p2_constraints,
        fine_condensed.trace_constraints,
    )
    f2, f2_audit = build_p2_galerkin_fine_matrix(
        fine_condensed,
        p2_space,
        fine_space,
        p2_constraints,
    )
    coarse_blocks, projected_audit = project_condensed_blocks_to_coarse(
        fine_blocks,
        transfer,
        f2,
    )
    fine_diagonal, diagonal_audit = build_owner_local_slab_diagonal(fine_condensed)
    pc = P2AuxiliaryDiagonalModalPc(
        fine_operator=fine_operator,
        transfer=transfer,
        coarse_blocks=coarse_blocks,
        fine_diagonal=fine_diagonal,
    )
    audit = {
        "profile": "never_materialized_p2_auxiliary",
        "global_p6_matrix_materialized": False,
        "global_p6_transfer_materialized": False,
        "p2": {
            "active_rows": int(p2_constraints.active_rows),
            "f2": f2_audit,
            "projected_blocks": projected_audit,
            "diagonal": diagonal_audit,
        },
        "fine_operator_kind": "borrowed_p6_condensed_dtn_action",
    }
    return pc, transfer, fine_diagonal, audit
