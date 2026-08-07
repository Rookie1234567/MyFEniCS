from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from petsc4py import PETSc

from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    create_exact_block_ldu_preconditioner,
    solve_exact_block_ldu,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    internal_modal_rhs_correction,
)
from src.test.test_235_task037b_hybrid_local_dtn_action import (
    TestTask037bHybridLocalDtnAction as _H2bActionFixture,
)


def _fill_global_vector(vector: PETSc.Vec, seed: int) -> None:
    rng = np.random.default_rng(seed)
    values = rng.standard_normal(vector.getSize()) + 1j * rng.standard_normal(
        vector.getSize()
    )
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


def _relative_vector_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm() / max(float(expected.norm()), 1.0e-30))
    finally:
        difference.destroy()


class TestTask037bHybridBlockLdu:
    @classmethod
    def setup_class(cls):
        fixture = _H2bActionFixture
        fixture.setup_class()
        cls.fixture = fixture
        cls.layout = fixture.global_context.layout
        cls.operator = fixture.global_action
        cls.coupling = fixture.action_coupling
        cls.oracle_systems = {}
        for side in ("bottom", "top"):
            original = fixture.oracle_systems[side]
            cls.oracle_systems[side] = SimpleNamespace(
                side=original.side,
                cfg=original.cfg,
                local_mesh=original.local_mesh,
                V=original.V,
                floquet_data=original.floquet_data,
                A=original.A,
                b=original.b,
                global_size=original.global_size,
                static_condensation=None,
            )
        cls.preconditioner = create_exact_block_ldu_preconditioner(
            cls.layout,
            cls.oracle_systems["bottom"],
            cls.oracle_systems["top"],
            cls.coupling,
        )
        cls.rhs = cls.layout.pack(
            fixture.action["bottom"].b,
            fixture.action["top"].b,
            internal_modal_rhs_correction(cls.coupling),
        )

    @classmethod
    def teardown_class(cls):
        cls.rhs.destroy()
        cls.preconditioner.destroy()
        assert cls.preconditioner.factors_released
        cls.fixture.teardown_class()

    def _split_errors(self, actual: PETSc.Vec, expected: PETSc.Vec) -> dict[str, float]:
        actual_bottom, actual_top, actual_modal = self.layout.split(
            actual,
            self.fixture.action["bottom"].b,
            self.fixture.action["top"].b,
        )
        expected_bottom, expected_top, expected_modal = self.layout.split(
            expected,
            self.fixture.action["bottom"].b,
            self.fixture.action["top"].b,
        )
        try:
            return {
                "global": _relative_vector_error(actual, expected),
                "bottom": _relative_vector_error(actual_bottom, expected_bottom),
                "top": _relative_vector_error(actual_top, expected_top),
                "modal": float(
                    np.linalg.norm(actual_modal - expected_modal)
                    / max(np.linalg.norm(expected_modal), 1.0e-30)
                ),
            }
        finally:
            actual_bottom.destroy()
            actual_top.destroy()
            expected_bottom.destroy()
            expected_top.destroy()

    def test_exact_block_ldu_inverse_identity(self):
        assert self.preconditioner.inventory["global_A_materialized"] is False
        assert self.preconditioner.inventory["oracle_local_direct_factor_count"] == 2
        for seed in (13, 29, 41):
            source = self.operator.createVecRight()
            preconditioned = self.operator.createVecLeft()
            action = self.operator.createVecLeft()
            _fill_global_vector(source, seed)
            try:
                self.preconditioner.apply(None, source, preconditioned)
                self.operator.mult(preconditioned, action)
                errors = self._split_errors(action, source)
                if self.layout.comm.rank == 0:
                    print(f"H3 exact_pc seed={seed} errors={errors}", flush=True)
                assert max(errors.values()) <= 1.0e-11
            finally:
                action.destroy()
                preconditioned.destroy()
                source.destroy()

    def test_outer_fgmres_matches_direct_oracle(self):
        direct_system = build_hybrid_augmented_direct_system(
            self.oracle_systems["bottom"],
            self.oracle_systems["top"],
            self.coupling,
        )
        direct_solution = solve_hybrid_augmented_direct(
            direct_system,
            self.oracle_systems["bottom"],
            self.oracle_systems["top"],
        )
        result = solve_exact_block_ldu(self.operator, self.rhs, self.preconditioner)
        try:
            assert self.preconditioner.factors_released
            solution_error = _relative_vector_error(result.solution, direct_solution.x)
            _, _, candidate_modal = self.layout.split(
                result.solution,
                self.fixture.action["bottom"].b,
                self.fixture.action["top"].b,
            )
            _, _, direct_modal = self.layout.split(
                direct_solution.x,
                self.fixture.action["bottom"].b,
                self.fixture.action["top"].b,
            )
            modal_error = float(
                np.linalg.norm(candidate_modal - direct_modal)
                / max(np.linalg.norm(direct_modal), 1.0e-30)
            )
            if self.layout.comm.rank == 0:
                print(
                    "H3 solve "
                    f"iterations={result.iterations} reason={result.converged_reason} "
                    f"true={result.true_relative_residual:.3e} "
                    f"blocks={result.block_relative_residuals} "
                    f"solution={solution_error:.3e} modal={modal_error:.3e}",
                    flush=True,
                )
            assert result.iterations <= 3
            assert result.converged_reason > 0
            assert result.true_relative_residual <= 1.0e-10
            assert max(result.block_relative_residuals.values()) <= 1.0e-10
            assert solution_error <= 1.0e-10
            assert modal_error <= 1.0e-10
        finally:
            result.destroy()
            direct_solution.destroy()
            direct_system.destroy()
