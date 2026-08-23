"""Native-complex HX-style inverse for a positive LOR edge operator.

The high-order physical action is deliberately outside this module.  This
core owns one positive LOR edge matrix, one scalar nodal PCGAMG hierarchy,
and the fixed Hiptmair--Xu correction sequence used by the L2 oracle:
edge Jacobi, gradient correction, x/y/z vector-nodal corrections, and edge
Jacobi.  It accepts already assembled LOR matrices; it never assembles a
high-order matrix, creates a global transfer matrix, or gathers numeric data.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from petsc4py import PETSc


LOR_HX_EDGE_JACOBI_OMEGA = 2.0 / 3.0
LOR_HX_GAMG_MAX_LEVELS = 8
LOR_HX_VECTOR_AXES = ("x", "y", "z")
LOR_HX_VARIANT_SEQUENTIAL = "sequential-v1"
LOR_HX_VARIANT_ADDITIVE = "additive-v2"
LOR_HX_FORBIDDEN_PC_TYPES = frozenset(
    {"lu", "cholesky", "redundant", "hypre", "ams"}
)


def _shape(matrix: Any) -> tuple[int, int]:
    return tuple(int(value) for value in matrix.getSize())


def _require_shape(matrix: Any, expected: tuple[int, int], name: str) -> None:
    if _shape(matrix) != expected:
        raise ValueError(f"{name} has shape {_shape(matrix)}, expected {expected}")


def _finite_local(vector: PETSc.Vec) -> bool:
    return bool(np.all(np.isfinite(np.asarray(vector.array))))


class NativeComplexLORHX:
    """Apply the fixed native-complex LOR-HX correction sequence.

    Matrix arguments are borrowed.  The object owns only its scalar KSP and
    the copied edge-Jacobi diagonal.  The scalar KSP is ``preonly`` with one
    PCGAMG application per nodal correction; x/y/z reuse that same hierarchy.
    """

    def __init__(
        self,
        edge_matrix: Any,
        nodal_matrix: Any,
        gradient: Any,
        gradient_adjoint: Any,
        vector_prolongations: Sequence[Any],
        vector_restrictions: Sequence[Any],
        *,
        variant: str = LOR_HX_VARIANT_SEQUENTIAL,
    ) -> None:
        self._destroyed = False
        if variant not in (LOR_HX_VARIANT_SEQUENTIAL, LOR_HX_VARIANT_ADDITIVE):
            raise ValueError(f"unsupported LOR-HX variant {variant!r}")
        self._variant = variant
        self._edge_matrix = edge_matrix
        self._nodal_matrix = nodal_matrix
        self._gradient = gradient
        self._gradient_adjoint = gradient_adjoint
        self._vector_prolongations = tuple(vector_prolongations)
        self._vector_restrictions = tuple(vector_restrictions)
        if len(self._vector_prolongations) != 3 or len(self._vector_restrictions) != 3:
            raise ValueError("HX requires exactly x/y/z vector corrections")

        edge_rows, edge_cols = _shape(edge_matrix)
        if edge_rows != edge_cols:
            raise ValueError("LOR edge operator must be square")
        node_rows, node_cols = _shape(nodal_matrix)
        if node_rows != node_cols:
            raise ValueError("scalar nodal operator must be square")
        _require_shape(gradient, (edge_rows, node_rows), "gradient")
        _require_shape(gradient_adjoint, (node_rows, edge_rows), "gradient_adjoint")
        for axis, (prolongation, restriction) in enumerate(
            zip(
                self._vector_prolongations,
                self._vector_restrictions,
                strict=True,
            )
        ):
            _require_shape(prolongation, (edge_rows, node_rows), f"Pi_{LOR_HX_VECTOR_AXES[axis]}")
            _require_shape(restriction, (node_rows, edge_rows), f"Pi_{LOR_HX_VECTOR_AXES[axis]}_adjoint")

        diagonal = edge_matrix.createVecLeft()
        edge_matrix.getDiagonal(diagonal)
        diagonal_values = np.asarray(diagonal.array, dtype=np.complex128).copy()
        diagonal.destroy()
        if not np.all(np.isfinite(diagonal_values)) or np.any(
            np.real(diagonal_values) <= 0.0
        ):
            raise ValueError("LOR edge Jacobi diagonal is not finite positive")
        self._edge_diagonal_inverse = 1.0 / diagonal_values

        self._nodal_ksp = PETSc.KSP().create(nodal_matrix.getComm())
        self._nodal_ksp.setOptionsPrefix("l2_native_hx_")
        self._nodal_ksp.setOperators(nodal_matrix)
        self._nodal_ksp.setType("preonly")
        nodal_pc = self._nodal_ksp.getPC()
        nodal_pc.setType("gamg")
        nodal_pc.setGAMGType("agg")
        nodal_pc.setGAMGLevels(LOR_HX_GAMG_MAX_LEVELS)
        options = PETSc.Options()
        options["l2_native_hx_ksp_type"] = "preonly"
        options["l2_native_hx_pc_type"] = "gamg"
        options["l2_native_hx_pc_gamg_type"] = "agg"
        options["l2_native_hx_pc_gamg_levels"] = str(LOR_HX_GAMG_MAX_LEVELS)
        options["l2_native_hx_mg_coarse_pc_type"] = "jacobi"
        options["l2_native_hx_mg_coarse_ksp_type"] = "preonly"
        self._nodal_ksp.setFromOptions()
        nodal_pc.setType("gamg")
        nodal_pc.setGAMGType("agg")
        nodal_pc.setGAMGLevels(LOR_HX_GAMG_MAX_LEVELS)
        self._nodal_ksp.setUp()
        for option_name in (
            "l2_native_hx_ksp_type",
            "l2_native_hx_pc_type",
            "l2_native_hx_pc_gamg_type",
            "l2_native_hx_pc_gamg_levels",
            "l2_native_hx_mg_coarse_pc_type",
            "l2_native_hx_mg_coarse_ksp_type",
        ):
            options.delValue(option_name)

        observed_levels = int(nodal_pc.getMGLevels())
        if not 1 <= observed_levels <= LOR_HX_GAMG_MAX_LEVELS:
            raise RuntimeError(
                "PCGAMG observed levels outside fixed maximum: "
                f"{observed_levels} not in [1, {LOR_HX_GAMG_MAX_LEVELS}]"
            )
        coarse = nodal_pc.getMGCoarseSolve()
        coarse_ksp_type = "none"
        coarse_pc_type = "none"
        if coarse is not None:
            coarse_ksp_type = str(coarse.getType())
            coarse_pc_type = str(coarse.getPC().getType())
            if coarse_ksp_type != "preonly" or coarse_pc_type != "jacobi":
                raise RuntimeError(
                    "L2 coarse PC contract is not preonly+jacobi: "
                    f"ksp={coarse_ksp_type}, pc={coarse_pc_type}"
                )
        level_pcs: list[str] = []
        for level in range(observed_levels):
            smoother = nodal_pc.getMGSmoother(level)
            if smoother is not None:
                level_pcs.append(str(smoother.getPC().getType()))
        forbidden = sorted(
            set(level_pcs + [coarse_pc_type]) & LOR_HX_FORBIDDEN_PC_TYPES
        )
        if forbidden:
            raise RuntimeError(f"forbidden scalar PC type observed: {forbidden}")

        self._observed_levels = observed_levels
        self._coarse_ksp_type = coarse_ksp_type
        self._coarse_pc_type = coarse_pc_type
        self._level_pcs = tuple(level_pcs)
        self._apply_count = 0
        self._last_correction_count = 0
        self._last_output_finite = False

    @property
    def audit(self) -> dict[str, Any]:
        if self._destroyed:
            raise RuntimeError("HX object has been destroyed")
        return {
            "schema": (
                "task038.lor-native-complex-hx.v2"
                if self._variant == LOR_HX_VARIANT_ADDITIVE
                else "task038.lor-native-complex-hx.v1"
            ),
            "variant": self._variant,
            "composition": (
                "additive" if self._variant == LOR_HX_VARIANT_ADDITIVE else "sequential"
            ),
            "original_residual_for_all_corrections": self._variant
            == LOR_HX_VARIANT_ADDITIVE,
            "edge_jacobi_correction_count": 2,
            "edge_jacobi_omega": LOR_HX_EDGE_JACOBI_OMEGA,
            "edge_jacobi_pre": True,
            "edge_jacobi_post": True,
            "gradient_correction_count": 1,
            "vector_correction_axes": list(LOR_HX_VECTOR_AXES),
            "vector_correction_order": "x_then_y_then_z",
            "nodal_correction_count": 4,
            "one_v_cycle_per_nodal_correction": True,
            "one_shared_scalar_hierarchy": True,
            "hierarchy_object_count": 1,
            "pc_type": "gamg",
            "pc_gamg_type": "agg",
            "maximum_levels": LOR_HX_GAMG_MAX_LEVELS,
            "observed_levels": self._observed_levels,
            "coarse_ksp_type": self._coarse_ksp_type,
            "coarse_pc_type": self._coarse_pc_type,
            "smoother_pc_types": list(self._level_pcs),
            "apply_count": self._apply_count,
            "last_nodal_correction_count": self._last_correction_count,
            "last_output_finite": self._last_output_finite,
            "global_transfer_matrix": False,
            "global_numeric_allgather": False,
            "global_direct_coarse": False,
            "high_order_aij": False,
            "real_imag_split": False,
            "hypre_ams": False,
        }

    def _edge_jacobi(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.array[:] = (
            LOR_HX_EDGE_JACOBI_OMEGA
            * np.asarray(source.array)
            * self._edge_diagonal_inverse
        )

    def _correction(
        self,
        restriction: Any,
        prolongation: Any,
        residual: PETSc.Vec,
        result: PETSc.Vec,
        edge_delta: PETSc.Vec,
        edge_action: PETSc.Vec,
        nodal_rhs: PETSc.Vec,
        nodal_delta: PETSc.Vec,
    ) -> None:
        restriction.mult(residual, nodal_rhs)
        nodal_delta.set(0.0 + 0.0j)
        self._nodal_ksp.solve(nodal_rhs, nodal_delta)
        prolongation.mult(nodal_delta, edge_delta)
        result.axpy(1.0 + 0.0j, edge_delta)
        self._edge_matrix.mult(edge_delta, edge_action)
        residual.axpy(-1.0 + 0.0j, edge_action)

    def _additive_correction(
        self,
        restriction: Any,
        prolongation: Any,
        original_residual: PETSc.Vec,
        result: PETSc.Vec,
        edge_delta: PETSc.Vec,
        nodal_rhs: PETSc.Vec,
        nodal_delta: PETSc.Vec,
    ) -> None:
        """Add one correction evaluated from the unchanged original residual."""

        restriction.mult(original_residual, nodal_rhs)
        nodal_delta.set(0.0 + 0.0j)
        self._nodal_ksp.solve(nodal_rhs, nodal_delta)
        prolongation.mult(nodal_delta, edge_delta)
        result.axpy(1.0 + 0.0j, edge_delta)

    def _apply_additive(
        self, residual: PETSc.Vec, output: PETSc.Vec | None
    ) -> PETSc.Vec:
        """Apply the frozen additive composition without residual updates."""

        owns_output = output is None
        result = residual.duplicate() if owns_output else output
        original_residual = residual.duplicate()
        edge_delta = residual.duplicate()
        nodal_rhs = self._nodal_matrix.createVecRight()
        nodal_delta = nodal_rhs.duplicate()
        try:
            result.set(0.0 + 0.0j)
            residual.copy(original_residual)
            self._edge_jacobi(original_residual, edge_delta)
            result.axpy(1.0 + 0.0j, edge_delta)
            self._additive_correction(
                self._gradient_adjoint,
                self._gradient,
                original_residual,
                result,
                edge_delta,
                nodal_rhs,
                nodal_delta,
            )
            for restriction, prolongation in zip(
                self._vector_restrictions,
                self._vector_prolongations,
                strict=True,
            ):
                self._additive_correction(
                    restriction,
                    prolongation,
                    original_residual,
                    result,
                    edge_delta,
                    nodal_rhs,
                    nodal_delta,
                )
            self._edge_jacobi(original_residual, edge_delta)
            result.axpy(1.0 + 0.0j, edge_delta)
            if not _finite_local(result):
                raise FloatingPointError("HX output is non-finite")
            self._apply_count += 1
            self._last_correction_count = 4
            self._last_output_finite = True
            return result
        except BaseException:
            if owns_output:
                result.destroy()
            raise
        finally:
            original_residual.destroy()
            edge_delta.destroy()
            nodal_rhs.destroy()
            nodal_delta.destroy()

    def apply(self, residual: PETSc.Vec, output: PETSc.Vec | None = None) -> PETSc.Vec:
        """Apply the fixed HX sequence and return an owned PETSc vector."""

        if self._destroyed:
            raise RuntimeError("HX object has been destroyed")
        if residual.getSize() != _shape(self._edge_matrix)[0]:
            raise ValueError("residual has an unexpected LOR edge size")
        if self._variant == LOR_HX_VARIANT_ADDITIVE:
            return self._apply_additive(residual, output)
        owns_output = output is None
        result = residual.duplicate() if owns_output else output
        edge_residual = residual.duplicate()
        edge_delta = residual.duplicate()
        edge_action = residual.duplicate()
        nodal_rhs = self._nodal_matrix.createVecRight()
        nodal_delta = nodal_rhs.duplicate()
        try:
            result.set(0.0 + 0.0j)
            residual.copy(edge_residual)
            self._edge_jacobi(edge_residual, edge_delta)
            edge_delta.copy(result)
            self._edge_matrix.mult(edge_delta, edge_action)
            edge_residual.axpy(-1.0 + 0.0j, edge_action)
            self._correction(
                self._gradient_adjoint,
                self._gradient,
                edge_residual,
                result,
                edge_delta,
                edge_action,
                nodal_rhs,
                nodal_delta,
            )
            for restriction, prolongation in zip(
                self._vector_restrictions,
                self._vector_prolongations,
                strict=True,
            ):
                self._correction(
                    restriction,
                    prolongation,
                    edge_residual,
                    result,
                    edge_delta,
                    edge_action,
                    nodal_rhs,
                    nodal_delta,
                )
            self._edge_jacobi(edge_residual, edge_delta)
            result.axpy(1.0 + 0.0j, edge_delta)
            if not _finite_local(result):
                raise FloatingPointError("HX output is non-finite")
            self._apply_count += 1
            self._last_correction_count = 4
            self._last_output_finite = True
            return result
        except BaseException:
            if owns_output:
                result.destroy()
            raise
        finally:
            edge_residual.destroy()
            edge_delta.destroy()
            edge_action.destroy()
            nodal_rhs.destroy()
            nodal_delta.destroy()

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._nodal_ksp.destroy()
        self._destroyed = True


__all__ = [
    "LOR_HX_EDGE_JACOBI_OMEGA",
    "LOR_HX_FORBIDDEN_PC_TYPES",
    "LOR_HX_GAMG_MAX_LEVELS",
    "LOR_HX_VARIANT_ADDITIVE",
    "LOR_HX_VARIANT_SEQUENTIAL",
    "LOR_HX_VECTOR_AXES",
    "NativeComplexLORHX",
]
