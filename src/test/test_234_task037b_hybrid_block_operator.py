from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.coupling.hybrid_internal_modes import build_hybrid_internal_mode_coupling
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    build_hybrid_augmented_direct_system,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system


def _relative_vector_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    actual.copy(difference)
    difference.axpy(PETSc.ScalarType(-1.0), expected)
    try:
        return float(difference.norm() / max(expected.norm(), 1.0e-30))
    finally:
        difference.destroy()


def _relative_array_error(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(
        np.linalg.norm(np.asarray(actual) - np.asarray(expected))
        / max(np.linalg.norm(np.asarray(expected)), 1.0e-30)
    )


def _fill_vector(vector: PETSc.Vec, seed: int) -> None:
    rng = np.random.default_rng(seed)
    values = rng.standard_normal(vector.getSize())
    values = values + 1j * rng.standard_normal(vector.getSize())
    first, last = (int(value) for value in vector.getOwnershipRange())
    vector.getArray()[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)


class TestTask037bHybridBlockOperator:
    @classmethod
    def setup_class(cls):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cls.cfg = cfg
        cross_section = build_matching_cross_section(cfg, "stage4_xy")
        cls.spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        target = np.sqrt(
            (cfg.k0 * complex(cfg.n_air)) ** 2 - cfg.kx**2 - cfg.ky**2 + 0.0j
        )
        cls.mode_vectors = []

        def synthetic_mode(component: int, beta: complex, direction: str):
            trace = fem.Function(cls.spaces.transverse)

            def field(x):
                phase = np.exp(1j * (cfg.kx * x[0] + cfg.ky * x[1]))
                values = np.zeros((2, x.shape[1]), dtype=PETSc.ScalarType)
                values[component, :] = phase
                return values

            trace.interpolate(field)
            trace.x.scatter_forward()
            mixed = fem.Function(cls.spaces.mixed)
            mixed.x.array[:] = 0.0
            mixed.x.array[cls.spaces.transverse_to_mixed] = trace.x.array
            mixed.x.scatter_forward()
            vector = mixed.x.petsc_vec.duplicate()
            mixed.x.petsc_vec.copy(vector)
            cls.mode_vectors.append(vector)
            return SimpleNamespace(
                beta=complex(beta),
                right=SimpleNamespace(right_full=vector),
                left_full=vector,
                direction=direction,
                passive_branch_valid=True,
            )

        cls.positive = SimpleNamespace(
            modes=[
                synthetic_mode(0, target, "forward"),
                synthetic_mode(1, target, "forward"),
            ]
        )
        cls.negative = SimpleNamespace(
            modes=[
                synthetic_mode(0, -target, "backward"),
                synthetic_mode(1, -target, "backward"),
            ]
        )
        cls.bottom_system = assemble_hybrid_local_dtn_system(cfg, "bottom")
        cls.top_system = assemble_hybrid_local_dtn_system(cfg, "top")
        cls.coupling = build_hybrid_internal_mode_coupling(
            cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            cls.bottom_system,
            cls.top_system,
        )
        cls.direct = build_hybrid_augmented_direct_system(
            cls.bottom_system,
            cls.top_system,
            cls.coupling,
        )
        cls.action, cls.context = create_hybrid_assembled_block_action(
            cls.bottom_system,
            cls.top_system,
            cls.coupling,
        )

    @classmethod
    def teardown_class(cls):
        cls.action.destroy()
        cls.context.destroy()
        cls.direct.destroy()
        cls.coupling.destroy()
        cls.bottom_system.destroy()
        cls.top_system.destroy()
        for vector in cls.mode_vectors:
            vector.destroy()

    def _packed_seed(self, seed: int, *, bottom=True, top=True, modal=True):
        bottom_vector = self.bottom_system.A.createVecRight()
        top_vector = self.top_system.A.createVecRight()
        if bottom:
            _fill_vector(bottom_vector, seed)
        else:
            bottom_vector.set(0.0)
        if top:
            _fill_vector(top_vector, seed + 4)
        else:
            top_vector.set(0.0)
        if modal:
            modal_rng = np.random.default_rng(seed + 101)
            modal_values = modal_rng.standard_normal(self.context.layout.modal_count)
            modal_values = modal_values + 1j * modal_rng.standard_normal(
                self.context.layout.modal_count
            )
        else:
            modal_values = np.zeros(
                self.context.layout.modal_count, dtype=np.complex128
            )
        packed = self.context.layout.pack(bottom_vector, top_vector, modal_values)
        bottom_vector.destroy()
        top_vector.destroy()
        return packed

    def _assert_action(self, source: PETSc.Vec, label: str) -> dict[str, float]:
        expected = self.direct.A.createVecLeft()
        actual = self.action.createVecLeft()
        self.direct.A.mult(source, expected)
        self.action.mult(source, actual)
        expected_bottom, expected_top, expected_modal = self.context.layout.split(
            expected,
            self.bottom_system.b,
            self.top_system.b,
        )
        actual_bottom, actual_top, actual_modal = self.context.layout.split(
            actual,
            self.bottom_system.b,
            self.top_system.b,
        )
        try:
            errors = {
                "global": _relative_vector_error(actual, expected),
                "bottom": _relative_vector_error(actual_bottom, expected_bottom),
                "top": _relative_vector_error(actual_top, expected_top),
                "modal": _relative_array_error(actual_modal, expected_modal),
            }
            if MPI.COMM_WORLD.rank == 0:
                print(f"H2a {label}: {errors}", flush=True)
            for name, error in errors.items():
                assert error <= 1.0e-11, f"{label} {name} error={error:.3e}"
            return errors
        finally:
            expected_bottom.destroy()
            expected_top.destroy()
            actual_bottom.destroy()
            actual_top.destroy()
            expected.destroy()
            actual.destroy()

    def test_inventory_mapping_and_pack_split(self):
        assert self.action.getType() == "python"
        assert self.context.inventory == {
            "matrix_type": "python",
            "matrix_free": True,
            "global_A_materialized": False,
            "bottom_A_assembled": True,
            "top_A_assembled": True,
            "global_size": self.context.layout.global_size,
            "local_size": self.context.layout.local_size,
            "modal_count": self.context.layout.modal_count,
        }
        mapped = np.concatenate(
            (
                self.context.layout.map_bottom(
                    np.arange(self.bottom_system.global_size)
                ),
                self.context.layout.map_top(np.arange(self.top_system.global_size)),
                self.context.layout.map_modal(
                    np.arange(self.context.layout.modal_count)
                ),
            )
        )
        expected_rows = np.arange(self.context.layout.global_size)
        missing = np.setdiff1d(expected_rows, mapped).size
        extra = np.setdiff1d(mapped, expected_rows).size
        duplicates = mapped.size - np.unique(mapped).size
        assert missing == 0
        assert extra == 0
        assert duplicates == 0
        assert np.array_equal(
            np.sort(mapped), np.arange(self.context.layout.global_size)
        )
        for projection in (
            self.coupling.bottom.projection,
            self.coupling.top.projection,
        ):
            ranges = MPI.COMM_WORLD.allgather(
                tuple(int(value) for value in projection.getOwnershipRange())
            )
            assert ranges[:-1] == [(0, 0)] * (MPI.COMM_WORLD.size - 1)
            assert ranges[-1] == (0, self.context.mode_count)
        bottom = self.bottom_system.A.createVecRight()
        top = self.top_system.A.createVecRight()
        _fill_vector(bottom, 13)
        _fill_vector(top, 17)
        modal = np.arange(self.context.layout.modal_count) + 1j
        packed = self.context.layout.pack(bottom, top, modal)
        split_bottom, split_top, split_modal = self.context.layout.split(
            packed, bottom, top
        )
        try:
            pack_errors = {
                "bottom": _relative_vector_error(split_bottom, bottom),
                "top": _relative_vector_error(split_top, top),
                "modal": _relative_array_error(split_modal, modal),
            }
            if MPI.COMM_WORLD.rank == 0:
                print(
                    f"H2a mapping: missing={missing} extra={extra} "
                    f"duplicates={duplicates}; pack_split={pack_errors}",
                    flush=True,
                )
            assert pack_errors["bottom"] <= 1.0e-13
            assert pack_errors["top"] <= 1.0e-13
            assert pack_errors["modal"] <= 1.0e-13
        finally:
            split_bottom.destroy()
            split_top.destroy()
            packed.destroy()
            bottom.destroy()
            top.destroy()

    def test_three_random_rhs_and_block_probes_match_direct_oracle(self):
        for seed in range(3):
            source = self._packed_seed(seed)
            try:
                self._assert_action(source, f"random_{seed}")
            finally:
                source.destroy()
        source = self.direct.b.copy()
        try:
            self._assert_action(source, "physical_packed_rhs")
        finally:
            source.destroy()
        for label, kwargs in (
            ("bottom_only", {"bottom": True, "top": False, "modal": False}),
            ("top_only", {"bottom": False, "top": True, "modal": False}),
            ("modal_only", {"bottom": False, "top": False, "modal": True}),
        ):
            source = self._packed_seed(23, **kwargs)
            try:
                self._assert_action(source, label)
            finally:
                source.destroy()

    def test_context_destroy_is_repeatable(self):
        action, context = create_hybrid_assembled_block_action(
            self.bottom_system,
            self.top_system,
            self.coupling,
        )
        action.destroy()
        context.destroy()
        context.destroy()
