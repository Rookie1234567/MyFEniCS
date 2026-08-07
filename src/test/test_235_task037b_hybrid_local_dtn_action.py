from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.coupling.hybrid_internal_modes import build_hybrid_internal_mode_coupling
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.solvers.condensed_dtn import (
    build_explicit_condensed_operator,
    condensed_rhs,
    extract_petsc_condensed_blocks,
    recover_petsc_auxiliary,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    internal_modal_rhs_correction,
)
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
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


class TestTask037bHybridLocalDtnAction:
    @classmethod
    def setup_class(cls):
        cls.cfg = replace(
            target_stage4_config(degree=2, h_nm=10.0),
            matrix_diagnostics_assemble_unconstrained=False,
            matrix_diagnostics_assemble_only=False,
            matrix_diagnostics_factorization_only=False,
            stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        )
        cls.direct = {}
        cls.action = {}
        cls.reference_blocks = {}
        cls.reference_matrices = {}
        cls.reference_ports = {}
        cls.reference_rhs = {}
        cls.mode_vectors = []
        for side in ("bottom", "top"):
            direct = assemble_hybrid_local_dtn_system(cls.cfg, side)
            action = assemble_hybrid_local_dtn_action_system(cls.cfg, side)
            blocks = extract_petsc_condensed_blocks(
                direct.A,
                direct.b,
                n_fe=direct.n_fe,
                n_aux=direct.n_external_aux,
            )
            reference, port = build_explicit_condensed_operator(blocks)
            cls.direct[side] = direct
            cls.action[side] = action
            cls.reference_blocks[side] = blocks
            cls.reference_matrices[side] = reference
            cls.reference_ports[side] = port
            cls.reference_rhs[side] = condensed_rhs(blocks)

        cls.spaces = build_cross_section_spaces(
            build_matching_cross_section(cls.cfg, "stage4_xy"),
            transverse_degree=2,
        )
        target = np.sqrt(
            (cls.cfg.k0 * complex(cls.cfg.n_air)) ** 2
            - cls.cfg.kx**2
            - cls.cfg.ky**2
            + 0.0j
        )

        def synthetic_mode(component: int, beta: complex, direction: str):
            trace = fem.Function(cls.spaces.transverse)

            def field(x):
                phase = np.exp(1j * (cls.cfg.kx * x[0] + cls.cfg.ky * x[1]))
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
        cls.oracle_systems = {}
        for side in ("bottom", "top"):
            direct = cls.direct[side]
            cls.oracle_systems[side] = SimpleNamespace(
                side=side,
                cfg=cls.cfg,
                local_mesh=direct.local_mesh,
                V=direct.V,
                floquet_data=direct.floquet_data,
                A=cls.reference_matrices[side],
                b=cls.reference_rhs[side],
                global_size=direct.n_fe,
                n_external_aux=0,
                static_condensation=direct.static_condensation,
                assembly_backend_actual=direct.assembly_backend_actual,
            )
        cls.action_coupling = build_hybrid_internal_mode_coupling(
            cls.cfg,
            cls.spaces,
            cls.positive,
            cls.negative,
            cls.action["bottom"],
            cls.action["top"],
        )
        cls.oracle_action, cls.oracle_context = create_hybrid_assembled_block_action(
            cls.oracle_systems["bottom"],
            cls.oracle_systems["top"],
            cls.action_coupling,
        )
        cls.global_action, cls.global_context = create_hybrid_assembled_block_action(
            cls.action["bottom"],
            cls.action["top"],
            cls.action_coupling,
        )

    @classmethod
    def teardown_class(cls):
        cls.global_action.destroy()
        cls.global_context.destroy()
        cls.oracle_action.destroy()
        cls.oracle_context.destroy()
        cls.action_coupling.destroy()
        for side in ("bottom", "top"):
            cls.reference_rhs[side].destroy()
            cls.reference_matrices[side].destroy()
            cls.reference_ports[side].destroy()
            cls.reference_blocks[side].destroy()
            cls.action[side].destroy()
            cls.direct[side].destroy()
        for vector in cls.mode_vectors:
            vector.destroy()

    def test_action_only_inventory_and_three_active_probes(self):
        for side in ("bottom", "top"):
            direct = self.direct[side]
            candidate = self.action[side]
            reference = self.reference_matrices[side]
            reference_blocks = self.reference_blocks[side]

            assert candidate.A.getType() == "python"
            assert candidate.A.getSize() == (direct.n_fe, direct.n_fe)
            assert candidate.global_size == direct.n_fe
            assert candidate.n_external_aux == 0
            assert candidate.inventory["global_A_materialized"] is False
            assert candidate.inventory["global_F_materialized"] is False
            assert candidate.inventory["bottom_global_F_materialized"] is False
            assert candidate.inventory["top_global_F_materialized"] is False
            assert candidate.inventory["explicit_external_c_matrix_count"] == 0
            assert candidate.inventory["explicit_external_d_matrix_count"] == 0
            assert candidate.inventory["direct_factor_count"] == 0
            assert candidate.inventory["external_mode_count"] == len(
                candidate.external_modes
            )
            assert candidate.inventory["external_auxiliary_rows_in_krylov"] == 0
            assert candidate.inventory["bottom_global_F_materialized"] is False
            assert candidate.inventory["top_global_F_materialized"] is False
            assert candidate.blocks.F is None
            assert candidate.blocks.C.getType() == "python"
            assert candidate.blocks.D.getType() == "python"
            assert reference_blocks.F.getType() != "python"
            assert reference_blocks.C.getType() != "python"
            assert reference_blocks.D.getType() != "python"

            rhs_error = _relative_vector_error(candidate.b, self.reference_rhs[side])
            assert rhs_error <= 1.0e-11, f"{side} condensed RHS error={rhs_error:.3e}"
            if MPI.COMM_WORLD.rank == 0:
                print(f"H2b-L {side} rhs={rhs_error:.3e}", flush=True)

            for probe_index, seed in enumerate((101, 211, 307)):
                actual_source = candidate.A.createVecRight()
                reference_source = reference.createVecRight()
                _fill_global_vector(actual_source, seed)
                actual_source.copy(reference_source)
                actual_target = candidate.A.createVecLeft()
                reference_target = reference.createVecLeft()
                candidate.A.mult(actual_source, actual_target)
                reference.mult(reference_source, reference_target)
                action_error = _relative_vector_error(
                    actual_target,
                    reference_target,
                )
                actual_aux = recover_petsc_auxiliary(
                    candidate.blocks,
                    actual_source,
                )
                reference_aux = recover_petsc_auxiliary(
                    reference_blocks,
                    reference_source,
                )
                recovery_error = _relative_vector_error(actual_aux, reference_aux)
                if MPI.COMM_WORLD.rank == 0:
                    print(
                        f"H2b-L {side} probe={probe_index} "
                        f"action={action_error:.3e} recovery={recovery_error:.3e}",
                        flush=True,
                    )
                try:
                    assert action_error <= 1.0e-11
                    assert recovery_error <= 1.0e-11
                finally:
                    reference_aux.destroy()
                    actual_aux.destroy()
                    reference_target.destroy()
                    actual_target.destroy()
                    reference_source.destroy()
                    actual_source.destroy()

    def _assert_global_action(self, source: PETSc.Vec, label: str):
        expected = self.oracle_action.createVecLeft()
        actual = self.global_action.createVecLeft()
        self.oracle_action.mult(source, expected)
        self.global_action.mult(source, actual)
        expected_bottom, expected_top, expected_modal = (
            self.oracle_context.layout.split(
                expected,
                self.oracle_systems["bottom"].b,
                self.oracle_systems["top"].b,
            )
        )
        actual_bottom, actual_top, actual_modal = self.global_context.layout.split(
            actual,
            self.action["bottom"].b,
            self.action["top"].b,
        )
        errors = {
            "global": _relative_vector_error(actual, expected),
            "bottom": _relative_vector_error(actual_bottom, expected_bottom),
            "top": _relative_vector_error(actual_top, expected_top),
            "modal": float(
                np.linalg.norm(actual_modal - expected_modal)
                / max(np.linalg.norm(expected_modal), 1.0e-30)
            ),
        }
        if MPI.COMM_WORLD.rank == 0:
            print(f"H2b-G {label} errors={errors}", flush=True)
        try:
            for error in errors.values():
                assert error <= 1.0e-11
        finally:
            actual_bottom.destroy()
            actual_top.destroy()
            expected_bottom.destroy()
            expected_top.destroy()
            actual.destroy()
            expected.destroy()

    def test_global_seven_probes_and_mapping(self):
        layout = self.global_context.layout
        oracle_layout = self.oracle_context.layout
        assert layout.global_size == oracle_layout.global_size
        assert layout.bottom_ranges == oracle_layout.bottom_ranges
        assert layout.top_ranges == oracle_layout.top_ranges
        mapped = np.concatenate(
            (
                layout.map_bottom(np.arange(self.action["bottom"].global_size)),
                layout.map_top(np.arange(self.action["top"].global_size)),
                layout.map_modal(np.arange(layout.modal_count)),
            )
        )
        missing = np.setdiff1d(np.arange(layout.global_size), mapped).size
        extra = np.setdiff1d(mapped, np.arange(layout.global_size)).size
        duplicates = mapped.size - np.unique(mapped).size
        assert missing == 0
        assert extra == 0
        assert duplicates == 0
        assert self.global_context.inventory["bottom_A_assembled"] is False
        assert self.global_context.inventory["top_A_assembled"] is False
        assert self.global_context.inventory["bottom_global_F_materialized"] is False
        assert self.global_context.inventory["top_global_F_materialized"] is False
        assert (
            self.global_context.inventory["bottom_explicit_external_c_matrix_count"]
            == 0
        )
        assert (
            self.global_context.inventory["bottom_explicit_external_d_matrix_count"]
            == 0
        )
        assert (
            self.global_context.inventory["top_explicit_external_c_matrix_count"] == 0
        )
        assert (
            self.global_context.inventory["top_explicit_external_d_matrix_count"] == 0
        )
        assert self.global_context.inventory["explicit_external_c_matrix_count"] == 0
        assert self.global_context.inventory["explicit_external_d_matrix_count"] == 0
        assert self.global_context.inventory["p6_direct_factor_count"] == 0
        assert self.oracle_context.inventory["bottom_A_assembled"] is True
        assert self.oracle_context.inventory["top_A_assembled"] is True
        if MPI.COMM_WORLD.rank == 0:
            print(
                f"H2b-G mapping missing={missing} extra={extra} "
                f"duplicates={duplicates}",
                flush=True,
            )

        roundtrip_bottom = self.action["bottom"].A.createVecRight()
        roundtrip_top = self.action["top"].A.createVecRight()
        _fill_global_vector(roundtrip_bottom, 41)
        _fill_global_vector(roundtrip_top, 43)
        roundtrip_modal = np.arange(layout.modal_count, dtype=np.complex128) + 1j
        packed = layout.pack(roundtrip_bottom, roundtrip_top, roundtrip_modal)
        split_bottom, split_top, split_modal = layout.split(
            packed,
            roundtrip_bottom,
            roundtrip_top,
        )
        pack_errors = {
            "bottom": _relative_vector_error(split_bottom, roundtrip_bottom),
            "top": _relative_vector_error(split_top, roundtrip_top),
            "modal": float(
                np.linalg.norm(split_modal - roundtrip_modal)
                / max(np.linalg.norm(roundtrip_modal), 1.0e-30)
            ),
        }
        if MPI.COMM_WORLD.rank == 0:
            print(f"H2b-G pack_split={pack_errors}", flush=True)
        try:
            for error in pack_errors.values():
                assert error <= 1.0e-13
        finally:
            split_bottom.destroy()
            split_top.destroy()
            packed.destroy()
            roundtrip_bottom.destroy()
            roundtrip_top.destroy()

        for seed in (5, 17, 29):
            bottom = self.action["bottom"].A.createVecRight()
            top = self.action["top"].A.createVecRight()
            _fill_global_vector(bottom, seed)
            _fill_global_vector(top, seed + 1)
            modal = np.random.default_rng(seed + 100).standard_normal(
                layout.modal_count
            ) + 1j * np.random.default_rng(seed + 101).standard_normal(
                layout.modal_count
            )
            source = layout.pack(bottom, top, modal)
            try:
                self._assert_global_action(source, f"random_{seed}")
            finally:
                source.destroy()
                bottom.destroy()
                top.destroy()

        bottom_rhs = self.action["bottom"].b
        top_rhs = self.action["top"].b
        source = layout.pack(
            bottom_rhs,
            top_rhs,
            internal_modal_rhs_correction(self.action_coupling),
        )
        try:
            self._assert_global_action(source, "physical_packed_rhs")
        finally:
            source.destroy()
        for label, bottom_on, top_on, modal_on in (
            ("bottom_only", True, False, False),
            ("top_only", False, True, False),
            ("modal_only", False, False, True),
        ):
            bottom = self.action["bottom"].A.createVecRight()
            top = self.action["top"].A.createVecRight()
            if bottom_on:
                _fill_global_vector(bottom, 71)
            else:
                bottom.set(0.0)
            if top_on:
                _fill_global_vector(top, 73)
            else:
                top.set(0.0)
            modal = (
                np.ones(layout.modal_count, dtype=np.complex128)
                if modal_on
                else np.zeros(layout.modal_count, dtype=np.complex128)
            )
            source = layout.pack(bottom, top, modal)
            try:
                self._assert_global_action(source, label)
            finally:
                source.destroy()
                bottom.destroy()
                top.destroy()
