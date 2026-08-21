"""Focused D2 distributed trace-harmonic core tests."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc
from slepc4py import SLEPc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.fullspace_slab_interface import build_fullspace_slab_interface
from src.solvers.fullspace_trace_harmonic import (
    build_trace_harmonic_definition,
)
from src.solvers.fullspace_trace_harmonic_distributed import (
    D2_EPS_MAX_IT,
    D2_EPS_TOL,
    D2_KSP_MAX_IT,
    D2_KSP_RTOL,
    D2_RANK_PREFIXES,
    D2_SHARED_TRACE_WEIGHT,
    DistributedTraceHarmonicBasis,
    DistributedTraceHarmonicSlab,
    _InteriorRestricted,
    _ordered_slab_definitions,
    _stable_eigen_order,
    _two_pass_mgs,
)
from src.test.stage2_test_utils import stage4_block_config


class _ArrayShell:
    """Small PETSc MatShell used only to exercise the algebra contract."""

    def __init__(self, array: np.ndarray):
        self.array = np.asarray(array, dtype=np.complex128)
        size = int(self.array.shape[0])
        if self.array.shape != (size, size):
            raise ValueError("synthetic shell must be square")
        self.matrix = PETSc.Mat().createPython(
            ((size, size), (size, size)),
            context=self,
            comm=MPI.COMM_WORLD,
        )
        self.matrix.setUp()

    def mult(self, _matrix, vector, result):
        result.getArray()[:] = self.array @ vector.getArray(readonly=True)

    def destroy(self, _matrix=None):
        matrix = self.matrix
        self.matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()


class _WorkspaceStub:
    def __init__(self):
        self.destroy_count = 0

    def destroy(self):
        self.destroy_count += 1


def _shell_dense(shell: _ArrayShell) -> np.ndarray:
    size = shell.array.shape[0]
    result = np.empty_like(shell.array)
    basis = shell.matrix.createVecRight()
    action = shell.matrix.createVecLeft()
    try:
        for column in range(size):
            basis.set(0.0)
            basis.getArray()[column] = 1.0
            shell.matrix.mult(basis, action)
            result[:, column] = action.getArray(readonly=True)
    finally:
        action.destroy()
        basis.destroy()
    return result


def _solve_small_generalized(stiffness, mass):
    chol = np.linalg.cholesky(mass)
    whitened = np.linalg.solve(chol, stiffness)
    whitened = np.linalg.solve(chol.conj(), whitened.T).T
    values, vectors = np.linalg.eigh(whitened)
    vectors = np.linalg.solve(chol.conj().T, vectors)
    return values, vectors


def test_d2_stable_eigen_order_keeps_vector_indices_aligned():
    ordered, permutation = _stable_eigen_order((3.0, 1.0, 1.0, 0.5))
    assert ordered == ((0.5, 0), (1.0, 1), (1.0, 2), (3.0, 3))
    assert permutation == (3, 1, 2, 0)
    eps_vectors = ("eps0", "eps1", "eps2", "eps3")
    assert tuple(eps_vectors[index] for index in permutation) == (
        "eps3",
        "eps1",
        "eps2",
        "eps0",
    )


def test_d2_slab_definitions_are_stably_ordered_by_slab_id():
    reverse = (SimpleNamespace(slab_id=1), SimpleNamespace(slab_id=0))
    ordered = _ordered_slab_definitions(reverse)
    assert tuple(item.slab_id for item in ordered) == (0, 1)


def test_d2_basis_release_keeps_z_and_rejects_rebuild():
    basis = object.__new__(DistributedTraceHarmonicBasis)
    z = np.asarray(
        [[1.0 + 0.2j, 0.0], [0.0, 1.0 - 0.1j], [0.5j, 0.25]],
        dtype=np.complex128,
    )
    z.flags.writeable = False
    slab0 = _WorkspaceStub()
    slab1 = _WorkspaceStub()
    basis._definitions = (object(), object())
    basis.comm = MPI.COMM_WORLD
    basis._slabs = (slab0, slab1)
    basis._z = z
    basis._candidate_order = ((1.0, 0, 0), (2.0, 1, 0))
    basis._audit = {
        "construction_workspace_released": False,
        "slab_eigen_audits": ({"slab": 0}, {"slab": 1}),
    }
    basis._construction_workspace_released = False
    basis._destroyed = False
    basis.release_construction_workspace()
    assert basis.audit["construction_workspace_released"] is True
    assert basis.audit["slab_eigen_audits"] == ({"slab": 0}, {"slab": 1})
    assert np.shares_memory(basis.columns, z)
    assert np.array_equal(basis.columns, z)
    vector = PETSc.Vec().createSeq(3, comm=MPI.COMM_WORLD)
    try:
        basis.fill_column(1, vector)
        assert np.array_equal(vector.getArray(readonly=True), z[:, 1])
    finally:
        vector.destroy()
    with pytest.raises(RuntimeError, match="after construction workspace release"):
        basis.build(rank=1)
    with pytest.raises(RuntimeError, match="already been released"):
        basis.release_construction_workspace()
    basis.destroy()
    basis.destroy()
    assert slab0.destroy_count == 1
    assert slab1.destroy_count == 1


def _real_fixture(tmp_path: Path, degree: int):
    comm = MPI.COMM_WORLD
    root = Path(comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0))
    cfg = replace(
        stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=50.0,
            stage4_dtn_order_policy="zero_order",
            incident_theta_deg=21.131,
            incident_phi_deg=33.690,
        ),
        nedelec_degree=degree,
    )
    mesh_data = build_airbox_mesh_3d(
        cfg, root / f"mesh-d2-p{degree}-n{comm.size}"
    )
    raw_space = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_space, mesh_data, cfg)
    topology = build_fullspace_slab_interface(
        floquet_data.mpc.function_space,
        mesh_data,
        floquet_data,
        cfg,
    )
    definitions = tuple(
        build_trace_harmonic_definition(
            topology,
            mesh_data,
            raw_space,
            floquet_data.mpc,
            slab_id,
        )
        for slab_id in (0, 1)
    )
    return cfg, mesh_data, floquet_data, topology, definitions


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="synthetic MatShell algebra uses one local PETSc ownership range",
)
def test_d2_synthetic_shell_extension_and_mgs():
    stiffness = np.asarray(
        [
            [4.0, 0.2, 0.5, 0.0],
            [0.2, 3.0, 0.0, 0.3],
            [0.5, 0.0, 5.0, 0.4],
            [0.0, 0.3, 0.4, 6.0],
        ],
        dtype=np.complex128,
    )
    mass = np.asarray([[2.0, 0.1j], [-0.1j, 1.5]], dtype=np.complex128)
    b_shell = _ArrayShell(stiffness)
    try:
        template = b_shell.matrix.createVecRight()
        restricted = _InteriorRestricted(
            b_shell.matrix,
            template,
            np.asarray([2, 3], dtype=np.int32),
        )
        ksp = PETSc.KSP().create(MPI.COMM_WORLD)
        try:
            ksp.setType(PETSc.KSP.Type.CG)
            ksp.getPC().setType(PETSc.PC.Type.NONE)
            ksp.setTolerances(rtol=D2_KSP_RTOL, max_it=D2_KSP_MAX_IT)
            ksp.setOperators(restricted.matrix)
            fixed_trace = template.duplicate()
            interior_solution = template.duplicate()
            extension = template.duplicate()
            rhs = template.duplicate()
            residual = template.duplicate()
            try:
                fixed_trace.set(0.0)
                fixed_trace.getArray()[:2] = (1.0 + 0.2j, -0.4 + 0.1j)
                b_action = template.duplicate()
                try:
                    b_shell.matrix.mult(fixed_trace, b_action)
                    rhs.set(0.0)
                    rhs.getArray()[2:] = -b_action.getArray(readonly=True)[2:]
                finally:
                    b_action.destroy()
                interior_solution.set(0.0)
                ksp.solve(rhs, interior_solution)
                assert int(ksp.getConvergedReason()) > 0
                fixed_trace.copy(result=extension)
                extension.axpy(PETSc.ScalarType(1.0), interior_solution)
                assert np.array_equal(
                    extension.getArray(readonly=True)[:2],
                    fixed_trace.getArray(readonly=True)[:2],
                )
                restricted.matrix.mult(interior_solution, residual)
                residual.axpy(PETSc.ScalarType(-1.0), rhs)
                assert residual.norm() / max(rhs.norm(), 1.0e-30) <= 1.0e-10
            finally:
                residual.destroy()
                rhs.destroy()
                extension.destroy()
                interior_solution.destroy()
                fixed_trace.destroy()
            k_shell = _ArrayShell(np.asarray([[3.0, 0.2], [0.2, 2.0]]))
            m_shell = _ArrayShell(mass)
            try:
                k_dense = _shell_dense(k_shell)
                m_dense = _shell_dense(m_shell)
                assert np.linalg.norm(k_dense - k_dense.conj().T) <= 1.0e-12
                assert np.linalg.norm(m_dense - m_dense.conj().T) <= 1.0e-12
                values, vectors = _solve_small_generalized(k_dense, m_dense)
                assert np.all(np.isfinite(values))
                for index, value in enumerate(values):
                    left = k_dense @ vectors[:, index]
                    right = value * (m_dense @ vectors[:, index])
                    assert np.linalg.norm(left - right) <= 1.0e-10
                merged = _two_pass_mgs(
                    [
                        np.asarray([1.0 + 0.2j, 0.0j]),
                        np.asarray([0.1j, 1.0 - 0.3j]),
                    ],
                    MPI.COMM_WORLD,
                )
                gram = np.asarray(
                    [[np.vdot(left, right) for right in merged] for left in merged]
                )
                assert np.linalg.norm(gram - np.eye(2)) <= 1.0e-12
                assert tuple(sorted(D2_RANK_PREFIXES)) == (16, 32, 48, 64)
                assert D2_SHARED_TRACE_WEIGHT == 0.5
            finally:
                m_shell.destroy()
                k_shell.destroy()
        finally:
            ksp.destroy()
            restricted.destroy()
            template.destroy()
    finally:
        b_shell.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="synthetic SLEPc backend uses one local PETSc ownership range",
)
def test_d2_synthetic_krylov_schur_shift_cg_backend():
    size = 12
    indices = np.arange(size, dtype=np.float64)
    stiffness = np.diag(3.0 + indices)
    stiffness += 0.02 * np.ones((size, size))
    mass_vector = 0.1 + 0.01 * indices
    mass = np.eye(size) + np.outer(mass_vector, mass_vector)
    stiffness_shell = _ArrayShell(stiffness)
    mass_shell = _ArrayShell(mass)
    eps = SLEPc.EPS().create(MPI.COMM_WORLD)
    try:
        eps.setOperators(stiffness_shell.matrix, mass_shell.matrix)
        eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
        eps.setType(SLEPc.EPS.Type.KRYLOVSCHUR)
        eps.setWhichEigenpairs(SLEPc.EPS.Which.SMALLEST_REAL)
        eps.setDimensions(nev=2, ncv=8)
        eps.setTolerances(tol=D2_EPS_TOL, max_it=D2_EPS_MAX_IT)
        spectral_transform = eps.getST()
        spectral_transform.setType(SLEPc.ST.Type.SHIFT)
        spectral_transform.setShift(0.0)
        spectral_ksp = spectral_transform.getKSP()
        spectral_ksp.setType(PETSc.KSP.Type.CG)
        spectral_ksp.getPC().setType(PETSc.PC.Type.NONE)
        spectral_ksp.setTolerances(
            rtol=D2_KSP_RTOL, atol=0.0, max_it=D2_KSP_MAX_IT
        )
        eps.solve()
        assert int(eps.getConvergedReason()) > 0
        assert int(eps.getConverged()) >= 2
        assert spectral_transform.getType().lower() == "shift"
        assert spectral_ksp.getType().lower() == "cg"
        assert spectral_ksp.getPC().getType().lower() == "none"
        assert "lu" not in spectral_ksp.getPC().getType().lower()
        vector = stiffness_shell.matrix.createVecRight()
        stiffness_action = stiffness_shell.matrix.createVecLeft()
        mass_action = mass_shell.matrix.createVecLeft()
        residual = stiffness_shell.matrix.createVecLeft()
        try:
            for index in range(2):
                eigenvalue = complex(eps.getEigenvalue(index))
                eps.getEigenvector(index, vector)
                stiffness_shell.matrix.mult(vector, stiffness_action)
                mass_shell.matrix.mult(vector, mass_action)
                stiffness_action.copy(result=residual)
                residual.axpy(
                    PETSc.ScalarType(-eigenvalue.real), mass_action
                )
                denominator = max(
                    stiffness_action.norm(),
                    abs(eigenvalue.real) * mass_action.norm(),
                    1.0e-300,
                )
                assert residual.norm() / denominator <= 1.0e-10
        finally:
            residual.destroy()
            mass_action.destroy()
            stiffness_action.destroy()
            vector.destroy()
    finally:
        eps.destroy()
        mass_shell.destroy()
        stiffness_shell.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="real p2 distributed trace-harmonic serial fixture",
)
def test_d2_real_p2_basis_extension_phase_and_repeat(tmp_path: Path):
    _cfg, _mesh_data, _floquet_data, topology, definitions = _real_fixture(
        tmp_path, 2
    )
    basis = DistributedTraceHarmonicBasis(definitions)
    try:
        first = basis.build(rank=4, requested_eigenpairs=4)
        assert first.shape[1] == 4
        assert np.all(np.isfinite(first))
        local_gram = np.asarray(
            [[np.vdot(left, right) for right in first.T] for left in first.T]
        )
        gram = topology.mesh.comm.allreduce(local_gram, op=MPI.SUM)
        assert np.linalg.norm(gram - np.eye(4)) <= 1.0e-10
        assert basis.audit["physical_action_applied"] is False
        assert basis.audit["az_e_not_built"] is True
        assert basis.audit["numeric_allgather"] is False
        assert basis.audit["shared_trace_weight"] == 0.5
        assert basis.audit["retained_z_bytes_global"] > 0
        repeated = basis.build(rank=4, requested_eigenpairs=4)
        assert repeated.shape == first.shape
        assert np.array_equal(first, repeated)
        assert all(
            slab._eigen_audit["harmonic_extension_residual_max"] <= 1.0e-10
            for slab in basis._slabs
        )
    finally:
        basis.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="real p2 distributed trace action MPI2 smoke",
)
def test_d2_real_p2_mpi2_trace_action_repeat(tmp_path: Path):
    _cfg, _mesh_data, _floquet_data, topology, definitions = _real_fixture(
        tmp_path, 2
    )
    slabs = tuple(DistributedTraceHarmonicSlab(item) for item in definitions)
    try:
        assert len(set(topology.mesh.comm.allgather(topology.canonical_sha256))) == 1
        for slab in slabs:
            trace = slab.create_trace_vector()
            first = slab.create_trace_vector()
            second = slab.create_trace_vector()
            try:
                values = trace.getArray()
                values[:] = 0.0
                seed = slab._seed_vector(0)
                try:
                    values[:] = seed.getArray(readonly=True)
                finally:
                    seed.destroy()
                slab.mass_matrix.mult(trace, first)
                slab.mass_matrix.mult(trace, second)
                assert np.array_equal(
                    first.getArray(readonly=True),
                    second.getArray(readonly=True),
                )
                assert slab.trace_matrix.getType().lower() == "python"
                assert slab._bii.matrix.getType().lower() == "python"
            finally:
                second.destroy()
                first.destroy()
                trace.destroy()
    finally:
        for slab in slabs:
            slab.destroy()


def test_d2_production_ast_forbidden_paths_and_fixed_api():
    path = Path(__file__).parents[1] / "solvers/fullspace_trace_harmonic_distributed.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    basis_build = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "build"
    )
    assert not any(
        isinstance(node, ast.Call)
        and (
            (
                isinstance(node.func, ast.Name)
                and node.func.id == "_two_pass_mgs"
            )
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "_two_pass_mgs"
            )
        )
        for node in ast.walk(basis_build)
    )
    assert not any(
        isinstance(node, ast.Name) and node.id == "columns"
        for node in ast.walk(basis_build)
    )
    forbidden_calls = {
        "createAIJ",
        "assemble_matrix",
        "static_condensation",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
        if isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = {
                argument.arg
                for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            }
            assert not names.intersection({"residual", "source", "rho"})
    assert "D2_PROFILE" in text
    assert "numeric_allgather" in text
    assert "owner_range_metadata_alltoall" in text
    assert "orthogonalization_scratch_bytes_global_max" in text
    assert "orthogonalization_scratch_bytes_global_sum" in text
    assert "exact_array_size_derived_upper_bound" in text
