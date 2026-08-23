"""Research-only exact interface Schur actions for Task040 V1-2.

The module separates the small dense algebra oracle from the PETSc carrier.
Both implement

    S_Gamma = A_Gamma,Gamma - A_Gamma,I A_I,I^{-1} A_I,Gamma.

Only the interior block is factorized.  The PETSc path keeps the Schur blocks
as sparse actions and retains distributed vectors; it never gathers a finite-
element-sized matrix or forms a global direct factor.
"""

from __future__ import annotations

import hashlib
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
    "PetscDistributedPetrovAction",
    "PetscFixedProjectedGroupInverse",
    "build_numpy_interface_schur_oracle",
    "build_petsc_interface_schur_oracle",
    "build_distributed_petrov_action",
    "build_fixed_projected_group_inverse",
    "project_petrov_columns",
)


def _small_svd_diagnostics(matrix: np.ndarray) -> dict[str, Any]:
    singular_values = np.linalg.svd(matrix, compute_uv=False)
    return {
        "rank": int(np.linalg.matrix_rank(matrix)),
        "singular_values": singular_values.tolist(),
        "condition": float(singular_values[0] / singular_values[-1]),
    }


def _int_array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.int64))
    return hashlib.sha256(array.tobytes()).hexdigest()


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
        self._row_copy_indices: dict[
            tuple[int, int], tuple[np.ndarray, np.ndarray]
        ] = {}
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
        try:
            lower_rows = set(map(int, self._blocks[0].gamma_rows))
            middle_rows = set(map(int, self._blocks[1].gamma_rows))
            upper_rows = set(map(int, self._blocks[2].gamma_rows))
            lower_support = set(map(int, self.interface_supports[0]))
            upper_support = set(map(int, self.interface_supports[1]))
            local_identity_ok = (
                lower_rows == middle_rows.intersection(lower_support)
                and upper_rows == middle_rows.intersection(upper_support)
                and middle_rows == (lower_rows | upper_rows)
            )
            if not bool(
                bare.getComm().tompi4py().allreduce(local_identity_ok, op=MPI.LAND)
            ):
                raise ValueError(
                    "shared Gamma row ownership is not aligned across groups"
                )
            for source_group in range(3):
                source_positions = {
                    int(row): index
                    for index, row in enumerate(self._blocks[source_group].gamma_rows)
                }
                for target_group in range(3):
                    source_indices: list[int] = []
                    target_indices: list[int] = []
                    for target_index, row in enumerate(
                        self._blocks[target_group].gamma_rows
                    ):
                        source_index = source_positions.get(int(row))
                        if source_index is not None:
                            source_indices.append(source_index)
                            target_indices.append(target_index)
                    self._row_copy_indices[(source_group, target_group)] = (
                        np.asarray(source_indices, dtype=np.intp),
                        np.asarray(target_indices, dtype=np.intp),
                    )
        except Exception:
            self.destroy()
            raise

    def _copy_group_rows(
        self,
        source: PETSc.Vec,
        target: PETSc.Vec,
        source_group: int,
        target_group: int,
        *,
        add: bool = False,
    ) -> None:
        source_indices, target_indices = self._row_copy_indices[
            (int(source_group), int(target_group))
        ]
        if not add:
            target.set(0.0)
        if add:
            target.array[target_indices] += source.array[source_indices]
        else:
            target.array[target_indices] = source.array[source_indices]
        target.assemble()

    def _neighbor_block_apply(
        self,
        target_group: int,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        target_group = int(target_group)
        if target_group not in (0, 1, 2):
            raise ValueError("directed-neighbor target group must be 0, 1, or 2")
        target_block = self._blocks[target_group]
        if (
            source.getSize() != target_block._gamma_rhs.getSize()
            or target.getSize() != target_block._gamma_output.getSize()
        ):
            raise ValueError("directed-neighbor Vec layout does not match target group")
        if target_group == 0:
            neighbor = 1
            neighbor_source = self._blocks[neighbor]._gamma_rhs.duplicate()
            neighbor_target = self._blocks[neighbor]._gamma_output.duplicate()
            try:
                self._copy_group_rows(
                    source,
                    neighbor_source,
                    target_group,
                    neighbor,
                )
                self._blocks[neighbor].apply(neighbor_source, neighbor_target)
                self._copy_group_rows(
                    neighbor_target,
                    target,
                    neighbor,
                    target_group,
                )
            finally:
                neighbor_target.destroy()
                neighbor_source.destroy()
            return
        if target_group == 2:
            neighbor = 1
            neighbor_source = self._blocks[neighbor]._gamma_rhs.duplicate()
            neighbor_target = self._blocks[neighbor]._gamma_output.duplicate()
            try:
                self._copy_group_rows(
                    source,
                    neighbor_source,
                    target_group,
                    neighbor,
                )
                self._blocks[neighbor].apply(neighbor_source, neighbor_target)
                self._copy_group_rows(
                    neighbor_target,
                    target,
                    neighbor,
                    target_group,
                )
            finally:
                neighbor_target.destroy()
                neighbor_source.destroy()
            return

        lower_source = self._blocks[0]._gamma_rhs.duplicate()
        upper_source = self._blocks[2]._gamma_rhs.duplicate()
        lower_target = self._blocks[0]._gamma_output.duplicate()
        upper_target = self._blocks[2]._gamma_output.duplicate()
        try:
            self._copy_group_rows(
                source,
                lower_source,
                target_group,
                0,
            )
            self._copy_group_rows(
                source,
                upper_source,
                target_group,
                2,
            )
            self._blocks[0].apply(lower_source, lower_target)
            self._blocks[2].apply(upper_source, upper_target)
            self._copy_group_rows(
                lower_target,
                target,
                0,
                1,
            )
            self._copy_group_rows(
                upper_target,
                target,
                2,
                1,
                add=True,
            )
        finally:
            upper_target.destroy()
            lower_target.destroy()
            upper_source.destroy()
            lower_source.destroy()

    def apply_directed_neighbor(
        self, target_group: int, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        """Apply the frozen neighbor transmission map for one target group.

        Group 0 receives group 1's lower-directed Schur, group 2 receives
        group 1's upper-directed Schur, and group 1 receives the block-diagonal
        group 0/group 2 neighbor maps.  Compressed Gamma vectors are remapped
        by original active-row identity; no FE-sized numeric gather is used.
        """

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        self._neighbor_block_apply(target_group, source, target)

    def apply_group(
        self,
        group: int,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        self._blocks[int(group)].apply(source, target)

    def group_gamma_layout(self, group: int) -> dict[str, Any]:
        """Return the public distributed layout for one interface Gamma block."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        vector = self._blocks[int(group)]._gamma_rhs
        first, last = map(int, vector.getOwnershipRange())
        rows = self.group_gamma_rows_local(group)
        comm = vector.getComm().tompi4py()
        global_rows = np.asarray(
            [row for part in comm.allgather(rows.tolist()) for row in part],
            dtype=np.int64,
        )
        if len(global_rows) != int(vector.getSize()):
            raise ValueError("Gamma row metadata does not match Vec global size")
        if len(np.unique(global_rows)) != len(global_rows):
            raise ValueError("Gamma row metadata contains duplicate global rows")
        return {
            "global_size": int(vector.getSize()),
            "local_size": int(vector.getLocalSize()),
            "ownership_range": [first, last],
            "gamma_rows_local_sha256": _int_array_sha256(rows),
            "gamma_rows_global_order_sha256": _int_array_sha256(global_rows),
        }

    def group_gamma_rows_local(self, group: int) -> np.ndarray:
        """Return a copy of the original active rows in Gamma Vec order."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        return self._blocks[int(group)].gamma_rows.copy()

    def create_group_gamma_vector(self, group: int) -> PETSc.Vec:
        """Create an owned Gamma Vec; the caller owns and destroys it."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        return self._blocks[int(group)]._gamma_rhs.duplicate()

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
            "directed_blocks": {
                "group0_to_lower": "group1.lower",
                "group1_to_lower": "group0.lower",
                "group1_to_upper": "group2.upper",
                "group2_to_upper": "group1.upper",
            },
            "group_blocks": [block.diagnostics for block in self._blocks],
        }

    def destroy(self) -> None:
        if getattr(self, "_destroyed", True):
            return
        for block in reversed(self._blocks):
            block.destroy()
        self._blocks.clear()
        self._row_copy_indices.clear()
        self._destroyed = True


def build_petsc_interface_schur_oracle(
    bare: PETSc.Mat,
    group_rows: Sequence[np.ndarray],
    interface_supports: Sequence[Mapping[str, Any] | Sequence[int]],
) -> PetscInterfaceSchurOracle:
    return PetscInterfaceSchurOracle(bare, group_rows, interface_supports)


class PetscDistributedPetrovAction:
    """Owner-row Petrov carrier with only replicated small contractions."""

    def __init__(
        self,
        layout: PETSc.Vec,
        scalar_apply: Callable[[PETSc.Vec, PETSc.Vec], None],
        exact_apply: Callable[[PETSc.Vec, PETSc.Vec], None],
        local_z: np.ndarray,
        local_y: np.ndarray,
        local_row_ids: np.ndarray | None = None,
    ) -> None:
        self._comm = layout.getComm().tompi4py()
        self._template = layout.duplicate()
        self._scalar_apply = scalar_apply
        self._exact_apply = exact_apply
        self._local_z = np.asarray(local_z, dtype=np.complex128).copy()
        self._local_y = np.asarray(local_y, dtype=np.complex128).copy()
        self._local_row_ids = (
            None
            if local_row_ids is None
            else np.asarray(local_row_ids, dtype=np.int64).copy()
        )
        self._delta_local = np.empty((0, 0), dtype=np.complex128)
        self._gram = np.empty((0, 0), dtype=np.complex128)
        self._projected_scalar = np.empty((0, 0), dtype=np.complex128)
        self._projected_exact = np.empty((0, 0), dtype=np.complex128)
        self._gram_svd: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._ownership_range = tuple(map(int, layout.getOwnershipRange()))
        self._destroyed = False
        self._detached = False
        self.apply_count = 0
        self.scalar_apply_count = 0
        self.exact_apply_count = 0
        try:
            local_rows = int(self._template.getLocalSize())
            global_rows = int(self._template.getSize())
            local_shape_valid = (
                self._local_z.ndim == 2
                and self._local_y.ndim == 2
                and self._local_z.shape == self._local_y.shape
                and self._local_z.shape[0] == local_rows
                and self._local_z.shape[1] > 0
            )
            local_span = int(self._local_z.shape[1]) if self._local_z.ndim == 2 else -1
            shape_valid = bool(self._comm.allreduce(local_shape_valid, op=MPI.LAND))
            span_min = int(self._comm.allreduce(local_span, op=MPI.MIN))
            span_max = int(self._comm.allreduce(local_span, op=MPI.MAX))
            if not shape_valid or span_min <= 0 or span_min != span_max:
                raise ValueError("Petrov owner-row arrays have incompatible shapes")
            local_finite = bool(
                np.all(np.isfinite(self._local_z))
                and np.all(np.isfinite(self._local_y))
            )
            if not self._comm.allreduce(local_finite, op=MPI.LAND):
                raise ValueError("Petrov owner-row arrays are not finite")
            row_ids_valid = self._local_row_ids is None or (
                self._local_row_ids.ndim == 1
                and self._local_row_ids.size == local_rows
                and np.all(self._local_row_ids >= 0)
                and np.unique(self._local_row_ids).size == self._local_row_ids.size
            )
            if not self._comm.allreduce(bool(row_ids_valid), op=MPI.LAND):
                raise ValueError("Petrov local row identities have the wrong shape")
            self.global_rows = global_rows
            self.local_rows = local_rows
            self.span_size = span_min
            self._gram = self._allreduce_small(self._local_y.conj().T @ self._local_z)
            self._gram_svd = self._factor_small_gram(self._gram)
            self._build_projected_columns()
        except Exception:
            self.destroy()
            raise

    def _allreduce_small(self, local: np.ndarray) -> np.ndarray:
        value = np.asarray(local, dtype=np.complex128)
        result = np.empty_like(value)
        self._comm.Allreduce(value, result, op=MPI.SUM)
        return result

    @staticmethod
    def _factor_small_gram(
        gram: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        u, singular_values, vh = np.linalg.svd(gram, full_matrices=False)
        if singular_values.size == 0 or singular_values[-1] <= (
            np.finfo(float).eps * max(float(singular_values[0]), 1.0)
        ):
            raise ValueError("distributed Petrov Gram is singular")
        return u, singular_values, vh

    def _solve_gram(self, rhs: np.ndarray) -> np.ndarray:
        if self._gram_svd is None:
            raise RuntimeError("distributed Petrov Gram is unavailable")
        u, singular_values, vh = self._gram_svd
        rhs = np.asarray(rhs, dtype=np.complex128)
        if rhs.ndim == 1:
            return vh.conj().T @ ((u.conj().T @ rhs) / singular_values)
        return vh.conj().T @ ((u.conj().T @ rhs) / singular_values[:, None])

    def _synthesize_owner_rows(self, local_values: np.ndarray) -> PETSc.Vec:
        values = np.asarray(local_values, dtype=np.complex128)
        if values.ndim != 1 or values.size != self.local_rows:
            raise ValueError("owner-row vector has the wrong local size")
        vector = self._template.duplicate()
        vector.array[:] = np.asarray(values, dtype=PETSc.ScalarType)
        return vector

    def _check_layout(self, vector: PETSc.Vec) -> None:
        if (
            vector.getSize() != self.global_rows
            or vector.getLocalSize() != self.local_rows
            or tuple(map(int, vector.getOwnershipRange())) != self._ownership_range
        ):
            raise ValueError("Petrov Vec has the wrong ownership layout")

    def project_owner_rows(self, source: PETSc.Vec) -> np.ndarray:
        """Return the replicated small vector Yᴴ source."""

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        self._check_layout(source)
        local = self._local_y.conj().T @ np.asarray(source.array, dtype=np.complex128)
        return self._allreduce_small(local)

    @property
    def gamma_rows_local(self) -> np.ndarray | None:
        """Return a copy of the optional owner-local Gamma row identities."""

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        return None if self._local_row_ids is None else self._local_row_ids.copy()

    @property
    def ownership_range(self) -> tuple[int, int]:
        """Return the compressed Vec ownership range used by the carrier."""

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        return tuple(self._ownership_range)

    def _build_projected_columns(self) -> None:
        local_rows = self.local_rows
        scalar_projected_local = np.empty(
            (self.span_size, self.span_size), dtype=np.complex128
        )
        exact_projected_local = np.empty_like(scalar_projected_local)
        self._delta_local = np.empty((local_rows, self.span_size), dtype=np.complex128)
        for column in range(self.span_size):
            source = self._synthesize_owner_rows(self._local_z[:, column])
            scalar_target = self._template.duplicate()
            exact_target = self._template.duplicate()
            try:
                self._scalar_apply(source, scalar_target)
                self.scalar_apply_count += 1
                self._exact_apply(source, exact_target)
                self.exact_apply_count += 1
                scalar_local = np.asarray(scalar_target.array, dtype=np.complex128)
                exact_local = np.asarray(exact_target.array, dtype=np.complex128)
                self._delta_local[:, column] = exact_local - scalar_local
                scalar_projected_local[:, column] = (
                    self._local_y.conj().T @ scalar_local
                )
                exact_projected_local[:, column] = self._local_y.conj().T @ exact_local
            finally:
                exact_target.destroy()
                scalar_target.destroy()
                source.destroy()
        self._projected_scalar = self._allreduce_small(scalar_projected_local)
        self._projected_exact = self._allreduce_small(exact_projected_local)

    def synthesize_owner_rows(self, local_values: np.ndarray) -> PETSc.Vec:
        """Create one distributed Vec from owner-local values; caller destroys it."""

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        return self._synthesize_owner_rows(local_values)

    @property
    def projected_contractions(self) -> dict[str, np.ndarray]:
        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        return {
            "gram": self._gram.copy(),
            "scalar": self._projected_scalar.copy(),
            "exact": self._projected_exact.copy(),
            "delta": self._projected_exact - self._projected_scalar,
        }

    def projected_woodbury_factors(self) -> dict[str, np.ndarray]:
        """Export owner-local ``U=delta`` and ``V=Y G^-H`` copies.

        The adjoint factor is obtained with the carrier's SVD solve for
        ``G^-1 Y^H``; no normal equations or global basis replication are
        introduced.  The arrays are caller-owned tiny/local copies.
        """

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        v_adjoint = self._solve_gram(self._local_y.conj().T)
        return {
            "U": self._delta_local.copy(),
            "V": v_adjoint.conj().T.copy(),
            "G": self._gram.copy(),
        }

    def detach_projected_woodbury_factors(self) -> dict[str, np.ndarray]:
        """Transfer finalized projected factors and release resident carrier state.

        This explicit producer path moves the existing owner-local ``U``
        storage without copying it.  ``V`` is formed once from the finalized
        SVD solve, while the small contractions are transferred as the
        carrier's existing arrays.  After return the action is detached and
        cannot be applied again; the caller owns the returned arrays.
        """

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        v_adjoint = self._solve_gram(self._local_y.conj().T)
        factors = {
            "U": self._delta_local,
            "V": v_adjoint.conj().T,
            "G": self._gram,
            "projected_scalar": self._projected_scalar,
            "projected_exact": self._projected_exact,
        }
        self._template.destroy()
        self._scalar_apply = None
        self._exact_apply = None
        self._local_z = np.empty((0, 0), dtype=np.complex128)
        self._local_y = np.empty((0, 0), dtype=np.complex128)
        self._local_row_ids = None
        self._delta_local = np.empty((0, 0), dtype=np.complex128)
        self._gram = np.empty((0, 0), dtype=np.complex128)
        self._projected_scalar = np.empty((0, 0), dtype=np.complex128)
        self._projected_exact = np.empty((0, 0), dtype=np.complex128)
        self._gram_svd = None
        self._detached = True
        self._destroyed = True
        return factors

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        if (
            source.getSize() != self.global_rows
            or target.getSize() != self.global_rows
            or source.getLocalSize() != self.local_rows
            or target.getLocalSize() != self.local_rows
        ):
            raise ValueError("Petrov source/target has the wrong Vec layout")
        self._check_layout(source)
        self._check_layout(target)
        self._scalar_apply(source, target)
        self.scalar_apply_count += 1
        coefficients = self._solve_gram(self.project_owner_rows(source))
        target.array[:] += np.asarray(
            self._delta_local @ coefficients, dtype=PETSc.ScalarType
        )
        self.apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._destroyed:
            return {
                "destroyed": True,
                "detached": self._detached,
                "resident_local_rows": int(self._local_z.shape[0]),
                "apply_count": self.apply_count,
            }

        return {
            "schema": "task040.v1_2.distributed_petrov_action.v1",
            "global_rows": self.global_rows,
            "local_rows": self.local_rows,
            "ownership_range": list(self._ownership_range),
            "gamma_rows_local_count": (
                None if self._local_row_ids is None else int(self._local_row_ids.size)
            ),
            "z_shape_local": list(self._local_z.shape),
            "y_shape_local": list(self._local_y.shape),
            "basis_global_replicated": False,
            "fe_numeric_allgather": False,
            "small_replicated_shapes": {
                "gram": list(self._gram.shape),
                "projected_scalar": list(self._projected_scalar.shape),
                "projected_exact": list(self._projected_exact.shape),
            },
            "gram": _small_svd_diagnostics(self._gram),
            "projected_scalar": _small_svd_diagnostics(self._projected_scalar),
            "projected_exact": _small_svd_diagnostics(self._projected_exact),
            "column_action_count": self.span_size,
            "scalar_apply_count": self.scalar_apply_count,
            "exact_apply_count": self.exact_apply_count,
            "apply_count": self.apply_count,
            "detached": self._detached,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._template.destroy()
        self._local_z = np.empty((0, 0), dtype=np.complex128)
        self._local_y = np.empty((0, 0), dtype=np.complex128)
        self._local_row_ids = None
        self._delta_local = np.empty((0, 0), dtype=np.complex128)
        self._gram = np.empty((0, 0), dtype=np.complex128)
        self._projected_scalar = np.empty((0, 0), dtype=np.complex128)
        self._projected_exact = np.empty((0, 0), dtype=np.complex128)
        self._scalar_apply = None
        self._exact_apply = None
        self._destroyed = True


class PetscFixedProjectedGroupInverse:
    """Distributed Woodbury inverse over one borrowed exact base factor.

    The represented operator is ``A = B + U V^H``.  ``B`` is supplied only
    through a factor-like object exposing ``solve(source, target)``.  U, V,
    and ``W = B^-1 U`` remain owner-local; only
    ``K = I + V^H W`` and its SVD are replicated.  This is a research-only
    carrier for the conditional V1-3 path, not a KSP or a full-side inverse.
    """

    def __init__(
        self,
        template: PETSc.Vec,
        base_factor: Any,
        local_u: np.ndarray,
        local_v: np.ndarray,
    ) -> None:
        if not callable(getattr(base_factor, "solve", None)):
            raise TypeError("base_factor must expose solve(source, target)")
        self._comm = template.getComm().tompi4py()
        self._template = template.duplicate()
        self._base_factor = base_factor
        self._ownership_range = tuple(map(int, template.getOwnershipRange()))
        self.global_rows = int(template.getSize())
        self.local_rows = int(template.getLocalSize())
        self._local_u = np.asarray(local_u, dtype=np.complex128).copy()
        self._local_v = np.asarray(local_v, dtype=np.complex128).copy()
        self._w_local: np.ndarray | None = None
        self._k: np.ndarray | None = None
        self._k_svd: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        self._base_solution = None
        self._destroyed = False
        self.apply_count = 0
        self.base_solve_count = 0
        try:
            local_shape_valid = bool(
                self._local_u.ndim == 2
                and self._local_v.ndim == 2
                and self._local_u.shape == self._local_v.shape
                and self._local_u.shape[0] == self.local_rows
                and self._local_u.shape[1] > 0
            )
            local_rank = int(self._local_u.shape[1]) if self._local_u.ndim == 2 else -1
            shape_valid = bool(self._comm.allreduce(local_shape_valid, op=MPI.LAND))
            rank_min = int(self._comm.allreduce(local_rank, op=MPI.MIN))
            rank_max = int(self._comm.allreduce(local_rank, op=MPI.MAX))
            if not shape_valid or rank_min <= 0 or rank_min != rank_max:
                raise ValueError(
                    "Woodbury owner-local U/V arrays have incompatible shapes"
                )
            finite = bool(
                np.all(np.isfinite(self._local_u))
                and np.all(np.isfinite(self._local_v))
            )
            if not self._comm.allreduce(finite, op=MPI.LAND):
                raise ValueError("Woodbury owner-local U/V arrays are not finite")
            self.rank = rank_min
            self._base_solution = self._template.duplicate()
            u_vector = self._template.duplicate()
            w_vector = self._template.duplicate()
            w_local = np.empty((self.local_rows, self.rank), dtype=np.complex128)
            try:
                for column in range(self.rank):
                    u_vector.array[:] = np.asarray(
                        self._local_u[:, column], dtype=PETSc.ScalarType
                    )
                    u_vector.assemble()
                    self._base_factor.solve(u_vector, w_vector)
                    self.base_solve_count += 1
                    w_local[:, column] = np.asarray(w_vector.array, dtype=np.complex128)
            finally:
                w_vector.destroy()
                u_vector.destroy()
            local_k = self._local_v.conj().T @ w_local
            k = self._allreduce_small(local_k)
            k += np.eye(self.rank, dtype=np.complex128)
            self._k_svd = self._factor_small(k)
            self._w_local = w_local
            self._k = k
        except Exception:
            self.destroy()
            raise

    def _allreduce_small(self, value: np.ndarray) -> np.ndarray:
        result = np.empty_like(np.asarray(value, dtype=np.complex128))
        self._comm.Allreduce(np.asarray(value, dtype=np.complex128), result, op=MPI.SUM)
        return result

    @staticmethod
    def _factor_small(
        matrix: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        u, singular_values, vh = np.linalg.svd(matrix, full_matrices=False)
        if singular_values.size == 0 or not np.all(np.isfinite(singular_values)):
            raise ValueError("Woodbury small K SVD is not finite")
        tolerance = (
            np.finfo(float).eps
            * max(matrix.shape)
            * max(float(singular_values[0]), 1.0)
        )
        if singular_values[-1] <= tolerance:
            raise ValueError("Woodbury small K is singular")
        return u, singular_values, vh

    def _solve_small(self, rhs: np.ndarray) -> np.ndarray:
        if self._k_svd is None:
            raise RuntimeError("Woodbury small K is unavailable")
        u, singular_values, vh = self._k_svd
        return vh.conj().T @ ((u.conj().T @ rhs) / singular_values)

    def _check_layout(self, vector: PETSc.Vec) -> None:
        if (
            int(vector.getSize()) != self.global_rows
            or int(vector.getLocalSize()) != self.local_rows
            or tuple(map(int, vector.getOwnershipRange())) != self._ownership_range
        ):
            raise ValueError("Woodbury Vec has the wrong ownership layout")

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply ``(B + U V^H)^-1`` to distributed ``source``."""

        if self._destroyed:
            raise RuntimeError("Woodbury group inverse is destroyed")
        self._check_layout(source)
        self._check_layout(target)
        if self._w_local is None:
            raise RuntimeError("Woodbury owner-local W is unavailable")
        self._base_factor.solve(source, self._base_solution)
        self.base_solve_count += 1
        local_rhs = self._local_v.conj().T @ np.asarray(
            self._base_solution.array, dtype=np.complex128
        )
        coefficients = self._solve_small(self._allreduce_small(local_rhs))
        self._base_solution.copy(target)
        target.array[:] -= np.asarray(
            self._w_local @ coefficients, dtype=PETSc.ScalarType
        )
        finite = bool(
            np.all(np.isfinite(coefficients)) and np.all(np.isfinite(target.array))
        )
        if not self._comm.allreduce(finite, op=MPI.LAND):
            raise FloatingPointError(
                "Woodbury group inverse produced non-finite values"
            )
        self.apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._destroyed:
            return {
                "schema": "task040.v1_3.fixed_projected_group_inverse.v1",
                "destroyed": True,
                "apply_count": self.apply_count,
                "base_solve_count": self.base_solve_count,
                "base_factor_reference_released": True,
            }
        if self._k is None or self._w_local is None or self._k_svd is None:
            raise RuntimeError("Woodbury diagnostics requested before setup")
        singular_values = self._k_svd[1]
        return {
            "schema": "task040.v1_3.fixed_projected_group_inverse.v1",
            "operator_identity": "B_plus_U_VH",
            "global_rows": self.global_rows,
            "local_rows": self.local_rows,
            "ownership_range": list(self._ownership_range),
            "owner_local_u_shape": list(self._local_u.shape),
            "owner_local_v_shape": list(self._local_v.shape),
            "owner_local_w_shape": list(self._w_local.shape),
            "small_replicated_shapes": {"K": list(self._k.shape)},
            "K_rank": int(np.linalg.matrix_rank(self._k)),
            "K_singular_values": singular_values.tolist(),
            "K_condition_number": float(singular_values[0] / singular_values[-1]),
            "normal_equations": False,
            "fe_numeric_allgather": False,
            "nested_ksp_count": 0,
            "base_factor_borrowed": True,
            "base_factor_reference_released": False,
            "apply_count": self.apply_count,
            "base_solve_count": self.base_solve_count,
            "destroyed": False,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self._base_solution is not None:
            self._base_solution.destroy()
            self._base_solution = None
        self._template.destroy()
        self._local_u = np.empty((0, 0), dtype=np.complex128)
        self._local_v = np.empty((0, 0), dtype=np.complex128)
        self._w_local = None
        self._k = None
        self._k_svd = None
        self._base_factor = None
        self._destroyed = True


def build_distributed_petrov_action(
    layout: PETSc.Vec,
    scalar_apply: Callable[[PETSc.Vec, PETSc.Vec], None],
    exact_apply: Callable[[PETSc.Vec, PETSc.Vec], None],
    local_z: np.ndarray,
    local_y: np.ndarray,
    local_row_ids: np.ndarray | None = None,
) -> PetscDistributedPetrovAction:
    """Build a distributed owner-row carrier from a caller-owned Vec layout."""

    return PetscDistributedPetrovAction(
        layout, scalar_apply, exact_apply, local_z, local_y, local_row_ids
    )


def build_fixed_projected_group_inverse(
    template: PETSc.Vec,
    base_factor: Any,
    local_u: np.ndarray,
    local_v: np.ndarray,
) -> PetscFixedProjectedGroupInverse:
    """Build the opt-in distributed ``B + U V^H`` inverse carrier."""

    return PetscFixedProjectedGroupInverse(
        template,
        base_factor,
        local_u,
        local_v,
    )


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
