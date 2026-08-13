from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.fem import petsc as fem_petsc
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_h2b_m6b_shifted_lu_store import (
    H2BM6BShiftedLUFactor,
    H2BM6BShiftedLUPatchStore,
    M6B_ALLOWED_SHIFTED_BETAS,
    build_h2b_m6b_shifted_lu_factor,
    build_h2b_m6b_shifted_lu_patch_store,
    load_h2b_m6b_shifted_lu_patch_store,
    shifted_lu_factor_nbytes,
    stream_write_h2b_m6b_shifted_lu_patch_store,
    write_h2b_m6b_shifted_lu_patch_store,
)
from src.solvers.hcurl_h2b_m6b_shifted_patch_pc import (
    H2BM6BShiftedPatchPC,
    M6BOuterMatPythonContext,
    M6BShiftedPCContext,
    build_m6b_outer_mat,
    build_m6b_volume_form,
    compose_m6b_physical_rhs,
    evaluate_m6b_screen_gate,
    m6b_shifted_local_matrix,
    m6b_material_tag_coverage,
)
from src.common.config_3d import target_stage4_config
from src.solvers.common_3d_forms import _build_variational_forms


def _local_matrix() -> np.ndarray:
    return np.asarray(
        (
            (2.0 + 0.4j, 0.2 - 0.1j, 0.1 + 0.2j),
            (0.3 + 0.1j, 1.7 + 0.2j, -0.2 + 0.1j),
            (0.1 - 0.3j, 0.2 + 0.2j, 1.4 + 0.5j),
        ),
        dtype=np.complex128,
        order="C",
    )


def _store(tmp_path: Path) -> H2BM6BShiftedLUPatchStore:
    factor = build_h2b_m6b_shifted_lu_factor(
        _local_matrix(), task037_extra_m6b=True
    )
    neighborhoods = (
        {
            "neighborhood_id": 0,
            "key_sha256": "0" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },
        {
            "neighborhood_id": 1,
            "key_sha256": "1" * 64,
            "cell_ordinals": [1],
            "multiplicity": 1,
            "factor_id": 0,
        },
    )
    store = build_h2b_m6b_shifted_lu_patch_store(
        (factor,),
        neighborhoods,
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([0, 3, 6], dtype=np.int64),
        np.asarray([0, 1, 2, 1, 2, 3], dtype=np.int64),
        identity={
            "source_provenance": "test",
            "beta": 1.0,
            "operator": "synthetic shifted full-space",
        },
        task037_extra_m6b=True,
    )
    manifest = write_h2b_m6b_shifted_lu_patch_store(
        store, tmp_path / "shifted_store", task037_extra_m6b=True
    )
    return load_h2b_m6b_shifted_lu_patch_store(
        manifest, task037_extra_m6b=True
    )


def _single_cell_store(tmp_path: Path) -> H2BM6BShiftedLUPatchStore:
    factor = build_h2b_m6b_shifted_lu_factor(
        _local_matrix(), task037_extra_m6b=True
    )
    store = build_h2b_m6b_shifted_lu_patch_store(
        (factor,),
        ({
            "neighborhood_id": 0,
            "key_sha256": "2" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 3], dtype=np.int64),
        np.asarray([0, 1, 2], dtype=np.int64),
        identity={"source_provenance": "test-slave", "beta": 1.0},
        task037_extra_m6b=True,
    )
    manifest = write_h2b_m6b_shifted_lu_patch_store(
        store, tmp_path / "single_shifted_store", task037_extra_m6b=True
    )
    return load_h2b_m6b_shifted_lu_patch_store(
        manifest, task037_extra_m6b=True
    )


def test_m6b_beta_half_store_roundtrip_and_pc_identity(tmp_path: Path):
    assert M6B_ALLOWED_SHIFTED_BETAS == (0.5, 1.0)
    matrix = _local_matrix()
    factor = build_h2b_m6b_shifted_lu_factor(
        matrix, beta=0.5, task037_extra_m6b=True
    )
    store = build_h2b_m6b_shifted_lu_patch_store(
        (factor,),
        ({
            "neighborhood_id": 0,
            "key_sha256": "7" * 64,
            "cell_ordinals": [0],
            "multiplicity": 1,
            "factor_id": 0,
        },),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 3], dtype=np.int64),
        np.asarray([0, 1, 2], dtype=np.int64),
        identity={"source_provenance": "beta-half", "beta": 0.5},
        task037_extra_m6b=True,
    )
    manifest = write_h2b_m6b_shifted_lu_patch_store(
        store, tmp_path / "beta_half_store", beta=0.5, task037_extra_m6b=True
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["beta"] == 0.5
    assert payload["audit"]["beta"] == 0.5
    assert payload["factors"][0]["beta"] == 0.5
    loaded = load_h2b_m6b_shifted_lu_patch_store(
        manifest, task037_extra_m6b=True
    )
    assert loaded.audit["beta"] == 0.5
    pc = H2BM6BShiftedPatchPC(
        loaded,
        global_row_count=3,
        shifted_action=lambda values: np.array(values, dtype=np.complex128, copy=True),
        task037_extra_m6b=True,
    )
    assert pc.audit["beta"] == 0.5
    with pytest.raises(ValueError, match="writer beta"):
        write_h2b_m6b_shifted_lu_patch_store(
            loaded,
            tmp_path / "beta_mismatch",
            beta=1.0,
            task037_extra_m6b=True,
        )
    with pytest.raises(ValueError, match="0.5 or 1"):
        build_h2b_m6b_shifted_lu_factor(
            matrix, beta=0.25, task037_extra_m6b=True
        )


def test_m6b_zgetrf_roundtrip_and_exact_factor_bytes(tmp_path: Path):
    matrix = _local_matrix()
    factor = build_h2b_m6b_shifted_lu_factor(
        matrix, task037_extra_m6b=True
    )
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.4j, 0.5 - 0.1j], dtype=np.complex128)
    solution = factor.solve(rhs)
    assert np.linalg.norm(matrix @ solution - rhs) <= 1.0e-12
    assert factor.beta == 1.0
    assert factor.factorization_info == 0
    assert factor.factor_nbytes == shifted_lu_factor_nbytes(3)
    assert factor.audit_jsonable()["full_dense_patch_matrix_retained"] is False
    assert factor.audit_jsonable()["pivots_retained"] is not False


def test_m6b_cold_store_is_mmap_readonly_and_factor_is_shared(tmp_path: Path):
    store = _store(tmp_path)
    assert store.factor_for_cell(0) is store.factor_for_cell(1)
    factor = store.factor_for_cell(0)
    assert factor.beta == 1.0
    assert isinstance(factor.lu.base, np.memmap)
    assert isinstance(factor.pivots.base, np.memmap)
    assert factor.lu.flags.writeable is False
    assert factor.pivots.flags.writeable is False
    audit = store.audit_jsonable()
    assert audit["beta"] == 1.0
    assert audit["factor_count"] == 1
    assert audit["factor_reuse_count"] == 1
    assert audit["factor_copy_count"] == 0
    assert audit["full_dense_patch_matrix_retained"] is False
    assert audit["materialization_identity"]["global_matrix"] is False


def test_m6b_stream_writer_binds_repeat_matrix_and_factor_sha(tmp_path: Path):
    matrix = np.eye(882, dtype=np.complex128) * (2.0 + 0.25j)
    factor = build_h2b_m6b_shifted_lu_factor(
        matrix, beta=0.5, task037_extra_m6b=True
    )
    record = {
        "neighborhood_id": 0,
        "key_sha256": "3" * 64,
        "first_matrix_sha256": factor.matrix_sha256,
        "repeat_matrix_sha256": factor.matrix_sha256,
        "expected_matrix_sha256": factor.matrix_sha256,
        "repeat_factor_sha256": factor.factor_sha256,
        "expected_factor_sha256": factor.factor_sha256,
    }

    def records():
        yield record, matrix

    manifest = stream_write_h2b_m6b_shifted_lu_patch_store(
        records(),
        tmp_path / "streamed_shifted_store",
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 882], dtype=np.int64),
        np.arange(882, dtype=np.int64),
        neighborhoods=(
            {"neighborhood_id": 0, "key_sha256": "3" * 64},
        ),
        identity={"source_provenance": "test", "beta": 0.5},
        beta=0.5,
        expected_factor_count=1,
        expected_neighborhood_count=1,
        task037_extra_m6b=True,
    )
    observed = json.loads(manifest.read_text(encoding="utf-8"))["neighborhoods"][0]
    assert observed["matrix_sha256"] == factor.matrix_sha256
    assert observed["factor_sha256"] == factor.factor_sha256

    bad_record = dict(record)
    bad_record["expected_factor_sha256"] = "0" * 64

    def bad_records():
        yield bad_record, matrix

    with pytest.raises(ValueError, match="factor SHA"):
        stream_write_h2b_m6b_shifted_lu_patch_store(
            bad_records(),
            tmp_path / "bad_streamed_shifted_store",
            np.asarray([0], dtype=np.int32),
            np.asarray([0, 882], dtype=np.int64),
            np.arange(882, dtype=np.int64),
            neighborhoods=(
                {"neighborhood_id": 0, "key_sha256": "3" * 64},
            ),
            identity={"source_provenance": "test", "beta": 0.5},
            beta=0.5,
            expected_factor_count=1,
            expected_neighborhood_count=1,
            task037_extra_m6b=True,
        )


def test_m6b_stream_writer_does_not_deduplicate_neighborhood_factors(
    tmp_path: Path,
):
    matrix = np.eye(882, dtype=np.complex128) * (2.0 + 0.25j)
    neighborhoods = (
        {"neighborhood_id": 0, "key_sha256": "5" * 64},
        {"neighborhood_id": 1, "key_sha256": "6" * 64},
    )

    def records():
        yield neighborhoods[0], matrix
        yield neighborhoods[1], matrix

    manifest = stream_write_h2b_m6b_shifted_lu_patch_store(
        records(),
        tmp_path / "duplicate_matrix_store",
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([0, 882, 1764], dtype=np.int64),
        np.arange(1764, dtype=np.int64),
        neighborhoods=neighborhoods,
        identity={"source_provenance": "test", "beta": 1.0},
        expected_factor_count=2,
        expected_neighborhood_count=2,
        task037_extra_m6b=True,
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    factors = payload["factors"]
    observed = payload["neighborhoods"]
    assert [item["factor_id"] for item in factors] == [0, 1]
    assert [item["factor_id"] for item in observed] == [0, 1]
    assert factors[0]["lu_path"] != factors[1]["lu_path"]
    assert factors[0]["pivot_path"] != factors[1]["pivot_path"]
    assert payload["audit"]["factor_count"] == 2


def test_m6b_rhs_canonical_writer_uses_three_argument_api():
    signature = inspect.signature(
        __import__(
            "src.solvers.hcurl_canonical_vector_dolfinx",
            fromlist=["iter_canonical_full_fe_dual_packets"],
        ).iter_canonical_full_fe_dual_packets
    )
    assert list(signature.parameters)[0:3] == [
        "function_space",
        "mpc",
        "recovered_vec",
    ]
    assert list(signature.parameters)[3] == "geometry_tolerance"
    source = inspect.getsource(runner._run_m6b_online_worker)
    assert "dual_iterator(function_space, floquet.mpc, rhs_vec)," in source
    assert "dual_iterator(function_space, floquet.mpc, rhs_vec, floquet)" not in source


def test_m6b_nonhermitian_pc_uses_conjugate_omega_and_one_shifted_action(tmp_path: Path):
    store = _store(tmp_path)
    global_matrix = np.asarray(
        (
            (1.5 + 0.2j, 0.1, 0.0, 0.0),
            (0.2 - 0.1j, 1.2 + 0.3j, 0.1, 0.0),
            (0.0, 0.2, 1.4 - 0.1j, 0.2),
            (0.0, 0.0, 0.1 + 0.2j, 0.9 + 0.4j),
        ),
        dtype=np.complex128,
    )
    calls: list[np.ndarray] = []

    def shifted_action(values: np.ndarray) -> np.ndarray:
        calls.append(np.array(values, copy=True))
        return np.ascontiguousarray(global_matrix @ values)

    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.4 - 0.2j, 0.7 + 0.3j])
    pc = H2BM6BShiftedPatchPC(
        store,
        global_row_count=4,
        shifted_action=shifted_action,
        task037_extra_m6b=True,
    )
    correction, measurement = pc.apply_with_measurement(rhs)
    z0 = np.zeros(4, dtype=np.complex128)
    z0[:3] = store.solve(0, rhs[:3])
    z0[1:4] += store.solve(1, rhs[1:4])
    z0[1:3] /= 2.0
    q = global_matrix @ z0
    omega = np.vdot(q, rhs) / np.vdot(q, q)
    assert np.allclose(correction, omega * z0, rtol=1.0e-13, atol=1.0e-13)
    assert measurement["omega"] == [float(omega.real), float(omega.imag)]
    assert measurement["exact_shifted_action_count"] == 1
    assert len(calls) == 1
    assert measurement["rho_star"] <= measurement["rho_unit"]
    assert pc.audit["factor_reuse_count"] == 1
    assert pc.audit["per_cell_solution_retained"] is False


def test_m6b_pc_batches_reused_factor_solves_and_matches_cell_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = _store(tmp_path)
    calls = []
    original_solve = H2BM6BShiftedLUFactor.solve

    def counted_solve(self, rhs):
        calls.append(np.asarray(rhs).shape)
        return original_solve(self, rhs)

    monkeypatch.setattr(H2BM6BShiftedLUFactor, "solve", counted_solve)
    pc = H2BM6BShiftedPatchPC(
        store,
        global_row_count=4,
        shifted_action=lambda values: np.array(values, copy=True),
        task037_extra_m6b=True,
    )
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.1j, 0.4 - 0.2j, 0.7 + 0.3j])
    observed, _ = pc.apply_with_measurement(rhs)
    local0 = store.solve(0, rhs[:3])
    local1 = store.solve(1, rhs[1:4])
    expected = np.zeros(4, dtype=np.complex128)
    expected[:3] += local0
    expected[1:4] += local1
    expected[1:3] /= 2.0
    omega = np.vdot(expected, rhs) / np.vdot(expected, expected)
    assert np.allclose(observed, expected * omega)
    assert calls[0] == (3, 2)
    assert pc.audit["solve_count_per_apply"] == 1
    assert pc.audit["rhs_count"] == 2
    assert pc.audit["factor_reuse_exercised"] == 1


def test_m6b_slave_identity_row_is_carried_without_a_patch_factor(tmp_path: Path):
    store = _single_cell_store(tmp_path)
    matrix = np.eye(4, dtype=np.complex128) * (1.0 + 0.2j)
    calls = []

    def shifted_action(values: np.ndarray) -> np.ndarray:
        calls.append(1)
        return matrix @ values

    rhs = np.asarray([1.0 + 0.1j, -0.2 + 0.4j, 0.5 - 0.3j, 0.7 + 0.8j])
    pc = H2BM6BShiftedPatchPC(
        store,
        global_row_count=4,
        shifted_action=shifted_action,
        slave_identity_rows=(3,),
        task037_extra_m6b=True,
    )
    correction, measurement = pc.apply_with_measurement(rhs)
    assert np.allclose(
        correction[3],
        rhs[3] * (measurement["omega"][0] + 1j * measurement["omega"][1]),
    )
    assert measurement["exact_shifted_action_count"] == 1
    assert len(calls) == 1


class _Volume:
    def __init__(self, values: np.ndarray) -> None:
        self.values = np.asarray(values, dtype=np.complex128)
        self.output = PETSc.Vec().createSeq(self.values.size, comm=PETSc.COMM_SELF)
        self.calls = 0

    def mult(self, source: PETSc.Vec) -> PETSc.Vec:
        self.output.getArray()[:] = self.values * source.getArray(readonly=True)
        self.calls += 1
        return self.output


class _Dtn:
    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = 2.0 * source.getArray(readonly=True)

    def apply_hermitian(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = (3.0 - 0.5j) * source.getArray(readonly=True)

    def compose_physical_rhs(self, base: PETSc.Vec, amplitudes: np.ndarray, target: PETSc.Vec) -> None:
        target.getArray()[:] = base.getArray(readonly=True) + amplitudes[0]


def test_m6b_outer_sum_and_complete_physical_rhs_without_global_matrix():
    volume = _Volume(np.asarray([1.0 + 0.1j, 2.0 - 0.2j]))
    dtn = _Dtn()
    context = M6BOuterMatPythonContext(volume, dtn, owned_rows=2, global_rows=2)
    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    base = source.duplicate()
    rhs = source.duplicate()
    source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
    base.getArray()[:] = [3.0, 4.0]
    try:
        context.mult(None, source, target)
        assert np.allclose(
            target.getArray(readonly=True),
            volume.values * source.getArray(readonly=True)
            + 2.0 * source.getArray(readonly=True),
        )
        compose_m6b_physical_rhs(dtn, base, np.asarray([0.25 + 0.5j]), rhs)
        assert np.allclose(rhs.getArray(readonly=True), base.getArray(readonly=True) + 0.25 + 0.5j)
        assert context.audit["global_matrix"] is False
        assert context.audit["augmented_matrix"] is False
        assert context.audit["explicit_C_materialized_count"] == 0
        source.getArray()[:] = [0.25 - 0.1j, 0.75 + 0.2j]
        context.mult(None, source, target)
        assert np.allclose(
            target.getArray(readonly=True),
            volume.values * source.getArray(readonly=True)
            + 2.0 * source.getArray(readonly=True),
        )
    finally:
        rhs.destroy()
        base.destroy()
        target.destroy()
        source.destroy()
        context.destroy()
        volume.output.destroy()


def test_m6b_outer_hermitian_adapter_composes_volume_and_dtn():
    volume = _Volume(np.asarray([1.0 + 0.1j, 2.0 - 0.2j]))
    adjoint_volume = _Volume(np.asarray([4.0 - 0.3j, 5.0 + 0.4j]))
    dtn = _Dtn()
    context = M6BOuterMatPythonContext(
        volume,
        dtn,
        owned_rows=2,
        global_rows=2,
        volume_hermitian_action=adjoint_volume,
    )
    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    try:
        source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
        context.apply_hermitian(source, target)
        assert np.allclose(
            target.getArray(readonly=True),
            adjoint_volume.values * source.getArray(readonly=True)
            + (3.0 - 0.5j) * source.getArray(readonly=True),
        )
        assert context.audit["hermitian_action_available"] is True
        assert context.audit["hermitian_apply_count"] == 1
    finally:
        target.destroy()
        source.destroy()
        context.destroy()
        adjoint_volume.output.destroy()
        volume.output.destroy()


def test_m6b_outer_mat_destroy_callback_is_idempotent_and_preserves_borrowed_output():
    volume = _Volume(np.asarray([1.0 + 0.1j, 2.0 - 0.2j]))
    dtn = _Dtn()
    matrix, context = build_m6b_outer_mat(
        volume,
        dtn,
        owned_rows=2,
        global_rows=2,
        comm=PETSc.COMM_SELF,
    )
    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    try:
        source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
        matrix.mult(source, target)
        matrix.destroy()
        context.destroy()
        assert volume.output.getSize() == 2
    finally:
        context.destroy()
        target.destroy()
        source.destroy()
        volume.output.destroy()


def test_m6b_petsc_pc_context_uses_unmeasured_core_apply():
    class Core:
        audit = {}

        def apply(self, values):
            return np.array(values, dtype=np.complex128, copy=True)

        def apply_with_measurement(self, _values):
            raise AssertionError("production PC path must not collect diagnostics")

    source = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
    target = source.duplicate()
    try:
        source.getArray()[:] = [1.0 + 0.2j, -0.5 + 0.1j]
        context = M6BShiftedPCContext(Core())
        context.apply(None, source, target)
        assert np.array_equal(target.getArray(readonly=True), source.getArray(readonly=True))
        assert context.audit["last_measurement"] is None
    finally:
        target.destroy()
        source.destroy()


def test_m6b_shared_volume_form_matches_physical_and_shifted_mass(tmp_path: Path):
    cfg = target_stage4_config(degree=1, h_nm=10.0)
    msh = mesh.create_unit_cube(
        MPI.COMM_SELF,
        2,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
    )
    cell_count = int(msh.topology.index_map(msh.topology.dim).size_local)
    tags = np.asarray(
        [cfg.tags.air, cfg.tags.substrate, cfg.tags.grating] * 3,
        dtype=np.int32,
    )[:cell_count]
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(cell_count, dtype=np.int32),
        tags,
    )
    facet_tags = mesh.meshtags(
        msh,
        msh.topology.dim - 1,
        np.empty(0, dtype=np.int32),
        np.empty(0, dtype=np.int32),
    )
    mesh_data = SimpleNamespace(mesh=msh, cell_tags=cell_tags, facet_tags=facet_tags)
    function_space = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 1, dtype=default_real_type),
    )
    old_ufl, _ = _build_variational_forms(msh, mesh_data, cfg, function_space)
    shared_cache = tmp_path / "shared"
    old_cache = tmp_path / "old"
    shared_cache.mkdir()
    old_cache.mkdir()
    (tmp_path / "delta").mkdir()
    import benchmarks.run_task037_extra_h2b as h2b

    jit_options = h2b._expected_jit_options(shared_cache)
    new0, epsilon0, abs_epsilon0, beta0, coverage0 = build_m6b_volume_form(
        function_space, mesh_data, cfg, beta=0.0
    )
    new1, epsilon1, abs_epsilon1, beta1, coverage1 = build_m6b_volume_form(
        function_space, mesh_data, cfg, beta=1.0
    )
    new05, epsilon05, abs_epsilon05, beta05, coverage05 = build_m6b_volume_form(
        function_space, mesh_data, cfg, beta=0.5
    )
    assert coverage0 == coverage1
    assert coverage0 == coverage05
    assert coverage0["owned_cell_count"] == cell_count
    assert coverage0["complete"] is True
    air_only_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(cell_count, dtype=np.int32),
        np.full(cell_count, cfg.tags.air, dtype=np.int32),
    )
    air_only_data = SimpleNamespace(
        mesh=msh, cell_tags=air_only_tags, facet_tags=facet_tags
    )
    air_only_coverage = m6b_material_tag_coverage(air_only_data, cfg)
    assert air_only_coverage["tag_counts"] == {
        "air": cell_count,
        "substrate": 0,
        "grating": 0,
    }
    compiled0 = fem.form(new0, jit_options=jit_options)
    compiled1 = fem.form(new1, jit_options=jit_options)
    compiled05 = fem.form(new05, jit_options=jit_options)
    state0, _ = h2b._form_code_state(compiled0.code)
    state1, _ = h2b._form_code_state(compiled1.code)
    state05, _ = h2b._form_code_state(compiled05.code)
    assert new0.signature() == new1.signature()
    assert new0.signature() == new05.signature()
    assert compiled0.module.__name__ == compiled1.module.__name__
    assert compiled0.module.__name__ == compiled05.module.__name__
    assert state0 == "cold_decl_impl_generated"
    assert state1 == "hit_no_new_decl_impl"
    assert state05 == "hit_no_new_decl_impl"
    old_form = fem.form(old_ufl, jit_options=h2b._expected_jit_options(old_cache))
    delta_ufl = (
        PETSc.ScalarType(1j * float(cfg.k0) ** 2)
        * beta1
        * abs_epsilon0
        * ufl.inner(ufl.TrialFunction(function_space), ufl.TestFunction(function_space))
        * ufl.Measure("dx", domain=msh)
    )
    delta_form = fem.form(
        delta_ufl, jit_options=h2b._expected_jit_options(tmp_path / "delta")
    )
    matrices = [
        fem_petsc.assemble_matrix(form)
        for form in (old_form, compiled0, compiled1, compiled05, delta_form)
    ]
    for matrix in matrices:
        matrix.assemble()
    old_matrix, new0_matrix, new1_matrix, new05_matrix, delta_matrix = matrices
    source = old_matrix.createVecRight()
    observed = old_matrix.createVecLeft()
    expected = old_matrix.createVecLeft()
    delta = old_matrix.createVecLeft()
    difference = old_matrix.createVecLeft()
    try:
        local = source.getArray()
        ids = np.arange(local.size, dtype=np.float64)
        local[:] = (1.0 + 0.013 * ids) + 1j * (0.35 - 0.007 * ids)
        old_matrix.mult(source, expected)
        new0_matrix.mult(source, observed)
        expected.copy(result=difference)
        difference.axpy(-1.0, observed)
        assert difference.norm() / max(expected.norm(), 1.0e-30) <= 1.0e-11
        new1_matrix.mult(source, observed)
        new0_matrix.mult(source, expected)
        delta_matrix.mult(source, delta)
        observed.copy(result=difference)
        difference.axpy(-1.0, expected)
        difference.axpy(-1.0, delta)
        assert difference.norm() / max(delta.norm(), 1.0e-30) <= 1.0e-11
        new05_matrix.mult(source, observed)
        new0_matrix.mult(source, expected)
        delta_matrix.mult(source, delta)
        observed.copy(result=difference)
        difference.axpy(-1.0, expected)
        difference.axpy(-0.5, delta)
        assert difference.norm() / max(delta.norm(), 1.0e-30) <= 1.0e-11
    finally:
        for vector in (source, observed, expected, delta, difference):
            vector.destroy()
        for matrix in matrices:
            matrix.destroy()
    with pytest.raises(ValueError, match="exactly 0, 0.5 or 1"):
        build_m6b_volume_form(function_space, mesh_data, cfg, beta=0.25)
    with pytest.raises(ValueError, match="no-PML"):
        build_m6b_volume_form(
            function_space,
            mesh_data,
            replace(cfg, use_pml=True),
            beta=0.0,
        )
    bad_cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(cell_count - 1, dtype=np.int32),
        tags[:-1],
    )
    bad_mesh_data = SimpleNamespace(
        mesh=msh, cell_tags=bad_cell_tags, facet_tags=facet_tags
    )
    with pytest.raises(ValueError, match="cover"):
        build_m6b_volume_form(
            function_space, bad_mesh_data, cfg, beta=0.0
        )


def test_m6b_shared_kernel_identity_is_phase_and_signature_bound():
    cfg = SimpleNamespace(
        use_pml=False,
        pml_top_thickness=0.0,
        pml_bottom_thickness=0.0,
        divergence_penalty=0.0,
    )
    outer = {
        "role": "outer_volume",
        "beta": 0.0,
        "beta_runtime_parameter": "fem.Constant",
        "operator_identity": runner.M6B_SHARED_VOLUME_OPERATOR,
        "representation": runner.M6B_SHARED_VOLUME_REPRESENTATION,
        "module_name": "libffcx_forms_synthetic",
        "ufl_signature": "shared-ufl",
        "ufcx_signature": "shared-ufcx",
        "code_state": "cold_decl_impl_generated",
    }
    shifted = dict(
        outer,
        role="shifted_volume",
        beta=runner.M6B_BETA,
        code_state="hit_no_new_decl_impl",
    )
    identity = runner._m6b_shared_kernel_identity(
        outer, shifted, cfg, phase="stage"
    )
    assert runner._m6b_shared_kernel_valid(identity, phase="stage") is True
    assert runner._m6b_form_records_bound(outer, shifted, identity, phase="stage") is True
    assert runner._m6b_shared_kernel_valid(identity, phase="unknown") is False
    for field, bad_value in {
        "module_name": "libffcx_forms_other",
        "ufl_signature": "different-ufl",
        "ufcx_signature": "different-ufcx",
        "code_state": "cold_decl_impl_generated",
        "operator_identity": "wrong-operator",
        "representation": "wrong-representation",
        "beta": 0.25,
        "beta_runtime_parameter": "python_float",
    }.items():
        tampered = dict(shifted)
        tampered[field] = bad_value
        assert (
            runner._m6b_form_records_bound(outer, tampered, identity, phase="stage")
            is False
        )
    bad_physics = copy.deepcopy(identity)
    bad_physics["fixed_physics"]["use_pml"] = True
    assert runner._m6b_form_records_bound(
        outer, shifted, bad_physics, phase="stage"
    ) is False


def test_m6b_runner_fixes_beta_half_without_beta_cli():
    assert runner.M6B_BETA == 0.5
    parser_source = inspect.getsource(runner._parser)
    assert "--beta" not in parser_source
    assert "beta_values" not in parser_source
    assert runner._parser().parse_args(
        ["m6b-worker", "--run-dir", "synthetic-run"]
    ).command == "m6b-worker"


def test_m6b_local_matrix_uses_beta_half_coefficient():
    curl = np.asarray([[2.0 + 0.2j, 0.1 - 0.3j]], dtype=np.complex128)
    mass = np.asarray([[0.5 - 0.1j, 0.2 + 0.4j]], dtype=np.complex128)
    epsilon = 2.0 + 0.75j
    k0 = 3.0
    observed = m6b_shifted_local_matrix(
        curl, mass, epsilon, k0, runner.M6B_BETA
    )
    expected = curl + k0**2 * (
        -epsilon + 1j * runner.M6B_BETA * abs(epsilon)
    ) * mass
    beta_one = m6b_shifted_local_matrix(curl, mass, epsilon, k0, 1.0)
    assert np.allclose(observed, expected, rtol=0.0, atol=1.0e-14)
    assert not np.allclose(observed, beta_one, rtol=0.0, atol=1.0e-14)


def test_m6b_form_record_removes_inherited_proxy_identity():
    class FakeH2B:
        @staticmethod
        def _form_record(*_args):
            return {
                "proxy_identity": {"operator": "B0"},
                "module_name": "libffcx_forms_synthetic",
                "ufl_signature": "synthetic-ufl",
                "ufcx_signature": "synthetic-ufcx",
            }

    action = SimpleNamespace(_action_form=object(), _action_ufl=object())
    record = runner._m6b_form_record(
        FakeH2B(),
        action,
        Path("/tmp/m6b-form-record-test-cache"),
        SimpleNamespace(),
        SimpleNamespace(),
        "outer_volume",
        0.0,
    )
    assert "proxy_identity" not in record
    assert record["role"] == "outer_volume"
    assert record["beta"] == 0.0
    assert record["beta_runtime_parameter"] == "fem.Constant"
    assert record["operator_identity"] == runner.M6B_SHARED_VOLUME_OPERATOR
    assert record["representation"] == runner.M6B_SHARED_VOLUME_REPRESENTATION
    assert record["module_name"] == "libffcx_forms_synthetic"
    assert record["ufl_signature"] == "synthetic-ufl"
    assert record["ufcx_signature"] == "synthetic-ufcx"


def _valid_worker_payload() -> dict[str, object]:
    lifecycle = {
        "return_code": 0,
        "termination": None,
        "processes_gone": True,
        "peak_rss_bytes": runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES - 1,
        "swap_bytes": 0,
        "compiler_descendant_pids": [],
        "watchdog_rss_limit_bytes": runner.M6B_WATCHDOG_RSS_LIMIT_BYTES,
        "completion_rss_limit_bytes": runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES,
        "timeout_seconds": runner.M6B_ONLINE_TIMEOUT_SECONDS,
    }
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
    }
    runtime = {
        "qualified_activation": "1",
        "sys_executable": "/tmp/repo/.venv/bin/python",
        "petsc_scalar_type": "complex128",
        "petsc_int_type": "int32",
        "threads": {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        "compiler": {"identity": "synthetic"},
        "mpi_size": 1,
    }
    probe_hashes = {
        "rhs_sha256": "b" * 64,
        "correction0_sha256": "c" * 64,
        "action_sha256": "d" * 64,
        "correction_sha256": "e" * 64,
        "residual_sha256": "f" * 64,
    }
    probe = {
        "wall_seconds": 1.0,
        "hashes": probe_hashes,
        "finite": True,
        "exact_shifted_action_count": 1,
        "partition_of_unity_closure_error": 0.0,
    }
    stage_lifecycle = dict(lifecycle)
    stage_lifecycle["timeout_seconds"] = runner.M6B_STAGE_TIMEOUT_SECONDS
    payload = {
        "schema": runner.M6B_WORKER_SCHEMA,
        "scope": runner._m6b_scope(phase="mpi1"),
        "p6": {
            "global_cells": runner.M6B_GLOBAL_CELLS,
            "local_cells": runner.M6B_GLOBAL_CELLS,
            "local_nloc": runner.M6B_LOCAL_NLOC,
            "global_rows": runner.M6B_GLOBAL_ROWS,
            "constraint_count": runner.M6B_CONSTRAINTS,
        },
        "source_at_start": source,
        "source_at_end": dict(source),
        "runtime_identity": runtime,
        "cache": {"stage": [], "before": [], "after": [], "final": [], "unchanged": True},
        "pc_repeat": {"first": probe, "second": copy.deepcopy(probe), "identical": True},
        "stage": stage_lifecycle,
        "online": dict(lifecycle),
        "factor_store": {
            "schema": "task037.extra.h2b.m6b.shifted-lu-store.v1",
            "beta": runner.M6B_BETA,
            "factor_order": 882,
            "factor_count": 84,
            "cell_count": 252,
            "factor_payload_bytes": runner.M6B_FACTOR_PAYLOAD_BYTES,
            "retained_total_bytes": runner.M6B_FACTOR_PAYLOAD_BYTES + 100,
            "retained_total_gate": True,
            "factor_reuse_count": 168,
            "factor_copy_count": 0,
            "mmap_loaded": True,
            "full_dense_patch_matrix_retained": False,
            "pivots_retained": True,
            "mmap_readonly": True,
            "max_live_patch_matrix_count": 1,
            "max_live_lu_factor_count": 1,
            "materialization_identity": {
                "global_matrix": False,
                "global_constraint_matrix": False,
                "patch_matrices": False,
                "per_cell_factor": False,
                "static_condensation": False,
                "trace_slab": False,
                "schur": False,
                "slab_factor": False,
            },
        },
        "screen": {
            "20": {"true_relative_residual": 0.50},
            "100": {"true_relative_residual": 0.10},
            "150": {"true_relative_residual": 0.10},
            "200": {"true_relative_residual": 0.05},
        },
        "architecture": {
            "global_matrix": False,
            "fine_space": "uncondensed_fullspace",
            "augmented_matrix": False,
            "static_condensation": False,
            "trace_slab_pc": False,
            "explicit_C_materialized_count": 0,
            "explicit_D_materialized_count": 0,
            "dtn": True,
            "pde": False,
        },
    }
    builder_factor = copy.deepcopy(payload["factor_store"])
    builder_factor["mmap_loaded"] = False
    builder_factor["mmap_readonly"] = False
    payload["builder_factor_audit"] = builder_factor
    screen_metadata = {
        "schema": "task037.extra.h2b.m6b.screen.v1",
        "rows": runner.M6B_GLOBAL_ROWS,
        "ksp_type": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart_set": 20,
        "max_it": 200,
        "max_it_actual": 200,
        "rtol": 0.0,
        "atol": 0.0,
        "iterations": 200,
        "converged_reason": -3,
        "fixed_screen": True,
        "operator_apply_count": 200,
        "pc_apply_count": 200,
        "sample_action_count": 4,
        "samples": copy.deepcopy(payload["screen"]),
    }
    pc_audit = {
        "schema": "task037.extra.h2b.m6b.shifted-patch-pc.v1",
        "beta": runner.M6B_BETA,
        "unique_factor_count": 84,
        "solve_count_per_apply": 84,
        "factor_reuse_count": 168,
        "factor_reuse_exercised": 168,
        "rhs_count": 252,
        "factor_copy_count": 0,
        "per_cell_solution_retained": False,
        "fine_space": "uncondensed_fullspace",
        "partition_of_unity_closure_error": 0.0,
        "materialization_identity": {
            "global_matrix": False,
            "global_constraint_matrix": False,
            "patch_matrices": False,
            "per_cell_factor": False,
            "static_condensation": False,
            "trace_slab": False,
            "schur": False,
            "slab_factor": False,
        },
    }
    payload["screen_metadata"] = screen_metadata
    payload["phase_source_identity"] = {
        "pass": True,
        "source_commit_full_sha": source["source_commit_full_sha"],
        "phase_names": ["stage", "builder", "online", "watchdog"],
        "all_tracked_source_clean": True,
    }
    shared_kernel = {
        "schema": runner.M6B_SHARED_VOLUME_SCHEMA,
        "phase": "mpi1",
        "operator_identity": runner.M6B_SHARED_VOLUME_OPERATOR,
        "representation": runner.M6B_SHARED_VOLUME_REPRESENTATION,
        "fixed_physics": {
            "use_pml": False,
            "pml_top_thickness": 0.0,
            "pml_bottom_thickness": 0.0,
            "divergence_penalty": 0.0,
            "material_representation": "DG0_epsilon_and_abs_epsilon",
        },
        "beta_runtime_parameter": "fem.Constant",
        "outer_beta": 0.0,
        "shifted_beta": runner.M6B_BETA,
        "module_name": "libffcx_forms_synthetic",
        "ufl_signature": "synthetic-shared-ufl",
        "ufcx_signature": "synthetic-shared-ufcx",
        "outer_code_state": "hit_no_new_decl_impl",
        "shifted_code_state": "hit_no_new_decl_impl",
        "same_module": True,
        "same_ufl_signature": True,
        "same_ufcx_signature": True,
    }
    outer_form = {
        "role": "outer_volume",
        "beta": 0.0,
        "beta_runtime_parameter": "fem.Constant",
        "operator_identity": runner.M6B_SHARED_VOLUME_OPERATOR,
        "representation": runner.M6B_SHARED_VOLUME_REPRESENTATION,
        "module_name": shared_kernel["module_name"],
        "ufl_signature": shared_kernel["ufl_signature"],
        "ufcx_signature": shared_kernel["ufcx_signature"],
        "code_state": "hit_no_new_decl_impl",
    }
    shifted_form = dict(outer_form, role="shifted_volume", beta=runner.M6B_BETA)
    material_tag_coverage = {
        "owned_cell_count": runner.M6B_GLOBAL_CELLS,
        "allowed_tag_values": {"air": 1, "substrate": 2, "grating": 3},
        "tag_counts": {"air": 84, "substrate": 84, "grating": 84},
        "complete": True,
    }
    payload["online_measurement"] = {
        "screen": copy.deepcopy(screen_metadata),
        "pc_audit": pc_audit,
        "shared_volume_kernel": shared_kernel,
        "form": {
            "outer_volume": outer_form,
            "shifted_volume": shifted_form,
            "shared_volume_kernel": shared_kernel,
        },
        "material_tag_coverage": material_tag_coverage,
    }
    return payload


def test_m6b_checker_and_screen_gate_fail_closed_on_missing_or_tampered_keys():
    valid = _valid_worker_payload()
    assert runner._m6b_check_payload(valid)["pass"] is True
    assert valid["online_measurement"]["screen"]["samples"] == valid["screen"]
    assert evaluate_m6b_screen_gate(
        valid["screen"],
        online_peak_rss_bytes=runner.M6B_ONLINE_COMPLETION_RSS_LIMIT_BYTES - 1,
        online_swap_bytes=0,
        processes_gone=True,
    )["pass"] is True
    missing = copy.deepcopy(valid)
    del missing["factor_store"]["factor_payload_bytes"]
    assert runner._m6b_check_payload(missing)["pass"] is False
    bad_screen = copy.deepcopy(valid)
    bad_screen["screen"]["200"]["true_relative_residual"] = 0.50
    assert runner._m6b_check_payload(bad_screen)["pass"] is False
    bad_arch = copy.deepcopy(valid)
    bad_arch["architecture"]["global_matrix"] = True
    assert runner._m6b_check_payload(bad_arch)["pass"] is False
    bad_phase_source = copy.deepcopy(valid)
    bad_phase_source["phase_source_identity"]["source_commit_full_sha"] = "0" * 40
    assert runner._m6b_check_payload(bad_phase_source)["pass"] is False


def test_m6b_screen_structure_is_separate_from_performance_gate():
    valid = _valid_worker_payload()
    negative = copy.deepcopy(valid)
    for key in ("20", "100", "150", "200"):
        negative["screen"][key]["true_relative_residual"] = 0.70
    negative["screen_metadata"]["samples"] = copy.deepcopy(negative["screen"])
    samples = negative["screen"]
    assert runner._m6b_screen_structure_valid(samples) is True
    assert runner._m6b_screen_metadata_valid(negative["screen_metadata"]) is True
    assert runner._m6b_screen_valid(samples) is False
    checked = runner._m6b_check_payload(negative)
    assert checked["checks"]["screen"] is False
    assert checked["pass"] is False

    missing = copy.deepcopy(samples)
    del missing["20"]
    assert runner._m6b_screen_structure_valid(missing) is False
    nonfinite = copy.deepcopy(samples)
    nonfinite["20"]["true_relative_residual"] = np.nan
    assert runner._m6b_screen_structure_valid(nonfinite) is False


def test_m6b_nonnegative_evidence_quantities_fail_closed():
    valid = _valid_worker_payload()
    bad_screen = copy.deepcopy(valid["screen"])
    bad_screen["20"]["true_relative_residual"] = -1.0
    assert runner._m6b_screen_structure_valid(bad_screen) is False
    assert runner._m6b_screen_valid(bad_screen) is False

    cfg = SimpleNamespace(
        use_pml=False,
        pml_top_thickness=0.0,
        pml_bottom_thickness=0.0,
        divergence_penalty=0.0,
    )
    online_form = valid["online_measurement"]["form"]
    builder_outer = dict(
        online_form["outer_volume"], code_state="cold_decl_impl_generated"
    )
    builder_shifted = dict(
        online_form["shifted_volume"], code_state="hit_no_new_decl_impl"
    )
    builder_shared = runner._m6b_shared_kernel_identity(
        builder_outer, builder_shifted, cfg, phase="stage"
    )
    builder = {
        "sample_patch_action_closure": {"0": 0.0, "42": 0.0, "83": 0.0},
        "class_block_audit": {
            "class_count": 24,
            "factor_count": 24,
            "reconstruction_count": 24,
            "fresh_B_beta_class_count": 24,
            "fresh_B_beta_matrix_count": 24,
            "operator_identity": runner.M6B_SHIFTED_OPERATOR,
            "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
            "r2_numeric_store_used_for_blocks": False,
            "global_matrix_materialized": False,
        },
        "cache": {"stage": [], "before": [], "after": [], "unchanged": True},
        "form": builder_shifted,
        "shared_volume_kernel": builder_shared,
        "material_tag_coverage": valid["online_measurement"][
            "material_tag_coverage"
        ],
    }
    assert runner._m6b_builder_summary_valid(builder) is True
    builder["sample_patch_action_closure"]["42"] = -1.0
    assert runner._m6b_builder_summary_valid(builder) is False

    bad_pc = copy.deepcopy(valid["online_measurement"]["pc_audit"])
    bad_pc["partition_of_unity_closure_error"] = -1.0
    assert runner._m6b_pc_audit_valid(bad_pc) is False

    for side in ("first", "second"):
        bad_repeat = copy.deepcopy(valid)
        bad_repeat["pc_repeat"][side]["partition_of_unity_closure_error"] = -1.0
        assert runner._m6b_check_payload(bad_repeat)["pass"] is False


def test_m6b_progress_constants_keep_dependency_order():
    assert runner.M6B_STAGE_EVENTS.index("proxy_forms_ready") < runner.M6B_STAGE_EVENTS.index(
        "outer_form_ready"
    ) < runner.M6B_STAGE_EVENTS.index("shifted_form_ready") < runner.M6B_STAGE_EVENTS.index(
        "surface_forms_ready"
    )
    assert runner.M6B_BUILDER_EVENTS.index("class_expansion_ready") < runner.M6B_BUILDER_EVENTS.index(
        "class_blocks_ready"
    ) < runner.M6B_BUILDER_EVENTS.index("neighborhood_ready")
    assert runner.M6B_ONLINE_EVENTS.index("cache_ready") < runner.M6B_ONLINE_EVENTS.index(
        "store_ready"
    )


def test_m6b_builder_and_online_require_stage_kernel(monkeypatch):
    valid = _valid_worker_payload()
    cfg = SimpleNamespace(
        use_pml=False,
        pml_top_thickness=0.0,
        pml_bottom_thickness=0.0,
        divergence_penalty=0.0,
    )
    online_form = valid["online_measurement"]["form"]
    builder_outer = dict(
        online_form["outer_volume"], code_state="cold_decl_impl_generated"
    )
    builder_shifted = dict(
        online_form["shifted_volume"], code_state="hit_no_new_decl_impl"
    )
    builder_shared = runner._m6b_shared_kernel_identity(
        builder_outer, builder_shifted, cfg, phase="stage"
    )
    builder = {
        "schema": runner.M6B_BUILDER_SCHEMA,
        "scope": runner._m6b_scope(phase="builder"),
        "status": "measurement_complete",
        "p6": valid["p6"],
        "runtime_identity": valid["runtime_identity"],
        "source_at_start": valid["source_at_start"],
        "source_at_end": valid["source_at_end"],
        "cache": {"stage": [], "before": [], "after": [], "unchanged": True},
        "factor_store": valid["factor_store"],
        "factor_audit": valid["builder_factor_audit"],
        "form": builder_shifted,
        "shared_volume_kernel": builder_shared,
        "material_tag_coverage": valid["online_measurement"][
            "material_tag_coverage"
        ],
        "class_block_audit": {
            "class_count": 24,
            "factor_count": 24,
            "reconstruction_count": 24,
            "fresh_B_beta_class_count": 24,
            "fresh_B_beta_matrix_count": 24,
            "operator_identity": runner.M6B_SHIFTED_OPERATOR,
            "numeric_matrix_source": "fresh_transformed_B_beta_class_block",
            "r2_numeric_store_used_for_blocks": False,
            "global_matrix_materialized": False,
        },
        "sample_patch_action_closure": {"0": 0.0, "42": 0.0, "83": 0.0},
    }
    online = copy.deepcopy(valid)
    online["status"] = "measurement_complete"
    process = {
        "timeline_metrics": {"peak_rss_bytes": 1, "swap_bytes": 0},
        "peak_rss_bytes": 1,
        "swap_bytes": 0,
        "processes_gone": True,
        "timeout_seconds": runner.M6B_BUILDER_TIMEOUT_SECONDS,
    }
    import benchmarks.run_task037_extra_h2b as h2b

    monkeypatch.setattr(runner, "_evidence_valid", lambda _value: True)
    monkeypatch.setattr(runner, "_m6b_lifecycle_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_m6b_progress_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_m6b_expected_p6", lambda _value: True)
    monkeypatch.setattr(h2b, "_runtime_valid", lambda _value: True)
    monkeypatch.setattr(h2b, "_source_pair_valid", lambda *_args: True)
    monkeypatch.setattr(h2b, "_cache_snapshot", lambda _path: [])
    assert runner._m6b_phase_gate(
        h2b,
        Path("."),
        builder,
        process,
        monitor_phase="builder",
        progress_phase="builder",
        expected_events=runner.M6B_BUILDER_EVENTS,
        compiler_must_be_empty=True,
        timeout_seconds=runner.M6B_BUILDER_TIMEOUT_SECONDS,
        stage_cache=[],
        stage_kernel=None,
    ) is False
    process["timeout_seconds"] = runner.M6B_ONLINE_TIMEOUT_SECONDS
    assert runner._m6b_phase_gate(
        h2b,
        Path("."),
        online,
        process,
        monitor_phase="online",
        progress_phase="mpi1",
        expected_events=runner.M6B_ONLINE_EVENTS,
        compiler_must_be_empty=True,
        timeout_seconds=runner.M6B_ONLINE_TIMEOUT_SECONDS,
        stage_cache=[],
        stage_kernel=None,
    ) is False


def test_m6b_builder_and_loaded_audits_are_distinct_producer_shapes():
    valid = _valid_worker_payload()
    loaded = valid["factor_store"]
    builder = valid["builder_factor_audit"]
    assert runner._m6b_loaded_factor_audit_valid(loaded) is True
    assert runner._m6b_builder_factor_audit_valid(builder) is True
    assert runner._m6b_loaded_factor_audit_valid(builder) is False
    assert runner._m6b_builder_factor_audit_valid(loaded) is False


def test_m6b_phase_source_identity_binds_all_producer_phases():
    source = {
        "source_commit_full_sha": "a" * 40,
        "tracked_source_dirty": False,
    }
    summaries = {
        name: {
            "source_at_start": dict(source),
            "source_at_end": dict(source),
        }
        for name in ("stage", "builder", "online", "watchdog")
    }
    assert runner._m6b_phase_source_identity(summaries) == {
        "pass": True,
        "source_commit_full_sha": "a" * 40,
        "phase_names": ["stage", "builder", "online", "watchdog"],
        "all_tracked_source_clean": True,
    }
    tampered_sha = copy.deepcopy(summaries)
    tampered_sha["builder"]["source_at_start"]["source_commit_full_sha"] = "b" * 40
    assert runner._m6b_phase_source_identity(tampered_sha)["pass"] is False
    tampered_dirty = copy.deepcopy(summaries)
    tampered_dirty["watchdog"]["source_at_end"]["tracked_source_dirty"] = True
    assert runner._m6b_phase_source_identity(tampered_dirty)["pass"] is False


def test_m6b_dynamic_prediction_replaces_builder_store_reserve():
    valid = _valid_worker_payload()
    retained = valid["factor_store"]["retained_total_bytes"]
    prediction = runner._dynamic_predicted_live_set(retained)
    assert prediction["basis"] == "builder factor_audit.retained_total_bytes"
    assert prediction["components"]["shifted_store_retained_total_bytes"] == retained
    assert "shifted_lu_factor_payload_bytes" not in prediction["components"]


def test_m6b_patch_closure_borrows_action_output_without_destroy():
    class BorrowedResult:
        def __init__(self, values):
            self.values = values

        def getArray(self, readonly=True):
            return self.values

    class BorrowedAction:
        def __init__(self):
            self.result = None

        def mult(self, source):
            values = np.zeros(4, dtype=np.complex128)
            values[[1, 3]] = source.getArray(readonly=True)[[1, 3]]
            self.result = BorrowedResult(values)
            return self.result

    source = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    action = BorrowedAction()
    try:
        assert runner._m6b_patch_closure(
            np.eye(2, dtype=np.complex128), [1, 3], action, source
        ) == 0.0
        assert action.result is not None
    finally:
        source.destroy()


def test_m6b_scope_prediction_and_parser_are_fixed():
    assert runner.M6B_FACTOR_PAYLOAD_BYTES == 1_045_826_208
    prediction = runner._predicted_live_set()
    assert prediction["is_measurement"] is False
    assert prediction["gate"] is True
    assert not hasattr(runner, "_not_ready")
    parser = runner._parser()
    assert parser.parse_args(["m6b-stage-worker", "--run-dir", "/tmp/m6b"]).command == "m6b-stage-worker"
    assert parser.parse_args(
        ["m6b-check", "--run-dir", "/tmp/m6b", "--output", "/tmp/m6b.json"]
    ).command == "m6b-check"


def test_m6b_command_preserves_qualified_interpreter_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resolved_interpreter = Path(runner.sys.executable).resolve()
    qualified_link = tmp_path / ".venv" / "bin" / "python"
    qualified_link.parent.mkdir(parents=True)
    qualified_link.symlink_to(resolved_interpreter)
    monkeypatch.setattr(runner.sys, "executable", str(qualified_link))

    command = runner._m6b_command("m6b-worker", tmp_path / "run")

    assert command[0] == str(qualified_link)
    assert command[0] != str(resolved_interpreter)
    assert command[1:5] == [
        "-m",
        "benchmarks.run_task037_extra_m6b",
        "m6b-worker",
        "--run-dir",
    ]
    assert command[5] == str((tmp_path / "run").resolve())
