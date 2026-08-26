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
from bisect import bisect_right
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

from .hybrid_local_dtn_woodbury import ResearchExactFactorInverse
from .hybrid_interface_packet import canonical_key_sha256

__all__ = (
    "NumpyInterfaceSchurOracle",
    "PetscInterfaceSchurOracle",
    "PetscFullInterfaceSchurAction",
    "CanonicalInterfaceLayout",
    "build_canonical_interface_layout",
    "build_owner_local_group_rows",
    "build_v6_cell_recovery_group_pairs",
    "build_v6_cell_recovery_owner_group_rows",
    "ProjectedExactPetrovAction",
    "PetscDistributedPetrovAction",
    "PetscFixedProjectedGroupInverse",
    "build_numpy_interface_schur_oracle",
    "build_petsc_interface_schur_oracle",
    "build_petsc_full_interface_schur_action",
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

    def _check_vectors(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("PETSc interface Schur block is destroyed")
        if source.getSize() != self._gamma_rhs.getSize():
            raise ValueError("PETSc interface Schur source has the wrong size")
        if target.getSize() != self._gamma_output.getSize():
            raise ValueError("PETSc interface Schur target has the wrong size")

    def apply_gamma_gamma(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply only the principal ``A_Gamma,Gamma`` block."""

        self._check_vectors(source, target)
        self._a_gg.mult(source, target)

    def apply_interior_correction(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply ``A_Gamma,I A_I,I^-1 A_I,Gamma`` without ``A_Gamma,Gamma``."""

        self._check_vectors(source, target)
        self._a_ig.mult(source, self._interior_rhs)
        self._factor.solve(self._interior_rhs, self._interior_solution)
        self._a_gi.mult(self._interior_solution, target)

    def solve_interior(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Solve one group interior block for an independent full-state audit."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur block is destroyed")
        if source.getSize() != self._gamma_rhs.getSize():
            raise ValueError("PETSc interior solve source has the wrong size")
        reference = self._interior_solution
        if (
            target.getSize() != reference.getSize()
            or target.getLocalSize() != reference.getLocalSize()
            or tuple(map(int, target.getOwnershipRange()))
            != tuple(map(int, reference.getOwnershipRange()))
        ):
            raise ValueError("PETSc interior solve target has the wrong layout")
        self._a_ig.mult(source, self._interior_rhs)
        self._factor.solve(self._interior_rhs, target)

    def create_interior_vector(self) -> PETSc.Vec:
        """Create a caller-owned vector in this group's interior layout."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur block is destroyed")
        return self._interior_solution.duplicate()

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        self._check_vectors(source, target)
        self.apply_gamma_gamma(source, self._gamma_output)
        self.apply_interior_correction(source, self._gamma_work)
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
        self._bare = bare
        self._blocks: list[_PetscInterfaceSchurBlock] = []
        self._row_copy_indices: dict[
            tuple[int, int], tuple[np.ndarray, np.ndarray]
        ] = {}
        bare_comm = bare.getComm().tompi4py()
        self._bare_ownership_ranges = tuple(
            tuple(map(int, value))
            for value in bare_comm.allgather(bare.getOwnershipRange())
        )
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

    def apply_group_gamma_gamma(
        self,
        group: int,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        """Apply one group's ``A_Gamma,Gamma`` block exactly once."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        self._blocks[int(group)].apply_gamma_gamma(source, target)

    def apply_group_interior_correction(
        self,
        group: int,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        """Apply one group's interior-elimination correction only."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        self._blocks[int(group)].apply_interior_correction(source, target)

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

    def create_group_interior_vector(self, group: int) -> PETSc.Vec:
        """Create a caller-owned vector in one group's interior layout."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        return self._blocks[int(group)].create_interior_vector()

    def solve_group_interior(
        self,
        group: int,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        """Solve ``A_II x = A_IGamma source`` for a full-state audit."""

        if self._destroyed:
            raise RuntimeError("PETSc interface Schur oracle is destroyed")
        self._blocks[int(group)].solve_interior(source, target)

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


@dataclass(frozen=True)
class CanonicalInterfaceLayout:
    """Owner-local mapping from current Gamma rows to joint positions.

    The complete physical-key inventory is used only while the layout is
    constructed.  Each rank retains only the rows it owns and their positions
    in the canonical ``Gamma_L``-then-``Gamma_U`` vector.
    """

    local_row_to_position: Mapping[int, int]
    lower_global_count: int
    upper_global_count: int
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        mapping = {
            int(row): int(position)
            for row, position in dict(self.local_row_to_position).items()
        }
        if len(mapping) != len(self.local_row_to_position):
            raise ValueError("canonical local row mapping contains duplicates")
        if any(position < 0 for position in mapping.values()):
            raise ValueError("canonical local positions must be nonnegative")
        joint_count = int(self.lower_global_count) + int(self.upper_global_count)
        if any(position >= joint_count for position in mapping.values()):
            raise ValueError("canonical local positions exceed joint size")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("canonical local positions are not bijective")
        if int(self.lower_global_count) <= 0 or int(self.upper_global_count) <= 0:
            raise ValueError("canonical interface counts must be positive")
        object.__setattr__(self, "local_row_to_position", mapping)
        object.__setattr__(self, "lower_global_count", int(self.lower_global_count))
        object.__setattr__(self, "upper_global_count", int(self.upper_global_count))
        object.__setattr__(self, "audit", dict(self.audit))


def build_canonical_interface_layout(
    lower_layout: Any,
    upper_layout: Any,
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    expected_lower_count: int | None = None,
    expected_upper_count: int | None = None,
) -> CanonicalInterfaceLayout:
    """Build an owner-local canonical L/U row-position map.

    ``GammaCanonicalLayout`` carries physical canonical keys together with
    current owner-local raw rows.  The keys and rows are gathered once to the
    root as metadata, sorted by key there, and only each rank's row-position
    map is scattered back.  No numeric Gamma values and no complete key/row
    inventory are retained on every rank.
    """

    def local_pairs(layout: Any, name: str) -> list[tuple[str, int]]:
        try:
            keys = tuple(str(value) for value in layout.canonical_keys)
            rows = np.asarray(layout.gamma_rows_local, dtype=np.int64)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"{name} Gamma layout is not readable") from exc
        if rows.ndim != 1 or len(keys) != rows.size:
            raise ValueError(f"{name} Gamma layout keys and rows differ")
        if len(set(keys)) != len(keys) or len(np.unique(rows)) != rows.size:
            raise ValueError(f"{name} Gamma layout is not locally bijective")
        return [(key, int(row)) for key, row in zip(keys, rows, strict=True)]

    local_error: str | None = None
    try:
        lower_pairs = local_pairs(lower_layout, "lower")
        upper_pairs = local_pairs(upper_layout, "upper")
    except Exception as exc:
        lower_pairs = []
        upper_pairs = []
        local_error = f"{type(exc).__name__}: {exc}"
    errors = comm.allgather(local_error)
    first_error = next((error for error in errors if error is not None), None)
    if first_error is not None:
        raise ValueError(f"canonical Gamma metadata validation failed: {first_error}")

    gathered = comm.gather(
        {"lower": lower_pairs, "upper": upper_pairs},
        root=0,
    )
    root_error: str | None = None
    rank_maps: list[dict[int, int]] | None = None
    audit: dict[str, Any] | None = None
    if comm.rank == 0:
        try:
            assert gathered is not None
            flattened: dict[str, list[tuple[str, int, int]]] = {
                "lower": [],
                "upper": [],
            }
            for rank, payload in enumerate(gathered):
                for name in ("lower", "upper"):
                    flattened[name].extend(
                        (key, row, rank) for key, row in payload[name]
                    )
            lower_count = len(flattened["lower"])
            upper_count = len(flattened["upper"])
            if expected_lower_count is not None and lower_count != int(
                expected_lower_count
            ):
                raise ValueError(
                    f"lower Gamma count {lower_count} != {expected_lower_count}"
                )
            if expected_upper_count is not None and upper_count != int(
                expected_upper_count
            ):
                raise ValueError(
                    f"upper Gamma count {upper_count} != {expected_upper_count}"
                )
            all_rows = [
                row for values in flattened.values() for _key, row, _rank in values
            ]
            if len(all_rows) != len(set(all_rows)):
                raise ValueError("canonical Gamma raw rows overlap between planes")
            for name in ("lower", "upper"):
                plane_keys = [key for key, _row, _rank in flattened[name]]
                if len(plane_keys) != len(set(plane_keys)):
                    raise ValueError(f"canonical {name} Gamma keys are duplicated")
            ordered = {
                name: sorted(values, key=lambda item: item[0])
                for name, values in flattened.items()
            }
            positions = {
                name: {
                    row: offset + index
                    for index, (_key, row, _rank) in enumerate(values)
                }
                for name, values, offset in (
                    ("lower", ordered["lower"], 0),
                    ("upper", ordered["upper"], lower_count),
                )
            }
            rank_maps = [{} for _rank in range(comm.size)]
            for name in ("lower", "upper"):
                for _key, row, rank in flattened[name]:
                    if row in rank_maps[rank]:
                        raise ValueError("canonical local row maps are not unique")
                    rank_maps[rank][row] = positions[name][row]
            lower_keys = tuple(item[0] for item in ordered["lower"])
            upper_keys = tuple(item[0] for item in ordered["upper"])
            lower_rows = np.asarray(
                [item[1] for item in ordered["lower"]], dtype=np.int64
            )
            upper_rows = np.asarray(
                [item[1] for item in ordered["upper"]], dtype=np.int64
            )
            audit = {
                "schema": "task040.v6_2.canonical_interface_layout.v1",
                "lower_global_count": lower_count,
                "upper_global_count": upper_count,
                "joint_global_count": lower_count + upper_count,
                "canonical_order": "Gamma_L_then_Gamma_U_by_physical_key",
                "lower_key_order_sha256": canonical_key_sha256(lower_keys),
                "upper_key_order_sha256": canonical_key_sha256(upper_keys),
                "canonical_key_order_sha256": canonical_key_sha256(
                    [
                        {"side": "Gamma_L", "key": key}
                        for key in lower_keys
                    ]
                    + [
                        {"side": "Gamma_U", "key": key}
                        for key in upper_keys
                    ]
                ),
                "lower_raw_row_order_sha256": _int_array_sha256(lower_rows),
                "upper_raw_row_order_sha256": _int_array_sha256(upper_rows),
                "root_metadata_gather": True,
                "per_rank_full_interface_replica": False,
                "owner_local_mapping": True,
                "canonical_position_bijection": True,
                "coverage_exact": True,
                "numeric_allgather": False,
                "fe_numeric_allgather": False,
                "local_key_counts_by_rank": [
                    len(payload["lower"]) + len(payload["upper"])
                    for payload in gathered
                ],
            }
        except Exception as exc:
            root_error = f"{type(exc).__name__}: {exc}"
    root_error = comm.bcast(root_error, root=0)
    if root_error is not None:
        raise ValueError(f"canonical Gamma metadata construction failed: {root_error}")
    rank_map = comm.scatter(rank_maps, root=0)
    audit = comm.bcast(audit, root=0)
    assert audit is not None
    return CanonicalInterfaceLayout(
        local_row_to_position=rank_map,
        lower_global_count=int(audit["lower_global_count"]),
        upper_global_count=int(audit["upper_global_count"]),
        audit=audit,
    )


class PetscFullInterfaceSchurAction:
    """Owner-local full-interface Schur action on a canonical Gamma Vec.

    ``canonical_layout`` supplies only this rank's current-row to canonical-
    position map.  The group-1 Gamma Vec is only an owner-local carrier and
    may interleave lower and upper rows by rank.  Three ``VecScatter`` objects
    are built once at construction to route between those layouts.

    The action applies the exact algebra

    ``S_Gamma = A_Gamma,Gamma - sum_j A_Gamma,Ij A_Ij,Ij^-1 A_Ij,Gamma``.

    The middle group's ``A_Gamma,Gamma`` is applied once; groups 0 and 2
    contribute correction-only terms.  All numerical work vectors and
    scatters are distributed and allocated before the first apply.
    """

    def __init__(
        self,
        oracle: PetscInterfaceSchurOracle,
        *,
        canonical_layout: CanonicalInterfaceLayout,
        own_oracle: bool = False,
    ) -> None:
        if not isinstance(oracle, PetscInterfaceSchurOracle):
            raise TypeError("full-interface action requires a PETSc Schur oracle")
        if not isinstance(canonical_layout, CanonicalInterfaceLayout):
            raise TypeError("full-interface action requires a canonical layout")
        self._oracle = oracle
        self._canonical_layout = canonical_layout
        self._own_oracle = bool(own_oracle)
        self._comm = oracle._blocks[0]._a_gg.getComm().tompi4py()
        self._template: PETSc.Vec | None = None
        self._group1_source: PETSc.Vec | None = None
        self._group1_boundary: PETSc.Vec | None = None
        self._group1_correction: PETSc.Vec | None = None
        self._lower_source: PETSc.Vec | None = None
        self._lower_target: PETSc.Vec | None = None
        self._upper_source: PETSc.Vec | None = None
        self._upper_target: PETSc.Vec | None = None
        self._scatters: dict[int, PETSc.Scatter] = {}
        self._destroyed = False
        self._oracle_destroyed = False
        self._apply_count = 0
        self._layout_audit: dict[str, Any] = {}
        self._factor_ready_observed: int | None = None
        self._factor_simultaneous_max = 0
        self._group_positions: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        try:
            expected_size = int(
                self._canonical_layout.lower_global_count
                + self._canonical_layout.upper_global_count
            )
            if expected_size == 0:
                raise ValueError("full-interface Gamma layout cannot be empty")
            petsc_comm = oracle._blocks[0]._a_gg.getComm()
            self._template = PETSc.Vec().createMPI(
                (None, expected_size), comm=petsc_comm
            )
            self._group1_source = oracle.create_group_gamma_vector(1)
            self._group1_boundary = self._group1_source.duplicate()
            self._group1_correction = self._group1_source.duplicate()
            self._lower_source = oracle.create_group_gamma_vector(0)
            self._lower_target = self._lower_source.duplicate()
            self._upper_source = oracle.create_group_gamma_vector(2)
            self._upper_target = self._upper_source.duplicate()
            self._layout_audit = self._validate_joint_layout()
            self._build_scatters()
            ready = self._observe_factor_state()
            if ready != 3:
                raise RuntimeError(
                    "V6 full-interface action requires three ready group factors"
                )
        except Exception:
            self.destroy()
            raise

    def _validate_joint_layout(self) -> dict[str, Any]:
        if self._template is None:
            raise RuntimeError("full-interface layout template is unavailable")
        layout_audit = dict(self._canonical_layout.audit)
        lower_count = int(self._canonical_layout.lower_global_count)
        upper_count = int(self._canonical_layout.upper_global_count)
        expected_size = lower_count + upper_count
        if not bool(layout_audit.get("canonical_position_bijection")):
            raise ValueError("canonical Gamma layout is not bijective")
        if not bool(layout_audit.get("coverage_exact")):
            raise ValueError("canonical Gamma layout does not have exact coverage")
        local_size_ok = int(self._template.getSize()) == expected_size
        if not bool(self._comm.allreduce(local_size_ok, op=MPI.LAND)):
            raise ValueError("canonical Gamma Vec has the wrong global size")

        local_supports = (
            np.asarray(self._oracle.interface_supports[0], dtype=np.int64),
            np.asarray(self._oracle.interface_supports[1], dtype=np.int64),
        )
        if np.intersect1d(local_supports[0], local_supports[1]).size:
            raise ValueError("local Gamma supports overlap")
        local_interface_rows = set(
            map(int, np.concatenate(local_supports).tolist())
        )
        local_mapping = self._canonical_layout.local_row_to_position
        local_mapping_ok = set(local_mapping) == local_interface_rows
        expected_local_count = int(
            self._canonical_layout.audit["local_key_counts_by_rank"][self._comm.rank]
        )
        local_mapping_ok = local_mapping_ok and len(local_mapping) == expected_local_count
        if not bool(self._comm.allreduce(local_mapping_ok, op=MPI.LAND)):
            raise ValueError(
                "canonical owner-local mapping does not match local Gamma support"
            )
        expected_by_group = (
            set(map(int, local_supports[0])),
            set(map(int, np.concatenate(local_supports))),
            set(map(int, local_supports[1])),
        )
        owner_first, owner_last = self._oracle._bare_ownership_ranges[self._comm.rank]
        group_positions: list[np.ndarray] = []
        group_order_hashes: list[str] = []
        group_local_hashes: list[str] = []
        for group in range(3):
            rows = np.asarray(
                self._oracle.group_gamma_rows_local(group), dtype=np.int64
            )
            position_values = np.asarray(
                [local_mapping.get(int(row), -1) for row in rows], dtype=np.int64
            )
            local_rows_ok = (
                np.unique(rows).size == rows.size
                and bool(np.all(np.isin(rows, tuple(expected_by_group[group]))))
                and bool(np.all((rows >= owner_first) & (rows < owner_last)))
                and np.unique(position_values).size == position_values.size
                and bool(
                    np.all(
                        (position_values >= 0) & (position_values < expected_size)
                    )
                )
            )
            if group == 0:
                position_range = (0, lower_count)
                expected_count = lower_count
            elif group == 1:
                position_range = (0, expected_size)
                expected_count = expected_size
            else:
                position_range = (lower_count, expected_size)
                expected_count = upper_count
            local_rows_ok = local_rows_ok and bool(
                np.all(
                    (position_values >= position_range[0])
                    & (position_values < position_range[1])
                )
            )
            local_count = int(self._comm.allreduce(rows.size, op=MPI.SUM))
            if not bool(
                self._comm.allreduce(
                    local_rows_ok and local_count == expected_count,
                    op=MPI.LAND,
                )
            ):
                raise ValueError(
                    f"group{group} Gamma rows do not cover its owner-local support"
                )
            group_positions.append(position_values.astype(PETSc.IntType, copy=False))
            local_hash = _int_array_sha256(rows)
            rank_hashes = self._comm.allgather(local_hash)
            group_local_hashes.append(local_hash)
            group_order_hashes.append(
                hashlib.sha256(repr(tuple(rank_hashes)).encode()).hexdigest()
            )

        group1_vector = self._oracle._blocks[1]._gamma_rhs
        group1_first, group1_last = map(int, group1_vector.getOwnershipRange())
        group1_positions = group_positions[1]
        group1_order_is_canonical_local = bool(
            group1_positions.size == group1_last - group1_first
            and np.array_equal(
                np.asarray(group1_positions, dtype=np.int64),
                np.arange(group1_first, group1_last, dtype=np.int64),
            )
        )
        group1_order_is_canonical = bool(
            self._comm.allreduce(group1_order_is_canonical_local, op=MPI.LAND)
        )

        ownership = [
            tuple(map(int, value))
            for value in self._comm.allgather(self._template.getOwnershipRange())
        ]
        ownership_sorted = sorted(ownership)
        ownership_valid = bool(
            ownership_sorted
            and ownership_sorted[0][0] == 0
            and ownership_sorted[-1][1] == int(self._template.getSize())
            and all(
                left[1] == right[0]
                for left, right in zip(ownership_sorted, ownership_sorted[1:])
            )
            and all(last >= first for first, last in ownership_sorted)
        )
        if not ownership_valid:
            raise ValueError("canonical Gamma Vec ownership is not contiguous")

        self._group_positions = tuple(group_positions)
        return {
            "global_size": expected_size,
            "local_size": int(self._template.getLocalSize()),
            "ownership_ranges": [list(value) for value in ownership],
            "canonical_ownership_ranges": [list(value) for value in ownership_sorted],
            "lower_global_rows": lower_count,
            "upper_global_rows": upper_count,
            "canonical_order": layout_audit.get(
                "canonical_order", "Gamma_L_then_Gamma_U_by_physical_key"
            ),
            "lower_order_sha256": layout_audit["lower_key_order_sha256"],
            "upper_order_sha256": layout_audit["upper_key_order_sha256"],
            "canonical_order_sha256": layout_audit["canonical_key_order_sha256"],
            "group_order_sha256": group_order_hashes,
            "group_local_row_sha256": group_local_hashes,
            "group1_owner_order_digest_sha256": group_order_hashes[1],
            "group1_order_is_canonical": group1_order_is_canonical,
            "value_basis": "current_raw_active_coefficients",
            "canonical_block_transforms_applied": False,
            "transform_required_for": "V6-3_full_spectrum_trace_authority",
            "canonical_position_bijection": True,
            "coverage_exact": True,
            "owner_distributed": True,
            "owner_local_mapping_count": len(local_mapping),
            "root_metadata_gather": True,
            "per_rank_full_interface_replica": False,
            "numeric_allgather": False,
            "fe_numeric_allgather": False,
        }

    def _build_scatters(self) -> None:
        if self._template is None:
            raise RuntimeError("cannot build Gamma scatters without a template")
        if self._group_positions is None:
            raise RuntimeError("canonical Gamma positions are unavailable")
        vectors = {
            0: self._lower_source,
            1: self._group1_source,
            2: self._upper_source,
        }
        petsc_comm = self._template.getComm()
        for group, vector in vectors.items():
            if vector is None:
                raise RuntimeError(f"group{group} scatter target is unavailable")
            positions = self._group_positions[group]
            source_is = PETSc.IS().createGeneral(positions, comm=petsc_comm)
            first, last = map(int, vector.getOwnershipRange())
            target_is = PETSc.IS().createStride(
                last - first,
                first=first,
                step=1,
                comm=petsc_comm,
            )
            try:
                self._scatters[group] = PETSc.Scatter().create(
                    self._template, source_is, vector, target_is
                )
            finally:
                target_is.destroy()
                source_is.destroy()

    def _observe_factor_state(self) -> int:
        diagnostics = self._oracle.diagnostics
        ready = int(diagnostics.get("factor_count_ready", 0))
        if self._factor_ready_observed is None:
            self._factor_ready_observed = ready
        self._factor_simultaneous_max = max(self._factor_simultaneous_max, ready)
        return ready

    @property
    def comm(self) -> MPI.Intracomm:
        return self._comm

    @property
    def global_size(self) -> int:
        return int(self._layout_audit["global_size"])

    def _check_live(self) -> None:
        if self._destroyed:
            raise RuntimeError("full-interface Schur action is destroyed")

    def _check_layout(self, vector: PETSc.Vec) -> None:
        if self._template is None:
            raise RuntimeError("full-interface layout template is unavailable")
        if (
            vector.getSize() != self._template.getSize()
            or vector.getLocalSize() != self._template.getLocalSize()
            or tuple(map(int, vector.getOwnershipRange()))
            != tuple(map(int, self._template.getOwnershipRange()))
        ):
            raise ValueError("full-interface Vec has the wrong Gamma ownership layout")

    def _check_group_layout(self, group: int, vector: PETSc.Vec) -> None:
        reference = self._oracle._blocks[int(group)]._gamma_rhs
        if (
            vector.getSize() != reference.getSize()
            or vector.getLocalSize() != reference.getLocalSize()
            or tuple(map(int, vector.getOwnershipRange()))
            != tuple(map(int, reference.getOwnershipRange()))
        ):
            raise ValueError("group Gamma Vec has the wrong ownership layout")

    def create_interface_vector(self) -> PETSc.Vec:
        """Create a caller-owned Vec with the canonical joint Gamma layout."""

        self._check_live()
        if self._template is None:
            raise RuntimeError("full-interface layout template is unavailable")
        return self._template.duplicate()

    def restrict_interface(self, source: PETSc.Vec) -> tuple[PETSc.Vec, PETSc.Vec]:
        """Restrict a canonical Gamma vector to owner-local L/U vectors."""

        self._check_live()
        self._check_layout(source)
        lower = self._oracle.create_group_gamma_vector(0)
        upper = self._oracle.create_group_gamma_vector(2)
        try:
            self._scatters[0].scatter(
                source,
                lower,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            self._scatters[2].scatter(
                source,
                upper,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            return lower, upper
        except Exception:
            upper.destroy()
            lower.destroy()
            raise

    def restrict_group_interface(self, group: int, source: PETSc.Vec) -> PETSc.Vec:
        """Restrict a canonical interface vector to one owner-local group."""

        self._check_live()
        self._check_layout(source)
        group = int(group)
        if group not in self._scatters:
            raise ValueError("full-interface group must be 0, 1, or 2")
        target = self._oracle.create_group_gamma_vector(group)
        try:
            self._scatters[group].scatter(
                source,
                target,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            return target
        except Exception:
            target.destroy()
            raise

    def extract_interface_from_active_vector(self, source: PETSc.Vec) -> PETSc.Vec:
        """Extract Gamma rows from an active-vector result into canonical order.

        The input is an owner-local active vector, typically the result of an
        independent bare-``F`` multiply.  Only the local Gamma rows are
        copied into the prebuilt lower/upper scatters; no numeric values are
        gathered across ranks.
        """

        self._check_live()
        bare = self._oracle._bare
        bare_first, bare_last = map(int, bare.getOwnershipRange())
        if (
            source.getSize() != bare.getSize()[0]
            or source.getLocalSize() != bare_last - bare_first
            or tuple(map(int, source.getOwnershipRange()))
            != (bare_first, bare_last)
        ):
            raise ValueError("active-vector result has the wrong bare-F layout")
        first, _last = map(int, source.getOwnershipRange())
        lower = self._oracle.create_group_gamma_vector(0)
        upper = self._oracle.create_group_gamma_vector(2)
        target: PETSc.Vec | None = None
        try:
            for group, vector in ((0, lower), (2, upper)):
                rows = self._oracle.group_gamma_rows_local(group)
                if vector.getLocalSize() != rows.size:
                    raise ValueError("active-vector Gamma rows do not match group Vec")
                vector.array[:] = np.asarray(
                    source.array[rows - first], dtype=PETSc.ScalarType
                )
                vector.assemble()
            target = self.create_interface_vector()
            self.prolong_interface(lower, upper, target)
            return target
        except Exception:
            if target is not None:
                target.destroy()
            raise
        finally:
            upper.destroy()
            lower.destroy()

    def build_full_eliminated_state(
        self,
        source: PETSc.Vec,
    ) -> tuple[PETSc.Vec, dict[str, np.ndarray | int]]:
        """Build one full active state using the three group interior solves.

        This is an identity-audit helper, not the Schur action implementation:
        the caller can apply the independent bare ``F`` to the returned state
        and compare that residual with ``MatPython.mult``.  Only owner-local
        Gamma/interior rows are assembled into the full active vector.
        """

        self._check_live()
        self._check_layout(source)
        full = self._oracle._bare.createVecRight()
        full.set(0.0)
        first, last = map(int, full.getOwnershipRange())
        assigned: dict[int, complex] = {}
        interior_rows: set[int] = set()
        gamma_rows: set[int] = set()
        temporaries: list[PETSc.Vec] = []
        try:
            for group in range(3):
                group_source = self.restrict_group_interface(group, source)
                interior = self._oracle.create_group_interior_vector(group)
                temporaries.extend((group_source, interior))
                self._oracle.solve_group_interior(group, group_source, interior)
                interior.scale(PETSc.ScalarType(-1.0))
                gamma_rows_local = self._oracle.group_gamma_rows_local(group)
                interior_rows_local = self._oracle._blocks[group].interior_rows.copy()
                if (
                    group_source.getLocalSize() != gamma_rows_local.size
                    or interior.getLocalSize() != interior_rows_local.size
                ):
                    raise ValueError(
                        "group elimination vector does not match owner-local rows"
                    )
                gamma_values = np.asarray(
                    group_source.array, dtype=np.complex128
                ).copy()
                interior_values = np.asarray(
                    interior.array, dtype=np.complex128
                ).copy()
                for row, value in zip(gamma_rows_local, gamma_values, strict=True):
                    row = int(row)
                    if not first <= row < last:
                        raise ValueError("group Gamma row is not owned by this rank")
                    previous = assigned.get(row)
                    if previous is not None and not np.isclose(
                        previous, value, rtol=0.0, atol=1.0e-13
                    ):
                        raise ValueError("overlapping group Gamma values disagree")
                    assigned[row] = complex(value)
                    gamma_rows.add(row)
                for row, value in zip(
                    interior_rows_local, interior_values, strict=True
                ):
                    row = int(row)
                    if not first <= row < last:
                        raise ValueError("group interior row is not owned by this rank")
                    previous = assigned.get(row)
                    if previous is not None and not np.isclose(
                        previous, value, rtol=0.0, atol=1.0e-13
                    ):
                        raise ValueError("overlapping group interior values disagree")
                    assigned[row] = complex(value)
                    interior_rows.add(row)
            expected_local_rows = set(range(first, last))
            if gamma_rows.intersection(interior_rows):
                raise ValueError("full-state Gamma and interior rows overlap")
            if set(assigned) != expected_local_rows:
                raise ValueError(
                    "full-state rows do not cover the local bare-F ownership range"
                )
            global_assigned = int(
                self._comm.allreduce(len(assigned), op=MPI.SUM)
            )
            global_gamma = int(self._comm.allreduce(len(gamma_rows), op=MPI.SUM))
            global_interior = int(
                self._comm.allreduce(len(interior_rows), op=MPI.SUM)
            )
            if global_assigned != int(full.getSize()):
                raise ValueError("full-state rows do not cover the bare-F size")
            if global_gamma + global_interior != int(full.getSize()):
                raise ValueError("full-state Gamma/interior coverage is incomplete")
            for row, value in assigned.items():
                full.array[row - first] = PETSc.ScalarType(value)
            full.assemble()
            return full, {
                "gamma_rows_local": np.asarray(sorted(gamma_rows), dtype=np.int64),
                "interior_rows_local": np.asarray(
                    sorted(interior_rows), dtype=np.int64
                ),
                "group_interior_solve_count": 3,
            }
        except Exception:
            full.destroy()
            raise
        finally:
            for vector in reversed(temporaries):
                vector.destroy()

    def prolong_interface(
        self,
        lower: PETSc.Vec,
        upper: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        """Prolong owner-local L/U vectors into the canonical Gamma layout."""

        self._check_live()
        self._check_layout(target)
        self._check_group_layout(0, lower)
        self._check_group_layout(2, upper)
        target.set(0.0)
        self._scatters[0].scatter(
            lower,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self._scatters[2].scatter(
            upper,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        target.assemble()

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Apply the exact joint Schur with one principal Gamma action."""

        self._check_live()
        self._check_layout(source)
        self._check_layout(target)
        if (
            self._group1_source is None
            or self._group1_boundary is None
            or self._group1_correction is None
            or self._lower_source is None
            or self._lower_target is None
            or self._upper_source is None
            or self._upper_target is None
        ):
            raise RuntimeError("full-interface scratch vectors are unavailable")

        target.set(0.0)
        self._scatters[1].scatter(
            source,
            self._group1_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._oracle.apply_group_gamma_gamma(
            1, self._group1_source, self._group1_boundary
        )
        self._scatters[1].scatter(
            self._group1_boundary,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        self._oracle.apply_group_interior_correction(
            1, self._group1_source, self._group1_correction
        )
        self._group1_correction.scale(PETSc.ScalarType(-1.0))
        self._scatters[1].scatter(
            self._group1_correction,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )

        self._scatters[0].scatter(
            source,
            self._lower_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._oracle.apply_group_interior_correction(
            0, self._lower_source, self._lower_target
        )
        self._lower_target.scale(PETSc.ScalarType(-1.0))
        self._scatters[0].scatter(
            self._lower_target,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )

        self._scatters[2].scatter(
            source,
            self._upper_source,
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._oracle.apply_group_interior_correction(
            2, self._upper_source, self._upper_target
        )
        self._upper_target.scale(PETSc.ScalarType(-1.0))
        self._scatters[2].scatter(
            self._upper_target,
            target,
            addv=PETSc.InsertMode.ADD_VALUES,
            mode=PETSc.ScatterMode.REVERSE,
        )
        target.assemble()
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        if self._destroyed:
            factor_after = 0 if self._oracle_destroyed else None
            factor_ready = 0 if self._oracle_destroyed else self._observe_factor_state()
        else:
            factor_after = None
            factor_ready = self._observe_factor_state()
        factor_ready_observed = int(self._factor_ready_observed or 0)
        return {
            "schema": "task040.v6_2.full_interface_schur.petsc.v1",
            "formula": "A_GammaGamma_global-sum(A_GammaI*A_II^-1*A_IGamma)",
            "interface_layout": dict(self._layout_audit),
            "value_basis": self._layout_audit.get(
                "value_basis", "current_raw_active_coefficients"
            ),
            "canonical_block_transforms_applied": bool(
                self._layout_audit.get("canonical_block_transforms_applied", False)
            ),
            "factor_count_ready": factor_ready,
            "factor_count_ready_observed": factor_ready_observed,
            "factor_count_after_cleanup": factor_after,
            "factor_lifecycle": {
                "ready": factor_ready_observed,
                "after_cleanup": factor_after,
                "simultaneous_max": int(self._factor_simultaneous_max),
            },
            "group_factor_count": factor_ready,
            "full_side_exact_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
            "dense_interface_materialization": False,
            "full_interface_numeric_replica": False,
            "numeric_allgather": False,
            "fe_numeric_allgather": False,
            "owner_local_scratch": True,
            "scratch_vector_count": 7,
            "layout_template_vector_count": 1,
            "preallocated_vector_count": 8,
            "scratch_vectors_allocated_per_apply": 0,
            "scatter_count": 3,
            "scatter_allocated_at_construction": True,
            "apply_count": int(self._apply_count),
            "destroyed": bool(self._destroyed),
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        for scatter in self._scatters.values():
            scatter.destroy()
        self._scatters.clear()
        for name in (
            "_upper_target",
            "_upper_source",
            "_lower_target",
            "_lower_source",
            "_group1_correction",
            "_group1_boundary",
            "_group1_source",
            "_template",
        ):
            vector = getattr(self, name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        if self._own_oracle:
            self._oracle.destroy()
            self._oracle_destroyed = True
        self._destroyed = True


class _PetscFullInterfaceSchurMatContext:
    def __init__(self, action: PetscFullInterfaceSchurAction) -> None:
        self.action: PetscFullInterfaceSchurAction | None = action

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        if self.action is None:
            raise RuntimeError("full-interface MatPython context is destroyed")
        self.action.apply(source, target)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self.action is not None:
            self.action.destroy()
            self.action = None


def build_petsc_full_interface_schur_action(
    oracle: PetscInterfaceSchurOracle,
    *,
    canonical_layout: CanonicalInterfaceLayout,
    own_oracle: bool = True,
) -> tuple[PETSc.Mat, PetscFullInterfaceSchurAction]:
    """Create a distributed MatPython full-interface Schur action.

    The returned Mat and action are both caller-owned.  With the default
    ``own_oracle=True`` destroying either one also releases the oracle's three
    group factors; callers must not destroy that oracle independently.
    """

    action = PetscFullInterfaceSchurAction(
        oracle,
        canonical_layout=canonical_layout,
        own_oracle=own_oracle,
    )
    if action._template is None:
        action.destroy()
        raise RuntimeError("full-interface action did not create a template")
    sizes = (
        (action._template.getLocalSize(), action.global_size),
        (action._template.getLocalSize(), action.global_size),
    )
    try:
        matrix = PETSc.Mat().createPython(
            sizes,
            context=_PetscFullInterfaceSchurMatContext(action),
            comm=action.comm,
        )
    except Exception:
        action.destroy()
        raise
    try:
        matrix.setUp()
    except Exception:
        matrix.destroy()
        raise
    return matrix, action


def build_owner_local_group_rows(
    local_group_pairs: Sequence[Sequence[int]] | np.ndarray,
    ownership_ranges: Sequence[Sequence[int]],
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    global_size: int | None = None,
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], dict[str, Any]]:
    """Route sparse ``(active_row, group)`` pairs to their PETSc row owner.

    Cell recovery can observe a shared interface row on more than one rank.
    This helper routes only the sparse row/group identities with ``Alltoall``;
    the owner deduplicates them and returns sorted local rows for groups 0, 1,
    and 2.  It never allocates a global boolean mask or gathers numeric data.
    """

    ranges = [tuple(map(int, value)) for value in ownership_ranges]
    if len(ranges) != comm.size:
        raise ValueError("owner ranges must contain one interval per MPI rank")
    ranked_ranges = sorted(
        enumerate(ranges), key=lambda item: (item[1][0], item[1][1], item[0])
    )
    ordered = [value for _rank, value in ranked_ranges]
    if (
        not ordered
        or ordered[0][0] != 0
        or any(right[0] != left[1] for left, right in zip(ordered, ordered[1:]))
        or any(last < first for first, last in ordered)
    ):
        raise ValueError("owner ranges must be contiguous")
    inferred_size = ordered[-1][1]
    if global_size is None:
        global_size = inferred_size
    if int(global_size) != inferred_size:
        raise ValueError("owner ranges do not cover the declared global size")

    raw = np.asarray(local_group_pairs)
    if raw.size == 0:
        raw = np.empty((0, 2), dtype=np.int64)
    if raw.ndim != 2 or raw.shape[1] != 2:
        raise ValueError("group pairs must have shape (count, 2)")
    if not np.issubdtype(raw.dtype, np.integer):
        raise TypeError("group pairs must contain integer row identities")
    pairs = [(int(row), int(group)) for row, group in raw.tolist()]
    send: list[list[tuple[int, int]]] = [[] for _ in range(comm.size)]
    starts = [first for _rank, (first, _last) in ranked_ranges]
    for row, group in pairs:
        if row < 0 or row >= int(global_size):
            raise ValueError("group pair row is outside the global ownership span")
        if group not in (0, 1, 2):
            raise ValueError("group pair group must be 0, 1, or 2")
        owner_index = bisect_right(starts, row) - 1
        if owner_index < 0:
            raise ValueError("group pair has no unique PETSc row owner")
        owner_rank, owner_range = ranked_ranges[owner_index]
        if not (owner_range[0] <= row < owner_range[1]):
            raise ValueError("group pair has no unique PETSc row owner")
        send[owner_rank].append((row, group))

    received = comm.alltoall(send)
    received_pairs = [pair for packet in received for pair in packet]
    unique_pairs = set(received_pairs)
    result = tuple(
        np.asarray(
            sorted(row for row, group in unique_pairs if group == index),
            dtype=PETSc.IntType,
        )
        for index in range(3)
    )
    first, last = ranges[comm.rank]
    if any(np.any((rows < first) | (rows >= last)) for rows in result):
        raise RuntimeError("owner routing returned a non-local group row")

    local_hashes = tuple(_int_array_sha256(rows) for rows in result)
    hash_by_group = tuple(comm.allgather(local_hashes))
    audit = {
        "global_size": int(global_size),
        "ownership_ranges": [list(value) for value in ranges],
        "input_pair_count_local": len(pairs),
        "routed_pair_count_local": len(received_pairs),
        "duplicate_pair_count_local": len(received_pairs) - len(unique_pairs),
        "owner_local": True,
        "numeric_allgather": False,
        "groups": [
            {
                "local_row_count": int(rows.size),
                "local_row_sha256": local_hashes[index],
                "all_rank_local_row_sha256": [
                    hashes[index] for hashes in hash_by_group
                ],
            }
            for index, rows in enumerate(result)
        ],
    }
    return result, audit


def build_v6_cell_recovery_group_pairs(
    cell_recovery_maps: Sequence[Any],
    geometry: Any,
    z_values: Sequence[float],
    expansion_by_original: Mapping[int, Any],
    *,
    global_size: int,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Build sparse local ``(active_row, group)`` pairs for V6.

    Each rank examines only its incident cell recovery maps.  A shared trace
    row can consequently be reported by more than one rank; the subsequent
    owner router is responsible for sending it to its unique PETSc row owner
    and removing duplicates.  This path deliberately never creates a
    ``(3, global_size)`` boolean mask or gathers numeric row values.
    """

    z_axis = np.asarray(z_values, dtype=np.float64)
    local_pairs: list[tuple[int, int]] = []
    local_error: str | None = None
    try:
        if z_axis.shape != (7,) or np.any(np.diff(z_axis) <= 0.0):
            raise ValueError("V6 cell recovery requires six ordered z layers")
        coordinates = np.asarray(geometry.x, dtype=np.float64)
        cell_dofmap = geometry.dofmap
        if len(cell_recovery_maps) > len(cell_dofmap):
            raise ValueError("owned cell recovery maps exceed geometry cells")
        for cell, recovery in enumerate(cell_recovery_maps):
            geometry_indices = np.asarray(cell_dofmap[cell], dtype=np.int64)
            if geometry_indices.size == 0:
                raise ValueError("V6 cell recovery encountered an empty cell")
            centroid_z = float(np.mean(coordinates[geometry_indices, 2]))
            layer = int(np.searchsorted(z_axis, centroid_z, side="right") - 1)
            if layer < 0 or layer >= 6:
                raise ValueError(
                    f"V6 cell recovery layer {layer} is outside z partition"
                )
            group = layer // 2
            for original in recovery.trace_original_dofs:
                expansion = expansion_by_original.get(int(original))
                if expansion is None:
                    raise ValueError(
                        f"V6 trace row {int(original)} has no active expansion"
                    )
                active_ids, coefficients = expansion
                for active, coefficient in zip(active_ids, coefficients, strict=True):
                    if coefficient == 0:
                        continue
                    active = int(active)
                    if active < 0 or active >= int(global_size):
                        raise ValueError(
                            f"V6 active expansion row {active} is outside matrix"
                        )
                    local_pairs.append((active, group))
    except Exception as exc:
        local_error = f"{type(exc).__name__}: {exc}"

    errors = comm.allgather(local_error)
    if any(error is not None for error in errors):
        raise ValueError(
            "V6 sparse cell-recovery pair construction failed: "
            + next(error for error in errors if error is not None)
        )
    pairs = np.asarray(local_pairs, dtype=np.int64)
    if pairs.size == 0:
        pairs = np.empty((0, 2), dtype=np.int64)
    return pairs, {
        "schema": "task040.v6_2.cell_recovery_sparse_pairs.v1",
        "input_scope": "local_incident_cells",
        "local_cell_count": int(len(cell_recovery_maps)),
        "owned_cell_prefix": True,
        "ghost_geometry_cells_ignored": int(len(cell_dofmap) - len(cell_recovery_maps)),
        "local_pair_count": int(len(local_pairs)),
        "global_pair_count_before_owner_dedup": int(
            sum(comm.allgather(len(local_pairs)))
        ),
        "mapping_source": (
            "cell_recovery_maps + trace_constraints.expansion_by_original "
            "+ local_mesh.geometry.z_values"
        ),
        "global_boolean_mask_allocated": False,
        "fe_numeric_allgather": False,
        "numeric_allgather": False,
        "owner_routing_required": True,
    }


def build_v6_cell_recovery_owner_group_rows(
    system: Any,
    matrix: PETSc.Mat,
    *,
    comm: MPI.Intracomm | None = None,
) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], dict[str, Any]]:
    """Build V6 owner-local group rows without a FE-sized boolean mask."""

    matrix_comm = matrix.getComm().tompi4py()
    if comm is None:
        comm = matrix_comm
    if comm.size != matrix_comm.size or comm.rank != matrix_comm.rank:
        raise ValueError("V6 row-builder communicator does not match the matrix")
    condensed = system.static_condensation.condensed
    geometry = system.local_mesh.mesh.geometry
    pairs, pair_audit = build_v6_cell_recovery_group_pairs(
        condensed.cell_recovery_maps,
        geometry,
        system.local_mesh.z_values,
        condensed.trace_constraints.expansion_by_original,
        global_size=int(matrix.getSize()[0]),
        comm=comm,
    )
    ownership_ranges = comm.allgather(matrix.getOwnershipRange())
    rows, routing_audit = build_owner_local_group_rows(
        pairs,
        ownership_ranges,
        comm=comm,
        global_size=int(matrix.getSize()[0]),
    )
    return rows, {
        **pair_audit,
        "schema": "task040.v6_2.cell_recovery_owner_rows.v1",
        "mapping_source": "v6_sparse_pairs_alltoall_owner_dedup",
        "owner_rows_local": [int(values.size) for values in rows],
        "routing": routing_audit,
    }


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
        self._additional_action_counts: dict[str, int] = {}
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

    def project_additional_action(
        self,
        action: Callable[[PETSc.Vec, PETSc.Vec], None],
        *,
        name: str,
        semantic: str,
    ) -> dict[str, Any]:
        """Project one extra distributed action on the retained owner basis.

        This is a narrow producer-only hook for a small Petrov matrix such as
        ``Y1^H [oracle.apply_group(1)] Z1``.  It reuses one source and target
        Vec for all columns and only allreduces the resulting small matrix;
        no FE-sized numeric data or normal equations are introduced.
        """

        if self._destroyed:
            raise RuntimeError("distributed Petrov action is destroyed")
        if not callable(action):
            raise TypeError("additional Petrov action must be callable")
        projected_local = np.empty(
            (self.span_size, self.span_size), dtype=np.complex128
        )
        local_y_h = self._local_y.conj().T
        source = self._template.duplicate()
        target = self._template.duplicate()
        apply_count = 0
        try:
            for column in range(self.span_size):
                source.array[:] = np.asarray(
                    self._local_z[:, column], dtype=PETSc.ScalarType
                )
                source.assemble()
                target.set(0.0)
                action(source, target)
                target.assemble()
                target_local = np.asarray(target.array, dtype=np.complex128)
                projected_local[:, column] = local_y_h @ target_local
                apply_count += 1
        finally:
            target.destroy()
            source.destroy()
        projected = self._allreduce_small(projected_local)
        if not np.isfinite(projected).all():
            raise ValueError(f"additional Petrov projection {name} is nonfinite")
        self._additional_action_counts[name] = (
            self._additional_action_counts.get(name, 0) + apply_count
        )
        return {
            "name": str(name),
            "semantic": str(semantic),
            "projected": projected,
            "shape": [int(item) for item in projected.shape],
            "dtype": "complex128",
            "finite": True,
            **_small_svd_diagnostics(projected),
            "apply_count": int(apply_count),
            "total_apply_count": int(self._additional_action_counts[name]),
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
        self._local_z = np.empty((0, 0), dtype=np.complex128)
        v_adjoint = self._solve_gram(self._local_y.conj().T)
        np.conjugate(v_adjoint.T, out=self._local_y)
        del v_adjoint
        factors = {
            "U": self._delta_local,
            "V": self._local_y,
            "G": self._gram,
            "projected_scalar": self._projected_scalar,
            "projected_exact": self._projected_exact,
        }
        self._template.destroy()
        self._scalar_apply = None
        self._exact_apply = None
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
                "additional_action_counts": dict(self._additional_action_counts),
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
            "additional_action_counts": dict(self._additional_action_counts),
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
