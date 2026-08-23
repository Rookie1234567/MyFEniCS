"""Research-only exact interface Schur actions for Task040 V1-2.

The module separates the small dense algebra oracle from the PETSc carrier.
Both implement

    S_Gamma = A_Gamma,Gamma - A_Gamma,I A_I,I^{-1} A_I,Gamma.

Only the interior block is factorized.  The PETSc path keeps the Schur blocks
as sparse actions and retains distributed vectors; it never gathers a finite-
element-sized matrix or forms a global direct factor.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse

__all__ = (
    "NumpyInterfaceSchurOracle",
    "PetscInterfaceSchurOracle",
    "ProjectedExactPetrovAction",
    "build_numpy_interface_schur_oracle",
    "build_petsc_interface_schur_oracle",
    "project_petrov_columns",
)


class _NumpyInterfaceSchurBlock:
    """One tiny dense block; production ownership is supplied by the PETSc class."""

    def __init__(
        self,
        bare: np.ndarray,
        group_rows: Sequence[int],
        gamma_rows: Sequence[int],
        *,
        name: str,
    ) -> None:
        matrix = np.asarray(bare, dtype=np.complex128)
        group = np.asarray(group_rows, dtype=np.int64)
        gamma = np.asarray(gamma_rows, dtype=np.int64)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
            raise ValueError("tiny Schur oracle requires a square bare matrix")
        if len(np.unique(group)) != len(group) or len(np.unique(gamma)) != len(gamma):
            raise ValueError("tiny Schur rows must be unique")
        if not set(gamma).issubset(set(group)):
            raise ValueError("interface rows must be contained in the group")
        interior = np.asarray(
            [row for row in group if row not in set(gamma)], dtype=np.int64
        )
        if interior.size == 0:
            raise ValueError("each Schur block needs an interior row set")
        self.name = str(name)
        self.group_rows = group
        self.gamma_rows = gamma
        self.interior_rows = interior
        self._a_gg = matrix[np.ix_(gamma, gamma)].copy()
        self._a_gi = matrix[np.ix_(gamma, interior)].copy()
        self._a_ig = matrix[np.ix_(interior, gamma)].copy()
        self._lu = lu_factor(matrix[np.ix_(interior, interior)], check_finite=True)
        self._destroyed = False
        self.apply_count = 0

    @property
    def gamma_size(self) -> int:
        return int(self.gamma_rows.size)

    def apply(self, values: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("tiny interface Schur block is destroyed")
        values = np.asarray(values, dtype=np.complex128)
        vector = values.ndim == 1
        if vector:
            values = values[:, None]
        if values.shape[0] != self.gamma_size:
            raise ValueError("tiny Schur input has the wrong interface size")
        interior = lu_solve(self._lu, self._a_ig @ values, check_finite=True)
        result = self._a_gg @ values - self._a_gi @ interior
        self.apply_count += 1
        return result[:, 0] if vector else result

    def dense_for_tiny_oracle(self) -> np.ndarray:
        return np.asarray(self.apply(np.eye(self.gamma_size, dtype=np.complex128)))

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._a_gg = np.empty((0, 0), dtype=np.complex128)
        self._a_gi = np.empty((0, 0), dtype=np.complex128)
        self._a_ig = np.empty((0, 0), dtype=np.complex128)
        self._lu = None
        self._destroyed = True


class NumpyInterfaceSchurOracle:
    """Small independent four-direction Schur oracle."""

    def __init__(
        self,
        bare: np.ndarray,
        group_rows: Sequence[Sequence[int]],
        interface_supports: Sequence[Sequence[int]],
    ) -> None:
        if len(group_rows) != 3 or len(interface_supports) != 2:
            raise ValueError("V1-2 Schur needs three groups and two interfaces")
        self._bare = np.asarray(bare, dtype=np.complex128)
        self.interface_supports = tuple(
            np.asarray(rows, dtype=np.int64) for rows in interface_supports
        )
        union = np.unique(np.concatenate(self.interface_supports))
        self.interface_rows = union
        self._blocks: list[_NumpyInterfaceSchurBlock] = []
        self._destroyed = False
        try:
            for index, rows in enumerate(group_rows):
                group = np.asarray(rows, dtype=np.int64)
                gamma = np.asarray(
                    [row for row in group if row in set(union)], dtype=np.int64
                )
                self._blocks.append(
                    _NumpyInterfaceSchurBlock(
                        self._bare,
                        group,
                        gamma,
                        name=f"group{index}",
                    )
                )
        except Exception:
            self.destroy()
            raise

    def _check_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("tiny interface Schur oracle is destroyed")

    def _block_matrix(self, group: int) -> np.ndarray:
        self._check_live()
        return self._blocks[group].dense_for_tiny_oracle()

    def directed_blocks(self) -> dict[str, np.ndarray]:
        """Return the four directed blocks in frozen lower/upper order."""

        lower = self.interface_supports[0]
        upper = self.interface_supports[1]
        group1 = self._blocks[1].gamma_rows
        group1_lower = [int(np.flatnonzero(group1 == row)[0]) for row in lower]
        group1_upper = [int(np.flatnonzero(group1 == row)[0]) for row in upper]
        return {
            "group0_to_lower": self._block_matrix(0),
            "group1_to_lower": self._block_matrix(1)[
                np.ix_(group1_lower, group1_lower)
            ],
            "group1_to_upper": self._block_matrix(1)[
                np.ix_(group1_upper, group1_upper)
            ],
            "group2_to_upper": self._block_matrix(2),
        }

    def interface_matrix(self, interface: int) -> np.ndarray:
        """Return the tiny sum of the two directed sides for one interface."""

        blocks = self.directed_blocks()
        if interface == 0:
            return blocks["group0_to_lower"] + blocks["group1_to_lower"]
        if interface == 1:
            return blocks["group1_to_upper"] + blocks["group2_to_upper"]
        raise ValueError("interface index must be 0 or 1")

    def cross_interface_coupling_blocks(self) -> dict[str, np.ndarray]:
        matrix = self._block_matrix(1)
        rows = self._blocks[1].gamma_rows
        lower = [
            int(np.flatnonzero(rows == row)[0]) for row in self.interface_supports[0]
        ]
        upper = [
            int(np.flatnonzero(rows == row)[0]) for row in self.interface_supports[1]
        ]
        return {
            "lower_to_upper": matrix[np.ix_(upper, lower)],
            "upper_to_lower": matrix[np.ix_(lower, upper)],
        }

    def cross_interface_coupling_norms(self) -> dict[str, float]:
        return {
            name: float(np.linalg.norm(value))
            for name, value in self.cross_interface_coupling_blocks().items()
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        self._check_live()
        directed = self.directed_blocks()
        return {
            "schema": "task040.v1_2.interface_schur.numpy_oracle.v1",
            "formula": "A_GammaGamma-A_GammaI*A_II^-1*A_IGamma",
            "directed_block_norms": {
                name: float(np.linalg.norm(value)) for name, value in directed.items()
            },
            "group1_cross_interface_coupling_norms": self.cross_interface_coupling_norms(),
            "factor_count_ready": 3,
            "factor_count_after_cleanup": None,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "dense_materialization": "tiny_oracle_only",
        }

    def destroy(self) -> None:
        if getattr(self, "_destroyed", True):
            return
        for block in self._blocks:
            block.destroy()
        self._blocks.clear()
        self._bare = np.empty((0, 0), dtype=np.complex128)
        self._destroyed = True


def build_numpy_interface_schur_oracle(
    bare: np.ndarray,
    group_rows: Sequence[Sequence[int]],
    interface_supports: Sequence[Sequence[int]],
) -> NumpyInterfaceSchurOracle:
    return NumpyInterfaceSchurOracle(bare, group_rows, interface_supports)


class _PetscInterfaceSchurBlock:
    def __init__(
        self,
        bare: PETSc.Mat,
        group_rows: np.ndarray,
        gamma_rows: np.ndarray,
        *,
        name: str,
    ) -> None:
        comm = bare.getComm().tompi4py()
        gamma_rows = np.asarray(gamma_rows, dtype=PETSc.IntType)
        group_rows = np.asarray(group_rows, dtype=PETSc.IntType)
        if comm.allreduce(int(gamma_rows.size), op=MPI.SUM) == 0:
            raise ValueError("PETSc Schur block has no interface rows")
        interior_rows = np.asarray(
            [row for row in group_rows if row not in set(gamma_rows)],
            dtype=PETSc.IntType,
        )
        if comm.allreduce(int(interior_rows.size), op=MPI.SUM) == 0:
            raise ValueError("PETSc Schur block has no interior rows")
        petsc_comm = bare.getComm()
        gamma_is = PETSc.IS().createGeneral(gamma_rows, comm=petsc_comm)
        interior_is = PETSc.IS().createGeneral(interior_rows, comm=petsc_comm)
        self.name = name
        self.group_rows = group_rows
        self.gamma_rows = gamma_rows
        self.interior_rows = interior_rows
        self._a_gg = None
        self._a_gi = None
        self._a_ig = None
        self._factor = None
        self._gamma_rhs = None
        self._interior_rhs = None
        self._interior_solution = None
        self._gamma_output = None
        self._gamma_work = None
        self._destroyed = False
        a_ii = None
        try:
            self._a_gg = bare.createSubMatrix(gamma_is, gamma_is)
            self._a_gi = bare.createSubMatrix(gamma_is, interior_is)
            self._a_ig = bare.createSubMatrix(interior_is, gamma_is)
            a_ii = bare.createSubMatrix(interior_is, interior_is)
            self._factor = ResearchExactFactorInverse(
                a_ii,
                factor_solver_type="mumps",
                factor_only_storage=True,
            )
            self._factor.release_borrowed_matrix()
            a_ii.destroy()
            a_ii = None
            self._gamma_rhs = self._a_ig.createVecRight()
            self._interior_rhs = self._a_ig.createVecLeft()
            self._interior_solution = self._a_gi.createVecRight()
            self._gamma_output = self._a_gg.createVecLeft()
            self._gamma_work = self._a_gi.createVecLeft()
        except Exception:
            if a_ii is not None:
                a_ii.destroy()
            gamma_is.destroy()
            interior_is.destroy()
            self.destroy()
            raise
        gamma_is.destroy()
        interior_is.destroy()
        self.apply_count = 0

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("PETSc interface Schur block is destroyed")
        if source.getSize() != self._gamma_rhs.getSize():
            raise ValueError("PETSc interface Schur source has the wrong size")
        if target.getSize() != self._gamma_output.getSize():
            raise ValueError("PETSc interface Schur target has the wrong size")
        self._a_ig.mult(source, self._interior_rhs)
        self._factor.solve(self._interior_rhs, self._interior_solution)
        self._a_gg.mult(source, self._gamma_output)
        self._a_gi.mult(
            self._interior_solution,
            self._gamma_work,
        )
        self._gamma_output.axpy(PETSc.ScalarType(-1.0), self._gamma_work)
        self._gamma_output.copy(target)
        self.apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "gamma_rows_local": int(self.gamma_rows.size),
            "interior_rows_local": int(self.interior_rows.size),
            "factor": None if self._factor is None else self._factor.diagnostics,
            "apply_count": self.apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if getattr(self, "_destroyed", True):
            return
        for name in (
            "_gamma_output",
            "_gamma_work",
            "_interior_solution",
            "_interior_rhs",
            "_gamma_rhs",
        ):
            vector = getattr(self, name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        for name in ("_a_gg", "_a_gi", "_a_ig"):
            matrix = getattr(self, name, None)
            if matrix is not None:
                matrix.destroy()
                setattr(self, name, None)
        if self._factor is not None:
            self._factor.destroy()
            self._factor = None
        self._destroyed = True


class PetscInterfaceSchurOracle:
    """Distributed sparse-block Schur carrier with exactly three AII factors."""

    def __init__(
        self,
        bare: PETSc.Mat,
        group_rows: Sequence[np.ndarray],
        interface_supports: Sequence[Mapping[str, Any] | Sequence[int]],
    ) -> None:
        if len(group_rows) != 3 or len(interface_supports) != 2:
            raise ValueError("V1-2 PETSc Schur needs three groups and two interfaces")
        self._blocks: list[_PetscInterfaceSchurBlock] = []
        self._destroyed = False
        supports: list[np.ndarray] = []
        for support in interface_supports:
            values = (
                support["active_support"] if isinstance(support, Mapping) else support
            )
            supports.append(np.unique(np.asarray(values, dtype=PETSc.IntType)))
        interface_union = np.unique(np.concatenate(supports))
        try:
            for index, rows in enumerate(group_rows):
                group = np.asarray(rows, dtype=PETSc.IntType)
                if len(np.unique(group)) != len(group):
                    raise ValueError("PETSc group rows must be unique")
                gamma = np.asarray(
                    [row for row in group if row in set(interface_union)],
                    dtype=PETSc.IntType,
                )
                self._blocks.append(
                    _PetscInterfaceSchurBlock(
                        bare,
                        group,
                        gamma,
                        name=f"group{index}",
                    )
                )
        except Exception:
            self.destroy()
            raise
        self.interface_supports = tuple(supports)

    def apply_group(
        self,
        group: int,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        self._blocks[int(group)].apply(source, target)

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._destroyed:
            return {
                "factor_count_ready": 0,
                "factor_count_after_cleanup": 0,
                "destroyed": True,
            }
        comm = self._blocks[0]._a_gg.getComm().tompi4py()
        local_factor_count = sum(
            1
            for block in self._blocks
            if block._factor is not None
            and bool(block._factor.diagnostics["factor_matrix_alive"])
        )
        factor_count = int(comm.allreduce(local_factor_count, op=MPI.MIN))
        return {
            "schema": "task040.v1_2.interface_schur.petsc.v1",
            "formula": "A_GammaGamma-A_GammaI*A_II^-1*A_IGamma",
            "factor_count_ready": factor_count,
            "factor_count_after_cleanup": None,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "dense_materialization": False,
            "group_blocks": [block.diagnostics for block in self._blocks],
        }

    def destroy(self) -> None:
        if getattr(self, "_destroyed", True):
            return
        for block in reversed(self._blocks):
            block.destroy()
        self._blocks.clear()
        self._destroyed = True


def build_petsc_interface_schur_oracle(
    bare: PETSc.Mat,
    group_rows: Sequence[np.ndarray],
    interface_supports: Sequence[Mapping[str, Any] | Sequence[int]],
) -> PetscInterfaceSchurOracle:
    return PetscInterfaceSchurOracle(bare, group_rows, interface_supports)


def project_petrov_columns(
    apply: Callable[[np.ndarray], np.ndarray],
    z_columns: np.ndarray,
    y_columns: np.ndarray,
) -> dict[str, Any]:
    """Form a tiny dense YᴴSZ projection for unit tests only."""

    z = np.asarray(z_columns, dtype=np.complex128)
    y = np.asarray(y_columns, dtype=np.complex128)
    if z.ndim != 2 or y.ndim != 2 or z.shape[0] != y.shape[0]:
        raise ValueError("Petrov columns must be row-compatible matrices")
    images = np.column_stack(
        [np.asarray(apply(z[:, i]), dtype=np.complex128) for i in range(z.shape[1])]
    )
    projected = y.conj().T @ images
    singular_values = np.linalg.svd(projected, compute_uv=False)
    rank = int(np.linalg.matrix_rank(projected))
    condition = float(np.linalg.cond(projected)) if projected.size else float("inf")
    return {
        "projected": projected,
        "rank": rank,
        "singular_values": singular_values,
        "condition": condition,
        "yhz": y.conj().T @ z,
        "finite": bool(np.all(np.isfinite(projected))),
    }


class ProjectedExactPetrovAction:
    """Tiny-dense-only low-rank correction over a frozen Petrov span.

    This helper is not a formal distributed carrier. The stored correction is
    only the selected-span action difference; no global dense operator is
    formed.
    """

    def __init__(
        self,
        scalar_apply: Callable[[np.ndarray], np.ndarray],
        exact_apply: Callable[[np.ndarray], np.ndarray],
        z_columns: np.ndarray,
        y_columns: np.ndarray,
    ) -> None:
        self._scalar_apply = scalar_apply
        self._exact_apply = exact_apply
        self.z = np.asarray(z_columns, dtype=np.complex128).copy()
        self.y = np.asarray(y_columns, dtype=np.complex128).copy()
        if self.z.ndim != 2 or self.y.shape != self.z.shape:
            raise ValueError("projected exact span shapes do not match")
        self._delta = np.column_stack(
            [
                np.asarray(exact_apply(self.z[:, i]), dtype=np.complex128)
                - np.asarray(scalar_apply(self.z[:, i]), dtype=np.complex128)
                for i in range(self.z.shape[1])
            ]
        )
        self._yhz = self.y.conj().T @ self.z
        u, singular_values, vh = np.linalg.svd(self._yhz, full_matrices=False)
        if singular_values.size == 0 or singular_values[-1] <= (
            np.finfo(float).eps * max(float(singular_values[0]), 1.0)
        ):
            raise ValueError("Petrov span Gram is singular")
        self._petrov_svd = (u, singular_values, vh)
        self._span_identity_error = float(
            np.linalg.norm(self._yhz - np.eye(self.z.shape[1]))
        )
        self.apply_count = 0
        self._destroyed = False

    def apply(self, source: np.ndarray) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("projected exact action is destroyed")
        source = np.asarray(source, dtype=np.complex128)
        result = np.asarray(self._scalar_apply(source), dtype=np.complex128)
        rhs = self.y.conj().T @ source
        u, singular_values, vh = self._petrov_svd
        coefficients = vh.conj().T @ ((u.conj().T @ rhs) / singular_values)
        result = result + self._delta @ coefficients
        self.apply_count += 1
        return result

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "schema": "task040.v1_3.projected_exact_petrov.v1",
            "span_size": int(self.z.shape[1]),
            "span_identity_error": self._span_identity_error,
            "petrov_gram_condition": float(
                self._petrov_svd[1][0] / self._petrov_svd[1][-1]
            ),
            "projected_exact_correction": True,
            "carrier": "tiny_dense_only",
            "formal_use": False,
            "global_dense_operator_materialized": False,
            "apply_count": self.apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.z = np.empty((0, 0), dtype=np.complex128)
        self.y = np.empty((0, 0), dtype=np.complex128)
        self._delta = np.empty((0, 0), dtype=np.complex128)
        self._scalar_apply = lambda value: value
        self._exact_apply = lambda value: value
        self._destroyed = True
