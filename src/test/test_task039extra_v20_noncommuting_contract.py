"""Selective V20 contract tests reused from the frozen ea717 V19 tests.

These are algebra/cache-identity checks only.  They do not build the formal
5 nm mesh, assemble a large matrix, or run an outer solve.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import CellRecoveryMap
from src.solvers.p6_cell_condensed_action import (
    P6CellCondensedAction,
    P6CellPortTerms,
    condense_physical_cell_blocks,
)


FROZEN_SOURCE = "ea717ed5c6ffe45214ecdeca80cabdaeaef5960b"


def _matrix(
    rng: np.random.Generator,
    rows: int,
    columns: int,
    diagonal: float = 0.0,
) -> np.ndarray:
    value = rng.normal(size=(rows, columns)) + 1j * rng.normal(size=(rows, columns))
    if rows == columns:
        value += diagonal * np.eye(rows)
    return value.astype(np.complex128)


@dataclass
class _FakeCondensed:
    blocks: tuple[dict[str, np.ndarray], ...]

    def __post_init__(self) -> None:
        self.matrix = None
        self.active_rows = 2
        self.appended_rows = 2
        self.full_rows = 4
        self.owned_active_rows = 2
        self.owned_appended_rows = 2
        self.comm = MPI.COMM_SELF
        trace = np.asarray([2, 3], dtype=PETSc.IntType)
        self.owned_trace_original_dofs = trace.copy()
        self.trace_constraints = SimpleNamespace(
            owned_active_original_dofs=trace.copy(),
            original_to_active={2: 0, 3: 1},
            expansion_by_original={
                2: (np.asarray([0], dtype=PETSc.IntType), np.asarray([1.0 + 0.0j])),
                3: (np.asarray([1], dtype=PETSc.IntType), np.asarray([1.0 + 0.0j])),
            },
        )
        self.cell_recovery_maps = tuple(
            CellRecoveryMap(
                interior_original_dofs=np.asarray([0, 1], dtype=PETSc.IntType),
                trace_original_dofs=trace.copy(),
                class_key=(index,),
            )
            for index, _block in enumerate(self.blocks)
        )
        self.interior_lu_by_class = {}
        self.interior_from_trace_by_class = {}
        self.trace_from_interior_rhs_by_class = {}
        self.retained_local_schur_by_class = {}
        for index, block in enumerate(self.blocks):
            from scipy.linalg import lu_factor, lu_solve

            factor = lu_factor(block["Vii"])
            xit = lu_solve(factor, block["Vit"])
            self.interior_lu_by_class[(index,)] = factor
            self.interior_from_trace_by_class[(index,)] = -xit
            self.trace_from_interior_rhs_by_class[(index,)] = -block["Vti"] @ lu_solve(
                factor, np.eye(2, dtype=np.complex128)
            )
            self.retained_local_schur_by_class[(index,)] = block["Vtt"] - block["Vti"] @ xit
        self.build_audit = {}

    def create_augmented_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createSeq(self.active_rows + self.appended_rows, comm=MPI.COMM_SELF)

    def destroy(self) -> None:
        self.matrix = None


def _problem() -> tuple[_FakeCondensed, dict[str, np.ndarray], P6CellCondensedAction]:
    rng = np.random.default_rng(20260914)
    block = {
        "Vii": _matrix(rng, 2, 2, 5.0),
        "Vit": _matrix(rng, 2, 2),
        "Vti": _matrix(rng, 2, 2),
        "Vtt": _matrix(rng, 2, 2, 3.0),
        "Bi": _matrix(rng, 2, 2),
        "Bt": _matrix(rng, 2, 2),
        "Di": _matrix(rng, 2, 2),
        "Dt": _matrix(rng, 2, 2),
        "H": _matrix(rng, 2, 2, 4.0),
    }
    condensed = _FakeCondensed((block,))
    terms = {
        0: P6CellPortTerms(
            block["Bi"], block["Di"], np.asarray([0, 1], dtype=PETSc.IntType),
            Bt=block["Bt"], Dt=block["Dt"], H=block["H"],
        )
    }
    action = P6CellCondensedAction(
        condensed,
        H_p=block["H"] * 0.0 + _matrix(rng, 2, 2, 6.0),
        port_terms=terms,
    )
    return condensed, block, action


def test_noncommuting_sum_adjoint_bilinear_repeat_and_input_immutability() -> None:
    rng = np.random.default_rng(3920)
    fields = []
    for seed in (1, 2):
        local = np.random.default_rng(seed)
        fields.append({
            name: _matrix(local, rows, columns, diagonal)
            for name, rows, columns, diagonal in (
                ("Vii", 2, 2, 5.0), ("Vit", 2, 2, 0.0),
                ("Vti", 2, 2, 0.0), ("Vtt", 2, 2, 3.0),
                ("Bi", 2, 2, 0.0), ("Bt", 2, 2, 0.0),
                ("Di", 2, 2, 0.0), ("Dt", 2, 2, 0.0),
                ("H", 2, 2, 4.0),
            )
        })
    names = ("Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H")
    condensed_cells = [
        condense_physical_cell_blocks(*(field[name] for name in names))
        for field in fields
    ]
    combined = {name: fields[0][name] + fields[1][name] for name in fields[0]}
    combined_cell = condense_physical_cell_blocks(*(combined[name] for name in names))
    assert not np.allclose(
        combined_cell.S_V,
        condensed_cells[0].S_V + condensed_cells[1].S_V,
    )

    _condensed, block, action = _problem()
    hp = action.H_p
    inverse = np.linalg.inv(block["Vii"])
    reduced = np.block([
        [block["Vtt"] - block["Vti"] @ inverse @ block["Vit"],
         block["Bt"] - block["Vti"] @ inverse @ block["Bi"]],
        [-(block["Dt"] - block["Di"] @ inverse @ block["Vit"]),
         hp + block["Di"] @ inverse @ block["Bi"]],
    ])
    x = _matrix(rng, 4, 1)[:, 0]
    y = _matrix(rng, 4, 1)[:, 0]
    y_before = y.copy()
    inventory_before = dict(action.buffer_inventory)
    observed = action.apply(y)
    repeated = action.apply(y)
    np.testing.assert_array_equal(y, y_before)
    np.testing.assert_allclose(observed, repeated, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        np.vdot(x, observed),
        np.vdot(reduced.conj().T @ x, y),
        rtol=2e-12,
        atol=2e-12,
    )
    assert dict(action.buffer_inventory) == inventory_before
    action.destroy()


def test_fixed_p64_galerkin_then_condense_does_not_equal_trace_condense() -> None:
    A6 = np.asarray([
        [4.0 + 0.2j, 0.7 - 0.1j, 1.2 + 0.3j],
        [-0.4 + 0.5j, 3.3 - 0.2j, -0.8 + 0.4j],
        [0.6 - 0.7j, 1.1 + 0.2j, 2.4 + 0.6j],
    ], dtype=np.complex128)
    P64 = np.asarray([
        [1.0 + 0.1j, 0.0 + 0.0j],
        [0.25 - 0.2j, 0.0 + 0.0j],
        [0.0 + 0.0j, 1.0 + 0.0j],
    ], dtype=np.complex128)
    A4 = P64.conj().T @ A6 @ P64
    np.testing.assert_allclose(
        A4,
        np.asarray([[4.31225 + 0.026j, 0.95 + 0.12j],
                    [0.985 - 0.81j, 2.4 + 0.6j]], dtype=np.complex128),
        rtol=0.0,
        atol=2e-15,
    )
    S6 = A6[2:3, 2:3] - A6[2:3, :2] @ np.linalg.solve(A6[:2, :2], A6[:2, 2:3])
    S4 = A4[1:2, 1:2] - A4[1:2, :1] @ np.linalg.solve(A4[:1, :1], A4[:1, 1:2])
    restricted_fine_schur = P64[2:3, 1:2].conj().T @ S6 @ P64[2:3, 1:2]
    assert abs(complex(S4[0, 0] - restricted_fine_schur[0, 0])) > 1.0e-3
    np.testing.assert_allclose(S4, np.asarray([[2.16138079 + 0.75247356j]]), rtol=2e-8, atol=2e-8)
    np.testing.assert_allclose(
        restricted_fine_schur,
        np.asarray([[2.40110146 + 0.77955336j]]),
        rtol=2e-8,
        atol=2e-8,
    )
