"""Fixed Route-B 6-to-2-to-1 nested LOR V-cycle.

This is the reusable numerical core for the authorized Route-B auxiliary
hierarchy.  It owns the two degree-three Chebyshev/Jacobi smoothers, one
small p1 PREONLY+LU/MUMPS factor, and reusable level work vectors.  The
caller-owned S2 foundation remains outside this object's destruction scope;
only its ``restrict_into``/``lift_into`` adapter is used at the high-space
boundary.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import numpy as np

from .fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
from .fullspace_lor_hx_root_cause import (
    DiagnosticDirectSolver,
    M0_DIRECT_BACKEND,
)
from .fullspace_lor_nested_interlevel_runtime import RouteBNestedHierarchyExtension


ROUTE_B_VCYCLE_SCHEMA = "task038.lor-edge-geometric-mg.route-b-vcycle.v1"
ROUTE_B_LEVELS = (6, 2, 1)
ROUTE_B_PAIRS = ((6, 2), (2, 1))
CHEBYSHEV_DEGREE = 3
POWER_STEPS = 10


class RouteBNestedVcycle:
    """One fixed 6 -> 2 -> 1 right-preconditioner action.

    The level-6 and level-2 smoothers are fixed degree-three Jacobi-scaled
    Chebyshev actions.  The p1 factor is constructed once and reused for one
    solve per apply.  ``apply`` returns the one newly allocated high-space
    correction required by the public adapter; every other vector is retained
    by this object and reused.
    """

    def __init__(self, foundation: Any, extension: RouteBNestedHierarchyExtension) -> None:
        if foundation is None or extension is None:
            raise ValueError("Route-B V-cycle requires foundation and extension")
        levels = extension.levels
        if tuple(sorted(levels)) != tuple(sorted(ROUTE_B_LEVELS)):
            raise ValueError("Route-B V-cycle levels must be exactly (6, 2, 1)")
        if levels[6].matrix is not foundation.low_matrix:
            raise ValueError("Route-B level 6 must reuse foundation.low_matrix")
        self.foundation = foundation
        self.extension = extension
        self.level6 = levels[6]
        self.level2 = levels[2]
        self.level1 = levels[1]
        self.smoother6 = None
        self.smoother2 = None
        self.level1_solver = None
        self._work: list[Any] = []
        self._destroyed = False
        self.apply_count = 0
        self.max_p1_relative_residual = 0.0
        self._transfer_counts = {
            "6_2_primal": 0,
            "6_2_adjoint": 0,
            "2_1_primal": 0,
            "2_1_adjoint": 0,
        }
        try:
            self.smoother6 = FixedChebyshevJacobiPETSc(self.level6.matrix)
            self.smoother2 = FixedChebyshevJacobiPETSc(self.level2.matrix)
            self.level1_solver = DiagnosticDirectSolver(
                self.level1.matrix, label="route-b-p1-exact-oracle"
            )
            self._allocate_work()
            self.audit = MappingProxyType({
                "schema": ROUTE_B_VCYCLE_SCHEMA,
                "levels": ROUTE_B_LEVELS,
                "pairs": ROUTE_B_PAIRS,
                "chebyshev_degree": CHEBYSHEV_DEGREE,
                "power_steps": POWER_STEPS,
                "pre_polynomial_count": 1,
                "post_polynomial_count": 1,
                "vcycle_count": 1,
                "p1_exact_factor": True,
                "p1_solver_backend": M0_DIRECT_BACKEND,
                "p6_exact_factor": False,
                "level2_exact_factor": False,
                "global_direct_coarse": False,
                "global_high_order_aij": False,
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "hx_hierarchy_built": False,
                "pcgamg_hierarchy_built": False,
                "smoother_levels": (6, 2),
                "outer_ksp_created": False,
                "p1_factor_ksp_created": True,
                "physical_solve": False,
                "recovery": False,
                "retains_per_apply_history": False,
                "foundation_caller_owned": True,
            })
        except Exception:
            self.destroy()
            raise

    def _allocate_work(self) -> None:
        def right(matrix: Any) -> Any:
            value = matrix.createVecRight()
            self._work.append(value)
            return value

        def left(matrix: Any) -> Any:
            value = matrix.createVecLeft()
            self._work.append(value)
            return value

        # Level 6: rhs, pre solution, two actions/residuals, correction.
        self._rhs6 = right(self.level6.matrix)
        self._z6_pre = right(self.level6.matrix)
        self._a6 = left(self.level6.matrix)
        self._r6 = left(self.level6.matrix)
        self._z6 = right(self.level6.matrix)
        self._post_a6 = left(self.level6.matrix)
        self._post_r6 = left(self.level6.matrix)
        self._post_correction6 = right(self.level6.matrix)
        self._solution6 = right(self.level6.matrix)

        # Level 2: the restricted residual and one nested correction.
        self._rhs2 = right(self.level2.matrix)
        self._z2_pre = right(self.level2.matrix)
        self._a2 = left(self.level2.matrix)
        self._r2 = left(self.level2.matrix)
        self._z2 = right(self.level2.matrix)
        self._post_a2 = left(self.level2.matrix)
        self._post_r2 = left(self.level2.matrix)
        self._post_correction2 = right(self.level2.matrix)
        self._correction2 = right(self.level2.matrix)

        # Level 1: rhs, exact solution, and explicit residual check.
        self._rhs1 = right(self.level1.matrix)
        self._solution1 = right(self.level1.matrix)
        self._a1 = left(self.level1.matrix)
        self._r1 = left(self.level1.matrix)

    @property
    def work_vectors(self) -> tuple[Any, ...]:
        """The retained internal Vec objects, for lifecycle auditing."""

        return tuple(self._work)

    def _transfer_into(self, pair: tuple[int, int], source: Any, target: Any, *, adjoint: bool) -> None:
        if adjoint:
            self.extension.apply_adjoint_into(pair, source, target)
            self._transfer_counts[f"{pair[0]}_{pair[1]}_adjoint"] += 1
        else:
            self.extension.apply_primal_into(pair, source, target)
            self._transfer_counts[f"{pair[0]}_{pair[1]}_primal"] += 1

    def _solve_level1_into(self) -> float:
        target = self._solution1
        target.set(0.0 + 0.0j)
        self.level1_solver.ksp.solve(self._rhs1, target)
        self.level1_solver.solve_count += 1
        reason = int(self.level1_solver.ksp.getConvergedReason())
        self.level1.matrix.mult(target, self._a1)
        self._rhs1.copy(self._r1)
        self._r1.axpy(-1.0, self._a1)
        rhs_norm = float(self._rhs1.norm())
        residual_norm = float(self._r1.norm())
        relative = residual_norm / max(rhs_norm, np.finfo(float).tiny)
        solution_norm = float(target.norm())
        finite = bool(np.isfinite(solution_norm) and np.isfinite(relative))
        if reason <= 0 or not finite:
            raise RuntimeError("Route-B p1 exact solve did not produce a finite solution")
        return float(relative)

    def apply_into(self, high_residual: Any, high_target: Any) -> dict[str, object]:
        if self._destroyed:
            raise RuntimeError("Route-B V-cycle has been destroyed")
        order: list[str] = []

        self.foundation.restrict_into(high_residual, self._rhs6)
        self.smoother6.apply_into(self._rhs6, self._z6_pre)
        order.append("level6_pre")
        self.level6.matrix.mult(self._z6_pre, self._a6)
        self._rhs6.copy(self._r6)
        self._r6.axpy(-1.0, self._a6)

        self._transfer_into((6, 2), self._r6, self._rhs2, adjoint=True)
        order.append("p62_adjoint")
        self.smoother2.apply_into(self._rhs2, self._z2_pre)
        order.append("level2_pre")
        self.level2.matrix.mult(self._z2_pre, self._a2)
        self._rhs2.copy(self._r2)
        self._r2.axpy(-1.0, self._a2)

        self._transfer_into((2, 1), self._r2, self._rhs1, adjoint=True)
        order.append("p21_adjoint")
        level1_relative_residual = self._solve_level1_into()
        self.max_p1_relative_residual = max(
            self.max_p1_relative_residual, float(level1_relative_residual)
        )
        order.append("level1_exact_solve")

        self._transfer_into((2, 1), self._solution1, self._correction2, adjoint=False)
        order.append("p21_primal")
        self._z2_pre.copy(self._z2)
        self._z2.axpy(1.0, self._correction2)
        self.level2.matrix.mult(self._z2, self._post_a2)
        self._rhs2.copy(self._post_r2)
        self._post_r2.axpy(-1.0, self._post_a2)
        self.smoother2.apply_into(self._post_r2, self._post_correction2)
        self._z2.axpy(1.0, self._post_correction2)
        order.append("level2_post")

        self._transfer_into((6, 2), self._z2, self._z6, adjoint=False)
        order.append("p62_primal")
        self._z6_pre.copy(self._solution6)
        self._solution6.axpy(1.0, self._z6)
        self.level6.matrix.mult(self._solution6, self._post_a6)
        self._rhs6.copy(self._post_r6)
        self._post_r6.axpy(-1.0, self._post_a6)
        self.smoother6.apply_into(self._post_r6, self._post_correction6)
        self._solution6.axpy(1.0, self._post_correction6)
        order.append("level6_post")

        self.foundation.lift_into(self._solution6, high_target)
        self.apply_count += 1
        facts = {
            "order": tuple(order),
            "level6_pre_count": 1,
            "level6_post_count": 1,
            "level2_pre_count": 1,
            "level2_post_count": 1,
            "transfer_62_primal_count": 1,
            "transfer_62_adjoint_count": 1,
            "transfer_21_primal_count": 1,
            "transfer_21_adjoint_count": 1,
            "p1_solve_count": int(self.level1_solver.solve_count),
            "p1_solver_backend": M0_DIRECT_BACKEND,
            "p1_relative_residual": level1_relative_residual,
            "output_finite": bool(np.isfinite(float(high_target.norm()))),
            "apply_count": int(self.apply_count),
        }
        for name, count in self._transfer_counts.items():
            facts[f"transfer_{name}_total"] = int(count)
        self.last_apply_facts = facts
        return facts

    def apply(self, high_residual: Any) -> Any:
        if self._destroyed:
            raise RuntimeError("Route-B V-cycle has been destroyed")
        output = self.foundation.high_primal_source.duplicate()
        try:
            self.apply_into(high_residual, output)
        except Exception:
            output.destroy()
            raise
        return output

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self.level1_solver is not None:
            self.level1_solver.destroy()
            self.level1_solver = None
        for vector in self._work:
            vector.destroy()
        self._work = []
        if self.smoother2 is not None:
            self.smoother2.destroy()
            self.smoother2 = None
        if self.smoother6 is not None:
            self.smoother6.destroy()
            self.smoother6 = None
        if self.extension is not None:
            self.extension.destroy()
            self.extension = None
        self.foundation = None
        self.level6 = self.level2 = self.level1 = None


__all__ = ["RouteBNestedVcycle"]
