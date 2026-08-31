"""Small independent authorities for the J3 two-form physical volume split."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_forms import _build_physical_volume_terms
from src.solvers.fullspace_lor_native_hx_fixture import (
    build_frozen_fullspace_primal_source,
    l2_source_formula,
)
from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
from src.solvers.fullspace_physical_action import FullspaceSplitVolumeAction
from src.test.stage2_test_utils import stage4_block_config


ORIGINAL_UFL_SOURCE_SHA = "99c85b1d1cc34e55ebfdb58323fed0b47d15c257"


def _fixture(tmp_path: Path, degree: int):
    cfg = replace(
        stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            divergence_penalty=0.0,
            mesh_target_size=50.0,
            mesh_cell_type="hexahedron",
            mesh_spacing_mode="boundary_fitted",
            mesh_axis_cell_counts=(4, 4, 3),
            stage4_dtn_order_policy="zero_order",
        ),
        nedelec_degree=degree,
        visualization_degree=degree,
    )
    mesh_data = build_airbox_mesh_3d(
        cfg, tmp_path / f"j3-oracle-mesh-p{degree}"
    )
    raw_space = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            degree,
            dtype=default_real_type,
        ),
    )
    floquet = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    return cfg, mesh_data, floquet


def _original_combined_physical_form(mesh_data, cfg, space):
    """Independent pre-J3 copy of the old combined isotropic UFL expression."""

    u = ufl.TrialFunction(space)
    v = ufl.TestFunction(space)
    dx = ufl.Measure(
        "dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags
    )
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    return sum(
        (
            PETSc.ScalarType(1.0 / cfg.mu_r)
            * ufl.inner(curl_u, curl_v)
            * dx(tag)
            - cfg.k0**2
            * PETSc.ScalarType(eps_r)
            * ufl.inner(u, v)
            * dx(tag)
        )
        for tag, eps_r in (
            (cfg.tags.air, cfg.eps_r),
            (cfg.tags.substrate, cfg.substrate_index**2),
            (cfg.tags.grating, cfg.grating_index**2),
        )
    )


def _nonzero_slave_probe(matrix: PETSc.Mat) -> PETSc.Vec:
    """Build a deterministic assembled-space probe with nonzero slave rows."""

    source = matrix.createVecRight()
    start, stop = source.getOwnershipRange()
    indices = np.arange(start, stop, dtype=PETSc.IntType)
    coordinate = np.arange(start, stop, dtype=np.float64)
    values = (1.0 + 0.013 * coordinate) + 1j * (0.35 - 0.007 * coordinate)
    source.setValues(
        indices,
        np.asarray(values, dtype=PETSc.ScalarType),
    )
    source.assemble()
    return source


def _frozen_source(floquet, cfg, label: str) -> tuple[PETSc.Vec, dict]:
    source, facts = build_frozen_fullspace_primal_source(
        floquet.mpc.function_space, floquet, cfg, label
    )
    assert facts["name"] == label
    assert facts["formula"] == l2_source_formula(label)
    return source, facts


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    difference = np.asarray(left - right, dtype=np.complex128)
    reference = np.asarray(right, dtype=np.complex128)
    return float(
        np.linalg.norm(difference)
        / max(np.linalg.norm(reference), np.finfo(float).tiny)
    )


def _split_action(mesh_data, cfg, space, mpc):
    u = ufl.TrialFunction(space)
    v = ufl.TestFunction(space)
    dx = ufl.Measure(
        "dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags
    )
    curl_form, mass_form = _build_physical_volume_terms(cfg, u, v, dx)
    return FullspaceSplitVolumeAction(
        curl_form,
        mass_form,
        space,
        mpc=mpc,
        jit_options={},
    )


def _stream_original_integrals(original_form, space, mpc, source):
    """Evaluate original UFL integrals one at a time, never using the split API."""

    accumulator = source.duplicate()
    accumulator.set(0.0)
    try:
        for integral in original_form.integrals():
            component = build_fullspace_mpc_form_action(
                ufl.Form([integral]),
                space,
                mpc=mpc,
                slave_row_identity=False,
                jit_options={},
            )
            try:
                accumulator.axpy(PETSc.ScalarType(1.0), component.apply(source))
            finally:
                component.destroy()
        source_values = np.asarray(source.getArray(readonly=True))
        owned_slaves = np.asarray(
            [
                int(row)
                for row in np.asarray(mpc.slaves, dtype=np.int32)
                if int(row) < source_values.size
            ],
            dtype=np.int32,
        )
        if owned_slaves.size:
            accumulator.getArray()[owned_slaves] = source_values[owned_slaves]
        accumulator.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        return accumulator
    except Exception:
        accumulator.destroy()
        raise


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial J3 oracle")
@pytest.mark.parametrize("degree", [2, 3])
def test_original_assembled_mpc_action_matches_two_form_sum(
    tmp_path: Path, degree: int
) -> None:
    cfg, mesh_data, floquet = _fixture(tmp_path, degree)
    space = floquet.mpc.function_space
    mpc = floquet.mpc
    original = _original_combined_physical_form(mesh_data, cfg, space)
    assembled = dolfinx_mpc.assemble_matrix(fem.form(original), mpc, bcs=[])
    assembled.assemble()
    split = _split_action(mesh_data, cfg, space, mpc)
    source = _nonzero_slave_probe(assembled)
    expected = assembled.createVecLeft()
    try:
        before = np.asarray(source.getArray(readonly=True)).copy()
        assembled.mult(source, expected)
        observed = np.asarray(split.apply(source).getArray(readonly=True)).copy()
        reference = np.asarray(expected.getArray(readonly=True)).copy()
        assert np.all(np.isfinite(observed))
        assert _relative(observed, reference) <= 1.0e-12
        assert np.array_equal(
            observed,
            np.asarray(split.apply(source).getArray(readonly=True)),
        )
        assert np.array_equal(
            np.asarray(source.getArray(readonly=True)), before
        )
        audit = split.audit
        assert audit["component_count"] == 2
        assert audit["slave_row_identity_owner"] == "curl_curl"
        assert audit["constraint_identity_rows_exactly_once"] is True
        assert audit["third_persistent_sum_vector"] is False
        assert audit["components"]["curl_curl"]["slave_row_identity"] is True
        assert audit["components"]["complex_material_mass"]["slave_row_identity"] is False
        owned_slaves = np.asarray(
            [
                int(row)
                for row in np.asarray(mpc.slaves, dtype=np.int32)
                if int(row) < before.size
            ],
            dtype=np.int32,
        )
        if owned_slaves.size:
            assert np.array_equal(observed[owned_slaves], before[owned_slaves])
    finally:
        source.destroy()
        expected.destroy()
        split.destroy()
        split.destroy()
        assembled.destroy()


@pytest.mark.skipif(MPI.COMM_WORLD.size != 1, reason="serial p6 streaming authority")
def test_p6_original_integral_streaming_authority_for_fixed_sources(
    tmp_path: Path,
) -> None:
    cfg, mesh_data, floquet = _fixture(tmp_path, 6)
    space = floquet.mpc.function_space
    mpc = floquet.mpc
    original = _original_combined_physical_form(mesh_data, cfg, space)
    split = _split_action(mesh_data, cfg, space, mpc)
    try:
        assert len(original.integrals()) >= 3
        audit = split.audit
        assert audit["components"]["curl_curl"]["slave_row_identity"] is True
        assert audit["components"]["complex_material_mass"]["slave_row_identity"] is False
        for label in ("random", "gradient", "curl", "checkerboard"):
            source, _facts = _frozen_source(floquet, cfg, label)
            before = np.asarray(source.getArray(readonly=True)).copy()
            reference = _stream_original_integrals(original, space, mpc, source)
            try:
                observed = np.asarray(split.apply(source).getArray(readonly=True)).copy()
                repeated = np.asarray(split.apply(source).getArray(readonly=True)).copy()
                assert np.all(np.isfinite(observed))
                assert np.linalg.norm(observed) > 0.0
                assert _relative(observed, reference.getArray(readonly=True)) <= 1.0e-12
                assert np.array_equal(observed, repeated)
                assert np.array_equal(
                    np.asarray(source.getArray(readonly=True)), before
                )
                scale = PETSc.ScalarType(0.37 - 0.21j)
                scaled, _scaled_facts = _frozen_source(floquet, cfg, label)
                scaled.scale(scale)
                scaled_observed = np.asarray(
                    split.apply(scaled).getArray(readonly=True)
                ).copy()
                assert _relative(scaled_observed, scale * observed) <= 1.0e-12
                scaled.destroy()
            finally:
                reference.destroy()
                source.destroy()
        random_source, _random_facts = _frozen_source(floquet, cfg, "random")
        gradient_source, _gradient_facts = _frozen_source(floquet, cfg, "gradient")
        random_before = np.asarray(
            random_source.getArray(readonly=True)
        ).copy()
        gradient_before = np.asarray(
            gradient_source.getArray(readonly=True)
        ).copy()
        sum_source = random_source.copy()
        try:
            random_output = np.asarray(
                split.apply(random_source).getArray(readonly=True)
            ).copy()
            gradient_output = np.asarray(
                split.apply(gradient_source).getArray(readonly=True)
            ).copy()
            sum_source.axpy(PETSc.ScalarType(1.0), gradient_source)
            additive_output = np.asarray(
                split.apply(sum_source).getArray(readonly=True)
            ).copy()
            assert np.all(np.isfinite(additive_output))
            assert _relative(
                additive_output, random_output + gradient_output
            ) <= 1.0e-12
            assert np.array_equal(
                np.asarray(random_source.getArray(readonly=True)), random_before
            )
            assert np.array_equal(
                np.asarray(gradient_source.getArray(readonly=True)), gradient_before
            )
        finally:
            sum_source.destroy()
            random_source.destroy()
            gradient_source.destroy()
    finally:
        split.destroy()
        split.destroy()
